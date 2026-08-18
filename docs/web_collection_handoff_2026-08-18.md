# 🔁 인수인계 — 미래에셋 웹 수집 · 코드북 완성 · DB 적재 (2026-08-18)

> 대상: 공모펀드 외부 수집 트랙 (페이지 10,565 · Holdings 59,206행 · 투자설명서 186건)
> 기준일 2026-07-11 · 마감 2026-09-06 (D-19)
> **이 문서만 읽고 이어서 작업할 수 있게 썼습니다. §1 사용 규칙을 먼저 읽으세요.**
>
> 앞 인수인계 → `docs/eda/public_funds_handoff_2026-08-18.md` (값 의미·결측 트랙.
> 그 문서 §6 ①이 지목한 "다음 작업"이 이 세션에서 완결됐습니다)
> 상세 로그 → `docs/DATA_COLLECTION_PLAN.md` §3.5 · 다음 스텝 → `docs/PROGRESS_2026-08-18.md` §3

---

## 0. 세 줄 요약

1. **미래에셋증권 펀드상세 페이지가 조회 키(`itm_no`)째로 뚫렸습니다** — 설정일·보수 5종 분해·
   운용사 법인명이 SSR로 노출되어 **10,565종목 전건(100%) 수집 완료**, 실패 0.
2. **운용사 67/67 · 수탁사 16/18 법인명이 '추정'이 아니라 '관측'이 됐고** 코드북·`organization.yaml`·
   KG에 반영 완료 (`or_co_xtn_itt_cd` 매핑 67/67, `build_ontology.py` 오류 0). 8/19 마감 해소.
3. **판정 5건 확정**: `'20'`=단위형(A) · `'06'`=파생형 · 순자산 0=센티넬(298/298) ·
   M109⇒자펀드(반례 0) · `'00'`=98년대 레거시(B+). Holdings는 전 행 기준일 ≤ 7/11로 사용 가능.

---

## 1. 수집물 사용 규칙 — 이어받는 사람이 먼저 읽을 것

| # | 규칙 | 배경 |
| :- | :--- | :--- |
| 1 | 🔴 **페이지 값은 2026-08-18 시점** — 불변 사실(설정일·법인명·모펀드명·단위형)만 확정 근거. 시계열(순자산·수익률)은 답변 근거 금지 | 기준일 유출 감점 (`PROJECT.md` §2-2). 그래서 `ext_fund_page`에 순자산·수익률을 **의도적으로 안 넣었다** — CSV에만 있다 |
| 2 | **Holdings는 `bas_dt`(기준일)가 행마다 붙는다** — 현재 전 행 `as_of_ok=True`(≤7/11)지만, 재수집 시 필터 필수 | 85%가 2026-06-01 기준. 자펀드는 2023~2025년 기준일도 있음(오래된 look-through) — 답변 시 기준일 병기 |
| 3 | 🔴 **`scripts/build_db.py`를 재실행하면 `ext_*` 테이블이 사라질 수 있다** → 직후 `python scripts/load_external_web.py` 재실행 (멱등, 수 초) | ext 테이블은 CSV에서 적재되는 보조 테이블이다 |
| 4 | **마스터와 상충하면 마스터 우선** · `retrieved_context`에 `source: miraeasset_web` 구분 표기 | `PROJECT.md` §3 |
| 5 | 페이지 수익률 `-999`는 센티넬 (CSV에서 볼 때) | fund_pages_full.csv의 M*_BNFR |
| 6 | 🔴 **수집 데이터는 git에 넣지 않는다** — repo가 **public**. 마스터 파생 컬럼·웹 원본 재배포 금지. `.gitignore` 예외 해제 금지 | `PROGRESS_2026-08-18.md` §4 (공유는 zip을 비공개 채널로) |
| 7 | 복수관측 코드 6종(00080008 등)은 **코드 매핑이 흔들리는 게 아니라 일부 펀드가 이관**된 것 — 종목별 운용사는 `ext_fund_page.mgmt_co_nm`이 정답 | `asset_manager_audit.csv` |

---

## 2. 이번 세션 산출물

### git에 있는 것 (커밋 70df09f + 이 문서)

| 파일 | 상태 | 내용 |
| :--- | :--- | :--- |
| `scripts/crawl_miraeasset_full.py` | 🆕 | 전량 크롤 (재개 가능 — raw 캐시 스킵) |
| `scripts/load_external_web.py` | 🆕 | CSV → `ext_fund_page`·`ext_fund_holdings` 적재 (멱등) |
| `scripts/fetch_prospectus_targets.py` | 🆕 | 투자설명서 표적 다운로드·검증 |
| `notebooks/collect_miraeasset_web.ipynb` | 🆕 | 파일럿 + 엔드포인트 발견 기록 (실행 출력 보존) |
| `ontology/codebooks/asset_manager.csv` | 37→**67행** | 정정 6 · 신규 30 · 전 코드 법인명 |
| `ontology/codebooks/trustee.csv` | **16/18 확보** | 투자설명서 신탁업자 절 관측 |
| `ontology/shared/organization.yaml` | 노드 +18 | 삼성액티브 pending 확정 · 제2코드 alias 3건 · 이관 관측 QA |
| `ontology/ontology.ttl` | 재생성 | kg_node 121 · kg_alias 215 |
| `docs/DATA_COLLECTION_PLAN.md` | 🆕 | 수집 계획 + 실행 로그 (§3.5) |
| `docs/PROGRESS_2026-08-18.md` | 🆕 | 진행상황 + **다음 스텝 §3** + 데이터 git 정책 §4 |

