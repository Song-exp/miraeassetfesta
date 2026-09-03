# -*- coding: utf-8 -*-
"""라운드 채점 — 값·축·단위·범위 4열 + 이전 라운드 대비 회귀 (결과집합 기준).

🔴 회귀는 **SQL 문자열이 아니라 결과집합**으로 본다. HCX 는 같은 의미를 매번 다르게 쓰므로
   문자열 diff 를 회귀로 세면 노이즈가 실제 회귀를 덮는다 (2026-09-03 H2 검증에서 실측:
   SQL 문자열 7건 변경 중 결과집합이 실제로 달라진 것은 1건뿐이었다).

4열 (지시서 rule_delivery_audit §5 · 이관 절차 §4):
  값   생성 SQL 의 결과집합이 gold_sql 과 같은가        (gold_sql 있는 문항만)
  축   집계 단위가 맞는가 — 펀드 개수 질의에 펀드키가 쓰였는가
  단위 모수가 맞는가 — 펀드 집계·랭킹에 판매중·공모가 걸렸는가
  범위 SQL 이 실행되고 0행으로 무너지지 않았는가

사용:
  ./.venv/Scripts/python.exe eval/score_round.py eval/probe_all_2026-09-03_r17.json \
      --prev eval/probe_all_2026-09-03_r15.json
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.loader import connect_readonly  # noqa: E402
from eval.run_paired import rows_match  # noqa: E402  (관대 결과집합 비교 — 컬럼 순서 인공물 방지)

_FUNDKEY = re.compile(r"or_co_xtn_itt_cd.{0,200}mtco_itm_no", re.S | re.I)
_REFUSAL = ("확인할 수 없", "확인되지 않", "존재하지 않", "수록되어 있지 않", "제공되지 않", "없습니다")


# `10. [Plan] SQL 생성 — 아래 문장을 실행합니다` 다음 줄부터가 실행 SQL 이다.
_PLAN_SQL = re.compile(r"\[Plan\][^\n]*SQL 생성[^\n]*\n(.*?)(?=\n\d+\. \[|\Z)", re.S)
_STEP = re.compile(r"\n\d+\. \[")


def extract_sql(trace: str) -> str:
    """think_trace 에서 **실행된** SQL 을 뽑는다.

    🔴 "마지막 SELECT" 로 뽑으면 안 된다 — trace 뒤쪽 산문에 그 낱말이 또 나온다
       (`[Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 …)`). 2026-09-03 자기검증에서
       실측: 239문항 중 223문항이 그 산문을 SQL 로 뽑아 실행불가로 잡혔다(범위 6.7%).
       `[Plan] SQL 생성` 줄 **다음**을 읽는 것이 정본이고, 없으면 FROM 이 있는 SELECT 로 폴백한다.
    """
    if not trace:
        return ""
    m = _PLAN_SQL.search(trace)
    if m:
        return m.group(1).strip().rstrip(" ;")
    cands = [x.group(0).strip() for x in
             re.finditer(r"SELECT\b.*?(?=(?:\n\d+\. \[)|\Z)", trace, re.S | re.I)
             if re.search(r"\bfrom\s+[a-z_]+", x.group(0), re.I)]
    return (cands[-1] if cands else "").rstrip(" ;")


def rows(con, sql: str):
    try:
        return con.execute(sql).fetchmany(200)
    except sqlite3.Error:
        return None


def same_rows(a, b) -> bool:
    return {tuple(map(str, r)) for r in a} == {tuple(map(str, r)) for r in b}


def four_columns(con, question: str, sql: str, answer: str, gold_sql: str | None) -> dict:
    low = (sql or "").lower()
    fund = "public_funds" in low
    counting = any(w in question for w in ("몇 개", "개수", "몇개"))
    agg = bool(re.search(r"order\s+by|count\s*\(|sum\s*\(|avg\s*\(", low))
    got = rows(con, sql) if sql else None

    val = None
    if gold_sql:
        want = rows(con, gold_sql)
        # 🔴 전체 튜플 일치로 보면 안 된다 — HCX 가 gold 와 다른 컬럼을 첫 자리에 놓으면 의미가 맞아도
        #    불일치가 난다(run_paired 2026-08-31 정정). 그 관대 비교를 그대로 쓴다.
        val = got is not None and want is not None and rows_match(got, want)
    return {
        "값": val,
        "축": (bool(_FUNDKEY.search(sql or "")) if (fund and counting) else None),
        "단위": (("sale_yn" in low and "prvo_pbff_desc" in low) if (fund and agg) else None),
        # 범위 — SQL 이 없으면 거절 경로다. 거절 문구가 있으면 정상(불가응답), 없으면 무응답 실패.
        "범위": (any(m in (answer or "") for m in _REFUSAL) if not sql
                 else (got is not None and len(got) > 0)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("now")
    ap.add_argument("--prev", help="이전 라운드 JSON — 결과집합 기준 회귀 대조")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    con = connect_readonly()
    gold: dict[str, str] = {}
    for p in sorted((ROOT / "eval").glob("questions_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("gold_sql"):
                    gold[d["qid"]] = d["gold_sql"]

    now = {x["qid"]: x for x in json.loads(Path(a.now).read_text(encoding="utf-8"))}
    prev = ({x["qid"]: x for x in json.loads(Path(a.prev).read_text(encoding="utf-8"))}
            if a.prev else {})

    out: dict[str, dict] = {}
    for qid, x in now.items():
        sql = extract_sql(x.get("think_trace") or "")
        rec = {"q": x["question"], "sql": sql,
                "cols": four_columns(con, x["question"], sql, x.get("answer") or "", gold.get(qid))}
        if qid in prev:
            psql = extract_sql(prev[qid].get("think_trace") or "")
            pr, nr = rows(con, psql) if psql else None, rows(con, sql) if sql else None
            # 🔴 결과집합 기준 — 문자열이 달라도 결과가 같으면 변화 없음
            if pr is None and nr is None:
                rec["delta"] = "둘 다 SQL 없음/실행불가"
            elif pr is None:
                rec["delta"] = "개선(이전 실행불가 → 지금 실행)"
            elif nr is None:
                rec["delta"] = "🔴 회귀(이전 실행 → 지금 실행불가)"
            elif same_rows(pr, nr):
                rec["delta"] = "동일"
            else:
                rec["delta"] = "결과 달라짐"
            rec["prev_cols"] = four_columns(con, x["question"], psql,
                                            prev[qid].get("answer") or "", gold.get(qid))
        out[qid] = rec

    print(f"=== 4열 채점 — {Path(a.now).name} · {len(out)}문항 ===")
    print(f"  {'열':6s}{'통과/대상':>14s}{'비율':>9s}")
    for col in ("값", "축", "단위", "범위"):
        t = [v["cols"][col] for v in out.values() if v["cols"][col] is not None]
        k = sum(1 for x in t if x)
        print(f"  {col:6s}{f'{k}/{len(t)}':>14s}{(k/len(t)*100 if t else 0):>8.1f}%")

    if prev:
        print(f"\n=== 이전 라운드 대비 (결과집합 기준) — {Path(a.prev).name} ===")
        for k, n in Counter(v.get("delta") for v in out.values() if v.get("delta")).most_common():
            print(f"  {k:28s} {n:4d}")
        print("\n  열별 이전→지금 (공통 문항)")
        for col in ("값", "축", "단위", "범위"):
            pr = [(v["prev_cols"][col], v["cols"][col]) for v in out.values()
                  if v.get("prev_cols") and v["prev_cols"][col] is not None and v["cols"][col] is not None]
            b = sum(1 for o, x in pr if o and not x)
            c = sum(1 for o, x in pr if x and not o)
            print(f"    {col:6s} {sum(1 for o,_ in pr if o):3d}/{len(pr):3d} → "
                  f"{sum(1 for _,x in pr if x):3d}/{len(pr):3d}  회귀 {b} · 이득 {c}")

    path = a.out or str(ROOT / "eval" / (Path(a.now).stem + "_scored.json"))
    Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n산출 {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
