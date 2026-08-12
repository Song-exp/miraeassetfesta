# EDA 노트북 — 결측 판정 강화 + 기초 통계 절 신설

> 2026-08-12 · 대상: `notebooks/eda_template.ipynb` (우선) → `notebooks/public_funds_eda.ipynb`

## 1. 배경

`notebooks/eda_template.ipynb` 는 63셀 규모로 이미 안전 셋업·헬퍼·구조 검증·결측 판정·엔티티 탐색·질의 생성기를 갖추고 있다. 그러나 요청받은 두 축 — 결측 처리와 기초 통계 — 에 다음 구멍이 있다.

| # | 구멍 | 근거 |
| :-: | :--- | :--- |
| 1 | 결측 도구가 `IS NULL` 만 센다 | `why_missing`·`co_missing` 이 공백문자열·센티넬을 무시. `EDA_GUIDE.md` §8-② 가 경고한 함정과 동일 — *"IS NULL만 세면 해외ETF 기초지수 결측이 0.1%로 보이지만 실제 값 보유는 51.9%"* |
| 2 | 결측 원인 컬럼을 사람이 지정해야 한다 | `why_missing(col, by)` 의 `by` 가 수동. `public_funds_notes.md` D.9(`해당없음` 오판 정정)를 손으로 찾은 과정이 자동화되어 있지 않다 |
| 3 | 기초 통계가 행 단위다 | `overview()` 는 95,619행 기준. 실제 종목은 11,139개(8.6배 중복)이므로 평균·분포·범주 비중이 속성태그 개수로 가중된 값이 된다 |
| 4 | 수치형 분포·이상치를 노트북에서 보지 않는다 | 분위수·이론적 하한 위반이 `.auto.yaml` 안에만 있고 조회 수단이 없다 |

## 2. 설계 원칙 (기존 가이드에서 승계)

1. **채우지 않는다.** 결측은 대치하지 않고 유형을 판정해 라벨링한다 (`EDA_GUIDE.md` §3 🕳️).
2. **정제 DataFrame 을 만들지 않는다.** 규칙은 SQL 조각으로 들고 다니며 원본에 매번 적용한다 (§6). 노트북에서 만든 정제본은 런타임에 전달되지 않고 `gold_sql` 을 어긋나게 한다.
3. **판정은 `ontology/enums/<domain>.yaml` 에 산다.** 노트북은 gitignore 대상이라 여기 적은 것은 전달되지 않는다.
4. **이미 찾은 것을 다시 찾지 않는다.** `profile_table.py` 탐지기가 잡은 것은 재탐지하지 않고 조회만 한다.
5. **사실과 판정을 섞지 않는다.** 결측률은 판정이지 사실이 아니므로 계산 근거를 함께 노출한다.

## 3. 배치

셀 삭제·이동 없음. 기존 셀 3개 교체 + 새 절 삽입.

```
 [1~5]   셋업 · 헬퍼 · overview()          그대로
 [6~11]  🧱 구조 검증 (행의 단위 확정)        그대로   ※ ENTITY_KEY 의 출처
 [12~15] 🔬 원본 대조                       그대로
 [16~25] 🕳️ 결측 판정                      ★ 강화
 [26~27] 1단계 산출물 확인                   그대로
 ──────── ★ 📊 기초 통계 (신설) ────────
 [28~30] 유도 규칙 검증
 [31~ ]  🧬 엔티티 탐색 → §3 → §4           그대로
```

「결측 → 기초 통계」 순서는 노트북 cell 16 이 이미 선언한 논리(*"결측이 무엇인지 모른 채 분포를 보면 그 분포가 왜곡돼 있습니다"*)를 따른 것이다.

## 4. 🕳️ 결측 절 강화

### 4.1 `is_missing(col)` — 결측 정의의 단일 출처

`NULL` + 공백문자열 + `<domain>.yaml` 에 `missing` 으로 선언된 센티넬을 함께 세는 SQL 조각을 반환한다. `not_applicable` 로 선언된 값은 결측에서 **제외**한다. 절의 모든 도구가 이 하나를 쓴다.

- 입력: 컬럼명
- 출력: `WHERE` 에 넣을 수 있는 SQL 불린 표현식 문자열
- 의존: `DECL["columns"][col]["missing_semantics"]`, `missing_reason`

결과적으로 yaml 판정이 결측 계산에 실제로 반영된다 — 선언이 장식이 아니라 동작이 된다.

### 4.2 `miss_scan()` — 전 컬럼 결측 전수 표

컬럼 × {null, 공백, 판정대기 센티넬, 0값} 을 한 DataFrame 으로. `기계결측률`(null+blank)과 `판정후결측률` 두 열을 나란히 두어 판정이 결측률을 얼마나 바꿨는지 보이게 한다.

