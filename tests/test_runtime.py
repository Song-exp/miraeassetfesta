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
    # 2026-09-02 KG 1R S6 — 범위는 테이블별 선언(range_by_table)에서: 펀드는 1~6 (종전 공용 상수 0~6)
    assert "[Gate] 기각" in r.think_trace and "1~6" in r.think_trace and "1(매우 높은 위험)~6" in r.answer


def test_risk_grade_6_valid(ctx):
    # 🔴 규칙 §4 — 6등급은 정상이다 (1~5 제약은 오류). 기각되면 안 된다
    r = answer_question("T-06", "위험등급 6등급 채권 알려줘", ctx=ctx)
    assert "[Gate] 통과" in r.think_trace


def test_cutoff_future(ctx):
    # 🔴 08-30: 연도만 보고 게이트에서 기각하지 않는다 — 플래너가 없으면 해석을 검사할 수 없어 기준일 안내로 끝낸다
    r = answer_question("T-07", "2027년 만기 예정 수익률 전망 알려줘", ctx=ctx)
    assert "[Gate] 기각" not in r.think_trace and "2026-08-24" in r.answer
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
    # 8R B-4″-b — ETF 기본모수 확정식(`pd_grp_no='ETF' AND pd_sale_yn=1`)이 서면서 기준이 바뀌었다.
    #   1,780(무필터) → 1,235(ETF만) → **1,160(ETF∧판매중)**. 판매중 기준은 이 프로젝트의 기본모수 규칙이고
    #   KG 4R G1(`domestic_etfs: pd_sale_yn=1`)이 명시한 축이다 — KG 심사관 gold 도 같은 축을 쓴다
    #   (X8 'S&P500 추종 국내 ETF' 24 · AA22 광의 45 둘 다 pd_sale_yn=1 에서 재현).
    assert "1160" in r.retrieved_context


def test_manager_full_name_grounds(ctx):
    """FND-034 실측 — 라벨이 약칭('삼성', 2자)뿐이라 매칭 하한(한글 3자)에 걸려 Ground 0 →
    플래너가 수탁사 코드 서브쿼리를 지어내 '0개' 오답. 정식명 라벨 병합('삼성/삼성자산운용')로
    '삼성자산운용' 질의가 운용사 코드에 매핑돼야 한다."""
    from src.runtime.pipeline import _ground
    _, lines = _ground("삼성자산운용이 운용하는 공모펀드는 몇 개야?", ctx, ["public_funds"])
    assert any("Org_00040010" in l and "or_co_xtn_itt_cd" in l for l in lines), lines
    # 약칭 2자('삼성')는 여전히 매칭에 참여하지 않는다 — '삼성전자' 질의 오탐 방지
    _, l2 = _ground("삼성전자를 담은 공모펀드 알려줘", ctx, ["public_funds"], cross=True)
    assert not any("Org_00040010" in l for l in l2), l2
    # 🔴 회귀 보호 — 정식명을 label_ko 에 '/' 병합하면 조각에 단어경계가 붙어 브랜드+상품명
    #    합성어('미래에셋코어테크')의 브랜드 매칭이 죽는다 (2026-09-01 저녁 FND-016 재검 실측)
    _, l3 = _ground("미래에셋코어테크 펀드 1년 수익률 알려줘", ctx, ["public_funds"])
    assert any("Org_00080008" in l for l in l3), l3


def test_route_narrowed_by_ground_and_series_no_mismatch(ctx):
    """FND-032 실측 — '펀드' 명사 없는 질의가 미특정으로 빠져 FROM domestic_bonds 완전일치 → 오거절.

    ① Ground 매핑이 public_funds 만 가리키면 라우팅을 그 상품군으로 좁힌다.
    ② Fund 노드의 코드가 질문의 호수와 다를 수 있으면(디스커버리 노드 rptt = 4호에 2호 질문)
       코드 매핑을 싣지 않고 이름 검색을 지시한다 — 4호 값이 2호의 답으로 나가는 것을 막는다.
    """
    r = answer_question("T-032", "미래에셋디스커버리증권투자신탁 2호 위험등급 알려줘", ctx=ctx)
    # 3R A-3 — '투자신탁' 이 상품 명사(§3.3 법적형태)라 라우터가 바로 public_funds 를 정한다(종전 미특정 → Ground 보정 경로)
    assert "머리명사 투자신탁" in r.think_trace and "public_funds" in r.think_trace
    assert "코드 매핑을 싣지 않는다" in r.think_trace and "rptt_ksd_itm_no" not in r.think_trace
    # 호수 없는 질의는 코드 매핑 유지(불개입)
    r2 = answer_question("T-032b", "미래에셋디스커버리증권투자신탁 위험등급 알려줘", ctx=ctx)
    assert "public_funds" in r2.think_trace and "rptt_ksd_itm_no" in r2.think_trace


def test_cutoff_august_allowed(ctx):
    # 기준일 2026-08-22 — 8월은 기준일 포함 월이라 게이트를 통과해야 한다 (2차 데이터 전환 회귀 테스트)
    r = answer_question("T-11", "2026년 8월 상장한 국내 ETF 알려줘", ctx=ctx)
    assert "[Gate] 기각" not in r.think_trace


def test_cutoff_october_rejected(ctx):
    r = answer_question("T-12", "2026년 10월에 상장 예정인 국내 ETF 알려줘", ctx=ctx)
    assert "2026-08-24" in r.answer and "['202610']" in r.think_trace


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
    # 🔴 2026-08-31 서버 실측 — '담은' 이 힌트에 없어 단일 라우팅에서 종목 노드가 규칙 E 로 버려졌다
    assert gate.is_cross_query("Li Auto 담은 국내 ETF 알려줘", ["domestic_etfs"], 1)
    assert gate.is_cross_query("삼성전자가 담긴 ETF", ["domestic_etfs"], 1)


def test_join_keys_no_isin_join(ctx):
    """해외ETF 조인은 티커 경유 — isin 조인은 63종 중복으로 다른 ETF 구성종목이 붙는다(오배정 8건 실증)."""
    from src.runtime.pipeline import JOIN_KEYS
    ovs = dict(JOIN_KEYS)["ext_ovs_etf_holdings"]
    assert "pd_isin_cd" not in ovs and "etf_ticker" in ovs


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
    rows, n = _execute("SELECT pd_nm, mat_dt FROM domestic_bonds WHERE mat_dt >= 20260824 LIMIT 3")
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
    same, changed2 = normalize_date_literals("SELECT 1 FROM domestic_bonds WHERE mat_dt <= 20290824 LIMIT 1")
    assert not changed2


def test_normalize_date_literals_integer_arithmetic():
    """2026-09-05 #68 — 덧셈판 산술폭탄: "지난달에 만기된 채권" 이 `mat_dt <= 20260824+90` 로 나갔다.
    SQLite 정수 덧셈(20260914)으로 실행은 되지만 90일 뒤(20261122)가 아니다 — 달력 계산 리터럴로 치환한다."""
    from src.runtime.pipeline import normalize_date_literals as f
    fixed, changed = f("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20260824 AND 20260930 AND mat_dt <= 20260824+90 LIMIT 30")
    assert changed and "mat_dt <= 20261122" in fixed and "+" not in fixed
    assert "20270824" in f("SELECT 1 FROM domestic_bonds WHERE mat_dt <= 20260824 + 10000 LIMIT 1")[0]    # 10000 = 1년
    assert "20270224" in f("SELECT 1 FROM domestic_bonds WHERE mat_dt <= 20260824+600 LIMIT 1")[0]        # 600 = 6개월
    assert "isu_dt >= 20260225" in f("SELECT 1 FROM domestic_bonds WHERE isu_dt >= 20260824-180 LIMIT 1")[0]   # 뺄셈·발행 축도
    # 날짜 모양이 아닌 산술은 존중 · 소수점 붙은 리터럴 뒤의 숫자는 산술이 아니다
    assert not f("SELECT 1 FROM domestic_bonds WHERE applied_yield > 5+1 LIMIT 1")[1]
    assert not f("SELECT 1 FROM domestic_bonds WHERE mat_dt >= 20260824.0 LIMIT 1")[1]


def test_maturity_lower_bound_injection():
    from src.runtime.pipeline import ensure_maturity_lower_bound
    fixed, changed = ensure_maturity_lower_bound("SELECT pd_nm FROM domestic_bonds WHERE mat_dt <= 20290824 LIMIT 5")
    assert changed and "(mat_dt >= 20260824 AND mat_dt <= 20290824)" in fixed
    # BETWEEN(자체 하한)·과거 상한("만기 지난")·하한 보유 SQL 은 건드리지 않는다
    assert not ensure_maturity_lower_bound("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20270101 AND 20271231 LIMIT 1")[1]
    assert not ensure_maturity_lower_bound("SELECT 1 FROM domestic_bonds WHERE mat_dt <= 20260821 LIMIT 1")[1]
    assert not ensure_maturity_lower_bound("SELECT 1 FROM domestic_bonds WHERE mat_dt > 20260822 AND mat_dt <= 20290824 LIMIT 1")[1]


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
    # 🔄 2026-09-03 #51 — '3년 안에' 는 상대 시점 확정표의 창이다. 종전엔 하한만 주입하고 상한은 플래너의 as-of 오기(2029-08-22)를
    #    그대로 두었지만, 이제 창 가드가 판정일+3년(20290824)으로 통째로 확정한다(규칙 만기윈도우 "3년이면 20290824").
    assert "[Guard] 상대 시점 창 확정" in r.think_trace and "'3년 안에'" in r.think_trace
    assert "mat_dt BETWEEN 20260824 AND 20290824" in r.sql and "20290822" not in r.sql
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
    # 🔄 2026-08-31 밤 — 옛 불개입 폐기: 불완전 IN 목록('AA 이상' 인데 AA0·AA- 누락)도 서열로 교정한다
    f_in, c_in = expand_grade_comparison(
        "SELECT 1 FROM domestic_bonds WHERE TRIM(crd_grd) IN ('AAA','AA+') LIMIT 1", "AA등급 이상")
    assert c_in and "TRIM(crd_grd) IN ('AAA', 'AA+', 'AA0', 'AA-')" in f_in
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
        "AND applied_yield > 0 AND mat_dt >= 20260824 AND pd_risk_gcd <> '11' AND COALESCE(TRIM(crd_grd),'') <> 'C0' AND bd_ofr_tcd <> '사모'")
    assert not ensure_credit_backstop(full, q)[1]
    # 2026-09-02 — 랭킹 제외에 만기 경과(mat_dt >= 기준일)가 추가됐다: 하한 없는 완성식은 그 절만 주입된다
    without_mat = full.replace("AND mat_dt >= 20260824 ", "")
    fixed3, changed3 = ensure_credit_backstop(without_mat, q)
    assert changed3 and fixed3.count("mat_dt >= 20260824") == 1 and "사모" in fixed3


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


def test_ensure_reco_exclusions():
    from src.runtime.pipeline import ensure_reco_exclusions
    sql = ("SELECT pd_nm, srfc_irt, applied_yield FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='회사채' "
           "AND TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-') ORDER BY srfc_irt DESC LIMIT 5")
    q = "AA등급 이상 회사채 중에서 표면금리 높은 순으로 5개 추천해줘"
    # 2026-08-31 저녁 실측 — 추천인데 사모 3건이 1~3위 혼입 → 제외 절 주입
    fixed, changed = ensure_reco_exclusions(sql, q)
    assert changed
    assert "bd_ofr_tcd <> '사모'" in fixed and "pd_risk_gcd <> '11'" in fixed and "applied_yield > 0" in fixed
    assert fixed.index("<> '사모'") < fixed.index("ORDER BY")
    # 범주 명시 우회 — '사모' 를 콕 집은 질문엔 사모 제외를 넣지 않는다
    f2, _ = ensure_reco_exclusions(sql, "AA등급 이상 사모 회사채 표면금리 높은 순 5개")
    assert "bd_ofr_tcd" not in f2
    # 발동 조건 밖 — 랭킹 신호 없음(개수·조회) / 채권 테이블 아님
    assert not ensure_reco_exclusions(sql, "표면금리 5% 넘는 회사채 30개 보여줘")[1]
    assert not ensure_reco_exclusions("SELECT pd_abrv_nm FROM domestic_etfs LIMIT 5", q)[1]
    # '골라줘' 도 추천 신호 (2026-09-01 실측: '골라줘' 질의가 제외 없이 나감)
    assert ensure_reco_exclusions(sql, "안전한 회사채 몇 개만 골라줘")[1]


def test_ensure_reco_sort():
    from src.runtime.pipeline import ensure_reco_sort
    # 2026-09-01 서버 실측 — '망하지 않을 회사가 발행한 채권만 골라줘' 가 정렬 없는 임의 5행
    sql = ("SELECT DISTINCT pd_no, TRIM(pd_nm), applied_yield, pd_risk_nm FROM domestic_bonds "
           "WHERE pd_risk_gcd = '16' LIMIT 5")
    q = "망하지 않을 회사가 발행한 채권만 골라줘"
    fixed, changed = ensure_reco_sort(sql, q)
    assert changed and "ORDER BY applied_yield DESC" in fixed
    assert fixed.index("ORDER BY") < fixed.index("LIMIT")
    # 불개입 — 이미 정렬 있음 / 다른 축 요구(만기) / 집계 / applied_yield 미선택(DISTINCT 제약) /
    # 추천 신호 없음 / 채권 테이블 아님
    assert not ensure_reco_sort(fixed, q)[1]
    assert not ensure_reco_sort(sql, "만기 짧은 걸로 골라줘")[1]
    assert not ensure_reco_sort("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE pd_risk_gcd='16'", q)[1]
    assert not ensure_reco_sort("SELECT DISTINCT pd_no, TRIM(pd_nm) FROM domestic_bonds LIMIT 5", q)[1]
    assert not ensure_reco_sort(sql, "위험등급 6등급 채권 5개 보여줘")[1]
    assert not ensure_reco_sort("SELECT pd_abrv_nm, applied_yield FROM domestic_etfs LIMIT 5", q)[1]


def test_server_probe_fixes_20260831_night(ctx):
    """2026-08-31 밤 서버 실측 5건 후속 — 날조 발행사·16 폴백·IN 서열·잔존일수 단위·0행 진단 노출."""
    from src.runtime.pipeline import ensure_ktb_kind, ensure_top_safety, expand_grade_comparison, _cell
    # ① 국고채 질의의 날조 발행사 제거 + STRIPS 회수 (실측: TRIM(pd_pbcm)='한국은행' 필터로 0행 '미수록' — 발행사는 전부 '대한민국')
    sql = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(pd_pbcm) = '한국은행' AND TRIM(bd_knd) = '국고채권' LIMIT 30"
    fixed, changed = ensure_ktb_kind(sql, "국고채는 총 몇종목이야?")
    assert changed and "한국은행" not in fixed and "std_pd_scls_nm)='국고채'" in fixed
    assert "한국은행" in ensure_ktb_kind(sql, "한국은행이 보유한 국고채 몇 종목이야?")[0]   # 질문이 명시하면 의도 존중
    # ② '가장 안전한 회사채' — 6등급 없는 종류 + '16' 단독은 IN ('15','16') 폴백으로 완화 (실측: 0행 '확인 불가' 오답)
    s16 = "SELECT pd_no FROM domestic_bonds WHERE pd_risk_gcd = '16' AND TRIM(std_pd_mcls_nm)='회사채' ORDER BY applied_yield DESC LIMIT 3"
    f3, c3 = ensure_top_safety(s16, "가장 안전한 회사채 3개 추천해줘")
    assert c3 and "IN ('15','16')" in f3
    # ③ 'A등급 이상' 불완전 IN 목록 교정 (실측: IN ('AA-','AA0',…) 으로 나가 상위 표면금리 209종목 누락)
    sin = ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(crd_grd) IN ('AA-', 'AA0') "
           "AND TRIM(std_pd_mcls_nm)='회사채' ORDER BY srfc_irt DESC LIMIT 5")
    f4, c4 = expand_grade_comparison(sin, "a등급 이상 회사채 중에서 표면금리 높은 순으로 5개 추천해줘")
    assert c4 and "'AAA'" in f4 and "'A-'" in f4 and "('AA-', 'AA0')" not in f4
    assert not expand_grade_comparison(
        "SELECT 1 FROM domestic_bonds WHERE TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-','A+','A0','A-') LIMIT 1",
        "A등급 이상 채권 알려줘")[1]                 # 이미 맞는 목록은 불개입
    # ④ 잔존일수 단위를 렌더 층에서 박는다 (실측: 9,375일이 '약 93.75년' 으로 환산 환각)
    assert _cell(9375.0, "remaining_days") == "9375일(약 25.7년)"
    # ⑤ 0행 진단('조건별 단독 조회')은 trace 에만 — 사용자 답변에서 제거
    class ZeroPlanner:
        def plan_sql(self, question, grounding):
            return "SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd)='보험회사채' AND pd_risk_gcd='16' LIMIT 5"
        def compose_answer(self, question, rows, answer_rules=""):
            return "호출되면 안 됨"
    r = answer_question("T-31", "위험등급 6등급 보험회사채 알려줘", planner=ZeroPlanner(), ctx=ctx)
    assert "확인되지 않습니다" in r.answer and "조건별 단독 조회" not in r.answer
    assert "조건별 단독 조회" in r.think_trace


