# -*- coding: utf-8 -*-
"""라운드 30 — 오답기록 #84(하이일드 세 겹) 회귀.

2026-09-06 밤 서버 실측: '하이일드 채권 수익률 높은 순 5개' 가 ① 규칙 `투기등급` 무시(모수 18,060) ② 우회 어휘 불일치
(투기등급 126종목 전부 1등급 → `pd_risk_gcd <> '11'` 이 곧 0행) ③ `ORDER BY 3 DESC` 서수가 가드 넷을 우회.

부류로 잡는다 — 사례 표가 아니라 규칙 표:
  · 서수 ORDER BY 3형 × 뒤 가드 4개 발동 · 컬럼명 형 불변 · UNION/서브쿼리 불개입 · 항 수 초과 원문 · DB 행 동일
  · enforce 슬롯 positive_any: 긍정 7어휘 발동 · 부정문 불발 · 사용자 등급 명시 불개입 · 다른 테이블 불개입
  · 로더 검증기: 모르는 질문 축·list 안 mark 중복 → 로드 거부
  · 우회 어휘 = yaml triggers(선언 원천) · 등급 정렬 가드가 슬롯 IN 을 지우지 않음 · 고지 문장 절별 · C0 주의
  · 라우터: '채권' 낱말 없는 4문형이 채권으로 · IN 목록 = 등급서열 BB+ 이하 ∩ 값 사전(스냅샷 감사)
"""
import copy
import re

import pytest

from src.runtime import guard, loader
from src.runtime import pipeline as pl
from src.runtime import router

T = ["domestic_bonds"]


@pytest.fixture(scope="module")
def ctx():
    return loader.load_context()


@pytest.fixture(scope="module")
def con():
    c = loader.connect_readonly()
    yield c
    c.close()


# ── ③ 서수 ORDER BY 정규화 ──────────────────────────────────────────────────────
_BASE = "SELECT pd_no, TRIM(pd_nm), applied_yield FROM domestic_bonds WHERE mat_dt >= 20260824 GROUP BY pd_no "


@pytest.mark.parametrize("tail, expect", [
    ("ORDER BY 3 DESC LIMIT 5", "ORDER BY applied_yield DESC LIMIT 5"),
    ("ORDER BY 3 LIMIT 5", "ORDER BY applied_yield LIMIT 5"),
    ("ORDER BY 3 DESC, 1 LIMIT 5", "ORDER BY applied_yield DESC, pd_no LIMIT 5"),
    ("ORDER BY 3 DESC LIMIT 5 /*M:BONDPOP*/", "ORDER BY applied_yield DESC LIMIT 5 /*M:BONDPOP*/"),
])
def test_ordinal_resolved(tail, expect):
    out, changed = pl.resolve_ordinal_order_by(_BASE + tail)
    assert changed and out.endswith(expect), out


def test_ordinal_alias_wins():
    sql = "SELECT pd_nm, MAX(applied_yield) AS ay FROM domestic_bonds GROUP BY pd_no ORDER BY 2 DESC LIMIT 5"
    out, changed = pl.resolve_ordinal_order_by(sql)
    assert changed and out.endswith("ORDER BY ay DESC LIMIT 5")


def test_ordinal_expression_without_alias():
    sql = "SELECT pd_nm, TRIM(crd_grd) FROM domestic_bonds ORDER BY 2 LIMIT 5"
    out, changed = pl.resolve_ordinal_order_by(sql)
    assert changed and out.endswith("ORDER BY TRIM(crd_grd) LIMIT 5")


@pytest.mark.parametrize("sql", [
    _BASE + "ORDER BY applied_yield DESC LIMIT 5",                                   # 컬럼명 형 — 멱등
    _BASE + "ORDER BY 7 DESC LIMIT 5",                                               # 항 수 초과 — 원문(SQLite 가 오류)
    "SELECT * FROM domestic_bonds ORDER BY 3 LIMIT 5",                               # SELECT *
    "SELECT 'a' AS grp, pd_nm FROM domestic_bonds UNION ALL SELECT 'b', pd_abrv_nm FROM domestic_etfs ORDER BY 2 LIMIT 5",  # UNION — 서수가 정석
    "SELECT pd_nm FROM (SELECT pd_nm, applied_yield FROM domestic_bonds) ORDER BY 2 LIMIT 5",   # 서브쿼리
    "SELECT pd_abrv_nm, du_last_aum FROM domestic_etfs ORDER BY 2 DESC LIMIT 5",     # 다른 테이블 — 채권 한정
])
def test_ordinal_untouched(sql):
    out, changed = pl.resolve_ordinal_order_by(sql)
    assert not changed and out == sql


