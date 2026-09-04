# 도메인 원고 템플릿 — ETF 국내·해외 (담당: ETF)

> **이 파일이 곧 제안서의 ETF 몫이다.** §A~§E 를 채우면 리드가 절 번호 그대로 이어 붙인다.
> `../proposal/ontology_engineering_etf.md`(8/26) 의 결함→선언 8건이 이미 원고다. 이 템플릿은 그 8건을 **3층 라벨·런타임 소비처·실측 사례**로 보강하고, 국내·해외를 한 장에 대칭으로 그리는 구조도를 더한다.
> `▶` 가 채울 곳. 규칙: ① 수치는 NUMBERS ② 결함→선언 인과 ③ Federated·그래프 탐색·추론 금지 ④ 공유 개체 정의는 리드 2.2.1 참조.
> 마감: 초안 9/3, 완성 9/4. ETF 담당은 추가로 **2.1 데이터 절 통합**과 **부록 편집**을 맡는다(`01_작성방향_분담.md` §0-2).

| 이 파일의 절 | 전체 보고서 위치 | 분량 |
| :-- | :-- | :-- |
| §A | 2.1.1~2.1.3 (ETF 단락 + 절 전체 통합) | 1쪽 + 통합 |
| §B | **2.2.3 ETF 국내·해외** | 3쪽 |
| §C | 4.2 흐름도 ETF | 1쪽 |
| §D | 5.2 현업 적용 지점 ETF | 1단락 |
| §E | 부록 A·B·C ETF분 | 별도 |

---

## §A. 데이터 (→ 2.1) — ETF 단락 1쪽 + 절 통합

ETF 는 외부 수집의 98% 를 차지하므로 2.1 절 전체의 통합자다. 골격은 `docs/proposal_data_pipeline_section.md`(수집·적재·신뢰성·활용·한계). 채권·펀드 담당의 단락(`04_도메인_채권.md` §A, `06_도메인_펀드.md` §A)을 받아 2.1.1 에 배치한다.

**예시 문장 (ETF 단락):**

> 두 ETF 마스터(국내 1,780행 × 98컬럼, 해외 6,037행 × 49컬럼)에는 **구성종목 컬럼이 없다.** 주최 공식 예시 5문항 중 3문항("캠브리콘 편입", "에코프로 자회사 편입", "우주항공 테마 연결")이 구성종목을 묻는다. 그래서 국내는 KRX 공시 구성종목 75,859행(1,160/1,235 ETF, 93.9%), 해외는 SEC EDGAR NPORT-P 906,848행(1,356/5,972, 22.7%)을 수집해 `ext_etf_holdings`·`ext_ovs_etf_holdings` 에 적재했다.
> 해외 NPORT-P 는 보고기준일이 8종(2025-10-31 ~ 2026-06-30)으로 흩어져 최대 8개월 시차가 있다. 답변에 `report_date` 를 병기하는 원칙은 여기서 나왔다. 현금·파생 등 티커 없는 10,123행은 Security 노드로 만들지 않았다 — 구성종목 수 집계를 오염시키기 때문이다.
> 신뢰성 관리 사례 하나: 온톨로지 감사(9/2)에서 2차 데이터 신규 컬럼 `ref_geo_focus` 23종이 Region 에 0/23 연결된 것을 커버리지 리포트가 잡아냈고 87% 로 복구했다. 반대로 원천 자체의 지역 오분류(미국 28건·중국 15건, 예: `TIGER 미국S&P500선물(H)` → 국내)는 값을 고치지 않고 `지역질의_합집합` 규칙으로 우회했다(466→494건).

✅ 커버리지 NUMBERS 일치 확인(2026-09-03 재생성분): 국내 1,160/1,235 = **93.9%** · 해외 1,356/5,972 = **22.7%**.
🔴 국내 모수 주의 — '1,160/1,780 = 65.2%' 로 쓰지 말 것. 안 붙는 620건은 ETN 545(구성종목 개념 없음) + 판매종료 ETF 75건이라 유효 모수는 ETF 1,235다(`external_join.coverage` 주석 확정).

수집·적재 4단 (적재 Flow 도해용):