def test_ensure_maturity_sort():
    from src.runtime.pipeline import ensure_maturity_sort
    # 2026-08-31 서버 실측 — '한전 만기 최장' 이 ORDER BY dur DESC 로 2049년 채권 오답 (실제 최장 2052년)
    sql = "SELECT pd_nm, mat_dt, dur FROM domestic_bonds WHERE TRIM(pd_pbcm)= '한국전력공사(주)' ORDER BY dur DESC LIMIT 1"
    q = "한전 채권 중 만기가 가장 긴 건 뭐야?"
    fixed, changed = ensure_maturity_sort(sql, q)
    assert changed and "ORDER BY mat_dt DESC" in fixed and "mat_dt >= 20260824" in fixed
    # 만기 짧은 순(ASC)에도 하한 주입 — 만기일 0값 4행·만기 경과 49행이 1위로 오는 것 차단.
    # 하한은 >= — 당일 만기(잔존 1일) 7종목이 진짜 최단이다 (2026-09-01 서버 실측: > 로 누락)
    f2, c2 = ensure_maturity_sort("SELECT pd_nm FROM domestic_bonds ORDER BY dur ASC LIMIT 5", "만기 짧은 채권 5개 알려줘")
    assert c2 and "ORDER BY mat_dt ASC" in f2 and "mat_dt >= 20260824" in f2
    # 불개입 — 듀레이션을 직접 물음 / 이미 mat_dt 정렬 / 채권 테이블 아님
    assert not ensure_maturity_sort(sql, "한전 채권 중 듀레이션 가장 긴 것")[1]
    assert not ensure_maturity_sort("SELECT pd_nm FROM domestic_bonds ORDER BY mat_dt DESC LIMIT 1", q)[1]
    assert not ensure_maturity_sort("SELECT pd_abrv_nm FROM domestic_etfs ORDER BY dur DESC LIMIT 1", q)[1]


def test_ensure_cutoff_inclusive():
    from src.runtime.pipeline import ensure_cutoff_inclusive
    # 2026-09-01 서버 실측 — '만기가 가장 짧은 채권 뭐야' 가 mat_dt > 20260822 로 당일 만기 7종목 누락
    fixed, changed = ensure_cutoff_inclusive(
        "SELECT pd_nm, mat_dt FROM domestic_bonds WHERE mat_dt > 20260822 ORDER BY mat_dt ASC LIMIT 1")
    assert changed and "mat_dt >= 20260824" in fixed and "mat_dt > 20260822" not in fixed
    # REAL 적재 리터럴(20260822.0)도 교정
    assert ensure_cutoff_inclusive("SELECT 1 FROM domestic_bonds WHERE mat_dt > 20260822.0")[1]
    # 불개입 — 이미 >= / 기준일이 아닌 날짜의 부등호(사용자 조건) / 상한
    assert not ensure_cutoff_inclusive("SELECT 1 FROM domestic_bonds WHERE mat_dt >= 20260824")[1]   # 판정일 리터럴은 불개입
    assert ensure_cutoff_inclusive("SELECT 1 FROM domestic_bonds WHERE mat_dt >= 20260822")[1]       # as-of 리터럴은 8/24 로 교정 (2026-09-02)
    assert not ensure_cutoff_inclusive("SELECT 1 FROM domestic_bonds WHERE mat_dt > 20270101")[1]
    assert not ensure_cutoff_inclusive("SELECT 1 FROM domestic_bonds WHERE mat_dt <= 20260822")[1]


def test_price_ambiguity_clarify(ctx):
    from src.runtime.pipeline import price_ambiguity_clarify
    # 2026-08-31 서버 실측 — '제일 싼 채권' 에 되묻지 않고 가격 해석 단정 (싸다 = 🔴 기본값 금지 다의어)
    assert price_ambiguity_clarify("제일 싼 채권 알려줘", ["domestic_bonds"])
    assert price_ambiguity_clarify("저렴한 채권 추천해줘", ["domestic_bonds"])
    assert price_ambiguity_clarify("가장 비싼 채권은 뭐야?", ["domestic_bonds"])
    # 단서 낱말이 있으면 되묻지 않는다 · 채권 밖 상품군 불개입
    assert price_ambiguity_clarify("가격이 제일 싼 채권", ["domestic_bonds"]) is None
    assert price_ambiguity_clarify("수익률 기준으로 제일 싼 채권", ["domestic_bonds"]) is None
    assert price_ambiguity_clarify("보수가 제일 싼 ETF", ["domestic_etfs"]) is None
    # 풀패스 — HCX 미연결이어도 결정층이 되묻는다 (역질문은 유효 답변)
    r = answer_question("T-30", "제일 싼 채권 알려줘", ctx=ctx)
    assert "[Clarify] 되묻기(결정층)" in r.think_trace and "어느 쪽" in r.answer


def test_check_values_currency(ctx):
    from src.runtime import guard
    # 2026-08-31 서버 실측 — curr_cd='XS'(ISIN 접두사 환각)가 값 검사를 통과. vocab 등재 후 차단 확인
    v = guard.check_values("SELECT pd_no FROM domestic_bonds WHERE curr_cd = 'XS' LIMIT 30", ctx)
    assert v and "curr_cd" in str(v[0]) and "XS" in str(v[0])
    assert not guard.check_values("SELECT pd_no FROM domestic_bonds WHERE curr_cd = 'KRW' LIMIT 30", ctx)


def test_ensure_top_safety():
    from src.runtime.pipeline import ensure_top_safety
    # 2026-08-31 실측 — '가장 안전한 채권 3개' 가 IN ('15','16') + 수익률 내림차순으로 나가
    # 5등급 콜옵션부 7.1% 가 1~3위 (위험등급방향의 '16 단독' 분기 미적용)
    sql = ("SELECT DISTINCT pd_no, TRIM(pd_nm), applied_yield, pd_risk_gcd, pd_risk_nm FROM domestic_bonds "
           "WHERE pd_risk_gcd IN ('15', '16') AND curr_cd = 'KRW' AND mat_dt >= 20260824 "
           "AND applied_yield IS NOT NULL AND applied_yield > 0 AND pd_risk_gcd <> '11' "
           "AND COALESCE(TRIM(crd_grd),'') <> 'C0' AND bd_ofr_tcd <> '사모' ORDER BY applied_yield DESC LIMIT 3")
    q = "가장 안전한 채권 3개 추천해줘"
    fixed, changed = ensure_top_safety(sql, q)
    assert changed and "pd_risk_gcd = '16'" in fixed and "'15'" not in fixed
    assert "pd_risk_gcd <> '11'" in fixed                     # 음의 필터(고위험제외)는 건드리지 않는다
    assert "ORDER BY applied_yield DESC" in fixed             # 전 행 동급 — 수익률 정렬은 동점자 처리
    # 위험등급 필터가 아예 없으면 주입 (WHERE 끝, ORDER BY 앞)
    f2, c2 = ensure_top_safety("SELECT pd_nm FROM domestic_bonds WHERE curr_cd='KRW' ORDER BY applied_yield DESC LIMIT 3", q)
    assert c2 and f2.index("pd_risk_gcd = '16'") < f2.index("ORDER BY")
    # = '15' 단독도 교정 · 6등급이 실존하는 종류(국고채·은행채 — 특수은행채 16등급 1,241행 실측)는 발동
    assert "pd_risk_gcd = '16'" in ensure_top_safety("SELECT pd_nm FROM domestic_bonds WHERE pd_risk_gcd = '15' LIMIT 3", q)[0]
    assert ensure_top_safety(sql, "가장 안전한 국고채 3개 추천해줘")[1]
    assert ensure_top_safety(sql, "가장 안전한 은행채 3개 추천해줘")[1]
    # 어구 변종(2026-09-01 전수조사에서 누락 발견분) — 어순 역전·조사 2글자·외래어·덜 위험·안전성 높음
    for variant in ("가장 위험이 낮은 채권 골라줘", "위험도가 가장 낮은 채권", "리스크가 가장 낮은 채권 추천",
                    "가장 덜 위험한 채권", "안전성이 가장 높은 채권 3개"):
        assert ensure_top_safety(sql, variant)[1], variant
    # 부도-공포 서술형(2026-09-01 실측 사각 보강) — S-009 '원금 잃기 싫은데' 계열
    for variant in ("망하지 않을 회사 채권 골라줘", "돈 떼일 걱정 없는 채권 뭐 있어?",
                    "원금 잃기 싫은데 채권 뭐 사면 돼?", "부도 걱정 없는 채권"):
        assert ensure_top_safety(sql, variant)[1], variant
    # '망하지 않을 회사가 발행한' — 회사채(6등급 0행)를 지목하므로 완화 branch: 16 단독 → IN ('15','16')
    f_corp, c_corp = ensure_top_safety(
        "SELECT pd_nm FROM domestic_bonds WHERE pd_risk_gcd = '16' AND TRIM(std_pd_mcls_nm)='회사채' LIMIT 5",
        "망하지 않을 회사가 발행한 채권만 골라줘")
    assert c_corp and "IN ('15','16')" in f_corp
    # '원금을 잃을 수도 있어?' 사실확인은 트리거 밖 — 잃기 싫/잃으면 안 꼴만
    assert not ensure_top_safety(sql, "채권도 원금을 잃을 수 있어?")[1]
    # 구조표시 CASE 동반 — 치환은 WHERE 범위만: SELECT 의 pd_risk_gcd IN ('11','12','13') 은 보존 (전수조사 실측 파손)
    case_sql = ("SELECT pd_nm, CASE WHEN TRIM(bd_knd) IN ('특수은행채','일반은행채','금융지주회사채') "
                "AND pd_risk_gcd IN ('11','12','13') THEN '은행 자본성증권' ELSE '' END AS 구조, pd_risk_nm "
                "FROM domestic_bonds WHERE pd_risk_gcd IN ('15','16') ORDER BY applied_yield DESC LIMIT 3")
    f3, c3 = ensure_top_safety(case_sql, q)
    assert c3 and "IN ('11','12','13')" in f3 and "pd_risk_gcd = '16'" in f3 and "IN ('15','16')" not in f3
    # 불개입 — 이미 16 단독 / 최상급 아님(IN 15,16 이 정답) / 안정추구형(15,16) / 수익률 하한 요구(폴백 영역) /
    # 6등급 없는 종류(회사채 — 강제하면 0행) / 반대 방향 최상급 동반(비교 질의) / 채권 테이블 아님
    assert not ensure_top_safety("SELECT pd_nm FROM domestic_bonds WHERE pd_risk_gcd = '16' LIMIT 3", q)[1]
    assert not ensure_top_safety(sql, "위험 낮은 채권 3개 추천해줘")[1]
    assert not ensure_top_safety(sql, "안정추구형 투자자용 채권 3개")[1]
    assert not ensure_top_safety(sql, "가장 안전한 채권 중 수익률 6.5% 이상 3개")[1]
    assert not ensure_top_safety(sql, "가장 안전한 회사채 3개 추천해줘")[1]
    assert not ensure_top_safety(sql, "가장 안전한 채권과 가장 위험한 채권 하나씩 알려줘")[1]
    assert not ensure_top_safety("SELECT pd_abrv_nm FROM domestic_etfs LIMIT 3", q)[1]


def test_strip_fabricated_risk_filter():
    from src.runtime.pipeline import strip_fabricated_risk_filter
    # 2026-09-01 서버 실측 — '수익률이 제일 높은 채권' 에 pd_risk_gcd = '16' 이 날조되어
    # 6등급 최고 6.231% 오답 (실제 최고 신보 유동화 728.524% C0·1등급. _TOP_SAFE_Q 미매치 확인)
    sql = ("SELECT DISTINCT pd_no, TRIM(pd_nm) as 상품명, applied_yield FROM domestic_bonds "
           "WHERE pd_risk_gcd = '16' AND applied_yield IS NOT NULL AND applied_yield > 0 "
           "ORDER BY applied_yield DESC LIMIT 5")
    q = "수익률이 제일 높은 채권이 뭐야?"
    fixed, changed = strip_fabricated_risk_filter(sql, q)
    assert changed and "pd_risk_gcd" not in fixed and "applied_yield > 0" in fixed
    assert "ORDER BY applied_yield DESC" in fixed
    # 절이 중간·끝에 있어도 앞뒤 AND 와 함께 떨어진다 · IN 꼴도 · '가장 낮은' 방향도
    f2, c2 = strip_fabricated_risk_filter(
        "SELECT pd_nm FROM domestic_bonds WHERE curr_cd='KRW' AND pd_risk_gcd IN ('15','16') "
        "ORDER BY applied_yield DESC LIMIT 5", "수익률이 가장 낮은 채권은?")
    assert c2 and "pd_risk_gcd" not in f2 and "curr_cd='KRW'" in f2 and " AND  AND " not in f2
    # WHERE 가 그 절뿐이면 WHERE 통째 제거
    f3, c3 = strip_fabricated_risk_filter(
        "SELECT pd_nm FROM domestic_bonds WHERE pd_risk_gcd = '16' ORDER BY applied_yield DESC LIMIT 5", q)
    assert c3 and "WHERE" not in f3 and "ORDER BY applied_yield DESC" in f3
    # 불개입 — 위험·안전·등급 어휘가 필터를 정당화 / 고위험제외(<>)는 음의 필터라 보존 /
    # WHERE 에 OR(그룹 논리) / 위험 필터 없음 / 수익률 최상급 아님 / 채권 테이블 아님
    assert not strip_fabricated_risk_filter(sql, "가장 안전하면서 수익률이 제일 높은 채권")[1]
    assert not strip_fabricated_risk_filter(sql, "위험등급 1등급 중 수익률이 제일 높은 채권")[1]
    assert not strip_fabricated_risk_filter(sql, "1등급 채권 중 수익률이 가장 높은 건?")[1]
    assert not strip_fabricated_risk_filter(
        "SELECT pd_nm FROM domestic_bonds WHERE pd_risk_gcd <> '11' ORDER BY applied_yield DESC LIMIT 5", q)[1]
    assert not strip_fabricated_risk_filter(
        "SELECT pd_nm FROM domestic_bonds WHERE (pd_risk_gcd = '16' OR crd_grd='AAA') LIMIT 5", q)[1]
    assert not strip_fabricated_risk_filter(
        "SELECT pd_nm FROM domestic_bonds WHERE curr_cd='KRW' LIMIT 5", q)[1]
    assert not strip_fabricated_risk_filter("SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_risk_cd='PD_RISK_GCD_16' LIMIT 5", q)[1]
    # 2026-09-02 확장 — 추천·구매의향 문형도 받는다 ('1년만 굴릴 건데 어떤 채권 사면 돼?' 가
    # 최상급·_RECO_Q 어느 쪽에도 안 걸려 날조 '16' 통과 → 6등급 2·4·5·6·7위 답변 실측)
    win = ("SELECT DISTINCT pd_no, pd_nm, applied_yield, remaining_days FROM domestic_bonds "
           "WHERE mat_dt >= 20260824 AND mat_dt <= 20270824 AND pd_risk_gcd = '16' "
           "ORDER BY applied_yield DESC LIMIT 30")
    f4, c4 = strip_fabricated_risk_filter(win, "1년만 굴릴 건데 어떤 채권 사면 돼?")
    assert c4 and "pd_risk_gcd" not in f4 and "mat_dt >= 20260824" in f4
    assert strip_fabricated_risk_filter(sql, "수익률 높은 순으로 5개 추천해줘")[1]  # 옛 불개입 케이스 → 확장 후 양성
    # 부도-공포 서술형(_TOP_SAFE_Q)은 _RISK_VOCAB 밖이지만 '16' 이 정답 — 불개입 (오폭 봉인)
    assert not strip_fabricated_risk_filter(win, "망하지 않을 회사 채권만 골라줘")[1]
    assert not strip_fabricated_risk_filter(win, "돈 떼일 걱정 없는 채권 중 수익률 최고는?")[1]


def test_distribution_answer_distinct_bonds():
    from src.runtime.pipeline import _distribution_answer as d
    # 2026-09-02 서버 실측 — '신용등급별 몇 종목' 전사 실패(AA+ 2,516 누락 · BB0→'B0' 라벨 뒤틀림 ·
    # 무등급을 '기타' 창작 · 14/16줄). 조립기가 COUNT(DISTINCT pd_no) 를 안 받아 미발동이 원인
    sql = ("SELECT TRIM(crd_grd) AS 신용등급, COUNT(DISTINCT pd_no) AS 종목수 FROM domestic_bonds "
           "GROUP BY 1 ORDER BY 1 LIMIT 30")
    rows = "신용등급 | 종목수\n | 2954\nAA+ | 2516\nAAA | 8646"
    out = d(sql, rows, 3)
    assert out and "AA+" in out and "2,516종목" in out and "(미수록): 2,954종목" in out
    assert "전체" in out and "중복" in out          # 범주 합 ≠ 전체 DISTINCT 주석 (실제 DB 재계산)
    # 불개입 — 3열(2열째가 COUNT 아님 · 위험등급 코드+이름 꼴) / 펀드 테이블 COUNT(DISTINCT pd_no) 없음
    assert d("SELECT pd_risk_gcd, pd_risk_nm, COUNT(DISTINCT pd_no) FROM domestic_bonds GROUP BY 1,2 LIMIT 30",
             "a | b | c\n11 | x | 1\n12 | y | 2", 2) is None
    assert d("SELECT zrin_btyp_nm, COUNT(DISTINCT pd_no) FROM public_funds GROUP BY 1 LIMIT 30",
             "a | b\nx | 1\ny | 2", 2) is None


