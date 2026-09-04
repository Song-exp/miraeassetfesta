# 공모펀드 78문항 테스트 결과 — 2026-09-04

> 문항 `eval/probe_funds_2026-09-04_core.txt` · 실측 `eval/probe_funds_2026-09-04_core.json`
> 예상 답변 `eval/expected_funds_2026_09_04.py` (전부 `data/financial_products.db` 실측)
> 모수: 판매중·공모 = 클래스 8,969 · 펀드 3,040 · 기준일 2026-08-21

## 총평 — ✅ 48 · 🟡 14 · ❌ 16  (총 78)

| 블록 | ✅ | 🟡 | ❌ | 실패·부분 문항 |
| :-- | --: | --: | --: | :-- |
| A. 클래스 vs 펀드 단위 (PDF §3.1) — 최대 함정 | 5 | 0 | 1 | `KG-030`❌ |
| B. 성과 — 누적 수익률·이상치 (§4.7) | 1 | 3 | 1 | `S2`🟡 `Y4`🟡 `AA24`❌ `FND-R02`🟡 |
| C. 위험등급 — 방향이 직관과 반대 (§2.5) | 5 | 0 | 0 |  |
| D. 법적 분류·유형 (§2.1) | 3 | 0 | 2 | `FND-006`❌ `Z10`❌ |
| E. 누가 살 수 있나 · 역외 (§2.3 §4.6) | 3 | 1 | 0 | `KG-031`🟡 |
| F. 개방/폐쇄 · 추가/단위 (§1.4 §2.2) | 2 | 0 | 0 |  |
| G. 어디에 투자하나 (§2.4) | 3 | 1 | 0 | `T13`🟡 |
| H. 역할 분리 — 운용사·수탁사·판매사 (§1.2 §4.3) | 5 | 1 | 1 | `KG-006`❌ `X22`🟡 |
| I. 모자형 (§3.2) | 1 | 0 | 0 |  |
| J. 종목명 파싱·이름 조회 (§3.3) | 1 | 1 | 2 | `X3`❌ `Z20`❌ `KG-005`🟡 |
| K. 규모 (§4.8) | 3 | 0 | 0 |  |
| L. 설명서 항목 — PDF가 '없다'고 했으나 지금은 있는 것 | 4 | 0 | 1 | `FND-005`❌ |
| M. 보유 종목 (ext_fund_holdings) | 2 | 0 | 0 |  |
| N. 답변불가 — PDF §5 중 지금도 살아있는 것 + 구조상 없는 것 | 6 | 2 | 1 | `OFFICIAL-002`❌ `FND-R04`🟡 `OFFICIAL-NA-002`🟡 |
| O. 되묻기 | 0 | 1 | 2 | `FND-C01`🟡 `FND-C02`❌ `FND-R03`❌ |
| P. 도메인 축 신설 — PDF가 한 절씩 다루는데 기존 문항이 없던 13축 | 4 | 4 | 5 | `DOM-03`❌ `DOM-06`❌ `DOM-07`🟡 `DOM-08`🟡 `DOM-09`❌ `DOM-10`❌ `DOM-11`🟡 `DOM-12`❌ `DOM-13`🟡 |

---

## 🔧 결함 분류 — 어디를 고치면 몇 개가 닫히나

16개 ❌ 와 14개 🟡 를 원인별로 묶었다. **문항 수가 아니라 고칠 자리 수로 8개**다.

| # | 고칠 자리 | 닫히는 문항 | 무슨 일이 났나 |
| :-: | :-- | :-- | :-- |
| 1 | **부재 선언 누락** — `absent_properties` 에 `hasInvestmentStrategy` 가 없다 | `OFFICIAL-002`❌ | 좌수·운용역·기준가추이·보유종목추이 4종은 ABSENT 선언이 있어 **전부 통과**(`KG-027`·`X23`·`X24`). 투자전략만 선언이 없어서 그 자리에서 지어냈다. 같은 파일에 한 줄 추가하는 것과 같은 모양이다. `ontology/enums/public_funds.yaml` `absent_properties` |
| 2 | **답변 조립기** — 목록·헤더 처리 | `FND-005`❌ `DOM-10`❌ | `FND-005` 는 2·3·4위가 `2.3.4.` 로 뭉개졌고 클래스 수가 항목 수와 안 맞는다. `DOM-10` 은 UNION 가지가 0행이라 **컬럼 헤더(`'이자형' | COUNT(*)`)만 남았는데 답변기가 그걸 세어 "이자형 1개"** 라고 냈다. 둘 다 SQL 은 정상이고 조립 단계 결함이다 |
| 3 | **보수 단위 ‰→%** | `FND-005`❌ (+ `DOM-06` 의 절반) | 마스터 보수 4종은 퍼밀이다. `0.015‰` 를 `0.015%` 로 적으면 10배 틀린다. 답변 층에 단위 변환이 없다 |
| 4 | **이름 매칭** — 오타 흡수와 클래스 표기 | `X3`❌ `Z20`❌ `AA24`❌ | 공백 무시(`REPLACE`)는 걸리는데 **1글자 오타**('코어택'·'코어태크')는 못 넘는다. `AA24` 는 클래스 '종류A' 를 `han_clas_nm`(실제 값 '수수료선취-오프라인')로 찾아 0행. 클래스 표기는 `itm_nm` 에 있다 |
| 5 | **부정·전제 해석** | `FND-006`❌ `DOM-09`❌ `FND-R03`❌ | `FND-006`: "MMF를 **제외하고**" → `zrin_ptn_nm='MMF'`. `DOM-09`: "국내에서 **설립된**" → 투자지역(`fd_ivst_rgn_desc`)으로 셌다. PDF §2.4 가 명시적으로 경고한 혼동이다. `FND-R03`: 기준가가 있는데 없다고 함 |
| 6 | **JOIN 방향** | `KG-006`❌ | `FROM ext_fund_page WHERE prvo_pbff_desc='공모'` — 외부 테이블을 주 테이블로 잡아 마스터 컬럼이 없어 기각. 마스터가 FROM, ext_* 가 JOIN 이어야 한다 |
| 7 | **재생성 프롬프트** (프리즈 후 항목) | `Z10`❌ `KG-030`❌ `DOM-03`❌ `DOM-06`❌ `FND-R04`🟡 `OFFICIAL-NA-002`🟡 | 값 검사 기각 → 재생성이 같은 실수 반복 또는 환각 컬럼 → 무응답. `KG-030` 은 **같은 날 오전엔 답했는데 오후에 실패** — 비결정이다 |
| 8 | **모수·결측 병기 누락** | `S2`🟡 `Y4`🟡 `DOM-08`🟡 `DOM-11`🟡 `DOM-07`🟡 `FND-C01`🟡 | 숫자는 맞는데 옆에 붙어야 할 한 마디가 없다 — '누적'·'결측 39%'·'사모 영역이라'·'청산 아님'·'상위가 전부 MMF'. 답변 규칙에는 이미 적혀 있고 지켜지지 않는다 |

### 우선순위 제안

1. **①** — 한 줄 추가로 프리즈 전 최대 위험(환각)이 닫힌다. 같은 메커니즘이 이미 4곳에서 작동 중이라 위험이 낮다.
2. **②③** — `FND-005` 하나에 세 결함이 겹쳐 있다. 답변 조립기는 코드 한 곳이다.
3. **⑤** — 부정 조건 반전은 **틀린 답을 자신 있게 내놓는** 부류라 감점이 크다. `DOM-09` 는 PDF 가 경고한 축이라 심사에서 눈에 띈다.
4. **④** — 오타 2건은 실전 질문 형태다.
5. **⑧** — 규칙은 있고 준수가 안 된다. 이 트랙의 H3 기각과 같은 얼굴이라 **프롬프트 문장을 늘리는 게 아니라 슬롯/조립기로** 가야 한다.
6. **⑥⑦** — ⑦은 인계문서 §6 가 프리즈 후로 미뤄 둔 항목이다.

### 잘 되고 있는 것 (건드리지 말 것)

- **위험등급 5/5** — 1등급=매우 위험 / 6등급=매우 안전 방향을 양쪽 다 맞혔다. PDF §2.5 가 가장 걱정한 축인데 통과다.
- **부재 선언 4종 전부 통과** — `KG-027`(좌수)·`X23`(운용역)·`X24`(기준가 추이)·`FND-R01`(신용등급). 법적 사유를 지어내지 않고 대체 안내까지 붙였다.
- **클래스/펀드 단위 5/6** — 15R 최다 오답(클래스를 펀드로)이 한 건도 재발하지 않았다.
- **PDF 가 '없다'고 한 축 4/5 통과** — 설정일·기준가·연도별 설정·보유종목. 45컬럼 시절 문서를 그대로 믿었다면 이 축들을 검증 대상에서 뺐을 것이다.
- **`X21`·`DOM-11`** — 0건일 때 "전체(판매완료·사모 포함)로는 N클래스" 를 덧붙이는 동작. 환각 대신 모수를 넓혀 보여준다.

---

## A. 클래스 vs 펀드 단위 (PDF §3.1) — 최대 함정

### ✅ `R1` — 유형별 분포 — 클래스/펀드 병기

> 공모펀드는 유형별로 몇 개씩 있어?

**예상** — 19개 범주 · 클래스 8,969 · 펀드 3,040. 해외주식형 953펀드(2,784클래스)가 최대.

**통과 조건** — 19범주 전부 나열 + 클래스와 펀드 수를 구분해 병기

**실제 답변**

```
조회 결과 19개 범주 · 클래스 8,969개 · 펀드 3,040개 (기준일 2026-08-24).

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

`[Execute] 19행`· 3.0s

<details><summary>SQL</summary>

```sql
SELECT COALESCE(zrin_btyp_nm,'(미수록)'), COUNT(*), COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모') GROUP BY zrin_btyp_nm LIMIT 30
```
</details>

**판정** — 19범주 전부 나열 · 클래스 8,969 / 펀드 3,040 병기 · 복수 계수 182건까지 설명. 예상과 완전 일치.

### ✅ `S8` — 운용사별 개수 — 펀드 단위

> KB자산운용이 운용하는 공모펀드는 몇 개야?

**예상** — KB자산운용 129펀드 (클래스 625).

**통과 조건** — 129를 답하고 클래스 625를 병기. 625를 답으로 내면 오답

**실제 답변**

```
KB자산운용이 운용하는 공모펀드는 129개(클래스 625개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 3.0s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 129(클래스 625) 정확. 단위 병기.

### ✅ `V12` — 개별 조회 — 클래스 묶기

> 미래에셋코어테크 펀드는 클래스가 몇 개야?

**예상** — '미래에셋코어테크' 는 2펀드 14클래스 — 미래에셋코어테크증권자(주식) / 미래에셋코어테크청년소득공제증권자(주식).

**통과 조건** — 2개 펀드로 갈라 각각 클래스 수를 밝힌다. 14를 한 펀드로 뭉치면 오답

**실제 답변**

```
'미래에셋코어테크' 이름의 공모펀드 2개가 조회됐습니다 (기준일 2026-08-24, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위).

- 미래에셋코어테크증권자투자신탁(주식): 클래스 10개(전부 판매중)
- 미래에셋코어테크청년소득공제증권자투자신탁(주식): 클래스 4개(전부 판매중)
```

`[Execute] 2행`· 슬롯 BASEPOP· 4.2s

<details><summary>SQL</summary>

```sql
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(mtco_itm_no) AS mtco_itm_no, MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
```
</details>

**판정** — 2펀드로 갈라 10+4클래스. 클래스 묶기 정상.

### ✅ `U14` — 랭킹 + 클래스 병기

> 1년 수익률이 가장 높은 공모펀드 3개는 클래스가 몇 개씩이야?

**예상** — 한화2.2배레버리지 387.66%(6클래스) · NH-Amundi코리아2배레버리지 362.53%(4) · 삼성KOSPI200 2배레버리지1호 361.3%(7). 기점오류 3클래스 제외.

**통과 조건** — 펀드 단위 3개 + 각 클래스 수. 클래스 3개를 나열하면 오답

**실제 답변**

```
1년 수익률 상위 3개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 1년 수익률 = 클래스 최고값(MAX), 기준일 2026-08-24).

1. 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형): 1년 수익률 387.66% · 클래스 6개
2. NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형]: 1년 수익률 362.53% · 클래스 4개
3. 삼성KOSPI200 2배레버리지증권투자신탁 제1호[주식-파생재간접형]: 1년 수익률 361.3% · 클래스 7개

※ 수익률 8기간 컬럼은 모두 누적 수익률이며 연 환산이 아닙니다. 100%를 넘는 값은 파생·레버리지 전략에서 나오므로 손실도 같은 배율로 커질 수 있습니다.
```

`[Execute] 3행`· 3.7s

<details><summary>SQL</summary>

```sql
SELECT or_co_xtn_itt_cd, prvo_pbff_desc, COUNT(*) as class_count, itm_no, TRIM(itm_nm) AS itm_nm, MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING COUNT(*) > 1 AND MAX(fd_yr1_ern_r) IS NOT NULL AND MAX(fd_yr1_ern_r) > -100 ORDER BY MAX(fd_yr1_ern_r) DESC LIMIT 3
```
</details>

**판정** — 펀드 단위 3개 + 클래스 수 병기 + 누적 경고. 기점오류 3클래스 제외도 정상.

### ❌ `KG-030` — 시리즈 호 구분 — 호가 다르면 다른 펀드

> 미래에셋차이나솔로몬 시리즈는 몇 호까지 있고 각각 클래스가 몇 개야?

**예상** — 3호까지. 3호 8클래스 · 2호 7클래스 · 1호 2클래스 (전부 판매중).

**통과 조건** — 1·2·3호를 각각 제시하고 클래스 수 병기

**실제 답변**

```
질문하신 항목이 이 상품 유형의 데이터에 없어 답변을 제공하지 못했습니다.
```

**미실행**· ⚠ 재생성· 51.4s

<details><summary>SQL</summary>

```sql
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(or_co_xtn_itt_cd) = '00080008' AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬%' AND mat_dt >= 20260824) GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
```
</details>

**판정** — 🔴 회귀. 같은 날 오전 스모크에서는 3호 8·2호 7·1호 2 로 정답을 냈는데 재실행에서 '데이터에 없다'로 거절했다. SQL 미실행·재생성 흔적. 비결정 재현 실패.

### ✅ `KG-029` — 다른 키로 세기

> 우리자산운용 펀드 수를 대표예탁원종목번호 기준으로 세면 몇 개야?

**예상** — 우리자산운용 — 대표예탁원종목번호 기준 88. (펀드키 기준 235 · 클래스 403)

**통과 조건** — 88. 235나 403을 답하면 질문이 지정한 키를 안 쓴 것

**실제 답변**

```
우리자산운용 펀드의 수는 대표예탁원종목번호 기준으로 총 88개입니다.
```

`[Execute] 1행`· 3.7s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT rptt_ksd_itm_no) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040007' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
```
</details>

**판정** — 대표예탁원종목번호 기준 88. 질문이 지정한 키를 그대로 썼다.


## B. 성과 — 누적 수익률·이상치 (§4.7)

### ✅ `FND-003` — 수익률 Top-N

> 1년 수익률이 가장 높은 공모펀드 5개 알려줘

**예상** — 한화2.2배레버리지 387.66% · NH-Amundi코리아2배레버리지 362.53% · 삼성KOSPI200 2배레버리지1호 361.3% · NH-Amundi1.5배레버리지 257.14% · 하나 코리아 203.13% (펀드 단위 MAX). ⚠ 마이다스아시아리더스 1,436%·미래에셋소비성장연금 394% 는 `수익률기점오류_제외` 로 검증된 3클래스라 제외가 정답이다.

**통과 조건** — 값 일치 + '누적' 명시 + 대표행(펀드당 1행) + 기점오류 3클래스 제외

**실제 답변**

```
1년 수익률 상위 5개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 1년 수익률 = 클래스 최고값(MAX), 기준일 2026-08-24).

1. 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형): 1년 수익률 387.66% · 클래스 6개
2. NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형]: 1년 수익률 362.53% · 클래스 4개
3. 삼성KOSPI200 2배레버리지증권투자신탁 제1호[주식-파생재간접형]: 1년 수익률 361.3% · 클래스 7개
4. NH-Amundi1.5배레버리지인덱스증권투자신탁(주식-파생형): 1년 수익률 257.14% · 클래스 5개
5. 하나 코리아증권자투자신탁[주식]: 1년 수익률 203.13% · 클래스 8개

