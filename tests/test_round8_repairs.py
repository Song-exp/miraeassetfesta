# -*- coding: utf-8 -*-
"""8R 수리 회귀 — docs/recheck_2026-09-03_round8_plan.md 항목별.

각 테스트 = 계획표의 (b) 열에 적은 이름. 실패하면 그 항목의 일반 규칙이 깨진 것이다.
"""
import pytest

from src.runtime import pipeline as P
from src.runtime.loader import db_path

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


# ── 항목 1 · KG 부류 D — Answer 가드 상호 무력화 ────────────────────────────────
KG8_SQL = ("SELECT trim(trusc_xtn_itt_cd) as 수탁회사명, SUM(fd_nast_suma) as 수탁금액, COUNT(*) as 펀드수, "
           "CAST(ROUND((SUM(fd_nast_suma))/100000000.0) AS INTEGER) || '억원' AS \"수탁금액_억원\" "
           "FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
KG8_ROWS = ("수탁회사명 | 수탁금액 | 펀드수 | 수탁금액_억원\n"
            "00020054 | 100 | 714 | 1억원\n00020004 | 90 | 516 | 1억원\n00020027 | 80 | 465 | 1억원")


def test_answer_guards_independent():
    """표기 → 숨김 순서라면 두 가드가 모두 걸린다 (7R 은 숨김이 표기를 무음 종료시켰다)."""
    labeled_rows, labeled = P.label_code_columns(KG8_ROWS, KG8_SQL)
    assert labeled == ["수탁회사명"], labeled
    assert "홍콩상하이" in labeled_rows.splitlines()[1], labeled_rows
    kept, hidden = P._hide_answer_columns(labeled_rows, KG8_SQL)
    assert hidden == ["수탁금액"], hidden
    assert "홍콩상하이" in kept.splitlines()[1], kept          # 표기가 숨김 뒤에도 살아 있다

    # 반대 순서(7R 동작)는 여전히 무음 종료 — 그래서 순서를 뒤집은 것이고, 이제 사유가 남는다
    hidden_first, _ = P._hide_answer_columns(KG8_ROWS, KG8_SQL)
    skip: list = []
    _, none = P.label_code_columns(hidden_first, KG8_SQL, skip)
    assert none == [] and skip, (none, skip)


def test_label_skip_silent_only_when_no_code_column():
    """코드 컬럼이 없으면 스킵 사유를 남기지 않는다 (트레이스 잡음 금지)."""
    skip: list = []
    P.label_code_columns("itm_nm\n미래에셋코어테크", "SELECT itm_nm, COUNT(*) FROM public_funds GROUP BY 1", skip)
    assert skip == []


def test_name_dict_trace():
    """이름 열이 없어 대조 사전이 비면 사유가 남는다 (X18)."""
    skip: list = []
    out, fixes = P.verify_product_names("미래에셋코어텍증권모투자신탁 입니다.",
                                        "mother_fund_names_raw\n미래에셋코어텍증권모투자신탁(주식)", skip)
    assert fixes == [] and skip, (fixes, skip)
