# 🔎 검수 B — Index→Region / AssetClass 규칙 edge 검수 (2026-08-25)

> 대상: `gen_shared_auto.py` 키워드 규칙으로 만든 `coversRegion`·`hasAssetClass` edge. 상품 연결 수(국내ETF `ref_base_index` + 해외 `cu_base_index` + 판매중 펀드 `bmrk_nm` 행수) 상위 150 지수를 눈으로 검수하고, 규칙 보정 + `codebooks/index_axis_override.csv`(라벨 완전일치, 규칙보다 우선) 로 정정했다.
> 표의 '전' = 검수 전 DB(kg_edge) 값, '후' = 보정된 생성기 결과 (full build 는 코디네이터가 수행). `*` = Equity 기본값 폴백(규칙 미적중), `ov` = override 적용.

## 0. 요약

- Index 노드 3172 (수동 21). **수동 노드 21개에 edge 가 아예 없었음** (KOSPI200 2,532상품·MSCI ACWI 726·S&P 500 TR 352 …) → 수동 노드에도 규칙/override 적용.
- coversRegion 미적중 733 → **637** · Equity 기본값(규칙 미적중) 2,121 → **593** (양성 주식 규칙 추가로 '적중' 으로 전환, 기본값은 원자재·통화·디지털자산 등 지역 개념이 없는 지수 위주로 남음)
- override 37건 (수동 노드·한글 약칭·JACI·제로인·DWGRTT·단일종목 등 규칙으로 안 되는 것)

## 1. 규칙 변경 (오탐 원인 → 수정)

| 오탐 | 원인 | 수정 |
| :-- | :-- | :-- |
| `Dow Jones US Large Cap … Stk Mkt` → 한국 | `MK\s*` 가 'Mkt' 에 매치 | `\bMKF?\b` 단어 경계 |
| `Russell 1000/2000/3000`, `Crypto Assets` → 중국 | `SSE` 가 RUSSELL·ASSET 부분문자열 | `\bSSE\b` |
| `Akros Tesla Covered Call` → 한국·채권 | `CALL` 이 콜금리 규칙에 매치 | `(?<!COVERED)\bCALL\b(?!\s*BALANCED)` + 커버드콜은 Alternatives 우선 |
| `S&P 500 Dividend … Yield` → 채권 | `YIELD` | 주식 양성 규칙(DIVIDEND·MINERS·EQUITY…) 을 채권보다 먼저 |
| `MSCI AC Asia Pacific ex Japan` → 일본 | `JAPAN` | `(?<!EX )JAPAN` 가드 + Asia 규칙 순서 |
| `MSCI EAFE` → 유럽 | 임의 매핑 | `Region_GlobalExUS` (선진국 ex US) |
| `NYSE Arca Gold Miners`, `Copper Mining` → 원자재 | GOLD/COPPER | MINERS·MINING·PRODUCERS → Equity 우선 |
| `60% MSCI World/40% US Agg` → 채권 | `/` 형 합성 미인식 | `is_composite` 에 `\d+%…/` 인식 → Mixed |
| `7RCC Bitcoin Carbon Credit` → 채권 | CREDIT | `(?<!CARBON )CREDIT`, 디지털자산 → Alternatives |
| `JP Morgan GBI/EMBI/JACI` → 주식 | 약어 미등록 | GBI·EMBI·JACI → Bond (JACI 는 Asia) |
| `Bloomberg Municipal`, `iBoxx USD`, `ICE BofA Pref` → 지역 없음 | 규칙 없음 | MUNI·IBOXX USD·ICE BofA Core/Pref → US |
| `MSCI Germany/Brazil/…` → 유럽/남미 권역 | 국가 노드 없었음 | region.yaml 국가 노드(8/25) 로 세분화: DAX·GERMANY→Germany, TSX→Canada, ASX→Australia, BSE→India … |
| `MSCI North America` → 미국 | AMERICA | `NORTH AMERICA` 를 US 보다 먼저 → NorthAmerica |
| `KRX300`·`CSI300`·`CSI_500` → 미적중 | 단어 경계 | `KRX\d*`·`CSI[\s_]?\d` |
| S&P 한정어 없는 지수(`S&P Equal Weight`) → 미적중 | US 규칙에서 S&P 제거(ASX·BSE 오탐 방지) | 국가·글로벌 규칙 뒤 폴백 `S&P(?!\s*GSCI)` → US |

