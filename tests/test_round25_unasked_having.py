# -*- coding: utf-8 -*-
"""25R — 질문이 묻지 않은 개수 조건(HAVING COUNT) 걷기 · 채권 확장 (2026-09-05 · 사고 #77 곁가지 ⓑ).

"한국전력공사 채권은 이자를 몇 개월마다 줘?" 가 분포용 HAVING 을 달고 나갔다:
    GROUP BY bd_intp_tcd HAVING COUNT(DISTINCT pd_no) > 1 OR bd_intp_tcd IS NULL
한전은 이표채 한 범주뿐이라 티가 안 났지만 **(발행사×이자지급구분) 950 조합이 종목 1개**다 —
BNP PARIBAS SA(복리채 1 · 이표채 1)로 같은 질문을 던지면 0행 → "정보 없음"(사실 왜곡).

24R `drop_unasked_count_having`(펀드 고유키 묶음)의 확장. 경계는 **묶음 키의 종류가 아니라 질문**이다:
분포를 물었으면(`유형별로 알려줘`) GROUP BY 가 답의 축이라 손대지 않고, 분포 어휘가 없을 때만 걷는다.
24R 의 `test_분포_묶음에는_불개입` 이 그대로 통과해야 한다.

과적합 점검:
 ① 사례 표가 아니라 SQL 모양으로 판정한다 — HAVING 절의 모든 항이 COUNT 비교이거나 묶음 키 IS NULL 일 때만.
 ② `MAX(col) > 5`(`_insert_having` 이 WHERE 에서 옮겨 온 값 술어)·`col = MAX(col)` 은 분류 불가라 불개입.
 ③ 절 전체를 걷어 `OR` 잔반이 남지 않는다 — 종전 단항 절삭은 `… > 1 OR x IS NULL` 의 뒤 절을 매달아 뒀다.
 ④ eval 226문항 전건 대조: 걷힌 173건 중 개수 임계를 실제로 물은 문항 0(그런 문형은 `_MULTIPLICITY_Q` 가 먼저 잡는다).
"""
import sqlite3

import pytest

from src.runtime.loader import db_path
from src.runtime.pipeline import drop_unasked_count_having

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")

ACCIDENT = ("SELECT TRIM(bd_intp_tcd) AS bd_intp_tcd, COUNT(DISTINCT pd_no) FROM domestic_bonds "
            "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (TRIM(pd_pbcm) = '{p}') "
            "GROUP BY bd_intp_tcd HAVING COUNT(DISTINCT pd_no) > 1 OR bd_intp_tcd IS NULL "
            "LIMIT 30 /*M:BONDPOP*/")
Q_KEPCO = "한국전력공사 채권은 이자를 몇 개월마다 줘?"
Q_BNP = "BNP PARIBAS SA 채권은 이자를 몇 개월마다 줘?"


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
    yield c
    c.close()


# ── ① 사고 재현 — 걷어야 한다 · OR 잔반이 남으면 안 된다 ─────────────────────
@pytest.mark.parametrize("issuer, q", [("한국전력공사(주)", Q_KEPCO), ("BNP PARIBAS SA", Q_BNP)])
def test_accident_having_dropped(issuer, q):
    out, fixed = drop_unasked_count_having(ACCIDENT.format(p=issuer), q)
    assert fixed
    assert "having" not in out.lower()
    assert "OR bd_intp_tcd IS NULL" not in out          # 절 전체를 걷었다
    assert "GROUP BY bd_intp_tcd" in out                # 묶음은 남는다
    assert "/*M:BONDPOP*/" in out                       # 슬롯 표식 보존


def test_single_item_category_no_longer_vanishes(con):
    """ⓑ 의 실체 — 종목이 하나뿐인 범주가 통째로 사라지던 자리."""
    sql = ACCIDENT.format(p="BNP PARIBAS SA")
    assert con.execute(sql).fetchall() == []            # 종전: 0행
    out, fixed = drop_unasked_count_having(sql, Q_BNP)
    assert fixed
    assert sorted(con.execute(out).fetchall()) == [("complex", 0)][:0] + [("복리채", 1), ("이표채", 1)]


def test_kepco_value_unchanged(con):
    """한전은 이표채 한 범주라 값이 그대로여야 한다 — 걷어도 답이 바뀌지 않는다."""
    sql = ACCIDENT.format(p="한국전력공사(주)")
    out, _ = drop_unasked_count_having(sql, Q_KEPCO)
    assert con.execute(sql).fetchall() == con.execute(out).fetchall() == [("이표채", 385)]


def test_950_single_item_combinations_exist(con):
    """전수 근거 — 이 절이 감추는 (발행사×이자지급구분) 조합이 실제로 몇 개인가."""
    n = con.execute("SELECT COUNT(*) FROM (SELECT TRIM(pd_pbcm) p, TRIM(bd_intp_tcd) t "
                    "FROM domestic_bonds WHERE curr_cd='KRW' AND mat_dt>=20260824 "
                    "GROUP BY 1,2 HAVING COUNT(DISTINCT pd_no)=1)").fetchone()[0]
    assert n == 950, f"조합 수가 변했다: {n}"


