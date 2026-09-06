# -*- coding: utf-8 -*-
"""2026-08-30 전수조사 B·E·F·G·H 반영 회귀 테스트 — 전부 HCX 0회(오프라인).

F  라우팅: 단어 목록 없이 문장 구조 + 온톨로지 값 (scripts/route_prototype.py 36문항 그대로)
E  KG 매핑: 정해진 상품군 밖 노드로 fallback 하지 않는다
B  문지기: 연도는 SQL 사후 검사 · 신용등급은 표준표로 판정 (CB 무시 · BB+ 데이터 없음 · AAAA 존재하지 않음)
G  되묻기: 플래너가 CLARIFY: 를 돌려주면 그 문장이 답이다
H  답변 규칙: yaml answer_rules 가 compose_answer 에 실린다
"""

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import CLARIFY_PREFIX, answer_question, build_grounding
from src.runtime.router import route

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")

B, DE, OE, PF = "domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"
ETFS = {DE, OE}


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── F 라우팅 — 시제품 36문항. 기대값: 정확히 그 집합이거나(set), 그 부분집합이면서 비어 있지 않음(frozenset) ──
ROUTE_CASES = [
    # 채권 19 — '채권' 글자 없는 통칭(국고채·통안채·지방채·영구채·코코본드·은행채·카드채)도 채권으로
    ("신용등급 AA- 이상 채권 알려줘", {B}), ("국고채 수익률 알려줘", {B}), ("통안채 몇 개 있어?", {B}),
    ("지방채 알려줘", {B}), ("은행채 중 AAA", {B}), ("MBS 채권 수익률", {B}), ("카드채 수익률", {B}),
    # 국내상품 vs 해외티커 비교 — 긴 국내 상품명이 점수를 부풀려 해외가 70% 컷에 잘렸다(2026-09-01).
    # 상품명 직격 매치 테이블은 컷 면제. 단 'AAA'(티커=신용등급 다의어)는 면제 자격 없음 — 위 은행채 케이스.
    ("TIGER 미국S&P500 이랑 VOO 중 뭐가 나아", ETFS),
    ("SCHD랑 TIGER 미국배당다우존스 비교", ETFS),
    ("한국전력 채권 알려줘", {B}), ("LH 채권", {B}), ("산업은행 채권", {B}), ("삼성전자 채권", {B}),
    ("현대카드 채권 수익률", {B}), ("영구채 알려줘", {B}), ("코코본드 알려줘", {B}), ("듀레이션 짧은 채권", {B}),
    ("표면금리 높은 채권", {B}), ("위험등급 낮은 채권", {B}), ("만기 2027년 채권", {B}), ("잔존만기 1년 이내 채권", {B}),
    # 2026-09-02 gold 재투입 실측 — 조사가 붙은 값('국고채는')·구조 용어(전환사채·CB·스트립)가 미특정으로 빠져 라우팅 범위 가드가 정답 SQL 을 기각
    ("국고채는 총 몇 종목이야?", {B}), ("전환사채(CB) 알려줘", {B}), ("교환사채 알려줘", {B}), ("스트립 채권 있어?", {B}),
    ("유동화 채권 몇 개야?", {B}), ("지방채는 안전해?", {B}),
    # 국내 ETF 6 — '채권형 ETF' 는 ETF 다. 국내/해외를 문장으로 못 가르면 둘 다 넘긴다
    ("채권형 ETF 추천", frozenset(ETFS)), ("채권 ETF 중 수익률 높은 것", frozenset(ETFS)),
    ("KODEX 국고채3년 알려줘", {DE}), ("국고채 ETF 순자산 큰 순", frozenset(ETFS)),
    ("TIGER 미국S&P500 총보수", {DE}), ("총보수 낮은 ETF", frozenset(ETFS)),
    # 해외 ETF 3
    ("미국 나스닥 추종 해외 ETF", {OE}), ("QQQ 알려줘", {OE}), ("해외 채권 ETF 중 총보수 낮은 것", {OE}),
    # 펀드 4
    ("삼성전자 보유한 펀드 알려줘", {PF}), ("채권형 펀드 중 1년 수익률 높은 것", {PF}),
    ("미래에셋자산운용 펀드", {PF}), ("설정액 큰 펀드", {PF}),
    # 교차·모호 4
    ("삼성전자를 보유한 국내/해외 ETF 와 공모펀드를 연수익률 기준 TOP10", {DE, OE, PF}),
    ("채권과 ETF 중 뭐가 안전해?", frozenset({B, DE, OE})),
    ("한국전력공사가 발행한 채권", {B}),
]


