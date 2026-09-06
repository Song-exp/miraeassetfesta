# -*- coding: utf-8 -*-
"""라운드 33 — 서버 QA r1 심사관 §③(가) 부류 BA~BP 회귀 (간섭 지도 docs/bonds_2026-09-06_round1_plan.md).

부류별 섹션 · 발동/불개입 짝. 입력은 서버 think_trace 의 SQL 원문(eval/probe_bonds_2026-09-06_r1.json)이고,
가드 함수를 직접 호출해 결과 SQL 과 DB 실행 값을 검사한다.
"""
import pytest

from src.runtime import guard, loader
from src.runtime import pipeline as pl

T = ["domestic_bonds"]


@pytest.fixture(scope="module")
def ctx():
    return loader.load_context()


@pytest.fixture(scope="module")
def con():
    c = loader.connect_readonly()
    yield c
    c.close()


def _one(con, sql):
    return con.execute(sql).fetchone()


# ══════════════════════════════════════════════════════════════════════════════
# BL — 창 확정 가드의 슬롯 마커 사각 (UT-094 · D-025)
#   일반 규칙: `_WHERE_BODY` 를 읽는 가드는 `/*M:…*/` 마커를 먼저 벗긴다 — 마커는 컬럼이 아니다. 마커는 LIMIT 앞뿐 아니라 절 사이에도 온다.
# ══════════════════════════════════════════════════════════════════════════════
UT094_Q = "2024년에 발행된 회사채 평균 표면금리 얼마야?"
UT094_SQL = ("SELECT AVG(srfc_irt) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 "
             "AND (TRIM(std_pd_mcls_nm) = '회사채' AND isu_dt > 20240101 AND isu_dt < 20240901) /*M:BONDPOP*/ LIMIT 30")


def test_BL_window_marker_before_limit(con):
    out, note = pl.enforce_relative_window(UT094_SQL, UT094_Q)
    assert note and "isu_dt BETWEEN 20240101 AND 20241231" in out
    assert "/*M:BONDPOP*/" in out and "mat_dt >= 20260824" in out              # 마커·구매가능 하한 보존
    n, avg = _one(con, out.replace("SELECT AVG(srfc_irt)", "SELECT COUNT(DISTINCT pd_no), AVG(srfc_irt)"))
    assert n == 2672 and round(avg, 3) == 3.651                                   # gold UT-094


def test_BL_window_marker_mid_where():
    q = "만기까지 들고 갈 건데, 3년 안에 만기되는 안전한 채권 몇 개만 골라줘"
    sql = ("SELECT pd_no FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND (curr_cd = 'KRW' AND pd_risk_gcd = '16' "
           "AND mat_dt BETWEEN 20260101 AND 20291231) /*M:BONDPOP*/ AND applied_yield > 0 AND bd_ofr_tcd <> '사모' LIMIT 30")
    out, note = pl.enforce_relative_window(sql, q)
    assert note and "mat_dt BETWEEN 20260824 AND 20290824" in out and "20291231" not in out
    assert out.count("/*M:BONDPOP*/") == 1 and "applied_yield > 0" in out and "bd_ofr_tcd <> '사모'" in out


def test_BL_window_without_marker_unchanged_behaviour():
    sql = UT094_SQL.replace(" /*M:BONDPOP*/", "")
    out, note = pl.enforce_relative_window(sql, UT094_Q)
    assert note and "isu_dt BETWEEN 20240101 AND 20241231" in out and "/*M:" not in out


def test_BL_effective_window_with_marker():
    sql = ("SELECT pd_no FROM domestic_bonds WHERE curr_cd = 'KRW' AND pd_risk_gcd = '16' AND mat_dt BETWEEN 20260824 AND 20290824 "
           "/*M:BONDPOP*/ AND applied_yield > 0 LIMIT 30")
    assert pl._effective_mat_window(sql) == "2026-08-24~2029-08-24"
    assert pl._effective_mat_window(sql.replace("/*M:BONDPOP*/ ", "")) == "2026-08-24~2029-08-24"


def test_BL_threshold_with_marker():
    q = "A등급 이상 회사채 중 표면금리 5% 넘는 채권 몇 종목이야?"
    sql = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND "
           "(TRIM(std_pd_mcls_nm) = '회사채' AND srfc_irt >= 5) /*M:BONDPOP*/ LIMIT 30")
    out, fixed = pl.align_threshold_operator(sql, q)
    assert fixed and "srfc_irt > 5" in out and out.count("/*M:BONDPOP*/") == 1 and "LIMIT 30" in out


def test_BL_split_slot_markers_helper():
    body, marks = pl._split_slot_markers(" a = 1 /*M:BONDPOP*/ AND b = 2 /*M:SPECGRADE*/ ")
    assert body == "a = 1 AND b = 2" and marks == " /*M:BONDPOP*/ /*M:SPECGRADE*/"
    assert pl._split_slot_markers("a = 1") == ("a = 1", "")


# ══════════════════════════════════════════════════════════════════════════════
# BA — 값-컬럼 교정 뒤 종류 확정식 재적용 (A-043 · D-027)
#   일반 규칙: 리터럴 '국고채' 등호는 컬럼 불문 국고채 확정식으로 치환하고, 이미 있는 확정식은 가려서(멱등) 중첩하지 않는다.
#   F1(fix_value_column) 채택 뒤 ensure_ktb_kind·ensure_kind_filter 를 한 번 더 돈다.
# ══════════════════════════════════════════════════════════════════════════════
A043_Q = "국공채 중 국고채만 몇 종목이야?"
A043_FIXED = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND "
              "(TRIM(std_pd_scls_nm) = '국고채' OR (COALESCE(TRIM(bd_knd),'') = '국고채권' AND TRIM(std_pd_scls_nm) = '국고채')) /*M:BONDPOP*/ LIMIT 30")
D027_Q = "28년 12월까지 만기가 돌아오는 국고채 알려줘"
D027_RAW = ("SELECT DISTINCT pd_no, pd_nm, mat_dt FROM domestic_bonds WHERE mat_dt BETWEEN 20260824 AND 20281231 AND "
            "(std_pd_mcls_nm = '국고채' OR (COALESCE(std_pd_mcls_nm, '') = '')) LIMIT 30")


def test_BA_scls_eq_any_column_to_ktb(con):
    out, fixed = pl.ensure_ktb_kind(A043_FIXED, A043_Q)                       # OR 가지에 '국고채권' 이 있어도 ④ 가 돈다
    assert fixed and "= '국고채'" not in out.replace(pl._KTB_FILTER, "") and _one(con, out)[0] == 295
    out2, fixed2 = pl.ensure_ktb_kind(D027_RAW, D027_Q)                        # 대분류 컬럼에 쓴 '국고채' 도 확정식
    assert fixed2 and pl._KTB_FILTER in out2
    assert _one(con, out2.replace("SELECT DISTINCT pd_no, pd_nm, mat_dt", "SELECT COUNT(DISTINCT pd_no)").replace("LIMIT 30", ""))[0] == 49


def test_BA_idempotent_when_filter_present():
    sql = f"SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd='KRW' AND {pl._KTB_FILTER} LIMIT 30"
    assert pl.ensure_ktb_kind(sql, "국고채는 총 몇 종목이야?") == (sql, False)
    loose = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND "
             "(TRIM(bd_knd) ='국고채권' OR (COALESCE(TRIM(bd_knd),'')='' AND TRIM(std_pd_scls_nm)= '국고채')) /*M:BONDPOP*/ LIMIT 30")
    assert pl.ensure_ktb_kind(loose, "국고채는 총 몇 종목이야?") == (loose, False)   # 공백만 다른 확정식도 원문 그대로(D-029 ✅ SQL 불변)
    once, _ = pl.ensure_ktb_kind(A043_FIXED, A043_Q)
    assert pl.ensure_ktb_kind(once, A043_Q) == (once, False)


