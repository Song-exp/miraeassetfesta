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
