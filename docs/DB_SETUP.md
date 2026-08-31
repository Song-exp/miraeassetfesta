# 🗄️ DB 구축 가이드 — 로컬 재현 절차 (2026-08-31)

> git 저장소에는 **코드·규칙·코드북만** 있다. DB(`data/financial_products.db`, 263MB)와
> 원천 데이터는 public 저장소라 올리지 않는다 — **드라이브 공유분 2개**를 받아 아래 위치에 놓고
> 스크립트를 순서대로 돌리면 전원이 같은 DB 를 재현한다 (생성기는 결정적이다).
>
> ⚡ **지름길**: 완제품 DB 를 드라이브에서 받았다면 `data/financial_products.db` 에 넣고
> 바로 [§4 검증](#4-검증--이-네-개가-통과하면-성공)으로 건너뛴다. ①~⑤ 불필요.

---

## 1. 준비물

| 무엇 | 어디서 | 어디에 놓나 |
| :-- | :-- | :-- |
| 저장소 | `git clone` + `pip install -r requirements.txt` | — |
| ① 주최 배포본 (2차, 8/24) | 드라이브 공유 | `1.금융상품/` (루트) |
| ② 외부 수집분 (27,550파일) | 드라이브 공유 | `data/external/` |

🔴 `1.금융상품/`·`data/`·`*.zip` 은 전부 `.gitignore` 에 있다 — **절대 커밋하지 말 것**
(8/31 사고: `git add -A` 로 zip 770MB 가 커밋돼 push 가 끊겼다).

## 2. 파일 배치 구조

```
미래에셋/                              ← 저장소 루트
│
├─ 1.금융상품/                         ← ① 주최 배포본 (build_db.py 가 루트에서 자동 탐색 —
│   │                                     폴더명에 "금융상품" 만 들어 있으면 됨)
│   ├─ {prefix}_data.xlsx             4개 테이블 각각 data + schema 쌍
│   ├─ {prefix}_schema.xlsx              (prbd01n001 = 국내채권 등)
│   └─ _v1_20260711/                  1차 배포본(*_datarows.xlsx) 보관 — 자동 탐색 제외.
│                                     🔴 1차·2차는 컬럼 수가 달라 섞으면 안 된다
│
└─ data/
    ├─ financial_products.db          ← 산출물 (여기에 생성됨)
    └─ external/                      ← ② 외부 수집분
        ├─ holdings/
        │   └─ domestic_holdings_20260710.csv       국내 ETF 구성종목
        ├─ holdings_overseas/
        │   ├─ overseas_holdings.csv                해외 ETF 구성종목 (SEC NPORT-P)
        │   └─ ticker_series_map.csv                해외 티커 ↔ ISIN 조인 키
        └─ miraeasset_web/
            ├─ fund_pages_full.csv                  펀드 페이지 수집물
            └─ holdings_full.csv                    펀드 구성종목
```

## 3. 실행 순서 — 5단계 (반드시 이 순서)

```bash
python scripts/build_db.py                    # ① 마스터 4테이블 (엑셀 → SQLite)
python scripts/load_external_holdings.py      # ② ext_etf_holdings · ext_ovs_etf_holdings
python scripts/load_external_web.py           # ③ ext_fund_page · ext_fund_holdings
python scripts/gen_security_auto.py           # ④ 종목 노드 재생성 (shared/security_auto.yaml)
python scripts/build_ontology.py              # ⑤ kg_node·kg_alias·kg_edge·kg_closure + ttl
```

- ①은 기존 DB 의 `ext_*`/`kg_*` 를 건드리지 않는다(마스터만 replace) — 재실행 안전.
- ②③은 멱등(drop & recreate).
- ④⑤는 DB 가 있어야 돌므로 ①~③ 뒤에만.
- 🪟 **Windows 콘솔**이면 한글·기호 출력이 cp949 로 깨질 수 있다 —
  `PYTHONIOENCODING=utf-8` (PowerShell: `$env:PYTHONIOENCODING='utf-8'`) 를 앞에 붙인다.

## 4. 검증 — 이 네 개가 통과하면 성공

```bash
python scripts/check_yaml_dupkeys.py     # 문제 0개
python scripts/build_ontology.py --check # 오류 0 (경고는 봐도 됨)
python eval/run_gold_check.py            # 실패 0 (HCX 안 씀 — 몇 번이든 무료)
python -m pytest tests -q                # 전부 통과 (DB 없으면 skip 되던 테스트들이 살아난다)
```

완성 DB 는 **14테이블**이다 — 마스터 4(`domestic_bonds`·`domestic_etfs`·`overseas_etfs`·`public_funds`)
+ 외부 4(`ext_etf_holdings`·`ext_ovs_etf_holdings`·`ext_fund_holdings`·`ext_fund_page`)
+ KG 4(`kg_node`·`kg_alias`·`kg_edge`·`kg_closure`) + `build_info`(v2_20260824 · 2026-08-22).
`deploy/deploy.sh` 0단계가 같은 목록으로 검사하므로, 배포가 통과하면 DB 도 맞는 것이다.

## 5. 자주 걸리는 것

| 증상 | 원인 · 조치 |
| :-- | :-- |
| `금융상품 데이터 디렉터리를 찾을 수 없습니다` | ①이 루트에 없거나 폴더명에 "금융상품" 이 없음 |
| 컬럼 수가 문서와 다름 (채권 40컬럼 등) | 1차 배포본을 읽었다 — `*_datarows.xlsx` 는 `_v1_20260711/` 로 치우고 2차(`*_data.xlsx`)만 |
| gold check 에서 KG 문항 실패 | ④⑤를 안 돌렸거나 옛 DB — `kg_node` 유무 확인 후 ④⑤ 재실행 |
| `UnicodeEncodeError: 'cp949' ...` | Windows 콘솔 — `PYTHONIOENCODING=utf-8` 붙이고 재실행 |
| pytest 다수 skip | DB 없음 — §3 먼저 |

> 관련 문서: 규칙 수정·검증 루프는 [`TEAM_WORKFLOW.md`](TEAM_WORKFLOW.md) §5,
> 서버 배포는 [`DEPLOY.md`](DEPLOY.md), 파이프라인 원리는 [`HOW_IT_WORKS.md`](HOW_IT_WORKS.md).
