# -*- coding: utf-8 -*-
"""평가셋 jsonl 에 gold_sql 채우기 — 2차 스키마(기준일 2026-08-22) 기준. 실행 후 run_gold_check.py 로 검증.

규칙(도메인 yaml query_rules): ETF/ETN 분리 pd_grp_no · 펀드 모수 sale_yn='판매중' AND prvo_pbff_desc='공모'
· 수치 정렬 IS NOT NULL AND <> 0 · 수익률 > -100 · 인버스 = pd_abrv_nm LIKE '%인버스%' · 채권 GROUP BY pd_no
· 보수 ‰→% /10 · 교차질의 = 도메인별 서브쿼리 UNION ALL + 상품군 컬럼.
reject/clarify 문항은 gold_sql=null + gold_reason. 2차 데이터로 답변 가능해진 '구 unanswerable' 문항은
gold_sql 을 함께 실어 두고 gold_reason 에 승격 권고를 남긴다 (expected_behavior 는 건드리지 않음).
"""
import json, sqlite3, sys, os
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.runtime.pipeline import validate_sql  # noqa: E402

AS_OF = "2026-08-22"
FUND = "sale_yn='판매중' AND prvo_pbff_desc='공모'"
ETF = "pd_grp_no='ETF'"

G = {}  # qid -> (sql or None, reason or None)

# ── 공식 예시 ─────────────────────────────────────────────
G["OFFICIAL-001"] = (f"""SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(crd_grd) AS crd_grd, mat_dt, applied_yield
FROM domestic_bonds WHERE curr_cd='KRW' AND mat_dt > 20260822 AND TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-')
GROUP BY pd_no ORDER BY mat_dt LIMIT 30""", "구매가능=만기 미경과(buyable_quantity 무효). 결측 등급 4,020건은 모수 제외·명시")
G["OFFICIAL-002"] = ("""SELECT p.itm_no, p.itm_nm, p.zrin_btyp_nm, p.zrin_ptn_nm, p.or_attr_desc, p.zrin_attr_nms, p.fd_ivst_rgn_desc,
e.mother_fund_names_raw, e.prospectus_url FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no=p.itm_no
WHERE p.itm_nm LIKE '%국민성장%' AND p.sale_yn='판매중' LIMIT 20""", "partial — 구조(유형·속성·모펀드)는 마스터+ext_fund_page, '투자전략 동향'은 설명서 텍스트(외부) 필요")
G["OFFICIAL-003"] = ("""SELECT DISTINCT e.pd_abrv_nm, e.pd_nm, e.wu_inv_rgn, h.report_date, h.pct_val AS cambricon_pct
FROM overseas_etfs e JOIN ext_ovs_etf_holdings h ON h.isin=e.pd_isin_cd
WHERE h.holding_name LIKE '%Cambricon%'
ORDER BY h.pct_val DESC LIMIT 20""", "partial — Cambricon 편입 ETF 는 수집 범위(AUM 상위) 내 EM 광역 ETF 뿐, '중국 반도체' 테마 ETF 는 0건 → 모수(커버리지)·report_date 병기하고 테마 조건 미충족을 명시")
G["OFFICIAL-004"] = (f"""SELECT '국내ETF' AS grp, pd_abrv_nm AS name, wu_inv_rgn AS region, du_er_6m AS ret_6m, du_last_aum AS aum
FROM domestic_etfs WHERE {ETF} AND (pd_abrv_nm LIKE '%우주%' OR pd_abrv_nm LIKE '%항공%')
UNION ALL SELECT '해외ETF', pd_abrv_nm, wu_inv_rgn, NULL, du_last_aum FROM overseas_etfs
WHERE pd_grp_no='ETF' AND (pd_nm LIKE '%Aerospace%' OR pd_nm LIKE '%Space%') ORDER BY 1, aum DESC LIMIT 40""",
    "partial — '이력'은 스냅샷에 없음. 6개월 수익률(국내)로 대체, 해외는 기간수익률 미수록")