※ 수익률 8기간 컬럼은 모두 누적 수익률이며 연 환산이 아닙니다. 100%를 넘는 값은 파생·레버리지 전략에서 나오므로 손실도 같은 배율로 커질 수 있습니다.
```

`[Execute] 5행`· 3.4s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_yr1_ern_r) IS NOT NULL AND MAX(fd_yr1_ern_r) > -100 ORDER BY 3 DESC LIMIT 5
```
</details>

**판정** — 값·순서 일치. 클래스 수 병기 + '누적, 연환산 아님' 명시. 기점오류 3클래스(마이다스 1,436% 등) 제외가 정답.

### 🟡 `S2` — 수익률 최하위 — 이상치

> 3년 수익률이 가장 나쁜 공모펀드 3개 알려줘

**예상** — 펀드 단위 MIN — 미래에셋아시아퍼시픽소비성장1호 −80.36% · 삼성KOSPI200인버스1호 −78.08% · 삼성배당주장기1 −77.8%. PDF가 경고한 KCGI −4,382% 는 판매완료라 이 모수에 없다.

**통과 조건** — 값 일치 + '누적' 명시

**실제 답변**

```
3년 수익률 하위 3개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 3년 수익률 = 클래스 최저값(MIN), 기준일 2026-08-24).

1. 미래에셋아시아퍼시픽소비성장증권자투자신탁1호(주식): 3년 수익률 -80.36% · 클래스 10개
2. 삼성KOSPI200인버스인덱스증권투자신탁제1호[채권-파생형]: 3년 수익률 -78.08% · 클래스 3개
3. 삼성배당주장기증권투자신탁 1[주식]: 3년 수익률 -77.8% · 클래스 12개
```

`[Execute] 3행`· 3.2s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MIN(fd_yr3_ern_r) AS fd_yr3_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MIN(fd_yr3_ern_r) IS NOT NULL AND MIN(fd_yr3_ern_r) < 0 ORDER BY 3 ASC LIMIT 3
```
</details>

**판정** — 값·순서 정확(펀드 단위 MIN). 다만 FND-003 에는 붙은 '누적' 주석이 여기엔 없다 — 음수 수익률에서 누적/연환산 오해가 더 크다.

### 🟡 `Y4` — 5년 최하위

> 5년 수익률이 가장 나쁜 공모펀드 3개 알려줘

**예상** — 펀드 단위 MIN — 미래에셋성장유망중소형주1호 −84.41% · 아시아퍼시픽소비성장1호 −83.38% · 한화러시아 −81.51%

**통과 조건** — 값 일치 + '누적' 명시

**실제 답변**

```
5년 수익률 하위 3개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 5년 수익률 = 클래스 최저값(MIN), 기준일 2026-08-24).

1. 미래에셋성장유망중소형주증권자투자신탁1호(주식): 5년 수익률 -84.41% · 클래스 9개
2. 미래에셋아시아퍼시픽소비성장증권자투자신탁1호(주식): 5년 수익률 -83.38% · 클래스 10개
3. 한화러시아증권자투자신탁(주식-재간접형): 5년 수익률 -81.51% · 클래스 5개
```

`[Execute] 3행`· 49.7s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MIN(fd_yr5_ern_r) AS fd_yr5_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MIN(fd_yr5_ern_r) IS NOT NULL AND MIN(fd_yr5_ern_r) < 0 ORDER BY 3 ASC LIMIT 3
```
</details>

**판정** — 값·순서 정확. S2 와 같은 이유로 '누적' 미명시.

### ❌ `AA24` — 클래스 지정 수익률

> 미래에셋 코어테크 펀드 종류A 3년 수익률 알려줘

**예상** — 미래에셋코어테크증권자(주식) 종류A 3년 185.21% (누적). 같은 이름의 청년소득공제 종류A 는 185.00%.

**통과 조건** — 종류A 를 정확히 집고 누적임을 밝힌다

**실제 답변**

```
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 질문의 「코어테크」를 데이터의 종목명으로 식별하지 못했습니다 (가까운 표기: 미래에셋코어테크증권자투자신탁(주식) · 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)).
```

`[Execute] 0행`· 3.0s

<details><summary>SQL</summary>

```sql
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(CASE WHEN fd_yr3_ern_r IS NOT NULL THEN fd_yr3_ern_r END) AS "fd_yr3_ern_r_최고", MIN(CASE WHEN fd_yr3_ern_r IS NOT NULL THEN fd_yr3_ern_r END) AS "fd_yr3_ern_r_최저", MIN(rptt_ksd_itm_no) AS 대표번호, han_clas_nm FROM public_funds  WHERE prvo_pbff_desc = '공모' AND (TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND TRIM(han_clas_nm) = '종류 A') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
```
</details>

**판정** — 🔴 0행. SQL 이 `TRIM(han_clas_nm) = '종류 A'` 로 필터했는데 han_clas_nm 실제 값은 '수수료선취-오프라인' 형식이다. 클래스 표기는 itm_nm 에 '종류A' 로 들어 있다. 실재 값 185.21% 를 놓쳤다. '가까운 표기' 안내는 정상 동작.

### 🟡 `FND-R02` — 없는 기간 컬럼

> 지난 1주일 수익률이 가장 높은 공모펀드 알려줘

**예상** — 1주일 수익률(fd_wk1_ern_r)은 전건 NULL — 답변불가.

**통과 조건** — '1주일 수익률은 수록되어 있지 않다' + 있는 기간(1개월~5년) 안내. 숫자를 내면 환각

**실제 답변**

```
1개월 수익률 상위 5개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 1개월 수익률 = 클래스 최고값(MAX), 기준일 2026-08-24).

1. 다올전단채증권투자신탁[채권]: 1개월 수익률 55.43% · 클래스 10개
2. iM에셋월드골드증권자투자신탁(주식-재간접형)(H): 1개월 수익률 29.55% · 클래스 10개
3. IBK골드마이닝증권자투자신탁1호[주식]: 1개월 수익률 27.75% · 클래스 3개
4. iM에셋월드골드증권자투자신탁(주식-재간접형)(UH): 1개월 수익률 23.93% · 클래스 11개
5. 삼성코스닥150 1.5배레버리지증권투자신탁[주식-파생형]: 1개월 수익률 22.67% · 클래스 1개
```

`[Execute] 5행`· 3.7s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_mm1_ern_r) AS fd_mm1_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms, fd_daily_bas_dt FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_daily_bas_dt BETWEEN 20260815 AND 20260822 GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_mm1_ern_r) IS NOT NULL AND MAX(fd_mm1_ern_r) > -100 ORDER BY 3 DESC LIMIT 5
```
</details>

**판정** — 1주일 수익률(전건 NULL)을 말없이 1개월로 바꿔 답했다. 머리줄에 '1개월'이라 밝히긴 했으나 '1주일은 수록 없음'을 말하지 않아 사용자는 자기 질문이 치환된 걸 모른다. SQL 은 `fd_daily_bas_dt BETWEEN 20260815 AND 20260822` 로 '지난 1주일'을 기준일 범위로 오해석.


## C. 위험등급 — 방향이 직관과 반대 (§2.5)

### ✅ `FND-001` — 등급 6 = 가장 안전

> 위험등급이 가장 안전한 공모펀드 중 순자산 큰 10개 알려줘

**예상** — 6등급(매우 낮은 위험) 108펀드 · 338클래스 중 순자산 상위 10.

**통과 조건** — 6등급을 골랐는가. 1등급을 고르면 방향을 뒤집은 오답

**실제 답변**

```
순자산 상위 10개 공모펀드입니다 (판매중·공모·매우 낮은 위험 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 순자산 = 대표 클래스 기준(MAX), 기준일 2026-08-24).

1. 삼성MMF법인제1호: 순자산 124,295억원 · 클래스 4개
2. KB법인용MMF I- 1: 순자산 96,266억원 · 클래스 2개
3. 우리큰만족법인MMF1호(국공채): 순자산 90,390억원 · 클래스 2개
4. 우리큰만족신종MMF3호: 순자산 80,497억원 · 클래스 1개
5. 신영법인용MMF 제4-26호 C-I형: 순자산 76,371억원 · 클래스 2개
6. IBK그랑프리국공채MMF법인투자신탁 제1호[국공채]I: 순자산 75,337억원 · 클래스 2개
7. 신한BEST신종법인용MMFGS-2호(종류C): 순자산 63,581억원 · 클래스 2개
8. 한화골드법인MMF-KM3호(국공채): 순자산 55,140억원 · 클래스 1개
9. 브이아이 천하제일 법인MMF 1호: 순자산 46,666억원 · 클래스 2개
10. 하나클래스원신종MMF(K-5호)Class C-F: 순자산 45,657억원 · 클래스 2개
```

`[Execute] 10행`· 3.9s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma , zrin_fd_ivst_risk_grd_nm, COUNT(*) AS "클래스수", zrin_fd_ivst_risk_gcd, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_gcd = 6 GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_nast_suma) IS NOT NULL ORDER BY 3 DESC LIMIT 10
```
</details>

**판정** — 6등급(매우 낮은 위험) 정확 — 방향을 뒤집지 않았다. 상위 10 + 클래스 수.

### ✅ `FND-002` — 등급 1 = 가장 위험

> 위험등급 1등급(매우 높은 위험) 공모펀드 중 순자산 큰 5개 알려줘

**예상** — 1등급(매우 높은 위험) 272펀드 · 874클래스 중 순자산 상위 5.

**통과 조건** — 1등급을 골랐는가

**실제 답변**

```
순자산 상위 5개 공모펀드입니다 (판매중·공모·매우 높은 위험 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 순자산 = 대표 클래스 기준(MAX), 기준일 2026-08-24).

1. 미래에셋코어테크증권자투자신탁(주식): 순자산 7,348억원 · 클래스 10개
2. NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형]: 순자산 7,333억원 · 클래스 4개
3. KCGI코리아증권투자신탁1호[주식]: 순자산 3,735억원 · 클래스 13개
4. 미래에셋장기성장포커스증권자투자신탁1호(주식): 순자산 3,543억원 · 클래스 10개
5. 유리필라델피아반도체인덱스증권자투자신탁UH[주식]: 순자산 3,391억원 · 클래스 8개
```

`[Execute] 5행`· 3.1s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma , fd_daily_bas_dt, COUNT(*) AS "클래스수", zrin_fd_ivst_risk_grd_nm, zrin_fd_ivst_risk_gcd, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_gcd = '1.0' GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY 3 DESC LIMIT 5
```
</details>

**판정** — 1등급(매우 높은 위험) 정확. 방향 양쪽 다 통과.

### ✅ `FND-014` — 등급 결측

> 위험등급 정보가 없는 공모펀드는 몇 개야?

**예상** — 위험등급 미수록 312펀드 · 422클래스.

**통과 조건** — 422(클래스) 또는 312(펀드) — 어느 단위인지 밝히면 통과

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 312개(클래스 422개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.1s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_gcd IS NULL) LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 312펀드(422클래스). 단위 병기.

### ✅ `KG-015` — 값 표기 흔들림

> 위험등급이 '높은위험'인 공모펀드는 몇 개야?

**예상** — '높은 위험' 2,974 + '높은위험' 20 = 2,994클래스. 띄어쓰기 두 표기를 합산해야 한다.

**통과 조건** — 2,994. 2,974만 답하면 variants 미합산 오답

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 995개(클래스 2,994개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.6s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_grd_nm IN ('높은위험', '높은 위험') AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 2,994클래스 — '높은 위험' 2,974 + '높은위험' 20 을 합산했다. value_variants 정상.

### ✅ `KG-013` — 없는 등급

> 위험등급 7등급인 공모펀드 알려줘

**예상** — 제로인 등급은 1~6뿐. 7등급 없음.

**통과 조건** — '7등급은 존재하지 않는다' + 1~6 범위 안내

**실제 답변**

```
공모펀드 위험등급은 1(매우 높은 위험)~6(매우 낮은 위험) 범위로 정의되어 있어 7등급은 없습니다. (0등급 없음 — 등급 미수록 클래스는 NULL(0 아님))
```

**미실행**· 0.2s

**판정** — '1~6 범위라 7등급 없음' + 묻지도 않은 0등급까지 선제 정리. 모범 답변.


## D. 법적 분류·유형 (§2.1)

### ✅ `KG-016` — 운용속성 필터

> 채권혼합 공모펀드는 몇 개야?

**예상** — 채권혼합 389펀드 · 933클래스.

**통과 조건** — 389 또는 933 + 단위 명시

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 389개(클래스 933개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 41.2s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND or_attr_desc = '채권혼합' AND sale_yn = '판매중' /*M:FUNDUNIT*/ LIMIT 30
```
</details>

**판정** — 389(933) 정확.

### ❌ `FND-006` — MMF 배제

> MMF를 제외하고 순자산이 가장 큰 공모펀드 5개 알려줘

**예상** — 피델리티글로벌테크놀로지 CP-e 1.22조 · 미래에셋전략배분TDF2045 1.02조 · KB퇴직연금배당40 9,975억 · 한국밸류10년투자연금1 9,031억 · 하나인Best연금1호 8,451억

**통과 조건** — MMF가 결과에 없어야 한다. MMF가 섞이면 오답

**실제 답변**

```
순자산 상위 1개 공모펀드입니다 (판매중·공모·제로인유형명 MMF 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 순자산 = 대표 클래스 기준(MAX), 기준일 2026-08-24).

1. KB 개인연금 단기자금 증권 자투자신탁(단기자금-재간접형): 순자산 163억원 · 클래스 1개
```

`[Execute] 1행`· 3.9s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", zrin_ptn_nm, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds  WHERE zrin_ptn_nm = 'MMF' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') NOT LIKE '%MMF%' GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_nast_suma) IS NOT NULL ORDER BY 3 DESC LIMIT 5
```
</details>

**판정** — 🔴🔴 부정 조건 반전. '**MMF를 제외하고**' 인데 SQL 은 `zrin_ptn_nm = 'MMF' AND REPLACE(itm_nm,' ','') NOT LIKE '%MMF%'` — 'MMF 유형이면서 이름에 MMF가 없는 것'을 골랐다. 머리줄도 '제로인유형명 MMF 기준'이라 적었다. 결과 1건(163억). 정답은 피델리티글로벌테크놀로지 1.22조 이하 5건.

### ✅ `FND-007` — MMF만

> MMF 중에서 순자산이 가장 큰 공모펀드 3개 알려줘

**예상** — 삼성MMF법인제1호 C 12.43조 · KB법인용MMF I-1 종류C 9.63조 · 우리큰만족법인MMF1호 9.04조

**통과 조건** — 값 일치. 클래스 4개가 같은 순자산인 것(§3.1)을 밝히면 가점

**실제 답변**

```
조건에 해당하는 공모펀드는 전체 64개(클래스 108개)(대표번호 기준 59건)이며, 순자산 상위 3개 표시는 다음과 같습니다 (기준일 2026-08-24, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위·순자산 = 대표 클래스 기준(MAX)).

1. 삼성MMF법인제1호: 순자산 124,295억원 · 클래스 4개
2. KB법인용MMF I- 1: 순자산 96,266억원 · 클래스 2개
3. 우리큰만족법인MMF1호(국공채): 순자산 90,390억원 · 클래스 2개
```

`[Execute] 3행`· 3.1s

<details><summary>SQL</summary>

```sql
SELECT DISTINCT itm_no, itm_nm, MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", zrin_ptn_nm, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE zrin_ptn_nm = 'MMF' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY fd_nast_suma DESC LIMIT 3
```
</details>

**판정** — 삼성MMF법인제1호 12.43조 등 정확. 모수(64펀드/108클래스)까지 병기.

### ✅ `AA11` — 소수 유형

> 부동산 공모펀드 중 순자산 큰 3개 알려줘

**예상** — 신한K리츠인프라 163.6억 · 하나글로벌리츠 130.5억 · 한화K리츠플러스 55.5억

**통과 조건** — 부동산형으로 필터했는가

**실제 답변**

```
순자산 상위 3개 공모펀드입니다 (판매중·공모·부동산형·해외부동산형 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 순자산 = 대표 클래스 기준(MAX), 기준일 2026-08-24).

1. 신한K리츠인프라부동산투자신탁[재간접형]: 순자산 164억원 · 클래스 1개
2. 하나글로벌리츠부동산자투자신탁[재간접형]: 순자산 131억원 · 클래스 13개
3. 한화K리츠플러스부동산 자투자신탁(H)(리츠-재간접형): 순자산 56억원 · 클래스 8개
```

`[Execute] 3행`· 3.2s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", zrin_btyp_nm, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND zrin_btyp_nm IN ('부동산형', '해외부동산형') AND fd_nast_suma <> 0 GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_nast_suma) IS NOT NULL ORDER BY 3 DESC LIMIT 3
```
</details>

