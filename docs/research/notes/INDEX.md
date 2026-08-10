# 선행연구 노트 INDEX

금융 도메인 온톨로지 / LLM·KG 스키마 설계 관련.

| id | 제목 | 🔍 확인 수준 | 우선순위 | 한 줄 요지 | 🚫 적용 가능성 |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `FIBO_funds-model` | FIBO — Collective Investment Vehicles | **부분 확인** (클래스·속성 목록 추출) | 높음 | 펀드 종류(주식형·채권형)는 **owl:Class 하위클래스**이고, 클래스(종류형)는 `FundShareClassUnit` 별도 개체 | **조건부** — 층위 원칙·명명만 차용. 보수·포트폴리오·환매조건이 우리 데이터에 없어 통째 임포트는 빈 클래스 양산 |

---

## 아직 검색 요약 수준 (신뢰 불가 — 원문 확인 필요)

아래는 **검색 결과 스니펫만** 본 것입니다. 카드로 만들지 않았습니다.

| 주제 | 단서 | 왜 볼 만한가 |
| :--- | :--- | :--- |
| SKOS vs OWL 분류 모델링 | [W3C SKOS Reference](https://www.w3.org/TR/skos-reference/) | 분류 체계를 개체로 둘지 클래스로 둘지의 표준 근거. SKOS 는 개념을 **individual** 로 모델링 |
| Semantic Layers for LLM Analytics | arXiv 2604.25149 | 시맨틱 레이어가 LLM 분석의 정확도·환각에 미치는 영향 (3개 모델 페어 벤치마크) |
| Ontology-grounded KG construction | arXiv 2510.20345 (survey) | LLM 으로 KG 구축 시 온톨로지를 지시 프롬프트로 쓰는 방법 |
| Text2GQL-Bench | arXiv 2602.11745 | 자연어 → 그래프 질의 벤치마크 |
| KG-LLM-Papers | [zjukg/KG-LLM-Papers](https://github.com/zjukg/KG-LLM-Papers) | KG+LLM 논문 목록 — 후속 탐색 출발점 |

> ⚠️ **위 항목은 인용하지 마세요.** 원문을 읽고 카드를 만든 뒤에만 근거로 씁니다.