G["OFFICIAL-005"] = f"""SELECT e.pd_abrv_nm, e.du_last_aum, e.pd_risk_nm, e.cu_lev_fector, h.constituent, h.weight_pct, h.as_of
FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code=e.pd_itm_no
WHERE e.{ETF} AND h.constituent IN ('에코프로비엠','에코프로머티','에코프로에이치엔') AND e.du_last_aum IS NOT NULL AND e.du_last_aum<>0
ORDER BY e.du_last_aum DESC LIMIT 10""", "자회사 목록은 온톨로지 기업관계(에코프로비엠·에코프로머티·에코프로에이치엔) — 위험요인은 위험등급·레버리지 배수로"
G["OFFICIAL-NA-001"] = (None, "Gate② enum — 'AAAA' 는 crd_grd 15종 화이트리스트에 없음")
G["OFFICIAL-NA-002"] = (None, "Ground 매칭 0 + 상품명 정확일치 0건(3테이블) → 불가응답. LIKE 부분매칭 금지")
G["OFFICIAL-NA-003"] = (None, "상품명 정확일치 0건(KODEX 로봇액티브·KODEX 글로벌로봇 등 유사 4건 존재) → 불가응답 또는 유사상품 역질문")

# ── 국내 ETF ─────────────────────────────────────────────
G["ETF-D-001"] = f"""SELECT pd_abrv_nm, cu_lev_fector, wu_inv_rgn, du_last_aum FROM domestic_etfs
WHERE {ETF} AND wu_inv_rgn='미국' AND ABS(cu_lev_fector)>1 AND pd_abrv_nm NOT LIKE '%인버스%' ORDER BY du_last_aum DESC LIMIT 30"""
G["ETF-D-002"] = f"""SELECT pd_abrv_nm, pd_risk_nm, du_last_aum FROM domestic_etfs
WHERE {ETF} AND wu_inv_ast_type='채권' AND pd_risk_cd='PD_RISK_GCD_16' ORDER BY du_last_aum DESC LIMIT 30"""
G["ETF-D-003"] = f"""SELECT pd_abrv_nm, pd_pen_risk_nm, du_last_aum FROM domestic_etfs
WHERE {ETF} AND pd_pen_tr_yn='Y' AND pd_pen_risk_nm='안전자산' AND du_last_aum IS NOT NULL AND du_last_aum<>0 ORDER BY du_last_aum DESC LIMIT 5"""
G["ETF-D-004"] = "SELECT pd_abrv_nm, cu_fund_mgmt_co, ref_fund_mgmt_co, pd_risk_nm FROM domestic_etfs WHERE TRIM(pd_abrv_nm)='KODEX 200' LIMIT 1"
G["ETF-D-005"] = "SELECT pd_abrv_nm, cu_fund_mgmt_co, cu_charge_rt FROM domestic_etfs WHERE TRIM(pd_abrv_nm)='KODEX 반도체' AND cu_charge_rt IS NOT NULL AND cu_charge_rt<>0 LIMIT 1"
G["ETF-D-006"] = "SELECT pd_abrv_nm, ref_fund_mgmt_co, cu_fund_mgmt_co, cu_charge_rt FROM domestic_etfs WHERE TRIM(pd_abrv_nm)='KODEX 레버리지' LIMIT 1"
G["ETF-D-007"] = "SELECT pd_abrv_nm, cu_fund_mgmt_co, du_last_aum FROM domestic_etfs WHERE TRIM(pd_abrv_nm) IN ('KODEX 200','TIGER 200') ORDER BY du_last_aum DESC LIMIT 2"
G["ETF-D-008"] = f"""SELECT pd_abrv_nm, cu_fund_mgmt_co, ref_base_index, du_last_aum FROM domestic_etfs
WHERE {ETF} AND ref_base_index IN ('S&P 500 TR','S&P 500 CR') AND pd_abrv_nm NOT LIKE '%레버리지%' AND pd_abrv_nm NOT LIKE '%인버스%'
AND du_last_aum IS NOT NULL AND du_last_aum<>0 ORDER BY du_last_aum DESC LIMIT 3"""
G["ETF-D-009"] = "SELECT pd_abrv_nm, du_er_1y FROM domestic_etfs WHERE TRIM(pd_abrv_nm) IN ('KODEX 반도체','TIGER 반도체') AND du_er_1y > -100 ORDER BY du_er_1y DESC LIMIT 2"
G["ETF-D-010"] = f"SELECT pd_abrv_nm, cu_fund_mgmt_co, du_last_aum FROM domestic_etfs WHERE {ETF} AND du_last_aum IS NOT NULL AND du_last_aum<>0 ORDER BY du_last_aum DESC LIMIT 5"
G["ETF-D-011"] = f"""SELECT pd_abrv_nm, du_er_1y, du_last_aum FROM domestic_etfs
WHERE {ETF} AND wu_inv_ast_type='채권' AND du_er_1y IS NOT NULL AND du_er_1y > -100 AND du_er_1y<>0 ORDER BY du_er_1y DESC LIMIT 5"""
G["ETF-D-012"] = f"SELECT ref_fund_mgmt_co, COUNT(*) AS n FROM domestic_etfs WHERE {ETF} AND ref_fund_mgmt_co IS NOT NULL GROUP BY ref_fund_mgmt_co ORDER BY n DESC LIMIT 5"
G["ETF-D-013"] = (f"""SELECT 'ETF' AS grp, pd_abrv_nm AS name, du_er_1y AS ret_1y, du_last_aum AS aum FROM domestic_etfs WHERE {ETF} AND ref_fund_mgmt_co LIKE 'Mirae Asset%'
UNION ALL SELECT '펀드', itm_nm, fd_yr1_ern_r, fd_nast_suma FROM public_funds WHERE {FUND} AND or_co_xtn_itt_cd='00080008'
ORDER BY 1, aum DESC LIMIT 40""", "🔼 승격 권고 — 2차: ref_fund_mgmt_co + asset_manager.csv(00080008=미래에셋자산운용)로 교차 가능")
G["ETF-D-014"] = (f"""SELECT '국내ETF' AS grp, pd_abrv_nm AS name, ref_base_index AS idx, cu_charge_rt AS fee FROM domestic_etfs WHERE {ETF} AND ref_base_index IN ('S&P 500 TR','S&P 500 CR')
UNION ALL SELECT '해외ETF', pd_abrv_nm, cu_base_index, cu_charge_rt FROM overseas_etfs WHERE pd_grp_no='ETF' AND cu_base_index IN ('S&P 500 TR','S&P 500 CR')
ORDER BY 1, name LIMIT 60""", "🔼 승격 권고 — 2차 ref_base_index 로 지수명 정규 표기 일치")
G["ETF-D-015"] = (None, "상품명 정확일치 0건 → 불가응답 (유사: KODEX 로봇액티브 등 4건 — 역질문 가능)")
G["ETF-D-016"] = (None, "Gate② 위험등급 범위 0~6 — 7등급 없음")
G["ETF-D-017"] = (None, "ref_base_index/상품명에 KOSPI 300 0건 → 불가응답 (KOSPI 200·100 존재 안내 가능)")
G["ETF-D-018"] = (f"""SELECT e.pd_abrv_nm, h.weight_pct, h.as_of FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code=e.pd_itm_no
WHERE e.{ETF} AND h.constituent='삼성전자' ORDER BY h.weight_pct DESC LIMIT 5""", "🔼 승격 권고 — ext_etf_holdings(8/21) 편입비중. 단일종목 ETF(비중 100% 근접) 포함됨을 명시")
G["ETF-D-019"] = ("SELECT pd_abrv_nm, ref_base_index, cu_base_index FROM domestic_etfs WHERE TRIM(pd_abrv_nm)='KODEX 200' LIMIT 1",
                  "🔼 승격 권고 — 2차 ref_base_index='KOSPI 200 CR' 수록")
