# -*- coding: utf-8 -*-
"""플래너·근거문서 테스트 — HCX 호출 없이 전부 오프라인으로 돈다.

네트워크를 타는 것은 HCXClient 뿐이고, 여기서는 가짜 클라이언트를 주입한다.
검증 대상은 두 가지다: ① LLM 출력에서 SQL 을 꺼내는 규칙 ② 프롬프트에 실리는 근거의 내용.
"""

import pytest

from src.hcx.planner import ANSWER_CONFIG, SQL_CONFIG, HCXPlanner, extract_sql
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import build_grounding, validate_sql


class FakeHCX:
    """HCXClient.complete 시그니처만 흉내낸다."""

    def __init__(self, text):
        self.text = text
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return type("R", (), {"text": self.text})()

    def close(self):
        pass


# ── extract_sql — 형식 위반 흡수 ────────────────────────────────────────

def test_extract_plain():
    assert extract_sql("SELECT pd_nm FROM domestic_etfs LIMIT 5") == "SELECT pd_nm FROM domestic_etfs LIMIT 5"


def test_extract_fenced():
    out = extract_sql("```sql\nSELECT pd_nm FROM domestic_etfs LIMIT 5\n```")
    assert out == "SELECT pd_nm FROM domestic_etfs LIMIT 5"


def test_extract_drops_preamble_and_semicolon():
    # 모델이 잡담을 붙이거나 세미콜론을 찍어도 한 문장만 남아야 한다
    out = extract_sql("네, 아래 쿼리입니다.\nSELECT pd_nm FROM domestic_etfs LIMIT 5;\n설명: ...")
    assert out == "SELECT pd_nm FROM domestic_etfs LIMIT 5"
    assert validate_sql(out) is None


def test_extract_multi_statement_is_truncated():
    # 🔴 다중 문장은 여기서 잘리고, 남은 것도 validate_sql 이 다시 본다
    out = extract_sql("SELECT 1 FROM public_funds LIMIT 1; DROP TABLE public_funds")
    assert "DROP" not in out.upper()


def test_extract_non_select_passes_through():
    # SELECT 가 아니면 억지로 고치지 않는다 — 기각은 validate_sql 의 몫
    assert validate_sql(extract_sql("DELETE FROM domestic_etfs")) is not None


# ── HCXPlanner — 주입한 가짜 클라이언트로 왕복 ──────────────────────────

def test_planner_roundtrip():
    sql_c = FakeHCX("```sql\nSELECT pd_nm FROM domestic_etfs LIMIT 5\n```")
    ans_c = FakeHCX("  국내 ETF 5건입니다.  ")
    p = HCXPlanner(sql_client=sql_c, answer_client=ans_c)

    sql = p.plan_sql("국내 ETF 알려줘", "# 스키마\n## domestic_etfs\npd_nm(상품명)")
    assert sql == "SELECT pd_nm FROM domestic_etfs LIMIT 5"
    assert "pd_nm(상품명)" in sql_c.calls[0][1]        # 근거문서가 프롬프트에 실렸는가
    assert "LIMIT" in sql_c.calls[0][0]                # 시스템 프롬프트에 LIMIT 규칙이 있는가

    assert p.compose_answer("국내 ETF 알려줘", "pd_nm\nTIGER 200") == "국내 ETF 5건입니다."
    assert "TIGER 200" in ans_c.calls[0][1]


def test_answer_prompt_forbids_outside_facts():
    # 환각 방지 문구가 시스템 프롬프트에서 사라지면 안 된다 (감점 1순위)
    from src.hcx.planner import _ANSWER_SYSTEM

    assert "추정하지 않는다" in _ANSWER_SYSTEM and "2026-08-22" in _ANSWER_SYSTEM


def test_sql_budget_fits_case_expressions():
    # 🔄 2026-08-30 밤 — "SQL 은 짧다" 전제가 깨졌다. 채권 추천 SQL 은 yaml '구조'(693자)·'보강'(533자) CASE 를 그대로 옮겨
    #    1,757자(추정 660~840토큰)라 512 에서 잘린다. max_tokens 는 상한이지 사용량이 아니므로 rate limit 비용은 그대로다.
    assert SQL_CONFIG.max_tokens >= 1024
    assert SQL_CONFIG.temperature == 0.0


# ── 근거문서 — DB 필요 ──────────────────────────────────────────────────

