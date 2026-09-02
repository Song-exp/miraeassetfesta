# -*- coding: utf-8 -*-
"""think_trace 관찰성 — 팀이 "KG·온톨로지를 의도대로 썼는가" 를 눈으로 볼 수 있는가.

🔴 이 테스트가 지키는 것은 답변 정확도가 아니라 **검토 가능성**이다.
   챗봇이 고른 SQL 이 잘려 보이면, 조건식이 틀렸는지 KG 매핑이 틀렸는지 구분할 수 없다.
   (2026-08-30: think_trace 가 SQL 을 120자에서 잘라 실제 실행문을 볼 수 없었다.)
"""

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question

needs_db = pytest.mark.skipif(not db_path().exists(), reason="DB 없음 — build_db.py 선행 필요")

# 120자를 넘는 SQL — 잘림이 있으면 반드시 걸린다
LONG_SQL = (
    "SELECT pd_nm, pd_itm_no, cu_fund_mgmt_co, du_last_aum FROM domestic_etfs "
    "WHERE du_last_aum IS NOT NULL AND du_last_aum > 0 ORDER BY du_last_aum DESC LIMIT 5"
)
NO_LIMIT_SQL = "SELECT COUNT(*) AS n FROM domestic_etfs WHERE pd_grp_no = 'ETF' AND cu_fund_mgmt_co IS NOT NULL"


class FakePlanner:
    """plan_sql·compose_answer 시그니처만 흉내낸다 — HCX 호출 0회."""

    def __init__(self, sql):
        self.sql = sql
        self.grounding = None

    def plan_sql(self, question, grounding):
        self.grounding = grounding
        return self.sql

    def compose_answer(self, question, rows, answer_rules=""):
        return "테스트 답변"


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@needs_db
def test_think_trace_carries_full_sql(ctx):
    """실행한 SQL 전문이 think_trace 에 남는다 — 잘리면 조건식을 검토할 수 없다."""
    assert len(LONG_SQL) > 120, "잘림을 검출하려면 120자를 넘겨야 한다"
    r = answer_question("T-SQL", "순자산이 큰 국내 ETF 5개", planner=FakePlanner(LONG_SQL), ctx=ctx)
    # 4R B-4: SELECT 의 du_last_aum 에 억원 열이 병기되고, 8R B-4″-b: WHERE 에 ETF 기본모수가 주입되므로
    # 원문 그대로가 아니다 — 이 테스트가 지키는 것은 **실행한 SQL 전문이 잘리지 않고 trace 에 실리는가** 뿐이다.
    assert r.sql in r.think_trace and len(r.sql) > 120, r.sql
    assert LONG_SQL.split(" FROM ", 1)[0] in r.sql and r.sql.endswith("ORDER BY du_last_aum DESC LIMIT 5")
    assert "억원" in r.sql


@needs_db
def test_result_exposes_executed_sql(ctx):
    """로그·UI 가 쓸 수 있도록 SQL 이 별도 필드로 나온다."""
    r = answer_question("T-SQL2", "순자산이 큰 국내 ETF 5개", planner=FakePlanner(LONG_SQL), ctx=ctx)
    assert r.sql.startswith(LONG_SQL.split(" FROM ", 1)[0]) and "억원" in r.sql
    assert r.sql.endswith("ORDER BY du_last_aum DESC LIMIT 5") and "du_last_aum IS NOT NULL" in r.sql


@needs_db
def test_executed_sql_is_the_corrected_one(ctx):
    """LIMIT 보정이 일어나면 **보정된 실제 실행문**이 남는다 — 생성 원문이 아니다."""
    r = answer_question("T-SQL3", "국내 ETF 몇 개야?", planner=FakePlanner(NO_LIMIT_SQL), ctx=ctx)
    assert r.sql.startswith(NO_LIMIT_SQL) and "LIMIT" in r.sql
    assert r.sql in r.think_trace


@needs_db
def test_result_exposes_grounding_handed_to_planner(ctx):
    """플래너에 실제로 넘어간 근거문서 원문이 나온다 — KG·yaml 이 쓰였는지의 유일한 증거다."""
    p = FakePlanner(LONG_SQL)
    r = answer_question("T-GRD", "순자산이 큰 국내 ETF 5개", planner=p, ctx=ctx)
    assert r.grounding == p.grounding
    assert "# 스키마" in r.grounding


@needs_db
def test_trace_names_grounding_blocks(ctx):
    """근거문서에 어떤 블록이 실렸는지 trace 로 알 수 있다 — 글자 수만으로는 알 수 없다."""
    r = answer_question("T-GRD2", "미래에셋자산운용이 운용하는 국내 ETF 5개",
                        planner=FakePlanner(LONG_SQL), ctx=ctx)
    plan = [ln for ln in r.think_trace.splitlines() if "[Plan] 근거문서" in ln][0]
    assert "KG 개체 매핑" in plan and "도메인 규칙" in plan and "스키마" in plan
    # 블록 이름만 — 블록 안의 지시문 주석까지 긁어오면 요약이 아니다
    assert "IN 으로" not in plan
    # 2026-08-30 R-5 — 답변불가 규칙 블록(enums/_refusal.yaml)이 항상 실린다
    # 2026-08-31 — ETF clarify 블록 신설(557eb3a)로 되묻기 규칙도 실린다
    assert plan.split("구성: ")[1].split(" + ") == ["KG 개체 매핑", "도메인 규칙", "되묻기 규칙", "답변불가 규칙", "스키마"]


@needs_db
def test_rejected_sql_still_visible(ctx):
    """Guard 가 기각해도 무엇을 기각했는지 보여야 한다 — 안 보이면 원인을 못 찾는다."""
    bad = ("SELECT name, type, rootpage, sql FROM sqlite_master WHERE name LIKE '%etf%' "
           "AND type = 'table' ORDER BY name COLLATE NOCASE LIMIT 10")
    assert len(bad) > 120
    r = answer_question("T-BAD", "테이블 목록", planner=FakePlanner(bad), ctx=ctx)
    assert "[Guard] SQL 기각" in r.think_trace
    assert bad in r.think_trace