G["ETF-D-020"] = (None, "clarify — '안전' 기준(위험등급/자산군/지역) 역질문")
G["ETF-D-021"] = f"SELECT pd_abrv_nm, wu_inv_rgn, du_last_aum FROM domestic_etfs WHERE {ETF} AND (pd_abrv_nm LIKE '%우주%' OR pd_abrv_nm LIKE '%항공%') ORDER BY du_last_aum DESC LIMIT 30"
G["ETF-D-022"] = (G["OFFICIAL-005"][0].replace("LIMIT 10", "LIMIT 1"), "🔼 승격 권고 — OFFICIAL-005 와 동일 경로")
G["ETF-D-023"] = f"SELECT pd_abrv_nm, du_last_aum FROM domestic_etfs WHERE {ETF} AND (pd_abrv_nm LIKE '%2차전지%' OR pd_abrv_nm LIKE '%배터리%') AND du_last_aum IS NOT NULL AND du_last_aum<>0 ORDER BY du_last_aum DESC LIMIT 5"

# ── 해외 ETF ─────────────────────────────────────────────
O = "pd_grp_no='ETF'"
G["ETF-O-001"] = f"SELECT pd_abrv_nm, pd_nm, cu_charge_rt, du_last_aum FROM overseas_etfs WHERE {O} AND wu_inv_ast_type='Bond' AND cu_charge_rt>0 AND cu_charge_rt<=0.05 ORDER BY cu_charge_rt, du_last_aum DESC LIMIT 30"
G["ETF-O-002"] = f"SELECT pd_abrv_nm, pd_nm, du_last_aum FROM overseas_etfs WHERE {O} AND pd_exg_mkt_cd='NAS' AND wu_inv_ast_type='Equity' AND du_last_aum IS NOT NULL AND du_last_aum<>0 ORDER BY du_last_aum DESC LIMIT 5"
G["ETF-O-003"] = f"SELECT pd_abrv_nm, pd_nm, cu_lev_fector, du_last_aum FROM overseas_etfs WHERE cu_inverse_short_yn='Y' OR cu_lev_fector<0 ORDER BY du_last_aum DESC LIMIT 30"
G["ETF-O-004"] = "SELECT pd_abrv_nm, cu_fund_mgmt_co, cu_charge_rt, du_last_aum FROM overseas_etfs WHERE pd_abrv_nm='SPY' LIMIT 1"
G["ETF-O-005"] = "SELECT pd_abrv_nm, cu_charge_rt FROM overseas_etfs WHERE pd_abrv_nm='VOO' LIMIT 1"
G["ETF-O-006"] = "SELECT pd_itm_no, pd_abrv_nm, cu_fund_mgmt_co, pd_exg_mkt_cd FROM overseas_etfs WHERE pd_abrv_nm='QQQ' LIMIT 1"
G["ETF-O-007"] = "SELECT pd_abrv_nm, cu_base_index, cu_charge_rt FROM overseas_etfs WHERE pd_abrv_nm IN ('VOO','IVV','SPY') ORDER BY cu_charge_rt LIMIT 3"
G["ETF-O-008"] = f"""SELECT CASE WHEN cu_fund_mgmt_co LIKE '%BlackRock%' THEN 'BlackRock' ELSE 'Vanguard' END AS mgr, COUNT(*) AS n
FROM overseas_etfs WHERE {O} AND (cu_fund_mgmt_co LIKE '%BlackRock%' OR cu_fund_mgmt_co LIKE '%Vanguard%') GROUP BY 1 ORDER BY n DESC LIMIT 2"""
G["ETF-O-009"] = f"SELECT wu_inv_ast_type, ROUND(AVG(cu_charge_rt),3) AS avg_fee, COUNT(*) AS n FROM overseas_etfs WHERE {O} AND cu_charge_rt>0 AND wu_inv_ast_type IS NOT NULL GROUP BY 1 ORDER BY avg_fee LIMIT 10"
G["ETF-O-010"] = f"SELECT pd_abrv_nm, pd_nm, du_last_aum FROM overseas_etfs WHERE {O} AND du_last_aum IS NOT NULL AND du_last_aum<>0 ORDER BY du_last_aum DESC LIMIT 5"
G["ETF-O-011"] = f"SELECT pd_abrv_nm, pd_nm, cu_charge_rt, du_last_aum FROM overseas_etfs WHERE {O} AND wu_inv_ast_type='Equity' AND cu_charge_rt>0 ORDER BY cu_charge_rt, du_last_aum DESC LIMIT 5"
G["ETF-O-012"] = f"SELECT cu_fund_mgmt_co, COUNT(*) AS n FROM overseas_etfs WHERE {O} GROUP BY 1 ORDER BY n DESC LIMIT 5"
G["ETF-O-013"] = (G["ETF-D-014"][0], "🔼 승격 권고 — ETF-D-014 와 동일")
G["ETF-O-014"] = (f"""SELECT '해외ETF' AS grp, pd_abrv_nm AS name, du_last_aum AS aum FROM overseas_etfs WHERE {O} AND cu_fund_mgmt_co LIKE '%BlackRock%'
UNION ALL SELECT '국내ETF', pd_abrv_nm, du_last_aum FROM domestic_etfs WHERE {ETF} AND (ref_fund_mgmt_co LIKE '%BlackRock%' OR cu_fund_mgmt_co LIKE '%블랙록%')
ORDER BY 1, aum DESC LIMIT 30""", "partial — 해외 498건, 국내 0건(국내 부재를 명시하는 것이 정답)")
G["ETF-O-015"] = (None, "pd_exg_mkt_cd 에 KRX 없음(AMX/NAS/NYS/101/102) → 불가응답")
G["ETF-O-016"] = (None, "pd_trd_ccy 전부 USD → EUR 거래 0건 불가응답")
G["ETF-O-017"] = (None, "티커 정확일치 0건 → 불가응답")
G["ETF-O-018"] = ("SELECT pd_abrv_nm, du_er_1d, du_clpr, du_clpr_base_dt FROM overseas_etfs WHERE pd_abrv_nm='IVV' LIMIT 1",
                  "partial — 1년수익률 컬럼 부재(불가 명시) + 1일수익률·종가 기준일 병기")
