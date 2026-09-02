# -*- coding: utf-8 -*-
"""paired v2(2026-08-31) 실측 실패에서 나온 가드 2건 — 곱슬따옴표 정규화 · 컬럼 환각 검출."""
import glob
import json
import os

import re

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

    # 🔴 빠진 쪽만 주입한다 (2026-08-31 밤 FND-030) — 한쪽만 쓴 SQL 이 반쪽 모수로 나가던 것을 막는다.
    #    기존 조건은 그대로 두고 없는 것만 채운다.
    s, ok = f("SELECT COUNT(*) FROM public_funds WHERE thco_sale_yn='Y' AND prvo_pbff_desc='공모' LIMIT 30",
              "미래에셋증권에서 살 수 있는 공모펀드는 몇 개야?")
    assert ok and "sale_yn = '판매중'" in s and s.count("prvo_pbff_desc") == 1
    s, ok = f("SELECT itm_nm FROM public_funds WHERE sale_yn='판매완료' ORDER BY 1 LIMIT 5", "펀드")
    assert ok and "판매완료" in s and "prvo_pbff_desc = '공모'" in s and "'판매중'" not in s

    # 🔴 9/1 FND-R06 실측 — ext_* 설명서 조인도 기본모수 대상이다. JOIN 전체 제외가
    #    판매완료 펀드(신바람삼성 1997-10-28)를 '가장 오래된 펀드'로 내보냈다.
    s, ok = f("SELECT itm_nm, estb_dt FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
              "WHERE prvo_pbff_desc = '공모' ORDER BY estb_dt ASC LIMIT 1",
              "설정일이 가장 오래된 공모펀드 알려줘")
    assert ok and "sale_yn = '판매중'" in s and s.count("prvo_pbff_desc") == 1

    # 발동 금지 3갈래 — 모수 확장 질문 · 타 상품군 조인(교차질의) · 집계도 랭킹도 아님
    assert not f("SELECT itm_nm FROM public_funds ORDER BY 1 LIMIT 5", "사모 펀드 중 큰 것")[1]
    assert not f("SELECT 1 FROM public_funds p JOIN domestic_etfs d ON 1=1 ORDER BY 1 LIMIT 5", "펀드")[1]
    assert not f("SELECT itm_nm FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 5", "펀드")[1]


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
    # 불개입 3갈래 — '클래스' 명시 질문의 GROUP BY 없는 조회(2026-09-02 부터 GROUP BY 부재는 주입 분기 —
    # test_fund_rank_group_by_injected) · 펀드단위 키 아닌 GROUP BY · JOIN(교차)
    assert not f("SELECT fd_yr1_ern_r FROM public_funds WHERE itm_nm LIKE '%코어테크%' ORDER BY fd_yr1_ern_r DESC LIMIT 10",
                 "코어테크 클래스별 1년 수익률")[1]
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

    # 🔴 9/1 서버 실측(021·022·031) — 순자산 랭킹은 억 원 파생 컬럼 병기 (13자리 옮겨쓰기 자릿수 훼손)
    nast_rank = ("SELECT itm_no, TRIM(itm_nm), fd_nast_suma FROM public_funds "
                 "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' ORDER BY 3 DESC LIMIT 5")
    s3, ok3 = f(nast_rank)
    assert ok3 and "'억원'" in s3 and s3.index("순자산_억원") < s3.upper().index("FROM")
    assert not f(s3)[1]                                    # 멱등
    # 수익률 랭킹에는 붙지 않는다
    assert "순자산_억원" not in f(grade_rank)[0]

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
    # 9/1 서버 실측 — BETWEEN 1 AND 3 우회(높은위험 30행 조회). 뒤집힘 표현형 확장분
    between = flipped.replace("zrin_fd_ivst_risk_gcd = 1",
                              "zrin_fd_ivst_risk_gcd BETWEEN 1 AND 3")
    s2, ok2 = f(between, "안전한 펀드 추천해줘")
    assert ok2 and "zrin_fd_ivst_risk_gcd = 6" in s2 and "BETWEEN" not in s2
    for form in ("zrin_fd_ivst_risk_gcd <= 2", "zrin_fd_ivst_risk_gcd IN (1, 2, 3)"):
        sx, okx = f(flipped.replace("zrin_fd_ivst_risk_gcd = 1", form), "안전한 펀드 추천해줘")
        assert okx and "zrin_fd_ivst_risk_gcd = 6" in sx
    # 안전 방향 범위(4~6·6 포함)는 불개입
    assert not f(flipped.replace("zrin_fd_ivst_risk_gcd = 1",
                                 "zrin_fd_ivst_risk_gcd BETWEEN 4 AND 6"),
                 "안전한 펀드 추천해줘")[1]


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
    assert f("코어테크 펀드 수익률", []) == "코어테크"          # 4R K-1: Ground 0 이어도 상품 명사 앞 덩어리는 후보(FND-016 문형)


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


def test_distribution_answer_assembled():
    """FND-038 재검 실측 — 답변기가 19행 중 17행만 나열 + '일부' 서술. 분포는 기계 조립한다."""
    from src.runtime.pipeline import _distribution_answer as f

    sql = ("SELECT COALESCE(zrin_btyp_nm,'(미수록)'), COUNT(*) FROM public_funds "
           "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY zrin_btyp_nm LIMIT 30")
    rows = "COALESCE | COUNT(*)\n(미수록) | 418\nMMF | 108\n해외기타 | 801"
    a = f(sql, rows, 3)
    assert a and "3개 범주" in a and "1,327건" in a
    assert "(미수록): 418건" in a and "해외기타: 801건" in a       # 전 행 보존
    # 불개입 — GROUP BY 없음 · SELECT 3항목 · 둘째가 COUNT 아님 · 행 형식 불일치
    assert f("SELECT COUNT(*) FROM public_funds LIMIT 1", "COUNT(*)\n5", 1) is None
    assert f("SELECT a, b, COUNT(*) FROM public_funds GROUP BY 1,2 LIMIT 30", rows, 3) is None
    assert f("SELECT zrin_btyp_nm, AVG(fd_yr1_ern_r) FROM public_funds GROUP BY 1 LIMIT 30", rows, 3) is None


def test_fund_mgmt_modal_name():
    """FND-035 재검 실측 — MAX(mgmt_co_nm) 이 합병 코드 구명칭(프랭클린 10행)을 사전순으로 뽑음.
    소수 이름 제외(DB 실측 기반)로 정본 이름(우리자산운용 373행)이 나와야 한다."""
    import sqlite3
    from src.runtime.pipeline import ensure_fund_mgmt_modal_name as f, _minority_mgmt_names

    assert "00040007/프랭클린템플턴투자신탁운용" in _minority_mgmt_names()
    # 🔴 쌍 제외 근거 — '우리자산운용' 은 00040007 다수(413)·00040023 소수(1): 전역 이름 제외는 오답
    assert "00040023/우리자산운용" in _minority_mgmt_names()
    assert "00040007/우리자산운용" not in _minority_mgmt_names()
    sql = ("SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) AS code, MAX(mgmt_co_nm) AS nm "
           "FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
           "WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' "
           "AND printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) = '00040007' GROUP BY 1 LIMIT 5")
    s, ok = f(sql)
    assert ok and "|| '/' || mgmt_co_nm NOT IN" in s
    assert not f(s)[1]                                     # 멱등
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    code, nm = con.execute(s).fetchone()
    assert (code, nm) == ("00040007", "우리자산운용")
    assert not f("SELECT itm_nm FROM public_funds LIMIT 5")[1]


def test_fund_country_tag_canonicalized():
    """FND-026 재검 실측 — ='글로벌' 오모수 + wrap 없는 태그 LIKE 98/560행 누락을 정식형으로 교체."""
    from src.runtime.pipeline import ensure_fund_country_tag as f

    q = "중국에 투자하는 공모펀드 알려줘"
    bad = ("SELECT DISTINCT itm_no, itm_nm FROM public_funds WHERE prvo_pbff_desc = '공모' "
           "AND (fd_ivst_rgn_desc = '글로벌' OR prfd_attr_cds LIKE '%,CHN,%') "
           "AND sale_yn = '판매중' LIMIT 30")
    s, ok = f(bad, q)
    assert ok and "fd_ivst_rgn_desc" not in s
    assert s.count("',' || prfd_attr_cds || ',' LIKE '%,CHN,%'") == 1     # 2R Q3: 같은 정식형 OR 중복은 하나로 접는다
    assert " OR " not in s
    assert not f(s, q)[1]                                  # 멱등
    # 불개입 — 국가어 없음(지역어 질의) · 펀드 테이블 아님
    assert not f(bad, "글로벌 펀드 알려줘")[1]
    assert not f("SELECT 1 FROM domestic_etfs WHERE wu_inv_rgn='중국' LIMIT 5", q)[1]


def test_strip_disclaimer():
    """면책 금지 규칙 5회 재발 실측 — '금융기관 문의·전문가 상담' 문장을 통째로 걷어낸다."""
    from src.runtime.pipeline import strip_disclaimer as f

    a = ("1. 삼성MMF법인제1호 C 클래스 - 124295억원\n\n"
         "이 펀드들은 모두 선취 수수료가 없으며, 순자산이 큰 순으로 정렬되어 있습니다. "
         "더 자세한 내용은 해당 금융기관에 문의하시기 바랍니다.")
    s, ok = f(a)
    assert ok and "문의" not in s and "124295억원" in s and "정렬되어 있습니다." in s
    # 쉼표 낀 긴 문장도 통째로
    b = "안전성이 중요한 경우 전문가와 상담하여 자신의 투자 목표에 맞는 상품을 선택하는 것이 좋습니다."
    s2, ok2 = f("위험등급은 6등급입니다. " + b)
    assert ok2 and "전문가" not in s2 and "6등급입니다." in s2
    # 불개입 — 면책 없음 · 면책뿐인 답(빈 답변 방지)
    assert f("위험등급은 6등급입니다.") == ("위험등급은 6등급입니다.", False)
    only = "자세한 내용은 금융기관에 문의하세요."
    assert f(only) == (only, False)


def test_fund_distinct_count_replaced():
    """FND-034 실측 — COUNT(*) 가 클래스 850 을 '펀드 850개' 로 (구분 누락 6번째 재발).
    펀드 개수 질의는 COUNT(DISTINCT 펀드키)+클래스수 병기로 교체하고 DB 실행까지 단언한다."""
    import sqlite3
    from src.runtime.pipeline import ensure_fund_distinct_count as f

    q = "삼성자산운용이 운용하는 공모펀드는 몇 개야?"
    bad = ("SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040010') "
           "AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30")
    s, ok = f(bad, q)
    assert ok and '"펀드수"' in s and '"클래스수"' in s
    assert not f(s, q)[1]                                  # 멱등 (COUNT(*) 단독 형태가 아니게 됨)
    con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
    funds, classes = con.execute(s).fetchone()
    assert (funds, classes) == (207, 850)                  # 2026-09-01 DB 실측 gold
    # 🔴 역외 키 (2026-09-02 재검 부수 발견) — mtco_itm_no NULL 110행이 키 NULL 로 뭉치면 2,930 으로 과소.
    #    COALESCE(…, itm_no) 형이라야 gold 키와 같은 3,040.
    base = f("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30", q)[0]
    assert con.execute(base).fetchone() == (3040, 8969)
    # 불개입 — 클래스 수 질문 · 개수 질의 아님 · GROUP BY 분포
    assert not f(bad, "삼성자산운용 펀드는 클래스가 몇 개야?")[1]
    assert not f(bad, "삼성자산운용 펀드 알려줘")[1]
    assert not f("SELECT zrin_btyp_nm, COUNT(*) FROM public_funds GROUP BY 1 LIMIT 30",
                 "공모펀드는 유형별로 몇 개씩 있어?")[1]


def test_fund_series_boundary_injected():
    """FND-032 실측 — HCX 가 호 경계식을 `'2호' IN (a OR b)`(항상 거짓)로 옮겨 0행 오거절.
    'N호' 언급 절을 걷어내고 GLOB 확정식을 주입한다."""
    from src.runtime.pipeline import ensure_fund_series_boundary as f

    q = "미래에셋디스커버리증권투자신탁 2호 위험등급 알려줘"
    bad = ("SELECT zrin_fd_ivst_risk_grd_nm, itm_no, TRIM(itm_nm) AS itm_nm FROM public_funds "
           "WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋디스커버리증권투자신탁%' "
           "AND '2호' IN (REPLACE(itm_nm,' ','') LIKE '%[^0-9]2호%' OR REPLACE(itm_nm,' ','') LIKE '%2호[^0-9]%') "
           "LIMIT 30")
    s, ok = f(bad, q)
    assert ok and "GLOB '*[^0-9.]2호*'" in s and "GLOB '*[^0-9.]2[([]*'" in s and "IN (" not in s   # 2R Q6: 'N(' 표기 병행
    assert "LIKE '%미래에셋디스커버리증권투자신탁%'" in s          # 이름 절은 보존
    assert not f(s, q)[1]                                          # 멱등
    # 불개입 — 호수 없음 · 이름 검색 없음 · 펀드 테이블 아님
    assert not f(bad, "미래에셋디스커버리증권투자신탁 위험등급 알려줘")[1]
    assert not f("SELECT COUNT(*) FROM public_funds WHERE sale_yn='판매중' LIMIT 1", q)[1]
    assert not f("SELECT 1 FROM domestic_bonds WHERE pd_nm LIKE '%2호%' LIMIT 5", q)[1]


def test_fund_mixed_type_canonical_filter():
    """FND-023 실측 2회 — '혼합형' 질의의 유형 필터를 zrin 확정식(주식혼합형+채권혼합형)으로 교체."""
    from src.runtime.pipeline import ensure_fund_mixed_type as f

    q = "혼합형 공모펀드 중 1년 수익률 상위 5개 알려줘"
    bad = ("SELECT itm_no, TRIM(itm_nm), MAX(fd_yr1_ern_r) AS r FROM public_funds "
           "WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
           "AND or_attr_desc IN ('혼합자산', '대출형', '개발형') "
           "GROUP BY or_co_xtn_itt_cd, mtco_itm_no ORDER BY 3 DESC LIMIT 5")
    s, ok = f(bad, q)
    assert ok and "zrin_btyp_nm IN ('주식혼합형','채권혼합형')" in s and "혼합자산" not in s
    assert not f(s, q)[1]                                  # 멱등
    # 불개입 — 구체 유형 명시 · 유형 조건 없음 · 유형 조건 2개(치환이 얽힌다) · '혼합형' 없음
    assert not f(bad, "혼합자산 펀드 수익률 상위 5개")[1]
    assert not f("SELECT itm_nm FROM public_funds WHERE sale_yn='판매중' LIMIT 5", q)[1]
    two = bad.replace("AND or_attr_desc IN ('혼합자산', '대출형', '개발형')",
                      "AND or_attr_desc = '혼합자산' AND zrin_btyp_nm = '주식혼합형'")
    assert not f(two, q)[1]
    assert not f(bad, "채권형 펀드 알려줘")[1]


def test_value_violation_hints_similar_values_first():
    """FND-023 실측 — '혼합형' 기각 예시가 임의 표본이라 재생성이 힌트 0 으로 REFUSE.
    어간('혼합') 포함 실제 값(주식혼합·채권혼합)이 예시 맨 앞에 와야 재생성이 고친다."""
    from src.runtime.loader import load_context
    from src.runtime import guard

    ctx = load_context()
    sql = ("SELECT itm_nm FROM public_funds WHERE or_attr_desc = '혼합형' "
           "AND sale_yn = '판매중' LIMIT 30")
    vs = guard.check_values(sql, ctx)
    assert len(vs) == 1
    msg = str(vs[0])
    assert "주식혼합" in msg and "채권혼합" in msg
    # 유사 값이 없으면 종전처럼 정렬 표본을 보여준다
    vs2 = guard.check_values(
        "SELECT itm_nm FROM public_funds WHERE or_attr_desc = '없는유형ZZZ' LIMIT 5", ctx)
    assert len(vs2) == 1 and "실제 값 예" in str(vs2[0])


def test_empty_string_literal_is_missing_idiom_not_value(ctx=None):
    """`col = ''` 은 결측 관용구다 — 값 사전 검사로 기각하면 답변 가능한 결측 건수 질의가
    오거절로 나간다 (2026-09-01 FND-037 실측: 벤치마크 결측 418행 질의가 가드에 막힘)."""
    from src.runtime.loader import load_context
    from src.runtime import guard

    ctx = load_context()
    sql = ("SELECT COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' "
           "AND (bmrk_nm IS NULL OR bmrk_nm = '' OR bmrk_eng_nm = '') AND sale_yn = '판매중' LIMIT 30")
    assert guard.check_values(sql, ctx) == []
    # 빈 문자열 면제가 실제 없는 값 검사를 무디게 하면 안 된다
    bad = "SELECT COUNT(*) FROM public_funds WHERE zrin_btyp_nm = '' OR zrin_btyp_nm = '없는유형ZZZ' LIMIT 5"
    assert len(guard.check_values(bad, ctx)) == 1


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


def test_fund_prospectus_opens_ext_table():
    """설정일·환매 질의는 ext_fund_page 를 열어야 한다 — 마스터에 없다고 거절하던 오거절 차단.

    2026-08-31 밤 리드 지적 후속: 설정일은 ext_fund_page.estb_dt 에 93.7% 수록돼 있는데,
    조인 키가 cross 질의에만 실려 단일 도메인 질의는 테이블 존재조차 몰랐다."""
    from src.runtime.loader import load_context
    from src.runtime.pipeline import answer_question

    ctx = load_context()

    class P:
        def plan_sql(self, q, g):
            assert "ext_fund_page" in g, "설명서 조인 키가 근거문서에 없다"
            assert "estb_dt" in g, "설정일 컬럼 안내가 없다"
            return ("SELECT p.itm_no, TRIM(p.itm_nm), e.estb_dt FROM public_funds p "
                    "JOIN ext_fund_page e ON e.itm_no = p.itm_no WHERE p.sale_yn='판매중' "
                    "AND p.prvo_pbff_desc='공모' AND e.estb_dt IS NOT NULL ORDER BY e.estb_dt ASC LIMIT 5")
        def compose_answer(self, q, rows, answer_rules=""):
            return "ok"

    r = answer_question("T-EXT", "설정일이 가장 오래된 공모펀드 알려줘", planner=P(), ctx=ctx)
    assert "1999" in r.retrieved_context, r.retrieved_context[:200]


def test_hedge_fund_rule_is_answerable_now():
    """구 '헤지펀드없음' 규칙(오거절)이 정정됐는지 — 공모 헤지펀드는 사모투자재간접 형태로 실재한다."""
    from src.runtime.loader import load_context

    ctx = load_context()
    g = ctx.planner_context(["public_funds"], "공모 헤지펀드 중 수익률 좋은 것 알려줘")
    assert "사모투자재간접" in g and "글로벌헤지전략" in g
    assert "수록되어 있지 않습니다" not in g          # 조회 없이 거절하라는 옛 지시가 사라졌다


def test_ambiguous_join_column_rejected():
    """설정일 질의 실측 — JOIN 에서 한정 안 된 itm_no 는 실행 시 ambiguous 오류라 미리 기각한다."""
    from src.runtime.loader import load_context
    from src.runtime import guard

    ctx = load_context()
    bad = ("SELECT itm_no, TRIM(itm_nm), fd_daily_bas_dt FROM public_funds "
           "JOIN ext_fund_page ON public_funds.itm_no = ext_fund_page.itm_no "
           "WHERE prvo_pbff_desc = '공모' ORDER BY estb_dt ASC LIMIT 1")
    assert "itm_no" in guard.ambiguous_columns(bad, ctx)
    good = ("SELECT p.itm_no, TRIM(p.itm_nm), e.estb_dt FROM public_funds p "
            "JOIN ext_fund_page e ON e.itm_no = p.itm_no WHERE p.sale_yn='판매중' "
            "ORDER BY e.estb_dt ASC LIMIT 5")
    assert not guard.ambiguous_columns(good, ctx)
    # 단일 테이블은 검사 대상이 아니다
    assert not guard.ambiguous_columns("SELECT itm_no FROM public_funds LIMIT 5", ctx)


