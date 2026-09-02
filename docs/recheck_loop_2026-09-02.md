# 재검 루프 실측 기록 — 2026-09-02 (HANDOFF §1 P1 7문항 + 형제 12문항)

> 구조: 에이전트 A(실행·수리) ↔ 에이전트 B(공모펀드 전문가 심사, 근거 `docs/domain/public_funds.md`). 서버 `/answer` 직접 실측. 라운드마다 같은 질문의 **초기 답변과 수정 후 답변 전문**을 남긴다.
> 1라운드 = 배포 전(9e0b691) · 2라운드 = A 수리 P1~P7 + 리뷰 수리 ②-1~7 배포 후(31e72ef).
> 채점 상세: `docs/recheck_2026-09-02_round1.md` · `_round1_review.md` · `_round2.md`. 원본 JSON: `eval/probe_recheck_2026-09-02*.json`. 재생성: `eval/render_probe_md.py`.

## 판정 요약

| ID | 질문 | 1라운드(초기) | 2라운드(수리 후) |
| :-- | :-- | :-- | :-- |
| R1 | 공모펀드는 유형별로 몇 개씩 있어? | ✅ 값 / 🟡 서술 — 19범주·8,969 완전 일치. '건'=클래스 행수인데 펀드 수(3,040) 미병기 | 200 · 2.1s |
| R2 | 펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘 | ✅ 값 / 🟡 서술 — 823·235·207·205·142 + 우리자산운용 정확. 면책 '관련 기관에 문의' 미제거 + 전수 집계에 거짓 유보 | 200 · 9.3s |
| R3 | 중국에 투자하는 공모펀드 알려줘 | 🟡 경로 정답 / 서술 결함 4 — 국가 태그 확정식 발동(CHN 560행). 상품명 훼손 FOSS(실제 FOCUS) · 30행 중 5행만 · 같은 펀드 클래스 별개 나열 · 태그 코드 노출 | 200 · 8.8s |
| R4 | 미래에셋코어테크 펀드 1년 수익률 알려줘 | ✅ 값 / 🟡 묶기 — Org_00080008 복귀, 188.83% 실값. 6펀드 37클래스를 1클래스로(3회째), LIMIT 30이 본체 최고 189.77 절단 | 200 · 8.1s |
| R5 | 한국투자신탁운용이 운용하는 공모펀드는 몇 개야? | ✅ 값(기대값 정정) / 🟡 서술 — 143/541이 맞고 HANDOFF 142/540이 틀림(KG가 00040105 병합). 클래스 541 버림 · 2코드 합산 미고지 | 200 · 2.5s |
| R6 | 미래에셋차이나솔로몬증권투자신탁 2호 위험등급 알려줘 | ✅ 값 / 🟡 서술 — 2등급(높은 위험) 정답, 마커 3종 확인. 등급 숫자 미병기 · LIMIT 1 · 기본모수 없음(잠재) | 200 · 35.9s |
| R7 | 공모펌드 중 1년 수익률이 가장 높은 3개 알려줘 | ❌ — 마이다스 미노출(기점오류 가드는 발동). 클래스 단위 top3 = 한화2.2배 1펀드 도배. gold 펀드단위: 한화 387.66 · NH-Amundi코리아2배 362.53 · 삼성KOSPI200 2배 361.3. 원인: GROUP BY 미주입 | 200 · 8.7s |
| S1 | 1년 수익률이 가장 높은 공모펌드 5개 알려줘 | — | 200 · 9.5s |
| S2 | 3년 수익률이 가장 나쁜 공모펀드 3개 알려줘 | — | 200 · 7.1s |
| S3 | 삼성코리아대표 펀드 1년 수익률 알려줘 | — | 200 · 9.2s |
| S4 | KB차이나 펀드 위험등급 알려줘 | — | 200 · 24.6s |
| S5 | 미래에셋차이나솔로몬증권투자신탁 3호 위험등급 알려줘 | — | 200 · 3.6s |
| S6 | 인도에 투자하는 공모펀드 알려줘 | — | 200 · 24.9s |
| S7 | 베트남에 투자하는 공모펀드 알려줘 | — | 200 · 9.9s |
| S8 | KB자산운용이 운용하는 공모펀드는 몇 개야? | — | 200 · 2.2s |
| S9 | 피델리티자산운용이 운용하는 공모펀드는 몇 개야? | — | 200 · 22.4s |
| S10 | 공모펀드는 약관 분류별로 몇 개씩 있어? | — | 200 · 1.2s |
| S11 | 순자산이 가장 큰 운용사 상위 3개 알려줘 | — | 200 · 60.9s |
| S12 | 코어테크 펌드 1년 수익률 알려줘 | — | 200 · 11.5s |

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

### 2라운드(수리 후) — HTTP 200 · 2.1s

**answer**

```text
조회 결과 19개 범주 · 클래스 8,969개 · 펀드 3,040개 (기준일 2026-08-22).

- (미수록): 펀드 308개 (클래스 418개)
- MMF: 펀드 64개 (클래스 108개)
- 기타: 펀드 15개 (클래스 51개)
- 부동산형: 펀드 3개 (클래스 11개)
- 외화 MMF: 펀드 8개 (클래스 30개)
- 절대수익추구형: 펀드 79개 (클래스 235개)
- 주식형: 펀드 559개 (클래스 1,773개)
- 주식혼합형: 펀드 68개 (클래스 155개)
- 채권형: 펀드 145개 (클래스 610개)
- 채권혼합형: 펀드 240개 (클래스 534개)
- 커머더티형: 펀드 16개 (클래스 48개)
- 특별자산: 펀드 2개 (클래스 8개)
- 해외기타: 펀드 176개 (클래스 801개)
- 해외부동산형: 펀드 23개 (클래스 73개)
- 해외주식형: 펀드 953개 (클래스 2,784개)
- 해외주식혼합형: 펀드 134개 (클래스 327개)
- 해외채권형: 펀드 223개 (클래스 511개)
- 해외채권혼합형: 펀드 191개 (클래스 440개)
- 해외특별자산: 펀드 15개 (클래스 52개)

클래스별 유형이 갈리는 펀드 182건은 복수 범주에 계수되어 범주별 펀드 수의 합(3,222)은 전체 펀드 수(3,040)와 다릅니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 19
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,719자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 분포 결측 라벨 — GROUP BY 축의 NULL 에 '(미수록)' 이름 부여 (2026-09-01 FND-038 실측: 라벨이 빈칸이라 답변기가 418행 그룹을 통째로 빠뜨렸다)
8. [Guard] 분포 펀드수 병기 — COUNT(DISTINCT 펀드키) 3열 주입 (2026-09-02 R1 재검: '건' 이 클래스 행 수임을 답이 밝히지 못함 — 클래스/펀드 구분 누락 7번째)
9. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COALESCE(zrin_btyp_nm,'(미수록)'), COUNT(*), COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모') GROUP BY zrin_btyp_nm LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 19행 조회 (상한 30)
13. [Answer] 분포 답변 기계 조립 — 2열(범주·건수) GROUP BY 결과는 HCX 없이 전 행을 그대로 옮긴다 (2026-09-01 FND-038 재검: 19행 중 17행 나열 + '일부' 서술 재발)
```

</details>

<details><summary>retrieved_context</summary>

