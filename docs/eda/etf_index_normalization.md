# 🧭 지수(벤치마크) 정규화 — ETF↔펀드↔해외ETF 교차조인

> **목적:** 같은 지수를 상품군마다 다르게 표기하는 문제를 정규화해 **하나의 지수 노드**로 잇는다.
> 이게 벤치마크 **B안(독립 개체)** 의 실행 — *"S&P500 추종 ETF + 그 지수 벤치마크 펀드"* 교차질의를 가능케 함.
> 산출물: [`ontology/codebooks/index_master.csv`](../../ontology/codebooks/index_master.csv) (94 표기 → 86 base 지수).
> 원천: `data/external/lookups/index_master_draft.csv` (리드 수집, 94종).

---

## 1. 왜 정규화가 필요한가 — 같은 지수, 다른 표기

| 상품군 | S&P500을 이렇게 적음 |
| :--- | :--- |
| 해외ETF | `S&P 500 TR` (335) · `S&P 500 CR` (51) · `S&P 500 NR` (1) |
| 국내ETF | 상품명 `TIGER 미국S&P500` (cu_base_index 89% 결측) |
| 펀드 | `bmrk_nm` 에 `S&P500 지수` 등 |

→ 표기가 다르면 **컴퓨터가 같은 지수인 줄 모름** → 교차질의 반쪽. `base_index` 로 통일.

---

## 2. 정규화 규칙 (`official_name` → `base_index`)

재현 가능한 규칙 (idx_norm2.py):

| # | 규칙 | 예 |
| :-- | :--- | :--- |
| 1 | **수익률 방식** 접미 제거 (TR/CR/NR/PR/GR/ER, ±USD) | `S&P 500 TR`·`CR`·`NR` → `S&P 500` |
| 2 | **배율** 제거 (`150%`·`90%`) | `코스닥150 150%` → `코스닥 150` |
| 3 | **철자 변형** 통일 | `MSCI AC World` → `MSCI ACWI` |
| 4 | 후미 괄호 마커·`Index` 제거 | `MSCI ACWI (Net Return)` → `MSCI ACWI` |
| 5 | **서브지수 수식어는 유지** (섹터·팩터) | `S&P 500 Value`·`Energy`·`Equal Weight` 는 별개 지수 |

**통합 결과 (수익률변형 묶임):**
```
S&P 500          ← S&P 500 Index · S&P 500 Total Return · S&P 500 (Price Return)
MSCI ACWI        ← MSCI ACWI Index · (Net Return) · (Gross/Total Return) · MSCI AC World NR/TR
MSCI Emerging Markets · MSCI World · ICE BofA US 3-Month T-Bill …
```
→ **94 표기 → 86 base 지수.**

---

## 3. 커버리지 — 어디까지 정규화되나

| 상품군 | 지수 행 커버 | 한계 |
| :--- | :--- | :--- |
| **국내ETF** | ✅ **95%** (58행 유효분) | cu_base_index 자체가 89% 결측 → US추종분은 **상품명 유추** 필요 |
| **해외ETF** | 🟡 **35%** (2,933행 중) | distinct 1,731 중 마스터는 **상위 60**만. 긴꼬리 1,671(각 1~8회)는 니치 지수 미수록 |
| 복합식 BM | ❌ 제외 | `MSCI ACWI CR 50% + 종합채권 50%` 류 — 단일지수 아님, 별도 처리 |

> 🔴 **해외 긴꼬리:** S&P500 계열만 74종 서브지수(Value/Energy/Quality/…). 이건 정규화가 아니라
> **개별 지수라 통합 안 됨** (통합하면 오답). 상위 60 = 실사용 빈도 대부분 커버.

---

## 4. 🔵 B안 교차조인 타깃 — 상품군을 잇는 base 지수

`base_index` 가 같으면 ETF·펀드·해외ETF가 **한 지수 노드**에 매달림:

| base 지수 | 국내ETF | 해외ETF | 가능해지는 질의 |
| :--- | :--- | :--- | :--- |
| **MSCI ACWI** | `MSCI ACWI`(6) | `MSCI AC World NR/TR`(20+) | "전세계(ACWI) 추종 상품 국내+해외" |
| **S&P 500** | 상품명 유추 | `S&P 500 TR/CR`(387) | "S&P500 추종 ETF + 벤치마크 펀드" |
| **MSCI Emerging Markets** | `MSCI EM`(1) | `MSCI EM NR`(25) | 신흥국 교차 |
| **코스피 200** | `KOSPI200`(9) | (없음, 미국ETF는 코스피 미추종) | 국내 전용 |

> 주식 base 지수 54종이 교차질의 핵심. **펀드 `bmrk_nm` 도 같은 base로 정규화하면** 3상품군 완전 연결.

---

## 5. 다음 (승격·확장)

| 할 일 | 담당 |
| :--- | :--- |
| 펀드 `bmrk_nm` 을 같은 `base_index` 규칙으로 정규화 → 3상품군 조인 완성 | 펀드팀 협업 |
| 국내ETF US추종분 상품명→지수 유추 (cu_base_index 89% 결측 보완) | ETF |
| 해외 긴꼬리 지수 필요시 확장 (현 상위 60 → 질의 빈발분 추가) | ETF, 후속 |
| confidence=B 11종 재검증 (채권 KIS 지수 등) | 리드/펀드팀 |
| 복합식 BM 분해 규칙 (`A 50%+B 50%` → 2개 지수 연결) | 워크샵 |
