# -*- coding: utf-8 -*-
"""채권 안내판 전수 재현 — query_rules·synonyms·normalization·name_encoding 에 적힌 숫자·조건식을 DB 로 다시 센다.

사용: python scripts/audit_bonds_rules.py   (불일치가 있으면 ❌ 로 표시, exit 1)

audit_bonds_claims.py 가 `columns` 칸(문서)을 보는 것과 달리, 이 스크립트는 **HCX 가 실제로 읽는 문장**(loader.planner_context 가
싣는 query_rules·normalization·synonyms + answer_rules 의 근거)만 본다. 구조·보강 CASE 는 yaml 에서 그대로 꺼내 실행한다 —
규칙을 고치면 여기 기대값도 같이 고친다 (2026-08-30 밤 신설, 94건 전부 일치 확인).
"""
import os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlite3, re, sys, yaml
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("data/financial_products.db")
con.create_function("REGEXP", 2, lambda p, s: 1 if s is not None and re.search(p, s) else 0)
B = "FROM domestic_bonds"
res = []


def chk(id_, claim, sql, exp, tol=0):
    got = con.execute(sql).fetchone()
    got = got[0] if len(got) == 1 else tuple(got)

    def eq(a, b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) <= tol
        return a == b
    if exp is None:
        ok = True
    elif isinstance(exp, tuple):
        ok = len(got) == len(exp) and all(eq(g, e) for g, e in zip(got, exp))
    else:
        ok = eq(got, exp)
    res.append((ok, id_, claim, exp, got))


doc = yaml.safe_load(open("ontology/enums/domestic_bonds.yaml", encoding="utf-8"))


def _rule(v):
    """규칙 본문 — 2026-09-04 이후 규칙은 {text: 지시, evidence: 근거} 형이다(문자열 형도 그대로 받는다).
    감사는 지시와 근거를 모두 대조 대상으로 본다(둘 다 사람이 읽는 문장이고 숫자가 들어 있다)."""
    if isinstance(v, dict):
        return " ".join(str(v.get(k, "")) for k in ("text", "evidence") if v.get(k))
    return v


qr = {k: _rule(v) for k, v in doc["query_rules"].items()}
G15 = ['AAA', 'AA+', 'AA0', 'AA-', 'A+', 'A0', 'A-', 'BBB+', 'BBB0', 'BBB-', 'BB0', 'BB-', 'B+', 'B-', 'C0']
IN10 = ",".join(repr(g) for g in G15[:10])
IN5 = ",".join(repr(g) for g in G15[10:])

