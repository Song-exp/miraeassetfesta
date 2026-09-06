# -*- coding: utf-8 -*-
"""라운드35 P1-4·P1-7 — 개수 의도와 모수 표기 (사고 #100·#97).

P1-4 개수 조립기는 SQL 모양만 보고 질문이 개수를 물었는지 보지 않았다. '1184 지금 살 수 있어?' 가
      COUNT 로 나가 "조건에 해당하는 채권은 총 385종목"(그 발행사 전체)으로 답했다.
P1-7 규칙 `기본모수` 는 "답변에 모수를 밝힌다" 고 선언하는데 조립기는 기준일만 적었다 —
      산금채 503종목 중 4종목이 만기 경과로 빠져 499 가 됐는데 그 말이 없었다.
"""

import json
import pathlib

import pytest

from src.runtime.loader import db_path
from src.runtime.pipeline import _bond_count_answer, drop_unasked_count_on_named_item as drop

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")
ROOT = pathlib.Path(__file__).resolve().parents[1]

ITEM_COUNT = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds "
              "WHERE TRIM(pd_nm) = '한국전력공사채권1184' AND curr_cd = 'KRW' AND mat_dt >= 20260824 LIMIT 30")


def test_지목_종목에_안_물은_COUNT_는_컬럼조회로():
    out, fired = drop(ITEM_COUNT, "한국전력공사채권1184 지금 살 수 있어?")
    assert fired and out.startswith("SELECT * FROM domestic_bonds")
    assert "TRIM(pd_nm) = '한국전력공사채권1184'" in out          # 조건은 그대로 — 걷는 것은 COUNT 뿐


@pytest.mark.parametrize("sql, q, why", [
    (ITEM_COUNT, "한국전력공사채권1184 몇 종목이야?", "개수를 물었다"),
    ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(pd_pbcm) = '한국전력공사(주)' LIMIT 30",
     "한국전력공사 채권 살 수 있어?", "종목 지목이 없다 — 발행사 문형의 개수는 옳은 답이다"),
    ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(bd_knd)='통화안정채권' LIMIT 30",
     "통안채 몇 개 있어?", "주어 정규식엔 안 걸리지만 개수 문항이다"),
    ("SELECT COUNT(*) FROM domestic_bonds WHERE TRIM(pd_nm)='풍산109' GROUP BY pd_no LIMIT 30",
     "풍산109 살 수 있어?", "GROUP BY 가 있으면 불개입"),
])
def test_불개입(sql, q, why):
    assert drop(sql, q)[1] is False, why


def test_eval_개수문항은_전부_불개입():
    """지금 옳게 답하는 개수 문항을 하나도 잃지 않는다."""
    qs = []
    for p in sorted((ROOT / "eval").glob("questions_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("question"):
                    qs.append(d["question"])
    cnt_sql = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(bd_knd)='통화안정채권' LIMIT 30"
    assert [q for q in qs if drop(cnt_sql, q)[1]] == []       # 종목 지목이 없으니 전 문항 불개입


# ── P1-7 모수 표기 ────────────────────────────────────────────────────────────────────────
def test_구매가능_모수를_쓰면_모수를_밝힌다():
    sql = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 "
           "AND (TRIM(bd_knd)='특수은행채' AND TRIM(pd_pbcm)='한국산업은행') LIMIT 30")
    out = _bond_count_answer(sql, "c\n499", 1, "산금채는 몇 종목이야?")
    assert "499종목" in out and "원화·만기 미도래 기준" in out and "2026-08-24" in out


def test_모수를_안_썼으면_붙이지_않는다():
    out = _bond_count_answer("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(bd_knd)='특수은행채' LIMIT 30",
                             "c\n1310", 1, "특수은행채는 몇 종목이야?")
    assert "1,310종목" in out and "원화·만기 미도래" not in out
