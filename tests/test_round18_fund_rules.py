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


# ── 단계 1·2 잔여 게이트 (DOM-09 · DOM-12 · FND-R02) + ABSENT (OFFICIAL-002) ──────
#    🔴 오발동 회귀가 본체다 — 형제 질문은 78문항 셋에서 실제로 ✅ 인 것을 골랐다.
@pytest.mark.parametrize("q, fires, why", [
    ("국내에서 설립된 공모펀드는 몇 개야?", True, "DOM-09 — 설립국가 95% 미기재"),
    ("2025년에 설정된 공모펀드는 몇 개야?", False, "X19 ✅ — '설정된' 단독은 설정일 질의"),
    ("가장 최근에 설정된 공모펀드 알려줘", False, "KG-033 ✅"),
    ("원화가 아닌 통화로 설정된 공모펀드는 몇 개야?", False, "DOM-03 — 통화 질의"),
    ("국내에 투자하는 공모펀드는 몇 개야?", False, "투자지역은 답변 가능"),
    ("룩셈부르크에서 설립된 공모펀드 알려줘", False, "코드 442 로 답변 가능"),

    ("전문투자자만 살 수 있는 공모펀드는 몇 개야?", True, "DOM-12 — 코드 의미 미제공"),
    ("개인이 가입할 수 있는 공모펀드는 몇 개야?", False, "pers_corp_desc 로 답변 가능"),

    ("지난 1주일 수익률이 가장 높은 공모펀드 알려줘", True, "FND-R02 — fd_wk1_ern_r 전건 NULL"),
    ("1개월 수익률 상위 5개 공모펀드 알려줘", False, "fd_mm1_ern_r 은 있다"),
    ("1년 수익률이 가장 높은 공모펀드 알려줘", False, "FND-003 ✅"),

    ("미래에셋코어테크 펀드의 투자전략 알려줘", True, "순수 전략 질의 — ABSENT"),
    ("국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘", False, "OFFICIAL-002 — 구조는 답해야 한다"),
    ("미래에셋코어테크 펀드의 보수와 운용전략 알려줘", False, "보수가 물려 있어 SQL 을 돌린다"),
])
def test_remaining_gates(ctx, q, fires, why):
    r = gate.check(q, ctx, FUNDS)
    assert bool(r.rejected) is fires, f"{why} | 발동={bool(r.rejected)} 기대={fires}: {q}"


def test_gate_premises_still_hold():
    """게이트 4종의 전제 수치. 깨지면 즉답 문구가 거짓이 된다."""
    con = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
    base = "FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모'"
    q = lambda sql: con.execute(sql).fetchone()[0]
    estb = q(f"SELECT COUNT(*) {base} AND fd_estb_ctry_cd = '000'")
    total = q(f"SELECT COUNT(*) {base}")
    wk1 = q(f"SELECT COUNT(*) {base} AND fd_wk1_ern_r IS NOT NULL")
    pfiv = q(f"SELECT COUNT(DISTINCT pfiv_sale_cntl_tcd) {base}")
    con.close()
    assert total == 8969
    assert estb / total > 0.94, f"설립국가 미기재율이 95% 아래로 내려갔다: {estb}/{total}"
    assert wk1 == 0, f"1주일 수익률이 채워졌다 — 게이트 해제 검토: {wk1}행"
    assert pfiv > 1, "판매통제코드가 상수가 되면 게이트 사유가 바뀐다"


# ── 단계 3·4·5 — 별칭 규약 · 이관 4줄 · 소분류 · JOIN 방향 ──────────────────────
def test_fee_alias_rule(ctx):
    assert "총보수_퍼센트" in ctx.planner_context(FUNDS, "총보수가 가장 낮은 공모펀드 5개 알려줘")
    assert "총보수_퍼센트" in ctx.answer_context(FUNDS)


@pytest.mark.parametrize("needle, qid", [
    ("3,531건(39%)이 미수록", "DOM-08"),
    ("법인 자금 파킹용 MMF", "FND-C01"),
    ("상품 간 크기 비교가 무의미", "FND-R03"),
])
def test_transferred_answer_rules(ctx, needle, qid):
    assert needle in ctx.answer_context(FUNDS), qid


def test_subcategory_and_join_direction(ctx):
    pc = ctx.planner_context(FUNDS, "해외주식형 중에서 인도주식 유형인 공모펀드는 몇 개야?")
    assert "인도주식" in pc, "Z10 — 소분류 값이 플래너에 없으면 리터럴을 지어낸다"
    pc2 = ctx.planner_context(FUNDS, "미래에셋코어테크 펀드의 설정일과 모펀드 알려줘")
    assert "ext_fund_page 를 FROM 에 두지 않는다" in pc2, "KG-006"


# ── DOM-03 · 도메인 간 컬럼명 충돌 — 컬럼 단위 가드는 테이블로 한정한다 ──────────────
def test_forbidden_literal_guard_is_table_scoped():
    """채권용 curr_cd 규칙이 펀드 SQL 을 기각했다(DOM-03). 두 테이블의 사실이 정반대다.

    domestic_bonds.curr_cd = KRW·000 뿐 → 외화 조건 금지가 맞다.
    public_funds.curr_cd  = 기본모수에 USD 152·EUR 29·JPY 4·SEK 1·AUD 1 → `!= 'KRW'` 가 정답 SQL 이다.
    """
    from src.runtime.pipeline import forbidden_literal_use as f
    assert f("SELECT pd_nm FROM domestic_bonds WHERE curr_cd <> 'KRW' LIMIT 30"), "채권 규칙은 살아 있어야 한다"
    assert f("SELECT pd_nm FROM domestic_bonds WHERE curr_cd = '000' LIMIT 30")
    assert f("SELECT itm_nm FROM public_funds WHERE curr_cd != 'KRW' LIMIT 30") is None
    assert f("SELECT itm_nm FROM public_funds WHERE curr_cd <> 'KRW' LIMIT 30") is None


def test_dom03_non_krw_counts():
    """가드 통과 뒤 실제로 gold(131펀드/187클래스)가 나오는가."""
    con = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
    n = con.execute(
        "SELECT COUNT(*) FROM public_funds "
        "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND curr_cd != 'KRW'"
    ).fetchone()[0]
    con.close()
    assert n == 187, f"비원화 클래스 수가 바뀌었다: {n}"
