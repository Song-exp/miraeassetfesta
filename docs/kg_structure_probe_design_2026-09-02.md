# 온톨로지·KG 구조 검증 문항 설계 — 2026-09-02

> 목적: 재검 중인 19문항(HANDOFF §1 P1 7 + 형제 12, `eval/probe_recheck_2026-09-02_r2.txt`)이 **결정층 수리의 재현**을 보는 세트라면, 이 세트는 **온톨로지(.ttl)·KG(kg_* 4테이블)·규칙(yaml)·코드북이 서로 맞물려 있는가**를 시험한다.
> 산출물: `eval/questions_kg_structure.jsonl` (35문항, KG-001~035) + 이 문서. 코드·yaml 은 손대지 않았다.
> gold 는 전부 DB(`data/financial_products.db`, 8/22 정본) 실측이며 기본모수 = `sale_yn='판매중' AND prvo_pbff_desc='공모'` 8,969행 / 3,040펀드(현행 펀드키). 실측이 불가능한 문항은 reject 가 정답임을 명시했다.

---

## ① 설계 의도와 축별 표

### 설계 원칙 4가지

1. **한 문항 = 온톨로지 요소 하나**. 각 문항에 시험 요소(`kg_elements`)와 **예상 실패 층**(라우터/KG/가드/게이트/조립)을 붙였다. 답이 틀리면 어느 층인지 바로 갈리도록 must_not_include 에 "그 층이 만드는 오답 값"을 심었다(예: KG-023 은 closure 오적용이면 `삼성MMF법인제1호`가 1위로 온다).
2. **형제 문항 원칙**(HANDOFF 교훈 3). 이미 검증된 대표 사례의 형제를 골랐다 — 미래에셋(4자) ↔ 영문 'Mirae Asset'(KG-001), 중국 CHN ↔ 일본 JPN·미국 USA·대만 TWN(KG-019~021), 한투 143 ↔ 띄어쓰기 변형(KG-004), R6 2호 ↔ 시리즈 전체(KG-030).
3. **기존 문항과 중복 회피**. `question_design_public_funds_2026-08-31.md` §1 커버리지 매트릭스와 `questions_*.jsonl` 60문항을 대조해 겹치는 건 제외했다(역외 개수 FND-013, 오래된 펀드 R06, 삼성 펀드 clarify C02, 삼성전자 TOP10 CROSS-001, 벤치마크 KOSPI200 펀드 측 FND-036 등). 남긴 형제는 축이 다르다(KG-026 은 ETF 측 교차, KG-029 는 rptt 키).
4. **gold 는 값 + 기준**. 분류축이 둘인 문항(KG-016 채권혼합, KG-022 유럽, KG-025 ETF 개수)은 "기준을 밝힌 답" 이면 어느 쪽도 정답으로 두고, 기준 없이 한 숫자만 내면 부분으로 채점하도록 note 에 적었다.

### 축별 문항 표

**A. 개체 해소(Entity Resolution) — 5문항**