def test_spaceless_name_match():
    """FND-R05 후속 — 종목명 LIKE 는 공백 무시 매칭으로 바꾼다.

    실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다. 매칭을 넓히기만 하므로
    존재하지 않는 상품(R05)은 여전히 0행이다."""
    from src.runtime.pipeline import ensure_spaceless_name_match as f

    s, ok = f("SELECT itm_no FROM public_funds WHERE itm_nm LIKE '%미래에셋 코어테크%' LIMIT 30")
    assert ok and "REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%'" in s
    assert not f(s)[1]                                  # 멱등
    # TRIM 감싼 형태·NOT LIKE 도 처리
    s2, ok2 = f("SELECT 1 FROM public_funds WHERE TRIM(itm_nm) NOT LIKE '%상장 지수%' LIMIT 5")
    assert ok2 and "REPLACE(itm_nm,' ','') NOT LIKE '%상장지수%'" in s2
    # 다른 컬럼은 건드리지 않는다
    assert not f("SELECT 1 FROM public_funds WHERE han_clas_policies LIKE '%전문투자자%' LIMIT 5")[1]


def test_prospectus_hint_not_triggered_by_공모펀드():
    """FND-028 실측 — '모펀드' 가 '공모펀드'·'사모펀드' 에 걸려 거의 모든 질의가 설명서 조인 대상이 됐다."""
    from src.runtime.pipeline import _FUND_EXT_HINTS as H

    assert not H.search("개인이 가입할 수 있는 공모펀드는 몇 개야?")
    assert not H.search("사모펀드 알려줘")
    assert H.search("이 펀드의 모펀드가 뭐야?")
    assert H.search("설정일이 가장 오래된 공모펀드 알려줘")
    assert H.search("환매 수수료가 없는 펀드 알려줘")


def test_fund_padded_columns_trimmed():
    """FND-030 실측 — 펀드 코드 컬럼도 패딩이 있어 무TRIM 등호가 0행이 된다.

    KG 가 준 '0016022' 로 = 비교하면 0행, DB 원값은 '0016022 '(8자, 202행)."""
    from src.runtime.pipeline import ensure_trimmed_compare as f

    s, ok = f("SELECT COUNT(*) FROM public_funds WHERE trusc_xtn_itt_cd = '0016022' LIMIT 30")
    assert ok and "TRIM(trusc_xtn_itt_cd) = '0016022'" in s
    assert not f(s)[1]                                    # 멱등
    # LIKE 는 % 가 패딩을 흡수하므로 불개입
    assert not f("SELECT 1 FROM public_funds WHERE itm_nm LIKE '%코어테크%' LIMIT 5")[1]


def test_sales_company_rule_grounded():
    """FND-030 — '미래에셋증권에서 살 수 있는' 은 판매사 질의(thco_sale_yn)여야 한다."""
    from src.runtime.loader import load_context

    ctx = load_context()
    g = ctx.planner_context(["public_funds"], "미래에셋증권에서 살 수 있는 공모펀드는 몇 개야?")
    assert "thco_sale_yn" in g and "수탁사" in g


def test_enum_value_suffix_fix():
    """FND-024 실측 — '재간접형' 처럼 접미사만 다른 표기를 실제 값으로 흡수한다.

    값 검사 기각 → 재생성이 사유의 '실제 값 예' 4개를 그대로 IN 에 넣는 오작동 → 거절로 나갔다.
    답변 가능한 질의(2,594행)가 거절되던 경로를 없앤다."""
    from src.runtime.loader import load_context
    from src.runtime.pipeline import ensure_enum_value_fix as f

    ctx = load_context()
    s, ok = f("SELECT COUNT(*) FROM public_funds WHERE or_attr_desc = '재간접형' LIMIT 30", ctx)
    assert ok and "'재간접'" in s and "재간접형" not in s
    assert not f(s, ctx)[1]                                # 멱등
    # 불개입 — 이미 실제 값 · 컬럼 오선택(재생성 사유로 넘긴다)
    assert not f("SELECT 1 FROM public_funds WHERE or_attr_desc='재간접' LIMIT 5", ctx)[1]
    assert not f("SELECT 1 FROM public_funds WHERE or_attr_desc='해외주식형' LIMIT 5", ctx)[1]


def test_public_only_narrowing_and_type_rule():
    """FND-038 실측 — '공모펀드는 유형별로' 질의에 사모가 섞이면 좁히고, '유형'=자산유형 규칙이 실린다."""
    from src.runtime.pipeline import ensure_fund_base_population as f
    from src.runtime.loader import load_context

    s, ok = f("SELECT prvo_pbff_desc, COUNT(*) FROM public_funds WHERE sale_yn='판매중' "
              "AND prvo_pbff_desc IN ('공모','사모') GROUP BY 1 LIMIT 2",
              "공모펀드는 유형별로 몇 개씩 있어?")
    assert ok and "prvo_pbff_desc = '공모'" in s and "'사모'" not in s
    # 사모를 물으면 건드리지 않는다 (_POP_WIDEN)
    assert not f("SELECT COUNT(*) FROM public_funds WHERE prvo_pbff_desc IN ('공모','사모') LIMIT 5",
                 "사모까지 포함해서 몇 개야?")[1]

    g = load_context().planner_context(["public_funds"], "공모펀드는 유형별로 몇 개씩 있어?")
    assert "zrin_btyp_nm" in g and "제로인 미수록" in g and "모집 방식" in g


def test_group_null_label():
    """FND-038 실측 — 분포 집계의 NULL 그룹에 라벨을 줘야 답변이 그 행을 빠뜨리지 않는다."""
    from src.runtime.pipeline import ensure_group_null_label as f

    s, ok = f("SELECT zrin_btyp_nm, COUNT(*) FROM public_funds WHERE sale_yn='판매중' "
              "GROUP BY zrin_btyp_nm LIMIT 30")
    assert ok and "COALESCE(zrin_btyp_nm,'(미수록)')" in s
    assert not f(s)[1]                                     # 멱등
    # 불개입 — GROUP BY 없음 · 축이 서술 컬럼이 아님 · 이미 COALESCE
    assert not f("SELECT COUNT(*) FROM public_funds LIMIT 1")[1]
    assert not f("SELECT itm_no, COUNT(*) FROM public_funds GROUP BY itm_no LIMIT 5")[1]


# ── 2026-09-02 재검 1라운드 (docs/recheck_2026-09-02_round1.md) — 결정층 수리 P1~P7 ──
_R7_SQL = ("SELECT itm_no, TRIM(itm_nm), fd_yr1_ern_r, zrin_attr_nms FROM public_funds WHERE sale_yn = '판매중' "
           "AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r > -100 "
           "AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') ORDER BY 3 DESC LIMIT 3")


def _ro():
    import sqlite3
    return sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)


def test_fund_rank_group_by_injected():
    """R7 실측 — 미특정 경로에서 HCX 가 GROUP BY 를 버리자 클래스 단위 top3 가 한화2.2배 3클래스 도배.
    GROUP BY 부재면 펀드키를 주입하고 MAX/MIN 으로 감싸 gold(펀드단위)와 같은 3펀드가 나와야 한다."""
    from src.runtime.pipeline import ensure_fund_rank_representative as f

    q = "공모펌드 중 1년 수익률이 가장 높은 3개 알려줘"
    s, ok = f(_R7_SQL, q)
    assert ok and "GROUP BY printf" in s and "MAX(fd_yr1_ern_r) AS fd_yr1_ern_r" in s and '"클래스수"' in s
    assert s.upper().index("GROUP BY") < s.upper().index("ORDER BY")
    assert not f(s, q)[1]                                  # 멱등 — 이미 GROUP BY 가 있고 MAX 로 감쌌으면 불개입
    con = _ro()
    rows = con.execute(s).fetchall()
    assert [r[2] for r in rows] == [387.66, 362.53, 361.3]    # gold: 한화2.2배 · NH-Amundi코리아2배 · 삼성KOSPI200 2배
    assert len({r[1][:6] for r in rows}) == 3                 # 서로 다른 펀드
    assert "한화2.2배" in rows[0][1] and "NH-Amundi" in rows[1][1] and "삼성KOSPI200" in rows[2][1]
    # MIN 경로 (018 잠재 리스크 — 하위 랭킹은 펀드당 MIN 클래스)
    s2, ok2 = f(_R7_SQL.replace("ORDER BY 3 DESC", "ORDER BY 3 ASC"), "1년 수익률이 가장 낮은 공모펀드 3개")
    assert ok2 and "MIN(fd_yr1_ern_r) AS fd_yr1_ern_r" in s2
    assert [r[2] for r in con.execute(s2)] == [-83.96, -79.07, -73.98]
    # 정렬 컬럼이 SELECT 에 없으면 별칭으로 실어 ORDER BY 이름을 살린다 + 식별 컬럼 보강
    s3, ok3 = f("SELECT zrin_attr_nms FROM public_funds WHERE sale_yn = '판매중' ORDER BY fd_nast_suma DESC LIMIT 3", "순자산 큰 펀드")
    assert ok3 and "MAX(fd_nast_suma) AS fd_nast_suma" in s3 and "TRIM(itm_nm) AS itm_nm" in s3
    assert len(con.execute(s3).fetchall()) == 3
    # 비발동 — 질문에 '클래스' · SELECT 가 COUNT 집계 · 기존 GROUP BY(종전 wrap 경로 그대로)
    assert not f(_R7_SQL, "1년 수익률 높은 클래스 3개")[1]
    assert not f("SELECT COUNT(*) FROM public_funds ORDER BY fd_yr1_ern_r DESC LIMIT 1", q)[1]
    s4, ok4 = f(_FND15_SQL, q)
    assert ok4 and "GROUP BY or_co_xtn_itt_cd" in s4 and s4.count("GROUP BY") == 1



_R4_SQL = ("SELECT fd_yr1_ern_r, itm_nm FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' "
           "AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' "
           "AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r <> 0 LIMIT 30")
_R6_SQL = ("SELECT zrin_fd_ivst_risk_grd_nm FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬증권투자신탁%' "
           "AND REPLACE(itm_nm,' ','') GLOB '*[^0-9]2호*' LIMIT 1")


def test_fund_lookup_grouping():
    """R4 재검 — 이름 검색 30행(6펀드 37클래스)을 답변기가 1클래스로 답함 3회째. SELECT 단계에서 펀드키로 묶어
    클래스수·최고/최저를 병기하면 답변기는 6행을 복사만 한다. R6 — LIMIT 1 이라 클래스수 병기가 불가능하던 것."""
    from src.runtime.pipeline import ensure_fund_lookup_grouping as f, ensure_fund_evidence_columns as ev

    con = _ro()
    s, ok = f(_R4_SQL, "미래에셋코어테크 펀드 1년 수익률 알려줘")
    assert ok and "GROUP BY printf" in s and '"클래스수"' in s and '"fd_yr1_ern_r_최고"' in s and "LIMIT 30" in s
    assert not f(s, "미래에셋코어테크 펀드 1년 수익률 알려줘")[1]     # 멱등 — GROUP BY 가 생겼으면 불개입
    rows = con.execute(s).fetchall()
    assert len(rows) == 6                                          # 6펀드 (2026-09-02 DB 실측)
    assert rows[0][1].startswith("미래에셋코어테크증권자투자신탁") and rows[0][2] == 9   # 본체가 첫 행(최단 이름) · <>0 필터 후 9클래스
    assert rows[0][3] == 9                                         # 판매중클래스수 (리뷰 ②-7 — 기본모수 미주입의 보완)
    assert (rows[0][4], rows[0][5]) == (189.77, 187.09)            # 최고·최저 — 1클래스(188.83)만 답하던 것의 재료
    # R6 — 등급명만 SELECT → 묶기 + 근거컬럼 가드의 역방향 gcd 병기. 🔴 이 펀드는 클래스마다 mtco_itm_no 가
    #    달라(531101~531107) 정본 펀드키로는 6행이다 — 값은 전 행 '높은 위험'·2 로 같고 클래스수 합이 7.
    s6, ok6 = f(_R6_SQL, "미래에셋차이나솔로몬증권투자신탁 2호 위험등급 알려줘")
    assert ok6 and "MAX(zrin_fd_ivst_risk_grd_nm) AS zrin_fd_ivst_risk_grd_nm" in s6 and "LIMIT 1" not in s6
    s6, ok6b = ev(s6)
    assert ok6b and "zrin_fd_ivst_risk_gcd" in s6
    cols6 = [d[0] for d in con.execute(s6).description]
    rows6 = [dict(zip(cols6, r)) for r in con.execute(s6).fetchall()]
    assert rows6 and all(r["zrin_fd_ivst_risk_grd_nm"] == "높은 위험" and r["zrin_fd_ivst_risk_gcd"] == 2 for r in rows6)
    assert sum(r["클래스수"] for r in rows6) == 7 and sum(r["판매중클래스수"] for r in rows6) == 7   # 7클래스 전부 판매중 (리뷰 ②-7)
    assert all(r["대표번호"] == "031910531100" for r in rows6)         # 2R Q4-b 표시 단위 — 조립기가 1줄로 접는 근거
    # 비발동 — '클래스' 열거(033) · 보수(020) · ORDER BY 랭킹(P1 담당) · COUNT 집계 · 이름 필터 없음
    q33 = "미래에셋코어테크 펀드는 어떤 클래스들이 있어?"
    s33 = ("SELECT itm_no, TRIM(itm_nm) FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크증권자투자신탁%' "
           "AND sale_yn='판매중' LIMIT 30")
    assert not f(s33, q33)[1] and len(con.execute(s33).fetchall()) == 10
    assert not f(_R4_SQL, "미래에셋코어테크 펀드 클래스별 총보수 알려줘")[1]
    assert not f(_R4_SQL.replace("LIMIT 30", "ORDER BY fd_yr1_ern_r DESC LIMIT 30"), "q")[1]
    assert not f("SELECT COUNT(*) FROM public_funds WHERE itm_nm LIKE '%코어테크%' LIMIT 30", "q")[1]
    assert not f("SELECT fd_yr1_ern_r, itm_nm FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' LIMIT 30", "q")[1]
    # 식이 섞인 SELECT 는 안전하게 불개입
    assert not f("SELECT fd_yr1_ern_r * 2, itm_nm FROM public_funds WHERE itm_nm LIKE '%코어테크%' LIMIT 30", "q")[1]


def test_fund_evidence_grade_code_symmetric():
    """R6 재검 — 등급명만 조회하면 '2등급' 숫자를 못 붙인다. 이름→코드 역방향 병기 (코드→이름은 종전대로)."""
    from src.runtime.pipeline import ensure_fund_evidence_columns as f

    s, ok = f("SELECT zrin_fd_ivst_risk_grd_nm, itm_no, itm_nm FROM public_funds WHERE itm_nm LIKE '%솔로몬%' LIMIT 30")
    assert ok and s.startswith("SELECT zrin_fd_ivst_risk_grd_nm, itm_no, itm_nm, zrin_fd_ivst_risk_gcd FROM")
    assert not f(s)[1]                                             # 멱등
    s2, ok2 = f("SELECT itm_no, itm_nm FROM public_funds WHERE zrin_fd_ivst_risk_gcd = 2 LIMIT 30")
    assert ok2 and "zrin_fd_ivst_risk_grd_nm" in s2 and s2.count("zrin_fd_ivst_risk_gcd") == 2   # WHERE 1 + SELECT 쌍 병기 1 (2R Q4-d)
    assert not f(s2)[1]                                            # 멱등 — 쌍은 한 패스에 붙는다


_R3_SQL = ("SELECT DISTINCT itm_no, itm_nm, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' "
           "AND (',' || prfd_attr_cds || ',' LIKE '%,CHN,%' OR ',' || prfd_attr_cds || ',' LIKE '%,CHN,%') "
           "AND sale_yn = '판매중' LIMIT 30")
_R3_ROWS = ("itm_no | itm_nm | prfd_attr_cds\n"
            "KR510502099M | 삼성중국본토중소형FOCUS증권자투자신탁UH(주식)Ce | C103,CHN\n"
            "KR5127450020 | KB중국본토A주증권자투자신탁[주식]A | CHN")


def test_fund_list_grouping():
    """R3 재검 — ORDER BY 없는 LIMIT 30 이 임의 30행(재현성 없음) + 같은 펀드 C2·C5 별개 나열.
    펀드키 GROUP BY + 순자산순 대표행으로 30개 서로 다른 펀드, 1행 KB중국본토A주(14클래스)."""
    from src.runtime.pipeline import ensure_fund_list_grouping as f, ensure_fund_evidence_columns as ev

    q = "중국에 투자하는 공모펀드 알려줘"
    s, ok = f(_R3_SQL, q)
    assert ok and "GROUP BY printf" in s and "ORDER BY fd_nast_suma DESC" in s and '"클래스수"' in s
    assert not f(s, q)[1]                                          # 멱등
    s, _ = ev(s)
    assert "순자산_억원" in s                                       # 순자산 정렬 → 억원 병기가 따라온다
    rows = _ro().execute(s).fetchall()
    assert len(rows) == 30 and len({r[0] for r in rows}) == 30
    assert rows[0][1].startswith("KB중국본토A주") and rows[0][3] == 14 and rows[0][-1] == "1453억원"
    # 비발동 — '클래스' 질문 · 이미 ORDER BY · 이름 필터(개별 조회 가드 담당) · SELECT 에 식별 컬럼 없음
    assert not f(_R3_SQL, "중국 펀드 클래스 알려줘")[1]
    assert not f(_R3_SQL.replace("LIMIT 30", "ORDER BY itm_nm LIMIT 30"), q)[1]
    assert not f("SELECT itm_no, itm_nm FROM public_funds WHERE itm_nm LIKE '%중국%' LIMIT 30", q)[1]
    assert not f("SELECT fd_yr1_ern_r FROM public_funds WHERE sale_yn='판매중' LIMIT 30", q)[1]


def test_coverage_counts():
    """R3 재검 — LIMIT 도달 목록의 전체 규모(560행/248펀드)를 SQLite 재실행 1회로 센다."""
    from src.runtime.pipeline import _coverage_counts as f, ensure_fund_list_grouping as fl

    assert f(_R3_SQL) == (560, 248, False)
    assert f(fl(_R3_SQL, "q")[0]) == (560, 248, True)               # 펀드키 GROUP BY 는 허용 — 표시 단위가 펀드
    total, funds, grouped = f("SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '국고채권' LIMIT 30")
    assert total > 30 and funds is None and not grouped              # 타 도메인은 행수만
    assert f("SELECT zrin_btyp_nm, COUNT(*) FROM public_funds GROUP BY 1 LIMIT 30") is None   # 분포 집계는 대상 아님


def test_verify_product_names():
    """R3 재검 — 답변의 '삼성중국본토중소형FOSS' 는 DB 0행(실제 FOCUS). 조회 원문 사전으로 근사 토큰만 교정."""
    from src.runtime.pipeline import verify_product_names as f

    a = "* 삼성중국본토중소형FOSS증권자투자신탁UH(주식)Ce(C101, M109, CHN)\n* KB중국본토A주증권자투자신탁[주식]A"
    out, fixes = f(a, _R3_ROWS)
    assert "FOCUS" in out and "FOSS" not in out and len(fixes) == 1 and "KB중국본토A주증권자투자신탁[주식]A" in out
    assert f(out, _R3_ROWS) == (out, [])                              # 정확 일치는 무변경
    prose = "레버리지 펀드는 변동성이 큽니다. 알려드리겠습니다. 1. 한화2.2배레버리지인덱스 펀드"
    assert f(prose, _R3_ROWS) == (prose, [])                          # 무관 문장·8자 서술 토큰 불개입
    assert f(a, "COUNT(*)\n5") == (a, [])                             # 이름 컬럼 없는 결과


def test_hide_answer_columns():
    from src.runtime.pipeline import _hide_answer_columns as f

    out, hidden = f(_R3_ROWS)
    assert hidden == ["prfd_attr_cds"] and "prfd_attr_cds" not in out and "C103,CHN" not in out
    assert out.splitlines()[1] == "KR510502099M | 삼성중국본토중소형FOCUS증권자투자신탁UH(주식)Ce"
    assert f("prfd_attr_cds\nCHN") == ("prfd_attr_cds\nCHN", [])       # 유일 컬럼이면 남긴다
    assert f("itm_no | itm_nm\nA | B") == ("itm_no | itm_nm\nA | B", [])


