# -*- coding: utf-8 -*-
"""미래에셋증권 펀드 상세 페이지 + 구성종목 전량 수집 (중단·재개 가능).

근거: docs/DATA_COLLECTION_PLAN.md §2 P1·P3 · 파일럿: notebooks/collect_miraeasset_web.ipynb

수집 범위
  Stage A (페이지): 당사취급(thco_sale_yn='Y') 전체 + 판매중(미취급 11) + fd_set_pcd='00' 전량
  Stage B (구성종목): 판매중 펀드의 클래스묶음(mtco_itm_no) 대표 1클래스 → a07.json
                      (구성종목은 펀드 수준 속성 — 형제 클래스는 동일하다고 가정)

재개: raw/*.html.gz · holdings_raw.jsonl 에 있는 대상은 재요청하지 않는다.
완료: FULL_CRAWL_DONE.json 마커 + fund_pages_full.csv · holdings_full.csv 산출.
⚠️ 페이지 값은 수집 시점 상태 — 불변 사실만 확정 근거. Holdings 는 as_of_ok(bas_dt ≤ 7/11)만 채택.
"""
import gzip
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "financial_products.db"
OUT = ROOT / "data" / "external" / "miraeasset_web"
RAW = OUT / "raw"
RAW.mkdir(parents=True, exist_ok=True)
HOLD_JSONL = OUT / "holdings_raw.jsonl"
FAIL_CSV = OUT / "failures.csv"
DONE_MARKER = OUT / "FULL_CRAWL_DONE.json"

BASE = "https://securities.miraeasset.com"
DETAIL = BASE + "/mw/mks/mks4116/p11.do"
HOLDINGS_EP = BASE + "/mw/mks/mks4116/a07.json"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1")
SLEEP = 0.6
AS_OF_LIMIT = "20260824"  # 8/24 공지: 8/24까지 발행분 허용 (기존 20260711)
RETRIEVED_AT = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
SRC_PAGE = "miraeasset_web(mks4116/p11.do)"
SRC_HOLD = "miraeasset_web(mks4116/a07.json)"

VAR_RE = re.compile(r'var\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"\n]*)"\s*;')
SETVAL_RE = re.compile(r'\$\("#(\w+)"\)\.(?:html|text)\("([^"\n]*)"\)')
MOFUND_RE = re.compile(r'[가-힣A-Za-z0-9()\-&/·]+모투자신탁(?:\([^)<"]*\))?')
KEEP = ["FDN", "ADMICN", "estd", "TFEE", "SLE_FEE", "ADMI_FEE", "TRST_FEE",
        "OFW_TRST_FEE", "NASST_SUM", "ESTP", "M1_BNFR", "M3_BNFR", "M6_BNFR",
        "M12_BNFR", "RPC_PHBT_YN", "RPC_FEE_EXP", "RPC_TGM_GIV", "PD_CLSS",
        "PD_TYP_CD", "fdStcCd", "spcDvCd", "unibusYn", "HAN_CLAS_NM",
        "dms_fo_dv_cd", "bfFeeexp", "feeYn", "fdClssLv"]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def new_session():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    return s


def record_failure(stage, key, err):
    new = not FAIL_CSV.exists()
    with FAIL_CSV.open("a", encoding="utf-8-sig") as f:
        if new:
            f.write("stage,key,error,at\n")
        f.write(f"{stage},{key},\"{str(err)[:120]}\",{datetime.now().isoformat()}\n")


def crawl_pages(con):
    rows = con.execute("""
        select distinct itm_no from public_funds
        where itm_no like 'KR%'
          and (thco_sale_yn='Y' or sale_yn='판매중' or fd_set_pcd='00')
        order by (sale_yn='판매중') desc, (thco_sale_yn='Y') desc, itm_no
    """).fetchall()
    targets = [r[0] for r in rows]
    todo = [t for t in targets if not (RAW / (t + ".html.gz")).exists()]
    log(f"Stage A 페이지 — 대상 {len(targets)} · 캐시 제외 {len(todo)}")

    s = new_session()
    fails = 0
    consec = 0
    for i, itm in enumerate(todo, 1):
        try:
            r = s.get(DETAIL, params={"fd_cd": itm}, timeout=25)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            (RAW / (itm + ".html.gz")).write_bytes(gzip.compress(r.text.encode("utf-8")))
            consec = 0
        except Exception as e:
            fails += 1
            consec += 1
            record_failure("page", itm, e)
            if consec >= 10:
                log(f"연속 실패 {consec} — 120초 대기 후 세션 재생성")
                time.sleep(120)
                s = new_session()
                consec = 0
        time.sleep(SLEEP)
        if i % 200 == 0:
            log(f"  pages {i}/{len(todo)} (실패 누적 {fails})")
    log(f"Stage A 완료 — 신규 {len(todo)} · 실패 {fails}")
    return len(targets), fails


