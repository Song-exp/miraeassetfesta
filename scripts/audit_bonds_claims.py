# 채권 yaml 의 모든 수치 주장 → 2차 DB 재현. 불일치만 앞에 모아 출력.
import sqlite3, re, os, sys
os.chdir(r"C:\Users\bella\Desktop\대학\공모전\트리플에이치\미래에셋")
c = sqlite3.connect("data/financial_products.db")
c.create_function("REGEXP", 2, lambda p, s: 1 if (s is not None and re.search(p, s)) else 0)
q = lambda s: c.execute(s).fetchall()
one = lambda s: c.execute(s).fetchone()[0]

results = []  # (id, claim, expected, actual, ok)
def chk(id_, claim, sql, expected, tol=0.0):
    try:
        got = c.execute(sql).fetchone()
        got = got[0] if len(got) == 1 else tuple(got)
    except Exception as e:
        got = f"ERR {e}"
    if isinstance(expected, tuple):
        ok = isinstance(got, tuple) and len(got) == len(expected) and all(_eq(a, b, tol) for a, b in zip(got, expected))
    else:
        ok = _eq(got, expected, tol)
    results.append((id_, claim, expected, got, ok))
def _eq(a, b, tol):
    if a is None or b is None: return a == b
    try: return abs(float(a) - float(b)) <= tol
    except: return a == b

