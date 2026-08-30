# -*- coding: utf-8 -*-
"""HCX 플래너 — pipeline 의 `Planner` 프로토콜 구현체.

두 지점에서만 LLM 을 씁니다 (BUILD_PLAN §5 — 그 외 단계는 코드가 합니다):

  ① plan_sql       질의 + 근거문서 → SQLite SELECT 한 문장
  ② compose_answer 질의 + 조회 결과 → 한국어 답변

🔴 여기서 만든 SQL 을 신뢰하지 않습니다. 반환값은 pipeline.validate_sql() 이 다시 검사하고
   (SELECT 단일문·테이블 화이트리스트·LIMIT), 통과한 것만 read-only 커넥션에서 실행됩니다.
   즉 이 파일이 잘못된 SQL 을 내놓아도 DB 는 안전하고, 답변은 '확인 불가' 로 떨어집니다.

🔴 `compose_answer` 는 조회 결과 밖의 사실을 쓰지 못하게 프롬프트로 묶습니다. 환각은 감점
   1순위입니다 (PROJECT.md §2). 조회가 0건이면 여기까지 오지도 않습니다 — pipeline 이 먼저
   '확인할 수 없음' 으로 끊습니다.

토큰 예산: 벤치 결론 3 (docs/bench/hcx_latency.md) — 병목은 레이턴시가 아니라 rate limit
(분당 질의 3.6개)입니다. 그래서 근거문서는 pipeline 이 **탐지된 테이블만** 담아 보냅니다.
"""

from __future__ import annotations

import os
import re

from src.runtime.pipeline import CLARIFY_PREFIX

from .client import HCXClient, HCXConfig

# SQL 출력 상한. 🔴 512 는 부족하다 (2026-08-30 밤 실측) — 채권 추천 SQL 은 yaml 의 '구조'(693자)·'보강'(533자) CASE 를 그대로
# 옮겨 적어야 해서 1,757자(추정 660~840토큰)가 되고, 512 에서 잘리면 SELECT 가 중간에 끊겨 validate/실행에서 죽는다.
# max_tokens 는 상한이지 사용량이 아니다 — 짧은 SQL 의 비용은 그대로다. HCX-005 출력 한도(4,096) 안.
SQL_CONFIG = HCXConfig(model="HCX-005", max_tokens=1536, temperature=0.0)
ANSWER_CONFIG = HCXConfig(model="HCX-005", max_tokens=1024, temperature=0.0)

_SQL_SYSTEM = """너는 SQLite SQL 생성기다. 주어진 스키마·도메인 규칙·개체 매핑만 사용해 질문을 SQL 한 문장으로 옮긴다.

출력 규칙
- SQL 한 문장만 출력한다. 설명·주석·코드펜스를 붙이지 않는다.
- SELECT 로 시작한다. INSERT·UPDATE·DELETE·DROP·PRAGMA 등은 금지다.
- 세미콜론을 붙이지 않는다.
- LIMIT 을 반드시 붙인다 (최대 30).
- 테이블 별칭(AS d, e, h …)을 쓰지 않는다. 컬럼은 항상 `테이블명.컬럼명` 으로 적는다.
  (별칭과 근거문서의 조인 키를 섞어 `d.ext_etf_holdings.ticker` 같은 잘못된 이름을 만드는 사고가 있었다.)

근거 규칙
- FROM·JOIN 에는 근거문서에 나온 테이블만 쓴다.
- 스키마에 없는 컬럼은 존재하지 않는 것이다. 만들어내지 않는다.
- 'KG 개체 매핑' 에 DB 실제 값이 주어졌으면 그 값으로 정확히 일치 조건을 쓴다 (LIKE 로 흉내내지 않는다).
- '도메인 규칙' 에 조건식이 있으면 그 조건식을 그대로 쓴다.
- '교차질의 조인 키' 가 주어졌으면 그 조건으로 JOIN 한다. 구성종목·설명서 조건은 외부 테이블의 컬럼이다 — 마스터 테이블에 그 컬럼이 있는 것처럼 쓰지 않는다.
- 값은 근거문서에 나온 것만 쓴다. 개체 식별자(Org_… · Idx_… 같은 내부 ID)를 값으로 쓰지 않는다.
- 사람이 읽을 수 있는 상품명 컬럼을 함께 SELECT 한다.
- 근거문서에 '# 시점 주의' 가 있으면 그 연도는 만기일(mat_dt) 조건에만 쓴다. 그 시점의 가격·수익률·전망을 묻는 질문이면 연도를 SQL 에 쓰지 않는다.

되묻기 (예외 출력)
- 근거문서에 '# 되묻기 규칙' 이 있고, 질문의 낱말이 그 규칙의 다의어에 해당하며, 어느 뜻인지 정할 단서가 질문에 없을 때만
  SQL 대신 `CLARIFY: ` 뒤에 사용자에게 되물을 한 문장(한국어, 선택지를 보여 준다)을 출력한다.
- 단서가 있으면 되묻지 않고 SQL 을 쓴다. 되묻기는 위 경우 외에는 쓰지 않는다."""

