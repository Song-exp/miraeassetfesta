# -*- coding: utf-8 -*-
"""21R — 숫자만으로는 오해되는 자리에 도메인 한 문장 (DOM-06 · DOM-07 · DOM-11).

셋 다 규칙 문장으로는 이미 선언돼 있는데 **네 회차 내리 답변에 닿지 않았다** — 조립기가 적는다.
판정 근거는 SQL·결과 행이라 질문 문구에 최소한으로만 기댄다.

  DOM-07  "판매완료된 공모펀드는 몇 개야? **이미 청산된 거야?**" — 숫자만 답하고 뒷부분을 넘겼다.
          PDF §2.3: 판매완료는 신규 가입 중단이지 청산이 아니다.
  DOM-11  "헤지펀드인 공모펀드는 몇 개야?" — 0 이 나오는 것이 **정상**인데(사모 영역) 그 말이
          없으면 결손처럼 읽힌다.
  DOM-06  "A클래스와 C클래스 중 어느 쪽이 보수가 낮아?" — 총보수만 비교하면 절반이다. A 는 가입 시
          **선취 수수료**를 따로 떼는데 금액이 마스터에 없어 유불리는 투자 기간의 문제다(PDF §3.1).
"""
import json
import re

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question, domain_caveats

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def probe():
    with open("eval/probe_funds_2026-09-05_r4.json", encoding="utf-8") as f:
        return {r["qid"]: r for r in json.load(f)}


def test_sale_complete_is_not_liquidation():
    out = domain_caveats("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매완료'", "펀드수\n3934")
    assert out and "청산" in out[0] and "신규 가입" in out[0]


@pytest.mark.parametrize("rows, q, expect, why", [
    ("펀드수 | 클래스수\n0 | 0", "헤지펀드인 공모펀드는 몇 개야?", True, "0 이면 사모 영역임을 밝힌다"),
    ("펀드수 | 클래스수\n34 | 98", "헤지펀드인 공모펀드는 몇 개야?", False, "값이 있으면 설명이 필요 없다"),
    ("펀드수\n0", "스페인에 투자하는 공모펀드 있어?", False, "🔴 헤지펀드와 무관한 0행에는 붙지 않는다"),
])
def test_hedge_fund_note(rows, q, expect, why):
    assert bool(domain_caveats("SELECT a FROM public_funds", rows, q)) is expect, why


def test_class_fee_caveat_needs_both_fee_types():
    """결과에 선취·미징구가 **함께** 있을 때만 — 한쪽만 있으면 비교가 아니다."""
    both = "itm_nm | han_clas_nm\nx 종류A | 수수료선취-오프라인\ny 종류C | 수수료미징구-오프라인"
    out = domain_caveats("SELECT a FROM public_funds", both)
    assert out and "선취 수수료" in out[0] and "투자 기간" in out[0]
    one = "itm_nm | han_clas_nm\nx 종류A | 수수료선취-오프라인"
    assert not domain_caveats("SELECT a FROM public_funds", one)


def _replay(ctx, rec, compose="[HCX]"):
    sql = re.findall(r"(?:재생성 SQL|SQL 생성)[^\n]*\n(SELECT[^\n]+)", rec["think_trace"])[-1]

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return compose

    return answer_question(rec["qid"], rec["question"], planner=P(), ctx=ctx).answer or ""


@pytest.mark.parametrize("qid, needle", [
    ("DOM-07", "청산"),
    ("DOM-11", "사모 영역"),
])
def test_end_to_end(ctx, probe, qid, needle):
    assert needle in _replay(ctx, probe[qid]), qid


def test_dom06_caveat_rides_the_hcx_path(ctx, probe):
    """DOM-06 은 HCX 산문 경로다 — 조립기가 아니라 답변 반환 직전에 붙는다."""
    ans = _replay(ctx, probe["DOM-06"], compose="A클래스의 총보수가 더 낮습니다. A 1.435% · C 1.755%.")
    assert "선취 수수료" in ans and "길게 보유하면 A" in ans, ans


@pytest.mark.parametrize("qid", ["FND-012", "X21"])
def test_untouched(ctx, probe, qid):
    ans = _replay(ctx, probe[qid])
    for w in ("청산", "사모 영역", "선취 수수료"):
        assert w not in ans, f"{qid} 에 {w} 가 붙었다"


def test_fee_total_column_is_injected_when_items_are_listed():
    """🔴 2026-09-05 DOM-06 서버 실측 — HCX 가 보수 4항목을 따로 뽑아 답변에서 손으로 더했고
    **산수를 틀렸다**("0.72 + 0.68 + 0.02 + 0.015 = 1.605%" — 실제 1.435). 합계는 SQL 이 낸다.
    yaml `보수단위` 가 "% 환산 별칭을 반드시 함께 낸다" 고 못박은 자리다."""
    from src.runtime.pipeline import connect_readonly, ensure_fee_percent_select
    sql = ("SELECT TRIM(itm_nm) AS itm_nm, or_co_rwrd_r, sale_co_rwrd_r, trusc_rwrd_r, ofwk_trus_rwrd_r "
           "FROM public_funds WHERE REPLACE(REPLACE(itm_nm,' ',''),'-','') LIKE '%종류A' "
           "AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크증권자투자신탁(주식)%' LIMIT 3")
    out, fixed = ensure_fee_percent_select(sql)
    assert fixed and '"총보수_퍼센트"' in out and '" FROM' in out, out
    con = connect_readonly()
    try:
        cur = con.execute(out)
        row = dict(zip([d[0] for d in cur.description], cur.fetchone()))
    finally:
        con.close()
    assert row["총보수_퍼센트"] == 1.435, row      # 손으로 더하면 틀리던 값

    # 이미 총보수 열이 있으면 손대지 않는다
    have = 'SELECT ROUND((or_co_rwrd_r + sale_co_rwrd_r)/10.0, 4) AS "총보수_퍼센트" FROM public_funds'
    assert ensure_fee_percent_select(have)[1] is False


@pytest.mark.parametrize("answer, sql, expect, why", [
    ("A클래스의 총보수는 1.435‰, C는 1.755‰입니다.",
     'SELECT a, ROUND((or_co_rwrd_r + sale_co_rwrd_r)/10.0,4) AS "총보수_퍼센트" FROM public_funds',
     "A클래스의 총보수는 1.435%, C는 1.755%입니다.",
     "🔴 SQL 이 % 로 환산해 냈으면 답변의 ‰ 는 오기다 — 읽는 사람에겐 10배 차이"),
    ("총보수는 14.35‰ 입니다.",
     "SELECT or_co_rwrd_r + sale_co_rwrd_r AS total FROM public_funds",
     "총보수는 14.35‰ 입니다.",
     "원값(‰)을 그대로 낸 SQL 에는 손대지 않는다 — 그때는 ‰ 가 맞다"),
    ("A클래스의 총보수는 1.435%입니다.",
     'SELECT ROUND((or_co_rwrd_r)/10.0,4) AS "총보수_퍼센트" FROM public_funds',
     "A클래스의 총보수는 1.435%입니다.", "‰ 가 없으면 할 일이 없다"),
])
def test_permille_symbol(answer, sql, expect, why):
    from src.runtime.pipeline import fix_permille_symbol
    assert fix_permille_symbol(answer, sql)[0] == expect, why
