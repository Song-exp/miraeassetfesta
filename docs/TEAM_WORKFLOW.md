# 👥 팀 실험 → 수정 → 반영 (팀원용)

> 2026-08-26. 챗봇으로 관찰한 것을 **온톨로지에 반영해 다시 챗봇에 태우는** 한 바퀴.
> 루프의 기술적 배경은 `docs/EXPERIMENT_LOOP.md`, 판정 규칙 12종은 `docs/ontology_rules/`.

---

## 0. 접속

```
https://49.50.134.229.nip.io/chat?t=<CHAT_TOKEN>
```

설치할 것 없습니다. 브라우저만 있으면 됩니다. 답변 아래 **`think_trace`** 가 펼쳐져 있는데, **이게 이 실험의 핵심 도구**입니다 (§2).

> ⚠️ **번갈아 쓰세요.** HCX 한도가 분당 2건이 안 됩니다(질의 1건 = HCX 2회). 동시에 치면 서로 20초씩 기다립니다.
> ⚠️ 질문·답변·근거는 **전부 서버에 자동 기록**됩니다. 캡처하지 않아도 됩니다.

---

## 1. 무엇을 물어볼 것인가

평가는 **35문항 (상 10 / 중 10 / 하 10 / 답변불가 5)** 입니다. 자기 도메인에서 이 비율대로 흔들어 보세요.

| 유형 | 예시 | 노리는 것 |
| :-- | :-- | :-- |
| 하 — 단순 조회 | "KODEX 200 총보수 알려줘" | 표기 매핑이 되는가 |
| 중 — 조건·정렬 | "신용등급 AAA 회사채 중 만기 긴 3개" | 조건식·정렬축이 맞는가 |
| 상 — 교차·연산 | "삼성전자를 보유한 국내/해외 ETF와 펀드를 수익률 TOP10" | 조인·모수가 맞는가 |
| 답변불가 | "KODEX AI 로봇 ETF", "신용등급 AAAA" | **지어내지 않는가** ← 감점 1순위 |

**조사를 붙인 실제 말투로 물어보세요.** "AAAA 채권"이 아니라 "AAAA**인** 채권". 실제로 조사 하나 때문에 게이트가 뚫린 버그가 있었습니다.

---

## 2. 답이 이상하면 — `think_trace` 부터 읽는다 🔴

답만 보고 "틀렸다"고 하면 어디를 고칠지 알 수 없습니다. 파이프라인은 6단계이고, **몇 번에서 틀어졌는지가 곧 고칠 위치**입니다.

```
1. [Normalize]  질의 정리
2. [Ground]     질의의 표기 → DB 실제 값      ← KG(온톨로지 개체)
3. [Gate]       답할 수 없는 질의인가 판정      ← 기각 규칙
4. [Plan]       근거문서 조립 → SQL 생성        ← query_rules
5. [Guard]      SQL 안전 검사
6. [Execute]    조회 → [Answer] 문장 생성
```

### 증상 → 원인 → 고칠 곳

| `think_trace` 에서 보이는 것 | 무슨 일인가 | 고칠 곳 | 규칙 문서 |
| :-- | :-- | :-- | :-- |
| `[Ground] 매칭 없음` 인데 상품·운용사·지수 이름을 물었다 | KG에 그 표기가 없다 | `ontology/shared/*.yaml` 의 alias, `ontology/codebooks/*.csv` | `01_naming` |
| `[Ground]` 가 **엉뚱한 노드**를 잡았다 | 같은 표기가 여러 도메인에 걸린다 | 위와 같음 | `01_naming` |
| `[Gate] 기각` 인데 **답할 수 있는** 질의였다 | 기각 규칙이 과하다 | `enums/*.yaml` 의 `absent_in`·`value_semantics` | `10_absent` |
| `[Gate] 통과` 인데 **없는 걸** 물었다 | 기각 규칙이 부족하다 (환각 위험) | 위와 같음 | `10_absent` |
| `[Plan] SQL 생성` 의 **조건식이 틀렸다** | 규칙이 없거나 틀렸다 ← **가장 흔함** | `enums/*.yaml` 의 `query_rules` | `05_population` `06_derivation` |
| 수치가 이상하다 (개수가 부풀거나 모자람) | 행의 단위(grain)나 모수 정의 | `query_rules` 의 대표행·모수 규칙 | `04_grain` `05_population` |
| 정렬 결과에 **성격이 다른 게 섞였다** | 한 컬럼에 이종이 섞여 있다 | `query_rules` 의 유형 분리 | `07_disjoint` |
| 자릿수가 이상하다 (보수 0.03 vs 30) | 단위 미선언 (‰ vs %) | `columns.<col>` 의 단위 | `08_unit` |
| 쓰면 안 되는 컬럼을 썼다 | 배제 미선언 | `query_rules` 금지 규칙 | `09_forbid` |
| 기준일이 없거나 미래를 말한다 | 시점 미선언 | `query_rules` 기준일 | `12_asof` |
| `[Execute] 0행` 인데 **있어야 한다** | 조건식 or 표기 매핑 | 위 둘 중 하나 | — |
| `[Guard] SQL 기각` | 가드 오탐 | **코드 — 담당자에게** | — |
| 조회는 맞는데 **문장이 과장·추측** | 답변 프롬프트 | **코드 — 담당자에게** | — |

