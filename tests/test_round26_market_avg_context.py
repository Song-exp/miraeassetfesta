# -*- coding: utf-8 -*-
"""범주축 평균 비교의 구성 효과 — enforce 슬롯 MKTAVG (2026-09-05).

서버 실측: "장내 채권이랑 장외 중 어디가 수익률 높아?" 가
`SELECT TRIM(pd_exg_mkt), AVG(applied_yield) … GROUP BY pd_exg_mkt ORDER BY 2 DESC LIMIT 2`
로 나가 "장외 8.60% > 장내 4.13%" 로 답했다. 값은 전부 실제 행이라 환각 검사에 걸리지 않지만,
그 평균은 C0·위험1등급 부실채 96종목(최고 728.5%)이 만든 것이고 부실채·사모를 빼면 순위가 뒤집힌다.

규칙 `시장집계금지`("pd_exg_mkt 단독 group-by 금지 — 구성 효과 교란")는 **이미 있었다**.
강제하는 가드가 없어 선언이 그대로 비켜간 자리라, 슬롯으로 강제한다.

여기서 지키는 것 넷:
  ① 범주축 AVG(applied_yield) 집계에 모수·부실채제외평균 열이 병기된다
  ② 집계 항목이 SELECT 의 마지막이 아니면 불개입 — 자리번호(`ORDER BY 2`)를 밀지 않는다
  ③ 구성 효과가 실재한다 — 부실채를 빼면 장내·장외 순위가 실제로 역전된다(DB 실측)
  ④ 규칙 본문이 세 요건(모수·제외평균·구성 효과 고지)을 계속 말한다
"""
from __future__ import annotations

import re
import sqlite3

import pytest

from src.runtime import guard
from src.runtime.loader import connect_readonly, load_context

_MKT_SQL = (
    "SELECT TRIM(pd_exg_mkt) AS pd_exg_mkt, AVG(applied_yield) AS 평균수익률 "
    "FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 "
    "AND (applied_yield > 0) GROUP BY pd_exg_mkt ORDER BY 2 DESC LIMIT 2"
)
# `종류비교` 규칙이 지시하는 모양 — ROUND 로 감싸고 별칭이 없다
_KIND_SQL = (
    "SELECT CASE WHEN TRIM(bd_knd)='국고채권' THEN '국고채' "
    "WHEN TRIM(bd_knd)='통화안정채권' THEN '통안채' END AS 종류, ROUND(AVG(applied_yield),2) "
    "FROM domestic_bonds WHERE applied_yield > 0 "
    "AND TRIM(bd_knd) IN ('국고채권','통화안정채권') GROUP BY 종류 LIMIT 30"
)


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def _fire(ctx, sql, question="장내 채권이랑 장외 중 어디가 수익률 높아?"):
    return guard.apply_enforce(sql, question, ["domestic_bonds"], set(), ctx)


# ── ① 병기 ────────────────────────────────────────────────────────────────
def test_market_avg_gets_population_and_clean_average(ctx):
    out, fired = _fire(ctx, _MKT_SQL)
    assert "MKTAVG" in fired
    assert "COUNT(DISTINCT pd_no) AS 종목수" in out
    assert "부실채제외평균" in out
    assert "AS 평균수익률" in out, "원래 별칭이 살아 있어야 한다 (캡처 그룹 치환)"
    assert "{1}" not in out and "{2}" not in out and "{3}" not in out, "자리표시자가 남았다"


def test_slot_survives_round_wrapper(ctx):
    """`종류비교` 가 지시하는 ROUND(AVG(...),2) 형에도 붙는다 — 시장축 전용이 아니다."""
    out, fired = _fire(ctx, _KIND_SQL, "국고채랑 통안채 중 뭐가 수익률 높아?")
    assert "MKTAVG" in fired
    assert "ROUND(AVG(applied_yield),2)" in out, "원래 집계 표현이 그대로 살아야 한다"
    assert "부실채제외평균" in out


def test_rewritten_sql_executes_and_keeps_positional_order(ctx):
    """자리번호 정렬(`ORDER BY 2`)이 살아 있는지 — 열을 뒤에 더하므로 안 밀린다."""
    out, _ = _fire(ctx, _MKT_SQL)
    con = connect_readonly()
    cur = con.execute(out.split("/*M:")[0])
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    assert cols[:2] == ["pd_exg_mkt", "평균수익률"]
    assert "종목수" in cols and "부실채제외평균" in cols
    assert [r[0] for r in rows] == ["장외", "장내"], "ORDER BY 2 DESC(원 평균 기준) 가 유지돼야 한다"
    by_mkt = {r[0]: r for r in rows}
    # 원 평균은 장외가 높지만, 부실채를 뺀 평균은 장내가 높다 — 답변이 둘을 다 보게 하는 것이 이 슬롯의 목적
    assert by_mkt["장외"][1] > by_mkt["장내"][1]
    assert by_mkt["장외"][3] < by_mkt["장내"][3]


def test_slot_is_idempotent(ctx):
    once, _ = _fire(ctx, _MKT_SQL)
    twice, fired = _fire(ctx, once)
    assert fired == [] and twice == once
    assert twice.count("부실채제외평균") == 1


