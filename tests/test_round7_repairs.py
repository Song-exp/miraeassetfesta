# -*- coding: utf-8 -*-
"""7R 수리 회귀 — 재검 §③(M′·R′·S′·P′·B-4′) + KG §③(G1~G7). 간섭 지도: docs/recheck_2026-09-02_round7_plan.md

SQL 은 전부 6R 실측 원문(eval/probe_recheck_2026-09-02_r6*.json)이다 — 문항별 예외가 아니라
"HCX 가 그 모양을 냈을 때 결정층이 무엇을 하는가" 를 고정한다.
"""
import re

import pytest

from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── 뿌리③+④ — 답변 표면 규약 (S′ 뒤 · G4 · B-4′ · B-5) ──

def test_answer_surface_rules(ctx):
    from src.runtime import pipeline as P

    # ① B-4′ — 대체 표시 열이 없으면 원 단위 금액을 숨기지 않는다 (6R Y16: overseas_etfs 는 억원 병기 대상 밖)
    y16_sql = ("SELECT TRIM(cu_fund_mgmt_co) AS 운용사, SUM(du_last_aum) AS 총순자산USD FROM overseas_etfs "
               "WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    rows = "운용사 | 총순자산USD\nBlackRock Fund Advisors | 4378085220000.0"
    kept, hidden = P._hide_answer_columns(rows, y16_sql)
    assert not hidden and "4378085220000" in kept, "대체 열이 없는데 값을 숨겼다"

    # ② 억원 열이 있으면 종전대로 원값만 숨긴다 (V7·W10 불변)
    v7_sql = ("SELECT cu_fund_mgmt_co, SUM(du_last_aum) AS total_aum, "
              "CAST(SUM(du_last_aum)/100000000 AS INTEGER) || '억원' AS \"total_aum_억원\" FROM domestic_etfs GROUP BY 1")
    kept2, hidden2 = P._hide_answer_columns("cu_fund_mgmt_co | total_aum | total_aum_억원\n삼성 | 164377105967341 | 1643771억원", v7_sql)
    assert hidden2 == ["total_aum"] and "1643771억원" in kept2

    # ③ 내부 태그 코드는 대체 열과 무관하게 종전대로 숨긴다 (R3 불변)
    _, hidden3 = P._hide_answer_columns("itm_nm | prfd_attr_cds\n펀드 | C101,M109", "SELECT itm_nm, prfd_attr_cds FROM public_funds")
    assert hidden3 == ["prfd_attr_cds"]

    # ④ G4 — 코드 컬럼은 **별칭과 무관하게** 원 컬럼으로 판정하고 이름·기계 표기로 굽는다 (KG-008 날조 차단)
    kg8_sql = ("SELECT trim(trusc_xtn_itt_cd) as 수탁회사명, COUNT(*) as 펀드수 FROM public_funds GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    out, labeled = P.label_code_columns("수탁회사명 | 펀드수\n00050004 | 257\n00020004 | 1656", kg8_sql)
    assert labeled == ["수탁회사명"], labeled
    for ln in out.splitlines()[1:]:
        v = ln.split(" | ")[0]
        assert re.fullmatch(r"(?:코드 \d+\(기관명 미수록\)|.+\(\d+\))", v), v

    # ⑤ G4 — 값이 있는 코드를 숨겨 '부재' 로 서술하게 두지 않는다 (Z23: trusc 코드 00020088 → '수록 안 됨')
    z23_sql = ("SELECT MIN(itm_no) AS 대표_itm_no, MAX(trusc_xtn_itt_cd) AS trusc_xtn_itt_cd FROM public_funds GROUP BY 1")
    out5, labeled5 = P.label_code_columns("대표_itm_no | trusc_xtn_itt_cd\nKR5153450780 | 00020088", z23_sql)
    # 수탁 코드도 kg_alias 에 실재한다(00020088 → 신한은행) — 매핑이 있으면 정본 이름, 없으면 '코드 X(기관명 미수록)'
    assert labeled5 == ["trusc_xtn_itt_cd"] and "00020088" in out5
    assert re.search(r"\S+\(00020088\)|코드 00020088\(기관명 미수록\)", out5), out5

    # ⑥ 이름 컬럼·종목번호는 건드리지 않는다 (과잉 개입 방지)
    _, none = P.label_code_columns("itm_nm | 클래스수\n미래에셋코어테크 | 10", "SELECT itm_nm, COUNT(*) AS 클래스수 FROM public_funds GROUP BY 1")
    assert none == []

    # ⑦ B-5 — 부사가 낀 면책("금융 기관에 **직접** 문의")과 투자권유형 문장을 걷어낸다 (Z21·Z23·Y16)
    z21 = ("죄송합니다. 제공된 데이터에는 정보가 포함되어 있지 않습니다. 해당 정보를 찾기 위해서는 금융 기관에 "
           "직접 문의하시거나, 공식 웹사이트를 참고하시는 것을 추천드립니다.")
    out7, hit7 = P.strip_disclaimer(z21)
    assert hit7 and "문의" not in out7, out7
    y16 = "이들은 대형 자산운용사입니다. 따라서 투자자들은 이러한 운용사의 ETF들을 긍정적으로 검토해볼 수 있을 것입니다."
    out8, hit8 = P.strip_disclaimer(y16)
    assert hit8 and "긍정적으로 검토" not in out8, out8
    # 정상 문장은 살아남는다
    assert P.strip_disclaimer("순자산 상위 3개 운용사입니다.")[1] is False


def test_zero_row_reason_never_leaks_sql(ctx):
    """S′ 뒤 — 0행 문구에 SQL 절 원문(`itm_no IN (…)`·`REPLACE(`·`LIKE '%`)이 절대 실리지 않는다 (6R W11)."""
    from src.runtime.pipeline import _zero_row_reason

    for sql in (
        "SELECT itm_no FROM public_funds WHERE itm_no IN ('030230002D36') AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30",
        "SELECT itm_no FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%존재하지않는펀드명%' AND sale_yn = '판매중' LIMIT 30",
    ):
        txt = _zero_row_reason(sql)
        assert txt
        for tok in ("itm_no", "REPLACE(", "LIKE '%", "IN (", "sale_yn", "SELECT"):
            assert tok not in txt, (tok, txt)


# ── 뿌리② — 펀드 키 컬럼 교정 (S′ 앞) ──

def test_fund_key_column_correction(ctx):
    """6R W11 실측 SQL — `itm_no IN ('030230002D36')` 은 0행. 그 값은 rptt_ksd_itm_no 에만 실재한다."""
    from src.runtime.pipeline import ensure_fund_key_column, _execute

    w11 = ("SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS \"클래스수\", "
           "CAST(SUM(fd_nast_suma)/100000000 AS INTEGER) || '억원' AS \"순자산_억원\" FROM public_funds "
           "WHERE itm_no IN ('030230002D36') AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30")
    fixed, notes = ensure_fund_key_column(w11)
    assert notes and "rptt_ksd_itm_no" in fixed, notes
    assert "MIN(itm_no) AS 대표_itm_no" in fixed, "SELECT 의 같은 컬럼명까지 바꿨다"
    rows, n = _execute(fixed)
    assert n == 1 and "14" in rows and "3,34" not in rows, rows      # 14클래스 · 3,345억
    assert "3345억원" in rows or "3344억원" in rows, rows

    # V4 계열 — 이미 옳은 컬럼을 쓴 SQL 은 불변
    v4 = "SELECT itm_no FROM public_funds WHERE rptt_ksd_itm_no = '030230002D36' LIMIT 30"
    assert ensure_fund_key_column(v4) == (v4, [])
    # 어느 키에도 없는 리터럴은 손대지 않는다 (값 검사·0행 진단에 맡긴다)
    bogus = "SELECT itm_no FROM public_funds WHERE itm_no = 'ZZZNOTAKEY' LIMIT 30"
    assert ensure_fund_key_column(bogus) == (bogus, [])


# ── 뿌리⑤ — precheck 파싱 검사 (G6 · Z13) ──

def test_precheck_parses_sql(ctx):
    """KG 4R G6 — 문법 오류는 실행 전에 잡힌다. 6R Z13: 괄호 불균형이 '검사 통과' 뒤 OperationalError 로 죽었다."""
    from src.runtime.pipeline import validate_sql

    z13 = ("SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' AND prvo_pbff_desc = '공모') "
           "UNION ALL (SELECT COUNT(*) FROM domestic_etfs WHERE cu_fund_mgmt_co = 'KB' AND pd_grp_no = 'ETF') LIMIT 30")
    err = validate_sql(z13)
    assert err and ("괄호" in err or "문법" in err), err

    # 🔴 없는 컬럼은 여기서 기각하지 않는다 — guard.unknown_columns 가 더 나은 사유를 내는 자리다(중복 0)
    assert validate_sql("SELECT itm_no FROM public_funds WHERE zzz_nope = '1' LIMIT 5") is None
    from src.runtime import guard
    assert guard.unknown_columns("SELECT itm_no FROM public_funds WHERE zzz_nope = '1' LIMIT 5", ctx)
    # 정상 SQL 은 통과 (EXPLAIN 드라이런이 무해해야 한다)
    for ok in (
        "SELECT itm_no, itm_nm FROM public_funds WHERE sale_yn = '판매중' LIMIT 30",
        "WITH x AS (SELECT pd_no, applied_yield FROM domestic_bonds) SELECT * FROM x LIMIT 5",
        "SELECT COUNT(*) FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no LIMIT 30",
    ):
        assert validate_sql(ok) is None, (ok, validate_sql(ok))


# ── 뿌리①-A — 묶기 가드 게이트 (M′ · R′) ──

_S4 = ("SELECT DISTINCT itm_no, itm_nm, zrin_fd_ivst_risk_grd_nm, zrin_fd_ivst_risk_gcd FROM public_funds "
       "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%KB차이나%' ORDER BY itm_no ASC LIMIT 30")
_T14 = ("SELECT AVG(fd_nast_suma) as avg_nast_suma, CAST(ROUND((AVG(fd_nast_suma))/100000000.0) AS INTEGER) || '억원' "
        "AS \"avg_nast_suma_억원\" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') "
        "AND REPLACE(itm_nm,' ','') LIKE '%베트남그로스%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30")
_V12 = ("SELECT DISTINCT itm_no, COUNT(*) as class_count FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' "
        "AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY itm_no LIMIT 30")
_W5 = ("SELECT DISTINCT itm_no, COUNT(*) as clas_count FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE "
       "'%미래에셋차이나솔로몬증권투자신탁%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
       "AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2[([]*') "
       "GROUP BY itm_no ORDER BY clas_count DESC LIMIT 30")
_T6 = ("SELECT DISTINCT itm_no, itm_nm, han_clas_nm FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
       "AND REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬증권투자신탁%' "
       "AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]3호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]3[([]*') LIMIT 30")


def _lookup(sql, q):
    from src.runtime.pipeline import ensure_fund_lookup_grouping, _execute, _lookup_answer
    out, ok = ensure_fund_lookup_grouping(sql, q)
    if not ok:
        return None, None
    rows, n = _execute(out)
    return out, _lookup_answer(out, rows, n, None, None)


def test_lookup_grouping_shape_invariant(ctx):
    """M′+R′ — HCX 가 ORDER BY·집계·GROUP BY itm_no 를 붙여도 개별 조회 묶기는 같은 결과를 낸다 (6R S4·T14·V12·W5)."""
    # ① S4 — `ORDER BY itm_no ASC` 를 붙여도 4펀드 9/11/14/3클래스 · 2·2·2·4등급
    _, a = _lookup(_S4, "KB차이나 펀드 위험등급 알려줘")
    assert a and "4개가 조회" in a, a
    for frag in ("클래스 9개", "클래스 11개", "클래스 14개", "클래스 3개", "2등급", "4등급"):
        assert frag in a, (frag, a)
    assert "KB차이나그로스" in a                                   # 6R 은 이 펀드를 통째로 누락했다

    # ② T14 — `AVG(fd_nast_suma)` 를 써도 SUM 으로 되굽는다: 4펀드 2,528/766/769/183억 ("212억원" 아님)
    _, b = _lookup(_T14, "한국투자베트남그로스 펀드 순자산 알려줘")
    assert b and "212억원" not in b, b
    for frag in ("2,528억원", "766억원", "769억원", "183억원"):
        assert frag in b, (frag, b)

    # ③ V12 — `GROUP BY itm_no` 는 클래스 단위 키라 항상 교체 대상. 본체 10클래스
    _, c = _lookup(_V12, "미래에셋코어테크 펀드는 클래스가 몇 개야?")
    assert c and "미래에셋코어테크증권자투자신탁(주식): 클래스 10개" in c, c
    assert "총 30개" not in c and ":  ·" not in c

    # ④ W5 — 총 7개 (6R 은 "1개")
    _, d = _lookup(_W5, "미래에셋차이나솔로몬증권투자신탁 2호는 클래스가 몇 개야?")
    assert d and "클래스 7개" in d, d

    # ⑤ 불개입 유지 — GROUP BY 없는 클래스 열거(T6, 동결선 ✅) · 값 컬럼 랭킹 · 보수 질의 · 전체 개수 집계
    from src.runtime.pipeline import ensure_fund_lookup_grouping as f
    assert not f(_T6, "미래에셋차이나솔로몬증권투자신탁 3호는 클래스가 몇 개야?")[1]
    rank = _S4.replace("ORDER BY itm_no ASC", "ORDER BY fd_yr1_ern_r DESC")
    assert not f(rank, "KB차이나 펀드 수익률 높은 순")[1]
    assert not f(_S4, "KB차이나 펀드 클래스별 총보수 알려줘")[1]
    cnt = ("SELECT COUNT(*) FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%피델리티%' "
           "AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30")
    assert not f(cnt, "피델리티 이름이 들어간 공모펀드는 몇 개야?")[1]
    # 멱등 — 이미 펀드키로 묶인 SQL 은 다시 묶지 않는다
    out, _ = f(_S4, "KB차이나 펀드 위험등급 알려줘")
    assert not f(out, "KB차이나 펀드 위험등급 알려줘")[1]


# ── 뿌리①-B — 기본모수 사후조건 (G1 · F6′ 일부 보류) ──

def test_base_population_post_chain(ctx):
    """G1 — 기본모수 주입은 SQL 모양과 무관하다. 6R KG-018: HCX 원 SQL 에 정렬·집계가 없어 초기 가드를 건너뛴 뒤
    목록 묶기가 ORDER BY·COUNT 를 붙여 판매완료 포함 모수(96펀드/427클래스)로 나갔다."""
    from src.runtime.pipeline import ensure_fund_base_population as f, answer_question

    # 모양 조건(ORDER BY·집계) 없는 SQL — 초기 호출은 종전대로 건너뛰고, 사후조건(post)은 주입한다
    plain = "SELECT DISTINCT itm_no, itm_nm FROM public_funds WHERE prvo_pbff_desc = '공모' LIMIT 30"
    assert f(plain, "단위형이면서 개방형인 공모펀드도 있어?")[1] is False
    out, ok = f(plain, "단위형이면서 개방형인 공모펀드도 있어?", post=True)
    assert ok and "sale_yn = '판매중'" in out and out.count("prvo_pbff_desc") == 1
    assert f(out, "q", post=True)[1] is False                       # 멱등

    # 🟡 개별 조회는 사후조건에서 건드리지 않는다 (F6′ 보류 — 동결선 W5·X18 이탈)
    lookup = ("SELECT DISTINCT itm_no, itm_nm FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 30")
    assert f(lookup, "미래에셋코어테크 펀드 알려줘", post=True)[1] is False
    # JOIN 의 `ON e.itm_no = p.itm_no` 는 개별 조회의 키 핀이 아니다 — 사후조건이 꺼지면 안 된다
    joined = ("SELECT itm_nm, estb_dt FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
              "WHERE prvo_pbff_desc = '공모' LIMIT 30")
    assert f(joined, "설정일이 오래된 공모펀드", post=True)[1] is True

    # 전 체인 — KG-018 실측 SQL 이 판매중 모수를 얻는다
    class P:
        def plan_sql(self, q, g):
            return ("SELECT DISTINCT itm_no, itm_nm, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' "
                    "AND han_clas_policies LIKE '%폐쇄형%' LIMIT 30")

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-KG018", "단위형이면서 개방형인 공모펀드도 있어?", planner=P(), ctx=ctx)
    assert "sale_yn = '판매중'" in r.sql and "기본모수 사후조건" in r.think_trace


# ── 뿌리⑥ — 질문이 고른 축의 보존·주입 (P′ · G3) ──

def test_axis_clause_preserved(ctx):
    """Y7 — '주식형' 이 SQL 어디에도 없어 답이 전체 랭킹(V5)과 바이트 단위로 같았다. 확정식은 없으면 주입한다."""
    from src.runtime.pipeline import ensure_fund_type_axis as f, answer_question

    base = ("SELECT e.mgmt_co_nm, SUM(p.fd_nast_suma) AS total FROM public_funds p "
            "LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    out, ok = f(base, "주식형 펀드 순자산이 가장 큰 운용사 3곳 알려줘")
    assert ok and "zrin_btyp_nm = '주식형'" in out
    assert f(out, "주식형 펀드 순자산이 가장 큰 운용사 3곳 알려줘")[1] is False        # 멱등

    # 불개입 — 유형 축이 없는 질의(V5·S11·Y6) · 유형 절이 이미 있음 · 개별 조회 · 보통명사 오탐
    assert f(base, "순자산이 가장 큰 자산운용사 5곳 알려줘")[1] is False
    assert f(base + " ", "순자산이 가장 큰 운용사 상위 3개 알려줘")[1] is False
    have = base.replace("GROUP BY", "WHERE p.zrin_btyp_nm = '해외주식형' GROUP BY")
    assert f(have, "해외주식형 펀드 순자산이 가장 큰 운용사")[1] is False
    lookup = "SELECT itm_nm FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 30"
    assert f(lookup, "미래에셋코어테크 주식형 펀드 알려줘")[1] is False
    # '기타'·'MMF'·'특별자산' 같은 보통명사 값은 확정식 대상이 아니다 ('…형' 3자 이상만)
    assert f(base, "기타 운용사 알려줘")[1] is False

    # 전 체인 — gold: 미래에셋 69,336(142펀드) · NH-Amundi 46,152(28) · 신영 41,914(18)
    class P:
        def plan_sql(self, q, g):
            return base

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-Y7", "주식형 펀드 순자산이 가장 큰 운용사 3곳 알려줘", planner=P(), ctx=ctx)
    for frag in ("69,336억원", "펀드 142개", "46,152억원", "41,914억원"):
        assert frag in r.answer, (frag, r.answer)
    assert "377,707" not in r.answer                     # 6R 은 전체 랭킹(V5)을 그대로 냈다


# ── 뿌리⑦-a — 조회값↔서술 기계 대조 (G5, 단일 집계 갈래) ──

def test_positive_count_not_refused(ctx):
    """G5 — 결과가 비어 있지 않은데 '없음/확인 불가' 로 서술하면 기각한다. 4도메인 공통(종전엔 채권 SQL 만).
    KG 4R X17 실측: `SELECT COUNT(*) FROM public_funds …` 이 7 을 냈는데 "클래스 개수는 확인할 수 없습니다"."""
    from src.runtime.pipeline import answer_question

    x17 = ("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
           "AND REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬%' "
           "AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2[([]*') LIMIT 30")

    class P:
        def plan_sql(self, q, g):
            return x17

        def compose_answer(self, q, rows, answer_rules=""):
            return "제공된 데이터에 따르면 미래에셋차이나솔로몬 2호의 클래스 개수는 확인할 수 없습니다."

    r = answer_question("T-X17", "미래에셋차이나솔로몬 2호는 클래스가 몇 개야?", planner=P(), ctx=ctx)
    assert "확인할 수 없" not in r.answer, r.answer
    assert "7클래스(판매 단위)" in r.answer, r.answer
    assert "집계 오거절 교정" in r.think_trace


# ── 뿌리⑦-b — 설정연도 확정식 (G2 · KG-035 · X19) ──

def test_estb_year_canonical(ctx):
    """G2 — 같은 문형 세 문항이 날짜 절만 달라 답이 갈렸다: Z22(estb_dt 범위) 정답 ↔ KG-035(fd_daily_bas_dt) ↔ X19(estb_dt <=).
    설정일 정본은 ext_fund_page.estb_dt 뿐이고 연도는 [YYYY0101, (YYYY+1)0101) 범위로 확정한다."""
    from src.runtime.pipeline import ensure_fund_estb_year as f, answer_question, _execute

    kg035 = ("SELECT COUNT(*) AS \"클래스수\" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
             "AND fd_daily_bas_dt BETWEEN 20260000 AND 20269999 LIMIT 30")
    out, ok = f(kg035, "2026년에 설정된 공모펀드는 몇 개야?")
    assert ok and "fd_daily_bas_dt" not in out and "estb_dt >= '20260101' AND estb_dt < '20270101'" in out
    assert "20269999" not in out, out          # BETWEEN 을 쪼개다 남긴 껍데기 절

    x19 = ("SELECT COUNT(*) FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
           "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND estb_dt <= 20250930 LIMIT 30")
    out2, ok2 = f(x19, "2025년에 설정된 공모펀드는 몇 개야?")
    assert ok2 and "20250930" not in out2 and "estb_dt >= '20250101'" in out2
    assert f(out2, "2025년에 설정된 공모펀드는 몇 개야?")[1] is False        # 멱등

    # 불개입 — 설정 어휘 없음 · 연도 없음 · 만기 질의(mat_dt 가드 영역)
    assert f(kg035, "2026년 만기 채권 알려줘")[1] is False
    assert f(kg035, "설정된 공모펀드 알려줘")[1] is False

    # 전 체인 — KG-035 39펀드/124클래스 · X19 107/305 (2024년은 Z22 gold 107/287 과 같은 식)
    key = ("COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN "
           "length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) "
           "END, itm_no)) AS \"펀드수\", ")
    for q, s, want in (("2026년에 설정된 공모펀드는 몇 개야?", kg035.replace("SELECT ", "SELECT " + key), ("39개", "124개")),
                       ("2025년에 설정된 공모펀드는 몇 개야?", x19.replace("SELECT COUNT(*)", "SELECT " + key + "COUNT(*) AS \"클래스수\""), ("107개", "305개"))):
        class P:
            def plan_sql(self, qq, g):
                return s

            def compose_answer(self, qq, rows, answer_rules=""):
                return "x"

        r = answer_question("T-G2", q, planner=P(), ctx=ctx)
        assert "ext_fund_page" in r.sql, r.sql
        for frag in want:
            assert frag in r.answer, (q, frag, r.answer)


# ── 뿌리⑦-c — 클래스 표기 축 확정식 (G7 · Z1) ──

def test_class_notation_is_name_suffix(ctx):
    """G7 — '종류A·Ce' 는 수수료체계(han_clas_nm)가 아니라 종목명 접미. DB 전수: han_clas_nm 에 '종류 A' 0건."""
    from src.runtime.pipeline import ensure_fund_class_notation as f, answer_question
    from src.runtime.loader import connect_readonly

    con = connect_readonly()
    try:
        assert con.execute("SELECT COUNT(*) FROM public_funds WHERE TRIM(han_clas_nm) = '종류 A'").fetchone()[0] == 0
    finally:
        con.close()

    z1 = ("SELECT itm_no, itm_nm, bns_bpr FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' "
          "AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND TRIM(han_clas_nm) = '종류 A' LIMIT 30")
    out, ok = f(z1, "미래에셋코어테크 펀드 종류A 기준가 알려줘")
    assert ok and "han_clas_nm" not in out and "LIKE '%종류A'" in out
    assert f(out, "미래에셋코어테크 펀드 종류A 기준가 알려줘")[1] is False      # 멱등
    assert f(z1, "미래에셋코어테크 펀드 A클래스 기준가 알려줘")[1] is True     # 'A클래스' 형도 같은 축

    # 하이픈·공백 무시 — 질문 'Ce' ↔ DB '종류C-e'
    out2, ok2 = f(z1, "미래에셋코어테크 펀드 Ce 클래스 기준가")
    assert ok2 and "LIKE '%종류CE'" in out2.upper()

    # 불개입 — 표기 없음 · DB 에 없는 우연한 영문 토큰('ETF 클래스'·'클래스가 몇 개')
    assert f(z1, "미래에셋코어테크 펀드 기준가 알려줘")[1] is False
    assert f(z1, "미래에셋코어테크 펀드는 클래스가 몇 개야?")[1] is False
    assert f(z1, "ETF 클래스 알려줘")[1] is False

    # 전 체인 — 단일 클래스 값(F2 범위가 저절로 좁혀진다). 본체 종류A 기준가 4,726.41
    class P:
        def plan_sql(self, q, g):
            return z1

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-Z1", "미래에셋코어테크 펀드 종류A 기준가 알려줘", planner=P(), ctx=ctx)
    assert "4,726.41" in r.answer and "클래스에 따라 다름" not in r.answer, r.answer
