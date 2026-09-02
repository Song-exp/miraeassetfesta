# 재검 루프 실측 기록 — 2026-09-02 (HANDOFF §1 P1 7문항)

> 구조: 에이전트 A(실행·수리) ↔ 에이전트 B(공모펀드 전문가 심사). 서버 `/answer` 직접 실측. 라운드마다 같은 질문의 **초기 답변과 수정 후 답변 전문**을 남긴다.
> 채점 상세: `docs/recheck_2026-09-02_round1.md` (B 보고서). 원본 JSON: `eval/probe_recheck_2026-09-02*.json`. 재생성: `eval/render_probe_md.py`.

## 판정 요약

| ID | 질문 | 1라운드(초기) |
| :-- | :-- | :-- |
| R1 | 공모펀드는 유형별로 몇 개씩 있어? | ✅ 값 / 🟡 서술 — 19범주·8,969 완전 일치. '건'=클래스 행수인데 펀드 수(3,040) 미병기 |
| R2 | 펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘 | ✅ 값 / 🟡 서술 — 823·235·207·205·142 + 우리자산운용 정확. 면책 '관련 기관에 문의' 미제거 + 전수 집계에 거짓 유보 |
| R3 | 중국에 투자하는 공모펀드 알려줘 | 🟡 경로 정답 / 서술 결함 4 — 국가 태그 확정식 발동(CHN 560행). 상품명 훼손 FOSS(실제 FOCUS) · 30행 중 5행만 · 같은 펀드 클래스 별개 나열 · 태그 코드 노출 |
| R4 | 미래에셋코어테크 펀드 1년 수익률 알려줘 | ✅ 값 / 🟡 묶기 — Org_00080008 복귀, 188.83% 실값. 6펀드 37클래스를 1클래스로(3회째), LIMIT 30이 본체 최고 189.77 절단 |
| R5 | 한국투자신탁운용이 운용하는 공모펀드는 몇 개야? | ✅ 값(기대값 정정) / 🟡 서술 — 143/541이 맞고 HANDOFF 142/540이 틀림(KG가 00040105 병합). 클래스 541 버림 · 2코드 합산 미고지 |
| R6 | 미래에셋차이나솔로몬증권투자신탁 2호 위험등급 알려줘 | ✅ 값 / 🟡 서술 — 2등급(높은 위험) 정답, 마커 3종 확인. 등급 숫자 미병기 · LIMIT 1 · 기본모수 없음(잠재) |
| R7 | 공모펌드 중 1년 수익률이 가장 높은 3개 알려줘 | ❌ — 마이다스 미노출(기점오류 가드는 발동). 클래스 단위 top3 = 한화2.2배 1펀드 도배. gold 펀드단위: 한화 387.66 · NH-Amundi코리아2배 362.53 · 삼성KOSPI200 2배 361.3. 원인: GROUP BY 미주입 |

---

## R1. 공모펀드는 유형별로 몇 개씩 있어?

### 1라운드(초기) — HTTP 200 · 2.5s · ✅ 값 / 🟡 서술 — 19범주·8,969 완전 일치. '건'=클래스 행수인데 펀드 수(3,040) 미병기

**answer**

```text
조회 결과 19개 범주, 합계 8,969건입니다 (기준일 2026-08-22).

- (미수록): 418건
- MMF: 108건
- 기타: 51건
- 부동산형: 11건
- 외화 MMF: 30건
- 절대수익추구형: 235건
- 주식형: 1,773건
- 주식혼합형: 155건
- 채권형: 610건
- 채권혼합형: 534건
- 커머더티형: 48건
- 특별자산: 8건
- 해외기타: 801건
- 해외부동산형: 73건
- 해외주식형: 2,784건
- 해외주식혼합형: 327건
- 해외채권형: 511건
- 해외채권혼합형: 440건
- 해외특별자산: 52건
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 19
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,692자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 분포 결측 라벨 — GROUP BY 축의 NULL 에 '(미수록)' 이름 부여 (2026-09-01 FND-038 실측: 라벨이 빈칸이라 답변기가 418행 그룹을 통째로 빠뜨렸다)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COALESCE(zrin_btyp_nm,'(미수록)'), COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모') GROUP BY zrin_btyp_nm LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 19행 조회 (상한 30)
12. [Answer] 분포 답변 기계 조립 — 2열(범주·건수) GROUP BY 결과는 HCX 없이 전 행을 그대로 옮긴다 (2026-09-01 FND-038 재검: 19행 중 17행 나열 + '일부' 서술 재발)
```