```bash
python scripts/fetch_etf_holdings.py        # 국내: KRX 공시 구성종목 → 75,859행
python scripts/fetch_overseas_holdings.py   # 해외: SEC EDGAR NPORT-P → 906,848행
python scripts/load_external_holdings.py    # ext_etf_holdings · ext_ovs_etf_holdings 적재
python scripts/build_ontology.py            # KG 재생성 + V1~V7 검증 게이트 + coverage report
```

---

## §B. 온톨로지 엔지니어링 — ETF (→ 2.2.3) — 3쪽

### B.0 도입 (3줄)

> ETF 도메인은 테이블이 둘이다 — 국내 ETF 와 해외 ETF. 겉보기엔 같은 상품군이지만 데이터 사정은 꽤 다르다. 국내에는 위험등급이 있는데 해외에는 그 컬럼 자체가 없고, 국내는 운용사·지수 같은 정보가 컬럼 두 개에 이중으로 들어 있다(원천이 둘이라서다). **이 비대칭을 그대로 드러내는 것**이 ETF 절의 설계 포인트다 — 없는 것을 있는 척하지 않고, 두 벌인 것은 두 벌이라고 선언했다.
>
> 결정 하나가 온톨로지 전체 구조를 정했다. 두 테이블 모두 ETN(상장지수증권)이 섞여 있다 — 국내 545건, 해외 65건. ETN 은 ETF 와 달리 증권사가 발행하는 채무증권이라 성격이 다른 상품이다. 그래서 "국내ETF 테이블 ⊂ ETF" 처럼 테이블을 상품 종류 밑에 두면 ETN 545건까지 ETF 로 단정하는 모순이 생긴다. 결론: **테이블(데이터 출처)과 상품 종류(ETF/ETN)는 별개의 축**으로 분리하고, 종류 판별은 컬럼(`pd_grp_no`)이 맡는다.

### B.1 구조도 (그림 B-2) — 국내·해외 좌우 대칭, 가운데 공유 개체

```mermaid
flowchart LR
  DE["fp:DomesticETF<br/>1,780행 · 98컬럼<br/>ETF 1,235 / ETN 545 (pd_grp_no)<br/>query_rules 54 · ABSENT 3"]
  OE["fp:OverseasETF<br/>6,037행 · 49컬럼<br/>ETF 5,972 / ETN 65 (cu_etn_yn)<br/>query_rules 27 · ABSENT 2"]
  subgraph HUB[공유 개체 — A 와 같은 순서]
    ORG[Organization]; CG[CreditGrade]; RG["RiskGrade<br/>국내 1~6"]; AC[AssetClass]; IDX["Index<br/>변형→정본 closure"]; REG["Region<br/>국가⊂권역⊂글로벌"]; CTY[Country]; CUR[Currency]; SEC["Security<br/>ext_* 경유"]; FND[Fund]; FA[FundAttribute]
  end
  DE == "cu_fund_mgmt_co (99) / ref_fund_mgmt_co (29)" ==> ORG
  DE == "ref_base_index (904) / cu_base_index (19)" ==> IDX
  DE == "wu_inv_rgn (11) / ref_geo_focus (23)" ==> REG
  DE == "wu_inv_ast_type (9) / ref_ast_type (7)" ==> AC
  DE -- "pd_risk_cd / pd_risk_nm (6)" --> RG
  DE -- "pd_curr_cd (1)" --> CUR
  DE -- "ext_etf_holdings (10,154)" --> SEC
  DE -. "⊘ 신용등급 없음" .-> CG
  ORG <-- "cu_fund_mgmt_co (382)" --- OE
  IDX <-- "cu_base_index (1,848)" --- OE
  REG <-- "wu_inv_rgn (59)" --- OE
  AC <-- "wu_inv_ast_type (6)" --- OE
  CUR <-- "pd_trd_ccy (1)" --- OE
  SEC <-- "ext_ovs_etf_holdings (31,117)" --- OE
  RG <-. "⊘ 위험등급 컬럼 자체 없음 → HCX 0회 기각" .- OE
  CG <-. "⊘" .- OE
  DE ~~~ CTY; DE ~~~ FND; DE ~~~ FA
```

이중선(═) = 원천 이원화(국내에만 4개). 하단 주석: 시계열 부재 `hasHoldingsHistory`·`hasNavHistory`(국내). 상단에 `fp:ETF ⟂ fp:ETN` 밴드를 얹고 `pd_grp_no`/`cu_etn_yn` 으로 판별한다는 화살표를 그린다.