> 코드 문제(`[Guard]`·`[Answer]`)는 yaml로 못 고칩니다. **질문 문구만 담당자에게** 넘기세요.

### 🆕 화면에 같이 나오는 것 (2026-08-30) — KG·온톨로지를 의도대로 썼는지 보는 법

`/chat` 화면과 CLI 가 **실행 SQL 전문**과 **근거문서 원문**을 함께 보여줍니다.
(그 전에는 `think_trace` 가 SQL 을 120자에서 잘라, 조건식이 틀렸는지 매핑이 틀렸는지 구분할 수 없었습니다.)

| 보이는 것 | 무엇을 확인하나 |
| :-- | :-- |
| **실행 SQL** (`sql`) | 🔴 **실제로 실행된 문장**입니다(LIMIT 보정 후). `query_rules` 의 조건식이 그대로 들어갔는지, `[Ground]` 가 찾아준 값이 `IN (...)` 에 **전부** 들어갔는지 여기서 봅니다 |
| **근거문서** (`grounding`) | 플래너에게 실제로 넘어간 프롬프트 원문입니다. `# KG 개체 매핑` · `# 교차질의 조인 키` · `# 도메인 규칙` · `# 스키마` 네 블록. **yaml 을 고쳤는데 답이 그대로면 여기부터 봅니다** — 이 문서에 반영이 안 됐으면 반영 경로(빌드·`/reload`)가 문제입니다 |
| `[Plan] 근거문서 조립 … 구성:` | 어떤 블록이 실렸는지 요약. `KG 개체 매핑` 이 없으면 개체를 못 찾은 것입니다 |

**검토 시 가장 자주 나오는 판정 두 가지**

- `[Ground]` 는 별칭 43종을 찾아줬는데 SQL 은 `IN ('미래에셋')` 하나만 썼다 → **KG 는 정상, 플래너가 덜 썼다.** 근거문서의 지시 문구(코드) 문제이므로 담당자에게.
- SQL 조건식에 `query_rules` 의 조건이 아예 없다 → **yaml 이 근거문서에 안 실렸다.** 근거문서 원문에서 그 규칙을 검색해 보고, 없으면 yaml 위치·빌드 반영을 확인합니다.

---

## 3. 어디를 고치나 — yaml 지도

```
ontology/
├─ enums/            도메인별 "이 컬럼을 어떻게 읽고 어떻게 질의하나"
│  ├─ domestic_bonds.yaml     채권
│  ├─ domestic_etfs.yaml      국내 ETF
│  ├─ overseas_etfs.yaml      해외 ETF
│  └─ public_funds.yaml       공모펀드
│      · columns.<col>        컬럼의 의미·결측·함정
│      · query_rules          🔴 질의 조건식 — 대부분 여기를 고칩니다
│      · normalization        비교 전 정규화
└─ shared/           도메인을 가로지르는 개체 (KG 노드가 됩니다)
   ├─ organization.yaml  index.yaml  region.yaml
   ├─ credit_grade.yaml  risk_grade.yaml  currency.yaml  asset_class.yaml
   └─ *_auto.yaml        🔴 생성물 — 직접 고치지 말 것
```

**`.auto.yaml` · `.ttl` · `kg_*` 는 전부 생성물입니다.** 손으로 고치면 다음 빌드에 사라집니다.

---

## 4. 어떻게 쓰나 — 판정 작성 규칙

