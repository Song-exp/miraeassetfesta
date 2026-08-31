# -*- coding: utf-8 -*-
"""채점기 — 4도메인 공용 (2026-08-31, HANDOFF §2-2 1).

문항별 판정:
  answer 문항   — 파이프라인 SQL 실행 결과 집합 == gold_sql 실행 결과 집합 (첫 컬럼 값, 순서 무시)
  거절/되묻기   — 답변이 거절·역질문 형(REFUSAL_MARKERS)이고 조회 결과를 근거로 내지 않았어야 한다
  must_include / must_not_include — 답변 텍스트 검사 (HCX 모드에서만 — fake 답변은 텍스트가 없다)

자체 검증(기본): **가짜 플래너에 gold_sql 을 물려** 돌린다 — answer 문항이 100% 가 아니면
채점기(또는 게이트·가드가 gold 를 막는 회귀)가 잘못된 것이므로 exit 1.
🔴 이때 게이트/가드가 gold_sql 을 기각하면 그 자체가 발견이다 — 채점기는 그것을 실패로 보고한다.

HCX 모드: --planner hcx (HCX ~문항 수 × 2회 호출 — 평가 기간엔 돌리지 말 것).

사용:
  python eval/run_score.py                       # 자체 검증 (HCX 0회)
  python eval/run_score.py --planner hcx         # 실채점
  python eval/run_score.py --only 펀드           # category 부분일치 필터
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.loader import connect_readonly, load_context   # noqa: E402
from src.runtime.pipeline import answer_question   # noqa: E402

REFUSAL_MARKERS = ("확인할 수 없", "확인되지 않", "존재하지 않", "수록되어 있지 않",
                   "제공되지 않", "미수록", "답변을 제공할 수 없", "?")


class GoldPlanner:
    """가짜 플래너 — plan_sql 이 gold_sql 을 그대로 낸다. compose 는 행 유무만 말한다 (HCX 0회)."""

    def __init__(self):
        self.gold_sql = None

    def plan_sql(self, question, grounding):
        return self.gold_sql or "SELECT 1 WHERE 0 LIMIT 1"

    def compose_answer(self, question, rows, answer_rules=""):
        return f"[fake] rows={'yes' if rows.strip() else 'no'}"


def result_set(con, sql):
    try:
        rows = con.execute(sql).fetchmany(200)
    except sqlite3.Error:
        return None
    return frozenset(str(r[0]).strip() for r in rows)


def score_one(q: dict, r, con, hcx: bool) -> tuple[bool, str]:
    """(정답 여부, 사유). expected_behavior 별 판정 + (HCX 모드) must 검사."""
    beh = q.get("expected_behavior", "answer")
    ans = r.answer or ""
    if beh == "answer":
        if not q.get("gold_sql"):
            return False, "gold_sql 없음(answer 문항)"
        if not r.sql:
            return False, f"SQL 미생성 — trace 말미: {r.think_trace.splitlines()[-1][:80] if r.think_trace else ''}"
        got, want = result_set(con, r.sql), result_set(con, q["gold_sql"])
        if got is None:
            return False, "생성 SQL 실행 실패"
        if got != want:
            return False, f"결과 집합 불일치 (생성 {len(got)} vs gold {len(want or ())})"
    else:  # reject / clarify / reject_or_clarify / reject_or_partial …
        refused = any(m in ans for m in REFUSAL_MARKERS)
        grounded_rows = bool(r.retrieved_context.strip()) if getattr(r, "retrieved_context", "") else False
        if "partial" in beh and not refused:
            pass  # partial 허용 — 값 제시 답변도 인정
        elif not refused:
            return False, "거절/되묻기 형이 아님"
        elif grounded_rows and "partial" not in beh:
            return False, "거절인데 조회 결과를 근거로 냄"
    if hcx:
        for m in q.get("must_include") or []:
            if m not in ans:
                return False, f"must_include 누락: {m!r}"
        for m in q.get("must_not_include") or []:
            if m in ans:
                return False, f"must_not_include 포함: {m!r}"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", choices=["fake", "hcx"], default="fake")
    ap.add_argument("--only", default="", help="category 부분일치 필터")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    qs = []
    for f in sorted(glob.glob(str(ROOT / "eval" / "questions_*.jsonl"))):
        qs += [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    if a.only:
        qs = [q for q in qs if a.only in q.get("category", "")]

    ctx = load_context()
    con = connect_readonly()
    hcx = a.planner == "hcx"
    if hcx:
        from src.hcx.planner import HCXPlanner
        planner = HCXPlanner()
    else:
        planner = GoldPlanner()

    by_cat: dict[str, list] = defaultdict(list)
    fails = []
    for q in qs:
        if not hcx:
            planner.gold_sql = q.get("gold_sql")
        r = answer_question(q["qid"], q["question"], planner=planner, ctx=ctx)
        ok, why = score_one(q, r, con, hcx)
        by_cat[q.get("category", "?")].append(ok)
        if not ok:
            fails.append((q["qid"], q.get("expected_behavior", "answer"), why, q["question"][:36]))
        print(f"{'✅' if ok else '❌'} {q['qid']:>10} [{q.get('expected_behavior','answer'):>17}] {q['question'][:40]}"
              + (f"  ← {why}" if why else ""))

    print()
    total_ok = sum(sum(v) for v in by_cat.values())
    total = sum(len(v) for v in by_cat.values())
    for cat in sorted(by_cat):
        v = by_cat[cat]
        print(f"  {cat:24} {sum(v)}/{len(v)}")
    print(f"합계 {total_ok}/{total} = {total_ok / max(total, 1):.1%}  (planner={a.planner})")
    if fails:
        print("\n실패 목록:")
        for qid, beh, why, qq in fails:
            print(f"  {qid} [{beh}] {why} — {qq}")
    if a.out:
        Path(a.out).write_text(json.dumps({qid: why for qid, _, why, _ in fails} | {"total": f"{total_ok}/{total}"},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
    # 자체 검증 모드: answer 문항은 gold 를 물렸으니 전부 맞아야 한다.
    # 거절형은 게이트가 잡는 것만 맞는다(플래너 되묻기는 fake 로 재현 불가) — answer 실패만 exit 에 반영.
    if not hcx:
        answer_fail = [f for f in fails if f[1] == "answer"]
        if answer_fail:
            print(f"\n🔴 자체 검증 실패 — answer 문항 {len(answer_fail)}건: 채점기 또는 게이트/가드의 gold 기각 회귀")
            return 1
        print(f"\n자체 검증 통과 — answer 문항 전부 정답. 거절형 미달 {len(fails)}건은 플래너 필요(needs_hcx) 분류와 대조할 것")
    return 0


if __name__ == "__main__":
    sys.exit(main())