| 연결 | 국내 컬럼 (값 수) | 해외 컬럼 (값 수) | 비고 |
| :-- | :-- | :-- | :-- |
| Organization | `cu_fund_mgmt_co` 99 / `ref_fund_mgmt_co` 29 | `cu_fund_mgmt_co` 382 | 운용사(hasManager). 구상호·후계 법인 슬롯 |
| Index | `ref_base_index` 904 / `cu_base_index` 19 | `cu_base_index` 1,848 | TR/CR/NR 변형 → 정본 |
| Region | `wu_inv_rgn` 11 / `ref_geo_focus` 23 | `wu_inv_rgn` 59 | 한글·영문 이원화 |
| AssetClass | `wu_inv_ast_type` 9 / `ref_ast_type` 7 | `wu_inv_ast_type` 6 | |
| RiskGrade | `pd_risk_cd`/`pd_risk_nm` 6 (**1~6**) | **⊘** | 🔴 주최 자료 예시는 `1~5` 이나 국내ETF 실측은 **1~6** — 6등급(매우낮은위험) 21건이 실재해 1~5 로 제약하면 차단된다. 채권(0~6)과 함께 `range_by_table` 이 테이블별로 선언한다 |
| Currency | `pd_curr_cd` 1 | `pd_trd_ccy` 1 | EUR 등 상수 게이트 |
| Security | `ext_etf_holdings` 10,154 | `ext_ovs_etf_holdings` 31,117 | holds = ext 테이블 |
| ⊘ CreditGrade | ⊘ | ⊘ | ETF 는 발행사 신용등급 없음 |

### B.2 결함 → 선언 (6건 채택) — `../proposal/ontology_engineering_etf.md` §2 의 8건에 아래 세 줄을 보강

여섯 건 모두 같은 이야기 구조다: **데이터가 이렇게 생겨서(결함) → 이렇게 선언했고(층) → 실행 중 어느 단계가 그 선언을 읽으며(런타임) → 실제로 이런 사고를 막았다(실측)**. 표의 '층'은 3층 구조를 가리킨다 — 1층 값 사전(어떤 표기가 어떤 실제 값인지), 2층 규칙 문서(질의를 어떻게 짜야 하는지), 3층 게이트(아예 못 하게 막는 것). 실측 사례의 probe ID 는 전부 `eval/` 평가셋에서 재실행해 볼 수 있다. 상세 템플릿은 `04_도메인_채권.md` §B.2 와 동일.

| # | 기존 원고 | 층 | 런타임에서 | 실측 사례 (probe ID·응답 — 채움 완료 9/3) |
| :-: | :-- | :-: | :-- | :-- |
| 1 | 2-1 ETN 545건 혼입 → `disjointWith` + 축 분리 | 선언·2 | Plan 이 `ETF만: pd_grp_no='ETF'` 규칙을 always_on 주입 | **ETF-D-025** — "인버스 ETF 3개"(8/31 실측)가 규칙 누락 시 1위에 ETN(KB 블룸버그 인버스2X 천연가스선물 ETN)을 냈다. 인버스 235건 중 189건(80%)이 ETN — 규칙 도입 후 ETF 46건만 응답 |
| 2 | 2-2 해외 위험등급 컬럼 부재 → ABSENT | 3 | Gate `absent_in` — HCX 0회 기각 + 대체 안내 | "위험등급 낮은 해외ETF" → 기각 응답 |
| 3 | 2-3 총보수 유효 67건, 0=미입력 → `보수유효` + 모수 명시 + **적용 범위** | 2 | Plan 규칙 + 조립이 모수 병기 | ETF-O-020(8/31): 규칙 없이는 0값 419건이 "가장 저렴" 도배. 🔴 반대 방향도 실측 — **ETF-D-036**(9/2): 이 조건이 개수 집계에 **과잉 적용**돼 삼성 227개가 18개로. "보수를 묻지 않은 질의에는 걸지 않는다" 적용 범위 명시로 해소(재검증 9/3 ◎). 규칙엔 조건만이 아니라 **적용 범위와 반례**가 함께 있어야 한다는 교훈의 대표 사례 |
| 4 | 2-5 레버리지 부호 소실 → 이름으로 방향, `ABS()` 배수 | 2 | `derivation_rules.inverse_direction` | 상품명 '인버스' 225건 vs 음수 부호 23건 — 부호만 믿으면 90% 소실. 해외도 동형: **ETF-O-033**(9/1) 플래그 단독 조건이 진짜 인버스 8건(QBER·SNK 등)을 누락 → 플래그+배수+이름 합집합 조건으로 확정 |
| 5 | 2-6 지수 표기 불일치 → `fp:Index` 독립 개체 + closure | 1 | Ground 가 변형 표기를 정본 노드로 접지, closure 후손 전개 | `Idx_MSCI_ACWI` 하나에 국내ETF·해외ETF·펀드 — **2.2.5 통합 증거로 리드가 인용** |
| 6 | 2-7·2-8 지역 삼중 표기 → Region 계층 / 구성종목 부재 → Security 노드 | 1 | Ground: Security 키 우선순위(티커>cusip>LEI>이름), **이름만 같으면 병합 금지**(삼성전자↔삼성전기) | 공식 예시 #3 캠브리콘 — Ground 가 표기 **6종**(ticker '688256 C1' · constituent · isin · holding_nm 2종 · cusip)을 한 노드로 내려줌(9/3 서버 재검증 trace, §C 원문). 감사: `ref_geo_focus` 0→87% 복구 |