```text
COALESCE(zrin_btyp_nm,'(미수록)') | COUNT(*) | 펀드수
(미수록) | 418 | 308
MMF | 108 | 64
기타 | 51 | 15
부동산형 | 11 | 3
외화 MMF | 30 | 8
절대수익추구형 | 235 | 79
주식형 | 1773 | 559
주식혼합형 | 155 | 68
채권형 | 610 | 145
채권혼합형 | 534 | 240
커머더티형 | 48 | 16
특별자산 | 8 | 2
해외기타 | 801 | 176
해외부동산형 | 73 | 23
해외주식형 | 2784 | 953
해외주식혼합형 | 327 | 134
해외채권형 | 511 | 223
해외채권혼합형 | 440 | 191
해외특별자산 | 52 | 15
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

### 2라운드(수리 후) — HTTP 200 · 9.3s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 28
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,669자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) AS 운용사코드, MAX(mtco_nm) AS 운용사명, COUNT(DISTINCT CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no ELSE substr('0000000' || mtco_itm_no, -7) END) AS 펀드수 FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 3 DESC LIMIT 5
7. [Guard] SQL 기각 — 스키마에 없는 컬럼: mtco_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: mgmt_co_nm, mtco_itm_no — 뜻이 같다는 보장은 없다)
8. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 4.3s)
9. [Guard] 운용사 최빈 이름 — MAX(mgmt_co_nm) 이 합병 코드의 구명칭을 사전순으로 뽑던 것을 소수 이름 제외로 교정 (2026-09-01 FND-035 재검: 00040007 이 프랭클린템플턴(10행)으로 표기 — 정본은 우리자산운용 373행)
10. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) AS 운용사코드, MAX(CASE WHEN printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || mgmt_co_nm NOT IN ('00040007/프랭클린템플턴투자신탁운용', '00040010/삼성액티브자산운용', '00040011/미래에셋자산운용', '00040013/슈로더자산운용', '00040023/우리자산운용', '00080008/멀티에셋자산운용', '00080008/미래에셋맵스자산운용') THEN mgmt_co_nm END) AS 운용사명, COUNT(DISTINCT COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS 펀드수 FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 3 DESC LIMIT 5
11. [Guard] 재생성 후에도 실패 — 한정되지 않은 모호 컬럼: itm_no
12. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

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

### 2라운드(수리 후) — HTTP 200 · 8.8s

**answer**

```text
다음은 중국에 투자하는 공모펀드 중 일부입니다:

1. KB중국본토A주증권자투자신탁[주식]A - 14개의 클래스가 있으며, 1,453억원의 자산을 보유하고 있습니다.
2. 미래에셋차이나솔로몬증권투자신탁1호(주식)종류A - 1개의 클래스가 있고, 1,393억원의 자산이 있습니다.
3. 신한중국의꿈증권자투자신탁제2호(H)[주식]종류A - 3개의 클래스가 포함되어 있으며, 자산 규모는 1,038억원입니다.
4. 미래에셋차이나그로스증권자투자신탁1호(주식)A - 7개의 클래스가 있고, 855억원의 자산을 가지고 있습니다.
5. KB연금중국본토A주증권자투자신탁(주식) C 클래스 - 2개의 클래스가 있으며, 자산은 570억원입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,731자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 지역 컬럼 등호·미래핑 태그 LIKE 를 ','||prfd_attr_cds||',' 정식형으로 교체 (2026-09-01 FND-026 재검: ='글로벌' 오모수 + wrap 없는 LIKE 가 98/560행 누락)
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND (',' || prfd_attr_cds || ',' LIKE '%,CHN,%' OR ',' || prfd_attr_cds || ',' LIKE '%,CHN,%') AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 30행 조회 (상한 30)
12. [Answer] 내부 코드 컬럼 숨김 — prfd_attr_cds (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)
13. [Answer] 커버리지 병기 — LIMIT 도달, 전체 560행 / 248펀드 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)
14. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
15. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | 순자산_억원 | prfd_attr_cds
KR5127450020 | KB중국본토A주증권자투자신탁[주식]A | 14 | 145347201786.0 | 1453억원 | N122,M109,C101,G118,C103,D102,CHN,M111,V102
KR5153651002 | 미래에셋차이나솔로몬증권투자신탁1호(주식)종류A | 1 | 139343522568.0 | 1393억원 | M111,V102,CHN,C103,G118,D102,D105,C101
KR5117651001 | 신한중국의꿈증권자투자신탁제2호(H)[주식]종류A | 3 | 103801550961.0 | 1038억원 | V102,M111,CHN,N109,D102,G118,C103,C101,D105,M109
KR510902833M | 미래에셋차이나그로스증권자투자신탁1호(주식)A | 7 | 85543985603.0 | 855억원 | M111,V102,N135,M109,C101,C103,G118,CHN,D102
KR5127450170 | KB연금중국본토A주증권자투자신탁(주식) C 클래스 | 2 | 57096094326.0 | 570억원 | V102,M111,F103,D102,C103,C101,G110,M109,CHN
KR5153450558 | 미래에셋G2이노베이터증권자투자신탁(주식)C-P | 15 | 53590819904.0 | 535억원 | M109,G110,C101,W142,C103,G118,D102,F101,F103,M111,CHN,USA,N130,V102
KR5153450050 | 미래에셋차이나본토증권자투자신탁1호(H)(주식) A | 9 | 51347546834.0 | 513억원 | M111,V102,N122,M109,C101,CHN,G118,C103,D102
KR5152450035 | 다올중국1등주증권자투자신탁[주식] 종류C-P | 12 | 46953148656.0 | 469억원 | G118,C103,HKG,D102,W122,G110,M109,C101,M111,F103,CHN,V102
KR5127450180 | KB차이나고배당증권자투자신탁(주식)A | 9 | 44724711958.0 | 447억원 | C101,CHN,P101,M109,D102,W122,G118,C103,V102,M111
KR5127450340 | KB차이나AI테크증권자투자신탁(주식)A | 11 | 42141466412.0 | 421억원 | M109,C101,CHN,C103,D102,W122,M111,N143,V102,N130
KR5129450070 | 한화중국본토증권자투자신탁 H(주식) 종류A | 9 | 41005226943.0 | 410억원 | M111,V102,N122,M109,C101,C103,G118,CHN,D102
KR5187450051 | 에셋플러스차이나리치투게더연금증권자투자신탁1호(주식)종류C | 1 | 37096170507.0 | 370억원 | V102,D103,M111,F103,CHN,C103,C101,G110,M109
KR5148800005 | 피델리티차이나증권자투자신탁(주식-재간접형)종류A | 7 | 36490930104.0 | 364억원 | N109,M111,V102,M109,D105,C101,C103,G118,W122,D102,CHN
KR510802834M | 미래에셋차이나그로스증권자투자신탁1호(주식)A-e | 1 | 34703649167.0 | 347억원 | M111,V102,D106,N135,CHN,M109,C101,G118,C103,D102
KR510502101M | 삼성클래식중국본토중소형FOCUS연금증권자투자신탁H(주식)C | 1 | 33463426742.0 | 334억원 | V102,F103,M111,CHN,D102,C103,C101,N122,M109,P104,G110
KR510902037M | 미래에셋친디아업종대표증권자투자신탁1호(주식)종류A | 1 | 33024633137.0 | 330억원 | D102,G118,C103,C101,M109,V102,CHN,M111,IND,N138,F101
KR5147450083 | KCGI차이나증권투자신탁[주식]종류C-Pe | 11 | 32772741772.0 | 327억원 | C101,G110,CHN,D102,W122,G118,C103,F101,V102,D106,M111,F103
KR5114450261 | 삼성클래식차이나본토연금증권자투자신탁H[주식]C | 1 | 28349381587.0 | 283억원 | F102,C103,D102,G110,M109,N122,C101,CHN,M111,V102
KR5142450020 | 키움슈로더차이나그로스증권자투자신탁(주식-재간접형) A | 7 | 26936892168.0 | 269억원 | C103,G118,D102,M109,M112,C101,M111,V102,N109,CHN
KR510902023M | 미래에셋차이나디스커버리증권투자신탁1호(주식)(C-A) | 1 | 26282119575.0 | 262억원 | C101,D105,W122,D102,C103,G118,CHN,V102,M111
KR510902045M | 미래에셋차이나솔로몬증권투자신탁2호(주식)(C-A) | 1 | 26078145965.0 | 260억원 | G118,C103,D102,D105,C101,M111,V102,CHN
KR5114450087 | 삼성CHINA2.0본토증권자투자신탁 1[주식](Ci) | 9 | 25255212197.0 | 252억원 | V102,M111,CHN,D102,C103,G118,C101,N122,M109
KR510509007M | 삼성누버거버먼차이나증권자투자신탁H(주식-재간접형)C-P | 2 | 24857018941.0 | 248억원 | D102,W122,C103,M112,C101,CHN,G110,M109,V102,M111,F103
KR511102079M | 한국투자신종개인연금네비게이터중국본토증권전환형자투자신탁2호H(주식) | 1 | 24430564965.0 | 244억원 | C101,M109,CHN,G101,N122,D102,C103,F104,V102
KR5114470050 | 삼성중국본토레버리지증권자투자신탁 제1호[주식-파생재간접형]_A | 4 | 23840863685.0 | 238억원 | C103,D102,N122,M109,M112,C101,M111,V102,S117,CHN,S104
KR510902047M | 미래에셋코친디아포커스7증권자투자신탁1호(주식)(C-A) | 2 | 23538095963.0 | 235억원 | C103,G118,KOR,D102,V103,W127,D105,C101,M111,CHN,IND
KR510902839M | 미래에셋차이나그로스증권자투자신탁1호(주식)C-e | 1 | 20863479096.0 | 208억원 | D102,C103,G118,C101,M109,N135,D106,V102,M111,CHN
KR5133450011 | 카디안 차이나드래곤AShare증권자투자신탁(UH)[주식]클래스A | 10 | 20072781257.0 | 200억원 | N122,M109,D105,C101,C103,G118,D102,CHN,M111,V102
KR5148490010 | 피델리티차이나컨슈머증권자투자신탁[주식-재간접형]종류A | 9 | 18226301982.0 | 182억원 | C103,G118,CHN,W122,D102,M109,M112,C101,M111,V102,M120
KR5133450030 | 카디안 차이나드래곤AShare증권자투자신탁(H)[주식]클래스A | 11 | 18138946718.0 | 181억원 | CHN,D102,C103,G118,C101,N122,M109,D105,V102,M111
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