B = "FROM domestic_bonds"
# ── row_grain ─────────────────────────────────────────────
chk("RG-1", "행 21,882 · pd_no distinct 20,497", f"SELECT COUNT(*), COUNT(DISTINCT pd_no) {B}", (21882, 20497))
chk("RG-2", "중복 pd_no 1,078 (2행 772·3행 305·4행 1)", f"SELECT COUNT(*), SUM(n=2), SUM(n=3), SUM(n=4) FROM (SELECT pd_no, COUNT(*) n {B} GROUP BY pd_no HAVING n>=2)", (1078, 772, 305, 1))
chk("RG-3", "장내 17,746(pd_no 유일) · 장외 4,136(pd_no 3,828)", f"SELECT SUM(pd_exg_mkt='장내'), (SELECT COUNT(DISTINCT pd_no) {B} WHERE pd_exg_mkt='장내'), SUM(pd_exg_mkt='장외'), (SELECT COUNT(DISTINCT pd_no) {B} WHERE pd_exg_mkt='장외') {B}", (17746, 17746, 4136, 3828))
chk("RG-4", "중복 1,078 중 장내1+장외 1,077 · 장외 LOT 만 1", f"SELECT SUM(i=1 AND o>=1), SUM(i=0) FROM (SELECT pd_no, SUM(pd_exg_mkt='장내') i, SUM(pd_exg_mkt='장외') o {B} GROUP BY pd_no HAVING COUNT(*)>=2)", (1077, 1))
chk("RG-5", "info_base_dt 단일값 20260821", f"SELECT COUNT(DISTINCT info_base_dt), MIN(info_base_dt) {B}", (1, 20260821))
chk("RG-6", "eval_price 다른 중복 종목 8", f"SELECT COUNT(*) FROM (SELECT pd_no {B} GROUP BY pd_no HAVING COUNT(*)>=2 AND COUNT(DISTINCT eval_price)>1)", 8)
chk("RG-7", "값 같은 중복 종목 1,069 (1,078-8-1?)", f"SELECT COUNT(*) FROM (SELECT pd_no {B} GROUP BY pd_no HAVING COUNT(*)>=2 AND COUNT(DISTINCT eval_price)=1)", 1070)
# ── 식별 ─────────────────────────────────────────────
chk("C-pd_nm-1", "패딩 684행", f"SELECT SUM(pd_nm<>TRIM(pd_nm)) {B}", 684)
chk("C-pd_nm-2", "distinct TRIM 이름 20,499", f"SELECT COUNT(DISTINCT TRIM(pd_nm)) {B}", 20499)
chk("C-pd_nm-3", "'(사)' 1,984행 중 공모 1,981", f"SELECT COUNT(*), SUM(bd_ofr_tcd='공모') {B} WHERE pd_nm LIKE '%(사)%'", (1984, 1981))
chk("C-pd_nm-4", "'(사)' 특수채 1,683", f"SELECT COUNT(*) {B} WHERE pd_nm LIKE '%(사)%' AND std_pd_mcls_nm='특수채'", 1683)
chk("C-abrv", "약어명 NULL 12 + 빈 2", f"SELECT SUM(pd_abrv_nm IS NULL), SUM(pd_abrv_nm IS NOT NULL AND TRIM(pd_abrv_nm)='') {B}", (12, 2))
chk("C-eng", "영문명 NULL 3 + 빈 2", f"SELECT SUM(pd_eng_nm IS NULL), SUM(pd_eng_nm IS NOT NULL AND TRIM(pd_eng_nm)='') {B}", (3, 2))
chk("C-abrveng", "영문약어 NULL 12 + 빈 2", f"SELECT SUM(pd_abrv_eng_nm IS NULL), SUM(pd_abrv_eng_nm IS NOT NULL AND TRIM(pd_abrv_eng_nm)='') {B}", (12, 2))
chk("C-ctry", "KR 21,881 · XS 1", f"SELECT SUM(TRIM(pd_ctry_cd)='KR'), SUM(TRIM(pd_ctry_cd)='XS') {B}", (21881, 1))
# ── 분류 ─────────────────────────────────────────────
chk("C-mcls", "회사채 12,865 · 특수채 6,177 · 국공채 2,840 · distinct 3", f"SELECT SUM(TRIM(std_pd_mcls_nm)='회사채'), SUM(TRIM(std_pd_mcls_nm)='특수채'), SUM(TRIM(std_pd_mcls_nm)='국공채'), COUNT(DISTINCT TRIM(std_pd_mcls_nm)) {B}", (12865, 6177, 2840, 3))
chk("C-scls-1", "소분류 13종 · NULL 0", f"SELECT COUNT(DISTINCT TRIM(std_pd_scls_nm)), SUM(std_pd_scls_nm IS NULL OR TRIM(std_pd_scls_nm)='') {B}", (13, 0))
chk("C-scls-2", "일반사채 회사채 12,133 / 특수채 614", f"SELECT SUM(TRIM(std_pd_mcls_nm)='회사채'), SUM(TRIM(std_pd_mcls_nm)='특수채') {B} WHERE TRIM(std_pd_scls_nm)='일반사채'", (12133, 614))
chk("C-scls-3", "특수은행채 특수채 1,322 / 회사채 2", f"SELECT SUM(TRIM(std_pd_mcls_nm)='특수채'), SUM(TRIM(std_pd_mcls_nm)='회사채') {B} WHERE TRIM(std_pd_scls_nm)='특수은행채'", (1322, 2))
chk("C-scls-4", "국고채 371·국민주택 210·지역개발 1,679·도시철도 452·물가채 6·중앙은행채 33", f"SELECT SUM(TRIM(std_pd_scls_nm)='국고채'), SUM(TRIM(std_pd_scls_nm)='국민주택'), SUM(TRIM(std_pd_scls_nm)='지역개발'), SUM(TRIM(std_pd_scls_nm)='도시철도'), SUM(TRIM(std_pd_scls_nm)='물가채'), SUM(TRIM(std_pd_scls_nm)='중앙은행채') {B}", (371, 210, 1679, 452, 6, 33))
chk("C-bdknd-1", "bd_knd 결측 152 · distinct 32", f"SELECT SUM(bd_knd IS NULL OR TRIM(bd_knd)=''), COUNT(DISTINCT CASE WHEN TRIM(bd_knd)<>'' THEN TRIM(bd_knd) END) {B}", (152, 32))
chk("C-bdknd-2", "통화안정채권 33 · MBS 1,396 · 유동화회사채 1,528 · Conduit 1,025", f"SELECT SUM(TRIM(bd_knd)='통화안정채권'), SUM(TRIM(bd_knd)='MBS'), SUM(TRIM(bd_knd)='유동화회사채'), SUM(TRIM(bd_knd)='Conduit회사채') {B}", (33, 1396, 1528, 1025))
chk("C-bdknd-3", "bd_knd 결측 ∩ pd_pbcm 결측 149", f"SELECT COUNT(*) {B} WHERE (bd_knd IS NULL OR TRIM(bd_knd)='') AND (pd_pbcm IS NULL OR TRIM(pd_pbcm)='')", 149)
chk("C-bdknd-4", "분리채권 209 전부 할인채", f"SELECT COUNT(*), SUM(bd_intp_tcd='할인채') {B} WHERE pd_nm LIKE '%분리채권%'", (209, 209))
# ── 발행자·시장 ─────────────────────────────────────────────
chk("C-pbcm-1", "pd_pbcm 결측 149 · raw distinct 1,837 · TRIM 1,818", f"SELECT SUM(pd_pbcm IS NULL OR TRIM(pd_pbcm)=''), COUNT(DISTINCT pd_pbcm), COUNT(DISTINCT TRIM(pd_pbcm)) {B}", (149, 1837, 1818))
chk("C-pbcm-2", "유동화 3종 3,949", f"SELECT COUNT(*) {B} WHERE TRIM(bd_knd) IN ('MBS','유동화회사채','Conduit회사채')", 3949)
chk("C-pbcm-3", "유동화 조건식 전체 4,045 · 그중 AAA 3,198", f"SELECT COUNT(*), SUM(TRIM(crd_grd)='AAA') {B} WHERE TRIM(bd_knd) IN ('MBS','유동화회사채','Conduit회사채') OR pd_pbcm LIKE '%유동화%' OR pd_pbcm LIKE '%신용보증%' OR pd_pbcm LIKE '%기술보증%' OR pd_nm LIKE '%유동화%'", (4045, 3198))
chk("C-mkt-1", "장외 avg applied_yield 8.59(>0 한정) · 장내 4.13", f"SELECT ROUND(AVG(CASE WHEN pd_exg_mkt='장외' AND applied_yield>0 THEN applied_yield END),2), ROUND(AVG(CASE WHEN pd_exg_mkt='장내' THEN applied_yield END),2) {B}", (8.59, 4.13), 0.01)
chk("C-mkt-2", "사모 1,981행 전부 장외?  (yaml pd_exg_mkt.trap 는 1,981 · bd_ofr_tcd 는 2,007)", f"SELECT COUNT(*), SUM(pd_exg_mkt='장외') {B} WHERE bd_ofr_tcd='사모'", (2007, 2007))
chk("C-curr", "KRW 21,881 · '000' 1", f"SELECT SUM(TRIM(curr_cd)='KRW'), SUM(TRIM(curr_cd)='000') {B}", (21881, 1))
# ── 발행조건 ─────────────────────────────────────────────
chk("C-intp-1", "이표 18,059·복리 2,867·할인 689·단리 267", f"SELECT SUM(bd_intp_tcd='이표채'), SUM(bd_intp_tcd='복리채'), SUM(bd_intp_tcd='할인채'), SUM(bd_intp_tcd='단리채') {B}", (18059, 2867, 689, 267))
chk("C-intp-2", "할인채 중 srfc_irt>0 668 · 이름 '할인' 50", f"SELECT SUM(srfc_irt>0), SUM(pd_nm LIKE '%할인%') {B} WHERE bd_intp_tcd='할인채'", (668, 50))
chk("C-inrt", "고정 20,904·변동 830·고정+변동 148", f"SELECT SUM(bd_inrt_tcd='고정금리'), SUM(bd_inrt_tcd='변동금리'), SUM(bd_inrt_tcd='고정+변동금리') {B}", (20904, 830, 148))
chk("C-inrt-2", "고정+변동 148: 신종·영구·후순위 0 · 사모 76 · 콜 26", f"SELECT SUM(pd_nm REGEXP '신종|영구|[(/]후[)/]'), SUM(bd_ofr_tcd='사모'), SUM(pd_nm REGEXP '[(/]콜[)/]') {B} WHERE bd_inrt_tcd='고정+변동금리'", (0, 76, 26))
chk("C-inrt-3", "이름 '변' 431행(LIKE '%변%'): 변동 393 · 고정+변동 37 · 고정 1", f"SELECT COUNT(*), SUM(bd_inrt_tcd='변동금리'), SUM(bd_inrt_tcd='고정+변동금리'), SUM(bd_inrt_tcd='고정금리') {B} WHERE pd_nm LIKE '%변%'", (431, 393, 37, 1))
chk("C-ofr-1", "공모 19,875 · 사모 2,007 · 사모 전부 장외 · 사모 pen N 전부", f"SELECT SUM(bd_ofr_tcd='공모'), SUM(bd_ofr_tcd='사모'), SUM(bd_ofr_tcd='사모' AND pd_exg_mkt='장외'), SUM(bd_ofr_tcd='사모' AND pd_pen_tr_yn='N') {B}", (19875, 2007, 2007, 2007))
chk("C-ofr-2", "이름 '사모' 1,981 전부 사모 · 사모인데 이름에 없음 26", f"SELECT SUM(pd_nm LIKE '%사모%'), SUM(pd_nm LIKE '%사모%' AND bd_ofr_tcd='사모'), SUM(bd_ofr_tcd='사모' AND pd_nm NOT LIKE '%사모%') {B}", (1981, 1981, 26))
chk("C-srfc-1", "srfc NULL 1 · 0값 579 (이표 499·복리 57·할인 21·단리 2)", f"SELECT SUM(srfc_irt IS NULL), SUM(srfc_irt=0), SUM(srfc_irt=0 AND bd_intp_tcd='이표채'), SUM(srfc_irt=0 AND bd_intp_tcd='복리채'), SUM(srfc_irt=0 AND bd_intp_tcd='할인채'), SUM(srfc_irt=0 AND bd_intp_tcd='단리채') {B}", (1, 579, 499, 57, 21, 2))
chk("C-srfc-2", "srfc=0 중 CB 이름 324 · 주식연계 합계 488", f"SELECT SUM(pd_nm REGEXP '\\d+CB|[(/]전환[)/]'), SUM(pd_nm REGEXP '\\d+CB|[(/]전환[)/]|\\d+EB|\\d+BW|교환|신주') {B} WHERE srfc_irt=0", (324, 488))
chk("C-isudt", "isu_dt 0값 25 · NULL 1", f"SELECT SUM(isu_dt='0' OR isu_dt=0), SUM(isu_dt IS NULL) {B}", (25, 1))
chk("C-matdt-1", "mat_dt 0값 4 · NULL 1", f"SELECT SUM(mat_dt='0' OR mat_dt=0), SUM(mat_dt IS NULL) {B}", (4, 1))
chk("C-matdt-2", "만기 경과(≤20260821) 49 · 미경과(≥20260822) 21,828", f"SELECT SUM(CAST(mat_dt AS INT) BETWEEN 1 AND 20260821), SUM(CAST(mat_dt AS INT)>=20260822) {B}", (49, 21828))
chk("C-matdt-3", "8/22 만기 7행 · remaining_days=1", f"SELECT COUNT(*), SUM(remaining_days=1) {B} WHERE CAST(mat_dt AS INT)=20260822", (7, 7))
chk("C-isubal", "isu_bal 0값 325 · max 46.50조", f"SELECT SUM(isu_bal_amt=0), ROUND(MAX(isu_bal_amt)/1e12,2) {B}", (325, 46.50), 0.01)
chk("C-tisu", "bd_tisu_a 0값 259 · =잔액 18,704 · >잔액 2,949", f"SELECT SUM(bd_tisu_a=0), SUM(bd_tisu_a=isu_bal_amt), SUM(bd_tisu_a>isu_bal_amt) {B}", (259, 18704, 2949))
chk("C-tcd-1", "exrt tcd 99 21,338·01 49·02 264·03 3·04 226·05 2", f"SELECT SUM(exrt_grte_ern_r_tcd='99'), SUM(exrt_grte_ern_r_tcd='01'), SUM(exrt_grte_ern_r_tcd='02'), SUM(exrt_grte_ern_r_tcd='03'), SUM(exrt_grte_ern_r_tcd='04'), SUM(exrt_grte_ern_r_tcd='05') {B}", (21338, 49, 264, 3, 226, 2))
chk("C-tcd-2", "02 >0 184 · 04 >0 30 · tcd<>99 544 중 주식연계 538", f"SELECT SUM(exrt_grte_ern_r_tcd='02' AND exrt_grte_ern_r>0), SUM(exrt_grte_ern_r_tcd='04' AND exrt_grte_ern_r>0), SUM(exrt_grte_ern_r_tcd<>'99'), SUM(exrt_grte_ern_r_tcd<>'99' AND pd_nm REGEXP 'CB|EB|BW|전환|교환|신주') {B}", (184, 30, 544, 538))
chk("C-exrt", "exrt_grte_ern_r 0값 21,626 · >0 256 · tcd=99 & >0 4", f"SELECT SUM(exrt_grte_ern_r=0), SUM(exrt_grte_ern_r>0), SUM(exrt_grte_ern_r_tcd='99' AND exrt_grte_ern_r>0) {B}", (21626, 256, 4))
chk("C-rpy", "exrt_rpy_r =100 21,642 · <>100 240 · 0값 1 · max 779.7", f"SELECT SUM(exrt_rpy_r=100), SUM(exrt_rpy_r<>100), SUM(exrt_rpy_r=0), ROUND(MAX(exrt_rpy_r),1) {B}", (21642, 240, 1, 779.7), 0.1)
# ── 신용·위험등급 ─────────────────────────────────────────────
chk("C-crd-1", "crd 결측 4,020 (국공채 2,840·특수채 254·회사채 926) · 유효 17,862 · distinct 15", f"SELECT SUM(crd_grd IS NULL OR TRIM(crd_grd)=''), SUM((crd_grd IS NULL OR TRIM(crd_grd)='') AND TRIM(std_pd_mcls_nm)='국공채'), SUM((crd_grd IS NULL OR TRIM(crd_grd)='') AND TRIM(std_pd_mcls_nm)='특수채'), SUM((crd_grd IS NULL OR TRIM(crd_grd)='') AND TRIM(std_pd_mcls_nm)='회사채'), SUM(crd_grd IS NOT NULL AND TRIM(crd_grd)<>''), COUNT(DISTINCT CASE WHEN TRIM(crd_grd)<>'' THEN TRIM(crd_grd) END) {B}", (4020, 2840, 254, 926, 17862, 15))
for g, n in [("AAA",8722),("AA+",2543),("AA0",1241),("AA-",3530),("A+",678),("A0",737),("A-",124),("BBB+",109),("BBB0",45),("BBB-",7),("BB0",13),("BB-",3),("B+",2),("B-",5),("C0",103)]:
    chk(f"C-crd-{g}", f"crd {g} = {n} (yaml value_semantics)", f"SELECT COUNT(*) {B} WHERE TRIM(crd_grd)='{g}'", n)