def test_ensure_positive_count_answered():
    from src.runtime.pipeline import ensure_positive_count_answered as f
    # 2026-09-02 서버 실측 — 퇴직연금 COUNT(*)=1,929 정상 반환에도 "정보가 포함되어 있지 않습니다" 오거절
    sql = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE pd_pen_tr_yn = 'Y' AND curr_cd = 'KRW' AND mat_dt >= 20260824"
    rows = "COUNT(DISTINCT pd_no)\n843"
    refusal = "조회 결과에 퇴직연금에서 구매 가능한 특정 채권에 대한 정보가 포함되어 있지 않습니다. 따라서 이에 대해 답변을 드릴 수 없습니다."
    fixed, changed = f(refusal, sql, rows, 1, "퇴직연금으로 살 수 있는 채권 있어?")
    assert changed and "843" in fixed and "종목" in fixed and fixed.startswith("네, 있습니다")
    # 존재 문형 아니면 접두 없음 · COUNT(*) 는 행 기준 단서
    f2, c2 = f(refusal, "SELECT COUNT(*) FROM domestic_bonds WHERE pd_pen_tr_yn='Y'", "COUNT(*)\n1929", 1, "퇴직연금 채권 몇 개야")
    assert c2 and "1,929" in f2 and "행 기준" in f2
    # 2026-09-02 확장 — 거절이 아닌 '없습니다' 부정 단정 (COUNT 19 반환에도 '0등급 채권은 없습니다')
    sql00 = "SELECT COUNT(*) FROM domestic_bonds WHERE pd_risk_gcd = '00'"
    f3, c3 = f("조회 결과에 따르면, 위험등급 0등급인 채권은 없습니다. 6등급을 추천드립니다.",
               sql00, "COUNT(*)\n19", 1, "위험등급 0등급인 채권 있어?")
    assert c3 and "19" in f3 and f3.startswith("네, 있습니다")
    # 숫자를 인용한 답변은 '없' 이 있어도 불개입 ('0등급은 없고 해당없음 19종목')
    assert not f("정식 0등급은 없습니다만 등급 미부여(해당없음) 19종목이 있습니다.", sql00, "COUNT(*)\n19", 1, "있어?")[1]
    # 불개입 — 정상 답변 / 값 0 / 다행 결과 / 집계 아닌 SELECT / 2항목 SELECT
    assert not f("네, 843종목 있습니다.", sql, rows, 1, "있어?")[1]
    assert not f(refusal, sql, "COUNT(DISTINCT pd_no)\n0", 1, "있어?")[1]
    assert not f(refusal, sql, "a\n1\n2", 2, "있어?")[1]
    assert not f(refusal, "SELECT pd_no FROM domestic_bonds LIMIT 1", "pd_no\nKR123", 1, "있어?")[1]
    assert not f(refusal, "SELECT COUNT(*), pd_nm FROM domestic_bonds", "c | n\n3 | x", 1, "있어?")[1]


def test_ensure_distinct_count_existence():
    from src.runtime.pipeline import ensure_distinct_count
    # 2026-09-02 — '있어?' 존재 문형에도 COUNT(*)→DISTINCT 교정 (옛 트리거는 종목·몇 개·개수만)
    sql = "SELECT COUNT(*) FROM domestic_bonds WHERE pd_pen_tr_yn = 'Y' AND curr_cd = 'KRW' AND mat_dt >= 20260824 LIMIT 30"
    fixed, changed = ensure_distinct_count(sql, "퇴직연금으로 살 수 있는 채권 있어?")
    assert changed and "COUNT(DISTINCT pd_no)" in fixed
    # COUNT 없는 목록 SELECT 는 불개입(존재 질문의 예시 목록은 살린다)
    assert not ensure_distinct_count("SELECT pd_no, pd_nm FROM domestic_bonds LIMIT 30", "채권 있어?")[1]


def test_ensure_grade_select_column():
    from src.runtime.pipeline import ensure_grade_select_column
    # 2026-09-02 서버 실측 — '등급 높은 채권으로 골라줘' 가 crd_grd IN 필터(15,845종목)를 제대로
    # 걸고도 SELECT 가 pd_no·pd_nm 뿐이라 답변기가 "등급 정보가 포함되어 있지 않다" 오거절
    sql = ("SELECT DISTINCT pd_no, TRIM(pd_nm) FROM domestic_bonds "
           "WHERE crd_grd IN ('AAA', 'AA+', 'AA0', 'AA-') AND applied_yield > 0 LIMIT 30")
    fixed, changed = ensure_grade_select_column(sql)
    assert changed and "TRIM(crd_grd) AS crd_grd" in fixed
    assert fixed.index("crd_grd") < fixed.upper().index("FROM")
    # 불개입 — 이미 SELECT 에 있음 / 집계 / GROUP BY / crd_grd 미사용(crd_grd_dt 는 별개) / 타 테이블
    assert not ensure_grade_select_column(fixed)[1]
    assert not ensure_grade_select_column(
        "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE crd_grd='AAA'")[1]
    assert not ensure_grade_select_column(
        "SELECT TRIM(crd_grd), pd_no FROM domestic_bonds WHERE TRIM(crd_grd)='AAA' LIMIT 5")[1]
    assert not ensure_grade_select_column(
        "SELECT pd_no FROM domestic_bonds WHERE crd_grd_dt >= 20260101 LIMIT 5")[1]
    assert not ensure_grade_select_column(
        "SELECT pd_no, COUNT(*) FROM domestic_bonds WHERE crd_grd='AAA' GROUP BY pd_no")[1]


def test_ensure_top_row_cited():
    from src.runtime.pipeline import ensure_top_row_cited
    # 2026-09-02 서버 실측 — '1년만 굴릴 건데' 답변이 정렬 결과의 2·4·5·6·7위만 나열,
    # 1위(KR354404GC55 3.986%)·3위(KR356501GG82 3.94%) 증발. 값이 전부 실제 행이라 환각 검사 밖
    sql = ("SELECT pd_no, pd_nm, applied_yield FROM domestic_bonds "
           "WHERE pd_risk_gcd='16' ORDER BY applied_yield DESC LIMIT 30")
    rows = "\n".join([
        "pd_no | pd_nm | applied_yield",
        "KR354404GC55 | MBS2022-9 | 3.986",
        "KR356601GF82 | 용인도시공사2025-2 | 3.957",
        "KR356501GG82 | 평택도시공사 2026-2(사) | 3.94",
        "KR354405GC62 | MBS2022-11 | 3.914",
        "KR354427GC41 | MBS2022-8 | 3.866",
    ])
    ans = "추천드립니다.\n* KR356601GF82: 용인 3.957%\n* KR354405GC62: MBS11 3.914%\n* KR354427GC41: MBS8 3.866%"
    fixed, changed = ensure_top_row_cited(ans, sql, rows)
    assert changed and "KR354404GC55" in fixed and "KR356501GG82" in fixed
    assert "1위" in fixed and "3위" in fixed and fixed.startswith(ans)
    # 불개입 — 상위부터 순서대로 인용(누락 없음) / 인용 pd_no 2개 미만(이름만 답변) /
    # 집계·GROUP BY / ORDER BY 없음
    assert not ensure_top_row_cited(
        "* KR354404GC55 3.986%\n* KR356601GF82 3.957%", sql, rows)[1]
    assert not ensure_top_row_cited("용인도시공사2025-2 를 추천합니다 (KR356601GF82)", sql, rows)[1]
    assert not ensure_top_row_cited(ans, "SELECT pd_risk_gcd, COUNT(*) FROM domestic_bonds GROUP BY 1", rows)[1]
    assert not ensure_top_row_cited(ans, "SELECT pd_no FROM domestic_bonds LIMIT 30", rows)[1]


def test_ensure_ktb_kind_and_distinct_count():
    from src.runtime.pipeline import ensure_ktb_kind, ensure_distinct_count
    # 2026-08-31 저녁 실측 — '국고채 몇 종목' 이 대분류 국공채 COUNT(*) = 2,840 행수로 나감
    sql = "SELECT COUNT(*) FROM domestic_bonds WHERE std_pd_mcls_nm='국공채'"
    q = "국고채는 총 몇 종목이야?"
    fixed, changed = ensure_ktb_kind(sql, q)
    assert changed and "TRIM(bd_knd)='국고채권'" in fixed and "std_pd_scls_nm)='국고채'" in fixed
    fixed2, c2 = ensure_distinct_count(fixed, q)
    assert c2 and "COUNT(DISTINCT pd_no)" in fixed2
    # bd_knd='국고채권' 단독은 STRIPS 21종목이 빠진 274종목 — 확정식으로 확장한다 (2026-08-31 밤 개선: 옛 불개입 폐기)
    f3, c3 = ensure_ktb_kind("SELECT 1 FROM domestic_bonds WHERE TRIM(bd_knd)='국고채권' LIMIT 1", q)
    assert c3 and "std_pd_scls_nm)='국고채'" in f3
    # 불개입 — 합성어(미국채) / 이미 확정식(STRIPS 분기 포함) / 대분류 앵커 없음 / 종목·개수 어휘 없음
    assert not ensure_ktb_kind(sql, "미국채 금리 알려줘")[1]
    assert not ensure_ktb_kind(f3, q)[1]
    assert not ensure_ktb_kind("SELECT COUNT(*) FROM domestic_bonds", q)[1]
    assert not ensure_distinct_count("SELECT COUNT(*) FROM domestic_bonds", "채권 데이터가 총 몇 행이야?")[1]


def test_ensure_ktb_kind_strips_escape():
    """STRIPS 탈출구 (2026-08-31 밤 리드 결정) — 질문이 스트립을 콕 집으면 가드가 넘겨짚지 않는다."""
    from src.runtime.pipeline import ensure_ktb_kind
    plain = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(bd_knd)='국고채권' LIMIT 30"
    # ③ 스킵 — 'STRIPS 제외' 정밀 질의에서 bd_knd 단독식을 확장하지 않는다 (한글·영문 표기 모두)
    for q in ("스트립 채권 제외하고 국고채만 몇 종목이야?", "STRIPS 빼고 국고채 개수 알려줘",
              "원금이자분리채권 제외 국고채는?"):
        assert not ensure_ktb_kind(plain, q)[1], q
    # ② 는 여전히 교정하되 bd_knd 단독식으로만 — 대분류 뭉개기(2,840)는 STRIPS 질의에서도 오답이다
    mcls = "SELECT COUNT(*) FROM domestic_bonds WHERE std_pd_mcls_nm='국공채'"
    fixed, changed = ensure_ktb_kind(mcls, "스트립 제외한 국고채 몇 종목이야?")
    assert changed and "TRIM(bd_knd)='국고채권'" in fixed and "std_pd_scls_nm" not in fixed
    # 낱말이 없으면 종전대로 확정식(STRIPS 포함) 확장 — 회귀 방지
    assert "std_pd_scls_nm)='국고채'" in ensure_ktb_kind(plain, "국고채 몇 종목이야?")[0]


def test_validate_sql_relaxations():
    from src.runtime.pipeline import validate_sql
    # 2026-08-31 저녁 — 읽기 전용인데 기각되던 형태 2종 허용
    assert validate_sql("SELECT REPLACE(pd_nm,' ','') FROM domestic_bonds LIMIT 5") is None
    assert validate_sql("WITH b AS (SELECT pd_nm FROM domestic_bonds) SELECT * FROM b LIMIT 5") is None
    # 위험 형태는 그대로 차단
    assert validate_sql("REPLACE INTO domestic_bonds VALUES (1)") is not None
    assert validate_sql("SELECT 1 FROM secret_table LIMIT 1") is not None


def test_normalize_table_names():
    from src.runtime.pipeline import normalize_table_names
    # 2026-08-31 저녁 실측 — 존재하지 않는 bonds_master 환각 (조건식은 정확)
    sql = "SELECT pd_nm, applied_yield FROM bonds_master WHERE bd_knd IN ('일반은행채', '특수은행채') ORDER BY applied_yield DESC LIMIT 5"
    fixed, changed = normalize_table_names(sql)
    assert changed and "FROM domestic_bonds" in fixed and "bonds_master" not in fixed
    # 불개입 — 정상 테이블 / 채권 컬럼 없는 미지 테이블(추정 금지) / CTE 별칭
    assert not normalize_table_names("SELECT pd_nm FROM domestic_bonds LIMIT 5")[1]
    assert not normalize_table_names("SELECT x FROM etf_master WHERE du_er_1y > 0 LIMIT 5")[1]
    assert not normalize_table_names("WITH b AS (SELECT bd_knd FROM domestic_bonds) SELECT * FROM b LIMIT 5")[1]


def test_ensure_trimmed_compare():
    from src.runtime.pipeline import ensure_trimmed_compare
    # 2026-08-31 저녁 실측 — 무TRIM IN 은 16행만 통과 (TRIM 2,031행)
    fixed, changed = ensure_trimmed_compare("SELECT 1 FROM domestic_bonds WHERE bd_knd IN ('일반은행채','특수은행채') LIMIT 5")
    assert changed and "TRIM(bd_knd) IN" in fixed
    fixed2, c2 = ensure_trimmed_compare("SELECT 1 FROM domestic_bonds WHERE pd_pbcm = '한국산업은행' LIMIT 5")
    assert c2 and "TRIM(pd_pbcm) =" in fixed2
    # 불개입 — 이미 TRIM / LIKE(와일드카드가 패딩 흡수) / 무패딩 컬럼
    assert not ensure_trimmed_compare("SELECT 1 FROM domestic_bonds WHERE TRIM(bd_knd)='국고채권' LIMIT 1")[1]
    assert not ensure_trimmed_compare("SELECT 1 FROM domestic_bonds WHERE pd_pbcm LIKE '%한국%' LIMIT 1")[1]
    assert not ensure_trimmed_compare("SELECT 1 FROM domestic_bonds WHERE crd_grd = 'AAA' LIMIT 1")[1]


def test_ensure_trimmed_group_keys():
    """2026-09-04 오답기록 #63 — 집계·정렬 키의 무TRIM 패딩.

    서버 실측 `GROUP BY pd_pbcm` 이 고정폭 패딩으로 같은 기관을 갈라 한국산업은행 503→500,
    한국토지주택공사 499→498 이 되고 2·3위 순서가 뒤바뀌었다(ETF FIN-06 과 같은 병)."""
    import sqlite3

    from src.runtime.loader import db_path
    from src.runtime.pipeline import ensure_trimmed_compare as f

    sql = ("SELECT pd_pbcm, COUNT(DISTINCT pd_no) FROM domestic_bonds "
           "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 GROUP BY pd_pbcm ORDER BY 2 DESC LIMIT 5")
    fixed, changed = f(sql)
    assert changed and "GROUP BY TRIM(pd_pbcm)" in fixed
    assert "SELECT TRIM(pd_pbcm)," in fixed          # 표시 이름과 묶음 키를 같은 값으로
    if db_path().exists():                            # 순위가 실제로 바뀌는지 — 동률 499 두 기관
        con = sqlite3.connect(db_path())
        assert [r[1] for r in con.execute(fixed)][:3] == [1555, 499, 499]
        assert [r[1] for r in con.execute(sql)][:3] == [1555, 498, 498]   # 무TRIM 이면 갈린다

    # 별칭은 건드리지 않는다 — `AS TRIM(x)` 는 문법 오류다 (6R 고정선 S12)
    aliased, ch2 = f("SELECT pd_pbcm AS 발행사, COUNT(*) AS pd_pbcm FROM domestic_bonds GROUP BY pd_pbcm LIMIT 5")
    assert ch2 and "TRIM(pd_pbcm) AS 발행사" in aliased and "AS pd_pbcm" in aliased and "AS TRIM(" not in aliased

    # 🔴 펀드단위 확정식은 불개입 — or_co_xtn_itt_cd 는 raw = trim 이라 이득이 0 인데
    #    확정식 문자열이 바뀌면 뒤따르는 슬롯·가드가 같은 식을 못 알아본다(6R 고정선 R4·R6)
    fund = ("SELECT MIN(itm_no) FROM public_funds WHERE sale_yn = '판매중' "
            "GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) LIMIT 30")
    assert f(fund) == (fund, False)

    # 정렬 키에 패딩 컬럼이 없으면 원문 그대로 (공백까지 보존 — 뒤 가드가 같은 문자열로 본다)
    plain = "SELECT pd_nm FROM domestic_bonds\n ORDER BY mat_dt DESC  LIMIT 3"
    assert f(plain) == (plain, False)


def test_bondpop_slot():
    """2026-09-04 오답기록 #64 · 리드 결정 — 채권 집계·랭킹의 기본모수는 구매가능(8/24)이다."""
    from src.runtime import guard
    from src.runtime.loader import load_context

    ctx = load_context()
    fire = lambda sql, q: guard.apply_enforce(sql, q, ["domestic_bonds"], set(), ctx)

    out, fired = fire("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds "
                      "WHERE TRIM(bd_inrt_tcd) IN ('변동금리', '고정+변동금리') LIMIT 30",
                      "금리가 고정이 아니라 변동인 채권은 몇 개야?")
    assert fired == ["BONDPOP"] and "curr_cd = 'KRW' AND mat_dt >= 20260824 AND (" in out

    # 🔴 OR 절은 괄호로 감싸야 한다 — 안 감싸면 (모수 AND a) OR b 로 새고 모수가 무력해진다
    out2, f2 = fire("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='국공채' "
                    "OR (COALESCE(TRIM(bd_knd),'')='' AND TRIM(std_pd_scls_nm)='국고채') LIMIT 30",
                    "국고채를 포함해서 국공채는 총 몇 종목이야?")
    assert f2 == ["BONDPOP"] and out2.count("(TRIM(std_pd_mcls_nm)='국공채' OR") == 1

    # 불개입 — 만기 하한이 이미 있거나 / 만기 지난 것을 명시적으로 묻거나 / 집계·랭킹이 아닐 때
    assert fire("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds "
                "WHERE curr_cd='KRW' AND mat_dt >= 20260824 LIMIT 30", "지금 매수할 수 있는 채권 몇 종목이야?")[1] == []
    assert fire("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE mat_dt < 20260824 LIMIT 30",
                "만기가 지난 채권은 몇 종목이야?")[1] == []
    assert fire("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd)='국고채권' LIMIT 5",
                "국고채 알려줘")[1] == []