def crawl_holdings(con):
    rows = con.execute("""
        select coalesce(mtco_itm_no, itm_no) grp, min(itm_no) rep
        from public_funds
        where sale_yn='판매중' and itm_no like 'KR%'
        group by grp order by grp
    """).fetchall()
    done = set()
    if HOLD_JSONL.exists():
        with HOLD_JSONL.open(encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["grp"])
                except Exception:
                    pass
    todo = [(g, rep) for g, rep in rows if g not in done]
    log(f"Stage B Holdings — 그룹 {len(rows)} · 캐시 제외 {len(todo)}")

    s = new_session()
    fails = 0
    consec = 0
    with HOLD_JSONL.open("a", encoding="utf-8") as f:
        for i, (grp, rep) in enumerate(todo, 1):
            try:
                r = s.post(HOLDINGS_EP,
                           data={"itm_no": rep, "all": "1", "stk_yn": "1",
                                 "bd_yn": "1", "drvs_yn": "1", "liqt_yn": "1"},
                           headers={"X-Requested-With": "XMLHttpRequest",
                                    "Referer": DETAIL + "?fd_cd=" + rep},
                           timeout=25)
                j = r.json()
                f.write(json.dumps({"grp": grp, "itm_no": rep,
                                    "bas_dt": j.get("bas_dt", ""),
                                    "returnCode": j.get("returnCode"),
                                    "grid": j.get("grid01", [])},
                                   ensure_ascii=False) + "\n")
                consec = 0
            except Exception as e:
                fails += 1
                consec += 1
                record_failure("holdings", rep, e)
                if consec >= 10:
                    log(f"연속 실패 {consec} — 120초 대기 후 세션 재생성")
                    time.sleep(120)
                    s = new_session()
                    consec = 0
            time.sleep(SLEEP)
            if i % 200 == 0:
                f.flush()
                log(f"  holdings {i}/{len(todo)} (실패 누적 {fails})")
    log(f"Stage B 완료 — 신규 {len(todo)} · 실패 {fails}")
    return len(rows), fails


def parse_page(itm_no, html):
    d = {}
    for m in VAR_RE.finditer(html):
        k, v = m.group(1), m.group(2)
        if k in KEEP and v:
            d[k] = v
    for m in SETVAL_RE.finditer(html):
        k, v = m.group(1), m.group(2)
        if k in KEEP and v and k not in d:
            d[k] = v
    ok = bool(d.get("FDN"))
    row = {"itm_no": itm_no, "page_ok": ok,
           "mo_fund_names": ";".join(sorted(set(MOFUND_RE.findall(html)))) if ok else ""}
    row.update({k: d.get(k, "") for k in KEEP})
    return row


def export(con):
    import pandas as pd

    log("파싱·적재 시작")
    rows = []
    files = sorted(RAW.glob("*.html.gz"))
    for i, p in enumerate(files, 1):
        html = gzip.decompress(p.read_bytes()).decode("utf-8", "replace")
        rows.append(parse_page(p.name[:-8], html))
        if i % 2000 == 0:
            log(f"  parse {i}/{len(files)}")
    df = pd.DataFrame(rows)
    df["retrieved_at"] = RETRIEVED_AT
    df["source"] = SRC_PAGE
    df["prospectus_url"] = ("https://file.funddoctor.co.kr/app/file_download.asp"
                            "?memb_cd=7070&file_gb=R2&pfund_cd=" + df["itm_no"])
    master = pd.read_sql("""
        select itm_no, max(std_itm_no) std_itm_no, max(itm_abrv_nm) itm_abrv_nm,
               max(or_co_xtn_itt_cd) or_co_xtn_itt_cd, max(fd_set_pcd) fd_set_pcd,
               max(pfiv_sale_cntl_tcd) pfiv_sale_cntl_tcd, max(or_attr_desc) or_attr_desc,
               max(cast(fd_nast_suma as real)) fd_nast_suma, max(sale_yn) sale_yn,
               max(coalesce(thco_sale_yn,'')) thco_sale_yn,
               max(coalesce(mtco_itm_no, itm_no)) grp
        from public_funds group by itm_no""", con)
    df = df.merge(master, on="itm_no", how="left")
    df.to_csv(OUT / "fund_pages_full.csv", index=False, encoding="utf-8-sig")
    log(f"fund_pages_full.csv — {len(df)}행 · page_ok {int(df.page_ok.sum())}")

    hrows = []
    if HOLD_JSONL.exists():
        with HOLD_JSONL.open(encoding="utf-8") as f:
            for line in f:
                try:
                    j = json.loads(line)
                except Exception:
                    continue
                for g in j.get("grid", []):
                    hrows.append({"grp": j["grp"], "itm_no": j["itm_no"],
                                  "bas_dt": j.get("bas_dt", ""),
                                  "isin": g.get("zrin_itm_bztp_cd"),
                                  "holding_nm": g.get("itm_bztp_nm"),
                                  "weight_pct": g.get("fd_wtrt"),
                                  "asset_type": g.get("ast_tp_nm"),
                                  "market": g.get("mkt_tcd_nm")})
    hdf = pd.DataFrame(hrows)
    if len(hdf):
        hdf["as_of_ok"] = hdf.bas_dt.astype(str) <= AS_OF_LIMIT
        hdf["retrieved_at"] = RETRIEVED_AT
        hdf["source"] = SRC_HOLD
        hdf.to_csv(OUT / "holdings_full.csv", index=False, encoding="utf-8-sig")
    n_grp = hdf.grp.nunique() if len(hdf) else 0
    log(f"holdings_full.csv — {len(hdf)}행 · 그룹 {n_grp}")
    return {"pages": len(df), "pages_ok": int(df.page_ok.sum()),
            "holdings_rows": len(hdf), "holdings_groups": int(n_grp),
            "holdings_asof_ok_rows": int(hdf.as_of_ok.sum()) if len(hdf) else 0}


def main():
    t0 = time.time()
    log(f"전량 수집 시작 — {ROOT}")
    con = sqlite3.connect(DB)
    n_pages, f_a = crawl_pages(con)
    n_groups, f_b = crawl_holdings(con)
    stats = export(con)
    stats.update({"page_targets": n_pages, "holding_groups_target": n_groups,
                  "fail_pages": f_a, "fail_holdings": f_b,
                  "elapsed_min": round((time.time() - t0) / 60, 1),
                  "retrieved_at": RETRIEVED_AT})
    DONE_MARKER.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    log(f"완료 {stats}")


if __name__ == "__main__":
    main()
