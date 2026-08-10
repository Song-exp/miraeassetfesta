# FIBO — Collective Investment Vehicles (펀드 온톨로지 표준)

| 항목 | 내용 |
| :--- | :--- |
| **출처** | EDM Council FIBO, `SEC/Funds/CollectiveInvestmentVehicles.rdf` (master) |
| **URL** | https://github.com/edmcouncil/fibo/blob/master/SEC/Funds/CollectiveInvestmentVehicles.rdf |
| **형식** | OWL 2 DL |
| 🔍 **확인 수준** | **부분 확인** — RDF 원문을 WebFetch 로 가져와 **클래스·오브젝트 속성 전체 목록과 3개 질의에 대한 추출만** 받았습니다. 파일 본문을 직접 통독하지 않았고, 각 클래스의 `rdfs:subClassOf` 공리·제약(restriction)은 확인하지 못했습니다. |
| **우선순위** | 높음 — 우리가 지금 설계 중인 펀드 온톨로지의 직접 선행연구 |

---

## 핵심 발견

### 1. 펀드 클래스(종류형)는 **독립 클래스**로 존재한다

```
FundShareClassUnit
  "the legal structure in which you can purchase part of an investment pool,
   defined by a variety of characteristics like investor type, minimum size of
   investment, distribution type, fee and currency"
```

우리가 `ShareClass`(종류A/C/e…)를 별도 개체로 세우려던 판단과 **일치**합니다.
정의에 **fee·currency·investor type** 이 명시돼 있어, 클래스가 비용 구조 축이라는 도메인 이해도 확인됩니다.

관련 클래스: `AccumulatingShareClass`, `DistributingShareClass`
→ 분배 방식(재투자형/분배형)이 **ShareClass 의 하위 클래스**로 갈립니다.

### 2. 펀드 유형(주식형·채권형)은 **`owl:Class` 하위클래스**다 — 개체가 아니다 ★

```
EquityFund, NoteFund   →  owl:Class (CollectiveInvestmentVehicle 하위)
```

즉 *"주식형"* 은 값이 아니라 **클래스 자체**입니다.
`펀드 —ofType→ 주식형` 이 아니라 `EquityFund ⊑ Fund` 이고, 특정 펀드는 `EquityFund` 의 인스턴스입니다.

동시에 분류 체계 자체를 다루는 클래스도 따로 있습니다:

```
FundClassification, FundClassificationScheme
```

→ **분류 체계를 온톨로지 안에서 1급 시민으로 다룹니다.** 여러 기관의 분류 코드(우리의 `kofia_fd_ccd`)를
표현할 자리가 여기입니다.

### 3. 관계 속성 (원문에서 확인된 이름)

| 개념 | FIBO 속성 |
| :--- | :--- |
| 운용사 | `hasManagementCompany` |
| 수탁사 | `hasDepository` (클래스 `FundDepositary`) |
| 클래스/수익증권 | `hasTradableUnit` |
| 포트폴리오 | `hasPortfolio` (클래스 `FundPortfolio`) |
| 벤치마크 | `definesBenchmark` (클래스 `PortfolioBenchmark`) |
| 위험수준 | `hasIntendedRiskLevel` (클래스 `RiskLevel`) |
| 투자전략 | `hasInvestmentStrategy` (클래스 `InvestmentStrategy`) |
| 배당/분배 정책 | `hasFundPolicy` (`FundDistributionPolicy`, `FundDividendPolicy` …) |

**역할별 조직이 전부 별도 클래스입니다:** `FundAccountant`, `FundDepositary`, `FundDistributor`,
`FundTransferAgent`, `FundOrderDesk`, `FundSupervisoryAuthority`, `FundsProcessingParty`

### 4. 투자 전략이 축별로 쪼개져 있다

```
InvestmentStrategy
  ├ AssetClassStrategy      (자산군)
  ├ SectorStrategy          (섹터)
  ├ JurisdictionStrategy    (지역·관할)
  ├ CurrencyStrategy        (통화)
  └ OrganizationStrategy
```

→ 우리가 `Region`·`Currency`·`FundType` 을 평평하게 나열하려던 것과 달리,
FIBO 는 **"전략(Strategy)" 이라는 상위 개념 아래 축별 하위 클래스**로 묶습니다.

---

## ▶ 우리 프로젝트에 적용

### 🚫 적용 가능성: **조건부**

**조건:** FIBO 전체(2,446 클래스)를 도입하는 것이 아니라, **클래스 층위 결정 원칙과 명명만 차용**할 때.

| 우리 상황 | FIBO 방식 | 적용 판단 |
| :--- | :--- | :--- |
| `ShareClass` 를 별도 개체로 | `FundShareClassUnit` 존재 | ✅ **그대로 채용** |
| `FundType`(주식형·채권형…) 을 "분류값 개체"로 | `owl:Class` 하위클래스 | 🔴 **우리 모델 수정 필요** |
| `Region`·`Currency` 를 평면 나열 | `*Strategy` 하위로 묶음 | ⚠️ 검토 — 우리 데이터는 전략 서술이 없어 과할 수 있음 |
| 운용사·수탁사 별도 노드 | `hasManagementCompany` / `hasDepository` | ✅ 채용, 속성명도 차용 가능 |
| `kofia_fd_ccd` 20자리 분류코드 | `FundClassificationScheme` | ✅ 표현할 자리가 있음 |

**불가 요소:** FIBO 는 포트폴리오·수수료·환매조건을 전제로 설계돼 있는데
(`FundPortfolio`, `performanceFee`, `redemptionFee`, `minimumSubscriptionAmount` …),
**우리 데이터엔 보수·포트폴리오·환매조건이 전부 없습니다.** 해당 가지는 통째로 비게 됩니다.
→ FIBO 를 그대로 가져오면 빈 클래스가 대부분인 온톨로지가 됩니다.

### 결론

**FIBO 를 임포트하지 말고, 층위 결정 원칙만 가져옵니다.**
평가 대상은 우리 데이터로 답할 수 있는 질의이지 표준 준수 여부가 아니며,
빈 클래스가 많은 온톨로지는 오히려 설계 의도를 흐립니다.

---

## ⚠️ 한계

- RDF 원문을 직접 통독하지 않았습니다. 클래스·속성 **목록**은 확보했으나
  각 클래스의 `subClassOf` 계층과 `owl:Restriction` 은 미확인입니다.
- 따라서 *"EquityFund 가 CollectiveInvestmentVehicle 의 하위"* 라는 진술은
  추출 결과에 의존하며, 원문 공리로 직접 확인하지 못했습니다.
- 한국 공모펀드의 클래스 체계(A/C/e/P)가 `FundShareClassUnit` 에 어떻게 매핑되는지는
  FIBO 에 규정이 없습니다 — 국내 관행이라 우리가 정의해야 합니다.