@pytest.mark.parametrize("q, sql", [
    ("국고채를 포함해서 국공채는 전부 몇 종목이야?", "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='국공채' LIMIT 30"),
    ("은행채는 몇 종목이나 있어?", "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(bd_knd) IN ('일반은행채','특수은행채') LIMIT 30"),
])
def test_BA_gov_head_untouched(q, sql):
    assert pl.ensure_ktb_kind(sql, q) == (sql, False)


def test_BA_refix_after_value_column(ctx, con):
    """F1 채택 뒤 종류 가드를 다시 돈 결과가 A-043 → 295 · D-027 → 49 (answer_question 분기와 같은 순서로 재현)."""
    raw = A043_FIXED.replace("TRIM(std_pd_scls_nm) = '국고채' OR", "TRIM(std_pd_mcls_nm) = '국고채' OR")
    viol = guard.check_values(raw, ctx)
    fixed_sql, fixed = pl.fix_value_column(raw, viol)
    assert fixed and guard.check_values(fixed_sql, ctx) == []
    assert _one(con, fixed_sql)[0] == 290                                       # 재적용 전 — 물가연동 5종목 누락
    refixed, again = pl.ensure_ktb_kind(fixed_sql, A043_Q)
    refixed, _ = pl.ensure_kind_filter(refixed, A043_Q)
    assert again and _one(con, refixed)[0] == 295


# ══════════════════════════════════════════════════════════════════════════════
# BB — 종류 확정식 정합: 과확장·모순 (A-008 · S-010)
#   일반 규칙: 질문의 종류 확정식이 하나(F)이면, 종류·이름·발행사 컬럼만으로 된 WHERE 최상위 절의 종류 리터럴이 F 밖으로 새거나
#   이름·발행사 OR 가지가 붙어 있으면 그 절을 F 로 교체. F 안의 값만 있는 좁힘(IN 둘 이상)은 ① 좁힘 복원의 몫 — 불개입.
# ══════════════════════════════════════════════════════════════════════════════
A008_Q = "통안채 몇 개 있어?"
A008_SQL = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND "
            "(TRIM(bd_knd) IN ('통화안정채권','MBS','유동화회사채') OR pd_pbcm LIKE '%유동화%' OR pd_nm LIKE '%유동화%' "
            "OR pd_nm LIKE '%신용보증%' OR pd_nm LIKE '%기술보증%') /*M:BONDPOP*/ LIMIT 30")
S010_Q = "망하지 않을 회사가 발행한 채권만 골라줘"
S010_SQL = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, MAX(applied_yield) AS applied_yield FROM domestic_bonds WHERE "
            "(TRIM(std_pd_mcls_nm)='국공채' OR COALESCE(TRIM(pd_pbcm),'')='한국은행' OR pd_nm LIKE '%(정부보증)%') AND curr_cd = 'KRW' "
            "AND mat_dt >= 20260824 AND applied_yield > 0 GROUP BY pd_no ORDER BY MAX(applied_yield) DESC LIMIT 5")


def test_BB_overexpanded_in_list_replaced(con):
    out, note = pl.restore_kind_breadth(A008_SQL, A008_Q)
    assert note and "TRIM(bd_knd)='통화안정채권'" in out and "MBS" not in out and "LIKE" not in out
    assert out.count("/*M:BONDPOP*/") == 1 and _one(con, out)[0] == 33                  # gold BND-A-008


def test_BB_contradicting_mcls_replaced(con):
    out, note = pl.restore_kind_breadth(S010_SQL, S010_Q)
    assert note and "TRIM(std_pd_mcls_nm)='회사채'" in out and "국공채" not in out and "한국은행" not in out
    assert "applied_yield > 0" in out and "ORDER BY MAX(applied_yield) DESC LIMIT 5" in out
    rows = con.execute(out).fetchall()
    assert rows and all("지역개발" not in r[1] and "도시철도" not in r[1] for r in rows)


@pytest.mark.parametrize("q, sql", [
    # 종류 낱말 둘(국고채·국공채) — 불개입
    ("국고채를 포함해서 국공채는 전부 몇 종목이야?", "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE (std_pd_mcls_nm='국공채' OR pd_nm LIKE '%국고채%') LIMIT 30"),
    # 국고채는 ensure_ktb_kind 의 몫
    ("국고채는 총 몇 종목이야?", "SELECT COUNT(*) FROM domestic_bonds WHERE TRIM(pd_pbcm) = '한국은행' AND TRIM(bd_knd) = '국고채권' LIMIT 30"),
    # F 안의 값으로 좁힘(IN 둘) — ① 의 몫, 불개입
    ("회사채 수익률 높은 순", "SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) IN ('일반회사채','할부금융채') LIMIT 5"),
    # 발행사 이름이 질문에 있는 절 — 사용자 조건
    ("삼성전자라는 회사가 발행한 채권 있어?", "SELECT pd_no FROM domestic_bonds WHERE pd_pbcm LIKE '%삼성전자%' LIMIT 30"),
    # 배제 낱말
    ("회사채 말고 은행채 보여줘", "SELECT pd_no FROM domestic_bonds WHERE TRIM(bd_knd)='일반회사채' LIMIT 30"),
    # 부정 연산 절(BR-P09 꼴) — 불개입
    ("A등급 이상 회사채 중 표면금리 높은 순으로 5개 알려줘", "SELECT pd_no FROM domestic_bonds WHERE (std_pd_mcls_nm = '회사채' AND TRIM(crd_grd) IN ('AAA','AA+') AND bd_knd NOT IN ('할인채', '단리채')) LIMIT 5"),
])
def test_BB_untouched_two_kinds_and_friends(q, sql):
    assert pl.restore_kind_breadth(sql, q) == (sql, None)


def test_BB_untouched_structure_predicate():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) IN ('특수은행채','일반은행채','금융지주회사채') AND pd_risk_gcd IN ('11','12','13') LIMIT 30"
    assert pl.restore_kind_breadth(sql, "코코본드 알려줘") == (sql, None)               # 종류 낱말 없음 → F 비어 있음


def test_BB_untouched_backstop():
    sql = ("SELECT pd_no FROM domestic_bonds WHERE (TRIM(std_pd_mcls_nm)='국공채' OR COALESCE(TRIM(pd_pbcm),'')='한국은행' "
           "OR pd_nm LIKE '%(정부보증)%' OR TRIM(pd_pbcm) IN ('한국주택금융공사','한국토지주택공사')) LIMIT 30")
    assert pl.restore_kind_breadth(sql, "정부가 보증하는 채권 알려줘") == (sql, None)     # '정부 보증' 은 종류 낱말이 아니다(D-014)


def test_BB_name_branch_of_kind_word_is_overexpansion():
    sql = "SELECT pd_nm FROM domestic_bonds WHERE (TRIM(std_pd_mcls_nm)='회사채' OR pd_nm LIKE '%회사채%') LIMIT 5"
    out, note = pl.restore_kind_breadth(sql, "회사채 알려줘")
    assert note and "LIKE" not in out and "TRIM(std_pd_mcls_nm)='회사채'" in out


