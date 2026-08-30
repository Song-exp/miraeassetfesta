# -*- coding: utf-8 -*-
"""paired 실험 — 같은 문항을 두 설정으로 돌려 McNemar b/c 와 Wilson 95% CI 를 낸다 (2026-08-30 R-8 · SL-1 §4.4 방식).

설정은 환경변수 RULES_MODE 로 고른다 (pipeline.build_grounding 이 읽는다):
  full     — 도메인 규칙 전부 주입 (종전)
  layered  — triggered 규칙은 질문 어휘가 있을 때만 (R-2)
정답 판정:
  answer 문항  — 생성 SQL 의 실행 결과 집합 == gold_sql 실행 결과 집합 (순서 무시, 컬럼 무시하고 첫 컬럼 값 집합 비교)
  거절형 문항  — 답변이 확인불가/되묻기/REFUSE 형이면 정답 (retrieved_context 가 비어 있어야 한다)
🔴 HCX 를 문항당 최대 2~3회 호출한다 (63문항 × 2설정 ≈ 130~190회). 평가 기간엔 돌리지 말 것.

사용: python eval/run_paired.py [--modes full,layered] [--limit N] [--out eval/paired_result.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.loader import connect_readonly, load_context   # noqa: E402
from src.runtime.pipeline import answer_question   # noqa: E402

REFUSAL_MARKERS = ("확인할 수 없", "확인되지 않", "존재하지 않", "수록되어 있지 않", "제공되지 않", "?")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_exact_p(b: int, c: int) -> float:
    """두 설정의 불일치 개수 b(A만 정답)·c(B만 정답) — 양측 정확 이항검정."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def result_set(con: sqlite3.Connection, sql: str) -> frozenset | None:
    try:
        rows = con.execute(sql).fetchmany(200)
    except sqlite3.Error:
        return None
    return frozenset(str(r[0]).strip() for r in rows)


def judge(q: dict, r, con) -> bool:
    beh = q.get("expected_behavior", "answer")
    if beh == "answer":
        if not q.get("gold_sql") or not r.sql:
            return False
        got, want = result_set(con, r.sql), result_set(con, q["gold_sql"])
        return got is not None and want is not None and got == want
    # 거절형 — 답변이 거절/되묻기이고 조회 결과를 근거로 내지 않았어야 한다
    return any(m in r.answer for m in REFUSAL_MARKERS) and not r.retrieved_context.strip().count("\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="full,layered")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "eval" / "paired_result.json"))
    a = ap.parse_args()
    modes = a.modes.split(",")
    from src.hcx.planner import HCXPlanner   # HCX 키 필요
    qs = []
    for f in sorted((ROOT / "eval").glob("questions_*.jsonl")):
        qs += [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    if a.limit:
        qs = qs[: a.limit]
    ctx = load_context()
    con = connect_readonly()
    planner = HCXPlanner()
    outcome: dict[str, dict[str, bool]] = {}
    for m in modes:
        os.environ["RULES_MODE"] = m
        for q in qs:
            r = answer_question(q["qid"], q["question"], planner=planner, ctx=ctx)
            outcome.setdefault(q["qid"], {})[m] = judge(q, r, con)
            print(f"[{m}] {q['qid']} {'✅' if outcome[q['qid']][m] else '❌'} {q['question'][:40]}")
    n = len(qs)
    for m in modes:
        k = sum(1 for v in outcome.values() if v.get(m))
        lo, hi = wilson(k, n)
        print(f"{m}: {k}/{n} = {k / n:.1%}  Wilson95 [{lo:.1%}, {hi:.1%}]")
    if len(modes) == 2:
        A, B = modes
        b = sum(1 for v in outcome.values() if v.get(A) and not v.get(B))
        c = sum(1 for v in outcome.values() if v.get(B) and not v.get(A))
        print(f"McNemar {A}-only {b} · {B}-only {c} · exact p = {mcnemar_exact_p(b, c):.4f}"
              + ("  (CI 겹침 — 차이 없음으로 기록)" if abs(b - c) < 3 else ""))
    Path(a.out).write_text(json.dumps(outcome, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