| qid | 난이도 | 기대 | 질문 | 시험 요소 | gold(실측) | 예상 실패 층 |
| :-- | :-: | :-: | :-- | :-- | :-- | :-- |
| KG-001 | 중 | answer | Mirae Asset이 운용하는 공모펀드는 몇 개야? | `kg_node.label_en` 슬롯을 정식 한글명이 점유(09-01 수리 부작용) — 영문 alias 는 `domestic_etfs.ref_fund_mgmt_co` 에만 | 823펀드/2,066클래스 | KG(Ground 매칭) |
| KG-002 | 상 | answer | 프랭클린템플턴이 운용하는 공모펀드 알려줘 | Org_00040022 노드는 살아 있으나 판매중 0행 · 이름 잔존 39펀드는 00040007 우리자산운용(이관) · kg_synonym 부재 · ext mgmt_co_nm 10행 구명칭 잔존 | 코드 0 / 이름 39펀드·68클래스(우리자산운용) / 역외 템플턴글로벌본드 8 | KG → 가드(0행 단정) |
| KG-003 | 중 | reject_or_clarify | 메리츠자산운용이 운용하는 공모펀드는 몇 개야? | 코드북 67법인에 없음 · 구상호(KCGI←메리츠) 주석에만 · 동명 증권사 '메리츠증권'(ETN 발행사 97) 노드 | 없음 (KCGI 추정 안내 허용 27펀드/133클래스) | KG(증권사 노드 오매핑) → 라우터(ETF 유출) |
| KG-004 | 하 | answer | 한국 투자 신탁 운용 이 운용하는 공모펀드는 몇 개야? | label_en 무경계 부분일치가 공백 삽입에도 먹는지 · 제2코드 00040105 병합 | 143펀드/541클래스 | KG(공백 정규화) |
| KG-005 | 상 | answer | 이름이 삼성으로 시작하는 공모펀드는 몇 개고, 그중 삼성자산운용이 운용하는 건 몇 개야? | Org_00040010 ⊥ Org_SamsungActive 분리 · clarify.펀드이름 오발동 여부 · 2자 라벨 하한 | 217/906 = 삼성 207/850 + 삼성액티브 10/56 | 게이트(CLARIFY 오발동) → KG → 조립 |

**B. 관계·역관계 — 6문항**

| qid | 난이도 | 기대 | 질문 | 시험 요소 | gold(실측) | 예상 실패 층 |
| :-- | :-: | :-: | :-- | :-- | :-- | :-- |
| KG-006 | 하 | answer | 미래에셋코어테크 펀드의 운용사와 수탁사는 어디야? | `fp:hasManager` 펀드→운용사 방향 · Org_trustee_00020088 라벨 · 역할 3종 분리 | 미래에셋자산운용 / 신한은행(00020088) | KG(수탁 코드→이름) → 조립 |
| KG-007 | 하 | answer | 미래에셋자산운용에 의해 운용되는 공모펀드는 몇 개야? | `fp:manages owl:inverseOf fp:hasManager` 가 트리거('운용되는' 은 triggers 에 없음)로 내려갔는지 · kg_edge 에 Org→상품 edge 0 | 823/2,066 | 라우터/규칙 트리거 |
| KG-008 | 중 | answer | 공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘 | trusc → Org_trustee_* · 운용사·수탁사가 같은 fp:Organization(역할 속성 부재) · 센티넬 제외 | HSBC 714/1,827 · 국민은행 516/1,656 · 씨티 465/1,466 | 플래너(컬럼 오선택) → KG(코드만 나열) |
| KG-009 | 상 | answer | 미래에셋증권이 수탁사인 공모펀드도 있어? | raw `'0016022 '`(7자리+공백) vs trustee.csv `00016022` vs KG alias `0016022` · Org_trustee_0016022/00160022 두 노드 · 당사판매 트리거 오개입 | 2펀드/14클래스 (iM에셋 타이거 포커스 6 · 머스트원앤온리 8) | 가드(당사판매 강제) → KG(코드폭 0행) |
| KG-010 | 중 | answer | 미래에셋코어테크 펀드의 모펀드는 뭐야? | `feedsInto` edge(1,704) · MotherFund 노드 717 · 설명서항목 규칙 · 모자형≠재간접 | 미래에셋코어테크증권모투자신탁(주식) | 플래너(오거절) → KG(edge 미활용) |
| KG-011 | 중 | answer | KB자산운용 펀드 중 국민은행이 수탁하는 공모펀드는 몇 개야? | 'KB' 동음이의(운용사 vs 수탁은행) · 국민은행 코드 2종 미병합 · 0행 진단 | 0 (KB 수탁사는 씨티 170·HSBC 120·신한 116…) | KG(브랜드 오매핑) → 가드(0행→거절) |

**C. 분류 계층·enum 제약 — 7문항**