**판정을 회의록이나 슬랙에만 적으면 챗봇은 모릅니다.** 프롬프트는 yaml에서 나옵니다.

한 줄 고칠 때도 이 셋을 같이 씁니다:

```yaml
  유동화위험금지: "유동화 = TRIM(bd_knd) IN ('MBS','유동화회사채','Conduit회사채') 3,949
    + 코드 밖 SPC 96 = 4,045행 (🔴 2026-08-26 정정 — Conduit회사채 1,025행을 코드로 편입.
    이전 3,036행은 발행사명 패턴으로 16행만 회수해 1,009행이 누락됐다).
    조건식: TRIM(bd_knd) IN ('MBS','유동화회사채','Conduit회사채') OR pd_pbcm LIKE '%유동화%'"
```

| 요소 | 왜 |
| :-- | :-- |
| **판정** (무엇이 맞다) | 이게 프롬프트로 들어간다 |
| **근거·수치** (실측 몇 행) | 다음 사람이 뒤집을 때 필요하다 |
| **날짜와 무엇이 바뀌었나** | 1차/2차 수치가 섞이면 추적 불가 |

> 🔴 **수치는 반드시 2차 데이터(기준일 2026-08-22)로 실측**해서 쓰세요. 1차 수치를 옮겨 적으면 조용히 틀립니다.
> ```bash
> python -c "import sqlite3;print(sqlite3.connect('data/financial_products.db').execute('select count(*) from domestic_bonds where ...').fetchone())"
> ```

---

## 5. 고쳤으면 — 검증 3종

```bash
python scripts/check_yaml_dupkeys.py       # yaml 중복키 → 0개여야 함
python scripts/build_ontology.py --check   # 오류 0 이어야 함 (경고는 봐도 됨)
python eval/run_gold_check.py              # 63/63 유지되어야 함
```

`run_gold_check` 는 **HCX를 쓰지 않습니다.** 한도와 무관하니 몇 번이든 돌리세요.

---

## 6. 반영 — 고친 파일에 따라 두 갈래

```bash
git add ontology/... && git commit && git push
```

| 고친 것 | 명령 | 시간 |
| :-- | :-- | :-- |
| `enums/*.yaml` (질의 규칙) | `bash deploy/deploy.sh --yaml-only` | 약 5초 |
| `shared/*.yaml` (개체·alias) | `python scripts/build_ontology.py` → `bash deploy/deploy.sh --db-only` | 약 1분 |

**왜 다른가**: `enums` 의 규칙은 yaml 파일에서 바로 읽지만, `shared` 의 개체는 **DB 안의 `kg_*` 테이블로 구워지기** 때문입니다. 개체를 고치면 KG를 다시 만들어 DB째 보내야 합니다.

> 배포는 SSH가 열린 자리에서만 됩니다. 안 되면 담당자에게.

---

## 7. 마지막 — 회귀로 고정

**이걸 안 하면 같은 오답이 또 나옵니다.** 고친 질의를 평가 문항으로 올립니다.

`eval/questions_<도메인>.jsonl` 에 한 줄 추가:

```json
{"qid": "ETF-D-024", "difficulty": "중", "qtype": "조건검색", "expected_behavior": "answer",
 "question": "실험에서 틀렸던 질문 그대로",
 "gold_sql": "SELECT ... LIMIT 30",
 "must_include": ["답변에 반드시 있어야 할 것"],
 "must_not_include": ["있으면 오답인 것"],
 "note": "왜 이 문항이 필요한지 — 무엇이 틀렸었나"}
```

`expected_behavior` 는 `answer` · `unanswerable` · `clarify` 중 하나입니다. 그다음 `python eval/run_gold_check.py`.

---

## 하면 안 되는 것

| ❌ | 왜 |
| :-- | :-- |
| `.auto.yaml` · `*.ttl` · `kg_*` 직접 수정 | 생성물. 다음 빌드에 사라집니다 |
| 1차(7/11) 수치를 그대로 옮겨 적기 | 2차와 컬럼명·모수가 다릅니다 |
| 판정을 문서·슬랙에만 적기 | 프롬프트에 안 들어갑니다 |
| 실측 없이 "아마 이럴 것" 으로 규칙 쓰기 | 그 규칙이 그대로 답변이 됩니다 |
| 9/6 코드 프리즈 이후 이 루프 돌리기 | 제출물 변경 = 실격 |
