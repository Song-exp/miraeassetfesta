# -*- coding: utf-8 -*-
"""라운드 34 — 서버 QA r1 심사관 §③(가) 🟡 BO(조립기 고지·표기 묶음) 회귀.

입력은 서버 실측 SQL·결과 행 원문(eval/probe_bonds_2026-09-06_r1.json)이고, 조립기·가드를 직접 호출해
결과 문자열과 DB 값을 검사한다. 항목마다 발동/불개입 짝 + 형제 케이스(어휘 변형·다른 컬럼/값).
"""
import pytest

from src.runtime import loader
from src.runtime import pipeline as pl


@pytest.fixture(scope="module")
def con():
    c = loader.connect_readonly()
    yield c
    c.close()


def _rows(header: list, *body: list) -> str:
    return "\n".join([" | ".join(header)] + [" | ".join(str(v) for v in r) for r in body])


# ══════════════════════════════════════════════════════════════════════════════
# BO(d) — 날짜 컬럼은 사람 표기로 (D-052 '발행일 20260626')
#   일반 규칙: 목록 조립기의 일반 컬럼 루프에서 `*_dt` 는 mat_dt 와 같은 규칙(_fmt_ymd)으로 적는다.
# ══════════════════════════════════════════════════════════════════════════════
D052_SQL = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, MAX(srfc_irt) AS srfc_irt , mat_dt, isu_dt, TRIM(crd_grd) AS crd_grd "
            "FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (TRIM(bd_knd)='회사채' "
            "AND isu_dt BETWEEN 20260224 AND 20260824 AND isu_dt > 0) GROUP BY pd_no "
            "ORDER BY MAX(srfc_irt) DESC, MIN(mat_dt) ASC, pd_no ASC LIMIT 5 /*M:BONDPOP*/")


def test_BO_d_isu_dt_formatted():
    rows = _rows(["pd_no", "pd_nm", "srfc_irt", "mat_dt", "isu_dt", "crd_grd"],
                 ["KR6000", "중진공2026제1차스케일업유동화전문3-1(사)(콜/후)", "20.0", "20311226", "20260626", "C0"])
    out = pl._bond_list_answer(D052_SQL, rows, 1, "최근 6개월 안에 새로 발행된 회사채 중에 표면금리 높은 5개 알려줘")
    assert "발행일 2026-06-26" in out and "발행일 20260626" not in out
    assert "만기 2031-12-26" in out                                   # 종전 표기 유지


def test_BO_d_isu_dt_real_literal_formatted():
    """형제 — REAL 적재(20260626.0)도 같은 표기. `_cell` 은 정수까지만 되돌린다."""
    rows = _rows(["pd_nm", "isu_dt"], ["감마블레오제일차3(사모/콜/강제)", "20260529.0"])
    out = pl._bond_list_answer("SELECT pd_nm, isu_dt FROM domestic_bonds WHERE isu_dt > 0 LIMIT 5", rows, 1, "발행일 알려줘")
    assert "발행일 2026-05-29" in out


def test_BO_d_non_date_column_untouched():
    """불개입 — 날짜가 아닌 컬럼(종류·듀레이션)은 원값 그대로."""
    rows = _rows(["pd_nm", "bd_knd", "dur"], ["한국전력공사 843", "일반특수법인채", "1.6579"])
    out = pl._bond_list_answer("SELECT pd_nm, bd_knd, dur FROM domestic_bonds WHERE curr_cd='KRW' LIMIT 5", rows, 1, "한국전력 채권 알려줘")
    assert "종류 일반특수법인채" in out and "듀레이션 1.6579" in out