# ══════════════════════════════════════════════════════════════════════════════
# BI — 비최상급 '안전한' = IN ('15','16') · 6등급 없는 종류의 최상급 안전 질의에 위험 절이 없으면 폴백 주입 (D-025 · S-010)
# ══════════════════════════════════════════════════════════════════════════════
def test_BI_plain_safe_is_15_16(con):
    q = "만기까지 들고 갈 건데, 3년 안에 만기되는 안전한 채권 몇 개만 골라줘"
    sql = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd = 'KRW' AND pd_risk_gcd = '16' "
           "AND mat_dt BETWEEN 20260824 AND 20290824 LIMIT 30")
    out, fixed = pl.ensure_top_safety(sql, q)
    assert fixed and "pd_risk_gcd IN ('15','16')" in out and "= '16'" not in out
    # 위험 절이 없는 추천 질의엔 주입 · 이미 15·16 이면 불개입 · 사실확인(추천 신호 없음)엔 주입하지 않음 · 등급 숫자 명시는 사용자 조건
    out2, fixed2 = pl.ensure_top_safety("SELECT pd_no FROM domestic_bonds WHERE curr_cd='KRW' ORDER BY applied_yield DESC LIMIT 5", q)
    assert fixed2 and out2.index("IN ('15','16')") < out2.index("ORDER BY")
    assert not pl.ensure_top_safety(out, q)[1]
    assert not pl.ensure_top_safety("SELECT COUNT(*) FROM domestic_bonds WHERE curr_cd='KRW' LIMIT 1", "채권은 안전한 투자야?")[1]
    assert not pl.ensure_top_safety("SELECT pd_no FROM domestic_bonds WHERE pd_risk_gcd = '14' LIMIT 5", "4등급 정도로 안전한 채권")[1]
    # 최상급은 종전대로 '16' 단독
    assert "pd_risk_gcd = '16'" in pl.ensure_top_safety("SELECT pd_no FROM domestic_bonds WHERE pd_risk_gcd IN ('15','16') LIMIT 5", "가장 안전한 채권 5개 추천해줘")[0]


def test_BI_kind_without_safe_grade_injects_fallback(con):
    sql = "SELECT pd_no, TRIM(pd_nm) FROM domestic_bonds WHERE TRIM(std_pd_mcls_nm)='회사채' AND curr_cd='KRW' AND mat_dt >= 20260824 ORDER BY applied_yield DESC LIMIT 5"
    out, fixed = pl.ensure_top_safety(sql, S010_Q)
    assert fixed and "pd_risk_gcd IN ('15','16')" in out and out.index("IN ('15','16')") < out.index("ORDER BY")
    assert con.execute(out).fetchall()
    # BB → BI 를 이은 S-010 전체 경로 — 회사채 5등급만 남는다
    step1, _ = pl.restore_kind_breadth(S010_SQL, S010_Q)
    step2, _ = pl.ensure_top_safety(step1, S010_Q)
    grades = {r[0] for r in con.execute(step2.replace("SELECT pd_no, TRIM(pd_nm) AS pd_nm, MAX(applied_yield) AS applied_yield", "SELECT DISTINCT pd_risk_gcd"))}
    assert grades == {"15"}


# ══════════════════════════════════════════════════════════════════════════════
# BD — HCX 구문 결함 기계 교정(재생성 전) (D-037 · D-045 · D-010 · S-004)
#   일반 규칙: ① IN 목록 안 TRIM('x') → 'x'(여분 `)` 함께) ② 따옴표 불균형 LIKE 조각의 OR 가지 제거 / AND 절이면 닫기
#   ③ 스키마 밖 컬럼이 GROUP BY/ORDER BY 항에만 있으면 그 항 제거. 조건절에 쓰였으면 불개입.
# ══════════════════════════════════════════════════════════════════════════════
D037_RAW = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, crd_grd, mat_dt FROM domestic_bonds WHERE std_pd_mcls_nm = '회사채' AND crd_grd IN TRIM('AA'), TRIM('AA+') "
            "AND mat_dt BETWEEN 20270101 AND 20271231 GROUP BY pd_no LIMIT 30")
D045_RAW = ("SELECT pd_no, TRIM(pd_nm), MAX(srfc_irt) AS srfc_irt , crd_grd, mat_dt FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND "
            "(TRIM(std_pd_mcls_nm) = '회사채' AND TRIM(crd_grd) IN ('AAA', 'AA+', 'AA0', 'AA-', 'A+', 'A0', 'A-'), TRIM('AA'), TRIM('AAA')) "
            "AND srfc_irt IS NOT NULL AND srfc_irt > 0) AND pd_risk_gcd <> '11' GROUP BY pd_no ORDER BY MAX(srfc_irt) DESC LIMIT 5")
D010_RAW = "SELECT pd_nm, pd_abrv_nm FROM domestic_bonds WHERE (pd_nm LIKE '%코코본드%' OR pd_nm LIKE '%/코/%) GROUP BY pd_no LIMIT 30"
S004_RAW = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, MAX(applied_yield) AS applied_yield, pd_risk_gcd, pd_risk_nm, TRIM(crd_grd) AS crd_grd FROM domestic_bonds "
            "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND pd_risk_gcd IN ('15','16') AND std_pd_mcls_nm = '회사채' AND applied_yield > 0 "
            "GROUP BY pd_no, mtco_itm_no ORDER BY MAX(applied_yield) DESC, pd_no ASC LIMIT 3")


def test_BD_in_trim_literals(ctx, con):
    out, fixed = pl.fix_sql_syntax_slips(D037_RAW)
    assert fixed and "crd_grd IN ('AA', 'AA+')" in out and "TRIM('AA')" not in out
    assert pl._sql_precheck(out, ctx, T, False, question="") is None                 # 문법 통과
    out2, _ = pl.expand_grade_comparison(out, "내년에 만기가 되는 회사채 중 신용등급이 AA 이상인 것을 알려줘")
    assert "IN ('AAA', 'AA+', 'AA0', 'AA-')" in out2 and guard.check_values(out2, ctx) == []   # 'AA' 오기는 서열 확장이 받는다


def test_BD_trailing_trim_and_paren(ctx, con):
    out, fixed = pl.fix_sql_syntax_slips(D045_RAW)
    assert fixed and "TRIM('AA')" not in out and out.count("(") == out.count(")")
    assert "srfc_irt > 0) AND pd_risk_gcd" in out and pl._sql_precheck(out, ctx, T, False, question="") is None
    out2, _ = pl.expand_grade_comparison(out, "표면금리가 높은 순으로 A등급 이상 회사채 5종목 알려줘")
    assert guard.check_values(out2, ctx) == [] and len(con.execute(out2).fetchall()) == 5   # gold D-045 5행


def test_BD_unbalanced_like_branch(ctx):
    out, fixed = pl.fix_sql_syntax_slips(D010_RAW)
    assert fixed and "'%/코/%" not in out and "pd_nm LIKE '%코코본드%'" in out and "GROUP BY pd_no LIMIT 30" in out
    assert pl._sql_precheck(out, ctx, T, False, question="") is None
    # AND 자리면 가지를 떼지 않고 따옴표를 닫는다
    out2, fixed2 = pl.fix_sql_syntax_slips("SELECT pd_nm FROM domestic_bonds WHERE pd_nm LIKE '%코코본드%' AND pd_nm LIKE '%/코/% GROUP BY pd_no LIMIT 30")
    assert fixed2 and "pd_nm LIKE '%/코/%' GROUP BY" in out2


