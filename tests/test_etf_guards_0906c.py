# -*- coding: utf-8 -*-
"""2026-09-06 라운드 12 — 잘리지 않은 목록의 거짓 유보 · 거절 사유 창작.

#43 "캠브리콘 편입 중국 반도체 ETF": 14행(< 상한 30) 전수를 받고 "이외에도 더 많은 상품들이 있을 수 있습니다".
#44 URL 한 줄 질문: 거절 사유가 "개인정보 보호법에 따라 … 법적인 문제" — 규칙이 금지한 창작 문형.
"""
from src.runtime import pipeline as P


LIST_SQL = ("SELECT DISTINCT d.pd_abrv_nm AS 티커, d.pd_nm AS 상품명 FROM domestic_etfs d "
            "LEFT JOIN ext_etf_holdings eh ON d.pd_itm_no = eh.etf_code "
            "WHERE eh.constituent = 'Cambricon Technologies Corp Ltd' AND d.pd_grp_no = 'ETF' AND d.pd_sale_yn = 1 LIMIT 30")


def test_false_hedge_stripped_on_untruncated_plain_list():
    a = ("조회된 14건 중 상위 4개의 캠브리콘 편입 중국 반도체 ETF 관련 상품명은 다음과 같습니다. "
         "1. 삼성 KODEX 차이나AI반도체TOP10 2. KB RISE 중국본토대형주CSI100 "
         "이외에도 더 많은 상품들이 있을 수 있습니다.")
    out, hedged = P.strip_false_hedge(a, LIST_SQL, 14)
    assert hedged
    assert "더 많은 상품" not in out and "KODEX 차이나AI반도체TOP10" in out


def test_false_hedge_kept_when_list_is_truncated_by_explicit_limit():
    sql = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' ORDER BY du_last_aum DESC LIMIT 5"
    a = "순자산 상위 5개는 다음과 같습니다. 1. KODEX 200 … 이외에도 더 많은 상품이 있을 수 있습니다."
    assert not P.strip_false_hedge(a, sql, 5)[1], "상위 5 로 잘린 목록에서 '더 있다' 는 참이다"
    assert not P.strip_false_hedge(a, LIST_SQL, 30)[1], "상한 30 에 닿았으면 커버리지 병기 몫"


def test_refusal_reason_fabricated_law_is_replaced():
    why = ("질문이 요구하는 정보는 개인정보 보호법에 따라 수집하거나 제공할 수 없습니다. 해당 웹사이트에서는 당첨자 발표를 위한 "
           "개인 식별 정보를 수집하지 않으며, 이를 위반하는 행위는 법적인 문제가 될 수 있습니다.")
    out, fixed = P.sanitize_refusal_reason(why, "https://miraeassetfesta.com/winners")
    assert fixed and "보호법" not in out and "법적" not in out
    assert "수록되어 있지 않습니다" in out


def test_refusal_reason_legit_is_kept():
    why = "수익률 전망은 제공된 데이터에 없습니다. 과거 수익률(1개월~1년)은 조회해 드릴 수 있습니다."
    assert P.sanitize_refusal_reason(why, "KODEX 200 앞으로 오를까?") == (why, False)
    # 질문이 스스로 법·정책을 꺼냈으면 손대지 않는다
    why2 = "세법상 과세 기준은 데이터에 없습니다."
    assert not P.sanitize_refusal_reason(why2, "ETF 배당소득세 관련 법 규정 알려줘")[1]
