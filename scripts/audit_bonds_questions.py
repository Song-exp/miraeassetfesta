# 질문 유형별 — 규칙대로 SQL 을 짜면 실제로 뭐가 나오나. 상위 결과의 이상치를 눈으로 본다.
import sqlite3, re, os
os.chdir(r"C:\Users\bella\Desktop\대학\공모전\트리플에이치\미래에셋")
c = sqlite3.connect("data/financial_products.db")
c.create_function("REGEXP", 2, lambda p, s: 1 if (s is not None and re.search(p, s)) else 0)
q = lambda s: c.execute(s).fetchall()
def show(title, sql, n=10):
    print(f"\n### {title}")
    print("   " + re.sub(r"\s+", " ", sql.strip())[:300])
    try:
        cur = c.execute(sql); cols = [d[0] for d in cur.description]; rows = cur.fetchmany(n)
        print("   | " + " | ".join(cols))
        for r in rows: print("   | " + " | ".join("" if v is None else (str(v).strip()[:34] if isinstance(v, str) else (f"{v:.3f}" if isinstance(v, float) else str(v))) for v in r))
    except Exception as e: print("   ERR", e)

# LIKE 기반 특수구조 플래그 (REGEXP 없는 런타임용) — 정규식 count 와 대조
FLAG_LIKE = {
 "콜": "(pd_nm LIKE '%(콜)%' OR pd_nm LIKE '%(콜/%' OR pd_nm LIKE '%/콜)%' OR pd_nm LIKE '%/콜/%')",
 "풋": "(pd_nm LIKE '%(풋)%' OR pd_nm LIKE '%(풋/%' OR pd_nm LIKE '%/풋)%' OR pd_nm LIKE '%/풋/%')",
 "후": "(pd_nm LIKE '%(후)%' OR pd_nm LIKE '%(후/%' OR pd_nm LIKE '%/후)%' OR pd_nm LIKE '%/후/%')",
 "전환": "(pd_nm LIKE '%(전환)%' OR pd_nm LIKE '%(전환/%' OR pd_nm LIKE '%/전환)%' OR pd_nm LIKE '%/전환/%')",
 "CB": "(pd_nm GLOB '*[0-9]CB*')", "EB": "(pd_nm GLOB '*[0-9]EB*')", "BW": "(pd_nm GLOB '*[0-9]BW*')",
 "신종영구": "(pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%')", "분리": "(pd_nm LIKE '%분리채권%')",
 "코코": "((pd_nm LIKE '%코코%' AND pd_nm NOT LIKE '%코코리아%') OR pd_nm LIKE '%조건부자본%')", "물가": "(pd_nm LIKE '%물가%')",
}
FLAG_RE = {"콜":"[(/]콜[)/]","풋":"[(/]풋[)/]","후":"[(/]후[)/]","전환":"[(/]전환[)/]","CB":r"\d+CB","EB":r"\d+EB","BW":r"\d+BW","신종영구":"신종|영구","분리":"분리채권","코코":"코코(?!리아)|조건부자본","물가":"물가"}
print("### LIKE 조건식 ↔ 정규식 count 대조")
for k in FLAG_LIKE:
    a = q(f"SELECT COUNT(*) FROM domestic_bonds WHERE {FLAG_LIKE[k]}")[0][0]; b = q(f"SELECT COUNT(*) FROM domestic_bonds WHERE pd_nm REGEXP '{FLAG_RE[k]}'")[0][0]
    print(f"   {k:<6} LIKE {a:>5} | REGEXP {b:>5} {'✅' if a==b else '❌'}")
SPECIAL = " OR ".join(FLAG_LIKE.values())
print("   특수구조 합집합(행):", q(f"SELECT COUNT(*), COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE {SPECIAL}"))
BASE = "curr_cd='KRW' AND CAST(mat_dt AS INT)>=20260822"
REC = f"{BASE} AND NOT ({SPECIAL}) AND bd_ofr_tcd<>'사모' AND NOT (pd_risk_gcd='11' OR TRIM(crd_grd)='C0')"
print("   추천 모수(구매가능·특수구조·사모·고위험 제외):", q(f"SELECT COUNT(*), COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE {REC}"))

