# -*- coding: utf-8 -*-
"""20R — 클래스 표기가 종목명 접미라는 사실이 세 자리에서 새던 것 (AA24 · DOM-06, 1·2·3차 내리 ❌).

`종류A`·`Ce`·`C-P2` 는 수수료체계(`han_clas_nm`)가 아니라 **종목명 접미**다. 그 확정식은 6R 부터
있었는데 세 가지 이유로 안 걸렸다.

  ① 정규식이 공백을 건너뛰며 붙여 "종류A 3년" 이 `A 3` → `A3` 접미가 없어 통째로 None (AA24)
  ② 표기를 **하나만** 돌려줘 "A클래스와 C클래스 중" 비교가 성립하지 않음 (DOM-06)
  ③ 확정식이 자기 조건을 넣으면서 HCX 의 기존 클래스 조건을 안 걷어 `(A OR C) AND A` = A (DOM-06)
"""
import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import (_class_notations_in_question, _strip_class_nm_predicates,
                                  answer_question, ensure_fund_class_notation, ensure_orderby_in_range)

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── ① 긴 후보가 실패하면 줄여 재시도 ────────────────────────────────────────
@pytest.mark.parametrize("q, expect", [
    ("미래에셋 코어테크 펀드 종류A 3년 수익률 알려줘", ["A"]),      # 🔴 종전엔 'A3' 로 잡혀 None
    ("미래에셋코어테크 펀드는 A클래스와 C클래스 중 어느 쪽이 보수가 낮아?", ["A", "C"]),
    ("미래에셋코어테크 종류Ce 순자산", ["CE"]),
    ("ETF 클래스 알려줘", []),                                  # DB 에 없는 접미는 버린다
])
def test_class_notations(q, expect):
    assert _class_notations_in_question(q) == expect


# ── ③ 형제 조건을 살리고 클래스 술어만 걷는다 ────────────────────────────────
def test_strip_keeps_siblings_inside_parentheses():
    """🔴 괄호 한 덩어리를 통째로 버려 이름·운용사 필터까지 날아갔다(AA24: 모수 344펀드)."""
    expr = ("(REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%' "
            "AND REPLACE(han_clas_nm,' ','') LIKE '%종류A%' "
            "AND TRIM(or_co_xtn_itt_cd) = '00080008')")
    out = _strip_class_nm_predicates(expr)
    assert "미래에셋코어테크" in out and "or_co_xtn_itt_cd" in out
    assert "han_clas_nm" not in out


def test_strip_also_removes_existing_suffix_filter():
    """확정식이 자기 것을 넣기 전에 HCX 의 클래스 접미 조건도 걷는다 — 안 걷으면 교집합이 한쪽만 남는다."""
    expr = "REPLACE(REPLACE(itm_nm,' ',''),'-','') LIKE '%종류A' AND sale_yn = '판매중'"
    out = _strip_class_nm_predicates(expr)
    assert "종류A" not in out and "sale_yn" in out


def test_comparison_question_keeps_both_classes():
    sql = ("SELECT itm_no, han_clas_nm FROM public_funds WHERE "
           "REPLACE(REPLACE(itm_nm,' ',''),'-','') LIKE '%종류A' "
           "AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%' LIMIT 30")
    out, fixed = ensure_fund_class_notation(sql, "미래에셋코어테크 펀드는 A클래스와 C클래스 중 어느 쪽이 보수가 낮아?")
    assert fixed and "LIKE '%종류A'" in out and "LIKE '%종류C'" in out
    assert out.count("LIKE '%종류A'") == 1, "기존 조건이 남아 AND 로 겹쳤다"
    assert "미래에셋코어테크" in out


# ── 위치 ORDER BY 범위 보정 ────────────────────────────────────────────────
@pytest.mark.parametrize("sql, dropped, why", [
    ("SELECT a, b, c FROM public_funds ORDER BY 4 DESC LIMIT 30", [4], "SELECT 3열인데 4번 — 문법 오류"),
    ("SELECT a, b, c FROM public_funds ORDER BY 4 DESC, 2 ASC LIMIT 30", [4], "남은 키가 있으면 그것만"),
    ("SELECT a, b, c FROM public_funds ORDER BY 3 DESC LIMIT 30", [], "정상"),
])
def test_orderby_range(sql, dropped, why):
    out, got = ensure_orderby_in_range(sql)
    assert got == dropped, why
    if dropped and not got == []:
        assert "ORDER BY 4" not in out


def test_dom06_end_to_end(ctx):
    """A(14.35‰)·C(17.55‰) 두 클래스가 모두 조회돼야 비교가 성립한다."""
    sql = ("SELECT DISTINCT itm_no, han_clas_nm, or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r "
           "+ ofwk_trus_rwrd_r AS \"총보수_퍼센트\" FROM public_funds WHERE "
           "REPLACE(REPLACE(itm_nm,' ',''),'-','') LIKE '%종류A' AND TRIM(or_co_xtn_itt_cd) = '00080008' "
           "AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' "
           "AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%' ORDER BY 4 DESC LIMIT 30")

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "ROWS:\n" + rows

    r = answer_question("DOM-06", "미래에셋코어테크 펀드는 A클래스와 C클래스 중 어느 쪽이 보수가 낮아?",
                        planner=P(), ctx=ctx)
    ans = r.answer or ""
    # 값은 % 로 구워져 나온다(‰ 14.35 → 1.435) — `ensure_fee_percent_select` 가 식에 ÷10 을 굽는다
    assert "1.435" in ans and "1.755" in ans, ans     # A 와 C 가 둘 다 있어야 한다
    assert "종류A" in ans and "종류C" in ans, "종목명이 없으면 어느 행이 A 인지 알 수 없다"


def test_aa24_end_to_end(ctx):
    sql = ("SELECT itm_no, TRIM(itm_nm) AS itm_nm, fd_yr3_ern_r FROM public_funds WHERE "
           "prvo_pbff_desc = '공모' AND (REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%' "
           "AND REPLACE(han_clas_nm,' ','') LIKE '%종류A%' AND TRIM(or_co_xtn_itt_cd) = '00080008') LIMIT 30")

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "ROWS:\n" + rows

    r = answer_question("AA24", "미래에셋 코어테크 펀드 종류A 3년 수익률 알려줘", planner=P(), ctx=ctx)
    assert "185.21" in (r.answer or ""), r.answer
