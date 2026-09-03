# -*- coding: utf-8 -*-
"""H2 처방 검증 — `종목단위` 문장 한정이 개별 조회를 다치지 않는가.

전달 감사 H2: `종목단위`(행 = itm_no)와 `펀드단위`(GROUP BY …)가 둘 다 always_on 이라
개수 질문에서 행 단위와 펀드 단위를 함께 지시받았다. 처방은 트리거로 내리는 것이 아니라
**문장을 자기 범위로 한정**하는 것이다 — triggered 로 내리면 클래스 어휘가 없는 개별 조회에서
행 단위 근거가 통째로 사라진다.

그래서 확인할 것 둘 (리드 지정 통과 조건):
  ① 개별 조회 21문항 — 회귀 0 (SQL·답변이 실질적으로 바뀌지 않는다)
  ② 개수 문항 4개(KG-025 · X9 · S8 · R1) — 대조. 나빠지지 않았는가

🔴 가드는 **켠 채로** 돈다. 이건 운영 형상의 회귀 검사지, 감사 §4-3 같은 순수 실험이 아니다.
🔴 HCX 를 문항당 2~3회 호출한다(25문항 × 2조건 ≈ 50질의). 팀이 챗봇을 쓰는 시간대엔 돌리지 말 것.

사용: ./.venv/Scripts/python.exe eval/check_h2_grain.py
"""
from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from src.runtime import pipeline  # noqa: E402
from src.runtime.loader import load_context  # noqa: E402

# 처방 전 문장 — 이 커밋에서 바뀐 그 한 줄
BEFORE = "행 = itm_no (dedup 불필요 — 2차)"


def read(path: Path) -> list[tuple[str, str]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            parts = line.split("\t")
            if len(parts) >= 2:
                out.append((parts[0], parts[1]))
    return out


def main() -> int:
    from src.hcx.planner import HCXPlanner

    solo = read(ROOT / "eval" / "probe_h2_solo.txt")
    cnt = read(ROOT / "eval" / "probe_h2_count.txt")
    qs = [("solo", q, t) for q, t in solo] + [("count", q, t) for q, t in cnt]
    planner = HCXPlanner()

    out: dict[str, dict] = {}
    t0 = time.time()
    for cond in ("before", "after"):
        # 🔴 load_context 는 @lru_cache — 사본을 만들지 않으면 두 조건이 같은 객체다
        ctx = copy.deepcopy(load_context())
        if cond == "before":
            ctx.enums["public_funds"]["query_rules"]["종목단위"] = BEFORE
        for kind, qid, question in qs:
            r = pipeline.answer_question(qid, question, planner=planner, ctx=ctx)
            out.setdefault(qid, {"kind": kind, "q": question})[cond] = {
                "sql": r.sql, "answer": (r.answer or "")[:400]}
            print(f"[{cond}] {qid:16s} {question[:44]}")
    dt = time.time() - t0

    # ── 판정 ──
    def norm(s: str | None) -> str:
        return " ".join((s or "").split()).lower()

    solo_changed = [q for q, v in out.items()
                    if v["kind"] == "solo" and norm(v["before"]["sql"]) != norm(v["after"]["sql"])]
    cnt_changed = [q for q, v in out.items()
                   if v["kind"] == "count" and norm(v["before"]["sql"]) != norm(v["after"]["sql"])]

    print(f"\n=== ① 개별 조회 {len(solo)}문항 — SQL 변경 {len(solo_changed)}건 ===")
    for q in solo_changed:
        print(f"  🔴 {q}: {out[q]['q'][:50]}")
        print(f"     before: {norm(out[q]['before']['sql'])[:160]}")
        print(f"     after : {norm(out[q]['after']['sql'])[:160]}")
    if not solo_changed:
        print("  ✅ 회귀 0 — 개별 조회 경로는 문장 한정에 영향받지 않는다")

    print(f"\n=== ② 개수 문항 {len(cnt)}개 대조 — SQL 변경 {len(cnt_changed)}건 ===")
    for _q, v in ((q, out[q]) for q in out if out[q]["kind"] == "count"):
        same = norm(v["before"]["sql"]) == norm(v["after"]["sql"])
        print(f"\n  [{_q}] {'동일' if same else '변경'} — {v['q'][:48]}")
        if not same:
            print(f"     before: {norm(v['before']['sql'])[:200]}")
            print(f"     after : {norm(v['after']['sql'])[:200]}")

    p = ROOT / "eval" / "h2_grain_check.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n소요 {dt:.0f}초 · 산출 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
