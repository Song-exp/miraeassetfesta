# -*- coding: utf-8 -*-
"""2026-09-06 라운드 15 — 3차 재배포 실측 ETF 오답 5부류.

① B2 "KODEX 200 운용사랑 기초지수 알려줘" — '운용사' 한 낱말로 public_funds 로 가서 0행 → "확인되지 않습니다".
② B5 "KODEX 200이랑 TIGER 200 중에 뭐가 더 커?" — 기본모수 주입이 `A OR B` 에 AND 를 덧붙여 최상위 혼용을 만들었고 검사기가 기각.
③ D2 "최근 한 달 자금 유입이 많은 ETF" — 없는 축인데 게이트를 통과해 일거래대금을 '자금 유입액' 으로 답함.
④ A2 "에코프로 자회사 편입 ETF 중 순자산 큰 상품" — 결과는 순자산순인데 답변이 1.58조를 1위·25.8조를 2위로 적음.
⑤ C5 "2026년 상장 ETF 중 월배당" — 25행을 받고 5개만 적으며 총 건수 미고지.
"""
import pytest

from src.runtime import gate, pipeline as P, router
from src.runtime.loader import connect_readonly, load_context


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def con():
    return connect_readonly()


def test_manager_word_does_not_beat_grounded_product_name(ctx):
    """① 값이 상품군을 특정하면 '운용사' 폴백은 서지 않는다."""
    assert router.route("KODEX 200 운용사랑 기초지수 알려줘", ctx).tables == ["domestic_etfs"]
    assert router.route("TIGER 200 운용사 어디야?", ctx).tables == ["domestic_etfs"]
    # 불개입 — 상품 이름이 없는 순수 운용사 질의는 종전대로 펀드 마스터
    assert router.route("순자산이 가장 큰 운용사 상위 3개", ctx).tables == ["public_funds"]
    assert router.route("펀드를 가장 많이 운용하는 운용사 상위 5개", ctx).tables == ["public_funds"]
    # 상품 명사가 있으면 그것이 머리다(종전 동작)
    assert router.route("운용사별 ETF 개수 상위 5곳 알려줘", ctx).tables == ["domestic_etfs", "overseas_etfs"]


def test_base_population_injection_keeps_or_branch_parenthesised(con):
    """② 모수 절이 최상위 OR 뒤에 붙어도 실행 가능한 SQL 이어야 한다."""
    hcx = ("SELECT TRIM(pd_abrv_nm) AS 상품명, du_last_aum FROM domestic_etfs "
           "WHERE replace(pd_abrv_nm,' ','') LIKE '%KODEX200%' OR replace(pd_abrv_nm,' ','') LIKE '%TIGER200%' "
           "AND pd_grp_no = 'ETF' AND pd_sale_yn = 1 ORDER BY du_last_aum DESC LIMIT 2")
    assert P.validate_sql(hcx) is not None                    # 종전엔 여기서 기각되고 끝났다
    fixed, changed = P.ensure_or_group_parens(hcx)
    assert changed and P.validate_sql(fixed) is None
    rows = con.execute(fixed).fetchall()
    assert [r[0] for r in rows] == ["KODEX 200", "TIGER 200"] and rows[0][1] > rows[1][1]
    # 멱등 — 이미 접힌 문장은 다시 건드리지 않는다
    assert P.ensure_or_group_parens(fixed) == (fixed, False)


def test_guard_chain_folds_parens_after_late_injections(ctx):
    """② 체인 끝 재괄호화 — 중간 가드가 AND 를 덧붙여도 검사기를 통과한다."""
    hcx = ("SELECT TRIM(pd_abrv_nm) AS 상품명, du_last_aum FROM domestic_etfs "
           "WHERE replace(pd_abrv_nm,' ','') LIKE '%KODEX200%' OR replace(pd_abrv_nm,' ','') LIKE '%TIGER200%' "
           "ORDER BY du_last_aum DESC LIMIT 2")
    out = P._apply_sql_guards(hcx, "KODEX 200이랑 TIGER 200 중에 뭐가 더 커?", None, None,
                              lambda *a, **k: None, ctx, ["domestic_etfs"], False)
    assert "pd_grp_no" in out, out                             # 모수는 붙었고
    assert P.validate_sql(out) is None, out                    # 문장은 살아 있다


