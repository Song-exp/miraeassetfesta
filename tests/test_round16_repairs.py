"""16R 수리 회귀 테스트 — 계획서 `docs/recheck_2026-09-03_round16_plan.md` §① 의 (b) 열이 지정한 이름.

각 테스트는 그 항목이 되돌아가면 실패한다. 값은 전부 DB 실측(하드코딩된 기대값은 gold 실측치).
"""
import re
import sqlite3

import pytest

from src.runtime import pipeline as P
from tests.test_guard_v2 import _R3_SQL


def _run(sql: str) -> tuple[str, int]:
    """SQL 을 실행해 (답변 입력 표, 행수) — 조립기 검증용."""
    con = P.connect_readonly()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rs = cur.fetchall()
    finally:
        con.close()
    body = [" | ".join(cols)] + [" | ".join(P._cell(v, c) for v, c in zip(r, cols)) for r in rs]
    return "\n".join(body), len(rs)


def _list_sql(tag: str) -> str:
    sql, _ = P.ensure_fund_list_grouping(_R3_SQL.replace("CHN", tag), "q")
    sql, _ = P.ensure_amount_eok_columns(sql)
    return sql


# ── P2-a 부류 AE — 목록 접기를 SQL 층으로 ────────────────────────────────────
def test_list_grouping_uses_rptt_axis():
    """목록 GROUP BY 축은 랭킹·개별 조회와 같은 `_FUND_GROUP_EXPR`(rptt) 다 — LIMIT 이 접기 위에 걸린다."""
    sql, done = P.ensure_fund_list_grouping(_R3_SQL, "중국에 투자하는 공모펀드 알려줘")
    assert done and f"GROUP BY {P._FUND_GROUP_EXPR}" in sql
    assert "대표번호" not in sql                      # 사후 접기 재료는 더 이상 싣지 않는다
    # 대표번호 축 총계 실측 — 심사관 gold: 중국 106 · 브라질 11 · 홍콩 14 · 러시아 8 · 인도네시아 1
    for tag, rptt in (("CHN", 106), ("BRA", 11), ("HKG", 14), ("RUS", 8), ("IDN", 1)):
        assert P._coverage_counts(_list_sql(tag))[2] == rptt, tag


def test_list_answer_no_post_fold():
    """T10 — mtco 공유로 흡수돼 사라졌던 펀드가 돌아오고, 클래스수가 LIMIT 전에 집계된다."""
    sql = _list_sql("BRA")
    rows, n = _run(sql)
    ans = P._list_answer(sql, rows, n)
    assert ans and n == 11
    assert "미래에셋삼바브라질" in ans                                  # 13억·5클래스 — 14R 사후 접기가 흡수했다
    assert re.search(r"미래에셋브라질하이인컴채권증권자투자신탁\[채권\]: 순자산 22억원 · 클래스 5개", ans)
    assert "전체 19개(클래스 42개)(대표번호 기준 11건)" in ans           # 머리줄 축 3종 병기


def test_list_answer_freeze_v8_v9():
    """감시선 — V8(홍콩 14행)·V9(러시아 8행)는 전수 gold 다. 행 수·클래스수 합이 움직이면 안 된다."""
    for tag, rows_n, classes in (("HKG", 14, 30), ("RUS", 8, 51)):
        sql = _list_sql(tag)
        rows, n = _run(sql)
        ans = P._list_answer(sql, rows, n)
        assert ans and n == rows_n, tag
        body = "\n".join(ans.splitlines()[2:])           # 머리줄의 총 클래스수는 빼고 행만 센다
        assert sum(int(m) for m in re.findall(r"클래스 (\d+)개", body)) == classes, tag


# ── P2-b 부류 AF — 기관 이름은 KG 정본으로, 번역은 HCX 에 맡기지 않는다 ──────
def test_org_name_column_canonicalized():
    """V7·W10 — 영문 법인명이 HCX 로 넘어가 즉석 번역됐다. 국내는 정본 치환, 해외 영문명은 불변(U8·Y16)."""
    sql = ("SELECT ref_fund_mgmt_co, SUM(du_last_aum) AS total_aum FROM domestic_etfs "
           "GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    rows = ("ref_fund_mgmt_co | total_aum\n"
            "Samsung Asset Management Co Ltd | 1.0\n"
            "Mirae Asset Global Investments Co Ltd | 2.0\n"
            "KB Asset Ltd | 3.0")
    out, touched = P.label_code_columns(rows, sql)
    assert touched == ["ref_fund_mgmt_co"]
    assert "삼성자산운용" in out and "미래에셋자산운용" in out and "KB자산운용" in out
    assert "글로벌" not in out and "인베스트먼트" not in out
    assert P.label_code_columns(out, sql) == (out, [])                # 멱등
    # 해외 ETF — label_official 이 없고 label_ko 가 영문명 자신이라 원값 그대로다
    ovs = "cu_fund_mgmt_co | du_last_aum\nBlackRock Fund Advisors | 1.0"
    assert P.label_code_columns(ovs, "SELECT cu_fund_mgmt_co, du_last_aum FROM overseas_etfs LIMIT 3") == (ovs, [])


# ── P3-a/P3-b KG ③-1·③-2 — 교차질의 가지 ─────────────────────────────────────
_X9 = ("(SELECT '공모펀드' AS 구분, COUNT(*) FROM public_funds WHERE or_co_xtn_itt_cd = '00080008' "
       "AND sale_yn = '판매중' AND prvo_pbff_desc = '공모') UNION ALL "
       "(SELECT '국내ETF', COUNT(*) FROM domestic_etfs "
       "WHERE ref_fund_mgmt_co = 'Mirae Asset Global Investments Co Ltd') LIMIT 30")


def test_distinct_count_labeled_union_branch():
    """X8·X9 — 라벨 리터럴이 앞에 오는 SELECT 항목에서도 `COUNT(*)` 를 찾아 펀드단위 집계로 교체한다."""
    q = "미래에셋자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야?"
    out, notes = P.apply_union_branch_guards(_X9, q)
    assert any("펀드단위 집계 교체" in nt for nt in notes)
    con = P.connect_readonly()
    try:
        assert [tuple(r)[1:] for r in con.execute(out)] == [(823, 2066), (230, None)]   # 823펀드/2,066클래스
    finally:
        con.close()
    # 단일 SELECT 개수 문항은 한 글자도 안 바뀐다(멱등 · 형태 불변)
    solo = ("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' "
            "AND prvo_pbff_desc = '공모' LIMIT 30")
    fixed, ok = P.ensure_fund_distinct_count(solo, "공모펀드는 몇 개야?")
    assert ok and '"펀드수"' in fixed and P.ensure_fund_distinct_count(fixed, "공모펀드는 몇 개야?") == (fixed, False)


def test_validate_sql_accepts_parenthesized_union():
    """Z13·CROSS-003 — 괄호 친 UNION 가지는 SQLite 문법이 아니다. 정규화해서 실행 가능한 한 문장으로 만든다."""
    with pytest.raises(sqlite3.OperationalError):
        P.connect_readonly().execute(_X9)                 # 원문은 SQLite 가 거부한다 — near "(" syntax error
    out, notes = P.apply_union_branch_guards(_X9, "미래에셋자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야?")
    assert "가지 괄호 제거(SQLite 복합 SELECT 문법)" in notes
    assert P.validate_sql(out) is None                    # 구조 게이트·EXPLAIN 둘 다 통과