G["ETF-O-019"] = (None, "cu_base_index 센티넬('Index is not provided…') → 데이터상 미제공 명시")
G["ETF-O-020"] = (None, "clarify — 자산군/지역 조건 역질문")
G["ETF-O-021"] = f"SELECT pd_abrv_nm, pd_nm, du_last_aum FROM overseas_etfs WHERE {O} AND (pd_nm LIKE '%Semiconductor%' OR pd_nm LIKE '%Chip%') AND du_last_aum IS NOT NULL AND du_last_aum<>0 ORDER BY du_last_aum DESC LIMIT 5"
G["ETF-O-022"] = (G["OFFICIAL-003"][0], "🔼 승격(partial) 권고 — Cambricon 편입 ETF 는 EM 광역 ETF 뿐, 중국 반도체 테마 ETF 0건(커버리지 274/5,972). OFFICIAL-003 과 동일")
G["ETF-O-023"] = f"SELECT pd_abrv_nm, pd_nm, du_last_aum FROM overseas_etfs WHERE {O} AND (pd_nm LIKE '%Aerospace%' OR pd_nm LIKE '%Space%' OR pd_nm LIKE '%Defense%') ORDER BY du_last_aum DESC LIMIT 30"

# ── 교차·답변불가 ─────────────────────────────────────────
G["CROSS-001"] = (f"""SELECT * FROM (
SELECT '국내ETF' AS grp, e.pd_abrv_nm AS name, e.du_er_1y AS ret_1y, h.as_of AS hold_as_of
FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code=e.pd_itm_no
WHERE e.{ETF} AND h.constituent='삼성전자' AND e.du_er_1y IS NOT NULL AND e.du_er_1y > -100 AND e.du_er_1y<>0
UNION ALL
SELECT '공모펀드', p.itm_nm, p.fd_yr1_ern_r, MAX(h.bas_dt)
FROM public_funds p JOIN ext_fund_holdings h ON h.grp=p.mtco_itm_no AND h.or_co=p.or_co_xtn_itt_cd
WHERE p.{FUND} AND h.holding_nm LIKE '%삼성전자%' AND p.fd_yr1_ern_r IS NOT NULL AND p.fd_yr1_ern_r > -100 AND p.fd_yr1_ern_r<>0
GROUP BY p.itm_no
) ORDER BY ret_1y DESC LIMIT 20""", "해외ETF 는 연수익률 미수록 — 주최 확정으로 순위에서 제외(병기도 하지 않음). Holdings 기준일 병기.")
G["CROSS-002"] = (G["ETF-D-014"][0].replace("cu_charge_rt AS fee FROM domestic_etfs", "CASE WHEN cu_charge_rt>0 THEN cu_charge_rt ELSE NULL END AS fee FROM domestic_etfs"),
                  "국내 총보수 0 = 미입력 → NULL 로 표시(대부분 미수록)")
