# 선행연구 노트 INDEX

금융 도메인 온톨로지 / LLM·KG 스키마 설계 + 대회 벤치마크 관련.
종합 판단은 [`../선행연구_종합_2026-08-30.md`](../선행연구_종합_2026-08-30.md) — "어떤 관계를 잡아야 하나 · 관계 외에 무엇이 정확도를 좌우하나".
설계 관점 정리는 [`../KG_온톨로지_설계_인사이트_2026-08-30.md`](../KG_온톨로지_설계_인사이트_2026-08-30.md) — 인사이트 8개 + kg_node·kg_alias·kg_edge·yaml·파생·검증 구성요소별 포인트.
구현·기대효과는 [`../개선_구현_및_기대효과_2026-08-30.md`](../개선_구현_및_기대효과_2026-08-30.md).
현 구축물·계획과의 대조·개정안은 [`../온톨로지_개정안_2026-08-30.md`](../온톨로지_개정안_2026-08-30.md).
카드 작성 시 대조한 과제 제약은 [`../TASK_CONTEXT_2026-08-30.md`](../TASK_CONTEXT_2026-08-30.md).

| id | 제목 | 🔍 확인 수준 | 우선순위 | 한 줄 요지 | 🚫 적용 가능성 |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `SL-1` [semantic-layer-benchmark](semantic-layer-benchmark.md) | Semantic Layers for Reliable LLM-Powered Data Analytics (arXiv 2604.25149, 2026) | **원문 정독** (Fig.1 미렌더) | 🔥필독 | 4KB 규칙 문서 하나로 **+17.2~+23.2pp**(Table 1), 모델 간 차이는 ~5pp. 검색형 < 통째 주입(§6.5). 이득은 테이블 선택·스냅샷·지표 공식·센티넬·기준일 5범주(§5.4). **관계(edge) ablation 없음** | **가능** — 우리 yaml 이 그 문서. 도메인당 ~2,200토큰 목표·기준일 고정 문장·gold 63 paired 재실행 |
| `JAMIA-1` [jamia2025_pvsql-business-context](jamia2025_pvsql-business-context.md) | Automating PV evidence generation: context-aware SQL (JAMIA Open 2025, 주최 인용) | **원문 정독** (Fig·부록 S1 미확인) | 🔥필독 | 주최 인용 **8.3%→78.3%** 본문 확인(Table 1·2). 스키마 축소만으로는 10%(Table 3) — 문서가 일한다. 기전 = 개념→(컬럼,값) 규칙 | **가능** — 절대치는 옮기지 말 것(n=60, 33테이블을 gold 보고 선정). 순서와 기전만 인용 |
| `DK-1` [2510.02394_domain-knowledge-retrieval-text2sql](2510.02394_domain-knowledge-retrieval-text2sql.md) | Retrieval and Augmentation of Domain Knowledge for Text-to-SQL (arXiv 2510.02394, 2025) | **원문 정독** (Fig.1·2 깨짐) | 🔥필독 | 규칙 **전부 주입 39.0 < 선별 주입 47.5**(Table VI), `'표현' refers to SQL조각` 형식 > 평문, 사람 검수 +4~7pp. 관계 근거 없음 | **가능**(트리거 기반 선별·구조화 형식) / **조건부**(임베딩 SbR — 한국어 어절 미검증) |
| `ENT-1` [2606.03363_entsql-enterprise-grounding](2606.03363_entsql-enterprise-grounding.md) | EntSQL: Grounding Text-to-SQL in Long-Context Enterprise Knowledge (arXiv 2606.03363, 2026) | **원문 정독** (Fig.2 일부 미판독) | 📖참고 | 짧은 evidence > 긴 문서 > 없음(6.8→15.9→21.4, Table 2). **실패 54.6% 가 WHERE/enum 값 오류**(Fig. 4), 조인은 Other 21% 일부. 언어 차이 미미 | **조건부** — 규칙 라우팅·enum 검증기 가능, 벤치마크 자체는 불가 |
| `KGQA-1` [2507.04127_byokg-rag](2507.04127_byokg-rag.md) | BYOKG-RAG: Multi-Strategy Graph Retrieval for KGQA (arXiv 2507.04127, 2025) | **원문 정독** (표 열 섞임 복원) | 🔥필독 | 관계형·집계형 KG(Northwind)는 **질의 생성 55.3 vs 트리플 검색 0.7·홉 탐색 3.4**(Table 1). 링킹 산출물 다변화 +4~9, 실행 되먹임 1회 +9.6(Table 7). 관계 타입별 ablation 없음 | **조건부** — Linker 1회+되먹임 1회로 자르면 가능. 초안답(LLM 지식)은 채택 금지 |
| `KGG-1` [2606.22419_kg-grounding-only-out-of-training](2606.22419_kg-grounding-only-out-of-training.md) | KG Grounding Helps LLMs Only for Out-of-Training Knowledge (arXiv 2606.22419, 2026) | **원문 정독** (Fig 캡션만) | 🔥필독 | 공개 KG **+0**, 학습 밖 사실 **+77pp**(Table 3·4), LLM 없는 데이터 계층 100%. 이름에서 추론 가능한 속성은 그라운딩 이득 없음(inferable). verbatim 개체 제약 0→82% | **조건부** — 결론·verbatim 제약·이름 규약은 조건식 규칙으로(파생 컬럼 안은 8/30 저녁 폐기) 가능, Cypher·벡터·재시도 루프 불가 |
| `REF-1` [2601.10398_latent-refusal-text2sql](2601.10398_latent-refusal-text2sql.md) | LatentRefusal: Latent-Signal Refusal for Unanswerable Text-to-SQL (arXiv 2601.10398, 2026) | **원문 정독** (부록 표 일부 깨짐) | 📖참고 | 생성 전·실행 없는 답변가능성 게이트 정식화. API 프롬프트 기준선도 금융 도메인 97.2 F1(Table 1). 거절 유형 9종(부록 A) | **불가**(hidden state 탐침) / **조건부**(정식화·거절 유형 → `refusal_rules`) |
| `SCH-1` [2505.18363_schemagraphsql-fk-pathfinding](2505.18363_schemagraphsql-fk-pathfinding.md) | SchemaGraphSQL: FK 그래프 경로탐색 스키마 링킹 (arXiv 2505.18363, 2025) | **원문 정독** | 📖참고 | 재현율 우선 union 이 정밀 선택보다 EX +2~12pp(Table 3). oracle 링킹과 1.5pp 차 → 병목은 링킹이 아님. **8테이블에선 그래프가 퇴화** | **조건부** — `JOIN_KEYS` 를 "조인 경로 문자열"로 프롬프트에, 테이블 라우팅 union. FK edge 는 KG 에 넣지 않음 |
| `VAL-1` [2506.07245_sde-sql-value-retrieval](2506.07245_sde-sql-value-retrieval.md) | SDE-SQL: Self-Driven Exploration with SQL Probes (arXiv 2506.07245, 2025) | **원문 정독** | 📖참고 | 탐색(값·컬럼 후보 해소) −3.2pp, 스키마 링킹 −0.8pp(Table 1). **"빈 결과=오류" 전제** — 거절 문항과 충돌. 0행 진단은 SQLGlot 규칙(LLM 0회) | **조건부** — 규칙 기반 Sub-SQL 0행 진단만 가능, 프로브·self-consistency·LIKE 완화 불가 |
| `ONT-1` [2410.09244_progressive-ontology-reveal](2410.09244_progressive-ontology-reveal.md) | Progressively Revealing Ontologies (RelationalAI, arXiv 2410.09244, 2024) | **원문 정독** (Fig.1 미확인) | 📖참고 | 큰 온톨로지는 "딱 필요한 조각"만. 온톨로지에 담을 것 = 개념·관계의 자연어 서술 + 형식 서술 + 개념 간 경로. **정량 실험 없음**(Sequeda 16→54% 인용뿐) | **조건부** — 근사 단계를 KG Ground 로 대체 시 원리 적용, 수치 근거로는 불가 |
| `2025-winner-benchmark` | 2025(9회) 대상작 "기술적 분석 특화 금융 에이전트" | **슬라이드 직접 확인** (1~8·20·22 / 9~19 미확인) | 매우 높음 | 우리 아키텍처 방향 검증 + 사업화(§5) 모범답안 | **뼈대만 차용** |
| `FIBO_funds-model` | FIBO — Collective Investment Vehicles | **부분 확인** (클래스·속성 목록) | 높음 | 펀드 종류는 owl:Class 하위클래스, 클래스(종류형)는 `FundShareClassUnit` 별도 개체 | **조건부** — 층위 원칙·명명만 |

