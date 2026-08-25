# -*- coding: utf-8 -*-
"""해외 ETF 구성종목 수집 — SEC EDGAR NPORT-P.

1단계: company_tickers_mf.json 으로 티커→(cik, seriesId, classId) 매핑
2단계: overseas_etfs AUM 상위 200 조인 → ticker_series_map.csv
3단계: 매칭 상위 N개 series 의 최신 NPORT-P(보고기준일 ≤ 2026-08-24) 구성종목 추출
"""
import csv, json, re, sqlite3, sys, time
from pathlib import Path
import xml.etree.ElementTree as ET
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "holdings_overseas"
OUT.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "miraeasset-festa-research contact@miraeassetfesta.example"}
AS_OF_LIMIT = "2026-08-24"  # 8/24 공지: 8/24까지 발행분 허용 (기존 7/11)
SLEEP = 0.2

session = requests.Session()
session.headers.update(UA)
_last = [0.0]

def get(url, **kw):
    wait = SLEEP - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    r = session.get(url, timeout=30, **kw)
    _last[0] = time.time()
    r.raise_for_status()
    return r

def step1_2(top_n=200):
    print("== step1: company_tickers_mf.json ==", flush=True)
    r = get("https://www.sec.gov/files/company_tickers_mf.json")
    j = r.json()
    fields = j["fields"]  # expect [cik, seriesId, classId, symbol]
    print("fields:", fields, "rows:", len(j["data"]))
    idx = {f: i for i, f in enumerate(fields)}
    sym_map = {}  # symbol -> list of (cik, seriesId, classId)
    for row in j["data"]:
        sym = str(row[idx["symbol"]]).upper().strip()
        sym_map.setdefault(sym, []).append(
            (row[idx["cik"]], row[idx["seriesId"]], row[idx["classId"]]))

    print("== step2: DB top", top_n, "join ==", flush=True)
    con = sqlite3.connect(f"file:{ROOT/'data'/'financial_products.db'}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("""select pd_itm_no, pd_abrv_nm, pd_us_cik, pd_isin_cd, du_last_aum
                   from overseas_etfs order by du_last_aum desc limit ?""", (top_n,))
    rows = cur.fetchall()
    con.close()

    out_rows, matched = [], 0
    for itm, abrv, db_cik, isin, aum in rows:
        ticker = (abrv or itm or "").upper().split(".")[0].strip()
        hits = sym_map.get(ticker, [])
        if hits:
            matched += 1
            cik, sid, clsid = hits[0]
            note = "multi" if len(hits) > 1 else ""
        else:
            cik, sid, clsid, note = "", "", "", ""
        out_rows.append(dict(ticker=ticker, db_cik=db_cik, sec_cik=cik,
                             seriesId=sid, classId=clsid, matched=bool(hits),
                             note=note, aum_usd=aum, isin=isin))
    p = OUT / "ticker_series_map.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader(); w.writerows(out_rows)
    print(f"match: {matched}/{len(rows)} = {matched/len(rows):.1%} -> {p}")
    return out_rows

NS = {"n": "http://www.sec.gov/edgar/nport"}
ATOM = {"a": "http://www.w3.org/2005/Atom"}

def nport_filings_for_series(series_id, count=8):
    """browse-edgar atom: 해당 series 의 NPORT-P (accession, cik, filing_date) 최신순."""
    url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
           f"&CIK={series_id}&type=NPORT-P&dateb=&owner=include&count={count}&output=atom")
    root = ET.fromstring(get(url).content)
    cik_el = root.find(".//a:company-info/a:cik", ATOM)
    cik = int(cik_el.text) if cik_el is not None else None
    out = []
    for e in root.findall(".//a:entry", ATOM):
        acc = e.find(".//a:accession-number", ATOM)
        fd = e.find(".//a:filing-date", ATOM)
        if acc is not None:
            out.append((acc.text.strip(), cik, fd.text.strip() if fd is not None else ""))
    return out

def parse_nport(cik, accession):
    """primary_doc.xml 파싱 → (series_id, rep_pd_date, holdings[])."""
    accn = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}"
    try:
        xml = get(f"{base}/primary_doc.xml").content
    except requests.HTTPError:
        idx = get(f"{base}/index.json").json()
        names = [i["name"] for i in idx["directory"]["item"] if i["name"].endswith(".xml")]
        xml = get(f"{base}/{names[0]}").content
    root = ET.fromstring(xml)
    gen = root.find(".//n:genInfo", NS)
    sid = gen.findtext("n:seriesId", default="", namespaces=NS)
    rep_dt = gen.findtext("n:repPdDate", default="", namespaces=NS)
    holds = []
    for inv in root.findall(".//n:invstOrSec", NS):
        name = inv.findtext("n:name", default="", namespaces=NS)
        lei = inv.findtext("n:lei", default="", namespaces=NS)
        cusip = inv.findtext("n:cusip", default="", namespaces=NS)
        bal = inv.findtext("n:balance", default="", namespaces=NS)
        pct = inv.findtext("n:pctVal", default="", namespaces=NS)
        try:
            pctf = float(pct)
        except ValueError:
            pctf = 0.0
        holds.append(dict(holding_name=name.strip(), lei=lei, cusip=cusip,
                          balance=bal, pct_val=pct, _pctf=pctf))
    holds.sort(key=lambda h: -h["_pctf"])
    return sid, rep_dt, holds

HOLD_COLS = ["etf_ticker", "seriesId", "report_date", "rank", "holding_name",
             "cusip", "lei", "pct_val", "balance", "accession"]

def step3(map_rows, top_n=20):
    """증분 저장 + 재개: 이미 수집된 티커는 건너뛰고, ETF 단위로 즉시 append."""
    print(f"== step3: NPORT-P holdings for top {top_n} matched ==", flush=True)
    targets = [r for r in map_rows if r["seriesId"]][:top_n]
    p = OUT / "overseas_holdings.csv"
    logp = OUT / "fetch_log.csv"
    done = set()
    if p.exists():
        with open(p, encoding="utf-8-sig") as f:
            done = {r["etf_ticker"] for r in csv.DictReader(f)}
    if logp.exists():
        with open(logp, encoding="utf-8-sig") as f:
            done |= {r["ticker"] for r in csv.DictReader(f) if r["status"] == "OK"}
    new_file = not p.exists()
    new_log = not logp.exists()
    fh = open(p, "a", newline="", encoding="utf-8-sig")
    wh = csv.DictWriter(fh, fieldnames=HOLD_COLS)
    if new_file:
        wh.writeheader()
    fl = open(logp, "a", newline="", encoding="utf-8-sig")
    wl = csv.writer(fl)
    if new_log:
        wl.writerow(["ticker", "seriesId", "status", "detail"])
    n_rows = n_ok = 0
    for t in targets:
        if t["ticker"] in done:
            continue
        done.add(t["ticker"])  # 상위 200 내 동일 티커 중복(예: SHV) 재수집 방지
        tkr, sid, rows_out, log = _collect_one(t)
        for r in rows_out:
            wh.writerow(r)
        n_rows += len(rows_out)
        n_ok += 1 if rows_out else 0
        for l in log:
            wl.writerow(l)
        fh.flush(); fl.flush()
    fh.close(); fl.close()
    print(f"done: +{n_ok} ETFs, +{n_rows} rows (skipped {len(done)} already done) -> {p}")

def _collect_one(t):
    """한 티커 수집 → (ticker, seriesId, holding rows, log rows)."""
    all_rows, log = [], []
    tkr, sid = t["ticker"], t["seriesId"]
    try:
        filings = nport_filings_for_series(sid)
        if not filings:
            log.append((tkr, sid, "FAIL", "no NPORT-P filings via series lookup"))
            print(f"  {tkr} {sid}: no filings", flush=True)
            return tkr, sid, all_rows, log
        picked = None  # (acc, rep_dt, holds) — repPdDate ≤ limit 중 최신 기준일
        for acc, cik, fdate in filings:
            got_sid, rep_dt, holds = parse_nport(cik, acc)
            if got_sid and got_sid != sid:
                log.append((tkr, sid, "WARN", f"seriesId mismatch in {acc}: {got_sid}"))
            if not rep_dt or rep_dt > AS_OF_LIMIT:
                print(f"  {tkr}: skip {acc} rep_pd={rep_dt} > {AS_OF_LIMIT}")
                continue
            if picked is None or rep_dt > picked[1]:
                picked = (acc, rep_dt, holds)
            if picked[1] >= "2026-03-31":  # 직전 분기 확보 → 충분히 최신
                break
        if not picked:
            log.append((tkr, sid, "FAIL", "no filing with repPdDate <= limit"))
            return tkr, sid, all_rows, log
        acc, rep_dt, holds = picked
        for rank, h in enumerate(holds, 1):
            all_rows.append(dict(etf_ticker=tkr, seriesId=sid, report_date=rep_dt,
                                 rank=rank, holding_name=h["holding_name"],
                                 cusip=h["cusip"], lei=h["lei"],
                                 pct_val=h["pct_val"], balance=h["balance"],
                                 accession=acc))
        log.append((tkr, sid, "OK", f"{rep_dt} {len(holds)} holdings ({acc})"))
        print(f"  {tkr} {sid}: {rep_dt} {len(holds)} holdings", flush=True)
    except Exception as ex:
        log.append((tkr, sid, "FAIL", f"{type(ex).__name__}: {ex}"))
        print(f"  {tkr} {sid}: FAIL {ex}", flush=True)
    return tkr, sid, all_rows, log

if __name__ == "__main__":
    n_map = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    n_hold = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    rows = step1_2(n_map)
    if n_hold:
        step3(rows, n_hold)