def test_ordinal_rows_identical(con):
    a = _BASE + "ORDER BY 3 DESC, pd_no LIMIT 20"
    b, _ = pl.resolve_ordinal_order_by(a)
    assert con.execute(a).fetchall() == con.execute(b).fetchall()


def test_ordinal_unlocks_four_guards():
    """서수를 되돌린 뒤 대표행 극값·근거컬럼·동률 2차 키·머리줄 정렬축이 전부 발동한다 (#84 ③ 네 가드)."""
    q = "하이일드 채권 수익률 높은 순 5개"
    sql = _BASE + "ORDER BY 3 DESC LIMIT 5"
    sql, _ = pl.resolve_ordinal_order_by(sql)
    sql, ev = pl.ensure_bond_evidence_columns(sql)
    sql, rp = pl.ensure_bond_representative(sql)
    sql, tb = pl.ensure_tie_break(sql, q)
    assert ev and rp and tb, sql
    assert "TRIM(crd_grd) AS crd_grd" in sql and "mat_dt" in sql
    assert "MAX(applied_yield)" in sql and "pd_no ASC" in sql
    m = re.search(r"ORDER\s+BY\s+(?:MAX|MIN)?\(?\s*([A-Za-z_]\w*)", sql, re.I)
    assert m and m.group(1) == "applied_yield"                 # 머리줄 정렬축 정규식이 읽는 형


def test_representative_wraps_when_hcx_already_grouped():
    sql = "SELECT pd_nm, applied_yield FROM domestic_bonds WHERE mat_dt >= 20260824 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 5"
    out, changed = pl.ensure_bond_representative(sql)
    assert changed and "MAX(applied_yield)" in out and out.count("GROUP BY") == 1


def test_evidence_columns_allow_group_by_pd_no_only():
    ok, _ = pl.ensure_bond_evidence_columns("SELECT pd_nm, applied_yield FROM domestic_bonds GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 5")
    no, _ = pl.ensure_bond_evidence_columns("SELECT pd_pbcm, applied_yield FROM domestic_bonds GROUP BY pd_pbcm ORDER BY applied_yield DESC LIMIT 5")
    assert "crd_grd" in ok and "crd_grd" not in no


# ── ① enforce 슬롯 SPECGRADE · 만기구간 3슬롯 ───────────────────────────────────
_SPEC_IN = "TRIM(crd_grd) IN ('BB0','BB-','B+','B-','C0')"
_LIST = "SELECT pd_nm, applied_yield FROM domestic_bonds WHERE applied_yield > 0 ORDER BY applied_yield DESC LIMIT 5"


@pytest.mark.parametrize("q", ["하이일드 채권 수익률 높은 순 5개", "정크본드 수익률 높은 순", "투기등급 채권 추천",
                               "투기 등급 채권 몇 종목", "투자부적격 채권 알려줘", "투자 부적격 등급 채권", "투자등급 미만 채권 수익률"])
def test_specgrade_fires_on_positive_mention(ctx, q):
    out, fired = guard.apply_enforce(_LIST, q, T, set(), ctx)
    assert "SPECGRADE" in fired and _SPEC_IN in out and "/*M:SPECGRADE*/" in out


@pytest.mark.parametrize("q", ["하이일드 말고 안전한 채권 추천해줘", "정크 빼고 수익률 높은 채권", "투기등급 아닌 채권 추천",
                               "투기등급 채권은 제외하고 추천해줘", "하이일드 채권들은 말고"])
def test_specgrade_silent_on_negation(ctx, q):
    out, fired = guard.apply_enforce(_LIST, q, T, set(), ctx)
    assert "SPECGRADE" not in fired and _SPEC_IN not in out


