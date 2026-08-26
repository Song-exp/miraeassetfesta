# 🧾 운용사 코드북 웹 검수 — 2026-08-25

> 대상: `asset_manager_en.csv` 29행(한↔영 대응, 기존 근거 = 2차 DB 동일 행 공기) · `asset_manager.csv` derived 상위 40.
> 출처 1개씩 WebSearch 로 확인. `name_en_lipper` = DB(Lipper `ref_fund_mgmt_co`) 표기 보존 — KG alias 는 이 값, `name_en` 은 현행 공식 영문명.

## 1. 한↔영 29행

| 코드 | 한글 | DB(Lipper) 표기 | 확정 영문명 | status | 출처 |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 00040010 | 삼성자산운용 | Samsung Asset Management Co Ltd | Samsung Asset Management Co., Ltd. | verified | https://en.wikipedia.org/wiki/Samsung_Asset_Management |
| 00080008 | 미래에셋자산운용 | Mirae Asset Global Investments Co Ltd | Mirae Asset Global Investments Co., Ltd. | verified | https://www.sec.gov/edgar/browse/?CIK=0001569395 |
| 00040035 | KB자산운용 | KB Asset Ltd | KB Asset Management Co., Ltd. | verified | https://www.kbam.co.kr/en |
| 00040024 | 한국투자신탁운용 | Korea Investment Management Co Ltd | Korea Investment Management Co., Ltd. | verified | https://thevc.kr/koreainvestmentmanagement |
| 00040027 | 한화자산운용 | Hanwha Asset Management | Hanwha Asset Management Co., Ltd. | verified | https://www.hanwhafund.co.kr/en/global-network |
| 00040067 | 신한자산운용 | Shinhan Asset Management Co Ltd | Shinhan Asset Management Co., Ltd. | verified | https://englishdart.fss.or.kr/dsbc001/selectPopup.ax?selectKey=00243553 |
| 00080052 | 키움투자자산운용 | Kiwoom Asset Management Co.,Ltd | Kiwoom Asset Management Co., Ltd. | verified | https://www.kiwoomam.com/KI0800000000M |
| 00040040 | NH-Amundi자산운용 | NH-Amundi Asset Management Co Ltd | NH-Amundi Asset Management Co., Ltd. | verified | https://www.nh-amundi.com/en/company/introduction |
| 00040005 | 하나자산운용 | Hana Asset Management Co Ltd | Hana Asset Management Co., Ltd. | verified | https://www.hanaam.com/ |
| 00080135 | 삼성액티브자산운용 | Samsung Active Asset Management | Samsung Active Asset Management Co., Ltd. | verified | https://www.samsungactive.co.kr/eng/main.do |
| 00080248 | 타임폴리오자산운용 | Time Folio Asset Management Co Ltd | TIMEFOLIO Asset Management Co., Ltd. | corrected | https://www.timefolio.co.kr/en/ |
| 00040007 | 우리자산운용 | Woori Asset Management Corp | Woori Asset Management Corp. | verified | https://thevc.kr/wooriassetmanagement |
| 00080086 | 에셋플러스자산운용 | Asset Plus Investment Management Co Ltd | Assetplus Investment Management Co., Ltd. | corrected | https://www.linkedin.com/company/assetplus-investment-management-co-ltd |
| 00080033 | BNK자산운용 | BNK Asset Management Co Ltd | BNK Asset Management Co., Ltd. | verified | https://www.bnkasset.co.kr/company/overview.aspx |
| 00040006 | DB자산운용 | DB Asset Management Co Ltd | DB Asset Management Co., Ltd. | verified | https://www.db-asset.com/front/kr/company/organization |
| 00080022 | 아이비케이자산운용 | IBK Asset Management Co Ltd | IBK Asset Management Co., Ltd. | verified | https://www.ibkasset.com/ |
| 00040018 | 브이아이자산운용 | VI Asset Management Korea Co Ltd | VI Asset Management Korea Co., Ltd. | verified | https://altss.com/profile/vi-asset-management-korea |
| 00040021 | 흥국자산운용 | Heungkuk Investment Trust Management Co., Ltd | Heungkuk Asset Management Co., Ltd. | corrected | https://englishdart.fss.or.kr/dsbh001/main.do?rcpNo=20251030000249 |
| 00080041 | 현대자산운용 | Hyundai Asset Management Co Ltd | Hyundai Asset Management Co., Ltd. | verified | https://www.linkedin.com/company/hyundai-asset-management-co.-ltd. |
| 00040001 | 교보악사자산운용 | Kyobo AXA Investment Managers Co Ltd | Kyobo AXA Investment Managers Co., Ltd. | verified | https://lei.bloomberg.com/leis/view/988400SR8XGNC82K2Y53 |
| 00080005 | 마이다스에셋자산운용 | Midas Asset Management Co Ltd | Midas Asset Management Co., Ltd. | verified | https://www.bloomberg.com/profile/company/MIDASAMZ:KS |
| 00040004 | 대신자산운용 | Daishin Investment Trust Management | Daishin Asset Management Co., Ltd. | corrected | https://www.crunchbase.com/organization/daishin-asset-management |
| 00040087 | 케이씨지아이자산운용 | KCGI Asset Management Co Ltd | KCGI Asset Management Co., Ltd. | verified | https://www.kcgiam.com/company/introduction.php |
| 00080021 | 한국투자밸류자산운용 | Korea Investment Value Asset Management Co Ltd | Korea Investment Value Asset Management Co., Ltd. | verified | https://vam.koreainvestment.com/eng/about.do?cmd=pageLink&link=company |
| 00080043 | 트러스톤자산운용 | Truston Asset Management Co Ltd | Truston Asset Management Co., Ltd. | verified | https://lei.bloomberg.com/leis/view/988400TCDOXEUPWQR670 |
| 00080010 | 유리자산운용 | Yurie asset Management Inc | Yurie Asset Management Inc. | verified | https://www.yurieasset.co.kr/ |
| 00080162 | 디에스자산운용 | DS Asset Management Co Ltd | DS Asset Management Co., Ltd. | verified | https://www.crunchbase.com/organization/ds-asset-management |
| 00080035 | iM에셋자산운용 | IM Asset Investment & Management Co Ltd | iM Asset Investment & Management Co., Ltd. | verified | https://m.kofia.or.kr/brd/m_31/view.do?seq=6605 |
| 00080359 | 더제이자산운용 | The J Investment Co Ltd | TheJ Asset Management Co., Ltd. | corrected | https://www.thejasset.com/etc/credit-information.php |

