# -*- coding: utf-8 -*-
"""25R — 이자지급 주기 축 부재 (2026-09-05 · 사고 #77).

"한국전력공사 채권은 이자를 몇 개월마다 줘?" 에 HCX 가 **주기를 지급 방식으로 갈음**했다:
    SELECT TRIM(bd_intp_tcd) AS 이자지급주기 … GROUP BY … HAVING COUNT(DISTINCT pd_no) > 1  → "이표채 · 385"
질문은 주기(3개월·6개월)를 물었고 답은 방식(이표채)이다. 58컬럼 전수 확인 결과 주기 컬럼은 없다.
→ yaml absent_properties.hasCouponFrequency (게이트 어휘 · HCX 0회). 코드 변경 없음 —
  hasCreditGradeHistory(#65)·hasYieldHistory(#72)·hasIndustrySector(난이도상 #3) 에 이은 같은 부류 4번째.

과적합 점검:
 ① 어휘는 **이자 앵커 + 주기 축 낱말**. '개월·달' 단독은 "만기 몇 개월 남았어" 를 오폭하므로 걸지 않는다.
 ② 답할 수 있는 이웃 질문(이자지급방식·이표채·표면금리)은 주기 낱말이 없어 통과한다.
 ③ 테이블 단위 선언인 것이 설계상 옳다 — 같은 '지급주기' 축이 국내ETF 에는 실재한다(pd_dvid_cycl M/Q/S/A).
    게이트는 라우팅된 한 테이블의 선언만 보므로(gate.check ①-0) ETF 분배주기 질의는 영향이 없다.
 ④ HAVING COUNT(...) > 1 은 (발행사×이자지급구분) 950 조합을 통째로 감춘다 — BNP PARIBAS SA 는
    복리채 1 · 이표채 1 이라 같은 SQL 이 0행을 낸다. 게이트가 SQL 이전에 끊으므로 이 경로 자체가 사라진다.
"""
import sqlite3

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

Q = "한국전력공사 채권은 이자를 몇 개월마다 줘?"
PROP = "hasCouponFrequency"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def _fired(ctx, q, tables=("domestic_bonds",)):
    g = gate.check(q, ctx, list(tables))
    return g.rejected and PROP in (g.reason or ""), g


# ── ① 주기 문형은 SQL 이전에 끊긴다 ────────────────────────────────────────────
@pytest.mark.parametrize("q", [
    Q,
    "BNP PARIBAS SA 채권은 이자를 몇 개월마다 줘?",
    "이 채권 이자 언제 나와?",
    "이자 지급 주기가 어떻게 돼?",
    "쿠폰 지급 주기 알려줘",
    "한전 채권 이자를 몇 번 주나요?",
    "연 몇 번 이자 받아?",
    "이자 몇 달마다 지급돼?",
    "이표 지급일이 언제야?",
    "이자를 분기마다 주는 채권 알려줘",
    "일 년에 몇 회 이자 지급하나요?",
    "이자 지급 빈도 알려줘",
])
def test_coupon_frequency_rejected(ctx, q):
    fired, g = _fired(ctx, q)
    assert fired, f"주기 질의가 게이트를 지나갔다: {q} · {g.reason}"


# ── ② 답할 수 있는 이웃 질문은 통과한다 (오폭) ────────────────────────────────
@pytest.mark.parametrize("q", [
    "한전 채권 이자지급방식이 뭐야?",
    "이표채가 뭐야?",
    "만기 몇 개월 남았어?",
    "한전 채권 만기까지 몇 달 남았어?",
    "표면금리 5% 넘는 채권 알려줘",
    "이자를 많이 주는 채권 추천해줘",
    "할인채 목록 보여줘",
    "이자율 높은 순으로 정렬해줘",
    "복리채랑 이표채 차이가 뭐야?",
    "한전 채권 몇 종목이야?",
    "이자지급구분이 이표채인 채권 수",
    "3개월 안에 만기되는 채권",
    "이자 많이 주는 순서로 5개",
    "한국전력공사 채권 표면금리 알려줘",
    "신용등급 AA- 이상 채권",
])
def test_neighbour_questions_pass(ctx, q):
    fired, g = _fired(ctx, q)
    assert not fired, f"답할 수 있는 질문을 주기 부재로 기각했다: {q}"


# ── ③ 다른 도메인 무영향 — ETF 는 분배주기 컬럼이 실재한다 ────────────────────
@pytest.mark.parametrize("q", [
    "이 ETF 분배금 몇 개월마다 줘?",
    "ETF 분배금 지급 주기 알려줘",
    "월배당 ETF 알려줘",
])
def test_etf_distribution_cycle_untouched(ctx, q):
    fired, _ = _fired(ctx, q, tables=("domestic_etfs",))
    assert not fired, f"ETF 분배주기 질의가 채권 선언에 걸렸다: {q}"


def test_etf_cycle_column_actually_exists():
    """③ 의 전제 — 주기 축이 ETF 에는 있고 채권에는 없다는 것이 DB 사실이어야 한다."""
    con = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
    try:
        etf = {r[1] for r in con.execute('PRAGMA table_info("domestic_etfs")')}
        bond = {r[1] for r in con.execute('PRAGMA table_info("domestic_bonds")')}
    finally:
        con.close()
    assert "pd_dvid_cycl" in etf
    assert not [c for c in bond if any(k in c.lower() for k in ("cyc", "freq", "period"))]


# ── ④ 답변 문장 — 결론 → 이유 → 대안 (2026-09-05 wording) ─────────────────────
def test_answer_is_customer_wording(ctx):
    _, g = _fired(ctx, Q)
    a = g.answer or ""
    assert "확인할 수 없습니다" in a                       # 결론
    assert "이표채" in a and "표면금리" in a                # 이유(무엇이 있는지)
    assert "다시 물어봐 주시면" in a                        # 대안
    for leak in ("bd_intp_tcd", "srfc_irt", "absent", "domestic_bonds"):
        assert leak not in a, f"고객 문장에 내부 표기 누출: {leak}"


# ── ⑤ 선언이 ttl 로 나갔는가 (yaml → bond_kr.ttl 생성물 동기) ─────────────────
def test_declaration_reached_ttl():
    import os
    ttl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "ontology", "bond_kr.ttl")
    s = open(ttl, encoding="utf-8").read()
    assert f"# ABSENT: fp:DomesticBond 에는 fp:{PROP} 없음" in s
    # 🔄 2026-09-06 — 숫자를 박아 두면 부재축을 하나 선언할 때마다 이 줄이 깨진다(hasTradingVolume·
    #    hasMinimumInvestment 를 더하며 7→9). 기대값을 **선언에서 세어** ttl 이 yaml 을 빠짐없이 옮겼는지만 본다.
    import yaml as _yaml
    onto = os.path.dirname(ttl)
    doc = _yaml.safe_load(open(os.path.join(onto, "enums", "domestic_bonds.yaml"), encoding="utf-8"))
    declared = [it["property"] for it in (doc.get("absent_properties") or [])]
    for prop in declared:
        assert f"# ABSENT: fp:DomesticBond 에는 fp:{prop} 없음" in s, f"ttl 에 안 나간 선언: {prop}"
    # 스키마에서 바로 오는 ABSENT 3건(hasAssetClass·tracksIndex·hasRegion) + 선언분
    assert s.count("# ABSENT:") == 3 + len(declared)