@pytest.mark.parametrize("sql", [
    "SELECT pd_nm FROM domestic_bonds WHERE TRIM(crd_grd) = 'BB0' LIMIT 30",
    "SELECT pd_nm FROM domestic_bonds WHERE crd_grd IN ('BB0','BB-') LIMIT 30",
    "SELECT pd_nm FROM domestic_bonds WHERE TRIM(crd_grd) IN ('B-') ORDER BY applied_yield DESC LIMIT 5",
])
def test_specgrade_defers_to_user_grade(ctx, sql):
    out, fired = guard.apply_enforce(sql, "하이일드 중 BB0 등급만 보여줘", T, set(), ctx)
    assert "SPECGRADE" not in fired


def test_specgrade_select_only_crd_grd_is_not_a_condition(ctx):
    sql = "SELECT pd_nm, TRIM(crd_grd) AS crd_grd, applied_yield FROM domestic_bonds ORDER BY applied_yield DESC LIMIT 5"
    out, fired = guard.apply_enforce(sql, "정크본드 수익률 높은 순", T, set(), ctx)
    assert "SPECGRADE" in fired


def test_specgrade_other_table_untouched(ctx):
    sql = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 5"
    out, fired = guard.apply_enforce(sql, "하이일드 ETF 추천", ["domestic_etfs"], set(), ctx)
    assert "SPECGRADE" not in fired and out == sql


@pytest.mark.parametrize("q, mark, frag", [
    ("단기채 추천해줘", "MATSHORT", "mat_dt >= 20260824 AND mat_dt < 20270824"),
    ("단기물 수익률 높은 순", "MATSHORT", "mat_dt < 20270824"),
    ("중기채 몇 종목이야", "MATMID", "mat_dt BETWEEN 20270824 AND 20310824"),
    ("장기채 몇 종목이야", "MATLONG", "mat_dt > 20310824"),
    ("장기로 굴릴 채권 추천", "MATLONG", "mat_dt > 20310824"),
])
def test_maturity_slots(ctx, q, mark, frag):
    sql = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds LIMIT 30" if "몇" in q else _LIST
    out, fired = guard.apply_enforce(sql, q, T, set(), ctx)
    assert mark in fired and frag in out
    assert len([m for m in fired if m.startswith("MAT")]) == 1          # 구간 슬롯은 하나만


def test_maturity_slot_defers_to_user_window(ctx):
    sql = "SELECT pd_nm FROM domestic_bonds WHERE mat_dt BETWEEN 20270101 AND 20271231 LIMIT 30"
    out, fired = guard.apply_enforce(sql, "단기채 중 2027년 만기", T, set(), ctx)
    assert not any(m.startswith("MAT") for m in fired)


def test_negated_long_positive_short(ctx):
    out, fired = guard.apply_enforce(_LIST, "장기채 말고 단기채로 골라줘", T, set(), ctx)
    assert "MATSHORT" in fired and "MATLONG" not in fired


def test_two_marks_coexist_and_idempotent(ctx):
    out, fired = guard.apply_enforce(_LIST, "정크본드 수익률 높은 순", T, set(), ctx)
    assert set(fired) == {"BONDPOP", "SPECGRADE"} and out.count("/*M:") == 2
    again, fired2 = guard.apply_enforce(out, "정크본드 수익률 높은 순", T, set(), ctx)
    assert fired2 == [] and again == out


# ── 로더 검증기 ──────────────────────────────────────────────────────────────────
def _ctx_with(ctx, mutate):
    c2 = copy.copy(ctx)
    c2.enums = copy.deepcopy(ctx.enums)
    mutate(c2.enums["domestic_bonds"]["query_rules"])
    return c2


def test_validator_rejects_unknown_question_axis(ctx):
    def mut(rules):
        rules["투기등급"]["enforce"]["when"]["question"] = {"positiv_any": ["하이일드"]}
    with pytest.raises(ValueError, match="허용 밖"):
        loader.validate_enforce(_ctx_with(ctx, mut))