# 대표행
chk("대표행-1", "1,078종목이 2~4행", f"SELECT COUNT(*), MIN(n), MAX(n) FROM (SELECT pd_no, COUNT(*) n {B} GROUP BY pd_no HAVING n>1)", (1078, 2, 4))
chk("대표행-2", "장외행 NULL: 종류·등급·발행사·위험등급·듀레이션", f"SELECT SUM(bd_knd IS NULL), SUM(crd_grd IS NULL), SUM(pd_pbcm IS NULL), SUM(pd_risk_gcd IS NULL), SUM(dur IS NULL) {B} WHERE pd_exg_mkt='장외'", None)
# 판매행
chk("판매행-1", "buy_yield NOT NULL 634 · 전부 장외", f"SELECT COUNT(*), SUM(pd_exg_mkt<>'장외') {B} WHERE buy_yield IS NOT NULL", (634, 0))
chk("판매행-2", "복수 LOT 종목 307 (2개 306 · 3개 1 · 1개 19 = 634)", f"SELECT SUM(n>=2), SUM(n=2), SUM(n=3), SUM(n=1) FROM (SELECT pd_no, COUNT(*) n {B} WHERE buy_yield IS NOT NULL GROUP BY pd_no)", (307, 306, 1, 19))
# 구매가능
chk("구매가능-1", "KRW AND mat_dt>=20260822 = 21,828", f"SELECT COUNT(*) {B} WHERE curr_cd='KRW' AND mat_dt >= 20260822", 21828)
chk("구매가능-2", "그중 판매행 634", f"SELECT COUNT(*) {B} WHERE curr_cd='KRW' AND mat_dt >= 20260822 AND buy_yield IS NOT NULL", 634)
# 위험등급방향
chk("위험등급-1", "코드 집합 11~16·00", f"SELECT GROUP_CONCAT(v) FROM (SELECT DISTINCT TRIM(pd_risk_gcd) v {B} WHERE pd_risk_gcd IS NOT NULL ORDER BY 1)", "00,11,12,13,14,15,16")
chk("위험등급-2", "국공채 2,839/2,840 = '16'", f"SELECT SUM(pd_risk_gcd='16'), COUNT(*) {B} WHERE TRIM(std_pd_mcls_nm)='국공채'", (2839, 2840))
chk("위험등급-4", "5등급 = AA- 이상 회사채만 · 6등급 회사채 0 · 6등급 최고 수익률 6.23 (안전 = IN 15,16 의 데이터 근거)", f"SELECT SUM(pd_risk_gcd='15' AND TRIM(crd_grd) NOT IN ('AAA','AA+','AA0','AA-')), SUM(pd_risk_gcd='15' AND TRIM(std_pd_mcls_nm)<>'회사채'), SUM(pd_risk_gcd='16' AND TRIM(std_pd_mcls_nm)='회사채'), ROUND(MAX(CASE WHEN pd_risk_gcd='16' THEN applied_yield END),2) {B} WHERE curr_cd='KRW'", (0, 0, 0, 6.23))
chk("위험등급-3", "pd_risk_nm 11 / 16 문구", f"SELECT MIN(CASE WHEN pd_risk_gcd='11' THEN TRIM(pd_risk_nm) END), MIN(CASE WHEN pd_risk_gcd='16' THEN TRIM(pd_risk_nm) END) {B}", None)
# 등급서열
chk("등급-1", "데이터 등급 15종", f"SELECT COUNT(DISTINCT TRIM(crd_grd)) {B} WHERE crd_grd IS NOT NULL AND TRIM(crd_grd)<>''", 15)
chk("등급-2", "NULL 4,020 = 국공채 2,840 + 특수채 254 + 회사채 926", f"SELECT COUNT(*), SUM(TRIM(std_pd_mcls_nm)='국공채'), SUM(TRIM(std_pd_mcls_nm)='특수채'), SUM(TRIM(std_pd_mcls_nm)='회사채') {B} WHERE crd_grd IS NULL OR TRIM(crd_grd)=''", (4020, 2840, 254, 926))
chk("등급-3", "'AA'·'A'·'BBB'·'BB'·'B' 단독 0건", f"SELECT COUNT(*) {B} WHERE TRIM(crd_grd) IN ('AA','A','BBB','BB','B')", 0)
chk("등급-4", "BB+·B0·CCC·CC·D 0건", f"SELECT COUNT(*) {B} WHERE TRIM(crd_grd) IN ('BB+','B0','CCC','CC','D')", 0)
chk("등급-5", "AA- 이상 / 투자등급 / 투기 행수 (합 = 17,862)", f"SELECT SUM(TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-')), SUM(TRIM(crd_grd) IN ({IN10})), SUM(TRIM(crd_grd) IN ({IN5})) {B}", None)
# 수익률·듀레이션·장내
chk("수익률정상", "applied_yield=0 201행", f"SELECT COUNT(*) {B} WHERE applied_yield=0", 201)
chk("듀레이션정상", "dur 99 → 3 · 0 → 52 · NULL 16", f"SELECT SUM(dur=99), SUM(dur=0), SUM(dur IS NULL) {B}", (3, 52, 16))
chk("장내종가-1", "장내 17,746행 · 종가>0 1,270 · 0 16,476 · 장외 4,136 전부 NULL", f"SELECT SUM(pd_exg_mkt='장내'), SUM(pd_exg_mkt='장내' AND exg_close_price>0), SUM(pd_exg_mkt='장내' AND exg_close_price=0), SUM(pd_exg_mkt='장외' AND exg_close_price IS NULL) {B}", (17746, 1270, 16476, 4136))
chk("장내종가-2", "장외 exg_close_price: NOT NULL 수 / 0값 수", f"SELECT SUM(exg_close_price IS NOT NULL), SUM(exg_close_price=0) {B} WHERE pd_exg_mkt='장외'", None)
chk("장내종가-3", "장내 종가 0(거래없음) / >0", f"SELECT SUM(exg_close_price=0), SUM(exg_close_price>0) {B} WHERE pd_exg_mkt='장내'", None)
# 구조표시 CASE — yaml 에서 그대로 꺼내 실행
m = re.search(r"(CASE WHEN .*? END) AS 구조", qr["구조표시"], re.S)
case_struct = m.group(1)
chk("구조표시-분포", "CASE 실행 · 값 분포", f"SELECT GROUP_CONCAT(k||':'||n, ' · ') FROM (SELECT {case_struct} k, COUNT(*) n {B} GROUP BY 1 ORDER BY 2 DESC)", None)
chk("구조-은행자본성", "은행 3종 + 위험 1~3 = 278", f"SELECT COUNT(*) {B} WHERE TRIM(bd_knd) IN ('특수은행채','일반은행채','금융지주회사채') AND pd_risk_gcd IN ('11','12','13')", 278)
chk("구조-코코", "코코 정규식 266 · 그중 은행자본성 264", f"SELECT COUNT(*), SUM(TRIM(bd_knd) IN ('특수은행채','일반은행채','금융지주회사채') AND pd_risk_gcd IN ('11','12','13')) {B} WHERE pd_nm REGEXP '코코(?!리아)|조건부자본|조건상각|조건부\\(상\\)'", (266, 264))
chk("구조-콜", "LIKE 콜 AND NOT 콜마 = 2,678 = 경계식", f"SELECT SUM(pd_nm LIKE '%콜%' AND pd_nm NOT LIKE '%콜마%'), SUM(pd_nm REGEXP '(?<![가-힣])콜(?![가-힣])') {B}", (2678, 2678))
chk("구조-풋", "풋 4형 529", f"SELECT SUM(pd_nm LIKE '%(풋)%' OR pd_nm LIKE '%(풋/%' OR pd_nm LIKE '%/풋)%' OR pd_nm LIKE '%/풋/%'), SUM(pd_nm REGEXP '[(/]풋[)/]') {B}", (529, 529))
chk("구조-후", "후 4형 530", f"SELECT SUM(pd_nm LIKE '%(후)%' OR pd_nm LIKE '%(후/%' OR pd_nm LIKE '%/후)%' OR pd_nm LIKE '%/후/%'), SUM(pd_nm REGEXP '[(/]후[)/]') {B}", (530, 530))
chk("구조-CB", "GLOB [0-9]CB OR (전환 = 389", f"SELECT SUM(pd_nm GLOB '*[0-9]CB*' OR pd_nm LIKE '%(전환%' OR pd_nm LIKE '%/전환%'), SUM(pd_nm REGEXP '\\d+CB|[(/]전환[)/]') {B}", (389, 389))
chk("구조-영구", "신종|영구 266 / 종목 237", f"SELECT SUM(pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%'), COUNT(DISTINCT CASE WHEN pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%' THEN pd_no END) {B}", (266, 237))
chk("구조-EB/BW/분리/물가", "137 · 32 · 209 · 6", f"SELECT SUM(pd_nm GLOB '*[0-9]EB*'), SUM(pd_nm GLOB '*[0-9]BW*'), SUM(pd_nm LIKE '%분리채권%'), SUM(pd_nm LIKE '%물가%') {B}", (137, 32, 209, 6))
chk("구조-분리채권", "분리채권 209 전부 6등급·대분류 국공채·할인채 (bd_knd 는 국고채권 188 + 장외 NULL 21)", f"SELECT SUM(pd_risk_gcd='16'), SUM(TRIM(std_pd_mcls_nm)='국공채'), SUM(TRIM(bd_intp_tcd)='할인채'), SUM(bd_knd IS NULL) {B} WHERE pd_nm LIKE '%분리채권%'", (209, 209, 209, 21))
chk("구조-합집합", "구조 열 비어있지 않음 3,581행 / 3,520종목 (이름 11패턴 합집합 3,578 + 은행 자본성증권 컬럼 판정 1행 + 2026-09-06 종류 결측 보완 2행)", f"SELECT COUNT(*), COUNT(DISTINCT pd_no) {B} WHERE ({case_struct}) <> ''", (3581, 3520))
# ESG
for lab, exp in (("녹", 356), ("사", 1984), ("지", 159)):
    chk(f"ESG-{lab}", f"4형 LIKE = {exp} = 정규식", f"SELECT SUM(pd_nm LIKE '%({lab})%' OR pd_nm LIKE '%({lab}/%' OR pd_nm LIKE '%/{lab})%' OR pd_nm LIKE '%/{lab}/%'), SUM(pd_nm REGEXP '[(/]{lab}[)/]') {B}", (exp, exp))
