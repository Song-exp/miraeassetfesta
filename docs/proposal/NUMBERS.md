# 📊 제안서 수치 — 단일 출처 (GENERATED)

> `python scripts/gen_proposal_numbers.py` 로 재생성. **제안서 문서는 이 파일만 인용한다.**
> 문서마다 수치를 따로 적으면 데이터 갱신 때 어긋난다 — 8/25 초안이 실제로 그렇게 낡았다.
> 생성 시각 기준 DB: `financial_products.db`

## 1. 마스터 (주최 제공)

| 테이블 | 소스 파일 | 행 | 컬럼 | 버전 | 기준일 |
| :-- | :-- | --: | --: | :-- | :-- |
| `domestic_bonds` | prbd01n001_data.xlsx | 21,882 | 58 | v2_20260824 | 2026-08-22 |
| `domestic_etfs` | pref01n001_data.xlsx | 1,780 | 98 | v2_20260824 | 2026-08-22 |
| `overseas_etfs` | pref02n001_data.xlsx | 6,037 | 49 | v2_20260824 | 2026-08-22 |
| `public_funds` | prfd01n001_data.xlsx | 23,676 | 75 | v2_20260824 | 2026-08-22 |
| **합계** | | **53,375** | | | |

### 상품군 구성

- `domestic_etfs`: ETF 1,235 · ETN 545
- `overseas_etfs`: ETF 5,972 · ETN 65

## 2. 외부 수집 (L2)

| 수집물 | 행 | 커버리지 | 기준일 |
| :-- | --: | :-- | :-- |
| 국내 ETF 구성종목 | 75,859 | ETF 1,160/1,235 (93.9%) | 2026-08-21 |
| 해외 ETF 구성종목 | 906,848 | ETF 1,356/5,972 (22.7%) | 2025-10-31~2026-06-30 (8종) |
| 펀드 구성종목 | 59,206 | — | 행별 `bas_dt` |
| 펀드 웹 페이지 | 10,565 | — | — |

> 🔴 해외 구성종목 보고기준일이 **2025-10-31~2026-06-30 로 8종** — 최대 8개월 시차. 답변에 `report_date` 병기 필수.

## 3. 온톨로지 · 지식그래프

| 항목 | 값 |
| :-- | --: |
| `kg_node` | 41,580 |
| `kg_alias` | 66,592 |
| `kg_edge` | 7,414 |
| `kg_closure` | 9,965 |

### 개체 종류별 노드

| 개체 | 노드 수 |
| :-- | --: |
| Security | 27,996 |
| Fund | 7,584 |
| Index | 3,172 |
| Organization | 2,527 |
| FundAttribute | 179 |
| Region | 60 |
| CreditGrade | 21 |
| Country | 17 |
| AssetClass | 9 |
| Currency | 8 |
| RiskGrade | 7 |

### 제출 ttl 5분할 (규격 p.9)

| 파일 | 줄 |
| :-- | --: |
| `ontology/common.ttl` | 58,967 |
| `ontology/bond_kr.ttl` | 36 |
| `ontology/etf_kr.ttl` | 34 |
| `ontology/etf_gl.ttl` | 21 |
| `ontology/fund_pub.ttl` | 34 |

## 4. 평가셋

- `questions_cross_and_unanswerable.jsonl`: 9문항 (사람 검증 8)
- `questions_domestic_bonds.jsonl`: 36문항 (사람 검증 36)
- `questions_domestic_etfs.jsonl`: 36문항 (사람 검증 31)
- `questions_official_sample.jsonl`: 8문항 (사람 검증 6)
- `questions_overseas_etfs.jsonl`: 28문항 (사람 검증 27)
- `questions_public_funds.jsonl`: 20문항 (사람 검증 0)
- `questions_top_safety_probe.jsonl`: 10문항 (사람 검증 10)

**합계 147문항 · 사람 검증 118건**