</details>

<details><summary>retrieved_context</summary>

```text
COALESCE(zrin_btyp_nm,'(미수록)') | COUNT(*)
(미수록) | 418
MMF | 108
기타 | 51
부동산형 | 11
외화 MMF | 30
절대수익추구형 | 235
주식형 | 1773
주식혼합형 | 155
채권형 | 610
채권혼합형 | 534
커머더티형 | 48
특별자산 | 8
해외기타 | 801
해외부동산형 | 73
해외주식형 | 2784
해외주식혼합형 | 327
해외채권형 | 511
해외채권혼합형 | 440
해외특별자산 | 52
```

</details>

---

## R2. 펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘

### 1라운드(초기) — HTTP 200 · 12.5s · ✅ 값 / 🟡 서술 — 823·235·207·205·142 + 우리자산운용 정확. 면책 '관련 기관에 문의' 미제거 + 전수 집계에 거짓 유보

**answer**

```text
펀드를 가장 많이 운용하는 운용사 상위 5곳은 다음과 같습니다.

1. 미래에셋자산운용: 823개의 펀드 운용
2. 우리자산운용: 235개의 펀드 운용
3. 삼성자산운용: 207개의 펀드 운용
4. iM에셋자산운용: 205개의 펀드 운용
5. 한국투자신탁운용: 142개의 펀드 운용

이 순위는 조회된 데이터를 기반으로 한 것이며, 더 많은 펀드를 운용하는 곳이 있을 수 있습니다. 추가 정보가 필요하시다면 관련 기관에 문의하시기 바랍니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 28
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,622자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) AS 운용사코드, MAX(mtco_nm) AS 운용사이름, COUNT(DISTINCT CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no ELSE substr('0000000' || mtco_itm_no, -7) END) AS 펀드수 FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 3 DESC LIMIT 5
7. [Guard] SQL 기각 — 스키마에 없는 컬럼: mtco_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: mgmt_co_nm, mtco_itm_no — 뜻이 같다는 보장은 없다)
8. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 4.4s)
9. [Guard] 운용사 최빈 이름 — MAX(mgmt_co_nm) 이 합병 코드의 구명칭을 사전순으로 뽑던 것을 소수 이름 제외로 교정 (2026-09-01 FND-035 재검: 00040007 이 프랭클린템플턴(10행)으로 표기 — 정본은 우리자산운용 373행)
10. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) AS 운용사코드, MAX(CASE WHEN printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || mgmt_co_nm NOT IN ('00040007/프랭클린템플턴투자신탁운용', '00040010/삼성액티브자산운용', '00040011/미래에셋자산운용', '00040013/슈로더자산운용', '00040023/우리자산운용', '00080008/멀티에셋자산운용', '00080008/미래에셋맵스자산운용') THEN mgmt_co_nm END) AS 운용사이름, COUNT(DISTINCT CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END) AS 펀드수 FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 3 DESC LIMIT 5
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 5행 조회 (상한 30)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
운용사코드 | 운용사이름 | 펀드수
00080008 | 미래에셋자산운용 | 823
00040007 | 우리자산운용 | 235
00040010 | 삼성자산운용 | 207
00080035 | iM에셋자산운용 | 205
00040024 | 한국투자신탁운용 | 142
```

</details>

---

## R3. 중국에 투자하는 공모펀드 알려줘

### 1라운드(초기) — HTTP 200 · 9.4s · 🟡 경로 정답 / 서술 결함 4 — 국가 태그 확정식 발동(CHN 560행). 상품명 훼손 FOSS(실제 FOCUS) · 30행 중 5행만 · 같은 펀드 클래스 별개 나열 · 태그 코드 노출

**answer**

