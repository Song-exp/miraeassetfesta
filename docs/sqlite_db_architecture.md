# 🗄️ SQLite 데이터베이스 아키텍처 및 구축 가이드 (`SQLITE_SETUP.md`)

> **미래에셋 금융상품 마스터 데이터 (약 14.5만 건) SQLite DB 구축 및 조회 스펙 문서**

---

## 1. 프로젝트 DB 개요 및 관리 구조

* **생성 파일 위치**: `data/financial_products.db`
* **자동 변환 스크립트**: `scripts/build_db.py`
* **데이터 원본**: `1.금융상품/` (엑셀 마스터 및 스키마 파일 8종)
* **총 데이터 수량**: **145,393 건** (4개 마스터 데이터 세트 + 1개 메타데이터 테이블)

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
  - `PD_RISK_GCD`: 위험등급 (1~5등급)
  - `ISU_DT` / `MAT_DT`: 발행일 / 만기일
  - `SRFC_IRT`: 표면금리 (%)
  - `BUY_YIELD`: 매수수익률 (%)
  - `AFTER_TAX_YIELD`: 세후수익률 (%)
  - `DUR`: 듀레이션
  - `EVAL_PRICE`: 평가가격

---

### 📊 2) `domestic_etfs` (국내ETF 마스터)
* **레코드 건수**: **1,734 건**
* **원본 파일**: `PREF01N001_국내ETF마스터_20260711_datarows.xlsx`
* **주요 속성**:
  - `pd_itm_no`: ETF 종목코드 (PK)
  - `pd_nm` / `pd_abrv_nm`: 종목명 / 약어명
  - `cu_fund_mgmt_co`: 운용사 (예: 미래에셋자산운용, 삼성자산운용)
  - `cu_base_index`: 기초지수 (예: 코스피 200)
  - `cu_charge_rt`: 총보수요율 (%)
  - `pd_risk_cd`: 위험등급 (1~5등급)
  - `du_er_1y`: 최근 1년 수익률 (%)
  - `du_er_ytd`: YTD (연초 대비) 수익률 (%)
  - `du_last_aum`: 순자산 총액 (AUM)

---

### 📊 3) `overseas_etfs` (해외ETF 마스터)
* **레코드 건수**: **5,646 건**
* **원본 파일**: `PREF02N001_해외ETF마스터_20260711_datarows.xlsx`
* **주요 속성**:
  - `pd_itm_no`: 해외 ETF 티커 / 종목코드
  - `pd_nm`: 종목명
  - `pd_isin_cd`: ISIN 코드
  - `pd_exg_mkt_cd`: 상장시장 (예: NYSE, NASDAQ)
  - `pd_trd_ccy`: 거래통화 (USD 등)
  - `cu_fund_mgmt_co`: 운용사명
  - `cu_charge_rt`: 총보수요율 (%)
  - `du_last_aum`: 순자산 AUM
  - `du_er_1d`: 1일 수익률 (%)

---

### 📊 4) `public_funds` (공모펀드 마스터)
* **레코드 건수**: **95,619 건**
* **원본 파일**: `PRFD01N001_공모펀드마스터_20260711_datarows.xlsx`
* **주요 속성**:
  - `std_itm_no`: 표준코드 (PK)
  - `itm_nm`: 펀드 종목명
  - `or_co_xtn_itt_cd`: 운용사 코드
  - `zrin_fd_ivst_risk_gcd`: 위험등급
  - `fd_yr1_ern_r`: 최근 1년 수익률 (%)
  - `fd_mm3_ern_r`: 3개월 수익률 (%)
  - `fd_nast_suma`: 순자산 총액 (AUM)
  - `exchdg_yn`: 환헤지 여부 (Y/N)

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

### 💡 질의 예시 1: *"국내 상장 ETF 중 최근 1년 수익률이 가장 높은 채권형 ETF 3개를 알려줘."*
```sql
SELECT pd_nm, du_er_1y, cu_fund_mgmt_co, du_last_aum
FROM domestic_etfs
WHERE wu_inv_ast_type LIKE '%채권%'
ORDER BY du_er_1y DESC
LIMIT 3;
```

### 💡 질의 예시 2: *"위험등급 1등급인 공모펀드 중 1년 수익률 상위 5개 종목은?"*
```sql
SELECT itm_nm, fd_yr1_ern_r, fd_nast_suma
FROM public_funds
WHERE zrin_fd_ivst_risk_gcd = '1'
ORDER BY fd_yr1_ern_r DESC
LIMIT 5;
```

---

## 👥 5. 팀원 Git 협업 가이드

저장소 크기가 커지는 것을 방지하기 위해 `.db` 바이너리 대신 구축 스크립트(`scripts/build_db.py`)를 Git으로 관리합니다.

팀원분들은 `git pull` 후 아래 명령어를 터미널에서 **단 한 번 실행**하시면 본인 로컬 환경에 동일한 SQLite DB가 자동 구축됩니다:

```bash
# 가상환경 활성화 후 실행
python scripts/build_db.py
```