@pytest.mark.parametrize("question,expected", ROUTE_CASES)
def test_route(ctx, question, expected):
    r = route(question, ctx)
    got = set(r.tables)
    if isinstance(expected, frozenset):
        assert got and got <= expected, (question, r)
    else:
        assert got == expected, (question, r)
    assert r.decided, (question, r)


# ── 08-30 밤 스트레스(107문항)에서 나온 약한 고리 — 수정 후 회귀 ──
STRESS_CASES = [
    ("국채 알려줘", {B}),                       # 2자 통칭 — yaml synonyms 는 2자 허용
    ("물가연동국채 알려줘", {B}), ("신종자본증권 알려줘", {B}), ("후순위채 알려줘", {B}),
    ("해외 채권 알려줘", {B}),                  # 수식어(해외)가 상품(채권)과 안 맞으면 상품을 따른다 → 외화채없음 규칙
    ("채권이랑 펀드 중 뭐가 나아?", {B, PF}),     # 접속 조사 '이랑'
    ("채권 또는 ETF", frozenset({B, DE, OE})),   # 접속사 '또는'
    ("채권형 상품 추천해줘", {PF}),              # '채권형' 은 유형 수식어 — 채권이 아니다
    ("만기 2030-12-31 채권", {B}), ("2026년 9월 만기", {B}),   # '만기' 2자 동의어로 채권
]


@pytest.mark.parametrize("question,expected", STRESS_CASES)
def test_route_stress(ctx, question, expected):
    got = set(route(question, ctx).tables)
    if isinstance(expected, frozenset):
        assert got and got <= expected, (question, got)
    else:
        assert got == expected, (question, got)


def test_future_tokens_formats():
    assert gate.future_tokens("만기 2030-12-31") == ["2030"]
    assert gate.future_tokens("2027.03 만기") == ["2027"]
    assert gate.future_tokens("20270101 이후") == ["2027"]
    assert gate.future_tokens("2026-09 만기") == ["202609"]
    assert gate.future_tokens("2026년 8월 상장") == []
    assert gate.future_tokens("내년 만기 채권") == ["2027"]
    assert gate.future_tokens("30년 만기 국채") == []          # 두 자리 연도는 만기 기간과 구분 불가 — 잡지 않는다


def test_bond_only_query_is_never_cross(ctx):
    # 채권엔 구성종목(ext_*) 이 없다 — '보유한' 이 있어도 교차질의가 아니고 주식 노드도 매핑하지 않는다
    r = answer_question("S-01", "삼성전자를 보유한 채권 알려줘", ctx=ctx)
    assert "교차질의" not in r.think_trace and "(Security)" not in r.think_trace


def test_crd_token_ignores_typo_tail(ctx):
    r = answer_question("S-02", "A++ 채권 알려줘", ctx=ctx)
    assert "[Gate] 통과" in r.think_trace


def test_route_undecided_falls_back_to_all(ctx):
    r = route("수익률 높은 상품 추천해줘", ctx)
    assert not r.decided and len(r.tables) == 4


def test_route_vocab_is_generated_not_written(ctx):
    # 어휘는 DB·yaml 에서 온다 — 채권 어휘에 대분류·채권종류·발행사·동의어가 다 들어 있어야 한다
    v = ctx.route_vocab[B]
    assert "국공채" in v and "국고채권" in v          # 범주형 컬럼 값 (대분류·채권종류)
    assert "한국전력공사" in v                       # kg_alias 발행사
    assert "통안채" in v and "영구채" in v            # yaml synonyms
    assert "채권" not in v                          # 상품 명사는 ① 겹 몫
    assert sum(len(x) for x in ctx.route_vocab.values()) > 10_000


def test_trace_shows_route(ctx):
    r = answer_question("R-01", "국고채 수익률 알려줘", ctx=ctx)
    assert "[Route] 상품군 — domestic_bonds" in r.think_trace


# ── E 매핑 — 상품군 밖 노드로 fallback 금지 ─────────────────────────────

def test_ground_no_fallback_to_stock_node(ctx):
    r = answer_question("E-01", "한국전력 채권 알려줘", ctx=ctx)
    assert "(Security)" not in r.think_trace and "ext_etf_holdings" not in r.think_trace
    assert "[Route] 상품군 — domestic_bonds" in r.think_trace


