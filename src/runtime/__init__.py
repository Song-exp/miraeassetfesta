"""런타임 에이전트 파이프라인.

질의 → [Ground] KG 개체 매핑 → [Gate] 온톨로지·enum 네거티브 검사 → [Plan] SQL 생성(HCX)
     → [Guard] SQL 사후 검사 → [Execute] SQLite → [Answer] 답변 + think_trace

yaml(enums·shared)과 kg_* 테이블이 판단의 원천이다 — 이 코드는 그걸 읽어 집행만 한다.
"""