# ══════════════════════════════════════════════════════════════════════════════
# BO(e) — 장내종가 0 은 '장내 거래 없음' (D-013 녹색채권 30행 전부 '장내종가 0.0')
#   일반 규칙: 스키마 missing_semantics `0: missing` 인 값은 값으로 적지 않는다(수익률 0 = '미수록' 과 같은 축).
# ══════════════════════════════════════════════════════════════════════════════
D013_SQL = ("SELECT pd_nm, pd_abrv_nm, pd_eng_nm, pd_no, pd_pbcm, bd_knd, pd_risk_gcd, pd_risk_nm, applied_yield, "
            "after_tax_yield, exg_close_price, exg_close_price_base_dt, remaining_days FROM domestic_bonds "
            "WHERE (pd_nm LIKE '%(녹)%' OR pd_nm LIKE '%(녹/%' OR pd_nm LIKE '%/녹)%' OR pd_nm LIKE '%/녹/%') "
            "AND curr_cd = 'KRW' AND mat_dt >= 20260824 GROUP BY pd_no LIMIT 30")
D013_HEAD = ["pd_nm", "pd_abrv_nm", "pd_eng_nm", "pd_no", "pd_pbcm", "bd_knd", "pd_risk_gcd", "pd_risk_nm",
             "applied_yield", "after_tax_yield", "exg_close_price", "exg_close_price_base_dt", "remaining_days"]


def test_BO_e_zero_exchange_close_price():
    rows = _rows(D013_HEAD, ["산금채 21신복300010071C(녹)(콜)", "", "", "KR1", "한국산업은행", "특수은행채", "16",
                             "매우낮은위험(6등급)", "4.808", "", "0.0", "", "9178일(약 25.1년)"])
    out = pl._bond_list_answer(D013_SQL, rows, 1, "녹색채권 알려줘")
    assert "장내종가 없음(장내 거래 없음)" in out and "장내종가 0" not in out


def test_BO_e_real_price_kept_with_base_date():
    """불개입 — 0 이 아닌 종가는 기준일과 한 덩어리로 종전대로 적는다."""
    rows = _rows(D013_HEAD, ["서울교통공사 2023-2(녹)", "", "", "KR2", "서울교통공사", "일반지방공사채", "16",
                             "매우낮은위험(6등급)", "4.37", "", "9985.5", "20260731", "1486일(약 4.1년)"])
    out = pl._bond_list_answer(D013_SQL, rows, 1, "녹색채권 알려줘")
    assert "장내종가 9985.5(종가 기준일 2026-07-31)" in out


def test_BO_e_is_zero_helper():
    assert pl._is_zero("0") and pl._is_zero("0.0") and pl._is_zero(0.0)
    assert not pl._is_zero("9985.5") and not pl._is_zero("") and not pl._is_zero("미수록")


# ══════════════════════════════════════════════════════════════════════════════
# BO(f) — 듀레이션 정렬 목록엔 잔존일수 병기 (D-011 · 리드 J 결정)
#   일반 규칙: 정렬 축마다 판단에 필요한 재료가 다르다 — 수익률 축은 만기일·신용등급, 듀레이션 축은 잔존일수.
# ══════════════════════════════════════════════════════════════════════════════
D011_Q = "듀레이션 짧은 채권 추천해줘"
# 🔴 근거컬럼 보강은 대표행 보정(MAX/MIN 감쌈) **앞**에서 돈다(서버 trace D-011·D-012 순서) — 입력은 감싸기 전 모양이다.
D011_SQL = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, dur, TRIM(crd_grd) AS crd_grd FROM domestic_bonds "
            "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND dur IS NOT NULL AND dur != 99 AND dur != 0 "
            "AND pd_risk_gcd <> '11' AND COALESCE(TRIM(crd_grd),'') <> 'C0' AND bd_ofr_tcd <> '사모' "
            "ORDER BY dur ASC, pd_no ASC LIMIT 5")


def test_BO_f_duration_sort_adds_remaining_days(con):
    out, fixed = pl.ensure_bond_evidence_columns(D011_SQL)
    assert fixed and "remaining_days" in out.split("FROM")[0]
    assert "mat_dt" not in out.split("FROM")[0]              # 수익률 축 재료는 끌어오지 않는다
    got = con.execute(out).fetchall()
    assert len(got) == 5 and all(r[-1] is not None for r in got)


