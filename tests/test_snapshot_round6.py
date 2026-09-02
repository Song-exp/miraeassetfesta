# -*- coding: utf-8 -*-
"""6R 고정선 — 5R 재검 ✅(값 ✅ 포함) + KG 2R/3R ✅ 문항의 **결정층** 결과 스냅샷 (HCX 0회).

r5 서버 원본(eval/probe_recheck_2026-09-02_r5.json)의 최종 SQL 을 가짜 플래너로 재투입해 라우팅 테이블 · Ground 노드 ·
가드 후 SQL WHERE 절 · 조립기 마커 · 행수를 기록한다. 6R 수리가 다른 ✅ 의 경로를 바꾸면 여기서 깨진다(docs/recheck_2026-09-02_round6_plan.md).

갱신: SNAPSHOT_WRITE=1 pytest tests/test_snapshot_round6.py  (의도한 변경일 때만 — 커밋 본문에 어느 qid 가 왜 바뀌었는지 적는다)
"""
import json
import os
import re

import pytest

from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "tests", "snapshots", "round6_fixedline.json")
R5 = os.path.join(ROOT, "eval", "probe_recheck_2026-09-02_r5.json")


def _ok_qids():
    ok = []
    for ln in open(os.path.join(ROOT, "docs", "recheck_2026-09-02_round5.md"), encoding="utf-8"):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")] if ln.startswith("| ") else []
        m = re.match(r"^([RSTVW]\d+)\b", cells[0]) if cells else None
        if m and len(cells) >= 3 and cells[2].startswith("✅"):
            ok.append(m.group(1))
    for ln in open(os.path.join(ROOT, "docs", "kg_structure_probe_round3_2026-09-02.md"), encoding="utf-8"):
        m = re.match(r"\| ((?:KG-\d+|X\d+)) \|", ln)
        if m:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if any(c == "✅" for c in cells[2:5]) and "❌" not in cells[2:5]:
                ok.append(m.group(1))
    return ok


def _decision_layer(ctx, item):
    from src.runtime.pipeline import answer_question
    tr = item.get("think_trace") or ""
    sqls = re.findall(r"\n\d+\. \[Plan\] (?:SQL 생성|재생성 SQL) — 아래 문장을 실행합니다\n(.*?)(?=\n\d+\. )", tr, re.S)
    if not sqls:
        return {"gate": True, "answer": (item.get("answer") or "")[:80]}
    sql_in = sqls[-1].strip()

    class P:
        def plan_sql(self, q, g):
            return sql_in

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX"

    r = answer_question(item["qid"], item["question"], planner=P(), ctx=ctx)
    route = re.search(r"\[Route\] 상품군 — ([^·\n]+)", r.think_trace)
    nodes = sorted(set(re.findall(r"→ ((?:Org|Fund|Country|FundAttr|Region|RiskGrade|Idx|AssetClass|CG|Curr|Sec)_[\w]+) \(", r.think_trace)))
    where = ""
    if r.sql:
        m = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", r.sql, re.I | re.S)
        where = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    markers = re.findall(r"\[(?:Answer|Gate)\] ([^—\n]+?기계 조립|기각)", r.think_trace)
    n = re.search(r"\[Execute\] (\d+)행", r.think_trace)
    return {"route": (route.group(1).strip() if route else ""), "nodes": nodes, "where": where,
            "assembler": markers[0].strip() if markers else "HCX", "rows": int(n.group(1)) if n else None,
            "answer_head": (r.answer or "")[:60] if (markers and "기각" not in markers[0]) else ""}


def test_round6_fixed_line():
    ctx = load_context()
    data = {it["qid"]: it for it in json.load(open(R5, encoding="utf-8"))}
    qids = [q for q in _ok_qids() if q in data]
    assert len(qids) >= 40, qids
    current = {q: _decision_layer(ctx, data[q]) for q in qids}
    if os.environ.get("SNAPSHOT_WRITE") or not os.path.exists(SNAP):
        with open(SNAP, "w", encoding="utf-8", newline="\n") as f:
            json.dump(current, f, ensure_ascii=False, indent=1)
        return
    snap = json.load(open(SNAP, encoding="utf-8"))
    diffs = {q: (snap.get(q), current[q]) for q in qids if snap.get(q) != current[q]}
    assert not diffs, "고정선 이탈: " + json.dumps(diffs, ensure_ascii=False, indent=1)[:4000]
