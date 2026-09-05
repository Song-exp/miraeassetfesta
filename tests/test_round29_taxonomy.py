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


# ── ④ 별칭 자백 검사 (G2) — 모델이 별칭에 적은 축이 선언상 없는 축이면 기각 ────────
@pytest.mark.parametrize("label, sql", [
    # 과거 사고의 실제 SQL 꼴 — 별칭이 축 대체를 자백한다
    ("#77 이자주기", "SELECT TRIM(bd_intp_tcd) AS 이자지급주기, COUNT(DISTINCT pd_no) "
                     "FROM domestic_bonds WHERE pd_pbcm LIKE '%한국전력%' GROUP BY 1"),
    ("#65 등급이력", "SELECT pd_nm, crd_grd_dt AS 등급변동일 FROM domestic_bonds "
                     "WHERE crd_grd_dt BETWEEN 20260701 AND 20260824"),
    ("#72 금리이력", "SELECT pd_nm, srfc_irt AS 금리추이 FROM domestic_bonds ORDER BY mat_dt DESC LIMIT 30"),
    ("#67 업종", "SELECT pd_nm, pd_pbcm AS 업종 FROM domestic_bonds WHERE pd_nm LIKE '%우주항공%'"),
    ("#81 거래량", "SELECT pd_nm, exg_close_price AS 거래량 FROM domestic_bonds ORDER BY exg_close_price DESC"),
    ("#81 최소금액", "SELECT pd_nm, eval_price AS 최소투자금액 FROM domestic_bonds LIMIT 5"),
])
def test_axis_alias_confession_rejects(ctx, label, sql):
    from src.runtime.pipeline import axis_alias_confession
    why = axis_alias_confession(sql, ctx)
    assert why, f"축 대체를 못 잡음: {label}"
    assert "없는 축" in why


@pytest.mark.parametrize("label, sql", [
    # 헷갈리는 정상 별칭 — 한 글자 차이로 뜻이 갈린다
    ("등급적용일", "SELECT pd_nm, crd_grd_dt AS 등급적용일 FROM domestic_bonds"),
    ("이자지급방식", "SELECT TRIM(bd_intp_tcd) AS 이자지급방식, COUNT(*) FROM domestic_bonds GROUP BY 1"),
    ("거래구분", "SELECT pd_exg_mkt AS 거래구분, COUNT(*) FROM domestic_bonds GROUP BY 1"),
    ("장내종가", "SELECT pd_nm, exg_close_price AS 장내종가 FROM domestic_bonds WHERE exg_close_price>0"),
    ("발행기관", "SELECT TRIM(pd_pbcm) AS 발행기관, COUNT(*) AS 종목수 FROM domestic_bonds GROUP BY 1"),
    ("민평수익률", "SELECT pd_nm, applied_yield AS 민평수익률 FROM domestic_bonds ORDER BY applied_yield DESC LIMIT 5"),
    ("만기·잔존", "SELECT pd_nm, mat_dt AS 만기일, remaining_days AS 잔존일수 FROM domestic_bonds"),
    # 🔴 다른 도메인에는 실재하는 축이다 — 테이블을 안 보고 별칭만 보면 여기서 오폭한다
    ("ETF 분배주기", "SELECT pd_abrv_nm, pd_dvid_cycl AS 분배주기 FROM domestic_etfs"),
])
def test_axis_alias_confession_does_not_overreach(ctx, label, sql):
    from src.runtime.pipeline import axis_alias_confession
    assert axis_alias_confession(sql, ctx) is None, f"정상 별칭을 기각: {label}"


