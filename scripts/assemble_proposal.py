# -*- coding: utf-8 -*-
"""기술제안서 취합본 재조립 — 13_데이터절_통합.md · 14_부록_취합.md 를 원본에서 다시 만든다.

    python scripts/assemble_proposal.py

원본(04·05·06 §A/§E, 07 부록 리드분)이 갱신될 때마다 실행 → 13·14 가 항상 원문과 일치.
손 편집 금지 — 13·14 를 직접 고치면 다음 실행에서 사라진다. 문구 수정은 원본 파일에서.
"""
import datetime
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "docs", "기술제안서")
TODAY = datetime.date.today().isoformat()


def read(name):
    return open(os.path.join(D, name), encoding="utf-8").read()


def sec(text, start, end=None, label=""):
    i = text.find(start)
    if i < 0:
        raise SystemExit(f"❌ {label}: '{start}' 를 못 찾았다 — 원본 절 제목이 바뀌었는지 확인")
    j = text.find(end, i + 1) if end else len(text)
    if j < 0:
        j = len(text)
    return text[i:j].rstrip()


def numbers(key_start, key_end):
    t = open(os.path.join(ROOT, "docs", "proposal", "NUMBERS.md"), encoding="utf-8").read()
    return sec(t, key_start, key_end, "NUMBERS")


bond = read("04_도메인_채권.md")
etf = read("05_도메인_ETF.md")
fund = read("06_도메인_펀드.md")
lead = read("07_리드_공통절.md")

bond_a = sec(bond, "## §A", "## §B", "04 §A")
etf_a = sec(etf, "## §A", "## §B", "05 §A")
fund_a = sec(fund, "## §A", "## §B", "06 §A")
b_e = sec(bond, "## §E", None, "04 §E")
e_e = sec(etf, "## §E", "## 제출 전 체크", "05 §E")
f_e = sec(fund, "## §E", None, "06 §E")
lead_ap = sec(lead, "## 부록 리드분", None, "07 부록분")

kg_stats = numbers("## 3. 온톨로지", "## 4.")

doc13 = f"""# 2.1 특화 데이터 수집·정제 — 통합본 (생성 {TODAY} · scripts/assemble_proposal.py)

> 🔴 이 파일은 **생성물**이다 — 직접 고치지 말 것. 04·05·06 §A 를 고친 뒤 재실행하면 반영된다.
> 수치는 NUMBERS 만 인용. 조판 시 절 번호: 2.1 (3쪽). 편집 책임: ETF 담당.

## 2.1.0 데이터 계층 — 무엇을 어디서 가져와 어떻게 우선순위를 두는가

| 계층 | 원천 | 규모 (NUMBERS §1~§3) | 역할 | 충돌 시 |
| :-- | :-- | :-- | :-- | :-- |
| **L0 마스터** (주최 v2_20260824) | 채권·국내ETF·해외ETF·펀드 4테이블 | 53,375행 · 280컬럼 · 기준일 2026-08-22 | 모든 답변의 기준 | **항상 우선** |
| **L1 판정** (온톨로지·KG) | `enums/*.yaml`·`shared/*.yaml`·`codebooks/*.csv` → ttl 5분할 + `kg_*` 4테이블 | 노드 41,580 · alias 66,592 · edge 7,414 · closure 9,965 | 결측·0·센티넬의 **의미**, 표기↔정본, 질의 규칙 | 값을 바꾸지 않음 — 배제·해석만 |
| **L2 외부 보강** | 국내 KRX 공시 · 해외 SEC EDGAR NPORT-P · 펀드 설명서·미래에셋 웹 | 구성종목 982,707 + 펀드 59,206 + 웹 10,565 | 마스터에 없는 사실(구성종목·설정일·환매규칙) | 마스터 non-null 우선, 출처·기준일 병기 |

원칙 셋: ① 값을 고치지 않고 **배제·판정**한다(주최 8/24 "0·결측은 의도된 내용") ② 모수를 답변에 밝힌다 ③ 시계열이 어긋나는 값은 적재하지 않는다(펀드 웹 수집분 실례 — §2.1.1 펀드).

## 2.1.1 도메인별 수집·정제

{bond_a}

{etf_a}

{fund_a}

## 2.1.2 적재 Flow

```bash
python scripts/fetch_etf_holdings.py        # 국내 ETF 구성종목 (KRX 공시) → 75,859행
python scripts/fetch_overseas_holdings.py   # 해외 ETF 구성종목 (SEC EDGAR NPORT-P) → 906,848행
python scripts/load_external_holdings.py    # ext_etf_holdings · ext_ovs_etf_holdings 적재
python scripts/load_external_web.py         # 펀드 설명서·웹 → ext_fund_holdings · ext_fund_page
python scripts/build_db.py                  # 마스터 4테이블 적재
python scripts/build_ontology.py            # yaml → ttl 5분할 + kg_* 4테이블 + V1~V7 검증 + coverage report
```

수정 반영 경로(운영): `enums/*.yaml` → `deploy.sh --yaml-only`(5초) · `shared/*.yaml`·코드북 → `build_ontology.py` 후 `--db-only`(1분). 배포는 GitHub `main` 만 본다.

## 2.1.3 신뢰성·무결성 관리 — "원천이 틀리면 답변이 틀린다"

| 장치 | 내용 | 실제로 잡아낸 것 (실측) |
| :-- | :-- | :-- |
| 빌드 검증 게이트 V1~V7 | yaml 이 DB 에 없는 컬럼·값을 가리키면 산출물 생성 거부 | 2차 전환 시 값 불일치 12건 |
| coverage report | 축별 미매핑 값을 매 빌드 리포트 | `ref_geo_focus` 0/23 미연결 발견 → 87% 복구 |
| 교차 대조 | 실세계 알려진 값으로 코드 의미 확인 | 거래소 `AMX`=AMEX 오독을 VOO·SPY 상장 사실로 정정 |
| 수치 단일 출처 | 제안서 수치는 `NUMBERS.md` 생성기만 — 손 전사 금지 | 세 문서가 따로 적던 `fss 11,611` 어긋남(실측 11,655)을 생성기 편입으로 차단 |
| 오답 → 회귀 승격 | 서버 오답을 eval 문항으로 승격, note 에 실측 기록 | ETF 29건 · 채권 50여건 기록표 운용 |

## 한계

- 해외 구성종목 커버리지 22.7%(AUM 상위 위주) · 보고기준일 8종 산개(최대 8개월) — `report_date` 병기로 대응 (ETF).
- 원천 오분류는 규칙으로 우회하되, 두 컬럼이 모두 틀린 잔존 사례는 복구 불가 — 기록만 (ETF·전수조사).
- 펀드 웹 수집분의 시계열 값 미적재 — 기준일 정합을 위해 정보량을 포기한 트레이드오프 (펀드).
- 채권은 외부 보강 원천 자체가 없어 코드북(등급 서열표) 1종으로만 보강 (채권).
"""