def test_ensure_count_query():
    from src.runtime.pipeline import ensure_count_query, _cell
    # 2026-09-01 서버 실측 — '5% 넘는 건 몇 개야' 에 COUNT 없는 목록 + 잔존일수순 임의 3행
    sql = ("SELECT DISTINCT pd_no, TRIM(pd_nm) as 상품명, applied_yield, pd_risk_gcd, pd_risk_nm, "
           "std_pd_mcls_nm, remaining_days FROM domestic_bonds WHERE curr_cd = 'KRW' "
           "AND mat_dt >= 20260824 AND applied_yield > 5 ORDER BY remaining_days LIMIT 3")
    q = "지금 살 수 있는 채권 중에 수익률 5% 넘는 건 몇 개야?"
    fixed, changed = ensure_count_query(sql, q)
    assert changed and fixed.startswith("SELECT COUNT(DISTINCT pd_no)")
    assert "applied_yield > 5" in fixed and "ORDER BY" not in fixed and "LIMIT" not in fixed
    # 의문 어구 변종
    for v in ("은행채는 몇 종목이나 있어?", "국고채는 총 몇 종목이야?", "표면금리 0%인 채권 개수 좀"):
        assert ensure_count_query(sql, v)[1], v
    # 불개입 — 개수 지정 추천('몇 개만 골라줘') / 이미 COUNT / GROUP BY(범주별 집계) / 중첩 SELECT / 타 테이블
    assert not ensure_count_query(sql, "안전한 채권 몇 개만 골라줘")[1]
    assert not ensure_count_query(sql, "채권 3개 보여줘")[1]
    assert not ensure_count_query("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds", q)[1]
    assert not ensure_count_query("SELECT bd_knd, COUNT(DISTINCT pd_no) FROM domestic_bonds GROUP BY bd_knd", q)[1]
    assert not ensure_count_query("SELECT * FROM (SELECT pd_no FROM domestic_bonds) LIMIT 5", q)[1]
    assert not ensure_count_query("SELECT pd_abrv_nm FROM domestic_etfs LIMIT 5", q)[1]
    # 잔존일수 렌더 — 1년 미만은 '6일(약 0.0년)' 이 아니라 '6일' (2026-09-01 서버 답변 관측)
    assert _cell(6.0, "remaining_days") == "6일"
    assert _cell(9375.0, "remaining_days") == "9375일(약 25.7년)"


def test_ensure_kind_filter():
    from src.runtime.pipeline import ensure_kind_filter
    # 2026-08-31 저녁 실측 — 'AA등급 이상 회사채' 인데 종류 조건 통째 부재
    sql = ("SELECT pd_nm, srfc_irt FROM domestic_bonds WHERE TRIM(crd_grd) IN ('AAA', 'AA+', 'AA0', 'AA-') "
           "ORDER BY srfc_irt DESC LIMIT 5")
    fixed, changed = ensure_kind_filter(sql, "AA등급 이상 회사채 중에서 표면금리 높은 순으로 5개 추천해줘")
    assert changed and "TRIM(std_pd_mcls_nm)='회사채'" in fixed
    assert fixed.index("회사채'") < fixed.index("ORDER BY")
    # 은행채 → 2종 IN · 긴 낱말 소진('일반은행채' 가 '은행채' 로 이중 매칭되지 않음)
    f2, c2 = ensure_kind_filter(sql, "은행채 중 수익률 높은 것")
    assert c2 and "IN ('일반은행채','특수은행채')" in f2
    f3, c3 = ensure_kind_filter(sql, "일반은행채만 보여줘")
    assert c3 and "TRIM(bd_knd)='일반은행채'" in f3 and "특수은행채" not in f3
    # 불개입 — 복수 종류(비교) / SQL 에 이미 종류 컬럼 / 종류 낱말 없음 / 합성어 국채
    assert not ensure_kind_filter(sql, "국고채와 회사채 수익률 비교")[1]
    assert not ensure_kind_filter("SELECT 1 FROM domestic_bonds WHERE TRIM(bd_knd)='MBS' LIMIT 1", "MBS 알려줘")[1]
    assert not ensure_kind_filter(sql, "수익률 높은 채권 5개")[1]
    assert not ensure_kind_filter(sql, "미국채 금리 어때")[1]
    # 서술형(발행 주체 풀어쓰기 — 2026-08-31 리드 지적) — 낱말 없이도 종류 특정
    f4, c4 = ensure_kind_filter(sql, "회사에서 발행한 채권 중 금리 높은 것 알려줘")
    assert c4 and "TRIM(std_pd_mcls_nm)='회사채'" in f4
    f5, c5 = ensure_kind_filter(sql, "은행이 발행한 채권 뭐 있어?")
    assert c5 and "IN ('일반은행채','특수은행채')" in f5
    # 구체 주체 우선 소진 — '한국은행이 발행'≠은행채, '카드회사가 발행'≠회사채
    f6, c6 = ensure_kind_filter(sql, "한국은행이 발행한 채권 알려줘")
    assert c6 and "통화안정채권" in f6 and "일반은행채" not in f6
    f7, c7 = ensure_kind_filter(sql, "카드회사가 발행한 채권 수익률은?")
    assert c7 and "신용카드채" in f7 and "std_pd_mcls_nm" not in f7
    f8, c8 = ensure_kind_filter(sql, "정부가 발행한 채권 보여줘")
    assert c8 and "TRIM(std_pd_mcls_nm)='국공채'" in f8
    # 2026-09-01 서버 실측 — SELECT 의 TRIM(pd_pbcm) 표시 컬럼은 필터가 아니다: 발동해야 함
    show_sql = ("SELECT DISTINCT pd_no, TRIM(pd_nm), TRIM(pd_pbcm) as 발행기관, applied_yield "
                "FROM domestic_bonds WHERE pd_risk_gcd = '16' LIMIT 5")
    f9, c9 = ensure_kind_filter(show_sql, "망하지 않을 회사가 발행한 채권만 골라줘")
    assert c9 and "TRIM(std_pd_mcls_nm)='회사채'" in f9
    # WHERE 의 pd_pbcm 은 발행사 필터 — 종전대로 불개입 (발행사조회 영역)
    assert not ensure_kind_filter(
        "SELECT pd_nm FROM domestic_bonds WHERE pd_pbcm LIKE '%한국전력%' LIMIT 5",
        "회사가 발행한 채권 알려줘")[1]
    # 특정 발행사 지칭 — SQL 에 발행사 필터가 있으면 종류를 덧씌우지 않는다 (발행사조회 영역)
    issuer_sql = "SELECT pd_nm FROM domestic_bonds WHERE pd_pbcm LIKE '%삼성전자%' LIMIT 30"
    assert not ensure_kind_filter(issuer_sql, "삼성전자라는 회사가 발행한 채권 알려줘")[1]


class BuggyNoKindRecoPlanner:
    """2026-08-31 저녁 서버 실측 SQL ① 그대로 — 등급 IN 은 맞췄으나 회사채 필터 부재 + 제외 없음."""

    def plan_sql(self, question, grounding):
        return ("SELECT pd_nm, bd_intp_tcd, bd_inrt_tcd, srfc_irt, applied_yield FROM domestic_bonds "
                "WHERE TRIM(crd_grd) IN ('AAA', 'AA+', 'AA0', 'AA-') ORDER BY srfc_irt DESC LIMIT 5")

    def compose_answer(self, question, rows, answer_rules=""):
        return "ok"


def test_full_path_kind_and_reco(ctx):
    r = answer_question("T-25", "AA등급 이상 회사채 중에서 표면금리 높은 순으로 5개 추천해줘",
                        planner=BuggyNoKindRecoPlanner(), ctx=ctx)
    assert "[Guard] 종류 조건 주입" in r.think_trace
    assert "[Guard] 추천 제외 주입" in r.think_trace
    assert "우리금융캐피탈458" in r.retrieved_context      # 정답 1위 복귀
    assert "뉴스텔라" not in r.retrieved_context           # 사모 혼입 차단


class BuggyBankTablePlanner:
    """2026-08-31 저녁 서버 실측 SQL ② 그대로 — bonds_master 환각 + 무TRIM IN."""

    def plan_sql(self, question, grounding):
        return ("SELECT pd_nm, applied_yield FROM bonds_master WHERE bd_knd IN ('일반은행채', '특수은행채') "
                "ORDER BY applied_yield DESC LIMIT 5")

    def compose_answer(self, question, rows, answer_rules=""):
        return "ok"


def test_full_path_bank_table_recovers(ctx):
    r = answer_question("T-26", "은행채 중에서 수익률 높은 순으로 5개 알려줘",
                        planner=BuggyBankTablePlanner(), ctx=ctx)
    assert "[Guard] 테이블명 교정" in r.think_trace
    assert "[Guard] TRIM 보정" in r.think_trace
    assert "질의를 안전하게 실행할 수 없" not in r.answer   # 기각 대신 실행
    assert "[Execute] 5행 조회" in r.think_trace
    assert "한국수출입금융" in r.retrieved_context          # 특수은행채(4위) 포함 — 무TRIM 16행 풀이면 불가능


class BuggyKtbCountPlanner:
    """2026-08-31 저녁 실측 오답 SQL — '국고채' 를 대분류 국공채 행수로 뭉갬."""

    def plan_sql(self, question, grounding):
        return "SELECT COUNT(*) FROM domestic_bonds WHERE std_pd_mcls_nm='국공채'"

    def compose_answer(self, question, rows, answer_rules=""):
        return "ok"


def test_full_path_ktb_count_recovers(ctx):
    r = answer_question("T-24", "국고채는 총 몇 종목이야?", planner=BuggyKtbCountPlanner(), ctx=ctx)
    assert "[Guard] 국고채 종류 교정" in r.think_trace
    assert "[Guard] 종목 수 교정" in r.think_trace
    assert "295" in r.retrieved_context and "2840" not in r.retrieved_context


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


# ── 엣지케이스 가드 2건 (리드 서버 실검증 2026-08-31) ──────────────────────

def test_short_label_strips_corp_suffix():
    """'Li Auto Inc' 라벨이 'Li Auto' 질문에 안 걸리던 것 — 보조 키로 복구."""
    from src.runtime.pipeline import _short_label
    assert _short_label("Li Auto Inc") == "Li Auto"
    assert _short_label("Amazon.com Inc.") == "Amazon.com"
    assert _short_label("Taiwan Semiconductor Manufacturing Co Ltd") == "Taiwan Semiconductor Manufacturing"
    assert _short_label("NVIDIA Corp") == "NVIDIA"
    # 접미어가 없으면 보조 키를 만들지 않는다
    assert _short_label("Samsung Electronics") is None
    # SA·AG·NV 는 일부러 제외 — 회사명 본체와 헷갈린다
    assert _short_label("TotalEnergies SE") is None


def test_ground_partial_company_name(ctx):
    """'Li Auto' 처럼 짧게 불러도 매칭돼야 한다 (리드 실검증 엣지케이스 ①)."""
    from src.runtime.pipeline import _ground
    if not [n for n in ctx.kg_nodes if any("Li Auto" in l for l in n.labels)]:
        pytest.skip("Li Auto 노드 미빌드 — build_ontology.py 선행 필요")
    _, lines = _ground("Li Auto 담은 ETF", ctx, ["domestic_etfs"], cross=True)
    assert any("Li Auto" in l for l in lines), lines


def test_ground_partial_name_word_boundary(ctx):
    """보조 키는 단어 경계까지 본다 — 'Apple' 이 'Pineapple' 에 붙으면 안 된다."""
    from src.runtime.pipeline import _short_label
    import re
    short = _short_label("Apple Inc")
    assert short == "Apple"
    assert re.search(rf"(?<![A-Za-z0-9]){short}(?![A-Za-z0-9])", "Pineapple ETF") is None


def test_region_korea_is_listing_not_filter():
    """'국내 ETF' 의 '국내' 는 상장 시장 — wu_inv_rgn 필터로 쓰면 안 된다 (엣지케이스 ②)."""
    from src.runtime.pipeline import _region_korea_is_listing as f
    assert f("Li Auto를 담은 국내 ETF")
    assert f("국내 상장 ETF 중 미국에 투자하는 것")
    assert f("채권형 국내 ETF")
    assert f("국내ETF 알려줘")
    # 투자 대상을 가리키는 자리는 걸리지 않는다
    assert not f("국내에 투자하는 ETF")
    assert not f("국내 주식형 ETF")
    assert not f("국내 채권 알려줘")


def test_ground_drops_region_korea_for_listing(ctx):
    """'국내 상장 ETF 중 미국에 투자하는' — 국내는 빠지고 미국은 남아야 한다."""
    from src.runtime.pipeline import _ground
    _, lines = _ground("국내 상장 ETF 중 미국에 투자하는 것", ctx, ["domestic_etfs"], cross=True)
    assert any("Region_US" in l for l in lines), lines
    assert not any("Region_Korea (Region)" in l for l in lines), lines
    # 투자 대상 자리면 그대로 남는다
    _, lines2 = _ground("국내에 투자하는 ETF", ctx, ["domestic_etfs"], cross=True)
    assert any("Region_Korea" in l and "건너뜀" not in l for l in lines2), lines2


def test_guard_rejects_undeclared_table_reference():
    """FROM/JOIN 에 없는 테이블을 `테이블.컬럼` 으로 참조하면 실행이 깨진다 (서버 실측 2026-08-31).

    Guard 가 '통과' 를 찍고 Execute 에서 OperationalError 가 나 답변이 '오류' 로 나갔다.
    여기서 기각해야 재생성 1회가 JOIN 을 붙일 기회를 얻는다.
    """
    bad = ("SELECT pd_nm AS 상품명 FROM domestic_etfs "
           "WHERE TRIM(ext_etf_holdings.ticker) = 'LI' AND domestic_etfs.wu_inv_rgn = '국내' LIMIT 30")
    err = validate_sql(bad)
    assert err and "ext_etf_holdings" in err
    # 다른 마스터 테이블을 선언 없이 끌어다 쓰는 것도 같다
    assert validate_sql("SELECT pd_nm FROM domestic_etfs WHERE overseas_etfs.pd_nm='x' LIMIT 5")


def test_guard_allows_declared_join_and_alias():
    """정상 JOIN·별칭은 그대로 통과해야 한다 — 기각 규칙이 과잉이면 정답 SQL 을 버린다."""
    ok_join = ("SELECT pd_nm FROM domestic_etfs JOIN ext_etf_holdings "
               "ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no "
               "WHERE ext_etf_holdings.constituent = '삼성전자' LIMIT 30")
    assert validate_sql(ok_join) is None
    ok_alias = ("SELECT e.pd_nm FROM domestic_etfs e JOIN ext_etf_holdings h "
                "ON h.etf_ticker = e.pd_itm_no WHERE h.constituent = '삼성전자' LIMIT 30")
    assert validate_sql(ok_alias) is None
    assert validate_sql("SELECT d.pd_nm FROM domestic_etfs d WHERE d.pd_grp_no='ETF' LIMIT 5") is None


# ── 라우팅 결함 2건 (서버 실측 2026-08-31 저녁) ─────────────────────────

def test_route_lowercase_product_noun(ctx):
    """'etf' 소문자도 상품 명사로 잡혀야 한다.

    서버 실측: "안전한 etf상품 추천좀" 이 미특정 → 4테이블이 되어 근거문서가 39,403자로 불었고,
    HCX 가 펀드 컬럼(zrin_*)을 domestic_etfs 에 써서 재생성까지 실패했다.
    """
    from src.runtime.router import route
    for q in ("안전한 etf상품 추천좀", "etf 알려줘", "Etf 추천", "etn 알려줘"):
        r = route(q, ctx)
        assert r.decided, q
        assert set(r.tables) == {"domestic_etfs", "overseas_etfs"}, (q, r.tables)


def test_route_conjunction_na(ctx):
    """받침 없는 체언 뒤의 '나' 도 병렬 표지다 — 'ETF나 펀드' 에서 ETF 가 빠지면 안 된다.

    서버 실측: "삼성전자가 들어 있는 ETF나 펀드 중에 1년 수익률 좋은 걸 알려줘" 가
    머리명사를 '펀드' 하나로 잡아 public_funds 만 조회했다(ETF 통째로 누락).
    """
    from src.runtime.router import route
    r = route("삼성전자가 들어 있는 ETF나 펀드 중에 1년 수익률 좋은 걸 알려줘", ctx)
    assert set(r.tables) == {"domestic_etfs", "overseas_etfs", "public_funds"}, r.tables
    assert r.groups == 2, r.groups
    # '와' 로 이었을 때와 같아야 한다
    r2 = route("삼성전자가 들어 있는 ETF와 펀드 중에 1년 수익률 좋은 걸 알려줘", ctx)
    assert set(r.tables) == set(r2.tables)


def test_unknown_column_feedback_names_owner(ctx):
    """없는 컬럼이 어느 테이블 것인지 알려줘야 재생성이 같은 실수를 반복하지 않는다."""
    from src.runtime.pipeline import _name_owners
    msg = _name_owners(["zrin_fd_ivst_risk_gcd"], ctx)
    assert "public_funds" in msg


def test_unknown_column_feedback_suggests_near_miss(ctx):
    """어느 테이블에도 없는 환각 컬럼은 철자 유사 후보를 붙인다 (FND-035: mtco_nm 반복 실측)."""
    from src.runtime.pipeline import _name_owners
    msg = _name_owners(["mtco_nm"], ctx)
    assert "없는 컬럼" in msg and "mtco_itm_no" in msg


