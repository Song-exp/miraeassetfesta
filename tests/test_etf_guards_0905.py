# -*- coding: utf-8 -*-
"""2026-09-05 라운드 6 수리분 회귀 — ETF 안전등급 확정식 · 총보수 0→NULL · 교차 힌트 '비중' · 권유 문형.

서버 실측(구버전 배포분) 4문항이 낸 결함을 그대로 재현해 잡는다. HCX 없이 가드 함수만 돈다.
"""
import pytest

from src.runtime import gate as G
from src.runtime import pipeline as P


# ── #28 "안전한 ETF 추천해줘" — 위험 조건 없이 순자산 상위 5개(전부 2등급)가 나갔다 ──

def test_safe_grade_injected_when_absent():
    sql = ("SELECT pd_nm, TRIM(pd_abrv_nm) FROM domestic_etfs "
           "WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 ORDER BY du_last_aum DESC LIMIT 5")
    out, fixed = P.ensure_etf_safe_grade(sql, "안전한 ETF 추천해줘")
    assert fixed
    assert "pd_risk_nm IN ('매우낮은위험(6등급)','낮은위험(5등급)')" in out
    assert "pd_risk_nm" in out.split("FROM")[0], "답변이 기준을 밝힐 수 있게 SELECT 에 등급을 병기한다"
    assert "ORDER BY du_last_aum DESC" in out and "LIMIT 5" in out, "정렬·LIMIT 은 보존"


def test_safe_grade_reversed_is_replaced_without_breaking_sql():
    # 값 안의 '(1등급)' 괄호에서 정규식이 끊기면 꼬리가 남아 SQL 이 깨진다 — 단위 검증에서 실측한 회귀
    sql = ("SELECT pd_abrv_nm FROM domestic_etfs "
           "WHERE pd_risk_nm IN ('매우높은위험(1등급)','높은위험(2등급)') ORDER BY du_last_aum DESC LIMIT 5")
    out, fixed = P.ensure_etf_safe_grade(sql, "안전한 ETF 추천해줘")
    assert fixed
    assert out.count("pd_risk_nm") == 1
    assert "'높은위험(2등급)'" not in out and "(1등급)" not in out
    assert out.endswith("ORDER BY du_last_aum DESC LIMIT 5")
    assert out.count("(") == out.count(")"), out


def test_safe_grade_respects_explicit_grade_and_volatility_and_overseas():
    # ① 등급 숫자를 말했으면 모델 의도 존중
    assert not P.ensure_etf_safe_grade(
        "SELECT pd_nm FROM domestic_etfs ORDER BY du_last_aum DESC LIMIT 5", "안전한 3등급 ETF")[1]
    # ② 변동성 오름차순으로 '안전' 을 표현한 SQL 은 그대로
    assert not P.ensure_etf_safe_grade(
        "SELECT pd_abrv_nm, du_vlty_1y FROM domestic_etfs WHERE du_vlty_1y > 0 ORDER BY du_vlty_1y ASC LIMIT 5",
        "안전한 ETF")[1]
    # ③ 해외는 위험등급 컬럼이 없다 — absent 게이트 몫, 여기서 손대면 없는 컬럼이 된다
    assert not P.ensure_etf_safe_grade(
        "SELECT pd_nm FROM overseas_etfs WHERE pd_grp_no='ETF' ORDER BY du_last_aum DESC LIMIT 5",
        "안전한 해외 ETF")[1]
    # ④ 5·6등급이 이미 있으면 불개입
    assert not P.ensure_etf_safe_grade(
        "SELECT pd_nm FROM domestic_etfs WHERE pd_risk_nm IN ('매우낮은위험(6등급)','낮은위험(5등급)') LIMIT 5",
        "안전한 ETF")[1]


# ── #31 에코프로 — 묻지 않은 cu_charge_rt 0.0 이 "총보수는 없으며" 로 ──

def test_charge_nullif_wraps_bare_select_column_only():
    sql = ("SELECT domestic_etfs.pd_abrv_nm, domestic_etfs.cu_charge_rt, domestic_etfs.du_last_aum "
           "FROM domestic_etfs LEFT JOIN ext_etf_holdings ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no "
           "WHERE domestic_etfs.cu_charge_rt > 0 ORDER BY 3 DESC LIMIT 1")
    out, fixed = P.ensure_etf_charge_nullif(sql)
    assert fixed
    assert "NULLIF(domestic_etfs.cu_charge_rt, 0) AS cu_charge_rt" in out
    assert "WHERE domestic_etfs.cu_charge_rt > 0" in out, "WHERE 의 보수유효 조건은 건드리지 않는다"


def test_charge_nullif_idempotent_and_skips_aliased():
    already = "SELECT pd_abrv_nm, NULLIF(cu_charge_rt, 0) AS cu_charge_rt FROM domestic_etfs LIMIT 1"
    assert not P.ensure_etf_charge_nullif(already)[1]
    aliased = "SELECT pd_nm, cu_charge_rt AS 연간보수율pct FROM overseas_etfs LIMIT 1"
    assert not P.ensure_etf_charge_nullif(aliased)[1], "이미 별칭이 붙은 항목은 규칙(보수개별조회)의 몫"


# ── #29 "삼성전자 비중이 5% 넘는 ETF" — 교차로 안 잡혀 종목 노드가 버려졌다 ──

def test_cross_hint_covers_weight_phrasing():
    assert "비중" in G._CROSS_HINTS
    assert G.is_cross_query("삼성전자 비중이 5% 넘는 ETF 몇 개야?", ["domestic_etfs", "overseas_etfs"])
    assert G.is_cross_query("에코프로가 차지하는 비중이 큰 ETF", ["domestic_etfs"])


# ── #28 꼬리 — 근거 없는 권유 문장 ──

def test_disclaimer_strips_suitability_and_monitoring_tail():
    a = ("안전한 ETF로는 KODEX 200, TIGER 200 등이 있습니다. "
         "이들은 안정적인 수익을 추구하는 투자자들에게 적합합니다. "
         "하지만 투자 전 충분한 검토가 필요하며 주기적인 모니터링이 필요합니다.")
    out, fixed = P.strip_disclaimer(a)
    assert fixed
    assert "적합합니다" not in out and "모니터링" not in out
    assert "KODEX 200" in out, "값·목록은 남긴다"
