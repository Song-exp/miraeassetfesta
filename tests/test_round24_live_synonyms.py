"""동의어의 치환값은 DB 에 실재하는 표기여야 한다 — 죽은 동의어는 조용한 0행이다.

2026-09-05 최종 전수검사 실측: `신주인수권부사채`·`BW` 의 치환값이 `신주` 였는데
`pd_nm LIKE '%신주%'` 는 **DB 0행**이다. 동의어는 (1) planner_context 의
"사용자 표기 → DB 표기" 줄 (2) 라우팅 어휘 (3) Ground 보조 매칭 키 셋 다에 쓰이므로,
치환값이 죽어 있으면 HCX 가 그 글자로 LIKE 를 써서 "그런 상품이 없습니다" 로 끝난다.
`audit_bonds_rules.py` 가 잡던 불일치 2건이 이것뿐이었다.

이 테스트는 그 한 건을 잡는 특례가 아니라 **부류**를 잡는다 — 채권 동의어 전건의
치환값이 `pd_nm`·`bd_knd` 중 어느 한 곳에서든 실재하는지 DB 로 확인한다.
"""

import pytest

from src.runtime.loader import connect_readonly, load_context

# 동의어의 치환값이 실릴 수 있는 텍스트 컬럼 전부 — 종목명뿐 아니라 종류·이자유형·
# 대분류·발행사까지 봐야 한다(할인채는 bd_intp_tcd, 국공채는 std_pd_mcls_nm, 산은은 pd_pbcm).
_TEXT_COLUMNS = (
    "pd_nm", "bd_knd", "bd_intp_tcd", "bd_inrt_tcd", "bd_ofr_tcd",
    "std_pd_mcls_nm", "std_pd_scls_nm", "pd_pbcm", "pd_risk_nm", "curr_cd",
)

# 값이 아니라 **축(컬럼)** 을 가리키는 치환값 — 스키마 한글명이라 어느 행에도 글자로 남지 않는다.
# 여기에만 면제가 있고, 새 동의어가 값 축이면 자동으로 위 검사에 걸린다.
_AXIS_VALUES = {"듀레이션", "상환일자", "잔존일수", "적용신용등급", "표면이자율"}


@pytest.fixture(scope="module")
def bond_synonyms():
    ctx = load_context()
    return (ctx.enums.get("domestic_bonds") or {}).get("synonyms") or {}


def test_채권_동의어_치환값은_DB에_실재한다(bond_synonyms):
    con = connect_readonly()
    dead = []
    for term, canon in bond_synonyms.items():
        if canon in _AXIS_VALUES:
            continue
        where = " OR ".join(f"TRIM({c}) LIKE ?" for c in _TEXT_COLUMNS)
        n = con.execute(
            f"SELECT COUNT(*) FROM domestic_bonds WHERE {where}",
            tuple(f"%{canon}%" for _ in _TEXT_COLUMNS),
        ).fetchone()[0]
        if n == 0:
            dead.append((term, canon))
    assert not dead, f"치환값이 DB 0행인 동의어: {dead}"


def test_신주인수권부사채는_BW로_치환된다(bond_synonyms):
    """회귀 고정 — '신주' 로 되돌아가면 33행이 다시 0행이 된다."""
    assert bond_synonyms.get("신주인수권부사채") == "BW"
    assert bond_synonyms.get("BW") == "BW"
    con = connect_readonly()
    assert con.execute(
        "SELECT COUNT(*) FROM domestic_bonds WHERE pd_nm LIKE '%BW%'"
    ).fetchone()[0] == 33
    assert con.execute(
        "SELECT COUNT(*) FROM domestic_bonds WHERE pd_nm LIKE '%신주%'"
    ).fetchone()[0] == 0