@pytest.mark.parametrize("sql", [
    "SELECT pd_nm FROM domestic_bonds WHERE TRIM(crd_grd) IN ('AAA', 'AA+') AND pd_nm LIKE '%코코%' LIMIT 30",          # 정상
    "SELECT pd_nm FROM domestic_bonds WHERE pd_nm LIKE '%it''s%' LIMIT 30",                                             # 이스케이프 따옴표
    "SELECT pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm) = '(주)한국은행' AND crd_grd IN ('AAA') LIMIT 30",              # 리터럴 안 괄호
])
def test_BD_syntax_slips_untouched(sql):
    assert pl.fix_sql_syntax_slips(sql) == (sql, [])


def test_BD_group_by_unknown_column(ctx, con):
    err = pl._sql_precheck(S004_RAW, ctx, T, False, question="")
    assert err and "스키마에 없는 컬럼" in err
    out, dropped = pl.drop_unknown_select_columns(S004_RAW, err)
    assert dropped == ["GROUP BY mtco_itm_no"] and "GROUP BY pd_no ORDER BY" in out and "mtco_itm_no" not in out
    assert pl._sql_precheck(out, ctx, T, False, question="") is None
    rows = con.execute(out).fetchall()
    assert len(rows) == 3 and all(r[3] == "15" for r in rows)                          # gold S-004: 회사채 5등급 3종
    # WHERE 에 쓰인 없는 컬럼은 불개입(조건이 바뀐다)
    bad = "SELECT pd_no FROM domestic_bonds WHERE mtco_itm_no = 'x' GROUP BY pd_no, mtco_itm_no LIMIT 3"
    assert pl.drop_unknown_select_columns(bad, "스키마에 없는 컬럼: mtco_itm_no(→ public_funds 컬럼이다)") == (bad, [])


def test_BD_siblings_other_column_and_order_by(ctx):
    """형제 케이스 — 다른 컬럼·값(bd_knd IN TRIM(...)) · ORDER BY 항의 없는 컬럼 · 채권 밖 테이블은 불개입."""
    out, fixed = pl.fix_sql_syntax_slips("SELECT pd_nm FROM domestic_bonds WHERE bd_knd IN TRIM('일반회사채'), TRIM('할부금융채') AND curr_cd = 'KRW' LIMIT 30")
    assert fixed and "bd_knd IN ('일반회사채', '할부금융채') AND curr_cd" in out and pl._sql_precheck(out, ctx, T, False, question="") is None
    etf = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_risk_nm IN TRIM('6등급'), TRIM('5등급') LIMIT 30"
    assert pl.fix_sql_syntax_slips(etf) == (etf, [])                                     # 채권 전용 — ETF 경로 불변
    sql = "SELECT pd_no, TRIM(pd_nm) AS pd_nm FROM domestic_bonds WHERE curr_cd = 'KRW' ORDER BY mtco_itm_no ASC, pd_no ASC LIMIT 5"
    err = pl._sql_precheck(sql, ctx, T, False, question="")
    out2, dropped = pl.drop_unknown_select_columns(sql, err)
    assert dropped == ["ORDER BY mtco_itm_no ASC"] and "ORDER BY pd_no ASC LIMIT 5" in out2
    assert pl._sql_precheck(out2, ctx, T, False, question="") is None


# ══════════════════════════════════════════════════════════════════════════════
# BE — 구조 낱말 확정식 강제 (D-010)
#   일반 규칙: 구조 낱말(_STRUCT_ALIASES 키)이 질문에 하나 있고 WHERE 에 그 판정식(선언 구조표시 CASE)이 없으면 AND 주입 + 구조 낱말 조각의 pd_nm LIKE 절 제거.
# ══════════════════════════════════════════════════════════════════════════════
COCO_PRED = "TRIM(bd_knd) IN ('특수은행채','일반은행채','금융지주회사채')"


def test_BE_coco_predicate_injected(con):
    sql = "SELECT pd_nm, pd_abrv_nm, pd_pbcm, bd_knd, pd_risk_gcd, pd_risk_nm FROM domestic_bonds WHERE (pd_nm LIKE '%코코본드%' ) GROUP BY pd_no LIMIT 30"
    out, fixed = pl.ensure_kind_filter(sql, "코코본드 알려줘")
    assert fixed and COCO_PRED in out and "pd_risk_gcd IN ('11','12','13')" in out and "코코본드%" not in out
    n = _one(con, out.replace("SELECT pd_nm, pd_abrv_nm, pd_pbcm, bd_knd, pd_risk_gcd, pd_risk_nm", "SELECT COUNT(DISTINCT pd_no)").replace("GROUP BY pd_no LIMIT 30", ""))[0]
    assert n == 223                                                                     # 판정식 = 선언(gold D-010 CASE 첫 WHEN)
    # 형제: 동의어 '조건부자본증권' · WHERE 없는 SQL
    out2, fixed2 = pl.ensure_kind_filter("SELECT pd_nm FROM domestic_bonds LIMIT 30", "조건부자본증권 알려줘")
    assert fixed2 and "WHERE (" in out2 and COCO_PRED in out2 and out2.rstrip().endswith("LIMIT 30")


def test_BE_sibling_structures(ctx):
    # 전환사채: 라벨 조각('전환') LIKE 는 걷고 GLOB CB 판정식으로 · 후순위: 발행사 조건은 남기고 판정식만 AND
    out, fixed = pl.ensure_kind_filter("SELECT pd_nm FROM domestic_bonds WHERE pd_nm LIKE '%전환%' GROUP BY pd_no LIMIT 30", "전환사채(CB) 알려줘")
    assert fixed and "GLOB '*[0-9]CB*'" in out and "'%전환%'" not in out and "GROUP BY pd_no LIMIT 30" in out
    out2, fixed2 = pl.ensure_kind_filter("SELECT pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm)='한국전력공사(주)' LIMIT 30", "한전 후순위채 있어?")
    assert fixed2 and "TRIM(pd_pbcm)='한국전력공사(주)' AND (pd_nm LIKE '%(후)%'" in out2
    assert pl._sql_precheck(out, ctx, T, False, question="") is None and pl._sql_precheck(out2, ctx, T, False, question="") is None


@pytest.mark.parametrize("q, sql", [
    ("영구채 알려줘", "SELECT pd_nm FROM domestic_bonds WHERE (pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%') AND mat_dt >= 20260824 GROUP BY pd_no LIMIT 30"),   # D-009 — 판정식 그대로
    ("신종자본증권 중 만기가 가장 짧은 것 알려줘", "SELECT pd_nm FROM domestic_bonds WHERE (pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%') AND mat_dt >= 20260824 GROUP BY pd_no ORDER BY MIN(mat_dt) ASC LIMIT 1"),  # X11
    ("전환사채와 교환사채 차이", "SELECT pd_nm FROM domestic_bonds LIMIT 30"),                                                                  # 구조 낱말 둘
    ("코코본드 빼고 은행채 보여줘", "SELECT pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) IN ('일반은행채','특수은행채') LIMIT 30"),                # 배제 낱말 — 종류 블록도 불개입(종류 컬럼 있음)
    ("코코본드 ETF 알려줘", "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 30"),                                           # 채권 밖
])
def test_BE_untouched_when_predicate_present(q, sql):
    assert pl.ensure_kind_filter(sql, q) == (sql, False)


