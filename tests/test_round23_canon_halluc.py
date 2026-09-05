"""확정식이 축을 이미 심었으면 남은 환각 컬럼 절은 정보가 0이다 — 지우고 실행한다.

Z10·KG-018 실측: 유형 축 주입/속성 태그 확정식이 정답 필터를 넣었는데
HCX 가 asset_class·fund_type·fd_open_itt_cd 같은 없는 컬럼을 함께 써서
재생성 뒤에도 기각 → 거절. 확정식이 발동했으면 모수가 넓어질 수 없으므로 지운다.
"""

import pytest

from src.runtime.loader import load_context
from src.runtime.pipeline import drop_hallucinated_column_conjuncts


@pytest.fixture(scope="module", autouse=True)
def _schema():
    """_COLUMNS_OF 는 컨텍스트 적재가 채운다 — 없으면 함수가 손을 떼서 테스트가 통과처럼 보인다."""
    load_context()


def test_확정식이_섰으면_환각절을_지운다():
    sql = ("SELECT COUNT(*) FROM public_funds "
           "WHERE zrin_ptn_nm = '인도주식' AND asset_class = '해외주식형' AND fund_type = '공모'")
    out, dropped = drop_hallucinated_column_conjuncts(sql, canon_fired=True)
    assert "asset_class" not in out and "fund_type" not in out
    assert "zrin_ptn_nm = '인도주식'" in out
    assert len(dropped) == 2


def test_확정식이_없으면_리터럴이_겹칠_때만_지운다():
    """모수가 넓어지는 제거는 하지 않는다 — 거절이 오답보다 낫다."""
    sql = "SELECT COUNT(*) FROM public_funds WHERE asset_class = '해외주식형'"
    out, dropped = drop_hallucinated_column_conjuncts(sql, canon_fired=False)
    assert out == sql and not dropped


def test_확정식이_서도_문장은_망가지지_않는다():
    sql = ("SELECT itm_nm FROM public_funds "
           "WHERE ','||prfd_attr_cds||',' LIKE '%,C102,%' AND fd_open_itt_cd = 100 "
           "ORDER BY nast_tamt DESC")
    out, _ = drop_hallucinated_column_conjuncts(sql, canon_fired=True)
    assert "fd_open_itt_cd" not in out
    assert "ORDER BY nast_tamt DESC" in out
    assert " AND  AND " not in out and "WHERE AND" not in out.replace("  ", " ")


def test_성한_컬럼이_같은_OR_그룹에_있으면_가지만_걷는다():
    """🔴 6차 회귀: 확정식 필터와 환각 컬럼이 한 OR 그룹에 묶여 그룹째 사라졌고
    남은 조건이 sale_yn 뿐이라 답이 전체 모수(4,428펀드)로 나갔다."""
    sql = ("SELECT itm_no FROM public_funds WHERE sale_yn = '판매중' "
           "AND (','||prfd_attr_cds||',' LIKE '%,C102,%' OR fd_mdfy_itt_cd = 400) LIMIT 30")
    out, dropped = drop_hallucinated_column_conjuncts(sql, canon_fired=True)
    assert "prfd_attr_cds" in out, "확정식이 심은 필터가 사라지면 모수가 전체로 넓어진다"
    assert "fd_mdfy_itt_cd" not in out
    assert dropped == ["fd_mdfy_itt_cd 가지"]


def test_환각만_든_OR_그룹은_통째로_걷는다():
    sql = ("SELECT itm_no FROM public_funds WHERE sale_yn = '판매중' "
           "AND (asset_class = 'A' OR fund_type = 'B') LIMIT 30")
    out, dropped = drop_hallucinated_column_conjuncts(sql, canon_fired=True)
    assert "asset_class" not in out and "fund_type" not in out
    assert "sale_yn = '판매중'" in out


def test_알려진_컬럼_술어가_한_개도_줄지_않는다():
    """불변식 — 걷기 전후로 성한 컬럼의 등장 횟수가 유지된다."""
    import re
    sql = ("SELECT itm_no FROM public_funds WHERE sale_yn = '판매중' "
           "AND (','||prfd_attr_cds||',' LIKE '%,C102,%' OR fd_mdfy_itt_cd = 400) "
           "AND zrin_btyp_nm = '주식형' AND asset_class = 'X' LIMIT 30")
    out, _ = drop_hallucinated_column_conjuncts(sql, canon_fired=True)
    for col in ("sale_yn", "prfd_attr_cds", "zrin_btyp_nm"):
        assert len(re.findall(col, out)) == len(re.findall(col, sql)), col