| qid | 난이도 | 기대 | 질문 | 시험 요소 | gold(실측) | 예상 실패 층 |
| :-- | :-: | :-: | :-- | :-- | :-- | :-- |
| KG-012 | 중 | answer | 해외주식형 중에서 중국주식 유형인 공모펀드는 몇 개야? | zrin_btyp_nm→zrin_ptn_nm 계층(KG 에 소분류 노드·closure 없음) · class_hierarchy 가 ttl 로 안 나감 · 국가 태그와 축 분리 | 205펀드/522클래스 (CHN 태그 248 과 다름) | 가드(국가 태그 확정식 오발동) |
| KG-013 | 하 | reject | 위험등급 7등급인 공모펀드 알려줘 | `fp:riskGradeValue` 0~6 제약 · 게이트 enum 밖 즉답 | reject (1~6) | 게이트(미발동→'0개') |
| KG-014 | 중 | reject | 위험등급 0등급 공모펀드는 몇 개야? | RiskGrade_0 alias 는 채권만 · ttl 범위 0~6 의 domain 이 PublicFund 를 포함(과대 허용) | 펀드에 0등급 없음(NULL 422 ≠ 0) | 게이트 → 조립(NULL 을 0 으로) |
| KG-015 | 중 | answer | 위험등급이 '높은위험'인 공모펀드는 몇 개야? | RiskGrade_2 alias 2종(공백 변형) · value_variants | 995펀드/2,994클래스 | KG(변형 alias 미활용) → 가드(LIKE 과포함 5,593) |
| KG-016 | 중 | answer | 채권혼합 공모펀드는 몇 개야? | axis_fundType(or_attr_desc) vs assetClass(zrin_btyp_nm) 두 축 · 접미사 '형' · '혼합형' 확정식 오치환 | 약관 389/933 · 제로인 240/534(+해외 430/974) — 기준 병기 시 정답 | 가드(값 검사 기각) → 조립(기준 미표기) |
| KG-017 | 상 | answer | 폐쇄형 공모펀드는 몇 개야? | yaml axis_redemptionType "'폐쇄' 미확인" ↔ fund_attr_code.csv C104 폐쇄 6행 실재 · 태그 KG 부재 | 3펀드/6클래스 | 규칙(yaml 오서술→오거절) |
| KG-018 | 중 | answer | 단위형이면서 개방형인 공모펀드도 있어? | 추가/단위 ⊥ 개방/폐쇄 직교 축(도메인 §1.4) · 태그 C102∧C103 | 31펀드/189클래스 (단위형 전체 35/220) | 플래너(축 병합→0행) |

**D. 국가·지역·테마 태그 — 6문항**

| qid | 난이도 | 기대 | 질문 | 시험 요소 | gold(실측) | 예상 실패 층 |
| :-- | :-: | :-: | :-- | :-- | :-- | :-- |
| KG-019 | 중 | answer | 일본에 투자하는 공모펀드 알려줘 | 국가 태그 확정식 JPN 일반화 · Region_Japan public_funds alias 0 | 31펀드/79클래스 (이름 보조 38/103) · 1위 피델리티재팬 239억 | 가드(확정식 JPN 미발동) |
| KG-020 | 중 | answer | 미국에 투자하는 공모펀드는 몇 개야? | Region_US⊂NorthAmerica⊂Americas closure 역방향 오용('남미/북미' 489) · USA vs W104 북미(494) | 98펀드/333클래스 (이름 보조 167/611) | KG(closure→489) |
| KG-021 | 중 | answer | 대만에 투자하는 공모펀드 있어? | 태그 목록 밖 나라 → 이름 폴백 규칙 · entities.Country 17종 vs 실재 11종 | 태그 0 · 이름 1(피델리티대만펀드, 역외) | 가드(0행 오거절) |
| KG-022 | 상 | answer | 유럽에 투자하는 공모펀드는 몇 개야? | Region_Europe alias(지역 컬럼) ✅ vs 태그 범유럽/서유럽/동유럽/유로권 미연결 · 확정식이 '유럽' 을 국가로 오인 | 지역 61/193 · 확장 96/269 — 기준 병기 | 가드(존재하지 않는 국가코드 LIKE) |
| KG-023 | 상 | answer | 아시아에 투자하는 공모펀드 중 순자산 큰 5개 알려줘 | region.yaml Region_Korea parent Region_Asia → closure 로 국내 3,513행 유입 | KB중국본토A주 1,453억 · 차이나솔로몬1호 1,393억 · 한투베트남그로스 1,066억 · 신한중국의꿈2호 1,038억 · 미래에셋다이와넥스트아시아퍼시픽1호 669억 | KG(closure 오적용→MMF 도배) |
| KG-024 | 하 | answer | 반도체 테마 공모펀드는 몇 개야? | FundAttribute N축 KG 부재 · 테마≠유형 · 태그∪이름 | 12펀드/78클래스 | 가드(값 검사 기각) |