chk("ESG-동시", "두 라벨 동시 0건", f"SELECT COUNT(*) {B} WHERE (pd_nm REGEXP '[(/]녹[)/]') + (pd_nm REGEXP '[(/]사[)/]') + (pd_nm REGEXP '[(/]지[)/]') > 1", 0)
chk("ESG-(사)공모", "(사) 중 공모 1,981", f"SELECT SUM(bd_ofr_tcd='공모') {B} WHERE pd_nm REGEXP '[(/]사[)/]'", 1981)
chk("ESG-합", "셋의 OR = 2,499", f"SELECT COUNT(*) {B} WHERE pd_nm REGEXP '[(/][녹사지][)/]'", 2499)
# 고위험제외
HR = "pd_risk_gcd <> '11' AND COALESCE(TRIM(crd_grd), '') <> 'C0' AND bd_ofr_tcd <> '사모'"
chk("고위험-모수", "추천 모수 약 19,400 · 최고 9.82", f"SELECT COUNT(*), ROUND(MAX(applied_yield),2) {B} WHERE {HR} AND curr_cd='KRW' AND applied_yield>0", (19400, 9.82), 60)
chk("고위험-NULL함정", "COALESCE 식 vs NOT(a OR b)", f"SELECT SUM({HR}), SUM(NOT (pd_risk_gcd='11' OR crd_grd='C0') AND bd_ofr_tcd<>'사모') {B}", None)
chk("고위험-국공채최고", "국공채 최고 4.89", f"SELECT ROUND(MAX(applied_yield),2) {B} WHERE TRIM(std_pd_mcls_nm)='국공채'", 4.89, 0.01)
chk("고위험-50%", "50% 초과 96행 · 최고 728.5 · 전부 C0/1등급", f"SELECT COUNT(*), ROUND(MAX(applied_yield),1), SUM(TRIM(crd_grd)='C0' OR pd_risk_gcd='11') {B} WHERE applied_yield>50", (96, 728.5, 96))
chk("고위험-사모", "사모 2,007 · 공모 19,875", f"SELECT SUM(bd_ofr_tcd='사모'), SUM(bd_ofr_tcd='공모') {B}", (2007, 19875))
chk("고위험-NULL컬럼", "pd_risk_gcd NULL / bd_ofr_tcd NULL (<> 조건에서 빠지는 행)", f"SELECT SUM(pd_risk_gcd IS NULL), SUM(bd_ofr_tcd IS NULL) {B}", None)
# 신용보강 CASE
m = re.search(r"(CASE WHEN .*? END) AS 보강", qr["신용보강"], re.S)
case_cr = m.group(1)
chk("신용보강-분포", "A 2,873 · B 7 · C 2,968 · D 3,171 · E 2,648 · F 10,215", f"SELECT GROUP_CONCAT(k||':'||n, ' · ') FROM (SELECT SUBSTR({case_cr},1,1) k, COUNT(*) n {B} GROUP BY 1 ORDER BY 1)", "A:2873 · B:7 · C:2968 · D:3171 · E:2648 · F:10215")
chk("신용보강-누락0", "합 21,882", f"SELECT COUNT(*) {B} WHERE ({case_cr}) IS NOT NULL", 21882)
# 유동화·외화·기준일·발행사·공모사모
chk("유동화", "4,045", f"SELECT COUNT(*) {B} WHERE TRIM(bd_knd) IN ('MBS','유동화회사채','Conduit회사채') OR pd_pbcm LIKE '%유동화%' OR pd_pbcm LIKE '%신용보증%' OR pd_pbcm LIKE '%기술보증%' OR pd_nm LIKE '%유동화%'", 4045)
chk("외화채", "KRW 21,881 · '000' 1 · 통화 2종", f"SELECT SUM(curr_cd='KRW'), SUM(curr_cd='000'), COUNT(DISTINCT curr_cd) {B}", (21881, 1, 2))
chk("기준일", "info_base_dt 전부 20260821", f"SELECT GROUP_CONCAT(DISTINCT info_base_dt) {B}", "20260821")
chk("발행사-한전", "'한국전력공사(주)' 403", f"SELECT COUNT(*) {B} WHERE TRIM(pd_pbcm)='한국전력공사(주)'", 403)
chk("발행사-표기", "산은·기은·LH·주금공·현대차 표기 존재", f"SELECT SUM(TRIM(pd_pbcm)='한국산업은행'), SUM(TRIM(pd_pbcm)='(주)중소기업은행'), SUM(TRIM(pd_pbcm)='한국토지주택공사'), SUM(TRIM(pd_pbcm)='한국주택금융공사'), SUM(pd_pbcm LIKE '%현대자동차%') {B}", None)
chk("발행사-MBS", "주금공 1,558행 · MBS 1,396 = 전부 주금공", f"SELECT SUM(pd_pbcm LIKE '%한국주택금융공사%'), SUM(TRIM(bd_knd)='MBS'), SUM(TRIM(bd_knd)='MBS' AND pd_pbcm LIKE '%한국주택금융공사%') {B}", (1558, 1396, 1396))
chk("발행사-빈행", "발행사 빈 행 149 (전부 장외 · 형제행에 발행사 있는 건 8)", f"SELECT COUNT(*), SUM(pd_exg_mkt='장외') {B} WHERE pd_pbcm IS NULL OR TRIM(pd_pbcm)=''", (149, 149))
chk("장외등급", "장외 4,136 중 결측 2,023 · 장내 결측 11.3%", f"SELECT SUM(pd_exg_mkt='장외'), SUM(pd_exg_mkt='장외' AND (crd_grd IS NULL OR TRIM(crd_grd)='')), ROUND(100.0*SUM(pd_exg_mkt='장내' AND (crd_grd IS NULL OR TRIM(crd_grd)=''))/SUM(pd_exg_mkt='장내'),1) {B}", (4136, 2023, 11.3), 0.1)
# synonyms — DB 표기가 실제로 있는가
for k, v in doc["synonyms"].items():
    n1 = con.execute(f"SELECT COUNT(*) {B} WHERE TRIM(bd_knd)=? OR TRIM(std_pd_mcls_nm)=? OR TRIM(std_pd_scls_nm)=? OR TRIM(bd_intp_tcd)=? OR TRIM(bd_inrt_tcd)=?", (v, v, v, v, v)).fetchone()[0]
    n2 = con.execute(f"SELECT COUNT(*) {B} WHERE pd_nm LIKE ? OR pd_pbcm LIKE ?", (f"%{v}%", f"%{v}%")).fetchone()[0]
    n3 = con.execute("SELECT COUNT(*) FROM schema_metadata WHERE table_name='domestic_bonds' AND korean_name LIKE ?", (f"%{v}%",)).fetchone()[0]   # 한글 컬럼명은 '표면이자율/쿠폰금리' 처럼 복합 표기 — 부분 일치
    res.append((n1 + n2 + n3 > 0, f"syn-{k}", f"→ '{v}'", ">0", f"컬럼값 {n1} · 이름/발행사 LIKE {n2} · 한글컬럼명 {n3}"))
