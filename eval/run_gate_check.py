# -*- coding: utf-8 -*-
"""오프라인 게이트 회귀 — HCX 없이 전 문항을 Route·Ground·Gate 까지 돌려 두 가지를 검사한다 (2026-08-30 R-8).

  ① 거절형 문항 중 **게이트 층(①)** 유형(enum_unknown · enum_no_data · attribute_absent · constant_violation)은
     게이트가 기각해야 한다 — HCX 호출 0회가 정답 경로.
  ② 답변형(expected_behavior=answer) 문항은 게이트가 **기각하면 안 된다** — 오거절은 정답 문항을 버리는 것.
     (PROJECT.md: 답변 가능 문항에 거절 오발동 = 오답)

거절 유형(refusal_type)은 eval/*.jsonl 에 라벨돼 있다. ②·③ 층(REFUSE·CLARIFY·0행)은 HCX 가 필요하므로 여기선 세지 않고
run_paired.py 가 다룬다.

사용: python eval/run_gate_check.py            # 종료코드 1 = 회귀 실패
"""
from __future__ import annotations

import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.loader import load_context   # noqa: E402
from src.runtime.pipeline import answer_question   # noqa: E402

GATE_TIER = {"enum_unknown", "enum_no_data", "attribute_absent", "constant_violation"}


def load_questions() -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(ROOT / "eval" / "questions_*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> int:
    ctx = load_context()
    qs = load_questions()
    fails: list[str] = []
    tally: Counter = Counter()
    for q in qs:
        r = answer_question(q["qid"], q["question"], planner=None, ctx=ctx)
        gated = "[Gate] 기각" in r.think_trace
        beh = q.get("expected_behavior", "answer")
        rtype = q.get("refusal_type", "")
        if beh == "answer":
            tally["answer"] += 1
            if gated:
                fails.append(f"❌ 오거절 {q['qid']}: {q['question'][:50]} — {[l for l in r.think_trace.splitlines() if '[Gate]' in l][0][:120]}")
        elif rtype in GATE_TIER:
            tally[f"gate:{rtype}"] += 1
            if not gated:
                fails.append(f"❌ 미기각 {q['qid']} ({rtype}): {q['question'][:50]}")
        else:
            tally[f"needs_hcx:{rtype or beh}"] += 1
    print("문항", len(qs), "·", dict(tally))
    for f in fails:
        print(f)
    print(f"{'✅ 게이트 회귀 통과' if not fails else f'❌ 실패 {len(fails)}건'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