# ══════════════════════════════════════════════════════════════════════════════
# BF — 다의어 되묻기 트리거 확장 (C-016 · BR-X05)
#   일반 규칙: ① 종류 낱말(국공채·회사채)은 위험 축 단서가 아니다 — '가장 위험한 회사채' 도 되묻는다
#   ② '등급' 이 신용/위험/리스크/안전 한정어·등급값 없이 높낮이 어휘와 오면 되묻는다(clarify.다의어.등급 강제 부착)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("q", ["가장 위험한 회사채 뭐야?", "제일 위험한 국공채 알려줘", "위험도 높은 순으로 은행채 알려줘"])
def test_BF_risky_with_kind_word_clarifies(q):
    ask = pl.risk_ambiguity_clarify(q, T)
    assert ask and "투자위험등급" in ask and "신용등급" in ask


@pytest.mark.parametrize("q", ["등급 낮은 채권 알려줘", "등급이 높은 채권 5개", "등급 좋은 채권 골라줘", "낮은 등급 채권 뭐 있어?"])
def test_BF_grade_ambiguous_clarifies(ctx, q):
    ask = pl.grade_token_clarify(q, T, ctx)
    assert ask and ask.startswith("'등급' 이") and "신용등급" in ask and "위험등급" in ask


@pytest.mark.parametrize("q", [
    "위험이 가장 낮은 등급의 채권 알려줘",            # D-003 — '위험' 단서
    "신용등급 AA- 이상 채권 알려줘",                  # D-001
    "신용등급 BB+ 채권 알려줘",                       # U-018
    "신용등급 낮은 채권 알려줘", "위험등급 높은 채권 알려줘", "안전 등급 높은 채권",
    "BBB 등급 채권 알려줘", "5등급 채권 알려줘", "등급별 채권 수 알려줘", "등급 기준으로 정렬해줘",
])
def test_BF_grade_with_cue_untouched(ctx, q):
    assert pl.grade_token_clarify(q, T, ctx) is None or "'등급' 이" not in (pl.grade_token_clarify(q, T, ctx) or "")


def test_BF_scoped_to_bonds(ctx):
    assert pl.grade_token_clarify("등급 낮은 펀드 알려줘", ["public_funds"], ctx) is None
    assert pl.risk_ambiguity_clarify("가장 위험한 ETF 뭐야?", ["domestic_etfs"]) is None


# ══════════════════════════════════════════════════════════════════════════════
# BG — 랭킹 판정 신호 확장 (D-020)
#   일반 규칙: 수치 축 낱말(수익률·표면금리·금리·이자…) + 높은/낮은 + 목록 명사(것·채권·종목…)는 랭킹 — 축 바로 뒤에 최상급(가장·제일)이 끼면 사실확인 조회.
# ══════════════════════════════════════════════════════════════════════════════
D020_Q = "퇴직연금에 담을 수 있는 채권 중 수익률 높은 것 알려줘"
D020_SQL = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, applied_yield, pd_risk_gcd, pd_risk_nm, TRIM(crd_grd) AS crd_grd, mat_dt FROM domestic_bonds "
            "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND pd_pen_tr_yn = 'Y' AND applied_yield IS NOT NULL AND applied_yield > 0 "
            "ORDER BY applied_yield DESC LIMIT 5")


def test_BG_axis_phrase_is_rank(con):
    assert pl._RECO_Q.search(D020_Q) and pl._RANK_Q.search(D020_Q)
    out, fixed = pl.ensure_reco_exclusions(D020_SQL, D020_Q)
    assert fixed and "pd_risk_gcd <> '11'" in out and "<> 'C0'" in out and "bd_ofr_tcd <> '사모'" in out
    rows = con.execute(out).fetchall()
    assert rows[0][1] == "롯데캐피탈 410-6" and all(r[3] != "11" for r in rows)            # gold D-020 1위 · 1등급 코코본드 제거
    # 형제 — 다른 축·다른 명사·'낮은'
    for q in ("표면금리 높은 채권 알려줘", "이자 높은 거 보여줘", "수익률 낮은 종목 알려줘", "금리가 높은 편인 채권"):
        assert pl._RECO_Q.search(q), q


@pytest.mark.parametrize("q", [
    "수익률이 가장 높은 채권은 뭐야?",          # F-021 — 사실확인 최상급(C0 728.524% 정답)
    "수익률이 제일 높은 채권이 뭐야?",          # D-030
    "신용등급 낮은 채권 알려줘",                # 수치 축 아님(등급은 다른 가드·되묻기 몫)
    "만기가 가장 짧은 채권 뭐야?",              # D-032
    "수익률이 높은 채권은 위험도 높아?",        # 사실 질문이지만 목록 명사 뒤 — 랭킹으로 봐도 조회 무해(제외 없이) — 여기선 RECO 만 검사
])
def test_BG_superlative_fact_not_rank(q):
    if "위험도" in q:
        return
    assert not pl._RECO_Q.search(q) and not pl._RANK_Q.search(q), q


# ══════════════════════════════════════════════════════════════════════════════
# BH — 추천 질의의 집계 SQL → 목록 강제 · 다열 집계 1행 기계 조립 (D-025)
#   일반 규칙: 추천 질의(_RECO_Q · 개수 의문 없음)에 SELECT 가 집계만이면 표준 목록 + ORDER BY applied_yield DESC LIMIT 5 로 재작성(ensure_count_query 역방향).
#   남는 다열 집계 1행은 _bond_avg_answer 가 값 그대로 조립한다(HCX 산문 0).
# ══════════════════════════════════════════════════════════════════════════════
D025_Q = "만기까지 들고 갈 건데, 3년 안에 만기되는 안전한 채권 몇 개만 골라줘"
D025_AGG = ("SELECT COUNT(DISTINCT pd_no), AVG(applied_yield) FROM domestic_bonds WHERE curr_cd = 'KRW' AND pd_risk_gcd IN ('15','16') "
            "AND applied_yield > 0 AND bd_ofr_tcd <> '사모' AND mat_dt BETWEEN 20260824 AND 20290824 /*M:BONDPOP*/ LIMIT 30")


def test_BH_reco_aggregate_to_list(con):
    out, fixed = pl.ensure_count_query(D025_AGG, D025_Q)
    assert fixed and out.startswith("SELECT pd_no, TRIM(pd_nm) AS pd_nm") and "pd_risk_nm" in out
    assert "ORDER BY applied_yield DESC LIMIT 5" in out and out.count("/*M:BONDPOP*/") == 1 and "COUNT(" not in out
    rows = con.execute(out).fetchall()
    assert len(rows) == 5 and all(r[5] in ("15", "16") for r in rows)                 # gold D-025: 15·16 · 수익률 높은 순 5행
    # 형제 — 다른 축(표면금리)은 그 축으로 · 개수 의문이 있으면 개수 질문(불개입) · 정방향(목록→COUNT)은 종전대로
    out2, _ = pl.ensure_count_query("SELECT AVG(srfc_irt) FROM domestic_bonds WHERE curr_cd='KRW' LIMIT 30", "표면금리 높은 채권 5개 골라줘")
    assert "ORDER BY srfc_irt DESC" in out2
    cnt = "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE curr_cd='KRW' LIMIT 30"
    assert pl.ensure_count_query(cnt, "추천할 만한 회사채 몇 개나 있어?") == (cnt, False)
    assert pl.ensure_count_query("SELECT pd_no, pd_nm FROM domestic_bonds WHERE curr_cd='KRW' LIMIT 30", "수익률 5% 넘는 건 몇 개야?")[0].startswith("SELECT COUNT(DISTINCT pd_no)")
    etf = "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 30"
    assert pl.ensure_count_query(etf, "ETF 추천해줘") == (etf, False)                    # 채권 전용


