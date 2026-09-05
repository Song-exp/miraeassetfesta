# -*- coding: utf-8 -*-
"""20R — 숫자 옆에 붙어야 할 한 마디를 조립기가 적는다 (DOM-08 · T13, 결함 ⑧).

  DOM-08  "환헤지되는 공모펀드는 몇 개야?"  → 1,328펀드는 정확한데 `exchdg_yn` 은
          판매중·공모의 **39% 가 미수록**이다. Y 만 세고 그 말을 안 하면 "나머지는 환헤지를
          안 한다" 로 읽힌다 — 실제로는 모르는 것이다.
  T13     "미국에 투자하는 공모펀드 알려줘"  → 국가 태그(USA) 98펀드 vs 지역 대분류 114펀드.
          **두 축이 갈리는 질문**이라 어느 쪽을 썼는지 밝히지 않으면 수를 검증할 수 없다.

🔴 yaml 의 `answer_policy` 를 그대로 붙이지 않는다 — 그건 HCX 에게 주는 **지시문**이지
   사용자에게 보일 문장이 아니다("→ '해당사항 없음'"). 결측률은 DB 에서 직접 센다.
"""
import json
import re

import pytest

from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import answer_question, country_axis_note, flag_missing_note

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


@pytest.fixture(scope="module")
def probe():
    with open("eval/probe_funds_2026-09-05_r3.json", encoding="utf-8") as f:
        return {r["qid"]: r for r in json.load(f)}


def test_missing_rate_is_counted_from_the_db():
    sql = ("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' "
           "AND (prvo_pbff_desc = '공모' AND exchdg_yn = 'Y') LIMIT 30")
    note = flag_missing_note(sql)
    assert note and "39%" in note and "환헤지여부" in note, note
    assert "'아니오' 라는 뜻이 아닙니다" in note


def test_base_population_flag_is_skipped():
    """🔴 `sale_yn` 은 모든 질의에 붙어 있어 늘 먼저 잡힌다 — 건너뛰지 않으면 엉뚱한 컬럼을 고지한다."""
    assert flag_missing_note("SELECT COUNT(*) FROM public_funds WHERE sale_yn='판매중' LIMIT 30") is None


def test_axis_note_names_the_axis():
    sql = ("SELECT itm_no FROM public_funds WHERE ',' || prfd_attr_cds || ',' LIKE '%,USA,%' "
           "AND prvo_pbff_desc = '공모' LIMIT 30")
    note = country_axis_note(sql, "미국에 투자하는 공모펀드 알려줘")
    assert note and "USA" in note and "국가 태그" in note, note
    assert country_axis_note("SELECT itm_no FROM public_funds WHERE sale_yn='판매중'", "펀드 알려줘") is None


def _replay(ctx, rec):
    sql = re.findall(r"(?:재생성 SQL|SQL 생성)[^\n]*\n(SELECT[^\n]+)", rec["think_trace"])[-1]

    class P:
        def plan_sql(self, q, g):
            return sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX-CALLED"

    return answer_question(rec["qid"], rec["question"], planner=P(), ctx=ctx).answer or ""


def test_dom08_end_to_end(ctx, probe):
    ans = _replay(ctx, probe["DOM-08"])
    assert "1,328" in ans and "39%" in ans, ans


def test_t13_end_to_end(ctx, probe):
    ans = _replay(ctx, probe["T13"])
    assert "USA" in ans and "국가 태그" in ans, ans


@pytest.mark.parametrize("qid", ["FND-012", "X21"])
def test_untouched(ctx, probe, qid):
    """플래그·국가 축이 없는 질의에는 아무것도 붙지 않는다."""
    ans = _replay(ctx, probe[qid])
    assert "미수록입니다" not in ans and "국가 태그" not in ans, ans