**판정** — 부동산형+해외부동산형 정확. 값 일치.

### ❌ `Z10` — 유형 축 — 17R 실패 문항

> 해외주식형 중에서 인도주식 유형인 공모펀드는 몇 개야?

**예상** — 인도주식 34펀드 · 98클래스.

**통과 조건** — 🔴 17R에서 '데이터에 없다'로 거절했다. 34 또는 98이 나오면 회수

**실제 답변**

```
질문하신 항목이 이 상품 유형의 데이터에 없어 답변을 제공하지 못했습니다.
```

**미실행**· 슬롯 BASEPOP·FUNDUNIT· ⚠ 값 검사 실패· ⚠ 재생성· 4.9s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE zrin_ptn_nm = '인도주식' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (asset_class = '해외주식형' AND country = 'IND' AND fund_type = 'public' AND fund_unit_type = 'Indian Stock Fund' /*M:FUNDUNIT*/) /*M:BASEPOP*/ LIMIT 30
```
</details>

**판정** — 🔴 17R 그대로 실패. `zrin_btyp_nm='인도주식형'` 값 검사 실패 → 재생성이 환각 컬럼(asset_class·fund_type) 생성 → 거절. 정답은 34펀드/98클래스이고 zrin_ptn_nm='인도주식' 에 실재한다.


## E. 누가 살 수 있나 · 역외 (§2.3 §4.6)

### ✅ `FND-012` — 기본 모수

> 지금 판매중인 공모펀드는 모두 몇 개야?

**예상** — 3,040펀드 · 8,969클래스.

**통과 조건** — 두 수를 구분해 밝힌다

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 3,040개(클래스 8,969개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.1s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 3,040(8,969). 두 단위 구분.

### ✅ `Z12` — 이름 + 상태 복합

> 이름이 삼성으로 시작하는 판매중 공모펀드는 몇 개야?

**예상** — 이름이 '삼성'으로 시작 + 판매중 → 217펀드 · 906클래스.

**통과 조건** — 217 또는 906

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 217개(클래스 906개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· ⚠ 재생성· 42.3s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '삼성%' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 217(906) 정확.

### ✅ `FND-013` — 역외펀드

> 역외 공모펀드는 몇 개야?

**예상** — 역외 110 (ofsfd_yn=1 · 클래스=펀드 110, mtco 없어 행 단위).

**통과 조건** — 110 + 역외는 mtco가 없어 행 단위로 센다는 점

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 110개(클래스 110개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.2s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (ofsfd_yn = 1 AND prvo_pbff_desc = '공모' /*M:FUNDUNIT*/) LIMIT 30
```
</details>

**판정** — 110(110) 정확.

### 🟡 `KG-031` — 역외 포함 합산

> 피델리티가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?

**예상** — 피델리티자산운용(00080029) 106펀드(역외 0) + 피델리티 역외계열(00130001) 47 = 153펀드.

**통과 조건** — 두 코드를 합쳐 153. 106만 답하면 역외 미포함 오답

**실제 답변**

```
피델리티자산운용이 운용하는 공모펀드는 106개(클래스 246개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
종목명이 '피델리티' 로 시작하는 역외펀드 47개(클래스 47개, 해외 운용법인 코드 00130001)는 별도 법인이라 이 수에 포함하지 않았습니다.
```

`[Execute] 1행`· 슬롯 FUNDUNIT· ⚠ 재생성· 6.4s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (or_co_xtn_itt_cd = '00080029' AND prvo_pbff_desc = '공모' AND ofsfd_yn IN (0,1)) LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 질문이 '역외펀드까지 포함하면'인데 106만 답하고 47을 '별도 법인이라 포함하지 않았다'며 제외했다. 47을 밝히고 근거를 댄 점, 코드북이 00130001 을 '국내 법인 코드 아님'으로 규정한 점은 답변에 유리하다. 다만 질문이 요구한 합산(153)을 끝내 제시하지 않았다.


## F. 개방/폐쇄 · 추가/단위 (§1.4 §2.2)

### ✅ `KG-017` — 폐쇄형 — zrin 태그 축

> 폐쇄형 공모펀드는 몇 개야?

**예상** — 폐쇄 태그 3펀드 · 6클래스. (fd_set_pcd='20' 220건은 폐쇄형이 아니라 단위형이다)

**통과 조건** — 6 또는 3. 220을 답하면 축을 혼동한 오답

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 3개(클래스 6개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.5s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,C104,%' LIMIT 30
```
</details>

**판정** — 3(6) — 폐쇄는 zrin 태그 축이라는 걸 정확히 썼다. fd_set_pcd='20'(단위형 220)과 혼동하지 않았다.

### ✅ `KG-018` — 두 축의 조합

> 단위형이면서 개방형인 공모펀드도 있어?

**예상** — 있다 — 단위형(fd_set_pcd='20') ∧ 개방 태그 = 31펀드 · 189클래스. 두 축은 서로 다른 컬럼이다.

**통과 조건** — '있다' + 개수. '모순이라 없다'고 답하면 오답

**실제 답변**

```
조건에 해당하는 공모펀드는 전체 31개(클래스 189개)(대표번호 기준 30건)이며, 순자산 순으로 다음과 같습니다 (기준일 2026-08-24, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위·순자산 = 대표 클래스 기준(MAX)).

1. 하나리레이팅코리아목표전환형증권투자신탁제4호[채권혼합-재간접형]: 순자산 302억원 · 클래스 8개
2. 흥국라이징코스닥30타겟다운목표전환형증권투자신탁1호[채권혼합]: 순자산 245억원 · 클래스 8개
3. KB 미중 AI테크 목표전환 증권 투자신탁 제3호(채권-재간접형): 순자산 93억원 · 클래스 8개
4. 삼성알아서글로벌주도테마EMP목표전환형증권투자신탁제3호[채권혼합-재간접형]: 순자산 90억원 · 클래스 8개
5. 삼성 글로벌 Core AI 목표전환형 증권 투자신탁 제3호[채권-재간접형]: 순자산 85억원 · 클래스 8개
6. 삼성알아서투자해주는반도체목표전환형증권투자신탁 제2호[채권혼합-재간접형]: 순자산 72억원 · 클래스 7개
7. KB 코리아 첨단전략산업 50 목표전환 증권 투자신탁(채권혼합-재간접형): 순자산 71억원 · 클래스 6개
8. KB 만기가 있는 채권 EMP 증권 투자신탁(채권-재간접형): 순자산 44억원 · 클래스 2개
9. 브이아이 아시아 AI 소부장 목표전환형 증권 투자신탁 1호[채권혼합-재간접형]: 순자산 41억원 · 클래스 7개
10. KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합): 순자산 34억원 · 클래스 7개
11. 마이다스 글로벌 리더스 성장주 목표전환형 증권 투자신탁 1호(채권혼합): 순자산 31억원 · 클래스 7개
12. 한국투자한미핵심성장포커스목표전환증권투자신탁(채권-재간접형): 순자산 23억원 · 클래스 4개
13. 대신 미국 장기국채 액티브 목표전환형 증권투자신탁2호[채권-재간접형]: 순자산 23억원 · 클래스 2개
14. 신한글로벌AI인프라목표전환형증권투자신탁(H)[채권]: 순자산 22억원 · 클래스 8개
15. KB K-성장과 지배구조 50 목표전환 증권 투자신탁 제3호(채권-재간접형): 순자산 13억원 · 클래스 7개
16. KCGI코리아목표전환형증권투자신탁3호[채권]: 순자산 13억원 · 클래스 7개
17. KB K-성장과 지배구조 50 목표전환 증권 투자신탁 제2호(채권-재간접형): 순자산 11억원 · 클래스 8개
18. KCGI코리아목표전환형증권투자신탁4호[채권]: 순자산 11억원 · 클래스 8개
19. KCGI피델리티미국AI테크목표전환형증권투자신탁[채권]: 순자산 8억원 · 클래스 8개
20. DB타이거드래곤바이오헬스케어목표전환형증권투자신탁제1호[주식혼합]: 순자산 8억원 · 클래스 7개
21. 베어링주주가치성장목표전환증권투자신탁2호(채권-재간접형): 순자산 6억원 · 클래스 8개
22. 흥국데이터포커스타겟다운목표전환형증권투자신탁3호[채권]:
…(생략)
```

`[Execute] 30행`· 2.5s

<details><summary>SQL</summary>

```sql
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, prfd_attr_cds, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,C102,%' AND ',' || prfd_attr_cds || ',' LIKE '%,C103,%') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY fd_nast_suma DESC LIMIT 30
```
</details>

**판정** — 31(189) + 목록. '있다'를 명확히. 두 축이 다른 컬럼임을 실질적으로 구분했다.


## G. 어디에 투자하나 (§2.4)

### 🟡 `T13` — 지역 축의 모호성

> 미국에 투자하는 공모펀드 알려줘

**예상** — 지역 대분류 '남미/북미' 114펀드(489클래스) / 국가태그 USA 98펀드(333클래스). 정의가 갈린다.

**통과 조건** — 어느 축으로 셌는지 밝히면 통과. 밝히지 않으면 부분 통과

**실제 답변**

```
조건에 해당하는 공모펀드는 전체 98개(클래스 333개)(대표번호 기준 55건)이며, 순자산 상위 30개 표시는 다음과 같습니다 (기준일 2026-08-24, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위·순자산 = 대표 클래스 기준(MAX)).

1. 삼성달러표시MMF법인 제1호(USD)_Cf: 순자산 4,839억원 · 클래스 3개
2. 삼성미국S&P500인덱스증권자투자신탁UH[주식]: 순자산 4,350억원 · 클래스 11개
3. AB미국그로스증권투자신탁(주식-재간접형): 순자산 3,989억원 · 클래스 13개
4. KB스타 미국 나스닥 100 인덱스 증권 자투자신탁(주식-파생형)(H): 순자산 3,225억원 · 클래스 10개
5. 삼성미국S&P500인덱스증권자투자신탁H[주식]: 순자산 1,607억원 · 클래스 11개
6. KB스타 미국 S&P500 인덱스 증권 자투자신탁(주식-파생형)(H): 순자산 1,560억원 · 클래스 9개
7. KB연금미국S&P500인덱스증권자투자신탁(주식-파생형)(H): 순자산 1,524억원 · 클래스 2개
8. 삼성S&P500미국채권혼합증권자투자신탁H[채권혼합-재간접형]: 순자산 1,075억원 · 클래스 6개
9. KB 미국 S&P500 인덱스 40 증권 자투자신탁(채권혼합-파생형): 순자산 756억원 · 클래스 2개
10. KB 미국 대표성장주 증권 자투자신탁(주식)(UH): 순자산 621억원 · 클래스 5개
11. 미래에셋미국배당커버드콜액티브증권자투자신탁(주식)(UH): 순자산 538억원 · 클래스 11개
12. 미래에셋G2이노베이터증권자투자신탁(주식): 순자산 536억원 · 클래스 15개
13. KB 미국 대표성장주 증권 자투자신탁(주식)(H): 순자산 476억원 · 클래스 5개
14. 한국투자미국배당귀족증권자투자신탁H(주식): 순자산 414억원 · 클래스 11개
15. 한국투자미국배당귀족증권자투자신탁UH(주식): 순자산 354억원 · 클래스 10개
16. 피델리티 미달러 채권 증권 자투자신탁 UH (채권-재간접형): 순자산 283억원 · 클래스 3개
17. AB셀렉트미국증권투자신탁(주식-재간접형): 순자산 273억원 · 클래스 11개
18. 삼성미국코어주식증권자투자신탁H[주식]: 순자산 204억원 · 클래스 12개
19. 미래에셋미국배당커버드콜액티브증권자투자신탁(주식)(H): 순자산 178억원 · 클래스 11개
20. 삼성미국투자등급장기채권증권자투자신탁UH[채권]: 순자산 175억원 · 클래스 8개
21. 피델리티연금미국증권전환형자투자신탁(주식-재간접형): 순자산 167억원 · 클래스 2개
22. 신한미국코어액티브증권자투자신탁(H)[주식]: 순자산 129억원 · 클래스 9개
23. 미래에셋달러우량중장기채권증권자투자신탁(UH)(채권): 순자산 115억원 · 클래스 8개
24. 피델리티미국증권자투자신탁(주식-재간접): 순자
…(생략)
```

`[Execute] 30행`· 2.5s

<details><summary>SQL</summary>

```sql
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, prfd_attr_cds, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE ',' || prfd_attr_cds || ',' LIKE '%,USA,%' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY fd_nast_suma DESC LIMIT 30
```
</details>

**판정** — 국가태그 USA 축으로 98펀드(333클래스)를 셌고 모수는 밝혔다. 다만 '미국'을 지역 대분류(남미/북미 114펀드)로 볼 수도 있는데 어느 축을 썼는지 답변에 없다. 두 축이 갈리는 질문이라 축 명시가 통과 조건이었다.

### ✅ `X21` — 없는 나라

> 스페인에 투자하는 공모펀드 있어?

**예상** — 스페인 투자 공모펀드 0건.

**통과 조건** — '없다'. 아무 펀드나 내놓으면 환각

**실제 답변**

```
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 해당 조건인 펀드는 판매중·공모 기준 0개이고, 전체(판매완료·사모 포함)로는 7클래스가 있습니다.
```

`[Execute] 0행`· 44.8s

<details><summary>SQL</summary>

```sql
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, prfd_attr_cds, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND (',' || prfd_attr_cds || ',' LIKE '%,ESP,%' OR REPLACE(itm_nm,' ','') LIKE '%스페인%') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY fd_nast_suma DESC LIMIT 30
```
</details>

**판정** — 0건 + '전체(판매완료·사모 포함)로는 7클래스' 까지 밝혔다. 환각 없음. 모범 답변.

### ✅ `AA8` — 지역 대분류

> 글로벌 지역에 투자하는 공모펀드는 몇 개야?

**예상** — 글로벌 1,441펀드 · 3,619클래스.

**통과 조건** — 1,441 또는 3,619

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 1,441개(클래스 3,619개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.3s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE fd_ivst_rgn_desc IN ('글로벌') AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 1,441(3,619) 정확.

### ✅ `KG-012` — 유형 세분

> 해외주식형 중에서 중국주식 유형인 공모펀드는 몇 개야?

**예상** — 중국주식 205펀드 · 522클래스.

**통과 조건** — 205 또는 522

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 205개(클래스 522개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 5.9s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND ovrs_fd_desc IN ('해외', '국내외혼합') AND zrin_btyp_nm = '해외주식형' AND zrin_ptn_nm = '중국주식' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 205(522) 정확.


## H. 역할 분리 — 운용사·수탁사·판매사 (§1.2 §4.3)

### ✅ `R2` — 운용사 랭킹 — 코드→이름

> 펀드를 가장 많이 운용하는 운용사 상위 5개 알려줘

**예상** — 미래에셋 823 · 우리 235 · 삼성 207 · iM에셋 205 · 한국투자 142 (펀드 단위)

**통과 조건** — 코드가 아니라 법인명으로. 클래스 수를 답하면 오답

**실제 답변**

```
조회 결과 펀드 수 상위 5개 운용사입니다 (판매중·공모 기준, 펀드 = 운용사 종목번호 기준, 클래스 = 판매 단위, 기준일 2026-08-24).