def test_validator_rejects_duplicate_mark_inside_list(ctx):
    def mut(rules):
        rules["만기구간"]["enforce"][1]["mark"] = "MATSHORT"
    with pytest.raises(ValueError, match="중복"):
        loader.validate_enforce(_ctx_with(ctx, mut))


def test_validator_rejects_non_dict_slot(ctx):
    def mut(rules):
        rules["만기구간"]["enforce"] = ["MATSHORT"]
    with pytest.raises(ValueError, match="dict"):
        loader.validate_enforce(_ctx_with(ctx, mut))


def test_current_declaration_loads(ctx):
    loader.validate_enforce(ctx)                              # 현 선언은 통과
    slots = guard.enforce_slots(ctx.enums["domestic_bonds"]["query_rules"]["만기구간"])
    assert [e["mark"] for e in slots] == ["MATSHORT", "MATMID", "MATLONG"]
    assert guard.enforce_slots({"text": "문자열 규칙"}) == [] and guard.enforce_slots("문자열") == []


# ── ② 우회 어휘 · 등급 정렬 충돌 · 고지 · C0 ───────────────────────────────────
def test_rank_exclusions_skip_risk_and_c0_for_spec_words():
    sql = "SELECT pd_nm, applied_yield FROM domestic_bonds WHERE mat_dt >= 20260824 AND applied_yield > 0 ORDER BY applied_yield DESC LIMIT 5"
    excl = pl._rank_exclusions(sql, "하이일드 채권 수익률 높은 순 5개")
    assert "pd_risk_gcd <> '11'" not in excl and not any("C0" in e for e in excl)
    assert "bd_ofr_tcd <> '사모'" in excl                       # 사모는 등급 범주가 아니라 유지


def test_rank_exclusions_keep_all_on_negation():
    sql = "SELECT pd_nm, applied_yield FROM domestic_bonds WHERE mat_dt >= 20260824 AND applied_yield > 0 ORDER BY applied_yield DESC LIMIT 5"
    excl = pl._rank_exclusions(sql, "하이일드 말고 안전한 채권 추천해줘")
    assert "pd_risk_gcd <> '11'" in excl and any("C0" in e for e in excl)


def test_spec_words_come_from_yaml(ctx):
    trig = ctx.enums["domestic_bonds"]["query_rules"]["투기등급"]["triggers"]
    assert "B등급" not in trig and "BB등급" not in trig           # 'BBB등급' 오폭 어휘 제거
    pat = pl._spec_grade_pattern()
    assert all(re.search(pat, w) for w in trig)


def test_grade_rank_sort_keeps_slot_in(ctx):
    q = "하이일드 채권 신용등급 낮은 순 3개"
    sql = "SELECT pd_nm, TRIM(crd_grd) AS crd_grd FROM domestic_bonds WHERE mat_dt >= 20260824 ORDER BY crd_grd ASC LIMIT 3"
    sql, fired = guard.apply_enforce(sql, q, T, set(), ctx)
    out, changed = pl.ensure_grade_rank_sort(sql, q)
    assert "SPECGRADE" in fired and changed and _SPEC_IN in out


def test_grade_rank_sort_still_drops_fabricated_in():
    q = "SK 계열사 회사채 신용등급 가장 낮은 3개"
    sql = "SELECT pd_nm, TRIM(crd_grd) AS crd_grd FROM domestic_bonds WHERE pd_pbcm LIKE '%SK%' AND TRIM(crd_grd) IN ('A-','BBB-') ORDER BY crd_grd ASC LIMIT 3"
    out, changed = pl.ensure_grade_rank_sort(sql, q)
    assert changed and "IN ('A-','BBB-')" not in out


def _rows(cols, recs):
    return " | ".join(cols) + "\n" + "\n".join(" | ".join(r) for r in recs)


