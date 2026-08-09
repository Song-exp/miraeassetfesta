# 🗄️ SQLite 데이터베이스 아키텍처 및 구축 가이드 (`SQLITE_SETUP.md`)

> **미래에셋 금융상품 마스터 데이터 (약 14.5만 건) SQLite DB 구축 및 조회 스펙 문서**

---

## 1. 프로젝트 DB 개요 및 관리 구조

* **생성 파일 위치**: `data/financial_products.db`
* **자동 변환 스크립트**: `scripts/build_db.py`
* **데이터 원본**: `1.금융상품/` (엑셀 마스터 및 스키마 파일 8종)
* **총 데이터 수량**: 마스터 4종 합계 **145,393 건** + 메타데이터 테이블 `schema_metadata` 207 건

```plaintext
미래에셋/
├── data/
│   └── financial_products.db      <-- 구축된 SQLite DB 파일 (총 145,393건)
├── scripts/
│   └── build_db.py                <-- 엑셀 ➔ SQLite 파싱 & 구축 스크립트
├── docs/
│   └── sqlite_db_architecture.md  <-- DB 아키텍처 및 스키마 문서
└── 1.금융상품/                    <-- 원본 엑셀 마스터 및 스키마 파일
```

---

## 2. DB 테이블 구성 및 명세 (Total 5개 테이블)

### 📊 1) `domestic_bonds` (국내채권 마스터)
* **레코드 건수**: **42,394 건**
* **원본 파일**: `PRBD01N001_국내채권마스터_20260711_datarows.xlsx`
* **주요 속성**:
  - `PD_NO`: 채권 종목코드 (PK)
  - `PD_NM`: 종목명
  - `PD_RISK_GCD`: 위험등급 — **INTEGER 0~6** (⚠️ 1~5 아님. 6등급 10,408건, 0등급 58건)
  - `CRD_GRD`: 신용등급 — `AAA/AA+/AA0/AA-/…/C` 20종 (⚠️ **`AA0` 처럼 `0` 표기**. `'AA'`로 조회 시 0건)
  - `PD_EVCO_CRD_GRD`: 평가사별 신용등급 — 콤마 결합 문자열(`'A+, AA-, AA-'`), 결측 41.1%
  - `ISU_DT` / `MAT_DT`: 발행일 / 만기일
  - `SRFC_IRT`: 표면금리 (%)
  - `BUY_YIELD`: 매수수익률 (%) — **결측 97.9%** (수록 881건)
  - `AFTER_TAX_YIELD`: 세후수익률 (%) — **결측 97.9%** (수록 881건)
  - `DUR`: 듀레이션 — 결측 31.6%
  - `EVAL_PRICE`: 평가가격
  - `BD_KND`, `PD_NM`, `PD_ABRV_NM`, `PD_ENG_NM`, `PD_PBCM`: ⚠️ **고정폭 공백 패딩 존재** — 반드시 `TRIM()` 경유
    (`WHERE BD_KND='일반회사채'` → 188건 / `WHERE TRIM(BD_KND)='일반회사채'` → 13,998건)

---

### 📊 2) `domestic_etfs` (국내ETF 마스터)
* **레코드 건수**: **1,734 건**
* **원본 파일**: `PREF01N001_국내ETF마스터_20260711_datarows.xlsx`
* **주요 속성**:
  - `pd_itm_no`: ETF 종목코드 (PK)
  - `pd_nm` / `pd_abrv_nm`: 종목명 / 약어명
  - `pd_grp_no`: 🔴 **`'ETF'`(1,202) / `'ETN'`(532) 구분 컬럼.** 이 테이블은 ETF 전용이 아닙니다 — ETN 30.7% 혼입
  - `cu_fund_mgmt_co`: 운용사 — 약칭 위주(`삼성` 224, `미래에셋` 193, `KB` 147). ⚠️ `'미래에셋자산운용'`으로 조회 시 **0건**.
    정식명(`메리츠증권 주식회사`)·상품명 오염(약 60건)·`'.'` 혼재
  - `cu_base_index`: 기초지수 (예: `KOSPI200`) — **결측 96.7%** (수록 58건, 대부분이 NULL 아닌 **공백 문자열**)
  - `cu_charge_rt`: 총보수요율 (%) — **결측 87.5%** (non-null 217건, ⚠️ **그중 150건이 `0` → 실질 67건**)
  - `pd_risk_cd`: 위험등급 — 문자열 `PD_RISK_GCD_11` ~ `_16` (**뒤 2자리 − 10 = 등급**, 즉 1~6등급)
  - `du_er_1y`: 최근 1년 수익률 (%) — 결측 20.6%
  - `du_er_ytd`: YTD (연초 대비) 수익률 (%)
  - `du_last_aum`: 순자산 총액 (AUM) — 결측 16.2%
  - `pd_sect_nm`: 섹터명 — **전 레코드 결측** (조회 불가)

