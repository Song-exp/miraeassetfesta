# -*- coding: utf-8 -*-
"""ETF 기본모수 가드의 '날조 술어 제거' 가 사용자 조건을 지우던 자리 (2026-09-06 재생 E5·E25).

  E25 "레버리지 ETF 중에서 인버스는 빼고 몇 개야?"  `cu_lev_fector > 1` 이 지워져 전체 ETF 1,160 이 답이 됐다 —
      DB 스키마 한글명은 '배수', yaml korean_name 은 '레버리지배수'. 한쪽만 봐서 '레버리지' 를 못 이었다.
  E5  "미국 3배 레버리지 ETF 뭐 있어?"  Ground 가 '미국' → 'United States of America' 로 접지한 절이 지워져
      `WHERE  LIMIT 30` 문법 오류 → 거절.
정답 케이스(U8 의 `cu_charge_rt > 0` 제거)는 test_round8_repairs 가 지킨다.
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import db_path

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


def test_leverage_predicate_survives_via_yaml_korean_name():
    sql = "SELECT COUNT(*) FROM domestic_etfs WHERE cu_lev_fector > 1 LIMIT 30"
    out, _ = P.ensure_etf_base_population(sql, "레버리지 ETF 중에서 인버스는 빼고 몇 개야?")
    assert "cu_lev_fector > 1" in out, out
    assert "pd_grp_no = 'ETF'" in out and "pd_sale_yn = 1" in out


def test_kg_grounded_literal_counts_as_asked():
    assert P._literal_grounded("overseas_etfs", "wu_inv_rgn = 'United States of America'", "미국 3배 레버리지 ETF 뭐 있어?")
    assert not P._literal_grounded("overseas_etfs", "wu_inv_rgn = 'Europe'", "미국 3배 레버리지 ETF 뭐 있어?")


def test_removal_never_empties_where():
    sql = "SELECT pd_nm, pd_abrv_nm FROM overseas_etfs WHERE wu_inv_rgn = 'Europe' LIMIT 30"
    out, changed = P.ensure_etf_base_population(sql, "ETF 알려줘")
    assert "WHERE  LIMIT" not in out and "wu_inv_rgn = 'Europe'" in out, out
    assert not changed


def test_unasked_zero_filter_is_still_removed_when_other_predicates_remain():
    sql = ("SELECT ref_fund_mgmt_co, SUM(du_last_aum) FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 "
           "AND cu_charge_rt > 0 GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
    out, _ = P.ensure_etf_base_population(sql, "운용사별 순자산 합계 상위 5곳")
    assert "cu_charge_rt" not in out, out