기존 2-4(위험등급 0~6)는 채권 절과 겹치므로 한 줄로 줄이고 채권 B.2-2 를 참조한다.

**추가 소재 (본문 또는 부록):** 구성종목 조인 질의에 지역 필터 중첩 금지 — 캠브리콘 재검증(9/3)에서 `wu_inv_rgn='중국'` 중첩이 16→9건, 잘린 7건 중 5건이 rgn 오분류된 진짜 중국 상품(`7a3632a`) · 원천 지역 오분류 43건 → `지역질의_합집합` `(wu_inv_rgn='미국' OR ref_geo_focus='United States of America')`, 상품명 LIKE 금지('미국달러선물' 9종은 환율상품) · 섹터 질의는 `pd_sect_cd` 금지, `ref_base_index`·상품명·holdings 3축 우회 · 해외 `ISIN 조인 금지`(63종이 2상품에 걸림 — 리드 2.3.3 이 인용) · 티커 `ZZZZ` vs 실재 `ZZZ.O` — 완전 일치만.

### B.3 한계 (3줄)

① 해외 구성종목은 전체의 22.7%만 수집됐다(순자산 큰 상품 위주). 보고 기준일도 8종류로 흩어져 최대 8개월 차이가 난다. 우리가 할 수 있는 것은 답변에 모수와 기준일(`report_date`)을 함께 밝히는 것까지다 — 그 이상은 수집 원천(미국 SEC 의 분기 공시)의 한계다.
② 원천 데이터의 투자지역 오분류 43건은 두 컬럼을 합집합으로 보는 규칙으로 복구했다. 다만 `TIGER 중국소비테마`처럼 **두 컬럼이 모두 틀린** 경우는 컬럼으로는 복구할 방법이 없다. 값을 직접 고치지 않는다는 원칙(§1)의 비용이고, 전수조사 문서에 기록으로 남겼다.
③ "레버리지"의 경계(배수 절대값 >1)가 인버스2X 상품 98종을 함께 잡는 문제는 업무 정의가 필요한 사안이라 미확정으로 남겼다. 빼는 대신 "인버스가 섞여 있다"고 답변에 밝히는 방식으로 운용한다.

---

## §C. 기능 흐름도 — ETF (→ 4.2) — 1쪽

**질의**: 공식 예시 #3 *"캠브리콘이 편입된 중국 반도체 ETF를 알려줘"*