# normalization.zero_as_missing
for col, exp in (("exg_close_price", 16476), ("applied_yield", 201), ("isu_dt", 25), ("mat_dt", 4), ("isu_bal_amt", 325)):
    chk(f"zero-{col}", f"0값 {exp}", f"SELECT COUNT(*) {B} WHERE {col}=0", exp)
chk("mat_dt-NULL", "mat_dt NULL 행", f"SELECT SUM(mat_dt IS NULL), SUM(isu_dt IS NULL) {B}", None)
# isin_prefix
chk("isin", "KR6 12,834 · KR3 6,180 · KR2 2,239 · KR1 392 · KRC 209 · KRB 27 · XS3 1", f"SELECT GROUP_CONCAT(k||':'||n, ' · ') FROM (SELECT SUBSTR(pd_no,1,3) k, COUNT(*) n {B} GROUP BY 1 ORDER BY 2 DESC)", "KR6:12834 · KR3:6180 · KR2:2239 · KR1:392 · KRC:209 · KRB:27 · XS3:1")
chk("등급정규화", "TRIM(crd_grd)='AA' 0 · 'AA0' 1,241", f"SELECT SUM(TRIM(crd_grd)='AA'), SUM(TRIM(crd_grd)='AA0') {B}", (0, 1241))
chk("과세수익률금지", "avg_annual_tax_yield 전량 0", f"SELECT SUM(COALESCE(avg_annual_tax_yield,0)<>0) {B}", 0)
chk("더티금지", "dirty=eval_price 99%", f"SELECT ROUND(100.0*SUM(dirty=eval_price)/COUNT(*),1) {B}", 99.0, 0.5)
chk("잔존0", "remaining_days=0 49", f"SELECT COUNT(*) {B} WHERE remaining_days=0", 49)
chk("pd_nm-종목불일치", "같은 pd_no 에 다른 pd_nm 2종목", f"SELECT GROUP_CONCAT(pd_no||'='||names, ' | ') FROM (SELECT pd_no, GROUP_CONCAT(DISTINCT TRIM(pd_nm)) names {B} GROUP BY pd_no HAVING COUNT(DISTINCT TRIM(pd_nm))>1)", None)

bad = [r for r in res if not r[0]]
print(f"검사 {len(res)} · 일치 {len(res) - len(bad)} · 불일치 {len(bad)}")
for ok, i, c, e, g in res:
    mark = "ℹ️" if e is None else ("✅" if ok else "❌")
    print(f"{mark} {i:<18} {c}\n     기대={e}  실측={g}")
print("\n[길이] 구조 CASE", len(case_struct), "자 · 보강 CASE", len(case_cr), "자")
sys.exit(1 if bad else 0)
