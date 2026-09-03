# -*- coding: utf-8 -*-
"""규칙 전달 감사 §4-3 — 형식 실험 (H3). 조건 A(현행 규칙) vs B(교정 규칙) paired.

지시서: docs/rule_delivery_audit_2026-09-03.md §4-3.
  · 대상 규칙 5개(펀드): 기본모수 · 펀드단위(+종목단위) · 대표행 · 국가태그 · 위험등급 방향
  · **코드 가드는 양쪽 다 끈다** — pipeline._apply_sql_guards 를 인메모리로 우회한다.
    (§4-3-2 가 허용한 "측정 스크립트에서 건너뛰는 실행 경로". 서버 배포 대상 아님.)
  · 조건 B 본문은 eval/rule_delivery_variant_b.yaml. ontology/enums/*.yaml 은 **건드리지 않는다**.
  · 채점은 run_paired.py 의 judge/McNemar/Wilson 을 그대로 쓴다 (같은 자로 재는 것).

🔴 HCX 를 문항당 2~3회 호출한다. 팀이 챗봇을 쓰는 시간대에는 돌리지 말 것.
사용:
  ./.venv/Scripts/python.exe eval/rule_delivery_paired.py --smoke        # 2문항 · 왕복·처리량 확인
  ./.venv/Scripts/python.exe eval/rule_delivery_paired.py --conditions A,B
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")      # HCX 키 — scripts/bench_hcx.py 와 같은 방식

from src.runtime import pipeline  # noqa: E402
from src.runtime.loader import connect_readonly, load_context  # noqa: E402
from eval.run_paired import judge, mcnemar_exact_p, wilson  # noqa: E402

VARIANT = yaml.safe_load((ROOT / "eval" / "rule_delivery_variant_b.yaml").read_text(encoding="utf-8"))


# ── 조건 B 적용 — ctx 사본에만. 원본 yaml 파일은 열지도 않는다 ──────────────
def apply_variant_b(ctx):
    doc = ctx.enums["public_funds"]
    rules = doc["query_rules"]
    for name, text in (VARIANT.get("replace") or {}).items():
        if name in rules:
            rules[name] = text.strip()
    for name, spec in (VARIANT.get("retrigger") or {}).items():
        if name in rules:
            rules[name] = {"triggers": list(spec["triggers"]), "text": spec["text"].strip()}
    # answer_rules 는 리스트(문장들) — 대상 문장을 교정판으로 교체
    ar = doc.get("answer_rules") or []
    for _key, text in (VARIANT.get("answer_replace") or {}).items():
        for i, line in enumerate(ar):
            if "zrin_fd_ivst_risk_gcd" in str(line):
                ar[i] = text.strip()
                break
    # (ii) 이력·강조 기호 제거 — 규칙 본문 전체에 기계 적용
    pats = [re.compile(p) for p in (VARIANT.get("strip") or {}).get("patterns", [])]
    for name, rule in list(rules.items()):
        if str(name).startswith("_"):
            continue
        if isinstance(rule, dict) and "text" in rule:
            rule["text"] = _strip(str(rule["text"]), pats)
        elif isinstance(rule, str):
            rules[name] = _strip(rule, pats)
    return ctx


_SENT = re.compile((VARIANT.get("strip") or {}).get("sentence_markers") or r"(?!x)x")
# 🔴 지시문 보호 — 이 표지가 있는 문장은 이력 표지가 같이 있어도 **지우지 않는다**.
#    1차 시도에서 '판정·원인·오답이' 같은 넓은 표지를 쓰자 `집계_TopN_필수` 가 WHERE 조건을
#    통째로 잃고 꼬리 산문만 남았다. 그 상태로 B 를 돌리면 형식이 아니라 '망가진 규칙' 을 재게 된다.
_SQLISH = re.compile(
    r"SELECT|FROM|WHERE|GROUP BY|ORDER BY|COUNT|DISTINCT|JOIN|LIKE|IS NULL|IS NOT NULL"
    r"|CASE WHEN|COALESCE|substr|[a-z]{2,}_[a-z_]{2,}|→|=|≠|<>", re.I)


def _strip(text: str, pats) -> str:
    """(ii) 이력 제거.

    토큰만 지우면 분량이 안 준다(펀드 규칙 7,559→6,251, 83%) — 사연이 문장째 들어 있기 때문이다.
    그래서 문장 단위로 빼되, **SQL 조각·컬럼명이 든 문장은 남긴다**. 규칙의 지시는 지키고
    사연만 없앤다. 전부 걸리면 원문을 그대로 둔다(규칙을 통째로 없애지 않는다).
    """
    for p in pats:
        text = p.sub("", text)
    sents = re.split(r"(?<=[.。])\s+|\n", text)
    kept = [s for s in sents
            if s.strip() and (_SQLISH.search(s) or not _SENT.search(s))]
    out = "\n".join(kept) if kept else text
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def fresh_ctx():
    """🔴 load_context 는 @lru_cache(maxsize=1) 다 — 그냥 두 번 부르면 **같은 객체**가 온다.
    조건 B 를 그 위에 덮으면 A 까지 바뀐다(1차 시도에서 A·B 블록 크기가 같게 나온 원인).
    측정마다 깊은 사본을 쓴다."""
    return copy.deepcopy(load_context())


def block_size(ctx, question: str) -> int:
    """planner_context 전체 — 규칙 + normalization + 동의어 + 값 사전."""
    return len(ctx.planner_context(["public_funds"], question))


def rules_only_size(ctx, question: str, table: str = "public_funds") -> int:
    """규칙 부분만 — 지시서 §4-3-2 (iv) 의 '규칙 블록 상한 ≈2,500자' 가 재는 대상.

    🔴 planner_context 텍스트를 '- ' 접두로 잘라 세면 안 된다 — 여러 줄짜리 규칙 본문의
    둘째 줄부터가 통째로 빠진다(조건 B 의 SQL 조각 대응표가 전부 여러 줄이라 B 가
    실제보다 작게 잡혔다). planner_context 와 같은 트리거 논리로 규칙만 다시 조립해 센다.
    """
    q_cf = (question or "").casefold()
    parts = []
    for name, rule in ((ctx.enums.get(table) or {}).get("query_rules") or {}).items():
        if str(name).startswith("_"):
            continue
        if isinstance(rule, dict) and "triggers" in rule:
            if question is not None and not any(
                    str(w).casefold() in q_cf for w in rule.get("triggers") or []):
                continue
            rule = rule.get("text", "")
        body = rule if isinstance(rule, str) else yaml.safe_dump(
            rule, allow_unicode=True, sort_keys=False).strip()
        parts.append(f"- {name}: {body}")
    return len("\n".join(parts))


# ── 가드 우회 — 양쪽 조건 모두 끈다 (§4-3-2) ────────────────────────────────
def disable_guards():
    """ensure_* 결합 가드를 통째로 우회. 규칙 전달만 남겨 H3 를 순수하게 잰다."""
    original = pipeline._apply_sql_guards
    pipeline._apply_sql_guards = lambda sql, *a, **k: sql
    return original


def load_questions(smoke: bool) -> list[dict]:
    """지시서 §4-3-3 의 문항 셋.

    🔴 15R ❌30 은 리포에서 기계로 복원되지 않는다 — eval/verdicts_merged.json 은 13R 까지고
       docs/answer_quality_by_type_2026-09-03.md 는 30건 중 11건만 ID 로 지명한다.
       그래서 여기서는 **재현 가능한 대체 셋**을 쓴다: 펀드 gold 20 + 공식 예시 8 +
       품질 보고서가 ID 로 지명한 15R ❌ 문항 중 gold 에 있는 것. 원 셋을 쓰려면 리드가
       ❌30 의 qid 목록을 주면 이 함수만 바꾼다.
    """
    qs: list[dict] = []
    for f in ("questions_public_funds.jsonl", "questions_official_sample.jsonl"):
        p = ROOT / "eval" / f
        qs += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if smoke:
        qs = [q for q in qs if q["qid"] in ("FND-001", "FND-012")] or qs[:2]
    return qs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="A,B")
    ap.add_argument("--smoke", action="store_true", help="2문항만 — 왕복·처리량 확인")
    ap.add_argument("--out", default=str(ROOT / "eval" / "rule_delivery_paired.json"))
    a = ap.parse_args()

    from src.hcx.planner import HCXPlanner

    qs = load_questions(a.smoke)
    con = connect_readonly()
    planner = HCXPlanner()
    disable_guards()
    os.environ["RULES_MODE"] = "layered"          # 양쪽 다 현행 운영값(트리거 적용)

    outcome: dict[str, dict] = {}
    sizes: dict[str, list[int]] = {}
    t0 = time.time()
    for cond in a.conditions.split(","):
        ctx = fresh_ctx()
        if cond == "B":
            apply_variant_b(ctx)
        sizes[cond] = [rules_only_size(ctx, q["question"]) for q in qs]
        for q in qs:
            r = pipeline.answer_question(q["qid"], q["question"], planner=planner, ctx=ctx)
            ok = judge(q, r, con)
            outcome.setdefault(q["qid"], {})[cond] = {
                "ok": ok, "sql": r.sql, "answer": (r.answer or "")[:400],
                "rules_chars": rules_only_size(ctx, q["question"]),
                "ctx_chars": block_size(ctx, q["question"]),
            }
            print(f"[{cond}] {q['qid']} {'✅' if ok else '❌'} {q['question'][:44]}")
    dt = time.time() - t0

    conds = a.conditions.split(",")
    n = len(qs)
    summary = {"n": n, "seconds": round(dt, 1), "per_query_sec": round(dt / max(1, n * len(conds)), 1)}
    for c in conds:
        k = sum(1 for v in outcome.values() if (v.get(c) or {}).get("ok"))
        lo, hi = wilson(k, n)
        summary[c] = {"ok": k, "rate": round(k / n, 3), "wilson95": [round(lo, 3), round(hi, 3)],
                      "rules_chars_avg": round(sum(sizes[c]) / max(1, len(sizes[c])))}
        print(f"{c}: {k}/{n} = {k/n:.1%}  Wilson95 [{lo:.1%}, {hi:.1%}]  규칙블록 평균 {summary[c]['rules_chars_avg']:,}자")
    if len(conds) == 2:
        A, B = conds
        ok_ = lambda v, m: bool((v.get(m) or {}).get("ok"))
        b = sum(1 for v in outcome.values() if ok_(v, A) and not ok_(v, B))
        c_ = sum(1 for v in outcome.values() if ok_(v, B) and not ok_(v, A))
        p = mcnemar_exact_p(b, c_)
        summary["mcnemar"] = {"b_A_only": b, "c_B_only": c_, "exact_p": round(p, 4)}
        print(f"McNemar {A}-only {b} · {B}-only {c_} · exact p = {p:.4f}")

    Path(a.out).write_text(json.dumps({"summary": summary, "outcome": outcome},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n소요 {dt:.0f}초 · 질의당 {summary['per_query_sec']}초 → 산출 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
