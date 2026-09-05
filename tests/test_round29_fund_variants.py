# -*- coding: utf-8 -*-
"""주최 예시 유형을 펀드 형태로 옮긴 변형 14문항(2026-09-06) — 6건이 무너졌고 규칙으로 닫았다.

FV-1a 되묻기 오폭 → 목록 판정 확장 · FV-1b 위험등급 방향 · FV-2a 개요 다중 펀드 ·
FV-3b/5a/5b 보유종목 JOIN → 펀드 키 IN-부질의(+ 순자산 최상급 확정 랭킹 + 전용 조립기) · 유형 축 해외 확장.
"""

import pytest

from src.runtime.loader import load_context
from src.runtime.pipeline import (_LIST_ASK, _overview_answer, answer_question, ensure_fund_type_axis,
                                  ensure_risk_direction, rewrite_holdings_join)


@pytest.fixture(scope="module")
def ctx():
    return load_context()


class _Fixed:
    def __init__(self, sql): self.sql = sql
    def plan_sql(self, q, g): return self.sql
    def compose_answer(self, q, rows, a=""): return "[HCX]"


# ── FV-1b 위험등급 방향
def test_위험이_낮은_순은_코드_내림차순():
    sql = "SELECT itm_no, zrin_fd_ivst_risk_gcd FROM public_funds ORDER BY zrin_fd_ivst_risk_gcd ASC LIMIT 5"
    out, d = ensure_risk_direction(sql, "현재 판매 중인 원화 공모펀드 중 위험등급이 낮은 순으로 알려줘")
    assert d == "DESC" and "ORDER BY CAST(zrin_fd_ivst_risk_gcd AS INTEGER) DESC" in out


def test_위험이_높은_순은_그대로_오름차순():
    sql = "SELECT itm_no FROM public_funds ORDER BY zrin_fd_ivst_risk_gcd ASC LIMIT 5"
    assert ensure_risk_direction(sql, "위험이 높은 순으로 알려줘") == (sql, None)


# ── FV-1a 목록 판정
@pytest.mark.parametrize("q", ["위험등급 3등급 이상 종목 알려줘", "위험등급 2등급인 펀드 알려줘", "보수 낮은 상품 보여줘"])
def test_조건_붙은_종목_알려줘는_목록(q):
    assert _LIST_ASK.search(q)


def test_브랜드만_있는_속성_질의는_여전히_되묻기_대상():
    assert not _LIST_ASK.search("삼성 펀드 보수 알려줘")


# ── FV-2a 개요 다중 펀드
def test_개요_조립기는_펀드_둘을_나란히():
    rows = ("대표_itm_no | itm_nm | 클래스수 | 운용사코드 | 유형 | 약관분류 | 위험등급 | fd_nast_suma\n"
            "K1 | 미래에셋코어테크증권자투자신탁(주식) 종류A | 10 | 00080008 | 주식형 | 주식형 | 매우 높은 위험 | 734800000000\n"
            "K2 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A | 4 | 00080008 | 주식형 | 주식형 | 매우 높은 위험 | 1400000000")
    out = _overview_answer(rows, "미래에셋코어테크", "")
    assert out and "2개 있습니다" in out and out.count("- 상품명(대표 클래스)") == 2 and "7,348억원" in out


# ── 보유종목 JOIN → 펀드 키 IN-부질의
JOIN_SQL = ("SELECT p.itm_nm, e.class_desc_ko FROM public_funds p "
            "LEFT JOIN ext_fund_holdings f ON f.grp = p.mtco_itm_no AND f.or_co = p.or_co_xtn_itt_cd "
            "LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no "
            "WHERE f.holding_nm IN ('삼성전자') AND p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모' "
            "ORDER BY p.fd_nast_suma DESC LIMIT 1")


