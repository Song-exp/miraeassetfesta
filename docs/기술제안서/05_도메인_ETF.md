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

▶ 채울 것: 국내 커버리지 93.9%·해외 22.7% 가 NUMBERS 와 일치하는지. 수집 스크립트 이름과 실행 명령 1줄(적재 Flow 도해용).

---

## §B. 온톨로지 엔지니어링 — ETF (→ 2.2.3) — 3쪽

### B.0 도입 (3줄)

> ETF 는 **한 온톨로지 안에 두 테이블**이 있는 도메인이다. 국내는 공유 개체 5종에, 해외는 4종에 닿는다. 국내는 같은 개체에 두 컬럼이 닿는 경우가 넷(원천 이원화)이고, 해외는 위험등급 컬럼이 아예 없다. 이 **비대칭이 곧 설계 포인트**다. 그리고 두 테이블 모두 ETN 이 섞여 있어(545·65건) 테이블 클래스를 `fp:ETF` 하위로 두지 못했다 — 이 결정이 온톨로지 전체의 축 분리(테이블 축 / 상품종류 축)를 만들었다.

### B.1 구조도 (그림 B-2) — 국내·해외 좌우 대칭, 가운데 공유 개체

```mermaid
flowchart LR
  DE["fp:DomesticETF<br/>1,780행 · 98컬럼<br/>ETF 1,235 / ETN 545 (pd_grp_no)<br/>query_rules 44 · ABSENT 3"]
  OE["fp:OverseasETF<br/>6,037행 · 49컬럼<br/>ETF 5,972 / ETN 65 (cu_etn_yn)<br/>query_rules 23 · ABSENT 2"]
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
| RiskGrade | `pd_risk_cd`/`pd_risk_nm` 6 (**1~6**) | **⊘** | |
| Currency | `pd_curr_cd` 1 | `pd_trd_ccy` 1 | EUR 등 상수 게이트 |
| Security | `ext_etf_holdings` 10,154 | `ext_ovs_etf_holdings` 31,117 | holds = ext 테이블 |
| ⊘ CreditGrade | ⊘ | ⊘ | ETF 는 발행사 신용등급 없음 |

### B.2 결함 → 선언 (6건 채택) — `../proposal/ontology_engineering_etf.md` §2 의 8건에 아래 세 줄을 보강

기존 원고의 각 건에 **층 / 런타임에서 / 실측 사례** 세 줄을 덧붙인다. 템플릿은 `04_도메인_채권.md` §B.2 와 동일.

| # | 기존 원고 | 층 | 런타임에서 | 실측 사례 후보 (▶ probe ID·응답 채우기) |
| :-: | :-- | :-: | :-- | :-- |
| 1 | 2-1 ETN 545건 혼입 → `disjointWith` + 축 분리 | 선언·2 | Plan 이 `ETF만: pd_grp_no='ETF'` 규칙을 always_on 주입 | "ETF 중 총보수 낮은 것" 에 ETN 이 안 섞임 |
| 2 | 2-2 해외 위험등급 컬럼 부재 → ABSENT | 3 | Gate `absent_in` — HCX 0회 기각 + 대체 안내 | "위험등급 낮은 해외ETF" → 기각 응답 |
| 3 | 2-3 총보수 유효 67건, 0=미입력 → `보수유효` + 모수 명시 | 2 | Plan 규칙(triggered: '보수'·'수수료') + 조립이 모수 병기 | 2026-08-31 paired 실측 ETF-O-020: 규칙 없이는 0값 419건이 "가장 저렴" 도배 |
| 4 | 2-5 레버리지 부호 소실 → 이름으로 방향, `ABS()` 배수 | 2 | `derivation_rules.inverse_direction` | "인버스 ETF" 163건이 양수 배수로도 잡힘. 한계: `ABS>1` 경계 |
| 5 | 2-6 지수 표기 불일치 → `fp:Index` 독립 개체 + closure | 1 | Ground 가 변형 표기를 정본 노드로 접지, closure 후손 전개 | `Idx_MSCI_ACWI` 하나에 국내ETF·해외ETF·펀드 — **2.2.5 통합 증거로 리드가 인용** |
| 6 | 2-7·2-8 지역 삼중 표기 → Region 계층 / 구성종목 부재 → Security 노드 | 1 | Ground: Security 키 우선순위(티커>cusip>LEI>이름), **이름만 같으면 병합 금지**(삼성전자↔삼성전기) | 공식 예시 #3 캠브리콘 표기 6종 합집합 / 감사: `ref_geo_focus` 0→87% |

기존 2-4(위험등급 0~6)는 채권 절과 겹치므로 한 줄로 줄이고 채권 B.2-2 를 참조한다.

**추가 소재 (본문 또는 부록):** 원천 지역 오분류 43건 → `지역질의_합집합` `(wu_inv_rgn='미국' OR ref_geo_focus='United States of America')`, 상품명 LIKE 금지('미국달러선물' 9종은 환율상품) · 섹터 질의는 `pd_sect_cd` 금지, `ref_base_index`·상품명·holdings 3축 우회 · 해외 `ISIN 조인 금지`(63종이 2상품에 걸림 — 리드 2.3.3 이 인용) · 티커 `ZZZZ` vs 실재 `ZZZ.O` — 완전 일치만.

### B.3 한계 (3줄)

▶ 채울 것. 후보: ① 해외 구성종목 22.7%, 보고기준일 시차 ② 원천 지역 오분류 잔존(`TIGER 중국소비테마` 양쪽 다 오분류 — 컬럼으로 복구 불가) ③ 레버리지 `ABS>1` 경계 미확정(인버스2X 98/308) ④ 고아 쓰레기값 3종(`cu_fund_mgmt_co='.'` 등)은 기록만.

---

## §C. 기능 흐름도 — ETF (→ 4.2) — 1쪽

**질의**: 공식 예시 #5 *"에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인"* (3-hop 이 값 접지로 풀리는 사례. 대안: 예시 #3 캠브리콘)

```bash
# eval/probe_etf_flow.txt:  ETF-FLOW-1<TAB>에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘
export PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe eval/probe_server.py eval/probe_etf_flow.txt -o eval/probe_etf_flow.json
```

| 단계 | 이 질의에서 일어나는 일 | 읽는 온톨로지 요소 |
| :-- | :-- | :-- |
| Route | "ETF" 머리명사 → `domestic_etfs` (+ 교차 여부 판정) | 라우팅 어휘 |
| Ground | "에코프로" → `Sec_m_*` 정본 노드, `_asks_subsidiaries` 감지 → `subsidiaryOf` 1단 전개: 에코프로비엠·에코프로머티리얼즈·에코프로에이치엔 (DART 2025 사업보고서 근거) | 1층 Security + edge `subsidiaryOf` 3 |
| Gate | 부재·enum·상수 해당 없음 → 통과 | 3층 |
| Plan | KG 개체 매핑에 자회사 3사의 `ext_etf_holdings` 실제 값 주입, 조인키 `etf_code = pd_itm_no`, 규칙 `편입비중상위`·`ETF만`·`수익률정상` | 2층 + 조인키 |
| 검증 | WHERE 리터럴 ↔ 값 사전, JOIN 템플릿 준수 | 3층 |
| 실행 | holdings JOIN → `du_last_aum` 내림차순 | — |
| 조립 | 상위 상품 + 위험요인은 ▶ (마스터에 위험요인 텍스트가 있는지 확인 — 없으면 ABSENT 안내로 답하는 것이 정답) | answer_rules |

▶ 채울 것: 실제 think_trace 원문, answer 첫 3줄, 자회사 전개 없이 답했을 때와의 차이 한 줄(전개로 답이 통째로 바뀐 사례).

---

## §D. 현업 적용 지점 (→ 5.2) — 1단락

**예시 문장:**
> 운용사 합병·상호 변경은 `fp:formerName`·`fp:successor` 슬롯으로 흡수되므로 "구상호로 물어도 현재 운용사로 답하고 그 사실을 밝힌다." 원천의 지역 오분류는 값을 고치지 않고 규칙으로 우회하되 답변 근거에 드러나므로, 챗봇이 마스터 데이터 정비의 입력이 된다.

▶ 한 문장 더: 상품 기획·마케팅에서 "구성종목 기준 테마 ETF 탐색"이 상품명 기반 탐색과 어떻게 다른지.

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

### E.3 yaml 발췌 (부록 B) — 국내 44 · 해외 23 중 대표

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

▶ 채울 것: `derivation_rules.inverse_direction` 원문, `external_join` 블록 원문.

### E.4 값 수 표 (부록 C, 매트릭스 국내·해외 열) — §B.1 표 그대로. ▶ 조판 직전 재실측.

---

## 제출 전 체크

- [ ] 기존 원고 8건에 층·런타임·실측 세 줄이 붙었고, 본문은 6건으로 압축됐다
- [ ] 그림 B-2 가 국내·해외 대칭이고 개체 순서가 그림 A 와 같다
- [ ] 2-4(0~6)는 채권 절 참조로 줄였다 (중복 서술 금지)
- [ ] 2.1 절 통합본에 채권·펀드 단락이 들어갔다
- [ ] "Federated / 그래프 탐색 / 추론" 0건 · 수치는 NUMBERS
- [ ] §C 에 실제 think_trace 원문
