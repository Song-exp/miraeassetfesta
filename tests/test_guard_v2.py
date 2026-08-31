# -*- coding: utf-8 -*-
"""paired v2(2026-08-31) 실측 실패에서 나온 가드 2건 — 곱슬따옴표 정규화 · 컬럼 환각 검출."""
import glob
import json
import os

import pytest

from src.runtime import guard
from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


def test_unknown_columns_catches_hallucination(ctx):
    # paired v2 실측 — 교차 혼동 환각: domestic_etfs 에 채권 컬럼(pd_risk_gcd)·없는 컬럼(cu_last_aum)
    bad = "SELECT pd_nm, cu_last_aum FROM domestic_etfs WHERE pd_risk_gcd = '11' LIMIT 5"
    unk = guard.unknown_columns(bad, ctx)
    assert "cu_last_aum" in unk and "pd_risk_gcd" in unk


def test_unknown_columns_ok_for_real_derived_columns(ctx):
    # remaining_days·after_tax_yield 는 채권 담당의 실존 파생 컬럼 — 오탐이면 안 된다
    ok = "SELECT pd_nm, remaining_days FROM domestic_bonds WHERE after_tax_yield > 3 LIMIT 5"
    assert guard.unknown_columns(ok, ctx) == []


def test_unknown_columns_no_false_positive_on_gold(ctx):
    """전 gold SQL 에서 오탐 0 이어야 한다 — AS 별칭·내장함수·문자열 리터럴이 걸리면 안 된다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in sorted(glob.glob(os.path.join(root, "eval", "questions_*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            q = json.loads(line)
            if q.get("gold_sql"):
                unk = guard.unknown_columns(q["gold_sql"], ctx)
                assert not unk, f"{q['qid']}: 오탐 {unk}"


def test_curly_quotes_normalized(ctx):
    from src.runtime.pipeline import answer_question

    class P:
        def plan_sql(self, q, g):
            return "SELECT pd_no FROM domestic_bonds WHERE TRIM(bd_knd) = ‘국고채권’ LIMIT 5"

        def compose_answer(self, q, rows, answer_rules=""):
            return "t"

    r = answer_question("T-QT", "국고채권 알려줘", planner=P(), ctx=ctx)
    assert "따옴표 정규화" in r.think_trace
    assert "‘" not in (r.sql or "")


def test_fund_base_population_injected():
    """v2 실패 1순위 — 펀드 랭킹 SQL 에 기본모수가 없으면 기계 주입한다(보정, 기각 아님)."""
    from src.runtime.pipeline import ensure_fund_base_population as f

    # WHERE 있는 랭킹 — 기존 조건은 괄호로 보존
    s, ok = f("SELECT itm_nm FROM public_funds WHERE fd_yr1_ern_r IS NOT NULL ORDER BY fd_yr1_ern_r DESC LIMIT 5",
              "1년 수익률 높은 펀드 알려줘")
    assert ok and "sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (fd_yr1_ern_r IS NOT NULL)" in s

    # WHERE 없는 랭킹 — GROUP/ORDER 앞에 WHERE 삽입
    s, ok = f("SELECT itm_nm FROM public_funds ORDER BY fd_nast_suma DESC LIMIT 5", "규모 큰 펀드")
    assert ok and "WHERE sale_yn = '판매중'" in s and s.index("WHERE") < s.upper().index("ORDER BY")

    # 발동 금지 4갈래 — 모수 언급 SQL · 사모 질문 · 교차(JOIN) · 랭킹 아님
    assert not f("SELECT itm_nm FROM public_funds WHERE sale_yn='판매완료' ORDER BY 1 LIMIT 5", "펀드")[1]
    assert not f("SELECT itm_nm FROM public_funds ORDER BY 1 LIMIT 5", "사모 펀드 중 큰 것")[1]
    assert not f("SELECT 1 FROM public_funds p JOIN ext_fund_holdings h ON 1=1 ORDER BY 1 LIMIT 5", "펀드")[1]
    assert not f("SELECT COUNT(*) FROM public_funds LIMIT 1", "펀드 몇 개")[1]


# ── 펀드 랭킹 대표행·근거컬럼·방향 가드 4종 (2026-08-31 밤 — FND-019·015·C03 실측 채점 후속) ──

_FND15_SQL = ("SELECT itm_no, TRIM(itm_nm), fd_mm6_ern_r, COUNT(*) as cnt, fd_daily_bas_dt FROM public_funds "
              "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_mm6_ern_r IS NOT NULL AND fd_mm6_ern_r > -100 "
              "GROUP BY or_co_xtn_itt_cd, CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no "
              "ELSE substr('0000000' || mtco_itm_no, -7) END ORDER BY 3 DESC LIMIT 5")


def test_fund_rank_representative():
    """FND-015 실측 — 펀드단위 GROUP BY 랭킹의 bare 정렬 컬럼은 MAX/MIN 으로 감싼다."""
    from src.runtime.pipeline import ensure_fund_rank_representative as f

    # 위치 표기(ORDER BY 3) — SELECT 3번째 항목이 정렬 컬럼
    s, ok = f(_FND15_SQL)
    assert ok and "MAX(fd_mm6_ern_r) AS fd_mm6_ern_r" in s
    assert not f(s)[1]                                     # 멱등 — 이미 감쌌으면 불개입
    # 이름 표기 + 하위 랭킹(ASC) → MIN
    low = ("SELECT itm_no, fd_yr1_ern_r FROM public_funds WHERE fd_yr1_ern_r > -100 "
           "GROUP BY or_co_xtn_itt_cd, mtco_itm_no ORDER BY fd_yr1_ern_r ASC LIMIT 5")
    s2, ok2 = f(low)
    assert ok2 and "MIN(fd_yr1_ern_r) AS fd_yr1_ern_r" in s2
    # 불개입 3갈래 — GROUP BY 없는 개별 조회 · 펀드단위 키 아닌 GROUP BY · JOIN(교차)
    assert not f("SELECT fd_yr1_ern_r FROM public_funds WHERE itm_nm LIKE '%코어테크%' ORDER BY fd_yr1_ern_r DESC LIMIT 10")[1]
    assert not f("SELECT zrin_btyp_nm, fd_yr1_ern_r FROM public_funds GROUP BY zrin_btyp_nm ORDER BY 2 DESC LIMIT 5")[1]
    assert not f("SELECT p.fd_yr1_ern_r FROM public_funds p JOIN ext_fund_holdings h ON 1=1 "
                 "GROUP BY p.or_co_xtn_itt_cd, p.mtco_itm_no ORDER BY 1 DESC LIMIT 5")[1]


def test_fund_return_error_exclusion():
    """FND-019 실측 — 18개월+ 수익률 랭킹에만 기점오류 3클래스 NOT IN 주입 (단기·개별 조회 미적용)."""
    from src.runtime.pipeline import ensure_fund_return_error_exclusion as f

    long_rank = _FND15_SQL.replace("fd_mm6_ern_r", "fd_yr1_ern_r")
    s, ok = f(long_rank)
    assert ok and "itm_no NOT IN ('KR5157450126','KR5153450511','KR5119470012')".replace("','", "', '") in s
    assert s.upper().index("NOT IN") < s.upper().index("GROUP BY")    # WHERE 자리에 주입
    assert not f(s)[1]                                     # 멱등
    # 단기(6개월) 랭킹 — 규칙의 적용 경계 그대로 불개입 (FND-015 검증 목적)
    assert not f(_FND15_SQL)[1]
    # 개별 조회(itm_nm LIKE) — 불개입
    assert not f("SELECT itm_no, fd_yr1_ern_r FROM public_funds WHERE itm_nm LIKE '%코어테크%' "
                 "ORDER BY fd_yr1_ern_r DESC LIMIT 10")[1]


def test_fund_evidence_columns():
    """FND-019 실측 — 등급 코드 사용·수익률 정렬 SQL 의 SELECT 에 등급명·태그를 병기 (답변 재료)."""
    from src.runtime.pipeline import ensure_fund_evidence_columns as f

    grade_rank = ("SELECT itm_no, TRIM(itm_nm), fd_yr1_ern_r, fd_daily_bas_dt FROM public_funds "
                  "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_gcd = 3 "
                  "AND fd_yr1_ern_r > -100 GROUP BY or_co_xtn_itt_cd, mtco_itm_no ORDER BY 3 DESC LIMIT 3")
    s, ok = f(grade_rank)
    assert ok and "zrin_fd_ivst_risk_grd_nm" in s and "zrin_attr_nms" in s
    assert s.index("zrin_fd_ivst_risk_grd_nm") < s.upper().index("FROM")   # SELECT 끝에 추가
    assert not f(s)[1]                                     # 멱등
    # 단일 건수 질의(COUNT, GROUP BY 없음) — 출력 의미가 바뀌므로 불개입
    assert not f("SELECT COUNT(*) FROM public_funds WHERE zrin_fd_ivst_risk_gcd IS NULL LIMIT 1")[1]

    # 🔴 식별 컬럼 없는 값-only SQL — 답변기가 이름을 지어낸 배포 실측(§6-2d 후속) 대응
    valonly = ("SELECT fd_yr1_ern_r FROM public_funds WHERE or_co_xtn_itt_cd = '00080008' "
               "AND itm_nm LIKE '%코어테크%' AND sale_yn = '판매중' LIMIT 30")
    s2, ok2 = f(valonly)
    assert ok2 and "itm_no" in s2 and "TRIM(itm_nm) AS itm_nm" in s2
    assert s2.index("itm_no") < s2.upper().index("FROM")
    # 분포 집계(COUNT + GROUP BY)에는 식별 컬럼을 붙이지 않는다 — 행 의미가 바뀐다
    dist = "SELECT zrin_btyp_nm, COUNT(*) FROM public_funds GROUP BY zrin_btyp_nm LIMIT 30"
    assert "itm_no" not in f(dist)[0]

    # 🔴 WHERE 에 쓴 서술 컬럼이 SELECT 에 없으면 붙인다 — FND-R09 실측: 27행을 조회하고도
    #    필터 근거(han_clas_policies)가 결과에 없어 답변기가 "찾을 수 없습니다" 로 버렸다(§6-2f)
    r09 = ("SELECT DISTINCT itm_nm, mtco_itm_no, fd_daily_bas_dt FROM public_funds "
           "WHERE prvo_pbff_desc = '공모' AND han_clas_policies LIKE '%전문투자자%' "
           "AND sale_yn = '판매중' LIMIT 30")
    s3, ok3 = f(r09)
    assert ok3 and "han_clas_policies" in s3.split("FROM")[0]
    assert not f(s3)[1]                                   # 멱등
    # 기본모수 컬럼(sale_yn·prvo_pbff_desc)은 근거가 아니라 모수라 붙이지 않는다
    assert "sale_yn" not in s3.split("FROM")[0]


def test_fund_safe_grade_direction():
    """FND-C03 실측 — '안전' 질의의 등급 필터가 1·2 로 뒤집혔으면 6 으로 교정."""
    from src.runtime.pipeline import ensure_fund_safe_grade_direction as f

    flipped = ("SELECT itm_no, TRIM(itm_nm), zrin_fd_ivst_risk_grd_nm FROM public_funds "
               "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_gcd = 1 "
               "ORDER BY itm_no ASC LIMIT 5")
    s, ok = f(flipped, "안전한 펀드 추천해줘")
    assert ok and "zrin_fd_ivst_risk_gcd = 6" in s and "= 1" not in s
    # 불개입 3갈래 — 등급 숫자 명시 질문(FND-002 회귀 보호) · '안전' 어휘 없음 · 이미 6
    assert not f(flipped, "위험등급 1등급 펀드 알려줘")[1]
    assert not f(flipped, "위험한 펀드 알려줘")[1]
    assert not f(s, "안전한 펀드 추천해줘")[1]


# ── 상품 고유명 소실 가드 (2026-08-31 밤 — FND-016 최악 등급 오답 §6-2d) ──

def test_residual_name_token():
    """KG 라벨에 붙은 잔여 고유명만 잡는다 — 띄어 쓴 질의·일반어·조사는 불개입."""
    from src.runtime.pipeline import residual_name_token as f

    L = ["'미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'"]
    assert f("미래에셋코어테크 펀드 1년 수익률 알려줘", L) == "코어테크"
    assert f("미래에셋퇴직연금솔로몬 펀드 총보수 알려줘", L) == "퇴직연금솔로몬"
    assert f("미래에셋전략배분적격TDF2045 펀드는 어떤 클래스들이 있어?", L) == "전략배분적격TDF2045"
    # 불개입 — 띄어 쓴 브랜드 질의(FND-C02 되묻기 보호) · 조사만 남음 · 도메인 일반어 · 매핑 없음
    assert f("미래에셋 펀드 보수 알려줘", L) is None
    assert f("미래에셋이 운용하는 공모펀드는 몇 개야?", L) is None
    assert f("미래에셋증권에서 살 수 있는 공모펀드는 몇 개야?", L) is None    # '증권' 은 일반어
    assert f("코어테크 펀드 수익률", []) is None


def test_fund_name_filter_injected():
    """FND-016 재현 SQL — 이름 필터 주입 + LIMIT 1 해제. 이미 이름으로 푼 SQL 은 불개입."""
    from src.runtime.pipeline import ensure_fund_name_filter as f

    bug = ("SELECT fd_yr1_ern_r FROM public_funds WHERE or_co_xtn_itt_cd = '00080008' "
           "AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND fd_yr1_ern_r IS NOT NULL "
           "AND fd_yr1_ern_r <> 0 LIMIT 1")
    s, ok = f(bug, "코어테크")
    assert ok and "itm_nm LIKE '%코어테크%'" in s and "LIMIT 30" in s and "LIMIT 1" not in s
    assert not f(s, "코어테크")[1]                                    # 멱등
    # 불개입 — 토큰 없음 · 이미 itm_nm LIKE 있음 · 펀드 테이블 아님
    assert not f(bug, None)[1]
    assert not f("SELECT itm_no FROM public_funds WHERE itm_nm LIKE '%코어테크%' LIMIT 5", "코어테크")[1]
    assert not f("SELECT pd_nm FROM domestic_bonds LIMIT 1", "코어테크")[1]
    # COUNT 질의의 LIMIT 1 은 유지 (한 행이 정답)
    s2, ok2 = f("SELECT COUNT(*) FROM public_funds WHERE sale_yn='판매중' LIMIT 1", "코어테크")
    assert ok2 and "LIMIT 1" in s2


# ── 값 위반 사유에 컬럼 오선택 명시 (2026-08-31 밤 — FND-026 오거절 §6-2e) ──

def test_value_violation_names_owner_column():
    """'해외주식형' 은 없는 값이 아니라 zrin_btyp_nm 의 값이다 — 사유가 그 컬럼을 짚어야 재생성이 고친다."""
    from src.runtime.loader import load_context
    from src.runtime import guard

    ctx = load_context()
    sql = ("SELECT itm_nm FROM public_funds WHERE or_attr_desc = '해외주식형' "
           "AND sale_yn = '판매중' LIMIT 30")
    vs = guard.check_values(sql, ctx)
    assert len(vs) == 1 and vs[0].owner == "zrin_btyp_nm"
    assert "zrin_btyp_nm" in str(vs[0])
    # 어느 컬럼에도 없는 값이면 owner 는 비고, 종전 메시지 형태를 유지한다
    sql2 = "SELECT itm_nm FROM public_funds WHERE or_attr_desc = '없는유형ZZZ' LIMIT 5"
    vs2 = guard.check_values(sql2, ctx)
    assert len(vs2) == 1 and not vs2[0].owner and "실제 값 예" in str(vs2[0])


def test_country_tag_rule_is_grounded():
    """FND-026 — 국가 질의에 태그 코드표가 프롬프트로 실려야 한다 (KG 에 국가→태그 매핑이 없다)."""
    from src.runtime.loader import load_context

    ctx = load_context()
    g = ctx.planner_context(["public_funds"], "중국에 투자하는 공모펀드 알려줘")
    assert "CHN" in g and "prfd_attr_cds" in g
    assert "fd_ivst_rgn_desc 로 풀 수 없다" in g
    # 국가 어휘가 없는 질의엔 실리지 않는다 (triggered 규칙)
    assert "CHN" not in ctx.planner_context(["public_funds"], "순자산 큰 펀드 5개 알려줘")


def test_forbidden_column_rejected():
    """FND-R09 — 금지 컬럼(pfiv_sale_cntl_tcd)을 쓴 SQL 은 기각해 재생성 사유로 돌려준다.

    같은 질문에 1차는 han_clas_policies(정답 경로), 2차는 pfiv_sale_cntl_tcd 가 나온 실측 —
    HCX 비결정성이라 프롬프트 규칙만으로는 못 막는다."""
    from src.runtime.pipeline import forbidden_column_use as f, ensure_fund_evidence_columns

    why = f("SELECT itm_nm FROM public_funds WHERE pfiv_sale_cntl_tcd != '00' LIMIT 30")
    assert why and "han_clas_policies" in why          # 대안 경로를 사유에 담아야 재생성이 고친다
    assert f("SELECT itm_nm FROM public_funds WHERE fd_wk1_ern_r > 0 LIMIT 5")
    # 정상 SQL 은 통과
    assert f("SELECT itm_nm FROM public_funds WHERE han_clas_policies LIKE '%전문투자자%' LIMIT 30") is None
    # 근거컬럼 가드가 금지 컬럼을 SELECT 에 실어 주지 않는다 (금지를 거드는 꼴)
    s, _ = ensure_fund_evidence_columns(
        "SELECT itm_nm FROM public_funds WHERE pfiv_sale_cntl_tcd != '00' LIMIT 30")
    assert "pfiv_sale_cntl_tcd" not in s.split("FROM")[0]


def test_regenerated_sql_also_gets_guards():
    """FND-R09 실측 — 재생성 SQL 도 가드 체인을 타야 한다.

    금지 컬럼 기각 → 재생성이 han_clas_policies 로 정확히 고쳤는데, 재생성 경로가 ensure_limit 만
    거쳐 근거컬럼 보강을 건너뛰었다. 필터 컬럼이 SELECT 에 없어 답변기가 27행을 버렸다."""
    from src.runtime.loader import load_context
    from src.runtime.pipeline import answer_question

    ctx = load_context()

    class P:
        def __init__(self): self.n = 0
        def plan_sql(self, q, g):
            self.n += 1
            if self.n == 1:   # 1차 — 금지 컬럼
                return ("SELECT DISTINCT itm_nm FROM public_funds WHERE prvo_pbff_desc = '공모' "
                        "AND pfiv_sale_cntl_tcd != '00' LIMIT 30")
            return ("SELECT DISTINCT itm_nm FROM public_funds WHERE prvo_pbff_desc = '공모' "
                    "AND han_clas_policies LIKE '%전문투자자%' AND sale_yn = '판매중' LIMIT 30")
        def compose_answer(self, q, rows, answer_rules=""):
            return "ok"

    r = answer_question("T-R09", "전문투자자만 살 수 있는 공모펀드 알려줘", planner=P(), ctx=ctx)
    assert "재생성" in r.think_trace
    # 재생성 SQL 에도 근거컬럼(필터로 쓴 han_clas_policies)이 SELECT 에 실려야 한다
    assert "han_clas_policies" in r.sql.split("FROM")[0], r.sql
    assert r.retrieved_context.strip()          # 행이 실제로 조회된다
