# -*- coding: utf-8 -*-
"""라운드 32 — 서버 QA r1(87문항, eval/probe_bonds_2026-09-06_r1.json) 결함 회귀.

  · 구조 라벨을 bd_knd 값으로 쓴 SQL → 구조표시 CASE 판정식 (BND-D-019 전환사채 오거절)
  · SELECT 표시 컬럼만 없는 컬럼이면 떼고 살린다 (BND-S-004 mtco_itm_no 로 통째 기각)
  · 안전 최상급의 수익률 오름차순 → 내림차순 (BND-S-002 물가채 0.557% 1위)
발동/불개입 짝으로 둔다.
"""
import pytest

from src.runtime import guard, loader
from src.runtime import pipeline as pl

T = ["domestic_bonds"]


@pytest.fixture(scope="module")
def ctx():
    return loader.load_context()


@pytest.fixture(scope="module")
def con():
    c = loader.connect_readonly()
    yield c
    c.close()


# ── 구조 라벨 교정 ─────────────────────────────────────────────────────────────
def test_structure_label_in_list_becomes_case_predicate(ctx, con):
    sql = "SELECT pd_nm, bd_knd, applied_yield FROM domestic_bonds WHERE pd_nm LIKE '%전환%' OR bd_knd IN ('전환사채', '교환사채') GROUP BY pd_no LIMIT 30"
    out, fixed = pl.fix_structure_kind_literal(sql)
    assert fixed == ["전환사채", "교환사채"]
    assert "GLOB '*[0-9]CB*'" in out and "GLOB '*[0-9]EB*'" in out and "bd_knd IN" not in out
    assert guard.check_values(out, ctx) == [] and con.execute(out).fetchall()


@pytest.mark.parametrize("lit, frag", [
    ("전환사채", "CB"), ("CB", "CB"), ("영구채", "신종"), ("신종자본증권", "신종"), ("후순위", "(후)"),
    ("BW", "BW"), ("물가채", "물가"), ("코코본드", "pd_risk_gcd IN ('11','12','13')"),
])
def test_structure_label_equals(lit, frag):
    out, fixed = pl.fix_structure_kind_literal(f"SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '{lit}' LIMIT 30")
    assert fixed and frag in out and f"= '{lit}'" not in out          # 라벨 등호는 사라진다(코코본드 판정식은 bd_knd 종류를 정당하게 쓴다)


@pytest.mark.parametrize("sql", [
    "SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd)='국고채권' LIMIT 5",                    # 실값
    "SELECT pd_nm FROM domestic_bonds WHERE bd_knd IN ('전환사채','일반회사채') LIMIT 5",         # 라벨+실값 혼합
    "SELECT pd_nm FROM domestic_bonds WHERE bd_knd = '없는값' LIMIT 5",                           # 라벨도 실값도 아님 — 값 검사 몫
    "SELECT pd_nm, bd_knd FROM domestic_bonds WHERE pd_nm LIKE '%전환%' LIMIT 5",                # 조건 없음
    "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 5",                          # 다른 테이블
])
def test_structure_label_untouched(sql):
    out, fixed = pl.fix_structure_kind_literal(sql)
    assert out == sql and not fixed


def test_structure_predicates_come_from_declaration(ctx):
    preds = pl._structure_predicates()
    case = pl._structure_case(ctx)
    assert preds and all(cond in case for cond in preds.values())
    assert set(pl._STRUCT_ALIASES.values()) <= set(preds) | {"국고채 STRIPS"}


# ── 없는 컬럼 제거 ────────────────────────────────────────────────────────────
_S4 = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, MAX(applied_yield) AS applied_yield , pd_risk_gcd, pd_risk_nm, mat_dt, TRIM(crd_grd) AS crd_grd, mtco_itm_no "
       "FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND pd_risk_gcd = '16' AND std_pd_mcls_nm = '회사채' GROUP BY pd_no ORDER BY MAX(applied_yield) DESC LIMIT 3")


def test_drop_unknown_select_column_and_pass_precheck(ctx):
    err = pl._sql_precheck(_S4, ctx, T, False, question="가장 안전한 회사채 3개 추천해줘")
    assert err and "mtco_itm_no" in err
    out, dropped = pl.drop_unknown_select_columns(_S4, err)
    assert dropped == ["mtco_itm_no"] and "mtco_itm_no" not in out
    assert pl._sql_precheck(out, ctx, T, False, question="x") is None


def test_drop_unknown_untouched_when_used_in_where():
    sql = "SELECT pd_nm, mtco_itm_no FROM domestic_bonds WHERE mtco_itm_no = 'x' LIMIT 5"
    out, dropped = pl.drop_unknown_select_columns(sql, "스키마에 없는 컬럼: mtco_itm_no(→ public_funds 컬럼이다)")
    assert out == sql and not dropped


def test_drop_unknown_untouched_when_only_column():
    sql = "SELECT mtco_itm_no FROM domestic_bonds LIMIT 5"
    out, dropped = pl.drop_unknown_select_columns(sql, "스키마에 없는 컬럼: mtco_itm_no(→ public_funds 컬럼이다)")
    assert out == sql and not dropped


def test_drop_unknown_untouched_on_other_error():
    out, dropped = pl.drop_unknown_select_columns(_S4, "SQL 이 완결된 한 문장이 아니다")
    assert out == _S4 and not dropped


# ── 안전 최상급 정렬 방향 ──────────────────────────────────────────────────────
_S2 = ("SELECT pd_nm, pd_risk_nm, MIN(applied_yield) AS applied_yield , TRIM(crd_grd) AS crd_grd, mat_dt FROM domestic_bonds "
       "WHERE pd_risk_gcd = '16' AND curr_cd = 'KRW' AND mat_dt >= 20260824 GROUP BY pd_no ORDER BY MIN(applied_yield) ASC, pd_no ASC LIMIT 3")


def test_safety_sort_flipped_to_desc(con):
    out, changed = pl.flip_safety_sort(_S2, "리스크가 가장 낮은 채권 3개만 골라줘")
    assert changed and "ORDER BY MAX(applied_yield) DESC" in out and "MAX(applied_yield) AS applied_yield" in out
    assert "MIN(applied_yield)" not in out
    top = con.execute(out).fetchone()
    assert top[2] > 5                                        # 6등급 안에서 수익률 높은 순 — 물가채 0.557% 가 1위가 아니다


def test_safety_sort_plain_column():
    sql = "SELECT pd_nm, applied_yield FROM domestic_bonds WHERE pd_risk_gcd = '16' ORDER BY applied_yield LIMIT 3"
    out, changed = pl.flip_safety_sort(sql, "가장 안전한 채권 3개")
    assert changed and "ORDER BY applied_yield DESC" in out


@pytest.mark.parametrize("q", ["가장 안전한 채권 중 수익률 낮은 순 3개", "수익률이 가장 낮은 채권 3개", "리스크 낮은 채권 금리 낮은 것부터"])
def test_safety_sort_untouched_when_low_yield_asked(q):
    out, changed = pl.flip_safety_sort(_S2, q)
    assert not changed and out == _S2


def test_safety_sort_untouched_without_safety_words():
    out, changed = pl.flip_safety_sort(_S2, "6등급 채권 수익률 낮은 순 3개")
    assert not changed
    out2, changed2 = pl.flip_safety_sort(_S2.replace("ASC, pd_no ASC", "DESC, pd_no ASC"), "가장 안전한 채권 3개")
    assert not changed2                                      # 이미 DESC
