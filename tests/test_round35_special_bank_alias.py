# -*- coding: utf-8 -*-
"""라운드35 P1-6 — 특수은행채 발행사 통칭 5종 선언 (사고 #97).

규칙 원문 종류필터 ②는 "특수은행채(산금채 등) 포함" 이라고 이미 말하고 있었는데 어휘도 확정식도 없어
'산금채는 몇 종목이야?' 가 bd_knd='산업금융채권'(DB 에 없는 값)으로 나갔고, 재생성이 우연히 발행사를
골라 값만 맞았다. 선언만 있고 가드가 없으면 안 지켜진다 — 세 층(라우터·확정식·고지)에 같이 건다.
"""

import sqlite3

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import (_question_kind_filters, domain_caveats, ensure_kind_filter,
                                  ensure_trimmed_compare, restore_kind_breadth)
from src.runtime.router import route

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

# 통칭 → (발행사, 전체 종목 수) — DB 실측 전수. 특수은행채 발행사는 이 5곳뿐이다.
ALIASES = [("산금채", "한국산업은행", 503), ("중금채", "(주)중소기업은행", 398),
           ("수은채", "한국수출입은행", 221), ("농금채", "농협은행", 131), ("수협채", "수협은행", 57)]


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def _con():
    return sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)


@pytest.mark.parametrize("tok, issuer, n", ALIASES)
def test_발행사와_종목수가_실측과_같다(tok, issuer, n):
    with _con() as con:
        got = con.execute(
            "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds "
            "WHERE TRIM(bd_knd)='특수은행채' AND TRIM(pd_pbcm) = ?", (issuer,)).fetchone()[0]
    assert got == n


def test_특수은행채_발행사는_다섯곳뿐이다():
    """통칭 표가 사례 표가 아니라 전수 표라는 근거 — 늘거나 줄면 이 회귀가 먼저 깨진다."""
    with _con() as con:
        rows = con.execute("SELECT DISTINCT TRIM(pd_pbcm) FROM domestic_bonds "
                           "WHERE TRIM(bd_knd)='특수은행채'").fetchall()
    assert {r[0] for r in rows} == {i for _t, i, _n in ALIASES}


@pytest.mark.parametrize("tok, issuer, _n", ALIASES)
def test_라우터가_통칭을_채권으로_보낸다(ctx, tok, issuer, _n):
    """종전엔 4테이블 미특정이었다 — 규칙·확정식이 보는 어휘를 라우터도 봐야 한다."""
    assert route(f"{tok}는 몇 종목이야?", ctx).tables == ["domestic_bonds"]


@pytest.mark.parametrize("tok, issuer, _n", ALIASES)
def test_종류신호는_정확히_하나(tok, issuer, _n):
    """둘 이상이면 ensure_kind_filter 가 통째로 물러나 확정식이 안 붙는다."""
    assert len(_question_kind_filters(f"{tok}는 몇 종목이야?")) == 1


def test_확정식이_가드_사슬을_그대로_통과한다():
    q = "산금채는 몇 종목이야?"
    base = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds "
            "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 LIMIT 30")
    sql, injected = ensure_kind_filter(base, q)
    assert injected and "TRIM(pd_pbcm)='한국산업은행'" in sql
    kept, note = restore_kind_breadth(sql, q)
    assert note is None and kept == sql            # 괄호로 한 절 — 폭 복원이 건드리지 않는다
    assert ensure_trimmed_compare(kept)[0] == kept
    with _con() as con:
        assert con.execute(kept.replace(" LIMIT 30", "")).fetchone()[0] == 499   # 구매가능 모수


def test_축_대체를_답변에_밝힌다():
    sql = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' "
           "AND mat_dt >= 20260824 AND (TRIM(bd_knd)='특수은행채' AND TRIM(pd_pbcm)='한국산업은행') LIMIT 30")
    out = domain_caveats(sql, "c\n499", "산금채는 몇 종목이야?")
    assert out and "발행사 기준" in out[0] and "한국산업은행" in out[0] and "'산금채'는" in out[0]


def test_종류축_그대로인_질문에는_고지하지_않는다():
    assert domain_caveats("SELECT COUNT(*) FROM domestic_bonds WHERE TRIM(bd_knd)='특수은행채'",
                          "c\n1310", "특수은행채 몇 종목이야?") == []
