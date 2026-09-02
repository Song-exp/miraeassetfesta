# 📖 데이터 사전 — 도메인별 피처·의미·결측 판정

> DB 에 적재된 **모든 컬럼**(마스터 280 + 외부 50)의 뜻, 결측이 무슨 의미인지,
> 우리가 어떻게 판정했고 그 근거가 무엇인지. 외부 데이터(`ext_*`)까지 포함한다.

## 문서

| 문서 | 대상 | 컬럼 |
| :-- | :-- | --: |
| [`bonds.md`](bonds.md) | `domestic_bonds` | 58 |
| [`etf.md`](etf.md) | `domestic_etfs` · `overseas_etfs` · `ext_etf_holdings` · `ext_ovs_etf_holdings` | 98 + 49 + 8 + 11 |
| [`funds.md`](funds.md) | `public_funds` · `ext_fund_holdings` · `ext_fund_page` | 75 + 11 + 20 |

각 문서 구성: **§0 결측 원칙** → 테이블별 **질의 규칙(`query_rules`)** → **결측 상위 15** →
**⚠️ 판정↔실측 불일치** → **컬럼 사전(전 컬럼)** → **🔲 미판정 컬럼**.

## 판정 커버리지 (2026-08-26 기준)

| 테이블 | 판정 완료 | 미판정 |
| :-- | :-- | --: |
| `domestic_bonds` | **58/58** ✅ | 0 |
| `public_funds` | 69/75 | 6 |
| `domestic_etfs` | 57/98 | **41** |
| `overseas_etfs` | 19/49 | **30** |

🔲 미판정 = 주최가 준 한글명과 실측만 있고 **결측 사유·답변 정책이 없는** 상태다.
질의에 쓰면 안 되며, 이걸 채우는 것이 각 도메인의 남은 작업이다.
**해외ETF 30개·국내ETF 41개**가 가장 큰 공백이다.

## 🔴 손으로 고치지 마세요

세 문서 모두 **생성물**이다. 재생성하면 편집한 내용이 사라진다.

```bash
python scripts/gen_data_dictionary.py            # 3개 전부 (약 30초)
python scripts/gen_data_dictionary.py funds      # 하나만
```

내용을 바꾸려면 **원본**을 고친다.

| 바꾸려는 것 | 고칠 곳 |
| :-- | :-- |
| 마스터 컬럼의 판정 — 결측 사유·단위·답변 정책·함정 | `ontology/enums/<도메인>.yaml` 의 `columns.<컬럼>` |
| 도메인 질의 규칙 | 같은 파일의 `query_rules` |
| 외부(`ext_*`) 컬럼 의미 | `scripts/gen_data_dictionary.py` 의 `EXT_DICT` |
| 컬럼 한글명·타입 | 주최 원본(`*_schema.xlsx`) → `schema_metadata`. **우리가 못 바꾼다** |

`ontology/enums/*.yaml` 을 고치는 것은 문서만 바꾸는 게 아니다 —
`loader.planner_context()` 가 `query_rules`·`normalization` 을 **플래너 프롬프트로 그대로 넘긴다.**
즉 판정을 고치면 답변 동작이 바뀐다.

## 출처

| 층 | 무엇 | 신선도 |
| :-- | :-- | :-- |
| `schema_metadata` | 주최 컬럼 한글명·타입·Nullable (원본 `*_schema.xlsx`) | 2차 (8/22) |
| **라이브 DB 실측** | 결측·0값·distinct·범위·값 분포 | 생성 시점 |
| `ontology/enums/*.yaml` | 사람의 판정 | 2차 |
| `EXT_DICT` | 외부 컬럼 의미 — 적재 스크립트·수집 원천에서 확정 | 2차 |

> ⚠️ `ontology/enums/*.auto.yaml` 은 **쓰지 않는다.** 4개 전부 1차(7/11) 기준이라
> (`profile_table.py` 가 2차 전환 후 재실행되지 않았다) 수치가 죽어 있다.
> `docs/eda/*.md` 의 상세 노트도 마찬가지로 1차 기준이다 — **컬럼 의미 설명은 유효하지만 수치는 죽었다.**

## 관련 문서

| 목적 | 문서 |
| :-- | :-- |
| **규칙이 왜 그렇게 생겼나** — 규칙 12종 · 결함→규칙→실측 근거 | [`../ontology_rules/`](../ontology_rules/README.md) |
| 데이터가 어디에 있나 · DB 14테이블 구조 | [`../DATA_GUIDE_data폴더.md`](../DATA_GUIDE_data폴더.md) |
| 2차 전환이 무엇을 바꿨나 | [`../DATA_V2_2026-08-24_impact.md`](../DATA_V2_2026-08-24_impact.md) |
| 외부 수집 카탈로그·출처 규칙 | [`../EXTERNAL_DATA.md`](../EXTERNAL_DATA.md) |
| 답변 규칙 상위법 (주최 Q&A) | [`../../PROJECT.md`](../../PROJECT.md) §2 · [`../QNA_REVIEW_2026-08-25.md`](../QNA_REVIEW_2026-08-25.md) §3-1 |
| 앞으로 할 일 | [`../WORK_PLAN_2026-08-26.md`](../WORK_PLAN_2026-08-26.md) |
