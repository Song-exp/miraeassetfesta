# -*- coding: utf-8 -*-
"""라운드35 P0-2 — 되묻기 전제 실측 (사고 #98·#99).

되묻기 문장은 "그 값은 데이터에 없다" 고 **단정한다**. 그 단정을 재보고 말하는지 고정한다.
종전: 0행이면 옆 절 때문이어도 발행사 탓으로 돌려 실재하는 발행사를 '없다' 고 했다(1,818곳 중 1,392곳에서 재현).
"""

import sqlite3

import pytest

from src.runtime import pipeline as P
from src.runtime.loader import db_path

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

KEPCO = "한국전력공사(주)"


def _con():
    return sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)


def test_실재하는_발행사는_없다고_말하지_않는다():
    # #98 재현 SQL — 0행의 원인은 pd_no = 1184 이지 발행사가 아니다(발행사 단독 403행)
    sql = ("SELECT TRIM(pd_nm) AS pd_nm, srfc_irt, applied_yield FROM domestic_bonds "
           f"WHERE TRIM(pd_pbcm) = '{KEPCO}' AND pd_no = 1184 GROUP BY pd_no LIMIT 1")
    assert P._issuer_literal(sql) == KEPCO
    assert P._issuer_clarify_text(P._issuer_literal(sql)) == ""


def test_실재하지_않는_발행사는_종전대로_되묻는다():
    with _con() as con:
        assert con.execute("SELECT COUNT(*) FROM domestic_bonds WHERE TRIM(pd_pbcm) = '삼성전자'").fetchone()[0] == 0
    out = P._issuer_clarify_text("삼성전자")
    assert "데이터에 없습니다" in out and "말씀하신 건가요" in out


def test_발행사_전수_거짓단정_0건():
    """실재하는 발행사에 '없다' 문장이 나가는 곳이 하나도 없어야 한다 (종전 1,392/1,818)."""
    with _con() as con:
        issuers = [r[0] for r in con.execute(
            "SELECT DISTINCT TRIM(pd_pbcm) FROM domestic_bonds "
            "WHERE pd_pbcm IS NOT NULL AND TRIM(pd_pbcm) <> ''")]
    assert len(issuers) > 1000                                    # 모수가 줄면 이 회귀가 헐거워진다
    assert [i for i in issuers if P._issuer_clarify_text(i)] == []


def test_실재하는_ETF_는_자기자신을_대안으로_내밀지_않는다():
    with _con() as con:
        nm = con.execute("SELECT TRIM(pd_abrv_nm) FROM domestic_etfs ORDER BY du_last_aum DESC LIMIT 1").fetchone()[0]
    sql = f"SELECT pd_abrv_nm FROM domestic_etfs WHERE TRIM(pd_abrv_nm) = '{nm}' AND ttl_exp_rate < 0.0 LIMIT 30"
    assert P._suggest_similar_products(sql) == []


def test_실재하지_않는_ETF_는_종전대로_후보를_낸다():
    cand = P._suggest_similar_products(
        "SELECT pd_abrv_nm FROM domestic_etfs WHERE TRIM(pd_abrv_nm) = 'KODEX AI로봇' LIMIT 30")
    assert len(cand) >= 2 and all("KODEX" in c for c in cand)


def test_감싸진_LIKE_리터럴도_공백을_지운다():
    """컬럼만 REPLACE 되고 리터럴은 공백이 남던 자리 — 실측 공백 그대로 0행 / 제거 14행."""
    q = "SELECT 1 FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋 코어테크%' LIMIT 1"
    out, fixed = P.ensure_spaceless_name_match(q)
    assert fixed and "'%미래에셋코어테크%'" in out
    assert P.ensure_spaceless_name_match(out)[0] == out            # 멱등
    with _con() as con:
        assert con.execute(out.replace(" LIMIT 1", "")).fetchone() is not None
    assert P._suggest_similar_products(q) == []                    # 실재하므로 부재를 말하지 않는다
