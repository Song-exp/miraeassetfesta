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