이 한 문장이 어려운 이유부터 보자. 캠브리콘은 중국 상장사라 우리 데이터 안에서 **여섯 가지 표기**로 흩어져 있다 — 본토 티커(`688256 C1`), 영문 사명 두 형태, ISIN, CUSIP…. 게다가 "어느 ETF 가 이 회사를 담고 있는가"는 마스터 테이블에 없고 외부 수집한 구성종목 테이블에만 있다. 즉 표기 정규화, 구성종목 조인, 교차질의 판정이 전부 한 질의에 걸린다. (템플릿 1안은 예시 #5 에코프로였으나, 2026-09-03 현행 배포에서 받은 **실제 trace 원문**이 있는 캠브리콘으로 확정 — 대안 허용 조항.)

### 실제 think_trace (2026-09-03 서버 응답 원문 발췌)

```
2. [Route] 상품군 — domestic_etfs, overseas_etfs · 근거: 머리명사 ETF · 값 ['반도체', '중국']
3. [Ground] KG 개체 매핑 — '캠브리콘' → Sec_m_cambricon (Security) [+후손 3]
   → ext_etf_holdings.ticker='688256 C1' · constituent='Cambricon Technologies Corp Ltd'
   · ext_fund_holdings.isin='CNE1000041R8' · holding_nm 2종 · ext_ovs_etf_holdings.cusip='Y10823105'
   / '중국' → Region_China [+후손 1: Region_HongKong] → wu_inv_rgn='중국' · ref_geo_focus='China' …
4. [Gate] 통과 — 교차질의(구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
7. [Plan] SQL — … JOIN ext_etf_holdings ON etf_code = pd_itm_no WHERE constituent LIKE '%Cambricon%' …
9. [Execute] 9행 조회
```

| 단계 | 이 질의에서 일어나는 일 | 읽는 온톨로지 요소 |
| :-- | :-- | :-- |
| Route | "ETF" 머리명사 + 값('반도체'·'중국') → 국내·해외 병행 | 라우팅 어휘(자동 생성) |
| Ground | '캠브리콘' 이 **표기 6종**(중국 본토 티커·영문 사명 2형·ISIN·CUSIP)을 가진 한 Security 노드로 접지 — 사용자는 어느 표기도 몰라도 된다 | 1층 Security + alias |
| Gate | ext_* 조인 허용 판정 + 조인키 짝 주입(`etf_code = pd_itm_no`) | 3층 + external_join |
| Plan | KG 매핑 값을 그대로 WHERE 에 사용 — 문자열 유추 없음 | 2층 규칙 |
| 검증 | 테이블 화이트리스트 · ext↔마스터 짝 검사 · WHERE 값 사전 대조 | 3층 |
| 실행·조립 | 구성종목 JOIN → 국내 9종 응답 | answer_rules |

**이 질의는 처음부터 성공하지 않았다** — 실패를 세 번 고쳐서 여기까지 왔고, 그 과정이 곧 설계 근거다.

- **1차 실패 (9/1)**: 시스템이 자산군 컬럼에서 '반도체'를 찾았다. 그런 값은 없다 — 자산군은 주식·채권 같은 큰 분류지 섹터가 아니다. 결과 **0건**. → 섹터는 상품명·지수명·구성종목 3축으로만 찾는다는 규칙(`섹터테마질의`)이 여기서 나왔다.
- **2차 실패**: 규칙을 고쳐도 값 사전(KG)에 캠브리콘의 국내 티커 표기가 아예 없었다 — 접지(질문 속 이름을 DB 실제 값으로 바꿔 다는 단계)가 빈손으로 끝났다. → 코드북 감사로 종목 9개·852행을 복구해 DB 에 실었다.
- **3차 (9/3)**: 접지·조인은 성공했지만 지역 필터가 겹쳐 16건이 9건으로 잘렸다 — 잘린 것 중 5종이 지역 컬럼이 오분류된 **진짜 중국 상품**이었다. → "구성종목 근거가 이미 있으면 지역 필터를 겹치지 않는다"를 규칙에 보강했다. - **종결 (9/4)**: 보강 규칙이 배포된 서버에서 **14건으로 회복**했고, 1위(RISE 차이나AI반도체TOP4Plus, 편입비중 13.25%)가 정답지와 비중·순위까지 일치했다. 남은 차이 2건은 글로벌 로봇 ETF 라 "중국 반도체"라는 질문 취지상 빠지는 쪽이 자연스럽다. 규칙층(yaml)과 결정층 가드(기본모수 기계 주입·모수 한정 고지)가 함께 작동해 닫힌 사례다.

## §D. 현업 적용 지점 (→ 5.2) — 1단락

**예시 문장:**
> 운용사 합병·상호 변경은 `fp:formerName`·`fp:successor` 슬롯으로 흡수되므로 "구상호로 물어도 현재 운용사로 답하고 그 사실을 밝힌다." 원천의 지역 오분류는 값을 고치지 않고 규칙으로 우회하되 답변 근거에 드러나므로, 챗봇이 마스터 데이터 정비의 입력이 된다.

> 구성종목 기준 탐색은 상품명 기반 탐색과 **답 자체가 다르다.** 실측 대조(8/30): 시판 챗봇에 "삼성전자를 가장 많이 편입한 ETF"를 물으면 이름에 '삼성전자'가 든 상품('KODEX 삼성전자채권혼합', 실제 비중 28.6%)을 1위로 답한다. 구성종목을 실제로 열어 보면 1위는 'KODEX 삼성전자단일종목레버리지' — 비중 96.6%다. 테마 노출도를 이름이 아니라 보유 비중으로 재는 것, 이것이 이 온톨로지가 상품 기획·마케팅 현업에 주는 즉물적 가치다.

---

## §E. 부록 ETF분

### E.1 ttl 원문 (부록 A) — `etf_kr.ttl` · `etf_gl.ttl` 스키마부 그대로

```turtle
# etf_kr.ttl
fp:DomesticETF rdfs:subClassOf fp:Product ; rdfs:comment "SQLite 테이블 domestic_etfs"@ko .
fp:aum a owl:DatatypeProperty ; rdfs:domain fp:DomesticETF ; rdfs:range xsd:decimal ;
    rdfs:comment "순자산총액 — du_last_aum, KRW. 해외ETF(USD)와 통합 정렬 금지"@ko .
fp:leverageMultiple a owl:DatatypeProperty ; rdfs:domain fp:DomesticETF ; rdfs:range xsd:decimal ;
    rdfs:comment "레버리지 배수 — cu_lev_fector. 2차에서 부호 소실: 방향은 상품명 '인버스' 로 판정"@ko .
fp:riskGradeValue_DomesticETF rdfs:subPropertyOf fp:riskGradeValue ; rdfs:domain fp:DomesticETF ;
    rdfs:range [ a rdfs:Datatype ; owl:onDatatype xsd:integer ;
                 owl:withRestrictions ( [ xsd:minInclusive 1 ] [ xsd:maxInclusive 6 ] ) ] .

# etf_gl.ttl
fp:OverseasETF rdfs:subClassOf fp:Product ; rdfs:comment "SQLite 테이블 overseas_etfs"@ko .
fp:ForeignETF rdfs:subClassOf fp:ETF ; rdfs:comment "규격 p.9 예시 클래스 — OverseasETF 중 pd_grp_no='ETF' 5,972건"@ko .
fp:expenseRatio a owl:DatatypeProperty ; rdfs:domain fp:ETF ; rdfs:range xsd:decimal ;
    rdfs:comment "총보수(%) — cu_charge_rt. 국내ETF 는 유효 67건뿐(0=미입력)"@ko .
```
(`common.ttl` 의 `fp:ETF owl:disjointWith fp:ETN` 과 축 분리 주석은 리드가 부록 A 공통부에 수록)

### E.2 ABSENT 표 (부록 A)

| 테이블 | 속성 | 사유 | 대체 |
| :-- | :-- | :-- | :-- |
| DomesticETF | `hasCreditGrade` | ETF 는 발행사 신용등급 없음 — RiskGrade 와 별개 축 | — |
| DomesticETF | `hasHoldingsHistory` | 구성종목 1시점 | `ext_etf_holdings` |
| DomesticETF | `hasNavHistory` | 시세·기준가 단일 스냅샷 | — |
| OverseasETF | `hasCreditGrade` | 신용등급 컬럼 없음 | — |
| OverseasETF | `hasRiskGrade` | 위험등급 컬럼 자체 없음 → HCX 0회 기각 | — |

### E.3 yaml 발췌 (부록 B) — 국내 54 · 해외 27 중 대표

```yaml
# domestic_etfs.yaml
query_rules:
  ETF만: pd_grp_no = 'ETF'
  보수유효: cu_charge_rt > 0 AND pd_grp_no = 'ETF' — 0(=미입력)·NULL 1,713행이라 조건 없이 ASC 정렬하면 미입력 행이 상위
  편입비중상위: "○○를 가장 많이 편입한 ETF" 는 상품명이 아니라 ext_etf_holdings JOIN 후 weight_pct 정렬
  섹터테마질의: pd_sect_cd 사용 금지 — ref_base_index·상품명·holdings 3축 우회, 근거 축을 답변에 밝힌다
  수익률정상: <기간 컬럼> > -100 AND IS NOT NULL — -100 센티넬 1y 110건 전건 du_clpr=0 동반
clarify:
  존재하지_않는_개체: 정확 일치가 없으면 답하지 않는다. 유사 후보는 버리지 말고 역질문으로 제시 (KODEX AI로봇 → KODEX 로봇액티브·글로벌로봇 후보)

# overseas_etfs.yaml
query_rules:
  ISIN조인금지: pd_isin_cd·pd_lipper_id 는 단독 조인 키로 쓰지 않는다 — 63종이 2개 상품에 걸림. 키는 pd_itm_no
  레버리지: cu_lev_fector IS NOT NULL AND ABS(cu_lev_fector) <> 1 — NULL 5,136건(85%)은 미수록이지 1배 확정이 아님
gate_constants: (pd_trd_ccy 등 상수 컬럼 — "EUR 거래 해외ETF" 0.5s 기각)
```

```yaml
# domestic_etfs.yaml — derivation_rules (컬럼을 만들지 않고 규칙으로 선언)
derivation_rules:
  inverse_direction:
    규칙: "CASE WHEN pd_abrv_nm LIKE '%인버스%' THEN 'Inverse' ELSE 'Long' END"
    근거: 2차 배포에서 cu_lev_fector 부호 소실 — 상품명 '인버스' 225건 vs 음수 22건.
          부호 있는 22건은 OR 로 추가 포착 (pd_abrv_nm LIKE '%인버스%' OR cu_lev_fector < 0)

# domestic_etfs.yaml — external_join (구성종목 조인 계약)
external_join:
  ext_etf_holdings:
    key: "ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no"
    as_of: "2026-08-21"    # 전건 단일 · 마스터 기준일 대비 1일 전
    coverage: 유효 모수는 ETF 1,235 (ETN 545 는 구성종목 개념 없음 · 판매종료 75 제외)

# overseas_etfs.yaml — external_join
external_join:
  ext_ovs_etf_holdings:
    # 🔴 ISIN 조인 금지 — 실증: FILL.K 를 ISIN 조인하면 다른 ETF 의 구성종목 69행이 붙는다
    key: "ext_ovs_etf_holdings.etf_ticker = replace(replace(pd_itm_no,'.K',''),'.O','')"
```

### E.4 값 수 표 (부록 C, 매트릭스 국내·해외 열) — §B.1 표 그대로. ▶ 조판 직전 재실측.

---

## 제출 전 체크

> 2026-09-04 기계 검증 완료. 근거는 각 줄 끝에 적었다.

- [x] 기존 원고 8건에 층·런타임·실측 세 줄이 붙었고, 본문은 6건으로 압축됐다 — `26_ETF_최종원고.md` 소제목 ①~⑥
- [x] 그림 B-2 가 국내·해외 대칭이고 개체 순서가 그림 A 와 같다 — HUB 11종(ORG·CG·RG·AC·IDX·REG·CTY·CUR·SEC·FND·FA) · 국내 9간선 / 해외 9간선
- [x] 2-4(0~6)는 채권 절 참조로 줄였다 — 본문은 "채권(0~6)과 함께 `range_by_table`" 한 마디만, 상세는 채권 B.2-2
- [x] 2.1 절 통합본에 채권·펀드 단락이 들어갔다 — `13_데이터절_통합.md` 채권·공모펀드(23,676행/8,969 모수) 단락 확인
- [x] "Federated / 그래프 탐색 / 추론" 0건 · 수치는 NUMBERS — 본문 위반 0(이 파일의 2건은 템플릿 규칙 문장과 이 체크 항목 자체)
- [x] §C 에 실제 think_trace 원문 — 2026-09-03 서버 응답 발췌, `[Ground]` 단계 원문 포함

**남은 것 1건** — E.4 값 수 표는 조판 직전에 재실측한다(§E.4). 그 외 미완 없음.
