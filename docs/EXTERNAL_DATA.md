# 📦 외부 수집 데이터 카탈로그 — 2026-08-20 기준

> **이 문서의 역할** — `data/` 전체가 gitignore 라 수집 실물은 저장소에 없다. 이 카탈로그가 "무엇이,
> 어디서, 왜 수집됐고, 어떻게 재생성하는지"의 단일 참조다. **실물 공유는 드라이브**(하단 §업로드 가이드).
>
> 📁 폴더 구조·DB 테이블·재현 절차는 `DATA_GUIDE_data폴더.md` 참조.
>
> **공통 원칙** — ① 외부 자료는 **2026-08-24까지 발행분** 또는 불변 지식(코드북)만 (🔄 2026-08-25: 주최 8/24 공지로 7/11 → 8/24 완화. 마스터 기준일은 8/22. 기수집 7/10 스냅샷은 유효하나 구식 — 재수집 판단은 `DATA_V2_2026-08-24_impact.md` §4) ② 마스터와 상충 시
> 마스터 우선 ③ 답변 시 `retrieved_context` 에 출처 구분 표기 ④ 모든 파일에 원천 URL·as_of 기재.

---


> [!NOTE]
> **DB 적재 현황 (2026-08-25)** — `scripts/load_external_holdings.py` 로 구성종목 2종을 DB `ext_*` 테이블로 올렸다 (교차질의 재료).
>
> | 테이블 | 행 | 조인 키 | 마스터 커버리지 | 기준일 |
> | :-- | --: | :-- | :-- | :-- |
> | `ext_etf_holdings` | 75,859 | `etf_code` = `domestic_etfs.pd_itm_no` | ETF 1,160/1,235 (93.9%) | **2026-08-21** (재수집, 7/10본 보존) |
> | `ext_ovs_etf_holdings` | 906,848 | `isin` = `overseas_etfs.pd_isin_cd` (100% 매칭) | ETF 1,356/5,972 (22.7% · **AUM 가중 88.6%**) | 3/31~6/30 (ETF별 상이, 6/30 94종) |
> | `ext_fund_holdings` | 59,206 | `grp` = `mtco_itm_no` | (기존) | 행별 `bas_dt` |
> | `ext_fund_page` | 10,565 | `itm_no` | (기존) — 보수 단위 검증(‰) 근거 | 2026-08-18 관측 |
>
> 교차 예시 "삼성전자 보유" 실측(8/25 재수집 후): 국내ETF 246 · 해외ETF 84 · 펀드그룹 941. NVIDIA 보유 해외ETF 342 · 캠브리콘 보유 31. SQL 가드는 `ext_*` 를 마스터와 **함께 쓸 때만** 허용 (`src/runtime/loader.py EXT_TABLES`).
> ✅ 재수집 완료(2026-08-25): 국내 8/21 스냅샷(`holdings/domestic_holdings_20260821.csv`), 해외 AUM 상위 1,500 확장(`holdings_overseas_20260824/`, 1,288+60 재시도 = 1,356 · 미제출 13). 6/30 NPORT-P 는 제출기한(8/29) 전이라 94종만 확보 — 규칙(발행 ≤ 8/24)상 정상.

## 1. 구성종목 (Holdings) — 마스터에 컬럼 자체가 없던 값

> 🔧 **2026-08-30 갱신** — 아래 표가 오래도록 **7/10 · 3/31~5/31 본**(1차 제약 시절)을 적고 있어
> 상단 `[!NOTE]` DB 적재 현황(8/21본)과 한 문서 안에서 수치가 두 벌이었다. **DB 에 실제로 들어간 정본 기준으로 교체**했다.
> 옛 파일(`domestic_holdings_20260710.csv` · `holdings_overseas/`)은 비교용으로 **보존**한다 — 삭제 금지.
> 근거: 주최 8/24 공지 *"공시 및 기타 시장데이터는 금일 기준(~26.08.24 까지) 발행된 자료 사용가능"*.