G["CROSS-003"] = (f"""SELECT * FROM (
SELECT '국내ETF' AS grp, pd_abrv_nm AS name, pd_dvid_pay_months AS dist_info, du_last_aum AS aum FROM domestic_etfs
WHERE {ETF} AND pd_dvid_cycl='M' AND du_last_aum IS NOT NULL AND du_last_aum<>0 ORDER BY du_last_aum DESC LIMIT 5)
UNION ALL SELECT * FROM (
SELECT '공모펀드', itm_nm, CAST(fd_last_dstb_r AS TEXT), fd_nast_suma FROM public_funds
WHERE {FUND} AND fd_last_dstb_r>0 AND fd_nast_suma IS NOT NULL AND fd_nast_suma<>0 ORDER BY fd_nast_suma DESC LIMIT 5) LIMIT 10""",
    "ETF 월분배 = pd_dvid_cycl='M', 펀드 분배 = fd_last_dstb_r>0. 순자산 단위 KRW 동일")
G["UNANS-001"] = (None, "상품명 정확일치 0건 → 불가응답 또는 유사상품(KODEX 로봇액티브 등) 역질문")
G["UNANS-002"] = (None, "Gate② enum — AAAA 화이트리스트 밖")
G["UNANS-003"] = (None, "Gate③ cutoff — 2026년 10월 > 기준일 8/22")
G["UNANS-004"] = (None, "Gate① absent — RiskGrade × overseas_etfs")
G["UNANS-005"] = (None, "cu_charge_etc_rt 전부 0(미입력) → 모수 0건 불가응답")
G["UNANS-006"] = (None, "clarify — 기간·유형·개수 조건 역질문")

