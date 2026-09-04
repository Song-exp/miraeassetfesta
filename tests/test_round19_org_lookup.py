# -*- coding: utf-8 -*-
"""19R — 개별 펀드의 운용사·수탁사 (2026-09-04 KG-006).

펀드 질문 중 가장 기본이고 PDF §1.2 가 한 절을 쓴 축인데 두 회차 모두 완전 실패했다.
이 질의는 **SQL 만으로 풀 수 없다**:

    운용사 이름   ext_fund_page.mgmt_co_nm (65종)
    수탁사 이름   🔴 어느 컬럼에도 없다 — 마스터엔 코드(trusc_xtn_itt_cd)뿐, 이름은 KG 에만 (48노드)

그래서 HCX 가 매번 없는 컬럼을 지어냈다(mtco_nm·trusc_nm → 스키마 기각 → 재생성도 같은 실수 →
오거절). 답은 코드를 고르고 답변 층이 KG 이름으로 옮기는 것이다.
"""
import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question, ensure_fund_org_lookup

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

BAD = ("SELECT DISTINCT mtco_nm, trusc_nm FROM ext_fund_page WHERE itm_no IN "
       "(SELECT itm_no FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
       "AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%') LIMIT 30")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


class _NoHCX:
    def plan_sql(self, q, g):
        return BAD

    def compose_answer(self, q, rows, answer_rules=""):
        return "ROWS:\n" + rows


def test_builds_code_columns_from_broken_sql():
    out, fired = ensure_fund_org_lookup(BAD, "미래에셋코어테크 펀드의 운용사와 수탁사는 어디야?", "미래에셋코어테크")
    assert fired
    assert "or_co_xtn_itt_cd" in out and "trusc_xtn_itt_cd" in out
    assert "mtco_nm" not in out and "trusc_nm" not in out
    assert "FROM public_funds" in out


@pytest.mark.parametrize("q, token, why", [
    ("공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘", None, "집계 질의 — 상품 고유명이 없다"),
    ("수탁사가 국민은행인 공모펀드는 몇 개야?", None, "개수 질의"),
    ("미래에셋코어테크 펀드 순자산 알려줘", "미래에셋코어테크", "기관을 묻지 않는다"),
    ("미래에셋코어테크 펀드의 수탁사는 몇 곳이야?", "미래에셋코어테크", "개수 어휘가 있으면 불개입"),
])
def test_no_touch(q, token, why):
    assert ensure_fund_org_lookup(BAD, q, token) == (BAD, False), why


def test_end_to_end_names_come_from_kg(ctx):
    """🔴 수탁사 이름은 어느 컬럼에도 없다 — KG 가 옮겨야만 나온다."""
    r = answer_question("KG-006", "미래에셋코어테크 펀드의 운용사와 수탁사는 어디야?", planner=_NoHCX(), ctx=ctx)
    assert "기관 조회 확정식" in r.think_trace
    ans = r.answer or ""
    assert "미래에셋자산운용" in ans and "신한은행" in ans, ans
    assert "00080008" in ans and "00020088" in ans, "코드 병기가 사라졌다"