### 4.3 `explain_missing(col, top=5)` — 원인 컬럼 자동 탐색

나머지 전 컬럼을 후보 기준으로 스캔해 해당 컬럼의 결측을 가장 잘 설명하는 컬럼 상위 N 을 낸다.

- 지표 A — **엇갈림 건수**: 기준 컬럼의 특정 값과 결측이 완전 대응하는가. 0건이면 구조적 결측(`not_applicable`) 유력, 🔴 표시
- 지표 B — **그룹별 결측률 편차**: 최대 − 최소

`why_missing(col, by)` 는 유지하되 `is_missing()` 기반으로 교체한다. `explain_missing` 이 후보를 제시하고 `why_missing` 이 상세를 보는 2단 구성.

검증 기준: `public_funds` 에서 `prvo_fd_desc` → `prvo_pbff_desc`, `exchdg_yn` → `ovrs_fd_desc` 가 상위로 나와야 한다.

### 4.4 `co_missing_matrix()` — 동시결측 덩어리

결측이 있는 컬럼끼리 동시결측 비율 행렬. 같은 데이터 소스에서 온 결측 덩어리를 드러낸다. `co_missing(a, b)` 는 유지하되 `is_missing()` 기반으로 교체.

검증 기준: `fd_yr1_ern_r` ↔ `zrin_fd_ivst_risk_gcd` 가 높은 동시결측으로 잡혀야 한다 (노트 기록: 동시 18,404건, 등급만 결측 12건).

## 5. 📊 기초 통계 절 (신설)

### 5.1 전제 — `ENTITY_KEY`

`DECL["query_rules"]["종목단위"]` 의 `GROUP BY <컬럼>` 에서 파싱하고, 없으면 셀에서 직접 지정한다. 미지정이면 도구는 행 단위만 내고 경고를 출력한다 (다른 트랙이 구조 검증을 아직 안 돌렸을 수 있다).

**정제 DataFrame 을 만들지 않는다.** `GROUP BY` 서브쿼리 SQL 조각으로만 적용한다.

### 5.2 도구

| 도구 | 출력 |
| :--- | :--- |
| `stats_num(cols=None)` | 수치형 전 컬럼 — n / 평균 / std / min · p01 · p25 · p50 · p75 · p99 · max / 0건 / 음수건. **행단위 ‖ 엔티티단위 ‖ 차이배수** |
| `stats_cat(cols=None, top=3)` | 범주형 — distinct / 최빈값 / 상위 N 비중 / 1건짜리 값 개수(오염 후보). **행단위 비중 vs 엔티티단위 비중 차이** |
| `dist(col, bins=20, log=False)` | 단일 컬럼 분포. 텍스트 막대 기본, matplotlib 있으면 그림 |
| `show_outliers(col)` | **재탐지하지 않는다.** `.auto.yaml` 의 `outlier_high` · `wide_range` · `repeated_extreme` · `impossible_rate` 가 잡은 항목을 종목명과 함께 조회 |
| `corr_num(cols=None)` | 엔티티단위 수치형 상관 행렬 |

### 5.3 의존성

matplotlib 미설치. **텍스트 막대로 기본 동작**하게 쓰고 matplotlib 는 `try/except ImportError` 로 optional 처리한다. `requirements-dev.txt` 추가 여부는 별도 판단 — dev 전용이라 제출 Docker 이미지(`requirements.txt`)에는 영향 없다.

## 6. 검증 (DoD)

1. `jupyter nbconvert --execute` 로 두 노트북 **전 셀 실제 실행**, 예외 없이 완주
2. `public_funds_notes.md` 에 이미 기록된 수치가 새 도구에서 **그대로 재현**되는지 대조
   - 행 중복 8.6배 (95,619 / 11,139)
   - `exchdg_yn` 국내 87.7% vs 해외 0.8% 결측 → `explain_missing` 상위
   - `fd_yr1_ern_r` ↔ `zrin_fd_ivst_risk_gcd` 동시결측 18,404건
   - `fd_yr3_ern_r` 최소 −4,381% (KCGI베트남, `KR515303001M`)
3. 재현되지 않으면 도구가 틀린 것으로 본다
4. 읽기 전용 커넥션이 여전히 강제되는지 확인 (쓰기 시도 → 예외)
5. 두 노트북의 차이가 `DOMAIN` 값과 도메인별 실행 코드로만 남는지 확인

## 7. 범위 밖

- `_notes.md` 갱신 — 도구가 새 사실을 내면 그때 별도로
- `public_funds.yaml` 판정 추가 — 새 도구를 돌린 결과를 보고 판단
- 새 탐지기를 `profile_table.py` 에 추가하는 것 — 이 절은 조회 도구까지만
