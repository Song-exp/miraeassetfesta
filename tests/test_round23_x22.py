# -*- coding: utf-8 -*-
"""X22 — 집계 GROUP BY 실행 실패와 사라진 뒷질문.

1) `GROUP BY 1` 이 집계 열을 가리키면 SQLite 가 거부한다 → 위치 표기만 걷는다(이름 표기는 불개입).
2) 조건부 집계가 0 이면 **그 역할의 실제 값**을 KG 이름으로 붙인다 — 수탁사 이름은 어느 컬럼에도 없다.
"""

import pytest

from src.runtime.loader import load_context
from src.runtime.pipeline import absent_condition_actual, drop_aggregate_group_by


@pytest.fixture(scope="module", autouse=True)
def _ctx():
    load_context()


def test_집계를_가리키는_위치_group_by_를_걷는다():
    sql = "SELECT COUNT(*) AS a, MAX(x) AS b FROM t WHERE y = 1 GROUP BY 1 ORDER BY 2 ASC LIMIT 30"
    assert "GROUP BY" not in drop_aggregate_group_by(sql).upper()
    assert "ORDER BY 2 ASC LIMIT 30" in drop_aggregate_group_by(sql)


def test_묶음_키를_가리키면_그대로_둔다():
    for sql in ("SELECT nm, COUNT(*) AS c FROM t GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
                "SELECT nm, COUNT(*) FROM t GROUP BY nm LIMIT 5"):
        assert drop_aggregate_group_by(sql) == sql


def test_집계열만_골라_걷는다():
    sql = "SELECT nm, COUNT(*) AS c FROM t GROUP BY 1, 2 LIMIT 10"
    assert drop_aggregate_group_by(sql) == "SELECT nm, COUNT(*) AS c FROM t GROUP BY 1 LIMIT 10"


def test_수탁_조건_0_이면_실제_수탁사를_KG_이름으로_붙인다():
    sql = ("SELECT COUNT(DISTINCT CASE WHEN TRIM(trusc_xtn_itt_cd) = '00020004' "
           "THEN or_co_xtn_itt_cd END) AS n FROM public_funds "
           "WHERE TRIM(or_co_xtn_itt_cd) = '00040035' AND sale_yn = '판매중' "
           "AND prvo_pbff_desc = '공모' LIMIT 30")
    out = absent_condition_actual(sql, "n\n0", 1)
    assert out and "실제 수탁사" in out and "은행" in out
    assert "00020027" in out                       # 코드도 함께 — 이름만으로는 대조가 안 된다


def test_KG_로_이름이_풀리지_않는_컬럼엔_불개입():
    sql = "SELECT COUNT(CASE WHEN zrin_btyp_nm = '주식형' THEN 1 END) AS n FROM public_funds LIMIT 30"
    assert absent_condition_actual(sql, "n\n0", 1) is None