### 2라운드(수리 후) — HTTP 200 · 8.1s

**answer**

```text
미래에셋코어테크 펀드의 1년 수익률을 알려드리겠습니다.

- 미래에셋코어테크증권자투자신탁(주식) 종류 A: 최고 189.77%, 최저 187.09%
- 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류 A: 최고 188.63%, 최저 186.98%

두 펀드 모두 1년 동안 상당한 수익을 기록했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 10,118자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(fd_yr1_ern_r) AS "fd_yr1_ern_r_최고", MIN(fd_yr1_ern_r) AS "fd_yr1_ern_r_최저" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r <> 0 GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 6행 조회 (상한 30)
13. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_yr1_ern_r_최고 | fd_yr1_ern_r_최저
KR5153450780 | 미래에셋코어테크증권자투자신탁(주식) 종류A | 9 | 9 | 189.77 | 187.09
KR5153450910 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A | 4 | 4 | 188.63 | 186.98
KR5153451151 | 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류C-I | 3 | 3 | 13.66 | 13.19
KR5153451160 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류A-e | 5 | 5 | 15.98 | 15.21
KR5153490560 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류A | 12 | 12 | 17.73 | -41.31
KR5153490736 | 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류A-e | 4 | 4 | 17.41 | 17.31
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

### 2라운드(수리 후) — HTTP 200 · 2.5s

**answer**

```text
한국투자신탁운용이 운용하는 공모펀드는 143개(클래스 541개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
운용사 코드 2건(00040024·00040105)을 합산했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 26
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '한국투자신탁운용' → Org_00040024 (Organization) → public_funds.or_co_xtn_itt_cd='00040024' · public_funds.or_co_xtn_itt_cd='00040105'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,354자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
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

### 2라운드(수리 후) — HTTP 200 · 35.9s

**answer**

```text
미래에셋차이나솔로몬증권투자신탁 2호의 위험등급은 '**높은 위험**'이며, 등급 지수는 **2.0**입니다. 이는 모든 클래스(C1~C5 및 C-A)에 동일하게 적용됩니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 28
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — '미래에셋차이나솔로몬증권투자신탁' → Fund_284530e1ea (Fund) — ⚠️ 질문의 '2호' 와 이 노드의 코드가 가리키는 펀드가 다를 수 있어 코드 매핑을 싣지 않는다. public_funds.itm_nm 공백무시 LIKE + 호 경계(종목명검색 규칙)로 푼다
4. [Route] 미특정 보정 — KG 매핑이 public_funds 만 가리켜 그 상품군으로 좁힌다 (2026-09-01 FND-032 실측: 미특정 → 채권 테이블 SQL → 0행 오거절)
5. [Gate] 통과 — 대상 테이블 ['public_funds']
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,911자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] 호수 경계 주입 — N호 조건을 GLOB '*[^0-9]N호*' 확정식으로 교체 (2026-09-01 FND-032 실측: HCX 가 경계식을 `'2호' IN (a OR b)` 로 옮겨 항상-거짓 0행)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
10. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(zrin_fd_ivst_risk_grd_nm) AS zrin_fd_ivst_risk_grd_nm, zrin_fd_ivst_risk_gcd FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬증권투자신탁%' AND REPLACE(itm_nm,' ','') GLOB '*[^0-9]2호*' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
12. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
13. [Execute] 6행 조회 (상한 30)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | zrin_fd_ivst_risk_grd_nm | zrin_fd_ivst_risk_gcd
KR510902680M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C1 | 1 | 1 | 높은 위험 | 2.0
KR510902681M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C2 | 1 | 1 | 높은 위험 | 2.0
KR510902682M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C3 | 1 | 1 | 높은 위험 | 2.0
KR510902683M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C4 | 1 | 1 | 높은 위험 | 2.0
KR510902684M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C5 | 1 | 1 | 높은 위험 | 2.0
KR510902045M | 미래에셋차이나솔로몬증권투자신탁2호(주식)(C-A) | 2 | 2 | 높은 위험 | 2.0
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

### 2라운드(수리 후) — HTTP 200 · 8.7s

**answer**

```text
공모펀드 중 1년 수익률이 가장 높은 3개의 펀드는 다음과 같습니다.

1. 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류 Ce: 387.66%
2. NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형] Class Ae: 362.53%
3. 삼성KOSPI200 2배레버리지증권투자신탁 제1호[주식-파생재간접형]클래스 Ae: 361.3%

위 수익률은 모두 누적 수익률이며, 레버리지 및 전환형으로 인해 실제 투자 성과와 다를 수 있으므로 주의해야 합니다. 또한, 위험 등급과 기간을 함께 확인하는 것을 권장 드립니다. 다른 기간(1·3·6·18개월, 2·3·5년) 수익률 기준으로도 알고 싶으시다면 말씀해 주세요.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 27
2. [Route] 상품군 — public_funds · 근거: 머리명사 펌드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 9,781자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 대표행 보정 — GROUP BY 펀드키 주입 + MAX/MIN 감싸기 + 클래스수 병기 (2026-09-02 R7 실측: 미특정 경로에서 HCX 가 GROUP BY 를 버려 한화2.2배 3클래스 도배 — gold 는 NH-Amundi·삼성KOSPI200)
7. [Guard] 기점오류 제외 주입 — 18개월 이상 수익률 랭킹에 검증 3클래스 NOT IN 주입 (수익률기점오류_제외 규칙 미반영 실측 — 단기·개별 조회엔 미적용)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_no, TRIM(itm_nm), MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, fd_daily_bas_dt, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r > -100 AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY 3 DESC LIMIT 3
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 3행 조회 (상한 30)
12. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | TRIM(itm_nm) | fd_yr1_ern_r | fd_daily_bas_dt | 클래스수 | zrin_attr_nms
KR5129470016 | 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류Ce | 387.66 | 20260821 | 6 | 종류형 클래스펀드,온라인전용,개방,FoFs,인덱스,레버리지,추가,국내위탁판매,국내
KR5144470097 | NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형]Class Ae | 362.53 | 20260821 | 4 | 국내,온라인전용,추가,개방,레버리지,종류형 클래스펀드,인덱스,국내위탁판매
KR5114470045 | 삼성KOSPI200 2배레버리지증권투자신탁 제1호[주식-파생재간접형]클래스Ae | 361.3 | 20260821 | 4 | 레버리지,개방,온라인전용,추가,국내,국내위탁판매,종류형 클래스펀드,FoFs,인덱스
```

</details>

---

## S1. 1년 수익률이 가장 높은 공모펌드 5개 알려줘

### 2라운드(수리 후) — HTTP 200 · 9.5s

**answer**

```text
1년 수익률이 가장 높은 공모펀드 5개를 다음과 같이 안내드립니다:

1. 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류 Ce: 387.66%
2. NH-Amundi코리아2배레버리지증권투자신탁 [주식-파생형] Class Ae: 362.53%
3. 삼성KOSPI200 2배레버리지증권투자신탁 제1호 [주식-파생재간접형] 클래스 Ae: 361.3%
4. NH-Amundi 1.5배레버리지인덱스증권투자신탁 [주식-파생형] Class Ci: 257.14%
5. NH-Amundi 1.5배레버리지인덱스증권투자신탁 [주식-파생형] Class Ae: 256.89%

안내드린 모든 펀드의 수익률은 누적 수익률이며, 레버리지 및 전환형 특성 때문에 실제 투자성과와 차이가 있을 수 있으므로 주의가 필요합니다. 또한 위험 등급과 기간을 반드시 확인하시기 바랍니다. 다른 기간(1·3·6·18개월, 2·3·5년) 수익률 기준이 필요하시다면 추가로 말씀 부탁드립니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펌드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 9,781자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 대표행 보정 — GROUP BY 펀드키 주입 + MAX/MIN 감싸기 + 클래스수 병기 (2026-09-02 R7 실측: 미특정 경로에서 HCX 가 GROUP BY 를 버려 한화2.2배 3클래스 도배 — gold 는 NH-Amundi·삼성KOSPI200)
7. [Guard] 기점오류 제외 주입 — 18개월 이상 수익률 랭킹에 검증 3클래스 NOT IN 주입 (수익률기점오류_제외 규칙 미반영 실측 — 단기·개별 조회엔 미적용)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_no, TRIM(itm_nm), MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r > -100 AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY 3 DESC LIMIT 5
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 5행 조회 (상한 30)
12. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | TRIM(itm_nm) | fd_yr1_ern_r | 클래스수 | zrin_attr_nms
KR5129470016 | 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형) 종류Ce | 387.66 | 6 | 종류형 클래스펀드,온라인전용,개방,FoFs,인덱스,레버리지,추가,국내위탁판매,국내
KR5144470097 | NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형]Class Ae | 362.53 | 4 | 국내,온라인전용,추가,개방,레버리지,종류형 클래스펀드,인덱스,국내위탁판매
KR5114470045 | 삼성KOSPI200 2배레버리지증권투자신탁 제1호[주식-파생재간접형]클래스Ae | 361.3 | 4 | 레버리지,개방,온라인전용,추가,국내,국내위탁판매,종류형 클래스펀드,FoFs,인덱스
KR513706005M | NH-Amundi1.5배레버리지인덱스증권투자신탁(주식-파생형)Ci | 257.14 | 1 | 추가,국내,개방,레버리지,국내위탁판매,인덱스,종류형 클래스펀드
KR5144470017 | NH-Amundi 1.5배레버리지인덱스증권투자신탁[주식-파생형]Class Ae | 256.89 | 4 | 추가,온라인전용,국내,국내위탁판매,개방,인덱스,레버리지,종류형 클래스펀드
```

</details>

---

## S2. 3년 수익률이 가장 나쁜 공모펀드 3개 알려줘

### 2라운드(수리 후) — HTTP 200 · 7.1s

**answer**

```text
3년 수익률이 가장 나쁜 공모펀드 3개를 알려드리겠습니다.

1. 미래에셋아시아퍼시픽소비성장증권자투자신탁1호(주식)종류C3: -80.36%
2. 삼성KOSPI200인버스인덱스증권투자신탁제1호[채권-파생형]_클래스C: -78.08%
3. 삼성배당주장기증권투자신탁 1[주식](C 2): -77.8%

위의 세 가지 펀드는 모두 3년 동안 마이너스 수익률을 기록하였으며, 특히 '미래에셋아시아퍼시픽소비성장증권자투자신탁1호(주식)종류C3'가 가장 낮은 수익률을 보였습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,601자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 대표행 보정 — GROUP BY 펀드키 주입 + MAX/MIN 감싸기 + 클래스수 병기 (2026-09-02 R7 실측: 미특정 경로에서 HCX 가 GROUP BY 를 버려 한화2.2배 3클래스 도배 — gold 는 NH-Amundi·삼성KOSPI200)
7. [Guard] 기점오류 제외 주입 — 18개월 이상 수익률 랭킹에 검증 3클래스 NOT IN 주입 (수익률기점오류_제외 규칙 미반영 실측 — 단기·개별 조회엔 미적용)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_no, TRIM(itm_nm), MIN(fd_yr3_ern_r) AS fd_yr3_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_yr3_ern_r IS NOT NULL AND fd_yr3_ern_r < 0 AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY 3 ASC LIMIT 3
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 3행 조회 (상한 30)
12. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | TRIM(itm_nm) | fd_yr3_ern_r | 클래스수 | zrin_attr_nms
KR5153450037 | 미래에셋아시아퍼시픽소비성장증권자투자신탁1호(주식)종류C3 | -80.36 | 3 | 추가,국외,종류형 클래스펀드,국내위탁판매,개방,아-태(ex 일),해외비과세,소비재섹터,자펀드
KR5114470025 | 삼성KOSPI200인버스인덱스증권투자신탁제1호[채권-파생형]_클래스C | -78.08 | 3 | 추가,국내,국내위탁판매,인덱스,개방,리버스,종류형 클래스펀드
KR5114450142 | 삼성배당주장기증권투자신탁 1[주식](C 2) | -77.8 | 1 | 국내위탁판매,개방,국내,종류형 클래스펀드,배당주,추가
```

</details>

---

## S3. 삼성코리아대표 펀드 1년 수익률 알려줘

### 2라운드(수리 후) — HTTP 200 · 9.2s

**answer**

```text
삼성코리아대표 펀드의 1년 수익률을 알려드리겠습니다.

- 삼성코리아대표분할매수증권투자신탁 1[주식혼합]: 105.49%
- 삼성코리아대표증권자투자신탁 제1호[주식](A): 109.72%

두 펀드 모두 누적 수익률이며, 기간은 1년입니다. 다만, 목표전환증권투자신탁 제1호[채권] A 및 분할매수목표전환증권투자신탁 1[채권]_A 의 경우 관련 정보가 제공되지 않아 답변을 드리기 어렵습니다. 추가적인 기간이 있으시다면 말씀해 주시기 바랍니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 9,781자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
7. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(fd_yr1_ern_r) AS "fd_yr1_ern_r_최고", MIN(fd_yr1_ern_r) AS "fd_yr1_ern_r_최저" FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%삼성코리아대표%' AND prvo_pbff_desc = '공모' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 4행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_yr1_ern_r_최고 | fd_yr1_ern_r_최저
KR5114450100 | 삼성코리아대표분할매수증권투자신탁 1[주식혼합] | 1 | 1 | 105.49 | 105.49
KR5114450011 | 삼성코리아대표증권자투자신탁 제1호[주식](A) | 9 | 9 | 109.72 | 106.71
KR5114450170 | 삼성코리아대표그룹목표전환증권투자신탁 제1호[채권] A | 2 | 0 |  | 
KR5114440010 | 삼성코리아대표분할매수목표전환증권투자신탁 1[채권]_A | 2 | 0 |  | 
```

</details>

---

## S4. KB차이나 펀드 위험등급 알려줘

### 2라운드(수리 후) — HTTP 200 · 24.6s

**answer**

```text
KB차이나 관련 펀드의 위험 등급은 다음과 같습니다.

