# -*- coding: utf-8 -*-
"""수익률 형제 이탈 스캔 — 마이다스 패턴(기준가 기점 오류) 전수 탐지 (2026-08-31, 리드 지시).

시그니처: 같은 펀드(펀드단위 키)의 클래스인데 ① 2개 이상 기간에서 형제 중앙값과 ±3%p 안(정합)이면서
② 어떤 기간에서 |중앙값과의 차| > 50%p 이고 (배율 3배 이상 또는 부호 반전).
클래스 간 차이는 보수(연 1~2%p)뿐이므로 이 시그니처는 데이터 오류(기준가 기점·전환 처리)다.

확정 사례: 마이다스아시아리더스(H) Ce — 단기 3구간 소수점 정합 · 18개월+ ~27배 (검토기록 §13-1).
2클래스 펀드는 중앙값이 무의미해 대상 밖 — 미래에셋소비성장 C-e(1y 2.7배)처럼 손대조로만 잡힌다.

사용: python scripts/scan_return_anomalies.py [--csv out.csv]
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAD = "CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no ELSE substr('0000000' || mtco_itm_no, -7) END"
COLS = ["fd_mm1_ern_r", "fd_mm3_ern_r", "fd_mm6_ern_r", "fd_mm18_ern_r",
        "fd_yr1_ern_r", "fd_yr2_ern_r", "fd_yr3_ern_r", "fd_yr5_ern_r"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="")
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'financial_products.db'}?mode=ro", uri=True)
    rows = con.execute(
        f"SELECT or_co_xtn_itt_cd || '|' || COALESCE({PAD}, itm_no), itm_no, TRIM(itm_nm), sale_yn, "
        f"{', '.join(COLS)} FROM public_funds WHERE mtco_itm_no IS NOT NULL"
    ).fetchall()
    groups = defaultdict(list)
    for r in rows:
        groups[r[0]].append(r)

    flags = []
    for members in groups.values():
        if len(members) < 3:
            continue
        med = {}
        for i in range(len(COLS)):
            vals = [m[4 + i] for m in members if m[4 + i] is not None]
            if len(vals) >= 3:
                med[i] = statistics.median(vals)
        if len(med) < 3:
            continue
        for m in members:
            close = sum(1 for i in med if m[4 + i] is not None and abs(m[4 + i] - med[i]) <= 3)
            bad = []
            for i in med:
                v = m[4 + i]
                if v is None:
                    continue
                d = abs(v - med[i])
                if d > 50 and (abs(med[i]) < 1 or abs(v) > 3 * abs(med[i])
                               or abs(v) < abs(med[i]) / 3 or (v > 0) != (med[i] > 0)):
                    bad.append((COLS[i], v, round(med[i], 2)))
            if bad and close >= 2:
                flags.append((m[1], m[2], m[3], close, bad))

    flags.sort(key=lambda x: -max(abs(b[1] - b[2]) for b in x[4]))
    n_groups = sum(1 for v in groups.values() if len(v) >= 3)
    print(f"형제 3+ 그룹 {n_groups} · 플래그 클래스 {len(flags)}")
    for f in flags:
        worst = max(f[4], key=lambda b: abs(b[1] - b[2]))
        print(f"  {f[0]} [{f[2]}] 정합 {f[3]}기간 · 최대 이탈 {worst[0]} {worst[1]} (중앙값 {worst[2]}) — {f[1][:44]}")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.writer(fp)
            w.writerow(["itm_no", "itm_nm", "sale_yn", "close_periods", "column", "value", "sibling_median"])
            for f in flags:
                for b in f[4]:
                    w.writerow([f[0], f[1], f[2], f[3], *b])
        print(f"→ {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
