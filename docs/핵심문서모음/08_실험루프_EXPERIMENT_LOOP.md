# 🔁 실험 루프 — 챗봇으로 관찰하고 온톨로지를 고친다

> 2026-08-26 신설. 목표는 **"채팅 → 오답 발견 → yaml 수정 → 반영 → 회귀 고정"** 을 한 바퀴로 만드는 것.

---

## 0. 왜 yaml 인가

플래너(HCX)에 넘어가는 근거문서는 **코드가 아니라 yaml 에서 나옵니다.**

```
ontology/enums/*.yaml  ─ query_rules · normalization ─┐
ontology/shared/*.yaml ─ kg_node/kg_alias ───────────┼─▶ pipeline.build_grounding()
schema_metadata (DB)   ─ 컬럼·한글명 ─────────────────┘        │
                                                              ▼
                                                    HCX plan_sql 프롬프트
```

`build_grounding()` 은 네 덩어리를 이어 붙입니다 — **KG 개체 매핑 · 도메인 규칙 · 교차질의 조인 키 · 스키마**.
그래서 **판정을 문서에 적으면 챗봇은 모릅니다. yaml 에 적어야 프롬프트가 바뀝니다.**

실제로 확인된 예: `유동화위험금지` 규칙에 `Conduit회사채` 를 넣자, 다음 질의의 답이 3,036 → **4,045건**으로 바뀌었습니다.

---

## 1. 한 바퀴

| 단계 | 명령 | 걸리는 시간 |
| :-- | :-- | :-- |
| ① 관찰 | `python -m src.chat` (또는 `/chat?t=…`) | 질의당 3~6초 |
| ② 판정 | `ontology/enums/*.yaml` · `ontology/shared/*.yaml` 수정 | — |
| ③ 반영 | `python scripts/build_ontology.py` | kg_* 4테이블 + ttl 5분할 재생성 |
| ④ 확인 | 다시 ① (로컬은 즉시 / 서버는 `/reload`) | — |
| ⑤ 고정 | 오답을 `eval/questions_*.jsonl` 로 승격 → `python eval/run_gold_check.py` | HCX 불필요, 무제한 |

⑤를 건너뛰면 같은 오답이 다시 나옵니다. `run_gold_check` 는 **HCX 를 쓰지 않고 SQL 만 검증**하므로 rate limit 과 무관하게 몇 번이든 돌릴 수 있습니다.

### 로그가 산출물입니다

- 로컬 CLI → `logs/chat-YYYYMMDD.jsonl`
- 서버 API → `logs/api-YYYYMMDD.jsonl` (compose 가 `./logs` 로 마운트)

두 파일 모두 질의·답변·`retrieved_context`·`think_trace`·소요시간을 남깁니다. **틀린 질의를 여기서 골라 ⑤로 올립니다.**

---

## 2. 명령 모음

```bash
# 로컬 실험
python -m src.chat                          # 대화형
python -m src.chat -q "질문"                 # 한 건
python -m src.chat -f questions.txt          # 파일 배치
python -m src.chat --no-hcx -q "질문"        # Ground·Gate 만 (HCX 호출 0회)

# 반영
python scripts/build_ontology.py             # yaml → kg_* + ttl 5분할
python scripts/build_ontology.py --check     # 검증만 (산출물 생성 안 함)
python scripts/check_yaml_dupkeys.py         # yaml 중복키

# 회귀
python -m pytest tests -q
python eval/run_gold_check.py

# 서버 (로컬에서 실행)
bash deploy/deploy.sh                        # 코드 + DB + 기동
bash deploy/deploy.sh --code-only            # 코드만
bash deploy/deploy.sh --db-only              # DB만 + restart
curl -X POST -H "X-Reload-Token: $RELOAD_TOKEN" https://<IP>.nip.io/reload
```

---

## 3. 알고 써야 하는 제약

**① rate limit 이 병목입니다 — 레이턴시가 아닙니다.**
실측 p95 ~2초지만 토큰 한도 때문에 **분당 질의 3.6개**가 천장입니다 (`docs/bench/hcx_latency.md` 결론 3).
질의 1건 = HCX 2회(plan_sql + compose_answer)입니다. 팀원 여럿이 동시에 치면 바로 429 입니다.
→ 근거문서를 키우면 그만큼 처리량이 줄어듭니다. `build_grounding` 이 **탐지된 테이블만** 싣는 이유입니다.

**② `/reload` 는 워커별 캐시만 갱신합니다.**
`load_context()` 가 `@lru_cache(maxsize=1)` 이고 uvicorn 이 `--workers 2` 로 뜹니다.
한 번의 `/reload` 는 **한 워커만** 갱신합니다. 확실히 하려면 `docker compose restart api`.

**③ DB 파일을 갈았으면 `/reload` 로는 부족합니다.**
컨테이너가 잡고 있는 fd 는 옛 inode 를 가리킵니다. 반드시 `restart`.

**④ `/chat` 토큰은 UI 접근만 막습니다.**
`/answer` 는 평가 계약상 열려 있어야 하므로, 주소를 아는 사람은 직접 호출할 수 있습니다.
키 소진이 걱정되면 평가 기간 전까지 ACG 나 Caddy 에서 IP 를 제한하세요.

**⑤ 9/6 코드 프리즈 이후에는 이 루프를 돌리지 않습니다.**
제출물 변경은 실격 사유입니다. 프리즈 시점에 실험 경로(`/chat`)를 내리는 것을 전제로 씁니다.

---

## 4. 이 구조가 잡아낸 것들 (2026-08-26)

실험 4문항을 돌리는 동안 나온 실제 버그입니다 — 전부 회귀 테스트로 고정했습니다.

| 증상 | 원인 | 교훈 |
| :-- | :-- | :-- |
| "미래에셋자산운용이 운용하는 국내 ETF" → 0행 | Ground 가 대상 테이블을 안 보고 채권 발행사 노드를 골랐다 | 같은 표기가 여러 도메인에 걸린다 |
| `cu_fund_mgmt_co='Org_issuer_…'` | 근거문서에 개체 ID 를 실었다 | 플래너에는 **DB 실제 값만** 넘긴다 |
| "신용등급 AAAA**인** 채권" 이 게이트 통과 | `\b` 정규식 — 파이썬 re 에서 한글은 단어 문자다 | 테스트가 조사 없는 어투만 검사하고 있었다 |
| "삼성전자를 보유한 ETF" → OperationalError | 마스터에 없는 `constituent` 를 WHERE 에 썼다 | 교차질의는 **조인 키**를 근거로 줘야 한다 |
| "유동화 채권 몇 건이야?" → 기각 | `COUNT(*)` 에 LIMIT 이 없다고 guard 가 막았다 | 기각이 아니라 **보정**이 맞다 |

공통점: **단위 테스트로는 안 잡히고, 실제 질의를 흘려보내야 나왔습니다.** 루프를 만드는 이유입니다.