**E. 교차 도메인 — 4문항**

| qid | 난이도 | 기대 | 질문 | 시험 요소 | gold(실측) | 예상 실패 층 |
| :-- | :-: | :-: | :-- | :-- | :-- | :-- |
| KG-025 | 상 | answer | 삼성자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야? | Org_00040010 교차 alias(상품명 쓰레기 raw 13종 포함) · ETF⊥ETN · 삼성액티브·삼성증권 분리 | 펀드 207/850 · ETF 224(alias 집합 240) | KG(alias 불일치) → 가드(ETN 유입) |
| KG-026 | 상 | answer | KOSPI200 벤치마크 펀드와 KOSPI200 추종 국내 ETF 개수 | Idx_KOSPI200 의 ETF alias 가 `cu_base_index 'KOSPI200'`(실제 값은 공백 패딩·`ref_base_index 'KOSPI 200 CR'`) | 펀드 정확 421/부분 815 · ETF 50(계열 93) | KG(ETF 측 지수 alias 0건) |
| KG-027 | 하 | reject | 미래에셋코어테크 펀드 설정 좌수 알려줘 | fund_pub.ttl ABSENT 선언이 hasCreditGrade 1건뿐 — 좌수 부재 선언 없음 | reject (기준가·순자산 대체 안내 허용, 도출 금지) | 게이트(부재 미선언→계산 날조) |
| KG-028 | 중 | answer | 미래에셋코어테크 펀드가 가장 많이 보유한 종목은? | `fp:holds/isHeldBy` · ExternalHoldings 가 edge 테이블 · 모자형 대표성 | 삼성전자 24.95% · SK하이닉스 15.90% · 삼성전기 7.96% (2026-06-01, 종류A 1건) | 라우터(교차 미특정) → 플래너(조인 누락) |

**F. 집계 단위·키 — 3문항**

| qid | 난이도 | 기대 | 질문 | 시험 요소 | gold(실측) | 예상 실패 층 |
| :-- | :-: | :-: | :-- | :-- | :-- | :-- |
| KG-029 | 중 | answer | 우리자산운용 펀드 수를 대표예탁원종목번호 기준으로 세면? | KG Fund 노드 키(rptt) vs 런타임 펀드키(or_co+mtco) 이중성 · 개수 가드의 키 강제 치환 | 88 (현행키 235 · 클래스 403) | 가드(키 치환→235) |
| KG-030 | 상 | answer | 미래에셋차이나솔로몬 시리즈는 몇 호까지 있고 각각 클래스가 몇 개야? | N호 GLOB 이 '3(주식)' 표기 4행을 놓침 · rptt 3 vs 현행키 9 · 호수 불일치 차단 가드 | 1호 2 · 2호 7 · 3호 8 (17클래스) | 가드(GLOB 사각) → KG(차단) |
| KG-031 | 중 | answer | 피델리티가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야? | Org_00080029 vs Org_fund_00130001 미병합 · 역외 rptt NULL → KG Fund 노드 0 | 106/246 + 역외 47/47 = 153/293 | KG(역외 코드 미연결) |

**G. 시간·기준일 가드 — 4문항**