def test_r3_pipeline_markers(ctx):
    """HCX 경로 통합 — 내부 코드 숨김 · 커버리지 병기 · 이름 교정이 한 번에 발동한다.
    (2R Q5 이후 R3 원형은 목록 조립기에서 끝나므로, ORDER BY 가 있어 목록 묶기가 안 도는 형제 SQL 로 HCX 경로를 검증한다.)"""
    from src.runtime.pipeline import answer_question

    hcx_path = _R3_SQL.replace("LIMIT 30", "ORDER BY itm_nm LIMIT 30")

    class P:
        def plan_sql(self, q, g):
            return hcx_path

        def compose_answer(self, q, rows, answer_rules=""):
            self.rows = rows
            self.first = rows.splitlines()[2].split(" | ")[1].strip()
            return f"* {self.first.replace('투자신탁', '투자신닥')} 등이 있습니다."

    p = P()
    r = answer_question("T-R3", "중국에 투자하는 공모펀드 알려줘", planner=p, ctx=ctx)
    assert "[Guard] 목록 펀드 묶기" not in r.think_trace and "[Answer] 내부 코드 컬럼 숨김 — prfd_attr_cds" in r.think_trace
    assert "[Answer] 커버리지 병기 — LIMIT 도달, 전체 560행 / 248펀드" in r.think_trace
    assert p.rows.startswith("(조회 결과: 전체 560행 / 248펀드 중 30행 표시") and "prfd_attr_cds" not in p.rows
    assert "prfd_attr_cds" in r.retrieved_context                    # 조회 원문은 그대로
    assert "[Guard] 상품명 전사 교정" in r.think_trace and "신닥" not in r.answer and p.first in r.answer
    # LIMIT 미도달이면 종전 머리줄 그대로
    P.plan_sql = lambda self, q, g: hcx_path.replace("LIMIT 30", "LIMIT 5")
    r2 = answer_question("T-R3b", "중국에 투자하는 공모펀드 알려줘", planner=P(), ctx=ctx)
    assert "커버리지 병기" not in r2.think_trace


def test_count_answer_assembled(ctx):
    """R5 재검 — 가드가 `143 | 541` 을 만들었는데 답변기가 클래스 열을 버림. 펀드수/클래스수 1행은 기계 조립한다."""
    from src.runtime.pipeline import _count_answer as f, answer_question

    sql = ("SELECT COUNT(DISTINCT x) AS \"펀드수\", COUNT(*) AS \"클래스수\" FROM public_funds WHERE sale_yn = '판매중' "
           "AND (TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') AND prvo_pbff_desc = '공모') LIMIT 30")
    g = ["'한국투자신탁운용' → Org_00040024 (Organization) → public_funds.or_co_xtn_itt_cd='00040024' · public_funds.or_co_xtn_itt_cd='00040105'"]
    a = f(sql, "펀드수 | 클래스수\n143 | 541", 1, g)
    assert a and "143개(클래스 541개)" in a and "판매중·공모 기준" in a and "2026-08-22" in a
    assert "운용사 코드 2건(00040024·00040105)을 합산" in a
    # 코드 1건이면 합산 문장 없음 · 2열이 아닌 COUNT(채권 종목수)·행수 2 는 None
    assert "합산" not in f(sql, "펀드수 | 클래스수\n207 | 850", 1, ["'삼성자산운용' → Org_00040010 (Organization) → public_funds.or_co_xtn_itt_cd='00040010'"])
    assert f("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds LIMIT 1", "COUNT(DISTINCT pd_no)\n1406", 1, []) is None
    assert f(sql, "펀드수 | 클래스수\n1 | 2\n3 | 4", 2, g) is None
    # 통합 — R5 질문·SQL 로 HCX 답변기를 부르지 않는다 (KG 가 00040105 를 병합한 143/541)
    class P:
        calls = 0

        def plan_sql(self, q, g):
            return ("SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') "
                    "AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30")

        def compose_answer(self, q, rows, answer_rules=""):
            P.calls += 1
            return "x"

    r = answer_question("T-R5", "한국투자신탁운용이 운용하는 공모펀드는 몇 개야?", planner=P(), ctx=ctx)
    assert P.calls == 0 and "[Answer] 개수 답변 기계 조립" in r.think_trace
    assert "143개(클래스 541개)" in r.answer and "00040105" in r.answer


def test_distribution_fund_count_three_columns(ctx):
    """R1 재검 — 분포 답변의 '건' 이 클래스 행 수인데 펀드 수 미병기(구분 누락 7번째). 가드가 COUNT(DISTINCT 펀드키)
    3열을 붙이고 조립기가 `펀드 953개 (클래스 2,784개)` 로 옮긴다. 전체 펀드는 별도 DISTINCT(3,040 ≠ 범주 합 3,222)."""
    from src.runtime.pipeline import ensure_fund_distribution_fund_count as f, _distribution_answer as d, answer_question

    sql = ("SELECT COALESCE(zrin_btyp_nm,'(미수록)'), COUNT(*) FROM public_funds WHERE sale_yn = '판매중' "
           "AND (prvo_pbff_desc = '공모') GROUP BY zrin_btyp_nm LIMIT 30")
    s, ok = f(sql)
    assert ok and 'COUNT(DISTINCT printf' in s and '"펀드수"' in s and s.index('"펀드수"') < s.upper().index("FROM")
    assert not f(s)[1]                                             # 멱등
    # 비발동 — JOIN · SELECT 3항목 · GROUP BY 없음 · 둘째가 COUNT(*) 아님
    assert not f("SELECT p.zrin_btyp_nm, COUNT(*) FROM public_funds p JOIN ext_fund_page e ON e.itm_no = p.itm_no GROUP BY 1 LIMIT 30")[1]
    assert not f("SELECT a, b, COUNT(*) FROM public_funds GROUP BY 1, 2 LIMIT 30")[1]
    assert not f("SELECT COUNT(*) FROM public_funds LIMIT 1")[1]
    assert not f("SELECT zrin_btyp_nm, AVG(fd_yr1_ern_r) FROM public_funds GROUP BY 1 LIMIT 30")[1]
    # 조립기 3열 — 가짜 행
    rows = 'COALESCE | COUNT(*) | 펀드수\n(미수록) | 418 | 308\nMMF | 108 | 64'
    a = d(s, rows, 2)
    assert a and "- (미수록): 펀드 308개 (클래스 418개)" in a and "- MMF: 펀드 64개 (클래스 108개)" in a
    assert "2개 범주 · 클래스 526개 · 펀드 3,040개" in a               # 전체는 같은 WHERE 의 DISTINCT
    # 2열 입력은 종전 출력 그대로 (회귀 보호)
    a2 = d(sql, "COALESCE | COUNT(*)\n(미수록) | 418\nMMF | 108", 2)
    assert a2 and "2개 범주, 합계 526건" in a2 and "- MMF: 108건" in a2 and "펀드" not in a2
    # 통합 — R1 원 SQL → 19범주 · 클래스 8,969 · 펀드 3,040 · 복수 범주 182 (HCX 답변기 0회)
    class P:
        calls = 0

        def plan_sql(self, q, g):
            return "SELECT zrin_btyp_nm, COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' GROUP BY zrin_btyp_nm"

        def compose_answer(self, q, rows, answer_rules=""):
            P.calls += 1
            return "x"

    r = answer_question("T-R1", "공모펀드는 유형별로 몇 개씩 있어?", planner=P(), ctx=ctx)
    assert P.calls == 0 and "[Guard] 분포 펀드수 병기" in r.think_trace and "[Answer] 분포 답변 기계 조립" in r.think_trace
    assert "19개 범주 · 클래스 8,969개 · 펀드 3,040개" in r.answer
    assert "- 해외주식형: 펀드 953개 (클래스 2,784개)" in r.answer and "- (미수록): 펀드 308개 (클래스 418개)" in r.answer
    assert "182건은 복수 범주에 계수" in r.answer and "합(3,222)" in r.answer
    assert sum(1 for ln in r.answer.splitlines() if ln.startswith("- ")) == 19


_R2_ANSWER = ("펀드를 가장 많이 운용하는 운용사 상위 5곳은 다음과 같습니다.\n\n"
              "1. 미래에셋자산운용: 823개의 펀드 운용\n2. 우리자산운용: 235개의 펀드 운용\n3. 삼성자산운용: 207개의 펀드 운용\n"
              "4. iM에셋자산운용: 205개의 펀드 운용\n5. 한국투자신탁운용: 142개의 펀드 운용\n\n"
              "이 순위는 조회된 데이터를 기반으로 한 것이며, 더 많은 펀드를 운용하는 곳이 있을 수 있습니다. "
              "추가 정보가 필요하시다면 관련 기관에 문의하시기 바랍니다.")
_R2_SQL = ("SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) AS 운용사코드, MAX(mgmt_co_nm) AS 운용사이름, "
           "COUNT(DISTINCT mtco_itm_no) AS 펀드수 FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
           "WHERE public_funds.sale_yn = '판매중' GROUP BY 1 ORDER BY 3 DESC LIMIT 5")


def test_strip_disclaimer_r2_tail_and_false_hedge():
    """R2 재검 — '관련 기관에 문의' 는 종전 패턴 밖(로컬 재현 False) + 전수 집계 5행에 '더 있을 수 있음' 거짓 유보."""
    from src.runtime.pipeline import strip_disclaimer as d, strip_false_hedge as h

    s, ok = d(_R2_ANSWER)
    assert ok and "관련 기관" not in s and "추가 정보" not in s
    s, ok2 = h(s, _R2_SQL, 5)
    assert ok2 and "있을 수 있습니다" not in s and "기반으로 한 것이며" not in s
    assert all(v in s for v in ("823개", "235개", "207개", "205개", "142개")) and "다음과 같습니다." in s   # 값 5줄 보존
    # 패턴 확장 형제 — '해당 기관으로 확인' · '자세한 사항은 … 참고' · '일부' 유보
    assert "확인" not in d("순자산은 1,000억원입니다. 해당 기관으로 확인하시기 바랍니다.")[0]
    assert d("순자산은 1,000억원입니다. 자세한 사항은 운용사 홈페이지를 참고하세요.")[0] == "순자산은 1,000억원입니다."
    assert d("자세한 내용은 다음과 같습니다. 1. A펀드")[1] is False                    # 안내 도입부는 면책이 아니다
    assert h("A: 3개. 이는 일부일 수 있습니다.", "SELECT a, COUNT(*) FROM public_funds GROUP BY 1 LIMIT 30", 3)[0] == "A: 3개."
    # 불개입 — LIMIT 도달 목록(유보 정당) · 집계 아닌 목록 · 유보 문장 없음
    assert not h(_R2_ANSWER, _R2_SQL, 30)[1]
    assert not h("더 많은 펀드가 있을 수 있습니다.", "SELECT itm_nm FROM public_funds WHERE sale_yn='판매중' LIMIT 30", 5)[1]
    assert h("1위 823개입니다.", _R2_SQL, 5) == ("1위 823개입니다.", False)


def test_post_route_correction_from_sql(ctx):
    """P7-b — 라우터가 미특정으로 둔 질의도 HCX 가 FROM 을 하나로 정했으면 그 상품군의 답변 규칙·이름 필터를 살린다.
    R7 재검: 미특정 경로는 답변 규칙이 4도메인 12,443자로 희석됐다. 대표행 가드(P1)도 같은 경로에서 함께 발동해야 한다."""
    from src.runtime.pipeline import answer_question

    class P:
        def plan_sql(self, q, g):
            return _R7_SQL

        def compose_answer(self, q, rows, answer_rules=""):
            self.rules = answer_rules
            self.rows = rows
            return "x"

    p = P()
    q = "1년 수익률이 가장 높은 공모 상품 3개 알려줘"
    r = answer_question("T-R7b", q, planner=p, ctx=ctx)
    assert "[Route] 상품군 — 미특정" in r.think_trace
    assert "[Route] SQL 사후 보정 — FROM public_funds" in r.think_trace
    assert "GROUP BY 펀드키 주입" in r.think_trace and "(public_funds)" in r.think_trace.splitlines()[-1]
    assert p.rules == ctx.answer_context(["public_funds"])           # 4도메인 희석이 아니라 펀드 규칙 단일
    assert "NH-Amundi" in p.rows and "삼성KOSPI200" in p.rows          # gold 펀드단위 top3 가 답변 입력에 실린다
    # 라우터가 정한 질의엔 사후 보정 마커가 없다
    r2 = answer_question("T-R7c", "공모펌드 중 1년 수익률이 가장 높은 3개 알려줘", planner=P(), ctx=ctx)
    assert "SQL 사후 보정" not in r2.think_trace and "머리명사 펌드" in r2.think_trace


# ── 2026-09-02 리뷰(docs/recheck_2026-09-02_round1_review.md §②) — 배포 전 수리 7건의 회귀 ──
def test_name_filter_only_when_itm_nm_is_left_operand():
    """리뷰 ②-1 — SELECT 의 itm_nm 과 WHERE 의 다른 컬럼 LIKE 가 40자 안에 들면 이름 조회로 오인해
    "주식형 공모펀드" 목록이 개별 조회 묶기(최단 이름순 → 역외 1클래스 30개)로 빠졌다. 좌변 itm_nm 만 인정."""
    from src.runtime.pipeline import (_has_name_filter as h, ensure_fund_lookup_grouping as l,
                                      ensure_fund_list_grouping as g, ensure_fund_name_filter as nf)

    q = "주식형 공모펀드 알려줘"
    bad = ("SELECT itm_no, itm_nm FROM public_funds WHERE or_attr_desc LIKE '%주식%' AND sale_yn='판매중' "
           "AND prvo_pbff_desc='공모' LIMIT 30")
    assert not h(bad) and not l(bad, q)[1]
    s, ok = g(bad, q)
    assert ok and "ORDER BY fd_nast_suma DESC" in s
    first = _ro().execute(s).fetchone()
    assert first[2] > 1 or "역외" not in (first[1] or "")                 # 첫 행이 역외 1클래스 펀드가 아니다
    bad2 = "SELECT itm_nm FROM public_funds WHERE zrin_attr_nms LIKE '%중국%' LIMIT 30"
    assert not h(bad2) and not l(bad2, q)[1] and g(bad2, q)[1]
    assert not h("SELECT itm_nm FROM public_funds WHERE itm_nm NOT LIKE '%MMF%' LIMIT 30")    # 제외 필터는 이름 조회가 아니다
    # 이름 조회 3형은 종전대로 — 원형 · TRIM · 공백무시 REPLACE · GLOB
    assert h("SELECT itm_no FROM public_funds WHERE itm_nm LIKE '%코어테크%' LIMIT 30")
    assert h("SELECT itm_no FROM public_funds WHERE TRIM(itm_nm) LIKE '%코어테크%' LIMIT 30")
    assert h(_R4_SQL) and h(_R6_SQL) and l(_R4_SQL, "미래에셋코어테크 펀드 1년 수익률 알려줘")[1]
    # ensure_fund_name_filter 도 같은 판정 — SELECT 만 itm_nm 이면 '이미 이름 필터 있음' 이 아니다
    s2, ok2 = nf("SELECT itm_nm, fd_yr1_ern_r FROM public_funds WHERE or_attr_desc LIKE '%주식%' LIMIT 30", "코어테크")
    assert ok2 and "itm_nm LIKE '%코어테크%'" in s2
    assert not nf("SELECT itm_nm FROM public_funds WHERE itm_nm LIKE '%코어테크%' LIMIT 30", "코어테크")[1]


