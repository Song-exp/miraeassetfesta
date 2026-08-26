# 📁 `data/` · `1.금융상품/` — 데이터 설명서

> **이 문서가 답하는 것**: 어떤 데이터가 어디에 있고, 어디서 왔고, 무엇이 들어 있고, 어떻게 다시 만드는가.
> 기준: 2026-08-25 · 마스터 기준일 **2026-08-22**(해외 8/23 KST) · 외부자료 발행일 **≤ 2026-08-24**
> 관련: 변화 내역 `DATA_V2_2026-08-24_impact.md` · 수집 카탈로그 `EXTERNAL_DATA.md` · 인수인계 `HANDOFF_2026-08-25.md`
>
> 🔴 **`1.금융상품/` 과 `data/` 는 통째로 gitignore** 입니다. `git pull` 로는 오지 않으므로 드라이브 배포본(`mirae_data_20260825.zip`)을 받거나 §6 재현 절차로 직접 만드세요.

---

## 0. 전체 구조 한눈에

```
pj/mirae/
├─ 1.금융상품/                          주최 제공 원본 (Excel, 손대지 않음)
│  ├─ prbd01n001_data.xlsx / _schema.xlsx      국내채권
│  ├─ pref01n001_data.xlsx / _schema.xlsx      국내ETF
│  ├─ pref02n001_data.xlsx / _schema.xlsx      해외ETF
│  ├─ prfd01n001_data.xlsx / _schema.xlsx      공모펀드
│  └─ _v1_20260711/                     1차(7/11) 8파일 — 폐기됐으나 비교용 보관
│
└─ data/
   ├─ financial_products.db             🔵 정본 DB (263MB) — 아래 §2
   ├─ financial_products.v1_20260711.db    1차 DB 백업 (112MB, 참조용)
   ├─ kg_coverage_report.md             축별 매핑률 (빌드마다 자동 갱신)
   └─ external/                         외부 수집물 (마스터에 없는 사실)
      ├─ holdings/                      국내 ETF 구성종목 (7/10 · 8/21 두 스냅샷)
      ├─ holdings_overseas/             해외 구성종목 1차 수집 (186 ETF)
      ├─ holdings_overseas_20260824/    해외 구성종목 확장 수집 (1,356 ETF) 🆕
      ├─ lookups/                       코드북·규칙 원천 14종
      └─ miraeasset_web/                미래에셋증권 웹 크롤 (설명서 PDF·펀드 페이지, ~3.4GB)
```

**데이터 3계층** (충돌 시 우선순위):

| 계층 | 내용 | 충돌 시 |
| :-- | :-- | :-- |
| **L0 마스터** | `1.금융상품/` → DB 마스터 4테이블 | **항상 우선** (주최 규칙) |
| **L1 판정** | `ontology/` yaml·코드북 → `kg_*` 테이블 (git 추적) | 마스터 값을 바꾸지 않음. 해석·배제만 |
| **L2 외부** | `data/external/` → `ext_*` 테이블 | 마스터가 NULL 일 때만. 출처·기준일 병기 |

---

## 1. `1.금융상품/` — 주최 제공 원본

| 파일 | 행 × 열 | 테이블 ID | 비고 |
| :-- | --: | :-- | :-- |
| `prbd01n001_data.xlsx` | 21,882 × 58 | PRBD01N001 국내채권마스터 | PK 복합(`pd_no`+시장+기준일+`info_seq`) |
| `pref01n001_data.xlsx` | 1,780 × 98 | PREF01N001 국내ETF마스터 | ETF 1,235 + **ETN 545 혼입** |
| `pref02n001_data.xlsx` | 6,037 × 49 | PREF02N001 해외ETF마스터 | 전부 USD·미국 상장 |
| `prfd01n001_data.xlsx` | 23,676 × 75 | PRFD01N001 공모펀드마스터 | `itm_no` 가 행 단위 PK · **사모 8,960행 유입** |
| `*_schema.xlsx` × 4 | — | 컬럼 정의 | 순번/컬럼명/데이터타입/Nullable/컬럼코멘트 5열 → `schema_metadata` 로 적재 |

- 1차(7/11)본은 주최가 **정합성·코드 이슈로 폐기** → `_v1_20260711/` 에 보관만. 두 배포본은 컬럼 구성이 달라(채권 40→58, ETF 73→98, 펀드 45→75) **섞어 쓰면 안 됩니다.**
- 원본은 절대 수정하지 않습니다. 모든 가공은 `scripts/build_db.py` 를 통해서만.