def test_gate_annualized_return_absent(ctx):
    """'연평균 수익률' 은 HCX 없이 즉답 — 플래너·답변기가 층끼리 어긋나던 것 (FND-017 실측)."""
    from src.runtime import gate
    g = gate.check("연평균 수익률이 가장 높은 공모펀드 알려줘", ctx, ["public_funds"])
    assert g.rejected and "누적" in g.answer and "수록되어 있지 않" in g.answer
    # '연평균' 이 없으면 발동하지 않는다
    g2 = gate.check("1년 수익률이 가장 높은 공모펀드 알려줘", ctx, ["public_funds"])
    assert not g2.rejected


def test_gate_ac_class_choice_is_conditional_answer(ctx):
    """A/C 클래스 유불리는 게이트 즉답 — 플래너가 '정보가 없다'+전문가 면책으로 오거절 (FND-C04 실측)."""
    from src.runtime import gate
    g = gate.check("같은 펀드면 A클래스랑 C클래스 중 뭐가 유리해?", ctx, ["public_funds"])
    assert g.rejected and "투자 기간" in g.answer and "판매보수" in g.answer
    # 조회 질의(보수 알려줘)는 발동하지 않는다 — 판단 어휘가 있어야 한다
    g2 = gate.check("솔로몬 펀드 A클래스랑 C클래스 보수 알려줘", ctx, ["public_funds"])
    assert not g2.rejected


def test_gate_no_redemption_fee_is_qualified_answer(ctx):
    """환매수수료 '없음'은 게이트 즉답 — SQL 은 미수록 30행 조회에 성공했는데 답변기가 통째 거절 (FND-R07 실측)."""
    from src.runtime import gate
    g = gate.check("환매 수수료가 없는 펀드 알려줘", ctx, ["public_funds"])
    assert g.rejected and "단정할 수 없" in g.answer and "297" in g.answer
    g2 = gate.check("환매수수료 면제되는 펀드 있어?", ctx, ["public_funds"])
    assert g2.rejected
    # 조회 질의(조건 알려줘)·안내 요청은 발동하지 않는다
    for q in ("미래에셋 펀드 환매수수료 알려줘", "환매수수료 안내해줘"):
        assert not gate.check(q, ctx, ["public_funds"]).rejected


def test_ground_uses_yaml_synonyms(ctx):
    """yaml synonyms 가 Ground 매칭 키로도 쓰여야 한다 (서버 실측 2026-08-31 저녁).

    "국내 etf중 하이닉스가 가장많이 편입된상품" 이 KG 매칭 0건이라
    HCX 가 컬럼명을 추측해 holding_nm 을 만들어 냈다(실제 컬럼은 constituent).
    """
    from src.runtime.pipeline import _ground, _synonym_keys
    assert "하이닉스" in [t for t, _ in _synonym_keys(ctx).get("SK하이닉스", [])]    # 4R I-3: (통칭, 테이블) 쌍
    _, lines = _ground("국내 etf중 하이닉스가 가장많이 편입된상품은 무어야", ctx, ["domestic_etfs"], cross=True)
    assert any("Sec_kr_000660" in l for l in lines), lines
    # 정식 표기로 물어도 같은 노드
    _, full = _ground("SK하이닉스 담은 ETF", ctx, ["domestic_etfs"], cross=True)
    assert any("Sec_kr_000660" in l for l in full), full


# ── 라우팅 로컬 일제점검에서 나온 결함 3건 (2026-08-31 밤) ────────────────

def test_route_brand_with_space(ctx):
    """'KODEX 200' 처럼 띄어 쓴 상품명이 어휘에 안 걸리던 것.

    어휘는 공백을 뗀 'KODEX200' 으로 저장되는데(loader._VOCAB_STRIP) 영문 값에는
    한글에 있던 공백 무시 폴백이 없어 미특정 → 마스터 4테이블로 빠졌다.
    """
    from src.runtime.router import route
    for q in ("KODEX 200 알려줘", "KODEX200 알려줘", "TIGER 미국S&P500 총보수"):
        r = route(q, ctx)
        assert set(r.tables) == {"domestic_etfs"}, (q, r.tables)


def test_route_korean_transliteration(ctx):
    """'이티에프' 한글 음차도 상품 명사다."""
    from src.runtime.router import route
    for q in ("이티에프 알려줘", "이티에프중에 좋은거", "상장지수펀드 알려줘"):
        r = route(q, ctx)
        assert set(r.tables) == {"domestic_etfs", "overseas_etfs"}, (q, r.tables)


def test_route_all_tokens_are_qualifiers(ctx):
    """상품 명사가 전부 '…형' 이면 그것이 머리다 — 'ETF형 상품' 에는 다른 머리가 없다."""
    from src.runtime.router import route
    assert set(route("ETF형 상품", ctx).tables) == {"domestic_etfs", "overseas_etfs"}
    # 뒤에 진짜 머리가 있으면 종전대로 수식어로 버린다
    assert set(route("채권형 ETF 알려줘", ctx).tables) == {"domestic_etfs", "overseas_etfs"}
    assert set(route("주식형 펀드", ctx).tables) == {"public_funds"}


def test_ground_short_company_names(ctx):
    """짧은 회사명이 Sec_ 하한(한글 4·영문 6)에 통째로 걸려 있던 것.

    로컬 일제점검 2026-08-31: 국내ETF 편입 상위 28종 중 8종이 매칭 0이었다 —
    기아(170개 ETF)·현대차(168개)·카카오·테슬라·애플·네이버·NAVER·포스코홀딩스.
    """
    from src.runtime.pipeline import _ground
    for name in ("기아", "현대차", "카카오", "애플", "테슬라", "네이버", "포스코홀딩스"):
        _, lines = _ground(f"{name} 담은 ETF 알려줘", ctx, ["domestic_etfs"], cross=True)
        assert [x for x in lines if "건너뜀" not in x], f"{name} 매칭 0"


def test_ground_korean_josa_and_boundary(ctx):
    """조사는 붙여 쓰고(하이닉스'가'), 낱말이 이어지면 안 붙어야 한다(기아'자동차')."""
    from src.runtime.pipeline import _boundary_hit
    assert _boundary_hit("하이닉스", "하이닉스가 가장 많이")
    assert _boundary_hit("기아", "기아를 담은 ETF")
    assert _boundary_hit("네이버", "네이버의 비중이 높은")
    # 낱말이 이어지면 기각
    assert not _boundary_hit("기아", "기아자동차 담은 ETF")
    assert not _boundary_hit("나노", "나노기술 ETF")
    assert not _boundary_hit("농심", "농심라면 ETF")     # '라' 는 조사 모양이나 뒤에 '면' 이 붙는다
    # 영문은 영숫자 경계
    assert _boundary_hit("NAVER", "NAVER 담은 ETF")
    assert not _boundary_hit("Apple", "Pineapple ETF")


def test_ground_combined_label_split(ctx):
    """'네이버/NAVER' 처럼 한 칸에 두 표기가 든 라벨 — 한쪽으로 물어도 잡혀야 한다."""
    from src.runtime.pipeline import _ground
    for name in ("네이버", "NAVER", "포스코홀딩스"):
        _, lines = _ground(f"{name} 편입 ETF", ctx, ["domestic_etfs"], cross=True)
        assert [x for x in lines if "건너뜀" not in x], f"{name} 매칭 0"


def test_guard_rejects_wrong_table_qualifier(ctx):
    """선언된 테이블이어도 그 테이블에 없는 컬럼을 수식자로 붙이면 기각해야 한다.

    서버 실측 2026-08-31: SUM(domestic_etfs.weight_pct) — weight_pct 는 ext_etf_holdings 컬럼인데
    domestic_etfs 에 붙였고 Guard 가 '검사 통과' 를 찍었다(SQL 안 다른 테이블에 있어서).
    """
    bad = ("SELECT domestic_etfs.pd_abrv_nm, SUM(domestic_etfs.weight_pct) FROM domestic_etfs "
           "JOIN ext_etf_holdings ON domestic_etfs.pd_itm_no = ext_etf_holdings.etf_code "
           "WHERE ext_etf_holdings.constituent='SK하이닉스' GROUP BY 1 LIMIT 1")
    err = validate_sql(bad)
    assert err and "weight_pct" in err and "ext_etf_holdings" in err, err
    # 올바른 수식자·별칭은 통과
    ok = bad.replace("SUM(domestic_etfs.weight_pct)", "SUM(ext_etf_holdings.weight_pct)")
    assert validate_sql(ok) is None
    alias = ("SELECT e.pd_abrv_nm, SUM(h.weight_pct) FROM domestic_etfs e "
             "JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no GROUP BY 1 LIMIT 5")
    assert validate_sql(alias) is None


def test_guard_rejects_mismatched_ext_master_pair(ctx):
    """ext_* 를 남의 마스터와 조인하면 기각 — 컬럼이 각자 실존해 수식자 검사는 통과한다.

    서버 실측 2026-09-01(공식 예시 #3): domestic_etfs ⋈ ext_fund_holdings (d.pd_itm_no=h.grp)
    가 Guard 를 통과하고 0행 → '확인되지 않습니다' 오답.
    """
    bad = ("SELECT d.pd_abrv_nm FROM domestic_etfs d JOIN ext_fund_holdings h "
           "ON d.pd_itm_no = h.grp WHERE h.holding_nm = '캠브리콘' LIMIT 30")
    err = validate_sql(bad)
    assert err and "public_funds" in err, err
    ok = ("SELECT e.pd_abrv_nm FROM domestic_etfs e JOIN ext_etf_holdings h "
          "ON h.etf_code = e.pd_itm_no LIMIT 5")
    assert validate_sql(ok) is None


def test_kg_cambricon_domestic_link(ctx):
    """공식 예시 #3 — 캠브리콘 정본이 국내ETF 구성종목 노드(Sec_d, '688256 C1')까지 편다."""
    clos = ctx.kg_closure.get("Sec_m_cambricon") or []
    assert "Sec_d_f186d5f574" in clos, clos
    from src.runtime.pipeline import _ground
    _, lines = _ground("캠브리콘이 편입된 중국 반도체 ETF를 알려줘", ctx, ["domestic_etfs"], cross=True)
    assert any("ext_etf_holdings" in l for l in lines), lines


def test_zero_row_lookup_suggests_similar(ctx):
    """존재하지 않는 상품의 완전일치 조회가 0행이면 유사 후보를 되묻는다 (공식 예시 NA-3).

    '확인할 수 없음' 단문도 정답 처리되지만, clarify.존재하지_않는_개체 의 정답 형태는
    "혹시 △△ 를 말씀하신 건가요?" 되묻기다 — 후보 4종을 버리면 아깝다.
    """
    from src.runtime.pipeline import _suggest_similar_products
    cand = _suggest_similar_products(
        "SELECT * FROM domestic_etfs WHERE TRIM(pd_abrv_nm) = 'KODEX AI로봇' LIMIT 30")
    assert cand, "후보 0건"
    assert any("로봇" in c for c in cand), cand
    # 단일 토큰·미매칭 이름은 빈 목록 — 되묻기 없이 종전 확인불가 문구로
    assert _suggest_similar_products(
        "SELECT * FROM domestic_etfs WHERE TRIM(pd_abrv_nm) = 'VOO' LIMIT 30") == []


# ── R-2 triggers 도입 (2026-09-01) — 규칙 선별주입이 필요 규칙을 빠뜨리지 않는지 ──

def test_triggers_cover_regression_questions(ctx):
    """회귀 문항마다 그 문항이 의존하는 규칙이 프롬프트에 실려야 한다.

    always-on 39개 → triggered 27개로 바꾸면서 생기는 유일한 위험은 **누락**이다
    (과잉 주입은 무해). 문항-규칙 대응을 못박아 트리거를 좁힐 때 여기서 걸리게 한다.
    """
    NEED = {
        "인버스 ETF 3개 알려줘": ["인버스", "개수만_준_질의"],
        "총보수 낮은 국내 ETF 5개 알려줘": ["보수유효", "국내는_지역필터가_아니다"],
        "KODEX 200 총보수 알려줘": ["보수개별조회", "상품명조회"],
        "kodex 200 총보수 알려줘": ["보수개별조회"],          # 소문자 — loader casefold
        "Li Auto를 담은 국내 ETF 알려줘": ["편입비중상위", "국내는_지역필터가_아니다"],
        "레버리지제외하고 국내 etf중 하이닉스가 가장많이 편입된상품은 뭐야":
            ["편입비중상위", "레버리지"],
        "헬스케어 섹터 ETF 알려줘": ["섹터_한영대응", "섹터테마질의"],
        "에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘":
            ["위험요인질의", "편입비중상위"],
        "환헤지된 미국 ETF 알려줘": ["환헤지"],
        "선물 ETF 알려줘": ["선물"],
    }
    for q, rules in NEED.items():
        p = ctx.planner_context(["domestic_etfs"], question=q)
        for r in rules:
            assert f"- {r}:" in p, f"'{q}' 에 규칙 {r} 미주입"


def test_triggers_cover_overseas(ctx):
    NEED = {
        "수수료 저렴한 해외 ETF 5개 알려줘": ["보수유효", "개수만_준_질의"],
        "해외 인버스 ETF 3개 알려줘": ["인버스숏"],
        "VOO 정보 알려줘": ["개별조회_별칭", "상품명조회"],
        "캠브리콘이 편입된 중국 반도체 ETF를 알려줘": ["ISIN조인금지", "종목질의_회사채포함"],
    }
    for q, rules in NEED.items():
        p = ctx.planner_context(["overseas_etfs"], question=q)
        for r in rules:
            assert f"- {r}:" in p, f"'{q}' 에 규칙 {r} 미주입"


def test_triggers_trim_prompt(ctx):
    """트리거 도입의 목적 — 무관 규칙이 빠져 프롬프트가 줄어야 한다 (도입 전 11,760자 고정)."""
    p = ctx.planner_context(["domestic_etfs"], question="ETF 알려줘")
    # 6000 → 7000 (2026-09-02): 바이오 실측 수리로 always-on 3건 추가(질문에_없는_필터금지 등).
    # 도입 전 11,760자 대비 여전히 40%+ 절감 — 상한은 "다시 무한정 붇지 않게" 만 지킨다.
    assert len(p) < 7000, len(p)
    assert "- 환헤지:" not in p and "- 선물:" not in p     # 무관 규칙은 빠진다
    assert "- ETF만:" in p                                  # 보편 제약은 남는다


def test_paraphrases_still_get_critical_rules(ctx):
    """🔴 2026-09-01 2차 점검 — 트리거식 전환 직후 바꿔 말한 질의 7/9에서 규칙이 빠졌다.
    오답을 만드는 규칙(보수·인버스·편입비중·위험)은 always-on 으로 복귀했다 — 이 테스트는
    누군가 다시 트리거식으로 바꾸면 같은 사고가 재발한다는 것을 잡는 회귀 담장이다."""
    cases = [
        ("돈 제일 조금 떼가는 국내 ETF 5개", "보수유효"),
        ("제일 싸게 살 수 있는 ETF", "보수유효"),
        ("운용 코스트 낮은 ETF", "보수유효"),
        ("지수 반대로 가는 ETF 3개", "인버스"),
        ("떨어질 때 버는 ETF", "인버스"),
        ("삼성전자 제일 많이 갖고 있는 ETF", "편입비중상위"),
        ("원금 잃기 싫은데 뭐 사", "위험요인질의"),
        ("ETF 아무거나 5개", "개수만_준_질의"),
    ]
    misses = [f"{q} → {rule}" for q, rule in cases
              if f"- {rule}:" not in ctx.planner_context(["domestic_etfs"], question=q)]
    assert not misses, f"바꿔 말한 질의에서 규칙 누락: {misses}"


def test_validate_sql_rejects_unparenthesized_or_and():
    """서버 실측 2026-09-02 '바이오 ETF 추천' — OR 사슬 뒤 괄호 없는 AND 필터는
    마지막 가지에만 걸린다. validate_sql 이 기계적으로 기각해야 한다."""
    from src.runtime.pipeline import validate_sql
    bad = ("SELECT pd_nm FROM domestic_etfs WHERE pd_nm LIKE '%바이오%' "
           "OR ref_base_index LIKE '%Bio%' AND pd_grp_no='ETF' LIMIT 5")
    assert validate_sql(bad) and "괄호" in validate_sql(bad)
    ok = [
        ("SELECT pd_nm FROM domestic_etfs WHERE (pd_nm LIKE '%바이오%' "
         "OR ref_base_index LIKE '%Bio%') AND pd_grp_no='ETF' LIMIT 5"),
        "SELECT pd_nm FROM domestic_etfs WHERE pd_nm LIKE '%a%' OR pd_nm LIKE '%b%' LIMIT 5",
        ("SELECT pd_nm FROM domestic_etfs WHERE pd_grp_no='ETF' AND "
         "(pd_nm LIKE '%a%' OR (pd_nm LIKE '%b%' AND du_clpr>0)) LIMIT 5"),
        "SELECT pd_nm FROM domestic_etfs WHERE pd_nm LIKE '% OR %' AND du_clpr>0 LIMIT 5",
    ]
    for q in ok:
        assert validate_sql(q) is None, q


