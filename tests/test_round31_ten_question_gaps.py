# -*- coding: utf-8 -*-
"""라운드 31 — 09-06 밤 서버 10문항 실측(오답기록 #87~#96) 결함 F1~F8 회귀.

발동 문형과 불개입 문형을 짝으로 둔다 — 강제가 새 오답을 만들지 않는지가 채점 대상이다.
  F1 값-컬럼 자동 교정 · F2 절대 연도 발행 창 · F3 비교 경계 어휘 · F4 종류 좁힘 복원 · F5 평균 조립 ·
  F6 국공채 등급 미부여 표기 · F7 판매행·계열 고지 · F8 위험요인 잔존 표기
"""
from types import SimpleNamespace

import pytest

from src.runtime import loader
from src.runtime import pipeline as pl

Q8 = "2024년에 발행된 회사채 평균 표면금리 얼마야?"
Q6 = "A등급 이상 회사채 중 표면금리 5% 넘는 채권 몇 종목이야?"
Q5 = "최근 6개월 안에 발행된 회사채 중 신용등급 AA 이상 표면금리 높은 순 5개 알려줘"


@pytest.fixture(scope="module")
def con():
    c = loader.connect_readonly()
    yield c
    c.close()


# ── F2 절대 연도 발행 창 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("sql", [
    "SELECT AVG(srfc_irt) FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm) = '회사채' AND isu_dt > 20240101 AND isu_dt <= 20241231 LIMIT 30",
    # BONDPOP 이 감싼 괄호 안
    "SELECT AVG(srfc_irt) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (TRIM(std_pd_mcls_nm) = '회사채' AND isu_dt > 20240101 AND isu_dt <= 20241231) LIMIT 30 /*M:BONDPOP*/",
    # #94 재생성이 발행일을 만기로 갈아끼운 형 — 창이 발행 축으로 돌아온다
    "SELECT AVG(srfc_irt) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND mat_dt <= 20241231 AND std_pd_mcls_nm = '회사채' LIMIT 30",
])
def test_issue_year_window(sql):
    out, note = pl.enforce_relative_window(sql, Q8)
    assert note and "isu_dt BETWEEN 20240101 AND 20241231" in out
    assert "mat_dt <= 20241231" not in out
    assert "mat_dt >= 20260824" in out or "mat_dt" not in sql          # 구매가능 하한은 남긴다


@pytest.mark.parametrize("q", [
    "2024년에 발행된 회사채 중 2027년 만기 채권",     # 연도 둘 + 만기 낱말
    "2024년 만기 채권 몇 종목",                        # 발행 낱말 없음(만기 축은 다른 가드)
])
def test_issue_year_window_untouched_without_issuance(q):
    sql = "SELECT pd_nm FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm) = '회사채' LIMIT 30"
    out, note = pl.enforce_relative_window(sql, q)
    assert "isu_dt BETWEEN 2024" not in out


def test_issuer_plus_year_gets_issue_window():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE pd_pbcm LIKE '%삼성전자%' LIMIT 30"
    out, note = pl.enforce_relative_window(sql, "삼성전자가 2024년에 발행한 채권 있어?")
    assert "isu_dt BETWEEN 20240101 AND 20241231" in out and "pd_pbcm LIKE" in out


# ── F3 비교 경계 어휘 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("sql, q, want", [
    ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (TRIM(std_pd_mcls_nm) = '회사채' AND srfc_irt >= 5) LIMIT 30 /*M:BONDPOP*/", Q6, "srfc_irt > 5"),
    ("SELECT pd_nm FROM domestic_bonds WHERE applied_yield > 7 LIMIT 5", "수익률 7% 이상 채권", "applied_yield >= 7"),
    ("SELECT pd_nm FROM domestic_bonds WHERE applied_yield > 7 LIMIT 5", "수익률 7%를 초과하는 채권", "applied_yield > 7"),
    ("SELECT pd_nm FROM domestic_bonds WHERE dur <= 3 LIMIT 5", "듀레이션 3년 미만 채권", "dur < 3"),
    ("SELECT pd_nm FROM domestic_bonds WHERE dur < 3 LIMIT 5", "듀레이션 3년 이하 채권", "dur <= 3"),
])
def test_threshold_operator_follows_question(sql, q, want):
    out, fixed = pl.align_threshold_operator(sql, q)
    assert want in out
    assert bool(fixed) == (want not in sql)


