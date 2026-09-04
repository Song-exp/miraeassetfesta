# -*- coding: utf-8 -*-
"""19R — 외부표 INNER JOIN 이 모수를 조용히 깎던 자리 (2026-09-04 KG-005).

`ext_fund_page` 커버리지는 판매중·공모 8,408/8,969 = 93.7%. INNER JOIN 이면 나머지 561클래스가
사라지는데 답변 어디에도 그 말이 없어 사용자는 모수가 깎인 걸 알 수 없다.

안전성 — ext 컬럼이 WHERE 에 있으면 LEFT 로 바꿔도 결과가 같다(짝 없는 행은 NULL 이라 어떤
비교도 통과하지 못한다). 조건이 없을 때만 달라지고, 그때는 마스터 모수를 지키는 LEFT 가 옳다.
"""
import sqlite3

import pytest

from src.runtime import guard
from src.runtime.loader import db_path

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

J = ("FROM public_funds p {j} ext_fund_page e ON e.itm_no = p.itm_no "
     "WHERE p.sale_yn='판매중' AND p.prvo_pbff_desc='공모' AND REPLACE(p.itm_nm,' ','') LIKE '삼성%'")


def _one(sql):
    con = sqlite3.connect(str(db_path()))
    try:
        return con.execute(sql).fetchone()
    finally:
        con.close()


def test_converts_inner_ext_join():
    out, ch = guard.ensure_ext_left_join("SELECT a FROM public_funds JOIN ext_fund_page ON x=y")
    assert ch == ["ext_fund_page"] and "LEFT JOIN ext_fund_page" in out


@pytest.mark.parametrize("sql, why", [
    ("SELECT a FROM public_funds LEFT JOIN ext_fund_page ON x=y", "이미 LEFT"),
    ("SELECT a FROM ext_fund_page JOIN public_funds ON x=y", "FROM 이 마스터가 아니다"),
    ("SELECT a FROM public_funds JOIN domestic_etfs ON x=y", "ext_* 가 아닌 조인"),
])
def test_no_touch(sql, why):
    assert guard.ensure_ext_left_join(sql) == (sql, []), why


def test_left_restores_the_master_population():
    """INNER 는 모수를 깎고 LEFT 는 지킨다 — 이 차이가 이 가드의 존재 이유다."""
    inner = _one("SELECT COUNT(*) " + J.format(j="JOIN"))[0]
    left = _one("SELECT COUNT(*) " + J.format(j="LEFT JOIN"))[0]
    assert (inner, left) == (868, 906), f"{inner} / {left}"


def test_identical_when_ext_column_filters():
    """🔴 안전성의 근거 — ext 조건이 WHERE 에 있으면 두 조인이 같은 결과를 낸다."""
    w = " AND e.mgmt_co_nm LIKE '삼성%'"
    assert _one("SELECT COUNT(*) " + J.format(j="JOIN") + w) == _one("SELECT COUNT(*) " + J.format(j="LEFT JOIN") + w)


def test_kg033_max_is_unchanged():
    """ORDER BY <ext열> DESC LIMIT 1 — SQLite 는 NULL 을 최소로 보므로 최댓값이 그대로다."""
    q = ("SELECT itm_nm, estb_dt FROM public_funds {j} ext_fund_page "
         "ON ext_fund_page.itm_no = public_funds.itm_no "
         "WHERE sale_yn='판매중' AND (prvo_pbff_desc='공모') ORDER BY estb_dt DESC LIMIT 1")
    assert _one(q.format(j="JOIN")) == _one(q.format(j="LEFT JOIN"))