```text
조회 결과에 따르면 중국에 투자하는 공모펀드는 다음과 같습니다.

* 삼성중국본토중소형FOSS증권자투자신탁UH(주식)Ce(C101, M109, CHN)
* 삼성누버거버먼차이나증권자투자신탁H(주식-재간접형)A(V102, M111, CHN)
* 미래에셋차이나솔로몬증권투자신탁2호(주식)C2(CHN, C101, M111)
* 미래에셋차이나솔로몬증권투자신탁2호(주식)C5(D102, C101, CHN)
* 한국투자골드플랜차이나연금증권전환형자투자신탁 1호(주식) C(F102, CHN)
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,704자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 지역 컬럼 등호·미래핑 태그 LIKE 를 ','||prfd_attr_cds||',' 정식형으로 교체 (2026-09-01 FND-026 재검: ='글로벌' 오모수 + wrap 없는 LIKE 가 98/560행 누락)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND (',' || prfd_attr_cds || ',' LIKE '%,CHN,%' OR ',' || prfd_attr_cds || ',' LIKE '%,CHN,%') AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 30행 조회 (상한 30)
11. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
12. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | prfd_attr_cds
KR510502099M | 삼성중국본토중소형FOCUS증권자투자신탁UH(주식)Ce | C103,G118,D102,N122,P104,M109,CHN,C101,M111,D106,V102,N135
KR510509003M | 삼성누버거버먼차이나증권자투자신탁H(주식-재간접형)A | V102,M111,D102,CHN,W122,C103,M112,C101,M109
KR510902681M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C2 | V102,M111,CHN,C101,D102,G118,C103
KR510902684M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C5 | D102,C103,G118,CHN,C101,V102,M111
KR5113450131 | 한국투자골드플랜차이나연금증권전환형자투자신탁 1호(주식) C | V102,M111,D102,F102,C103,CHN,C101,M109,G110
KR5114450111 | 삼성 CHINA2.0 본토증권자투자신탁 제2호[주식] C1 클래스 | M111,V102,CHN,M109,N122,C101,G118,C103,D102
KR5114450189 | 삼성CHINA본토포커스증권자투자신탁 1[주식]Class Cp(퇴직) | C103,G118,D102,G115,N122,M109,CHN,C101,F103,M111,V102
KR5118450090 | 우리차이나본토주식증권자투자신탁UH(주식)Class A | S104,V102,CHN,M111,C101,N122,M109,D105,W108,D102,G118,C103
KR512002011M | 우리템플턴차이나드래곤증권자투자신탁(E)(주식-재간접형) | C103,D102,M109,C101,M112,CHN,V102
KR512102040M | 신한중국본토중소형주증권자투자신탁제1호(UH)[주식]Ae | M111,V102,D106,N122,M109,P104,C101,G118,C103,CHN,D102
KR5127450227 | KB차이나고배당40증권자투자신탁(채권혼합)C-퇴직연금클래스 | M111,W124,C103,D102,CHN,V103,M109,G115,P101,C101
KR5127651021 | KB차이나그로스증권자투자신탁(주식)C클래스 | CHN,M111,N135,V102,C103,G118,D102,M109,C101
KR513102120M | DB차이나증권투자신탁제1호(주식)C5 | D102,V103,CHN,C103,G118,C101,D105,M111
KR5131450046 | DB차이나본토RQFII증권자투자신탁(H)[주식]CE | D102,C103,G118,C101,N122,M109,D106,V102,CHN,M111
KR5131450048 | DB차이나본토RQFII증권자투자신탁(H)[주식] C-P | D102,C103,G118,C101,M109,G110,N122,CHN,V102,M111,F103
KR5133450046 | 카디안 차이나드래곤AShare증권자투자신탁(UH)[주식]클래스Ce | G118,C103,D102,N122,CHN,M109,D105,C101,M111,V102,D106
KR5133550039 | 카디안 차이나드래곤AShare증권자투자신탁(H)[주식]클래스CP | V102,F103,CHN,M111,D102,C103,G118,C101,M109,G115,N122
KR510502101M | 삼성클래식중국본토중소형FOCUS연금증권자투자신탁H(주식)C | V102,F103,M111,CHN,D102,C103,C101,N122,M109,P104,G110
KR510902495M | 미래에셋차이나본토증권자투자신탁2호(H)(주식)C | V102,M111,C101,N122,M109,D102,C103,CHN,G118
KR510909076M | 미래에셋차이나H레버리지2.0증권자투자신탁(주식-파생재간접형)C2 | M111,CHN,S117,V102,S104,C103,D102,M109,C101,M112
KR510909078M | 미래에셋차이나H레버리지2.0증권자투자신탁(주식-파생재간접형)C4 | C103,D102,M109,M112,C101,M111,V102,S117,S104,CHN
KR5113450101 | 한국투자글로벌브랜드파워증권자투자신탁UH(주식) 종류 C | M111,V102,G118,C103,D102,M109,CHN,C101
KR5142430010 | 키움슈로더차이나퇴직연금밸런스드40증권자투자신탁(채권혼합-재간접형) 종류C-e | W122,D102,V103,C103,C101,M112,M109,CHN,G115,D106,F103,M111,HKG
KR5148000011 | 피델리티차이나증권자투자신탁(주식-재간접형)종류C 5 | M109,C101,C103,G118,W122,D102,N109,CHN,M111,V102
KR5148800019 | 피델리티 차이나 증권 자투자신탁 (주식-재간접형) 종류 CP-e | G118,C103,D102,W122,CHN,G115,M109,C101,F103,M111,V102,D106,F101
KR5152450049 | 다올중국1등주증권자투자신탁[주식] 종류CW | W122,D102,CHN,C103,G118,C101,M109,V102,HKG,M105,F103,M111,F101
KR5117450036 | 신한차이나오퍼튜니티증권자투자신탁(H)[주식]종류Ce | C101,CHN,M109,D102,C103,G118,D106,V102,M111
KR5114450040 | 삼성CHINA2.0본토증권자투자신탁 1[주식](Cf) | G118,C103,D102,M109,N122,C101,CHN,M111,V102
KR5114470053 | 삼성중국본토레버리지증권자투자신탁 제1호[주식-파생재간접형]_C3 | C103,D102,M109,N122,C101,M112,M111,CHN,S117,V102,S104
KR5114490009 | 삼성누버거버먼차이나증권자투자신탁H(주식-재간접형)Cpe(퇴직연금) | D106,V102,M111,F103,W122,D102,CHN,C103,C101,M112,M109,G115
```

