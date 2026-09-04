# -*- coding: utf-8 -*-
"""KG 계층(kg_closure)·관계(subsidiaryOf) 후손 탐색 — 2026-08-30 ㉡ + E.

배경 (docs/PENDING_DECISIONS_ETF.md B-2 · docs/review_2026-08-26/채권_전수조사_2026-08-30.md §2-E):
- 정본 노드(Sec_m_*·CG_*·Idx_a_*)는 alias 가 0개고 실물 노드는 kg_closure 로 매달려 있는데,
  런타임이 closure 를 읽지 않아 정본에 매칭되면 SQL 에 넣을 값이 없었다.
- 대상 테이블에 alias 가 없으면 다른 테이블 alias 로 fallback 해 채권 질의에 ETF 구성종목 값이 실렸다.

HCX 없이 오프라인. DB 없으면 skip.
"""

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


class GroundingProbe:
    """근거문서만 받아 보는 플래너 — SQL 은 실행 가능한 아무 문장."""

    def plan_sql(self, question, grounding):
        return "SELECT 1 AS one FROM domestic_etfs LIMIT 1"

    def compose_answer(self, question, rows):
        return "probe"


def _grounding(ctx, q):
    r = answer_question("T-CL", q, planner=GroundingProbe(), ctx=ctx)
    return r.think_trace, r.grounding


# ── 로더 ────────────────────────────────────────────────────────────────

def test_loader_reads_closure(ctx):
    """kg_closure 가 ctx 에 올라와야 한다 — 조상 → 후손 목록."""
    assert "Sec_o_67066G104" in ctx.kg_closure["Sec_m_nvidia"]
    assert "CG_AAA" in ctx.kg_closure["CG_Investment"]


# ── 채권 — 신용등급 계층 + fallback 제거(E) ──────────────────────────────

def test_bond_credit_grade_expands_to_members(ctx):
    """'투자등급' → CG_Investment(alias 0) → 후손 AAA~BBB- 10종이 crd_grd 값으로 실린다."""
    trace, grounding = _grounding(ctx, "투자등급 채권 알려줘")
    assert "CG_Investment" in trace
    assert "domestic_bonds.crd_grd" in grounding
    assert "'AAA'" in grounding and "'BBB-'" in grounding


def test_bond_query_drops_foreign_table_alias(ctx):
    """E — 채권 질의에서 종목 노드(alias 는 ext_etf_holdings 뿐)는 매핑에서 빠진다.
    이전엔 fallback 으로 ext_etf_holdings.constituent='한국전력' 이 근거에 실려 구성종목 JOIN 을 유도했다."""
    trace, grounding = _grounding(ctx, "한국전력 채권 알려줘")
    assert "ext_etf_holdings" not in grounding
    assert "(Security)" not in grounding


# ── 펀드 — 정본 → 펀드 보유 ISIN 노드 ───────────────────────────────────

def test_fund_cambricon_via_closure(ctx):
    """'캠브리콘' → Sec_m_cambricon(alias 0) → 후손 Sec_f_CNE1000041R8 의 ext_fund_holdings 값."""
    trace, grounding = _grounding(ctx, "캠브리콘을 편입한 공모펀드 알려줘")
    assert "Sec_m_cambricon" in trace
    assert "ext_fund_holdings.isin" in grounding and "'CNE1000041R8'" in grounding
    assert "'CAMBRICON TECHNOLOGIES CORP'" in grounding


# ── ETF — 분신 합집합 · 자회사 관계 ─────────────────────────────────────

def test_etf_nvidia_union_of_split_nodes(ctx):
    """'엔비디아' 는 정본 1 + 실물 3(CUSIP 주식·회사채·LEI) 으로 갈려 있다 — 노드는 전부 합치되
    **조회에 쓸 수 있는 값만** 싣는다.

    🔴 2026-09-04 온톨로지 사용 감사 — cusip·lei 는 근거문서에서 뺐다(`_OPAQUE_ID_COLS`).
       kg_alias 에는 남아 있고 계층 합치기도 그대로지만, 값 목록을 프롬프트에 싣지 않는다:
       ① 실측상 **재현율이 이름보다 낮다** — 엔비디아 cusip 309 ETF vs 이름 356 ETF,
          cusip 만 잡는 ETF 0 · 이름만 잡는 ETF 47. 삼성전자 lei 82 vs 이름 84, lei 만 잡는 것 0.
       ② ETF yaml 규칙 109개 컬럼 중 이 둘을 쓰는 규칙이 하나도 없다 — 조회 경로가 없다.
       ③ 실측 해악 — 값 목록이 "여럿이면 IN 으로 모두" 안내와 겹쳐 없는 표기 창작의 재료가 됐다.
    """
    trace, grounding = _grounding(ctx, "엔비디아를 편입한 해외 ETF 알려줘")
    assert "'NVIDIA CORPORATION'" in grounding          # 정본 자체 alias
    assert "'NVIDIA Corp'" in grounding                 # Sec_o_67066G104 — 노드는 합쳐졌다
    assert "ext_ovs_etf_holdings.holding_name" in grounding
    # 불투명 식별자는 값도 컬럼명도 매핑 블록에 나오지 않는다 (스키마 줄에는 남는다)
    mapping = grounding.split("# 교차질의")[0]
    assert "cusip" not in mapping and "lei" not in mapping
    assert "'67066G104'" not in grounding and "'549300S4KLFTLO7GSQ80'" not in grounding


def test_etf_subsidiary_expansion(ctx):
    """공식 예시 #5 — '에코프로의 자회사' 는 subsidiaryOf 로 자회사 정본 3개를 찾고 각 후손의 값을 싣는다.
    이전엔 채권 발행사 노드 '(주)에코프로' 로 잘못 잡혔다."""
    trace, grounding = _grounding(ctx, "에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품")
    assert "Sec_m_ecopro" in trace
    assert "'에코프로비엠'" in grounding and "'에코프로머티'" in grounding and "'383310'" in grounding
    assert "pd_pbcm" not in grounding                   # 채권 발행사 노드는 대상 밖


def test_etf_without_subsidiary_word_stays_on_entity(ctx):
    """'에코프로 편입 ETF' 는 본체만 — 자회사 확장은 질문이 관계를 물을 때만."""
    trace, grounding = _grounding(ctx, "에코프로를 편입한 국내 ETF 알려줘")
    assert "'086520'" in grounding
    assert "'247540'" not in grounding
