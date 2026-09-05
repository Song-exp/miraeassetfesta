# -*- coding: utf-8 -*-
"""2026-09-05 채권 온톨로지·SQL 전수조사에서 나온 구멍의 회귀 — 문형 변종을 곱해 잠근다.

찾은 것 (전부 '한 문장' 이 아니라 부류였다):
  ① risk_ambiguity_clarify 오폭 — '가장 위험이 낮은 채권'(안전 질의)에 되묻기가 나갔다. 되묻기는 결정층 맨 앞이라
     한 번 걸리면 '16' 단독 안전 답변 경로가 통째로 사라진다.
  ② 같은 가드 미탐 — '리스크·위험도' 어휘와 '순위·목록·순서·N개' 꼬리를 몰라 11문형 중 8문형이 그냥 통과했다.
  ③ absent_properties.hasCouponFrequency 미탐 — 숫자 주기('6개월마다'·'1년에 두 번')·구어 꼬리('언제 들어와')를 놓쳤다.
  ④ absent_properties.hasYieldHistory 미탐 — 구어 과거형 '변했'·'어떻게 됐' 이 통째로 빠져 있었다.
"""
import pytest

from src.runtime.gate import check
from src.runtime.loader import load_context
from src.runtime.pipeline import risk_ambiguity_clarify

BONDS = ["domestic_bonds"]


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── ①·② 위험 되묻기 ────────────────────────────────────────────────
RISK_CLARIFY = [
    "가장 위험한 채권 뭐야?", "제일 위험한 채권 알려줘", "위험 높은 순으로 채권 알려줘",
    "위험한 채권 순위 알려줘", "위험한 채권 순서대로 알려줘", "위험한 채권 목록 보여줘",
    "위험한 채권 5개만 알려줘", "리스크가 가장 큰 채권 알려줘", "리스크 큰 채권 순으로 알려줘",
    "제일 리스크 높은 채권 뭐야", "위험도 높은 채권 알려줘", "위험도가 큰 채권 순위",
]
RISK_PASS = [
    # 반대 방향(안전) — '16' 단독으로 답해야 하는 문형. 되묻기가 가로채면 안 된다
    "가장 위험이 낮은 채권 알려줘", "제일 위험 낮은 채권", "리스크가 가장 낮은 채권 3개만 골라줘",
    "위험도가 낮은 채권 알려줘", "가장 안전한 채권 3개", "덜 위험한 채권 알려줘", "안전성 높은 채권 3개",
    "저는 안정형 투자자인데 어떤 채권을 사면 좋을까요?", "원금 잃기 싫은데 채권 뭐 사면 돼?",
    "망하지 않을 회사가 발행한 채권만 골라줘",
    # 축 단서가 있으면 되묻지 않는다
    "위험등급 높은 채권 알려줘", "신용등급 낮은 채권 알려줘", "듀레이션 긴 채권 알려줘",
    "부도 위험 큰 채권 알려줘", "위험등급 1등급 채권 알려줘",
]


@pytest.mark.parametrize("q", RISK_CLARIFY)
def test_risk_clarify_fires(q):
    assert risk_ambiguity_clarify(q, BONDS), f"축 단서 없는 위험 질의인데 되묻지 않는다: {q}"


@pytest.mark.parametrize("q", RISK_PASS)
def test_risk_clarify_does_not_overfire(q):
    assert risk_ambiguity_clarify(q, BONDS) is None, f"되묻기가 가로챘다(안전·단서 질의): {q}"


# ── ③·④ 없는 축 게이트 ────────────────────────────────────────────
CYCLE_BLOCK = [
    "한국전력공사 채권은 이자를 몇 개월마다 줘?", "이 채권 이자는 몇 달에 한 번 나와?",
    "1년에 몇 번 이자를 받아?", "1년에 몇 차례 이자 줘?", "이자를 1년에 두 번 주는 채권 알려줘",
    "이자를 6개월마다 주나?", "이자 3개월마다 나와?", "6개월에 한 번 이자 나와?",
    "채권 이자 언제 들어와?", "이자 며칠에 나와?", "이자 지급 스케줄 알려줘", "이표 주기 알려줘",
]
HISTORY_BLOCK = [
    "단가가 어떻게 변했어?", "가격이 변했어?", "수익률이 변했나?", "금리가 변했어?",
    "수익률이 어떻게 됐어?", "금리 어떻게 됐어?", "시세가 변했나?", "수익률 변했는지 알려줘",
]
GATE_PASS = [
    # 주기 게이트 오폭 후보 — 만기·이자지급'방식'·표면금리는 답할 수 있는 질문이다
    "만기 몇 개월 남았어?", "잔존만기 6개월 이내 채권 알려줘", "3개월 안에 만기되는 채권 몇 개야?",
    "이자지급방식이 뭐야?", "이표채 몇 종목이야?", "이자를 아예 안 주는 채권은 왜 그런거야?",
    "표면금리 높은 채권 추천해줘", "1년 수익률 알려줘",
    # 이력 게이트 오폭 후보 — 조건형·비교·변동성은 이력 질문이 아니다
    "금리가 오르면 어떤 채권이 유리해?", "금리가 변한다면 어떤 채권이 좋아?",
    "신용등급 대비 수익률이 오른 채권 알려줘", "수익률 변동성이 큰 채권?", "변동금리 채권 알려줘",
]


@pytest.mark.parametrize("q", CYCLE_BLOCK + HISTORY_BLOCK)
def test_absent_axis_gate_blocks(ctx, q):
    assert check(q, ctx, BONDS).rejected, f"없는 축인데 게이트를 지난다: {q}"


@pytest.mark.parametrize("q", GATE_PASS)
def test_absent_axis_gate_passes(ctx, q):
    assert not check(q, ctx, BONDS).rejected, f"답할 수 있는 질문을 게이트가 막는다: {q}"