---

## 아직 검색 요약 수준 (신뢰 불가 — 원문 확인 필요)

| 주제 | 단서 | 왜 볼 만한가 |
| :--- | :--- | :--- |
| 🔵 **주최 측 자체 벤치마크** (테크세션 23쪽) | 국내 ETF 도메인 · 자체 72문항 | 채점자의 사고 틀: ① SQL 실행성공 ~100% vs 정답률 45% ② 온톨로지 — 프롬프트 설명 주입 **+2.4pp** vs **런타임 식별 +20pp** ③ RDB 테마 0건 / Graph 36건 ④ 단일 검색기 천장 ~66% |
| Sequeda / Allemang — 온톨로지 제약 하 환각 0 (OBQC) | arXiv 2311.07509 · SL-1 §2.6 인용 | SL-1·ONT-1 이 "관계·온톨로지 제약의 효과" 근거로 **2차 인용**만 하는 원 논문. edge 설계 근거가 필요하면 다음 카드 대상 |
| Evaluation of Entity and Relation Linking for KGQA (K-CAP 2025) | ACM DL, 스니펫: "LLM 링커 재현율 우선이 종단 성능에 유리" | SCH-1 의 재현율 우선 결론과 같은 방향. 유료 |
| SKOS vs OWL 분류 모델링 | [W3C SKOS Reference](https://www.w3.org/TR/skos-reference/) | 분류 체계를 개체로 둘지 클래스로 둘지의 표준 근거 |
| Ontology-grounded KG construction (survey) | arXiv 2510.20345 | LLM 으로 KG 구축 시 온톨로지를 지시 프롬프트로 쓰는 방법 |
| KG-LLM-Papers | [zjukg/KG-LLM-Papers](https://github.com/zjukg/KG-LLM-Papers) | 후속 탐색 출발점 |

> ⚠️ **위 항목은 인용하지 마세요.** 원문을 읽고 카드를 만든 뒤에만 근거로 씁니다.
