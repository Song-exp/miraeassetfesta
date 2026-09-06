# -*- coding: utf-8 -*-
"""2026-09-06 라운드 16 — 최종 배포본 실측 오답 3건.

① A2 재실측: 순서 복원 가드가 **돌았는데도** 순서가 틀렸다 — 부분일치라 'KODEX 200TR' 이 'KODEX 200'(0번 행)에 붙어
   세 항목이 전부 0번으로 판정됐다. 긴 이름부터 맞추고 한 행은 한 번만 쓴다.
② C4: HCX 가 한글 테마어를 영문으로 옮겨 `pd_nm LIKE '%Covered Call%'` → 0행 → "상품 자체가 없습니다"(실제 62건).
③ D2: 부재 선언 게이트가 단일 테이블일 때만 발동해 국내+해외 2테이블 라우팅에서 통과했다. 일거래대금이 '자금 유입액' 으로 나갔다.
"""
import pytest

from src.runtime import gate, pipeline as P
from src.runtime.loader import connect_readonly, load_context


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def con():
    return connect_readonly()


ROWS_A2 = ("상품명 | 순자산_원_억원\nKODEX 200 | 258,342억원\nTIGER 200 | 105,772억원\nKODEX 200TR | 78,892억원\n"
           "KODEX 200타겟위클리커버드콜 | 59,451억원\nKODEX 2차전지산업 | 15,812억원")
SQL_A2 = "SELECT m.pd_abrv_nm, m.du_last_aum FROM domestic_etfs m ORDER BY \"순자산_원\" DESC LIMIT 30"


def test_reorder_matches_longest_name_first():
    """① 접두가 같은 이름이 섞여도 각 항목이 자기 행에 붙는다."""
    a = ("1. KODEX 200: 258,342억원\n2. KODEX 200TR: 78,892억원\n3. KODEX 200타겟위클리커버드콜: 59,451억원\n"
         "4. TIGER 200: 105,772억원\n5. KODEX 2차전지산업: 15,812억원")
    out, fixed = P.reorder_answer_list(a, ROWS_A2, SQL_A2)
    assert fixed
    got = [l.split(". ", 1)[1].split(":")[0] for l in out.splitlines()]
    assert got == ["KODEX 200", "TIGER 200", "KODEX 200TR", "KODEX 200타겟위클리커버드콜", "KODEX 2차전지산업"]
    assert P.reorder_answer_list(out, ROWS_A2, SQL_A2)[1] is False        # 멱등


def test_reorder_does_not_reuse_a_row():
    """① 같은 행에 두 항목이 붙지 않는다 — 붙으면 순서 판정이 무의미해진다."""
    a = "1. KODEX 200TR: 78,892억원\n2. KODEX 200: 258,342억원"
    out, fixed = P.reorder_answer_list(a, ROWS_A2, SQL_A2)
    assert fixed and out.splitlines()[0].startswith("1. KODEX 200:")


def test_english_theme_literal_restored_to_korean(con):
    """② 국내 상품명은 전부 한글이다 — 0건인 영문 리터럴을 질문의 한글 낱말로 되돌린다."""
    sql = ("SELECT pd_abrv_nm, pd_dvid_yield FROM domestic_etfs WHERE pd_grp_no = 'ETF' "
           "AND pd_dvid_yield > 0 AND pd_nm LIKE '%Covered Call%' AND pd_sale_yn = 1 ORDER BY 2 DESC LIMIT 3")
    out, tok = P.ensure_korean_name_literal(sql, "커버드콜 ETF 중에 분배율 높은 3개 알려줘")
    assert tok == "커버드콜"
    rows = con.execute(out.replace("/*g*/", "")).fetchall()
    assert len(rows) == 3 and rows[0][0] == "SOL 팔란티어커버드콜OTM채권혼합"
    # 불개입 — 리터럴이 한 건이라도 실재하면 손대지 않는다
    ok = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_nm LIKE '%KODEX%' LIMIT 5"
    assert P.ensure_korean_name_literal(ok, "KODEX 상품 알려줘")[1] is None
    # 불개입 — 해외·UNION 은 대상이 아니다(해외 상품명은 영문이다)
    ovs = "SELECT pd_nm FROM overseas_etfs WHERE pd_nm LIKE '%Covered Call%' LIMIT 5"
    assert P.ensure_korean_name_literal(ovs, "커버드콜 해외 ETF")[1] is None


def test_absent_axis_gated_when_all_routed_tables_lack_it(ctx):
    """③ 라우팅이 두 테이블이어도 양쪽 다 없는 축이면 기각한다."""
    for q in ["최근 한 달 자금 유입이 많은 ETF 알려줘", "자금이 가장 많이 몰린 ETF 알려줘"]:
        g = gate.check(q, ctx, ["domestic_etfs", "overseas_etfs"])
        assert g.rejected, q
        assert "자금 유출입" in g.answer
    # 불개입 — 한쪽에만 없는 축은 통과시킨다(다른 테이블이 답할 수 있다)
    assert not gate.check("추적오차 작은 ETF 알려줘", ctx, ["domestic_etfs", "overseas_etfs"]).rejected
    # 단일 테이블 판정은 종전대로
    assert gate.check("해외 ETF 중 추적오차 작은 것", ctx, ["overseas_etfs"]).rejected
    assert not gate.check("순자산 큰 ETF 알려줘", ctx, ["domestic_etfs", "overseas_etfs"]).rejected
