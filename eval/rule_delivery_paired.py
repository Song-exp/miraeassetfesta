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
    """문항 셋 = 15R ❌30 + 🟡11 (리드 제공, 2026-09-03).

    qid 목록: `eval/qids_15R_fail.txt`(30) · `eval/qids_15R_mid.txt`(11).
    질문 원문은 gold jsonl 에 있으면 거기서(gold_sql 도 함께 온다), 없으면 probe txt 에서 가져온다.
    🔴 probe 에서 온 문항은 `gold_sql` 이 없다 — `judge` 가 거절형으로 채점하므로 **answer 문항은
       전부 오답 처리된다.** 그래서 채점 모수를 gold_sql 보유 문항으로 한정하고, 나머지는
       "SQL 생성 여부"만 기록한다(아래 main 의 scored 참조).
    """
    want: list[str] = []
    for f in ("qids_15R_fail.txt", "qids_15R_mid.txt"):
        want += [l.strip() for l in (ROOT / "eval" / f).read_text(encoding="utf-8").splitlines() if l.strip()]

    gold: dict[str, dict] = {}
    for p in sorted((ROOT / "eval").glob("questions_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                gold[d["qid"]] = d
    probe: dict[str, str] = {}
    for p in sorted((ROOT / "eval").glob("probe_*.txt")):
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0] not in probe:
                probe[parts[0]] = parts[1]

    qs: list[dict] = []
    for qid in want:
        if qid in gold:
            qs.append({**gold[qid], "_src": "gold"})
        elif qid in probe:
            qs.append({"qid": qid, "question": probe[qid], "expected_behavior": "answer", "_src": "probe"})
    if smoke:
        qs = qs[:2]
    return qs


# ── §4-3-4 규칙별 준수 여부 — "SQL 에 확정식이 나타났는가" ────────────────
# 🔴 이게 H3 의 **직접 측정**이다. 정답률은 gold_sql 이 있는 문항에만 매길 수 있는데
#    15R ❌30 은 대부분 probe 유래라 gold 가 없다(41 중 7). 준수 여부는 41 전부에서 잰다.
#    "규칙이 실렸는데 지켰는가" 를 보는 것이므로 오히려 가설에 더 가까운 자다.
_FUNDKEY = re.compile(r"or_co_xtn_itt_cd.{0,120}mtco_itm_no", re.S | re.I)
_COUNTRY_WORDS = ("중국", "미국", "인도", "베트남", "일본", "러시아", "브라질", "홍콩", "독일", "대만", "호주", "스페인")
_SAFE_WORDS = ("안전", "안정")


def rule_compliance(question: str, sql: str) -> dict[str, bool | None]:
    """규칙 5개 × (적용 대상인가 / 지켰는가). 대상이 아니면 None."""
    sql = sql or ""
    low = sql.lower()
    fund = "public_funds" in low
    ranking = bool(re.search(r"order\s+by", low)) or bool(re.search(r"count\s*\(|sum\s*\(", low))
    counting = any(w in question for w in ("몇 개", "개수", "몇개"))
    out: dict[str, bool | None] = {}
    # 기본모수 — 펀드 집계·랭킹이면 판매중·공모 두 조건이 다 있어야 한다
    out["기본모수"] = (("sale_yn" in low and "prvo_pbff_desc" in low)
                   if (fund and ranking) else None)
    # 펀드단위 — 펀드 개수 질의면 펀드키(or_co + mtco)가 SQL 에 있어야 한다
    out["펀드단위"] = (bool(_FUNDKEY.search(sql)) if (fund and counting) else None)
    # 대표행 — 펀드 랭킹이면 펀드키로 GROUP BY 해야 한다
    out["대표행"] = ((bool(re.search(r"group\s+by", low)) and bool(_FUNDKEY.search(sql)))
                  if (fund and re.search(r"order\s+by", low) and not counting) else None)
    # 국가태그 — 국가어가 있으면 prfd_attr_cds 태그식으로 풀어야 한다(지역 컬럼 아님)
    has_country = any(w in question for w in _COUNTRY_WORDS)
    out["국가태그"] = (("prfd_attr_cds" in low and "fd_ivst_rgn_desc" not in low)
                   if (fund and has_country) else None)
    # 위험등급 방향 — '안전' 질의면 6등급(낮은 위험)이어야 한다. 1·2 면 뒤집힌 것
    has_safe = any(w in question for w in _SAFE_WORDS)
    if fund and has_safe and "zrin_fd_ivst_risk_gcd" in low:
        out["등급방향"] = not bool(re.search(r"zrin_fd_ivst_risk_gcd\s*=\s*[12](?![0-9])", low))
    else:
        out["등급방향"] = None
    return out


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
                "compliance": rule_compliance(q["question"], r.sql or ""),
            }
            print(f"[{cond}] {q['qid']} {'✅' if ok else '❌'} {q['question'][:44]}")
    dt = time.time() - t0

    conds = a.conditions.split(",")
    # 🔴 채점 모수는 **gold_sql 이 있는 문항**뿐이다. probe 에서만 온 문항은 정답 기준이 없어
    #    judge 가 거절형으로 떨어뜨린다 — 그걸 분모에 넣으면 두 조건이 똑같이 깎여 차이가 희석된다.
    scored = [q["qid"] for q in qs if q.get("gold_sql")]
    n = len(scored)
    summary = {"n_asked": len(qs), "n_scored": n, "n_unscored": len(qs) - n,
               "seconds": round(dt, 1), "per_query_sec": round(dt / max(1, len(qs) * len(conds)), 1)}
    for c in conds:
        k = sum(1 for q, v in outcome.items() if q in scored and (v.get(c) or {}).get("ok"))
        lo, hi = wilson(k, n)
        summary[c] = {"ok": k, "rate": round(k / n, 3), "wilson95": [round(lo, 3), round(hi, 3)],
                      "rules_chars_avg": round(sum(sizes[c]) / max(1, len(sizes[c])))}
        print(f"{c}: {k}/{n} = {k/n:.1%}  Wilson95 [{lo:.1%}, {hi:.1%}]  규칙블록 평균 {summary[c]['rules_chars_avg']:,}자")
    if len(conds) == 2:
        A, B = conds
        ok_ = lambda v, m: bool((v.get(m) or {}).get("ok"))
        b = sum(1 for q, v in outcome.items() if q in scored and ok_(v, A) and not ok_(v, B))
        c_ = sum(1 for q, v in outcome.items() if q in scored and ok_(v, B) and not ok_(v, A))
        p = mcnemar_exact_p(b, c_)
        summary["mcnemar"] = {"b_A_only": b, "c_B_only": c_, "exact_p": round(p, 4)}
        print(f"McNemar {A}-only {b} · {B}-only {c_} · exact p = {p:.4f}")

    # ── §4-3-4 준수율 표 ──
    RULES = ("기본모수", "펀드단위", "대표행", "국가태그", "등급방향")
    print("\n=== §4-3-4 규칙별 준수 (대상 문항 / 지킨 문항) ===")
    print(f"  {'규칙':10s}" + "".join(f"{c:>16s}" for c in conds))
    comp: dict = {}
    for rule in RULES:
        row = {}
        for c in conds:
            vals = [(v.get(c) or {}).get("compliance", {}).get(rule) for v in outcome.values()]
            tgt = [x for x in vals if x is not None]
            row[c] = {"target": len(tgt), "kept": sum(1 for x in tgt if x)}
        comp[rule] = row
        print(f"  {rule:10s}" + "".join(f"{row[c]['kept']:>7d}/{row[c]['target']:<8d}" for c in conds))
    summary["compliance"] = comp

    Path(a.out).write_text(json.dumps({"summary": summary, "outcome": outcome},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n소요 {dt:.0f}초 · 질의당 {summary['per_query_sec']}초 → 산출 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