def test_BH_multi_agg_row_assembled():
    sql = "SELECT COUNT(DISTINCT pd_no), AVG(applied_yield) FROM domestic_bonds WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 AND TRIM(std_pd_mcls_nm)='회사채' LIMIT 30"
    ans = pl._bond_avg_answer(sql, "COUNT(DISTINCT pd_no) | AVG(applied_yield)\n12572 | 3.9123", 1, "회사채는 몇 종목이고 평균 수익률은 얼마야?")
    assert ans and "12,572종목" in ans and "평균 수익률 3.91%" in ans and "기준일 2026-08-24" in ans
    ans2 = pl._bond_avg_answer("SELECT AVG(srfc_irt), MAX(srfc_irt) FROM domestic_bonds WHERE curr_cd='KRW' LIMIT 30", "AVG(srfc_irt) | MAX(srfc_irt)\n3.8 | 11.0", 1, "표면금리 평균과 최고")
    assert ans2 and "평균 표면금리 3.80%" in ans2 and "최고 표면금리 11.00%" in ans2
    # 불개입 — AVG 없는 집계(개수 조립기 몫) · 분포(GROUP BY) · 모르는 항
    assert pl._bond_avg_answer("SELECT COUNT(DISTINCT pd_no), MAX(applied_yield) FROM domestic_bonds LIMIT 30", "a | b\n1 | 2", 1, "q") is None
    assert pl._bond_avg_answer("SELECT TRIM(bd_knd), AVG(srfc_irt) FROM domestic_bonds GROUP BY 1 LIMIT 30", "bd_knd | AVG\na | 1\nb | 2", 2, "q") is None
    assert pl._bond_avg_answer("SELECT AVG(srfc_irt), GROUP_CONCAT(pd_nm) FROM domestic_bonds LIMIT 30", "a | b\n1 | x", 1, "q") is None


# ══════════════════════════════════════════════════════════════════════════════
# BJ — 반대 방향 최상급 비교 조립 (S-007)
#   일반 규칙: 안전·위험 최상급이 한 질문에 오면 6등급 1종목 ∪ 1등급 1종목(각 수익률 높은 순) UNION ALL 템플릿을 결정층이 세우고,
#   조립기는 /*TOPBOTH*/ 마커로 UNION 을 허용해 '각 1종목' 머리줄을 쓴다(위험 쪽은 조회라 고위험제외 미적용 · C0 주의 문구).
# ══════════════════════════════════════════════════════════════════════════════
S007_Q = "가장 안전한 채권이랑 가장 위험한 채권 하나씩 보여줘"
S007_SQL = ("SELECT TRIM(pd_nm) AS pd_nm, pd_risk_nm, applied_yield FROM domestic_bonds WHERE (pd_risk_gcd = '16' OR pd_risk_gcd = '11') "
            "AND mat_dt >= 20260824 AND curr_cd = 'KRW' GROUP BY pd_no LIMIT 2")


def test_BJ_both_extremes_template(ctx, con):
    out, fixed = pl.ensure_top_safety(S007_SQL, S007_Q)
    assert fixed and pl.TOPBOTH_MARK in out and out.count("UNION ALL") == 1 and "pd_risk_gcd = '16'" in out and "pd_risk_gcd = '11'" in out
    assert pl._sql_precheck(out, ctx, T, False, question=S007_Q) is None and guard.check_values(out, ctx) == []
    assert pl.ensure_top_safety(out, S007_Q) == (out, False)                            # 멱등
    rows, n = pl._execute(out)
    assert n == 2
    ans = pl._bond_list_answer(out, rows, n, S007_Q)
    assert ans and "6등급" in ans and "1등급" in ans and "[가장 안전]" in ans and "[가장 위험]" in ans
    assert "제외했습니다" not in ans and pl.C0_YIELD_NOTE in ans                          # gold S-007 must_not_include · C0 주의
    # 형제 — 어휘 변형도 같은 템플릿 · 한쪽 최상급만이면 종전 경로('16' 단독)
    for q in ("제일 안전한 채권과 제일 위험한 채권 하나씩 알려줘", "가장 안전한 것과 위험도가 가장 높은 것 비교해줘"):
        assert pl.TOPBOTH_MARK in pl.ensure_top_safety(S007_SQL, q)[0], q
    one, _ = pl.ensure_top_safety("SELECT pd_no FROM domestic_bonds WHERE pd_risk_gcd IN ('15','16') LIMIT 3", "가장 안전한 채권 3개 추천해줘")
    assert pl.TOPBOTH_MARK not in one and "pd_risk_gcd = '16'" in one
    etf = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no='ETF' LIMIT 2"
    assert pl.ensure_top_safety(etf, S007_Q) == (etf, False)                            # 채권 전용


def test_BJ_variant_inputs_same_template(ctx):
    """형제 — HCX 가 낸 SQL 의 컬럼·값·ORDER BY 항이 달라도 결정층 템플릿은 하나(입력 SQL 을 고치는 게 아니라 세운다)."""
    variants = [
        "SELECT pd_no, pd_nm, srfc_irt FROM domestic_bonds WHERE pd_risk_nm IN ('매우낮은위험','매우높은위험') AND curr_cd='KRW' LIMIT 2",
        "SELECT pd_nm, applied_yield FROM domestic_bonds WHERE pd_risk_gcd IN ('11','16') ORDER BY applied_yield ASC LIMIT 2",
        "SELECT pd_nm FROM domestic_bonds WHERE pd_risk_gcd IN ('16','11') ORDER BY pd_risk_gcd DESC, srfc_irt DESC LIMIT 2",
    ]
    first = pl.ensure_top_safety(variants[0], S007_Q)[0]
    for s in variants:
        out, fixed = pl.ensure_top_safety(s, S007_Q)
        assert fixed and out == first, s                       # 입력이 달라도 결과 SQL 동일
    assert pl._sql_precheck(first, ctx, T, False, question=S007_Q) is None


def test_BJ_survives_full_guard_chain(ctx):
    """가드 체인 전체를 태워도 템플릿이 살아 2행(6등급 1 · 1등급 1)을 낸다 — ensure_limit·정렬 가드가 가지 안 LIMIT 을 건드리지 않는다."""
    tpl = pl.ensure_top_safety(S007_SQL, S007_Q)[0]
    chained = pl._apply_sql_guards(tpl, S007_Q, None, None, lambda m: None, ctx, list(T))
    assert pl.TOPBOTH_MARK in chained and chained.count("LIMIT 1") == 2
    rows, n = pl._execute(chained)
    assert n == 2 and "매우낮은위험(6등급)" in rows and "매우높은위험(1등급)" in rows
    ans = pl._bond_list_answer(chained, rows, n, S007_Q)
    assert ans and ans.count("\n1. [가장 안전]") == 1 and "2. [가장 위험]" in ans


def test_BJ_no_intervention_without_both_extremes():
    """불개입 — 위험 최상급만이면(안전 최상급 없음) 종전대로 물러난다 · 수익률 하한 요구도 종전대로."""
    s = "SELECT pd_nm FROM domestic_bonds WHERE curr_cd='KRW' AND mat_dt >= 20260824 LIMIT 30"
    assert pl.ensure_top_safety(s, "가장 위험한 채권 알려줘") == (s, False)
    assert pl.ensure_top_safety(s, "가장 안전하면서 수익률 5% 이상인 채권") == (s, False)