def test_BO_f_duration_sort_idempotent():
    """불개입 — 잔존일수가 이미 SELECT 에 있으면 손대지 않는다(멱등)."""
    sql = D011_SQL.replace("TRIM(crd_grd) AS crd_grd", "TRIM(crd_grd) AS crd_grd, remaining_days")
    assert pl.ensure_bond_evidence_columns(sql) == (sql, False)


def test_BO_f_yield_sort_unchanged():
    """형제 — 수익률 정렬은 종전 그대로 만기일·신용등급만 붙는다(잔존일수 아님)."""
    sql = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, applied_yield FROM domestic_bonds "
           "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 ORDER BY applied_yield DESC LIMIT 5")
    out, fixed = pl.ensure_bond_evidence_columns(sql)
    head = out.split("FROM")[0]
    assert fixed and "mat_dt" in head and "crd_grd" in head and "remaining_days" not in head


def test_BO_f_maturity_sort_untouched():
    """불개입 — 만기(mat_dt) 정렬은 듀레이션 축이 아니다."""
    sql = ("SELECT pd_nm, pd_no, mat_dt FROM domestic_bonds WHERE mat_dt >= 20260824 "
           "ORDER BY mat_dt ASC, pd_no ASC LIMIT 1")
    assert pl.ensure_bond_evidence_columns(sql) == (sql, False)


def test_BO_f_answer_shows_remaining_days():
    """조립기까지 — 잔존일수가 실리면 행에 '잔존' 과 산출일 고지가 함께 나온다."""
    sql, _ = pl.ensure_bond_evidence_columns(D011_SQL)
    rows = _rows(["pd_no", "pd_nm", "dur", "crd_grd", "remaining_days"],
                 ["KR3", "티월드제일백육차유동화전문1-20", "0.0073", "AAA", "3일"])
    out = pl._bond_list_answer(sql, rows, 1, D011_Q)
    assert "잔존 3일" in out and "듀레이션 0.0073" in out and "산출일" in out


# ══════════════════════════════════════════════════════════════════════════════
# BO(a) — 최상급·절단 목록의 경계값 동률 고지 (D-032 만기 2026-08-24 20종목 · F-021 728.524% 2종목)
#   일반 규칙: 표시된 행끼리의 동률이 아니라 **표시 밖 동률**을 같은 모수에서 세어 밝힌다.
# ══════════════════════════════════════════════════════════════════════════════
D032_Q = "만기가 가장 짧은 채권 뭐야?"
D032_SQL = ("SELECT pd_nm, pd_no, MIN(mat_dt) AS mat_dt FROM domestic_bonds WHERE mat_dt >= 20260824 "
            "GROUP BY pd_no ORDER BY MIN(mat_dt) ASC, pd_no ASC LIMIT 1")


def test_BO_a_tie_count_measured(con):
    n = pl._bond_axis_tie_count(D032_SQL, "mat_dt", "20260824")
    assert n == con.execute("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE mat_dt >= 20260824 "
                            "AND mat_dt = 20260824").fetchone()[0] == 20


def test_BO_a_superlative_answer_discloses_tie():
    rows = _rows(["pd_nm", "pd_no", "mat_dt"], ["산업금융채권 22신이0400-0824-1", "KR4", "20260824"])
    out = pl._bond_list_answer(D032_SQL, rows, 1, D032_Q)
    assert "만기 2026-08-24인 종목은 모두 20종목으로 동률이며, 그중 1종목을 표시했습니다." in out


def test_BO_a_yield_axis_tie(con):
    """형제 — 축이 수익률이어도 같은 규칙(F-021 728.524% 2종목)."""
    sql = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, MAX(applied_yield) AS applied_yield , mat_dt, TRIM(crd_grd) AS crd_grd "
           "FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND applied_yield IS NOT NULL "
           "AND applied_yield > 0 GROUP BY pd_no ORDER BY MAX(applied_yield) DESC, pd_no ASC LIMIT 1")
    assert pl._bond_axis_tie_count(sql, "applied_yield", "728.524") == 2
    rows = _rows(["pd_no", "pd_nm", "applied_yield", "mat_dt", "crd_grd"],
                 ["KR5", "신보2024제15차유동화전문1-2(사)", "728.524", "20261130", "C0"])
    out = pl._bond_list_answer(sql, rows, 1, "수익률이 가장 높은 채권은 뭐야?")
    assert "수익률 728.524인 종목은 모두 2종목으로 동률이며, 그중 1종목을 표시했습니다." in out