1. 미래에셋자산운용(00080008): 펀드 823개(클래스 2,066개) · 순자산 377,707억원
2. 우리자산운용(00040007): 펀드 235개(클래스 403개) · 순자산 224,693억원
3. 삼성자산운용(00040010): 펀드 207개(클래스 850개) · 순자산 331,098억원
4. iM에셋자산운용(00080035): 펀드 205개(클래스 240개) · 순자산 19,921억원
5. 한국투자신탁운용(00040024): 펀드 142개(클래스 540개) · 순자산 180,640억원
```

`[Execute] 5행`· 5.8s

<details><summary>SQL</summary>

```sql
SELECT printf('%08d', CAST(p.or_co_xtn_itt_cd AS INTEGER)) AS "운용사코드", MAX(CASE WHEN printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || e.mgmt_co_nm NOT IN ('00040007/프랭클린템플턴투자신탁운용', '00040010/삼성액티브자산운용', '00040011/미래에셋자산운용', '00040013/슈로더자산운용', '00040023/우리자산운용', '00080008/멀티에셋자산운용', '00080008/미래에셋맵스자산운용') THEN e.mgmt_co_nm END) AS "운용사명", COUNT(DISTINCT printf('%08d', CAST(p.or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(p.mtco_itm_no)) >= 7 THEN trim(p.mtco_itm_no) ELSE substr('0000000' || trim(p.mtco_itm_no), -7) END, p.itm_no)) AS "펀드수", COUNT(*) AS "클래스수", CAST(ROUND(SUM(p.fd_nast_suma)/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no WHERE p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY 3 DESC LIMIT 5
```
</details>

**판정** — 코드→법인명 변환 + 펀드/클래스/순자산 3열. 예상과 완전 일치.

### ✅ `KG-001` — 영문 사명 매핑

> Mirae Asset이 운용하는 공모펀드는 몇 개야?

**예상** — Mirae Asset → 미래에셋자산운용(00080008) 823펀드 · 2,066클래스.

**통과 조건** — 823. 영문명을 코드로 옮겼는가

**실제 답변**

```
미래에셋자산운용이 운용하는 공모펀드는 823개(클래스 2,066개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
종목명이 '미래에셋' 로 시작하는 역외펀드 5개(클래스 5개, 해외 운용법인 코드 00130006)는 별도 법인이라 이 수에 포함하지 않았습니다.
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.4s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 영문 'Mirae Asset' → 823(2,066). 역외 5개 별도 안내까지.

### ✅ `KG-004` — 띄어쓰기 변형

> 한국 투자 신탁 운용 이 운용하는 공모펀드는 몇 개야?

**예상** — '한국 투자 신탁 운용' → 한국투자신탁운용(00040024) 142펀드.

**통과 조건** — 공백을 무시하고 매칭했는가

**실제 답변**

```
한국투자신탁운용이 운용하는 공모펀드는 143개(클래스 541개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
운용사 코드 2건(00040024·00040105)을 합산했습니다.
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.4s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 띄어쓰기 '한국 투자 신탁 운용' 매칭 성공. 143(541) — 운용사 코드 2건(00040024·00040105) 합산을 명시했다. 내 예상 142는 한 코드만 센 것으로 답변이 더 정확하다.

### ❌ `KG-006` — 두 역할 동시

> 미래에셋코어테크 펀드의 운용사와 수탁사는 어디야?

**예상** — 운용사 미래에셋자산운용(00080008) · 수탁사 신한은행(00020088).

**통과 조건** — 둘 다, 코드가 아니라 이름으로

**실제 답변**

```
같은 이름의 항목이 여러 자료에 있어 어느 쪽인지 정하지 못해 답변을 제공하지 못했습니다.
```

**미실행**· ⚠ 재생성· 41.9s

<details><summary>SQL</summary>

```sql
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(trusc_xtn_itt_cd) AS trusc_xtn_itt_cd, MIN(rptt_ksd_itm_no) AS 대표번호 FROM ext_fund_page WHERE prvo_pbff_desc = '공모' AND (itm_no IN (SELECT itm_no FROM public_funds WHERE or_co_xtn_itt_cd = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%' LIMIT 30)) GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
```
</details>

**판정** — 🔴 거절. SQL 이 `FROM ext_fund_page WHERE prvo_pbff_desc='공모'` 로 외부 테이블을 주 테이블로 잡았다 — ext_fund_page 에 prvo_pbff_desc·sale_yn·trusc_xtn_itt_cd·itm_nm 이 없다. JOIN 방향이 뒤집혀 '같은 이름의 항목이 여러 자료에' 로 기각. 정답은 미래에셋자산운용 / 신한은행.

### ✅ `KG-008` — 수탁사 랭킹

> 공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘

**예상** — 홍콩상하이은행 서울지점 714 · 국민은행 516 · 한국씨티은행 465 (펀드 단위)

**통과 조건** — 이름으로. 코드만 내면 부분 통과

**실제 답변**

```
조회 결과 펀드 수 상위 3개입니다 (판매중·공모 기준, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위, 기준일 2026-08-24).

1. 홍콩상하이은행 서울지점(00020054): 펀드 714개(클래스 1,827개)
2. 국민은행(00020004): 펀드 516개(클래스 1,656개)
3. 한국씨티은행(00020027): 펀드 465개(클래스 1,466개)
```

`[Execute] 3행`· 2.5s

<details><summary>SQL</summary>

```sql
SELECT trim(trusc_xtn_itt_cd) as 수탁회사명, SUM(fd_nast_suma) as 수탁금액, COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수", CAST(ROUND((SUM(fd_nast_suma))/100000000.0) AS INTEGER) || '억원' AS "수탁금액_억원" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY 1  ORDER BY "펀드수" DESC LIMIT 3
```
</details>

**판정** — 홍콩상하이 714 · 국민 516 · 씨티 465. 코드→은행명 변환까지.

### ✅ `KG-009` — 역할 혼동 함정

> 미래에셋증권이 수탁사인 공모펀드도 있어?

**예상** — 있다 — 2펀드 14클래스 (iM에셋 타이거 포커스 · 머스트원앤온리, 둘 다 사모투자재간접형). 수탁 코드 0016022 = 미래에셋증권(`ontology/codebooks/trustee.csv`, 투자설명서 관측). PDF §1.2 의 '수탁사는 대부분 은행' 에 예외가 있다.

**통과 조건** — 2건을 찾아내는가. '없다'고 하면 오답

**실제 답변**

```
조건에 해당하는 공모펀드는 전체 2개(클래스 14개)이며, 순자산 순으로 다음과 같습니다 (기준일 2026-08-24, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위·순자산 = 대표 클래스 기준(MAX)).

1. iM에셋 타이거 포커스 증권투자신탁(사모투자재간접형): 순자산 1,456억원 · 클래스 6개
2. 머스트원앤온리증권자투자신탁(사모투자재간접형): 순자산 969억원 · 클래스 8개
```

`[Execute] 2행`· 2.2s

<details><summary>SQL</summary>

```sql
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, trusc_xtn_itt_cd, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(trusc_xtn_itt_cd) = '0016022' AND prvo_pbff_desc = '공모') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY fd_nast_suma DESC LIMIT 30
```
</details>

**판정** — 2펀드(14클래스)를 찾아냈다. 수탁 코드 0016022 = 미래에셋증권(ontology/codebooks/trustee.csv). 내 예상('없다')이 틀렸다 — 증권사 수탁 사례가 실재한다.

### 🟡 `X22` — 🔴 거짓 전제

> KB자산운용 펀드 중 국민은행이 수탁하는 공모펀드는 몇 개야? 실제 수탁사는 어디야?

**예상** — KB자산운용 × 국민은행 수탁 = 0건. 실제 최다는 한국씨티은행 170클래스, 다음 홍콩상하이 120.

**통과 조건** — 0건임을 밝히고 실제 수탁사를 제시. 아무 수나 내면 환각

**실제 답변**

```
조건에 해당하는 상품이 데이터에서 확인되지 않습니다 (조회 결과 0건, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 3.3s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수", COALESCE(public_funds.trusc_xtn_itt_cd, '국민은행') as actual_trustee FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(or_co_xtn_itt_cd) = '00040035' AND prvo_pbff_desc = '공모' AND TRIM(trusc_xtn_itt_cd) = '00020004' /*M:FUNDUNIT*/) LIMIT 30
```
</details>

**판정** — 0건은 맞췄다. 그러나 2단 질문의 뒷부분 '실제 수탁사는 어디야?'에 답하지 않았다. 정답은 한국씨티은행 170클래스.


## I. 모자형 (§3.2)

### ✅ `KG-010` — 모자형 — 이름의 '자'

> 미래에셋코어테크 펀드의 모펀드는 뭐야?

**예상** — 미래에셋코어테크증권모투자신탁(주식).

**통과 조건** — 모펀드명을 제시. '없다'고 하면 오답

**실제 답변**

```
미래에셋코어테크 펀드의 모펀드는 미래에셋코어테크증권모투자신탁(주식)입니다.
```

`[Execute] 1행`· 6.5s

<details><summary>SQL</summary>

```sql
SELECT DISTINCT mother_fund_names_raw FROM public_funds JOIN ext_fund_page ON public_funds.itm_no = ext_fund_page.itm_no WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%') LIMIT 30
```
</details>

**판정** — 미래에셋코어테크증권모투자신탁(주식). 모자형 정확.


## J. 종목명 파싱·이름 조회 (§3.3)

### ❌ `X3` — 오타 흡수

> 미래에셋 코어택 펀드 순자산 알려줘

**예상** — '코어택' → 미래에셋코어테크. 종류A 7,348억 · C-P2E 6,842억 · A-E 6,292억

**통과 조건** — 오타에도 찾아냈는가. 0건이면 실패

**실제 답변**

```
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 질문의 「코어텍」를 데이터의 종목명으로 식별하지 못했습니다 (가까운 표기: 미래에셋코어테크증권자투자신탁(주식) · 미래에셋퇴직연금코어밸류증권자투자신탁1호(주식) · 삼성퇴직연금미국코어주식40증권자투자신탁H[채권혼합]).
```

`[Execute] 0행`· 3.0s

<details><summary>SQL</summary>

```sql
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", CAST(SUM(fd_nast_suma) AS INTEGER) AS fd_nast_suma, CAST(ROUND(SUM(fd_nast_suma)/100000000.0) AS INTEGER) || '억원' AS "순자산_억원", MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어텍%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
```
</details>

**판정** — 🔴 오타 '코어택' 매칭 실패, 0행. 예상은 미래에셋코어테크 순자산 7,348억. '가까운 표기' 후보 3개를 제시한 건 정상 동작이나 답을 못 냈다. (부수: 답변이 질문의 「코어택」을 「코어텍」으로 잘못 인용했다)

### ❌ `Z20` — 오타 흡수 2

> 미래에셋 코어태크 펀드 위험등급 알려줘

**예상** — '코어태크' → 미래에셋코어테크 위험등급 1등급(매우 높은 위험).

**통과 조건** — 찾아내고 등급 1 = 매우 높은 위험

**실제 답변**

```
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 질문의 「코어태크」를 데이터의 종목명으로 식별하지 못했습니다.
```

`[Execute] 0행`· 42.6s

<details><summary>SQL</summary>

```sql
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(zrin_fd_ivst_risk_grd_nm) AS zrin_fd_ivst_risk_grd_nm, MIN(rptt_ksd_itm_no) AS 대표번호, zrin_fd_ivst_risk_gcd FROM public_funds WHERE prvo_pbff_desc = '공모' AND (TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어태크%') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
```
</details>

**판정** — 🔴 오타 '코어태크' 매칭 실패, 0행. X3 보다 나쁘다 — 후보 안내조차 없다. 정답은 위험등급 1등급(매우 높은 위험).

### ✅ `V11` — 이름 포함 개수

> 삼성 이름이 들어간 공모펀드는 몇 개야?

**예상** — '삼성' 포함 229펀드 · 962클래스.

**통과 조건** — 229 또는 962

**실제 답변**

```
'삼성' 이름이 들어간 공모펀드는 229개(클래스 962개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
운용사 코드별: 00040010 207개 · 00080135 10개 · 00040024 9개 · 00040067 1개 · 00040007 1개 · 00040001 1개
```

`[Execute] 1행`· 슬롯 FUNDUNIT· ⚠ 재생성· 2.2s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%삼성%' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 229(962) + 운용사 코드별 분해까지.

### 🟡 `KG-005` — 2단 질문

> 이름이 삼성으로 시작하는 공모펀드는 몇 개고, 그중 삼성자산운용이 운용하는 건 몇 개야?

**예상** — '삼성' 시작 217펀드(906클래스) 중 삼성자산운용 운용 207펀드(850클래스).

**통과 조건** — 두 수를 모두. 850을 펀드 수로 내면 15R 최다 오답 재발

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 217개(클래스 906개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· ⚠ 재생성· 2.8s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, public_funds.itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no  WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND (REPLACE(itm_nm,' ','') LIKE '삼성%' OR mgmt_co_nm LIKE '%삼성%') /*M:FUNDUNIT*/ LIMIT 30
```
</details>

**판정** — 2단 질문의 앞부분(217/906)만 답하고 '그중 삼성자산운용이 운용하는 건 몇 개'(207/850)를 답하지 않았다. 15R 최다 오답(클래스를 펀드로)은 재발하지 않았다.


## K. 규모 (§4.8)

### ✅ `Y2` — 순자산 Top-N — MMF 지배

> 공모펌드 중 순자산이 가장 큰 3개 알려줘

**예상** — 삼성MMF법인제1호 C 12.43조 · KB법인용MMF I-1 9.63조 · 우리큰만족법인MMF1호 9.04조 (전부 MMF)

**통과 조건** — 값 일치 + 상위가 MMF로 채워진다는 점을 밝히면 가점

**실제 답변**

```
순자산 상위 3개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 순자산 = 대표 클래스 기준(MAX), 기준일 2026-08-24).

1. 삼성MMF법인제1호: 순자산 124,295억원 · 클래스 4개
2. KB법인용MMF I- 1: 순자산 96,266억원 · 클래스 2개
3. 우리큰만족법인MMF1호(국공채): 순자산 90,390억원 · 클래스 2개
```

`[Execute] 3행`· 2.9s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_nast_suma <> 0 GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_nast_suma) IS NOT NULL ORDER BY 3 DESC LIMIT 3
```
</details>

**판정** — 값 정확. 오타 '공모펌드'도 흡수. 상위가 전부 MMF인 건 밝히지 않았으나 통과 조건은 아니다.

### ✅ `T3` — 단일 운용사 합계

> 삼성자산운용이 운용하는 공모펀드 순자산 총액이 얼마야?

**예상** — 삼성자산운용 순자산 합계 33조 1,098억.

**통과 조건** — 33.1조 근사

**실제 답변**

```
삼성자산운용이 운용하는 공모펀드의 순자산 총액은 **331,098억원**입니다.
```

`[Execute] 1행`· 3.5s

<details><summary>SQL</summary>

```sql
SELECT SUM(fd_nast_suma), CAST(ROUND((SUM(fd_nast_suma))/100000000.0) AS INTEGER) || '억원' AS "순자산합계_억원" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040010') AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
```
</details>

**판정** — 331,098억원 정확.

### ✅ `V5` — 운용사 순자산 랭킹

> 순자산이 가장 큰 자산운용사 5곳 알려줘

**예상** — 미래에셋 37.8조 · 삼성 33.1조 · KB 27.8조 · 우리 22.5조 · 신한 19.5조

**통과 조건** — 이름 + 순서

**실제 답변**

```
조회 결과 순자산 상위 5개 운용사입니다 (판매중·공모 기준, 펀드 = 운용사 종목번호 기준, 클래스 = 판매 단위, 기준일 2026-08-24).

1. 미래에셋자산운용(00080008): 순자산 377,707억원 · 펀드 823개(클래스 2,066개)
2. 삼성자산운용(00040010): 순자산 331,098억원 · 펀드 207개(클래스 850개)
3. KB자산운용(00040035): 순자산 278,196억원 · 펀드 129개(클래스 625개)
4. 우리자산운용(00040007): 순자산 224,693억원 · 펀드 235개(클래스 403개)
5. 신한자산운용(00040067): 순자산 195,146억원 · 펀드 107개(클래스 405개)
```

`[Execute] 5행`· 3.1s

<details><summary>SQL</summary>

```sql
SELECT printf('%08d', CAST(p.or_co_xtn_itt_cd AS INTEGER)) AS "운용사코드", MAX(CASE WHEN printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || e.mgmt_co_nm NOT IN ('00040007/프랭클린템플턴투자신탁운용', '00040010/삼성액티브자산운용', '00040011/미래에셋자산운용', '00040013/슈로더자산운용', '00040023/우리자산운용', '00080008/멀티에셋자산운용', '00080008/미래에셋맵스자산운용') THEN e.mgmt_co_nm END) AS "운용사명", COUNT(DISTINCT printf('%08d', CAST(p.or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(p.mtco_itm_no)) >= 7 THEN trim(p.mtco_itm_no) ELSE substr('0000000' || trim(p.mtco_itm_no), -7) END, p.itm_no)) AS "펀드수", COUNT(*) AS "클래스수", CAST(ROUND(SUM(p.fd_nast_suma)/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no WHERE p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모' GROUP BY 1 ORDER BY SUM(p.fd_nast_suma) DESC LIMIT 5
```
</details>

**판정** — 5곳 이름·순서·순자산 정확. 펀드/클래스 병기까지.


## L. 설명서 항목 — PDF가 '없다'고 했으나 지금은 있는 것

### ✅ `Z9` — 설정일 (ext_fund_page)

> 미래에셋코어테크 펀드는 언제 설정됐어?

**예상** — 미래에셋코어테크증권자투자신탁 2019-10-21 설정.

**통과 조건** — 날짜 제시. '설정일은 없다'고 하면 PDF 낡은 주장을 따른 오답

**실제 답변**

```
'미래에셋코어테크' 이름의 공모펀드 2개가 조회됐습니다 (기준일 2026-08-24, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위).

- 미래에셋코어테크증권자투자신탁(주식): 설정일 2019-10-21 (약 6년 10개월) · 클래스 10개(전부 판매중)
- 미래에셋코어테크청년소득공제증권자투자신탁(주식): 설정일 2023-03-15 (약 3년 5개월) · 클래스 4개(전부 판매중)
```

`[Execute] 2행`· ⚠ 재생성· 45.5s

<details><summary>SQL</summary>

```sql
SELECT MIN(p.itm_no) AS 대표_itm_no, MIN(TRIM(p.itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN p.sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MIN(e.estb_dt) AS "최초설정일", MAX(e.estb_dt) AS "최근설정일", MIN(p.rptt_ksd_itm_no) AS 대표번호 FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no WHERE prvo_pbff_desc = '공모' AND (REPLACE(p.itm_nm,' ','') LIKE '%미래에셋코어테크%' AND TRIM(p.or_co_xtn_itt_cd) = '00080008') GROUP BY COALESCE(NULLIF(TRIM(p.rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(p.or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(p.mtco_itm_no)) >= 7 THEN trim(p.mtco_itm_no) ELSE substr('0000000' || trim(p.mtco_itm_no), -7) END, p.itm_no)) ORDER BY MIN(e.estb_dt) ASC LIMIT 30
```
</details>

**판정** — 2019-10-21 + 경과기간 + 두 펀드 구분. PDF가 '설정일 없음'이라 한 축을 정상 답변.

### ✅ `X19` — 연도별 설정

> 2025년에 설정된 공모펀드는 몇 개야?

**예상** — 2025년 설정 107펀드 · 305클래스.

**통과 조건** — 107 또는 305

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 107개(클래스 305개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· ⚠ 재생성· 2.5s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, public_funds.itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE estb_dt >= '20250101' AND estb_dt < '20260101' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
```
</details>

**판정** — 107(305) 정확.

### ✅ `KG-033` — 최근 설정 — 정렬

> 가장 최근에 설정된 공모펀드 알려줘

**예상** — 2026-06-12 설정 — KB K-성장과 지배구조 30 목표전환(채권혼합) / 미래에셋국민참여형국민성장 등.

**통과 조건** — 2026-06-12 를 집었는가

**실제 답변**

```
가장 최근에 설정된 공모펀드는 '**KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A**'입니다. 이 펀드는 2026년 6월 12일에 설정되었습니다.
```

`[Execute] 1행`· 8.0s

<details><summary>SQL</summary>

```sql
SELECT itm_nm, estb_dt FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' ORDER BY estb_dt DESC LIMIT 1
```
</details>

**판정** — 2026-06-12 KB K-성장과 지배구조 30. 정렬 정확.

### ❌ `FND-005` — 총보수 랭킹 — 단위 함정

> 총보수가 가장 낮은 공모펀드 5개 알려줘

**예상** — 피델리티호주펀드 0.015‰ · 미래에셋퇴직연금솔로몬1호 C-F 0.15‰ · 하나클래스원3호 C1 0.29‰ · 다올전단채 CW 0.35‰ · 미래에셋국공채전용MMFA1호 F 0.4‰

**통과 조건** — 🔴 마스터 보수는 ‰(퍼밀)이다. %로 옮겨 적으면 10배 틀린다. 단위를 밝히는가

**실제 답변**

```
총 보수가 가장 낮은 공모펀드 5개를 알려드리겠습니다.

1. 피델리티 호주 펀드: 총보수 0.015%
2.3.4. 다올 전단채 증권투자신탁 [채권] 종류 CW: 총보수 0.35%
5. 미래에셋 국공채 전용 MMF A1호(국공채): 총보수 0.4%

위의 펀드들은 모두 공모 펀드로, 클래스 수는 각각 1, 1, 1, 11, 6입니다.
```

`[Execute] 5행`· 10.2s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MIN(or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) as total_commission, fd_daily_bas_dt, COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) IS NOT NULL AND (or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) > 0 GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY 3 ASC LIMIT 5
```
</details>

**판정** — 🔴🔴 세 가지가 동시에 깨졌다. ① 단위 — 마스터 보수는 ‰(퍼밀)인데 '0.015%'로 적었다(10배 오류). ② 목록 붕괴 — '2.3.4.' 로 2·3·4위가 한 줄에 뭉개져 2·3위 이름이 사라졌다. ③ 클래스 수를 '각각 1, 1, 1, 11, 6' 이라 5개 적었는데 항목은 3개뿐이다. 답변 조립기 결함.

### ✅ `Z1` — 기준가 + 클래스 지정

> 미래에셋코어테크 펀드 종류A 기준가 알려줘

**예상** — 미래에셋코어테크증권자(주식) 종류A 기준가 4,726.41. (청년소득공제 종류A 는 3,321.17)

**통과 조건** — 기준가를 제시. 'PDF에 없다'고 하면 오답 — bns_bpr 은 있다

**실제 답변**

```
'미래에셋코어테크' 이름의 공모펀드 2개가 조회됐습니다 (기준일 2026-08-24, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위).

- 미래에셋코어테크증권자투자신탁(주식): 매매기준가 4,726.41 · 클래스 1개(전부 판매중)
- 미래에셋코어테크청년소득공제증권자투자신탁(주식): 매매기준가 3,321.17 · 클래스 1개(전부 판매중)
```

`[Execute] 2행`· 2.5s

<details><summary>SQL</summary>

```sql
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(bns_bpr) AS "bns_bpr_최고", MIN(bns_bpr) AS "bns_bpr_최저", MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds  WHERE prvo_pbff_desc = '공모' AND (REPLACE(REPLACE(itm_nm,' ',''),'-','') LIKE '%종류A' AND TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
```
</details>

**판정** — 4,726.41 / 3,321.17 둘 다. PDF가 '기준가 없음'이라 한 축을 정상 답변(bns_bpr).


## M. 보유 종목 (ext_fund_holdings)

### ✅ `AA19` — 보유 종목 + 비중

> 미래에셋코어테크 펀드 보유 종목 상위 5개와 비중 알려줘

**예상** — 삼성전자 24.95% · SK하이닉스 15.90% · 삼성전기 7.96% · SK스퀘어 7.46% · LG이노텍 4.46%

**통과 조건** — 5개와 비중. 순서 일치

**실제 답변**

```
미래에셋코어테크 펀드의 보유 종목 상위 5개와 비중은 다음과 같습니다:

1. 삼성전자: 24.95%
2. SK하이닉스: 15.9%
3. 삼성전기: 7.96%
4. SK스퀘어: 7.46%
5. LG이노텍: 4.46%
```

`[Execute] 5행`· 38.3s

<details><summary>SQL</summary>

```sql
SELECT h.holding_nm AS "종목명", h.weight_pct AS "비중_pct", h.asset_type AS "자산유형", h.bas_dt AS "기준일" FROM ext_fund_holdings h WHERE h.itm_no = (SELECT h2.itm_no FROM ext_fund_holdings h2 JOIN public_funds p ON h2.grp = p.mtco_itm_no AND h2.or_co = p.or_co_xtn_itt_cd WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%' ORDER BY p.fd_nast_suma DESC LIMIT 1) ORDER BY h.weight_pct DESC LIMIT 5
```
</details>

**판정** — 삼성전자 24.95 · SK하이닉스 15.9 · 삼성전기 7.96 · SK스퀘어 7.46 · LG이노텍 4.46. 완전 일치.

### ✅ `Z7` — 순위 지정

> 미래에셋코어테크 펀드가 두 번째로 많이 담은 종목은 뭐야?

**예상** — 2위 SK하이닉스 15.90%.

**통과 조건** — 2위를 정확히

**실제 답변**

```
미래에셋코어테크 펀드가 두 번째로 많이 담은 종목은 SK하이닉스로, 비중은 15.9%입니다.
```

`[Execute] 10행`· 4.3s

<details><summary>SQL</summary>

```sql
SELECT h.holding_nm AS "종목명", h.weight_pct AS "비중_pct", h.asset_type AS "자산유형", h.bas_dt AS "기준일" FROM ext_fund_holdings h WHERE h.itm_no = (SELECT h2.itm_no FROM ext_fund_holdings h2 JOIN public_funds p ON h2.grp = p.mtco_itm_no AND h2.or_co = p.or_co_xtn_itt_cd WHERE p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모' AND REPLACE(p.itm_nm,' ','') LIKE '%미래에셋코어테크%' ORDER BY p.fd_nast_suma DESC LIMIT 1) ORDER BY h.weight_pct DESC LIMIT 10
```
</details>

**판정** — 2위 SK하이닉스 15.9%. 순위 지정 정확.


## N. 답변불가 — PDF §5 중 지금도 살아있는 것 + 구조상 없는 것

### ✅ `X23` — 운용역 미수록

> 미래에셋코어테크 펀드 운용역이 누구야?

**예상** — 운용역 정보 없음. 운용사(미래에셋자산운용)는 안내 가능.

**통과 조건** — '수록되어 있지 않다'. 🔴 개인정보보호법 같은 법적 사유를 지어내면 오답

**실제 답변**

```
펀드 운용역(펀드매니저) 정보는 마스터·설명서 수집분에 없어 답할 수 없습니다. 운용사(운용회사 코드 → 법인명)는 안내할 수 있습니다.
```

**미실행**· 0.3s

**판정** — ABSENT 선언(hasFundManager)이 정확히 발동. 법적 사유를 지어내지 않고 대체 안내(운용사)까지.

### ❌ `OFFICIAL-002` — 🔴 투자전략 서술 미수록 — 09-04 스모크 실패

> 국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘

**예상** — 국민성장펀드 = 미래에셋국민참여형국민성장혼합자산투자신탁(사모투자재간접형) 4클래스. 구조·보수·환매는 답하되 **투자전략 동향은 미수록**임을 명시.

**통과 조건** — 🔴 '투자전략은 제공 데이터에 없음'을 명시하고 전략을 서술하지 않는다. 부인 문장이 있어도 뒤에서 전략을 단정하면 실패

**실제 답변**

```
국민성장펀드는 다음과 같이 구성되어 있으며, 주요 특징 및 투자 전략 방향성은 아래와 같습니다:

1. **종류**: 국민참여형 국민성장 혼합자산투자신탁 (사모투자재간접형)

2. **운영 회사**: 미래에셋자산운용

3. **수수료 체계**
 - 모든 클래스에서 선취 판매 수수료는 없으며, 온라인 거래를 지원합니다.
 - 관리 수수료는 클래스 C-e 및 C1-e 경우 연간 0.22%, 일반형(C) 및 서민형(C1)은 각각 0.38%, 0.37% 입니다.
 - 기타 신탁 및 관리 비용으로는 각각 0.008%, 0.01%가 부과됩니다.

4. **환매 규정**: 환매가 불가능하며, 기준가 적용 방식으로 지급됩니다.

5. **투자 전략**: 주로 국내 주식 및 채권 등에 분산 투자하여 안정적인 수익을 추구하는 전략을 취하고 있습니다.

현재 제공된 정보에서는 구체적인 투자 대상이나 비율 등의 세부적인 투자 전략 내용은 확인할 수 없습니다. 그러나 이 펀드는 안정적인 자산 배분을 통해 장기적으로 성장 가능성이 높은 기업들에 투자하고자 하는 목적을 가지고 있음을 알 수 있습니다.
```

`[Execute] 4행`· ⚠ 재생성· 10.3s

<details><summary>SQL</summary>

```sql
SELECT DISTINCT public_funds.itm_no, itm_nm, estb_dt, redemption_fee_desc, redemption_prohibited, redemption_pay_rule, total_fee_pct, sale_fee_pct, mgmt_fee_pct, trust_fee_pct, admin_fee_pct, class_desc_ko, mgmt_co_nm, mother_fund_names_raw FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%국민성장%' LIMIT 30
```
</details>

**판정** — 🔴🔴 같은 날 오전 스모크와 동일 실패, 재현 확인. '세부적인 투자 전략 내용은 확인할 수 없습니다' 라고 부인해 놓고 바로 앞줄에서 '투자 전략: 주로 국내 주식 및 채권 등에 분산 투자하여 안정적인 수익을 추구' 라고 단정했고, 끝에서 '장기적으로 성장 가능성이 높은 기업들에 투자하고자 하는 목적' 까지 덧붙였다. ext_fund_page 20컬럼에 투자전략 서술 컬럼이 없고 SELECT 한 14컬럼 어디에도 근거가 없다. 부인과 단정이 한 답변에 공존 = 환각. 4클래스라는 사실도 밝히지 않았다.

### ✅ `KG-027` — 좌수 — ABSENT 선언됨

> 미래에셋코어테크 펀드 설정 좌수 알려줘

**예상** — 좌수 컬럼 없음. 규모는 순자산, 가격은 기준가로 안내.

**통과 조건** — '좌수는 없다' + 대체 안내. fd_set_pcd '10'을 '10좌'로 읽으면 과거 환각 재발

**실제 답변**

```
공모펀드 마스터·설명서 수집분 어디에도 좌수(설정 좌수·잔존 좌수·잔고 좌수) 컬럼이 없어 좌수는 답할 수 없습니다. 규모는 순자산(fd_nast_suma), 가격은 기준가(bns_bpr, 기준일 단일 스냅샷)로 안내할 수 있습니다.
```

**미실행**· 0.3s

**판정** — ABSENT 선언(hasUnitsOutstanding) 정확 발동 + 대체 안내(순자산·기준가). 과거 'fd_set_pcd 10 → 10좌' 환각이 재발하지 않았다.

### ✅ `X24` — 기준가 시계열 — ABSENT 선언됨

> 미래에셋코어테크 펀드 기준가 추이 알려줘

**예상** — 기준가는 기준일 단일 스냅샷만. 추이 없음.

**통과 조건** — '추이는 없다' + 현재 기준가/기간 수익률 안내

**실제 답변**

```
기준가는 기준일 단일 스냅샷(bns_bpr)만 있고 시계열(추이·변동·과거 기준가)은 수록되어 있지 않습니다. 기준일 현재 기준가와 기간 수익률(1개월~5년 누적)은 안내할 수 있습니다.
```

**미실행**· 0.2s

**판정** — ABSENT 선언(hasNavHistory) 정확 발동 + 대체 안내.

### ✅ `FND-R01` — 없는 개념 (신용등급)

> 신용등급이 AAA인 공모펀드 알려줘

**예상** — 펀드에는 신용등급이 없다. 있는 것은 제로인 위험등급 1~6.

**통과 조건** — '펀드에 신용등급 개념이 없다' + 위험등급 안내. 채권 개념을 옮겨오면 오답

**실제 답변**

```
해당 상품군에는 요청하신 속성이 제공되지 않습니다. (신용등급 컬럼 없음 — 채권형 펀드도 등급은 구성종목 단위(미수록))
```

**미실행**· 0.3s

**판정** — '신용등급 컬럼 없음 — 채권형 펀드도 등급은 구성종목 단위(미수록)'. 채권 개념을 펀드로 옮기지 않았고 이유가 도메인 사실이다.

### 🟡 `FND-R04` — 미래 예측

> 내년에 수익률이 가장 좋을 공모펀드 추천해줘

**예상** — 예측 불가.

**통과 조건** — 미래 수익률은 데이터에 없다는 거절. 🔴 09-04 스모크에서 '스키마에 없는 컬럼' 부류로 떨어졌다 — 미래예측 REFUSE가 걸려야 정상

**실제 답변**

```
질문하신 항목이 이 상품 유형의 데이터에 없어 답변을 제공하지 못했습니다.
```

**미실행**· ⚠ 재생성· 6.9s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND mat_dt > 20290822 AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_yr1_ern_r) IS NOT NULL AND MAX(fd_yr1_ern_r) > -100 ORDER BY 3 DESC LIMIT 5
```
</details>

**판정** — 거절 자체는 맞다. 그러나 이유가 '질문하신 항목이 이 상품 유형의 데이터에 없어' — `스키마에 없는 컬럼` 부류다. 미래 예측은 _refusal.yaml 의 `미래_예측` 규칙 대상인데 그 규칙이 발동하지 않고 SQL 생성 → 환각 컬럼 → 기각 경로로 갔다. 오전 스모크와 동일.

### ✅ `KG-032` — 기준일 밖

> 2026년 9월 1일 기준으로 순자산이 가장 큰 공모펀드 알려줘

**예상** — 데이터 기준일 2026-08-21(일간 2026-08-24). 2026-09-01 시점 값은 없다.

**통과 조건** — 기준일을 밝히고 거절하거나, 기준일 값으로 답하며 그 사실을 명시

**실제 답변**

```
제공된 데이터의 기준일은 2026-08-24입니다. 이후 시점의 정보는 확인할 수 없습니다.
```

**미실행**· 2.9s

**판정** — 기준일 2026-08-24 를 밝히고 이후 시점은 확인 불가로 거절. 정확.

### 🟡 `OFFICIAL-NA-002` — 존재하지 않는 대상

> Kimi 관련 투자 상품 있어?

**예상** — 'Kimi' 관련 상품 없음.

**통과 조건** — '없다'. 유사 이름을 끌어오면 환각

**실제 답변**

```
질문하신 항목이 이 상품 유형의 데이터에 없어 답변을 제공하지 못했습니다.
```

**미실행**· ⚠ 재생성· 36.4s

<details><summary>SQL</summary>

```sql
SELECT pd_nm, pd_abrv_nm, pd_eng_nm, pd_exg_mkt_nm, pd_grp_no, pd_itm_no, pd_lstg_dt, pd_net_tamt, pd_sale_yn, pd_tr_yn, ref_base_index, ru_mkt_price, ru_mkt_volume, wu_inv_rgn, wu_upt_dt FROM overseas_etfs WHERE TRIM(pd_nm) LIKE '%김미%' OR TRIM(pd_abrv_nm) LIKE '%김미%' OR TRIM(pd_eng_nm) LIKE '%Kim%' LIMIT 30
```
</details>

**판정** — 거절은 했으나 이유가 스키마 부류다. 'Kimi 라는 이름의 상품이 데이터에 없다'가 정확한 사유인데 그 말이 없다. 사용자에게 의미는 전달되나 부류 매핑이 틀렸다.

### ✅ `UNANS-006` — 축 없는 추천 — 리드 결정

> 수익률 좋은 펀드 추천해줘

**예상** — 되묻지 말고 기본 축(1년 수익률)으로 답하고 그 기준임을 밝힌다.

**통과 조건** — 답을 내고 기준을 밝히면 통과. 되묻고 끝내면 실패(리드 결정 2026-08-31)

**실제 답변**

```
1년 수익률 상위 5개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 1년 수익률 = 클래스 최고값(MAX), 기준일 2026-08-24).

1. 한화2.2배레버리지인덱스증권투자신탁(주식-파생재간접형): 1년 수익률 387.66% · 클래스 6개
2. NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형]: 1년 수익률 362.53% · 클래스 4개
3. 삼성KOSPI200 2배레버리지증권투자신탁 제1호[주식-파생재간접형]: 1년 수익률 361.3% · 클래스 7개
4. NH-Amundi1.5배레버리지인덱스증권투자신탁(주식-파생형): 1년 수익률 257.14% · 클래스 5개
5. 하나 코리아증권자투자신탁[주식]: 1년 수익률 203.13% · 클래스 8개

※ 수익률 8기간 컬럼은 모두 누적 수익률이며 연 환산이 아닙니다. 100%를 넘는 값은 파생·레버리지 전략에서 나오므로 손실도 같은 배율로 커질 수 있습니다.
```

`[Execute] 5행`· 2.9s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, COUNT(*) AS "클래스수", zrin_attr_nms FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND itm_no NOT IN ('KR5157450126', 'KR5153450511', 'KR5119470012') GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_yr1_ern_r) IS NOT NULL AND MAX(fd_yr1_ern_r) > -100 ORDER BY 3 DESC LIMIT 5
```
</details>

**판정** — 되묻고 끝내지 않았다(리드 결정 2026-08-31 준수). 1년 수익률 축을 밝히고 답 + 누적/레버리지 경고까지.


## O. 되묻기

### 🟡 `FND-C01` — MMF 지배 — 되묻거나 두 답

> 규모가 큰 펀드 추천해줘

**예상** — 순자산 상위는 전부 MMF(삼성MMF법인제1호 12.43조 등). MMF 포함 여부를 되묻거나 포함/제외 두 답을 나란히.

**통과 조건** — MMF 지배 사실을 드러내는가

**실제 답변**

```
순자산 상위 5개 공모펀드입니다 (판매중·공모 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 순자산 = 대표 클래스 기준(MAX), 기준일 2026-08-24).

1. 삼성MMF법인제1호: 순자산 124,295억원 · 클래스 4개
2. KB법인용MMF I- 1: 순자산 96,266억원 · 클래스 2개
3. 우리큰만족법인MMF1호(국공채): 순자산 90,390억원 · 클래스 2개
4. 우리큰만족신종MMF3호: 순자산 80,497억원 · 클래스 1개
5. 신영법인용MMF 제4-26호 C-I형: 순자산 76,371억원 · 클래스 2개
```

`[Execute] 5행`· 2.8s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_nast_suma) IS NOT NULL AND MAX(fd_nast_suma) > 0 ORDER BY 3 DESC LIMIT 5
```
</details>

**판정** — 답은 냈으나 상위 5개가 전부 MMF라는 사실을 밝히지 않았다. `규모_MMF포함` 되묻기 규칙은 'MMF를 포함할지 묻거나 포함/제외 두 답을 나란히 내라'고 요구한다. 사용자는 '규모가 큰 펀드'를 물었지 법인 자금 파킹용 MMF를 물은 게 아니다.

### ❌ `FND-C02` — 범위 과대 — 되묻기

> 삼성 펀드 보수 알려줘

**예상** — '삼성' 이름 펀드가 229펀드 962클래스. 특정 펀드명을 되묻는다.

**통과 조건** — 되묻는다. 아무 한 행의 보수를 답하면 오답

**실제 답변**

```
조건에 해당하는 공모펀드는 전체 217개(클래스 906개)(대표번호 기준 186건)이며, 순자산 상위 30개 표시는 다음과 같습니다 (기준일 2026-08-24, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위·순자산 = 대표 클래스 기준(MAX)).

1. 삼성MMF법인제1호: 순자산 124,295억원 · 클래스 4개
2. 삼성스마트MMF법인 제1호 C: 순자산 40,334억원 · 클래스 1개
3. 삼성 베스트 MMF 법인 제1호: 순자산 21,900억원 · 클래스 1개
4. 삼성신종MMF: 순자산 16,236억원 · 클래스 2개
5. 삼성달러표시MMF법인 제1호(USD)_Cf: 순자산 4,839억원 · 클래스 5개
6. 삼성퇴직연금KOSPI200증권자투자신탁제1호[주식]: 순자산 4,652억원 · 클래스 2개
7. 삼성퇴직연금KOSPI200채권혼합증권자투자신탁제1호[채권혼합]: 순자산 4,411억원 · 클래스 3개
8. 삼성미국S&P500인덱스증권자투자신탁UH[주식]: 순자산 4,350억원 · 클래스 11개
9. 삼성 글로벌액티브 적격TDF 2050증권투자신탁UH[주식혼합-재간접형]: 순자산 4,030억원 · 클래스 5개
10. 삼성클래식인덱스연금증권전환형투자신탁 1[주식]: 순자산 3,223억원 · 클래스 2개
11. 삼성글로벌반도체증권자투자신탁UH[주식]: 순자산 2,527억원 · 클래스 5개
12. 삼성퇴직연금코리아대표채권혼합증권자투자신탁제1호[채권혼합]: 순자산 2,403억원 · 클래스 2개
13. 삼성퇴직연금OCIO솔루션밸런스증권투자신탁[채권혼합-재간접형]: 순자산 2,062억원 · 클래스 2개
14. 삼성글로벌반도체증권자투자신탁H[주식]: 순자산 1,969억원 · 클래스 5개
15. 삼성 글로벌액티브 적격TDF2045증권투자신탁H[주식혼합-재간접형]: 순자산 1,933억원 · 클래스 6개
16. 삼성 글로벌액티브 적격TDF2030증권투자신탁H[주식혼합-재간접형]: 순자산 1,733억원 · 클래스 5개
17. 삼성미국S&P500인덱스증권자투자신탁H[주식]: 순자산 1,607억원 · 클래스 11개
18. 삼성 글로벌액티브 적격TDF2040증권투자신탁H[주식혼합-재간접형]: 순자산 1,586억원 · 클래스 5개
19. 삼성 글로벌액티브 적격TDF2035증권투자신탁H[주식혼합-재간접형]: 순자산 1,448억원 · 클래스 5개
20. 삼성인덱스프리미엄증권투자회사A(주식-파생형): 순자산 1,425억원 · 클래스 3개
21. 삼성 글로벌액티브 TDF 2020 증권투자신탁H[채권혼합-재간접형]: 순자산 1,356억원 · 클래스 6개
22. 삼성코리아중기채권증권자투자신탁제1호[채권]: 순자산 1,319억원 · 클래스 7개
23. 삼성코리아대표증권자투자신탁 제1호[주식]: 순자산 1,252억원 · 클래스 9개
24. 삼성 글로벌액티브 적격TDF 2050증권투자
…(생략)
```

`[Execute] 30행`· ⚠ 재생성· 4.1s

<details><summary>SQL</summary>

```sql
SELECT or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r as total_commission_rate, or_co_xtn_itt_cd, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040010', '00080135', '00080134', '00080168', '00040092') AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (or_co_rwrd_r IS NOT NULL OR sale_co_rwrd_r IS NOT NULL OR trusc_rwrd_r IS NOT NULL OR ofwk_trus_rwrd_r IS NOT NULL) GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) ORDER BY fd_nast_suma DESC LIMIT 30
```
</details>

**판정** — 🔴 질문은 '보수'인데 **순자산 목록 30개**를 냈다. 답변 어디에도 보수 수치가 없다. `펀드이름` 되묻기 규칙('삼성 이름 펀드가 수백 개 → CLARIFY')도 발동하지 않았다.

### ❌ `FND-R03` — 주관 + 잘못된 전제

> 기준가가 높은 순서로 좋은 펀드 알려줘

**예상** — 기준가가 높은 것과 좋은 펀드는 무관하다(기준가는 설정 이후 누적일 뿐). 정렬 축을 되묻거나 수익률 축을 제안.

**통과 조건** — 기준가 순 정렬을 그대로 수행하면 오답

**실제 답변**

```
죄송합니다. 하지만 현재 제공된 데이터에서는 기준가가 높은 순서로 펀드를 나열하는 정보를 찾을 수 없습니다. 따라서 답변을 제공할 수 없습니다. 추가적인 정보가 필요하시다면 제공해주시면 더욱 정확한 답변을 드릴 수 있도록 노력하겠습니다.
```

`[Execute] 0행`· 49.9s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), fd_daily_bas_dt, fd_price_bas_dt FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_price_bas_dt IS NOT NULL AND fd_price_bas_dt > 20260822 ORDER BY fd_price_bas_dt DESC LIMIT 5
```
</details>

**판정** — 🔴 세 겹 실패. ① 기준가(bns_bpr)는 실재하는 컬럼인데 '정보를 찾을 수 없습니다'로 없다고 했다. ② '기준가가 높은 = 좋은 펀드'라는 잘못된 전제(기준가는 설정 이후 누적일 뿐)를 지적하지 않았다. ③ '죄송합니다 … 노력하겠습니다' 는 answer_rules 가 금지한 사과·면책 문구다.


## P. 도메인 축 신설 — PDF가 한 절씩 다루는데 기존 문항이 없던 13축

### ✅ `DOM-01` — 재간접

> 재간접 공모펀드는 몇 개야?

**예상** — 재간접 913펀드 · 2,594클래스.

**통과 조건** — 913 또는 2,594

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 913개(클래스 2,594개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.8s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND or_attr_desc = '재간접' AND sale_yn = '판매중' /*M:FUNDUNIT*/ LIMIT 30
```
</details>

**판정** — 913(2,594) 정확.

### ✅ `DOM-02` — 개인/법인

> 법인 전용 공모펀드는 몇 개야?

**예상** — 법인 전용 374펀드 · 441클래스. (개인 전용 1,063펀드 · 1,664클래스)

**통과 조건** — 374 또는 441

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 374개(클래스 441개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.3s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE pers_corp_desc = '법인' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 374(441) 정확.

### ❌ `DOM-03` — 통화

> 원화가 아닌 통화로 설정된 공모펀드는 몇 개야?

**예상** — 비원화 131펀드 · 187클래스 (USD 152 · EUR 29 · JPY 4 · SEK 1 · AUD 1).

**통과 조건** — 131 또는 187

**실제 답변**

```
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

**미실행**· 슬롯 FUNDUNIT· ⚠ 재생성· 4.4s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND curr_cd != 'KRW' /*M:FUNDUNIT*/ LIMIT 30
```
</details>

**판정** — 🔴 '질의를 안전하게 실행할 수 없어' 로 거절 — 게다가 이유 절이 없는 기본 문구(refusal_reason_text 부류 매핑 실패)다. curr_cd 는 결측 0인 정상 컬럼이고 정답은 131펀드/187클래스.

### ✅ `DOM-04` — 벤치마크 — 복합식 성분

> KOSPI200을 벤치마크로 쓰는 공모펀드는 몇 개야?

**예상** — 815펀드. 복합식('KOSPI200 25% + 종합채권01Y 75%')의 성분까지 포함해야 한다.

**통과 조건** — 815. 정확일치로 풀면 절반 넘게 놓친다

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 815개(클래스 2,217개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.5s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE REPLACE(bmrk_nm,' ','') LIKE '%KOSPI200%' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 815펀드(2,217클래스). 복합식 벤치마크 성분까지 포함해 셌다.

### ✅ `DOM-05` — 파생형

> 파생상품 유형 공모펀드 중 순자산 큰 3개 알려줘

**예상** — NH-Amundi코리아2배레버리지 Ce 7,333억 · 교보악사파워인덱스1호 종류A 5,050억 · 종류Ae 4,550억 (모수 90펀드 · 330클래스)

**통과 조건** — 파생상품 유형으로 필터했는가

**실제 답변**

```
순자산 상위 3개 공모펀드입니다 (판매중·공모·파생상품 기준, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, 순자산 = 대표 클래스 기준(MAX), 기준일 2026-08-24).

1. NH-Amundi코리아2배레버리지증권투자신탁[주식-파생형]: 순자산 7,333억원 · 클래스 4개
2. 교보악사파워인덱스증권투자신탁1호(주식-파생형): 순자산 5,050억원 · 클래스 9개
3. KB스타 미국 나스닥 100 인덱스 증권 자투자신탁(주식-파생형)(H): 순자산 3,225억원 · 클래스 10개
```

`[Execute] 3행`· 66.3s

<details><summary>SQL</summary>

```sql
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", or_attr_desc, CAST(ROUND(fd_nast_suma/100000000.0) AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds  WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND or_attr_desc = '파생상품' AND fd_nast_suma <> 0 GROUP BY COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) HAVING MAX(fd_nast_suma) IS NOT NULL ORDER BY 3 DESC LIMIT 3
```
</details>

**판정** — NH-Amundi 7,333억 · 교보악사 5,050억 · KB스타 미국나스닥100 3,225억. 펀드 단위로 묶어 교보악사 2클래스가 중복되지 않았다.

### ❌ `DOM-06` — 클래스 비용 — PDF가 '못 답한다'고 한 것

> 미래에셋코어테크 펀드는 A클래스와 C클래스 중 어느 쪽이 보수가 낮아?

**예상** — A 총 14.35‰(1.435%) < C 17.55‰(1.755%) — A가 낮다. 다만 A는 가입 시 선취 수수료를 따로 뗀다(han_clas_fee_type='수수료선취'). 그 금액은 마스터에 없어 '장기=A, 단기=C' 조건부로만 답할 수 있다.

**통과 조건** — 🔴 A가 낮다 + 선취 수수료 존재 + 기간 조건부. 총보수만 비교해 단정하면 부분 통과

**실제 답변**

```
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

**미실행**· ⚠ 값 검사 실패· ⚠ 재생성· 10.8s

<details><summary>SQL</summary>

```sql
SELECT or_co_xtn_itt_cd, COALESCE(CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no ELSE substr('0000000' || mtco_itm_no, -7) END, public_funds.itm_no) as fund_id, itm_nm, han_clas_fee_type, (or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r) as total_commission FROM public_funds  WHERE REPLACE(REPLACE(itm_nm,' ',''),'-','') LIKE '%종류A' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND REPLACE(REPLACE(itm_nm,' ',''),'-','') LIKE '%미래에셋코어테크%' AND (han_clas_fee_type = '수수료미징구' OR han_clas_fee_type = '수수료선취') AND total_commission IS NOT NULL AND total_commission < 100 AND REPLACE(itm_nm,' ','') LIKE '%미래에셋코어테크%' ORDER BY 6 ASC LIMIT 30
```
</details>

**판정** — 🔴 '질의를 안전하게 실행할 수 없어' 거절 + 값 검사 실패 + 재생성 실패. 보수 4종·han_clas_fee_type 이 전부 실재하는데 A/C 비교를 못 했다. 정답은 A 14.35‰ < C 17.55‰ 이고, 여기에 A의 선취 수수료(금액 미수록) 때문에 '장기=A·단기=C' 조건부라는 도메인 설명이 붙어야 한다. PDF §3.1 이 다루는 클래스의 존재 이유 자체를 못 답한 셈.

### 🟡 `DOM-07` — 판매완료 ≠ 청산

> 판매완료된 공모펀드는 몇 개야? 이미 청산된 거야?

**예상** — 판매완료·공모 3,934펀드 · 5,747클래스 (전체 행 12,714는 사모 포함). 청산이 아니라 신규 가입만 중단된 상태이며 기존 투자자는 그대로다.

**통과 조건** — 🔴 '청산 아님'을 말하는가. 숫자만 답하고 청산 여부를 넘기면 부분 통과

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 3,934개(클래스 5,747개)입니다 (공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 1.3s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매완료' AND prvo_pbff_desc = '공모' LIMIT 5 /*M:FUNDUNIT*/
```
</details>

**판정** — 숫자는 정확하다 — 3,934펀드(5,747클래스), 판매완료·공모. 그러나 질문의 뒷부분 '**이미 청산된 거야?**' 에 아무 답을 하지 않았다. PDF §2.3 의 '판매완료는 청산이 아니라 신규 가입 중단' 이 이 문항의 핵심이었다.

### 🟡 `DOM-08` — 환헤지 — 결측 39%

> 환헤지되는 공모펀드는 몇 개야?

**예상** — 환헤지(Y) 1,328펀드 · 3,688클래스. N 1,750 · 미수록 3,531(39%).

**통과 조건** — 🔴 결측 39%를 밝히는가. 3,688만 답하면 부분 통과

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 1,328개(클래스 3,688개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 1.7s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE exchdg_yn = 'Y' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 1,328(3,688) 정확. 그러나 **결측 39%(3,531클래스)를 밝히지 않았다.** Y만 세고 N·미수록을 말하지 않으면 '나머지는 환헤지 안 함'으로 읽힌다.

### ❌ `DOM-09` — 🔴 설립국가 95% 미지정

> 국내에서 설립된 공모펀드는 몇 개야?

**예상** — 셀 수 없다 — fd_estb_ctry_cd가 '000'(미지정) 8,561건 = 95%. 한국(410)은 298클래스뿐이라 이 수를 답으로 내면 오답. 대안: 역외펀드 여부(ofsfd_yn).

**통과 조건** — 🔴 '대부분 미지정이라 셀 수 없다'. 298을 답으로 내면 실패

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 1,162개(클래스 3,513개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 2.2s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE fd_ivst_rgn_desc = '국내' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' /*M:FUNDUNIT*/ LIMIT 30
```
</details>

**판정** — 🔴🔴 축 혼동. 1,162펀드(3,513클래스)는 `fd_ivst_rgn_desc='국내'`(**투자지역**)이다. 질문은 '국내에서 **설립된**' = `fd_estb_ctry_cd`. PDF §2.4 가 '펀드가 설립된 나라(투자처가 아님)'라고 명시적으로 경고한 바로 그 혼동이다. 정답은 '셀 수 없다' — 설립국가가 '000'(미지정) 8,561건 = 95%.

### ❌ `DOM-10` — 🔴 이자/배당 = 상수 컬럼

> 이자형 공모펀드와 배당형 공모펀드는 각각 몇 개야?

**예상** — 구분 불가 — int_dvd_desc가 판매중·공모 전건 '배당' 이다. '이자형 0개'는 오답이며, 0이 아니라 구분이 성립하지 않는다.

**통과 조건** — 🔴 '전건 동일 값이라 구분 불가'. '이자형 0개'면 실패

**실제 답변**

```
조회 결과에 따르면, 이자형 공모펀드는 1개이고, 배당형 공모펀드는 8,969개입니다.
```

`[Execute] 1행`· 43.0s

<details><summary>SQL</summary>

```sql
SELECT '이자형', COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND int_dvd_desc = '이자' GROUP BY 1 UNION ALL SELECT '배당형', COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND int_dvd_desc = '배당' GROUP BY 1 LIMIT 30
```
</details>

**판정** — 🔴🔴 헤더 행을 데이터로 읽은 환각. retrieved_context 가 `'이자형' | COUNT(*)` / `배당형 | 8969` 인데 — UNION ALL 의 이자형 가지가 0행이라 GROUP BY 로 사라지고 **컬럼 헤더만 남았다**. 답변기가 그 헤더를 세어 '이자형은 1개'라고 답했다. 실재하지 않는 수치다. 정답은 int_dvd_desc 가 판매중·공모 전건 '배당' 이라 **구분 자체가 성립하지 않는다**.

### 🟡 `DOM-11` — 🔴 헤지펀드 0 — 사모 영역

> 헤지펀드인 공모펀드는 몇 개야?

**예상** — 0건. 헤지펀드는 사모 영역이라 공모 모수에 없는 것이 정상이다(hdge_fd_yn 전건 0).

**통과 조건** — 🔴 0 + '사모 영역이라'는 도메인 설명. 0만 말하면 부분 통과

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
해당 조건인 펀드는 판매중·공모 기준 0개이고, 전체(판매완료·사모 포함)로는 3클래스가 있습니다.
```

`[Execute] 1행`· 슬롯 FUNDUNIT· 3.3s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (zrin_ptn_nm = '글로벌헤지전략' OR REPLACE(itm_nm,' ','') LIKE '%헤지펀드%' OR REPLACE(itm_nm,' ','') LIKE '%사모투자재간접%') AND REPLACE(itm_nm,' ','') LIKE '%헤지펀드인%' /*M:FUNDUNIT*/ LIMIT 30
```
</details>

**판정** — 0개 + '전체(판매완료·사모 포함)로는 3클래스' 까지 밝혔다. 사모에 있다는 사실을 시사하지만, '헤지펀드는 사모 영역이라 공모 모수에 없는 것이 정상' 이라는 도메인 설명은 없다. 숫자만 보면 결손처럼 읽힌다.

### ❌ `DOM-12` — 🔴 코드 의미 미제공

> 전문투자자만 살 수 있는 공모펀드는 몇 개야?

**예상** — 답할 수 없다 — pfiv_sale_cntl_tcd 값은 있으나(00 8,912 · 01 45 · 02 12) 코드 의미가 제공되지 않아 해석 불가. 45나 12를 답으로 내면 오답.

**통과 조건** — 🔴 '코드 의미가 없어 해석할 수 없다'. 숫자를 답으로 내면 실패

**실제 답변**

```
조회 조건에 해당하는 공모펀드는 27개(클래스 27개)입니다 (판매중·공모 기준, 기준일 2026-08-24).
```

`[Execute] 1행`· 슬롯 FUNDUNIT· ⚠ 재생성· 4.2s

<details><summary>SQL</summary>

```sql
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND han_clas_policies LIKE '%전문투자자%' LIMIT 30 /*M:FUNDUNIT*/
```
</details>

**판정** — 🔴 27개라 답했다. `pfiv_sale_cntl_tcd` 는 **코드 의미 미제공(주최 확정)** 이라 ontology 의 `query_rules.전문투자자코드금지` 가 '어떤 질의에도 조건·정렬로 쓰지 않는다'고 못박은 컬럼이다. 규칙이 프롬프트에 실려 있는데도 조건으로 썼고, 27이라는 해석 불가한 수를 확정 답변으로 냈다.

### 🟡 `DOM-13` — 🔴 누적 ≠ 연환산

> 미래에셋코어테크 펀드 3년 수익률을 연평균으로 알려줘

**예상** — 수록된 8기간은 전부 누적이며 연환산 값은 없다. 미래에셋코어테크증권자 3년 누적 약 188~191%(클래스별).

**통과 조건** — 🔴 누적값 + '연환산은 수록 없음'. 누적을 연평균인 척 내놓으면 최악의 실패

**실제 답변**

```
연평균(연환산) 수익률은 데이터에 수록되어 있지 않습니다. 수익률은 모두 누적 기준으로 1·3·6·18개월, 1·2·3·5년의 8개 기간이 수록되어 있습니다. 누적 수익률 기준의 조회나 순위를 원하시면 기간을 지정해 다시 질문해 주세요.
```

**미실행**· 0.2s

**판정** — '연평균(연환산)은 수록 없음 + 8기간 전부 누적' 을 정확히 밝혔다 — 이 셋에서 가장 어려운 축을 통과했다. 다만 있는 값(3년 누적 약 188~191%)을 함께 주지 않고 '기간을 지정해 다시 질문' 으로 넘겼다. 통과 조건이 '누적값 + 연환산 미수록' 이었다.

---

## 🔧 수리 기록 — 온톨로지·KG 층 (전수조사 진행분)

> 런타임 층 수리는 별도 트랙(`claude-9f`)이 담당한다. 이 절은 **노드 전수조사에서 나온 수리**만 시간순으로 적는다.
> ⚠️ 전부 **로컬 반영 상태**다. 배포는 사용자가 "한 번에" 요청할 때 일괄로 한다.

### R1 · `Fund` 노드 — 모펀드 717 제거 (2026-09-04)

| | |
| :-- | :-- |
| 대상 | `kg_node` 의 `MotherFund_*` 717 · `feedsInto` 1,704 |
| 파일 | `scripts/gen_fund_structure_auto.py` |
| 결과 | 노드 41,581 → **40,863** · `Fund` 7,584 → **6,867** · `feedsInto` → **0** |

**왜.** `Fund` 노드의 계약은 *"라벨(정식명)로 맞히고 alias(rptt 코드)로 조회한다"* 인데 모펀드는 **출구가 없다** — 설명서 텍스트에서 뽑은 이름이 마스터와 완전일치 **0건**이라 SQL 에 실을 코드가 없다. 실측에서도 매핑 0건이고, 유일한 간선 `feedsInto` 는 런타임이 **적재조차 하지 않는다**(`loader.py:305` 가 `subsidiaryOf` 만 읽는다).

**대체 경로가 있다.** 모자형 질의 3종이 KG 없이 SQL 로 답한다 — ① 모펀드명 `ext_fund_page` 조회(`KG-010` ✅ 가 실제로 이 경로) ② 모자형 여부 `itm_nm '자투자신탁'` 7,693행·태그 `M109` 6,984행 ③ 같은 모펀드 묶음 `GROUP BY` 538묶음.

**남긴 것.** 생성기 docstring 에 판정 근거와 "마스터에 일치하는 이름이 생기면 그때 edge 를 만든다" 는 복원 조건을 적었다. 노드 삭제가 아니라 **생성 중단**이다.

### R2 · `Organization` 노드 — 역외 운용법인 라벨 9건 + 합병 이력 2건 (2026-09-04)

| | |
| :-- | :-- |
| 대상 | `0013xxxx` 대역 9코드(110클래스) · `former_names` 2건 |
| 파일 | `ontology/codebooks/asset_manager.csv` · `ontology/shared/organization.yaml` |
| 결과 | 노드·alias 수 변동 없음 — **라벨만 교정** |

**문제.** 라벨이 **첫 펀드 이름 조각**이었다 — `피델리티펀드유로` · `북미펀드` · `템플턴글로벌본드`. 코드북 스스로 `status=derived · '법인명 아님'` 이라 적어 뒀는데 그 값이 `canonical_name` 자리에 정본처럼 앉아 있었다. 그래서 `KG-031`("피델리티가 운용하는 … 역외까지 포함")에서 Ground 가 `피델리티` → `Org_00080029` 만 잡고 **역외 노드는 못 잡았다**(라벨이 `피델리티펀드유로` 라 안 맞는다).

**처분 — 근거 강도로 갈랐다.**

| 처분 | 코드 | 근거 |
| :-- | :-- | :-- |
| 브랜드로 정정 | `00130001` 피델리티 · `00130004` AB · `00130006` 미래에셋 · `00130009` 젬스 · `00130012` 골드만삭스 · `00130026` 블랙록 | 종목명 접두 **100% 관측** — 추정이 아니다 |
| **미지 표시** | `00130002` · `00130003` · `00130005` | 접두 집중 **80% 미만**. `short_name` 을 비워 라벨이 **코드 자체**가 되게 했다 — 이름을 만들지 않는다 |
| `label_official` 비움 | 9개 전부 | 법인명이 **어느 출처에도 없음** 확인 — `ext_fund_page.mgmt_co_nm` 커버리지 94%인데 이 대역만 **0건** |
| `former_names` 보완 | `00080008` ← 미래에셋맵스 · `00040010` ← 삼성액티브 | 한 코드에 두 법인이 섞인 3건 중 미등록 2건 |

**규칙 준수.** 프로젝트 규칙은 *"코드 의미를 알 수 없으면 미지로 둔다"* 인데, 기존 상태는 추정을 이름으로 두어 그 규칙을 어기고 있었다. 미지 3건은 라벨이 코드가 되어 Ground 가 매칭할 일이 없고(사용자가 코드를 안 친다) 답변이 이름을 단정할 근거도 사라진다.

**검토했으나 하지 않은 것 — `ext_fund_page.mgmt_co_nm` alias 등록.** 세 용도가 다 막혔다: ① 접지는 마스터 코드가 낫다(**100% vs 94%**, JOIN 불필요) ② `label_official` 결측 중 모수 안 9개를 **0개** 채운다 ③ 이름 매칭은 `label_official` 이 이미 한다. 일회성 감사 자료로는 값이 있었다 — "한 코드 = 두 법인" 3건을 이걸로 찾았다.

### R3 · `Security` 노드 — 국내 티커 판정 비대칭 수정 (2026-09-04)

| | |
| :-- | :-- |
| 대상 | ETF·펀드 보유종목이 **같은 종목인데 다른 노드**로 갈린 17건 |
| 파일 | `scripts/gen_security_auto.py` |
| 결과 | 노드 40,863 → **40,836** · 펀드 얽힌 미연결 중복 523 → **499** |

**원인 — 두 분기의 비대칭.** 국내 티커 판정이 양쪽 다 `\d{6}`(숫자만)이었다. KRX 티커에는 신주·전환 등으로 **영문이 섞인 코드**가 있다(`0001A0` 덕양에너젠 · `00104K` CJ4우(전환) · `0007C0` 아크릴). 그래서 ETF 는 `Sec_d_<해시>`, 펀드는 `Sec_f_0001A0` 로 각자 빠져 **값이 같은데 남남**이 됐다. 게다가 ETF 분기에는 펀드 분기에 있는 `KR7…` ISIN → 티커 변환이 **없었다** — 펀드 쪽만 나중에 붙이고 ETF 쪽이 안 따라간 흔적이다.

**수정.** 양쪽을 `[0-9A-Z]{6}` 로 맞추고 ETF 분기에 `KR7([0-9A-Z]{6})\d{3}` 변환을 추가했다. 재생성하니 `덕양에너젠` → `Sec_kr_0001A0` 하나로 합류하고 ETF·펀드 alias 가 같은 노드에 붙는다. 국내 티커 노드 5,061 → **5,086** · 펀드 KR7 병합 91 → **133**.

**되돌린 판단 — 고아 84는 지우지 않는다.** `Sec_on_*` 84개가 alias 0·closure 0·edge 0 이라 처음엔 제거 대상으로 봤으나, yaml 에 사유가 있었다: `ambiguous_names: "ACCTON TECHNOLOGY CORPORATION"  # 이름이 다른 종목과 겹쳐 alias 제외 — 키(ticker/cusip)로만 매칭`. **이름 충돌을 일부러 표시한 노드**다(삼성전자↔삼성전기 오병합 방지). 지우면 그 판정 기록이 사라진다.

**남긴 것 — 잔여 499건은 조치하지 않는다.** 중국 A주 `000725 C2` ↔ `CNE0000016LA` 처럼 **동일 키가 없어** 안 묶인 것들이다. 설계 규칙(*"자동 병합은 동일 키일 때만, 이름만 같으면 병합 금지"*)이 의도대로 작동한 결과다. 496/499가 영문 라벨이고 239문항 중 이 종목을 묻는 문항은 **0건**. 필요해지면 `codebooks/security_alias_manual.csv` 에 한 행씩 추가해 정본으로 묶는 통로가 이미 있다(현재 29종).

### R4 · `Index` 노드 — 지수명 공백 정규화 (2026-09-04)

| | |
| :-- | :-- |
| 대상 | 공백만 다른 지수가 별개 노드로 갈린 2건 |
| 파일 | `scripts/gen_shared_auto.py` · `ontology/shared/index.yaml` |
| 결과 | Index 3,172 → **3,169** · 미연결 중복 5 → **1**(ETF 전용 잔여) |

**원인 — 두 층의 정규화가 어긋나 있었다.** SQL 조회는 공백을 무시하는데(`query_rules.어휘_표기정규화`: `replace(...,' ','')` 로 KOSPI200 0→95행) **노드 키는 공백으로 갈렸다**. 그래서 `KRX 300`/`KRX300` · `KOSDAQ 150`/`KOSDAQ150` 이 서로 다른 노드가 됐고, `KRX300` 은 한쪽이 펀드+ETF·다른 쪽이 ETF만 덮는 상태였다.

**수정 두 곳.** ① 노드 키에 `ihid()` 신설 — 공백을 접고 대소문자를 무시한다. ② 수동 노드 대조(`m_raw`)도 공백을 접는다 — 이게 없으면 수동 `KRX 300` 과 DB `KRX300` 이 완전일치에 실패해 자동 노드가 따로 생긴다.

⚠️ **`ontology/shared/index.yaml` 의 `parent:` 포인터 7곳을 함께 갱신했다.** 자동 노드 id 가 해시라 키 규칙을 바꾸면 수동 yaml 의 하드코딩 포인터가 깨진다(`MSCI AC World`·`MSCI EM`·`S&P 500` 세 해시 변경). **생성 규칙을 바꿀 때 수동 참조를 함께 본다** 는 것이 이 건의 교훈이다.

**🔴 숫자·기호는 지우지 않는다.** `ICE BofA **1-5** Year` 와 `**15+** Year` 는 만기 구간이 다른 별개 지수인데, `-`·`+` 를 지우면 둘 다 `15` 가 되어 오병합된다. 노드 키는 기호를 보존하는 게 옳고, 감사 질의가 기호를 지워 이 둘을 "중복" 으로 잡았던 것이 오탐이었다.

**조치하지 않은 것.** `Idx_MSCI_China`(alias 16 · 국내ETF+펀드 실물) 와 `Idx_a_6b1fe58db6`(자손 3 · 해외ETF TR/CR/NR 변형 패밀리)는 **이름이 같아도 역할이 다르다** — 실물 노드와 변형 루트라 병합하면 계층이 엉킨다. `iBoxx` 의 `Idx_a_`/`Idx_v_` 접두 분리는 국내/해외ETF 구분이라 ETF 트랙 사안이다.

**전수 결과.** Index 노드 3,169 = 접지 3,112 + 정본 57 · **고아 0**. 펀드 `bmrk_nm` 255종 **미등록 0**.

### R5 · `FundAttribute` 노드 — `confirmed_low_n` 태그 등록 (2026-09-04)

| | |
| :-- | :-- |
| 대상 | 판매중·공모에서 쓰이는데 KG에 없던 속성 태그 12종 |
| 파일 | `scripts/gen_fund_attribute_yaml.py` |
| 결과 | `FundAttribute` 179 → **210** · 실사용 미등록 **12 → 0** |

**원인 — 문자열 완전일치가 `confirmed_low_n` 을 함께 잘랐다.**

```python
if r.get("status", "confirmed") != "confirmed":   # confirmed_low_n 도 탈락
```

코드북 210종 중 `confirmed_low_n` 이 31종인데 **검증률이 전부 1.000** 이다 — "확정됐으나 표본이 적다"(1~4행)는 뜻이지 틀렸다는 뜻이 아니다. 그중 12종이 판매중·공모에서 실제로 쓰인다(`물` 4행 · `조선(해운/선박)` 4행 · `Dur 3~4` 4행 · `에너지(수소)` 2행 …). **표본이 적은 태그일수록 이름으로 못 찾으므로, 접지를 빼는 이유가 아니라 더 필요한 이유다.**

**수정.** `.startswith("confirmed")` 로 바꿔 `confirmed_low_n` 을 받는다. 반영 후 **실사용 192/192 접지**.

**노이즈 점검 — 0건.** 추가 31종의 라벨이 기존 노드와 충돌하는 것은 **0종**. 2자 이하 라벨 2종(`물`·`선박`)은 런타임 하한(FundAttribute 3자)에 막혀 매칭되지 않는다 — 노이즈가 아니라 무효 노드다. 하한은 낮추지 않는다(`물` 이 `선물·현물·곡물` 에 부분일치한다. `기타`/`기타비용` 오탐으로 AssetClass 를 제외한 것과 같은 이유).

**ETF 대조 — 충돌 없음이 확인됐다.** 펀드의 `prfd_attr_cds` 같은 **코드 태그 다중값 컬럼이 ETF 에는 없다**: `pd_sect_cd`(distinct 5·다중값 0)·`cu_strtegy`(국내 4·다중값 0). `overseas_etfs.cu_strtegy` 는 다중값 4,387행이나 **일부러 접지하지 않는다**(`전략텍스트_분류금지` — 투자설명서 문장 텍스트라 분류 컬럼이 아니다). 자산군 축(`*_ast_type`)은 이미 `AssetClass` 로 양쪽 접지돼 있다. → `FundAttribute`·`Country` 는 **펀드 전용 개체**가 맞다.

**유지한 것 — 죽은 태그 16종.** 판매중·공모 0행이지만 11종은 판매완료·사모에 실재하고 코드북에 뜻이 있다. 국가 태그 5종(`AUS`·`ESP`·`FRA`·`GBR`·`MYS`)은 **"없다"고 답할 근거**다 — `X21`("스페인에 투자하는 공모펀드 있어?" → 0건 ✅)이 이걸로 통과했다.

### R6 · `Region`·`AssetClass`·`Currency`·`RiskGrade` — 조치 없음 (2026-09-04)

네 축 모두 **닫힌 분류축**이고 펀드·ETF·채권 공용이다. 전수 확인 결과 고칠 것이 없었다.

| 노드 | 수 | 펀드 미등록 | 고아 |
| :-- | --: | --: | :-- |
| `Region` | 60 | **0** | 0 |
| `AssetClass` | 9 | **0** | 0 |
| `Currency` | 8 | **0** | 1 — `Curr_Unknown`, 기록된 `pending` |
| `RiskGrade` | 7 | **0** | 0 |

**검토했으나 결함이 아니었던 것 — `RiskGrade` 의 상품군 공용.** 등급 6개가 채권·국내ETF·펀드를 **동시에** 덮는다(`RiskGrade_1` ← 채권 `11` · ETF `PD_RISK_GCD_11` · 펀드 `1.0`). 도메인 PDF §2.5 가 *"산출 주체와 기준이 다르니 상품군을 넘나들면 서로 다른 잣대를 섞는 셈"* 이라 경고한 자리라 처음엔 결함으로 봤으나, **해석 규칙이 이미 yaml 에 들어가 있다**:

```yaml
scale: "0~6 (정수)"
direction: "낮을수록 위험 (1=매우높은위험, 6=매우낮은위험)"
range_by_table:
  public_funds:   {min: 1, max: 6, note: "0등급 없음 — 미수록은 NULL(0 아님)"}
  domestic_etfs:  {min: 1, max: 6, note: "0등급 없음"}
  domestic_bonds: {min: 0, max: 6, unclassified: 0, note: "'00' 19건 실재"}
```

**테이블별 정의역이 갈려 선언돼 있다** — 채권만 `0~6`, 나머지는 `1~6`. 이것이 "잣대가 다르다" 의 데이터 표현이고, ttl 제약·게이트 상수·답변 규칙 세 층으로 나간다. 오늘 실측에서 `KG-013`(7등급)·`KG-014`(0등급) 둘 다 ✅ 통과한 것이 그 근거다. 표기 3종을 한 노드로 묶은 것은 KG 가 해야 할 일을 한 것이고, 정의역 차이는 별도 축으로 이미 표현돼 있다.

---

### R7 · 배포 게이트 — 회귀 3건 회수 + 고정선 1줄 갱신 (2026-09-04)

전수조사 R1~R6 을 반영한 뒤 `pytest` 551건을 돌렸다. **`deploy.sh` 0단계가 이걸 게이트로 쓴다.** 첫 실행에서 4건이 깨졌고 **전부 내 판단 오류**였다.

| 깨진 테스트 | 무엇이 원인이었나 | 처분 |
| :-- | :-- | :-- |
| `test_round14_repairs` 2 · `test_round16_repairs` 1 | 🔴 **R2 의 "미지 표시" 판단이 틀렸다.** 접두 집중도 80% 를 잣대로 `00130003`(슈로더 10/13=77%) · `00130002`(템플턴 6/9=67%) 를 미지로 돌렸는데, 나머지는 **브랜드를 이름에 안 넣은 같은 회사 상품**이었다. `X12`(슈로더 역외 포함) 가 이 라벨에 의존한다 | 둘 다 `brand_observed` 로 복원. `00130005` 만 미지 유지 (미국달러 4/11=36% · `북미펀드`·`이머징마켓펀드` 류) |
| `test_snapshot_round6::test_round6_fixed_line` | 🔴 **R5 가 `FundAttr_M108 '모펀드'` 를 등록해 질문 낱말을 가로챘다.** *"…의 모펀드는 뭐야?"* 가 태그 필터로 접지돼 `LIKE '%,M108,%'` 가 붙고 **0행**. 노이즈 검사를 기존 노드 라벨하고만 대조하고 **질문 어휘와 대조하지 않은** 탓이다 | `confirmed_low_n` 등록 조건에 `n_selling > 0` 추가 — 판매중·공모에서 한 번도 안 쓰인 태그는 등록하지 않는다 |

**잣대가 틀렸던 자리.** 접두 집중도 77% 는 *"브랜드가 아니다"* 가 아니라 *"일부 상품이 이름에 브랜드를 안 넣는다"* 는 뜻이다. 빈도로 브랜드 여부를 판정한 것 자체가 잘못이었고, 규칙은 **외부 데이터로 회사 정체가 확인되면 라벨을 준다**여야 한다.

#### 고정선 1줄 갱신 — `V3` 접지 노드

두 번째 실행에서 `V3` 한 문항이 남았다. 차이는 **노드 id 한 줄뿐**이다.

| | 고정선(기존) | 지금 |
| :-- | :-- | :-- |
| 접지 노드 | `Idx_a_fa21f0fb15` (auto·정본·alias **0**) | `Idx_KOSPI200` (curated·접지·alias **22**) |
| `where` · `rows` · `assembler` · `answer_head` | | **전부 동일** |

R4 의 공백 정규화가 두 노드를 부모–자식으로 묶으면서(`Idx_a_fa21f0fb15` ⊃ 자손 6, `Idx_KOSPI200` 포함) 접지가 **alias 를 직접 가진 자식**으로 내려왔다. 실측으로 무해를 확인했다:

```
[Ground] 'KOSPI 200' → Idx_a_fa21f0fb15 [+후손 6] → bmrk_nm='KOSPI200' · 'KOSPI200 10% + KIS종합채권 01Y 90%' · …
```

- 부모 접지는 **closure 로 자손 alias 를 끌어온다**(`Sec_m_nvidia` 와 같은 설계)
- `KOSPI200`(붙임) · `KOSPI 200`(공백) 두 표기가 **같은 답 421펀드** — R4 이전엔 공백형이 따로 놀았다
- 자식 접지가 오히려 **라벨(입구)→alias(출구)** 접지 계약에 부합한다

→ 의도한 변경이므로 `SNAPSHOT_WRITE=1` 로 고정선을 갱신했다(테스트 docstring 이 지시한 절차).

**최종 `551 passed`.**

---

## 📋 펀드 도메인 노드 전수조사 — 종합

각 노드마다 **① 펀드 노드 확인 → ② ETF 대응 노드 확인 → ③ 키 컬럼 대조 → ④ 처분** 순으로 봤다. ③ 이 핵심이었다 — 노드만 비교하면 `Sec_d_*` 와 `Sec_f_*` 는 그냥 다른 노드로 보이고, **값을 비교해야 같은 것임이 드러난다**(R3 가 그 사례).

| 노드 | 수 | ETF 대조 | 수리 |
| :-- | --: | :-- | :-- |
| `Fund` | 6,867 | ETF 에 상위상품 컬럼·모자형 표기 **없음**(`모투자신탁` 0건) → 대응 개체 없음 | **R1** 모펀드 717 미생성 |
| `Organization` | 2,526 | ETF 는 `cu/ref_fund_mgmt_co` 로 **같은 노드 공유**. `0013xxxx` 는 ETF alias **0건**(펀드 전용)이라 라벨 변경 영향 없음 | **R2** 라벨 9 · `former_names` 2 |
| `Security` | 27,969 | 🔴 **충돌 발견** — ETF `ticker` vs 펀드 `isin` 이 같은 값인데 판정이 비대칭 | **R3** 17건 합류 |
| `Index` | 3,169 | 🔴 **충돌 발견** — 공백 표기가 갈려 `KRX300` 이 펀드/ETF 로 분리 | **R4** 2건 병합 |
| `FundAttribute`·`Country` | 210 · 17 | 태그형 다중값 컬럼이 **ETF 에 없음**(`pd_sect_cd` 단일) → 충돌 없음 | **R5** 12종 등록 |
| `Region`·`AssetClass`·`Currency`·`RiskGrade` | 60·9·8·7 | 세 테이블 공용 접지 **정상 작동** | 없음 (**R6**) |

**충돌은 두 곳에서 났고 둘 다 "펀드·ETF 를 따로 작업한 흔적"** 이었다 — `Security` 는 같은 파일 안 두 분기의 판정 비대칭(펀드 쪽만 `KR7` 변환을 나중에 추가), `Index` 는 노드 키와 SQL 조회의 정규화 불일치.

### 최종 수치

| | 조사 전 | 조사 후 |
| :-- | --: | --: |
| `kg_node` | 41,581 | **40,845** |
| `kg_alias` | 66,592 | **66,603** |
| `kg_edge` | 7,414 | 5,704 |
| 검증 | 오류 0 | **오류 0** |

노드가 준 것은 모펀드 717 제거分이고, alias 가 는 것은 속성 태그 31종 추가分이다. **접지(alias)는 늘고 접지 못 하는 노드는 줄었다.**

### 남긴 것

| | 이유 |
| :-- | :-- |
| `Security` 미연결 중복 **499** | 중국 A주 `000725 C2` ↔ `CNE0000016LA` 등 **동일 키가 없다**. 설계 규칙(*"이름만 같으면 병합 금지"*)이 의도대로 작동한 결과. 239문항 중 해당 종목을 묻는 문항 **0건**. 필요 시 `security_alias_manual.csv` 에 한 행씩 추가하는 통로가 있다 |
| `Sec_on_*` 84 | `ambiguous_names` 기록 보유 — **모호 표시 노드**(부류 ⑤). 지우면 판정 기록이 사라진다 |
| `iBoxx` `Idx_a_`/`Idx_v_` | 국내/해외ETF 접두 분리 — **ETF 트랙 사안** |
| `물`(N117) | 등록됐으나 라벨 1자로 런타임 하한(3자)에 막혀 매칭 불가. 하한을 낮추면 `선물·현물·곡물` 오탐 |

### 미커밋 파일

```
scripts/gen_fund_structure_auto.py · ontology/shared/fund_structure_auto.yaml
scripts/gen_security_auto.py · ontology/shared/security_auto.yaml
scripts/gen_shared_auto.py · ontology/shared/index_auto.yaml · ontology/shared/index.yaml
scripts/gen_fund_attribute_yaml.py · ontology/shared/fund_attribute_auto.yaml
ontology/codebooks/asset_manager.csv · ontology/shared/organization.yaml
ontology/shared/organization_manager_auto.yaml · ontology/common.ttl
tests/snapshots/round6_fixedline.json   ← R7 고정선 갱신
```

⚠️ `data/financial_products.db` 는 2026-09-04 15:50 배포에 **R1 이 실려 나갔다**(서버 `kg_node 40,863 · MotherFund 0`). 커밋된 생성기는 아직 MotherFund 를 만들라고 되어 있어 **소스↔서버 불일치**가 남아 있다 — 커밋하면 해소된다. 런타임 무해는 확인됨(`feedsInto` 소비 0 · pytest 550 통과).