### data/에만 있는 것 (git 미포함 — §1 규칙 6)

```
data/external/miraeasset_web/
├─ fund_pages_full.csv     10,565행 — 페이지 SSR 필드 + 마스터 조인 (6.6MB)
├─ holdings_full.csv       59,206행 — ISIN·비중·bas_dt·as_of_ok (8.9MB)
├─ mo_fund_map.csv          3,617행 — 자펀드↔모펀드명 (묶음 1,399 · 모펀드 707종)
├─ trustee_names_observed.csv · asset_manager_audit.csv · issu20_doc_check.csv
├─ raw/                    10,565개 html.gz (305MB) — 재파싱용 캐시
├─ prospectus/             PDF 186개 + 추출 txt (119MB) — 국민성장 4클래스 포함
└─ FULL_CRAWL_DONE.json    수집 통계
```

DB(`data/financial_products.db`): `ext_fund_page`(10,565) · `ext_fund_holdings`(59,206)

---

## 3. 확정된 것

| 대상 | 판정 | 근거 | 등급 |
| :--- | :--- | :--- | :-: |
| `fd_set_pcd '20'` | **단위형** | 간이투자설명서 표본 30/30 "단위형" 명시, "추가형" 0 | **A** |
| `or_attr_desc '06'` | **파생형** | 페이지 유형코드 39/39 = `06` · 정식명 "파생형" 38/39 | A |
| `fd_nast_suma = 0` | **센티넬(위장결측)** | 마스터 0인 298건 전원 페이지 순자산 > 0 | A- (형식 확정은 금투협 7/10 조회) |
| `M109` | **⇒ 자펀드** (역은 불성립) | 모펀드 명시 3,617건 중 반례 0 · 미보유 259건도 이름상 자펀드 → 재현율 93% | A |
| `fd_set_pcd '00'` | **98년대 구제도 레거시** | 110건 중 105건 설정일 1998~2000 · `프로단기공사채`류 · fss 결측 100%와 정합 | B+ |
| 수탁사 종별 `0002` | **은행** (추정→확정) | 12코드 전부 은행 관측 | A |

## 4. 재현·재개 방법

```
python scripts/crawl_miraeasset_full.py    # 전량 재수집 153분 · raw 캐시 있으면 그만큼 스킵
python scripts/load_external_web.py        # DB 적재 (몇 초, 멱등)
python scripts/build_ontology.py           # 코드북·yaml 검증 + ttl·kg 재생성
```

팀원이 zip(`fund_pages_full.csv` 등)을 받았다면: `data/external/miraeasset_web/`에 풀고 두 번째 명령만.

## 5. 다음 작업 — `PROGRESS_2026-08-18.md` §3이 원본, 요지만

1. **`ext_*` 테이블을 검색 레이어(NL2SQL·retrieved_context)에 연결** ← 최우선. 수집만 하고 안 쓰면 0점
2. §3 확정 판정을 `ontology/enums/public_funds.yaml`(`value_semantics`·`missing_profile`)에 반영
3. 모펀드 707종 개체화 → KG edge (3-hop 질의 대비)
4. 금투협: 7/10 순자산(Q5 형식 확정) · `kofia_fd_ccd` 정의서 · ETN 증권사 코드
5. P2 본대: pdf→MD 파이프라인 (`prospectus_url` 전 종목 준비됨, 소스코드 채점 직결)

## 6. 미해결·함정

- **수탁사 2코드 미확보** (각 1종목): `00160006`=TIGER일본엔인버스2X(⚠️ **공모펀드 마스터에 ETF 혼입** — 문서 채널이 다름) · `00160037`=더제이 1종(PDF 글리프 파손). 금투협 조회로 보완 가능
- **이관 3건 워크샵 안건**: 00040023 알리안츠→우리글로벌 · 00040013 키움슈로더→키움투자 ·
  00040084 도이치→DWS — 라벨/노드 병합은 organization.yaml 담당(Song-exp) 확인 후
- 페이지 사내코드 `PD_TYP_CD`가 마스터 `or_attr_desc`와 **동일 체계로 관측**됨 — `PD_CLSS`(7값)·
  `fdStcCd`·`spcDvCd`는 아직 미해독. 교차표는 `ext_fund_page`로 바로 뽑을 수 있음
- Holdings는 **펀드묶음(mtco) 대표 1클래스로만 수집** — 형제 클래스 동일 가정. 반례 발견 시 재검토