@pytest.mark.parametrize("sql, q", [
    ("SELECT pd_nm FROM domestic_bonds WHERE srfc_irt >= 5 LIMIT 5", "표면금리 5% 넘지 않는 채권"),          # 부정
    ("SELECT pd_nm FROM domestic_bonds WHERE applied_yield < 7 LIMIT 5", "수익률 7% 이상 채권"),               # 방향 뒤집힘
    ("SELECT pd_nm FROM domestic_bonds WHERE applied_yield > 5 AND srfc_irt > 5 LIMIT 5", "수익률 5% 넘고 표면금리 5% 이상"),  # 같은 숫자 둘
    ("SELECT pd_nm FROM domestic_bonds WHERE mat_dt >= 20270101 LIMIT 5", "2027년 이상 만기"),               # 날짜 컬럼
    ("SELECT pd_nm FROM domestic_bonds WHERE applied_yield > 5 LIMIT 5", "수익률 높은 채권 5개"),               # 숫자가 임계가 아님
    ("SELECT pd_abrv_nm FROM domestic_etfs WHERE du_er_1y >= 5 LIMIT 5", "1년 수익률 5% 넘는 ETF"),          # 채권 아님
])
def test_threshold_operator_untouched(sql, q):
    out, fixed = pl.align_threshold_operator(sql, q)
    assert out == sql and not fixed


def test_threshold_q6_value(con):
    sql = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (TRIM(std_pd_mcls_nm) = '회사채' AND TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-','A+','A0','A-') AND srfc_irt >= 5) LIMIT 30"
    out, _ = pl.align_threshold_operator(sql, Q6)
    assert con.execute(out).fetchone()[0] == 596 and con.execute(sql).fetchone()[0] == 615


# ── F4 종류 좁힘 복원 ──────────────────────────────────────────────────────────
def test_kind_breadth_restored():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE curr_cd = 'KRW' AND (TRIM(bd_knd) = '일반회사채' AND TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-')) LIMIT 5"
    out, note = pl.restore_kind_breadth(sql, Q5)
    assert note and "TRIM(std_pd_mcls_nm)='회사채'" in out and "일반회사채" not in out


def test_kind_breadth_single_in_list():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE bd_knd IN ('일반회사채') LIMIT 5"
    out, note = pl.restore_kind_breadth(sql, "회사채 수익률 높은 순")
    assert note and "std_pd_mcls_nm" in out


@pytest.mark.parametrize("sql, q", [
    ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '일반회사채' LIMIT 5", "일반회사채 수익률 높은 순"),        # 직접 말함
    ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '일반회사채' LIMIT 5", "회사채 중 금융채 빼고 수익률 높은 순"),  # 배제 의도
    ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) IN ('일반회사채','할부금융채') LIMIT 5", "회사채 수익률 높은 순"),  # IN 둘
    ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm) = '회사채' LIMIT 5", "회사채 수익률 높은 순"),        # 이미 대분류
    ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '국고채권' LIMIT 5", "국공채 중 수익률 높은 순"),           # 낱말 미포함
    ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '일반회사채' LIMIT 5", "국공채와 회사채 비교"),               # 대분류 둘
])
def test_kind_breadth_untouched(sql, q):
    out, note = pl.restore_kind_breadth(sql, q)
    assert out == sql and note is None


def test_kind_breadth_q5_top1(con):
    sql = ("SELECT TRIM(pd_nm), MAX(srfc_irt) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (TRIM(bd_knd) = '일반회사채' "
           "AND TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-') AND isu_dt BETWEEN 20260224 AND 20260824) AND applied_yield > 0 AND pd_risk_gcd <> '11' "
           "AND bd_ofr_tcd <> '사모' GROUP BY pd_no ORDER BY MAX(srfc_irt) DESC LIMIT 1")
    out, _ = pl.restore_kind_breadth(sql, Q5)
    assert con.execute(out).fetchone()[0].startswith("하나은행49-05단20갑-26")
    assert con.execute(sql).fetchone()[0].startswith("한국남동발전74-2")