show("Q1 수익률 높은 채권 추천 (추천 모수 · applied_yield)", f"SELECT TRIM(pd_nm) nm, applied_yield, TRIM(crd_grd) g, pd_risk_nm, TRIM(bd_knd) knd, eval_price, remaining_days FROM domestic_bonds WHERE {REC} AND applied_yield>0 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 10")
show("Q1b 같은 질문, 특수구조 제외 안 했을 때 (플래너가 플래그를 못 쓰면 이렇게 나옴)", f"SELECT TRIM(pd_nm) nm, applied_yield, TRIM(crd_grd) g, pd_risk_nm FROM domestic_bonds WHERE {BASE} AND bd_ofr_tcd<>'사모' AND NOT (pd_risk_gcd='11' OR TRIM(crd_grd)='C0') AND applied_yield>0 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 8")
show("Q2 안전한 채권 (국공채) 수익률 순", f"SELECT TRIM(pd_nm) nm, applied_yield, pd_risk_nm, remaining_days, TRIM(std_pd_scls_nm) s FROM domestic_bonds WHERE {REC} AND TRIM(std_pd_mcls_nm)='국공채' AND applied_yield>0 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 8")
show("Q3 듀레이션 짧은 채권 (금리위험 낮은)", f"SELECT TRIM(pd_nm) nm, dur, remaining_days, applied_yield, TRIM(crd_grd) g FROM domestic_bonds WHERE {REC} AND dur IS NOT NULL AND dur<>99 AND dur<>0 AND remaining_days>0 GROUP BY pd_no ORDER BY dur ASC LIMIT 8")
show("Q3b 듀레이션 긴 채권", f"SELECT TRIM(pd_nm) nm, dur, remaining_days/365.0 yrs, applied_yield FROM domestic_bonds WHERE {REC} AND dur IS NOT NULL AND dur<>99 AND dur<>0 GROUP BY pd_no ORDER BY dur DESC LIMIT 6")
show("Q4 만기 임박 채권 (잔존 30일 이내)", f"SELECT TRIM(pd_nm) nm, mat_dt, remaining_days, applied_yield, buy_yield FROM domestic_bonds WHERE {BASE} AND remaining_days>0 AND remaining_days<=30 GROUP BY pd_no ORDER BY remaining_days LIMIT 6")
show("Q5 표면금리 높은 채권 (고정·이표채만)", f"SELECT TRIM(pd_nm) nm, srfc_irt, bd_intp_tcd, bd_inrt_tcd, TRIM(crd_grd) g, pd_risk_nm, applied_yield FROM domestic_bonds WHERE {REC} AND bd_inrt_tcd='고정금리' AND bd_intp_tcd='이표채' AND srfc_irt>0 GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 8")
show("Q5b 표면금리 높은 채권 — 유형 분리 안 하면", f"SELECT TRIM(pd_nm) nm, srfc_irt, bd_intp_tcd, bd_inrt_tcd, TRIM(crd_grd) g FROM domestic_bonds WHERE {BASE} AND srfc_irt>0 GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 6")
show("Q6 지금 살 수 있는 채권 중 세후수익률 높은 것 (판매 LOT 634)", f"SELECT TRIM(pd_nm) nm, buy_yield, after_tax_yield, depo_equiv_yield_154, trade_price, TRIM(crd_grd) g, pd_risk_nm, remaining_days, info_seq FROM domestic_bonds WHERE buy_yield IS NOT NULL AND NOT ({SPECIAL}) ORDER BY after_tax_yield DESC LIMIT 8")
show("Q6b 판매 LOT 634 중 특수구조·사모·고위험 몇 개?", f"SELECT SUM({SPECIAL}) sp, SUM(bd_ofr_tcd='사모') pv, SUM(pd_risk_gcd='11' OR TRIM(crd_grd)='C0') hr, COUNT(*) n, COUNT(DISTINCT pd_no) pdno FROM domestic_bonds WHERE buy_yield IS NOT NULL")
show("Q7 퇴직연금에 담을 수 있는 채권 중 수익률 높은 것", f"SELECT TRIM(pd_nm) nm, applied_yield, TRIM(crd_grd) g, pd_risk_nm, TRIM(std_pd_mcls_nm) m FROM domestic_bonds WHERE {REC} AND pd_pen_tr_yn='Y' AND applied_yield>0 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 6")
show("Q8 발행사별 발행잔액 상위 (TRIM 후 집계)", "SELECT TRIM(pd_pbcm) issuer, COUNT(DISTINCT pd_no) n, ROUND(SUM(isu_bal_amt)/1e12,2) tril FROM (SELECT pd_no, pd_pbcm, MAX(isu_bal_amt) isu_bal_amt FROM domestic_bonds GROUP BY pd_no) GROUP BY TRIM(pd_pbcm) ORDER BY SUM(isu_bal_amt) DESC LIMIT 8")
show("Q8b 발행사명 '(주)' 위치 변종 — 같은 회사가 갈라지는 사례", "SELECT TRIM(pd_pbcm) a, COUNT(*) n FROM domestic_bonds WHERE TRIM(pd_pbcm) LIKE '%(주)%' GROUP BY 1 ORDER BY n DESC LIMIT 6")
show("Q8c 발행사 이름에 '(주)' 붙은 것 vs 안 붙은 같은 이름 (REPLACE 후 중복)", "SELECT REPLACE(REPLACE(TRIM(pd_pbcm),'(주)',''),' ','') k, COUNT(DISTINCT TRIM(pd_pbcm)) variants, GROUP_CONCAT(DISTINCT TRIM(pd_pbcm)) names FROM domestic_bonds WHERE pd_pbcm IS NOT NULL GROUP BY 1 HAVING variants>=2 ORDER BY variants DESC LIMIT 10")
show("Q9 채권 종류별 개수 (bd_knd TRIM)", "SELECT TRIM(bd_knd) knd, COUNT(DISTINCT pd_no) n FROM domestic_bonds WHERE TRIM(bd_knd)<>'' GROUP BY 1 ORDER BY n DESC LIMIT 32", 32)
show("Q9b 소분류 13종", "SELECT TRIM(std_pd_scls_nm) s, TRIM(std_pd_mcls_nm) m, COUNT(*) n FROM domestic_bonds GROUP BY 1,2 ORDER BY n DESC", 20)
show("Q10 OFFICIAL-001 판매 가능 원화채권 AA- 이상 (gold SQL 그대로)", "SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(crd_grd) AS crd_grd, mat_dt, applied_yield FROM domestic_bonds WHERE curr_cd='KRW' AND mat_dt > 20260822 AND TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-') GROUP BY pd_no ORDER BY mat_dt LIMIT 5", 5)
show("Q10b gold 의 mat_dt > 20260822 vs 규칙 >= 20260822 차이 (AA- 이상)", "SELECT SUM(CAST(mat_dt AS INT)=20260822) d0, SUM(CAST(mat_dt AS INT)>=20260822) ge, SUM(CAST(mat_dt AS INT)>20260822) gt FROM domestic_bonds WHERE curr_cd='KRW' AND TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-')")
show("Q11 장내 종가 있는 채권 최근 기준일 순", "SELECT TRIM(pd_nm) nm, exg_close_price, exg_close_yield, TRIM(exg_close_price_base_dt) dt FROM domestic_bonds WHERE exg_close_price>0 ORDER BY TRIM(exg_close_price_base_dt) DESC LIMIT 5", 5)
show("Q12 한국전력공사 채권 (pd_pbcm 정확일치 vs LIKE)", "SELECT SUM(TRIM(pd_pbcm)='한국전력공사') exact, SUM(pd_pbcm LIKE '%한국전력%') lk, SUM(pd_nm LIKE '%한국전력%') nm FROM domestic_bonds")
show("Q12b 위험등급 낮은(안전한) 채권 — '16' 이 정답. '11' 로 짜면?", "SELECT pd_risk_gcd, pd_risk_nm, COUNT(*) n, ROUND(AVG(applied_yield),2) avg_y FROM domestic_bonds GROUP BY 1,2 ORDER BY 1")
show("Q13 위험등급 6등급(매우낮은위험) 채권 수익률 상위", f"SELECT TRIM(pd_nm) nm, applied_yield, pd_risk_nm, TRIM(crd_grd) g, TRIM(std_pd_mcls_nm) m FROM domestic_bonds WHERE {REC} AND pd_risk_gcd='16' AND applied_yield>0 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 5", 5)
show("Q14 신용등급 BBB 이하 채권 (투기등급 포함) 개수", "SELECT TRIM(crd_grd) g, COUNT(DISTINCT pd_no) n, ROUND(AVG(applied_yield),2) y FROM domestic_bonds WHERE TRIM(crd_grd) IN ('BBB+','BBB0','BBB-','BB0','BB-','B+','B-','C0') GROUP BY 1")
show("Q15 잔존만기 구간별 (단기<1y/중기1~5y/장기>5y) 개수·평균수익률", f"SELECT CASE WHEN remaining_days<365 THEN '단기' WHEN remaining_days<=1825 THEN '중기' ELSE '장기' END k, COUNT(DISTINCT pd_no) n, ROUND(AVG(applied_yield),2) y FROM domestic_bonds WHERE {BASE} AND remaining_days>0 GROUP BY 1")
show("Q16 영구채 (신종·영구) — mat_dt 가 콜개시일", "SELECT TRIM(pd_nm) nm, mat_dt, remaining_days, dur, applied_yield, TRIM(crd_grd) g FROM domestic_bonds WHERE pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%' ORDER BY applied_yield DESC LIMIT 5", 5)
show("Q17 국고채 목록 수익률 (std_pd_scls_nm='국고채')", "SELECT TRIM(pd_nm) nm, srfc_irt, applied_yield, mat_dt, remaining_days FROM domestic_bonds WHERE TRIM(std_pd_scls_nm)='국고채' GROUP BY pd_no ORDER BY remaining_days LIMIT 5", 5)
show("Q18 발행일 2025년 채권 개수 / 발행일 결측", "SELECT SUM(CAST(isu_dt AS INT) BETWEEN 20250101 AND 20251231) y2025, SUM(isu_dt IS NULL OR CAST(isu_dt AS INT)=0) missing FROM domestic_bonds")
show("Q19 만기 2027년 채권 개수 (게이트가 막고 있는 질문)", "SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE CAST(mat_dt AS INT) BETWEEN 20270101 AND 20271231")
show("Q20 채권 총 개수 — COUNT(*) vs DISTINCT (대표행 규칙)", "SELECT COUNT(*) rows_, COUNT(DISTINCT pd_no) items FROM domestic_bonds")
show("Q21 카드채·캐피탈채 (bd_knd 실값)", "SELECT TRIM(bd_knd) k, COUNT(*) n FROM domestic_bonds WHERE TRIM(bd_knd) LIKE '%카드%' OR TRIM(bd_knd) LIKE '%할부%' OR TRIM(bd_knd) LIKE '%캐피탈%' OR TRIM(bd_knd) LIKE '%리스%' GROUP BY 1")
show("Q22 KG alias raw_value 패딩 여부 (pd_pbcm)", "SELECT SUM(raw_value<>TRIM(raw_value)) padded, COUNT(*) n, MIN(raw_value) sample FROM kg_alias WHERE table_name='domestic_bonds' AND column_name='pd_pbcm'")
show("Q23 예금환산 수익률 높은 것 (개인 15.4%)", "SELECT TRIM(pd_nm) nm, depo_equiv_yield_154, after_tax_yield, buy_yield, TRIM(crd_grd) g, pd_risk_nm FROM domestic_bonds WHERE depo_equiv_yield_154 IS NOT NULL ORDER BY depo_equiv_yield_154 DESC LIMIT 5", 5)
show("Q24 판매 LOT 중 위험등급·신용등급 분포", "SELECT pd_risk_nm, COUNT(*) n, MIN(TRIM(crd_grd)), MAX(TRIM(crd_grd)) FROM domestic_bonds WHERE buy_yield IS NOT NULL GROUP BY 1")
show("Q25 이름 검색 함정: '삼성' 들어간 채권 발행사", "SELECT TRIM(pd_pbcm) i, COUNT(*) n FROM domestic_bonds WHERE pd_pbcm LIKE '%삼성%' GROUP BY 1 ORDER BY n DESC LIMIT 8")