# ── ⑤ 2차 (09-06 저녁) — 부재축 어휘의 {AXIS} 확장 · 수수료/발행주체 선언 · 세금은 선언 안 함 ────
@pytest.mark.parametrize("question, prop", [
    # {AXIS} 확장 — 시계열 선언이 금리·수익률·가격 밖의 축에도 붙는다 (종전엔 통과했다)
    ("발행잔액이 어떻게 변했어?", "hasYieldHistory"),
    ("듀레이션 추이 알려줘", "hasYieldHistory"),
    ("잔존일수가 줄었나", "hasYieldHistory"),
    ("컨벡시티 변화 알려줘", "hasYieldHistory"),
    # 손 어휘를 지우지 않았으므로 종전 차단은 그대로다
    ("한전 채권 금리가 요즘 어떻게 움직였어?", "hasYieldHistory"),
    # 신설 두 건
    ("채권 살 때 수수료 얼마야", "hasFee"),
    ("한국전력 재무상태 어때", "hasIssuerFinancials"),
    ("이 발행사 부채비율 알려줘", "hasIssuerFinancials"),
    ("이 회사 망할 가능성 있어?", "hasIssuerFinancials"),
])
def test_axis_expanded_declarations_reject(ctx, question, prop):
    r = gate.check(question, ctx, [B])
    assert r.rejected and prop in r.reason


@pytest.mark.parametrize("question", [
    # 발행 시점은 축이 실재한다 (#66) — 시계열 확장이 여기를 삼키면 안 된다
    "최근 6개월 안에 새로 발행된 회사채 중에 표면금리 높은 5개 알려줘",
    "발행연도별 표면금리 알려줘",
    # 조건형·비율·변동금리 — 종전 오폭 방어가 {AXIS} 확장 뒤에도 유지된다
    "금리가 오르면 어떤 채권이 유리해?",
    "변동금리 채권 몇 종목?",
    "수익률 변동성 큰 채권",
    "신용등급 대비 수익률이 오른 채권",
    # 축 이름 + 정렬은 시계열이 아니다
    "발행잔액이 큰 채권 3개",
    "듀레이션 낮은 채권 추천",
    # 🔴 세금은 부재축이 아니다 — 세후 수익률 4종·예금환산 2종이 634행에 실재한다
    "세후 수익률 얼마야?",
    "채권 이자에 세금 얼마나 떼?",
    # 신용등급·위험등급은 발행주체 상태 선언이 삼키면 안 된다
    "한국전력 채권 신용등급 뭐야",
    "망하지 않을 회사가 발행한 채권만 골라줘",
])
def test_axis_expanded_declarations_do_not_overreach(ctx, question):
    r = gate.check(question, ctx, [B])
    assert not (r.rejected and any(p in r.reason for p in ("hasYieldHistory", "hasFee", "hasIssuerFinancials")))


def test_axis_placeholder_expanded_from_declarations(ctx):
    """{AXIS} 는 로더가 스키마·yaml korean_name·synonyms 에서 채운다 — 프롬프트·게이트에 자리표시자가 남으면 안 된다."""
    for item in ctx.absent_props[B]:
        for pat in item.get("vocab") or []:
            assert "{AXIS}" not in pat
    ys = next(it for it in ctx.absent_props[B] if it["property"] == "hasYieldHistory")
    joined = " ".join(ys["vocab"])
    for axis in ("발행잔액", "듀레이션", "잔존일수", "표면금리"):
        assert axis in joined


# ── ⑥ 09-06 저녁 — 약한 축 묶음(2~7): 만기구간 · 국민주택 · 투기등급 · 규모 · 복리/단리 · 예금비교 ────
@pytest.mark.parametrize("question", [
    "단기채 추천해줘", "장기채 뭐 있어", "중기채 수익률 높은 순",
    "국민주택채권 알려줘", "국민주택채권 지금 사면 수익률 어때?",
    "복리로 이자 붙는 채권 있어?", "단리채 몇 종목이야",
])
def test_weak_axes_now_route_to_bonds(ctx, question):
    """종전엔 어휘가 없어 4테이블 미특정(근거문서 희석)으로 빠지던 질문들."""
    assert route(question, ctx).tables == [B]
    assert not gate.check(question, ctx, [B]).rejected


# 🔴 규칙 **이름**이 아니라 본문 고유 문구로 잰다 — 고위험제외 본문이 '규칙 투기등급' 을 언급하므로
#    이름만 찾으면 triggered 규칙이 안 실려도 걸린다(초판 실패).
_RULE_MARK = {"만기구간": "채권 종류가 아니라 **만기 구간**이다",
              "투기등급": "표준표 BB+ 이하",
              "예금비교": "예금환산수익률 컬럼이 그 비교를 위해 있다"}