def test_risk_ambiguity_clarify(ctx):
    """리드 결정 2026-09-02 — '가장 위험한 채권' 은 투자위험등급/신용등급/금리위험 세 축이라 축 단서 없으면 되묻는다 (서버 실측: 1등급+수익률순 단정)."""
    from src.runtime.pipeline import risk_ambiguity_clarify as f, answer_question
    a = f("가장 위험한 채권 뭐야?", ["domestic_bonds"])
    assert a and "투자위험등급" in a and "신용등급" in a and "듀레이션" in a and "1,394종목" in a and "103종목" in a and "어느 기준" in a
    assert f("위험 높은 순으로 채권 알려줘", ["domestic_bonds"]) and f("제일 위험한 채권 추천해줘", ["domestic_bonds"])
    # 축 단서가 있으면 되묻지 않는다 · 채권 밖 테이블 불개입 · '안전' 질의는 별도 규칙(최상급 안전 = 6등급)
    assert f("위험등급 1등급 채권 알려줘", ["domestic_bonds"]) is None
    assert f("신용등급이 가장 낮은 채권", ["domestic_bonds"]) is None
    assert f("수익률 높은 위험한 채권", ["domestic_bonds"]) is None
    assert f("가장 위험한 펀드 뭐야?", ["public_funds"]) is None
    assert f("가장 안전한 채권 뭐야?", ["domestic_bonds"]) is None
    r = answer_question("T-RISK", "가장 위험한 채권 뭐야?", ctx=ctx)
    assert "[Clarify] 되묻기(결정층)" in r.think_trace and "728" not in r.answer and r.retrieved_context == ""


# ── 상대 시점 확정표 — 2026-09-03 서버 실측 #51 "내년에 만기가 되는 회사채 중 AA 이상" 오기각 회귀 ──────────
# 질문 시점(오늘) = 2026-08-24(월) 고정. HCX 가 '내년' 을 BETWEEN 20280824 AND 20290824 로 오계산했고
# 사후검사가 "SQL 에 2027 이 없다" 를 "만기 질의가 아니다" 로 읽어 기준일 안내로 끝냈다.

def test_resolve_relative_window_table():
    from src.runtime import gate
    w = gate.resolve_relative_window
    assert w("내년에 만기가 되는 회사채 중 신용등급이 AA 이상인 것을 알려줘") == [("내년", 20270101, 20271231)]
    assert w("오늘 만기인 채권 있어?") == [("오늘", 20260824, 20260824)]
    assert w("내일 만기 채권") == [("내일", 20260825, 20260825)]
    assert w("이번 주 만기") == [("이번 주", 20260824, 20260830)]                 # 8/24 월 ~ 8/30 일
    assert w("이번 달 만기") == [("이번 달", 20260824, 20260831)]
    assert w("다음 달 만기") == [("다음 달", 20260901, 20260930)]
    assert w("올해 안에 만기되는 채권") == [("올해", 20260824, 20261231)]
    assert w("연내 만기") == [("올해", 20260824, 20261231)]
    assert w("6개월 안에 만기되는 채권") == [("6개월 안에", 20260824, 20270224)]
    assert w("1년 안에 만기") == [("1년 안에", 20260824, 20270824)]
    assert w("3년 안에 만기되는 안전한 채권") == [("3년 안에", 20260824, 20290824)]
    assert w("1년 뒤 만기") == [("1년 뒤", 20270101, 20271231)]                    # 내년과 같은 읽기
    assert w("3년 뒤에 만기 돌아오는 채권은 몇 종목이야?") == [("3년 뒤", 20290101, 20291231)]
    assert w("내후년 만기 국고채") == [("내후년", 20280101, 20281231)]
    assert w("내년 상반기 만기") == [("내년 상반기", 20270101, 20270630)]          # '내년' 으로 또 잡히지 않는다
    # 기간 표현·상품명·발행사명은 창이 아니다
    assert w("10년 만기 채권 알려줘") == []
    assert w("잔존만기 3년 넘는 채권") == []
    assert w("10년 후순위채") == []
    assert w("KB내일드림 펀드") == [] and w("교보악사 내일환매 펀드") == [] and w("오늘이엔엠 채권") == []
    # future_tokens 는 확정표에서 연도를 받는다
    assert gate.future_tokens("내년에 만기되는 회사채") == ["2027"]
    assert gate.future_tokens("3년 뒤 만기 채권") == ["2029"]
    assert gate.future_tokens("올해 안에 만기되는 채권") == []


def test_enforce_relative_window():
    from src.runtime import gate
    from src.runtime.pipeline import enforce_relative_window
    q = "내년에 만기가 되는 회사채 중 신용등급이 AA 이상인 것을 알려줘"
    sql = ("SELECT pd_no, pd_nm, crd_grd, mat_dt, remaining_days FROM domestic_bonds WHERE mat_dt BETWEEN 20280824 AND 20290824 "
           "AND crd_grd IN ('AAA','AA+','AA0') AND TRIM(std_pd_mcls_nm)='회사채' LIMIT 30")
    fixed, note = enforce_relative_window(sql, q, gate.resolve_relative_window(q))
    assert note and "mat_dt BETWEEN 20270101 AND 20271231" in fixed and "20280824" not in fixed
    assert "crd_grd IN ('AAA','AA+','AA0')" in fixed and "TRIM(std_pd_mcls_nm)='회사채'" in fixed   # 다른 조건은 산다
    # remaining_days 조건은 걷어낸다(8/21 기준) — ORDER BY 의 remaining_days 는 남는다(mat_dt 와 단조)
    q2 = "1년 안에 만기되는 채권"
    fixed2, _ = enforce_relative_window("SELECT pd_nm FROM domestic_bonds WHERE remaining_days <= 365 AND curr_cd='KRW' ORDER BY remaining_days LIMIT 30",
                                        q2, gate.resolve_relative_window(q2))
    assert "remaining_days <= 365" not in fixed2 and "mat_dt BETWEEN 20260824 AND 20270824" in fixed2 and "ORDER BY remaining_days" in fixed2
    # 만기 조건이 없어도 질문이 '만기' 를 말하면 주입 — '오늘' 은 등호
    q3 = "오늘 만기인 채권 있어?"
    fixed3, _ = enforce_relative_window("SELECT pd_nm FROM domestic_bonds ORDER BY applied_yield DESC LIMIT 5", q3, gate.resolve_relative_window(q3))
    assert "WHERE mat_dt = 20260824" in fixed3
    # 불개입: '오늘' 이 시점일 뿐인 질의 · 만기 경과 질의 · 이미 같은 창
    q4 = "오늘 수익률 높은 채권"
    assert enforce_relative_window("SELECT pd_nm FROM domestic_bonds WHERE applied_yield > 5 LIMIT 5", q4, gate.resolve_relative_window(q4))[1] is None
    q5 = "올해 만기 지난 채권"
    assert enforce_relative_window("SELECT pd_nm FROM domestic_bonds WHERE mat_dt < 20260824 LIMIT 5", q5, gate.resolve_relative_window(q5))[1] is None
    assert enforce_relative_window("SELECT pd_nm FROM domestic_bonds WHERE mat_dt BETWEEN 20270101 AND 20271231 LIMIT 5", q, gate.resolve_relative_window(q))[1] is None
    # ── 2026-09-05 서버 실측 #66 회귀 — '축 대체': 발행 시점 질의에 만기 창을 강제하던 자리 ──
    # 원 사고: "최근 6개월 안에 새로 발행된 회사채 중 표면금리 높은 5개" 가 답한 5종목의 실제 발행일은
    #          2023-09-15 ~ 2025-09-24 로 5/5 전부 창 밖. 발행 축(isu_dt)이 있는데 창이 mat_dt 로 갔다.
    floor = "SELECT pd_nm FROM domestic_bonds WHERE curr_cd='KRW' AND mat_dt >= 20260824"
    for qi in ("최근 6개월 안에 새로 발행된 회사채 중에 표면금리 높은 5개 알려줘",
               "이번 달에 새로 나온 채권", "올해 발행된 채권 알려줘"):
        assert enforce_relative_window(floor + " LIMIT 30", qi, gate.resolve_relative_window(qi))[1] is None
    # HCX 가 isu_dt 로 옳게 써도 종전엔 mat_dt 창이 덧붙어 '발행 AND 만기' 로 오염됐다
    q6 = "올해 발행된 채권 알려줘"
    assert enforce_relative_window(floor + " AND isu_dt BETWEEN 20260101 AND 20260824 LIMIT 30", q6,
                                   gate.resolve_relative_window(q6))[1] is None
    # 구매가능 하한(mat_dt >= 판정일)은 사용자가 물은 만기 조건이 아니다 — 이것 때문에 만기를 말하지 않은
    # "오늘 수익률 높은 채권" 이 mat_dt = 20260824(만기가 오늘)로 좁혀졌다. q4 와 같은 질문, 실운영 SQL 형태.
    assert enforce_relative_window(floor + " AND applied_yield > 5 LIMIT 5", q4, gate.resolve_relative_window(q4))[1] is None
    # 만기 질의는 하한만 있어도 종전대로 발동한다
    q7 = "3년 안에 만기되는 안전한 채권 몇 개만 골라줘"
    assert "mat_dt BETWEEN 20260824 AND 20290824" in enforce_relative_window(floor + " LIMIT 30", q7, gate.resolve_relative_window(q7))[0]
    # '발행' 과 '만기' 를 함께 물으면 만기 축 판정은 살아 있다
    q8 = "올해 발행된 채권 중 내년에 만기되는 것"
    assert enforce_relative_window(floor + " LIMIT 30", q8, gate.resolve_relative_window(q8))[1] is None   # 창이 둘 → 불개입


def test_effective_mat_window_header():
    """2026-09-05 #68 — 머리줄 만기 창은 mat_dt 조건 전부의 교집합이다.

    "지난달에 만기된 채권들은 지금 어떻게 됐어?" 가 `BETWEEN 20260824 AND 20260930 AND mat_dt <= 20260824+90` 로 나갔고
    머리줄은 첫 BETWEEN 만 읽어 8/24~9/30 이라 적었다. 모수 473종목은 8/24~9/14(교집합)의 값이었다.
    """
    from src.runtime.pipeline import _effective_mat_window as w
    f = "SELECT pd_no FROM domestic_bonds WHERE "
    assert w(f + "mat_dt BETWEEN 20260824 AND 20260930 AND mat_dt <= 20260914 GROUP BY pd_no LIMIT 30") == "2026-08-24~2026-09-14"
    assert w(f + "(mat_dt >= 20260824 AND mat_dt <= 20290824) LIMIT 30") == "2026-08-24~2029-08-24"     # 괄호 그룹도 푼다
    assert w(f + "mat_dt = 20260824 LIMIT 30") == "2026-08-24"
    assert w(f + "mat_dt < 20260824 LIMIT 5") == "2026-08-24 이전"
    # 구매가능 하한 하나뿐이면 창이 아니다(모수) · OR 그룹은 창으로 읽지 않는다 · 조건 없음
    assert w(f + "curr_cd='KRW' AND mat_dt >= 20260824 LIMIT 30") is None
    assert w(f + "(mat_dt >= 20260824 OR mat_dt = 0) LIMIT 30") is None
    assert w("SELECT pd_no FROM domestic_bonds LIMIT 30") is None


def test_issuance_time_q_not_issuer_q():
    """🔴 "X가 발행한 채권" 의 '발행' 은 시점이 아니라 **발행 주체**다 (2026-09-05 #66 자기검토).

    첫 수리는 '발행' 어휘만 보고 발행 시점 질의로 판정해, 발행사 질의 4문항에 "이 질문은 발행 시점
    질의다 — 발행일은 isu_dt 다" 라는 거짓 단언을 프롬프트에 실었다(BND-U-035 되묻기 문항 포함).
    시점 신호(상대 창·과거 창·연도)가 함께 있을 때만 발행 시점 질의다.
    """
    from src.runtime.pipeline import is_issuance_time_q as f
    # 발행사 질의 — 시점 신호가 없다
    assert not f("삼성전자가 발행한 채권 있어?")
    assert not f("보험사가 발행한 채권 중에 제일 안전한 걸로 추천해줘")
    assert not f("망하지 않을 회사가 발행한 채권만 골라줘")
    assert not f("우주항공·방산 쪽 기업이 발행한 채권 정리해줘")
    assert not f("채권을 가장 많이 발행한 기관 5곳을 종목 수와 함께 알려줘")
    # 발행 시점 질의 — 상대 창·과거 창·연도
    assert f("최근 6개월 안에 새로 발행된 회사채 중에 표면금리 높은 5개 알려줘")
    assert f("올해 발행된 채권 알려줘")
    assert f("2024년에 발행된 채권 알려줘")
    assert f("이번 달에 새로 나온 채권")
    # 만기 어휘가 함께 있으면 만기 축 판정이 이긴다(창이 둘이면 가드가 따로 불개입한다)
    assert not f("올해 발행된 채권 중 내년에 만기되는 것")
    assert not f("내년에 만기가 되는 회사채 중 신용등급이 AA 이상인 것을 알려줘")


def test_resolve_past_window():
    """'최근 N개월'·'지난 N년' = 과거 방향 (2026-09-05 #66). 확정표(_RELATIVE_WINDOW)는 건드리지 않는다."""
    from src.runtime import gate
    p = gate.resolve_past_window
    assert p("최근 6개월 안에 새로 발행된 회사채") == [("최근 6개월", 20260224, 20260824)]
    assert p("지난 3개월 발행 채권") == [("지난 3개월", 20260524, 20260824)]
    assert p("최근 1년 안에 발행된 채권") == [("최근 1년", 20250824, 20260824)]
    assert p("지난 1주일 신규 발행") == [("지난 1주일", 20260817, 20260824)]
    assert p("올해 발행된 채권") == []                       # 과거 방향 낱말이 없다
    # 🔴 확정표는 그대로 — '최근 1년 수익률' 류(코퍼스 '최근' 9문항 중 6문항)를 오폭하지 않는다
    assert gate.resolve_relative_window("최근 1년 수익률이 더 높은 것은?") == []
    assert gate.resolve_relative_window("6개월 안에 만기되는 채권") == [("6개월 안에", 20260824, 20270224)]


def test_diagnose_zero_rows_or_branches():
    """0행 사유 — 최상위가 OR 한 덩어리여도 가지별로 진단한다 (2026-09-05 #66).

    원 사고: "우주항공·방산 쪽 기업이 발행한 채권" → `pd_pbcm LIKE '%우주항공%' OR LIKE '%방산%'` 0행 →
             사용자는 사유 없는 "확인되지 않습니다" 한 줄만 받았다.
    """
    from src.runtime import guard
    for sql in ("SELECT pd_nm FROM domestic_bonds WHERE pd_pbcm LIKE '%우주항공%' OR pd_pbcm LIKE '%방산%' LIMIT 30",
                "SELECT pd_nm FROM domestic_bonds WHERE (pd_pbcm LIKE '%우주항공%' OR pd_pbcm LIKE '%방산%') LIMIT 30"):
        d = guard.diagnose_zero_rows(sql)
        assert d and "우주항공" in d.user_text() and "방산" in d.user_text()
    # 조건이 하나뿐이면 종전대로 진단 없음
    assert guard.diagnose_zero_rows("SELECT pd_nm FROM domestic_bonds WHERE pd_pbcm LIKE '%삼성전자%' LIMIT 30") is None


def test_raise_maturity_floor_and_pin_now():
    from src.runtime.pipeline import raise_maturity_floor, pin_sql_now
    assert raise_maturity_floor("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20260101 AND 20261231", "올해 만기") == \
        ("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20260824 AND 20261231", True)
    assert raise_maturity_floor("SELECT 1 FROM domestic_bonds WHERE mat_dt >= 20250101 AND mat_dt <= 20261231", "x")[0].count("20260824") == 1
    # 만기 경과 질의 · 상한까지 과거인 창은 불개입
    assert not raise_maturity_floor("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20250101 AND 20260501", "만기 지난 채권")[1]
    assert not raise_maturity_floor("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20250101 AND 20260501", "2026년 상반기 만기")[1]
    fixed, changed = pin_sql_now("SELECT 1 WHERE mat_dt >= strftime('%Y%m%d','now','+1 year') AND d > CURRENT_DATE")
    assert changed and "'2026-08-24','+1 year'" in fixed and "CURRENT_DATE" not in fixed and "'2026-08-24'" in fixed


def test_align_maturity_year_between():
    from src.runtime.pipeline import align_maturity_year
    fixed, changed = align_maturity_year("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20280824 AND 20290824 LIMIT 1", ["2027"])
    assert changed and "mat_dt BETWEEN 20270101 AND 20271231" in fixed
    assert not align_maturity_year("SELECT 1 FROM domestic_bonds WHERE mat_dt BETWEEN 20270101 AND 20271231 LIMIT 1", ["2027"])[1]


class NextYearMiscountPlanner:
    """2026-09-03 서버 실측 SQL 그대로 — '내년' 을 +2~+3년 창으로 오계산."""

    def plan_sql(self, question, grounding):
        assert "질문 시점(오늘) = 2026-08-24" in grounding and "mat_dt BETWEEN 20270101 AND 20271231" in grounding
        return ("SELECT pd_no, pd_nm, crd_grd, mat_dt, remaining_days FROM domestic_bonds WHERE mat_dt BETWEEN 20280824 AND 20290824 "
                "AND crd_grd IN ('AAA','AA+','AA0') AND TRIM(std_pd_mcls_nm)='회사채' LIMIT 30")

    def compose_answer(self, question, rows, answer_rules=""):
        return "ok"


def test_full_path_next_year_maturity_not_rejected(ctx):
    r = answer_question("T-51", "내년에 만기가 되는 회사채 중 신용등급이 AA 이상인 것을 알려줘",
                        planner=NextYearMiscountPlanner(), ctx=ctx)
    assert "[Guard] 상대 시점 창 확정" in r.think_trace
    assert "mat_dt BETWEEN 20270101 AND 20271231" in r.sql and "20280824" not in r.sql
    assert "시점·전망 질의로 판정" not in r.think_trace and "이후 시점의 정보는 확인할 수 없습니다" not in r.answer
    assert "[Execute] 30행 조회" in r.think_trace
    assert "만기 2027-01-01~2027-12-31 · 질문 시점 2026-08-24 기준" in r.answer
    assert "잔존일수는 데이터 산출일 2026-08-21 기준" in r.answer
    # 시점·전망 질의는 여전히 기각 — mat_dt 조건이 없는 SQL
    class Forecast:
        def plan_sql(self, question, grounding):
            return "SELECT pd_nm, applied_yield FROM domestic_bonds WHERE applied_yield > 0 ORDER BY applied_yield DESC LIMIT 5"
        def compose_answer(self, question, rows, answer_rules=""):
            return "ok"
    r2 = answer_question("T-51b", "2027년 채권 시장 전망 알려줘", planner=Forecast(), ctx=ctx)
    assert "시점·전망 질의로 판정" in r2.think_trace and "2026-08-24" in r2.answer


