# -*- coding: utf-8 -*-
"""규칙 전달 감사 — yaml query_rules 가 HCX 프롬프트에 어떤 형태·분량·조합으로 실리는지 측정.

작업 지시서: docs/rule_delivery_audit_2026-09-03.md §4-1 · §4-2. **HCX 0회 · 측정만 · yaml·코드 수정 없음.**

  §4-1 트리거 커버리지 — triggered 규칙이 문항마다 실렸는가 / 안 실렸는가 (H1, H4)
  §4-2 모순·중복·과량 — always_on 동시 주입, 블록 분량, 사고 이력·부정문 (H2, H4)

사용: ./.venv/Scripts/python.exe eval/rule_delivery_audit.py
산출: eval/rule_delivery_trigger.json · eval/rule_delivery_volume.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.loader import TABLES, load_context  # noqa: E402
from src.runtime.router import route  # noqa: E402

ctx = load_context()

# ── 문항 셋 ①~④ — 지시서 4-0. gold 전량 + 공식 예시. qid 에 도메인이 들어 있다 ──
QFILES = sorted((ROOT / "eval").glob("questions_*.jsonl"))
QUESTIONS: list[dict] = []
for p in QFILES:
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            d["_file"] = p.stem.replace("questions_", "")
            QUESTIONS.append(d)
print(f"문항 {len(QUESTIONS)}건 · 파일 {len(QFILES)}개")


def rules_of(table: str) -> dict:
    return (ctx.enums.get(table) or {}).get("query_rules") or {}


def is_triggered(rule) -> bool:
    return isinstance(rule, dict) and "triggers" in rule


def rule_text(rule) -> str:
    if isinstance(rule, dict):
        return str(rule.get("text", ""))
    return str(rule)


# ══════════════════════════════════════════════════════════════════════
# §4-1. 트리거 커버리지
# ══════════════════════════════════════════════════════════════════════
# 라우팅이 그 테이블을 고른 문항만 모수다 — 라우팅에서 빠진 규칙은 트리거 문제가 아니다.
trig_rows: list[dict] = []
per_rule: dict[tuple[str, str], dict] = {}

for t in TABLES:
    for name, rule in rules_of(t).items():
        if str(name).startswith("_") or not is_triggered(rule):
            continue
        per_rule[(t, name)] = {
            "table": t, "rule": name,
            "triggers": [str(w) for w in (rule.get("triggers") or [])],
            "text_len": len(rule_text(rule)),
            "routed": 0, "fired": [], "missed": [],
        }

for q in QUESTIONS:
    question = q.get("question") or ""
    r = route(question, ctx)
    q_cf = question.casefold()
    for (t, name), rec in per_rule.items():
        if t not in r.tables:
            continue
        rec["routed"] += 1
        hit = [w for w in rec["triggers"] if w.casefold() in q_cf]
        (rec["fired"] if hit else rec["missed"]).append(
            {"qid": q.get("qid"), "q": question, "hit": hit})

for rec in per_rule.values():
    trig_rows.append({
        **{k: rec[k] for k in ("table", "rule", "triggers", "text_len", "routed")},
        "n_fired": len(rec["fired"]), "n_missed": len(rec["missed"]),
        "fire_rate": round(len(rec["fired"]) / rec["routed"], 3) if rec["routed"] else None,
        "fired": rec["fired"], "missed": rec["missed"],
    })
trig_rows.sort(key=lambda x: (x["table"], -(x["fire_rate"] or 0)))

# 문항별로도 — 어떤 질문이 triggered 규칙을 하나도 못 받았는가
per_q: list[dict] = []
for q in QUESTIONS:
    question = q.get("question") or ""
    r = route(question, ctx)
    q_cf = question.casefold()
    fired, avail = [], []
    for (t, name), rec in per_rule.items():
        if t not in r.tables:
            continue
        avail.append(name)
        if any(w.casefold() in q_cf for w in rec["triggers"]):
            fired.append(name)
    ctx_txt = ctx.planner_context(r.tables, question)
    per_q.append({
        "qid": q.get("qid"), "file": q["_file"], "q": question,
        "tables": r.tables, "route_decided": r.decided,
        "n_triggered_available": len(avail), "n_triggered_fired": len(fired),
        "fired": sorted(fired),
        "ctx_chars": len(ctx_txt), "ctx_lines": ctx_txt.count("\n") + 1,
    })

# ── §4-1-2. "그 규칙이 필요했던 문항" 판정 ───────────────────────────────
# 🔴 판정 기준 (산출물 표 머리에 그대로 적는다):
#   ① 그 문항의 `gold_sql` 이 외부 테이블(ext_*)을 쓴다 = 그 테이블이 **필요했다**.
#   ② 그런데 그 이름이 스키마 프롬프트에도, 실제로 실린 규칙 블록에도 **없다**.
#   → 모델은 존재를 모르는 테이블을 쓸 수 없다. 이 조합은 **오답이 확정된 미주입**이다.
#   ext_* 로 한정하는 이유: 마스터 컬럼은 schema_text 가 항상 싣기 때문에 규칙이 안 실려도
#   모델이 알 수 있다. ext_* 만이 "규칙(또는 cross 판정)이 유일한 전달 경로" 다.
#   ⚠️ 폐기한 두 기준 — (a) gold_reason 산문에 규칙 이름 글자매칭: '레버리지'·'단일종목' 이
#      설명 문장 낱말과 겹쳐 오탐 10건. (b) 규칙이 언급한 마스터 컬럼이 gold_sql 에 있으면 필요:
#      sale_yn·itm_no 같은 공통 컬럼이 거의 모든 gold 에 있어 662건 중 550건이 잡혔다(무의미).
from src.runtime import gate, pipeline  # noqa: E402  (cross 판정·설명서 안전망을 그대로 재현)

EXT_NAMES = ("ext_fund_page", "ext_fund_holdings", "ext_etf_holdings", "ext_ovs_etf_holdings")


def grounding_target(question: str, r) -> tuple[list[str], bool]:
    """pipeline.answer 의 target·cross 결정을 그대로 재현 — 스키마 프롬프트에 무엇이 실리는지 알려면 필요."""
    tables = r.tables if r.decided else []
    cross = gate.is_cross_query(question, tables, r.groups) and r.tables != ["domestic_bonds"]
    ext_hint = bool(pipeline._FUND_EXT_HINTS.search(question))
    if not cross and r.tables == ["public_funds"] and ext_hint:
        cross = True
    target = list(r.tables)
    if cross:
        target += [t for t in EXT_NAMES if t not in target]
    return target, cross


needed_rows = []
for q in QUESTIONS:
    question, gsql = q.get("question") or "", q.get("gold_sql") or ""
    if not gsql:
        continue                              # gold SQL 없는 문항(불가응답 등)은 판정 보류
    r = route(question, ctx)
    target, cross = grounding_target(question, r)
    schema_txt = ctx.schema_text(target)
    rules_txt = ctx.planner_context(r.tables, question)          # 실제로 실리는 규칙(트리거 적용)
    q_cf = question.casefold()
    for ext in EXT_NAMES:
        if ext not in gsql:
            continue                          # gold 가 이 외부 테이블을 안 쓴다 = 필요 없었다
        if ext in schema_txt or ext in rules_txt:
            continue                          # 어디로든 실렸다 = 미주입 아님
        # 이 외부 테이블을 알려줄 수 있었던 triggered 규칙 = 본문에 그 이름을 담은 규칙
        carriers = [(t, name, rule) for t in r.tables
                    for name, rule in rules_of(t).items()
                    if not str(name).startswith("_") and is_triggered(rule) and ext in rule_text(rule)]
        needed_rows.append({
            "qid": q.get("qid"), "q": question, "missing": ext,
            "tables": r.tables, "cross": cross,
            "in_schema": False, "in_rules": False,
            "carriers": [{"table": t, "rule": n,
                          "triggers": [str(w) for w in (rl.get("triggers") or [])],
                          "hit": [str(w) for w in (rl.get("triggers") or [])
                                  if str(w).casefold() in q_cf]}
                         for t, n, rl in carriers],
        })
gap = needed_rows                              # 이 목록 자체가 "필요했는데 프롬프트 어디에도 없음"

# ══════════════════════════════════════════════════════════════════════
# §4-2. 모순·중복·과량
# ══════════════════════════════════════════════════════════════════════
# 사고 이력 문구 — 지시서 §2-3 이 지목한 것(날짜·실측·재발·⛑🔴) 그대로
HIST = re.compile(r"20\d\d-\d\d-\d\d|\d\d/\d\d\b|실측|재발|⛑|🔴|🆕|✅|판정|이력|시점")
# 부정문 — "~하지 말 것", "~은 없다", "금지"
NEG = re.compile(r"금지|하지 ?말|쓰지 ?말|않는다|아니다|없다|말 것|안 된다|불가")

vol_rows = []
for t in TABLES:
    rs = rules_of(t)
    always = {k: v for k, v in rs.items() if not str(k).startswith("_") and not is_triggered(v)}
    trig = {k: v for k, v in rs.items() if not str(k).startswith("_") and is_triggered(v)}
    a_txt = "\n".join(f"- {k}: {rule_text(v)}" for k, v in always.items())
    all_txt = "\n".join(f"- {k}: {rule_text(v)}" for k, v in rs.items() if not str(k).startswith("_"))
    hist_lines = [ln for ln in all_txt.splitlines() if HIST.search(ln)]
    neg_rules = [{"rule": k, "chars": len(rule_text(v)),
                  "n_neg": len(NEG.findall(rule_text(v)))}
                 for k, v in rs.items()
                 if not str(k).startswith("_") and len(NEG.findall(rule_text(v))) >= 2]
    neg_rules.sort(key=lambda x: -x["n_neg"])
    longest = sorted(((k, len(rule_text(v))) for k, v in rs.items() if not str(k).startswith("_")),
                     key=lambda x: -x[1])[:5]
    # 전량 주입 시 실제 planner_context (normalization·vocab 포함) — 프롬프트 상한 감각용
    full_ctx = ctx.planner_context([t], None)
    vol_rows.append({
        "table": t,
        "n_rules": len(always) + len(trig), "n_always": len(always), "n_triggered": len(trig),
        "always_chars": len(a_txt), "all_rules_chars": len(all_txt),
        "planner_context_chars": len(full_ctx), "planner_context_lines": full_ctx.count("\n") + 1,
        "hist_lines": len(hist_lines), "hist_ratio": round(len(hist_lines) / max(1, all_txt.count("\n") + 1), 3),
        "longest_rules": [{"rule": k, "chars": n} for k, n in longest],
        "negative_rules": neg_rules,
        "hist_sample": hist_lines[:6],
    })

# ── 모순 후보: 같은 대상(집계 단위/모수/필터)에 다른 지시를 내리는 always_on 쌍 ──
# 지시서 §4-2-1 이 지목한 쌍을 먼저 확인하고, 기계로도 같은 컬럼을 GROUP BY/WHERE 에 쓰는 쌍을 훑는다.
NAMED_PAIRS = [
    ("public_funds", "종목단위", "펀드단위"),
    ("domestic_bonds", "대표행", "판매행"),
    ("domestic_etfs", "ETF만", "상품명조회"),
]
contradictions = []
for t, a, b in NAMED_PAIRS:
    rs = rules_of(t)
    rec = {"table": t, "pair": [a, b]}
    for k in (a, b):
        v = rs.get(k)
        rec[k] = None if v is None else {
            "exists": True, "always_on": not is_triggered(v),
            "chars": len(rule_text(v)), "text": rule_text(v)[:400],
        }
    both_always = all(isinstance(rec.get(k), dict) and rec[k]["always_on"] for k in (a, b))
    rec["둘 다 always_on"] = both_always
    contradictions.append(rec)

# 기계 훑기 — always_on 규칙 중 같은 컬럼을 언급하는 쌍(집계 단위 지시가 겹칠 후보)
GRP = re.compile(r"GROUP BY|COUNT\(|DISTINCT|행 ?= ?|dedup|단위")
auto_pairs = []
for t in TABLES:
    always = [(k, rule_text(v)) for k, v in rules_of(t).items()
              if not str(k).startswith("_") and not is_triggered(v)]
    grp_rules = [(k, txt) for k, txt in always if GRP.search(txt)]
    for i in range(len(grp_rules)):
        for j in range(i + 1, len(grp_rules)):
            auto_pairs.append({"table": t, "pair": [grp_rules[i][0], grp_rules[j][0]],
                               "both_always_on": True,
                               "why": "둘 다 always_on 이고 집계 단위(GROUP BY/COUNT/행 단위)를 지시한다"})

out1 = {"generated": "2026-09-03", "n_questions": len(QUESTIONS),
        "판정기준": "문항의 gold_reason·note 에 규칙 이름이 글자 그대로 나오면 '그 규칙이 필요했던 문항'. "
                  "이름이 안 적힌 문항은 판정 보류로 세지 않는다.",
        "per_rule": trig_rows, "per_question": per_q,
        "needed": needed_rows, "needed_but_missed": gap}
out2 = {"generated": "2026-09-03", "volume": vol_rows,
        "named_pairs": contradictions, "auto_pairs": auto_pairs}
(ROOT / "eval" / "rule_delivery_trigger.json").write_text(
    json.dumps(out1, ensure_ascii=False, indent=1), encoding="utf-8")
(ROOT / "eval" / "rule_delivery_volume.json").write_text(
    json.dumps(out2, ensure_ascii=False, indent=1), encoding="utf-8")

# ── 콘솔 요약 ──
print("\n=== §4-1 트리거 규칙 발동률 (라우팅된 문항 대비) ===")
for r in trig_rows:
    print(f"  {r['table'][:14]:14s} {r['rule'][:16]:16s} 라우팅 {r['routed']:3d} · 발동 {r['n_fired']:3d}"
          f" ({(r['fire_rate'] or 0)*100:5.1f}%) · 트리거 {len(r['triggers'])}개 · {r['text_len']}자")
never = [r for r in trig_rows if r["routed"] and r["n_fired"] == 0]
print(f"\n  🔴 한 번도 발동 안 한 규칙 {len(never)}개: " + ", ".join(f"{r['table'][:4]}/{r['rule']}" for r in never))

print(f"\n=== §4-1-2 gold_sql 이 쓴 ext_* 가 프롬프트 어디에도 없는 문항 {len(gap)}건 ===")
for g in gap:
    print(f"  🔴 {g['qid']:16s} {g['missing']:20s} route={g['tables']} cross={g['cross']}")
    print(f"     Q: {g['q'][:60]}")
    for c in g["carriers"]:
        print(f"     전달 가능했던 규칙: {c['rule']} · 트리거 {c['triggers'][:6]}… → 히트 {c['hit']}")
    if not g["carriers"]:
        print("     전달 가능했던 규칙 없음 — cross 판정만이 경로였다")

print("\n=== §4-2 도메인별 분량 ===")
print(f"  {'테이블':16s} {'규칙':>4s} {'always':>7s} {'trig':>5s} {'always자':>9s} {'전체자':>8s} {'ctx자':>8s} {'이력줄':>6s}")
for v in vol_rows:
    print(f"  {v['table']:16s} {v['n_rules']:4d} {v['n_always']:7d} {v['n_triggered']:5d}"
          f" {v['always_chars']:9,d} {v['all_rules_chars']:8,d} {v['planner_context_chars']:8,d} {v['hist_lines']:6d}")

print("\n=== §4-2 지목된 모순 쌍 ===")
for c in contradictions:
    print(f"  {c['table']} {c['pair']} → 둘 다 always_on: {c['둘 다 always_on']}")

print(f"\n기계 훑기 집계단위 동시주입 후보 {len(auto_pairs)}쌍")
print("산출: eval/rule_delivery_trigger.json · eval/rule_delivery_volume.json")