1. KB차이나고배당증권자투자신탁(주식)A - 높은 위험
2. KB차이나AI테크증권자투자신탁(주식)A - 높은 위험
3. KB차이나그로스증권자투자신탁(주식)Ae클래스 - 높은 위험
4. KB차이나고배당40증권자투자신탁(채권혼합)C-P클래스 - 보통 위험
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 9,911자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
7. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(zrin_fd_ivst_risk_grd_nm) AS zrin_fd_ivst_risk_grd_nm FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%KB차이나%' AND zrin_fd_ivst_risk_gcd IS NOT NULL GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 4행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | zrin_fd_ivst_risk_grd_nm
KR5127450180 | KB차이나고배당증권자투자신탁(주식)A | 9 | 9 | 높은 위험
KR5127450340 | KB차이나AI테크증권자투자신탁(주식)A | 11 | 11 | 높은 위험
KR5127651011 | KB차이나그로스증권자투자신탁(주식)Ae클래스 | 12 | 12 | 높은 위험
KR5127450227 | KB차이나고배당40증권자투자신탁(채권혼합)C-P클래스 | 3 | 3 | 보통 위험
```

</details>

---

## S5. 미래에셋차이나솔로몬증권투자신탁 3호 위험등급 알려줘

### 2라운드(수리 후) — HTTP 200 · 3.6s

**answer**

```text
미래에셋차이나솔로몬증권투자신탁 3호의 위험 등급은 '**높은 위험**'이며, 위험 등급 코드는 **2.0**입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 28
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — '미래에셋차이나솔로몬증권투자신탁' → Fund_284530e1ea (Fund) — ⚠️ 질문의 '3호' 와 이 노드의 코드가 가리키는 펀드가 다를 수 있어 코드 매핑을 싣지 않는다. public_funds.itm_nm 공백무시 LIKE + 호 경계(종목명검색 규칙)로 푼다
4. [Route] 미특정 보정 — KG 매핑이 public_funds 만 가리켜 그 상품군으로 좁힌다 (2026-09-01 FND-032 실측: 미특정 → 채권 테이블 SQL → 0행 오거절)
5. [Gate] 통과 — 대상 테이블 ['public_funds']
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,911자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] 호수 경계 주입 — N호 조건을 GLOB '*[^0-9]N호*' 확정식으로 교체 (2026-09-01 FND-032 실측: HCX 가 경계식을 `'2호' IN (a OR b)` 로 옮겨 항상-거짓 0행)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
10. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(zrin_fd_ivst_risk_grd_nm) AS zrin_fd_ivst_risk_grd_nm, zrin_fd_ivst_risk_gcd FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬증권투자신탁%' AND REPLACE(itm_nm,' ','') GLOB '*[^0-9]3호*' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
12. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
13. [Execute] 1행 조회 (상한 30)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | zrin_fd_ivst_risk_grd_nm | zrin_fd_ivst_risk_gcd
KR5153651035 | 미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C2 | 4 | 4 | 높은 위험 | 2.0
```

</details>

---

## S6. 인도에 투자하는 공모펀드 알려줘

### 2라운드(수리 후) — HTTP 200 · 24.9s

**answer**

```text
다음은 인도에 투자하는 공모펀드 목록입니다:

1. 미래에셋인도중소형포커스증권자투자신탁1호(주식)C-P2e - 673억원
2. 미래에셋인도중소형포커스증권자투자신탁1호(주식)종류A - 565억원
3. 미래에셋연금인디아업종대표증권자투자신탁1호(주식)종류C-P2e - 407억원
4. 미래에셋인디아디스커버리증권자투자신탁 1(주식)종류A - 399억원
5. 미래에셋인도중소형포커스증권자투자신탁1호(주식)C-Pe - 392억원
6. 미래에셋인도중소형포커스증권자투자신탁(주식)A-e - 389억원
7. 미래에셋인디아솔로몬증권투자신탁1호(주식)(C-A) - 347억원
8. 미래에셋친디아업종대표증권자투자신탁1호(주식)종류A - 330억원
9. 미래에셋인도채권증권자투자신탁1호(채권)종류C-i - 279억원
10. 미래에셋인도중소형포커스증권자투자신탁1호(주식)C-e - 264억원
11. 미래에셋코친디아포커스7증권자투자신탁1호(주식)(C-A) - 235억원
12. 피델리티인디아증권자투자신탁(주식-재간접형) CP-e - 234억원
13. 삼성인디아증권자투자신탁제2호[주식]_Cpe(퇴직연금) - 221억원
14. 삼성퇴직연금인디아40증권자투자신탁제1호[채권혼합]_Ce - 154억원
15. 미래에셋친디아컨슈머증권투자신탁1(주식)종류A - 153억원
16. 삼성인도중소형FOCUS증권자투자신탁UH[주식]_Cpe(퇴직연금) - 138억원
17. 미래에셋인디아디스커버리증권자투자신탁 1(주식)종류A-e - 122억원
18. 삼성퇴직연금인도중소형FOCUS40증권자투자신탁UH[채권혼합]_Ce - 113억원
19. 미래에셋연금인디아업종대표증권자투자신탁1호(주식)C-Pe - 112억원
20. 미래에셋인디아솔로몬증권투자신탁1호(주식)A-e - 107억원
21. 피델리티인디아증권자투자신탁(주식-재간접형)PRS-e - 102억원
22. 미래에셋연금인디아인프라증권자투자신탁1호(주식)C-Pe - 92억원
23. 미래에셋인디아인프라섹터증권자투자신탁1호(주식)C-E - 72억원
24. 삼성인도중소형FOCUS증권자투자신탁H[주식-파생형]_Ae - 66억원
25. 미래에셋우리아이친디아업종대표증권자투자신탁1호(주식)(C-A) - 58억원
26. 미래에셋코친디아포커스7증권자투자신탁1호(주식)C5 - 53억원
27. 우리프랭클린인디아증권자투자신탁(UH)(주식-재간접형)ClassC-P - 42억원
28. 미래에셋우리아이친디아업종대표증권자투자신탁1호(주식)C5 - 39억원
29. NH-Amundi 인도네시아 포커스 증권투자신탁[주식] Class C-P2e(퇴직연금) - 35억원
30. 미래에셋인도채권증권자투자신탁1호(채권)A-e - 34억원

