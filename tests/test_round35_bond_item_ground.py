# -*- coding: utf-8 -*-
"""라운드35 P0-1 — 채권 종목 지시자 그라운딩 (사고 #98·#99·#100).

채권 20,497종목에는 KG 노드가 없어 '한국전력공사채권1184' 에서 발행사만 잡히고 회차가 사라졌다.
남은 숫자를 HCX 가 pd_no = 1184 로 메꿔(pd_no 는 12자리 ISIN) 0행이 됐고, 같은 결손이
bd_knd 날조(#99)와 발행사 전체 개수(#100)로도 나왔다. 이름을 DB 실제 값으로 옮겨 그 결손을 막는다.
"""

import json
import pathlib
import sqlite3

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question, bond_item_in_question, _bond_item_names

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── 적중 — 질문이 종목을 지목하면 DB 실제 표기로 옮긴다 ──────────────────────────────────────
@pytest.mark.parametrize("q, want", [
    ("한국전력공사채권1184 표면금리랑 수익률 알려줘", "한국전력공사채권1184"),
    ("한국전력공사채권1184 발행잔액 얼마야?", "한국전력공사채권1184"),
    ("한국전력공사채권1184 지금 살 수 있어?", "한국전력공사채권1184"),
    ("풍산109 수익률 알려줘", "풍산109"),
    ("DGB금융지주24 신용등급", "DGB금융지주 24"),          # 질의엔 붙여 썼고 DB 는 띄어 쓴 표기
])
def test_종목_지목은_DB_실제_표기로(q, want):
    assert bond_item_in_question(q) == want


# ── 불개입 — 종목을 지목하지 않은 질문 ─────────────────────────────────────────────────────
@pytest.mark.parametrize("q", [
    "삼천리24년 만기 채권 알려줘",        # 연도 — '삼천리24' 가 실재 종목이라 단위 경계가 없으면 걸린다
    "서흥26년에 만기되는 채권",
    "경남개발공사27년 만기",
    "한국전력공사 채권 알려줘",            # 발행사 지목
    "산금채는 몇 종목이야?",
    "2027년에 만기되는 채권 알려줘",
    "국고채 몇 종목이야",
    "수익률 높은 채권 추천해줘",
])
def test_지목하지_않은_질문에는_불개입(q):
    assert bond_item_in_question(q) is None


def test_이름사전_불변식():
    """숫자 없는 이름은 없다 — 순 한글 낱말이 구조적으로 오탐이 될 수 없다는 근거."""
    names = _bond_item_names()
    assert len(names) > 19000
    assert all(any(ch.isdigit() for ch in k) and len(k) >= 5 for k in names)


def test_eval_전문항_오탐_0건():
    qs = []
    for p in sorted((ROOT / "eval").glob("questions_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("question"):
                    qs.append(d["question"])
    assert len(qs) >= 190
    assert [q for q in qs if bond_item_in_question(q)] == []


def test_상품군_간_이름_중복_0건():
    """종목명 하나로 상품군을 정할 수 있는 근거 — 다른 상품군을 가로채지 않는다."""
    keys = set(_bond_item_names())
    with sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True) as con:
        for tbl, col in (("domestic_etfs", "pd_abrv_nm"), ("domestic_etfs", "pd_nm"),
                         ("overseas_etfs", "pd_nm"), ("public_funds", "itm_nm")):
            other = {"".join((r[0] or "").split())
                     for r in con.execute(f"SELECT DISTINCT TRIM({col}) FROM {tbl} WHERE {col} IS NOT NULL")}
            assert not (keys & other), f"{tbl}.{col}"


class _P:
    sql = ("SELECT TRIM(pd_nm) AS pd_nm, srfc_irt, applied_yield FROM domestic_bonds "
           "WHERE TRIM(pd_nm) = '한국전력공사채권1184' LIMIT 30")

    def plan_sql(self, q, g):
        return _P.sql

    def compose_answer(self, q, rows, answer_rules=""):
        return "x"


def test_근거문서에_종목_지시자_블록이_실린다(ctx):
    r = answer_question("T-ITEM", "한국전력공사채권1184 표면금리랑 수익률 알려줘", planner=_P(), ctx=ctx)
    assert "[종목 지시자]" in r.grounding
    assert "TRIM(pd_nm) = '한국전력공사채권1184'" in r.grounding
    assert "[Ground] 종목 지시" in r.think_trace
    # 실제 값이 답에 닿는다 — 표면금리 3.72 · 수익률 5.051 (DB 실측)
    assert "3.72" in r.answer and "5.051" in r.answer


def test_이름만으로_상품군이_정해진다(ctx):
    """'풍산109 수익률' 은 종전에 4테이블 미특정이었다 — 이름이 가장 강한 라우팅 신호다."""
    r = answer_question("T-ROUTE", "풍산109 수익률 알려줘", planner=_P(), ctx=ctx)
    assert "[Route] 미특정 -> 종목 지시자" in r.think_trace