---

### 📊 3) `overseas_etfs` (해외ETF 마스터)
* **레코드 건수**: **5,646 건**
* **원본 파일**: `PREF02N001_해외ETF마스터_20260711_datarows.xlsx`
* **주요 속성**:
  - `pd_itm_no`: 해외 ETF 티커 / 종목코드
  - `pd_nm`: 종목명
  - `pd_isin_cd`: ISIN 코드
  - `pd_exg_mkt_cd`: 상장시장 — 실제 값은 `NYS` / `NAS` / `AMX` / `101` / `102` (⚠️ `'NYSE'`로 조회 시 **0건**)
  - `pd_trd_ccy`: 거래통화 — 전건 `USD` 단일
  - `cu_fund_mgmt_co`: 운용사명 — **영문** 372종 (`ARK Investment Management LLC`) + NULL
  - `cu_charge_rt`: 총보수요율 (%) — **결측 0%** (국내ETF 87.5% 결측과 대조)
  - `cu_base_index`: 기초지수 — ⚠️ **센티넬 문자열** 주의. `Index is not provided by Management Company` 1,984건,
    `Index is not available on Lipper Database` 721건 → 실질 수록 2,933건(51.9%)
  - `cu_etn_yn`: **ETN 여부** (`'Y'` 59건) — ETF 전용 질의 시 필터 필요
  - `cu_inverse_short_yn`: 인버스·숏 여부 (`'Y'` 171건)
  - `du_last_aum`: 순자산 AUM
  - `du_er_1d`: 1일 수익률 (%)

---

### 📊 4) `public_funds` (공모펀드 마스터)
* **레코드 건수**: **95,619 행** ⚠️ — 고유 펀드는 **11,127개**입니다 (아래 `std_itm_no` 항목 참조)
* **원본 파일**: `PRFD01N001_공모펀드마스터_20260711_datarows.xlsx`
* **주요 속성**:
  - `std_itm_no`: 표준코드 — 🔴 **PK가 아닙니다.** 95,619행 / distinct 11,127개 (평균 8.6행 중복)
  - `prfd_attr_cd`: 펀드 속성코드 — **실질 복합키는 `(std_itm_no, prfd_attr_cd)`**.
    같은 펀드가 속성코드별로 최대 16행까지 분리되어 있고, 이름·수익률·AUM 등 나머지 값은 전부 동일합니다.
  - `itm_nm`: 펀드 종목명 — 중복 종목명 11,138건
  - `or_co_xtn_itt_cd`: 운용사 코드 — ⚠️ **숫자 코드 67종만 수록. 운용사 이름 컬럼이 없음** (코드↔이름 매핑 필요)
  - `or_attr_desc`: 운용속성 — `주식형`/`채권형`/`재간접`/`MMF` 등 11종. ⚠️ 미해독 코드 `'06'` 5,436건 포함
  - `zrin_fd_ivst_risk_gcd`: 위험등급 — **REAL 1.0~6.0** (⚠️ 1~5 아님), **결측 19.3%**.
    라벨(`zrin_fd_ivst_risk_grd_nm`) 표기 흔들림: `'높은 위험'` vs `'높은위험'`
  - `fd_yr1_ern_r`: 최근 1년 수익률 (%) — 결측 32.6%
  - `fd_mm3_ern_r`: 3개월 수익률 (%)
  - `fd_nast_suma`: 순자산 총액 (AUM) — 결측 13.1%
  - `exchdg_yn`: 환헤지 여부 (Y/N)
  - `sale_yn`: 판매 여부 — `'판매중'` / `'판매완료'` (⚠️ Y/N 아님)
  - ⚠️ **보수 정보 컬럼 자체가 없습니다.** 펀드 보수 질의는 "데이터 미제공" 응답 대상

---

### 📋 5) `schema_metadata` (한글/영문 스키마 메타데이터)
* **레코드 건수**: **207 건**
* **용도**: 자연어 질의를 Text-to-SQL로 파싱할 때, 영문 컬럼명과 한글 컬럼명 의미를 1:1로 자동으로 연결해 주는 메타데이터 테이블.
* **주요 속성**: `table_name`, `column_name`, `korean_name`