def test_ground_full_issuer_name_still_maps(ctx):
    r = answer_question("E-02", "한국전력공사 채권 알려줘", ctx=ctx)
    assert "pd_pbcm=" in r.think_trace.replace('"', "'") and "한국전력공사" in r.think_trace


def test_ground_cross_query_keeps_security_node(ctx):
    # 교차질의(보유한)면 구성종목 노드는 ext_* 대상이라 살아 있어야 한다
    if not any(n.node_type == "Security" for n in ctx.kg_nodes):
        pytest.skip("Security 노드 미빌드")
    r = answer_question("E-03", "삼성전자를 보유한 ETF 알려줘", ctx=ctx)
    assert "(Security)" in r.think_trace


# ── B 문지기 — 신용등급은 표준표로 ────────────────────────────────────────

def test_std_grade_table_loaded_and_shaped(ctx):
    # 표준표는 data/external/lookups/credit_grade_scale.csv — data/ 는 무시 대상이지만 이 코드북 한 건만
    # 추적한다(.gitignore '예외 2', 2026-09-04). 없으면 게이트가 데이터 값만으로 판정해 조용히 덜 답하므로,
    # 이제는 건너뛸 사유가 아니라 '추적된 파일이 지워졌다' 는 신호다.
    assert ctx.std_grades, "credit_grade_scale.csv 가 없다 — git 추적 대상이니 clone/pull 상태를 확인하세요"
    assert len(ctx.std_grades) >= 20
    for g in ctx.std_grades:
        assert gate._GRADE_SHAPE.match(g), g      # '등급 모양' 규칙은 표의 구조에서 온다


@pytest.mark.parametrize("q", ["CB 발행한 채권 알려줘", "DC형 퇴직연금에 편입 가능한 채권", "신용등급 AAA인 CD 채권"])
def test_gate_ignores_non_grade_uppercase(ctx, q):
    r = answer_question("B-01", q, ctx=ctx)
    assert "[Gate] 통과" in r.think_trace, r.think_trace