@pytest.mark.parametrize("question, rule, present", [
    ("단기채 추천해줘", "만기구간", True),
    ("하이일드 채권 알려줘", "투기등급", True),
    ("예금보다 나은 채권 있어?", "예금비교", True),
    # 낱말이 없으면 안 실린다 — triggered 규칙은 프롬프트를 불리지 않는다
    ("수익률 높은 채권 5개", "만기구간", False),
    ("수익률 높은 채권 5개", "투기등급", False),
    ("수익률 높은 채권 5개", "예금비교", False),
])
def test_triggered_rules_load_only_when_asked(ctx, question, rule, present):
    assert (_RULE_MARK[rule] in ctx.planner_context([B], question)) is present


def test_kind_filter_national_housing(ctx):
    from src.runtime.pipeline import _question_kind_filters
    f = _question_kind_filters("국민주택채권 몇 종목이야")
    assert f == {"TRIM(bd_knd) IN ('국민주택1종','국민주택2종')"}
    assert _question_kind_filters("국민주택1종 알려줘") == {"TRIM(bd_knd)='국민주택1종'"}


@pytest.mark.parametrize("question, keeps_c0", [
    # 질문이 투기등급을 콕 집으면 C0 제외 절을 넣지 않는다 (126 → 23 조용한 축소 방지)
    ("하이일드 채권 알려줘", True),
    ("정크본드 5개", True),
    ("투자부적격 등급 채권 있어?", True),
    ("투기등급 채권 수익률 높은 순", True),
    # 일반 추천은 종전대로 C0 를 뺀다
    ("수익률 높은 채권 5개 추천해줘", False),
    ("안전한 채권 3개", False),
])
def test_speculative_grade_bypasses_c0_exclusion(question, keeps_c0):
    from src.runtime.pipeline import _rank_exclusions
    excl = _rank_exclusions("SELECT pd_nm FROM domestic_bonds WHERE 1=1", question)
    assert (not any("C0" in e for e in excl)) is keeps_c0


def test_maturity_bucket_rule_partitions_buyable_universe():
    """만기구간 세 구간의 합 = 구매가능 모수 (빠짐·겹침 0) — 규칙에 적은 수치 그대로."""
    import sqlite3
    con = sqlite3.connect(db_path())
    buy = "curr_cd='KRW' AND mat_dt>=20260824"
    s = con.execute(f"SELECT COUNT(DISTINCT pd_no) FROM {B} WHERE {buy} AND mat_dt<20270824").fetchone()[0]
    m = con.execute(f"SELECT COUNT(DISTINCT pd_no) FROM {B} WHERE {buy} AND mat_dt BETWEEN 20270824 AND 20310824").fetchone()[0]
    l = con.execute(f"SELECT COUNT(DISTINCT pd_no) FROM {B} WHERE {buy} AND mat_dt>20310824").fetchone()[0]
    tot = con.execute(f"SELECT COUNT(DISTINCT pd_no) FROM {B} WHERE {buy}").fetchone()[0]
    con.close()
    assert (s, m, l) == (6414, 11230, 2787)
    assert s + m + l == tot


def test_scale_ambiguity_declared(ctx):
    d = ctx.enums[B]["clarify"]["다의어"]
    assert "규모" in d and "bd_tisu_a" in d["규모"] and "isu_bal_amt" in d["규모"]


# ── ⑦ 09-06 밤 — 묶음 2~7 과적합 점검에서 나온 두 결함 ──────────────────────────────
def test_speculative_grade_rule_uses_only_real_values(ctx):
    """규칙 본문의 IN 리터럴은 값 검사를 통과해야 한다 — 표준표 11종을 다 적으면 6종이 기각당한다."""
    from src.runtime import guard
    rule = ctx.enums[B]["query_rules"]["투기등급"]["text"]
    m = re.search(r"IN \(([^)]*)\)", rule)
    assert m, "투기등급 규칙에 IN 리터럴이 없다"
    sql = f"SELECT pd_nm FROM {B} WHERE TRIM(crd_grd) IN ({m.group(1)})"
    assert guard.check_values(sql, ctx) == []
    for dead in ("'CCC'", "'D'", "'B0'", "'BB+'"):
        assert dead not in m.group(1)