# ── ② 분포를 물었으면 둔다 — 24R 경계 유지 ───────────────────────────────────
@pytest.mark.parametrize("sql, q", [
    ("SELECT zrin_btyp_nm, COUNT(*) AS cnt FROM public_funds GROUP BY zrin_btyp_nm HAVING cnt > 1 LIMIT 30",
     "유형별로 알려줘"),
    ("SELECT TRIM(bd_knd) AS k, COUNT(DISTINCT pd_no) AS cnt FROM domestic_bonds GROUP BY bd_knd HAVING cnt > 1 LIMIT 30",
     "채권 종류별 분포 알려줘"),
    ("SELECT TRIM(pd_pbcm) AS p, COUNT(DISTINCT pd_no) AS cnt FROM domestic_bonds GROUP BY pd_pbcm HAVING cnt > 1 LIMIT 30",
     "발행사별 채권 수 알려줘"),
    ("SELECT TRIM(bd_knd) AS k, COUNT(DISTINCT pd_no) AS cnt FROM domestic_bonds GROUP BY bd_knd HAVING cnt > 1 LIMIT 30",
     "채권 종류별로 몇 개씩 있어?"),
])
def test_distribution_question_untouched(sql, q):
    assert drop_unasked_count_having(sql, q)[1] is False, q


# ── ③ 질문이 개수를 물었으면 둔다 (24R) ───────────────────────────────────────
@pytest.mark.parametrize("q", [
    "클래스가 2개 이상인 펀드 알려줘", "클래스가 여러 개인 펀드", "중복된 종목 찾아줘",
    "채권을 여러 개 발행한 발행사", "종목이 2개 이상인 발행사 알려줘",
])
def test_multiplicity_question_untouched(q):
    sql = ("SELECT TRIM(pd_pbcm) AS p, COUNT(DISTINCT pd_no) AS cnt FROM domestic_bonds "
           "GROUP BY pd_pbcm HAVING cnt > 1 LIMIT 30")
    assert drop_unasked_count_having(sql, q)[1] is False, q


# ── ④ 값 술어 HAVING 은 걷지 않는다 (_insert_having 산물 보호) ───────────────
@pytest.mark.parametrize("sql", [
    "SELECT itm_no, MAX(fd_yr3_ern_r) FROM public_funds GROUP BY itm_no HAVING MAX(fd_yr3_ern_r) > 5 LIMIT 30",
    "SELECT itm_no, fd_yr1_ern_r FROM public_funds GROUP BY itm_no HAVING fd_yr1_ern_r = MAX(fd_yr1_ern_r) LIMIT 3",
    "SELECT itm_no FROM public_funds GROUP BY itm_no HAVING MAX(fd_nast_suma) IS NOT NULL LIMIT 30",
    "SELECT itm_no, MIN(dur) FROM domestic_bonds GROUP BY itm_no HAVING MIN(dur) < 3 LIMIT 30",
    "SELECT p, COUNT(*) AS cnt FROM domestic_bonds GROUP BY p HAVING cnt > 1 AND MAX(srfc_irt) > 5 LIMIT 30",
])
def test_value_predicate_having_kept(sql):
    assert drop_unasked_count_having(sql, "수익률 높은 상품 알려줘")[1] is False, sql


# ── ⑤ 절 경계가 흔들리는 모양은 불개입 ───────────────────────────────────────
@pytest.mark.parametrize("sql", [
    "SELECT p FROM (SELECT p, COUNT(*) c FROM domestic_bonds GROUP BY p HAVING COUNT(*) > 1) LIMIT 30",
    ("SELECT k, COUNT(*) AS cnt FROM domestic_bonds GROUP BY k HAVING cnt > 1 "
     "UNION SELECT k, COUNT(*) FROM domestic_etfs GROUP BY k LIMIT 30"),
])
def test_subquery_and_union_untouched(sql):
    assert drop_unasked_count_having(sql, Q_KEPCO)[1] is False


def test_no_group_by_or_no_having_untouched():
    assert drop_unasked_count_having(
        "SELECT pd_nm FROM domestic_bonds WHERE curr_cd='KRW' LIMIT 30", Q_KEPCO)[1] is False
    assert drop_unasked_count_having(
        "SELECT TRIM(bd_intp_tcd), COUNT(DISTINCT pd_no) FROM domestic_bonds GROUP BY 1 LIMIT 30",
        Q_KEPCO)[1] is False


# ── ⑥ '개별·차별·특별' 은 분포 어휘가 아니다 (○○별 규칙의 오폭 경계) ─────────
@pytest.mark.parametrize("q", ["개별 채권 알려줘", "특별한 채권 있어?", "차별화된 상품 추천해줘"])
def test_short_stem_byeol_is_not_distribution(q):
    sql = ("SELECT TRIM(bd_knd) AS k, COUNT(DISTINCT pd_no) AS cnt FROM domestic_bonds "
           "GROUP BY bd_knd HAVING cnt > 1 LIMIT 30")
    assert drop_unasked_count_having(sql, q)[1] is True, q