chk("C-crd-x", "위험11 중 AAA 1 · 무등급 921", f"SELECT SUM(TRIM(crd_grd)='AAA'), SUM(crd_grd IS NULL OR TRIM(crd_grd)='') {B} WHERE pd_risk_gcd='11'", (1, 921))
chk("C-crddt", "crd_grd_dt 0값 1 · 유효 17,875 · max 20260821 · 등급일만 있고 등급 없음 16", f"SELECT SUM(crd_grd_dt='0' OR crd_grd_dt=0), SUM(crd_grd_dt IS NOT NULL AND crd_grd_dt<>'0' AND crd_grd_dt<>0), MAX(CAST(crd_grd_dt AS INT)), SUM(crd_grd_dt IS NOT NULL AND crd_grd_dt<>'0' AND crd_grd_dt<>0 AND (crd_grd IS NULL OR TRIM(crd_grd)='')) {B}", (1, 17875, 20260821, 16))
chk("C-risk-1", "위험 00 19·11 1,441·12 74·13 146·14 1,424·15 9,849·16 8,929", f"SELECT SUM(pd_risk_gcd='00'), SUM(pd_risk_gcd='11'), SUM(pd_risk_gcd='12'), SUM(pd_risk_gcd='13'), SUM(pd_risk_gcd='14'), SUM(pd_risk_gcd='15'), SUM(pd_risk_gcd='16') {B}", (19, 1441, 74, 146, 1424, 9849, 8929))
chk("C-risk-2", "11 회사채 1,415 · 14 전부 회사채 · 15 전부 회사채 · 16 국공채 2,839·특수채 6,090", f"SELECT SUM(pd_risk_gcd='11' AND TRIM(std_pd_mcls_nm)='회사채'), SUM(pd_risk_gcd='14' AND TRIM(std_pd_mcls_nm)<>'회사채'), SUM(pd_risk_gcd='15' AND TRIM(std_pd_mcls_nm)<>'회사채'), SUM(pd_risk_gcd='16' AND TRIM(std_pd_mcls_nm)='국공채'), SUM(pd_risk_gcd='16' AND TRIM(std_pd_mcls_nm)='특수채') {B}", (1415, 0, 0, 2839, 6090))
chk("C-risk-3", "pd_risk_nm distinct 7 · gcd↔nm 1:1 · NULL 0", f"SELECT COUNT(DISTINCT pd_risk_nm), COUNT(DISTINCT pd_risk_gcd||'|'||pd_risk_nm), SUM(pd_risk_gcd IS NULL) {B}", (7, 7, 0))
# ── 위험지표 ─────────────────────────────────────────────
chk("C-dur-1", "dur NULL 16 · 99 3 · 0 52 (만기도래 48 · 잔존>0 4) · max 46.4", f"SELECT SUM(dur IS NULL), SUM(dur=99), SUM(dur=0), SUM(dur=0 AND remaining_days=0), SUM(dur=0 AND remaining_days>0), ROUND(MAX(CASE WHEN dur<>99 THEN dur END),1) {B}", (16, 3, 52, 48, 4, 46.4), 0.1)
chk("C-dur-2", "평균 dur(0·99 제외) 국공채 3.97 > 특수채 3.91 > 회사채 1.99", f"SELECT ROUND(AVG(CASE WHEN TRIM(std_pd_mcls_nm)='국공채' THEN dur END),2), ROUND(AVG(CASE WHEN TRIM(std_pd_mcls_nm)='특수채' THEN dur END),2), ROUND(AVG(CASE WHEN TRIM(std_pd_mcls_nm)='회사채' THEN dur END),2) {B} WHERE dur<>99 AND dur>0", (3.97, 3.91, 1.99), 0.02)
chk("C-dur-3", "이론 위반 dur > 잔존/365+0.1 : 198", f"SELECT COUNT(*) {B} WHERE dur IS NOT NULL AND dur<>99 AND remaining_days IS NOT NULL AND dur > remaining_days/365.0 + 0.1", 198)
chk("C-dur-4", "만기 경과인데 dur<>0 : 1 (아우딘퓨쳐스)", f"SELECT COUNT(*) {B} WHERE remaining_days=0 AND dur IS NOT NULL AND dur<>0", 1)
chk("C-cov", "cov 0값 102 · NULL 16 (=dur NULL)", f"SELECT SUM(cov=0), SUM(cov IS NULL), SUM(cov IS NULL AND dur IS NULL) {B}", (102, 16, 16))
chk("C-ndydur", "ndy_dur 0값 72 · dur>0인데 0 : 20 · 99 3 · dur 과 상이 21,428", f"SELECT SUM(ndy_dur=0), SUM(ndy_dur=0 AND dur>0), SUM(ndy_dur=99), SUM(ndy_dur<>dur) {B}", (72, 20, 3, 21428))
chk("C-ndycov", "ndy_cov 0값 121 · cov>0인데 0 : 20 · cov 와 상이 21,633", f"SELECT SUM(ndy_cov=0), SUM(ndy_cov=0 AND cov>0), SUM(ndy_cov<>cov) {B}", (121, 20, 21633))
chk("C-rd-1", "remaining_days 0 49 · NULL 5 · max 20,742 · 유효(>0) 21,828", f"SELECT SUM(remaining_days=0), SUM(remaining_days IS NULL), MAX(remaining_days), SUM(remaining_days>0) {B}", (49, 5, 20742, 21828))
chk("C-rd-2", "rd=0 ↔ mat_dt≤20260821 대칭차 0 · 만기 미래인데 0 : 0", f"SELECT SUM((remaining_days=0) <> (CAST(mat_dt AS INT) BETWEEN 1 AND 20260821)), SUM(remaining_days=0 AND CAST(mat_dt AS INT)>=20260822) {B} WHERE mat_dt IS NOT NULL AND remaining_days IS NOT NULL", (0, 0))
chk("C-rd-3", "rd=0 49행 판매 6컬럼 적중 0", f"SELECT SUM(buy_yield IS NOT NULL), SUM(bdbns_abl_chnl_tcd IS NOT NULL), SUM(buyable_quantity IS NOT NULL), SUM(sale_yield_base_dt IS NOT NULL) {B} WHERE remaining_days=0", (0, 0, 0, 0))
chk("C-rd-4", "만기 임박 ≤30일 (rd>0) 578", f"SELECT COUNT(*) {B} WHERE remaining_days>0 AND remaining_days<=30", 578)
# ── 가격 ─────────────────────────────────────────────
chk("C-ep-1", "eval_price NULL 0 · 1,112.06~49,493.53 · =10000 21 (만기 전 18)", f"SELECT SUM(eval_price IS NULL), ROUND(MIN(eval_price),2), ROUND(MAX(eval_price),2), SUM(eval_price=10000), SUM(eval_price=10000 AND remaining_days>0) {B}", (0, 1112.06, 49493.53, 21, 18), 0.01)
chk("C-ay-1", "applied_yield 0값 201 (주식연계 189·만기경과 4) · NULL 0", f"SELECT SUM(applied_yield=0), SUM(applied_yield=0 AND pd_nm REGEXP 'CB|EB|BW|전환|교환|신주'), SUM(applied_yield=0 AND remaining_days=0), SUM(applied_yield IS NULL) {B}", (201, 189, 4, 0))
chk("C-dirty", "dirty NULL 16 · =eval_price 21,655 / 21,866", f"SELECT SUM(dirty IS NULL), SUM(dirty=eval_price), SUM(dirty IS NOT NULL) {B}", (16, 21655, 21866))
chk("C-ndyep", "ndy_eval_price 0값(원본>0) 16 · =eval 34", f"SELECT SUM(ndy_eval_price=0 AND eval_price>0), SUM(ndy_eval_price=eval_price) {B}", (16, 34))
chk("C-ndyay", "ndy_applied_yield =applied 21,817 (yaml 정정 완료) · 위장결측 15", f"SELECT SUM(ndy_applied_yield=applied_yield), SUM(ndy_applied_yield=0 AND applied_yield>0) {B}", (21817, 15))
chk("C-ndydirty", "ndy_dirty =ndy_eval 21,617 · =dirty 34", f"SELECT SUM(ndy_dirty=ndy_eval_price), SUM(ndy_dirty=dirty) {B}", (21617, 34))
chk("C-exg-1", "장외 NULL 4,136 · 장내 0값 16,476 · >0 1,270 · 2,511~10,135", f"SELECT SUM(exg_close_price IS NULL AND pd_exg_mkt='장외'), SUM(exg_close_price=0 AND pd_exg_mkt='장내'), SUM(exg_close_price>0), ROUND(MIN(CASE WHEN exg_close_price>0 THEN exg_close_price END)), ROUND(MAX(exg_close_price)) {B}", (4136, 16476, 1270, 2511, 10135), 1)
chk("C-exg-2", "종가 기준일 연도 2026 158·2025 252·2024 253·2023 251·2022 250·2021 90·2020 12·2019 4", f"SELECT SUM(SUBSTR(TRIM(exg_close_price_base_dt),1,4)='2026'), SUM(SUBSTR(TRIM(exg_close_price_base_dt),1,4)='2025'), SUM(SUBSTR(TRIM(exg_close_price_base_dt),1,4)='2024'), SUM(SUBSTR(TRIM(exg_close_price_base_dt),1,4)='2023'), SUM(SUBSTR(TRIM(exg_close_price_base_dt),1,4)='2022'), SUM(SUBSTR(TRIM(exg_close_price_base_dt),1,4)='2021'), SUM(SUBSTR(TRIM(exg_close_price_base_dt),1,4)='2020'), SUM(SUBSTR(TRIM(exg_close_price_base_dt),1,4)='2019') {B} WHERE exg_close_price>0", (158, 252, 253, 251, 250, 90, 12, 4))
chk("C-exg-3", "exg_close_yield 유효 1,269 · base_dt 공백 16,453 · distinct 100 · 종가>0&공백 0", f"SELECT SUM(exg_close_yield>0), SUM(exg_close_price_base_dt IS NOT NULL AND TRIM(exg_close_price_base_dt)=''), COUNT(DISTINCT TRIM(exg_close_price_base_dt)), SUM(exg_close_price>0 AND (exg_close_price_base_dt IS NULL OR TRIM(exg_close_price_base_dt)='')) {B}", (1269, 16453, 100, 0))
# ── 판매 LOT ─────────────────────────────────────────────
chk("C-seq", "info_seq 1 21,574 · 2 307 · 3 1", f"SELECT SUM(info_seq=1), SUM(info_seq=2), SUM(info_seq=3) {B}", (21574, 307, 1))
chk("C-buy-1", "buy_yield 634 · 전부 장외 · 전부 미경과 · 2.08~5.29", f"SELECT COUNT(buy_yield), SUM(buy_yield IS NOT NULL AND pd_exg_mkt='장외'), SUM(buy_yield IS NOT NULL AND CAST(mat_dt AS INT)>=20260822), ROUND(MIN(buy_yield),2), ROUND(MAX(buy_yield),2) {B}", (634, 634, 634, 2.08, 5.29), 0.01)
chk("C-buy-2", "LOT 2개 종목 307", f"SELECT COUNT(*) FROM (SELECT pd_no {B} WHERE buy_yield IS NOT NULL GROUP BY pd_no HAVING COUNT(*)>=2)", 307)
chk("C-atx", "after_tax 634 · =depo154×0.846 634 · 세후>매수 72", f"SELECT COUNT(after_tax_yield), SUM(ABS(after_tax_yield - depo_equiv_yield_154*0.846) < 0.01), SUM(after_tax_yield > buy_yield) {B}", (634, 634, 72))
chk("C-corp", "corp 634 · pretax/buy 0.61~1.31 · after=pretax 31 · after/pretax 0.75~1.00", f"SELECT COUNT(corp_pretax_yield), ROUND(MIN(corp_pretax_yield/buy_yield),2), ROUND(MAX(corp_pretax_yield/buy_yield),2), SUM(corp_after_tax_yield=corp_pretax_yield), ROUND(MIN(corp_after_tax_yield/corp_pretax_yield),2), ROUND(MAX(corp_after_tax_yield/corp_pretax_yield),2) {B}", (634, 0.61, 1.31, 31, 0.75, 1.00), 0.01)
chk("C-pref", "pref_tax 634 · =after_tax 4", f"SELECT COUNT(pref_tax_yield), SUM(pref_tax_yield=after_tax_yield) {B}", (634, 4))
chk("C-avgtax", "avg_annual_tax non-null 634 전부 0", f"SELECT COUNT(avg_annual_tax_yield), SUM(avg_annual_tax_yield=0) {B}", (634, 634))
chk("C-depo", "depo154 634 · depo495 634 1.26~9.48 · 495>154 598", f"SELECT COUNT(depo_equiv_yield_154), COUNT(depo_equiv_yield_495), ROUND(MIN(depo_equiv_yield_495),2), ROUND(MAX(depo_equiv_yield_495),2), SUM(depo_equiv_yield_495>depo_equiv_yield_154) {B}", (634, 634, 1.26, 9.48, 598), 0.01)
chk("C-tp", "trade_price 634 · 5,570~10,759 · =eval 0 · ±50 이내 497", f"SELECT COUNT(trade_price), ROUND(MIN(trade_price)), ROUND(MAX(trade_price)), SUM(trade_price=eval_price), SUM(ABS(trade_price-eval_price)<=50) {B}", (634, 5570, 10759, 0, 497), 1)
chk("C-bq", "buyable_quantity >0 296 · =0 338 · 1,000배수 · ≤잔액", f"SELECT SUM(buyable_quantity>0), SUM(buyable_quantity=0), SUM(buyable_quantity>0 AND CAST(buyable_quantity AS INT)%1000<>0), SUM(buyable_quantity>isu_bal_amt) {B}", (296, 338, 0, 0))
chk("C-chnl", "채널 '온오프 겸용' 634 · tcd 0 634 · sale_yield_base_dt 20260821 634", f"SELECT SUM(TRIM(bdbns_abl_chnl_nm)='온오프 겸용'), SUM(CAST(bdbns_abl_chnl_tcd AS INT)=0), SUM(CAST(sale_yield_base_dt AS INT)=20260821) {B}", (634, 634, 634))
chk("C-upd", "pd_std_info_update 전 행 20260821", f"SELECT SUM(CAST(pd_std_info_update AS INT)=20260821) {B}", 21882)
chk("C-pen-1", "pen Y 1,931 (국공채 1,522·회사채 314·특수채 95) · N 19,951", f"SELECT SUM(pd_pen_tr_yn='Y'), SUM(pd_pen_tr_yn='Y' AND TRIM(std_pd_mcls_nm)='국공채'), SUM(pd_pen_tr_yn='Y' AND TRIM(std_pd_mcls_nm)='회사채'), SUM(pd_pen_tr_yn='Y' AND TRIM(std_pd_mcls_nm)='특수채'), SUM(pd_pen_tr_yn='N') {B}", (1931, 1522, 314, 95, 19951))
chk("C-pen-2", "pen Y 전부 공모 · 무등급 1,524 · A- 미만 15 (BBB+ — 'A- 이상' 아님)", f"SELECT SUM(bd_ofr_tcd<>'공모'), SUM(crd_grd IS NULL OR TRIM(crd_grd)=''), SUM(TRIM(crd_grd) IN ('BBB+','BBB0','BBB-','BB0','BB-','B+','B-','C0')) {B} WHERE pd_pen_tr_yn='Y'", (0, 1524, 15))
# ── name_encoding ─────────────────────────────────────────────
chk("N-isin", "KR6 12,834·KR3 6,180·KR2 2,239·KR1 392·KRC 209·KRB 27·XS3 1", f"SELECT SUM(SUBSTR(pd_no,1,3)='KR6'), SUM(SUBSTR(pd_no,1,3)='KR3'), SUM(SUBSTR(pd_no,1,3)='KR2'), SUM(SUBSTR(pd_no,1,3)='KR1'), SUM(SUBSTR(pd_no,1,3)='KRC'), SUM(SUBSTR(pd_no,1,3)='KRB'), SUM(SUBSTR(pd_no,1,3)='XS3') {B}", (12834, 6180, 2239, 392, 209, 27, 1))
chk("N-isin-2", "KR3 중 회사채 3 · KR6 전부 회사채", f"SELECT SUM(SUBSTR(pd_no,1,3)='KR3' AND TRIM(std_pd_mcls_nm)='회사채'), SUM(SUBSTR(pd_no,1,3)='KR6' AND TRIM(std_pd_mcls_nm)<>'회사채') {B}", (3, 0))
for fid, pat, n in [("is_callable","[(/]콜[)/]",2673),("is_puttable","[(/]풋[)/]",529),("is_convertible",r"\d+CB|[(/]전환[)/]",389),("is_subordinated","[(/]후[)/]",530),("is_perpetual","신종|영구",266),("is_exchangeable",r"\d+EB",137),("is_stripped","분리채권",209),("is_bw",r"\d+BW",32),("is_coco","코코(?!리아)|조건부자본",187),("is_inflation_linked","물가",6),("unresolved_PB",r"\d+PB",0)]:
    chk(f"N-{fid}", f"{fid} count {n}", f"SELECT COUNT(*) {B} WHERE pd_nm REGEXP '{pat}'", n)