def _hits(ctx, word):
    from src.runtime import pipeline as P
    r = answer_question("T", f"{word}를 편입한 공모펀드 알려줘", planner=_Fixed("SELECT 1"), ctx=ctx)
    # hits 는 answer_question 안에서만 있으니 여기선 접지 매핑 결과(SQL 재작성)로 간접 확인한다
    return r


def test_보유종목_JOIN_은_부질의로_바뀌고_JOIN_이_사라진다(ctx):
    r = answer_question("FV-5b", "삼성전자를 편입한 공모펀드 중 순자산이 가장 큰 상품의 위험등급과 보수 알려줘",
                        planner=_Fixed(JOIN_SQL), ctx=ctx)
    assert "펀드 키 IN-부질의" in r.think_trace and "확정 랭킹" in r.think_trace
    assert "join" not in r.sql.lower().replace("ext_fund_holdings h", "")      # 바깥 문장에 JOIN 없음
    assert "TRIM(h.grp) FROM ext_fund_holdings h" in r.sql
    assert r.answer.startswith("'삼성전자' 을(를) 편입한 공모펀드는 전체")
    assert "위험등급" in r.answer and "총보수(대표 클래스 최저)" in r.answer and "%" in r.answer


def test_위험요인_질문엔_서술_부재_고지(ctx):
    r = answer_question("FV-5a", "에코프로의 자회사를 편입한 공모펀드 중 순자산이 큰 상품의 위험요인 알려줘",
                        planner=_Fixed(JOIN_SQL.replace("'삼성전자'", "'에코프로'")), ctx=ctx)
    assert "위험요인 서술" in r.answer and "위험등급" in r.answer
    assert "8억원" not in r.answer                                   # bare 컬럼 억원 열의 임의 클래스 값이 아니다


def test_보유종목표가_FROM_이면_펀드_확정_목록으로_넘겨받는다(ctx):
    raw = ("SELECT h.holding_nm, h.weight_pct FROM ext_fund_holdings h WHERE h.itm_no = (SELECT h2.itm_no FROM ext_fund_holdings h2 "
           "JOIN public_funds p ON h2.grp = p.mtco_itm_no AND h2.or_co = p.or_co_xtn_itt_cd WHERE p.sale_yn = '판매중' "
           "AND ',' || prfd_attr_cds || ',' LIKE '%,CHN,%' AND p.prvo_pbff_desc = '공모' AND p.zrin_btyp_nm = '주식형' LIMIT 1) LIMIT 30")
    r = answer_question("FV-3b", "캠브리콘이 편입된 중국 주식형 공모펀드를 알려줘", planner=_Fixed(raw), ctx=ctx)
    assert "펀드 확정 목록" in r.think_trace and "[Execute]" in r.think_trace
    assert "0행" not in r.think_trace.split("[Execute]")[-1][:12]
    assert "해외주식형" in r.answer and "'캠브리콘' 을(를) 편입한 공모펀드는 전체" in r.answer


def test_편입_어휘가_없으면_불개입(ctx):
    class H: pass
    assert rewrite_holdings_join(JOIN_SQL, "삼성전자 관련 펀드 순자산 알려줘", ctx, []) == (JOIN_SQL, None)


# ── 유형 축 해외 확장
def test_중국_주식형은_주식_계열_LIKE():
    sql = "SELECT itm_no FROM public_funds WHERE sale_yn = '판매중' AND ',' || prfd_attr_cds || ',' LIKE '%,CHN,%' LIMIT 30"
    out, fixed = ensure_fund_type_axis(sql, "캠브리콘이 편입된 중국 주식형 공모펀드를 알려줘")
    assert fixed and "zrin_btyp_nm LIKE '%주식형'" in out


def test_국내_주식형은_등호_그대로():
    sql = "SELECT itm_no FROM public_funds WHERE sale_yn = '판매중' LIMIT 30"
    out, fixed = ensure_fund_type_axis(sql, "삼성전자가 편입된 국내 주식형 공모펀드를 알려줘")
    assert fixed and "zrin_btyp_nm = '주식형'" in out
