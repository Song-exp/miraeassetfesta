# 🔎 KG 종목 노드 — ㉢ 대상 11종 식별자 조사 (2026-08-30 · 병철)

> `docs/kg_security_gap_2026-08-28.md` 의 103종 중 **CSV 로 붙일 수 있는 11종**을 실측 조사한 결과.
> 리드 확답(㉢ 승인) 나면 `ontology/codebooks/security_alias_manual.csv` 에 바로 넣을 수 있게 준비해 둔 것이다.
> **모든 값은 DB 실측이다.** 외부 지식·추론으로 채운 칸은 하나도 없다.

---

## 0. 왜 11종인가

103종 중 CSV 가 붙일 수 있는 것은 **11종뿐**이다. 나머지 92종은 국내 구성종목 `ticker` 가 비어 있어
생성기(`gen_security_auto.py`)의 `where ticker is not null and ticker<>''` 에서 **노드 생성 자체가 안 된다.**

| 갈래 | 종수 | 국내ETF 연결 | 조치 |
| :-- | --: | --: | :-- |
| **ⓐ 블룸버그 티커 있음** | **11** | **102건** | ㉢(`dom_ticker` 열) 도입 시 즉시 해결 |
| ⓑ 티커 아예 없음 | 92 | 111건 | 각 1~3개 ETF 뿐 — 비용 대비 효과 낮아 **보류** |

> 종수로는 11%인데 **끊긴 연결의 절반(102/213)** 이 여기 몰려 있다.

---

## 1. 🔴 조사 중 발견한 함정 — `isin` 컬럼을 쓰면 안 된다

`ext_ovs_etf_holdings.isin` 은 **보유종목이 아니라 ETF 자신의 ISIN** 이다. 조인 키로 쓰이는 컬럼이다.

```
ETF=VOO  isin=US9229083632  · 보유=NVIDIA Corp  cusip=67066G104  lei=549300S4KLFTLO7GSQ80
                └─ overseas_etfs 에서 조회하면 'Vanguard 500 Index Fund;ETF' 다
```

**보유종목의 식별자는 `cusip` · `lei` 뿐이고, ISIN 은 `ext_fund_holdings.isin` 에서만 얻을 수 있다.**
이걸 모르고 `ext_ovs_etf_holdings.isin` 을 종목 ISIN 으로 넣으면 **엉뚱한 ETF 를 회사로 등록**하게 된다.

검증: NVIDIA 는 수동 코드북에 `cusip=67066G104 · lei=549300S4KLFTLO7GSQ80` 로 이미 등록돼 있는데,
위 방식으로 뽑은 실측값과 **정확히 일치**한다. 출처 판정이 맞다는 근거다.

> ⚠️ `cusip='000000000'` 은 센티넬이라 제외했다.

---

## 2. 11종 실측표

| 국내ETF | 회사 | `dom_ticker` (신설 열) | `cusip` | `lei` | 종목 ISIN |
| --: | :-- | :-- | :-- | :-- | :-- |
| 16 | Zhongji Innolight Co Ltd | `300308 C2|3308 HK` | — | `655600K7YZDKAI214O83` | `CNE100001CY9|CNE100001CYA` |
| 16 | Li Auto Inc | `2015 HK|LI US` | `50202M102` | `2549003R73Q70J5H4I65` | `US50202M1027` |
| 13 | BeOne Medicines Ltd | `6160 HK|BGNE US` | `07725L102|BVDKGC900` | `549300JFUK6FRD5MH739` | — |
| 11 | Midea Group Co Ltd | `000333 C2|300 HK` | — | `3003003TRPHLHZD2IF61` | `BBG000QLWGC0|CNE100001QQ5|CNE100001QQA|CNE100006M58` |
| 10 | WuXi AppTec Co Ltd | `2359 HK|603259 C1` | — | `254900OEPQLZSPLN9175` | `CNE1000031K4|CNE100003F19` |
| 9 | STMicroelectronics NV | `STM US|STMPA FP` | `861012102|N83574108` | `213800Z8NOHIKRI42W10` | — |
| 9 | China Construction Bank Corp | `601939 C1|939 HK` | `168919108` | `5493001KQW6DM7KEDR62` | `CNE1000002H1|CNE100000742` |
| 8 | Jiangsu Hengrui Pharmaceuticals Co Ltd | `1276 HK|600276 C1` | — | `2549003BT1XS3SE3E448` | `CNE0000014W7|CNE0000014WA` |
| 5 | GANFENG LITHIUM GROUP CO LTD | `002460 C2|1772 HK` | — | `3003006BE6UOHWEOOR42` | — |
| 4 | Pony AI Inc | `2026 HK|PONY US` | `732908108|G7171B106` | `9845006P7613D2A61368` | `KYG7171B1068|US7329081084` |
| 1 | News Corp | `NWS US|NWSA US` | `65249B109|65249B208` | `549300ITS31QK8VRBQ14` | — |

**LEI 는 11종 전부 단일값**이다 — 한 회사에 두 LEI 가 잡히는 경우는 없었다.

| 출처 | 컬럼 | 비고 |
| :-- | :-- | :-- |
| 국내 구성종목 | `ext_etf_holdings.ticker` | 블룸버그식(`2015 HK`·`LI US`). `rank<=50` 한정 |
| 해외 구성종목 | `ext_ovs_etf_holdings.cusip` · `.lei` | 보유종목 식별자 |
| 펀드 구성종목 | `ext_fund_holdings.isin` | 보유종목 ISIN |

---

## 3. ㉢ 수정 범위 — 2줄

`scripts/gen_security_auto.py` 169행 근처, 기존 `kr_ticker` 처리 옆:

```python
        for dt in (r.get("dom_ticker") or "").split("|"):
            if dt.strip(): targets.append(f"Sec_d_{sha(dt.strip())}")
```

CSV 에 `dom_ticker` 열 추가. **빈 값이면 아무 동작도 하지 않으므로 기존 18행에 영향이 없다.**

> ⚠️ 이 문서는 **조사 결과일 뿐 아직 CSV 에 넣지 않았다.** 리드가 ㉢ 을 승인해야 반영한다.
> ㉢ 없이 ㉠(CSV 채우기)만 하면 `Sec_d_*` 에 붙을 키가 없어 **0종도 연결되지 않는다.**

---

## 4. 반영 후 검증 절차

```bash
python scripts/gen_security_auto.py        # shared/security_auto.yaml 재생성
python scripts/build_ontology.py           # kg_* + ttl
python scripts/check_yaml_dupkeys.py
python -m pytest tests -q
```

확인할 것 — 11종 각각이 **국내 alias(`ext_etf_holdings`)와 해외 alias 를 같은 정본 노드 아래** 갖는가.
기대 복구량 **102건**(국내ETF↔종목 연결).

> 🔴 다만 **㉡(런타임이 `kg_closure` 후손을 읽게 하는 것)이 없으면 챗봇 답변은 그대로다.**
> 리드 확인: *"`loader.py`·`pipeline.py` 어디에도 `kg_closure` 를 읽는 코드가 없다"*