def test_BO_a_no_tie_no_note():
    """불개입 — 경계값이 유일하면 고지하지 않는다."""
    sql = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, MAX(applied_yield) AS applied_yield FROM domestic_bonds "
           "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 GROUP BY pd_no ORDER BY MAX(applied_yield) DESC, pd_no ASC LIMIT 1")
    rows = _rows(["pd_no", "pd_nm", "applied_yield"], ["KR6", "신보2024제15차유동화전문1-1(사)", "1064.523"])
    out = pl._bond_list_answer(sql, rows, 1, "수익률이 가장 높은 채권은 뭐야?")
    assert "동률이며" not in out


def test_BO_a_untouched_without_sort_axis():
    """불개입 — 정렬 축이 없는 조회 목록(ORDER BY 없음)엔 경계값이 없다."""
    sql = ("SELECT pd_nm, pd_pbcm, mat_dt FROM domestic_bonds WHERE TRIM(pd_pbcm) = '한국전력공사(주)' "
           "AND curr_cd = 'KRW' AND mat_dt >= 20260824 GROUP BY pd_no LIMIT 30")
    rows = _rows(["pd_nm", "pd_pbcm", "mat_dt"], ["한국전력공사 843", "한국전력공사(주)", "20280513"])
    out = pl._bond_list_answer(sql, rows, 1, "한국전력 채권 알려줘")
    assert "동률이며" not in out


# ══════════════════════════════════════════════════════════════════════════════
# BO(b) — 종류 확정식이 2종 이상이면 포함 종류 병기 (S-003 은행채 = 일반은행채 + 특수은행채)
#   일반 규칙: 통칭 하나가 여러 종류 값으로 풀리면 포함 목록을 밝힌다 — 목록은 선언 kind_filters 에서 읽는다.
# ══════════════════════════════════════════════════════════════════════════════
S003_Q = "가장 안전한 은행채 3개 추천해줘"
S003_SQL = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, MAX(applied_yield) AS applied_yield , pd_risk_gcd, pd_risk_nm, dur, "
            "remaining_days, TRIM(crd_grd) AS crd_grd, mat_dt FROM domestic_bonds "
            "WHERE TRIM(bd_knd) IN ('일반은행채','특수은행채') AND pd_risk_gcd = '16' AND curr_cd = 'KRW' "
            "AND mat_dt >= 20260824 AND applied_yield > 0 GROUP BY pd_no ORDER BY MAX(applied_yield) DESC LIMIT 3")


def test_BO_b_umbrella_kind_note():
    got = pl._kind_coverage_notes(S003_SQL, S003_Q)
    assert got == [("은행채", ["일반은행채", "특수은행채"])]
    notes = pl.bond_answer_notes(S003_SQL, "조건에 해당하는 채권은 전체 1,239종목이며", S003_Q)
    assert any("특수은행채" in n and "일반은행채" in n for n in notes)


def test_BO_b_sibling_multi_value_kinds():
    """형제 — 지방채 3종·국민주택 2종도 같은 규칙(값 목록은 선언에서)."""
    sql = ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) IN ('모집지방채','지역개발채','도시철도공채') "
           "AND curr_cd = 'KRW' AND mat_dt >= 20260824 LIMIT 30")
    got = pl._kind_coverage_notes(sql, "지방채 알려줘")
    assert got and got[0][0] == "지방채" and len(got[0][1]) == 3


def test_BO_b_single_value_kind_silent():
    """불개입 — 등호 하나로 풀리는 통칭(회사채)은 병기할 것이 없다."""
    sql = ("SELECT pd_nm FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='회사채' AND curr_cd = 'KRW' "
           "AND mat_dt >= 20260824 LIMIT 30")
    assert pl._kind_coverage_notes(sql, "회사채 알려줘") == []