# ── F1 값-컬럼 자동 교정 ─────────────────────────────────────────────────────────
def _viol(column, literal, owner, counts=()):
    return SimpleNamespace(table="domestic_bonds", column=column, literal=literal, owner=owner, owner_counts=counts)


def test_fix_value_column_equals_and_trim():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '회사채' AND bd_intp_tcd = '고정금리' LIMIT 5"
    out, fixed = pl.fix_value_column(sql, [_viol("bd_knd", "회사채", "std_pd_mcls_nm"), _viol("bd_intp_tcd", "고정금리", "bd_inrt_tcd")])
    assert "TRIM(std_pd_mcls_nm) = '회사채'" in out and "TRIM(bd_inrt_tcd) = '고정금리'" in out and len(fixed) == 2


def test_fix_value_column_single_in():
    out, fixed = pl.fix_value_column("SELECT pd_nm FROM domestic_bonds WHERE bd_knd IN ('회사채') LIMIT 5", [_viol("bd_knd", "회사채", "std_pd_mcls_nm")])
    assert "TRIM(std_pd_mcls_nm) IN ('회사채')" in out and fixed


@pytest.mark.parametrize("v", [
    _viol("pd_pbcm", "삼성전자", ""),                                             # 주인 없음 — 진짜 없는 값
    _viol("pd_pbcm", "국고채권", "bd_knd", (("bd_knd", 356), ("pd_pbcm", 300))),  # 주인이 압도적이지 않음
])
def test_fix_value_column_untouched(v):
    sql = f"SELECT pd_nm FROM domestic_bonds WHERE TRIM({v.column}) = '{v.literal}' LIMIT 5"
    out, fixed = pl.fix_value_column(sql, [v])
    assert out == sql and not fixed


def test_fix_value_column_dominant_owner():
    v = _viol("pd_pbcm", "국고채권", "bd_knd", (("bd_knd", 356), ("pd_pbcm", 1)))
    out, fixed = pl.fix_value_column("SELECT pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm) = '국고채권' LIMIT 5", [v])
    assert "TRIM(bd_knd) = '국고채권'" in out and fixed


def test_fix_value_column_then_values_pass(con):
    ctx = loader.load_context()
    from src.runtime import guard
    sql = "SELECT AVG(srfc_irt) FROM domestic_bonds WHERE TRIM(bd_knd) = '회사채' AND isu_dt BETWEEN 20240101 AND 20241231 LIMIT 30"
    viol = guard.check_values(sql, ctx)
    assert viol and viol[0].owner == "std_pd_mcls_nm"
    out, fixed = pl.fix_value_column(sql, viol)
    assert fixed and guard.check_values(out, ctx) == []


# ── F5 평균 조립 ───────────────────────────────────────────────────────────────
def test_avg_answer_with_population(con):
    sql = "SELECT AVG(srfc_irt) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND TRIM(std_pd_mcls_nm) = '회사채' AND isu_dt BETWEEN 20240101 AND 20241231 AND isu_dt > 0 LIMIT 30"
    val = con.execute(sql).fetchone()[0]
    ans = pl._bond_avg_answer(sql, f"AVG(srfc_irt)\n{val}", 1, Q8)
    assert ans and "종목" in ans and "행" in ans and "평균 표면금리" in ans and f"{val:.2f}" in ans
    assert "발행일 2024-01-01~2024-12-31" in ans


def test_avg_answer_null_is_not_refusal():
    ans = pl._bond_avg_answer("SELECT AVG(srfc_irt) FROM domestic_bonds WHERE mat_dt <= 20241231 AND mat_dt >= 20260824 LIMIT 30", "AVG(srfc_irt)\n", 1, Q8)
    assert ans and "해당하는 채권이 없어" in ans and "미수록" not in ans