def test_gate_aaaa_still_rejected(ctx):
    r = answer_question("B-02", "신용등급 AAAA 채권 있어?", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "존재하지 않는" in r.answer


def test_gate_bbplus_answers_no_data(ctx):
    r = answer_question("B-03", "신용등급 BB+ 채권 알려줘", ctx=ctx)
    assert "0건" in r.think_trace and "해당 등급의 채권이 없습니다" in r.answer
    assert "존재하지 않는" not in r.answer


# ── B 문지기 — 연도는 SQL 사후 검사 ────────────────────────────────────────

class SQLPlanner:
    def __init__(self, sql):
        self.sql = sql
        self.calls = []

    def plan_sql(self, question, grounding):
        self.grounding = grounding
        return self.sql

    def compose_answer(self, question, rows, answer_rules=""):
        self.calls.append(answer_rules)
        return "답변"


def test_future_year_as_maturity_passes(ctx):
    p = SQLPlanner("SELECT pd_nm, mat_dt FROM domestic_bonds WHERE mat_dt BETWEEN 20270101 AND 20271231 LIMIT 5")
    r = answer_question("B-04", "2027년 만기 채권 알려줘", planner=p, ctx=ctx)
    # 채권 목록은 기계 조립(2026-09-02)이라 머리줄에 기준일이 정당하게 실린다 — 기각 문구("이후 시점의 정보는 확인할 수 없습니다")가 아닌지만 본다
    assert "[Execute]" in r.think_trace and "확인할 수 없습니다" not in r.answer and "[Answer] 채권 목록 답변 기계 조립" in r.think_trace
    assert "# 시점 주의" in p.grounding


def test_future_year_not_maturity_rejected(ctx):
    p = SQLPlanner("SELECT pd_nm, applied_yield FROM domestic_bonds ORDER BY applied_yield DESC LIMIT 5")
    r = answer_question("B-05", "2027년 채권 시장 전망 알려줘", planner=p, ctx=ctx)
    assert "[Execute]" not in r.think_trace and "2026-08-24" in r.answer
    assert "mat_dt 조건에 쓰이지 않음" in r.think_trace


def test_sql_uses_as_maturity_helper():
    assert gate.sql_uses_as_maturity("… WHERE domestic_bonds.mat_dt < 20270101 LIMIT 5", ["2027"])
    assert gate.sql_uses_as_maturity("… WHERE mat_dt BETWEEN '2026-10-01' AND '2026-10-31'", ["202610"])
    assert not gate.sql_uses_as_maturity("… WHERE isu_dt LIKE '2027%' LIMIT 5", ["2027"])
    assert gate.future_tokens("2027년 만기, 2026년 12월 상환") == ["2027", "202612"]
    assert gate.future_tokens("2026년 8월 상장") == []


# ── G 되묻기 · H 답변 규칙 ──────────────────────────────────────────────

def test_clarify_from_planner_becomes_answer(ctx):
    p = SQLPlanner(f"{CLARIFY_PREFIX} '등급' 이 신용등급(AAA~C)인지 위험등급(1~6등급)인지 알려주시겠어요?")
    r = answer_question("G-01", "등급 낮은 채권 알려줘", planner=p, ctx=ctx)
    assert "[Clarify]" in r.think_trace and r.answer.startswith("'등급' 이")
    assert not r.retrieved_context and not r.sql


def test_grounding_carries_clarify_rules_for_bonds(ctx):
    g = build_grounding(ctx, [], [B], cross=False)
    assert "# 되묻기 규칙" in g and "싸다" in g
    g2 = build_grounding(ctx, [], [DE], cross=False)
    assert "# 되묻기 규칙" in g2 and "안전한" in g2  # 2026-08-31 ETF 에도 clarify 블록 신설 (557eb3a)


def test_answer_rules_reach_composer(ctx):
    # 채권 목록은 2026-09-02 부터, AVG 를 품은 다열 집계 1행은 2026-09-06(QA r1 BH)부터 기계 조립(HCX 0회)이라
    # 답변 규칙이 composer 에 닿는 경로는 조립기 밖의 집계 꼴(COUNT + MIN 날짜)로 확인한다
    p = SQLPlanner("SELECT COUNT(DISTINCT pd_no) AS 종목수, MIN(mat_dt) AS 최단만기 FROM domestic_bonds WHERE std_pd_mcls_nm='국공채' LIMIT 1")
    r = answer_question("H-01", "국공채 종목 수랑 가장 이른 만기 알려줘", planner=p, ctx=ctx)
    assert "[Answer]" in r.think_trace and p.calls
    assert "신용등급 미부여" in p.calls[0] and "## domestic_bonds" in p.calls[0]


def test_planner_context_has_synonyms(ctx):
    txt = ctx.planner_context([B])
    assert "동의어" in txt and "통안채→통화안정채권" in txt


def test_router_typo_펌드(ctx):
    """2026-09-02 R7 재검 — '공모펌드' 오타가 미특정 → 4테이블로 빠져 답변 규칙 희석·이름 필터 꺼짐.
    '펌드' 1줄 흡수. 🔴 '펀 드'(띄어쓰기)는 상품 명사 매칭이 원문 기준이라 여전히 미특정 — pipeline 의
    SQL 사후 라우팅 보정(7-b)이 담당한다는 사실을 여기 못 박아 둔다."""
    r = route("공모펌드 중 1년 수익률이 가장 높은 3개 알려줘", ctx)
    assert r.tables == [PF] and r.decided
    assert route("코어테크 펌드 1년 수익률 알려줘", ctx).tables == [PF]
    assert not route("공모 펀 드 알려줘", ctx).decided


def test_router_manager_word_narrows_to_three_tables(ctx):
    """2R Q2-c — '운용사' 만 있는 질의(S11)는 미특정 4테이블 대신 펀드·ETF 3테이블(채권엔 운용사 컬럼 없음).
    상품 명사가 있으면 그것이 머리다("펀드를 … 운용사" → 펀드)."""
    r = route("순자산이 가장 큰 운용사 상위 3개 알려줘", ctx)
    # 3R B-2 정정 — 실측 2/2 에서 HCX 가 ETF 를 골라 템플릿 불발 → 운용사 집계 정본 = 공모펀드 마스터로 확정
    assert r.tables == [PF] and r.decided
    assert route("순자산 합계가 가장 큰 자산운용사 3곳 알려줘", ctx).tables == [PF]           # T2 (B-1: '순자산' 은 컬럼 동의어라 어휘 아님)
    assert set(route("ETF 순자산이 가장 큰 운용사 3곳 알려줘", ctx).tables) <= {DE, OE}         # 상품 명사가 있으면 그것이 머리
    assert route("삼성코리아대표증권자투자신탁 1년 수익률 알려줘", ctx).tables == [PF]           # 3R A-3 (T7)
    assert set(route("KODEX200 증권상장지수투자신탁 알려줘", ctx).tables) <= {DE, OE}
    assert route("운용 펀드 수가 가장 많은 자산운용사 5곳 알려줘", ctx).tables == [PF]
    assert route("펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘", ctx).tables == [PF]