| qid | 난이도 | 기대 | 질문 | 시험 요소 | gold(실측) | 예상 실패 층 |
| :-- | :-: | :-: | :-- | :-- | :-- | :-- |
| KG-032 | 하 | reject_or_partial | 2026년 9월 1일 기준으로 순자산이 가장 큰 공모펀드 | build_info.as_of 8/22 · 실시간_시세 거절 vs 스냅샷 허용 경계 | 기준일 명시 후 8/22 값(삼성MMF법인제1호 12.4조) 대체 | 게이트/플래너(시점 무시) |
| KG-033 | 중 | answer | 가장 최근에 설정된 공모펀드 알려줘 | ext_fund_page.estb_dt JOIN · JOIN 기본모수 주입 | 2026-06-12 동률 2 (KB K-성장과 지배구조 30 목표전환 7클래스 · 미래에셋국민참여형 C1-e) | 플래너(오거절) → 가드(JOIN 모수) |
| KG-034 | 중 | answer | 미래에셋코어테크 펀드는 운용한 지 얼마나 됐어? | 문자열 날짜 산술 · 클래스별 설정일 상이 · '모델은 복사만' | 2019-10-23 → 약 6년 10개월(2,495일) | 플래너(산술) → 조립(LLM 산술) |
| KG-035 | 중 | answer | 2026년에 설정된 공모펀드는 몇 개야? | 연도 필터 · 개수 가드가 JOIN 경로에도 발동하는지 · 커버리지 병기 | 39펀드/124클래스 (1~6월, 8/22 이후 0) | 가드(JOIN 에 DISTINCT 미주입→124) |

합계 35문항 — A5 · B6 · C7 · D6 · E4 · F3 · G4. 기대행동: answer 30 · reject 3 · reject_or_clarify 1 · reject_or_partial 1 (게이트 문항 KG-013·014·027). gold_sql 32건 전부 DB 실행 확인(오류 0). 난이도: 하 7 · 중 19 · 상 9.

---

## ② 온톨로지·KG 를 읽으며 발견한 구조적 약점·불일치

읽은 것: `common.ttl`(4.8MB, 개체 전부) · `fund_pub.ttl`(11줄) · `etf_kr.ttl` · `bond_kr.ttl` · `shared/*.yaml`(organization·region·risk_grade·asset_class·fund_structure_auto) · `enums/public_funds.yaml` 1,339줄 · `_refusal.yaml` · `codebooks/*.csv` · `scripts/build_ontology.py` · DB `kg_*` 실물(node 41,384 · alias 66,396 · edge 7,414 · closure 9,967).

### ②-1 🔴 상위 5 (질문 세트가 직접 겨눈 것)

