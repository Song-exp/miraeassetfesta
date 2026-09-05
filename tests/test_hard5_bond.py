# -*- coding: utf-8 -*-
"""채권 난이도 상 5문항 수리 회귀 (2026-09-05 · docs/bond_hard5_fix_plan_2026-09-05.md).

서버 실측 5문항(에코프로 자회사 · SK 계열사 최저 등급 · 우주항공 관련 발행사 · 등급 변동 이력 · ESG 발행액순+위험요인)에서
드러난 결함을 부류 단위로 고친 뒤, 문항 자체와 형제 질문·gold 전건을 오프라인(HCX 0회)으로 잠근다.
"""

import json
import re
from pathlib import Path

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")

GOLD = Path("eval/questions_domestic_bonds.jsonl")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


class _BondProbe:
    """근거문서·게이트만 보는 플래너 — SQL 은 실행 가능한 아무 문장."""

    def plan_sql(self, question, grounding):
        return "SELECT pd_no, TRIM(pd_nm) AS pd_nm FROM domestic_bonds LIMIT 1"

    def compose_answer(self, question, rows):
        return "probe"


def _gold_questions():
    if not GOLD.exists():
        return []
    return [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── P3. 업종·테마·섹터 ABSENT (hasIndustrySector) ──────────────────────────────

def test_industry_absent_ungrounded_theme(ctx):
    """#3 — '우주항공 관련 발행사' 는 접지되는 개체가 없다 → 업종 ABSENT 로 HCX 0회 기각 + 발행사 이름 되묻기."""
    r = answer_question("H5-03", "최근 6개월 동안 우주항공 관련 발행사가 발행한 채권 정리해줘", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "hasIndustrySector" in r.think_trace
    assert "업종" in r.answer and "발행사 이름" in r.answer
    assert "상품 자체가 없" not in r.answer                      # 종전 오답 문구


def test_industry_absent_axis_word(ctx):
    """축의 이름(업종·테마·섹터)은 접지와 무관하게 발동한다."""
    for q in ("은행 업종 채권 알려줘", "2차전지 테마 회사채 있어?", "방산 섹터 채권 정리해줘"):
        g = gate.check(q, ctx, ["domestic_bonds"])
        assert g.rejected and "hasIndustrySector" in g.reason, q


def test_industry_grounded_issuer_passes(ctx):
    """'○○ 관련 채권' 에서 ○○ 이 발행사 노드로 접지되면 업종 질의가 아니다 — 통과."""
    r = answer_question("H5-03b", "한화에어로스페이스 관련 채권 알려줘", planner=_BondProbe(), ctx=ctx)
    assert "hasIndustrySector" not in r.think_trace and "[Gate] 통과" in r.think_trace


def test_industry_vocab_skips_ksan(ctx):
    """'산업' 은 한국산업은행·산업금융채권을 비켜 간다."""
    for q in ("한국산업은행 채권 알려줘", "산업금융채권 수익률 높은 순", "산업은행이 발행한 채권 개수"):
        g = gate.check(q, ctx, ["domestic_bonds"])
        assert not (g.rejected and "hasIndustrySector" in g.reason), q


def test_industry_absent_no_new_rejection_on_gold(ctx):
    """gold 채권 전건 — 새 선언이 answer 기대 문항을 하나도 새로 기각하지 않는다."""
    for x in _gold_questions():
        if x.get("expected_behavior") != "answer":
            continue
        g = gate.check(x["question"], ctx, ["domestic_bonds"], grounded_entity=True)
        assert not (g.rejected and "hasIndustrySector" in g.reason), x["qid"]
        g2 = gate.check(x["question"], ctx, ["domestic_bonds"], grounded_entity=False)
        assert not (g2.rejected and "hasIndustrySector" in g2.reason), x["qid"]


def test_yield_history_why_uses_snapshot_wording(ctx):
    """P0 — 개발자 사유에서도 8/22 를 '기준일' 이라 부르지 않는다(리드 결정 09-02: 판정·표기 기준일은 8/24)."""
    items = {i["property"]: i for i in ctx.absent_props["domestic_bonds"]}
    assert "기준일(2026-08-22)" not in items["hasYieldHistory"]["why"]