def esub(block, start, end, label):
    return sec(block, start, end, label)


doc14 = f"""# 부록 A·B·C — 취합본 (생성 {TODAY} · scripts/assemble_proposal.py)

> 🔴 이 파일은 **생성물**이다 — 직접 고치지 말 것. 04·05·06 §E·07 부록분을 고친 뒤 재실행하면 반영된다.
> KG 통계표는 NUMBERS §3 그대로.

# 부록 A — ttl 원문 · ABSENT 선언

## A.0 공통부 (리드)

{lead_ap}

## A.1 채권 (04 §E.1~E.2)

{esub(b_e, '### E.1', '### E.3', '04 E.1')}

## A.2 ETF (05 §E.1~E.2)

{esub(e_e, '### E.1', '### E.3', '05 E.1')}

## A.3 펀드 (06 §E.1~E.2)

{esub(f_e, '### E.1', '### E.3', '06 E.1')}

# 부록 B — yaml 규칙 발췌

## B.1 채권 (04 §E.3)

{esub(b_e, '### E.3', '### E.4', '04 E.3')}

## B.2 ETF (05 §E.3)

{esub(e_e, '### E.3', '### E.4', '05 E.3')}

## B.3 펀드 (06 §E.3)

{esub(f_e, '### E.3', '### E.4', '06 E.3')}

# 부록 C — 도메인×개체 값 수 · KG 통계

> 값 수 표는 각 도메인 §B.1 표를 인용(04·05·06). 아래는 NUMBERS §3 원문 — 재실행 시 자동 갱신.

{kg_stats}

## 편집 메모 (조판 시 확인)

- 수탁사 코드북 라벨 50종 중 18종 확보 — "없는 건 없다고 밝힌다" 원칙대로 모수 병기하고 진행(펀드 회신 §4, 1안 채택).
- 04·05·06 §E.4 값 수 표는 조판 직전 재실측(각 파일 표기 그대로).
"""

open(os.path.join(D, "13_데이터절_통합.md"), "w", encoding="utf-8", newline="\n").write(doc13)
open(os.path.join(D, "14_부록_취합.md"), "w", encoding="utf-8", newline="\n").write(doc14)
print(f"✅ 13({len(doc13.splitlines())}줄) · 14({len(doc14.splitlines())}줄) 재조립 완료")