1. **펀드키 이중성 — KG 와 런타임이 다른 '펀드'를 센다.** KG `Fund` 노드 6,867 은 `rptt_ksd_itm_no` 단위(`fund_structure_auto.yaml`), 런타임·gold·개수 가드(§0-5)는 `(or_co, zero-pad mtco)` 3,040. 기본모수에서 rptt distinct 1,809 (+역외 NULL 110). 우리 235→88 · iM에셋 205→29 · 피델리티 106→37 로 운용사별 편차가 2.7~7배(리뷰 §④ 확정). 역외 110행은 rptt 가 NULL 이라 **KG Fund 노드가 없다**. `enums.entities.Fund` note 가 "이름 충돌 — 두 축" 이라고 자인하면서 분리하지 않았다. → KG-029·030·031.
2. **운용사 라벨 슬롯 오용 + 동의어 층 부재.** 09-01 수리(HANDOFF §0-16)가 정식 법인명을 `kg_node.label_en` 에 넣어 **영문 라벨 자리가 사라졌다** — 'Mirae Asset Global Investments Co Ltd' 는 `domestic_etfs.ref_fund_mgmt_co` alias 로만 있고 라벨이 아니다. 구상호(프랭클린→우리, 메리츠→KCGI, DGB→iM에셋, 신한BNPP→신한, 동양→우리)는 `organization.yaml` 주석·"kg_synonym 후속" 메모로만 존재. 판매중 0행인 Org_00040022(프랭클린)·Org_00040023(알리안츠, label_en 은 우리글로벌자산운용) 노드는 살아 있고, 같은 법인(키움투자자산운용)이 Org_00040013·Org_00080052 두 노드다. → KG-001·002·003·004.
3. **역할 분리가 온톨로지에 없다.** 도메인 §1.2 의 운용사·수탁사·판매사 분리가 ttl 에서는 `fp:Organization` 단일 클래스 + `hasManager`/`hasIssuer` 두 속성뿐 — `hasTrustee`·`hasDistributor` 없음, disjointWith 는 ETF⊥ETN 하나뿐. 수탁사 alias(`trusc_xtn_itt_cd` 48종)가 같은 Organization 에 매달려 있어 FND-030 오매핑(판매사→수탁사)이 **구조적으로 재발 가능**. 수탁 코드는 DB raw `'0016022 '`(7자리+공백) ↔ `trustee.csv 00016022` ↔ KG alias `0016022` 세 표기가 다르고 `Org_trustee_0016022`·`Org_trustee_00160022` 가 공존, 국민은행도 00020004·00160005 두 노드. 0016xxxx 33코드는 `canonical_name` 이 코드 숫자 그대로. → KG-006·008·009·011.
4. **국가·태그 축이 KG 에 전혀 없고, Region closure 는 펀드 의미와 어긋난다.** `prfd_attr_cds`/`zrin_attr_nms` 227종(국가 17 + 속성 210)에 대한 kg_node/alias 0건 — 국가 태그 규칙(CHN·USA·JPN…)은 yaml 텍스트로만 산다. `Region_China/Japan/US/Taiwan` 노드는 public_funds alias 0(ETF 컬럼만). 반대로 `Region_Korea parent: Region_Asia` closure 를 펀드에 적용하면 '아시아' 질의에 국내 3,513행이 유입(947→4,460행). 세부지역 태그(범유럽 W114·서유럽 W115·동유럽 W116·유로권 W118·북미 W104)는 Region 노드와 미연결. `entities.Country` 17종 중 기본모수 실재는 11종. → KG-012·019~024.
5. **벤치마크·운용사 교차 alias 가 ETF 실물과 어긋난다.** `Idx_KOSPI200` 의 ETF alias 는 `domestic_etfs.cu_base_index 'KOSPI200'` 하나인데 그 컬럼은 공백 40자 패딩이고 실제 지수는 `ref_base_index 'KOSPI 200 CR'/'KOSPI 200 TR KRW'/'F-KOSPI 200'` — 교차 0건 위험. 운용사 alias 는 `cu_fund_mgmt_co` 에 **상품명이 들어간 오염 raw**(삼성 13종·미래에셋 40여 종 '미래에셋TIGER…증권상장지수투자신탁')를 rule 로 흡수했다. 미래에셋의 해외 ETF 자회사 Global X(123 ETF)는 별개 노드 `Org_mgr_0e93dc103a` 로 미연결. → KG-025·026.

### ②-2 그 밖의 불일치 목록