# ── 국고채 가드 머리명사 판별 + 채권 종목 수 기계 조립 — 2026-09-03 서버 실측 #52 회귀 ──────────
# "국고채를 포함해서 국공채는 전부 몇 종목이야?" → HCX 는 대분류 국공채를 맞게 썼는데 ensure_ktb_kind ②가 '국고채' 낱말만 보고
# 확정식으로 좁혀 295(정답 1,775). 답변도 "국고채를 포함한 국공채는 295종목" 으로 국공채 = 국고채 단정.

def test_ktb_head_is_gov():
    from src.runtime.pipeline import ktb_head_is_gov, ensure_ktb_kind
    assert ktb_head_is_gov("국고채를 포함해서 국공채는 전부 몇 종목이야?")
    assert ktb_head_is_gov("국공채는 몇 종목이야?")
    assert ktb_head_is_gov("국고채까지 합쳐서 국공채 전체 알려줘")
    assert not ktb_head_is_gov("국공채 중 국고채만 몇 종목이야?")
    assert not ktb_head_is_gov("국공채 가운데 국채는 몇 개야?")
    assert not ktb_head_is_gov("국고채는 총 몇 종목이야?")
    sql = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='국공채'"
    assert not ensure_ktb_kind(sql, "국고채를 포함해서 국공채는 전부 몇 종목이야?")[1]          # 대분류 유지
    assert "국고채권" in ensure_ktb_kind(sql, "국공채 중 국고채만 몇 종목이야?")[0]              # 부분집합은 교체
    assert "국고채권" in ensure_ktb_kind(sql, "국고채는 총 몇 종목이야?")[0]                     # 종전 동작 유지(BND-D-029)
    # ① 날조 발행사 제거는 머리명사와 무관하게 남는다
    fixed, changed = ensure_ktb_kind(sql + " AND TRIM(pd_pbcm)='한국은행'", "국고채를 포함해서 국공채는 전부 몇 종목이야?")
    assert changed and "한국은행" not in fixed and "std_pd_mcls_nm)='국공채'" in fixed


class GovCountPlanner:
    """HCX 가 맞게 쓴 SQL — 가드가 이것을 깨면 안 된다."""

    def plan_sql(self, question, grounding):
        return "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='국공채'"

    def compose_answer(self, question, rows, answer_rules=""):
        return "HCX 산문"


def test_full_path_gov_count_including_ktb(ctx):
    r = answer_question("T-52", "국고채를 포함해서 국공채는 전부 몇 종목이야?", planner=GovCountPlanner(), ctx=ctx)
    assert "[Guard] 국고채 종류 교정 보류" in r.think_trace and "[Guard] 국고채 종류 교정 —" not in r.think_trace
    assert "std_pd_mcls_nm)='국공채'" in r.sql and "국고채권" not in r.sql
    assert "[Answer] 채권 종목 수 답변 기계 조립" in r.think_trace and r.answer != "HCX 산문"
    # 🔴 2026-09-04 기준일 8/24 통일(리드 결정) — enforce 슬롯 BONDPOP 이 구매가능 모수를 주입해
    #    1,775(만기 경과 재정증권 1종목 포함) → 1,774 다. 국고채 확정식 295 는 두 모수에서 같다.
    assert "BONDPOP" in (r.enforce_fired or []) and "mat_dt >= 20260824" in r.sql
    assert "1,774종목" in r.answer and "그중 국고채(국고채권 + STRIPS)는 295종목" in r.answer
    # 부분집합 질의는 종전대로 확정식 교체 → 295
    r2 = answer_question("T-52b", "국공채 중 국고채만 몇 종목이야?", planner=GovCountPlanner(), ctx=ctx)
    assert "[Guard] 국고채 종류 교정 —" in r2.think_trace and "295종목" in r2.answer and "1,774" not in r2.answer
    # 대조군 — 국고채 언급 없는 국공채 집계는 가드 미발동
    r3 = answer_question("T-52c", "국공채는 몇 종목이야?", planner=GovCountPlanner(), ctx=ctx)
    assert "국고채 종류 교정" not in r3.think_trace and r3.answer.startswith("국공채는 총 1,774종목입니다")


def test_bond_count_answer_shapes():
    from src.runtime.pipeline import _bond_count_answer
    sql = "SELECT COUNT(DISTINCT pd_no) AS n FROM domestic_bonds WHERE curr_cd='KRW' AND applied_yield > 5 LIMIT 1"
    assert _bond_count_answer(sql, "n\n1406", 1, "수익률 5% 넘는 채권은 몇 종목이야?") == "수익률 5% 넘는 채권은 총 1,406종목입니다 (기준일 2026-08-24)."
    assert _bond_count_answer(sql, "n\n0", 1, "x 몇 종목이야?") is None                       # 0 은 _zero_count_answer 몫
    assert _bond_count_answer("SELECT COUNT(DISTINCT pd_no) AS n, COUNT(*) AS r FROM domestic_bonds LIMIT 1", "n | r\n33 | 40", 1, "통안채 몇 개 있어?") is None   # 2열은 불개입
    assert _bond_count_answer("SELECT TRIM(bd_knd), COUNT(DISTINCT pd_no) FROM domestic_bonds GROUP BY 1 LIMIT 30", "a | b\nx | 1", 1, "종류별 몇 개") is None


def test_residual_name_token_strips_trailing_product_noun():
    """상품 명사가 꼬리에 붙은 호칭이면 떼되, 이름의 일부면 남긴다 (2026-09-03 17R OFFICIAL-002).

    "국민성장펀드" 는 사람의 호칭이고 DB 이름엔 '펀드' 라는 글자가 없다
    (미래에셋국민참여형국민성장혼합자산투자신탁…) — 그대로 LIKE 하면 0행이다.
    반대로 '삼성코리아대표증권자투자신탁' 은 '투자신탁' 이 이름의 일부라 떼면 안 된다.
    판정 근거는 사전이 아니라 **DB 실재 여부**다.
    """
    from src.runtime.pipeline import residual_name_token

    assert residual_name_token("국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘", []) == "국민성장"
    assert residual_name_token("삼성코리아대표증권자투자신탁의 수탁사는 어디야?", []) \
        == "삼성코리아대표증권자투자신탁"
    # 머리명사만 있는 질의는 후보가 없다 (되묻기·일반 조회 경로 보존)
    assert residual_name_token("공모펀드는 유형별로 몇 개씩 있어?", []) is None


def test_refusal_reason_keeps_tail_and_hides_identifiers():
    """기각 사유를 사람 말로 앞에 붙이되, 두 가지를 지킨다 (2026-09-03 17R).

    ① 문장 끝 거절 어휘는 그대로 — 환각 방지 판정이 이 어휘를 본다.
    ② 컬럼명·테이블명 같은 내부 식별자를 사용자 문장에 넣지 않는다(사유는 think_trace 에 있다).
    """
    import re as _re
    from src.runtime.pipeline import refusal_reason_text

    ident = _re.compile(r"[a-z]{2,}_[a-z_]{2,}|domestic_|public_funds|ext_")
    errs = [
        "스키마에 없는 컬럼: mat_dt(→ domestic_bonds 컬럼이다. 이 테이블에는 없다)",
        "라우팅 대상(public_funds + 짝 ext_*) 밖 테이블 사용: domestic_etfs",
        "여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): itm_no",
        "코드 컬럼 리터럴 검증 실패: or_co_xtn_itt_cd",
        "LIMIT 누락",
        "아래 2가지를 **한 번에** 고친다 — (1) 스키마에 없는 컬럼: zrin_val (2) LIMIT 누락",
        None,
        "부류를 못 가리는 새 사유",
    ]
    for e in errs:
        text = refusal_reason_text(e)
        assert text.endswith("답변을 제공하지 못했습니다."), text
        assert not ident.search(text), f"내부 식별자 노출: {text}"

    # 부류를 가린 것은 종전 문구와 달라야 한다(이유가 붙어야 한다)
    assert refusal_reason_text(errs[0]) != refusal_reason_text(None)
    # 부류를 못 가리면 종전 문구 그대로
    assert refusal_reason_text(None).startswith("질의를 안전하게 실행할 수 없어")


# ── 정렬축 · 이자유형분리 (2026-09-04 서버 실측 회귀) ──────────────────────

def test_ensure_sort_axis():
    """'표면금리' 질의가 applied_yield 로 정렬돼 답변 축까지 '수익률' 로 바뀐 실측의 회귀."""
    from src.runtime.pipeline import ensure_sort_axis

    q = "A등급 이상 회사채 중 표면금리 높은 순으로 5개 알려줘"
    sql = ("SELECT pd_no, pd_nm, MAX(applied_yield) AS applied_yield, std_pd_mcls_nm, crd_grd, mat_dt "
           "FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='회사채' GROUP BY pd_no "
           "ORDER BY applied_yield DESC LIMIT 5")
    fixed, changed = ensure_sort_axis(sql, q)
    assert changed and "ORDER BY srfc_irt DESC" in fixed
    assert "srfc_irt" in fixed[:fixed.index("FROM")]          # 정렬 컬럼은 SELECT 에도 (필터컬럼표시)
    assert "applied_yield" in fixed                            # 기존 컬럼은 남긴다 — 병기
    # MAX/MIN 감싼 대표행 형도 축만 바꾼다(방향·감싸기 유지)
    f2, c2 = ensure_sort_axis(sql.replace("ORDER BY applied_yield", "ORDER BY MAX(applied_yield)"), q)
    assert c2 and "ORDER BY MAX(srfc_irt)" in f2
    # ② ORDER BY 부재 — ensure_reco_sort 가 표면금리 질의를 건너뛰는 사각을 받는다
    nosort = "SELECT pd_no, pd_nm, crd_grd FROM domestic_bonds WHERE TRIM(crd_grd)='AAA' LIMIT 5"
    f3, c3 = ensure_sort_axis(nosort, "표면금리 높은 채권 추천해줘")
    assert c3 and "ORDER BY srfc_irt DESC" in f3 and "srfc_irt" in f3[:f3.index("FROM")]
    f4, c4 = ensure_sort_axis(nosort, "표면금리 낮은 순으로 알려줘")
    assert c4 and "ORDER BY srfc_irt ASC" in f4
    # 불개입 — 수익률 질의 / 두 축 동시 언급 / 집계 / 이미 srfc_irt 정렬
    assert not ensure_sort_axis(sql, "수익률 높은 순으로 5개 알려줘")[1]
    assert not ensure_sort_axis(sql, "표면금리랑 수익률 높은 순으로 알려줘")[1]
    assert not ensure_sort_axis("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE srfc_irt > 5 LIMIT 1",
                                "표면금리 5% 넘는 채권 몇 종목이야?")[1]
    assert not ensure_sort_axis(sql.replace("applied_yield DESC", "srfc_irt DESC"), q)[1]


def test_ensure_coupon_type_split():
    """이자유형분리는 추천·랭킹에서만 — 조건검색에 주입하면 gold BND-D-028 모수가 599→497 로 깨진다."""
    from src.runtime.pipeline import ensure_coupon_type_split

    reco = ("SELECT pd_no, pd_nm, srfc_irt FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='회사채' "
            "GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 5")
    fixed, changed = ensure_coupon_type_split(reco, "표면금리 높은 순으로 5개 추천해줘")
    assert changed and "bd_intp_tcd)='이표채'" in fixed and "bd_inrt_tcd)='고정금리'" in fixed
    assert "srfc_irt > 0" in fixed
    assert fixed.index("이표채'") < fixed.index("ORDER BY")     # WHERE 안쪽에 붙는다
    # 🔴 조건검색(BND-D-028)에는 주입하지 않는다 — 정렬이 같아도 추천 신호가 없다
    lookup = ("SELECT pd_no, pd_nm, srfc_irt FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='회사채' "
              "AND srfc_irt > 5 GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 30")
    assert not ensure_coupon_type_split(lookup, "A등급 이상 회사채 중 표면금리가 5% 넘는 것을 알려줘")[1]
    # 불개입 — 질문이 이자 유형을 콕 집음 / 이미 유형 절 있음 / 수익률 정렬
    assert not ensure_coupon_type_split(reco, "할인채 중 표면금리 높은 순으로 추천해줘")[1]
    assert not ensure_coupon_type_split(reco + " ", "변동금리 채권 표면금리 순위 알려줘")[1]
    assert not ensure_coupon_type_split(fixed, "표면금리 높은 순으로 5개 추천해줘")[1]
    assert not ensure_coupon_type_split(reco.replace("srfc_irt DESC", "applied_yield DESC"),
                                        "수익률 높은 순으로 5개 추천해줘")[1]


def test_ensure_ktb_kind_scls_alone():
    """소분류 단독 국고채 필터를 확정식으로 — 2026-09-04 실측('국고채는 신용등급이 어떻게 돼?').

    std_pd_scls_nm='국고채' 단독은 290종목/371행: bd_knd='국고채권' 인데 소분류가 '물가채' 인
    물가연동국고채권 5종목이 빠진다(확정식 295종목/377행).
    """
    from src.runtime.pipeline import ensure_ktb_kind

    sql = "SELECT DISTINCT TRIM(crd_grd) FROM domestic_bonds WHERE TRIM(std_pd_scls_nm) = '국고채' LIMIT 30"
    fixed, changed = ensure_ktb_kind(sql, "국고채는 신용등급이 어떻게 돼?")
    assert changed and "TRIM(bd_knd)='국고채권'" in fixed and "std_pd_scls_nm)='국고채'" in fixed
    # 같은 절이 여러 번(종류비교 CASE) 나오면 전부 바꾼다
    twice = ("SELECT CASE WHEN TRIM(std_pd_scls_nm)='국고채' THEN '국고채' ELSE '통안채' END AS 종류 "
             "FROM domestic_bonds WHERE TRIM(std_pd_scls_nm)='국고채' OR TRIM(bd_knd)='통화안정채권' LIMIT 30")
    f2, c2 = ensure_ktb_kind(twice, "국고채랑 통안채 중 뭐가 수익률 높아?")
    assert c2 and "std_pd_scls_nm)='국고채' THEN" not in f2 and f2.count("TRIM(bd_knd)='국고채권'") == 2
    # STRIPS 탈출구 — 콕 집으면 bd_knd 단독식으로만
    f3, c3 = ensure_ktb_kind(sql, "스트립 제외한 국고채 신용등급 알려줘")
    assert c3 and "TRIM(bd_knd)='국고채권'" in f3 and "std_pd_scls_nm" not in f3
    # 불개입 — 이미 확정식 / 머리명사가 국공채
    assert not ensure_ktb_kind(fixed, "국고채는 신용등급이 어떻게 돼?")[1]
    assert not ensure_ktb_kind(sql, "국고채를 포함해서 국공채는 전부 몇 종목이야?")[1]


def test_bond_list_axis_leads_row():
    """행 앞머리 값은 정렬 축이다 — SELECT 에 수익률과 표면금리가 함께 와도 머리줄과 어긋나지 않는다."""
    from src.runtime.pipeline import _bond_list_answer

    sql = ("SELECT pd_no, pd_nm, srfc_irt, applied_yield, crd_grd FROM domestic_bonds "
           "WHERE TRIM(std_pd_mcls_nm)='회사채' GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 2")
    rows = ("pd_no | pd_nm | srfc_irt | applied_yield | crd_grd\n"
            "KR1 | 우리금융캐피탈458 | 7.5 | 4.1 | AA-\n"
            "KR2 | 엠캐피탈 355 | 7.5 | 4.2 | A0")
    out = _bond_list_answer(sql, rows, 2, "표면금리 높은 순으로 2개 추천해줘")
    assert out and "표면금리 높은 순" in out
    assert out.index("표면금리 7.5%") < out.index("수익률 4.1%")   # 정렬 축이 앞


def test_bond_list_axis_direction():
    """감싸지 않은 ORDER BY col DESC 의 방향 — '낮은 순' 으로 뒤집혀 나가던 자리 (2026-09-04)."""
    from src.runtime.pipeline import _bond_list_answer

    base = ("SELECT pd_no, pd_nm, srfc_irt FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='회사채' "
            "GROUP BY pd_no ORDER BY srfc_irt {} LIMIT 1")
    rows = "pd_no | pd_nm | srfc_irt\nKR1 | 우리금융캐피탈458 | 7.5"
    q = "표면금리 순으로 알려줘"
    assert "표면금리 높은 순" in _bond_list_answer(base.format("DESC"), rows, 1, q)
    assert "표면금리 낮은 순" in _bond_list_answer(base.format("ASC"), rows, 1, q)
    assert "표면금리 낮은 순" in _bond_list_answer(base.format(""), rows, 1, q)      # 무표기 = ASC
    assert "수익률 높은 순" in _bond_list_answer(
        base.format("DESC").replace("srfc_irt", "applied_yield"),
        rows.replace("srfc_irt", "applied_yield"), 1, "수익률 순으로 알려줘")