# ══════════════════════════════════════════════════════════════════════════════
# BK — 이자 미지급 = 할인채 확정식 · '왜' 는 설명형 (BR-X10)
#   일반 규칙: 선언 query_rules.무이자질의 를 런타임이 강제한다 — '이자를 안 주는/무이자/무이표/제로쿠폰' 은
#   bd_intp_tcd = '할인채' 하나로(있으면 교체·없으면 주입), 그리고 '왜' 문형은 목록이 아니라 구조 설명 + 종목 수로 답한다.
#   값·통칭은 코드에 적지 않는다: 확정식 값은 선언 문장에서, 통칭은 synonyms 에서, 다른 이자유형은 DB distinct 로 읽는다.
# ══════════════════════════════════════════════════════════════════════════════
X10_Q = "이자를 아예 안 주는 채권은 왜 그런거야?"
X10_SQL = ("SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(bd_intp_tcd) FROM domestic_bonds "
           "WHERE bd_intp_tcd IN ('할인채', '복리채', '단리채') AND bd_inrt_tcd = '고정금리' GROUP BY pd_no LIMIT 30")


def test_BK_zero_coupon_declaration_read():
    """확정식 값·통칭·타 유형은 전부 선언/DB 에서 읽는다 (코드 목록 0)."""
    assert pl._zero_coupon_value() == "할인채"                       # query_rules.무이자질의.text 의 bd_intp_tcd='…'
    assert set(pl._other_coupon_types()) == {"이표채", "복리채", "단리채"}     # DB distinct
    for w in ("무이자", "무이표", "제로쿠폰", "제로 쿠폰"):                    # synonyms 에서 온 통칭
        assert pl._zero_coupon_q(f"{w} 채권 알려줘"), w


def test_BK_zero_coupon_kind_fixed(ctx, con):
    out, fixed = pl.ensure_kind_filter(X10_SQL, X10_Q)
    assert fixed and "TRIM(bd_intp_tcd) = '할인채'" in out and "복리채" not in out and "단리채" not in out
    assert "bd_inrt_tcd = '고정금리'" in out and "GROUP BY pd_no LIMIT 30" in out       # 나머지 절 보존
    assert pl._sql_precheck(out, ctx, T, False, question=X10_Q) is None and guard.check_values(out, ctx) == []
    assert pl.ensure_kind_filter(out, X10_Q)[1] is False                                 # 멱등
    n, = _one(con, f"SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(bd_intp_tcd) = '할인채' "
                   f"AND curr_cd = 'KRW' AND mat_dt >= {pl.BUYABLE_INT}")
    assert n == 686                                                                       # gold BR-X10 기대 종목 수


def test_BK_zero_coupon_injected_when_absent():
    """형제 — 이자유형 절이 아예 없으면 주입 · 어휘 변형 4종 · 이미 확정식이면 불개입(멱등)."""
    bare = "SELECT pd_no, pd_nm FROM domestic_bonds WHERE curr_cd = 'KRW' LIMIT 30"
    for q in ("무이자 채권 알려줘", "무이표채 뭐 있어?", "제로쿠폰 채권 목록", "이자 없는 채권 보여줘"):
        out, fixed = pl.ensure_kind_filter(bare, q)
        assert fixed and "TRIM(bd_intp_tcd) = '할인채'" in out and "curr_cd = 'KRW'" in out, q
    already = "SELECT pd_no FROM domestic_bonds WHERE TRIM(bd_intp_tcd) = '할인채' LIMIT 30"
    assert pl.ensure_kind_filter(already, "무이자 채권 알려줘") == (already, False)


def test_BK_no_intervention():
    """불개입 — 부정문 · 다른 이자유형을 콕 집음 · 채권 아닌 테이블 · JOIN/서브쿼리."""
    assert not pl._zero_coupon_q("무이자 채권 말고 이표채로 알려줘")
    assert not pl._zero_coupon_q("복리채는 이자를 안 주나?")
    assert not pl._zero_coupon_q("이자를 가장 많이 주는 채권은?")
    etf = "SELECT pd_abrv_nm FROM domestic_etfs WHERE pd_grp_no = 'ETF' LIMIT 5"
    assert pl.ensure_kind_filter(etf, "무이자 상품 알려줘") == (etf, False)
    joined = ("SELECT b.pd_no FROM domestic_bonds b JOIN domestic_bonds c ON b.pd_no = c.pd_no "
              "WHERE b.bd_intp_tcd = '복리채' LIMIT 5")
    assert "복리채" in pl.ensure_kind_filter(joined, "무이자 채권 알려줘")[0]


def test_BK_coupon_split_stands_down():
    """충돌 예측 지점 — 표면금리 랭킹 분리 가드(_INTP_NAMED_Q)는 낱말만 봤다. 서술형 지목도 '콕 집음' 이라 불개입."""
    sql = ("SELECT pd_no, pd_nm, srfc_irt FROM domestic_bonds WHERE curr_cd = 'KRW' "
           "ORDER BY srfc_irt DESC LIMIT 5")
    assert pl.ensure_coupon_type_split(sql, "이자를 안 주는 채권 중 표면금리 높은 순 5개 추천") == (sql, False)
    assert pl.ensure_coupon_type_split(sql, "표면금리 높은 채권 추천해줘")[1] is True          # 종전 동작 유지


def test_BK_why_answer_explains(ctx):
    """'왜' 는 목록이 아니라 설명 + 종목 수. 수는 확정식·구매가능 모수로 결정층이 다시 센다(HCX SQL 모수에 안 맡긴다)."""
    fixed_sql, _ = pl.ensure_kind_filter(X10_SQL, X10_Q)
    ans = pl._zero_coupon_reason_answer(fixed_sql, X10_Q)
    assert ans and "686종목" in ans and "할인채" in ans
    assert "액면가" in ans and "발행 할인율" in ans                        # 선언이 허용한 서술 범위
    assert "수록되어 있지 않습니다" in ans                                  # 발행 사유는 부재 고지
    assert "국민주택" not in ans and "\n1. " not in ans                     # 목록이 아니다
    # 형제 — 이유 문형 변형은 같은 경로 · 목록 문형·확정식 없는 SQL 은 종전 목록 경로
    for q in ("무이자 채권은 왜 이자가 없어?", "제로쿠폰 채권은 어째서 이자를 안 주지?"):
        assert pl._zero_coupon_reason_answer(fixed_sql, q), q
    assert pl._zero_coupon_reason_answer(fixed_sql, "이자를 안 주는 채권 알려줘") is None
    assert pl._zero_coupon_reason_answer("SELECT pd_nm FROM domestic_bonds LIMIT 5", X10_Q) is None
    assert pl._zero_coupon_reason_answer("SELECT pd_abrv_nm FROM domestic_etfs LIMIT 5", X10_Q) is None



# ══════════════════════════════════════════════════════════════════════════════
# 🔴 질문 어휘 주의: 시험용 질의는 '무지개채권'(채권 낱말 포함)이다. '무지개채' 단독은 2026-09-06 main 의
#    도메인 밖 게이트(af3997b — 상품군 낱말·KG 매핑·스키마 어휘가 하나도 없으면 안내 문장)에 먼저 걸려
#    플래너까지 가지 않는다. BP 의 동작이 아니라 라우팅이 바뀐 것이라 시험 매개만 바꿨다(단언은 그대로).
# BP — 재생성 절약 · HCX 429 기록 (docs/bonds_latency_analysis_2026-09-06.md)
#   일반 규칙: ② 재생성이 정규화 후 같은 문장이거나 같은 값 위반을 되풀이하면 거기서 끝낸다(#87 형).
#   ③ 위반이 발행사 컬럼뿐이고 주인 컬럼도 없으면 값이 진짜 없는 것이다 — 재생성 대신 즉시 되묻기.
#   ④ 429 재시도·대기·응답 시간을 think_trace 의 [Plan] 마커로 남긴다(재시도 정책은 그대로 · 기록만).
# ══════════════════════════════════════════════════════════════════════════════
_BAD_KIND = "SELECT pd_no, pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '무지개채' AND mat_dt >= 20260824 LIMIT 5"
_BAD_KIND2 = "SELECT pd_no, TRIM(pd_nm) FROM domestic_bonds WHERE TRIM(bd_knd) = '무지개채' AND mat_dt >= 20260824 LIMIT 10"
_GOOD_KIND = "SELECT pd_no, TRIM(pd_nm) AS pd_nm FROM domestic_bonds WHERE TRIM(bd_knd) = '국고채권' AND mat_dt >= 20260824 LIMIT 5"
_BAD_ISSUER = "SELECT pd_no, pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm) = '삼성전자' AND mat_dt >= 20260824 LIMIT 5"


