# -*- coding: utf-8 -*-
"""2026-09-06 채권 분류 전수조사 반영 회귀 테스트 — 전부 HCX 0회(오프라인).

전수조사: scripts/audit_bonds_taxonomy.py (도달성·정합성 8층) · scripts/probe_absent_axes_0906.py (부재축 어휘)

① 라우팅 — 상품 명사가 **더 긴 온톨로지 값 안에 갇혀** 있으면 머리 명사가 아니다.
   전수 실측 255건이 자기 테이블에서 탈락하고 있었다(ETF 상품명 142 · 펀드 105 · 채권 8).
② 부재축 — 거래량·유동성 / 최소투자금액·매수단위는 58컬럼에 없다. 선언으로 HCX 앞에서 끊는다.
③ 구조 라벨 — 채권종류가 결측이라 코코 2행이 '은행 자본성증권' 라벨을 잃고 있었다.
"""

import re

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context
from src.runtime.router import route

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")

B, DE, OE, PF = "domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── ① 값 안에 갇힌 상품 명사는 머리가 아니다 ──────────────────────────────────
@pytest.mark.parametrize("question, expect", [
    # 채권 값 안의 '투자회사' 가 머리로 승격돼 공모펀드로 갔다 (부동산투자회사채 35종목 · 집합투자회사채 7종목)
    ("부동산투자회사채 몇 종목이야", [B]),
    ("집합투자회사채 뭐 있어", [B]),
    ("롯데위탁관리부동산투자회사 채권 있어?", [B]),
    # ETF 상품명 안의 '채권' 이 머리로 승격돼 채권으로 갔다 — 총보수·순자산은 채권에 없는 컬럼이다
    ("ACE종합채권(AA-이상)액티브 총보수 얼마야?", [DE]),
    ("KODEX 종합채권(AA-이상)액티브 순자산 알려줘", [DE]),
    ("HANARO단기채권액티브 수익률 어때", [DE]),
])
def test_head_noun_not_inside_longer_value(ctx, question, expect):
    assert route(question, ctx).tables == expect


@pytest.mark.parametrize("question, expect", [
    # 갇히지 않은 머리 명사는 종전대로 이긴다 — 과교정 방지
    ("채권형 ETF 추천해줘", [DE, OE]),
    ("MBS 채권 알려줘", [B]),
    ("한국전력 채권 알려줘", [B]),
    ("국고채는 총 몇 종목이야?", [B]),
    ("미래에셋 단기채권 펀드 알려줘", [PF]),
    ("안전한 etf상품 추천좀", [DE, OE]),
])
def test_head_noun_still_wins_when_not_enclosed(ctx, question, expect):
    assert route(question, ctx).tables == expect


# ── ② 미선언 부재축 두 건 ─────────────────────────────────────────────────────
@pytest.mark.parametrize("question, prop", [
    ("거래가 제일 활발한 채권 알려줘", "hasTradingVolume"),
    ("유동성 좋은 채권 추천해줘", "hasTradingVolume"),
    ("거래량 많은 채권 5개", "hasTradingVolume"),
    ("거래가 잘 안 되는 채권은 뭐야", "hasTradingVolume"),
    ("채권 최소 얼마부터 살 수 있어?", "hasMinimumInvestment"),
    ("최소 매수 단위가 어떻게 돼?", "hasMinimumInvestment"),
    ("몇 원부터 살 수 있어?", "hasMinimumInvestment"),
])
def test_absent_axis_rejected_before_hcx(ctx, question, prop):
    r = gate.check(question, ctx, [B])
    assert r.rejected and prop in r.reason
    assert r.answer and "확인할 수 없습니다" in r.answer


@pytest.mark.parametrize("question", [
    "장내에서 실제 거래된 가격이 가장 비싼 채권이 뭐야?",   # 사고 #79 — 가격 축은 답할 수 있다
    "장내에서 거래되는 채권 몇 종목이야",
    "매매단가 높은 채권 5개",
    "100만원으로 살 수 있는 채권 추천해줘",                # 사고 #78 — 거절이 아니라 고지를 달고 추천한다
    "최소 만기가 몇 년이야?",
    "최소 5% 이상 수익률 채권 알려줘",
    "제일 싼 채권 알려줘",
])
def test_absent_axis_does_not_overreach(ctx, question):
    r = gate.check(question, ctx, [B])
    assert not (r.rejected and ("hasTradingVolume" in r.reason or "hasMinimumInvestment" in r.reason))


# ── ③ 채권종류 결측이어도 은행 자본성증권 라벨이 붙는다 ──────────────────────
def test_capital_security_label_survives_missing_bond_kind(ctx):
    import sqlite3

    doc = ctx.enums[B]
    rule = doc["query_rules"]["구조표시"]
    rule = rule if isinstance(rule, str) else rule.get("text", "")
    case = re.search(r"CASE WHEN .*? END", rule, re.S).group(0)
    con = sqlite3.connect(db_path())
    label = "은행 자본성증권(후순위·조건부자본·영구)"
    n_label = con.execute(
        f"SELECT COUNT(*) FROM {B} WHERE ({case})=?", (label,)).fetchone()[0]
    # 이름에 코코 표기가 있는 행 전건이 이 열에 잡혀야 한다 (종전 264/266 — 결측 2행이 빠져 있었다)
    n_coco_total, n_coco_labeled = con.execute(
        f"SELECT COUNT(*), SUM(CASE WHEN ({case})=? THEN 1 ELSE 0 END) FROM {B} "
        r"WHERE pd_nm LIKE '%조건부자본%' OR pd_nm LIKE '%조건상각%' OR pd_nm LIKE '%코코%'",
        (label,)).fetchone()
    con.close()
    assert n_label == 280
    assert n_coco_labeled == n_coco_total
