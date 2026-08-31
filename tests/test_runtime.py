# -*- coding: utf-8 -*-
"""런타임 파이프라인 테스트 — 검증 게이트(BUILD_PLAN §5⑤) 문항이 실제로 기각·매핑되는지.

HCX 없이 전부 오프라인으로 돈다. DB(data/financial_products.db)가 없으면 skip.
"""

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question, validate_sql

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── 네거티브 게이트 — HCX 0회 기각 ──────────────────────────────────────

def test_absent_overseas_risk(ctx):
    r = answer_question("T-01", "위험등급 낮은 해외ETF 추천해줘", ctx=ctx)
    assert "hasRiskGrade" in r.think_trace and "[Gate] 기각" in r.think_trace
    assert "제공되지" in r.answer or "확인할 수 없" in r.answer


def test_absent_bond_index(ctx):
    r = answer_question("T-02", "기초지수를 추종하는 채권 알려줘", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "tracksIndex" in r.think_trace


def test_enum_crd_aaaa(ctx):
    r = answer_question("T-03", "신용등급 AAAA 채권 있어?", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "AAAA" in r.think_trace
    assert "존재하지 않는" in r.answer


def test_enum_crd_valid_not_rejected(ctx):
    # 정상 등급(AAA)은 기각되면 안 된다
    r = answer_question("T-04", "신용등급 AAA 채권 알려줘", ctx=ctx)
    assert "[Gate] 통과" in r.think_trace


def test_risk_grade_out_of_range(ctx):
    r = answer_question("T-05", "위험등급 9등급 펀드 보여줘", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "0~6" in r.think_trace


def test_risk_grade_6_valid(ctx):
    # 🔴 규칙 §4 — 6등급은 정상이다 (1~5 제약은 오류). 기각되면 안 된다
    r = answer_question("T-06", "위험등급 6등급 채권 알려줘", ctx=ctx)
    assert "[Gate] 통과" in r.think_trace


def test_cutoff_future(ctx):
    # 🔴 08-30: 연도만 보고 게이트에서 기각하지 않는다 — 플래너가 없으면 해석을 검사할 수 없어 기준일 안내로 끝낸다
    r = answer_question("T-07", "2027년 만기 예정 수익률 전망 알려줘", ctx=ctx)
    assert "[Gate] 기각" not in r.think_trace and "2026-08-22" in r.answer
    assert "사후 판정" in r.think_trace


# ── KG Ground — 표기 매핑 ───────────────────────────────────────────────

def test_ground_org(ctx):
    r = answer_question("T-08", "미래에셋이 운용하는 펀드 알려줘", ctx=ctx)
    assert "or_co_xtn_itt_cd='00080008'" in r.think_trace.replace('"', "'")


def test_ground_index(ctx):
    r = answer_question("T-09", "KOSPI200 추종 상품 알려줘", ctx=ctx)
    assert "Idx_KOSPI200" in r.think_trace


# ── SQL Guard ───────────────────────────────────────────────────────────

def test_sql_guard():
    ok = "SELECT pd_nm FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 5"
    assert validate_sql(ok) is None
    assert validate_sql("DELETE FROM domestic_etfs") is not None
    assert validate_sql("SELECT * FROM users LIMIT 5") is not None          # 화이트리스트 밖
    assert validate_sql("SELECT 1 FROM public_funds") is not None           # LIMIT 누락
    assert validate_sql("SELECT 1 FROM public_funds LIMIT 1; DROP TABLE x") is not None


# ── Plan 연결 시 경로 (가짜 planner 로 Execute 까지) ─────────────────────

class FakePlanner:
    def plan_sql(self, question, grounding):
        return "SELECT count(*) AS n FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 1"

    def compose_answer(self, question, rows, answer_rules=""):
        return f"조회 결과: {rows.splitlines()[-1]}건"


def test_full_path_with_planner(ctx):
    r = answer_question("T-10", "국내 ETF 몇 개야?", planner=FakePlanner(), ctx=ctx)
    assert "[Execute] 1행 조회" in r.think_trace
    assert "1235" in r.retrieved_context   # ETF 1,235건 — 2차 배포본(2026-08-22) 실측


def test_cutoff_august_allowed(ctx):
    # 기준일 2026-08-22 — 8월은 기준일 포함 월이라 게이트를 통과해야 한다 (2차 데이터 전환 회귀 테스트)
    r = answer_question("T-11", "2026년 8월 상장한 국내 ETF 알려줘", ctx=ctx)
    assert "[Gate] 기각" not in r.think_trace


def test_cutoff_october_rejected(ctx):
    r = answer_question("T-12", "2026년 10월에 상장 예정인 국내 ETF 알려줘", ctx=ctx)
    assert "2026-08-22" in r.answer and "['202610']" in r.think_trace


def test_planner_context_has_rules(ctx):
    txt = ctx.planner_context(["domestic_etfs", "public_funds"])
    assert "## domestic_etfs" in txt and "구매가능" in txt


def test_cross_query_guard_allows_ext_join():
    from src.runtime.pipeline import validate_sql
    ok = "SELECT e.pd_abrv_nm FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no WHERE h.constituent LIKE '%삼성전자%' LIMIT 10"
    assert validate_sql(ok) is None
    assert validate_sql("SELECT * FROM ext_etf_holdings LIMIT 5") is not None      # 마스터 없이 ext 단독 금지
    assert validate_sql("SELECT * FROM domestic_etfs JOIN sqlite_master LIMIT 5") is not None


def test_cross_query_detected(ctx):
    from src.runtime import gate
    assert gate.is_cross_query("삼성전자를 보유한 국내/해외 ETF와 공모펀드를 연 수익률 기준 TOP10 알려줘", [])
    assert gate.is_cross_query("채권과 ETF 중 뭐가 안전해?", ["domestic_bonds", "domestic_etfs"])
    assert not gate.is_cross_query("KODEX 200 총보수 알려줘", ["domestic_etfs"])


def test_security_grounding_no_false_positive(ctx):
    """삼성전자 ≠ 삼성전기 — Security 노드가 KG 에 있을 때만 검사 (security_auto.yaml 빌드 전이면 skip)."""
    sec = [n for n in ctx.kg_nodes if n.node_type == "Security"]
    if not sec:
        pytest.skip("Security 노드 미빌드 — build_ontology.py 선행 필요")
    r = answer_question("T-20", "삼성전자를 보유한 ETF 알려줘", ctx=ctx)
    assert "'삼성전자'" in r.think_trace and "(Security)" in r.think_trace
    assert "삼성전기" not in r.think_trace


def test_execute_renders_dates_as_int_and_strips_padding():
    """REAL 로 저장된 날짜가 '20271231.0' 으로, 고정폭 pd_nm 이 꼬리 공백째로 답변에 실리던 것 (2026-08-30 밤)."""
    from src.runtime.pipeline import _cell, _execute
    assert _cell(20271231.0, "mat_dt") == "20271231"
    assert _cell(7.123, "applied_yield") == "7.123"
    assert _cell(None, "crd_grd") == ""
    assert _cell("  국고채권 01500-2703  ", "pd_nm") == "국고채권 01500-2703"
    rows, n = _execute("SELECT pd_nm, mat_dt FROM domestic_bonds WHERE mat_dt >= 20260822 LIMIT 3")
    assert n == 3
    for line in rows.splitlines()[1:]:
        name, mat = line.split(" | ")
        assert name == name.strip() and mat.isdigit() and len(mat) == 8


# ── 날짜 리터럴·만기 하한 보정 — 2026-08-31 "3년 안에 만기되는 안전한 채권" 오답 회귀 ──────────

def test_normalize_date_literals_arithmetic_bomb():
    from src.runtime.pipeline import normalize_date_literals
    sql = "SELECT pd_nm FROM domestic_bonds WHERE mat_dt <= 2029-08-22 AND pd_risk_gcd IN ('15','16') LIMIT 30"
    fixed, changed = normalize_date_literals(sql)
    assert changed and "20290822" in fixed and "2029-08-22" not in fixed


def test_normalize_date_literals_quoted_and_noop():
    from src.runtime.pipeline import normalize_date_literals
    fixed, changed = normalize_date_literals("SELECT 1 FROM domestic_bonds WHERE mat_dt <= '2029-8-2' LIMIT 1")
    assert changed and "20290802" in fixed
    same, changed2 = normalize_date_literals("SELECT 1 FROM domestic_bonds WHERE mat_dt <= 20290822 LIMIT 1")
    assert not changed2


def test_maturity_lower_bound_injection():
    from src.runtime.pipeline import ensure_maturity_lower_bound
    fixed, changed = ensure_maturity_lower_bound("SELECT pd_nm FROM domestic_bonds WHERE mat_dt <= 20290822 LIMIT 5")
    assert changed and "(mat_dt > 20260822 AND mat_dt <= 20290822)" in fixed
    # BETWEEN(자체 하한)·과거 상한("만기 지난")·하한 보유 SQL 은 건드리지 않는다
    assert not ensure_maturity_lower_bound("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20270101 AND 20271231 LIMIT 1")[1]
    assert not ensure_maturity_lower_bound("SELECT 1 FROM domestic_bonds WHERE mat_dt <= 20260821 LIMIT 1")[1]
    assert not ensure_maturity_lower_bound("SELECT 1 FROM domestic_bonds WHERE mat_dt > 20260822 AND mat_dt <= 20290822 LIMIT 1")[1]


class BuggyMaturityPlanner:
    """2026-08-31 챗봇 실측 오답을 낸 SQL 그대로 — 파이프라인이 스스로 복구해야 한다."""

    def plan_sql(self, question, grounding):
        return ("SELECT pd_nm, pd_risk_gcd, mat_dt, dur FROM domestic_bonds "
                "WHERE mat_dt <= 2029-08-22 AND pd_risk_gcd IN ('15', '16') ORDER BY applied_yield DESC LIMIT 30")

    def compose_answer(self, question, rows, answer_rules=""):
        return "ok"


def test_full_path_buggy_date_sql_recovers(ctx):
    r = answer_question("T-20", "만기까지 들고 갈 건데, 3년 안에 만기되는 안전한 채권 몇 개만 골라줘",
                        planner=BuggyMaturityPlanner(), ctx=ctx)
    assert "[Guard] 날짜 리터럴 보정" in r.think_trace
    assert "[Guard] 만기 하한 보정" in r.think_trace
    assert "(mat_dt > 20260822 AND mat_dt <= 20290822)" in r.sql
    assert "산금채 1706복10A" not in r.retrieved_context   # 만기일 미수록(mat_dt=0) 행이 더는 새지 않는다
    assert "[Execute] 30행 조회" in r.think_trace


def test_planner_context_has_date_rules(ctx):
    g = ctx.planner_context(["domestic_bonds"])
    assert "날짜표기" in g and "만기윈도우" in g


def test_planner_context_credit_rule_imperative(ctx):
    # 2026-08-31 실측: '정부가 책임지는' 질의에 HCX 가 신용보강 필터를 무시하고 국공채만 조회 →
    # 규칙을 지시문 + 복사용 완성 WHERE 로 승격 (c788893 패턴). 안내판에 그 형태로 실리는지 고정.
    g = ctx.planner_context(["domestic_bonds"])
    assert "정부가 책임지는" in g                      # 트리거 어휘 (실측 질문 표현)
    assert "반드시 WHERE" in g and "국공채 단독 필터는 오답" in g
    assert "TRIM(pd_pbcm) IN ('한국주택금융공사','한국토지주택공사','한국산업은행','(주)중소기업은행')" in g


# ── 두 자리 연도 감지 + 만기 연도 교정 — 2026-08-31 "28년 12월까지 국고채" 오답 회귀 ──────────

def test_future_tokens_two_digit_year():
    from src.runtime import gate
    assert gate.future_tokens("28년 12월까지 만기가 돌아오는 국고채 알려줘") == ["2028"]
    assert gate.future_tokens("28년까지 만기되는 채권") == ["2028"]
    # 기간 표기는 연도가 아니다 — 오탐이 만기 질의를 기각시킨다
    assert gate.future_tokens("잔존만기가 28년 넘는 채권") == []
    assert gate.future_tokens("10년 만기 채권 알려줘") == []


def test_align_maturity_year():
    from src.runtime.pipeline import align_maturity_year
    sql = "SELECT pd_nm FROM domestic_bonds WHERE mat_dt > 20260822 AND mat_dt <= 20291231 LIMIT 30"
    fixed, changed = align_maturity_year(sql, ["2028"])
    assert changed and "mat_dt <= 20281231" in fixed and "20291231" not in fixed
    # 발동 조건 밖 — 연도 일치 / 복수 연도 / 상한 없음은 불개입
    assert not align_maturity_year(sql, ["2029"])[1]
    assert not align_maturity_year(sql, ["2027", "2028"])[1]
    assert not align_maturity_year("SELECT 1 FROM domestic_bonds WHERE mat_dt > 20270101 LIMIT 1", ["2028"])[1]


class BuggyYearPlanner:
    """2026-08-31 실측 오답 SQL 그대로 — 연도 오기 + 대분류 뭉개기. 연도는 파이프라인이 교정해야 한다."""

    def plan_sql(self, question, grounding):
        return ("SELECT pd_nm, mat_dt FROM domestic_bonds WHERE mat_dt > 20260822 AND mat_dt <= 20291231 "
                "AND std_pd_mcls_nm IN ('국공채', '특수채') LIMIT 30")

    def compose_answer(self, question, rows, answer_rules=""):
        return "ok"


def test_full_path_year_typo_recovers(ctx):
    r = answer_question("T-21", "28년 12월까지 만기가 돌아오는 국고채 알려줘",
                        planner=BuggyYearPlanner(), ctx=ctx)
    assert "[Guard] 만기 연도 교정" in r.think_trace
    assert "mat_dt <= 20281231" in r.sql
    # 🔴 교정 후 사후검사 통과 — 교정 전 SQL 로 검사하면 '2028 미사용' 으로 억울하게 기각된다
    assert "시점·전망 질의로 판정" not in r.think_trace
    assert "[Execute] 30행 조회" in r.think_trace


def test_expand_grade_comparison():
    from src.runtime.pipeline import expand_grade_comparison
    sql = "SELECT pd_nm, srfc_irt FROM domestic_bonds WHERE crd_grd='A-' AND srfc_irt > 5 LIMIT 30"
    # 2026-08-31 실측 사고 — 'a등급 이상'(소문자) 이 단일 등급 '=' 로 좁혀짐 → 7종 IN 확장
    fixed, changed = expand_grade_comparison(sql, "a등급 이상 회사채 중 표면금리가 5% 넘는 것을 알려줘")
    assert changed
    assert "TRIM(crd_grd) IN ('AAA', 'AA+', 'AA0', 'AA-', 'A+', 'A0', 'A-')" in fixed
    assert "crd_grd='A-'" not in fixed
    # 명시 접미사는 그 표기부터 — 'AA- 이상' = 4종
    fixed, changed = expand_grade_comparison(sql, "AA- 이상 채권만")
    assert changed and "TRIM(crd_grd) IN ('AAA', 'AA+', 'AA0', 'AA-')" in fixed
    # 이하 — 접미사 없는 통칭은 그 급 최상단부터 (BBB 이하 = BBB+ 부터 8종)
    fixed, changed = expand_grade_comparison(sql, "BBB등급 이하인 채권")
    assert changed and "TRIM(crd_grd) IN ('BBB+', 'BBB0', 'BBB-', 'BB0', 'BB-', 'B+', 'B-', 'C0')" in fixed
    # 부등호 문자열 비교(사전순 ≠ 서열)도 치환 대상
    fixed, changed = expand_grade_comparison(
        "SELECT 1 FROM domestic_bonds WHERE crd_grd >= 'A0' LIMIT 1", "A등급 이상 채권")
    assert changed and "TRIM(crd_grd) IN (" in fixed
    # 발동 조건 밖 — 이상/이하 없음 / 이미 IN / 범위(표기 2개) / crd_grd 비교 없음 / 이미 맞는 단일 등급
    assert not expand_grade_comparison(sql, "A등급 회사채의 표면금리")[1]
    assert not expand_grade_comparison(
        "SELECT 1 FROM domestic_bonds WHERE TRIM(crd_grd) IN ('AAA','AA+') LIMIT 1", "AA등급 이상")[1]
    assert not expand_grade_comparison(sql, "A등급 이상 AA등급 이하")[1]
    assert not expand_grade_comparison("SELECT 1 FROM domestic_bonds WHERE srfc_irt > 5 LIMIT 1", "A등급 이상")[1]
    assert not expand_grade_comparison("SELECT 1 FROM domestic_bonds WHERE crd_grd = 'AAA' LIMIT 1", "AAA 이상")[1]


class BuggyGradePlanner:
    """2026-08-31 실측 오답 SQL 그대로 — 'A등급 이상' 을 crd_grd='A-' 단일 등급으로 좁힘(모수 599 → 49).
    파이프라인이 서열 IN 으로 확장해야 한다. 종류 조건 부재는 규칙(종류필터·동의어 대분류)이 막는다."""

    def plan_sql(self, question, grounding):
        return "SELECT pd_nm, bd_intp_tcd, srfc_irt FROM domestic_bonds WHERE crd_grd='A-' AND srfc_irt > 5 LIMIT 30"

    def compose_answer(self, question, rows, answer_rules=""):
        return "ok"


def test_full_path_grade_floor_expands(ctx):
    r = answer_question("T-22", "A등급 이상 회사채 중 표면금리가 5% 넘는 것을 알려줘",
                        planner=BuggyGradePlanner(), ctx=ctx)
    assert "[Guard] 등급 서열 확장" in r.think_trace
    assert "TRIM(crd_grd) IN ('AAA', 'AA+', 'AA0', 'AA-', 'A+', 'A0', 'A-')" in r.sql
    assert "[Execute] 30행 조회" in r.think_trace


_BACKSTOP_BUGGY_SQL = ("SELECT pd_nm, applied_yield, std_pd_mcls_nm, pd_risk_gcd FROM domestic_bonds "
                       "WHERE (TRIM(std_pd_mcls_nm)='국공채' OR COALESCE(TRIM(pd_pbcm),'')='한국은행' "
                       "OR pd_nm LIKE '%(정부보증)%') ORDER BY applied_yield DESC LIMIT 5")


def test_ensure_credit_backstop():
    from src.runtime.pipeline import ensure_credit_backstop
    q = "정부가 책임지는채권 중에서 수익률 높은 순으로 5개 알려줘"
    # 2026-08-31 저녁 서버 실측 SQL 그대로 — C층 탈락 → C층 + 랭킹 제외 조건 주입
    fixed, changed = ensure_credit_backstop(_BACKSTOP_BUGGY_SQL, q)
    assert changed
    assert "'한국주택금융공사','한국토지주택공사','한국산업은행','(주)중소기업은행'" in fixed
    assert fixed.count("COALESCE(TRIM(pd_pbcm),'')='한국은행'") == 1     # 이미 있는 층은 중복 주입 금지
    assert "applied_yield > 0" in fixed and "pd_risk_gcd <> '11'" in fixed
    assert "bd_ofr_tcd <> '사모'" in fixed
    assert fixed.index("<> '사모'") < fixed.index("ORDER BY")            # 제외는 WHERE 끝, 정렬 앞
    # 랭킹 신호 없는 사실확인·집계 질의 — 층은 주입하되 제외는 넣지 않는다 (고위험제외 규칙)
    fixed2, changed2 = ensure_credit_backstop(_BACKSTOP_BUGGY_SQL, "정부가 보증하는 채권이 몇 개야?")
    assert changed2 and "한국주택금융공사" in fixed2 and "사모" not in fixed2
    # 발동 조건 밖 — 정부보강 어휘 없음 / 앵커(국공채 필터) 없음 / 이미 완성식
    assert not ensure_credit_backstop(_BACKSTOP_BUGGY_SQL, "국공채 수익률 높은 순 5개")[1]
    assert not ensure_credit_backstop("SELECT 1 FROM domestic_bonds WHERE crd_grd='AAA' LIMIT 1", q)[1]
    full = _BACKSTOP_BUGGY_SQL.replace("OR pd_nm LIKE '%(정부보증)%')",
        "OR pd_nm LIKE '%(정부보증)%' OR TRIM(pd_pbcm) IN ('한국주택금융공사','한국토지주택공사','한국산업은행','(주)중소기업은행')) "
        "AND applied_yield > 0 AND pd_risk_gcd <> '11' AND COALESCE(TRIM(crd_grd),'') <> 'C0' AND bd_ofr_tcd <> '사모'")
    assert not ensure_credit_backstop(full, q)[1]


def test_ensure_risk_name_column():
    from src.runtime.pipeline import ensure_risk_name_column
    fixed, changed = ensure_risk_name_column(_BACKSTOP_BUGGY_SQL)
    assert changed and "pd_risk_gcd, pd_risk_nm FROM" in fixed
    # 불개입 — 이미 있음 / SELECT 에 코드 없음(WHERE 만) / 함수 인자
    assert not ensure_risk_name_column(fixed)[1]
    assert not ensure_risk_name_column("SELECT pd_nm FROM domestic_bonds WHERE pd_risk_gcd='16' LIMIT 1")[1]
    assert not ensure_risk_name_column("SELECT COUNT(pd_risk_gcd) FROM domestic_bonds")[1]


class BuggyBackstopPlanner:
    """2026-08-31 저녁 서버 실측 오답 SQL 그대로 — 지시문 승격(fbc7e4d) 후에도 C층·제외 절 탈락."""

    def plan_sql(self, question, grounding):
        return _BACKSTOP_BUGGY_SQL

    def compose_answer(self, question, rows, answer_rules=""):
        return "ok"


def test_full_path_backstop_recovers(ctx):
    r = answer_question("T-23", "정부가 책임지는채권 중에서 수익률 높은 순으로 5개 알려줘",
                        planner=BuggyBackstopPlanner(), ctx=ctx)
    assert "[Guard] 신용보강 층 주입" in r.think_trace
    assert "[Guard] 위험등급 이름 보강" in r.think_trace
    assert "한국주택금융공사" in r.sql and "pd_risk_nm" in r.sql
    assert "[Execute] 5행 조회" in r.think_trace
    # 원 사고의 누락 1위(C층 5.859%)가 복귀하고, 사모/1등급 14.05% 는 제외된다
    assert "토지주택채권 330(변)" in r.retrieved_context
    assert "14.053" not in r.retrieved_context