@pytest.mark.parametrize("sql, rows, n", [
    ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds LIMIT 30", "COUNT(DISTINCT pd_no)\n35", 1),        # COUNT 는 다른 조립기
    ("SELECT AVG(srfc_irt), COUNT(*) FROM domestic_bonds LIMIT 30", "AVG(srfc_irt) | COUNT(*)\n3.8 | 10", 1),   # 항 둘
    ("SELECT TRIM(bd_knd), AVG(srfc_irt) FROM domestic_bonds GROUP BY 1 LIMIT 30", "bd_knd | AVG\na | 1\nb | 2", 2),  # 분포
])
def test_avg_answer_untouched(sql, rows, n):
    assert pl._bond_avg_answer(sql, rows, n, "표면금리 평균") is None


# ── F6 국공채 등급 미부여 · F7 판매행 고지 ───────────────────────────────────────
def test_list_answer_gov_bond_grade_wording(con):
    pd_no, nm = con.execute("SELECT pd_no, TRIM(pd_nm) FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='국공채' AND after_tax_yield IS NOT NULL ORDER BY after_tax_yield DESC LIMIT 1").fetchone()
    cols = ["pd_no", "pd_nm", "after_tax_yield", "crd_grd"]
    rows = " | ".join(cols) + f"\n{pd_no} | {nm} | 5.7027 | "
    sql = "SELECT pd_no, TRIM(pd_nm), MAX(after_tax_yield) AS after_tax_yield, TRIM(crd_grd) AS crd_grd FROM domestic_bonds WHERE after_tax_yield > 0 GROUP BY pd_no ORDER BY MAX(after_tax_yield) DESC LIMIT 5"
    ans = pl._bond_list_answer(sql, rows, 1, "지금 살 수 있는 채권 중 세후수익 높은 순 5개")
    assert "신용등급 미부여(국공채)" in ans and "신용등급 미수록" not in ans
    assert pl.SALES_LOT_NOTE in ans


def test_list_answer_corporate_missing_grade_stays_generic():
    cols = ["pd_no", "pd_nm", "applied_yield", "crd_grd"]
    rows = " | ".join(cols) + "\nKRX000 | 어떤회사채1 | 4.1 | "
    sql = "SELECT pd_no, TRIM(pd_nm), applied_yield, TRIM(crd_grd) AS crd_grd FROM domestic_bonds WHERE applied_yield > 0 ORDER BY applied_yield DESC LIMIT 5"
    ans = pl._bond_list_answer(sql, rows, 1, "수익률 높은 채권")
    assert "신용등급 미수록" in ans and pl.SALES_LOT_NOTE not in ans


def test_affiliate_note_only_with_affiliate_words():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE pd_pbcm LIKE '%에코프로%' LIMIT 5"
    assert any("발행사명에 '에코프로'" in n for n in pl.bond_answer_notes(sql, "", "에코프로의 자회사가 발행한 채권 중 표면금리 가장 높은 종목"))
    assert not any("자회사" in n for n in pl.bond_answer_notes(sql, "", "에코프로가 발행한 채권"))
    assert not any("자회사" in n for n in pl.bond_answer_notes("SELECT pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm) = '(주)에코프로' LIMIT 5", "", "에코프로 자회사 채권"))


# ── F8 위험요인 잔존 표기 ─────────────────────────────────────────────────────
def test_risk_profile_remaining_days_no_double_unit():
    spec = pl._risk_profile_spec()
    r = {"pd_risk_nm": "매우높은위험(1등급)", "crd_grd": "BBB+", "dur": "1.548", "remaining_days": "10296일(약 28.2년)", "구조": "영구채", "bd_ofr_tcd": "사모"}
    prof = pl._bond_risk_profile(r, list(r.keys()), spec)
    assert "10296일(약 28.2년)" in prof and "년)일" not in prof
    r2 = dict(r, remaining_days="245")
    assert "잔존 245일" in pl._bond_risk_profile(r2, list(r2.keys()), spec)
