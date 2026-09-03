# -*- coding: utf-8 -*-
"""enforce 슬롯 섀도 실행 — 이관 절차 단계 2 (docs/guard_to_yaml_migration_2026-09-03.md §3).

목적: 슬롯과 코드 가드가 **같은 결과**를 내는지, 슬롯이 **가드가 못 닿던 곳(교차 가지)** 에서
발동하는지 확인한다. 전환(단계 3)의 통과 조건은 판정표의 **"둘 다 발동·SQL 다름" 이 0** 인 것.

🔴 슬롯은 리포에서 `enabled: false` 다. 여기서만 **인메모리로 켜서** 비교한다 — 배포 형상은 안 바뀐다.
🔴 HCX 는 **문항당 1회 경로**만 탄다(정상 파이프라인 1회). 슬롯 적용은 그 raw_sql 에 대한
   결정적 후처리라 두 번째 HCX 호출이 필요 없다. 이래서 섀도가 싸다.

판정 5분류 (절차 §3-3):
  둘 다 미발동 / 가드만 발동 / 슬롯만 발동 / 둘 다·동일 SQL / 둘 다·다른 SQL

사용: ./.venv/Scripts/python.exe eval/enforce_shadow.py [--limit N]
산출: eval/enforce_shadow_2026-09-03.json
"""
from __future__ import annotations

import argparse
import copy
import json
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

# ── 문항 셋 ────────────────────────────────────────────────────────────────
# 절차 §3-2 는 "15R ❌30 + ✅표본 30 + 공식 9 + 교차 25 = 94" 를 지정했다.
# ❌30·🟡11 은 리드가 qid 목록을 줬다. 나머지 둘은 목록이 없어 **재현 가능한 규칙**으로 뽑았다:
#   ✅표본 30 — probe_all_2026-09-03_r9.txt(239) 에서 ❌30·🟡11·교차분을 뺀 192개를 매 6번째로.
#   교차     — gold jsonl + probe r9 를 합친 354문항 중 gate.is_cross_query 가 참인 것 전량.
#             🔴 **13건뿐이다**(절차의 25가 아니다). 이 문항 풀에 교차질의가 그만큼 없다.
# 목록 파일을 갈아끼우면 그대로 지정 셋으로 돌아간다.
QID_FILES = ("qids_15R_fail.txt", "qids_15R_mid.txt", "qids_shadow_ok30.txt", "qids_shadow_cross.txt")