def test_distribution_not_for_topn_or_entity_axis(ctx):
    """리뷰 ②-2 — JOIN 없는 운용사 top5(GROUP BY or_co_xtn_itt_cd … ORDER BY 2 DESC LIMIT 5)에 3열이 붙고 조립기가
    "5개 범주 · 펀드 3,040개 · 복수 범주 1,632건" 조작 통계를 만들었다. top-N 꼴·개체 축은 분포가 아니다."""
    from src.runtime.pipeline import (ensure_fund_distribution_fund_count as f, _distribution_answer as d, answer_question)

    top5 = ("SELECT or_co_xtn_itt_cd, COUNT(*) FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
    assert not f(top5)[1]
    assert d(top5, "or_co_xtn_itt_cd | COUNT(*)\n00080008 | 2000\n00040007 | 900", 2) is None
    # 개체 축은 LIMIT 30 이어도 분포가 아니다 · ORDER BY 있어도 LIMIT 30(상한)이면 분포
    assert not f("SELECT itm_no, COUNT(*) FROM public_funds GROUP BY 1 LIMIT 30")[1]
    assert f("SELECT zrin_btyp_nm, COUNT(*) FROM public_funds GROUP BY 1 ORDER BY 2 DESC LIMIT 30")[1]
    # 통합 — 운용사 top5 는 HCX 답변기로 간다(기계 조립 마커 없음)
    class P:
        calls = 0

        def plan_sql(self, q, g):
            return top5

        def compose_answer(self, q, rows, answer_rules=""):
            P.calls += 1
            return "x"

    r = answer_question("T-TOP5", "펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘", planner=P(), ctx=ctx)
    assert "분포 답변 기계 조립" not in r.think_trace and "분포 펀드수 병기" not in r.think_trace
    # 2R Q2 이후 운용사 집계는 템플릿 + 전용 조립기(HCX 0회)가 받는다 — 분포 조립기가 아니라는 점은 그대로
    assert P.calls == 0 and "[Answer] 운용사 집계 답변 기계 조립" in r.think_trace and "823개" in r.answer
    # 절단된 분포(n == MAX_ROWS)는 전체/복수 범주 문장을 굽지 않는다
    sql3 = ("SELECT COALESCE(zrin_btyp_nm,'(미수록)'), COUNT(*), COUNT(DISTINCT x) AS 펀드수 FROM public_funds "
            "WHERE sale_yn = '판매중' GROUP BY zrin_btyp_nm LIMIT 30")
    rows = "a | COUNT(*) | 펀드수\n" + "\n".join(f"c{i} | 10 | 5" for i in range(30))
    a = d(sql3, rows, 30)
    assert a and a.startswith("조회 결과 상위 30개 범주(전체 중 일부)") and "복수 범주" not in a and "전체 펀드 수" not in a


def test_count_answer_label_and_merge_from_sql():
    """리뷰 ②-3 — 사모 질의에 '공모펀드' 라벨 · KG 2코드인데 SQL 1코드에도 합산 문장. 둘 다 SQL 에서 읽는다."""
    from src.runtime.pipeline import _count_answer as f

    g = ["'한국투자신탁운용' → Org_00040024 (Organization) → public_funds.or_co_xtn_itt_cd='00040024' · public_funds.or_co_xtn_itt_cd='00040105'"]
    private = ("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE prvo_pbff_desc = '사모' "
               "AND TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') LIMIT 30")
    a = f(private, "펀드수 | 클래스수\n265 | 273", 1, g)
    assert "한국투자신탁운용이 운용하는 사모펀드는 265개(클래스 273개)" in a and "공모" not in a and "사모 기준" in a
    one = ("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE sale_yn = '판매중' "
           "AND TRIM(or_co_xtn_itt_cd) = '00040024' AND prvo_pbff_desc = '공모' LIMIT 30")
    a1 = f(one, "펀드수 | 클래스수\n142 | 540", 1, g)
    assert "공모펀드는 142개(클래스 540개)" in a1 and "합산" not in a1                 # SQL 코드 1건 → 합산 문장 없음
    both = one.replace("= '00040024'", "IN ('00040024', '00040105')")
    a2 = f(both, "펀드수 | 클래스수\n143 | 541", 1, g)
    assert "143개(클래스 541개)" in a2 and "운용사 코드 2건(00040024·00040105)을 합산" in a2   # R5 종전
    # 모집 조건 없음 → '펀드' · 운용사 매핑 없음 → '조회 조건에 해당하는'
    a3 = f("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE sale_yn = '판매중' LIMIT 30",
           "펀드수 | 클래스수\n10 | 20", 1, [])
    assert a3.startswith("조회 조건에 해당하는 펀드는 10개(클래스 20개)")


def test_verify_product_names_no_cross_product_or_particle_loss():
    """리뷰 ②-4 — 'KODEX200TR'→'KODEX200'(다른 실제 상품) 치환 · '…3호는'→'…2호'(조사 삭제 + 부정문 주어 반전)."""
    from src.runtime.pipeline import verify_product_names as f

    rows = ("itm_nm\n삼성KODEX200증권상장지수투자신탁[주식]\n미래에셋차이나솔로몬증권투자신탁2호(주식)C2\n"
            "삼성중국본토중소형FOCUS증권자투자신탁UH(주식)Ce")
    a = "삼성KODEX200TR증권상장지수투자신탁 은 조회되지 않았습니다."
    assert f(a, rows) == (a, [])                                                    # 상위 문자열 — 별개 상품
    b = "미래에셋차이나솔로몬증권투자신탁3호는 조회되지 않았습니다."
    assert f(b, rows) == (b, [])                                                    # 숫자열 상이 — 별개 상품
    c = "미래에셋차이나솔로몬증권투자신탁2호는 높은 위험입니다."
    assert f(c, rows) == (c, [])                                                    # 정확(조사 뗀 어간이 부분문자열)
    out, fixes = f("삼성중국본토중소형FOSS증권자투자신탁UH의 1년 수익률", rows)
    assert out == "삼성중국본토중소형FOCUS증권자투자신탁UH의 1년 수익률" and len(fixes) == 1   # 종전 교정 + 조사 보존
    d = "삼성중국본토중소형FOCUS증권자투자신탁H(주식) 은 없습니다."
    assert f(d, rows) == (d, [])                                                    # H/UH — 하위 문자열


def test_fund_rank_sort_col_inside_function():
    """리뷰 ②-5 — 정렬 컬럼이 함수 인자(ROUND(col,2))면 별칭까지 붙여 문법 오류 → 무응답. agg(col) 만 감싼다."""
    from src.runtime.pipeline import ensure_fund_rank_representative as f

    con = _ro()
    s = ("SELECT itm_nm, ROUND(fd_yr1_ern_r,2) FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
         "AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') ORDER BY 2 DESC LIMIT 5")   # 기점오류 제외는 체인의 별도 가드
    out, ok = f(s, "1년 수익률 높은 공모펀드 5개")
    assert ok and "ROUND(MAX(fd_yr1_ern_r),2)" in out and " AS fd_yr1_ern_r" not in out
    rows = con.execute(out).fetchall()
    assert rows[0][1] == 387.66 and len(rows) == 5
    # 이름 ORDER BY 도 살린다 — ORDER BY fd_yr1_ern_r → MAX(fd_yr1_ern_r)
    s2 = s.replace("ORDER BY 2 DESC", "ORDER BY fd_yr1_ern_r DESC")
    out2, ok2 = f(s2, "q")
    assert ok2 and "ORDER BY MAX(fd_yr1_ern_r) DESC" in out2 and con.execute(out2).fetchone()[1] == 387.66
    # 기존 GROUP BY 경로에서도 동일
    s3 = ("SELECT itm_no, ROUND(fd_mm6_ern_r,1) FROM public_funds WHERE sale_yn='판매중' "
          "GROUP BY or_co_xtn_itt_cd, mtco_itm_no ORDER BY 2 DESC LIMIT 3")
    out3, ok3 = f(s3, "q")
    assert ok3 and "ROUND(MAX(fd_mm6_ern_r),1)" in out3 and len(con.execute(out3).fetchall()) == 3
    # bare 컬럼 경로는 종전(별칭 유지)
    assert "MAX(fd_yr1_ern_r) AS fd_yr1_ern_r" in f(_R7_SQL, "q")[0]


def test_fund_lookup_grouping_net_assets_sum_in_eok():
    """리뷰 ②-6 — 이 DB 의 fd_nast_suma 는 클래스별 값이라 펀드 순자산은 SUM. 개별 조회 묶기가 MAX/MIN _최고/_최저 원 단위
    '.0' 로 실던 것을 정수 SUM + 억원 병기로. 최고/최저는 수익률 8종에만."""
    from src.runtime.pipeline import ensure_fund_lookup_grouping as f, ensure_fund_evidence_columns as ev

    s = ("SELECT fd_nast_suma, itm_nm, fd_yr1_ern_r FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크증권자투자신탁%' "
         "AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 30")
    out, ok = f(s, "미래에셋코어테크 펀드 순자산 알려줘")
    assert ok and "CAST(SUM(fd_nast_suma) AS INTEGER) AS fd_nast_suma" in out and '"순자산_억원"' in out
    assert "fd_nast_suma_최고" not in out and '"fd_yr1_ern_r_최고"' in out
    out2, _ = ev(out)
    assert out2.count("순자산_억원") == 1                                    # 근거컬럼 가드가 억원을 중복 병기하지 않는다
    cols = [d[0] for d in _ro().execute(out2).description]
    row = _ro().execute(out2).fetchone()
    rec = dict(zip(cols, row))
    assert rec["클래스수"] == 10 and rec["fd_nast_suma"] == 2914801034334 and rec["순자산_억원"] == "29148억원"
    assert isinstance(rec["fd_nast_suma"], int)                                # '.0' 없음


# ── 2026-09-02 한전·삼성전자 실측 후속 — 값 검사 TRIM 사각 · 랭킹 만기 제외 · 채권 대표행 · 0 집계 · 커버리지 ──

def test_check_values_sees_trim_wrapped_literals(ctx):
    """ensure_trimmed_compare 가 pd_pbcm·bd_knd 를 TRIM 으로 감싼 뒤에 값 검사가 돌아, 발행사·등급 리터럴 검사가 0건이었다."""
    def v(where):
        return [(x.column, x.literal) for x in guard.check_values(f"SELECT pd_nm FROM domestic_bonds WHERE {where} LIMIT 30", ctx)]
    assert v("TRIM(pd_pbcm) = '삼성전자'") == [("pd_pbcm", "삼성전자")]
    assert v("TRIM(crd_grd) = 'AAAA'") == [("crd_grd", "AAAA")]
    assert v("TRIM(pd_pbcm) = '한국전력공사'") == [("pd_pbcm", "한국전력공사")]          # '(주)' 누락 — 0행 오거절 원인
    assert v("pd_nm LIKE '%삼성전자%' OR TRIM(pd_pbcm) = '삼성전자'") == [("pd_pbcm", "삼성전자")]
    # 정상 값은 통과 — 등호·IN·COALESCE 감싸기 전부
    assert v("TRIM(pd_pbcm) = '한국전력공사(주)'") == []
    assert v("COALESCE(TRIM(pd_pbcm),'')='한국은행'") == []
    assert v("TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-')") == []
    # '(주)' 누락 위반의 힌트에 실제 표기가 앞에 온다 — 재생성이 이걸로 고친다
    vs = guard.check_values("SELECT pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm) = '한국전력공사' LIMIT 5", ctx)
    assert vs[0].hint and vs[0].hint[0] == "한국전력공사(주)"


def test_check_values_trim_aware_no_false_positive_on_gold(ctx):
    """검증 gold SQL 전부(TRIM·COALESCE 감싼 리터럴 포함)에서 위반 0 — 정상 값을 기각하면 안 된다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in sorted(glob.glob(os.path.join(root, "eval", "questions_*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            q = json.loads(line)
            if q.get("gold_sql") and q.get("gold_verified"):
                assert guard.check_values(q["gold_sql"], ctx) == [], q["qid"]


def test_rank_exclusions_add_maturity_cutoff():
    from src.runtime.pipeline import ensure_reco_exclusions as f
    sql = "SELECT pd_nm, applied_yield FROM domestic_bonds WHERE TRIM(pd_pbcm) = '한국전력공사(주)' ORDER BY applied_yield ASC LIMIT 5"
    q = "한전 채권 수익률 낮은 순으로 알려줘"
    fixed, ch = f(sql, q)
    assert ch and "mat_dt >= 20260822" in fixed and fixed.index("mat_dt") < fixed.index("ORDER BY")
    assert not f(fixed, q)[1]                                                       # 멱등 — 하한 있으면 재주입 없음
    assert "mat_dt" not in f(sql, "만기 지난 한전 채권 수익률 높은 순으로 알려줘")[0]     # 범주 언급 = 우회
    assert not f(sql.replace(" ORDER BY applied_yield ASC", ""), "한전 채권 알려줘")[1]  # 조회는 제외하지 않는다


def test_bond_evidence_and_representative(ctx):
    from src.runtime.pipeline import ensure_bond_evidence_columns as ev, ensure_bond_representative as rep, _execute
    sql = ("SELECT pd_nm, applied_yield FROM domestic_bonds WHERE TRIM(pd_pbcm) = '한국전력공사(주)' AND applied_yield > 0 "
           "AND mat_dt >= 20260822 ORDER BY applied_yield ASC LIMIT 5")
    s1, c1 = ev(sql)
    assert c1 and "mat_dt" in s1 and "TRIM(crd_grd) AS crd_grd" in s1
    assert not ev(s1)[1]
    s2, c2 = rep(s1)
    assert c2 and "GROUP BY pd_no" in s2 and "MIN(applied_yield) AS applied_yield" in s2 and "ORDER BY MIN(applied_yield) ASC" in s2
    rows, n = _execute(s2)
    names = [l.split(" | ")[0] for l in rows.splitlines()[1:]]
    assert n == 5 and len(set(names)) == 5 and "한국전력공사채권1063" not in names      # 중복 없음 · 만기 경과 없음
    assert names[0] == "한국전력공사채권1065"
    # DESC 는 MAX
    assert "MAX(applied_yield)" in rep("SELECT pd_nm, applied_yield FROM domestic_bonds ORDER BY applied_yield DESC LIMIT 5")[0]
    # 불개입 — 집계 · DISTINCT · 기존 GROUP BY · 장내/장외 컬럼 · 이름 컬럼 없음 · 만기 정렬(근거컬럼)
    assert not rep("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE applied_yield > 5 LIMIT 30")[1]
    assert not rep("SELECT DISTINCT pd_nm FROM domestic_bonds LIMIT 30")[1]
    assert not rep("SELECT pd_nm, applied_yield FROM domestic_bonds GROUP BY pd_no LIMIT 30")[1]
    assert not rep("SELECT pd_nm, pd_exg_mkt FROM domestic_bonds LIMIT 30")[1]
    assert not rep("SELECT applied_yield FROM domestic_bonds LIMIT 30")[1]
    assert not ev("SELECT pd_nm FROM domestic_bonds WHERE mat_dt >= 20260822 ORDER BY mat_dt DESC LIMIT 5")[1]


def test_zero_count_answer_and_issuer_clarify(ctx):
    from src.runtime.pipeline import _zero_count_answer as z, _suggest_similar_issuers as s, _issuer_literal as lit, _violated_issuer
    sql = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE pd_nm LIKE '%삼성전자%' OR TRIM(pd_pbcm) = '삼성전자' LIMIT 30"
    a = z(sql, "COUNT(DISTINCT pd_no)\n0", 1)
    assert a and "확인되지 않습니다" in a and "0종목" in a and "삼성카드(주)(323종목)" in a and "삼성전자" in a
    assert z(sql, "COUNT(DISTINCT pd_no)\n5", 1) is None                          # 양수는 불개입
    assert z("SELECT pd_nm FROM domestic_bonds LIMIT 1", "pd_nm\nx", 1) is None    # 집계 아님
    assert z(sql, "COUNT(DISTINCT pd_no)\n0", 0) is None                          # 0행은 별도 경로
    assert lit(sql) == "삼성전자" and lit("SELECT 1 FROM domestic_bonds WHERE pd_pbcm = '삼성카드(주)'") == "삼성카드(주)"
    c = s("한국전력공사")
    assert c and c[0].startswith("한국전력공사(주)(")                                  # 어간 포함 후보 우선
    assert s("삼") == [] and s(None) == []
    vs = guard.check_values("SELECT pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm) = '삼성전자' LIMIT 5", ctx)
    assert _violated_issuer(vs) == "삼성전자" and _violated_issuer([]) is None


def test_explicit_limit_hit_and_hedge_exemption():
    from src.runtime.pipeline import _explicit_limit_hit as hit, strip_false_hedge as h
    top5 = ("SELECT pd_nm, MAX(applied_yield) AS applied_yield FROM domestic_bonds WHERE applied_yield > 0 "
            "GROUP BY pd_no ORDER BY MAX(applied_yield) DESC LIMIT 5")
    assert hit(top5, 5) and not hit(top5, 4)
    assert not hit(top5.replace("LIMIT 5", "LIMIT 30"), 30)                         # 상한은 종전 커버리지 경로
    assert not hit("SELECT pd_nm FROM domestic_bonds LIMIT 5", 5)                   # 정렬 없는 목록은 '상위' 가 아니다
    # 잘린 개체 목록의 '더 있다' 는 참 — 걷어내지 않는다 / COUNT 정렬 top-k 는 전수 집계 — 종전대로 걷어낸다
    assert not h("상위 5개입니다. 이외에도 더 많은 채권이 있을 수 있습니다.", top5, 5)[1]
    assert h("A: 3개. 이는 일부일 수 있습니다.", "SELECT a, COUNT(*) FROM public_funds GROUP BY 1 ORDER BY 2 DESC LIMIT 5", 5)[0] == "A: 3개."


# ── 2026-09-02 라운드 2 (docs/recheck_2026-09-02_round2.md §③ Q1~Q7) ──
_R2_FIRST_SQL = ("SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) AS 운용사코드, MAX(mtco_nm) AS 운용사명, "
                 "COUNT(DISTINCT CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no ELSE substr('0000000' || mtco_itm_no, -7) END) AS 펀드수 "
                 "FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
                 "WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 3 DESC LIMIT 5")
_R2_REGEN_SQL = ("SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) AS 운용사코드, MAX(CASE WHEN printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || mgmt_co_nm "
                 "NOT IN ('00040007/프랭클린템플턴투자신탁운용', '00040010/삼성액티브자산운용', '00040011/미래에셋자산운용', '00040013/슈로더자산운용', "
                 "'00040023/우리자산운용', '00080008/멀티에셋자산운용', '00080008/미래에셋맵스자산운용') THEN mgmt_co_nm END) AS 운용사명, "
                 "COUNT(DISTINCT COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS 펀드수 "
                 "FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
                 "WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 3 DESC LIMIT 5")
_S11_REGEN_SQL = ("SELECT mgmt_co_nm, COUNT(*) as cnt FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
                  "GROUP BY mgmt_co_nm ORDER BY cnt DESC LIMIT 3")
_R2_GOLD = [("00080008", "미래에셋자산운용", 823), ("00040007", "우리자산운용", 235), ("00040010", "삼성자산운용", 207),
            ("00080035", "iM에셋자산운용", 205), ("00040024", "한국투자신탁운용", 142)]


def test_join_ambiguous_itm_no_qualified(ctx):
    """Q1-b — R2 2R 재생성 SQL(비한정 itm_no) 이 모호 컬럼 기각 → 거절. 기각 대신 FROM 테이블로 기계 한정한다."""
    from src.runtime.pipeline import qualify_join_columns as f, _apply_sql_guards

    assert guard.ambiguous_columns(_R2_REGEN_SQL, ctx) == ["itm_no"]          # 검사기 단독은 여전히 기각(안전망)
    s, cols = f(_R2_REGEN_SQL, ctx)
    assert cols == ["itm_no"] and guard.ambiguous_columns(s, ctx) == [] and "public_funds.itm_no)" in s
    assert "ext_fund_page.itm_no = public_funds.itm_no" in s                    # 이미 한정된 ON 절은 불변
    assert f(s, ctx) == (s, [])                                                 # 멱등
    rows = _ro().execute(s).fetchall()
    assert [tuple(r) for r in rows] == _R2_GOLD
    # 체인 통과(재생성 경로와 동일) 후에도 모호 컬럼 0 · 값 gold
    chained = _apply_sql_guards(_R2_REGEN_SQL, "펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘", None, None, lambda m: None, ctx)
    assert guard.ambiguous_columns(chained, ctx) == []
    # 1R 재생성 SQL(COALESCE 없음)은 무변경
    one_r = _R2_REGEN_SQL.replace("COALESCE(", "(").replace(", itm_no))", "))")
    assert f(one_r, ctx) == (one_r, [])


def test_ext_join_injected(ctx):
    """Q1-c(일반화) — 마스터 단독 SQL 이 1:1 외부 테이블 전용 컬럼을 쓰면 JOIN_KEYS 의 ON 절로 LEFT JOIN 을 주입하고,
    없는 컬럼이 그 ext 전용 컬럼의 유일 근사면 치환한다(mtco_nm → mgmt_co_nm 이 그 한 사례 — 하드코딩 아님)."""
    from src.runtime.pipeline import ensure_ext_join as f

    s, notes = f(_R2_FIRST_SQL, ctx)                                             # R2 1차: JOIN 있음 · 환각 컬럼만 치환
    assert notes == ["mtco_nm → mgmt_co_nm(유일 근사)"] and "MAX(mgmt_co_nm)" in s and s.count("ext_fund_page") == 2
    assert guard.unknown_columns(s, ctx) == []
    s2, notes2 = f(_S11_REGEN_SQL, ctx)                                          # S11 재생성: JOIN 주입
    assert notes2 and "FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE" in s2
    assert guard.unknown_columns(s2, ctx) == [] and len(_ro().execute(s2).fetchall()) == 3
    assert f(s2, ctx) == (s2, [])                                                # 멱등
    s3, _ = f("SELECT p.itm_nm, mgmt_co_nm FROM public_funds p WHERE p.sale_yn='판매중' LIMIT 5", ctx)   # 별칭
    assert "FROM public_funds p LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = p.itm_no WHERE" in s3
    # 비발동 — 마스터 컬럼만 · 타 도메인 · 팬아웃 테이블(ext_fund_holdings) 전용 컬럼은 자동 주입 대상 아님
    assert f("SELECT itm_nm FROM public_funds WHERE sale_yn='판매중' LIMIT 5", ctx) == ("SELECT itm_nm FROM public_funds WHERE sale_yn='판매중' LIMIT 5", [])
    assert f("SELECT pd_nm FROM domestic_bonds LIMIT 5", ctx)[1] == []
    assert "ext_fund_holdings" not in f("SELECT itm_nm, weight_pct FROM public_funds LIMIT 5", ctx)[0]


def test_r2_pipeline_no_longer_rejected(ctx):
    """R2 회귀 통합 — 1차 mtco_nm 환각이 기각 없이 JOIN·치환으로 살아나 재생성 예산이 보존되고, 값 gold 5행이 조회된다."""
    from src.runtime.pipeline import answer_question

    class P:
        plans = 0

        def plan_sql(self, q, g):
            P.plans += 1
            return _R2_FIRST_SQL

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-R2", "펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘", planner=P(), ctx=ctx)
    # 3R ④-2 — 템플릿(Q2-a)이 JOIN 주입(Q1-c)보다 먼저: R2 는 템플릿이 SQL 을 통째로 만들어 JOIN 주입 마커가 남지 않는다(작업 1회)
    assert P.plans == 1 and "[Guard] SQL 기각" not in r.think_trace and "[Guard] 운용사 집계 확정식" in r.think_trace
    assert "[Guard] 외부 테이블 JOIN 주입" not in r.think_trace
    assert "823" in r.retrieved_context and "우리자산운용" in r.retrieved_context and "142" in r.retrieved_context


_S11_FIRST_SQL = ("SELECT mtco_nm, COUNT(*) as cnt FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
                  "GROUP BY mtco_nm ORDER BY cnt DESC LIMIT 3")


def test_fund_manager_ranking_template(ctx):
    """Q2-a/b — S11: 이름 GROUP BY + COUNT(*) 로 순자산 질의를 오해. 코드 GROUP BY·최빈 이름·펀드수·클래스수·순자산 억원
    템플릿으로 교체하고 5열 결과는 기계 조립한다."""
    from src.runtime.pipeline import ensure_fund_manager_ranking as f, _manager_rank_answer as a, _apply_sql_guards, _execute

    q11 = "순자산이 가장 큰 운용사 상위 3개 알려줘"
    s, ok = f(_S11_FIRST_SQL, q11)
    assert ok and "GROUP BY 1 ORDER BY SUM(p.fd_nast_suma) DESC LIMIT 3" in s and "MAX(e.mgmt_co_nm)" in s
    assert not f(s, q11)[1]                                                    # 멱등
    chained = _apply_sql_guards(_S11_FIRST_SQL, q11, None, None, lambda m: None, ctx)
    assert guard.unknown_columns(chained, ctx) == [] and guard.ambiguous_columns(chained, ctx) == []
    rows, n = _execute(chained)
    body = [ln.split(" | ") for ln in rows.splitlines()[1:]]
    assert n == 3 and [(b[0], b[1], b[4]) for b in body] == [("00080008", "미래에셋자산운용", "377707억원"),
                                                             ("00040010", "삼성자산운용", "331097억원"),
                                                             ("00040035", "KB자산운용", "278196억원")]
    ans = a(chained, rows, n)
    assert ans and ans.startswith("조회 결과 순자산 상위 3개 운용사입니다") and "1. 미래에셋자산운용(00080008): 순자산 377,707억원 · 펀드 823개(클래스 2,066개)" in ans
    # R2 질문 → 펀드수 축 5행 = gold (최빈 이름 가드가 우리자산운용으로)
    q2 = "펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘"
    chained2 = _apply_sql_guards(_R2_FIRST_SQL, q2, None, None, lambda m: None, ctx)
    rows2, n2 = _execute(chained2)
    body2 = [ln.split(" | ") for ln in rows2.splitlines()[1:]]
    assert [(b[0], b[1], int(b[2])) for b in body2] == _R2_GOLD
    assert "1. 미래에셋자산운용(00080008): 펀드 823개(클래스 2,066개) · 순자산 377,707억원" in a(chained2, rows2, n2)
    # 부가 조건 보존 · 비발동('클래스' 명시 · 운용사 컬럼 없음 · 랭킹어 없음)
    s3, ok3 = f("SELECT or_co_xtn_itt_cd, COUNT(*) FROM public_funds WHERE zrin_btyp_nm = '주식형' GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
                "주식형 펀드를 가장 많이 운용하는 운용사 상위 5개")
    assert ok3 and "AND zrin_btyp_nm = '주식형'" in s3
    assert not f(_S11_FIRST_SQL, "운용사별 클래스 수 상위 3개")[1]
    assert not f("SELECT itm_nm FROM public_funds ORDER BY fd_nast_suma DESC LIMIT 3", q11)[1]
    assert not f(_S11_FIRST_SQL, "운용사 목록 알려줘")[1]
    assert a("SELECT COUNT(*) FROM public_funds LIMIT 1", "COUNT(*)\n5", 1) is None


def test_s11_pipeline_assembled(ctx):
    """S11 통합 — 라우터 3테이블 → 사후 보정(FROM public_funds · 재생성 문서 교체) → 템플릿 → 기계 조립(HCX 답변기 0회)."""
    from src.runtime.pipeline import answer_question

    class P:
        calls = 0

        def plan_sql(self, q, g):
            return _S11_FIRST_SQL

        def compose_answer(self, q, rows, answer_rules=""):
            P.calls += 1
            return "x"

    r = answer_question("T-S11", "순자산이 가장 큰 운용사 상위 3개 알려줘", planner=P(), ctx=ctx)
    assert P.calls == 0 and "[Guard] SQL 기각" not in r.think_trace
    # 3R B-2 — 상품 명사 없는 운용사 집계는 라우터가 public_funds 로 확정(사후 보정 불필요)
    assert "운용사 집계 정본 = 공모펀드 마스터" in r.think_trace and "SQL 사후 보정" not in r.think_trace
    assert "[Guard] 운용사 집계 확정식" in r.think_trace and "[Answer] 운용사 집계 답변 기계 조립" in r.think_trace
    assert "377,707억원" in r.answer and "삼성자산운용(00040010)" in r.answer and "KB자산운용(00040035)" in r.answer


def test_country_tag_guard_catches_bare_and_name_forms():
    """2R Q3 — S6: `prfd_attr_cds LIKE '%IND%'`(콤마 없음) · `zrin_attr_nms LIKE '%인도%'` 가 정규식 밖이라 가드 미발동 →
    인도네시아 7행 혼입(142행/59펀드, gold 135/58). 두 표현형을 정식형으로 치환하고 중복 OR 은 접는다."""
    from src.runtime.pipeline import ensure_fund_country_tag as f, _FUND_KEY_EXPR

    con = _ro()
    s6 = ("SELECT DISTINCT itm_no, itm_nm, prfd_attr_cds, zrin_attr_nms FROM public_funds WHERE prvo_pbff_desc = '공모' "
          "AND (prfd_attr_cds LIKE '%IND%' OR zrin_attr_nms LIKE '%인도%') AND sale_yn = '판매중' LIMIT 30")
    s, ok = f(s6, "인도에 투자하는 공모펀드 알려줘")
    canon = "',' || prfd_attr_cds || ',' LIKE '%,IND,%'"
    assert ok and "zrin_attr_nms LIKE" not in s and s.count(canon) == 1 and "'%IND%'" not in s
    assert not f(s, "인도에 투자하는 공모펀드 알려줘")[1]                      # 멱등
    cnt = s.replace("SELECT DISTINCT itm_no, itm_nm, prfd_attr_cds, zrin_attr_nms", f"SELECT COUNT(*), COUNT(DISTINCT {_FUND_KEY_EXPR})").replace(" LIMIT 30", "")
    assert con.execute(cnt).fetchone() == (135, 58)
    assert con.execute(cnt.replace("COUNT(*), COUNT(DISTINCT " + _FUND_KEY_EXPR + ")", "COUNT(*)") + " AND itm_nm LIKE '%인도네시아%'").fetchone() == (0,)
    # 인도네시아 질문은 IDN 경로 그대로(부분어 역방향)
    s2, ok2 = f("SELECT itm_nm FROM public_funds WHERE zrin_attr_nms LIKE '%인도네시아%' LIMIT 30", "인도네시아에 투자하는 공모펀드 알려줘")
    assert ok2 and "'%,IDN,%'" in s2 and "IND" not in s2
    # S7: 정식형 + 콤마 없는 둘째 절 → 하나로 접힘 · 119행
    s7 = ("SELECT itm_no, itm_nm FROM public_funds WHERE prvo_pbff_desc = '공모' AND (',' || prfd_attr_cds || ',' LIKE '%,VNM,%' "
          "OR prfd_attr_cds LIKE '%VNM%') AND sale_yn = '판매중' LIMIT 30")
    s3, ok3 = f(s7, "베트남에 투자하는 공모펀드 알려줘")
    assert ok3 and s3.count("'%,VNM,%'") == 1 and " OR " not in s3
    assert con.execute(s3.replace("SELECT itm_no, itm_nm", "SELECT COUNT(*)").replace(" LIMIT 30", "")).fetchone() == (119,)


_R4_ROWS = ("대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_yr1_ern_r_최고 | fd_yr1_ern_r_최저\n"
            "KR5153450780 | 미래에셋코어테크증권자투자신탁(주식) 종류A | 9 | 9 | 189.77 | 187.09\n"
            "KR5153450910 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A | 4 | 4 | 188.63 | 186.98\n"
            "KR5153451151 | 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류C-I | 3 | 3 | 13.66 | 13.19\n"
            "KR5153451160 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류A-e | 5 | 5 | 15.98 | 15.21")
_S3_ROWS = ("대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_yr1_ern_r_최고 | fd_yr1_ern_r_최저\n"
            "KR5114450100 | 삼성코리아대표분할매수증권투자신탁 1[주식혼합] | 1 | 1 | 105.49 | 105.49\n"
            "KR5114450011 | 삼성코리아대표증권자투자신탁 제1호[주식](A) | 9 | 9 | 109.72 | 106.71\n"
            "KR5114450170 | 삼성코리아대표그룹목표전환증권투자신탁 제1호[채권] A | 2 | 0 |  | \n"
            "KR5114440010 | 삼성코리아대표분할매수목표전환증권투자신탁 1[채권]_A | 2 | 0 |  | ")
_R6_ROWS = ("대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | zrin_fd_ivst_risk_grd_nm | zrin_fd_ivst_risk_gcd | 대표번호\n"
            + "\n".join(f"KR51090268{i}M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C{i+1} | 1 | 1 | 높은 위험 | 2 | 031910531100" for i in range(5))
            + "\nKR510902045M | 미래에셋차이나솔로몬증권투자신탁2호(주식)(C-A) | 2 | 2 | 높은 위험 | 2 | 031910531100")


def test_fund_stem():
    from src.runtime.pipeline import _fund_stem as f

    assert f("미래에셋코어테크증권자투자신탁(주식) 종류A") == "미래에셋코어테크증권자투자신탁(주식)"
    assert f("삼성코리아대표증권자투자신탁 제1호[주식](A)") == "삼성코리아대표증권자투자신탁 제1호[주식]"
    assert f("미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류A-e") == "미래에셋차이나코어테크증권자투자신탁(주식)(UH)"
    assert f("미래에셋차이나본토증권자투자신탁2호(UH)(주식)C3") == "미래에셋차이나본토증권자투자신탁2호(UH)(주식)"
    assert f("KB차이나고배당40증권자투자신탁(채권혼합)C-P클래스") == "KB차이나고배당40증권자투자신탁(채권혼합)"
    assert f("Plus신종개인용MMF2호 종류CP-1") == "Plus신종개인용MMF2호"
    assert f("삼성MMF법인제1호 C 클래스") == "삼성MMF법인제1호"


def test_lookup_answer_assembled(ctx):
    """2R Q4 — R4·S3: '종류A: 최고 189.77%'(종류A 실값 187.94)·판매완료 재료 미전달 · R6: '등급 지수 2.0'. 기계 조립."""
    from src.runtime.pipeline import _lookup_answer as f, _cell, ensure_fund_evidence_columns as ev, answer_question

    a = f(_R4_SQL, _R4_ROWS, 4, "코어테크")
    assert a.startswith("'코어테크' 이름의 공모펀드 4개가 조회됐습니다")
    assert "- 미래에셋코어테크증권자투자신탁(주식): 1년 수익률 187.09%~189.77% (클래스에 따라 다름, 누적) · 클래스 9개(전부 판매중)" in a
    assert "종류A" not in a and "(H)" in a and "(UH)" in a
    b = f("SELECT x FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%삼성코리아대표%' AND prvo_pbff_desc = '공모' LIMIT 30", _S3_ROWS, 4)
    assert "'삼성코리아대표' 이름의 공모펀드 4개" in b and "(A)" not in b and "106.71%~109.72%" in b
    assert b.count("판매완료(신규 가입 불가)") == 2 and "1년 수익률 105.49% (누적)" in b
    c = f(_R6_SQL, _R6_ROWS, 6)
    assert c.count("\n- ") == 1 and "- 미래에셋차이나솔로몬증권투자신탁2호(주식): 위험등급 2등급(높은 위험) · 클래스 7개(전부 판매중)" in c
    assert _cell(2.0, "zrin_fd_ivst_risk_gcd") == "2" and _cell(2.5, "zrin_fd_ivst_risk_gcd") == "2.5"
    # 비발동 — lookup 형이 아닌 결과
    assert f(_R4_SQL, "itm_no | itm_nm\nA | B", 1) is None
    # S4: WHERE 에 gcd IS NOT NULL 이 있어도 SELECT 에 없으면 gcd 병기 (역방향 판정은 head 기준)
    s4 = ("SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS \"클래스수\", MAX(zrin_fd_ivst_risk_grd_nm) AS zrin_fd_ivst_risk_grd_nm "
          "FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%KB차이나%' AND zrin_fd_ivst_risk_gcd IS NOT NULL GROUP BY itm_no LIMIT 30")
    s, ok = ev(s4)
    assert ok and ", zrin_fd_ivst_risk_gcd FROM" in s
    # 통합 — R4 SQL → 묶기(대표번호 포함) → 기계 조립(HCX 0회), 6펀드
    class P:
        calls = 0

        def plan_sql(self, q, g):
            return _R4_SQL

        def compose_answer(self, q, rows, answer_rules=""):
            P.calls += 1
            return "x"

    r = answer_question("T-R4", "미래에셋코어테크 펀드 1년 수익률 알려줘", planner=P(), ctx=ctx)
    assert P.calls == 0 and "[Answer] 개별 조회 답변 기계 조립" in r.think_trace and "대표번호" in r.retrieved_context
    assert "미래에셋코어테크증권자투자신탁(주식): 1년 수익률 187.09%~189.77%" in r.answer and "종류A" not in r.answer
    assert r.answer.count("\n- ") == 6
    # R6 통합 — 6행이 1줄 '클래스 7개' 로 접힌다 (표시 단위만 rptt · 카운트 gold 불변)
    P.plan_sql = lambda self, q, g: _R6_SQL
    r6 = answer_question("T-R6", "미래에셋차이나솔로몬증권투자신탁 2호 위험등급 알려줘", planner=P(), ctx=ctx)
    assert r6.answer.count("\n- ") == 1 and "위험등급 2등급(높은 위험) · 클래스 7개" in r6.answer


def test_list_answer_assembled(ctx):
    """2R Q5 — R3·S7: 커버리지를 구워 줘도 5·10행만 옮기고 "일부입니다" · S6: 총량 대신 "더 있을 수 있음". 목록은 전 행 + 총량 머리줄로 기계 조립."""
    from src.runtime.pipeline import answer_question, _list_answer as f

    class P:
        calls = 0
        sql = _R3_SQL

        def plan_sql(self, q, g):
            return P.sql

        def compose_answer(self, q, rows, answer_rules=""):
            P.calls += 1
            return "x"

    r = answer_question("T-R3L", "중국에 투자하는 공모펀드 알려줘", planner=P(), ctx=ctx)
    assert P.calls == 0 and "[Answer] 목록 답변 기계 조립" in r.think_trace
    assert r.answer.startswith("조건에 해당하는 공모펀드는 전체 248개(클래스 560개)이며, 순자산 상위 30개 펀드는 다음과 같습니다")
    body = [ln for ln in r.answer.splitlines() if re.match(r"\d+\. ", ln)]
    assert len(body) == 30 and body[0].startswith("1. KB중국본토A주증권자투자신탁[주식]: 순자산 1,453억원 · 클래스 14개")
    assert "일부" not in r.answer and "있을 수 있" not in r.answer
    # S7 베트남 — 38펀드 · 30줄
    P.sql = ("SELECT DISTINCT itm_no, itm_nm, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' "
             "AND (',' || prfd_attr_cds || ',' LIKE '%,VNM,%' OR prfd_attr_cds LIKE '%VNM%') AND sale_yn = '판매중' LIMIT 30")
    r7 = answer_question("T-S7", "베트남에 투자하는 공모펀드 알려줘", planner=P(), ctx=ctx)
    assert "전체 38개(클래스 119개)" in r7.answer and sum(1 for ln in r7.answer.splitlines() if re.match(r"\d+\. ", ln)) == 30
    # 절단 없음(LIMIT 5) → "전체 5개"
    P.sql = _R3_SQL.replace("LIMIT 30", "LIMIT 5")
    r5 = answer_question("T-R3s", "중국에 투자하는 공모펀드 알려줘", planner=P(), ctx=ctx)
    assert "상위 5개" in r5.answer or "전체 5개" in r5.answer
    # 비발동 — 목록 형이 아닌 결과
    assert f("SELECT itm_nm FROM public_funds LIMIT 5", "itm_nm\nA", 1) is None


def test_series_boundary_covers_paren_notation():
    """2R Q6 — S5: `GLOB '*[^0-9]3호*'` 가 ' 3(주식)' 표기 4클래스를 놓쳐 4/8. 'N호'·'N(' 두 표기를 함께 잡고 12호·2.2배는 배제."""
    from src.runtime.pipeline import ensure_fund_series_boundary as f

    con = _ro()
    base = "SELECT itm_no FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬증권투자신탁%' AND itm_nm LIKE '%3호%' LIMIT 30"
    s, ok = f(base, "미래에셋차이나솔로몬증권투자신탁 3호 위험등급 알려줘")
    assert ok and len(con.execute(s).fetchall()) == 8                     # 3호 4 + ' 3(주식)' 4 = 같은 대표번호 8클래스
    assert not f(s, "미래에셋차이나솔로몬증권투자신탁 3호 위험등급 알려줘")[1]   # 멱등
    s2, _ = f(base.replace("3호", "2호"), "미래에셋차이나솔로몬증권투자신탁 2호 위험등급 알려줘")
    assert len(con.execute(s2).fetchall()) == 7                           # R6 2호 그대로
    # 배제 — 12호 · 2.2배 (앞 글자가 숫자·소수점)
    assert con.execute("SELECT COUNT(*) FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%한화2.2배레버리지%' "
                       "AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2[([]*')").fetchone() == (0,)
    s12 = "SELECT COUNT(*) FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%12호%' AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2[([]*')"
    assert con.execute(s12).fetchone() == (0,)
    # 'GS지속가능성장 1[주식]' 형이 '1호' 질문에 잡힌다
    s3, _ = f("SELECT itm_no, itm_nm FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%삼성코리아대표분할매수%' AND itm_nm LIKE '%1호%' LIMIT 30",
              "삼성코리아대표분할매수 1호 알려줘")
    assert any("1[" in r[1] for r in con.execute(s3))



def test_count_answer_offshore_sibling_note():
    """2R Q7 — S9 피델리티: 국내 코드 00080029 106펀드로 답이 끝나면 브랜드 펀드 전부로 읽힌다. 같은 이름 접두의 역외 코드(종별 0013)
    행수를 별도 병기. S8 KB(역외 없음)는 무병기. 특정 운용사 하드코딩 없이 코드 종별 + 이름 접두로 판정."""
    from src.runtime.pipeline import _count_answer as f

    sql = ("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE sale_yn = '판매중' "
           "AND (TRIM(or_co_xtn_itt_cd) IN ('00080029') AND prvo_pbff_desc = '공모') LIMIT 30")
    g = ["'피델리티' → Org_00080029 (Organization) → public_funds.or_co_xtn_itt_cd='00080029'"]
    a = f(sql, "펀드수 | 클래스수\n106 | 246", 1, g)
    assert "피델리티가 운용하는 공모펀드는 106개(클래스 246개)" in a
    assert "종목명이 '피델리티' 로 시작하는 역외펀드 47개(클래스 47개, 해외 운용법인 코드 00130001)는 별도 법인이라" in a
    kb = f(sql.replace("00080029", "00040035"), "펀드수 | 클래스수\n129 | 625", 1,
           ["'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035'"])
    assert "129개(클래스 625개)" in kb and "역외" not in kb
    # 운용사 매핑이 없으면 병기 없음
    assert "역외" not in f(sql, "펀드수 | 클래스수\n1 | 2", 1, [])


# ── KG 구조 검증 1R (docs/kg_structure_probe_round1_2026-09-02.md) — 런타임 큐 ──
_KG002_FIRST = ("SELECT DISTINCT itm_no, itm_nm FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no "
                "WHERE public_funds.or_co_xtn_itt_cd = '00040022' AND public_funds.prvo_pbff_desc = '공모' AND public_funds.sale_yn = '판매중' "
                "AND ext_fund_page.mgmt_co_nm LIKE '%템플턴%' AND itm_nm LIKE '%템플턴%' LIMIT 30")
_KG002_REGEN = ("SELECT DISTINCT p.itm_no, p.itm_nm FROM public_funds p JOIN ext_fund_page e ON e.itm_no = p.itm_no "
                "WHERE p.or_co_xtn_itt_cd = '00040022' AND p.prvo_pbff_desc = '공모' AND p.sale_yn = '판매중' "
                "AND e.mgmt_co_nm LIKE '%템플턴%' AND p.itm_nm LIKE '%템플턴%' LIMIT 30")


def test_guard_keeps_qualifier_inside_function(ctx):
    """R3-⑤ (KG-002 실측) — TRIM 가드가 `public_funds.TRIM(or_co…)`, 공백무시 가드가 `p.REPLACE(itm_nm,…)` 을 만들어
    1차 기각·재생성 OperationalError → "오류" 무응답. 일반 규칙: 컬럼을 함수로 감쌀 때 한정자는 인자 안에 남는다."""
    from src.runtime.pipeline import ensure_trimmed_compare as t, ensure_spaceless_name_match as sp, _apply_sql_guards, _has_name_filter

    s, ok = t(_KG002_FIRST)
    assert ok and "TRIM(public_funds.or_co_xtn_itt_cd) = '00040022'" in s and "public_funds.TRIM(" not in s
    s2, ok2 = sp(_KG002_REGEN)
    assert ok2 and "REPLACE(p.itm_nm,' ','') LIKE '%템플턴%'" in s2 and "p.REPLACE(" not in s2
    assert _has_name_filter(s2)
    for raw in (_KG002_FIRST, _KG002_REGEN):
        chained = _apply_sql_guards(raw, "프랭클린템플턴이 운용하는 공모펀드 알려줘", "템플턴", None, lambda m: None, ctx)
        assert ".TRIM(" not in chained and ".REPLACE(" not in chained
        assert guard.unknown_columns(chained, ctx) == [] and guard.ambiguous_columns(chained, ctx) == []
        _ro().execute(chained).fetchall()                                   # 실행 가능
    # 무한정 형은 종전대로
    assert t("SELECT 1 FROM public_funds WHERE or_co_xtn_itt_cd = '00040022' LIMIT 1")[0].count("TRIM(or_co_xtn_itt_cd)") == 1


def test_absent_properties_gate(ctx):
    """KG 1R S5/R2 (KG-027) — 좌수 환각: fd_set_pcd '10' 을 "10좌" 로 6펀드 단언. 일반 규칙: enums absent_properties 선언 =
    ttl ABSENT = 게이트 어휘 → HCX 0회 즉답. 기준가(있음)는 통과, '기준가 추이'(시계열)는 기각. 4도메인 같은 형식."""
    from src.runtime import gate
    from src.runtime.pipeline import answer_question

    assert ctx.absent_props.get("public_funds") and ctx.absent_props.get("domestic_etfs") and ctx.absent_props.get("domestic_bonds")
    g = gate.check("미래에셋코어테크 펀드 설정 좌수 알려줘", ctx, ["public_funds"])
    assert g.rejected and "좌수" in g.answer and "좌입니다" not in g.answer and "억좌" not in g.answer and "순자산" in g.answer
    assert gate.check("미래에셋코어테크 펀드 잔존좌수 알려줘", ctx, ["public_funds"]).rejected
    assert gate.check("미래에셋코어테크 펀드 운용역이 누구야?", ctx, ["public_funds"]).rejected
    assert gate.check("미래에셋코어테크 펀드 기준가 추이 알려줘", ctx, ["public_funds"]).rejected
    assert not gate.check("미래에셋코어테크 펀드 기준가 알려줘", ctx, ["public_funds"]).rejected        # U14 대조군
    assert not gate.check("변동성이 낮은 공모펀드 알려줘", ctx, ["public_funds"]).rejected
    assert gate.check("KODEX 200 구성종목 변화 알려줘", ctx, ["domestic_etfs"]).rejected
    assert not gate.check("KODEX 200 구성종목 알려줘", ctx, ["domestic_etfs"]).rejected
    assert gate.check("한국전력 채권 신용등급 추이 알려줘", ctx, ["domestic_bonds"]).rejected
    assert not gate.check("한국전력 채권 신용등급 알려줘", ctx, ["domestic_bonds"]).rejected
    assert not gate.check("설정 좌수 알려줘", ctx, []).rejected                                           # 미특정은 불개입
    # 파이프라인 — HCX 0회 · trace 에 ABSENT 근거
    r = answer_question("T-KG027", "미래에셋코어테크 펀드 설정 좌수 알려줘", planner=None, ctx=ctx)
    assert "[Gate] 기각 — 온톨로지 ABSENT" in r.think_trace and "좌수" in r.answer and "좌입니다" not in r.answer
    # ttl 사영
    ttl = open("ontology/fund_pub.ttl", encoding="utf-8").read()
    assert "# ABSENT: fp:PublicFund 에는 fp:hasUnitsOutstanding 없음" in ttl
    assert "fp:hasCreditGradeHistory" in open("ontology/bond_kr.ttl", encoding="utf-8").read()


def test_risk_grade_range_by_table(ctx):
    """KG 1R S6/R16 (KG-013·014) — 공용 상수 0~6 이 펀드 0등급을 허용(NULL 422 ≠ 0)하고 즉답 문구도 "0~6". 일반 규칙: enum 제약은
    테이블별 선언(range_by_table)에서 판정·문구·ttl 제약을 생성한다. 채권 0(미분류 '00')은 답변 가능."""
    from src.runtime import gate
    from src.runtime.pipeline import answer_question

    assert ctx.grade_ranges["public_funds"]["min"] == 1 and ctx.grade_ranges["domestic_bonds"]["min"] == 0
    g = gate.check("위험등급 7등급인 공모펀드 알려줘", ctx, ["public_funds"])
    assert g.rejected and "1(매우 높은 위험)~6(매우 낮은 위험)" in g.answer and "0~6" not in g.answer and "7등급은 없습니다" in g.answer
    g0 = gate.check("위험등급 0등급 공모펀드는 몇 개야?", ctx, ["public_funds"])
    assert g0.rejected and "0등급은 없습니다" in g0.answer and "NULL" in g0.answer
    assert not gate.check("위험등급 0등급 국내채권은 몇 개야?", ctx, ["domestic_bonds"]).rejected        # U25 — 미분류 '00' 답변 가능
    assert gate.check("위험등급 7등급 국내채권 알려줘", ctx, ["domestic_bonds"]).rejected
    assert gate.check("위험등급 0등급 ETF 알려줘", ctx, ["domestic_etfs"]).rejected
    assert not gate.check("위험등급 0등급 상품 알려줘", ctx, []).rejected                                # 미특정 = 합집합 0~6
    assert not gate.check("위험등급 2등급 공모펀드 알려줘", ctx, ["public_funds"]).rejected
    r = answer_question("T-KG014", "위험등급 0등급 공모펀드는 몇 개야?", planner=None, ctx=ctx)
    assert "[Gate] 기각" in r.think_trace and "0등급은 없습니다" in r.answer and "422" not in r.answer
    ttl = open("ontology/fund_pub.ttl", encoding="utf-8").read()
    assert "fp:riskGradeValue_PublicFund rdfs:subPropertyOf fp:riskGradeValue" in ttl and "xsd:minInclusive 1 ] [ xsd:maxInclusive 6" in ttl
    assert "xsd:minInclusive 0 ] [ xsd:maxInclusive 6" in open("ontology/bond_kr.ttl", encoding="utf-8").read()


def test_org_label_slots_ground(ctx):
    """KG 1R S1 — Organization 라벨 슬롯 체계(정식명·영문·구상호·후계·provenance) 와 Ground 정규화 키.
    KG-004 공백 표기 · KG-001 영문(파생 'Asset' 오매칭 제거) · KG-002 구상호→후계 · KG-003 구상호(코드북 밖) · KG-015 alias raw 승격."""
    from src.runtime.pipeline import _ground, ground_notes

    def g(q, tables=("public_funds",)):
        hits, lines = _ground(q, ctx, list(tables))
        return [h.node_id for h in hits], lines

    ids, lines = g("한국 투자 신탁 운용 이 운용하는 공모펀드는 몇 개야?")
    assert ids == ["Org_00040024"] and "'00040024'" in lines[0] and "'00040105'" in lines[0] and "정식명 한국투자신탁운용" in lines[0]
    ids, lines = g("Mirae Asset이 운용하는 공모펀드는 몇 개야?")
    assert ids == ["Org_00080008"] and "Org_fund_" not in " ".join(lines)
    ids, _ = g("Samsung Asset Management가 운용하는 공모펀드는 몇 개야?")
    assert ids == ["Org_00040010"]
    ids, lines = g("프랭클린템플턴이 운용하는 공모펀드 알려줘")
    assert ids[:2] == ["Org_00040022", "Org_00040007"] and "'00040007'" in lines[0] and "우리자산운용" in lines[0]
    assert ground_notes(lines) and "현재 우리자산운용" in ground_notes(lines)[0]
    ids, lines = g("메리츠자산운용이 운용하는 공모펀드는 몇 개야?")
    assert ids == ["Org_00040087"] and "구상호" in lines[0] and "케이씨지아이자산운용" in lines[0]
    ids, lines = g("위험등급이 '높은위험'인 공모펀드는 몇 개야?")
    assert ids == ["RiskGrade_2"] and "'높은위험'" in lines[0] and "'2.0'" in lines[0]
    # 파생(derived) 노드는 매칭 키에서 제외 — 'Asset' 단독 질문도 Org_fund_00080164 로 가지 않는다
    assert ctx.kg_node_by_id["Org_fund_00080164"].provenance == "derived"
    ids, _ = g("Asset 펀드 알려줘")
    assert "Org_fund_00080164" not in ids
    # 회귀 — 합성어(FND-016)·정식명(034)·2코드(R5)·ETF 오염 raw 강등(KG-025)
    ids, lines = g("미래에셋코어테크 펀드 1년 수익률 알려줘")
    assert ids == ["Org_00080008"]
    ids, _ = g("삼성자산운용이 운용하는 공모펀드는 몇 개야?")
    assert ids == ["Org_00040010"]
    ids, lines = g("삼성자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야?", ("public_funds", "domestic_etfs"))
    assert "Org_00040010" in ids and "투자신탁" not in lines[0] and "외 " not in lines[0]
    # 개수 조립기 주어는 정식명, 구상호 주석 병기
    from src.runtime.pipeline import _count_answer
    _, lines = g("한국 투자 신탁 운용 이 운용하는 공모펀드는 몇 개야?")
    a = _count_answer("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE sale_yn='판매중' AND TRIM(or_co_xtn_itt_cd) IN ('00040024','00040105') AND prvo_pbff_desc='공모' LIMIT 30",
                      "펀드수 | 클래스수\n143 | 541", 1, lines)
    assert a.startswith("한국투자신탁운용이 운용하는 공모펀드는 143개(클래스 541개)")
    _, lines2 = g("메리츠자산운용이 운용하는 공모펀드는 몇 개야?")
    a2 = _count_answer("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE sale_yn='판매중' AND TRIM(or_co_xtn_itt_cd) = '00040087' AND prvo_pbff_desc='공모' LIMIT 30",
                       "펀드수 | 클래스수\n27 | 133", 1, lines2)
    assert "케이씨지아이자산운용이 운용하는 공모펀드는 27개" in a2 and "구상호" in a2
    # ttl 사영
    ttl = open("ontology/common.ttl", encoding="utf-8").read()
    assert 'fp:Org_00040007 fp:formerName "프랭클린템플턴투자신탁운용"@ko' in ttl and "fp:Org_00040022 fp:successor fp:Org_00040007" in ttl


def test_country_attr_tags_from_kg(ctx):
    """KG 1R S3/S4 + 3R C — 국가·속성 태그가 KG 개체(token alias)가 됐다. 국가어 사전 상수 제거 · 어떤 태그/컬럼/낱말을 썼든 canon 하나 ·
    희소 태그는 이름 폴백 · '유형' 이면 zrin_ptn_nm · 설정형태 어휘는 token 확정식 · Region_Korea 는 권역 후손 아님."""
    from src.runtime.pipeline import (_ground, ensure_fund_country_tag as ct, ensure_fund_attr_tag as at, _has_name_filter as hnf,
                                      _country_tag_map, ensure_fund_list_grouping)
    con = _ro()
    base = "sale_yn='판매중' AND prvo_pbff_desc='공모'"
    def cnt(where):
        return con.execute(f"SELECT COUNT(*), COUNT(DISTINCT {__import__('src.runtime.pipeline', fromlist=['x'])._FUND_KEY_EXPR}) FROM public_funds WHERE {base} AND {where}").fetchone()
    assert {w for w, _, _ in _country_tag_map()} >= {"중국", "차이나", "대만", "호주", "인도네시아", "인도"}
    # Ground — token alias 확정식 렌더링 · 2자 국가어 · '유형'
    _, lines = _ground("대만에 투자하는 공모펀드 있어?", ctx, ["public_funds"])
    assert lines and "Country_TWN" in lines[0] and "',' || public_funds.prfd_attr_cds || ',' LIKE '%,TWN,%'" in lines[0]
    _, lines = _ground("아시아에 투자하는 공모펀드 중 순자산 큰 5개 알려줘", ctx, ["public_funds"])
    assert "Region_Asia" in lines[0] and "Region_Korea" not in lines[0] and "'국내'" not in lines[0]          # S4 (KG-023)
    # C-1 태그 무관 교정(T4 IND→IDN) + 속성명 절 + 뒤콤마
    t4 = "SELECT itm_no, itm_nm FROM public_funds WHERE prvo_pbff_desc = '공모' AND (prfd_attr_cds LIKE '%IND%' OR zrin_attr_nms LIKE '%인도네시아,%') AND sale_yn = '판매중' LIMIT 30"
    s, ok = ct(t4, "인도네시아에 투자하는 공모펀드 알려줘")
    assert ok and s.count("'%,IDN,%'") == 1 and "IND" not in s.replace("IDN", "") and " OR " not in s
    assert cnt("',' || prfd_attr_cds || ',' LIKE '%,IDN,%'") == (7, 1)
    # S6 — 이름절 OR 소멸 → 135/58 · 목록 묶기 발동
    s6 = "SELECT DISTINCT itm_no, itm_nm, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND (',' || prfd_attr_cds || ',' LIKE '%,IND,%' OR REPLACE(itm_nm,' ','') LIKE '%인도%') AND sale_yn = '판매중' LIMIT 30"
    s, ok = ct(s6, "인도에 투자하는 공모펀드 알려줘")
    assert ok and "itm_nm" not in s.split("WHERE")[1] and s.count("'%,IND,%'") == 1 and not hnf(s)
    assert ensure_fund_list_grouping(s, "인도에 투자하는 공모펀드 알려줘")[1]
    assert cnt("',' || prfd_attr_cds || ',' LIKE '%,IND,%'") == (135, 58)
    # T13 미국 — 이름절(통화 표기 혼입) 제거 → 333/98
    t13 = "SELECT itm_no, itm_nm FROM public_funds WHERE (',' || prfd_attr_cds || ',' LIKE '%,USA,%' OR itm_nm LIKE '%미국%') AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 30"
    s, ok = ct(t13, "미국에 투자하는 공모펀드 알려줘")
    assert ok and "itm_nm LIKE" not in s and cnt("',' || prfd_attr_cds || ',' LIKE '%,USA,%'") == (333, 98)
    # KG-021 대만 — 설립국 컬럼 오용 → 희소 태그라 (TWN OR 이름) 폴백 → 피델리티대만 1행
    k21 = "SELECT itm_no, itm_nm FROM public_funds WHERE prvo_pbff_desc = '공모' AND fd_estb_ctry_cd = 410 AND sale_yn = '판매중' LIMIT 30"
    s, ok = ct(k21, "대만에 투자하는 공모펀드 있어?")
    assert ok and "fd_estb_ctry_cd" not in s and "'%,TWN,%'" in s and "LIKE '%대만%'" in s
    rows = con.execute(s).fetchall()
    assert len(rows) == 1 and "피델리티대만" in rows[0][1]
    # KG-012 — 템플릿 잔재 <CHN> + '유형' → zrin_ptn_nm 등호 → 205/522
    k12 = "SELECT COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' AND zrin_btyp_nm = '해외주식형' AND ',' || prfd_attr_cds || ',' LIKE '%,<CHN>,%' AND sale_yn = '판매중' LIMIT 30"
    s, ok = ct(k12, "해외주식형 중에서 중국주식 유형인 공모펀드는 몇 개야?")
    assert ok and "zrin_ptn_nm = '중국주식'" in s and "CHN" not in s
    assert cnt("zrin_btyp_nm = '해외주식형' AND zrin_ptn_nm = '중국주식'") == (522, 205)
    # 대조군 — 이미 정식형(R3 중국 560/248)은 무변경
    r3 = "SELECT itm_no FROM public_funds WHERE prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,CHN,%' AND sale_yn = '판매중' LIMIT 30"
    assert ct(r3, "중국에 투자하는 공모펀드 알려줘") == (r3, False)
    # R11 — 설정형태 token 확정식 (KG-017 폐쇄 3/6 · KG-018 단위∧개방 31/189)
    k17 = "SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND han_clas_policies LIKE '%폐쇄형%' LIMIT 30"
    s, ok = at(k17, "폐쇄형 공모펀드는 몇 개야?")
    assert ok and "han_clas_policies" not in s and "'%,C104,%'" in s and cnt("',' || prfd_attr_cds || ',' LIKE '%,C104,%'") == (6, 3)
    k18 = "SELECT DISTINCT zrin_btyp_nm, itm_no FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND zrin_btyp_nm IS NOT NULL LIMIT 30"
    s, ok = at(k18, "단위형이면서 개방형인 공모펀드도 있어?")
    assert ok and "'%,C102,%'" in s and "'%,C103,%'" in s and not at(s, "단위형이면서 개방형인 공모펀드도 있어?")[1]
    assert cnt("',' || prfd_attr_cds || ',' LIKE '%,C102,%' AND ',' || prfd_attr_cds || ',' LIKE '%,C103,%'") == (189, 31)
    _, lines = _ground("폐쇄형 공모펀드는 몇 개야?", ctx, ["public_funds"])
    assert any("FundAttr_C104" in ln for ln in lines)
    # C-3 — OR 묶인 이름절은 개별 조회가 아니다
    assert not hnf("SELECT itm_nm FROM public_funds WHERE (or_attr_desc LIKE '%주식%' OR itm_nm LIKE '%배당%') LIMIT 30")
    assert hnf("SELECT itm_nm FROM public_funds WHERE itm_nm LIKE '%코어테크%' AND sale_yn='판매중' LIMIT 30")
    assert hnf("SELECT itm_nm FROM public_funds WHERE (REPLACE(itm_nm,' ','') LIKE '%코어%' OR REPLACE(itm_nm,' ','') LIKE '%테크%') LIMIT 30")


def test_sql_precheck_generalized(ctx):
    """KG 1R R3 — 리터럴·구조 검증 일반화: 코드 컬럼 리터럴 실존(KG-003 'A011' · KG-004 80000000 · KG-025 IN('삼성','삼성KODEX')) ·
    템플릿 잔재(KG-012 <CHN>) · 비-SQLite TOP(KG-028) · 라우팅 대상 밖 테이블(KG-028). 전부 실행 전 기각 → 재생성 사유."""
    from src.runtime.pipeline import _sql_precheck as pc, validate_sql, answer_question

    k = "SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(or_co_xtn_itt_cd) = 'A011' AND prvo_pbff_desc = '공모') LIMIT 30"
    assert "A011" in (pc(k, ctx, ["public_funds"], False) or "") and "없는 코드" in pc(k, ctx, ["public_funds"], False)
    k4 = "SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = 80000000 AND prvo_pbff_desc = '공모' LIMIT 30"
    assert "따옴표 없는 숫자" in pc(k4, ctx, ["public_funds"], False)
    k25 = "SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('삼성', '삼성KODEX') AND prvo_pbff_desc = '공모' LIMIT 30"
    assert "'삼성'" in pc(k25, ctx, ["public_funds", "domestic_etfs"], False)
    ok = "SELECT COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040010', '00040024') AND sale_yn='판매중' LIMIT 30"
    assert pc(ok, ctx, ["public_funds"], False) is None
    assert pc("SELECT COUNT(*) FROM public_funds WHERE trim(trusc_xtn_itt_cd) = '0016022' LIMIT 1", ctx, ["public_funds"], False) is None   # 7자리 raw 도 실재
    assert "템플릿 자리표시자 <CHN>" in validate_sql("SELECT COUNT(*) FROM public_funds WHERE ',' || prfd_attr_cds || ',' LIKE '%,<CHN>,%' LIMIT 30")
    assert "TOP" in validate_sql("SELECT TOP 1 pd_nm FROM domestic_etfs LIMIT 30")
    k28 = "SELECT constituent, weight_pct FROM domestic_etfs JOIN ext_etf_holdings ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no WHERE domestic_etfs.pd_abrv_nm LIKE '%코어테크%' ORDER BY weight_pct DESC LIMIT 30"
    assert "밖 테이블 사용: domestic_etfs" in pc(k28, ctx, ["public_funds"], False)
    # KG 2R N1 — 교차 판정이어도 허용 집합은 라우터 마스터 + 짝 ext 뿐(KG-028 ETF 종목 환각) · 라우팅 일치는 통과
    assert "밖 테이블 사용" in pc(k28, ctx, ["public_funds"], True) and pc(k28, ctx, ["domestic_etfs"], False) is None
    # 통합 — KG-004 형(날조 코드)이 "0개" 단언으로 나가지 않는다 (1차 기각 → 재생성 → 재기각 → 유보)
    class P:
        def plan_sql(self, q, g):
            return k4

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-KG004", "XYZ자산운용이 운용하는 공모펀드는 몇 개야?", planner=P(), ctx=ctx)
    assert "0개" not in r.answer and "[Guard] SQL 기각" in r.think_trace and "따옴표 없는 숫자" in r.think_trace


def test_count_answer_subject_all_roles():
    """KG 1R R1 (KG-011) — 주어에 Ground 의 모든 기관(운용/수탁)을 역할과 함께 · 0 이면 센 조건을 굽는다."""
    from src.runtime.pipeline import _count_answer as f

    g = ["'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035'",
         "'국민은행' → Org_trustee_00020004 (Organization) → public_funds.trusc_xtn_itt_cd='00020004'"]
    sql = ("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' "
           "AND TRIM(trusc_xtn_itt_cd) = '00020004' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30")
    a = f(sql, "펀드수 | 클래스수\n0 | 0", 1, g)
    assert a.startswith("KB자산운용이 운용하고 국민은행이 수탁하는 공모펀드는 0개(클래스 0개)") and "교집합이 0" in a
    assert "129" not in a and "역외" not in a


def test_r3_name_resolution_A(ctx):
    """3R 부류 A — 이름 등호 → 공백무시 LIKE(T7) · Fund 접두 절단 라벨은 코드 핀 생략 + 결합 토큰(T12) · 라우터 '투자신탁' · 되묻기 후보 itm_nm."""
    from src.runtime.pipeline import (ensure_spaceless_name_match as sp, _ground, residual_name_token, answer_question,
                                      _suggest_similar_products)

    t7 = "SELECT fd_yr1_ern_r, itm_nm FROM public_funds WHERE itm_nm = '삼성코리아대표증권자투자신탁' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30"
    s, ok = sp(t7)
    assert ok and "REPLACE(itm_nm,' ','') LIKE '%삼성코리아대표증권자투자신탁%'" in s and " = '삼성" not in s
    assert sp("SELECT 1 FROM public_funds p WHERE TRIM(p.itm_nm) = '피델리티 인도네시아 펀드' LIMIT 1")[0].count("REPLACE(p.itm_nm,' ','') LIKE '%피델리티인도네시아펀드%'") == 1

    class P:
        sql = t7

        def plan_sql(self, q, g):
            return P.sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-T7", "삼성코리아대표증권자투자신탁 1년 수익률 알려줘", planner=P(), ctx=ctx)
    assert "머리명사 투자신탁" in r.think_trace and "[Answer] 개별 조회 답변 기계 조립" in r.think_trace
    assert "106.71%~109.72%" in r.answer and "클래스 9개" in r.answer and "(A)" not in r.answer
    # T12 — 접두 절단 Fund 라벨 → 코드 핀 생략 · 결합 토큰
    q12 = "NH-Amundi 1.5배레버리지인덱스 펀드 1년 수익률 알려줘"
    _, lines = _ground(q12, ctx, ["public_funds"])
    assert lines and "rptt_ksd_itm_no=" not in " ".join(lines) and "접두 절단 라벨" in lines[0]
    assert residual_name_token(q12, lines) == "NH-Amundi1.5배레버리지인덱스"
    P.sql = "SELECT fd_yr1_ern_r, itm_nm FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30"
    r12 = answer_question("T-T12", q12, planner=P(), ctx=ctx)
    assert "254.16%~257.14%" in r12.answer and "클래스 5개" in r12.answer and r12.answer.count("\n- ") == 1
    # R6 2호(호수 분기 흡수) 그대로 7클래스
    P.sql = _R6_SQL
    r6 = answer_question("T-R6b", "미래에셋차이나솔로몬증권투자신탁 2호 위험등급 알려줘", planner=P(), ctx=ctx)
    assert "클래스 7개" in r6.answer
    # A-4 — 펀드 되묻기 후보
    assert _suggest_similar_products("SELECT 1 FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋 코어테크%' LIMIT 1")


def test_r3_manager_scope_and_amount_B(ctx):
    """3R 부류 B — 컬럼 동의어는 라우팅 어휘 아님(B-1) · 원 단위 금액 숨김+억원(B-4) · 집계 head 에 식별 컬럼 미주입."""
    from src.runtime.pipeline import _hide_answer_columns as hide, ensure_fund_evidence_columns as ev

    assert "순자산" not in ctx.route_vocab["domestic_etfs"] and "순자산" not in ctx.route_vocab["public_funds"]
    out, hidden = hide("itm_nm | fd_nast_suma | 순자산_억원\nA | 145347201786.0 | 1453억원")
    assert "fd_nast_suma" in hidden and "145347201786" not in out and "1453억원" in out
    s, ok = ev("SELECT SUM(fd_nast_suma) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040010' AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 1")
    assert ok and '"순자산합계_억원"' in s and "itm_nm" not in s
    row = _ro().execute(s).fetchone()
    assert row[1] == "331098억원"


def test_r3_name_mode_D(ctx):
    """3R 부류 D (T11) — '이름이 들어간' 질의는 이름 모드: Org 코드 핀 생략 → itm_nm LIKE → 154/301 + 운용사 코드별 분해(역외 포함)."""
    from src.runtime.pipeline import _ground, residual_name_token, answer_question

    q = "피델리티 이름이 들어간 공모펀드는 몇 개야?"
    _, lines = _ground(q, ctx, ["public_funds"])
    assert lines and "이름 모드" in lines[0] and "or_co_xtn_itt_cd=" not in lines[0] and residual_name_token(q, lines) == "피델리티"

    class P:
        def plan_sql(self, q, g):
            return "SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30"

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-T11", q, planner=P(), ctx=ctx)
    assert "'피델리티' 이름이 들어간 공모펀드는 154개(클래스 301개)" in r.answer and "00130001 47개(역외)" in r.answer
    assert "별도 법인" not in r.answer                                   # 이름 모드는 역외가 이미 포함 — 병기 문장 없음


# ── 4R (docs/recheck_2026-09-02_round4.md §③) · KG 2R (docs/kg_structure_probe_round2_2026-09-02.md §④) ──
_T6_SQL = ("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
           "AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]3호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]3[([]*') LIMIT 5")
_T14_SQL = ("SELECT itm_no, itm_nm, fd_nast_suma FROM public_funds WHERE (TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') "
            "AND ',' || prfd_attr_cds || ',' LIKE '%,VNM,%' AND REPLACE(itm_nm,' ','') LIKE '%베트남그로스%') AND sale_yn = '판매중' "
            "AND prvo_pbff_desc = '공모' AND fd_nast_suma IS NOT NULL LIMIT 30")


def test_r4_country_name_component_I(ctx):
    """4R 부류 I — Country 개체는 독립 낱말일 때만(S4 'KB차이나'·T14 '베트남그로스'·V15 'NH-Amundi 인도네시아 포커스' 회귀).
    경계 = 이름 문자 전체, 상품명 성분(DB 부분열)이면 매핑 생략 + 이름 토큰, 국가 가드도 같은 판정, 통칭은 테이블 범위."""
    from src.runtime.pipeline import _ground, residual_name_token, _boundary_hit, ensure_fund_country_tag as ct, answer_question

    def g(q):
        hits, lines = _ground(q, ctx, ["public_funds"])
        return [h.node_id for h in hits], lines, residual_name_token(q, lines)

    ids, lines, tok = g("KB차이나 펀드 위험등급 알려줘")
    assert not [i for i in ids if i.startswith("Country_")] and tok == "KB차이나"
    ids, lines, tok = g("한국투자베트남그로스 펀드 순자산 알려줘")
    assert ids == ["Org_00040024"] and tok == "베트남그로스"
    ids, lines, tok = g("NH-Amundi 인도네시아 포커스 펀드 순자산 알려줘")
    assert "Country_IDN" not in ids and tok == "인도네시아포커스" and any("상품명 성분" in ln for ln in lines)
    assert g("인도네시아에 투자하는 공모펀드 알려줘")[0] == ["Country_IDN"] and g("미국에 투자하는 공모펀드는 몇 개야?")[0] == ["Country_USA"]
    assert _boundary_hit("차이나", "KB차이나") is False and _boundary_hit("차이나", "차이나에 투자") is True
    assert _boundary_hit("기아", "기아자동차") is False and _boundary_hit("기아", "기아를 담은") is True
    s = "SELECT 1 FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%KB차이나%' LIMIT 1"
    assert ct(s, "KB차이나 펀드 위험등급 알려줘") == (s, False)
    assert ct(_T14_SQL, "한국투자베트남그로스 펀드 순자산 알려줘") == (_T14_SQL, False)
    # T14 통합 — 국가 태그 절이 이름절을 지우지 않고 개별 조회 묶기(SUM·4펀드)로 복귀
    class P:
        sql = _T14_SQL

        def plan_sql(self, q, g):
            return P.sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-T14", "한국투자베트남그로스 펀드 순자산 알려줘", planner=P(), ctx=ctx)
    assert "[Answer] 개별 조회 답변 기계 조립" in r.think_trace and "순자산" in r.answer and "억원 (클래스 합계)" in r.answer
    # S4 통합 — HCX 가 국가 태그로 바꿔 쓴 SQL 도 이름 토큰이 강제되어 KB차이나 4펀드
    P.sql = ("SELECT DISTINCT zrin_fd_ivst_risk_grd_nm, itm_no, TRIM(itm_nm) AS itm_nm, zrin_fd_ivst_risk_gcd FROM public_funds "
             "WHERE ',' || prfd_attr_cds || ',' LIKE '%,CHN,%' AND zrin_fd_ivst_risk_gcd IS NOT NULL LIMIT 30")
    r4 = answer_question("T-S4", "KB차이나 펀드 위험등급 알려줘", planner=P(), ctx=ctx)
    assert "itm_nm LIKE '%KB차이나%'" in r4.sql.replace("REPLACE(itm_nm,' ','') LIKE", "itm_nm LIKE") and r4.answer.count("\n- ") == 4 and "DB차이나" not in r4.answer


def test_r4_skip_pin_token_J_K_L(ctx):
    """4R 부류 J·K·L — 코드 핀 생략 분기는 항상 이름 검색 토큰(T6 호수 → 8클래스) · 다중 토큰 LIKE 접기(R6) ·
    Ground 0 이어도 상품 고유명 후보(T8·T7 형) · 내부 지시문(⚙)은 답에 노출되지 않고 ℹ(구상호)만 병기."""
    from src.runtime.pipeline import (_ground, residual_name_token, ensure_spaceless_name_match as sp, answer_question,
                                      _standalone_name_token as st, ground_notes, _count_answer)

    q6 = "미래에셋차이나솔로몬증권투자신탁 3호는 클래스가 몇 개야?"
    _, lines = _ground(q6, ctx, ["public_funds"])
    assert residual_name_token(q6, lines) == "미래에셋차이나솔로몬증권투자신탁" and "⚙" in lines[0] and "rptt_ksd_itm_no=" not in lines[0]
    assert ground_notes(lines) == []                                          # L: 지시문은 답변 주석이 아니다

    class P:
        sql = _T6_SQL

        def plan_sql(self, q, g):
            return P.sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-T6", q6, planner=P(), ctx=ctx)
    assert "LIKE '%미래에셋차이나솔로몬증권투자신탁%'" in r.sql and "8" in r.retrieved_context.splitlines()[1]
    # J-2 — 4토큰 AND → 1토큰
    s4 = ("SELECT itm_no FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋%' AND REPLACE(itm_nm,' ','') LIKE '%차이나%' "
          "AND REPLACE(itm_nm,' ','') LIKE '%솔로몬%' AND REPLACE(itm_nm,' ','') LIKE '%증권투자신탁%' AND REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2호*' LIMIT 30")
    s, ok = sp(s4, "미래에셋차이나솔로몬증권투자신탁")
    assert ok and s.count("LIKE '%") == 1 and "'%미래에셋차이나솔로몬증권투자신탁%'" in s and "1=1" not in s
    assert len(_ro().execute(s).fetchall()) == 7
    # K-1 — 독립 후보
    assert st("KB차이나 펀드 위험등급 알려줘") == "KB차이나" and st("삼성코리아대표증권자투자신탁 1년 수익률 알려줘") == "삼성코리아대표증권자투자신탁"
    assert st("삼성 펀드 보수 알려줘") is None and st("공모펀드는 유형별로 몇 개씩 있어?") is None and st("한국투자신탁운용이 운용하는 공모펀드는 몇 개야?") is None
    # K-2 — 이름 모드 주어는 질문 + SQL 리터럴 (V11 '삼성' 은 Ground 0)
    a = _count_answer("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%삼성%' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30",
                      "펀드수 | 클래스수\n229 | 962", 1, [], "삼성 이름이 들어간 공모펀드는 몇 개야?")
    assert a.startswith("'삼성' 이름이 들어간 공모펀드는 229개(클래스 962개)") and "운용사 코드별" in a


def test_kg2r_table_scope_and_name_pin_N1_N2_M(ctx):
    """KG 2R N1·N2 + 4R M — 교차 플래그여도 허용 = 라우터 마스터 + 짝 ext(KG-028 ETF 종목 환각) · 이름 리터럴이 토큰을 포함하지 않으면
    토큰 치환(T8 'KB차이나'→'KB차이나그로스' · KG-034 '코어텍') · 코드 핀 개별 조회도 묶기(V4)."""
    from src.runtime.pipeline import _sql_precheck as pc, ensure_fund_name_filter as nf, ensure_fund_lookup_grouping as lg, _has_fund_key_pin, answer_question

    k28 = ("SELECT domestic_etfs.pd_abrv_nm, ext_etf_holdings.weight_pct FROM domestic_etfs JOIN ext_etf_holdings "
           "ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no WHERE domestic_etfs.pd_nm LIKE '%코어테크%' ORDER BY 2 DESC LIMIT 1")
    assert "domestic_etfs" in (pc(k28, ctx, ["public_funds"], True) or "")                 # cross=True 여도 기각
    ok28 = ("SELECT h.holding_nm, h.weight_pct FROM ext_fund_holdings h WHERE h.itm_no IN (SELECT p.itm_no FROM public_funds p "
            "WHERE REPLACE(p.itm_nm,' ','') LIKE '%코어테크%') ORDER BY h.weight_pct DESC LIMIT 3")
    assert pc(ok28, ctx, ["public_funds"], True) is None                                    # 짝 ext 는 허용
    assert pc("SELECT pd_nm FROM domestic_etfs LIMIT 5", ctx, ["domestic_etfs", "public_funds"], True) is None
    # N2
    s = "SELECT 1 FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%KB차이나%' LIMIT 30"
    out, ok = nf(s, "KB차이나그로스")
    assert ok and "'%KB차이나그로스%'" in out and out.count("LIKE") == 1
    out2, ok2 = nf("SELECT 1 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어텍%' LIMIT 30", "코어테크")
    assert ok2 and "'%코어테크%'" in out2
    assert not nf("SELECT 1 FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%KB차이나그로스증권자투자신탁%' LIMIT 30", "KB차이나그로스")[1]   # 더 긴 정식명 존중
    # M — 코드 핀 개별 조회(V4)
    v4 = ("SELECT zrin_fd_ivst_risk_grd_nm, itm_no, TRIM(itm_nm) AS itm_nm, zrin_fd_ivst_risk_gcd FROM public_funds "
          "WHERE TRIM(rptt_ksd_itm_no) IN ('030230002D36') AND zrin_fd_ivst_risk_grd_nm IS NOT NULL LIMIT 1")
    assert _has_fund_key_pin(v4) and lg(v4, "KB중국본토A주증권자투자신탁 위험등급 알려줘")[1]

    class P:
        def plan_sql(self, q, g):
            return v4

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-V4", "KB중국본토A주증권자투자신탁 위험등급 알려줘", planner=P(), ctx=ctx)
    assert "KB중국본토A주증권자투자신탁(주식): 위험등급 2등급(높은 위험) · 클래스 14개(전부 판매중)" in r.answer


def test_attr_tag_all_axes_N4(ctx):
    """KG 2R N4 (KG-024 회귀) — FundAttribute 전 축 token canon · 테마/섹터 축은 이름 병기 · 동일 라벨 노드 병합 · wrap 없는 태그 절 교정."""
    from src.runtime.pipeline import ensure_fund_attr_tag as at, _attr_word_map, _FUND_KEY_EXPR

    m = {w: (codes, nu) for w, codes, nu, _ in _attr_word_map()}
    assert m["반도체"] == (("N144",), True) and set(m["럭셔리"][0]) == {"N118", "N147"} and m["개방형"] == (("C103",), False)
    k24 = ("SELECT COUNT(*) FROM public_funds WHERE prfd_attr_cds LIKE '%,N144,%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30")
    s, ok = at(k24, "반도체 테마 공모펀드는 몇 개야?")
    assert ok and "(',' || prfd_attr_cds || ',' LIKE '%,N144,%' OR REPLACE(itm_nm,' ','') LIKE '%반도체%')" in s and s.count("N144") == 1
    assert not at(s, "반도체 테마 공모펀드는 몇 개야?")[1]
    cnt = _ro().execute(s.replace("COUNT(*)", f"COUNT(*), COUNT(DISTINCT {_FUND_KEY_EXPR})")).fetchone()
    assert cnt == (78, 12)                                                       # gold 12/78 (태그 ∪ 이름)
    # 기준선 HCX 형(이름 OR 속성명)도 같은 canon 으로 접힌다
    k24b = "SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모' AND (REPLACE(itm_nm,' ','') LIKE '%반도체%' OR zrin_attr_nms LIKE '%반도체%')) LIMIT 30"
    s2, ok2 = at(k24b, "반도체 테마 공모펀드는 몇 개야?")
    assert ok2 and "'%,N144,%'" in s2 and "zrin_attr_nms" not in s2
    # 비발동 — 라벨이 낱말 안에 붙은 경우('고배당' 의 '배당주' 아님) · 설정형태 통칭은 종전대로
    assert not at("SELECT 1 FROM public_funds LIMIT 1", "KB고배당주 펀드 알려줘")[1]
    assert "'%,C104,%'" in at("SELECT COUNT(*) FROM public_funds WHERE sale_yn='판매중' LIMIT 30", "폐쇄형 공모펀드는 몇 개야?")[0]


def test_amount_eok_common_B4(ctx):
    """4R B-4 확장 (V7) — 원 단위 집계의 HCX 별칭(total_aum)·ETF 도메인도 억원 병기 + 원값 숨김. 펀드 순자산 경로는 종전 이름(순자산_억원) 유지."""
    from src.runtime.pipeline import ensure_amount_eok_columns as f, _hide_answer_columns as hide, ensure_fund_evidence_columns as ev, _execute, _list_answer

    v7 = "SELECT cu_fund_mgmt_co, SUM(du_last_aum) as total_aum FROM domestic_etfs GROUP BY cu_fund_mgmt_co ORDER BY total_aum DESC LIMIT 3"
    s, ok = f(v7)
    assert ok and '"total_aum_억원"' in s and not f(s)[1]
    rows, n = _execute(s)
    hidden_rows, hidden = hide(rows, s)
    assert n == 3 and "total_aum" in hidden and "억원" in hidden_rows.splitlines()[1] and "967341" not in hidden_rows
    # 펀드 — 종전 이름·값 그대로(순자산_억원 1453억원 · 순자산합계_억원 331098억원)
    r3 = ev("SELECT itm_no, TRIM(itm_nm), fd_nast_suma FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' ORDER BY 3 DESC LIMIT 5")[0]
    assert r3.count('"순자산_억원"') == 1
    s2 = ev("SELECT SUM(fd_nast_suma) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040010' AND sale_yn='판매중' AND prvo_pbff_desc='공모' LIMIT 1")[0]
    assert _ro().execute(s2).fetchone()[1] == "331098억원"
    assert not f("SELECT pd_nm FROM domestic_bonds LIMIT 5")[1]


# ── 6R (docs/recheck_2026-09-02_round6_plan.md) ──
def test_r6_N_standalone_token_product_keys():
    """6R 부류 N — 라우터 머리명사(오타 '펌드' 포함)는 고유명 후보가 아니다: 일반어 제거 사전 = _GENERIC_NAME_TOKEN ∪ PRODUCT 키."""
    from src.runtime.pipeline import _standalone_name_token as st

    assert st("공모펌드 중 1년 수익률이 가장 높은 3개 알려줘") is None
    assert st("1년 수익률이 가장 높은 공모펌드 5개 알려줘") is None
    assert st("삼성코리아대표증권자투자신탁 1년 수익률 알려줘") == "삼성코리아대표증권자투자신탁"
    assert st("KB차이나그로스 펀드 위험등급 알려줘") == "KB차이나그로스"
    assert st("코어테크 펌드 1년 수익률 알려줘") == "코어테크"


def test_r6_F1_label_conflict_excluded(ctx):
    """6R F1 (KG-023·025·026·X8·X9·X15·X16 회귀) — Region/AssetClass/Country 라벨·상품군 명사와 같은 FundAttribute 라벨('ETF'·'중국'·'국내')은
    빌더가 provenance=label_conflict 로 사영하고 런타임은 매칭 키·속성 확정식에서 뺀다. 정상 라벨(반도체·폐쇄형)은 불변."""
    from src.runtime.pipeline import _ground, _attr_word_map

    conflicts = {n.node_id: n.label_ko for n in ctx.kg_nodes if n.node_type == "FundAttribute" and n.provenance == "label_conflict"}
    assert conflicts and "FundAttr_M113" in conflicts and any(v == "국내" for v in conflicts.values()) and any(v == "아시아" for v in conflicts.values())
    assert "ETF" not in {w for w, *_ in _attr_word_map()} and "아시아" not in {w for w, *_ in _attr_word_map()}
    ids = [h.node_id for h in _ground("ETF에 투자하는 공모펀드는 몇 개야?", ctx, ["public_funds"])[0]]
    assert "FundAttr_M113" not in ids
    ids = [h.node_id for h in _ground("중국에 투자하는 공모펀드와 국내 ETF는 각각 몇 개야?", ctx, ["public_funds", "domestic_etfs"])[0]]
    assert not [i for i in ids if i.startswith("FundAttr_")] and ("Country_CHN" in ids or "Region_China" in ids)
    ids = [h.node_id for h in _ground("아시아에 투자하는 공모펀드 중 순자산 큰 5개 알려줘", ctx, ["public_funds"])[0]]
    assert ids == ["Region_Asia"]
    assert "FundAttr_N144" in [h.node_id for h in _ground("반도체 테마 공모펀드는 몇 개야?", ctx, ["public_funds"])[0]]
    assert "FundAttr_C104" in [h.node_id for h in _ground("폐쇄형 공모펀드는 몇 개야?", ctx, ["public_funds"])[0]]


def test_r6_F2_class_dependent_range(ctx):
    """6R F2 (X25) — 클래스별로 값이 다른 컬럼(기준가 bns_bpr)은 단일 MAX 로 대표명에 붙이지 않고 MIN~MAX 범위 + '클래스에 따라 다름'.
    종속 여부는 DB 실측(다클래스 펀드에서 값이 갈리는 비율). 수익률 경로(R4)는 불변."""
    from src.runtime.pipeline import _class_dependent_cols, ensure_fund_lookup_grouping as lg, answer_question

    dep = _class_dependent_cols()
    assert "bns_bpr" in dep and "fd_nast_suma" not in dep
    x25 = ("SELECT bns_bpr, itm_nm FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' "
           "AND sale_yn = '판매중' LIMIT 30")
    s, ok = lg(x25, "미래에셋코어테크 펀드 기준가 알려줘")
    assert ok and '"bns_bpr_최고"' in s and '"bns_bpr_최저"' in s and "MAX(bns_bpr) AS bns_bpr" not in s
    lo, hi = _ro().execute("SELECT MIN(bns_bpr), MAX(bns_bpr) FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '미래에셋코어테크증권자투자신탁%' AND sale_yn='판매중'").fetchone()

    class P:
        def plan_sql(self, q, g):
            return x25

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-X25", "미래에셋코어테크 펀드 기준가 알려줘", planner=P(), ctx=ctx)
    first = [ln for ln in r.answer.splitlines() if ln.startswith("- 미래에셋코어테크증권자투자신탁(주식):")][0]
    assert f"{lo:,.2f}".rstrip("0").rstrip(".") in first and f"{hi:,.2f}".rstrip("0").rstrip(".") in first and "클래스에 따라 다름" in first and "종류" not in first
    assert "매매기준가" in first


def test_r6_Iprime_Jprime(ctx):
    """6R I′·J′ (W2·W3·W6) — 경계·성분 판정은 원문 기준(앞 라벨 소비가 뒤 경계를 만들지 않음) · 라벨을 품은 낱말 전체가 토큰 ·
    이름 토큰 개별 조회엔 Country 태그 불탑재 · 체인 끝 이름 토큰 사후조건."""
    from src.runtime.pipeline import _ground, residual_name_token, ensure_fund_country_tag as ct, answer_question

    def g(q):
        hits, lines = _ground(q, ctx, ["public_funds"])
        return [h.node_id for h in hits], lines

    ids, lines = g("미래에셋베트남 펀드 순자산 알려줘")
    assert "Country_VNM" not in ids and ids == ["Org_00080008"]
    ids, lines = g("피델리티재팬 펀드 1년 수익률 알려줘")
    assert "Country_JPN" not in ids and ids == ["Org_00080029"]
    assert g("베트남에 투자하는 공모펀드 알려줘")[0] == ["Country_VNM"]
    ids, _ = g("미래에셋이 운용하는 베트남 펀드 알려줘")
    assert "Country_VNM" in ids and "Org_00080008" in ids
    s = "SELECT itm_nm FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%베트남%' AND prfd_attr_cds LIKE '%VNM%' LIMIT 30"
    s2, ok2 = ct(s, "미래에셋베트남 펀드 순자산 알려줘", "베트남")                  # 이름 토큰 개별 조회 — 태그 절 제거(주입 없음)
    assert ok2 and "prfd_attr_cds" not in s2 and "'%베트남%'" in s2
    assert ct(s, "베트남에 투자하는 공모펀드 알려줘")[1]                                   # 목록 질의는 종전대로

    class P:
        sql = ("SELECT fd_yr1_ern_r, itm_no, TRIM(itm_nm) AS itm_nm, prfd_attr_cds FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080029' "
               "AND prfd_attr_cds LIKE '%JPN%' AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r > -100 LIMIT 1")

        def plan_sql(self, q, g):
            return P.sql

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r3 = answer_question("T-W3", "피델리티재팬 펀드 1년 수익률 알려줘", planner=P(), ctx=ctx)
    assert "[Answer] 개별 조회 답변 기계 조립" in r3.think_trace and "JPN" not in r3.sql and "'%피델리티재팬%'" in r3.sql
    assert "34.36%~36.28%" in r3.answer and "클래스 13개" in r3.answer and "판매완료" in r3.answer   # 14클래스 = 판매중 13 + 판매완료 1(별도 대표번호)
    # J′ — W6: 이름+4호 결합 LIKE 를 호수 가드가 제거해도 토큰이 체인 끝에서 복원
    P.sql = ("SELECT zrin_fd_ivst_risk_grd_nm, itm_nm FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
             "AND REPLACE(itm_nm,' ','') LIKE '%미래에셋디스커버리증권투자신탁4호%' LIMIT 30")
    r6 = answer_question("T-W6", "미래에셋디스커버리증권투자신탁 4호 위험등급 알려줘", planner=P(), ctx=ctx)
    assert "LIKE '%미래에셋디스커버리증권투자신탁%'" in r6.sql and "4호*'" in r6.sql      # 호수 가드가 이름 리터럴을 보존(사후조건은 벨트)
    assert "[Answer] 개별 조회 답변 기계 조립" in r6.think_trace and "위험등급 2등급" in r6.answer and "클래스 2개" in r6.answer


def test_r6_F4_zero_row_three_ways(ctx):
    """6R F4 (KG-012·X16·X3) — 0행 문구 세 갈래: (c) 식별 실패(오타 '코어택' → 가까운 표기) · (b) 기본모수 밖(태그는 있으나 판매중·공모 0) · (a) 교집합 0.
    국가 확정식 ⓐ의 LIKE 구멍(fd_ivst_rgn_desc LIKE '%중국%') 과 precheck 의 LIKE 리터럴 값사전 대조."""
    from src.runtime.pipeline import _zero_row_reason, ensure_fund_country_tag as ct, answer_question, _count_answer

    x3 = ("SELECT itm_nm FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어택%' "
          "AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30")
    r = _zero_row_reason(x3)
    assert "「코어택」" in r and "식별하지 못했" in r and "코어테크" in r and "실재" not in r
    b = ("SELECT COUNT(DISTINCT x) AS 펀드수, COUNT(*) AS 클래스수 FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
         "AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 30")
    rb = _zero_row_reason(b)
    assert "판매중·공모 기준 0개" in rb and "클래스가 있습니다" in rb
    a2 = _count_answer(b, "펀드수 | 클래스수\n0 | 0", 1, [])
    assert "판매중·공모 기준 0개" in a2 and "실재" not in a2
    a = _zero_row_reason("SELECT itm_nm FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' AND TRIM(trusc_xtn_itt_cd) = '00020004' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30")
    assert "교집합이 0" in a
    # KG-012 — LIKE 구멍: 확정식 ⓐ + 값사전 LIKE 대조
    k12 = "SELECT COUNT(*) FROM public_funds WHERE zrin_btyp_nm = '해외주식형' AND fd_ivst_rgn_desc LIKE '%중국%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30"
    s, ok = ct(k12, "해외주식형 중에서 중국주식 유형인 공모펀드는 몇 개야?")
    assert ok and "zrin_ptn_nm = '중국주식'" in s and "fd_ivst_rgn_desc" not in s
    viol = guard.check_values(k12, ctx)
    assert viol and any("중국" in str(v) for v in viol)
    assert not guard.check_values("SELECT 1 FROM public_funds WHERE zrin_btyp_nm LIKE '%주식%' LIMIT 1", ctx)      # 값의 부분열은 통과
    # 파이프라인 — X3 오타는 (c) 문구로 (0개 단정 없음)
    class P:
        def plan_sql(self, q, g):
            return x3

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r3 = answer_question("T-X3", "미래에셋 코어택 펀드 순자산 알려줘", planner=P(), ctx=ctx)
    assert "식별하지 못했" in r3.answer and "자체가 없습니다" not in r3.answer


def test_r6_O_numeric_clause_rerun(ctx):
    """6R O (5R S2) — 질문에 없는 숫자의 수치 비교 절(`fd_yr3_ern_r < -100`)이 단독 0행이면 그 절만 떼고 1회 재실행.
    질문의 숫자를 쓴 절·단독으로 행이 있는 절·서브쿼리는 손대지 않는다(조건 완화 금지)."""
    from src.runtime.pipeline import drop_unquestioned_numeric_clause as drop, answer_question

    s2 = ("SELECT itm_nm, fd_yr3_ern_r FROM public_funds WHERE fd_yr3_ern_r < -100 AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
          "ORDER BY fd_yr3_ern_r ASC LIMIT 5")
    out, dropped = drop(s2, "3년 수익률이 가장 낮은 공모펀드 5개 알려줘")
    assert dropped == "fd_yr3_ern_r < -100" and "-100" not in out and "sale_yn = '판매중'" in out
    # 질문의 숫자(10) 를 쓴 절 → 불개입 · 단독으로 행이 있는 절 → 불개입
    assert drop(s2.replace("< -100", "> 10"), "3년 수익률 10% 이상인 펀드")[1] is None
    assert drop(s2.replace("< -100", "< 0"), "3년 수익률이 마이너스인 펀드")[1] is None
    assert drop("SELECT 1 FROM public_funds WHERE fd_yr3_ern_r < -100 AND itm_no IN (SELECT itm_no FROM ext_fund_page) LIMIT 1", "x")[1] is None

    class P:
        def plan_sql(self, q, g):
            return s2

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-S2", "3년 수익률이 가장 낮은 공모펀드 5개 알려줘", planner=P(), ctx=ctx)
    assert "-100" not in r.sql and "수치 절 폐기" in r.think_trace and "확인되지 않습니다" not in r.answer


def test_r6_P_template_simple_predicates(ctx):
    """6R P (5R V5) — 운용사 템플릿 부가 절은 단순 술어만(윈도우·집계·서브쿼리 절은 폐기·기록) · precheck 가 WHERE 의 윈도우·집계를 기각
    (서브쿼리 안 집계는 합법) · 실행 오류도 재생성 1회 경로."""
    from src.runtime.pipeline import ensure_fund_manager_ranking as mgr, where_window_or_aggregate as wwa, answer_question

    v5 = ("SELECT mtco_nm, COUNT(*) AS n FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' "
          "AND zrin_btyp_nm = '해외주식형' AND RANK() OVER (ORDER BY fd_nast_suma DESC) <= 5 GROUP BY mtco_nm ORDER BY n DESC LIMIT 5")
    notes = []
    out, ok = mgr(v5, "해외주식형 펀드를 가장 많이 운용하는 운용사 5곳", notes)
    assert ok and "OVER" not in out and "zrin_btyp_nm = '해외주식형'" in out and notes and "부가 절 폐기" in notes[0]
    assert wwa(v5) and "RANK(" in wwa(v5)
    assert wwa("SELECT 1 FROM public_funds WHERE fd_nast_suma > 1 AND COUNT(*) > 3 LIMIT 1")
    assert wwa("SELECT 1 FROM public_funds WHERE itm_no IN (SELECT itm_no FROM public_funds GROUP BY itm_no HAVING COUNT(*) > 1) LIMIT 1") is None
    assert wwa("WITH r AS (SELECT itm_nm, RANK() OVER (ORDER BY fd_nast_suma DESC) rk FROM public_funds WHERE sale_yn = '판매중') SELECT * FROM r WHERE rk <= 5 LIMIT 5") is None

    # 실행 오류 → 재생성 1회: 1차 SQL 은 precheck 를 통과하나 실행이 죽는(윈도우를 HAVING 에) 문장, 2차는 정상
    calls = []

    class P:
        def plan_sql(self, q, g):
            calls.append(g)
            if len(calls) == 1:
                return "SELECT itm_nm FROM public_funds WHERE sale_yn = '판매중' GROUP BY itm_nm HAVING RANK() OVER (ORDER BY MAX(fd_nast_suma)) <= 3 LIMIT 3"
            return "SELECT itm_nm, fd_nast_suma FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' ORDER BY fd_nast_suma DESC LIMIT 3"

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-V5", "순자산 상위 펀드 3개", planner=P(), ctx=ctx)
    assert len(calls) == 2 and "실행 오류" in calls[1] and "실행 실패" in r.think_trace and "오류가 발생해" not in r.answer


def test_r6_F3_holdings_join_template(ctx):
    """6R F3 (KG-028·KG-034·X1·X2) — 개별 펀드의 구성종목 질의: public_funds 단독 SQL 을 ext_fund_holdings JOIN 확정식으로 교체
    (대표 클래스 1개 · 비중순). 트리거 없는 질의·펀드 미지정·이미 holdings 를 쓴 SQL 은 불개입. precheck 는 테이블 범위를 컬럼 검사 앞에."""
    from src.runtime.pipeline import ensure_fund_holdings_template as ht, _sql_precheck as pc, answer_question

    base = ("SELECT itm_nm FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%IBK중소형주코리아%' AND sale_yn = '판매중' "
            "AND prvo_pbff_desc = '공모' LIMIT 3")
    out, ok = ht(base, "IBK중소형주코리아 펀드가 가장 많이 보유한 종목 3개 알려줘", ctx)
    assert ok and "FROM ext_fund_holdings h" in out and "h2.grp = p.mtco_itm_no" in out and "LIKE '%IBK중소형주코리아%'" in out and "LIMIT 3" in out
    assert ht(base, "IBK중소형주코리아 펀드 순자산 알려줘", ctx)[1] is False
    assert ht("SELECT itm_nm FROM public_funds WHERE zrin_btyp_nm = '주식형' LIMIT 3", "주식형 펀드가 보유한 종목", ctx)[1] is False
    assert ht(out, "IBK중소형주코리아 펀드가 보유한 종목", ctx)[1] is False
    # precheck 순서 — 펀드 질의가 ETF 구성종목 테이블로 새면 '없는 컬럼' 이 아니라 '테이블 범위' 사유
    err = pc("SELECT e.pd_nm, h.constituent FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no "
             "WHERE h.constituent LIKE '%삼성전자%' LIMIT 3", ctx, ["public_funds"], False)
    assert err and err.startswith("라우팅 대상")

    class P:
        def plan_sql(self, q, g):
            return base

        def compose_answer(self, q, rows, answer_rules=""):
            return "x"

    r = answer_question("T-F3", "IBK중소형주코리아 펀드가 가장 많이 보유한 종목 3개 알려줘", planner=P(), ctx=ctx)
    assert "ext_fund_holdings" in r.sql and "구성종목 확정식" in r.think_trace
    assert "종목명" in r.retrieved_context and len(r.retrieved_context.splitlines()) == 4


def test_r6_F6_base_population_strict_and_join_count():
    """6R F6 (X10·KG-005·KG-035·X19) — 기본모수 판정은 단독 절: OR IS NULL·IN(판매완료)·<> 를 확정식으로 교체(다른 컬럼과 섞인 절·모수 확장 질의는 불개입)
    · 펀드단위 COUNT 치환이 LEFT JOIN ext_* 경로에서도 별칭 한정 키로 동작."""
    from src.runtime.pipeline import ensure_fund_base_population as bp, ensure_fund_distinct_count as dc

    q = "해외주식형 공모펀드는 몇 개야?"
    x10 = "SELECT COUNT(*) FROM public_funds WHERE zrin_btyp_nm = '해외주식형' AND (sale_yn = '판매중' OR sale_yn IS NULL) AND prvo_pbff_desc IN ('공모','사모') LIMIT 30"
    out, ok = bp(x10, q)
    assert ok and "sale_yn = '판매중'" in out and "IS NULL" not in out and "prvo_pbff_desc = '공모'" in out and "'사모'" not in out
    assert "zrin_btyp_nm = '해외주식형'" in out
    out2, ok2 = bp("SELECT COUNT(*) FROM public_funds p WHERE p.sale_yn <> '판매완료' AND p.prvo_pbff_desc = '공모' LIMIT 30", q)
    assert ok2 and "p.sale_yn = '판매중'" in out2 and "<>" not in out2
    # 이미 확정식 → 불개입 · 모수 확장 질의 → 불개입 · 다른 컬럼과 섞인 절 → 불개입
    assert bp("SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30", q)[1] is False
    assert bp(x10, "해외주식형 펀드는 판매완료 포함해서 몇 개야?")[1] is False
    mixed = "SELECT COUNT(*) FROM public_funds WHERE (sale_yn = '판매중' OR zrin_btyp_nm = '주식형') AND prvo_pbff_desc = '공모' LIMIT 30"
    assert "zrin_btyp_nm = '주식형'" in bp(mixed, q)[0]
    # JOIN 경로 펀드단위 COUNT
    x19 = ("SELECT COUNT(*) FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no "
           "WHERE p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모' AND e.estb_dt < 20100101 LIMIT 30")
    out3, ok3 = dc(x19, "2010년 이전에 설정된 공모펀드는 몇 개야?")
    assert ok3 and "COUNT(DISTINCT printf('%08d', CAST(p.or_co_xtn_itt_cd" in out3 and "p.mtco_itm_no" in out3 and ", p.itm_no)" in out3
    assert dc("SELECT COUNT(*) FROM public_funds p JOIN domestic_etfs d ON d.pd_itm_no = p.itm_no LIMIT 1", "펀드 몇 개")[1] is False
