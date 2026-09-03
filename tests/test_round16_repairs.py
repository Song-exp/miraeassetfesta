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


# ── P3-c KG ③-3·③-4 — KG-008 별칭 충돌 제거 + 조립기 배선 ────────────────────
_KG008 = ("SELECT trim(trusc_xtn_itt_cd) AS 수탁회사명, COUNT(*) as 펀드수, SUM(fd_nast_suma) AS 수탁금액 "
          "FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
          "GROUP BY 1 ORDER BY SUM(fd_nast_suma) DESC LIMIT 3")
_KG008_Q = "공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘"


def test_entity_rank_drops_conflicting_alias():
    """가드가 심는 축과 이름이 겹치는 HCX 항목은 접미로 피하지 말고 지운다 — 결과 열에 동명이 남으면 안 된다."""
    out, ok = P.ensure_fund_entity_count_ranking(_KG008, _KG008_Q)
    assert ok and "__g" not in out
    assert out.count('AS "펀드수"') == 1 and not re.search(r"\bas\s+펀드수\b", out, re.I)
    assert P.ensure_fund_entity_count_ranking(out, _KG008_Q)[1] is False        # 멱등
    rows, n = _run(out)
    assert [c.strip() for c in rows.splitlines()[0].split(" | ")].count("펀드수") == 1


def test_entity_rank_answer_wired():
    """14R 은 이 조립기를 정의만 하고 호출부에 배선하지 않았다 — SQL 행 순서 그대로, 값 축은 펀드수."""
    out, _ = P.ensure_fund_entity_count_ranking(_KG008, _KG008_Q)
    rows, n = _run(out)
    ans = P._entity_count_rank_answer(out, rows, n)
    assert ans is not None
    assert "1. 홍콩상하이은행 서울지점(00020054): 펀드 714개(클래스 1,827개)" in ans      # gold 714·516·465
    assert "2. 국민은행(00020004): 펀드 516개" in ans and "3. 한국씨티은행(00020027): 펀드 465개" in ans
    import inspect
    src = inspect.getsource(P.answer_question)
    assert "_entity_count_rank_answer(" in src                                  # 호출부 배선


# ── P3-d KG ③-5 — label_official 형제 코드 IN (등호·IN 양쪽 · 역조회 경로 포함) ──
def test_org_label_codes_expands_in_predicate():
    """Z16 — `IN ('00080052')` 단일 원소도 형제 코드로 넓힌다. 브랜드 어간 질의(X12)는 넓히지 않는다."""
    con = P.connect_readonly()
    try:
        z16 = ("SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00080052') "
               "AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 30")
        out, ok = P.ensure_org_label_codes(z16, "키움투자자산운용이 운용하는 공모펀드는 몇 개야?")
        assert ok and "'00040013'" in out and "'00080052'" in out
        assert P.ensure_org_label_codes(out, "키움투자자산운용이 운용하는 공모펀드는 몇 개야?")[1] is False   # 멱등
        cnt, _ = P.ensure_fund_distinct_count(out, "키움투자자산운용이 운용하는 공모펀드는 몇 개야?")
        assert con.execute(cnt).fetchone() == (112, 354)          # gold 112펀드/354클래스
        # X12 — 질문이 브랜드 어간('슈로더')이라 정본 이름('키움투자자산운용')이 없다 → 불개입
        x12 = ("SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040013','00130003') "
               "AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 30")
        assert P.ensure_org_label_codes(x12, "슈로더가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?") == (x12, False)
        cnt12, _ = P.ensure_fund_distinct_count(x12, "슈로더가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?")
        assert con.execute(cnt12).fetchone() == (28, 59)          # 28펀드/59클래스 불변
    finally:
        con.close()


# ── P3-e KG ③-6·③-7 부류 H — 약관분류 축 확정 주입 ──────────────────────────
def test_ptn_axis_no_space_join():
    """Z5 회귀 — 공백을 지우고 대조하면 「글로벌 주식형」이 약관분류 `글로벌주식` 으로 붙어 자산군 축이 꺼졌다."""
    assert P._ptn_value_in_question("글로벌 주식형 공모펀드는 몇 개야?") is None
    assert P._ptn_value_in_question("중국주식 유형 공모펀드는 몇 개야?") == "중국주식"
    z5 = ("SELECT COUNT(*) FROM public_funds WHERE fd_ivst_rgn_desc IN ('글로벌') "
          "AND (zrin_btyp_nm = '주식형' OR (zrin_btyp_nm IS NULL AND (TRIM(or_attr_desc) = '주식형'))) "
          "AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 30")
    q = "글로벌 주식형 공모펀드는 몇 개야?"
    out, ok = P.ensure_fund_type_axis(z5, q)
    assert ok and "zrin_btyp_nm = '주식형'" in out and "or_attr_desc" not in out   # 반쪽 인용 제거
    cnt, _ = P.ensure_fund_distinct_count(out, q)
    con = P.connect_readonly()
    try:
        assert con.execute(cnt).fetchone() == (10, 18)          # 1순위 판정(정확 일치) 기준 10펀드/18클래스
    finally:
        con.close()


def test_ptn_axis_injected():
    """Z11·Z10·AA6·AA7 — 약관분류 값을 지명하면 `zrin_ptn_nm` 확정식이 축이다. 환각 컬럼 절은 함께 사라진다."""
    from src.runtime import loader
    loader.load_context()
    con = P.connect_readonly()
    try:
        for q, sql, gold in (
            ("중국주식 유형 공모펀드는 몇 개야?",
             "SELECT COUNT(*) FROM public_funds WHERE asset_class = '중국주식' AND fund_type = '공모' LIMIT 30",
             (205, 522)),
            ("해외주식형 중에서 인도주식 유형인 공모펀드는 몇 개야?",
             "SELECT COUNT(*) FROM public_funds WHERE zrin_btyp_nm = '해외주식형' AND sale_yn='판매중' "
             "AND prvo_pbff_desc='공모' LIMIT 30", (34, 98)),
            ("해외주식형 중에서 베트남주식 유형인 공모펀드는 몇 개야?",
             "SELECT COUNT(*) FROM public_funds WHERE zrin_btyp_nm = '해외주식형' AND sale_yn='판매중' "
             "AND prvo_pbff_desc='공모' LIMIT 30", (25, 84)),
            ("일본주식 유형 공모펀드는 몇 개야?",
             "SELECT COUNT(*) FROM public_funds WHERE zrin_btyp_nm LIKE '%일본%' AND sale_yn='판매중' "
             "AND prvo_pbff_desc='공모' LIMIT 30", (37, 91)),
        ):
            out, ok = P.ensure_fund_type_axis(sql, q)
            assert ok and P.ensure_fund_type_axis(out, q)[1] is False, q       # 멱등
            out, _ = P.ensure_fund_base_population(out, q, post=True)
            out, _ = P.ensure_fund_distinct_count(out, q)
            out, _ = P.drop_hallucinated_column_conjuncts(out)
            assert con.execute(out).fetchone() == gold, q       # (펀드수, 클래스수)
    finally:
        con.close()
    # 리터럴이 다른 절에 없으면 환각 절을 지우지 않는다 — 모수가 넓어지면 안 된다
    keep = "SELECT COUNT(*) FROM public_funds WHERE bogus_col = '없는값' AND sale_yn = '판매중' LIMIT 30"
    assert P.drop_hallucinated_column_conjuncts(keep) == (keep, [])
