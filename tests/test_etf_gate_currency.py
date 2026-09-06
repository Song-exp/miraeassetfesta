# -*- coding: utf-8 -*-
"""2026-09-06 2차 재배포 실측 B5 — "외화로 거래되는 국내 ETF": 상수 게이트가 없어 HCX 가 통화 조건을 빼고 임의 30개를 답했다.
국내 상장 ETF·ETN 은 1,776/1,780 원화 — scope.currency 한 값이라 게이트 상수로 산다. 답변불가 문항에 답을 만들면 감점이다."""
import pytest

from src.runtime import gate
from src.runtime.loader import load_context


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_foreign_currency_domestic_etf_is_gated(ctx):
    for q in ["외화로 거래되는 국내 ETF", "달러로 거래되는 국내 ETF 있어?", "원화 아닌 통화로 표시된 ETF 알려줘"]:
        g = gate.check(q, ctx, ["domestic_etfs"])
        assert g.rejected, q
        assert "원화" in g.answer and "수록되어 있지 않" in g.answer


def test_currency_gate_does_not_fire_on_dollar_asset_questions(ctx):
    # 달러 '자산' 에 투자하는 ETF 는 답변 가능한 질의다 — 거래 통화 축이 아니다
    for q in ["미국달러선물 ETF 알려줘", "달러 자산에 투자하는 ETF 몇 개야?", "환노출 미국 ETF 알려줘"]:
        assert not gate.check(q, ctx, ["domestic_etfs"]).rejected, q
    # 두 테이블 라우팅에서는 상수 게이트가 발동하지 않는다(기존 방침 — 해외는 외화가 정상)
    assert not gate.check("외화로 거래되는 ETF", ctx, ["domestic_etfs", "overseas_etfs"]).rejected
