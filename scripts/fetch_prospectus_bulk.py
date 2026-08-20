# -*- coding: utf-8 -*-
"""간이투자설명서(R3) 벌크 수집 — 판매중 전 클래스 8,445.

목적 (DATA_NEEDS ④·⑥·⑦): 클래스별 보수 수치 · 개방형/폐쇄형(환매) 문구 · 비정형 코퍼스.
방법: scripts/fetch_prospectus_targets.py (P2 선발대)와 동일 — funddoctor 결정적 URL.
  문서 URL: file.funddoctor.co.kr/app/file_download.asp?memb_cd=7070&file_gb=R3&pfund_cd={itm_no}
  ⚠️ 간이투자설명서는 발행 시점 문서(불변 자료) — 시계열 수치가 아니므로 7/11 제약과 충돌하지 않음.
     단 답변 근거로 쓸 때는 불변 사실(보수율 체계·환매 조건·클래스 구조)만 사용 (웹 수집 사용규칙과 동일).

산출: data/external/miraeasset_web/prospectus/{itm_no}_R3.pdf (+ .txt 텍스트 추출)
      data/external/miraeasset_web/prospectus_bulk_log.csv (코드별 상태 — 재실행 시 스킵 기준)
재실행 안전: 로그에 있는 코드 + 이미 존재하는 PDF 는 건너뜀.
"""
import csv
import sqlite3
import sys
import time
from pathlib import Path

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "external" / "miraeasset_web" / "prospectus"
PDF_DIR.mkdir(parents=True, exist_ok=True)
LOG_CSV = ROOT / "data" / "external" / "miraeasset_web" / "prospectus_bulk_log.csv"

URL = "https://file.funddoctor.co.kr/app/file_download.asp?memb_cd=7070&file_gb=R3&pfund_cd={cd}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
SLEEP = 1.0
LOG_FIELDS = ["itm_no", "status", "size", "note"]


def load_done():
    done = set()
    if LOG_CSV.exists():
        with open(LOG_CSV, encoding="utf-8-sig", newline="") as f:
            done = {r["itm_no"] for r in csv.DictReader(f)}
    return done


def extract_text(p: Path, max_pages=15):
    try:
        rd = PdfReader(str(p))
        t = "\n".join((pg.extract_text() or "") for pg in rd.pages[:max_pages])
        p.with_suffix(".txt").write_text(t, encoding="utf-8")
        return True
    except Exception:  # noqa: BLE001 — 파싱 실패는 로그로만
        return False


def main():
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'financial_products.db'}?mode=ro", uri=True)
    targets = [r[0] for r in con.execute(
        "SELECT DISTINCT itm_no FROM public_funds WHERE sale_yn='판매중' AND itm_no <> '\"' ORDER BY itm_no"
    )]
    done = load_done()
    todo = [t for t in targets if t not in done]
    print(f"대상 {len(targets)} · 로그상 완료 {len(done)} · 남음 {len(todo)}", flush=True)

    new_log = not LOG_CSV.exists()
    lf = open(LOG_CSV, "a", encoding="utf-8-sig", newline="")
    lw = csv.DictWriter(lf, fieldnames=LOG_FIELDS)
    if new_log:
        lw.writeheader()

    s = requests.Session()
    s.headers["User-Agent"] = UA
    ok = skip = miss = err = 0
    try:
        for i, cd in enumerate(todo, 1):
            p = PDF_DIR / f"{cd}_R3.pdf"
            if p.exists():
                if not p.with_suffix(".txt").exists():
                    extract_text(p)
                lw.writerow({"itm_no": cd, "status": "exists", "size": p.stat().st_size, "note": "P2 선발대 기수집"})
                skip += 1
                continue
            status, size, note = "error", 0, ""
            try:
                r = s.get(URL.format(cd=cd), timeout=40)
                if r.status_code == 200 and r.content.startswith(b"%PDF"):
                    p.write_bytes(r.content)
                    extract_text(p)
                    status, size = "ok", len(r.content)
                    ok += 1
                else:
                    status, note = "no_doc", f"HTTP {r.status_code} / PDF 아님"
                    miss += 1
            except Exception as e:  # noqa: BLE001
                note = str(e)[:80]
                err += 1
            lw.writerow({"itm_no": cd, "status": status, "size": size, "note": note})
            if i % 100 == 0:
                lf.flush()
                print(f"[{i}/{len(todo)}] ok {ok} · no_doc {miss} · exists {skip} · err {err}", flush=True)
            time.sleep(SLEEP)
    finally:
        lf.close()
    print(f"완료 — ok {ok} · no_doc {miss} · exists {skip} · err {err}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