| # | 위치 | 어긋남 | 영향 |
| :-- | :-- | :-- | :-- |
| 6 | `public_funds.yaml axis_redemptionType` ↔ `codebooks/fund_attr_code.csv` | yaml: "'폐쇄' 태그는 2차 태그 목록에서 미확인" / 코드북: C104 폐쇄 195행(판매중 6) confirmed | 규칙을 믿으면 폐쇄형 오거절 (KG-017) |
| 7 | `common.ttl fp:riskGradeValue` (0~6, domain ∪ PublicFund) ↔ `risk_grade.yaml` RiskGrade_0 alias 는 domestic_bonds 만 | 펀드에 0등급을 ttl 이 허용 | NULL 422 를 0등급으로 오독 위험 (KG-014) |
| 8 | `public_funds.yaml class_hierarchy`(Fund→SecuritiesFund→EquityFund…) | `fund_pub.ttl` 에 subClassOf 계층 0 — `emit_ttl` 이 class_hierarchy 블록을 읽지 않는다 | 온톨로지 제출물에 펀드 분류 계층이 없음 (KG-012) |
| 9 | `fund_pub.ttl` ABSENT 선언 | hasCreditGrade 1건뿐. 좌수·운용역·기준가 시계열·환매조건(마스터) 부재 선언 없음 — 반면 bond_kr.ttl 은 3건 | 게이트 근거 부재 → 날조 여지 (KG-027) |
| 10 | `common.ttl inverseOf`(manages/issues/isHeldBy) ↔ `kg_edge` | Organization→상품 edge 0건(관계는 alias 로만). `query_rules.운용사질의` triggers 에 피동형('운용되는') 없음 | inverseOf 가 결정층에 없음 (KG-007) |
| 11 | `fund_structure_auto.yaml` MotherFund 717 · feedsInto 1,704 | 모펀드 이름 파싱 잔여로 가짜 허브 생성 — '증권모투자신탁'(fan-in 143)·'증권모투자신탁(주식)'(59)·'기본방침모투자신탁'(28)·'투자목적-모투자신탁'(26) | 모펀드 질의가 허브에 빨려 들어감 (KG-010 형제 위험) |
| 12 | `organization.yaml` Org_fund_0013xxxx 라벨 | 역외 운용법인 코드 라벨이 펀드명 접두('피델리티펀드유로'·'북미펀드'·'미래에셋차이나업') — asset_manager.csv 도 '법인명 아님' 자인 | 역외 펀드 운용사 답변 시 가짜 이름 노출 (KG-031) |
| 13 | `kg_alias public_funds.zrin_fd_ivst_risk_grd_nm` | '높은위험'·'보통위험' 변형 alias 있음(✅) 이나 `risk_grade.yaml` 주석 수치(163행·75행)는 1차 기준 — 2차 실측 20행·8행 | 문서 수치 구식 (KG-015 는 통과 예상) |
| 14 | `public_funds.yaml or_co_xtn_itt_cd.missing_semantics '99999999'` | "KG 에 Org_fund_99999999 노드를 만들고 있다 — 제거 대상" 서술 ↔ 현 KG 에는 해당 노드·Org_trustee_99999999/00000000 **없음** (이미 해소) | yaml 서술 구식 — 정정 큐 |
| 15 | `AssetClass` alias | zrin_btyp_nm 18종 전부 매핑됐으나 '해외주식형'·'주식형' 이 같은 AssetClass_Equity 로 합쳐져 국내/해외 구분 소실 · `or_attr_desc` 14종은 미매핑 | '주식형 펀드' 교차 질의에서 해외 포함 여부 불명 (KG-016) |
| 16 | `region.yaml Region_Russia` | parent 없음(글로벌 하위 개별국 미지정) · 펀드 RUS 태그 51행과 미연결 | 러시아 질의 closure 불능 |
| 17 | `public_funds.md §3.4·§4.8` (도메인 문서) | "mtco_itm_no = 운용 단위(모펀드) 키", "순자산 클래스 동일" — DB 실측과 불일치(리뷰 §④·②-6) | 문서 정정 큐(리뷰 ③-10) — 이 세트는 DB 실측을 우선했다 |

### ②-3 통과가 예상되는 요소(대조군)

- `RiskGrade_1~6` alias 실수 표기 '1.0'~'6.0' + 등급명 변형 2종 — KG-015.
- `Region_Asia/Europe/Global/Americas/Emerging/MEA/Korea` ← `fd_ivst_rgn_desc` 7종 매핑 완료 — KG-022·023 의 1차 경로.
- `ext_fund_page` 조인 규칙(설명서항목) — 설정일·모펀드·운용사명 경로 — KG-006·010·033~035.
- 09-02 수리분(국가 태그 확정식·개수 병기·억원 굽기)은 형제 문항에서 재현 여부만 본다.

---

## ③ 서버 실측용 probe 블록

`ID<TAB>질문` 형식 — 그대로 `eval/probe_kg_structure_2026-09-02.txt` 로 저장해 `eval/probe_server.py` 에 넣을 수 있다.