def test_list_answer_exclusion_note_per_clause_and_c0():
    cols = ["pd_nm", "applied_yield", "crd_grd", "mat_dt"]
    rows = _rows(cols, [["신보2024제15차유동화전문1-2(사)", "728.524", "C0", "20261130"],
                        ["에스엘엘중앙23", "17.121", "B-", "20280428"]])
    sql_smo = ("SELECT pd_nm, applied_yield, TRIM(crd_grd) AS crd_grd, mat_dt FROM domestic_bonds WHERE " + _SPEC_IN +
               " AND bd_ofr_tcd <> '사모' GROUP BY pd_no ORDER BY MAX(applied_yield) DESC LIMIT 5 /*M:SPECGRADE*/")
    ans = pl._bond_list_answer(sql_smo, rows, 2, "하이일드 채권 수익률 높은 순 5개")
    assert "사모 채권은 제외했습니다." in ans and "1등급" not in ans.split("\n")[-1].split("사모")[0]
    assert pl.C0_YIELD_NOTE in ans
    assert "BB+ 이하 기준" in ans                               # 슬롯 answer_note(P4)
    sql_both = sql_smo.replace("AND bd_ofr_tcd", "AND pd_risk_gcd <> '11' AND bd_ofr_tcd")
    ans2 = pl._bond_list_answer(sql_both, rows, 2, "채권 추천해줘")
    assert "위험등급이 매우 높은(1등급) 채권과 사모 채권은 제외했습니다." in ans2   # 둘 다면 종전 문장 그대로


def test_list_answer_no_c0_note_without_c0():
    cols = ["pd_nm", "applied_yield", "crd_grd", "mat_dt"]
    rows = _rows(cols, [["이랜드월드108", "6.618", "BBB0", "20270423"]])
    sql = "SELECT pd_nm, applied_yield, TRIM(crd_grd) AS crd_grd, mat_dt FROM domestic_bonds WHERE mat_dt >= 20260824 ORDER BY applied_yield DESC LIMIT 5"
    ans = pl._bond_list_answer(sql, rows, 1, "채권 추천해줘")
    assert pl.C0_YIELD_NOTE not in ans and "BB+ 이하" not in ans


def test_slot_answer_notes_by_mark():
    notes = pl._slot_answer_notes()
    assert set(notes) >= {"SPECGRADE", "MATSHORT", "MATMID", "MATLONG"}
    got = pl.bond_answer_notes("SELECT pd_nm FROM domestic_bonds WHERE mat_dt < 20270824 LIMIT 5 /*M:BONDPOP*/ /*M:MATSHORT*/", "")
    assert notes["MATSHORT"] in got and "BONDPOP" not in " ".join(got)
    assert pl.bond_answer_notes("SELECT pd_nm FROM domestic_bonds LIMIT 5", "") == []


# ── 라우터 · IN 목록 감사 ──────────────────────────────────────────────────────
@pytest.mark.parametrize("q", ["정크본드 수익률 높은 순 5개", "하이일드 수익률 높은 순 5개", "투기등급 추천해줘", "단기물 수익률 높은 순"])
def test_router_bond_without_the_word_bond(ctx, q):
    assert router.route(q, ctx).tables == ["domestic_bonds"]


def test_router_etf_head_noun_still_wins(ctx):
    assert "domestic_bonds" not in router.route("하이일드 ETF 추천", ctx).tables


def test_specgrade_in_list_matches_scale_below_bb_plus(ctx, con):
    """IN 목록은 적재분 스냅샷 — 등급서열 BB+ 이하 ∩ 값 사전 실재 == 슬롯 목록. 재적재로 갈리면 여기서 깨진다."""
    scale = list(loader.grade_scale("domestic_bonds", "crd_grd"))
    order = ["AAA", "AA+", "AA0", "AA-", "A+", "A0", "A-", "BBB+", "BBB0", "BBB-", "BB+", "BB0", "BB-", "B+", "B0", "B-", "CCC", "CC", "C0", "D"]
    below = {g for g in scale if g in order and order.index(g) >= order.index("BB+")}
    present = {r[0] for r in con.execute("SELECT DISTINCT TRIM(crd_grd) FROM domestic_bonds WHERE crd_grd IS NOT NULL")}
    slot = ctx.enums["domestic_bonds"]["query_rules"]["투기등급"]["enforce"]["sql"]
    declared = set(re.findall(r"'([^']+)'", slot))
    assert declared == (below & present) == {"BB0", "BB-", "B+", "B-", "C0"}