@pytest.mark.parametrize("question, clause", [
    # 부정문 — 범주를 빼 달라는 것이므로 제외 절을 그대로 넣는다 (종전엔 사모·투기·부실까지 전부 우회됐다)
    ("정크 말고 안전한 채권 추천해줘", "C0"),
    ("하이일드는 빼고 수익률 높은 채권 5개", "C0"),
    ("부실채 제외하고 수익률 높은 순", "C0"),
    ("투기등급 아닌 채권 중 수익률 높은 5개", "C0"),
    ("사모 빼고 추천해줘", "사모"),
    ("위험 높은 채권 말고 안전한 것", "'11'"),
])
def test_negated_category_keeps_exclusion(question, clause):
    from src.runtime.pipeline import _rank_exclusions
    assert clause in " ".join(_rank_exclusions("SELECT pd_nm FROM domestic_bonds WHERE 1=1", question))


@pytest.mark.parametrize("question, clause", [
    ("사모 채권 추천해줘", "사모"),
    ("위험 높은 채권 순위", "'11'"),
    ("투기등급 채권 수익률 높은 순", "C0"),
])
def test_positive_category_still_bypasses(question, clause):
    from src.runtime.pipeline import _rank_exclusions
    assert clause not in " ".join(_rank_exclusions("SELECT pd_nm FROM domestic_bonds WHERE 1=1", question))


# ── ⑧ 09-06 밤 2차 재점검 — 오분류 셋 ───────────────────────────────────────────────
@pytest.mark.parametrize("question", [
    "매출채권 유동화 채권 알려줘",      # 채권 구조 용어 — 발행사 재무가 아니다
    "부채담보부증권 알려줘",            # CDO
    "조건부자본증권 알려줘", "신종자본증권 뭐 있어",   # 이름에 '자본' 313행
    "구분이 어떻게 바뀐 거야", "기준일이 언제로 바뀌었어?", "개인이 오른 채권",   # {AXIS} 잡낱말이 시계열로 오폭하던 것
])
def test_recheck_structure_terms_and_modifier_fragments_pass(ctx, question):
    r = gate.check(question, ctx, [B])
    assert not (r.rejected and ("hasIssuerFinancials" in r.reason or "hasYieldHistory" in r.reason))


def test_axis_alternation_has_no_modifier_fragments(ctx):
    """{AXIS} 는 축 이름만 — korean_name 을 공백에서 쪼개 생긴 수식어 조각(개인·세후·구분·기준·코드)이 섞이면 안 된다."""
    ys = next(i for i in ctx.absent_props[B] if i["property"] == "hasYieldHistory")
    joined = " ".join(ys["vocab"])
    for junk in ("개인", "법인", "구분", "기준", "코드", "순번", "여부", "공통", "성격", "동일", "한전", "국채"):
        assert not re.search(rf"\|{junk}\|", joined) and not re.search(rf"\|{junk}\)", joined), junk
    for axis in ("발행잔액", "듀레이션", "잔존일수", "표면금리", "컨벡시티"):
        assert axis in joined


@pytest.mark.parametrize("question, clause", [
    ("하이일드 채권은 빼고 추천해줘", "C0"),      # 명사 뒤 조사
    ("투기등급 채권 말고 안전한 것", "C0"),        # 명사 둘
    ("사모채는 제외하고 추천", "사모"),
    ("C0 등급은 제외해줘", "C0"),
    ("부실 채권을 빼고 수익률 높은 순", "C0"),
    ("고위험 채권들은 말고", "'11'"),              # 복수 '들'
])
def test_negation_word_order_variants_keep_exclusion(question, clause):
    from src.runtime.pipeline import _rank_exclusions
    assert clause in " ".join(_rank_exclusions("SELECT pd_nm FROM domestic_bonds WHERE 1=1", question))
