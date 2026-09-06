# -*- coding: utf-8 -*-
"""라운드 33 — 서버 QA r1 심사관 §③(가) 부류 BA~BP 회귀 (간섭 지도 docs/bonds_2026-09-06_round1_plan.md).

부류별 섹션 · 발동/불개입 짝. 입력은 서버 think_trace 의 SQL 원문(eval/probe_bonds_2026-09-06_r1.json)이고,
가드 함수를 직접 호출해 결과 SQL 과 DB 실행 값을 검사한다.
"""
import pytest

from src.runtime import guard, loader
from src.runtime import pipeline as pl

T = ["domestic_bonds"]


@pytest.fixture(scope="module")
def ctx():
    return loader.load_context()


@pytest.fixture(scope="module")
def con():
    c = loader.connect_readonly()
    yield c
    c.close()


def _one(con, sql):
    return con.execute(sql).fetchone()


# ══════════════════════════════════════════════════════════════════════════════
# BL — 창 확정 가드의 슬롯 마커 사각 (UT-094 · D-025)
#   일반 규칙: `_WHERE_BODY` 를 읽는 가드는 `/*M:…*/` 마커를 먼저 벗긴다 — 마커는 컬럼이 아니다. 마커는 LIMIT 앞뿐 아니라 절 사이에도 온다.
# ══════════════════════════════════════════════════════════════════════════════
UT094_Q = "2024년에 발행된 회사채 평균 표면금리 얼마야?"
UT094_SQL = ("SELECT AVG(srfc_irt) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 "
             "AND (TRIM(std_pd_mcls_nm) = '회사채' AND isu_dt > 20240101 AND isu_dt < 20240901) /*M:BONDPOP*/ LIMIT 30")


def test_BL_window_marker_before_limit(con):
    out, note = pl.enforce_relative_window(UT094_SQL, UT094_Q)
    assert note and "isu_dt BETWEEN 20240101 AND 20241231" in out
    assert "/*M:BONDPOP*/" in out and "mat_dt >= 20260824" in out              # 마커·구매가능 하한 보존
    n, avg = _one(con, out.replace("SELECT AVG(srfc_irt)", "SELECT COUNT(DISTINCT pd_no), AVG(srfc_irt)"))
    assert n == 2672 and round(avg, 3) == 3.651                                   # gold UT-094


def test_BL_window_marker_mid_where():
    q = "만기까지 들고 갈 건데, 3년 안에 만기되는 안전한 채권 몇 개만 골라줘"
    sql = ("SELECT pd_no FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (curr_cd = 'KRW' AND pd_risk_gcd = '16' "
           "AND mat_dt BETWEEN 20260101 AND 20291231) /*M:BONDPOP*/ AND applied_yield > 0 AND bd_ofr_tcd <> '사모' LIMIT 30")
    out, note = pl.enforce_relative_window(sql, q)
    assert note and "mat_dt BETWEEN 20260824 AND 20290824" in out and "20291231" not in out
    assert out.count("/*M:BONDPOP*/") == 1 and "applied_yield > 0" in out and "bd_ofr_tcd <> '사모'" in out


def test_BL_window_without_marker_unchanged_behaviour():
    sql = UT094_SQL.replace(" /*M:BONDPOP*/", "")
    out, note = pl.enforce_relative_window(sql, UT094_Q)
    assert note and "isu_dt BETWEEN 20240101 AND 20241231" in out and "/*M:" not in out


def test_BL_effective_window_with_marker():
    sql = ("SELECT pd_no FROM domestic_bonds WHERE curr_cd = 'KRW' AND pd_risk_gcd = '16' AND mat_dt BETWEEN 20260824 AND 20290824 "
           "/*M:BONDPOP*/ AND applied_yield > 0 LIMIT 30")
    assert pl._effective_mat_window(sql) == "2026-08-24~2029-08-24"
    assert pl._effective_mat_window(sql.replace("/*M:BONDPOP*/ ", "")) == "2026-08-24~2029-08-24"


def test_BL_threshold_with_marker():
    q = "A등급 이상 회사채 중 표면금리 5% 넘는 채권 몇 종목이야?"
    sql = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND "
           "(TRIM(std_pd_mcls_nm) = '회사채' AND srfc_irt >= 5) /*M:BONDPOP*/ LIMIT 30")
    out, fixed = pl.align_threshold_operator(sql, q)
    assert fixed and "srfc_irt > 5" in out and out.count("/*M:BONDPOP*/") == 1 and "LIMIT 30" in out


def test_BL_split_slot_markers_helper():
    body, marks = pl._split_slot_markers(" a = 1 /*M:BONDPOP*/ AND b = 2 /*M:SPECGRADE*/ ")
    assert body == "a = 1 AND b = 2" and marks == " /*M:BONDPOP*/ /*M:SPECGRADE*/"
    assert pl._split_slot_markers("a = 1") == ("a = 1", "")
