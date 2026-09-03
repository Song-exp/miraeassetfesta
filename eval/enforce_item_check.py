# -*- coding: utf-8 -*-
"""전환 항목 paired 검사 — 값·축·단위·범위 4열 (이관 절차 §4 항목별 통과 조건).

한 항목(슬롯 하나)을 켠 뒤, **그 슬롯을 끈 상태**와 같은 문항으로 대조한다.
채점은 값 일치만으로 하지 않는다(절차 §5) — 네 열로 나눈다:

  값   생성 SQL 의 결과집합이 gold_sql 과 같은가          (gold_sql 있는 문항만)
  축   집계 단위가 맞는가 — 펀드 개수 질의에 펀드키가 쓰였는가
  단위 모수가 맞는가 — 집계·랭킹에 판매중·공모가 걸렸는가
  범위 SQL 이 실행되는가 · 0행으로 무너지지 않았는가

🔴 HCX 는 **한 번만** 탄다. 슬롯은 raw_sql 에 대한 결정적 후처리라, 같은 raw_sql 로
   '슬롯 끈 상태'와 '켠 상태'를 둘 다 만들 수 있다. paired 의 짝이 완벽히 맞는다
   (HCX 비결정성이 두 팔에 섞이지 않는다 — run_paired 방식보다 이 점이 낫다).

사용: ./.venv/Scripts/python.exe eval/enforce_item_check.py --mark BASEPOP
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from src.runtime import guard, pipeline  # noqa: E402
from src.runtime.loader import connect_readonly, load_context  # noqa: E402
from src.runtime.router import route  # noqa: E402
from eval.enforce_shadow import load_questions  # noqa: E402
from eval.run_paired import mcnemar_exact_p, wilson  # noqa: E402

_FUNDKEY = re.compile(r"or_co_xtn_itt_cd.{0,160}mtco_itm_no", re.S | re.I)


def set_slot(ctx, mark: str, on: bool) -> None:
    for doc in ctx.enums.values():
        for rule in (doc.get("query_rules") or {}).values():
            enf = rule.get("enforce") if isinstance(rule, dict) else None
            if isinstance(enf, dict) and enf.get("mark") == mark:
                enf["enabled"] = on


def rows(con, sql: str):
    try:
        return con.execute(sql).fetchmany(200)
    except sqlite3.Error:
        return None


def four_columns(con, question: str, sql: str, gold_sql: str | None) -> dict:
    """값·축·단위·범위. 해당 없으면 None (분모에서 뺀다)."""
    low = (sql or "").lower()
    fund = "public_funds" in low
    counting = any(w in question for w in ("몇 개", "개수", "몇개"))
    agg = bool(re.search(r"order\s+by|count\s*\(|sum\s*\(|avg\s*\(", low))
    got = rows(con, sql) if sql else None

    val = None
    if gold_sql:
        want = rows(con, gold_sql)
        val = (got is not None and want is not None
               and {tuple(map(str, r)) for r in got} == {tuple(map(str, r)) for r in want})
    axis = bool(_FUNDKEY.search(sql or "")) if (fund and counting) else None
    unit = ("sale_yn" in low and "prvo_pbff_desc" in low) if (fund and agg) else None
    scope = (got is not None and len(got) > 0) if sql else False
    return {"값": val, "축": axis, "단위": unit, "범위": scope}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark", required=True, help="전환한 슬롯의 mark (BASEPOP·FUNDUNIT·IDXCANON)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    from src.hcx.planner import HCXPlanner

    qs = load_questions()
    if a.limit:
        qs = qs[: a.limit]
    con = connect_readonly()
    planner = HCXPlanner()

    ctx_off = copy.deepcopy(load_context())      # 이 슬롯만 끈 상태 (= 전환 전)
    set_slot(ctx_off, a.mark, False)
    ctx_on = copy.deepcopy(load_context())       # 리포 상태 (= 전환 후)

    out: dict[str, dict] = {}
    t0 = time.time()
    for q in qs:
        # HCX 1회 — raw_sql 을 받는다
        r = pipeline.answer_question(q["qid"], q["question"], planner=planner, ctx=ctx_on)
        raw = r.raw_sql or ""
        tables = route(q["question"], ctx_on).tables
        rec = {"q": q["question"], "gold": bool(q.get("gold_sql"))}
        for arm, ctx in (("off", ctx_off), ("on", ctx_on)):
            sql, fired = guard.apply_enforce(raw, q["question"], list(tables), set(), ctx)
            rec[arm] = {"sql": sql, "fired": fired,
                        **four_columns(con, q["question"], sql, q.get("gold_sql"))}
        out[q["qid"]] = rec
        d = "→" if rec["off"]["sql"] != rec["on"]["sql"] else " "
        print(f"  {q['qid']:16s} {d} {q['question'][:44]}")
    dt = time.time() - t0

    print(f"\n=== {a.mark} 전환 paired — 값·축·단위·범위 4열 ===")
    print(f"  {'열':6s}{'끔(전환 전)':>16s}{'켬(전환 후)':>16s}{'b':>5s}{'c':>5s}{'p':>9s}")
    summary = {}
    for col in ("값", "축", "단위", "범위"):
        pairs = [(v["off"][col], v["on"][col]) for v in out.values()
                 if v["off"][col] is not None and v["on"][col] is not None]
        n = len(pairs)
        ko = sum(1 for o, _ in pairs if o)
        kn = sum(1 for _, x in pairs if x)
        b = sum(1 for o, x in pairs if o and not x)      # 끔만 통과 = 회귀
        c = sum(1 for o, x in pairs if x and not o)      # 켬만 통과 = 이득
        p = mcnemar_exact_p(b, c)
        lo1, hi1 = wilson(ko, n) if n else (0, 0)
        lo2, hi2 = wilson(kn, n) if n else (0, 0)
        summary[col] = {"n": n, "off": ko, "on": kn, "b_regress": b, "c_gain": c, "p": round(p, 4),
                        "wilson_off": [round(lo1, 3), round(hi1, 3)],
                        "wilson_on": [round(lo2, 3), round(hi2, 3)]}
        print(f"  {col:6s}{f'{ko}/{n}':>16s}{f'{kn}/{n}':>16s}{b:>5d}{c:>5d}{p:>9.4f}")
    regress = {c: s["b_regress"] for c, s in summary.items() if s["b_regress"]}
    print(f"\n🔴 회귀(끔만 통과) — {regress or '없음'}  ← 어느 열이든 0 이 아니면 그 항목은 되돌린다")

    path = a.out or str(ROOT / "eval" / f"enforce_item_{a.mark}.json")
    Path(path).write_text(json.dumps({"mark": a.mark, "n": len(qs), "seconds": round(dt, 1),
                                      "summary": summary, "outcome": out},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"소요 {dt:.0f}초 → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