---

## 2. `data/financial_products.db` — 정본 DB (263MB · 인덱스 47)

`python scripts/build_db.py` + `load_external_*` + `build_ontology.py` 로 생성. **14 테이블**:

### 2-1. 마스터 4 (L0 — 주최 원본 그대로)

| 테이블 | 행 | 열 | 원본 | 기준일 |
| :-- | --: | --: | :-- | :-- |
| `domestic_bonds` | 21,882 | 58 | prbd01n001_data.xlsx | 2026-08-22 |
| `domestic_etfs` | 1,780 | 98 | pref01n001_data.xlsx | 2026-08-22 |
| `overseas_etfs` | 6,037 | 49 | pref02n001_data.xlsx | 2026-08-22 |
| `public_funds` | 23,676 | 75 | prfd01n001_data.xlsx | 2026-08-22 |

> 컬럼명은 원본 그대로 **전부 소문자**(1차는 채권만 대문자였음). SQLite 는 컬럼명 대소문자를 구분하지 않습니다.
> 선행 0 보존 컬럼 15종(`or_co_xtn_itt_cd` `pd_ticker` `exrt_grte_ern_r_tcd` 등)은 문자열로 적재 — 코드북 조인 키이므로 숫자 추론 금지.

### 2-2. 외부 보강 4 (L2 — `ext_*`)

| 테이블 | 행 | 조인 키 | 원천 | 기준일 |
| :-- | --: | :-- | :-- | :-- |
| `ext_etf_holdings` | 75,859 | `etf_code` = `domestic_etfs.pd_itm_no` | FunETF 경유 KRX/코스콤 | **2026-08-21** |
| `ext_ovs_etf_holdings` | 906,848 | `isin` = `overseas_etfs.pd_isin_cd` | SEC EDGAR NPORT-P | ETF별 3/31~6/30 |
| `ext_fund_holdings` | 59,206 | `grp` = `public_funds.mtco_itm_no` | 미래에셋증권 웹 | 행별 `bas_dt` |
| `ext_fund_page` | 10,565 | `itm_no` = `public_funds.itm_no` | 미래에셋증권 웹 | 2026-08-18 관측 |

> 🔴 **상품→종목(holds) 관계는 `kg_edge` 가 아니라 이 테이블들이 edge 입니다** (행 100만). 플래너는 `kg_alias` 로 종목 키를 찾아 여기에 조인합니다.
> SQL 가드(`src/runtime/pipeline.py validate_sql`)는 `ext_*` 를 **마스터와 함께 쓸 때만** 허용합니다(단독 조회 금지).
> 기준일이 마스터(8/22)와 다르므로 답변에 `as_of`/`report_date` 병기가 규칙입니다.

### 2-3. 지식그래프 4 (L1 — `kg_*`, `build_ontology.py` 가 yaml 에서 생성)

| 테이블 | 행 | 내용 |
| :-- | --: | :-- |
| `kg_node` | 39,676 | 개체 9종 — Security 26,271 · Fund 7,600 · Index 3,172 · Organization 2,530 · Region 58 · CreditGrade 21 · AssetClass 9 · Currency 8 · RiskGrade 7 |
| `kg_alias` | 62,557 | 노드 ↔ (테이블, 컬럼, 원시값). "어느 컬럼의 어떤 값이 이 개체인가" |
| `kg_edge` | 7,414 | `hasAssetClass` 3,151 · `coversRegion` 2,556 · `feedsInto` 1,704 · `subsidiaryOf` 3 — **전부 `source: rule`(추정)** → 답변에 "추정" 병기 |
| `kg_closure` | 9,917 | 계층 조상 전개 (지수 패밀리·지역 계층·신용등급 밴드) — 런타임 비용 0 |

### 2-4. 메타 2

| 테이블 | 행 | 내용 |
| :-- | --: | :-- |
| `schema_metadata` | 280 | 컬럼별 한글명·데이터타입·Nullable (주최 schema.xlsx 원문) |
| `build_info` | 4 | 테이블별 소스 파일·행수·열수·`data_version=v2_20260824`·`as_of=2026-08-22` — **DB 가 어느 배포본인지 확인하는 곳** |

```sql
-- 내 DB 가 2차인지 확인
SELECT * FROM build_info;
```