_ANSWER_SYSTEM = """너는 금융상품 데이터 질의응답 답변자다. 아래 '조회 결과' 에 있는 사실만으로 답한다.

- 조회 결과에 없는 상품명·수치·해석을 덧붙이지 않는다. 추정하지 않는다.
- 숫자는 조회 결과의 값을 그대로 쓴다. 단위를 임의로 환산하지 않는다.
- 데이터 기준일은 2026-08-22 이다. 이후 시점을 말하지 않는다.
- 상품명은 조회 결과의 표기를 그대로 옮긴다. 띄어쓰기·괄호·대소문자를 고치지 않는다.
- 한국어로 3~5문장. 목록이면 최대 10개까지만 적는다.
- 조회 결과가 질문에 답하기에 부족하면 부족하다고 말한다.
- '# 답변 규칙' 이 주어지면 그에 따라 표현한다. 규칙은 조회 결과를 읽는 방법(빈 칸의 뜻·주의 문구·용어)이지 새 사실이 아니다."""

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.S | re.I)


def extract_sql(text: str) -> str:
    """LLM 출력에서 SQL 한 문장을 꺼낸다.

    프롬프트로 코드펜스를 금지해도 모델은 종종 붙인다. 형식 위반을 여기서 흡수하고,
    그래도 SELECT 가 아니면 그대로 돌려보낸다 — 기각은 validate_sql 의 몫이다.
    """
    s = text.strip()
    m = _FENCE.search(s)
    if m:
        s = m.group(1).strip()
    # 앞머리 잡담 제거 — 첫 SELECT 부터가 SQL 이다
    m = re.search(r"\bselect\b", s, re.I)
    if m:
        s = s[m.start():]
    s = s.split(";")[0]                      # 세미콜론 이후는 버린다 (다중 문장 방지)
    return re.sub(r"\s+", " ", s).strip()


def extract_clarify(text: str) -> str:
    """LLM 출력이 되묻기면 'CLARIFY: …' 한 줄로 정규화해 돌려주고, 아니면 빈 문자열.

    코드펜스·앞머리 잡담이 붙어도 첫 CLARIFY: 부터 그 줄 끝까지를 되묻는 문장으로 본다.
    SELECT 가 함께 있으면 SQL 로 본다 — 되묻기는 SQL 을 대신할 때만 유효하다.
    """
    m = re.search(rf"{CLARIFY_PREFIX}\s*(.+)", text, re.I)
    if not m or re.search(r"\bselect\b", text, re.I):
        return ""
    return f"{CLARIFY_PREFIX} {m.group(1).strip().rstrip('`').strip()}"


class HCXPlanner:
    """pipeline.Planner 구현. 호출 2회(plan_sql·compose_answer)가 한 질의의 HCX 예산이다."""

    def __init__(
        self,
        *,
        sql_client: HCXClient | None = None,
        answer_client: HCXClient | None = None,
    ):
        self._sql = sql_client or HCXClient(SQL_CONFIG)
        self._answer = answer_client or HCXClient(ANSWER_CONFIG)

    # -- Planner 프로토콜 -------------------------------------------------
    def plan_sql(self, question: str, grounding: str) -> str:
        user = f"{grounding}\n\n# 질문\n{question}\n\n# 출력\nSQL 한 문장 (되묻기면 CLARIFY: 문장):"
        text = self._sql.complete(_SQL_SYSTEM, user).text
        clarify = extract_clarify(text)
        if clarify:
            return clarify                      # pipeline 이 CLARIFY_PREFIX 를 보고 되묻기로 처리한다
        return extract_sql(text)

    def compose_answer(self, question: str, rows: str, answer_rules: str = "") -> str:
        rules = f"# 답변 규칙 (ontology/*.yaml answer_rules)\n{answer_rules}\n\n" if answer_rules else ""
        user = f"# 질문\n{question}\n\n{rules}# 조회 결과 (첫 줄은 컬럼명)\n{rows}\n\n# 답변"
        return self._answer.complete(_ANSWER_SYSTEM, user).text.strip()

    def close(self) -> None:
        self._sql.close()
        self._answer.close()


def build_planner() -> HCXPlanner | None:
    """키가 있으면 플래너를, 없으면 None 을 준다.

    None 이면 pipeline 이 Ground·Gate 까지만 돌고 '구축 중' 으로 응답한다 —
    키가 없다고 서버가 죽으면 안 된다 (평가 계약: 어떤 경우에도 200 + 5필드).
    """
    if not os.environ.get("HYPERCLOVA_API_KEY"):
        return None
    return HCXPlanner()
