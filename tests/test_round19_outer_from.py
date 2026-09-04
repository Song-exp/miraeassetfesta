# -*- coding: utf-8 -*-
"""19R — 가드 전제가 부질의 안의 FROM 을 보고 발동하던 자리 (2026-09-04 KG-006).

"미래에셋코어테크 펀드의 운용사와 수탁사는 어디야?" — 펀드 질문 중 가장 기본인데 완전 실패했다.
원인은 HCX 가 아니라 **가드였다**:

    SELECT … FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE …)

종전 전제가 "from public_funds" 를 아무 데서나 찾는 검색이라 부질의 안의 것을 보고 개별 조회
묶기 가드가 발동했고, 바깥 SELECT 에 public_funds 컬럼(sale_yn·rptt_ksd_itm_no·
or_co_xtn_itt_cd·mtco_itm_no)을 주입했다. 그 컬럼들은 ext_fund_page 에 없어 **가드가 만든
SQL 이 기각당했다** — 재생성도 같은 실패로 오거절.

가드들은 예외 없이 바깥 SELECT/WHERE 를 고치므로 판정도 바깥 FROM 이어야 한다.
"""
import pytest

from src.runtime.pipeline import _FUND_TBL, ensure_fund_lookup_grouping

BROKEN = ("SELECT itm_no, itm_nm, sale_yn FROM ext_fund_page "
          "WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%')")


@pytest.mark.parametrize("sql, expected, why", [
    ("SELECT a FROM public_funds WHERE x=1", True, "바깥 FROM 이 마스터"),
    (BROKEN, False, "🔴 부질의 안에만 있으면 발동하면 안 된다"),
    ("SELECT a FROM public_funds WHERE b IN (SELECT c FROM ext_fund_page)", True, "바깥이 마스터면 부질의는 무관"),
    ("select a FROM PUBLIC_FUNDS p", True, "대소문자 무시"),
    ("SELECT a FROM domestic_bonds", False, "다른 마스터"),
])
def test_outer_from_only(sql, expected, why):
    assert bool(_FUND_TBL.search(sql)) is expected, why


def test_lookup_grouping_does_not_fire_on_ext_from():
    """가드가 자기 템플릿을 못 쓰는 SQL 에 손대지 않는다 — 깨진 SQL 을 만들면 안 된다."""
    out, fixed = ensure_fund_lookup_grouping(BROKEN, "미래에셋코어테크 펀드의 운용사와 수탁사는 어디야?")
    assert (out, fixed) == (BROKEN, False)
    for col in ("sale_yn", "rptt_ksd_itm_no", "or_co_xtn_itt_cd", "mtco_itm_no"):
        assert out.count(col) == BROKEN.count(col), f"{col} 을 바깥 SELECT 에 주입했다"