# ── ② 불개입 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sql, why", [
    ("SELECT TRIM(bd_knd), AVG(applied_yield) AS y, COUNT(*) FROM domestic_bonds "
     "GROUP BY bd_knd LIMIT 30", "집계 항목이 마지막이 아니다 — 열을 더하면 자리번호가 밀린다"),
    ("SELECT AVG(applied_yield) FROM domestic_bonds LIMIT 30", "GROUP BY 가 없다 — 범주축 비교가 아니다"),
    ("SELECT TRIM(pd_exg_mkt), AVG(srfc_irt) FROM domestic_bonds GROUP BY pd_exg_mkt LIMIT 30",
     "축이 applied_yield 가 아니다"),
    ("SELECT '장내' AS mkt, AVG(applied_yield) FROM domestic_bonds GROUP BY mkt "
     "UNION ALL SELECT '장외' AS mkt, AVG(applied_yield) FROM domestic_bonds GROUP BY mkt",
     "UNION 은 가지마다 열 수가 갈리면 깨진다"),
])
def test_slot_stays_out(ctx, sql, why):
    out, fired = _fire(ctx, sql)
    assert "MKTAVG" not in fired, why
    assert "부실채제외평균" not in out, why


# ── ③ 구성 효과는 실재한다 (DB 실측 — 숫자가 바뀌면 규칙 문구도 바뀌어야 한다) ──
def test_distressed_bonds_actually_flip_the_ranking():
    con = connect_readonly()
    base = "curr_cd='KRW' AND mat_dt>=20260824 AND applied_yield>0"
    excl = ("COALESCE(pd_risk_gcd,'')<>'11' AND COALESCE(TRIM(crd_grd),'')<>'C0' "
            "AND COALESCE(TRIM(bd_ofr_tcd),'')<>'사모'")
    raw = dict(con.execute(
        f"SELECT TRIM(pd_exg_mkt), AVG(applied_yield) FROM domestic_bonds WHERE {base} GROUP BY 1"))
    clean = dict(con.execute(
        f"SELECT TRIM(pd_exg_mkt), AVG(applied_yield) FROM domestic_bonds "
        f"WHERE {base} AND {excl} GROUP BY 1"))
    assert raw["장외"] > raw["장내"], "원 평균은 장외가 높다 (오답이 나온 그 숫자)"
    assert clean["장내"] > clean["장외"], "부실채·사모를 빼면 뒤집힌다 — 규칙이 서 있는 근거"
    n = con.execute("SELECT COUNT(*) FROM domestic_bonds WHERE applied_yield > 50").fetchone()[0]
    bad = con.execute(
        "SELECT COUNT(*) FROM domestic_bonds WHERE applied_yield > 50 "
        "AND (TRIM(COALESCE(crd_grd,''))='C0' OR pd_risk_gcd='11')").fetchone()[0]
    assert (n, bad) == (96, 96), "50% 초과 96행이 전부 부실채라는 전제가 깨졌다"


def test_issuer_equality_drops_the_otc_row():
    """`발행사조회` — 발행사 등식이 결측행을 지운다. NH농협캐피탈269-1 이 그 사고의 표본."""
    con = connect_readonly()
    both = con.execute(
        "SELECT COUNT(*) FROM domestic_bonds WHERE pd_nm LIKE '%엔에이치농협캐피탈269-1%'").fetchone()[0]
    narrowed = con.execute(
        "SELECT COUNT(*) FROM domestic_bonds WHERE pd_nm LIKE '%엔에이치농협캐피탈269-1%' "
        "AND TRIM(pd_pbcm) = '엔에이치농협캐피탈(주)'").fetchone()[0]
    assert both == 2 and narrowed == 1, "장외행(pd_pbcm NULL)이 등식에 지워지는 구조"
    orphan = con.execute(
        "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE pd_no NOT IN "
        "(SELECT pd_no FROM domestic_bonds WHERE pd_pbcm IS NOT NULL AND TRIM(pd_pbcm)<>'')").fetchone()[0]
    assert orphan == 141, "발행사 축으로는 영영 안 잡히는 종목 수"


# ── ④ 선언이 요건을 계속 말하는가 ─────────────────────────────────────────
def test_rule_text_keeps_the_three_requirements(ctx):
    rule = ctx.enums["domestic_bonds"]["query_rules"]["시장집계금지"]
    text = rule["text"]
    for token in ("COUNT(DISTINCT pd_no)", "부실채", "구성", "8.60", "3.92"):
        assert token in text, f"규칙 본문에서 '{token}' 이 사라졌다"
    assert rule["enforce"]["mark"] == "MKTAVG"
    # 고위험제외의 '조회는 제외하지 않는다' 예외와 충돌하지 않는다는 것을 두 규칙 모두가 말한다
    assert "병기" in ctx.enums["domestic_bonds"]["query_rules"]["고위험제외"]["text"]


def test_enforce_never_reaches_prompt(ctx):
    out = ctx.planner_context(["domestic_bonds"], "장내 채권이랑 장외 중 어디가 수익률 높아?")
    assert "시장집계금지" in out
    for leak in ("MKTAVG", "replace_predicate", "from_pattern", "enforce"):
        assert leak not in out, f"{leak} 가 프롬프트로 샜다"
