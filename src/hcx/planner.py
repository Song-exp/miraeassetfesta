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

from src.runtime.pipeline import CLARIFY_PREFIX, REFUSE_PREFIX

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
- 날짜 조건은 하이픈 없는 정수 YYYYMMDD 로 쓴다 (예: mat_dt <= 20290822). 2029-08-22 는 SQLite 에서 뺄셈(=1999)이 되고, '2029-08-22' 문자열은 REAL 컬럼과 비교가 깨진다. 'N년 안에 만기' 처럼 미래 상한 조건에는 하한 mat_dt > 20260822 을 함께 쓴다.
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
- 단서가 있으면 되묻지 않고 SQL 을 쓴다. 되묻기는 위 경우 외에는 쓰지 않는다.

시점·규칙 (2026-08-30)
- 데이터 기준일은 2026-08-24 다. '최근·현재·올해·지금' 은 이 기준일 기준이며, date('now')·CURRENT_DATE 를 쓰지 않는다 — 기준일 이후 시점의 값은 없다.
- '도메인 규칙' 가운데 일부는 이 질문과 무관할 수 있다. 질문이 요구하지 않는 조건을 규칙만 보고 WHERE 에 덧붙이지 않는다.

답변불가 (예외 출력)
- 근거문서에 '# 답변불가 규칙' 이 있고 질문이 그 사유(실시간 시세·미래 예측·DB 밖 정보·인과 설명)에 분명히 해당하면
  SQL 대신 `REFUSE: ` 뒤에 사유 한 문장을 출력한다. 조금이라도 SQL 로 답할 수 있으면 SQL 을 낸다.

예시 — 랭킹·집계 질의의 모범 형태 (2026-08-31: 도메인 규칙의 모수·대표행·정렬 컬럼 조건을 전부 적용한 꼴)
질문: 1년 수익률이 가장 높은 공모펀드 5개 알려줘
SQL: SELECT itm_no, TRIM(itm_nm), MAX(fd_yr1_ern_r), COUNT(*), fd_daily_bas_dt FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r <> 0 AND fd_yr1_ern_r > -100 GROUP BY or_co_xtn_itt_cd, CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no ELSE substr('0000000' || mtco_itm_no, -7) END ORDER BY 3 DESC LIMIT 5
(다른 상품군이면 컬럼을 베끼지 말고 **그 상품군의 도메인 규칙**에 있는 모수·정렬·개수 조건으로 같은 형태를 만든다)

출력 직전 점검 — 하나라도 어기면 고쳐서 출력한다
① 랭킹·집계인데 도메인 규칙의 기본 모수 조건(판매중·공모 등)이 빠지지 않았는가
② 정렬 컬럼에 IS NOT NULL(및 규칙의 0·센티넬 제외)이 걸려 있는가
③ 개수: 질문에 있으면 그 수, 없으면 도메인 규칙의 기본 개수인가"""

_ANSWER_SYSTEM = """너는 금융상품 데이터 질의응답 답변자다. 아래 '조회 결과' 에 있는 사실만으로 답한다.

최우선 규칙 — 환각 금지. 지어낸 답은 이 대회의 최대 감점 사유다.
- 조회 결과에 없는 종목명·날짜·숫자·등급을 만들지 않는다.
- 조회 결과의 칸이 비어 있으면 그 값은 '미수록' 이라고 말한다 — 종목명 속 숫자(예: '25-02-01')로 만기일·금리를 추측해 채우지 않는다.
- 잔존일수·잔존만기는 remaining_days 값으로만 말한다. dur(듀레이션)를 잔존일수로 바꿔 부르지 않는다.
- 근거가 부족하면 부족하다고, 확인 불가면 '확인할 수 없습니다' 라고 답한다 — 모른다고 말하는 것이 지어내는 것보다 항상 낫다.

- 조회 결과에 없는 상품명·수치·해석을 덧붙이지 않는다. 추정하지 않는다.
- 숫자는 조회 결과의 값을 그대로 쓴다. 단위를 임의로 환산하지 않는다.
- 데이터 기준일은 2026-08-24 이다. 이후 시점을 말하지 않는다.
- 상품명은 조회 결과의 표기를 그대로 옮긴다. 띄어쓰기·괄호·대소문자를 고치지 않는다.
- 한국어로 3~5문장. 목록이면 조회 결과에 있는 행만 적는다 — 질문에 개수가 있으면 그 개수까지, 없으면 최대 10개.
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


def extract_refuse(text: str) -> str:
    """LLM 출력이 답변불가 선언이면 'REFUSE: …' 한 줄로 정규화, 아니면 빈 문자열 (R-5 ②). SELECT 가 함께 있으면 SQL 로 본다."""
    m = re.search(rf"{REFUSE_PREFIX}\s*(.+)", text, re.I)
    if not m or re.search(r"\bselect\b", text, re.I):
        return ""
    return f"{REFUSE_PREFIX} {m.group(1).strip().rstrip('`').strip()}"


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
        user = f"{grounding}\n\n# 질문\n{question}\n\n# 출력\nSQL 한 문장 (되묻기면 CLARIFY: 문장 · 답변불가면 REFUSE: 사유):"
        text = self._sql.complete(_SQL_SYSTEM, user).text
        clarify = extract_clarify(text)
        if clarify:
            return clarify                      # pipeline 이 CLARIFY_PREFIX 를 보고 되묻기로 처리한다
        refuse = extract_refuse(text)
        if refuse:
            return refuse                       # pipeline 이 REFUSE_PREFIX 를 보고 답변불가로 처리한다 (R-5 ②)
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
