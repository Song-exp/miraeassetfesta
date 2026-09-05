# -*- coding: utf-8 -*-
"""20R — 랭킹 기계 조립이 비켜가던 세 자리 (2026-09-05 3차 실측).

3차의 회귀·하락 3건(U14 · FND-001 · FND-007)은 **전부 같은 자리**였다: 셋 다 2차엔 기계 조립이
탔는데 3차엔 HCX 산문으로 떨어져 클래스명을 펀드명처럼 냈다("삼성MMF법인제1호 **C 클래스**").
원인은 `ensure_fund_rank_representative`(GROUP BY 펀드키 주입)가 세 가지 다른 이유로 무음 종료한 것.

  FND-001  ORDER BY 4 ASC, 3 DESC  → 첫 키만 봐서 4번(위험등급명)이 랭킹 컬럼이 아니라 None
  FND-007  LEFT JOIN ext_fund_page → 컬럼을 하나도 안 쓰는데 `join` 이 보이면 가드가 통째로 빠진다
  U14      ORDER BY 3 = COUNT(*)   → 축이 안 잡혀 None. 질문은 '1년 수익률이 가장 높은' 인데
"""
import pytest

from src.runtime import guard
from src.runtime.loader import db_path, load_context
from src.runtime.pipeline import (_axis_from_question, _fund_sort_target, answer_question,
                                  ensure_fund_rank_axis, ensure_fund_rank_representative)

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


class _NoHCX:
    def __init__(self, sql):
        self._sql = sql

    def plan_sql(self, q, g):
        return self._sql

    def compose_answer(self, q, rows, answer_rules=""):
        return "HCX-CALLED"


# ── ① ORDER BY 키를 전부 훑는다 ────────────────────────────────────────────
@pytest.mark.parametrize("sql, expect", [
    ("SELECT itm_no, TRIM(itm_nm), fd_nast_suma, zrin_fd_ivst_risk_grd_nm FROM public_funds "
     "ORDER BY 4 ASC, 3 DESC LIMIT 10", ("fd_nast_suma", "DESC")),          # 🔴 둘째 키가 축
    ("SELECT a, fd_nast_suma FROM public_funds ORDER BY fd_nast_suma DESC LIMIT 3",
     ("fd_nast_suma", "DESC")),                                             # 첫 키 — 종전과 동일
    ("SELECT a FROM public_funds ORDER BY MAX(fd_yr1_ern_r) DESC LIMIT 3", ("fd_yr1_ern_r", "DESC")),
    ("SELECT itm_no, COUNT(*) FROM public_funds GROUP BY 1 ORDER BY 2 DESC LIMIT 3", None),
])
def test_sort_target_scans_every_key(sql, expect):
    assert _fund_sort_target(sql) == expect


# ── ② 안 쓰는 ext 조인 제거 ────────────────────────────────────────────────
FND007 = ("SELECT DISTINCT p.itm_no, p.itm_nm, p.fd_nast_suma FROM public_funds p "
          "LEFT JOIN ext_fund_page e ON p.itm_no=e.itm_no "
          "WHERE zrin_ptn_nm = 'MMF' AND p.sale_yn='판매중' ORDER BY p.fd_nast_suma DESC LIMIT 3")


def test_drop_unused_ext_join_unblocks_the_rank_guard():
    assert ensure_fund_rank_representative(FND007, "MMF 중에서 순자산이 가장 큰 공모펀드 3개 알려줘")[1] is False
    out, dropped = guard.drop_unused_ext_join(FND007)
    assert dropped == ["ext_fund_page"] and "ext_fund_page" not in out
    assert ensure_fund_rank_representative(out, "MMF 중에서 순자산이 가장 큰 공모펀드 3개 알려줘")[1] is True


@pytest.mark.parametrize("sql, why", [
    ("SELECT p.itm_no, e.mgmt_co_nm FROM public_funds p LEFT JOIN ext_fund_page e ON p.itm_no=e.itm_no",
     "ext 컬럼을 쓰면 유지"),
    ("SELECT p.itm_no FROM public_funds p JOIN ext_fund_page e ON p.itm_no=e.itm_no",
     "INNER 는 대상이 아니다 — 걷어내면 모수가 넓어진다"),
])
def test_drop_unused_ext_join_no_touch(sql, why):
    assert guard.drop_unused_ext_join(sql) == (sql, []), why


# ── ③ 질문이 지목한 정렬축 ─────────────────────────────────────────────────
U14 = ("SELECT or_co_xtn_itt_cd, prvo_pbff_desc, COUNT(*), fd_yr1_ern_r FROM public_funds "
       "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL "
       "GROUP BY or_co_xtn_itt_cd HAVING COUNT(*) > 1 ORDER BY 3 DESC LIMIT 3")


def test_axis_from_question():
    assert _axis_from_question("1년 수익률이 가장 높은 공모펀드 3개") == "fd_yr1_ern_r"
    assert _axis_from_question("1개월 수익률 상위") == "fd_mm1_ern_r"
    assert _axis_from_question("순자산 큰 3개") == "fd_nast_suma"
    assert _axis_from_question("위험등급 낮은 펀드") is None


def test_rank_axis_is_corrected():
    assert _fund_sort_target(U14) is None
    out, fixed = ensure_fund_rank_axis(U14, "1년 수익률이 가장 높은 공모펀드 3개는 클래스가 몇 개씩이야?")
    assert fixed and _fund_sort_target(out) == ("fd_yr1_ern_r", "DESC")


@pytest.mark.parametrize("sql, q, why", [
    (U14, "공모펀드가 가장 많은 운용사 3곳", "질문이 랭킹 축을 이름으로 지목하지 않았다"),
    ("SELECT itm_no, fd_nast_suma FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%코어테크%' "
     "ORDER BY 1 LIMIT 3", "미래에셋코어테크 펀드 순자산 알려줘",
     "🔴 개별 조회엔 불개입 — 랭킹으로 읽히면 기점오류 제외가 끼어든다(고정선 R4·S3)"),
    # (삭제 2026-09-05 밤) 'SELECT 에 없으면 물러남' 케이스 — U14 서버 원문 실측으로 뒤집혔다: 축 컬럼은 덧붙인다 (test_round25_axis_select)
])
def test_rank_axis_no_touch(sql, q, why):
    assert ensure_fund_rank_axis(sql, q) == (sql, False), why


def test_u14_end_to_end(ctx):
    """세 조치가 함께 걸려 2차 수준으로 돌아온다 — HCX 0회."""
    r = answer_question("U14", "1년 수익률이 가장 높은 공모펀드 3개는 클래스가 몇 개씩이야?",
                        planner=_NoHCX(U14), ctx=ctx)
    ans = r.answer or ""
    assert "HCX-CALLED" not in ans
    assert "387.66%" in ans and "클래스 6개" in ans, ans