이 목록은 제공된 데이터를 기반으로 한 것이며, 더 많은 펀드가 있을 수 있습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,731자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", prfd_attr_cds, zrin_attr_nms FROM public_funds WHERE prvo_pbff_desc = '공모' AND (prfd_attr_cds LIKE '%IND%' OR zrin_attr_nms LIKE '%인도%') AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 30행 조회 (상한 30)
11. [Answer] 내부 코드 컬럼 숨김 — prfd_attr_cds (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)
12. [Answer] 커버리지 병기 — LIMIT 도달, 전체 142행 / 59펀드 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)
13. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | 순자산_억원 | prfd_attr_cds | zrin_attr_nms
KR5153450345 | 미래에셋인도중소형포커스증권자투자신탁1호(주식)C-P2e | 2 | 67311236798.0 | 673억원 | G118,C103,D102,M109,G115,C101,F103,M111,IND,N135,V102,D106,W110,F101 | 온라인전용,투자전략(전통),국내위탁판매,해외비과세,인도,개방,단순세액공제,추가,종류형 클래스펀드,국외,자펀드,아시아신흥국,단순비과세,퇴직연금
KR5153450340 | 미래에셋인도중소형포커스증권자투자신탁1호(주식)종류A | 8 | 56534832883.0 | 565억원 | D102,G118,C103,C101,P104,M109,N135,IND,V102,M111,W110 | 투자전략(전통),자펀드,종류형 클래스펀드,아시아신흥국,국외,중소형주,추가,해외비과세,인도,국내위탁판매,개방
KR5153450337 | 미래에셋연금인디아업종대표증권자투자신탁1호(주식)종류C-P2e | 3 | 40776634088.0 | 407억원 | D102,IND,C103,G118,C101,M109,G115,D106,V102,M111,F103,N138 | 단순세액공제,퇴직연금,국내위탁판매,인도,해외비과세,개방,종류형 클래스펀드,투자전략(우량주/블루칩),온라인전용,국외,추가,자펀드
KR5153651001 | 미래에셋인디아디스커버리증권자투자신탁 1(주식)종류A | 1 | 39986003046.0 | 399억원 | V102,M111,D102,G118,C103,C101,D105,IND | 개방,인도,종류형 클래스펀드,추가,국외,국내외혼합판매,해외비과세,국내위탁판매
KR510902922M | 미래에셋인도중소형포커스증권자투자신탁1호(주식)C-Pe | 1 | 39283255259.0 | 392억원 | W110,D101,N135,D106,V102,M111,F103,C101,G110,M109,P104,IND,C103,G118 | 연금저축,중소형주,아시아신흥국,자펀드,개방,인도,종류형 클래스펀드,투자전략(전통),단순세액공제,추가,국외,온라인전용,해외비과세,직판
KR510902914M | 미래에셋인도중소형포커스증권자투자신탁(주식)A-e | 1 | 38996980801.0 | 389억원 | W110,M111,N135,D106,V102,M109,P104,IND,C101,C103,G118,D102 | 투자전략(전통),온라인전용,해외비과세,아시아신흥국,종류형 클래스펀드,자펀드,개방,인도,국내위탁판매,국외,중소형주,추가
KR510102008M | 미래에셋인디아솔로몬증권투자신탁1호(주식)(C-A) | 1 | 34731054857.0 | 347억원 | M111,V102,C103,G118,IND,D102,D105,C101 | 국내외혼합판매,종류형 클래스펀드,해외비과세,국내위탁판매,추가,국외,개방,인도
KR510902037M | 미래에셋친디아업종대표증권자투자신탁1호(주식)종류A | 1 | 33024633137.0 | 330억원 | D102,G118,C103,C101,M109,V102,CHN,M111,IND,N138,F101 | 종류형 클래스펀드,단순비과세,자펀드,투자전략(우량주/블루칩),인도,개방,국외,중국,국내위탁판매,추가,해외비과세
KR5153420092 | 미래에셋인도채권증권자투자신탁1호(채권)종류C-i | 8 | 27945364331.0 | 279억원 | C103,D102,IND,M109,C101,M111,V102 | 국내위탁판매,추가,국외,종류형 클래스펀드,자펀드,개방,인도
KR510902919M | 미래에셋인도중소형포커스증권자투자신탁1호(주식)C-e | 1 | 26456147075.0 | 264억원 | M111,N135,D106,V102,IND,W110,C103,G118,D102,M109,P104,C101 | 자펀드,아시아신흥국,투자전략(전통),온라인전용,중소형주,인도,개방,해외비과세,추가,종류형 클래스펀드,국외,국내위탁판매
KR510902047M | 미래에셋코친디아포커스7증권자투자신탁1호(주식)(C-A) | 2 | 23538095963.0 | 235억원 | C103,G118,KOR,D102,V103,W127,D105,C101,M111,CHN,IND | 국내위탁판매,종류형 클래스펀드,인도,개방,추가,국내외,중국,국내외혼합판매,한중인,해외비과세,한국
KR5148450086 | 피델리티인디아증권자투자신탁(주식-재간접형) CP-e | 12 | 23425360287.0 | 234억원 | W110,F101,IND,V102,D106,M111,F103,C101,G115,M109,D102,G118,C103 | 종류형 클래스펀드,자펀드,국외,추가,단순비과세,인도,아시아신흥국,개방,온라인전용,퇴직연금,해외비과세,단순세액공제,국내위탁판매
KR5114450449 | 삼성인디아증권자투자신탁제2호[주식]_Cpe(퇴직연금) | 9 | 22125688629.0 | 221억원 | D102,G118,C103,IND,C101,G115,M109,V102,D106,M111,F103,W110,F101 | 국외,추가,인도,퇴직연금,개방,아시아신흥국,온라인전용,해외비과세,단순세액공제,단순비과세,국내위탁판매,종류형 클래스펀드,자펀드
KR5114430021 | 삼성퇴직연금인디아40증권자투자신탁제1호[채권혼합]_Ce | 2 | 15481287832.0 | 154억원 | W110,M111,F103,D106,G115,M109,IND,C101,C103,V103,D102 | 추가,국내외,아시아신흥국,인도,퇴직연금,개방,국내위탁판매,자펀드,종류형 클래스펀드,단순세액공제,온라인전용
KR5153450140 | 미래에셋친디아컨슈머증권투자신탁1(주식)종류A | 13 | 15308791902.0 | 153억원 | D102,G118,C103,C101,O132,IND,D105,CHN,V102,M111,W121 | 개방,인도,국내외혼합판매,중국,국외,추가,친디아,국내위탁판매,해외비과세,종류형 클래스펀드,소비재섹터
KR5114450618 | 삼성인도중소형FOCUS증권자투자신탁UH[주식]_Cpe(퇴직연금) | 4 | 13898115574.0 | 138억원 | D102,C103,G118,C101,G115,IND,M109,D106,V102,N135,M111,F103,F101,W110 | 개방,종류형 클래스펀드,국내위탁판매,자펀드,인도,퇴직연금,해외비과세,추가,단순세액공제,국외,온라인전용,아시아신흥국,투자전략(전통),단순비과세
KR5153651000 | 미래에셋인디아디스커버리증권자투자신탁 1(주식)종류A-e | 3 | 12217739437.0 | 122억원 | G118,C103,IND,D102,C101,M111,V102,D106 | 해외비과세,국내위탁판매,온라인전용,종류형 클래스펀드,추가,국외,인도,개방
KR5114430149 | 삼성퇴직연금인도중소형FOCUS40증권자투자신탁UH[채권혼합]_Ce | 2 | 11343475495.0 | 113억원 | D106,F103,M111,W110,V103,D102,C103,IND,C101,G115,M109,P104 | 아시아신흥국,추가,종류형 클래스펀드,자펀드,인도,개방,국내위탁판매,퇴직연금,국내외,온라인전용,단순세액공제,중소형주
KR510902871M | 미래에셋연금인디아업종대표증권자투자신탁1호(주식)C-Pe | 1 | 11280567084.0 | 112억원 | N138,M111,F103,V102,D106,G110,M109,C101,C103,IND,D102 | 단순세액공제,국내위탁판매,종류형 클래스펀드,자펀드,온라인전용,투자전략(우량주/블루칩),연금저축,국외,추가,인도,개방
KR510902856M | 미래에셋인디아솔로몬증권투자신탁1호(주식)A-e | 1 | 10789520223.0 | 107억원 | V102,D106,M111,C101,IND,D102,G118,C103 | 국내위탁판매,종류형 클래스펀드,개방,인도,추가,국외,해외비과세,온라인전용
KR515002055M | 피델리티인디아증권자투자신탁(주식-재간접형)PRS-e | 1 | 10234581059.0 | 102억원 | G118,C103,D102,G110,M109,C101,F103,M111,V102,D106,IND,W110 | 자펀드,국내위탁판매,추가,국외,단순세액공제,연금저축,개방,인도,아시아신흥국,종류형 클래스펀드,해외비과세,온라인전용
KR510902882M | 미래에셋연금인디아인프라증권자투자신탁1호(주식)C-Pe | 1 | 9267262434.0 | 92억원 | M111,F103,D106,V102,C103,D102,M109,G110,IND,C101 | 자펀드,온라인전용,연금저축,국내위탁판매,국외,추가,종류형 클래스펀드,단순세액공제,인도,개방
KR5153450256 | 미래에셋인디아인프라섹터증권자투자신탁1호(주식)C-E | 3 | 7294021806.0 | 72억원 | M111,V102,D106,N155,G118,C103,D102,M109,C101,IND | 인프라,자펀드,종류형 클래스펀드,해외비과세,인도,온라인전용,개방,추가,국내위탁판매,국외
KR5114470137 | 삼성인도중소형FOCUS증권자투자신탁H[주식-파생형]_Ae | 2 | 6694102653.0 | 66억원 | M111,IND,N135,D106,V102,W110,C103,G118,D102,M109,C101 | 종류형 클래스펀드,추가,투자전략(전통),국외,온라인전용,해외비과세,인도,아시아신흥국,개방,자펀드,국내위탁판매
KR510902075M | 미래에셋우리아이친디아업종대표증권자투자신탁1호(주식)(C-A) | 1 | 5896288652.0 | 58억원 | V102,M111,W121,IND,CHN,D102,C103,G118,N107,C101,D105,M109 | 추가,국외,중국,국내외혼합판매,개방,인도,종류형 클래스펀드,국내위탁판매,친디아,어린이펀드,자펀드,해외비과세
KR510902675M | 미래에셋코친디아포커스7증권자투자신탁1호(주식)C5 | 1 | 5321862135.0 | 53억원 | C101,C103,G118,KOR,D102,W127,V103,IND,CHN,M111 | 중국,추가,한국,개방,한중인,인도,종류형 클래스펀드,국내외,해외비과세,국내위탁판매
KR5134490039 | 우리프랭클린인디아증권자투자신탁(UH)(주식-재간접형)ClassC-P | 7 | 4286096770.0 | 42억원 | V102,M111,F103,M112,C101,G110,M109,IND,D102,C103 | 단순세액공제,국내위탁판매,추가,종류형 클래스펀드,국외,FoFs,자펀드,인도,연금저축,개방
KR510902575M | 미래에셋우리아이친디아업종대표증권자투자신탁1호(주식)C5 | 1 | 3998761049.0 | 39억원 | D102,CHN,G118,IND,C103,C101,N107,M109,V102,M111,W121 | 인도,개방,추가,국외,중국,종류형 클래스펀드,어린이펀드,해외비과세,자펀드,국내위탁판매,친디아
KR5144450052 | NH-Amundi 인도네시아 포커스 증권투자신탁[주식] Class C-P2e(퇴직연금) | 7 | 3509685271.0 | 35억원 | G115,C101,C103,G118,D102,IDN,F101,W112,M111,D106,V102 | 온라인전용,개방,퇴직연금,해외비과세,국내위탁판매,추가,국외,동남아,종류형 클래스펀드,단순비과세,인도네시아
KR510901112M | 미래에셋인도채권증권자투자신탁1호(채권)A-e | 1 | 3437059613.0 | 34억원 | C103,D102,IND,M109,C101,M111,V102,D106 | 종류형 클래스펀드,인도,개방,국외,온라인전용,추가,자펀드,국내위탁판매
```

</details>

---

## S7. 베트남에 투자하는 공모펀드 알려줘

### 2라운드(수리 후) — HTTP 200 · 9.9s

**answer**

```text
조회 결과에 베트남에 투자하는 공모펀드는 다음과 같습니다.