## 2. 상위 150 지수 검수표 (상품 연결 수 순)

| # | 지수 | 상품수 | Region 전 → 후 | AssetClass 전 → 후 | 판정 |
| :-: | :-- | --: | :-- | :-- | :-- |
| 1 | KOSPI200 | 2,532 | - → Korea | - → Equity | 정정 (override) [수동노드] |
| 2 | MSCI ACWI CR 50% + 종합채권01Y 50% | 1,570 | - → Global | - → Mixed | 정정 [수동노드] |
| 3 | MSCI ACWI | 726 | - → Global | - → Equity | 정정 [수동노드] |
| 4 | KOSPI200 25% + 종합채권01Y 75% | 527 | Korea → Korea | Mixed → Mixed | OK |
| 5 | MSCI CHINA | 398 | - → China | - → Equity | 정정 [수동노드] |
| 6 | S&P 500 TR | 352 | - → US | - → Equity | 정정 [수동노드] |
| 7 | KAP CD 6개월 90% | 350 | - → Korea | - → MoneyMarket | 정정 (override) [수동노드] |
| 8 | MSCI ACWI CR 25% + 종합채권01Y 75% | 257 | Global → Global | Mixed → Mixed | OK |
| 9 | 종합채권02Y 90% | 257 | Korea → Korea | Bond → Bond | OK |
| 10 | 중소형지수 | 231 | - → Korea | Equity → Equity | 정정 (override) |
| 11 | MSCI ACWI Information Technology | 198 | - → Global | - → Equity | 정정 [수동노드] |
| 12 | MSCI NORTH AMERICA | 190 | - → NorthAmerica | - → Equity | 정정 [수동노드] |
| 13 | MSCI ACWI Health Care | 174 | - → Global | - → Equity | 정정 [수동노드] |
| 14 | 종합채권 1~2년 | 168 | - → Korea | - → Bond | 정정 [수동노드] |
| 15 | S&P 500 CR | 154 | US → US | Equity → Equity | OK |
| 16 | KOSPI200 50% + 종합채권01Y 50% | 152 | Korea → Korea | Mixed → Mixed | OK |
| 17 | 코스피 고배당 50 | 152 | Korea → Korea | Equity → Equity | OK |
| 18 | 제로인 대안투자기대수익지수 | 148 | - → Korea | - → Alternatives | 정정 (override) [수동노드] |
| 19 | 종합채권03Y 90% | 140 | - → Korea | - → Bond | 정정 [수동노드] |
| 20 | DWGRTT 90% | 124 | - → Global | - → RealEstate | 정정 (override) [수동노드] |
| 21 | KOSPI200 10% + 종합채권 01Y 90% | 124 | Korea → Korea | Mixed → Mixed | OK |
| 22 | CALL | 108 | Korea → Korea | Bond → MoneyMarket | 정정 (override) |
| 23 | Bloomberg GLOBAL AGGREGATE(KRW HEDGED) 90% | 105 | Global → Global | Bond → Bond | OK |
| 24 | 국공채02Y 90% | 99 | Korea → Korea | Bond → Bond | OK |
| 25 | S&P 500 | 97 | US → US | Equity → Equity | OK |
| 26 | Bloomberg U.S. Aggregate Bond TR | 92 | - → US | - → Bond | 정정 [수동노드] |
| 27 | MSCI India | 90 | India → India | Equity → Equity | OK |
| 28 | Bloomberg U.S. AGGREGATE 90% | 83 | US → US | Bond → Bond | OK |
| 29 | MSCI ACWI CR 75% + 종합채권01Y 25% | 82 | Global → Global | Mixed → Mixed | OK |
| 30 | MSCI EM (EMERGING MARKETS) | 78 | - → Emerging | - → Equity | 정정 [수동노드] |
| 31 | MSCI EUROPE | 72 | Europe → Europe | Equity → Equity | OK |
| 32 | MSCI ACWI Energy | 65 | Global → Global | Equity → Equity | OK |
| 33 | MSCI AC ASIA PACIFIC ex JAPAN | 64 | Japan → Asia | Equity → Equity | 정정 |
| 34 | KOSPI200 5% + 종합채권 01Y 95% | 59 | Korea → Korea | Mixed → Mixed | OK |
| 35 | CSI 300 LOCAL 90% + CALL 10% | 54 | China → China | Mixed → Mixed | OK |
| 36 | MSCI CHINA A(로컬) | 50 | China → China | Equity → Equity | OK |
| 37 | MSCI WI | 48 | - → Global | Equity → Equity | 정정 (override) |
| 38 | KOSPI200 5% +  회사채I-BBB종합 02Y  95% | 46 | Korea → Korea | Mixed → Mixed | OK |
| 39 | MSCI AC ASIA | 46 | Asia → Asia | Equity → Equity | OK |
| 40 | Rogers International Commodity TR | 44 | - → - | - → Commodity | 정정 (override) [수동노드] |
| 41 | Bloomberg Global High Yield(USD Hedged) 90% | 44 | Global → Global | Bond → Bond | OK |
| 42 | MSCI WI (USD) ×90% + Call ×10% | 44 | - → Global | Mixed → Mixed | 정정 (override) |
| 43 | MSCI RUSSIA | 43 | - → Emerging | Equity → Equity | 정정 (override) |
| 44 | 베트남 호치민(LOCAL) | 43 | Vietnam → Vietnam | Equity → Equity | OK |
| 45 | KRX 300 | 42 | - → Korea | - → Equity | 정정 [수동노드] |
| 46 | MSCI AC Asia ex Japan | 42 | Japan → Asia | Equity → Equity | 정정 |
| 47 | 나스닥 100 | 41 | - → US | Equity → Equity | 정정 (override) |
| 48 | MSCI ACWI  90% + Call 10% | 40 | Global → Global | Mixed → Mixed | OK |
| 49 | MSCI BRIC | 40 | Emerging → Emerging | Equity → Equity | OK |
| 50 | MSCI ACWI (KRW) ×90% + Call ×10% | 38 | Global → Global | Mixed → Mixed | OK |
| 51 | Russell 1000 Growth TR | 37 | China → US | Equity → Equity | 정정 |
| 52 | MSCI CHINA CR 50% + MSCI INDIA CR USD in KRW 50% | 37 | China → China | Mixed → Mixed | OK |
| 53 | MSCI ACWI CR 50% + Bloomberg GLOBAL AGGREGATE(KRW HEDGED) 50% | 36 | Global → Global | Mixed → Mixed | OK |
| 54 | MSCI ACWI Materials | 35 | Global → Global | Equity → Equity | OK |
| 55 | Russell 1000 Value TR | 34 | China → US | Equity → Equity | 정정 |
| 56 | MSCI CHINA A | 33 | China → China | Equity → Equity | OK |
| 57 | 베트남 호치민(KRW) | 32 | Vietnam → Vietnam | Equity → Equity | OK |
| 58 | Topix CR | 30 | Japan → Japan | Equity → Equity | OK |
| 59 | MSCI EAFE NR USD | 30 | Europe → GlobalExUS | Equity → Equity | 정정 |
| 60 | 미국 국채 3개월[원화환산] | 30 | US → US | Bond → Bond | OK |
| 61 | CSI_500_LOCAL | 29 | China → China | Equity → Equity | OK |
| 62 | MSCI CHINA 90% + Call 10% | 29 | China → China | Mixed → Mixed | OK |
| 63 | Russell 3000 TR | 27 | China → US | Equity → Equity | 정정 |
| 64 | MSCI ACWI CR(in KRW) 50% + 종합채권01Y 50% | 27 | Global → Global | Mixed → Mixed | OK |
| 65 | MSCI NORTH AMERICA CR 50% + 종합채권01Y 50% | 27 | US → NorthAmerica | Mixed → Mixed | 정정 |
| 66 | NASDAQ 100 TR | 26 | US → US | Equity → Equity | OK |
| 67 | Russell 2000 TR | 26 | China → US | Equity → Equity | 정정 |
| 68 | KRX 건강산업 | 26 | Korea → Korea | Equity → Equity | OK |
| 69 | MSCI BRAZIL | 26 | LatinAmerica → Brazil | Equity → Equity | 정정 |
| 70 | KOSPI 200 CR | 25 | Korea → Korea | Equity → Equity | OK |
| 71 | MSCI EM (Emerging Markets) NR USD | 25 | Emerging → Emerging | Equity → Equity | OK |
| 72 | MSCI ACWI Financials | 25 | Global → Global | Equity → Equity | OK |
| 73 | S&P 500(KRW) | 23 | US → US | Equity → Equity | OK |
| 74 | 아멕스 금광업체 | 23 | - → US | Equity → Equity | 정정 (override) |
| 75 | MSCI Japan | 22 | Japan → Japan | Equity → Equity | OK |
| 76 | JP Morgan GBI Global | 22 | Global → Global | Equity → Bond | 정정 |
| 77 | MSCI GERMANY | 22 | - → Germany | Equity → Equity | 정정 |
| 78 | MSCI EM ASIA CR 25% + 종합채권01Y 75% | 21 | Emerging → Emerging | Mixed → Mixed | OK |
| 79 | ICE U.S. Treasury 20+ Year Bond TR USD | 20 | US → US | Bond → Bond | OK |
| 80 | MSCI AC World ex USA NR USD | 20 | GlobalExUS → GlobalExUS | Equity → Equity | OK |
| 81 | MSCI AC ASIA PACIFIC | 20 | Asia → Asia | Equity → Equity | OK |
| 82 | MSCI EM EUROPE | 20 | Emerging → Emerging | Equity → Equity | OK |
| 83 | 베트남 호치민 CR 50% + 국공채 01Y 50% | 20 | Vietnam → Vietnam | Mixed → Mixed | OK |
| 84 | MSCI AC World NR USD | 19 | Global → Global | Equity → Equity | OK |
| 85 | JP Morgan EMBI Global Diversified Index(USD) 90% + CALL 10% | 19 | Global → Global | Mixed → Mixed | OK |
| 86 | Bloomberg U.S. High Yield 2% Issuer cap 94% + Call 6% | 18 | US → US | Mixed → Mixed | OK |
| 87 | F-KOSPI 200 | 17 | Korea → Korea | Equity → Equity | OK |
| 88 | Bloomberg Municipal Bond TR | 17 | - → US | Bond → Bond | 정정 |
| 89 | JP Morgan EMBI Global Diversified Index(KRW) 90% + CALL 10% | 17 | Global → Global | Mixed → Mixed | OK |
| 90 | MSCI NORTH AMERICA CR 25% + 종합채권01Y 75% | 17 | US → NorthAmerica | Mixed → Mixed | 정정 |
| 91 | TOPIX CR in KRW | 17 | Japan → Japan | Equity → Equity | OK |
| 92 | ICE U.S. Treasury 7-10 Year TR USD | 16 | US → US | Bond → Bond | OK |
| 93 | NASDAQ 100 CR | 16 | US → US | Equity → Equity | OK |
| 94 | CSI 300 KRW 90% + CALL 10% | 16 | China → China | Mixed → Mixed | OK |
| 95 | JACI IG 90% | 16 | - → Asia | Equity → Bond | 정정 (override) |
| 96 | MSCI ACWI CR 25% + Bloomberg GLOBAL AGGREGATE(KRW HEDGED) 75% | 15 | Global → Global | Mixed → Mixed | OK |
| 97 | 코스피 전기전자 | 15 | Korea → Korea | Equity → Equity | OK |
| 98 | 종합채권 3개월~1년 | 14 | - → Korea | - → Bond | 정정 [수동노드] |
| 99 | Dow Jones Industrial Average CR | 14 | US → US | Equity → Equity | OK |
| 100 | MSCI BRAZIL CR 50% + MSCI RUSSIA CR 50% | 14 | LatinAmerica → Brazil | Mixed → Mixed | 정정 |
| 101 | MSCI CHINA 85% + Call 15% | 14 | China → China | Mixed → Mixed | OK |
| 102 | MSCI EUROPE SMALL CAP | 14 | Europe → Europe | Equity → Equity | OK |
| 103 | MSCI JAPAN VALUE | 14 | Japan → Japan | Equity → Equity | OK |
| 104 | S&P500 90% + Call 10% | 14 | US → US | Mixed → Mixed | OK |
| 105 | KOSPI Composite CR | 13 | Korea → Korea | Equity → Equity | OK |
| 106 | ICE BofA US 3-Month Treasury Bill TR USD | 13 | US → US | Bond → MoneyMarket | 정정 |
| 107 | Bloomberg U.S. High Yeild 2% Issuer cap 90% + Call 10% | 13 | US → US | Mixed → Mixed | OK |
| 108 | MSCI AC ASIA PACIFIC ex JAPAN NR USD 90% + Call 10% | 13 | Japan → Asia | Mixed → Mixed | 정정 |
| 109 | MSCI ACWI INFRASTRUCTURE | 13 | Global → Global | Equity → Equity | OK |
| 110 | MSCI EM CR 50% + 종합채권01Y 50% | 13 | Emerging → Emerging | Mixed → Mixed | OK |
| 111 | 항셍 차이나기업(H) | 13 | China → China | Equity → Equity | OK |
| 112 | ICE BofA US High Yield Constrained TR | 12 | US → US | Bond → Bond | OK |
| 113 | Nifty 50 CR | 12 | India → India | Equity → Equity | OK |
| 114 | S&P Global Infrastructure TR (USD) | 12 | Global → Global | Equity → Equity | OK |
| 115 | S&P Mid Cap 400 TR | 12 | US → US | Equity → Equity | OK |
| 116 | FTSE AW ex US 36% + S&P 500 54% + Call 10% | 12 | US → GlobalExUS | Mixed → Mixed | 정정 |
| 117 | JP Morgan GBI-EM Global Diversified | 12 | Global → Global | Equity → Bond | 정정 |
| 118 | KOSDAQ 70% + KOSPI 30% | 12 | Korea → Korea | Mixed → Mixed | OK |
| 119 | MSCI ACWI CR 50% + Bloomberg GLOBAL AGGREGATE EX-JPY 25% + DW GLOBAL REIT TR 25% | 12 | Global → Global | Mixed → Mixed | OK |
| 120 | MSCI ACWI IT 95% + Call 5% | 12 | Global → Global | Mixed → Mixed | OK |
| 121 | MSCI EM ASIA CR 50% + 종합채권01Y 50% | 12 | Emerging → Emerging | Mixed → Mixed | OK |
| 122 | MSCI EM LATIN AMERICA | 12 | Emerging → LatinAmerica | Equity → Equity | 정정 |
| 123 | MSCI South East Asia(원화환산) 95% + Call 5% | 12 | Asia → Asia | Mixed → Mixed | OK |
| 124 | NYSE FactSet Gbl Atnms Drvng and Elec Vhcl 90% + CALL 10% | 12 | US → Global | Mixed → Mixed | 정정 |
| 125 | Rogers International Commodity TR 90% | 12 | - → - | Commodity → Commodity | OK (override) |
| 126 | S&P500 CR 25% + MSCI EUROPE CR 25% + MSCI JAPAN VALUE 25% + MSCI AC ASIA PACIFIC ex JAPAN CR 25% | 12 | US → US | Mixed → Mixed | OK |
| 127 | 유로 스톡스50 | 12 | - → Europe | Equity → Equity | 정정 (override) |
| 128 | F-USDKRW | 11 | - → - | Currency → Currency | OK (override) |
| 129 | KRX Korea Value-Up CR | 11 | Korea → Korea | Equity → Equity | OK |
| 130 | CSI 500  LOCAL 90% + CALL 10% | 11 | China → China | Mixed → Mixed | OK |
| 131 | KOSPI200 200% | 11 | Korea → Korea | Equity → Equity | OK |
| 132 | MSCI ACWI CR 40% + 종합채권 02Y 60% | 11 | Global → Global | Mixed → Mixed | OK |
| 133 | MSCI ACWI CR(KRW) 75% + 종합채권01Y 25% | 11 | Global → Global | Mixed → Mixed | OK |
| 134 | MSCI South East Asia Index(KRW) 50% + VN Index(KRW) 35% + CALL 15% | 11 | Asia → Asia | Mixed → Mixed | OK |
| 135 | MSCI WORLD ESG LEADERS | 11 | Global → Global | Equity → Equity | OK |
| 136 | S&P 500 95% + CALL 5% | 11 | US → US | Mixed → Mixed | OK |
| 137 | S&P 500(KRW) 95% + CALL 5% | 11 | US → US | Mixed → Mixed | OK |
| 138 | [(MSCI World Index ×90% (KRW)) + (Call × 10%)] | 11 | Global → Global | Mixed → Mixed | OK |
| 139 | 동남아6개국 합성지수(싱가폴지수 MSCI 교체) | 11 | - → Asia | Equity → Equity | 정정 (override) |
| 140 | Bloomberg US 1-5 Yr Corporate Bond TR | 10 | US → US | Bond → Bond | OK |
| 141 | KOSDAQ | 10 | Korea → Korea | Equity → Equity | OK |
| 142 | KOSDAQ 150 | 10 | Korea → Korea | Equity → Equity | OK |
| 143 | S&P 500 Growth Total Return Index | 10 | US → US | Equity → Equity | OK |
| 144 | Bloomberg U.S. Corp Investment Grade TR | 10 | US → US | Bond → Bond | OK |
| 145 | Bloomberg US MBS TR | 10 | US → US | Bond → Bond | OK |
| 146 | Russell 1000 TR USD | 10 | China → US | Equity → Equity | 정정 |
| 147 | Russell 2000 Value TR | 10 | China → US | Equity → Equity | 정정 |
| 148 | Russell 2500 TR | 10 | China → US | Equity → Equity | 정정 |
| 149 | Bloomberg GLOBAL AGGREGATE 90% + CALL 10% | 10 | Global → Global | Mixed → Mixed | OK |
| 150 | Bloomberg GLOBAL HIGH YIELD(USD HEDGED) | 10 | Global → Global | Bond → Bond | OK |