---

## 3. 고속 조회를 위한 인덱스(Index) 설계

Agent의 15초 응답 SLA를 충족하기 위해, 빈번히 조회/정렬되는 필드에 고속 탐색 B-Tree 인덱스를 적용했습니다:

* **국내채권 (`domestic_bonds`)**: `PD_NO`, `PD_NM`, `PD_RISK_GCD`, `MAT_DT`, `AFTER_TAX_YIELD`
* **국내ETF (`domestic_etfs`)**: `pd_itm_no`, `pd_nm`, `cu_fund_mgmt_co`, `du_er_1y`, `du_last_aum`
* **해외ETF (`overseas_etfs`)**: `pd_itm_no`, `pd_nm`, `cu_fund_mgmt_co`, `du_er_1d`, `du_last_aum`
* **공모펀드 (`public_funds`)**: `std_itm_no`, `itm_nm`, `fd_yr1_ern_r`, `zrin_fd_ivst_risk_gcd`

---

## 4. Agent 연동 및 활용 예시 (Text-to-SQL)

사용자 질의가 들어왔을 때 Agent의 SQL 생성기가 아래와 같이 0.001초 만에 데이터베이스를 즉시 조회합니다.

> ⚠️ **SQL 생성 시 반드시 적용할 3가지** — 빠뜨리면 조용히 틀린 답이 나갑니다.
> 1. 문자열 비교는 **`TRIM()`** 경유 (고정폭 패딩)
> 2. 국내ETF는 **`pd_grp_no='ETF'`** 필터 (ETN 532건 혼입)
> 3. 공모펀드는 **`GROUP BY std_itm_no`** 또는 `DISTINCT` (같은 펀드가 최대 16행)

### 💡 질의 예시 1: *"국내 상장 ETF 중 최근 1년 수익률이 가장 높은 채권형 ETF 3개를 알려줘."*
```sql
SELECT TRIM(pd_nm) AS pd_nm, du_er_1y, TRIM(cu_fund_mgmt_co) AS mgmt_co, du_last_aum
FROM domestic_etfs
WHERE pd_grp_no = 'ETF'                    -- ETN 532건 제외
  AND TRIM(wu_inv_ast_type) = '채권'
  AND du_er_1y IS NOT NULL                 -- 결측 20.6%
ORDER BY du_er_1y DESC
LIMIT 3;
```
> ❌ **`WHERE wu_inv_ast_type LIKE '%채권%'` 만 쓰면 Top 3가 전부 ETN(메리츠 인버스 국채)으로 나옵니다.**
> 채권형 261건 중 79건(30%)이 ETN입니다.

### 💡 질의 예시 2: *"위험등급 1등급인 공모펀드 중 1년 수익률 상위 5개 종목은?"*
```sql
SELECT TRIM(itm_nm) AS itm_nm, MAX(fd_yr1_ern_r) AS er_1y, MAX(fd_nast_suma) AS aum
FROM public_funds
WHERE zrin_fd_ivst_risk_gcd = 1            -- REAL 컬럼 (1~6, 결측 19.3%)
  AND fd_yr1_ern_r IS NOT NULL             -- 결측 32.6%
GROUP BY std_itm_no                        -- 같은 펀드가 속성코드별로 최대 16행
ORDER BY er_1y DESC
LIMIT 5;
```
> ❌ **`GROUP BY` 없이 실행하면 상위 5개가 전부 동일한 펀드 1개로 채워집니다.** (실행 확인함)

> 🔎 **수익률 이상치 주의:** 국내ETF `du_er_1y` 최대값이 **2,738.95%**, 공모펀드 `fd_yr1_ern_r` 최대값이
> **975.1%** 입니다 (200% 초과 펀드 3,537행). 레버리지 상품이라도 비현실적인 값이라 **단위·데이터 오류 가능성**이
> 있습니다. Top-N 질의에서 이 값들이 1위로 올라오므로, EDA 담당자가 원본 schema의 단위 정의와 대조해
> 이상치 처리 방침을 정해야 합니다.

---

## 👥 5. 팀원 Git 협업 가이드

저장소 크기가 커지는 것을 방지하기 위해 `.db` 바이너리 대신 구축 스크립트(`scripts/build_db.py`)를 Git으로 관리합니다.

팀원분들은 `git pull` 후 아래 명령어를 터미널에서 **단 한 번 실행**하시면 본인 로컬 환경에 동일한 SQLite DB가 자동 구축됩니다:

```bash
# 가상환경 활성화 후 실행
python scripts/build_db.py
```
