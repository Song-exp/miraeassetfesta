# -*- coding: utf-8 -*-
"""22R — 공백만 다른 같은 값을 놓치던 자리 (KG-015).

    "위험등급이 '높은위험'인 공모펀드는 몇 개야?"
    → WHERE zrin_fd_ivst_risk_grd_nm IN ('높은위험')     ← 20클래스만

DB 에는 **같은 등급이 두 표기**로 들어 있다 — '높은 위험' 2,974클래스 · '높은위험' 20클래스
(보통 위험도 1,419 · 8). 합산해야 정답(995펀드/2,994클래스)이다. 4차엔 HCX 가 둘 다 넣어
맞혔고 5차엔 하나만 넣어 틀렸다 — 통과 조건이 "띄어쓰기 두 표기를 합산해야 한다" 인데
그 판단을 HCX 에 맡겨 둔 것이 원인이었다.

🔴 넓히는 것이 아니다 — 같은 개념의 다른 표기를 되찾는 것이다. 판정 근거는 값 사전이고
   공백을 지웠을 때 같은 값만 더한다.
"""
import json
import re

import pytest

from src.runtime import guard
from src.runtime.loader import connect_readonly, db_path, load_context
from src.runtime.pipeline import answer_question

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_both_spellings_exist_in_the_data():
    """가드의 전제 — 실제로 두 표기가 있다."""
    con = connect_readonly()
    try:
        rows = dict(con.execute(
            "SELECT zrin_fd_ivst_risk_grd_nm, COUNT(*) FROM public_funds "
            "WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
            "AND zrin_fd_ivst_risk_grd_nm IN ('높은 위험','높은위험') GROUP BY 1").fetchall())
    finally:
        con.close()
    assert rows == {"높은 위험": 2974, "높은위험": 20}, rows


@pytest.mark.parametrize("where, added, why", [
    ("zrin_fd_ivst_risk_grd_nm = '높은위험'", ["높은 위험"], "등호도 IN 으로 넓혀 합산"),
    ("zrin_fd_ivst_risk_grd_nm IN ('높은위험')", ["높은 위험"], "IN 한 값도 마찬가지"),
    ("zrin_fd_ivst_risk_grd_nm IN ('높은위험','높은 위험')", [], "이미 둘 다 있으면 불개입"),
    ("zrin_btyp_nm = '해외주식형'", [], "변형이 없는 값은 그대로"),
])
def test_variants(ctx, where, added, why):
    out, got = guard.ensure_spacing_variants(f"SELECT COUNT(*) FROM public_funds WHERE {where} LIMIT 30", ctx)
    assert got == added, why
    if added:
        for v in added:
            assert f"'{v}'" in out


def test_kg015_end_to_end(ctx):
    """합산하면 정답 995펀드 / 2,994클래스가 나온다."""
    with open("eval/probe_funds_2026-09-05_r5.json", encoding="utf-8") as f:
        rec = {r["qid"]: r for r in json.load(f)}["KG-015"]
    sql = re.findall(r"(?:재생성 SQL|SQL 생성)[^\n]*\n(SELECT[^\n]+)", rec["think_trace"])[-1]

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX-CALLED"

    r = answer_question("KG-015", rec["question"], planner=P(), ctx=ctx)
    assert "표기 변형 합산" in r.think_trace
    ans = r.answer or ""
    assert "995" in ans and "2,994" in ans, ans