| 데이터 | 위치 (`data/external/`) | 규모 | 원천 소스 | 의미 — 무엇이 열리나 |
| :--- | :--- | :--- | :--- | :--- |
| **국내 ETF·ETN 구성종목** | `holdings/domestic_holdings_20260821.csv` + `fetch_log_20260821.csv` **(정본)** · 7/10본 보존 | **75,859행** · **판매중 ETF 1,160/1,160 (100%)** | KRX/코스콤/제로인 원천 — FunETF 공개 API 경유 (`funetf.co.kr`, 기준일 `etfPdfYmd=20260821`). **8/24 공지 기준 적합** | 주최 예시질의 3번(캠브리콘 편입)·5번(에코프로 자회사) — "○○ 편입 ETF" 전반. ETN 532 전건 "미제공" 로그 = "ETN 은 구성종목이 없다" 답변의 실측 근거 |
| **해외 ETF 구성종목** | `holdings_overseas_20260824/` **(정본)** · `holdings_overseas/` 보존 | **906,848행** · **1,356 ETF** (AUM 상위 1,500 확장 · AUM 가중 88.6%) | **SEC EDGAR NPORT-P** 공시 (`data.sec.gov`) — 티커→seriesId 는 SEC 공식 `company_tickers_mf.json`. 보고기준일 **2025-10-31 ~ 2026-06-30**, 발행일 ≤ 8/24 | 해외판 "○○ 편입 ETF" (NVIDIA 편입 55개 실동작). 🔵 CIK 운용사 단위 문제 해소 실증. ⚠️ ETF별 기준일 이질 — 답변 시 report_date 병기 |

방법·스키마·한계: 각 폴더의 `SOURCES.md`. 재생성: `scripts/fetch_etf_holdings.py` · `scripts/fetch_overseas_holdings.py` (이어받기 지원).

## 2. 투자설명서 (비정형 코퍼스 + 구조 사실)

| 데이터 | 위치 | 규모 | 원천 소스 | 의미 |
| :--- | :--- | :--- | :--- | :--- |
| **간이투자설명서(R3) 벌크** | `miraeasset_web/prospectus/*.pdf`(+추출 `.txt`) + `prospectus_bulk_log.csv` | 판매중 **8,443/8,445 클래스 (99.98%)** · 약 3.4GB | funddoctor 결정적 URL (`file.funddoctor.co.kr` — memb_cd=7070·file_gb=R3). 발행 시점 불변 문서 | ④ 클래스별 보수 · ⑥ 환매 조건 · ⑦ `[Parsing]` 소스코드 채점용 비정형 코퍼스 (예시질의 2번 계열) |
| **설명서 구조 사실 추출본** | `lookups/fund_facts_from_prospectus.csv` | 8,443행 | 위 R3 텍스트에서 전수 추출 | 🔑 **축 승격의 근거**: `issuanceType` 확정(fd_set_pcd 반례 0) · `redemptionType` 부분 복구(판매중 전건 개방형) · 모자형 6,960(M109 재현율 83.3% 보완) · **총보수 8,227건**(근사 — 출처 병기 필수). 사용 규칙: `public_funds.yaml` `external_facts:` 절 |
| 투자설명서 표적분 (기수집 P2) | `miraeasset_web/prospectus/` 내 186파일 (R2 포함) | 186파일 | 동일 | 수탁사 법인명 16/18 · 단위형 30/30 · 국민성장 R2 |

재생성: `scripts/fetch_prospectus_bulk.py` (로그 기준 이어받기).

## 3. 미래에셋 웹 수집 (기존 트랙, 커밋 70df09f)

| 데이터 | 위치 | 규모 | 원천 소스 | 의미 |
| :--- | :--- | :--- | :--- | :--- |
| 펀드 상세 페이지 (불변 사실) | DB `ext_fund_page` (원본 `miraeasset_web/`) | 10,565행 | 미래에셋증권 웹 (2026-08-18 수집 — 불변 사실만: 설정일·법인명·모펀드명·단위형) | 운용사 67/67 법인명 · 설정일(접미결측 판정 A 승격 재료) · `fd_nast_suma=0` 센티넬 확정(298/298) |
| 펀드 구성종목 | DB `ext_fund_holdings` | 59,206행 | 동일 (펀드묶음 대표 1클래스, `bas_dt` 행별 필터 필수) | 펀드판 편입종목 질의 · 모자관계 |

재생성: `scripts/crawl_miraeasset_full.py` → `scripts/load_external_web.py` (멱등 — build_db 재실행 후 필수).

## 4. 코드북·조회 (불변 지식 — `lookups/`)