정정 5건(현행 공식명 ≠ Lipper 표기): 타임폴리오(Time Folio→TIMEFOLIO) · 에셋플러스(Asset Plus→Assetplus) · 흥국(Investment Trust Management→Asset Management) · 대신(Investment Trust Management→Asset Management) · 더제이(The J Investment→TheJ Asset Management). Lipper 표기는 alias 로 유지되므로 매핑엔 영향 없음.

## 2. derived 상위 40 (펀드 운용사 코드)

| 코드 | 브랜드 | 법인명 | status | 출처/사유 |
| :-- | :-- | :-- | :-- | :-- |
| 00080181 | IBK투자증권인 | 아이비케이투자증권(주) | web_confirmed | 웹 확인 https://m.ibks.com/iki/IKI010401.do (2026-08-25) — 증권사(집합투자업 겸영 추정) — 접두 점유 88% |
| 00130001 | 피델리티펀드유로 | - | derived | 종목명 접두 최빈값 (점유 4%) — 법인명 아님 / 검수 2026-08-25: 0013xxxx = 역외펀드 운용법인 계열(Fidelity) — 국내 법인 코드 아님, derived 유지 / 검수 2026-08-25: 0013xxxx = 역외펀드 운용법인 계열(Fidelity) — 국내 법인 코드 아님, derived 유지 |
| 00080380 | 미래고용보험기금 | - | derived | 종목명 접두 최빈값 (점유 6%) — 법인명 아님 / 검수 2026-08-25: 미래고용보험기금·SBI크로스보더·JKL 등 이질 PEF/기금 묶음 — 단일 운용사 아님 / 검수 2026-08-25: 미래고용보험기금·SBI크로스보더·JKL 등 이질 PEF/기금 묶음 — 단일 운용사 아님 |
| 00080109 | 포커스 | 포커스자산운용(주) | web_confirmed | 웹 확인 http://focusam.co.kr/ (2026-08-25) — Focus Asset Management |
| 00080165 | JB | JB자산운용(주) | web_confirmed | 웹 확인 https://www.jbam.co.kr/ (2026-08-25) — 구 더커자산운용, 2014 JB금융 편입 |
| 00080116 | W코스닥벤처(M | (주)더블유자산운용 | web_confirmed | 웹 확인 http://w-asset.com/ (2026-08-25) — W코스닥벤처 = 더블유자산운용. 00080394 와 동일 법인 가능 — 코드 중복 사유 미확인 |
| 00080131 | 더플랫폼 | - | derived | 종목명 접두 최빈값 (점유 57%) — 법인명 아님 / 검수 2026-08-25: 더플랫폼 — 플랫폼파트너스자산운용과 동일 여부 미확정 / 검수 2026-08-25: 더플랫폼 — 플랫폼파트너스자산운용과 동일 여부 미확정 |
| 00080085 | AIP | (주)에이아이피자산운용 | web_confirmed | 웹 확인 https://thevc.kr/aipassetmanagement (2026-08-25) — AIP Asset Management (구 FG자산운용) — 에이아이파트너스와 별개 |
| 00080226 | 비엔비 | 비엔비자산운용(주) | web_confirmed | 웹 확인 https://lei.bloomberg.com/leis/view/988400MIPEVM2LLUWP86 (2026-08-25) — BNB Asset Management |
| 00080107 | INMARK미국 | (주)인마크자산운용 | web_confirmed | 웹 확인 https://www.lei-lookup.com/record/988400QGFVBNPKHM8140/ (2026-08-25) — INMARK Asset Management |
| 00080153 | 동양종금하이일드 | - | derived | 종목명 접두 최빈값 (점유 33%) — 법인명 아님 / 검수 2026-08-25: 동양종금하이일드 — 구 동양종합금융증권 상품, 현 운용주체 미확정 / 검수 2026-08-25: 동양종금하이일드 — 구 동양종합금융증권 상품, 현 운용주체 미확정 |
| 00080115 | 오라이언 | 오라이언자산운용(주) | web_confirmed | 웹 확인 https://orioncm.co.kr/home/ (2026-08-25) — Orion Capital Management |
| 00080322 | 안다H | (주)안다에이치자산운용 | web_confirmed | 웹 확인 https://thevc.kr/andahassetmanagement (2026-08-25) — ANDA H — 안다자산운용(00080091) 물적분할 자회사 |
| 00080095 | 시몬느미국부동산 | 시몬느자산운용(주) | web_confirmed | 웹 확인 https://simonefg.co.kr/ (2026-08-25) — Simone Investment Managers |
| 00080126 | 인벡스 | 인벡스자산운용(주) | web_confirmed | 웹 확인 https://invex.co.kr/main2/ (2026-08-25) — INVEX Capital Management |
| 00080168 | 삼성SRA일반사 | 삼성에스알에이자산운용(주) | web_confirmed | 웹 확인 https://www.samsungsra.com/ko (2026-08-25) — Samsung SRA Asset Management |
| 00040099 | 신한금융투자 | 신한투자증권(주) | web_confirmed | 웹 확인 https://www.shinhansec.com/ (2026-08-25) — 구 신한금융투자(2022 사명변경) — 증권사 |
| 00130003 | 슈로더이머징유럽 | - | derived | 종목명 접두 최빈값 (점유 15%) — 법인명 아님 / 검수 2026-08-25: 0013xxxx 역외(Schroders) — derived 유지 / 검수 2026-08-25: 0013xxxx 역외(Schroders) — derived 유지 |
| 00080134 | 삼성 | - | derived | 종목명 접두 최빈값 (점유 25%) — 법인명 아님 / 검수 2026-08-25: '삼성' 접두 점유 25% — 삼성 계열 어느 법인인지 미확정(00040010 과 별개 코드) / 검수 2026-08-25: '삼성' 접두 점유 25% — 삼성 계열 어느 법인인지 미확정(00040010 과 별개 코드) |
| 00080252 | 케이알일반사모부 | - | derived | 종목명 접두 최빈값 (점유 64%) — 법인명 아님 / 검수 2026-08-25: 케이알 일반사모부동산 — 법인 미확정(검색 불일치) / 검수 2026-08-25: 케이알 일반사모부동산 — 법인 미확정(검색 불일치) |
| 00080399 | 블리츠리베로오아 | (주)블리츠자산운용 | web_confirmed | 웹 확인 http://www.blitz-asset.com/ (2026-08-25) — Blitz Asset Management |
| 00130005 | 북미펀드 | - | derived | 종목명 접두 최빈값 (점유 9%) — 법인명 아님 / 검수 2026-08-25: 0013xxxx 역외(북미펀드) — derived 유지 / 검수 2026-08-25: 0013xxxx 역외(북미펀드) — derived 유지 |
| 00080106 | 그로쓰힐 | 그로쓰힐자산운용(주) | web_confirmed | 웹 확인 http://m.growthhill.com/page/page13 (2026-08-25) — Growth Hill Asset Management |
| 00080199 | 마스턴제192호 | 마스턴투자운용(주) | web_confirmed | 웹 확인 https://lei.bloomberg.com/leis/view/9884005FNXAPJMH56Q49 (2026-08-25) — Mastern Investment Management |
| 00080290 | 웰브릿지 | 웰브릿지자산운용(주) | web_confirmed | 웹 확인 https://thevc.kr/wellbridgeassetmanagement (2026-08-25) — 라임 가교 운용사(2020 설립) |
| 00080123 | 한&파트너스 | (주)한앤파트너스자산운용 | web_confirmed | 웹 확인 https://thevc.kr/hannpartnersassetmanagement (2026-08-25) — HAN & Partners Asset Management |
| 00130004 | AB | - | derived | 종목명 접두 최빈값 (점유 30%) — 법인명 아님 / 검수 2026-08-25: 0013xxxx 역외(AllianceBernstein) — derived 유지 / 검수 2026-08-25: 0013xxxx 역외(AllianceBernstein) — derived 유지 |
| 00080242 | 타이거대체전문투 | (주)타이거대체투자운용 | web_confirmed | 웹 확인 http://www.tigeralt.com/ (2026-08-25) — Tiger Alternative Investors — 타이거자산운용투자일임(00080396)과 별개 |
| 00130002 | 템플턴글로벌본드 | - | derived | 종목명 접두 최빈값 (점유 22%) — 법인명 아님 / 검수 2026-08-25: 0013xxxx 역외(Franklin Templeton) — derived 유지 / 검수 2026-08-25: 0013xxxx 역외(Franklin Templeton) — derived 유지 |
| 00130006 | 미래에셋차이나업 | - | derived | 종목명 접두 최빈값 (점유 25%) — 법인명 아님 / 검수 2026-08-25: 0013xxxx 역외(미래에셋 홍콩/룩셈부르크 등) — derived 유지 / 검수 2026-08-25: 0013xxxx 역외(미래에셋 홍콩/룩셈부르크 등) — derived 유지 |
| 00130026 | 블랙록월드광업주 | - | derived | 종목명 접두 최빈값 (점유 25%) — 법인명 아님 / 검수 2026-08-25: 0013xxxx 역외(BlackRock) — derived 유지 / 검수 2026-08-25: 0013xxxx 역외(BlackRock) — derived 유지 |
| 00080190 | 한강BTL프로젝 | - | derived | 종목명 접두 최빈값 (점유 25%) — 법인명 아님 / 검수 2026-08-25: 한강BTL 프로젝트 — 특별자산 SPC 묶음, 운용사 미확정 / 검수 2026-08-25: 한강BTL 프로젝트 — 특별자산 SPC 묶음, 운용사 미확정 |
| 00080398 | 브이엠 | 브이엠자산운용(주) | web_confirmed | 웹 확인 http://www.vminvest.co.kr/ (2026-08-25) — VM Investment Management — 00080197 과 동일 브랜드(중복 코드 사유 미확인) |
| 00080158 | 아크 | 아크임팩트자산운용(주) | web_confirmed | 웹 확인 https://www.lei-lookup.com/record/988400AW10CF2P7HYM87/ (2026-08-25) — ARK Impact Asset Management |
| 00080197 | 브이엠 | 브이엠자산운용(주) | web_confirmed | 웹 확인 http://www.vminvest.co.kr/ (2026-08-25) — VM Investment Management — 00080398 과 동일 브랜드(중복 코드 사유 미확인) |
| 00080188 | 에이아이파트너스 | 에이아이파트너스자산운용(주) | web_confirmed | 웹 확인 https://www.legalentityidentifier.in/leicert/988400I3FCSJFGYOXG76/ (2026-08-25) — AI Partners Asset Management — AIP 와 별개 |
| 00080218 | 파인스트리트글로 | 파인스트리트자산운용(주) | web_confirmed | 웹 확인 https://www.pinestreetgrp.com/amc/ (2026-08-25) — PineStreet Asset Management (전문사모) |
| 00080326 | TCK | 토포앤코코리아자산운용(주) | web_confirmed | 웹 확인 https://www.newspim.com/news/view/20211109000647 (2026-08-25) — TCK Investments 국내 법인(2021 전문사모 등록) |
| 00080294 | NB글로벌비상장 | 누버거버먼자산운용(주) | web_confirmed | 웹 확인 https://www.nb.com/ko/kr/nb-korea-overview (2026-08-25) — Neuberger Berman Asset Management Korea (추정 — 'NB글로벌비상장' 접두) |
| 00080142 | 라쿤Agile전 | (주)라쿤자산운용 | web_confirmed | 웹 확인 https://www.raccoonasset.com/ (2026-08-25) — Raccoon Asset Management |

결과: web_confirmed +0 · derived 유지 13 (역외 `0013xxxx` 7 · PEF/SPC 묶음 3 · 미확정 4).

## 3. 눈에 띄는 발견

- `0013xxxx` 코드 7종은 전부 **역외펀드 운용법인**(Fidelity·Schroders·AB·Templeton·BlackRock·Mirae 역외) — 국내 법인명 대응 불가. 별도 축(`OffshoreManager`)으로 다루거나 브랜드 라벨 유지.
- 브이엠자산운용이 두 코드(00080398·00080197)에, 더블유자산운용도 두 코드(00080116·00080394)에 걸림 — 주최 내부 코드 체계상 법인 분할/이관 흔적. 노드 병합 여부는 워크샵 결정.
- 00040099 신한금융투자 → 현 신한투자증권(증권사), 00080181 IBK투자증권 — 운용사가 아닌 증권사 코드가 운용사 컬럼에 있음(집합투자업 겸영 또는 판매사 오기). 답변에 '운용사'로 서술 시 주의.
- 에이아이피(AIP, 00080085)와 에이아이파트너스(00080188)는 **별개 법인** — 이름 유사로 병합 금지.
- 안다H(00080322)는 안다자산운용(00080091) 물적분할 자회사, 타이거대체투자운용(00080242)은 타이거자산운용투자일임(00080396)과 별개 — parent 관계는 KG edge 후보(미생성).
