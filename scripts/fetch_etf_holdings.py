# -*- coding: utf-8 -*-
"""국내 ETF·ETN 구성종목(Holdings) 전량 수집 — FunETF 공개 API.

방법·출처: data/external/holdings/SOURCES.md (커밋 6941fbb 에서 확립, 대표 20개 검증 완료)
  - 엔드포인트: GET https://www.funetf.co.kr/api/public/product/view/etfpdf
  - 기준일 etfPdfYmd=SNAP (2026-08-21 = 마스터 기준일 8/22 토요일의 마지막 영업일; 외부자료 ≤ 8/24 허용)
  - 인증 불필요(ROLE_ANONYMOUS) · 요청 간격 0.6초

대상: domestic_etfs 전량 1,734 (ETF 1,202 + ETN 532 — ETN 은 '구성종목 미제공' 응답 예상, 로그로 기록)
산출: data/external/holdings/domestic_holdings_20260710.csv  (SOURCES.md §5 스키마)
      data/external/holdings/fetch_log_20260710.csv          (코드별 상태 — 재실행 시 스킵 기준)
재실행 안전: fetch_log 에 있는 코드는 건너뜀 (중단 후 이어받기 가능).
"""
import csv
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "external" / "holdings"
OUT_DIR.mkdir(parents=True, exist_ok=True)
# 스냅샷 기준일 — 마스터 기준일 8/22(토) 의 마지막 영업일 8/21. 1차(7/10) 파일은 그대로 두고 별도 파일로 쌓는다.
SNAP = "20260821"
HOLDINGS_CSV = OUT_DIR / f"domestic_holdings_{SNAP}.csv"
LOG_CSV = OUT_DIR / f"fetch_log_{SNAP}.csv"

URL = "https://www.funetf.co.kr/api/public/product/view/etfpdf"
PARAMS_BASE = {
    "fid": "2ETF01",
    "etfPdfYmd": SNAP,
    "roleType": "ROLE_ANONYMOUS",
    "schCtenDvsn": "MK_VIEW",
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
SLEEP = 0.6
AS_OF = f"{SNAP[:4]}-{SNAP[4:6]}-{SNAP[6:]}"

HOLD_FIELDS = ["etf_code", "etf_name", "rank", "ticker", "constituent", "weight_pct", "quantity", "as_of"]
LOG_FIELDS = ["etf_code", "etf_name", "grp", "status", "n_rows", "note"]


def load_done():
    if not LOG_CSV.exists():
        return set()
    with open(LOG_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["etf_code"] for r in csv.DictReader(f)}


def open_appender(path, fields):
    new = not path.exists()
    f = open(path, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(f, fieldnames=fields)
    if new:
        w.writeheader()
    return f, w


def extract_rows(payload):
    """응답 JSON 에서 구성종목 리스트를 찾는다 — 리스트 위치가 래핑돼 있어도 탐색."""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and ("citmNm" in v[0] or "ticker" in v[0]):
                rows = v
                break
            if isinstance(v, dict):
                inner = extract_rows(v)
                if inner:
                    rows = inner
                    break
        rows = rows or []
    else:
        rows = []
    return [r for r in rows if isinstance(r, dict) and ("citmNm" in r or "ticker" in r)]


def main():
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'financial_products.db'}?mode=ro", uri=True)
    targets = con.execute(
        "SELECT pd_itm_no, TRIM(pd_abrv_nm), pd_grp_no FROM domestic_etfs "
        "ORDER BY du_last_aum DESC"
    ).fetchall()
    done = load_done()
    todo = [t for t in targets if t[0] not in done]
    print(f"대상 {len(targets)} · 완료 {len(done)} · 남음 {len(todo)}", flush=True)

    hf, hw = open_appender(HOLDINGS_CSV, HOLD_FIELDS)
    lf, lw = open_appender(LOG_CSV, LOG_FIELDS)
    s = requests.Session()
    s.headers["User-Agent"] = UA

    ok = empty = err = 0
    try:
        for i, (code, name, grp) in enumerate(todo, 1):
            status, n, note = "error", 0, ""
            try:
                r = s.get(URL, params={**PARAMS_BASE, "itemId": code}, timeout=30)
                if r.status_code == 200:
                    rows = extract_rows(r.json())
                    if rows:
                        for rank, h in enumerate(rows, 1):
                            hw.writerow({
                                "etf_code": code, "etf_name": name, "rank": rank,
                                "ticker": h.get("ticker", ""), "constituent": h.get("citmNm", ""),
                                "weight_pct": h.get("evP", ""), "quantity": h.get("icuStkc", ""),
                                "as_of": AS_OF,
                            })
                        status, n = "ok", len(rows)
                        ok += 1
                    else:
                        status, note = "empty", "구성종목 미제공 응답"
                        empty += 1
                else:
                    note = f"HTTP {r.status_code}"
                    err += 1
            except Exception as e:  # noqa: BLE001 — 개별 실패는 로그로 남기고 계속
                note = str(e)[:80]
                err += 1
            lw.writerow({"etf_code": code, "etf_name": name, "grp": grp,
                         "status": status, "n_rows": n, "note": note})
            if i % 25 == 0:
                hf.flush(); lf.flush()
                print(f"[{i}/{len(todo)}] ok {ok} · empty {empty} · err {err} (최근: {name} {status})", flush=True)
            time.sleep(SLEEP)
    finally:
        hf.close(); lf.close()
    print(f"완료 — ok {ok} · empty {empty} · err {err}", flush=True)
    return 0 if err < len(todo) else 1


if __name__ == "__main__":
    sys.exit(main())