# ── 불일치 15건 상세 ──
print("\n\n===== 불일치 상세 =====")
show("M1 pen Y 인데 A- 미만 등급 15행", "SELECT TRIM(crd_grd) g, COUNT(*) n, GROUP_CONCAT(TRIM(pd_nm),' / ') FROM domestic_bonds WHERE pd_pen_tr_yn='Y' AND TRIM(crd_grd) IN ('BBB+','BBB0','BBB-','BB0','BB-','B+','B-','C0') GROUP BY 1")
show("M2 코코 187 등급 분포", "SELECT TRIM(crd_grd) g, COUNT(*) n FROM domestic_bonds WHERE pd_nm REGEXP '코코(?!리아)|조건부자본' GROUP BY 1 ORDER BY n DESC")
show("M3 corp_pretax/buy_yield 비율 분포", "SELECT ROUND(corp_pretax_yield/buy_yield,2) r, COUNT(*) n FROM domestic_bonds WHERE buy_yield>0 GROUP BY 1 ORDER BY 1 LIMIT 40", 40)
show("M4 corp_after/pretax 비율 분포", "SELECT ROUND(corp_after_tax_yield/corp_pretax_yield,2) r, COUNT(*) n FROM domestic_bonds WHERE corp_pretax_yield>0 GROUP BY 1 ORDER BY 1 LIMIT 40", 40)
show("M5 dur 최댓값 행", "SELECT TRIM(pd_nm), dur, remaining_days/365.0 FROM domestic_bonds WHERE dur<>99 ORDER BY dur DESC LIMIT 3", 3)
show("M6 이름 '변' LIKE 기준", "SELECT COUNT(*), SUM(bd_inrt_tcd='변동금리'), SUM(bd_inrt_tcd='고정+변동금리'), SUM(bd_inrt_tcd='고정금리') FROM domestic_bonds WHERE pd_nm LIKE '%변%'")