def load_questions() -> list[dict]:
    want: list[str] = []
    for f in QID_FILES:
        want += [l.strip() for l in (ROOT / "eval" / f).read_text(encoding="utf-8").splitlines() if l.strip()]
    gold: dict[str, dict] = {}
    for p in sorted((ROOT / "eval").glob("questions_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                gold.setdefault(d["qid"], d)
    probe: dict[str, str] = {}
    for p in sorted((ROOT / "eval").glob("probe_*.txt")):
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                probe.setdefault(parts[0], parts[1])
    out, seen = [], set()
    for qid in want:
        if qid in seen:
            continue
        seen.add(qid)
        if qid in gold:
            out.append({**gold[qid], "_src": "gold"})
        elif qid in probe:
            out.append({"qid": qid, "question": probe[qid], "_src": "probe"})
    return out


def enable_slots(ctx):
    """리포의 `enabled: false` 를 이 프로세스에서만 켠다. 파일은 건드리지 않는다."""
    on = []
    for t, doc in ctx.enums.items():
        for name, rule in (doc.get("query_rules") or {}).items():
            enf = rule.get("enforce") if isinstance(rule, dict) else None
            if isinstance(enf, dict) and enf.get("enabled") is False:
                enf["enabled"] = True
                on.append(f"{t}.{name}({enf.get('mark')})")
    return on


def rows_of(con, sql: str):
    try:
        return con.execute(sql).fetchmany(200)
    except sqlite3.Error:
        return None


def same_result(con, a: str, b: str) -> bool | None:
    """SQL 두 개가 같은 결과를 내는가. 둘 다 실행돼야 판정한다(하나라도 실패면 None)."""
    ra, rb = rows_of(con, a), rows_of(con, b)
    if ra is None or rb is None:
        return None
    return {tuple(str(x) for x in r) for r in ra} == {tuple(str(x) for x in r) for r in rb}


def norm(s: str | None) -> str:
    return " ".join((s or "").split()).lower()


def judge_one(qid, question, src, raw, guarded, ctx_slot, con) -> dict:
    """한 문항의 5분류 판정. raw_sql·guarded 만 있으면 되므로 재판정에 HCX 가 필요 없다."""
    tables = route(question, ctx_slot).tables
    slotted, fired = guard.apply_enforce(raw, question, tables, set(), ctx_slot)
    slotted_cmp = norm(slotted).split("/*m:")[0].strip()   # 표식 주석은 의미가 아니라 발동 흔적
    g_fired = norm(guarded) != norm(raw)
    s_fired = bool(fired)
    if not g_fired and not s_fired:
        verdict = "둘 다 미발동"
    elif g_fired and not s_fired:
        verdict = "가드만 발동"
    elif s_fired and not g_fired:
        verdict = "슬롯만 발동"
    elif norm(guarded) == slotted_cmp:
        verdict = "둘 다·동일 SQL"
    else:
        same = same_result(con, guarded, slotted) if raw else None
        verdict = ("둘 다·결과동일" if same else
                   ("둘 다·SQL 다름" if same is False else "둘 다·판정불가"))
    print(f"  {qid:16s} {verdict:14s} {question[:40]}")
    return {"q": question, "src": src, "verdict": verdict, "fired": fired,
            "raw_sql": raw, "guarded": guarded, "slotted": slotted}


def report(out, turned_on, dt, path, n) -> None:
    from collections import Counter
    tally = Counter(v["verdict"] for v in out.values())
    print("\n=== 판정표 (절차 §3-3) ===")
    for k, cnt in tally.most_common():
        print(f"  {k:16s} {cnt:4d}")
    hard = tally.get("둘 다·SQL 다름", 0)
    print(f"\n🔴 전환 통과 조건 — '둘 다·SQL 다름' = {hard} (0 이어야 단계 3 진행)")
    print(f"슬롯만 발동 {tally.get('슬롯만 발동', 0)}건 = 가드가 못 닿던 자리(이득 후보)")
    Path(path).write_text(json.dumps(
        {"generated": "2026-09-03", "n": n, "seconds": round(dt, 1),
         "slots_on": turned_on, "tally": dict(tally), "outcome": out},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n소요 {dt:.0f}초 → {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--replay", metavar="JSON",
                    help="저장된 결과의 raw_sql·guarded 로 **슬롯만 다시 적용**해 재판정 (HCX 0회). "
                         "슬롯 when/sql 을 고친 뒤 같은 문항으로 다시 재는 정상 경로다.")
    ap.add_argument("--out", default=str(ROOT / "eval" / "enforce_shadow_2026-09-03.json"))
    a = ap.parse_args()

    con = connect_readonly()
    ctx_slot = copy.deepcopy(load_context())        # 슬롯 판정용 사본
    turned_on = enable_slots(ctx_slot)

    if a.replay:
        prev = json.loads(Path(a.replay).read_text(encoding="utf-8"))
        print(f"재판정 — {a.replay} · 문항 {len(prev['outcome'])} · HCX 0회 · 슬롯 {turned_on}")
        out = {qid: judge_one(qid, v["q"], v.get("src", "?"), v["raw_sql"], v["guarded"],
                              ctx_slot, con) for qid, v in prev["outcome"].items()}
        report(out, turned_on, 0.0, a.out, len(out))
        return 0

    from src.hcx.planner import HCXPlanner

    qs = load_questions()
    if a.limit:
        qs = qs[: a.limit]
    planner = HCXPlanner()
    ctx_live = load_context()                       # 정상 경로 — 슬롯 off, 가드 on
    print(f"문항 {len(qs)} · 슬롯 {len(turned_on)}개 인메모리 점등: {turned_on}")

    out, t0 = {}, time.time()
    for q in qs:
        r = pipeline.answer_question(q["qid"], q["question"], planner=planner, ctx=ctx_live)
        out[q["qid"]] = judge_one(q["qid"], q["question"], q["_src"],
                                  r.raw_sql or "", r.sql or "", ctx_slot, con)
    report(out, turned_on, time.time() - t0, a.out, len(qs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