def test_BO_b_word_absent_from_question_silent():
    """불개입 — 질문이 그 통칭을 부르지 않았으면(가드가 넣은 필터) 병기하지 않는다."""
    assert pl._kind_coverage_notes(S003_SQL, "가장 안전한 채권 3개 추천해줘") == []


def test_BO_b_expression_absent_from_sql_silent():
    """불개입 — 질문에 통칭이 있어도 그 확정식이 SQL 에 없으면 침묵(다른 축으로 답한 목록)."""
    sql = "SELECT pd_nm FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 LIMIT 30"
    assert pl._kind_coverage_notes(sql, S003_Q) == []


# ══════════════════════════════════════════════════════════════════════════════
# BO(i) — 분포 답변은 집계 축을 밝힌다 (A-015 '채권 종류별' 을 소분류 13범주로 집계)
#   일반 규칙: 축 이름은 결과 헤더의 컬럼에서 읽고, 질문이 부른 정본 축과 다르면 그 축의 범주 수를 같은 모수에서 실측해 한 줄로.
# ══════════════════════════════════════════════════════════════════════════════
A015_Q = "채권 종류별로 몇 개씩 있어?"
A015_SQL = ("SELECT std_pd_scls_nm AS std_pd_scls_nm, COUNT(DISTINCT pd_no) AS 개수 FROM domestic_bonds "
            "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 GROUP BY 1 ORDER BY 개수 DESC LIMIT 30 /*M:BONDPOP*/")
A015_ROWS = _rows(["std_pd_scls_nm", "개수"], ["일반사채", 12473], ["공사채", 4142], ["특수은행채", 1299])


def test_BO_i_axis_disclosed_and_alternative(con):
    out = pl._distribution_answer(A015_SQL, A015_ROWS, 3, A015_Q)
    k = con.execute("SELECT COUNT(DISTINCT TRIM(bd_knd)) FROM domestic_bonds WHERE curr_cd = 'KRW' "
                    "AND mat_dt >= 20260824 AND COALESCE(TRIM(bd_knd),'') <> ''").fetchone()[0]
    assert "집계 축 소분류" in out
    assert f"채권 종류(bd_knd) 축으로 세면 {k:,}개 범주" in out


def test_BO_i_canonical_axis_no_alternative():
    """불개입 — 이미 bd_knd 로 집계했으면 대안 축을 말하지 않는다(축 이름만 밝힌다)."""
    sql = A015_SQL.replace("std_pd_scls_nm AS std_pd_scls_nm", "TRIM(bd_knd) AS bd_knd").replace("std_pd_scls_nm,", "bd_knd,")
    rows = _rows(["bd_knd", "개수"], ["일반회사채", 9000], ["국고채권", 295])
    out = pl._distribution_answer(sql, rows, 2, A015_Q)
    assert "집계 축 종류" in out and "축으로 세면" not in out


def test_BO_i_other_question_no_alternative():
    """불개입 — '종류' 를 묻지 않은 분포(등급별)는 대안 축이 없다."""
    sql = ("SELECT TRIM(crd_grd) AS crd_grd, COUNT(DISTINCT pd_no) FROM domestic_bonds "
           "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 GROUP BY 1 LIMIT 30")
    rows = _rows(["crd_grd", "COUNT(DISTINCT pd_no)"], ["AAA", 5000], ["AA+", 2516])
    out = pl._distribution_answer(sql, rows, 2, "신용등급별로 몇 종목이야?")
    assert "축으로 세면" not in out


def test_BO_i_fund_distribution_untouched():
    """불개입 — 펀드(COUNT(*)) 분포는 종전 문장 그대로(채권 축 고지 없음)."""
    sql = "SELECT fnd_type_nm, COUNT(*) FROM public_funds WHERE sale_yn='판매중' GROUP BY 1 LIMIT 30"
    rows = _rows(["fnd_type_nm", "COUNT(*)"], ["주식형", 100], ["채권형", 50])
    out = pl._distribution_answer(sql, rows, 2, "유형별로 몇 개야?")
    assert out.startswith("조회 결과 2개 범주, 합계 150건입니다 (기준일") and "집계 축" not in out