FILES = ["questions_official_sample", "questions_domestic_etfs", "questions_overseas_etfs", "questions_cross_and_unanswerable"]


def main():
    con = sqlite3.connect(f"file:{os.path.join(ROOT,'data','financial_products.db')}?mode=ro", uri=True)
    total = filled = 0
    for fn in FILES:
        path = os.path.join(ROOT, "eval", f"{fn}.jsonl")
        out = []
        n_f = n_t = 0
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            q = json.loads(line); n_t += 1
            spec = G[q["qid"]]
            sql, reason = (spec if isinstance(spec, tuple) else (spec, None))
            q["gold_as_of"] = AS_OF
            if sql:
                sql = " ".join(sql.split())
                err = validate_sql(sql)
                assert err is None, f"{q['qid']} guard: {err}"
                cur = con.execute(sql); cols = [d[0] for d in cur.description]; rows = cur.fetchall()
                q["gold_sql"] = sql; q["gold_rows"] = len(rows)
                q["gold_sample"] = [dict(zip(cols, [None if v is None else (round(v, 4) if isinstance(v, float) else v) for v in r])) for r in rows[:3]]
                n_f += 1
            else:
                q["gold_sql"] = None; q["gold_rows"] = None; q["gold_sample"] = None
            q["gold_reason"] = reason
            out.append(q)
        with open(path, "w", encoding="utf-8") as f:
            for q in out:
                f.write(json.dumps(q, ensure_ascii=False) + "\n")
        print(f"{fn}: gold_sql {n_f}/{n_t}")
        total += n_t; filled += n_f
    print(f"합계 gold_sql {filled}/{total}")


if __name__ == "__main__":
    main()