</details>

---

## R4. 미래에셋코어테크 펀드 1년 수익률 알려줘

### 1라운드(초기) — HTTP 200 · 5.0s · ✅ 값 / 🟡 묶기 — Org_00080008 복귀, 188.83% 실값. 6펀드 37클래스를 1클래스로(3회째), LIMIT 30이 본체 최고 189.77 절단

**answer**

```text
미래에셋코어테크 증권자투자신탁(주식) 종류 C-P2E의 1년 수익률은 188.83%입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 10,091자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT fd_yr1_ern_r, itm_nm FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r <> 0 LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 30행 조회 (상한 30)
12. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
fd_yr1_ern_r | itm_nm
17.41 | 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류C-P2E
17.36 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류C-P2e
188.83 | 미래에셋코어테크증권자투자신탁(주식) 종류C-P2E
13.28 | 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류C-P2e
17.26 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류C-Pe
-41.31 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류C3
188.64 | 미래에셋코어테크증권자투자신탁(주식) 종류C-Pe
3.21 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류C2
188.22 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류C-e
15.68 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류C-I
16.23 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류C1
186.98 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류C
187.76 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A
188.63 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A-e
15.29 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류C-P2e
17.33 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류Ae
187.94 | 미래에셋코어테크증권자투자신탁(주식) 종류A
16.94 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류A
188.38 | 미래에셋코어테크증권자투자신탁(주식) 종류C-E
16.99 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류C-P2
13.19 | 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류C-e
15.98 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류C-e
188.81 | 미래에셋코어테크증권자투자신탁(주식) 종류A-E
17.73 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류F
17.34 | 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류C-PE
187.99 | 미래에셋코어테크증권자투자신탁(주식) 종류C-P2
16.89 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류C4
187.09 | 미래에셋코어테크증권자투자신탁(주식) 종류C
16.81 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류C-P
17.31 | 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류C-e
```

</details>

---

## R5. 한국투자신탁운용이 운용하는 공모펀드는 몇 개야?

### 1라운드(초기) — HTTP 200 · 34.8s · ✅ 값(기대값 정정) / 🟡 서술 — 143/541이 맞고 HANDOFF 142/540이 틀림(KG가 00040105 병합). 클래스 541 버림 · 2코드 합산 미고지

**answer**

```text
한국투자신탁운용이 운용하는 공모펀드는 총 143개입니다. 이는 클래스 수를 제외한 순수하게 펀드만을 의미합니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 26
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '한국투자신탁운용' → Org_00040024 (Organization) → public_funds.or_co_xtn_itt_cd='00040024' · public_funds.or_co_xtn_itt_cd='00040105'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,307자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
8. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
9. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') AND prvo_pbff_desc = '공모') LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 1행 조회 (상한 30)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
143 | 541
```