상위 150 중 Region 변경 46 · AssetClass 변경 23 (변경의 대부분은 '없음 → 값' — 수동 노드 edge 신설).

## 3. 남은 불확실 (규칙으로 못 정한 것)

| 유형 | 예 | 처리 |
| :-- | :-- | :-- |
| 지역 미적중 (상품 44) | Rogers International Commodity TR | Commodity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 12) | Rogers International Commodity TR 90% | Commodity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 11) | F-USDKRW | Currency — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 9) | Bloomberg Commodity TR | Commodity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 7) | Bloomberg 1-3 Y Government/Credit TR | Bond — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 7) | CME CF Bitcoin Reference Rate - New York Variant CR USD | Alternatives — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 7) | Rogers International Commodity TR in KRW | Commodity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 5) | CME CF Ether-Dollar Reference Rate NY USD | Alternatives — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 5) | LBMA Gold Price PM USD | Commodity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 4) | Indxx Artificial Intelligence & Big Data USD | Equity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 4) | Solactive Auto & Elec Vehicles USD | Equity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 4) | Alerian MLP TR | Equity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 4) | FTSE 3 Months Treasury Bill TR | MoneyMarket — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 3) | S&P GSCI Crude Oil ER USD | Commodity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 3) | Alerian MLP Infrastructure TR USD | Equity — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 3) | Bloomberg 1-5 Y Government/Credit TR | Bond — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 3) | CME CF Solana-Dollar Reference Rate - New York Variant USD | Alternatives — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |
| 지역 미적중 (상품 3) | CME CF XRP Dollar Reference Rate - New York Variant USD | Alternatives — 원자재·통화·디지털자산은 지역 개념 없음(정상). 그 외는 override 후보 |

- Equity 기본값(`*`) 으로 남은 지수는 대부분 테마·팩터 지수(Akros·BITA·Solactive 계열) — 주식이 맞는 경우가 대부분이나 확정은 아님. 답변엔 `source: rule` 을 근거로 "추정" 병기.
- `MSCI RUSSIA` 는 러시아 노드가 없어 Emerging 으로 override. `Bloomberg 1-3 Y Government/Credit` 는 미국 여부 미확정(지역 없음 유지).
- 합성 벤치마크의 region 은 첫 구성요소 기준(예: `S&P500 25% + MSCI EUROPE 25% + …` → US) — 다지역 혼합임을 답변에서 밝힐 것.