```
# KG 구조 검증 35문항 — 2026-09-02 (gold: eval/questions_kg_structure.jsonl)
KG-001	Mirae Asset이 운용하는 공모펀드는 몇 개야?
KG-002	프랭클린템플턴이 운용하는 공모펀드 알려줘
KG-003	메리츠자산운용이 운용하는 공모펀드는 몇 개야?
KG-004	한국 투자 신탁 운용 이 운용하는 공모펀드는 몇 개야?
KG-005	이름이 삼성으로 시작하는 공모펀드는 몇 개고, 그중 삼성자산운용이 운용하는 건 몇 개야?
KG-006	미래에셋코어테크 펀드의 운용사와 수탁사는 어디야?
KG-007	미래에셋자산운용에 의해 운용되는 공모펀드는 몇 개야?
KG-008	공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘
KG-009	미래에셋증권이 수탁사인 공모펀드도 있어?
KG-010	미래에셋코어테크 펀드의 모펀드는 뭐야?
KG-011	KB자산운용 펀드 중 국민은행이 수탁하는 공모펀드는 몇 개야?
KG-012	해외주식형 중에서 중국주식 유형인 공모펀드는 몇 개야?
KG-013	위험등급 7등급인 공모펀드 알려줘
KG-014	위험등급 0등급 공모펀드는 몇 개야?
KG-015	위험등급이 '높은위험'인 공모펀드는 몇 개야?
KG-016	채권혼합 공모펀드는 몇 개야?
KG-017	폐쇄형 공모펀드는 몇 개야?
KG-018	단위형이면서 개방형인 공모펀드도 있어?
KG-019	일본에 투자하는 공모펀드 알려줘
KG-020	미국에 투자하는 공모펀드는 몇 개야?
KG-021	대만에 투자하는 공모펀드 있어?
KG-022	유럽에 투자하는 공모펀드는 몇 개야?
KG-023	아시아에 투자하는 공모펀드 중 순자산 큰 5개 알려줘
KG-024	반도체 테마 공모펀드는 몇 개야?
KG-025	삼성자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야?
KG-026	KOSPI200을 벤치마크로 쓰는 공모펀드와 KOSPI200을 추종하는 국내 ETF는 각각 몇 개야?
KG-027	미래에셋코어테크 펀드 설정 좌수 알려줘
KG-028	미래에셋코어테크 펀드가 가장 많이 보유한 종목은 뭐야?
KG-029	우리자산운용 펀드 수를 대표예탁원종목번호 기준으로 세면 몇 개야?
KG-030	미래에셋차이나솔로몬 시리즈는 몇 호까지 있고 각각 클래스가 몇 개야?
KG-031	피델리티가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?
KG-032	2026년 9월 1일 기준으로 순자산이 가장 큰 공모펀드 알려줘
KG-033	가장 최근에 설정된 공모펀드 알려줘
KG-034	미래에셋코어테크 펀드는 운용한 지 얼마나 됐어?
KG-035	2026년에 설정된 공모펀드는 몇 개야?
```

### 실측 순서 권고

1. **게이트 3건 먼저**(KG-013·014·027) — HCX 0회 즉답이어야 하며 비용이 없다.
2. **KG 층 단독 판별 6건**(KG-001·004·009·029·031·026) — 값이 틀리면 코드가 아니라 yaml/코드북 정정 대상이라 다른 세션의 `pipeline.py` 작업과 충돌하지 않는다.
3. **closure·태그 6건**(KG-012·019~024) — 09-02 국가 태그 확정식(§0-6)의 발동 폭을 잰다. 오발동(KG-012·022)과 미발동(KG-019~021)이 같이 나오면 확정식의 트리거 어휘 목록을 국가/권역/유형으로 3분해야 한다.
4. 나머지는 형제 검증 — 재검 19문항과 같은 날 돌려 회귀를 같이 본다.

### 채점 메모

- must_include 는 값 토큰 위주(콤마 유무 양쪽 허용해 채점 — '2,994'/'2994'), must_not_include 는 "그 층이 만드는 오답 값".
- 기준이 둘인 문항(KG-016·022·025·026)은 **기준을 밝힌 답** 이면 정답, 한 숫자만 내면 부분.
- reject_or_partial(KG-032)은 기준일 명시 없이 값을 내면 오답, 기준일을 밝히고 값을 내거나 거절하면 정답.