def test_fund_flow_axis_is_gated(ctx):
    """③ 자금유출입은 수록 축이 아니다 — 거래대금·순자산으로 바꿔 답하지 않는다."""
    for q in ["최근 한 달 자금 유입이 많은 ETF 알려줘", "자금이 가장 많이 몰린 ETF 알려줘", "설정액 증가한 ETF"]:
        g = gate.check(q, ctx, ["domestic_etfs"])
        assert g.rejected, q
        assert "자금 유출입" in g.answer and "거래대금" in g.answer
    # 불개입 — 수록된 축은 그대로 답한다
    for q in ["순자산 큰 ETF 알려줘", "거래대금 많은 ETF 알려줘", "KODEX 200 순자산 알려줘"]:
        assert not gate.check(q, ctx, ["domestic_etfs"]).rejected, q


def test_answer_list_order_follows_rows():
    """④ 정렬을 지시한 질의의 답변 순서는 결과 순서를 따른다."""
    rows = ("상품명 | 순자산_원_억원\nKODEX 200 | 258,342억원\nTIGER 200 | 105,772억원\n"
            "KODEX 200TR | 78,892억원\nKODEX 2차전지산업 | 15,812억원")
    sql = "SELECT m.pd_abrv_nm, m.du_last_aum FROM domestic_etfs m ORDER BY \"순자산_원\" DESC LIMIT 30"
    a = ("1. KODEX 2차전지산업: 순자산 15,812억원\n2. KODEX 200: 순자산 258,342억원\n"
         "3. TIGER 200: 순자산 105,772억원\n4. KODEX 200TR: 순자산 78,892억원")
    out, fixed = P.reorder_answer_list(a, rows, sql)
    assert fixed
    assert out.splitlines()[0].startswith("1. KODEX 200:")
    assert out.splitlines()[3].startswith("4. KODEX 2차전지산업")
    # 불개입 — 이미 결과 순서면 그대로
    assert P.reorder_answer_list(out, rows, sql)[1] is False
    # 불개입 — 결과에 없는 이름이 섞이면 순서를 판정하지 않는다(다른 가드 몫)
    assert P.reorder_answer_list("1. 없는상품: 1원\n2. KODEX 200: 258,342억원", rows, sql)[1] is False
    # 불개입 — ORDER BY 가 없으면 순서에 뜻이 없다
    assert P.reorder_answer_list(a, rows, "SELECT pd_abrv_nm FROM domestic_etfs LIMIT 30")[1] is False


def test_list_answer_states_total_count():
    """⑤ 받은 행보다 적게 적었으면 총 건수를 밝힌다."""
    rows = "pd_abrv_nm\n" + "\n".join(f"ETF{i}" for i in range(25))
    sql = "SELECT pd_nm, pd_abrv_nm FROM domestic_etfs WHERE pd_dvid_cycl = 'M' AND pd_lstg_dt BETWEEN 20260101 AND 20261231 LIMIT 30"
    a = "\n".join(f"{i}. ETF{i-1}" for i in range(1, 6))
    out, added = P.ensure_list_total(a, sql, rows, 25)
    assert added and "25건" in out and "5개" in out
    # 불개입 — 총 건수를 이미 말했으면 덧붙이지 않는다
    assert P.ensure_list_total(a + "\n\n총 25건입니다.", sql, rows, 25)[1] is False
    # 불개입 — 전 행을 적었으면 덧붙이지 않는다
    full = "\n".join(f"{i}. ETF{i-1}" for i in range(1, 26))
    assert P.ensure_list_total(full, sql, rows, 25)[1] is False
    # 불개입 — 집계(COUNT) 답변에는 걸지 않는다
    assert P.ensure_list_total(a, "SELECT COUNT(*) FROM domestic_etfs", rows, 25)[1] is False