| 파일 | 내용 | 원천 소스 | 의미 |
| :--- | :--- | :--- | :--- |
| `credit_grade_scale.csv` | 신용등급 20종(DB 표기) 서열·투자/투기 경계·정의 문구 | 한국기업평가 등급정의(한신평 교차) | "AAA>AA+" 서열을 상식 주입 → 출처 있는 근거로 (yaml §11 #5·#6 해소) |
| `bond_tax_rules.md` | 이자소득 15.4%·매매차익 비과세·개인국채 분리과세(조특법 §91의23)·법인 과세 | 소득세법·조특법·국세청 | 세후 수익률 답변 근거 — 데이터의 ×0.846 산식 정합 확인 |
| `bond_glossary.md` | 채권 용어 17종 정의(확인 14) — FRN·STRIPS·CB·코코·유동화 등 | 한국은행 경제금융용어 700선·기재부 | "선순위가 뭐예요?" 류 개념 질의 (플래그와 1:1) |
| `bond_issuer_background.md` | 발행기관 제도 배경 — 산은·기은 법정 손실보전, 한전은 없음 등 보증 성격 차등 | 각 설립법 현행 조문 | 발행사 노드 설명 속성 · "한전 채권 왜 안전해?" |
| `ktb_individual_structure.md` | 개인투자용국채: 미래에셋 단독 판매대행·유통시장 부존재 | 기재부 국채시장·KDI | "49건 전부 장외" 완전 설명 — 추정 🔸 → 확정 (검증 TODO 5 해소) |
| `collateral_type_map.csv` | 담보축: BD_KND 매핑 — 자산담보부 7,783·정부신용 2,019(A) + 무보증 32,592(B, 관행 근거 첨부) | 내부 유도 + 은행연합회(무보증 일반화) | `collateralType` 축 성립. 🔴 이름 파싱 불가 실측('담보' 0건) |
| `issuer_industry_map.csv` + `issuer_industry_top200.csv` | 업종축: BD_KND 1차(A급 61.3%) + 발행사명 키워드 2차 + 상위 200 검수표 | 내부 유도 | `issuerCategory` 축 성립 — "금융사 발행 채권" 질의 |
| `index_master_draft.csv` | 지수 94종 정식명·산출기관·자산군 (확정 83·추정 11) | 각 산출기관·언론 검증 | "같은 지수 추종 펀드·ETF" 교차 질의 · Index 축 상향 |
| `trustee_00160037.md` | 수탁사 00160037 = **삼성증권** ('더제이'는 펀드명 접두) | 더제이자산운용 공식 페이지 | 수탁사 17/18 — `ontology/codebooks/trustee.csv` 반영 완료 |
| `zeroin_methodology.md` | 위험등급 1~6 = **운용사 산정·공시** (제로인 게시 경유) | KG제로인 평가방법론·금융위 기준 | "제로인이 산출한 등급" 오서술 차단 (yaml 정정 완료) |
| `etn_issuers.csv` | ETN 발행 증권사 10곳 법인명 (협회 회원사코드는 비공개 확인) | 금투협 회원사현황 | Issuer 축 — 이름 정규화 경로 확정 |
| `kofia_fd_ccd_def.md` | 20자리 분류코드 정의서 **비공개 확인** + 입수 경로 3순위 | 금투협 규정·공시 시스템 | 협회 VOC 문의 발송 근거 |

## 5. 코드북 중 git 추적분 (`ontology/codebooks/` — push 됨)

`trustee.csv`(수탁사 17/18) · `fx_rate.csv`(**1,504.92** — 2026-07-10 ECB 참조환율, 잠정 연평균 교체) — 오늘 갱신.
기존: asset_manager(67)·market·etf_sector·region_map·asset_type_map 등.

---

## 📤 드라이브 업로드 가이드 (git 제외분 공유)

`data/` 전체가 gitignore — **`data/external/` 폴더를 통째로 드라이브에 올리면 된다.** 구성·용량:

| 폴더 | 용량 | 우선순위 |
| :--- | :--- | :--- |
| `data/external/lookups/` | <1MB | 🔴 필수 (코드북·조회 13파일 + fund_facts) |
| `data/external/holdings/` | 7.7MB | 🔴 필수 (국내 구성종목) |
| `data/external/holdings_overseas/` | 35MB | 🔴 필수 (해외 구성종목) |
| `data/external/miraeasset_web/` — prospectus 제외 | ~수백 MB | 🔴 필수 (웹 수집 원본·로그) |
| `data/external/miraeasset_web/prospectus/` | **~3.4GB** | 🟡 선택 — `.txt`(추출본)만 올리면 수십 MB. PDF 원본은 `scripts/fetch_prospectus_bulk.py` 로 각자 재생성 가능(약 2.5h) |

> 대안: 전 폴더가 **재생성 스크립트를 갖고 있으므로**(각 SOURCES.md·스크립트 헤더) 드라이브 없이
> pull 후 스크립트 재실행으로도 동일 데이터를 얻을 수 있다 — 단 외부 사이트 상태 변동 리스크가 있어
> 스냅샷 보존용으로 드라이브 업로드를 권장.