---

## 3. `data/external/holdings*` — ETF 구성종목 (교차질의의 핵심 재료)

### 3-1. `holdings/` — 국내

| 파일 | 행 | 내용 |
| :-- | --: | :-- |
| `domestic_holdings_20260821.csv` 🆕 | 75,859 | **8/21 스냅샷** · ETF 1,160/1,235(93.9%) · 오류 0 |
| `fetch_log_20260821.csv` | 1,780 | 코드별 상태 — **ETN 545 전건 "미제공"**(구조상 정상, 답변 근거) |
| `domestic_holdings_20260710.csv` | 75,081 | 1차 7/10 스냅샷 (비교·회귀용 보존) |
| `SOURCES.md` | — | 수집 방법·검증 |

컬럼: `etf_code, etf_name, rank, ticker, constituent, weight_pct, quantity, as_of`

### 3-2. `holdings_overseas_20260824/` — 해외 (확장) 🆕

| 파일 | 행 | 내용 |
| :-- | --: | :-- |
| `overseas_holdings.csv` | 906,848 | **1,356 ETF** — 종목수 커버리지 22.7%, **AUM 가중 88.6%** |
| `ticker_series_map.csv` | 1,500 | 티커 ↔ SEC seriesId ↔ ISIN (매칭 90.9%) |
| `fetch_log.csv` | — | ETF별 결과 (실패 13 = NPORT-P 미제출) |

컬럼: `etf_ticker, seriesId, report_date, rank, holding_name, cusip, lei, pct_val, balance, accession, isin`

- 보고기준일 분포: 4/30 443 · 5/31 389 · 3/31 352 · **6/30 94** (6/30분은 제출기한 8/29 전이라 일부만 — 규칙상 정상)
- `holdings_overseas/`(기존 186종본)는 티커 병합 시 보충용으로 남겨 둡니다.

### 3-3. 이름 매칭 함정 (Security 노드가 필요한 이유)

| 소스 | 키 | 삼성전자 표기 | 문제 |
| :-- | :-- | :-- | :-- |
| 국내 | 티커 `005930` | '삼성전자' | 깨끗 |
| 해외 | cusip / **LEI** | 'SAMSUNG ELECTRONICS CO LTD', 'SAMSUNG ELECTRONICS GDR REGS' | `LIKE '%Samsung Elec%'` 가 **삼성전기**('SAMSUNG ELECTRO-MECHANICS')까지 잡음 |
| 펀드 | ISIN | '삼성전자' 외 'KODEX 삼성전자단일종목레버리지', '2026-06 삼성전자개별선물' | ETF·선물이 종목명으로 섞임 (`asset_type` 로 분리) |

→ 이름 LIKE 로 풀지 말고 **`kg_alias` 에서 종목 노드를 찾아 조인**하세요. 정본은 `ontology/codebooks/security_alias_manual.csv` 18종.

---

## 4. `data/external/lookups/` — 코드북·규칙 원천 14종

| 파일 | 내용 |
| :-- | :-- |
| `credit_grade_scale.csv` | 신용등급 서열 19단계·투자/투기 경계 → `shared/credit_grade.yaml` 노드화 |
| `collateral_type_map.csv` · `issuer_industry_map.csv` · `issuer_industry_top200.csv` | 채권 담보구분·발행사 업종 (edge 후보, 아직 미연결) |
| `bond_tax_rules.md` · `bond_glossary.md` · `bond_issuer_background.md` · `ktb_individual_structure.md` | 채권 세금·용어·발행기관 제도 |
| `fund_facts_from_prospectus.csv` | 간이투자설명서 추출 8,443행 — **보수 단위 ‰ 확정의 근거** |
| `etn_issuers.csv` · `trustee_00160037.md` · `zeroin_methodology.md` · `kofia_fd_ccd_def.md` | ETN 발행사·수탁사·제로인 등급 방법론·협회 분류 |
| `index_master_draft.csv` | 1차 지수 초안 94종 (2차에서 `ref_base_index` 905종으로 대체됨 — 참조용) |

> git 추적되는 확정 코드북은 `ontology/codebooks/` 에 따로 있습니다(운용사 275·속성코드 210·종목 정본 18·지수 override 37 등).

---

## 5. `data/external/miraeasset_web/` — 웹 크롤 원본 (~3.4GB)

