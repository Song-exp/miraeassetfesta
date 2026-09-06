# -*- coding: utf-8 -*-
"""2026-09-07 라운드 17 — "1년에 배당금 제일 많이 주는 ETF": 정렬 축이 범주형 문자열 컬럼이었다.

`ORDER BY 2 DESC` 의 2번 항목이 분배주기(pd_dvid_cycl)였고 값이 'M'·'Q'·'S'·'A' 라
내림차순은 알파벳 역순이다. 판매중 ETF 중 7건뿐인 'S'(반기·연 2회)가 상위 다섯을 채웠고
답변은 연 2회 상품을 "배당 제일 많이 주는" 으로 냈다 — 질문과 정반대다.
값이 전부 실재하는 행이라 환각 검사에도 전사 검사에도 걸리지 않는다(A2 순서 사고와 같은 부류).
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import connect_readonly

BAD = ("SELECT pd_abrv_nm, pd_dvid_cycl AS 분배주기, pd_dvid_pay_cnt AS 연지급횟수, "
       "pd_dvid_pay_months AS 지급월 FROM domestic_etfs "
       "WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 ORDER BY 2 DESC LIMIT 5")
CYCL = ("SELECT pd_abrv_nm, pd_dvid_cycl FROM domestic_etfs "
        "WHERE pd_grp_no='ETF' AND pd_sale_yn=1 ORDER BY pd_dvid_cycl DESC LIMIT 3")


@pytest.fixture(scope="module")
def con():
    return connect_readonly()


def test_count_axis_replaces_categorical_sort(con):
    """'많이 주는' 은 연간 지급 횟수 축이다 — 서버가 낸 반기 2회가 아니라 월배당 12회."""
    out, col = P.ensure_etf_dividend_sort(BAD, "1년에 배당금 제일 많이주는 etf추천좀")
    assert col == "pd_dvid_pay_cnt"
    rows = con.execute(out.replace("/*g*/", "")).fetchall()
    assert len(rows) == 5
    assert all(r[2] == 12.0 and r[1] == "M" for r in rows), rows      # 전부 매월 12회
    assert "pd_dvid_pay_cnt > 0" in out.replace("/*g*/", "")           # 0·결측은 순위가 아니다


def test_yield_axis_when_question_asks_rate(con):
    """'분배율·고배당' 은 연환산 분배수익률 축이다. 분배**율**(율)과 수익**률**(률)의 글자 차이도 함께 본다."""
    for q in ("분배율 높은 ETF 알려줘", "배당수익률 높은 ETF", "고배당 ETF 추천해줘"):
        out, col = P.ensure_etf_dividend_sort(CYCL, q)
        assert col == "pd_dvid_yield", q
    out, _ = P.ensure_etf_dividend_sort(CYCL, "분배율 높은 ETF 알려줘")
    rows = con.execute(out.replace("/*g*/", "")).fetchall()
    assert rows[0][0] == "SOL 팔란티어커버드콜OTM채권혼합" and rows[0][2] > 27


def test_sort_column_is_added_to_select_when_missing():
    """정렬 컬럼이 SELECT 에 없으면 함께 싣는다 — 답변기는 실린 값만 인용한다."""
    out, col = P.ensure_etf_dividend_sort(CYCL, "분배율 높은 ETF 알려줘")
    head = out[:out.upper().find(" FROM ")]
    assert "pd_dvid_yield" in head


def test_no_touch_when_axis_is_already_numeric_or_unclear():
    """불개입 — 수치 정렬 · 집계 · 축을 정하지 않은 문장 · 분배 어휘 없음."""
    ok = ("SELECT pd_abrv_nm, pd_dvid_yield FROM domestic_etfs WHERE pd_grp_no='ETF' "
          "ORDER BY pd_dvid_yield DESC LIMIT 3")
    assert P.ensure_etf_dividend_sort(ok, "분배율 높은 ETF")[1] is None
    cnt = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_dvid_cycl='M' ORDER BY 1 DESC"
    assert P.ensure_etf_dividend_sort(cnt, "월배당 ETF 몇 개야")[1] is None
    assert P.ensure_etf_dividend_sort(CYCL, "배당 ETF 알려줘")[1] is None          # 축 불명
    assert P.ensure_etf_dividend_sort(CYCL, "순자산 큰 ETF 알려줘")[1] is None      # 분배 질의 아님