</details>

---

## R6. 미래에셋차이나솔로몬증권투자신탁 2호 위험등급 알려줘

### 1라운드(초기) — HTTP 200 · 3.5s · ✅ 값 / 🟡 서술 — 2등급(높은 위험) 정답, 마커 3종 확인. 등급 숫자 미병기 · LIMIT 1 · 기본모수 없음(잠재)

**answer**

```text
미래에셋차이나솔로몬증권투자신탁 2호의 위험 등급은 '**높은 위험**'입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 28
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — '미래에셋차이나솔로몬증권투자신탁' → Fund_284530e1ea (Fund) — ⚠️ 질문의 '2호' 와 이 노드의 코드가 가리키는 펀드가 다를 수 있어 코드 매핑을 싣지 않는다. public_funds.itm_nm 공백무시 LIKE + 호 경계(종목명검색 규칙)로 푼다
4. [Route] 미특정 보정 — KG 매핑이 public_funds 만 가리켜 그 상품군으로 좁힌다 (2026-09-01 FND-032 실측: 미특정 → 채권 테이블 SQL → 0행 오거절)
5. [Gate] 통과 — 대상 테이블 ['public_funds']
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,884자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] 호수 경계 주입 — N호 조건을 GLOB '*[^0-9]N호*' 확정식으로 교체 (2026-09-01 FND-032 실측: HCX 가 경계식을 `'2호' IN (a OR b)` 로 옮겨 항상-거짓 0행)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT zrin_fd_ivst_risk_grd_nm, itm_no, TRIM(itm_nm) AS itm_nm FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬증권투자신탁%' AND REPLACE(itm_nm,' ','') GLOB '*[^0-9]2호*' LIMIT 1
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 1행 조회 (상한 30)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
zrin_fd_ivst_risk_grd_nm | itm_no | itm_nm
높은 위험 | KR510902681M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C2
```

</details>

---

## R7. 공모펌드 중 1년 수익률이 가장 높은 3개 알려줘

### 1라운드(초기) — HTTP 200 · 10.3s · ❌ — 마이다스 미노출(기점오류 가드는 발동). 클래스 단위 top3 = 한화2.2배 1펀드 도배. gold 펀드단위: 한화 387.66 · NH-Amundi코리아2배 362.53 · 삼성KOSPI200 2배 361.3. 원인: GROUP BY 미주입

**answer**

```text
공모펀드 중 1년 수익률이 가장 높은 3개를 알려드리겠습니다.

1. 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류 Ce : 387.66%
2. 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류 C4 : 387.48%
3. 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류 A : 386.38%

이 세 가지 펀드는 모두 레버리지 기능이 있어 높은 수익을 추구하는 특징이 있습니다. 하지만 레버리지 펀드는 시장 변동성에 따라 손실이 확대될 수 있으므로 투자 전에 충분한 검토와 주의가 필요합니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 27
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — 매칭 없음
4. [Gate] 통과 — 대상 테이블 미특정
5. [Plan] 근거문서 조립 — 대상 마스터 4테이블 · 49,634자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 기점오류 제외 주입 — 18개월 이상 수익률 랭킹에 검증 3클래스 NOT IN 주입 (수익률기점오류_제외 규칙 미반영 실측 — 단기·개별 조회엔 미적용)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_no, TRIM(itm_nm), fd_yr1_ern_r, zrin_attr_nms FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r > -100 AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') ORDER BY 3 DESC LIMIT 3
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 3행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 12,443자 적용 (전체)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | TRIM(itm_nm) | fd_yr1_ern_r | zrin_attr_nms
KR5129470016 | 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류Ce | 387.66 | 종류형 클래스펀드,온라인전용,개방,FoFs,인덱스,레버리지,추가,국내위탁판매,국내
KR5129470015 | 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류C4 | 387.48 | 인덱스,개방,레버리지,국내,국내위탁판매,추가,종류형 클래스펀드,FoFs
KR5129470010 | 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류A | 386.38 | 종류형 클래스펀드,인덱스,국내위탁판매,개방,FoFs,국내,레버리지,추가
```

</details>
