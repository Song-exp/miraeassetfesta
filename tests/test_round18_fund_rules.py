# -*- coding: utf-8 -*-
"""18R 공모펀드 — 규칙 북 대조 후 '온톨로지에 없던' 것으로 확정해 신설한 규칙들.

근거: docs/funds_test_result_2026-09-04.md · docs/funds_ontology_fix_plan_2026-09-04.md
신설 5 + 횡전개 2. 각각 "실려야 한다"와 "오발동하면 안 된다" 를 함께 잰다 —
게이트 오발동은 답변 가능한 문항을 죽이므로 회귀에서 그쪽이 더 비싸다.
"""

import sqlite3

import pytest

from src.runtime import gate
from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")

FUNDS = ["public_funds"]


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── DOM-10 · 이자/배당 = 기본모수 상수 컬럼 → gate_constants (HCX 0회) ─────────────
@pytest.mark.parametrize("q, fires", [
    ("이자형 공모펀드와 배당형 공모펀드는 각각 몇 개야?", True),
    ("배당을 많이 준 공모펀드 알려줘", False),      # 분배(fd_last_dstb_r) 질의 — 답변 가능
    ("최근 분배율이 높은 펀드 5개", False),
    ("배당주 펀드 몇 개야", False),
    ("이자를 주는 채권형 펀드 있어?", False),
])
def test_int_dvd_gate(ctx, q, fires):
    r = gate.check(q, ctx, FUNDS)
    assert bool(r.rejected) is fires, f"게이트 발동={bool(r.rejected)} 기대={fires}: {q}"
    if fires:
        assert "구분" in (r.answer or ""), "0개가 아니라 '구분 불가' 로 말해야 한다"


def test_int_dvd_is_constant_in_base_population():
    """게이트의 전제 — 기본모수로 한정하면 전건 '배당'. 깨지면 게이트가 거짓이 된다."""
    con = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT int_dvd_desc, COUNT(*) FROM public_funds "
        "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY 1"
    ).fetchall()
    con.close()
    assert rows == [("배당", 8969)], f"상수성이 깨졌다 — 게이트 재판정 필요: {rows}"


# ── AA24 · 클래스 표기는 itm_nm 에 있다 (han_clas_nm 아님) ────────────────────────
def test_class_notation_rule_loaded(ctx):
    pc = ctx.planner_context(FUNDS, "미래에셋 코어테크 펀드 종류A 3년 수익률 알려줘")
    assert "클래스 표기('종류A'" in pc


def test_class_notation_sql_finds_the_row():
    """규칙이 지시한 SQL 이 gold(185.21%)를 실제로 집는가. han_clas_nm 쪽은 0행이어야 한다."""
    con = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
    base = "FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모'"
    hit = con.execute(
        f"SELECT itm_nm, fd_yr3_ern_r {base} "
        "AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%' "
        "AND REPLACE(itm_nm,' ','') LIKE '%종류A%'"
    ).fetchall()
    wrong = con.execute(
        f"SELECT COUNT(*) {base} AND TRIM(han_clas_nm) = '종류 A'"
    ).fetchone()[0]
    con.close()
    assert any(abs(r[1] - 185.21) < 0.01 for r in hit if r[1] is not None), hit
    assert wrong == 0, "han_clas_nm 으로 클래스 문자를 거는 경로가 살아났다 — 규칙 전제 재확인"


# ── FND-006 · 배제 낱말은 NOT 으로 푼다 ──────────────────────────────────────────
def test_negation_rule_is_triggered_only_when_asked(ctx):
    on = ctx.planner_context(FUNDS, "MMF를 제외하고 순자산이 가장 큰 공모펀드 5개 알려줘")
    off = ctx.planner_context(FUNDS, "KB자산운용 공모펀드 몇 개야")
    assert "부정조건" in on
    assert "부정조건" not in off, "트리거 없는 질의에 규칙이 새면 프롬프트만 비대해진다"


# ── answer_rules 4줄 (DOM-11 · T13 · 2단 질문 · OFFICIAL-002) ────────────────────
@pytest.mark.parametrize("needle", [
    "질문이 두 부분이면",          # KG-005 · X22 · KG-031 · DOM-07
    "신규 가입만 중단된 상태",      # DOM-07 뒷부분에 댈 근거 — 위 규칙의 짝
    "0건일 때 그것이",             # DOM-11 — 0 이 정상인지 결손인지
    "두 축으로 셀 수 있는",         # T13 — domestic_etfs 섹터테마질의 횡전개
    "항목 자체를 서술하지 않는다",   # OFFICIAL-002 — 부인·단정 공존 금지
])
def test_answer_rules_delivered(ctx, needle):
    assert needle in ctx.answer_context(FUNDS)


def test_int_dvd_note_no_longer_says_it_is_filterable(ctx):
    """구 note 는 '공모·판매중 한정하면 필터 축으로 쓸 수 있다' 는 반대 방향이었다."""
    note = str((ctx.enums["public_funds"]["columns"]["int_dvd_desc"]).get("note", ""))
    assert "전건 '배당' = 상수 컬럼" in note


# ── 복합질의 · answer_rules 의 플래너 쪽 짝 ────────────────────────────────────
def test_compound_query_rule_reaches_the_planner(ctx):
    """조립기는 SQL 이 안 가져온 수를 만들 수 없다 — 두 부분 질의는 플래너에도 실려야 한다."""
    on = ctx.planner_context(FUNDS, "이름이 삼성으로 시작하는 공모펀드는 몇 개고, 그중 삼성자산운용이 운용하는 건 몇 개야?")
    off = ctx.planner_context(FUNDS, "KB자산운용 공모펀드 순자산 알려줘")
    assert "복합질의" in on
    assert "복합질의" not in off