def test_bond_list_warning_basis_is_yield():
    """주의 문구 기준은 수익률 — 표면금리 7.5%(수익률 4.08%)에 원금 위험 문구를 붙이지 않는다 (2026-09-04)."""
    from src.runtime.pipeline import _bond_list_answer

    sql = ("SELECT pd_no, pd_nm, srfc_irt, applied_yield FROM domestic_bonds "
           "WHERE TRIM(std_pd_mcls_nm)='회사채' GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 1")
    q = "표면금리 높은 순으로 알려줘"
    low = "pd_no | pd_nm | srfc_irt | applied_yield\nKR1 | 우리금융캐피탈458 | 7.5 | 4.083"
    hi = "pd_no | pd_nm | srfc_irt | applied_yield\nKR1 | 엠캐피탈358-3 | 7.164 | 6.758"
    assert "원금을 돌려받지 못할" not in _bond_list_answer(sql, low, 1, q)
    assert "원금을 돌려받지 못할" in _bond_list_answer(sql, hi, 1, q)


# ── 확장성 — 선언이 원천인가 (코드 상수 제거 회귀) ─────────────────────────

def test_grade_scale_comes_from_declarations():
    """등급 서열은 코드 상수가 아니라 '표준표 rank ∩ 값 사전' 이다 (2026-09-04).

    표준 체계(무엇이 무엇보다 위인가)는 코드북, 실재 여부(이 적재분에 있는가)는 값 사전이 답한다.
    새 데이터에 CCC·D 가 들어오면 값 사전만 갱신되고 서열은 코드 수정 없이 따라온다.
    """
    import yaml as _yaml
    from src.runtime.loader import PROJECT_ROOT, grade_scale
    from src.runtime.pipeline import _grade_scale, expand_grade_comparison

    scale = list(grade_scale())
    assert _grade_scale() == scale

    # ① 순서는 코드북 rank 그대로
    import csv as _csv
    with open(PROJECT_ROOT / "data/external/lookups/credit_grade_scale.csv", encoding="utf-8") as f:
        rows = [r for r in _csv.DictReader(line for line in f if not line.startswith("#"))]
    std = [r["grade_db"].strip() for r in sorted(rows, key=lambda r: int(r["rank"]))]
    assert [g for g in std if g in scale] == scale, "서열 순서가 표준표 rank 와 다르다"

    # ② 실재 여부는 값 사전이 판정 — 데이터에 없는 표준등급(CCC·D)은 IN 목록에 넣지 않는다
    doc = _yaml.safe_load((PROJECT_ROOT / "ontology/enums/domestic_bonds.yaml").read_text(encoding="utf-8"))
    observed = set((doc["columns"]["crd_grd"]["value_semantics"] or {}))
    assert set(scale) == observed
    assert "D" not in scale and "CCC" not in scale

    # ③ 그런데 KG 에는 표준 20등급이 다 있다 — 새 데이터가 들어오면 알아본다
    cg = _yaml.safe_load((PROJECT_ROOT / "ontology/shared/credit_grade.yaml").read_text(encoding="utf-8"))
    ranks = {n["rank"] for n in cg["nodes"].values() if isinstance(n, dict) and "rank" in n}
    assert ranks == set(range(1, 21)), f"표준등급 20 전체가 노드여야 한다: {sorted(ranks)}"

    # ④ 서열 확장이 이 목록을 쓴다
    sql = "SELECT pd_nm FROM domestic_bonds WHERE crd_grd = 'A-' LIMIT 5"
    fixed, changed = expand_grade_comparison(sql, "A등급 이상 채권 알려줘")
    assert changed and all(f"'{g}'" in fixed for g in scale[:scale.index("A-") + 1])


def test_scope_declaration_drives_gate_constant(monkeypatch):
    """'외화채는 없다' 가 아니라 '지금 스코프가 원화뿐' 이다 (2026-09-04).

    1차 데이터엔 USD 19·JPY 1·EUR 1 이 있었다 — 한 번 변한 축을 상수로 못박으면 데이터가 바뀔 때
    자신 있게 오답한다. 스코프에 통화가 하나면 게이트 상수로 살고, 둘 이상이면 로더가 스스로 뺀다.
    """
    from src.runtime import loader

    assert loader.scope_values("domestic_bonds", "currency") == ["KRW"]
    ctx = loader.load_context()
    curr = [g for g in ctx.gate_constants.get("domestic_bonds", []) if g["column"] == "curr_cd"]
    assert curr and curr[0]["value"] == "KRW" and curr[0].get("scope_key") == "currency"
    assert "수록 범위" in curr[0]["answer"]          # '없습니다' 단정이 아니라 범위 표기

    # 스코프가 넓어지면(외화채 적재) 게이트는 저절로 꺼진다 — 규칙·코드는 그대로다
    monkeypatch.setattr(loader, "scope_values", lambda t, k: ["KRW", "USD"])
    loader.load_context.cache_clear()
    try:
        widened = loader.load_context()
        assert not [g for g in widened.gate_constants.get("domestic_bonds", []) if g["column"] == "curr_cd"]
    finally:
        loader.load_context.cache_clear()


def test_dataset_dates_come_from_declaration():
    """기준일 세 개(스냅샷·as-of·질문 시점)의 원천은 shared/dataset.yaml — 코드 상수가 아니다."""
    from src.runtime import gate
    from src.runtime.loader import dataset_scope

    dates = dataset_scope()["dates"]
    assert gate.DATA_CUTOFF == dates["decision"] == gate.BUYABLE_CUTOFF
    assert gate.SNAPSHOT_DATE == dates["snapshot"]
    assert dates["as_of"] != dates["decision"]        # as-of(8/22 토)와 판정일(8/24 월)은 다르다


def test_kind_filters_come_from_declaration():
    """종류 확정식의 원천은 enums `kind_filters` 다 — 코드 상수 표가 아니다 (2026-09-04).

    새 종류(전단채·CP·해외채)를 붙이는 일이 코드 수정이 아니라 선언 한 줄이어야 한다.
    """
    import yaml as _yaml
    from src.runtime.loader import PROJECT_ROOT, kind_filter_decl
    from src.runtime.pipeline import _KTB_FILTER, _P, _question_kind_filters

    decl = _yaml.safe_load((PROJECT_ROOT / "ontology/enums/domestic_bonds.yaml").read_text(encoding="utf-8"))["kind_filters"]
    toks, paras = kind_filter_decl("domestic_bonds", _P)
    assert len(toks) == len(decl["tokens"]) and len(paras) >= len(decl["paraphrases"])

    # 확정식이 선언 그대로 쓰인다 — 국고채는 STRIPS 포함형
    ktb = next(t["sql"] for t in decl["tokens"] if t["token"] == "국고채")
    assert _KTB_FILTER == ktb and "std_pd_scls_nm" in ktb
    assert _question_kind_filters("국고채 몇 종목이야?") == {ktb}
    assert _question_kind_filters("국채는 몇 종목이야?") == {ktb}      # 별칭 정규식도 선언에서
    assert _question_kind_filters("미국채 금리 알려줘") == set()        # 합성어 불개입
    assert _question_kind_filters("은행이 발행한 채권") == {"TRIM(bd_knd) IN ('일반은행채','특수은행채')"}


def test_safe_grade_presence_is_measured_not_listed():
    """'그 종류에 6등급이 있나' 는 열거가 아니라 DB 조회다 (2026-09-04 — 종전 _SAFE16_KINDS 8종 하드코딩)."""
    from src.runtime.pipeline import _kind_has_safe_grade, _kinds_without_safe_grade, ensure_top_safety

    assert _kind_has_safe_grade("TRIM(std_pd_mcls_nm)='국공채'")
    assert not _kind_has_safe_grade("TRIM(std_pd_mcls_nm)='회사채'")
    assert _kinds_without_safe_grade("가장 안전한 회사채 3개 추천해줘")     # 6등급 0 → 완화 대상
    assert not _kinds_without_safe_grade("가장 안전한 채권 3개 추천해줘")   # 종류 지목 없음

    # 회사채는 '16' 단독이 0행이라 IN ('15','16') 폴백, 종류 지목이 없으면 '16' 단독 유지
    s16 = "SELECT pd_no FROM domestic_bonds WHERE pd_risk_gcd = '16' AND TRIM(std_pd_mcls_nm)='회사채' ORDER BY applied_yield DESC LIMIT 3"
    fixed, changed = ensure_top_safety(s16, "가장 안전한 회사채 3개 추천해줘")
    assert changed and "IN ('15','16')" in fixed
    plain = "SELECT pd_no FROM domestic_bonds WHERE curr_cd='KRW' ORDER BY applied_yield DESC LIMIT 3"
    f2, c2 = ensure_top_safety(plain, "가장 안전한 채권 3개 추천해줘")
    assert c2 and "pd_risk_gcd = '16'" in f2


def test_grade_span_follows_the_standard_table():
    """'유효 등급은 AAA~D' 문구도 표준표에서 만든다 — 표가 늘면 문구가 따라온다 (2026-09-04)."""
    from src.runtime.gate import _grade_span
    from src.runtime.loader import load_context

    ctx = load_context()
    assert _grade_span(ctx) == "AAA~D"          # D 등급 노드 추가 후
    r = answer_question("T-grade-span", "신용등급 AAAA인 채권 알려줘", ctx=ctx)
    assert "AAA~D" in r.answer and "존재하지 않는" in r.answer
    # 표준표에 있으나 이 적재분에 없는 등급은 '없는 등급' 이 아니라 '해당 채권 없음'
    for tok in ("D", "CCC"):
        a = answer_question("T-nodata", f"신용등급 {tok}인 채권 알려줘", ctx=ctx).answer
        assert "체계에 있으나" in a and "없습니다" in a


# ── 동률 2차 정렬 · 대분류 값 정리 · owner 힌트 (2026-09-04 재배포 후 실측 #61·#62 회귀) ──

def test_ensure_tie_break():
    """표면금리 7.5% 동률의 1·2위가 실측마다 뒤바뀐 #62 의 회귀 — 2차 키가 없으면 등수는 DB 가 준 우연이다."""
    from src.runtime.pipeline import ensure_tie_break

    q = "표면금리가 높은 순으로 A등급 이상 회사채 5종목 알려줘"
    grouped = ("SELECT pd_no, pd_nm, MAX(srfc_irt) AS srfc_irt, crd_grd, mat_dt FROM domestic_bonds "
               "WHERE TRIM(std_pd_mcls_nm)='회사채' GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 5")
    fixed, changed = ensure_tie_break(grouped, q)
    assert changed and fixed.index("ORDER BY") < fixed.index("LIMIT")
    assert "pd_no ASC LIMIT" in fixed                         # 3차 키는 완전 결정성
    assert "MIN(CASE TRIM(crd_grd)" in fixed and "MIN(mat_dt) ASC" in fixed   # GROUP BY 면 집계로 감싼다
    assert fixed.index("'AAA' THEN 1") < fixed.index("ELSE")  # 서열은 우량이 앞(선언에서 온다)
    # GROUP BY 가 없으면 bare 컬럼으로
    flat = ("SELECT pd_no, pd_nm, srfc_irt, crd_grd, mat_dt FROM domestic_bonds "
            "WHERE srfc_irt > 5 ORDER BY srfc_irt DESC LIMIT 5")
    f2, c2 = ensure_tie_break(flat, q)
    assert c2 and "MIN(" not in f2 and "mat_dt ASC" in f2 and f2.rstrip().endswith("LIMIT 5")
    # 만기 정렬이면 만기를 2차 키로 다시 넣지 않는다
    f3, c3 = ensure_tie_break(flat.replace("ORDER BY srfc_irt", "ORDER BY mat_dt"), "만기 짧은 순 5개")
    assert c3 and "ORDER BY mat_dt DESC" in f3 and "mat_dt ASC" not in f3   # 만기를 2차 키로 겹쳐 넣지 않는다
    # 불개입 — 2차 키가 이미 있음(멱등) · 랭킹 축이 아님 · ORDER BY 없음 · JOIN
    assert not ensure_tie_break(f2, q)[1]
    assert not ensure_tie_break(flat.replace("ORDER BY srfc_irt DESC", "ORDER BY pd_nm ASC"), q)[1]
    assert not ensure_tie_break("SELECT COUNT(*) FROM domestic_bonds LIMIT 1", q)[1]
    assert not ensure_tie_break(flat.replace("FROM domestic_bonds", "FROM domestic_bonds JOIN x ON 1=1"), q)[1]


def test_coupon_split_ignores_select_columns():
    """#62 — SELECT 표시 컬럼의 bd_intp_tcd 를 '이미 유형 절' 로 읽어 가드가 자기를 껐다. 판정은 WHERE 범위."""
    from src.runtime.pipeline import ensure_coupon_type_split

    q = "표면금리가 높은 순으로 A등급 이상 회사채 5종목 알려줘"
    shown = ("SELECT pd_no, pd_nm, bd_intp_tcd, MAX(srfc_irt) AS srfc_irt, crd_grd FROM domestic_bonds "
             "WHERE TRIM(std_pd_mcls_nm)='회사채' GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 5")
    fixed, changed = ensure_coupon_type_split(shown, q)
    assert changed and "bd_inrt_tcd)='고정금리'" in fixed
    # WHERE 에 진짜 유형 필터가 있으면 종전대로 불개입
    filtered = shown.replace("WHERE TRIM(std_pd_mcls_nm)='회사채'",
                             "WHERE TRIM(std_pd_mcls_nm)='회사채' AND TRIM(bd_intp_tcd)='이표채'")
    assert not ensure_coupon_type_split(filtered, q)[1]


def test_normalize_mcls_values():
    """#61 — IN ('국공채','국고채권') 이 값 검사에 걸려 재생성도 같은 문장 → 정답 1,775 를 아는 질문이 오거절."""
    from src.runtime.pipeline import normalize_mcls_values

    q = "국고채 포함해서 국공채는 총 몇 종목이야?"
    sql = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm) IN ('국공채', '국고채권') LIMIT 30"
    fixed, changed = normalize_mcls_values(sql, q)
    assert changed and "'국고채권'" not in fixed and "IN ('국공채')" in fixed
    assert not normalize_mcls_values(fixed, q)[1]              # 멱등
    # 🔴 어디에도 없는 값은 그대로 기각돼야 한다 — 여기서 지우면 오답이 정답처럼 나간다
    assert not normalize_mcls_values(
        "SELECT * FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm) IN ('국공채','없는분류') LIMIT 30", q)[1]
    # 대분류 값이 하나도 안 남으면 손대지 않는다
    assert not normalize_mcls_values(
        "SELECT * FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm) IN ('국고채권','통안채') LIMIT 30", q)[1]


def test_owner_hint_picks_most_rows():
    """#61 — '국고채권' 은 bd_knd 356행이 주인인데 오염 1행짜리 pd_pbcm 이 지목돼 재생성이 헛돌았다."""
    from src.runtime.guard import _literal_row_counts

    counts = _literal_row_counts("domestic_bonds", ["pd_pbcm", "bd_knd"], "국고채권")
    assert counts["bd_knd"] > counts["pd_pbcm"]               # 356 vs 1
    assert max(counts, key=counts.get) == "bd_knd"


# ── KG 노드 작동 점검 (2026-09-04 전수) ────────────────────────────────────

def test_bond_node_coverage_and_grounding():
    """채권이 닿는 노드가 실제로 접지되는가 — 구조(커버리지)와 런타임(Ground) 양쪽."""
    from src.runtime.loader import connect_readonly, load_context
    from src.runtime.pipeline import _ground, expand_node

    ctx = load_context()
    with connect_readonly() as con:
        # ① 값 커버리지 — 등급·위험등급은 100%, 통화는 오염값 1건만 제외, 발행사는 종류 오염 1건만 제외
        for col, expect_miss in (("crd_grd", 0), ("pd_risk_gcd", 0), ("curr_cd", 1), ("pd_pbcm", 1)):
            vals = {(r[0] or "").strip() for r in con.execute(f"SELECT DISTINCT {col} FROM domestic_bonds")} - {""}
            mapped = {(r[0] or "").strip() for r in con.execute(
                "SELECT raw_value FROM kg_alias WHERE table_name='domestic_bonds' AND column_name=?", (col,))}
            assert len(vals - mapped) == expect_miss, f"{col} 미연결 {sorted(vals - mapped)[:3]}"

    # ② 밴드 closure — 자신 + 후손 10
    assert len(expand_node(ctx, "CG_Investment")) == 11
    assert len(expand_node(ctx, "CG_Speculative")) == 11

    # ③ 접지 — 등급·밴드·발행사(정식명·통칭·자동 통칭)·통화
    def ids(q, tables=("domestic_bonds",)):
        hits, _ = _ground(q, ctx, list(tables))
        return [getattr(h, "node_id", "?") for h in hits]

    assert "CG_AAm" in ids("AA- 이상 원화채권 알려줘")
    assert "CG_Investment" in ids("투자등급 채권 알려줘")
    assert "CG_Speculative" in ids("투기등급 채권 알려줘")
    assert "Curr_KRW" in ids("원화 채권 몇 종목이야?")
    kepco = ids("한국전력공사 채권 알려줘")
    for term in ("한전 채권 알려줘", "한국전력 채권 알려줘"):        # 손으로 적은 통칭
        assert ids(term) == kepco, term
    for term, full in (("산업은행", "한국산업은행"), ("도로공사", "한국도로공사"),
                       ("수출입은행", "한국수출입은행"), ("토지주택공사", "한국토지주택공사")):
        assert ids(f"{term} 채권 알려줘") == ids(f"{full} 채권 알려줘") != [], term   # 선언 규칙이 만든 통칭

    # ④ 회귀 — '한국전력' 은 ETF 교차질의에서 여전히 종목 노드다 (2026-08-26 오매칭 방지)
    assert ids("한국전력을 담은 국내 ETF 알려줘", ("domestic_etfs", "ext_etf_holdings")) == ["Sec_kr_015760"]
