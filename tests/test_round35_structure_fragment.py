# -*- coding: utf-8 -*-
"""라운드35 #101 — 구조 판정식 주입 시 HCX 이름 조각 절을 걷는다.

'전환사채(CB)는 몇 종목이야?' 가 388종목(선언 판정식)인데 385 로 나갔다. 구조 블록이 판정식을 AND 로
주입하면서 HCX 가 쓴 `(pd_nm LIKE '%전환%' OR pd_nm LIKE '%(전환%' OR pd_nm LIKE '%/전환%')` 를 걷지
못해 교집합이 됐고, 이름에 '전환' 이 없는 CB 표기 3종목이 잘렸다.

원인 둘 다 일반 구멍이었다:
  (1) 괄호 짝 계산이 **문자열 리터럴 안의 괄호**를 셌다(10R 에서 이미 배운 규칙인데 여기에만 미적용)
  (2) `'(전환'` 은 '전환사채' 의 부분문자열이 아니라 조각으로 인정받지 못했다 — 그런데 그것은
      **판정식이 직접 쓰는 표기**다(구조·ESG 라벨은 이름 안에서 괄호·슬래시로 감싸여 나타난다)
"""

import re
import sqlite3

import pytest

from src.runtime.loader import db_path
from src.runtime.pipeline import (_STRUCT_ALIASES, _is_structure_name_fragment, _structure_predicates,
                                  ensure_kind_filter)

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")
POP = "curr_cd = 'KRW' AND mat_dt >= 20260824"


def _con():
    return sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)


def _count(where):
    with _con() as con:
        return con.execute(f"SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE {where}").fetchone()[0]


def test_CB_는_선언_판정식_그대로_센다():
    q = "전환사채(CB)는 몇 종목이야?"
    hcx = "(pd_nm LIKE '%전환%' OR pd_nm LIKE '%(전환%' OR pd_nm LIKE '%/전환%')"
    out, fired = ensure_kind_filter(f"SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE {POP} AND {hcx}", q)
    assert fired and hcx not in out                       # 조각 절이 걷혔다
    with _con() as con:
        assert con.execute(out).fetchone()[0] == _count(f"{POP} AND ({_structure_predicates()['전환사채']})")


def test_이름에_전환이_없는_CB_가_살아난다():
    """잘렸던 3종목 — 판정식은 GLOB '*[0-9]CB*' 로 잡는데 '전환' 조각 절이 이를 잘랐다."""
    lost = _count(f"{POP} AND ({_structure_predicates()['전환사채']}) AND pd_nm NOT LIKE '%전환%'")
    assert lost == 3
    with _con() as con:
        names = {r[0] for r in con.execute(
            f"SELECT TRIM(pd_nm) FROM domestic_bonds WHERE {POP} "
            f"AND ({_structure_predicates()['전환사채']}) AND pd_nm NOT LIKE '%전환%'")}
    assert names == {"제주반도체9CB", "애드바이오텍10CB", "애드바이오텍11CB"}


def test_괄호짝은_리터럴_안의_괄호를_세지_않는다():
    words = {"전환사채", "CB"}
    pred_lits = {"%(전환%", "%/전환%", "(전환", "/전환"}
    clause = "(pd_nm LIKE '%전환%' OR pd_nm LIKE '%(전환%' OR pd_nm LIKE '%/전환%')"
    assert _is_structure_name_fragment(clause, words, pred_lits) is True


def test_판정식_표기가_아니고_낱말_조각도_아니면_남긴다():
    """사용자가 이름으로 더 좁힌 조건은 걷지 않는다 — 이 가드가 넓히기만 하지 않게 하는 경계."""
    words = {"전환사채", "CB"}
    pred_lits = {"%(전환%", "%/전환%"}
    assert _is_structure_name_fragment("(pd_nm LIKE '%전환%' OR pd_nm LIKE '%삼성%')", words, pred_lits) is False


@pytest.mark.parametrize("label", sorted(_structure_predicates()))
def test_판정식_리터럴은_전부_자기_판정식에서_조각으로_인정된다(label):
    """선언이 쓰는 표기를 선언이 모르는 표기로 취급하지 않는다 — 라벨 전수."""
    pred = _structure_predicates()[label]
    lits = re.findall(r"'([^']*)'", pred)
    if not lits:
        pytest.skip("이름 리터럴이 없는 판정식")
    words = {a for a, l in _STRUCT_ALIASES.items() if l == label} | {label}
    pred_lits = set(lits) | {x.replace("%", "").strip() for x in lits}
    for lit in lits:
        if "GLOB" in pred and lit.startswith("*"):
            continue                                       # GLOB 원자는 _NAME_LIKE_ATOM 대상이 아니다
        assert _is_structure_name_fragment(f"pd_nm LIKE '{lit}'", words, pred_lits) is True, (label, lit)