needs_db = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@needs_db
def test_grounding_has_three_sections(ctx):
    org = next(n for n in ctx.kg_nodes if n.node_id == "Org_00080008")
    g = build_grounding(ctx, [org], ["domestic_etfs"], cross=False)
    assert "# KG 개체 매핑" in g and "# 도메인 규칙" in g and "# 스키마" in g
    assert "pd_abrv_nm" in g                      # 스키마의 실제 컬럼
    assert "domestic_bonds" not in g              # 탐지된 테이블만 실린다 (토큰=처리량)


@needs_db
def test_grounding_gives_values_not_node_ids(ctx):
    # 🔴 개체 ID 가 프롬프트에 실리면 모델이 그걸 값으로 쓴다 (2026-08-26 실측 회귀)
    org = next(n for n in ctx.kg_nodes if n.node_id == "Org_00080008")
    g = build_grounding(ctx, [org], ["domestic_etfs"], cross=False)
    assert "Org_00080008" not in g
    assert "'미래에셋'" in g and "cu_fund_mgmt_co" in g
    assert "or_co_xtn_itt_cd" not in g            # 대상 아닌 테이블(public_funds) alias 는 빠진다


@needs_db
def test_ground_picks_node_that_has_target_table_alias(ctx):
    # '미래에셋자산운용' 은 채권 발행사 노드에도 걸린다. 국내ETF 질의면 ETF alias 를 가진 노드를 골라야 한다
    from src.runtime.pipeline import _ground

    hits, lines = _ground("미래에셋자산운용이 운용하는 국내 ETF 알려줘", ctx, ["domestic_etfs"])
    assert any(n.node_id == "Org_00080008" for n in hits), lines
    assert not any(n.node_id.startswith("Org_issuer_") for n in hits), lines


@needs_db
def test_grounding_cross_includes_ext(ctx):
    g = build_grounding(ctx, [], ["domestic_etfs"], cross=True)
    assert "ext_etf_holdings" in g and "constituent" in g


@needs_db
def test_grounding_falls_back_to_all_masters(ctx):
    g = build_grounding(ctx, [], [], cross=False)
    for t in ("domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"):
        assert t in g


@needs_db
def test_schema_text_covers_all_masters(ctx):
    # schema_metadata 280컬럼이 로드됐는가 — 빠지면 플래너가 컬럼을 지어낸다
    assert sum(len(ctx.schema[t]) for t in
               ("domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds")) == 280


@needs_db
def test_cross_grounding_has_join_key(ctx):
    # 🔴 조인 키가 없으면 모델이 마스터에 없는 컬럼을 WHERE 에 쓴다 (2026-08-26 실측 회귀)
    g = build_grounding(ctx, [], ["domestic_etfs"], cross=True)
    assert "ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no" in g
    assert "# 교차질의 조인 키" in g


@needs_db
def test_gate_rejects_crd_token_with_korean_particle(ctx):
    # 🔴 '\b' 는 한글 조사 앞에서 경계가 서지 않는다 — 'AAAA인' 이 게이트를 통과했었다
    from src.runtime.pipeline import answer_question

    for q in ("신용등급 AAAA인 채권 알려줘", "신용등급 AAAA등급 채권 있어?"):
        r = answer_question("T-CRD", q, ctx=ctx)
        assert "[Gate] 기각" in r.think_trace, q
        assert "AAAA" in r.think_trace


@needs_db
def test_gate_still_passes_valid_grade_with_particle(ctx):
    from src.runtime.pipeline import answer_question

    r = answer_question("T-CRD2", "신용등급 AAA인 회사채 알려줘", ctx=ctx)
    assert "[Gate] 통과" in r.think_trace


def test_ensure_limit_appends_when_missing():
    # 🔴 집계 질의는 LIMIT 을 안 쓴다. 기각하면 정답 SQL 을 만들고도 답을 못 낸다 (2026-08-26 회귀)
    from src.runtime.pipeline import MAX_ROWS, ensure_limit

    sql, changed = ensure_limit("SELECT COUNT(*) FROM domestic_bonds WHERE bd_knd='MBS'")
    assert changed and sql.endswith(f"LIMIT {MAX_ROWS}")
    assert validate_sql(sql) is None

    keep, changed2 = ensure_limit("SELECT pd_nm FROM domestic_etfs LIMIT 5")
    assert not changed2 and keep.endswith("LIMIT 5")
