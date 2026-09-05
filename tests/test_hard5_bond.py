# -*- coding: utf-8 -*-
"""채권 난이도 상 5문항 수리 회귀 (2026-09-05 · docs/bond_hard5_fix_plan_2026-09-05.md).

서버 실측 5문항(에코프로 자회사 · SK 계열사 최저 등급 · 우주항공 관련 발행사 · 등급 변동 이력 · ESG 발행액순+위험요인)에서
드러난 결함을 부류 단위로 고친 뒤, 문항 자체와 형제 질문·gold 전건을 오프라인(HCX 0회)으로 잠근다.
"""

import json
import re
from pathlib import Path

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")

GOLD = Path("eval/questions_domestic_bonds.jsonl")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


class _BondProbe:
    """근거문서·게이트만 보는 플래너 — SQL 은 실행 가능한 아무 문장."""

    def plan_sql(self, question, grounding):
        return "SELECT pd_no, TRIM(pd_nm) AS pd_nm FROM domestic_bonds LIMIT 1"

    def compose_answer(self, question, rows):
        return "probe"


def _gold_questions():
    if not GOLD.exists():
        return []
    return [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── P3. 업종·테마·섹터 ABSENT (hasIndustrySector) ──────────────────────────────

def test_industry_absent_ungrounded_theme(ctx):
    """#3 — '우주항공 관련 발행사' 는 접지되는 개체가 없다 → 업종 ABSENT 로 HCX 0회 기각 + 발행사 이름 되묻기."""
    r = answer_question("H5-03", "최근 6개월 동안 우주항공 관련 발행사가 발행한 채권 정리해줘", ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "hasIndustrySector" in r.think_trace
    assert "업종" in r.answer and "발행사 이름" in r.answer
    assert "상품 자체가 없" not in r.answer                      # 종전 오답 문구


def test_industry_absent_axis_word(ctx):
    """축의 이름(업종·테마·섹터)은 접지와 무관하게 발동한다."""
    for q in ("은행 업종 채권 알려줘", "2차전지 테마 회사채 있어?", "방산 섹터 채권 정리해줘"):
        g = gate.check(q, ctx, ["domestic_bonds"])
        assert g.rejected and "hasIndustrySector" in g.reason, q


def test_industry_grounded_issuer_passes(ctx):
    """'○○ 관련 채권' 에서 ○○ 이 발행사 노드로 접지되면 업종 질의가 아니다 — 통과."""
    r = answer_question("H5-03b", "한화에어로스페이스 관련 채권 알려줘", planner=_BondProbe(), ctx=ctx)
    assert "hasIndustrySector" not in r.think_trace and "[Gate] 통과" in r.think_trace


def test_industry_vocab_skips_ksan(ctx):
    """'산업' 은 한국산업은행·산업금융채권을 비켜 간다."""
    for q in ("한국산업은행 채권 알려줘", "산업금융채권 수익률 높은 순", "산업은행이 발행한 채권 개수"):
        g = gate.check(q, ctx, ["domestic_bonds"])
        assert not (g.rejected and "hasIndustrySector" in g.reason), q


def test_industry_absent_no_new_rejection_on_gold(ctx):
    """gold 채권 전건 — 새 선언이 answer 기대 문항을 하나도 새로 기각하지 않는다."""
    for x in _gold_questions():
        if x.get("expected_behavior") != "answer":
            continue
        g = gate.check(x["question"], ctx, ["domestic_bonds"], grounded_entity=True)
        assert not (g.rejected and "hasIndustrySector" in g.reason), x["qid"]
        g2 = gate.check(x["question"], ctx, ["domestic_bonds"], grounded_entity=False)
        assert not (g2.rejected and "hasIndustrySector" in g2.reason), x["qid"]


def test_yield_history_why_uses_snapshot_wording(ctx):
    """P0 — 개발자 사유에서도 8/22 를 '기준일' 이라 부르지 않는다(리드 결정 09-02: 판정·표기 기준일은 8/24)."""
    items = {i["property"]: i for i in ctx.absent_props["domestic_bonds"]}
    assert "기준일(2026-08-22)" not in items["hasYieldHistory"]["why"]


# ── P6. SELECT 보장 — 위험등급 이름(TRIM 래퍼) · 종목 식별 컬럼 ──────────────────

def test_risk_name_added_inside_trim_wrapper():
    """#2 — `TRIM(pd_risk_gcd) AS 위험등급` 은 표시 컬럼이다 → pd_risk_nm 이 붙어야 한다(코드 '14' 노출 차단)."""
    from src.runtime.pipeline import ensure_risk_name_column
    sql = ("SELECT pd_no, TRIM(pd_nm) AS 상품명, TRIM(crd_grd) AS 신용등급, TRIM(pd_risk_gcd) AS 위험등급, dur "
           "FROM domestic_bonds WHERE curr_cd = 'KRW' ORDER BY crd_grd LIMIT 3")
    out, fixed = ensure_risk_name_column(sql)
    assert fixed and "pd_risk_nm" in out and "TRIM(pd_risk_gcd, pd_risk_nm)" not in out
    assert "TRIM(pd_risk_gcd) AS 위험등급" in out


def test_risk_name_skips_aggregates_and_existing():
    from src.runtime.pipeline import ensure_risk_name_column
    for sql in ("SELECT COUNT(pd_risk_gcd) FROM domestic_bonds",
                "SELECT MAX(TRIM(pd_risk_gcd)) FROM domestic_bonds",
                "SELECT pd_risk_gcd, pd_risk_nm FROM domestic_bonds LIMIT 5"):
        assert ensure_risk_name_column(sql) == (sql, False), sql


def test_identity_columns_added_for_single_bond_lookup():
    """#1 — 종목 속성만 고른 SELECT 에 pd_no·pd_nm 을 앞세운다."""
    from src.runtime.pipeline import ensure_bond_identity_columns
    sql = ("SELECT domestic_bonds.pd_pbcm, domestic_bonds.srfc_irt, domestic_bonds.pd_risk_gcd, pd_risk_nm FROM domestic_bonds "
           "WHERE TRIM(domestic_bonds.pd_pbcm) = '(주)에코프로' AND curr_cd = 'KRW' AND mat_dt >= 20260824 "
           "ORDER BY domestic_bonds.srfc_irt DESC LIMIT 1")
    out, fixed = ensure_bond_identity_columns(sql)
    assert fixed and out.startswith("SELECT pd_no, TRIM(pd_nm) AS pd_nm, domestic_bonds.pd_pbcm")


def test_identity_columns_noninterference():
    from src.runtime.pipeline import ensure_bond_identity_columns
    for sql in ("SELECT DISTINCT TRIM(pd_pbcm) AS 발행사 FROM domestic_bonds WHERE crd_grd = 'AAA' LIMIT 30",
                "SELECT TRIM(pd_pbcm) AS 발행사, COUNT(DISTINCT pd_no) AS n FROM domestic_bonds GROUP BY 1 ORDER BY n DESC LIMIT 5",
                "SELECT TRIM(bd_knd), AVG(applied_yield) FROM domestic_bonds GROUP BY TRIM(bd_knd)",
                "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE mat_dt >= 20260824",
                "SELECT * FROM domestic_bonds WHERE pd_no = 'KR1' LIMIT 1",
                "SELECT pd_no, TRIM(pd_nm) AS pd_nm, applied_yield FROM domestic_bonds LIMIT 5",
                "SELECT pd_no FROM domestic_bonds WHERE crd_grd = 'AAA' LIMIT 5"):
        assert ensure_bond_identity_columns(sql) == (sql, False), sql


# ── P4. 종목명 LIKE 리터럴 출처 검사 ──────────────────────────────────────────────

_Q3_SQL = ("SELECT MIN(pd_no) AS pd_no, TRIM(pd_nm) AS 상품명 FROM domestic_bonds "
           "WHERE (pd_nm LIKE '%우주항공%' OR pd_nm LIKE '%Space%') AND curr_cd = 'KRW' AND mat_dt >= 20260824 "
           "GROUP BY pd_no ORDER BY MIN(pd_no) LIMIT 30")
_Q3 = "최근 6개월 동안 우주항공 관련 발행사가 발행한 채권 정리해줘"


def test_fabricated_name_branch_stripped(ctx):
    """#3 — 'Space' 는 질문에도 선언에도 없는 즉석 번역 → OR 가지 제거. '우주항공' 은 질문의 낱말이라 남는다."""
    from src.runtime.pipeline import strip_fabricated_name_branches
    out, stripped = strip_fabricated_name_branches(_Q3_SQL, _Q3, ctx)
    assert stripped == ["Space"] and "Space" not in out and "'%우주항공%'" in out
    assert "(pd_nm LIKE '%우주항공%')" in out


def test_fabricated_name_and_clause_rejected_by_precheck(ctx):
    from src.runtime.pipeline import _sql_precheck
    sql = "SELECT pd_no, TRIM(pd_nm) AS pd_nm FROM domestic_bonds WHERE pd_nm LIKE '%Space%' AND curr_cd = 'KRW' LIMIT 30"
    err = _sql_precheck(sql, ctx, ["domestic_bonds"], False, question=_Q3)
    assert err and "'Space'" in err and "REFUSE" in err
    assert _sql_precheck(sql, ctx, ["domestic_bonds"], False) is None          # question 없이 부르는 옛 경로는 불개입


def test_declared_name_literals_pass_without_question_word(ctx):
    """ESG 라벨·구조 표기는 질문에 그 글자가 없어도 선언된 표기라 통과한다."""
    from src.runtime.pipeline import _fabricated_name_literals
    sql = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm FROM domestic_bonds WHERE (pd_nm LIKE '%(녹)%' OR pd_nm LIKE '%/사/%' "
           "OR pd_nm LIKE '%(지)%') AND pd_nm LIKE '%신종%' AND pd_nm NOT LIKE '%콜마%' LIMIT 30")
    assert _fabricated_name_literals(sql, "ESG 채권 중 영구채 알려줘", ctx) == []


def test_gold_bond_sql_has_no_fabricated_name_literal(ctx):
    """gold 채권 SQL 전건 — pd_nm LIKE 리터럴(질문 밖 108건)이 전부 선언 표기라 출처 검사에 하나도 걸리지 않는다."""
    from src.runtime.pipeline import _fabricated_name_literals, strip_fabricated_name_branches
    for x in _gold_questions():
        sql = x.get("gold_sql") or ""
        if "pd_nm" not in sql:
            continue
        assert _fabricated_name_literals(sql, x["question"], ctx) == [], x["qid"]
        assert strip_fabricated_name_branches(sql, x["question"], ctx) == (sql, []), x["qid"]


# ── P5. 신용등급 서열 정렬 ───────────────────────────────────────────────────────

_Q2 = "SK 계열사 회사채 중 신용등급이 가장 낮은 종목 3개와 그 위험요인 정리해줘"
_Q2_SQL = ("SELECT pd_no, TRIM(pd_nm) AS 상품명, TRIM(crd_grd) AS 신용등급, TRIM(pd_risk_gcd) AS 위험등급, TRIM(pd_pbcm) AS 발행기관, "
           "dur AS 듀레이션, remaining_days AS 잔존일수, applied_yield AS 수익률 FROM domestic_bonds "
           "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (std_pd_mcls_nm = '회사채' AND (TRIM(pd_pbcm) LIKE 'SK%' "
           "OR TRIM(pd_pbcm) LIKE '(주)SK%' OR TRIM(pd_pbcm) LIKE '에스케이%' OR TRIM(pd_pbcm) LIKE '(주)에스케이%') "
           "AND crd_grd IN ('A-', 'BBB-')) GROUP BY pd_no ORDER BY MIN(crd_grd) ASC LIMIT 3")


def test_grade_rank_sort_rewrites_order_and_strips_fabricated_in(ctx):
    """#2 — 문자열 사전순 ORDER BY crd_grd → 선언 서열 CASE(DESC=낮은 순) · 질문에 등급 값이 없으니 IN 목록 제거 · 무등급 제외."""
    from src.runtime.pipeline import ensure_grade_rank_sort
    out, fixed = ensure_grade_rank_sort(_Q2_SQL, _Q2)
    assert fixed and "CASE TRIM(crd_grd)" in out and "DESC" in out and "crd_grd IN" not in out
    assert "crd_grd IS NOT NULL" in out and "/*GRADESORT:low*/" in out and "MIN(mat_dt) ASC, pd_no ASC" in out
    assert "TRIM(pd_pbcm) LIKE '에스케이%'" in out                 # OR 그룹은 그대로


def test_grade_rank_sort_gives_bbb_minus_first(ctx):
    """실측 정답 — SK 접두 회사채 최저 등급 3종목은 BBB- · BBB0 · BBB+ (A- 가 아니다)."""
    import sqlite3
    from src.runtime.pipeline import ensure_grade_rank_sort
    out, _ = ensure_grade_rank_sort(_Q2_SQL, _Q2)
    con = sqlite3.connect(str(db_path()))
    rows = con.execute(out).fetchall()
    con.close()
    assert [r[2] for r in rows] == ["BBB-", "BBB0", "BBB+"], rows


def test_grade_rank_sort_noninterference():
    from src.runtime.pipeline import ensure_grade_rank_sort
    sql = "SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(crd_grd) AS crd_grd FROM domestic_bonds WHERE crd_grd IN ('AAA','AA+') ORDER BY crd_grd LIMIT 5"
    # 맨 '등급' 은 되묻기 영역(BND-C-016) — 손대지 않는다
    assert ensure_grade_rank_sort(sql, "등급 낮은 채권 알려줘") == (sql, False)
    # 축이 금리면 불개입
    sql2 = "SELECT pd_no, srfc_irt FROM domestic_bonds WHERE TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-','A+','A0','A-') ORDER BY srfc_irt DESC LIMIT 5"
    assert ensure_grade_rank_sort(sql2, "A등급 이상 회사채 표면금리 높은 순 5개") == (sql2, False)
    # 질문에 등급 값이 있으면 IN 은 남는다(정렬만 서열로)
    out, fixed = ensure_grade_rank_sort(sql, "신용등급 AA 이상 채권 중 신용등급 가장 높은 5개")
    assert fixed and "crd_grd IN ('AAA','AA+')" in out and "ASC" in out


def test_grade_rank_sort_header_and_note(ctx):
    """조립기 머리줄은 '신용등급 낮은 순', 꼬리에 무등급 제외·동률 고지."""
    from src.runtime.pipeline import _bond_list_answer, ensure_grade_rank_sort, GRADE_SORT_NOTE
    import sqlite3
    out, _ = ensure_grade_rank_sort(_Q2_SQL, _Q2)
    con = sqlite3.connect(str(db_path()))
    cur = con.execute(out.replace("TRIM(pd_nm) AS 상품명", "TRIM(pd_nm) AS pd_nm"))
    cols = [d[0] for d in cur.description]
    lines = [" | ".join(cols)] + [" | ".join("" if v is None else str(v) for v in r) for r in cur.fetchall()]
    con.close()
    ans = _bond_list_answer(out, "\n".join(lines), len(lines) - 1, _Q2)
    assert ans and "신용등급 낮은 순" in ans and GRADE_SORT_NOTE in ans


# ── P7·P8. 고지 단일 통로 · 위험요인 재료 조립 ─────────────────────────────────────

_Q1 = "에코프로 자회사가 발행한 채권 중 표면금리가 가장 높은 종목의 위험요인 알려줘"
_Q1_SQL = ("SELECT domestic_bonds.pd_pbcm, domestic_bonds.srfc_irt, domestic_bonds.pd_risk_gcd, pd_risk_nm FROM domestic_bonds "
           "WHERE TRIM(domestic_bonds.pd_pbcm) IN ('(주)에코프로', '(주)에코프로비엠') AND curr_cd = 'KRW' AND mat_dt >= 20260824 "
           "ORDER BY domestic_bonds.srfc_irt DESC LIMIT 1")


def _run_rows(sql):
    import sqlite3
    con = sqlite3.connect(str(db_path()))
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    lines = [" | ".join(cols)] + [" | ".join("" if v is None else str(v) for v in r) for r in cur.fetchall()]
    con.close()
    return "\n".join(lines), len(lines) - 1


def test_risk_factor_columns_added(ctx):
    """#1 — 위험요인 질의는 SELECT 에 재료 컬럼과 구조 CASE 가 보장된다."""
    from src.runtime.pipeline import ensure_risk_factor_columns
    out, fixed = ensure_risk_factor_columns(_Q1_SQL, _Q1, ctx)
    assert fixed and all(c in out for c in ("crd_grd", "dur", "remaining_days", "mat_dt", "bd_ofr_tcd", "bd_intp_tcd")) and "AS 구조" in out
    # 트리거 없으면 불개입 · 집계 불개입
    assert ensure_risk_factor_columns(_Q1_SQL, "에코프로 채권 표면금리 높은 순", ctx) == (_Q1_SQL, False)
    agg = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE crd_grd = 'BBB+'"
    assert ensure_risk_factor_columns(agg, "BBB+ 채권 몇 개야? 위험요인도", ctx) == (agg, False)


def test_risk_profile_paragraph_for_ecopro_bm(ctx):
    """#1 정답행(에코프로비엠 신종자본증권 7-2) — 문단에 1등급·BBB+ 투자적격·영구채(콜 개시일)·사모가 데이터 값으로만 들어간다."""
    from src.runtime.pipeline import (ensure_risk_factor_columns, ensure_bond_identity_columns, _bond_list_answer,
                                      _risk_profile_spec)
    sql, _ = ensure_risk_factor_columns(_Q1_SQL, _Q1, ctx)
    sql, _ = ensure_bond_identity_columns(sql)
    rows, n = _run_rows(sql)
    ans = _bond_list_answer(sql, rows, n, _Q1)
    assert ans and "에코프로비엠 신종자본증권 7-2" in ans and "위험요인:" in ans
    assert "매우높은위험(1등급)" in ans and "BBB+" in ans and "투자적격" in ans
    assert "콜 개시일" in ans and "사모 발행" in ans
    assert _risk_profile_spec(ctx)["closing"] in ans
    assert "원금 손실" not in ans and "전망" not in ans.replace("업황·전망은 데이터에 없어", "")   # 일반론 금지


def test_risk_profile_limits_rows_and_esg_note(ctx):
    """#5 — 30행 목록: 문단은 상위 max_rows 까지, ESG 표기 기준 고지가 꼬리에 붙는다."""
    from src.runtime.pipeline import ensure_risk_factor_columns, _bond_list_answer, _risk_profile_spec, ESG_LABEL_NOTE
    q = "최근 6개월 안에 발행된 녹색채권·ESG 채권 중 발행액 큰 순으로 정리하고 위험요인도 알려줘"
    sql = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, pd_pbcm, isu_bal_amt, pd_risk_gcd, pd_risk_nm, srfc_irt, MAX(bd_tisu_a) AS bd_tisu_a "
           "FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND ((pd_nm LIKE '%(녹)%' OR pd_nm LIKE '%(지)%' OR pd_nm LIKE '%(사)%') "
           "AND isu_dt BETWEEN 20260224 AND 20260824 AND isu_dt > 0) GROUP BY pd_no ORDER BY MAX(bd_tisu_a) DESC LIMIT 30")
    sql, fixed = ensure_risk_factor_columns(sql, q, ctx)
    assert fixed
    rows, n = _run_rows(sql)
    assert n == 30
    ans = _bond_list_answer(sql, rows, n, q)
    assert ans and ans.count("위험요인:") == int(_risk_profile_spec(ctx)["max_rows"])
    assert ESG_LABEL_NOTE in ans and "상위 5개 종목까지" in ans
    assert "전체 336종목" in ans


def test_bond_answer_notes_for_hcx_path(ctx):
    """#2 — HCX 산문에 '발행사명 기준' 이 없으면 기계로 덧붙일 고지를 낸다 · 이미 있으면 내지 않는다."""
    from src.runtime.pipeline import bond_answer_notes, ensure_grade_rank_sort, GRADE_SORT_NOTE
    sql, _ = ensure_grade_rank_sort(_Q2_SQL, _Q2)
    notes = bond_answer_notes(sql, "SK에코플랜트186-1 신용등급 A- …")
    assert any("발행사명이 SK" in x for x in notes) and GRADE_SORT_NOTE in notes
    assert bond_answer_notes(sql, "발행사명이 SK 로 시작하는 발행사 기준 … " + GRADE_SORT_NOTE) == []
    assert bond_answer_notes("SELECT pd_no FROM domestic_bonds WHERE pd_nm LIKE '%(녹)%'", "녹색채권 3종목") == [
        "ESG 채권 여부는 종목명의 표기(녹=녹색채권 · 사=사회적채권 · 지=지속가능채권) 기준입니다."]


# ── P10. 0행 사유 — 이름 LIKE OR 그룹의 한국어화 ─────────────────────────────────

def test_humanize_like_or_group():
    from src.runtime.guard import _humanize_cond
    assert _humanize_cond("(pd_nm LIKE '%우주항공%' OR pd_nm LIKE '%Space%')") == "상품명에 '우주항공'·'Space' 중 하나 포함"
    assert _humanize_cond("(pd_nm LIKE '%우주항공%' OR pd_pbcm LIKE '%방산%')") is None       # 컬럼이 섞이면 종전대로
    assert _humanize_cond("(crd_grd = 'AAA' OR pd_risk_gcd = '16')") is None


# ── P1. KG — 정본 법인(Sec_m) ↔ 채권 발행사(Org_issuer) closure ────────────────────

def test_closure_links_master_to_bond_issuer(ctx):
    """정본 30 중 채권 발행사 법인 키 일치 2(에코프로·에코프로비엠)가 closure 후손으로 들어온다."""
    assert "Org_issuer_d52728ad91" in ctx.kg_closure["Sec_m_ecopro_bm"]
    assert "Org_issuer_3a48b4e41a" in ctx.kg_closure["Sec_m_ecopro"]
    assert "Sec_kr_247540" in ctx.kg_closure["Sec_m_ecopro_bm"]                     # 주식 후손은 그대로


def test_bond_subsidiary_question_grounds_to_subsidiary_issuer(ctx):
    """#1 — '에코프로 자회사가 발행한 채권' 은 자회사 발행사 (주)에코프로비엠 의 pd_pbcm 값으로 접지된다(종전엔 본체만)."""
    r = answer_question("H5-01", _Q1, planner=_BondProbe(), ctx=ctx)
    assert "Sec_m_ecopro" in r.think_trace
    assert "(주)에코프로비엠" in r.grounding and "pd_pbcm" in r.grounding
    assert "ext_etf_holdings" not in r.grounding                                     # 채권 대상 — 주식 alias 는 싣지 않는다


def test_etf_subsidiary_grounding_unchanged(ctx):
    """ETF 쪽 회귀 — 자회사 편입 ETF 질의의 접지에 채권 발행사 alias 가 섞이지 않는다(test_closure 와 같은 단언)."""
    class _EtfProbe(_BondProbe):
        def plan_sql(self, question, grounding):
            return "SELECT 1 AS one FROM domestic_etfs LIMIT 1"
    r = answer_question("H5-01e", "에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품", planner=_EtfProbe(), ctx=ctx)
    assert "'에코프로비엠'" in r.grounding and "pd_pbcm" not in r.grounding


# ── 종단(오프라인) — 서버가 낸 SQL 을 플래너 자리에 놓고 가드 체인 + 조립기를 통째로 태운다 ─────

class _FixedSql(_BondProbe):
    def __init__(self, sql):
        self._sql = sql

    def plan_sql(self, question, grounding):
        return self._sql

    def compose_answer(self, question, rows, *a, **k):
        return "HCX-산문(오프라인 대체)"


def test_e2e_q1_subsidiary_top_coupon_risk(ctx):
    """#1 종단 — 자회사 접지 뒤 HCX 가 두 발행사 IN 으로 SQL 을 내면, 종목명·위험요인 문단이 기계로 붙은 답이 나간다."""
    sql = ("SELECT domestic_bonds.pd_pbcm, domestic_bonds.srfc_irt, domestic_bonds.pd_risk_gcd FROM domestic_bonds "
           "WHERE TRIM(domestic_bonds.pd_pbcm) IN ('(주)에코프로', '(주)에코프로비엠') AND curr_cd = 'KRW' AND mat_dt >= 20260824 "
           "ORDER BY domestic_bonds.srfc_irt DESC LIMIT 1")
    r = answer_question("H5-01x", _Q1, planner=_FixedSql(sql), ctx=ctx)
    assert "에코프로비엠 신종자본증권 7-2" in r.answer and "위험요인:" in r.answer and "6.638" in r.answer
    assert "매우높은위험(1등급)" in r.answer and "BBB+" in r.answer and "콜 개시일" in r.answer
    assert "종목 식별 컬럼 보장" in r.think_trace and "위험요인 재료 컬럼 보장" in r.think_trace


def test_e2e_q2_lowest_grade_three(ctx):
    """#2 종단 — 서버가 낸 SQL(IN 날조 + 문자열 정렬)이 체인을 지나면 BBB-·BBB0·BBB+ 순으로 나가고 고지가 붙는다."""
    sql = ("SELECT pd_no, TRIM(pd_nm) AS 상품명, TRIM(crd_grd) AS 신용등급, TRIM(pd_risk_gcd) AS 위험등급, TRIM(pd_pbcm) AS 발행기관, "
           "dur AS 듀레이션, remaining_days AS 잔존일수, applied_yield AS 수익률 FROM domestic_bonds "
           "WHERE std_pd_mcls_nm = '회사채' AND pd_pbcm LIKE '%SK%' AND crd_grd IN ('A-', 'BBB-', 'BB+') ORDER BY crd_grd ASC LIMIT 3")
    r = answer_question("H5-02x", _Q2, planner=_FixedSql(sql), ctx=ctx)
    a = r.answer
    rows = [l for l in a.splitlines() if l[:2] in ("1.", "2.", "3.")]
    assert len(rows) == 3 and "BBB-" in rows[0] and "BBB0" in rows[1] and "BBB+" in rows[2], rows
    assert "신용등급 낮은 순" in a and "발행사명이 SK" in a and a.count("위험요인:") == 3 and "위험등급 14" not in a
    assert "신용등급 서열 정렬" in r.think_trace and "SELECT 별칭 정규화" in r.think_trace


def test_e2e_q5_esg_list_with_risk(ctx):
    """#5 종단 — 336종목 · 총발행액순 · ESG 표기 기준 고지 · 상위 5행 위험요인 문단."""
    q = "최근 6개월 안에 발행된 녹색채권·ESG 채권 중 발행액 큰 순으로 정리하고 위험요인도 알려줘"
    sql = ("SELECT pd_nm, pd_pbcm, isu_bal_amt, pd_risk_gcd, pd_risk_nm, srfc_irt, MAX(bd_tisu_a) AS bd_tisu_a FROM domestic_bonds "
           "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND ((pd_nm LIKE '%(녹)%' OR pd_nm LIKE '%(지)%' OR pd_nm LIKE '%(사)%') "
           "AND isu_bal_amt IS NOT NULL AND isu_dt BETWEEN 20260224 AND 20260824 AND isu_dt > 0) GROUP BY pd_no ORDER BY MAX(bd_tisu_a) DESC LIMIT 30")
    r = answer_question("H5-05x", q, planner=_FixedSql(sql), ctx=ctx)
    a = r.answer
    assert "전체 336종목" in a and "총발행액 많은 순" in a and "종목명의 표기" in a
    assert a.count("위험요인:") == 5 and "발행사의 재무 상태" in a
