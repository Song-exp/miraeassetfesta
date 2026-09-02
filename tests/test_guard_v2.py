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
    assert s.count("',' || prfd_attr_cds || ',' LIKE '%,CHN,%'") == 2
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
    assert ok and "GLOB '*[^0-9]2호*'" in s and "IN (" not in s
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
    assert (rows[0][3], rows[0][4]) == (189.77, 187.09)            # 최고·최저 — 1클래스(188.83)만 답하던 것의 재료
    # R6 — 등급명만 SELECT → 묶기 + 근거컬럼 가드의 역방향 gcd 병기. 🔴 이 펀드는 클래스마다 mtco_itm_no 가
    #    달라(531101~531107) 정본 펀드키로는 6행이다 — 값은 전 행 '높은 위험'·2 로 같고 클래스수 합이 7.
    s6, ok6 = f(_R6_SQL, "미래에셋차이나솔로몬증권투자신탁 2호 위험등급 알려줘")
    assert ok6 and "MAX(zrin_fd_ivst_risk_grd_nm) AS zrin_fd_ivst_risk_grd_nm" in s6 and "LIMIT 1" not in s6
    s6, ok6b = ev(s6)
    assert ok6b and "zrin_fd_ivst_risk_gcd" in s6
    rows6 = con.execute(s6).fetchall()
    assert rows6 and all(r[3] == "높은 위험" and r[4] == 2 for r in rows6) and sum(r[2] for r in rows6) == 7
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
    assert ok2 and "zrin_fd_ivst_risk_grd_nm" in s2 and s2.count("zrin_fd_ivst_risk_gcd") == 1


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
    """R3 경로 통합 — 목록 묶기 · 내부 코드 숨김 · 커버리지 병기 · 이름 교정이 한 번에 발동한다 (HCX 0회)."""
    from src.runtime.pipeline import answer_question

    class P:
        def plan_sql(self, q, g):
            return _R3_SQL

        def compose_answer(self, q, rows, answer_rules=""):
            self.rows = rows
            return "* KB중국본토A주증권자투자신닥[주식]A 등이 있습니다."

    p = P()
    r = answer_question("T-R3", "중국에 투자하는 공모펀드 알려줘", planner=p, ctx=ctx)
    assert "[Guard] 목록 펀드 묶기" in r.think_trace and "[Answer] 내부 코드 컬럼 숨김 — prfd_attr_cds" in r.think_trace
    assert "[Answer] 커버리지 병기 — LIMIT 도달, 전체 560행 / 248펀드" in r.think_trace
    assert p.rows.startswith("(조회 결과: 전체 560행 / 248펀드 중 30펀드 표시") and "prfd_attr_cds" not in p.rows
    assert "prfd_attr_cds" in r.retrieved_context                    # 조회 원문은 그대로
    assert "[Guard] 상품명 전사 교정" in r.think_trace and "신닥" not in r.answer and "KB중국본토A주증권자투자신탁[주식]A" in r.answer
    # LIMIT 미도달이면 종전 머리줄 그대로
    P.plan_sql = lambda self, q, g: _R3_SQL.replace("LIMIT 30", "LIMIT 5")
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