| 항목 | 규모 | 용도 |
| :-- | --: | :-- |
| `prospectus/` | 16,946 파일 (PDF+txt) | 간이투자설명서 — 보수·환매 조건 원문 |
| `fund_pages_full.csv` | 10,565 | 펀드 상세 페이지 → `ext_fund_page` |
| `holdings_full.csv` · `holdings_raw.jsonl` | 59,206 | 펀드 구성종목 → `ext_fund_holdings` |
| `asset_manager_audit.csv` | — | 운용사 법인명 관측 (코드북 근거) |
| `crawl.log` · `FULL_CRAWL_DONE.json` | — | 수집 로그·완료 표식 |

용량이 커서 배포 zip 에는 넣지 않습니다. 이미 배포된 기존 폴더를 그대로 두세요.

---

## 6. 재현 절차 — DB 를 직접 만들기

`1.금융상품/`(2차 8파일) + `data/external/` 만 있으면 전부 재생성됩니다. 손으로 만든 산출물은 없습니다.

```bash
python scripts/build_db.py               # 마스터 4테이블 + schema_metadata + build_info
python scripts/load_external_web.py      # ext_fund_page · ext_fund_holdings
python scripts/load_external_holdings.py # ext_etf_holdings · ext_ovs_etf_holdings (최신 스냅샷 자동 선택)
python scripts/gen_shared_auto.py        # shared/index_auto · organization_*_auto
python scripts/gen_security_auto.py      # shared/security_auto
python scripts/gen_fund_structure_auto.py# shared/fund_structure_auto
python scripts/build_ontology.py         # 검증(V1~V7) → ontology.ttl + kg_* + coverage report
python -m pytest tests -q                # 17 passed
python eval/run_gold_check.py            # 문항 63 · gold_sql 45 · 통과 63 · 실패 0
```

- `build_ontology.py` 는 yaml 이 DB 에 없는 컬럼·값을 가리키면 **빌드를 거부**합니다(죽은 alias 검출). 2차 전환 때 이 게이트가 12건의 불일치를 잡았습니다.
- 수집 스크립트(`fetch_etf_holdings.py` · `fetch_overseas_holdings.py`)는 재실행 시 이미 받은 항목을 건너뜁니다. 발행일 ≤ 2026-08-24 를 `assert` 로 강제합니다.

---

## 7. 배포본 — `mirae_data_20260825.zip` (100MB)

드라이브 업로드용. **2026-08-25 에 새로 만들어진 것만** 담았습니다(주최 원본·기존 수집물 제외).

| 포함 | 제외 |
| :-- | :-- |
| `financial_products.db` (263MB) · `kg_coverage_report.md` | `1.금융상품/` (주최 원본, 별도 배포됨) |
| `external/holdings/domestic_holdings_20260821.csv` + 로그 | `financial_products.v1_20260711.db` (1차 백업) |
| `external/holdings_overseas_20260824/` 전체 | `holdings_overseas/`(186종본) · `lookups/` · `miraeasset_web/` (기존 배포분) |
| `SOURCES.md` × 2 · `README_배포_20260825.md` | `domestic_holdings_20260710.csv` (기존) |

압축 해제 위치와 검증 명령은 zip 안 `README_배포_20260825.md` 에 있습니다.

---

## 8. 주의사항 요약

| # | 내용 |
| :-: | :-- |
| 1 | `1.금융상품/`·`data/` 는 **git 제외** — 코드만 pull 하면 DB 가 없어 테스트가 실패합니다 |
| 2 | 1차(7/11)와 2차(8/22) 데이터를 **섞지 마세요**. `build_info` 로 확인 |
| 3 | 선행 0 코드 컬럼은 문자열입니다. `WHERE or_co_xtn_itt_cd = 40010` 같은 숫자 비교 금지 |
| 4 | `ext_*` 는 마스터와 조인할 때만 사용. 기준일이 다르므로 답변에 병기 |
| 5 | `kg_edge` 는 전부 규칙 기반(추정) — 답변에 "추정" 병기 |
| 6 | 펀드 집계 기본 모수는 `sale_yn='판매중' AND prvo_pbff_desc='공모'` (8,969행) |
| 7 | 0·결측은 **의도된 값**(주최 공지) — 채우지 말고 배제하거나 "수록 없음" 으로 응답 |
| 8 | DB 를 직접 수정하지 마세요. 모든 변경은 yaml·스크립트를 고쳐 재생성 |
