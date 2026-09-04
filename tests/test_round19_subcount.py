# -*- coding: utf-8 -*-
"""19R — 부가 조건 집계가 클래스를 세고 단위를 안 밝히던 자리 (2026-09-04 KG-005).

    COUNT(DISTINCT <펀드키>) AS "펀드수", COUNT(*) AS "클래스수",
    SUM(CASE WHEN mgmt_co_nm LIKE '삼성%' THEN 1 ELSE 0 END) as samsung_mgt_cnt
    → 215 | 868 | 868

앞의 두 열은 펀드/클래스를 구분하는데 세 번째만 행(=클래스)을 센다. 별칭도 단위를 말하지 않아
답변이 "삼성자산운용이 운용하는 펀드는 868개" 로 나갔다 — 15R 최다 오답(클래스를 펀드로)의 재발.
"""
import re
import sqlite3

import pytest

from src.runtime.loader import db_path
from src.runtime.pipeline import ensure_fund_unit_subcount

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

KEY = ("printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || "
       "COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) "
       "ELSE substr('0000000' || trim(mtco_itm_no), -7) END, public_funds.itm_no)")
KG005 = (f'SELECT COUNT(DISTINCT {KEY}) AS "펀드수", COUNT(*) AS "클래스수", '
         "SUM(CASE WHEN mgmt_co_nm LIKE '삼성%' THEN 1 ELSE 0 END) as samsung_mgt_cnt "
         "FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
         "WHERE prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '삼성%' AND sale_yn = '판매중' LIMIT 30")


def test_splits_subcount_into_fund_and_class():
    out, fixed = ensure_fund_unit_subcount(KG005)
    assert fixed
    assert '"samsung_mgt_cnt_펀드수"' in out and '"samsung_mgt_cnt_클래스수"' in out
    assert "COUNT(DISTINCT CASE WHEN" in out


def test_executes_and_units_differ():
    """실행해서 두 값이 실제로 갈리는지 — 갈리지 않으면 이 가드는 의미가 없다."""
    out, _ = ensure_fund_unit_subcount(KG005)
    con = sqlite3.connect(str(db_path()))
    try:
        cur = con.execute(out)
        row = dict(zip([d[0] for d in cur.description], cur.fetchone()))
    finally:
        con.close()
    assert row["samsung_mgt_cnt_클래스수"] == 868
    assert row["samsung_mgt_cnt_펀드수"] == 215
    assert row["samsung_mgt_cnt_펀드수"] < row["samsung_mgt_cnt_클래스수"], "펀드 수가 클래스 수보다 커질 수 없다"


def test_key_is_taken_from_the_sql_so_joins_stay_qualified():
    """펀드키를 SQL 의 `펀드수` 열에서 그대로 떼어 쓴다 — JOIN 이 있어도 수식이 어긋나지 않는다."""
    out, _ = ensure_fund_unit_subcount(KG005)
    inj = re.search(r"COUNT\(DISTINCT CASE WHEN .*? THEN (.*?) END\)", out, re.S).group(1)
    assert "public_funds.itm_no" in inj


@pytest.mark.parametrize("sql, why", [
    ('SELECT COUNT(*) AS a, SUM(CASE WHEN sale_yn=\'판매중\' THEN 1 ELSE 0 END) AS b FROM public_funds',
     "펀드수 열이 없으면 펀드 단위 질의가 아니다"),
    (f'SELECT COUNT(DISTINCT {KEY}) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds',
     "SUM(CASE …) 가 없으면 할 일이 없다"),
])
def test_no_touch(sql, why):
    assert ensure_fund_unit_subcount(sql) == (sql, False), why
