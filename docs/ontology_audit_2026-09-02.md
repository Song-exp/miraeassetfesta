# 온톨로지 전수조사 — ETF 몫 (2026-09-02 · 병철)

> **왜** — 서현 제안: "세부사항 고치다 보면 큰 대분류가 망가지기도 한다. yaml 규칙을 훑고,
> 데이터 분류가 이상한 게 없는지 전수조사하자." 방법: DB distinct ↔ kg_alias 커버리지 전 컬럼 대조
> + 대분류(자산군·지역·그룹) vs 상품명 교차 검사. 전부 로컬 실측(HCX 0콜).

## ① 커버리지 — 건강함 (사실상 100%)

| 테이블 | KG 매핑 컬럼 | 상태 |
| :-- | :-: | :-- |
| domestic_etfs | 11개 | 전 컬럼 DB고유값 = KG수록값 (고아 3건 = 아래 쓰레기값뿐) |
| overseas_etfs | 5개 | 동일 (지수 2건 미세 누락 — 플레이스홀더) |

**고아로 남긴 쓰레기값 3종 (KG 무시가 정당— 원천 데이터 결함, DB 는 주최 배포본이라 수정 불가)**
- `cu_fund_mgmt_co = '.'` 1행 (BNK BNK27-12특수채액티브) — 운용사별 집계에서 '.' 1건이 뜰 수 있음
- `pd_curr_cd = 'CURR_CD_000'` 1행 · `ref_base_index = 'Index is not available on Lipper Database'` 1행

## ② 대분류 vs 상품명 교차 — 🔴 지역 오분류 발견 → 규칙으로 방어

| 검사 | 결과 |
| :-- | :-- |
| 자산군=주식 ↔ 이름 채권 | ✅ 0건 |
| ETF/ETN 그룹 혼입 | ✅ 0건 |
| 자산군=채권 ↔ 이름 주식 | 🟡 2건 — TIGER 우선주 · RISE 미국고정배당우선증권 (우선주=하이브리드, 원천 판단 존중) |
| **지역 ↔ 이름** | 🔴 **미국 28건 · 중국 15건 오분류** |

실례: `TIGER 미국S&P500선물(H)` → rgn=**국내** · `TIGER 차이나항셍30` → rgn=**국내** ·
`TIGER 차이나CSI300` → rgn=**이머징/브릭스**. `wu_inv_rgn` 단독 필터는 이들을 누락시킨다.

**처방 (query_rules.지역질의_합집합 신설)** — `(wu_inv_rgn='미국' OR ref_geo_focus='United States of America')`
합집합: 466→494건, 오분류 28건 복구. 🔴 상품명 LIKE 는 금지 — '미국달러선물' 9종은 환율 상품(오탐).
잔존 한계: `TIGER 중국소비테마` 는 rgn=아시아·geo=Korea 로 **양쪽 다** 오분류 — 컬럼으로는 복구 불가(기록만).

## ③ 빌더 V1 경고 17건 — 전부 채권·통화 (서현 몫 전달)

`build_ontology.py` 실행 시 죽은 alias 경고: `credit_grade.yaml` BB+·B0·CCC·CC0·C (DB distinct 에 없는 등급),
`currency.yaml` USD·JPY·EUR (domestic_bonds.curr_cd 에 없음). 의도된 여유분일 수 있으니 서현 판단 필요.

## ④ 결론

큰 그림은 안 망가져 있다 — 커버리지 100%·자산군/그룹 정합. 유일한 구조 결함은 **원천 지역 오분류**였고
규칙으로 방어했다. yaml 규칙끼리의 모순은 트리거 회귀 테스트(`test_triggers_*`·`test_paraphrases_*`)가 담장.
