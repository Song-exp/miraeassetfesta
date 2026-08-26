# ⚠️ 국내ETF 분류축(axis) 불일치 — 주최측 문의용 근거

> **목적:** schema 엑셀 `Sheet2_Sample` 의 주최측 `axis_*` 정답값이 상품명·데이터 컬럼과
> 불일치하는 케이스 정리. **디스코드/Q&A 문의 근거자료.**
> 근거: `PREF01N001_국내ETF마스터_schema.xlsx` Sheet2_Sample (샘플 100건) ↔ DB 실측.

---

## 요약

axis 7축 중 **5축은 데이터 컬럼으로 90~100% 유도 가능**하나, 아래 2축은 주최 정답이
상품명·자산군 컬럼과 상충하여 **규칙으로 유도 불가** (최대 87~92%).

| 축 | 최고 정확도 | 상태 |
| :--- | :---: | :--- |
| strategy / leverageType / distributionType | 100% | ✅ 확정 |
| replicationMethod | 99% | ✅ |
| region | 94% | ✅ |
| **assetType** | 92% | 🔴 아래 §1 |
| **underlyingScope** | 87% | 🔴 아래 §2 |

---

## 1. `axis_assetType` 불일치 — 자산군이 상품명과 반대

우리 규칙: `wu_inv_ast_type`(투자자산군 컬럼) → assetType 매핑.
아래는 **컬럼·상품명과 주최 정답이 다른** 케이스.

### 🔴 유형 A: 국고채인데 "Equity(주식)"

| 상품명 | 자산군 컬럼 | 우리 판정 | 주최 axis 정답 |
| :--- | :--- | :--- | :--- |
| KB RISE KIS국고채30년Enhanced | 채권 | Bond | **Equity** |
| 한국투자 ACE 국고채10년 | 채권 | Bond | **Equity** |
| 삼성 KODEX 국고채권 | 채권 | Bond | **Equity** |
| 키움 KIWOOM 10년국고채 | 채권 | Bond | **Equity** |

> 상품명에 `국고채`·`[채권]`이 명시돼 있고 자산군 컬럼도 `채권`인데 정답은 `Equity`.

### 🔴 유형 B: 단기채권인데 "MoneyMarket"

| 상품명 | 자산군 컬럼 | 우리 판정 | 주최 axis 정답 |
| :--- | :--- | :--- | :--- |
| 삼성 KODEX 머니마켓액티브 | 채권 | Bond | **MoneyMarket** |
| 삼성 KODEX 단기채권PLUS | 채권 | Bond | **MoneyMarket** |
| TIGER 단기통안채 | 채권 | Bond | **MoneyMarket** |

### 🔴 유형 C: 인프라(주식)인데 "RealEstate"

| 상품명 | 자산군 컬럼 | 우리 판정 | 주최 axis 정답 |
| :--- | :--- | :--- | :--- |
| KODEX 미국AI전력핵심인프라 | 주식 | Equity | **RealEstate** |
| KB RISE 네트워크인프라 | 주식 | Equity | **RealEstate** |

### 🔴 유형 D: 천연가스 선물(원자재)인데 "Equity"

| 상품명 | 자산군 컬럼 | 우리 판정 | 주최 axis 정답 |
| :--- | :--- | :--- | :--- |
| 삼성 인버스 2X 천연가스 선물 | 원자재 | Commodity | **Equity** |

---

## 2. `axis_underlyingScope` 불일치 — 상품명과 반대

우리 규칙: 상품명 기초자산 키워드(대표지수/단일종목/섹터).

| 상품명 | 우리 판정 | 주최 axis 정답 | 이상한 점 |
| :--- | :--- | :--- | :--- |
| KODEX SK하이닉스**단일종목**레버리지 | SingleStock | **SectorTheme** | '단일종목'인데 섹터 |
| TIGER **반도체TOP10** | SectorTheme | **MarketRepresentative** | 섹터인데 시장대표 |
| KB RISE 삼성전자SK하이닉스채권혼합50 | SectorTheme | **SingleStock** | 2종목인데 단일종목 |
| TIGER 미국배당다우존스 | SectorTheme | **MarketRepresentative** | |
| KODEX 국고채권 | MarketRepresentative | **SectorTheme** | |

> `pd_sect_cd=8`(단일종목ETF)로 SingleStock 유도 시도 → 오히려 87→83% 하락(불일치 다수).

---

## 3. 시도한 유도 방법 (전부 실패)

| 방법 | assetType | underlyingScope |
| :--- | :---: | :---: |
| 데이터 컬럼(wu_inv_ast_type) 매핑 | 92% | — |
| 상품명 키워드 | 92% | 87% |
| legacy_leaf 계층 파싱 | — | 76%(하락) |
| pd_sect_cd 코드 | — | 83%(하락) |

→ **주최 기준이 상품명·자산군 컬럼·계층 어느 것과도 일관되지 않음. 사람 손 주관 분류로 추정.**

---

## 3.5 🔬 컬럼 밀림(정답지 버그) 가설 — **기각** (2026-08-21 재검증)

국고채 ETF의 assetType=Equity 가 정답지 컬럼 밀림 오류인지 전체 축을 대조:

| 국고채 ETF 4건 | assetType | region | strategy | replication | leverageType | underlyingScope | distribution |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 전부 동일 | 🔴 **Equity** | Domestic ✅ | Passive ✅ | Physical ✅ | Standard ✅ | SectorTheme | Distributing ✅ |

→ **assetType 만 이상하고 나머지 6축은 전부 정상** = 값이 밀린 게 아님. **4개 운용사 국고채가 전부 Equity = 일관된 의도적 라벨링**(오타·랜덤 아님). 기준이 opaque 할 뿐, 정답지 버그는 아니다.

> 검토한 가설: "ETF는 법적으로 지분증권이라 Equity" → 그럼 전 ETF가 Equity여야 하나 단기채권은 MoneyMarket 이라 기각. **이유 불명 확정 → 주최 확인 필수.**

---

## 4. 📮 주최측 문의사항 (디스코드)

1. **axis_assetType 기준:** 국고채 ETF가 `Equity`, 단기채권이 `MoneyMarket` 으로 분류된
   기준이 무엇인가요? (자산군 컬럼="채권"과 상충. **정답지 컬럼밀림 아님 확인** — 나머지 6축 정상)
2. **평가 채점:** 평가 시 이 `axis_*` 값 기준으로 채점하나요, 참가팀 자체 분류도 인정되나요?
3. **axis_underlyingScope 유도 기준:** 상품명('단일종목' 등)과 다르게 분류된 근거를
   알 수 있을까요?

> 답변에 따라 온톨로지 assetType/underlyingScope 정의 방향 확정 (주최기준 채택 vs 자체정의).