chk("N-perp-pdno", "is_perpetual pd_no 237", f"SELECT COUNT(DISTINCT pd_no) {B} WHERE pd_nm REGEXP '신종|영구'", 237)
chk("N-coco-grade", "코코(옛 정규식) 187 — AA급 179 · 무등급 1 (전부 AA 아님)", f"SELECT COUNT(*), SUM(TRIM(crd_grd) LIKE 'AA%'), SUM(crd_grd IS NULL OR TRIM(crd_grd)='') {B} WHERE pd_nm REGEXP '코코(?!리아)|조건부자본'", (187, 179, 1))
chk("N-infl", "물가 6 = 물가채 6", f"SELECT SUM(pd_nm LIKE '%물가%' AND TRIM(std_pd_scls_nm)='물가채') {B}", 6)
# ── query_rules 수치 ─────────────────────────────────────────────
chk("Q-장외등급", "장외 등급 결측 2,023/4,136 · 장내 결측 11.3%", f"SELECT SUM(pd_exg_mkt='장외' AND (crd_grd IS NULL OR TRIM(crd_grd)='')), ROUND(100.0*SUM(pd_exg_mkt='장내' AND (crd_grd IS NULL OR TRIM(crd_grd)=''))/SUM(pd_exg_mkt='장내'),1) {B}", (2023, 11.3), 0.1)
chk("Q-구매가능", "mat_dt>=20260822 21,828", f"SELECT COUNT(*) {B} WHERE CAST(mat_dt AS INT)>=20260822", 21828)
chk("Q-고위험", "KRW yield>0 21,680 · 위험11∪C0 1,244 · +사모 2,223 · 모수 16,359 · max 9.824", f"SELECT COUNT(*), SUM(pd_risk_gcd='11' OR TRIM(crd_grd)='C0'), SUM(pd_risk_gcd='11' OR TRIM(crd_grd)='C0' OR bd_ofr_tcd='사모'), SUM(NOT (pd_risk_gcd='11' OR TRIM(crd_grd)='C0' OR bd_ofr_tcd='사모')), ROUND(MAX(CASE WHEN NOT (pd_risk_gcd='11' OR TRIM(crd_grd)='C0' OR bd_ofr_tcd='사모') THEN applied_yield END),3) {B} WHERE TRIM(curr_cd)='KRW' AND applied_yield>0", (21680, 1244, 2223, 16359, 9.824), 0.001)
chk("Q-고위험-2", ">50% 96행 전부 C0·위험11·공모 · >6% 34", f"SELECT SUM(applied_yield>50), SUM(applied_yield>50 AND TRIM(crd_grd)='C0' AND pd_risk_gcd='11' AND bd_ofr_tcd='공모'), SUM(applied_yield>6 AND NOT (pd_risk_gcd='11' OR TRIM(crd_grd)='C0' OR bd_ofr_tcd='사모')) {B} WHERE TRIM(curr_cd)='KRW'", (96, 96, 34))
chk("Q-외화", "curr_cd KRW 이외 1행 = XS3067881758 · srfc/mat/isu NULL", f"SELECT pd_no, srfc_irt IS NULL, mat_dt IS NULL, isu_dt IS NULL {B} WHERE TRIM(curr_cd)<>'KRW'", ("XS3067881758", 1, 1, 1))
chk("Q-grade-suffix", "'AA'·'A'·'BBB' 단독 표기 0건", f"SELECT COUNT(*) {B} WHERE TRIM(crd_grd) IN ('AA','A','BBB','BB','B','C')", 0)
chk("Q-crd-variants", "crd_grd 공백 변종(TRIM 전후 다른 값) 0", f"SELECT COUNT(*) {B} WHERE crd_grd IS NOT NULL AND crd_grd<>TRIM(crd_grd)", 0)

# ── 출력 ─────────────────────────────────────────────
bad = [r for r in results if not r[4]]
print(f"총 {len(results)}건 검사 · 불일치 {len(bad)}건\n")
print("=== 불일치 ===")
for id_, claim, exp, got, ok in bad:
    print(f"[{id_}] {claim}\n    yaml={exp}\n    DB  ={got}")
print("\n=== 일치 (id 만) ===")
print(", ".join(r[0] for r in results if r[4]))