1. 한국투자베트남그로스증권자투자신탁(주식) 종류A - 1066억원
2. 한국투자연금베트남증권자투자신탁(주식혼합) 종류 C - 537억원
3. 한국투자베트남증권자투자신탁1호(주식혼합) 종류 C - 516억원
4. 한국투자베트남그로스증권자투자신탁(주식)C-e - 491억원
5. 한국투자베트남그로스증권자투자신탁UH(주식)종류A - 252억원
6. 한국투자연금베트남그로스증권자투자신탁(주식)C - 235억원
7. 미래에셋베트남증권자투자신탁1호(UH)(주식)종류C-P2e - 223억원
8. 한국투자베트남그로스증권자투자신탁UH(주식)A-e - 206억원
9. 한국투자베트남그로스증권자투자신탁UH(주식)C-e - 180억원
10. 유리베트남알파증권자투자신탁[주식]A - 163억원

이는 일부이며, 더 많은 베트남 투자 공모펀드가 있을 수 있습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,731자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 지역 컬럼 등호·미래핑 태그 LIKE 를 ','||prfd_attr_cds||',' 정식형으로 교체 (2026-09-01 FND-026 재검: ='글로벌' 오모수 + wrap 없는 LIKE 가 98/560행 누락)
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND (',' || prfd_attr_cds || ',' LIKE '%,VNM,%' OR prfd_attr_cds LIKE '%VNM%') AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 30행 조회 (상한 30)
12. [Answer] 내부 코드 컬럼 숨김 — prfd_attr_cds (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)
13. [Answer] 커버리지 병기 — LIMIT 도달, 전체 119행 / 38펀드 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)
14. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
15. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | 순자산_억원 | prfd_attr_cds
KR5113450190 | 한국투자베트남그로스증권자투자신탁(주식) 종류A | 6 | 106602228139.0 | 1066억원 | C103,G118,D102,M109,C101,M111,V102,N135,VNM,F101,W110
KR5113440030 | 한국투자연금베트남증권자투자신탁(주식혼합) 종류 C | 4 | 53732856913.0 | 537억원 | VNM,W110,F103,M111,V102,G110,M109,C101,C103,D102
KR5113440021 | 한국투자베트남증권자투자신탁1호(주식혼합) 종류 C | 4 | 51667929305.0 | 516억원 | M111,VNM,V102,W110,C103,D102,M109,C101
KR511102094M | 한국투자베트남그로스증권자투자신탁(주식)C-e | 1 | 49193036845.0 | 491억원 | M111,V102,D106,N135,VNM,W110,G118,C103,D102,M109,C101
KR5113450170 | 한국투자베트남그로스증권자투자신탁UH(주식)종류A | 1 | 25220110919.0 | 252억원 | D102,C103,G118,C101,M109,V102,N135,M111,W110,VNM
KR511102098M | 한국투자연금베트남그로스증권자투자신탁(주식)C | 1 | 23574604295.0 | 235억원 | M109,G110,C101,C103,D102,M111,VNM,F103,V102,N135
KR5137450077 | 미래에셋베트남증권자투자신탁1호(UH)(주식)종류C-P2e | 10 | 22389820109.0 | 223억원 | D106,V102,W112,F103,M111,F101,D102,VNM,C103,G118,C101,M109,G115
KR511102095M | 한국투자베트남그로스증권자투자신탁UH(주식)A-e | 1 | 20641331645.0 | 206억원 | C103,G118,D102,VNM,M109,C101,M111,D106,V102,N135,F101,W110
KR511102096M | 한국투자베트남그로스증권자투자신탁UH(주식)C-e | 1 | 18086686743.0 | 180억원 | M109,C101,G118,C103,D102,VNM,W110,F101,M111,N135,V102,D106
KR5151450050 | 유리베트남알파증권자투자신탁[주식]A | 10 | 16349205938.0 | 163억원 | V102,W112,M111,F101,D102,C103,G118,C101,M109,VNM
KR511102092M | 한국투자베트남그로스증권자투자신탁UH(주식)C4 | 1 | 11942970292.0 | 119억원 | F101,W110,VNM,V102,N135,M111,C101,M109,D102,C103,G118
KR5237000001 | 미래에셋베트남증권투자회사1호(주식혼합) 종류A | 1 | 10676188314.0 | 106억원 | C103,D102,C101,M111,V102,VNM
KR5127440025 | KB베트남포커스증권자투자신탁(주식혼합)(H)C5클래스 | 7 | 10203176852.0 | 102억원 | D102,C103,VNM,C101,M109,V102,M111,W110
KR5137470130 | 미래에셋베트남증권자투자신탁1호(H-USD)(주식-파생형)종류A | 7 | 9294090197.0 | 92억원 | V102,M111,W112,F101,D102,G118,C103,VNM,C101,M109
KR511102099M | 한국투자연금베트남그로스증권자투자신탁(주식)C-e | 1 | 7742548866.0 | 77억원 | G110,M109,C101,C103,D102,VNM,F103,M111,V102,D106,N135
KR510902976M | 미래에셋베트남증권자투자신탁1호(UH)(주식)C-Pe | 1 | 7635874023.0 | 76억원 | C101,G110,M109,VNM,D102,C103,G118,F101,D106,V102,W112,M111,F103
KR5151451001 | 유리베트남알파증권자투자신탁UH[주식] C-P1e | 2 | 7280670715.0 | 72억원 | D106,V102,W112,F103,M111,F101,VNM,D102,C103,G118,C101,G115,M109
KR5114450429 | 삼성아세안플러스베트남증권자투자신탁 UH[주식]_CPe(퇴직연금) | 11 | 7072861936.0 | 70억원 | D106,V102,W112,F103,M111,F101,D102,C103,G118,VNM,C101,G115,M109
KR5153450520 | 미래에셋베트남&차이나증권투자신탁1호(주식)종류A | 2 | 6977815572.0 | 69억원 | D102,CHN,W128,G118,C103,C101,D105,V102,M111,VNM
KR5127470087 | KB스타베트남VN30인덱스증권자투자신탁[주식-파생형]Ae | 8 | 5436480838.0 | 54억원 | C101,M109,D102,C103,VNM,S104,D106,V102,W112,M111
KR510906204M | 미래에셋베트남증권자투자신탁1호(H-USD)(주식-파생형)A-e | 1 | 4762744413.0 | 47억원 | C101,M109,D102,C103,G118,F101,D106,V102,VNM,W112,M111
KR5149450076 | IBK베트남플러스아시아증권 투자신탁[주식]Ce | 2 | 4158494367.0 | 41억원 | VNM,D106,V102,M111,C101,D102,C103,G118
KR513502177M | 미래에셋베트남&차이나증권투자신탁1호(주식)종류C4 | 1 | 3130468430.0 | 31억원 | V102,CHN,M111,D102,W128,C103,G118,VNM,C101,D105
KR510906209M | 미래에셋베트남증권자투자신탁1호(H-USD)(주식-파생형)C-e | 1 | 2727230295.0 | 27억원 | F101,D106,V102,W112,M111,C101,VNM,M109,D102,C103,G118
KR510906211M | 미래에셋베트남증권자투자신탁1호(H-USD)(주식-파생형)C-Pe | 1 | 2332988270.0 | 23억원 | G118,C103,D102,G110,M109,C101,M111,F103,W112,V102,D106,VNM,F101
KR510902974M | 미래에셋베트남증권자투자신탁1호(UH)(주식)C-e | 1 | 2298758573.0 | 22억원 | F101,V102,D106,M111,VNM,W112,C101,M109,D102,G118,C103
KR5114470100 | 삼성아세안플러스베트남증권자투자신탁H[주식-파생형]_A | 9 | 1790676645.0 | 17억원 | V102,M111,W112,F101,D102,G118,C103,VNM,C101,M109
KR5151430032 | 유리베트남공모주증권자투자신탁[채권혼합]C-P1e | 4 | 1713952569.0 | 17억원 | D102,VNM,R106,C103,C101,M109,G115,V102,D106,M111,R105
KR511102089M | 한국투자베트남그로스증권자투자신탁UH(주식)C | 1 | 472224736.0 | 4억원 | C103,G118,D102,M109,C101,M111,VNM,N135,V102,F101,W110
KR5153450667 | 미래에셋베트남고배당IPO증권자투자신탁(H-USD)(주식-파생형)종류A-e | 7 | 265003277.0 | 2억원 | D106,V102,M111,VNM,D102,C103,C101,P101,M109
```

</details>

---

## S8. KB자산운용이 운용하는 공모펀드는 몇 개야?

### 2라운드(수리 후) — HTTP 200 · 2.2s

**answer**

```text
KB자산운용이 운용하는 공모펀드는 129개(클래스 625개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 24
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,340자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
129 | 625
```

</details>

---

## S9. 피델리티자산운용이 운용하는 공모펀드는 몇 개야?

### 2라운드(수리 후) — HTTP 200 · 22.4s

**answer**

```text
피델리티자산운용이 운용하는 공모펀드는 106개(클래스 246개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 26
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '피델리티자산운용' → Org_00080029 (Organization) → public_funds.or_co_xtn_itt_cd='00080029'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,342자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00080029') AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
106 | 246
```

</details>

---

## S10. 공모펀드는 약관 분류별로 몇 개씩 있어?

### 2라운드(수리 후) — HTTP 200 · 1.2s

**answer**

```text
조회 결과 9개 범주 · 클래스 8,969개 · 펀드 3,040개 (기준일 2026-08-22).

- MMF: 펀드 82개 (클래스 156개)
- 재간접: 펀드 913개 (클래스 2,594개)
- 주식형: 펀드 1,218개 (클래스 3,735개)
- 주식혼합: 펀드 110개 (클래스 239개)
- 채권형: 펀드 219개 (클래스 833개)
- 채권혼합: 펀드 389개 (클래스 933개)
- 특별자산: 펀드 5개 (클래스 12개)
- 파생상품: 펀드 90개 (클래스 330개)
- 혼합자산: 펀드 21개 (클래스 137개)

클래스별 유형이 갈리는 펀드 7건은 복수 범주에 계수되어 범주별 펀드 수의 합(3,047)은 전체 펀드 수(3,040)와 다릅니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,719자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 분포 결측 라벨 — GROUP BY 축의 NULL 에 '(미수록)' 이름 부여 (2026-09-01 FND-038 실측: 라벨이 빈칸이라 답변기가 418행 그룹을 통째로 빠뜨렸다)
8. [Guard] 분포 펀드수 병기 — COUNT(DISTINCT 펀드키) 3열 주입 (2026-09-02 R1 재검: '건' 이 클래스 행 수임을 답이 밝히지 못함 — 클래스/펀드 구분 누락 7번째)
9. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COALESCE(or_attr_desc,'(미수록)'), COUNT(*), COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모') GROUP BY or_attr_desc LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 9행 조회 (상한 30)
13. [Answer] 분포 답변 기계 조립 — 2열(범주·건수) GROUP BY 결과는 HCX 없이 전 행을 그대로 옮긴다 (2026-09-01 FND-038 재검: 19행 중 17행 나열 + '일부' 서술 재발)
```

</details>

<details><summary>retrieved_context</summary>

```text
COALESCE(or_attr_desc,'(미수록)') | COUNT(*) | 펀드수
MMF | 156 | 82
재간접 | 2594 | 913
주식형 | 3735 | 1218
주식혼합 | 239 | 110
채권형 | 833 | 219
채권혼합 | 933 | 389
특별자산 | 12 | 5
파생상품 | 330 | 90
혼합자산 | 137 | 21
```

</details>

---

## S11. 순자산이 가장 큰 운용사 상위 3개 알려줘

### 2라운드(수리 후) — HTTP 200 · 60.9s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 23
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — 매칭 없음
4. [Gate] 통과 — 대상 테이블 미특정
5. [Plan] 근거문서 조립 — 대상 마스터 4테이블 · 51,788자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Route] SQL 사후 보정 — FROM public_funds → 그 상품군의 답변 규칙·이름 필터 적용 (2026-09-02 R7 재검: 미특정 경로는 답변 규칙이 4도메인으로 희석되고 상품명 필터 가드가 꺼진다)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT mtco_nm, COUNT(*) as cnt FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY mtco_nm ORDER BY cnt DESC LIMIT 3
8. [Guard] SQL 기각 — 스키마에 없는 컬럼: mtco_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: mgmt_co_nm, mtco_itm_no — 뜻이 같다는 보장은 없다)
9. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 3.5s)
10. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT mgmt_co_nm, COUNT(*) as cnt FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY mgmt_co_nm ORDER BY cnt DESC LIMIT 3
11. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: mgmt_co_nm(→ ext_fund_page 컬럼이다. 이 테이블에는 없다)
12. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## S12. 코어테크 펌드 1년 수익률 알려줘

### 2라운드(수리 후) — HTTP 200 · 11.5s

**answer**

```text
조회된 '코어테크' 관련 펀드들의 1년 수익률을 안내드리겠습니다.

1. 미래에셋코어테크증권자투자신탁(주식) 종류 A: 최고 189.77%, 최저 187.09%
2. 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류 A: 최고 188.63%, 최저 186.98%

이 외에 '차이나', '글로벌" 등의 이름이 들어간 유사 펀드들도 있으며, 이들 펀드의 1년 수익률은 각각 다음과 같습니다.

3. 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류 C-I: 최고 13.66%, 최저 13.19%
4. 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류 A-e: 최고 15.98%, 최저 15.21%
5. 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류 A: 최고 17.73%, 최저 -41.31%
6. 미래에셋글로벌코어테크 EMP 증권자투자신탁2호(주식-재간접형) 종류 A-e: 최고 17.41%, 최저 17.31%

안내해 드린 수익률은 모두 누적 수익률이며, 기간은 1년입니다. 다른 기간(1·3·6·18개월, 2·3·5년) 수익률 기준을 원하시면 말씀해 주세요.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펌드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 9,781자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
7. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(fd_yr1_ern_r) AS "fd_yr1_ern_r_최고", MIN(fd_yr1_ern_r) AS "fd_yr1_ern_r_최저" FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r <> 0 GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 6행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_yr1_ern_r_최고 | fd_yr1_ern_r_최저
KR5153450780 | 미래에셋코어테크증권자투자신탁(주식) 종류A | 9 | 9 | 189.77 | 187.09
KR5153450910 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A | 4 | 4 | 188.63 | 186.98
KR5153451151 | 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류C-I | 3 | 3 | 13.66 | 13.19
KR5153451160 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류A-e | 5 | 5 | 15.98 | 15.21
KR5153490560 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류A | 12 | 12 | 17.73 | -41.31
KR5153490736 | 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류A-e | 4 | 4 | 17.41 | 17.31
```

</details>