def _P(sqls, calls):
    """가짜 플래너 — 호출 순서대로 SQL 을 내고 호출 횟수를 기록한다(HCX 0회)."""
    class P:
        def plan_sql(self, q, g):
            calls.append(q)
            return sqls[min(len(calls) - 1, len(sqls) - 1)]

        def compose_answer(self, q, rows, answer_rules=""):
            return "HCX 산문"
    return P()


def test_BP_norm_and_signature_helpers():
    assert pl._norm_sql_text("SELECT  a\nFROM t ") == pl._norm_sql_text("select a from t")
    assert pl._norm_sql_text("SELECT a FROM t LIMIT 5") != pl._norm_sql_text("SELECT a FROM t LIMIT 10")

    class V:
        def __init__(self, c, l):
            self.column, self.literal = c, l
    assert pl._violation_sig([V("a", "1"), V("b", "2")]) == pl._violation_sig([V("b", "2"), V("a", "1")])
    assert pl._violation_sig([]) == () and pl._violation_sig(None) == ()


def test_BP_same_regen_stops(ctx):
    """② 재생성이 같은 문장을 되풀이하면 마커를 남기고 끝낸다 — 같은 가드·같은 검사를 두 번 태우지 않는다."""
    calls = []
    r = pl.answer_question("T-BP2", "무지개채권 알려줘", planner=_P([_BAD_KIND], calls), ctx=ctx)
    assert len(calls) == 2                       # 재생성 1회는 돈다(같은 문장인지는 받아 봐야 안다)
    assert "재생성 무효" in r.think_trace and "#87 형" in r.think_trace
    assert "확인할 수 없습니다" in r.answer


def test_BP_same_violation_stops(ctx):
    """② 문장이 달라도 같은 값 위반을 되풀이하면 끝낸다."""
    calls = []
    r = pl.answer_question("T-BP2b", "무지개채권 알려줘", planner=_P([_BAD_KIND, _BAD_KIND2], calls), ctx=ctx)
    assert len(calls) == 2 and "재생성 무효" in r.think_trace and "bd_knd='무지개채'" in r.think_trace


def test_BP_regen_still_runs_when_it_changes(ctx):
    """불개입 — 재생성이 고쳐 오면 종전대로 그 SQL 을 쓴다(BP② 가 재생성 자체를 막으면 안 된다)."""
    calls = []
    r = pl.answer_question("T-BP2c", "무지개채권 알려줘", planner=_P([_BAD_KIND, _GOOD_KIND], calls), ctx=ctx)
    assert len(calls) == 2 and "재생성 무효" not in r.think_trace
    assert "국고채권" in r.sql and "무지개채" not in r.sql and r.retrieved_context.strip()


def test_BP_issuer_absent_skips_regen(ctx):
    """③ 발행사 값 부재는 재생성 없이 즉시 되묻기 — HCX 1회. 문구는 종전(재생성 후 실패) 경로와 같다."""
    calls = []
    r = pl.answer_question("T-BP3", "삼성전자가 발행한 채권 알려줘", planner=_P([_BAD_ISSUER], calls), ctx=ctx)
    assert len(calls) == 1                                              # 재생성 생략
    assert "발행사 값 부재 확정" in r.think_trace and "재생성 1회" not in r.think_trace
    assert "확인할 수 없습니다" in r.answer and "말씀하신 건가요" in r.answer and "삼성카드" in r.answer


def test_BP_non_issuer_violation_still_regenerates(ctx):
    """③ 의 경계 — 발행사 밖의 위반은 종전대로 재생성을 탄다(owner '' 전체로 넓히면 D-037 의 등급 재생성을 잃는다)."""
    calls = []
    pl.answer_question("T-BP3b", "무지개채권 알려줘", planner=_P([_BAD_KIND, _GOOD_KIND], calls), ctx=ctx)
    assert len(calls) == 2
    mixed = ("SELECT pd_no, pd_nm FROM domestic_bonds WHERE TRIM(pd_pbcm) = '삼성전자' "
             "AND TRIM(bd_knd) = '무지개채' AND mat_dt >= 20260824 LIMIT 5")
    calls2 = []
    r2 = pl.answer_question("T-BP3c", "삼성전자가 발행한 무지개채", planner=_P([mixed, _GOOD_KIND], calls2), ctx=ctx)
    assert len(calls2) == 2 and "발행사 값 부재 확정" not in r2.think_trace     # 다른 위반이 섞이면 재생성한다


def test_BP_hcx_call_note_recorded(ctx):
    """④ 플래너가 통계를 주면 [Plan] 마커로 찍고, 안 주면(옛 플래너·가짜 플래너) 침묵한다."""
    assert pl._hcx_call_note(object()) is None

    class Stat:
        def __init__(self, retries):
            self._r = retries

        def plan_sql(self, q, g):
            return "SELECT pd_no, TRIM(pd_nm) AS pd_nm FROM domestic_bonds WHERE mat_dt >= 20260824 LIMIT 3"

        def compose_answer(self, q, rows, answer_rules=""):
            return "ok"

        def last_call_stats(self):
            return {"retries": self._r, "wait_s": 20.0 * self._r, "latency_s": 1.4}
    r = pl.answer_question("T-BP4", "채권 3개만 보여줘", planner=Stat(2), ctx=ctx)
    assert "[Plan] HCX 호출 — 응답 1.4s · 429 재시도 2회 · 대기 40s" in r.think_trace
    assert "분당 토큰 한도" in r.think_trace                     # 꼬리는 재시도가 있을 때만
    note = pl._hcx_call_note(Stat(0))
    assert note and "재시도 0회 · 대기 0s" in note and "분당 토큰 한도" not in note


def test_BP_client_records_retry_stats(monkeypatch):
    """④ 클라이언트가 429 대기·재시도를 기록한다 — 정책(최대 3회·20초)은 그대로. 가짜 httpx 응답으로."""
    import src.hcx.client as C

    class Resp:
        def __init__(self, code):
            self.status_code, self.headers, self.text = code, {}, "{}"

        def json(self):
            return {"status": {"code": "20000"},
                    "result": {"message": {"content": "SELECT 1"}, "usage": {}, "finishReason": "stop"}}

    seq = [Resp(429), Resp(429), Resp(200)]

    class Http:
        def post(self, *a, **k):
            return seq.pop(0)
    slept = []
    monkeypatch.setattr(C.time, "sleep", lambda s: slept.append(s))
    cl = C.HCXClient(C.HCXConfig(model="X", max_retries=3, retry_wait_s=20.0), api_key="k", client=Http())
    res = cl.complete("sys", "user")
    assert res.retries == 2 and res.wait_s == 40.0 and slept == [20.0, 20.0]
    assert cl.last_retries == 2 and cl.last_wait_s == 40.0 and cl.last_latency_s >= 0
