"""파이프라인 오케스트레이터 — 단계별 실행 + think_trace 조립.

think_trace 는 각 단계가 **실제로 한 일**의 로그다 (LLM 생성물 아님 — hcx/client.py 원칙).
Plan(SQL 생성)·Answer(문장 생성)는 planner 인터페이스 뒤에 있다 — HCX 미연결 환경에서도
Ground·Gate·Guard·Execute 는 전부 동작·테스트 가능하다.
"""

from __future__ import annotations

import difflib
import inspect
import os
import re
from functools import lru_cache
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from . import gate, guard
from .loader import EXT_TABLES, TABLES, RuntimeContext, connect_readonly, load_context
from .router import route

MAX_ROWS = 30            # retrieved_context 폭주 방지 — 근거는 표본이면 충분하다
# 플래너가 SQL 대신 되묻기를 돌려줄 때의 접두어 — yaml `clarify` 규칙이 근거. 되묻기는 답변불가 문항의 정답 형태다 (주최 8/25)
CLARIFY_PREFIX = "CLARIFY:"
# 플래너가 SQL 대신 답변불가를 선언할 때의 접두어 — enums/_refusal.yaml 이 근거 (2026-08-30 R-5 ② 층)
REFUSE_PREFIX = "REFUSE:"
# HCX 재생성 예산 — 값 검사·SQL 기각에서 **한 번만**, 누적 시간이 이 안일 때만 (agent_architecture_notes §5 누적 12초 · 호출 2회 상한).
# 🔴 0행은 재생성 대상이 아니다 — 거절이 정답인 문항에서 조건 완화 = 환각 (PROJECT.md §9)
REGEN_BUDGET_S = 12.0
SQL_TIMEOUT_S = 10.0
CUTOFF_INT = int(gate.DATA_CUTOFF.replace("-", ""))   # 20260822 — 날짜 컬럼은 정수 YYYYMMDD (REAL 적재)


@dataclass
class PipelineResult:
    question_id: str
    question: str
    retrieved_context: str = ""
    think_trace: str = ""
    answer: str = ""
    # ── 아래 둘은 평가 응답 5필드가 아니다. 로그·실험 UI 가 쓰는 검토용 필드다 ──
    # 🔴 "KG·온톨로지를 의도대로 썼는가" 를 검토하려면 이 둘이 있어야 한다.
    #    sql 없이는 조건식이 틀렸는지 매핑이 틀렸는지 구분할 수 없고,
    #    grounding 없이는 어떤 yaml 규칙이 실제로 프롬프트에 실렸는지 알 수 없다.
    sql: str = ""            # 실제로 실행한 SQL (LIMIT 보정 후). 기각됐으면 기각된 SQL
    grounding: str = ""      # 플래너에 넘긴 근거문서 원문


class Planner(Protocol):
    """SQL·답변 생성기 — HCX 구현체를 여기 꽂는다. 시그니처 외에 아무것도 가정하지 않는다."""

    def plan_sql(self, question: str, grounding: str) -> str: ...     # SQL 한 문장, 또는 "CLARIFY: 되물을 문장"
    def compose_answer(self, question: str, rows: str, answer_rules: str = "") -> str: ...


def _accepts_answer_rules(planner) -> bool:
    """compose_answer 가 세 번째 인자(answer_rules)를 받는가 — 2인자 구현체(옛 프로브)는 규칙 없이 부른다."""
    try:
        params = inspect.signature(planner.compose_answer).parameters
    except (TypeError, ValueError):
        return True
    return len(params) >= 3 or any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params.values())


# ── SQL 사후 검사 — LLM 이 만든 SQL 을 신뢰하지 않는다 ──────────────────
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|pragma|vacuum|replace\s+into)\b", re.I
)   # 🔧 2026-08-31 저녁: replace → replace into 만 금지. REPLACE(pd_nm,' ','') 문자열 함수는 정당한 읽기 연산인데 기각되고 있었다


_TABLE_QUALIFIER = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*[A-Za-z_]\w*")
# ext_* ↔ 마스터 조인 짝 (external_join 정본). validate_sql 이 남남 조인을 기각하는 근거.
_EXT_PAIR = {"ext_etf_holdings": "domestic_etfs", "ext_ovs_etf_holdings": "overseas_etfs",
             "ext_fund_holdings": "public_funds", "ext_fund_page": "public_funds"}
# 테이블 -> 컬럼 집합. validate_sql 이 `테이블.컬럼` 수식자의 소속을 검사한다.
# ctx 없이 호출되는 순수 함수라 모듈 수준에 캐시한다 — load_context() 가 채운다(없으면 검사 생략).
_COLUMNS_OF: dict[str, set] = {}


def set_column_index(schema: dict) -> None:
    """{테이블: [(컬럼, …), …]} 를 받아 수식자 검사용 색인을 만든다."""
    _COLUMNS_OF.clear()
    for t, cols in (schema or {}).items():
        _COLUMNS_OF[t.lower()] = {c[0].lower() if isinstance(c, (list, tuple)) else str(c).lower()
                                  for c in cols}


def _name_owners(cols: list[str], ctx) -> str:
    """없는 컬럼마다 '어느 테이블 것인지' 를 붙인다 — 재생성 1회가 같은 실수를 반복하지 않게.

    🔴 2026-08-31 서버 실측 — "안전한 etf상품 추천좀" 이 라우팅 미특정으로 4테이블 규칙을 전부 싣자
       HCX 가 펀드 컬럼(zrin_fd_ivst_risk_gcd 등)을 domestic_etfs 에 썼다. Guard 가 기각했으나
       피드백이 "스키마에 없는 컬럼" 뿐이라 재생성도 같은 컬럼을 다시 써서 답변이 통째로 실패했다.
       '그건 public_funds 컬럼이다' 를 알려주면 모델이 테이블을 바꾸거나 그 조건을 뺄 수 있다.
    """
    schema = getattr(ctx, "schema", {}) or {}
    every = sorted({c.lower() for t in schema for c, *_ in schema[t]})
    out = []
    for col in cols:
        owner = next((t for t in schema if any(c.lower() == col.lower() for c, *_ in schema[t])), None)
        if owner:
            out.append(f"{col}(→ {owner} 컬럼이다. 이 테이블에는 없다)")
            continue
        # 어느 테이블에도 없는 환각 컬럼 — 철자 유사 후보를 붙인다 (mtco_nm·cu_last_aum 류.
        # 2026-09-01 FND-035 실측: 힌트 없는 기각은 재생성도 같은 컬럼을 반복했다)
        near = difflib.get_close_matches(col.lower(), every, n=2, cutoff=0.6)
        hint = (f"(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: {', '.join(near)} — 뜻이 같다는 보장은 없다)"
                if near else "(어느 테이블에도 없는 컬럼이다 — 스키마 목록의 컬럼만 쓴다)")
        out.append(col + hint)
    return ", ".join(out)


def validate_sql(sql: str) -> str | None:
    """위반 사유를 반환. None 이면 통과."""
    s = sql.strip().rstrip(";")
    if ";" in s:
        return "다중 문장 금지"
    if not re.match(r"^\s*(?:select|with)\b", s, re.I):
        # WITH(CTE)도 읽기 전용 단일문 — FROM/JOIN 테이블 검사는 CTE 본문까지 훑는다 (2026-08-31 저녁 오탐 방지)
        return "SELECT 만 허용"
    if _FORBIDDEN.search(s):
        return "금지 키워드 포함"
    used = {t for t in TABLES if re.search(rf"\b{t}\b", s, re.I)}
    if not used:
        m = re.search(r"\bfrom\s+([\w.]+)", s, re.I)
        return f"허용 테이블 밖: {m.group(1) if m else '?'}"
    # FROM/JOIN 에 등장하는 모든 테이블이 마스터 4 + 외부 ext_* 안에 있어야 한다 (교차질의 조인 허용, 그 외 차단)
    ctes = {n.lower() for n in re.findall(r"\b([A-Za-z_]\w*)\s+as\s*\(", s, re.I)}  # WITH 별칭은 테이블이 아니다
    declared = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", s, re.I)} | ctes
    for t in declared - ctes:
        if t not in TABLES and t not in EXT_TABLES:
            return f"허용 테이블 밖: {t}"
    # 🔴 FROM/JOIN 에 없는 테이블을 `테이블.컬럼` 으로 참조하면 실행 시 OperationalError 가 난다.
    #    2026-08-31 서버 실측 — "Li Auto를 담은 국내 ETF":
    #      SELECT pd_nm FROM domestic_etfs WHERE TRIM(ext_etf_holdings.ticker)='LI' … → 실행 실패.
    #    Guard 는 "검사 통과" 를 찍고 Execute 에서 죽어 답변이 '오류가 발생해 확인할 수 없습니다' 로 나갔다.
    #    여기서 기각하면 재생성 1회(R-4)가 사유를 받아 JOIN 을 붙일 기회를 얻는다.
    #    별칭(`d.pd_nm`)은 걸리지 않는다 — 아는 테이블 이름일 때만 본다.
    known = set(TABLES) | set(EXT_TABLES)
    for qual in {m.group(1).lower() for m in _TABLE_QUALIFIER.finditer(s)}:
        if qual in known and qual not in declared:
            return f"FROM/JOIN 에 없는 테이블 참조: {qual} (JOIN 을 붙이거나 조건을 옮겨야 한다)"
    # 🔴 ext_* 는 조인 짝이 정해져 있다 — 다른 마스터와 섞으면 의미가 틀린 조인이 된다.
    #    2026-09-01 서버 실측(공식 예시 #3): domestic_etfs 를 ext_fund_holdings(펀드 보유)와
    #    d.pd_itm_no = h.grp 로 조인 — 컬럼은 각자 실존해서 수식자 검사를 통과했지만 키가 남남이라 0행.
    #    ext_* 단독 사용(ext_etf_holdings.etf_name 만 조회 등)은 정상이므로,
    #    **다른 마스터가 선언돼 있는데 제 짝이 없을 때만** 기각한다.
    for ext, master in _EXT_PAIR.items():
        if ext in declared and master not in declared and (declared & set(TABLES)):
            return (f"{ext} 의 조인 짝은 {master} 다 — 다른 마스터와 조인 금지"
                    f" (교차질의 조인 키 목록의 짝을 그대로 쓴다)")
    # 🔴 선언된 테이블이어도 **그 테이블에 없는 컬럼**을 수식자로 붙이면 실행이 깨진다.
    #    2026-08-31 서버 실측 — "하이닉스가 가장많이 편입된 상품":
    #      SELECT ... SUM(domestic_etfs.weight_pct) FROM domestic_etfs JOIN ext_etf_holdings ...
    #      weight_pct 는 ext_etf_holdings 컬럼인데 domestic_etfs 에 붙였다.
    #    guard.unknown_columns 는 SQL 안 **어느 테이블에든** 있으면 통과시켜 이걸 못 잡는다.
    #    수식자는 명시적이라 애매함이 없다 — 여기서 정확히 기각한다.
    if _COLUMNS_OF:
        for m in _TABLE_QUALIFIER.finditer(s):
            t, col = m.group(1).lower(), m.group(0).split(".")[-1].strip().lower()
            cols = _COLUMNS_OF.get(t)
            if cols and col not in cols:
                owner = next((o for o, c in _COLUMNS_OF.items() if col in c), None)
                hint = f" ({owner} 컬럼이다)" if owner else ""
                return f"{t} 에 없는 컬럼: {col}{hint}"
    if not re.search(r"\blimit\s+\d+", s, re.I):
        return "LIMIT 누락"
    return None


def ensure_limit(sql: str) -> tuple[str, bool]:
    """LIMIT 이 없으면 붙인다. (보정된 SQL, 보정했는지)

    🔴 기각이 아니라 보정이다. LIMIT 의 목적은 결과 폭주를 막는 것인데, `COUNT(*)` 처럼
       한 행만 나오는 집계 질의에는 애초에 필요가 없어 모델이 자연스럽게 생략한다.
       그걸 기각하면 정답 SQL 을 만들고도 답을 못 내놓는다
       (2026-08-26 실측: "유동화 채권 몇 건이야?" → 조건식은 정확했으나 LIMIT 누락으로 기각).
       상한을 강제하는 성질은 그대로 유지된다.
    """
    if re.search(r"\blimit\s+\d+", sql, re.I):
        return sql, False
    return f"{sql.strip().rstrip(';')} LIMIT {MAX_ROWS}", True


_DATE_LIT = re.compile(r"(['\"]?)\b((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})\b\1")


def normalize_date_literals(sql: str) -> tuple[str, bool]:
    """하이픈 날짜 리터럴을 정수 YYYYMMDD 로 치환. (보정된 SQL, 보정했는지)

    🔴 SQLite 에서 따옴표 없는 2029-08-22 는 날짜가 아니라 뺄셈(=1999)이다 — 2026-08-31 실측:
       '3년 안에 만기' 질의가 mat_dt <= 1999 가 되어 만기일 미수록(mat_dt=0) 행 4개만 통과했고,
       답변 생성기가 그 빈칸을 종목명 숫자로 메꿔 환각 만기일('25-02-01' → 2025-02-01)이 나갔다.
       '2029-08-22' 문자열도 금물 — mat_dt 는 REAL 이라 타입 서열(REAL < TEXT)로 전 행이 통과한다.
       기각이 아니라 보정이다(ensure_limit 원칙): 정답 조건식을 형식 때문에 버리지 않는다.
    """
    def _to_int(m: re.Match) -> str:
        y, mo, d = m.group(2), int(m.group(3)), int(m.group(4))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return m.group(0)                # 날짜 모양이 아니면 산술로 존중 (실데이터엔 없다)
        return f"{y}{mo:02d}{d:02d}"
    fixed = _DATE_LIT.sub(_to_int, sql)
    return fixed, fixed != sql


_MAT_UPPER = re.compile(r"\bmat_dt\s*<=?\s*(\d{8})\b", re.I)
_MAT_LOWER = re.compile(r"\bmat_dt\s*>=?\s*\d|\bmat_dt\s+between\b", re.I)


def ensure_maturity_lower_bound(sql: str) -> tuple[str, bool]:
    """만기 상한만 있는 SQL 에 기준일 하한을 주입. (보정된 SQL, 보정했는지)

    'N년 안에 만기' 에 상한(mat_dt <= 미래일)만 걸면 만기일 미수록 0값 4행·만기 경과 49행이
    통과한다 — NULL-안전 제외 규칙과 같은 계열의 결측 누수. 상한이 기준일 이후일 때만 붙인다:
    '만기 지난 채권' 질의(상한이 과거)와 BETWEEN(자체 하한)은 건드리지 않는다.
    하한은 >= — 기준일 당일 만기(잔존 1일) 7종목은 모수다 (2026-09-01 실측: > 가 이들을 누락).
    """
    if _MAT_LOWER.search(sql):
        return sql, False
    m = _MAT_UPPER.search(sql)
    if not m or int(m.group(1)) <= CUTOFF_INT:
        return sql, False
    s, e = m.span()
    return f"{sql[:s]}(mat_dt >= {CUTOFF_INT} AND {sql[s:e]}){sql[e:]}", True


_CUTOFF_STRICT = re.compile(rf"\bmat_dt\s*>\s*{CUTOFF_INT}(?:\.0)?\b")


def ensure_cutoff_inclusive(sql: str) -> tuple[str, bool]:
    """기준일 하한의 초과(>)를 이상(>=)으로 교정. (보정된 SQL, 보정했는지)

    2026-09-01 서버 실측: '만기가 가장 짧은 채권 뭐야' 가 mat_dt > 20260822 로 나가
    기준일 당일 만기 7종목(잔존 1일 동률 — 진짜 최단)을 건너뛰고 8/23 채권(잔존 2일)을 답함.
    구매가능 모수는 mat_dt >= 20260822 다(규칙 구매가능 · gold 전 문항 동일 표기).
    기준일 리터럴에 붙은 > 만 교정한다 — 다른 날짜의 부등호는 사용자 조건일 수 있어 불개입."""
    new = _CUTOFF_STRICT.sub(f"mat_dt >= {CUTOFF_INT}", sql)
    return (new, new != sql)


def align_maturity_year(sql: str, tokens: list[str]) -> tuple[str, bool]:
    """질문의 연도와 SQL 만기 상한의 연도가 다르면 상한 연도를 질문 연도로 교정. (보정된 SQL, 교정했는지)

    2026-08-31 실측: '28년 12월까지 만기' → HCX 가 상한을 20291231 로 오기(연도 +1).
    발동 조건(전부 만족할 때만 — 넓히면 BETWEEN·복수 연도 질의를 다친다):
      ① 질문의 미래 연도 토큰(YYYY)이 정확히 1개  ② SQL 의 mat_dt 상한(<= / <)이 정확히 1개
      ③ 그 상한 리터럴의 연도 ≠ 토큰 연도.
    이 셋이 겹치면서 교정이 틀릴 상황은 없다 — '28년까지' 라고 묻고 상한이 2029 인 게 맞는 경우가 없으므로.
    """
    years = [t for t in tokens if len(t) == 4 and t.isdigit()]
    if len(years) != 1:
        return sql, False
    uppers = list(_MAT_UPPER.finditer(sql))
    if len(uppers) != 1:
        return sql, False
    lit = uppers[0].group(1)
    if lit[:4] == years[0]:
        return sql, False
    s, e = uppers[0].span(1)
    return sql[:s] + years[0] + lit[4:] + sql[e:], True


_GRADE_SCALE = ["AAA", "AA+", "AA0", "AA-", "A+", "A0", "A-",
                "BBB+", "BBB0", "BBB-", "BB0", "BB-", "B+", "B-", "C0"]
_Q_GRADE_CMP = re.compile(r"\b(AAA|AA|BBB|BB|A|B|C)\s*([+\-0])?\s*(?:등급|급)?\s*(이상|이하)", re.I)
_SQL_GRADE_CMP = re.compile(r"(?:TRIM\(\s*)?crd_grd\s*\)?\s*(=|>=|<=|>|<)\s*'([^']*)'", re.I)
_SQL_GRADE_IN = re.compile(r"crd_grd\s*\)?\s*(?:NOT\s+)?IN\s*\(", re.I)
_SQL_GRADE_IN_FULL = re.compile(r"(?:TRIM\(\s*)?crd_grd\s*\)?\s*IN\s*\(([^)]*)\)", re.I)   # NOT IN 은 구조상 매칭 안 됨


_FUND_TBL = re.compile(r"\bfrom\s+public_funds\b", re.I)
_SQL_ANCHOR = re.compile(r"\bgroup\s+by\b|\border\s+by\b", re.I)
# 질문이 모수 밖을 명시하면 주입하지 않는다 — '사모 펀드 중 큰 것' 에 공모 필터를 박으면 정반대 오답
_POP_WIDEN = ("사모", "판매완료", "판매 완료", "판매중단", "판매 중단", "역외", "전체 펀드", "모든 펀드", "판매종료")


def ensure_fund_base_population(sql: str, question: str) -> tuple[str, bool]:
    """펀드 랭킹 SQL 에 기본모수(판매중·공모)를 기계 주입. (보정된 SQL, 보정했는지)

    2026-08-31 paired v2: answer 실패 1순위(값 불일치 37건)가 기본모수·대표행 규칙 미적용 —
    규칙이 프롬프트에 실려도 무시된다. ensure_limit 원칙(기각이 아니라 보정)의 연장.
    발동 조건(전부 만족할 때만 — 넓히면 사모·판매완료 질의를 다친다):
      ① FROM public_funds (+ ext_* 설명서 조인 허용 — 타 상품군 조인·UNION 은 손대지 않는다.
         🔴 9/1 FND-R06 실측: ext_fund_page 조인 랭킹이 JOIN 제외 조건으로 빠져나가
         판매완료 펀드 1997-10-28 이 '가장 오래된 펀드'로 나갔다. sale_yn·prvo_pbff_desc 는
         public_funds 에만 있는 컬럼이라(PRAGMA 전수 확인) 조인문에도 비한정 주입이 모호하지 않다)
      ② ORDER BY 존재 (랭킹·Top-N 꼴)
      ③ SQL 에 sale_yn·prvo_pbff_desc 언급이 전혀 없음 (하나라도 있으면 모델 의도 존중)
      ④ 질문에 모수 확장 토큰(사모·판매완료·역외·전체)이 없음
    """
    if not _FUND_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I):
        return sql, False
    if re.search(r"\bjoin\b", sql, re.I) and re.search(
            r"\b(?:domestic_bonds|domestic_etfs|overseas_etfs)\b", sql, re.I):
        return sql, False
    # 🔴 랭킹(ORDER BY)뿐 아니라 **집계(COUNT/SUM/AVG)** 도 기본모수 대상이다 — 기본모수 규칙이
    #    "집계·Top-N" 을 함께 말한다. 2026-08-31 밤 FND-030 실측: COUNT 질의에 sale_yn 이 빠졌다.
    if not re.search(r"\border\s+by\b", sql, re.I) and not re.search(r"\b(?:count|sum|avg)\s*\(", sql, re.I):
        return sql, False
    if any(t in question for t in _POP_WIDEN):
        return sql, False
    # 🔴 질문이 '공모' 를 명시했는데 SQL 이 사모까지 포함하면 좁힌다 — 2026-09-01 FND-038 실측:
    #    "공모펀드는 유형별로 몇 개씩?" 에 prvo_pbff_desc IN ('공모','사모') 가 나가 사모 1,993개가
    #    답에 실렸다. 위 _POP_WIDEN 이 이미 '사모' 질문을 걸러내므로 여기 오는 것은 공모 질의뿐이다.
    m_in = re.search(r"\bprvo_pbff_desc\s+IN\s*\([^)]*'사모'[^)]*\)", sql, re.I)
    if m_in and "공모" in question:
        sql = sql[:m_in.start()] + "prvo_pbff_desc = '공모'" + sql[m_in.end():]
        return sql, True
    # 🔴 **빠진 쪽만** 주입한다 — 예전엔 둘 중 하나라도 있으면 통째로 건너뛰어서, 한쪽만 쓴 SQL 이
    #    반쪽 모수로 나갔다(2026-08-31 밤 FND-030 실측: prvo_pbff_desc 만 있고 sale_yn 누락).
    #    모수를 넓히는 질의는 위 _POP_WIDEN 이 이미 막으므로 모델 의도를 해치지 않는다.
    missing = [c for c, pat in (("sale_yn = '판매중'", r"\bsale_yn\b"),
                                ("prvo_pbff_desc = '공모'", r"\bprvo_pbff_desc\b"))
               if not re.search(pat, sql, re.I)]
    if not missing:
        return sql, False
    cond = " AND ".join(missing)
    m = re.search(r"\bwhere\b", sql, re.I)
    if m:
        # 기존 조건을 괄호로 감싼다 — 'WHERE a OR b' 에 그냥 AND 를 붙이면 (cond AND a) OR b 로 샌다
        e = m.end()
        tail = sql[e:]
        stop = _SQL_ANCHOR.search(tail) or re.search(r"\blimit\b", tail, re.I)
        body, rest = (tail[:stop.start()], tail[stop.start():]) if stop else (tail, "")
        return f"{sql[:e]} {cond} AND ({body.strip()}) {rest}".rstrip(), True
    anchor = _SQL_ANCHOR.search(sql)
    if not anchor:
        return sql, False
    s = anchor.start()
    return f"{sql[:s]}WHERE {cond} {sql[s:]}", True


# ── 펀드 랭킹 대표행·근거컬럼 가드 3종 (2026-08-31 밤 — FND-019·015 실측 채점 후속,
#    docs/question_design_public_funds_2026-08-31.md §4. 프롬프트에 실려도 무시되는 규칙의 결정 층) ──
_FUND_RANK_COLS = ("fd_mm1_ern_r", "fd_mm3_ern_r", "fd_mm6_ern_r", "fd_mm18_ern_r",
                   "fd_yr1_ern_r", "fd_yr2_ern_r", "fd_yr3_ern_r", "fd_yr5_ern_r", "fd_nast_suma")
_FUND_RETURN_COLS = _FUND_RANK_COLS[:-1]
_FUND_LONGTERM_COLS = ("fd_mm18_ern_r", "fd_yr1_ern_r", "fd_yr2_ern_r", "fd_yr3_ern_r", "fd_yr5_ern_r")
_RETURN_ERR_ITM = ("KR5157450126", "KR5153450511", "KR5119470012")   # 기준가 기점 오류 검증 3클래스 (리드 확정 08-31)
_ORDER_BY_HEAD = re.compile(r"\border\s+by\s+([^,]+?)(?:\s+(asc|desc))?\s*(?:,|\blimit\b|$)", re.I | re.S)


def _split_select_items(head: str) -> list[str]:
    """SELECT 목록을 최상위 쉼표로만 나눈다 — TRIM(..)·CASE..END·substr(..) 안의 쉼표는 건너뛴다."""
    items, depth, buf = [], 0, []
    for ch in head:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf))
    return items


def _fund_sort_target(sql: str) -> tuple[str, str] | None:
    """ORDER BY 첫 키가 가리키는 펀드 랭킹 컬럼과 방향 — (컬럼, 'DESC'|'ASC') 또는 None.

    위치 표기(ORDER BY 3)는 SELECT 목록을 최상위 쉼표로 갈라 그 자리 항목에서 컬럼을 찾는다
    (실측 SQL 두 건 모두 ORDER BY 3 위치 표기였다)."""
    frm = re.search(r"\bfrom\b", sql, re.I)
    m = _ORDER_BY_HEAD.search(sql)
    if not frm or not m:
        return None
    expr, direction = m.group(1).strip(), (m.group(2) or "ASC").upper()
    if expr.isdigit():
        sel = re.sub(r"^\s*select\s+(distinct\s+)?", "", sql[:frm.start()], flags=re.I)
        items = _split_select_items(sel)
        idx = int(expr) - 1
        if not (0 <= idx < len(items)):
            return None
        expr = items[idx]
    for col in _FUND_RANK_COLS:
        if re.search(rf"\b{col}\b", expr, re.I):
            return col, direction
    return None


def ensure_fund_rank_representative(sql: str, question: str = "") -> tuple[str, bool]:
    """펀드단위 랭킹의 대표행을 기계 보정한다. (보정된 SQL, 보정했는지)

    2026-08-31 밤 실측(FND-015 채점): 펀드단위 GROUP BY 는 했는데 SELECT 가 bare fd_mm6_ern_r 라
    펀드당 대표값이 **임의 클래스 행** — TOP5 값 5건 전부 MAX 클래스가 아니었고 5위는 6위와 동점까지 갔다.
    대표행 규칙("정렬 컬럼 MAX 인 클래스")이 프롬프트에 실려도 재현이 안 된다 — ensure_limit 원칙의 보정.
    MAX/MIN 하나만 있는 집계에서 bare 컬럼(itm_no·itm_nm)이 그 행의 값을 따라오는 SQLite 특성까지 겸사 —
    대표 클래스 itm_no 도 함께 맞는다. 발동 조건: ① public_funds 단독(JOIN·UNION 없음)
    ② GROUP BY 에 or_co_xtn_itt_cd(펀드단위 키 신호) ③ ORDER BY 첫 키가 랭킹 컬럼(수익률 8종·순자산)
    ④ 그 컬럼이 SELECT 에 bare 로 있다(집계 미포장). DESC 는 MAX, ASC(하위 랭킹)는 MIN.
    별칭 AS <컬럼> 을 붙여 이름·위치 ORDER BY 둘 다 살린다.

    🔴 **GROUP BY 부재 분기** (2026-09-02 R7 재검): 조건 ②가 HCX 준수에 의존해서, 미특정 경로(4테이블
    49,634자 근거문서)에서 HCX 가 GROUP BY 를 버리자 가드가 빈손 — 클래스 단위 top3 가 한화2.2배 한 펀드의
    Ce·C4·A 도배(387.66·387.48·386.38, gold 는 NH-Amundi 362.53·삼성KOSPI200 361.3). 정상 경로에서도
    비결정적으로 재발할 수 있는 구멍(§6-2s 018 잠재)이라 SQL 모양만으로 대표행을 보장한다:
    GROUP BY 가 없고 · 집계(COUNT/SUM/AVG)도 없고 · 질문이 '클래스' 단위를 명시하지 않으면
    `GROUP BY <펀드키>` 를 ORDER BY 앞에 주입하고 정렬 컬럼을 MAX/MIN 으로 감싼 뒤 SELECT 끝에
    `COUNT(*) AS 클래스수` 를 병기한다(끝에 붙이므로 위치 ORDER BY 번호는 안 흔들린다).
    식별 컬럼(itm_no·itm_nm)이 없으면 함께 붙인다 — 뒤의 근거컬럼 가드가 COUNT 를 보고 건너뛰기 때문.
    """
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union)\b", sql, re.I):
        return sql, False
    target = _fund_sort_target(sql)
    if not target:
        return sql, False
    col, direction = target
    agg = "MAX" if direction == "DESC" else "MIN"
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()]
    has_group = bool(re.search(r"\bgroup\s+by\b", sql, re.I))
    tail = sql[frm.start():]
    if has_group:
        if not re.search(r"\bgroup\s+by\b[^;]*\bor_co_xtn_itt_cd\b", sql, re.I):
            return sql, False
        head, wrapped, in_func = _wrap_sort_col(head, col, agg)
        if not wrapped:
            return sql, False
        if in_func:
            tail = _wrap_order_by_col(tail, col, agg)
        return head + tail, True
    # ── GROUP BY 부재: 펀드키 주입 ──
    if "클래스" in question or re.search(r"\b(?:count|sum|avg|total)\s*\(", head, re.I):
        return sql, False
    m_ob = re.search(r"\border\s+by\b", tail, re.I)
    if not m_ob:
        return sql, False
    add = []
    if "itm_nm" not in head and "itm_no" not in head:
        add += ["itm_no", "TRIM(itm_nm) AS itm_nm"]
    head, wrapped, in_func = _wrap_sort_col(head, col, agg)
    if not wrapped and not re.search(rf"\b{col}\b", head, re.I):
        add.append(f"{agg}({col}) AS {col}")     # 정렬 컬럼이 SELECT 에 없으면 별칭으로 실어 ORDER BY 이름을 살린다
    add.append('COUNT(*) AS "클래스수"')
    head = head.rstrip() + ", " + ", ".join(add) + " "
    tail = tail[:m_ob.start()].rstrip() + f" GROUP BY {_FUND_KEY_EXPR} " + tail[m_ob.start():]
    if in_func:
        tail = _wrap_order_by_col(tail, col, agg)
    return head + tail, True


def _wrap_sort_col(head: str, col: str, agg: str) -> tuple[str, bool, bool]:
    """SELECT 목록의 bare 정렬 컬럼을 agg(col) 로 감싼다. (새 head, 감쌌는지, 함수 인자 위치였는지)

    🔴 2026-09-02 리뷰 ②-5: 정렬 컬럼이 함수 안이면(`ROUND(fd_yr1_ern_r,2)`) 별칭까지 붙여
    `ROUND(MAX(fd_yr1_ern_r) AS fd_yr1_ern_r,2)` 문법 오류 → "데이터 조회 중 오류" 무응답. 함수 인자 위치면
    `agg(col)` 만 넣고 별칭은 생략한다 — 위치 ORDER BY 는 그대로 유효, 이름 ORDER BY 는 _wrap_order_by_col 이 맞춘다.
    """
    if re.search(rf"(?:max|min|avg|sum|total)\s*\(\s*{col}", head, re.I):
        return head, False, False
    m = re.search(rf"\b{col}\b(\s+as\s+\w+)?", head, re.I)
    if not m:
        return head, False, False
    if re.search(r"\w+\(\s*$", head[:m.start()]):
        return head[:m.start()] + f"{agg}({col})" + head[m.start() + len(col):], True, True
    alias = m.group(1) or f" AS {col}"
    return head[:m.start()] + f"{agg}({col}){alias}" + head[m.end():], True, False


def _wrap_order_by_col(tail: str, col: str, agg: str) -> str:
    """ORDER BY 첫 키가 이름으로 정렬 컬럼을 쓰면 agg(col) 로 — 별칭이 없어진 함수 인자 경우의 짝."""
    return re.sub(rf"(\border\s+by\s+(?:(?!max\(|min\()[^,])*?)\b{col}\b", rf"\1{agg}({col})", tail, count=1, flags=re.I)


def ensure_fund_return_error_exclusion(sql: str) -> tuple[str, bool]:
    """18개월+ 수익률 랭킹 SQL 에 기점오류 검증 3클래스 제외를 주입. (보정된 SQL, 보정했는지)

    수익률기점오류_제외 규칙이 근거문서에 실려도 SQL 에 반영되지 않는다 — FND-019 실측에서
    위험등급 3 모수에 신한농산물 C2(KR5119470012)가 실재, 18개월+ 랭킹이면 오답 확정이었다.
    발동 조건: ① public_funds 단독 ② ORDER BY 첫 키가 18개월+ 수익률 컬럼 ③ 제외 코드가 SQL 에 없음
    ④ itm_nm LIKE 필터 없음(개별 조회·이름 검색엔 규칙상 미적용). 단기(1·3·6개월) 정렬은
    _fund_sort_target 컬럼 판정에서 걸러진다 — 규칙의 적용 경계(FND-015 검증 목적) 그대로.
    """
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union)\b", sql, re.I):
        return sql, False
    if any(c in sql for c in _RETURN_ERR_ITM) or re.search(r"\bitm_nm\s+(?:not\s+)?like\b", sql, re.I):
        return sql, False
    target = _fund_sort_target(sql)
    if not target or target[0] not in _FUND_LONGTERM_COLS:
        return sql, False
    codes = ", ".join(f"'{c}'" for c in _RETURN_ERR_ITM)
    return _append_exclusions(sql, [f"itm_no NOT IN ({codes})"])


def ensure_fund_evidence_columns(sql: str) -> tuple[str, bool]:
    """펀드 SQL 의 SELECT 에 답변 근거 컬럼을 보강. (보정된 SQL, 보정했는지)

    FND-019·015 실측: 등급명·태그가 SELECT 에 없으면 답변 생성기가 방향 서술·주의 문구를 붙일
    **재료 자체가 없다** — ensure_risk_name_column(채권)의 펀드판. ① 위험등급 코드가 SQL 에 쓰였으면
    zrin_fd_ivst_risk_grd_nm 병기(등급 방향·이름 서술 근거) ② 정렬이 수익률 컬럼이면 zrin_attr_nms
    병기(100% 초과·레버리지 주의 문구 근거 — 수익률극단값 규칙의 SELECT 요건). COUNT 집계 질의(건수)는
    출력 형태를 바꾸지 않도록 불개입. SELECT 끝에 붙이므로 위치 ORDER BY 번호는 안 흔들린다.
    """
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union)\b", sql, re.I):
        return sql, False
    frm = re.search(r"\bfrom\b", sql, re.I)
    if not frm:
        return sql, False
    head = sql[:frm.start()]
    if re.search(r"\bcount\s*\(", head, re.I) and not re.search(r"\bgroup\s+by\b", sql, re.I):
        return sql, False        # 단일 건수 질의 — 열 추가가 출력 의미를 바꾼다
    add = []
    # 🔴 식별 컬럼이 없으면 답변기가 **이름을 지어낸다** — 2026-08-31 밤 배포 직후 실측:
    #    SELECT fd_yr1_ern_r 만 한 SQL(값 30개)에 답변기가 "종류A 17.41% · 종류B 17.36% · 종류C 17.26%"
    #    라고 클래스명을 붙여 냈다. 실제 그 값들은 글로벌코어테크EMP 의 것이고 종류A/B/C 라는 클래스도 없다.
    #    이름 필터(가드 5호)로 조회 범위는 맞췄는데 답변 층에서 다시 환각이 난 것 — 값만 있는 결과는
    #    "어느 상품의 값인지" 를 답변기가 복원할 수 없다. COUNT 집계는 출력 의미가 바뀌므로 제외.
    # 🔴 `head`(SELECT 목록)만 본다 — WHERE 의 `itm_nm LIKE` 를 SELECT 에 있는 것으로 오판하면
    #    바로 이 사고(값만 조회 → 이름 환각)를 놓친다. 실제로 첫 구현이 그렇게 새어 배포본에서 재현됐다.
    if "itm_nm" not in head and "itm_no" not in head and not re.search(r"\bcount\s*\(", head, re.I):
        add.append("itm_no")
        add.append("TRIM(itm_nm) AS itm_nm")
    # 일반 규칙: 위험등급은 **이름·코드가 SELECT 에 항상 쌍**으로 실린다 — 한쪽만 있으면 답이 '높은 위험' 으로 끝나거나
    #    '2.0' 코드만 남는다(R6 '2등급' 미병기 · S4: WHERE 의 `gcd IS NOT NULL` 을 보고 병기를 건너뜀). 판정은 `head` 기준이고
    #    한 패스에 둘 다 붙여 멱등을 지킨다(이름→코드·코드→이름을 번갈아 붙이면 패스마다 열이 는다).
    if "zrin_fd_ivst_risk_gcd" in sql and "zrin_fd_ivst_risk_grd_nm" not in head:
        add.append("zrin_fd_ivst_risk_grd_nm")
    if ("zrin_fd_ivst_risk_grd_nm" in head or "zrin_fd_ivst_risk_grd_nm" in add) and "zrin_fd_ivst_risk_gcd" not in head:
        add.append("zrin_fd_ivst_risk_gcd")
    target = _fund_sort_target(sql)
    if target and target[0] in _FUND_RETURN_COLS and "zrin_attr_nms" not in sql:
        add.append("zrin_attr_nms")
    # 🔴 순자산 랭킹은 억 원 파생 컬럼을 병기한다 — 2026-09-01 서버 실측(021·022·031): 답변기가
    #    13자리 원 단위를 옮겨 적다 자릿수를 훼손했다(1,024,955,248,968 → "10,249,525,488원").
    #    억 환산으로 답한 문항(025·029)은 전부 정확 — 안전하게 옮길 수 있는 수를 결과에 실어 준다.
    #    단위는 값에 구워 넣는다('10249억원') — 숫자만 주면 답변기가 단위를 지어낸다(재검 실측: "십억 원").
    if target and target[0] == "fd_nast_suma" and "순자산_억원" not in sql:
        add.append("CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS \"순자산_억원\"")
    # 🔴 **조건에 쓴 서술 컬럼이 결과에 없으면 답변기가 결과를 해석하지 못한다** — 2026-08-31 밤 실측(FND-R09):
    #    WHERE han_clas_policies LIKE '%전문투자자%' 로 27행을 정확히 조회하고도 SELECT 에 그 컬럼이 없어
    #    (itm_nm·mtco_itm_no·기준일만), 답변기가 "정보를 찾을 수 없습니다" 로 **조회 결과를 통째로 버렸다**.
    #    FND-016(이름 소실 → 환각)과 같은 뿌리다: 답변기는 SELECT 에 실린 것만 볼 수 있다.
    #    필터 근거를 답에 쓰려면 그 컬럼이 결과에 있어야 한다 — 최대 3개까지만 붙여 폭을 제한한다.
    where = re.search(r"\bwhere\b(.*?)(?:\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if where:
        known = {c.lower() for c, *_ in (getattr(_ev_ctx(), "schema", {}) or {}).get("public_funds", ())}
        for col in dict.fromkeys(re.findall(r"\b[a-z][a-z0-9_]{3,}\b", where.group(1), re.I)):
            c = col.lower()
            if len(add) >= 3:
                break
            if c in known and c not in _EVIDENCE_SKIP and c not in head.lower() and c not in " ".join(add).lower():
                add.append(c)
    if not add:
        return sql, False
    return head.rstrip() + ", " + ", ".join(add) + " " + sql[frm.start():], True


# 결과에 다시 실을 필요가 없는 컬럼 — 기본모수·식별자·이미 다루는 축·결측 판정용
_EVIDENCE_SKIP = {
    "sale_yn", "prvo_pbff_desc", "itm_no", "itm_nm", "itm_abrv_nm", "mtco_itm_no",
    "or_co_xtn_itt_cd", "null", "not", "and", "or", "like", "select", "from", "where",
    "trim", "coalesce", "cast", "substr", "length", "case", "when", "then", "else", "end",
    "zrin_fd_ivst_risk_gcd",   # 이름 컬럼(grd_nm)을 위에서 이미 붙인다
    "pfiv_sale_cntl_tcd",      # 사용 금지 컬럼 — 결과에 실어 주면 금지를 거드는 꼴이다 (아래 _FORBIDDEN_COLS)
}


# ── 사용 금지 컬럼 — 규칙(query_rules)에 적어도 플래너가 쓴다. 기각해서 재생성 사유로 돌려준다 ──
# 2026-08-31 밤 FND-R09 실측: 같은 질문에 1차는 han_clas_policies(정답 경로), 2차는
# pfiv_sale_cntl_tcd != '00'(금지 컬럼)이 나왔다 — HCX 비결정성이라 프롬프트 규칙만으론 못 막는다.
_FORBIDDEN_COLS = {
    "pfiv_sale_cntl_tcd":
        "pfiv_sale_cntl_tcd 는 코드 의미가 제공되지 않아 어떤 질의에도 조건·정렬로 쓸 수 없다"
        " — 전문투자자 조건은 han_clas_policies LIKE '%전문투자자%' 로 푼다"
        " (값: '전문투자자'·'전문투자자,펀드'·'기관,전문투자자' 등)",
    "fd_wk1_ern_r":
        "fd_wk1_ern_r 은 전건 결측이라 쓸 수 없다 — 1주 수익률은 수록되지 않았다고 답한다"
        " (대체로 1개월 fd_mm1_ern_r 안내는 가능)",
}


def forbidden_column_use(sql: str) -> str | None:
    """사용 금지 컬럼을 쓴 SQL 의 기각 사유 — 없으면 None."""
    for col, why in _FORBIDDEN_COLS.items():
        if re.search(rf"\b{col}\b", sql, re.I):
            return why
    return None


@lru_cache(maxsize=1)
def _ev_ctx():
    """스키마 조회용 컨텍스트 — 가드가 ctx 를 인자로 받지 않으므로 여기서 한 번만 로드한다."""
    from .loader import load_context
    return load_context()


# 설명서(ext_fund_page)에만 있는 항목을 가리키는 어휘 — 마스터 45컬럼에 없다고 거절하던 것을 연다
_FUND_EXT_HINTS = re.compile(
    r"설정일|설정된|언제\s*설정|설정\s*시기|오래된|신생|환매|투자설명서|설명서|(?<![공사])모펀드|지급일"
    # 🔴 (?<![공사])모펀드 — 그냥 '모펀드' 로 두면 "**공모펀드**"·"사모펀드" 에 걸려 거의 모든 펀드 질의가
    #    설명서 조인 대상이 된다(2026-08-31 밤 실측: "개인이 가입할 수 있는 공모펀드는 몇 개야?" 오발동).
    #    프롬프트가 2,000자 늘고 교차질의로 오분류된다.
)


_NAME_LIKE = re.compile(r"(?<!REPLACE\()(?:TRIM\(\s*)?\b(itm_nm)\b\s*\)?\s*((?:NOT\s+)?LIKE)\s*'((?:[^']|'')*)'", re.I)


def ensure_spaceless_name_match(sql: str) -> tuple[str, bool]:
    """종목명 LIKE 를 **공백 무시 매칭**으로 바꾼다. (보정된 SQL, 보정했는지)

    2026-08-31 밤 실측(FND-R05 후속): 사용자가 띄어 쓰면 있는 상품을 통째로 놓친다 —
    '미래에셋 코어테크' 그대로 0행 / 공백 제거 14행. 'AI 반도체' 도 0행 / 4행.
    종목명은 표기 공백이 제각각이라(삼성 베스트 MMF 법인 제1호) 양쪽 다 정규화해야 한다:
    REPLACE(itm_nm,' ','') LIKE '%<공백 제거 키워드>%'. 매칭을 넓히기만 하므로 안전하고,
    존재하지 않는 상품(FND-R05)은 여전히 0행이다.
    """
    def _fix(m: re.Match) -> str:
        pat = m.group(3).replace(" ", "")
        return f"REPLACE({m.group(1)},' ','') {m.group(2).upper()} '{pat}'"
    fixed = _NAME_LIKE.sub(_fix, sql)
    return fixed, fixed != sql


# 이름 조회 필터 — **좌변이 itm_nm** 인 LIKE/GLOB 만 (원형 · TRIM(itm_nm) · 공백무시 REPLACE 형).
# 🔴 2026-09-02 리뷰 ②-1: 종전 `itm_nm … {0,40}자 … LIKE` 40자 창이 SELECT 의 itm_nm 과 WHERE 의 다른 컬럼
#    LIKE(or_attr_desc·zrin_attr_nms)를 이름 조회로 오인 — "주식형 공모펀드" 목록이 개별 조회 묶기(최단 이름순)로
#    빠져 역외 1클래스 펀드 30개가 나갔다. `NOT LIKE` 는 제외 필터라 이름 조회가 아니다(NOT 이 끼면 불일치).
_NAME_FILTER = re.compile(
    r"(?:REPLACE\(\s*itm_nm\s*,\s*' '\s*,\s*''\s*\)|TRIM\(\s*itm_nm\s*\)|\bitm_nm\b)\s*(?:LIKE|GLOB)\b", re.I)


def _has_name_filter(sql: str) -> bool:
    """WHERE 절(FROM 뒤)에 좌변 itm_nm 의 LIKE/GLOB 이름 조회가 있는가."""
    frm = re.search(r"\bfrom\b", sql, re.I)
    return bool(frm) and bool(_NAME_FILTER.search(sql[frm.end():]))
_LOOKUP_ROW_UNIT = ("클래스", "보수", "수수료")     # 행(클래스) 단위가 정답인 질의 — 033 클래스 열거·020 클래스별 보수
_SELECT_PLAIN_ITEM = re.compile(r"(?:TRIM\(\s*)?([A-Za-z_]\w*)\s*\)?(?:\s+AS\s+(\w+))?", re.I)


@lru_cache(maxsize=1)
def _fund_col_types() -> dict[str, str]:
    """public_funds 컬럼 → SQL 타입(소문자). 스키마 원천(loader)에서 읽는다 — 하드코딩 아님."""
    return {c.lower(): (t or "").lower() for c, _, t, *_ in (getattr(_ev_ctx(), "schema", {}) or {}).get("public_funds", ())}


def ensure_fund_lookup_grouping(sql: str, question: str) -> tuple[str, bool]:
    """이름 검색(개별 조회) 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값을 병기. (보정된 SQL, 보정했는지)

    2026-09-02 R4 재검 — 이름 검색 30행(6펀드 37클래스)을 답변기가 펀드별로 묶지 않고 1클래스만 제시한 것이
    3회째(020·032 계열). 프롬프트 규칙("펀드별로 묶어라")은 재현이 안 되므로 SELECT 단계에서 묶어 주면
    답변기는 6행을 복사만 한다. R6 은 LIMIT 1 이라 "클래스 7개" 병기 자체가 불가능했다.
    발동 조건(전부): ① public_funds 단독(JOIN·UNION·GROUP BY 없음) ② itm_nm LIKE/GLOB 이름 필터 존재
    ③ ORDER BY 없음(랭킹은 ensure_fund_rank_representative 담당 · 그 밖의 정렬은 모델 의도 존중)
    ④ SELECT 에 집계·`*` 없음 ⑤ 질문에 '클래스'·'보수'·'수수료' 없음(행 단위가 정답인 질의는 불개입)
    ⑥ SELECT 항목이 전부 단순 컬럼(TRIM(col)·AS 별칭 허용) — 식이 섞였으면 안전하게 불개입.
    조치: SELECT 를 `MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS 클래스수` +
    수치 컬럼은 `MAX(col) AS col_최고, MIN(col) AS col_최저`, 문자·날짜 컬럼은 `MAX(col) AS col` 로 재작성하고
    `GROUP BY 펀드키`, `ORDER BY MIN(length(공백제거 이름)) ASC`(**가장 짧은 이름 = 본체** — "질문 이름과
    가장 정확히 일치하는 펀드를 먼저" 를 결정적으로), LIMIT 은 상한으로 푼다.
    """
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union|group\s+by|having|order\s+by)\b", sql, re.I):
        return sql, False
    if not _has_name_filter(sql) or any(t in question for t in _LOOKUP_ROW_UNIT):
        return sql, False
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()]
    if re.search(r"\b(?:count|sum|avg|min|max|total)\s*\(", head, re.I) or "*" in head:
        return sql, False
    sel = re.sub(r"^\s*select\s+(distinct\s+)?", "", head, flags=re.I)
    types = _fund_col_types()
    if not types:
        return sql, False
    # 판매중클래스수 병기 (2026-09-02 리뷰 ②-7) — 이름 조회에 기본모수를 박으면 판매완료·사모 14,707행 개별 조회가
    # 0행 오거절이라 주입하지 않는 대신, "클래스 7개 중 판매중 7개" 재료를 0행 위험 없이 싣는다.
    new = ["MIN(itm_no) AS 대표_itm_no", "MIN(TRIM(itm_nm)) AS itm_nm", 'COUNT(*) AS "클래스수"',
           "SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS \"판매중클래스수\""]
    for it in _split_select_items(sel):
        m = _SELECT_PLAIN_ITEM.fullmatch(it.strip())
        if not m:
            return sql, False
        col, alias = m.group(1).lower(), m.group(2)
        if col in ("itm_no", "itm_nm"):
            continue
        t = types.get(col)
        if t is None:
            return sql, False
        if col == "fd_nast_suma":
            # 🔴 순자산은 SUM — 이 DB 의 fd_nast_suma 는 **클래스별 값**이라 펀드 순자산은 합계다 (2026-09-02 리뷰 ②-6 실측:
            #    코어테크 본체 10클래스 합 2조9,148억 vs 최대 클래스 7,348억 · 삼성MMF법인제1호 4클래스 12.4조/1,051억/…).
            #    정수 CAST 로 '.0' 노출을 없애고 억원을 직접 굽는다(자릿수 훼손 계열 — 021·022·031 재검과 같은 처방).
            new += ["CAST(SUM(fd_nast_suma) AS INTEGER) AS fd_nast_suma",
                    "CAST(SUM(fd_nast_suma)/100000000 AS INTEGER) || '억원' AS \"순자산_억원\""]
        elif col in _FUND_RETURN_COLS:
            new += [f'MAX({col}) AS "{col}_최고"', f'MIN({col}) AS "{col}_최저"']     # 최고/최저는 수익률 8종에만
        else:
            new.append(f"MAX({col}) AS {alias or col}")
    # 2R Q4-b — 대표예탁원번호(rptt_ksd_itm_no)를 **표시 단위**로만 싣는다: 조립기가 같은 대표번호 행을 한 줄로 접는다
    #    (R6 6행 → "클래스 7개" 1줄). 카운트·랭킹 gold 의 펀드키는 그대로다(리뷰 ④ 완화 ⓐ).
    new.append("MIN(rptt_ksd_itm_no) AS 대표번호")
    tail = sql[frm.start():].rstrip()
    tail = re.sub(r"\blimit\s+\d+\s*$", "", tail, flags=re.I).rstrip()
    return (f"SELECT {', '.join(new)} {tail} GROUP BY {_FUND_KEY_EXPR} "
            f"ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT {MAX_ROWS}"), True


# ── 개별 조회 답변 기계 조립 (2R Q4 — R4·S3·S4·S5·R6·S12) ──
_STEM_ASSET = re.compile(
    r"^(.*?[\(\[][^\)\]]*(?:주식|채권|혼합|재간접|파생|MMF|부동산|특별자산|REITs|인프라|자산)[^\)\]]*[\)\]](?:\s*\((?:H|UH)\))?)", re.I)
_STEM_CLASS_TAIL = re.compile(r"\s*(?:종류|클래스|Class|_?C[A-Za-z0-9\-]*\s*클래스).*$")
_LOOKUP_HEAD = ["대표_itm_no", "itm_nm", "클래스수", "판매중클래스수"]
_RET_LABEL = {"fd_mm1_ern_r": "1개월", "fd_mm3_ern_r": "3개월", "fd_mm6_ern_r": "6개월", "fd_mm18_ern_r": "18개월",
              "fd_yr1_ern_r": "1년", "fd_yr2_ern_r": "2년", "fd_yr3_ern_r": "3년", "fd_yr5_ern_r": "5년"}


def _fund_stem(name: str) -> str:
    """종목명에서 클래스 접미를 떼고 자산유형 괄호(+환헤지 표기)까지 남긴다 — public_funds.md §3.3 종목명 구조.

    2026-09-02 R4·S3 재검: 대표명이 `… 종류A`·`(A)` 인 채로 범위값이 붙어 "종류A: 최고 189.77%" — 종류A 실값은 187.94.
    괄호가 없는 이름(MMF 등)은 '종류·클래스' 꼬리만 자르고, 그마저 없으면 원문.
    """
    n = name.strip()
    m = _STEM_ASSET.match(n)
    if m:
        return m.group(1).strip()
    return _STEM_CLASS_TAIL.sub("", n).strip() or n


def _pct(v: str) -> str:
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return s


def _lookup_answer(sql: str, rows: str, n: int, name_token: str | None = None) -> str | None:
    """개별 조회 묶기(lookup grouping) 결과의 답변을 기계 조립한다. 아니면 None. HCX 0회.

    2026-09-02 2R — 묶기 가드가 6행을 정확히 만들었는데 HCX 가 (R4·S3) 대표명의 클래스 접미에 범위값을 붙여 특정 클래스의
    값처럼 썼고, 클래스수·판매중클래스수(S3 판매완료)·gcd(R6·S5 "등급 지수 2.0") 재료를 옮기지 않았다. 같은 펀드의 클래스 간
    수익률 차이는 보수 차이(§3.1)라 "클래스에 따라 X%~Y%" 범위 표기가 적절하다 — 단 클래스명 없이.
    같은 대표번호(rptt_ksd_itm_no, 없으면 stem) 행은 한 줄로 접는다(클래스수 합·min/max 재계산 — 등급이 다르면 접지 않음).
    """
    lines = rows.splitlines()
    if n < 1 or len(lines) != n + 1:
        return None
    cols = [c.strip() for c in lines[0].split(" | ")]
    if cols[:4] != _LOOKUP_HEAD:
        return None
    recs = []
    for ln in lines[1:]:
        parts = [p.strip() for p in ln.split(" | ")]
        if len(parts) != len(cols):
            return None
        recs.append(dict(zip(cols, parts)))
    ret_cols = [c for c in _RET_LABEL if f"{c}_최고" in cols]
    has_grade = "zrin_fd_ivst_risk_grd_nm" in cols or "zrin_fd_ivst_risk_gcd" in cols
    has_nast = "fd_nast_suma" in cols
    if not (ret_cols or has_grade or has_nast):
        return None
    groups: dict[str, dict] = {}
    order: list[str] = []
    for r in recs:
        stem = _fund_stem(r["itm_nm"])
        key = r.get("대표번호") or f"stem:{stem}"
        grade = (r.get("zrin_fd_ivst_risk_grd_nm", ""), r.get("zrin_fd_ivst_risk_gcd", ""))
        if key in groups and has_grade and groups[key]["grade"] != grade:
            key = f"{key}#{r['대표_itm_no']}"
        if key not in groups:
            groups[key] = {"stem": stem, "n": 0, "m": 0, "grade": grade, "nast": 0, "ret": {c: [None, None] for c in ret_cols}}
            order.append(key)
        g = groups[key]
        g["n"] += int(float(r["클래스수"] or 0))
        g["m"] += int(float(r["판매중클래스수"] or 0))
        if has_nast and r.get("fd_nast_suma"):
            g["nast"] += int(float(r["fd_nast_suma"]))
        for c in ret_cols:
            lo, hi = r.get(f"{c}_최저", ""), r.get(f"{c}_최고", "")
            if lo != "" and hi != "":
                cur = g["ret"][c]
                g["ret"][c] = [float(lo) if cur[0] is None else min(cur[0], float(lo)),
                               float(hi) if cur[1] is None else max(cur[1], float(hi))]
    pop = "공모펀드" if re.search(r"prvo_pbff_desc\s*=\s*'공모'", sql, re.I) else "펀드"
    token = name_token
    if not token:
        m_like = re.search(r"(?:LIKE|GLOB)\s+'[%*]?([^'%*]+)[%*]?'", sql, re.I)
        token = m_like.group(1) if m_like else None
    head = (f"'{token}' 이름의 {pop} {len(order)}개가 조회됐습니다" if token else f"조회된 {pop} {len(order)}개입니다") \
        + f" (기준일 {gate.DATA_CUTOFF}, 펀드 = 대표예탁원번호 기준·클래스 = 판매 단위)."
    out = [head, ""]
    for key in order:
        g = groups[key]
        parts = []
        if g["m"] == 0:
            parts.append("판매완료(신규 가입 불가)")
        for c in ret_cols:
            lo, hi = g["ret"][c]
            label = _RET_LABEL[c]
            if lo is None:
                parts.append(f"{label} 수익률 미수록")
            elif lo == hi:
                parts.append(f"{label} 수익률 {_pct(lo)}% (누적)")
            else:
                parts.append(f"{label} 수익률 {_pct(lo)}%~{_pct(hi)}% (클래스에 따라 다름, 누적)")
        if has_grade:
            nm, gcd = g["grade"]
            if gcd:
                parts.append(f"위험등급 {int(float(gcd))}등급" + (f"({nm})" if nm else ""))
            elif nm:
                parts.append(f"위험등급 {nm}")
            else:
                parts.append("위험등급 미수록")
        if has_nast:
            parts.append(f"순자산 {g['nast'] // 100000000:,}억원 (클래스 합계)")
        tail = f"클래스 {g['n']}개" + ("(전부 판매중)" if g["m"] == g["n"] else f", 판매중 {g['m']}개")
        out.append(f"- {g['stem']}: " + " · ".join(parts) + f" · {tail}")
    return "\n".join(out)


def _list_answer(sql: str, rows: str, n: int) -> str | None:
    """순자산순 펀드 목록(ensure_fund_list_grouping 형)의 답변을 기계 조립한다. 아니면 None. HCX 0회.

    2026-09-02 2R — 커버리지 가드가 "(전체 560행/248펀드 중 30펀드 표시)" 를 구웠는데 R3 는 5행·S7 은 10행만 옮기고
    "일부입니다", S6 는 30행을 다 옮기고도 총량 대신 "더 많은 펀드가 있을 수 있습니다". 목록 전사는 분포(FND-038)와 같은
    결론 — LLM 에 맡길 수 없다. 발동: SQL 에 `GROUP BY 펀드키` + `ORDER BY fd_nast_suma DESC`, 헤더에 itm_nm·클래스수·순자산_억원.
    """
    if n < 1 or f"GROUP BY {_FUND_KEY_EXPR}" not in sql or not re.search(r"\border\s+by\s+fd_nast_suma\s+desc\b", sql, re.I):
        return None
    lines = rows.splitlines()
    if len(lines) != n + 1:
        return None
    cols = [c.strip() for c in lines[0].split(" | ")]
    if not {"itm_nm", "클래스수", "순자산_억원"} <= set(cols):
        return None
    recs = []
    for ln in lines[1:]:
        parts = [p.strip() for p in ln.split(" | ")]
        if len(parts) != len(cols):
            return None
        recs.append(dict(zip(cols, parts)))
    cov = _coverage_counts(sql)
    pop = "공모펀드" if re.search(r"prvo_pbff_desc\s*=\s*'공모'", sql, re.I) else "펀드"
    if cov and cov[1] is not None and cov[1] > n:
        head = (f"조건에 해당하는 {pop}는 전체 {cov[1]:,}개(클래스 {cov[0]:,}개)이며, 순자산 상위 {n}개 펀드는 다음과 같습니다"
                f" (기준일 {gate.DATA_CUTOFF}, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위).")
    else:
        total = f"(클래스 {cov[0]:,}개)" if cov else ""
        head = f"조건에 해당하는 {pop}는 전체 {n}개{total}이며, 순자산 순으로 다음과 같습니다 (기준일 {gate.DATA_CUTOFF})."
    out = [head, ""]
    for i, r in enumerate(recs, 1):
        eok = r.get("순자산_억원", "")
        eok_txt = f"{int(eok.replace('억원', '')):,}억원" if eok.endswith("억원") and eok[:-2].lstrip("-").isdigit() else (eok or "미수록")
        out.append(f"{i}. {_fund_stem(r['itm_nm'])}: 순자산 {eok_txt} · 클래스 {int(float(r['클래스수'] or 0))}개")
    return "\n".join(out)


def ensure_fund_list_grouping(sql: str, question: str) -> tuple[str, bool]:
    """ORDER BY 없는 펀드 목록(태그·유형 필터)을 펀드키로 묶어 순자산순 대표행으로. (보정된 SQL, 보정했는지)

    2026-09-02 R3 재검 — `LIMIT 30` 에 ORDER BY 가 없어 **임의 30행**(재현성 없음)이 나갔고, 같은 펀드(솔로몬 2호)의
    C2·C5 가 별개 항목으로 나열됐다. 발동 조건(전부): ① public_funds 단독(JOIN·UNION·GROUP BY 없음)
    ② SELECT 에 itm_no/itm_nm(목록 꼴)이 있고 집계·`*` 없음 ③ ORDER BY 없음(랭킹은 대표행 가드)
    ④ 이름 필터 없음(개별 조회는 ensure_fund_lookup_grouping) ⑤ 질문에 '클래스' 없음.
    조치: SELECT 끝에 `COUNT(*) AS 클래스수, MAX(fd_nast_suma) AS fd_nast_suma` + `GROUP BY 펀드키` +
    `ORDER BY fd_nast_suma DESC`(실측 상위: KB중국본토A주 14클래스 1,453억 · 미래에셋차이나솔로몬1호 · 신한중국의꿈2호).
    MAX 하나뿐인 집계라 bare 컬럼(itm_no·itm_nm·태그)은 그 MAX 클래스 행을 따라온다(SQLite).
    """
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union|group\s+by|having|order\s+by)\b", sql, re.I):
        return sql, False
    if _has_name_filter(sql) or "클래스" in question:
        return sql, False
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()]
    if "itm_nm" not in head and "itm_no" not in head:
        return sql, False
    if re.search(r"\b(?:count|sum|avg|min|max|total)\s*\(", head, re.I) or "*" in head:
        return sql, False
    tail = sql[frm.start():].rstrip()
    m_lim = re.search(r"\blimit\s+\d+\s*$", tail, re.I)
    body, lim = (tail[:m_lim.start()].rstrip(), tail[m_lim.start():]) if m_lim else (tail, "")
    add = 'COUNT(*) AS "클래스수"' + (", MAX(fd_nast_suma) AS fd_nast_suma" if "fd_nast_suma" not in head else "")
    return (f"{head.rstrip()}, {add} {body} GROUP BY {_FUND_KEY_EXPR} ORDER BY fd_nast_suma DESC {lim}").rstrip(), True


# ── 답변 입력 조립 3종 (2026-09-02 R3 재검 — 목록 답변의 총량 병기·내부 코드 숨김·이름 전사 교정) ──
_HIDE_FROM_ANSWER = {"prfd_attr_cds"}      # 내부 태그 코드(C101·M109…) — 근거컬럼 가드는 명칭(zrin_attr_nms)을 병기하므로 답변 재료가 아니다
_SIMPLE_FROM_WHERE = re.compile(r"\bfrom\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", re.I | re.S)


def _coverage_counts(sql: str) -> tuple[int, int | None, bool] | None:
    """LIMIT 에 잘린 목록의 전체 규모 — (전체 행수, 펀드수|None, 펀드 단위로 묶인 SQL 인지). 단순 SELECT 가 아니면 None.

    SQLite 재실행 1회·HCX 0회. public_funds 단독이면 펀드키 DISTINCT 도 센다. GROUP BY 는 펀드키 묶기
    (ensure_fund_list_grouping·lookup_grouping·대표행 가드가 만든 형태)만 허용 — 그때 표시 행은 펀드다.
    """
    if re.search(r"\b(?:union|having)\b|\(\s*select\b", sql, re.I):
        return None
    grouped = bool(re.search(r"\bgroup\s+by\b", sql, re.I))
    if grouped and f"GROUP BY {_FUND_KEY_EXPR}" not in sql:
        return None
    m = _SIMPLE_FROM_WHERE.search(sql)
    if not m:
        return None
    frm = m.group(1).strip()
    fund_only = _FUND_TBL.search(sql) and not re.search(r"\bjoin\b", sql, re.I)
    cols = f"COUNT(*), COUNT(DISTINCT {_FUND_KEY_EXPR})" if fund_only else "COUNT(*)"
    con = connect_readonly()
    try:
        row = con.execute(f"SELECT {cols} FROM {frm}").fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return int(row[0]), (int(row[1]) if fund_only else None), grouped


def _hide_answer_columns(rows: str) -> tuple[str, list[str]]:
    """답변 입력에서 내부 코드 컬럼을 뺀다 — retrieved_context 는 그대로. (정리된 표, 뺀 컬럼)"""
    lines = rows.splitlines()
    if not lines:
        return rows, []
    cols = lines[0].split(" | ")
    drop = [i for i, c in enumerate(cols) if c.strip().lower() in _HIDE_FROM_ANSWER]
    if not drop or len(drop) == len(cols):
        return rows, []
    keep = [i for i in range(len(cols)) if i not in drop]
    out = []
    for ln in lines:
        parts = ln.split(" | ")
        out.append(" | ".join(parts[i] for i in keep if i < len(parts)))
    return "\n".join(out), [cols[i].strip() for i in drop]


_NAME_COL = re.compile(r"\b(?:itm_nm|itm_abrv_nm|pd_nm|pd_abrv_nm|etf_name)\b", re.I)
_NAME_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{8,}")


def verify_product_names(answer: str, rows: str) -> tuple[str, list[str]]:
    """답변의 상품명 토큰을 조회 원문 사전과 대조해 근사 전사 오류를 DB 원문으로 되돌린다. (교정된 답변, 교정 목록)

    2026-09-02 R3 재검: "삼성중국본토중소형**FOSS**" — 실제 FOCUS, DB 에 'FOSS' 0행. 자릿수 훼손과 같은 계열
    (모델은 복사만 하게 하라). 사전 = 결과의 이름 컬럼(itm_nm·pd_nm 등) 값의 공백 제거 8자 이상 연속 토큰.
    답변의 8자 이상 연속 토큰이 어느 이름의 부분문자열이면 정확 — 불개입. 아니면 difflib 근사(0.85 이상)일 때만
    사전 토큰으로 치환한다. 4도메인 공통(ETF 종목명에도 그대로 유효). 🔴 줄 삭제는 하지 않는다 — 한국어 서술
    ('알려드리겠습니다' 8자)도 토큰으로 잡히므로 "어떤 이름과도 안 닮은 줄 제거" 는 문장을 죽인다.
    """
    lines = rows.splitlines()
    if len(lines) < 2:
        return answer, []
    cols = lines[0].split(" | ")
    idx = [i for i, c in enumerate(cols) if _NAME_COL.search(c)]
    if not idx:
        return answer, []
    names = set()
    for ln in lines[1:]:
        parts = ln.split(" | ")
        for i in idx:
            if i < len(parts) and parts[i].strip():
                names.add(parts[i].replace(" ", ""))
    if not names:
        return answer, []
    vocab = sorted({t for nm in names for t in _NAME_TOKEN.findall(nm)}, key=len, reverse=True)
    fixes: list[str] = []

    def _fix(m: re.Match) -> str:
        tok = m.group(0)
        if any(tok in nm for nm in names):
            return tok
        # 🔴 조사를 떼고 어간만 대조, 치환 시 조사를 되붙인다 — 2026-09-02 리뷰 ②-4 실측: "…신탁3호는 조회되지
        #    않았습니다" 가 조사 '는' 을 삼킨 채 '…2호' 로 치환돼 부정문의 주어가 뒤바뀌었다(의미 반전).
        stem = _PARTICLE.sub("", tok)
        particle = tok[len(stem):]
        if len(stem) < 8 or any(stem in nm for nm in names):
            return tok
        close = difflib.get_close_matches(stem, vocab, n=1, cutoff=0.85)
        if not close or close[0] == stem:
            return tok
        cand = close[0]
        # 🔴 치환 금지 — 상위/하위 문자열(KODEX200TR ↔ KODEX200 · H/UH · 1호/2호 접미)이거나 숫자열이 다르면
        #    별개 상품이다(종목명 구조 §3.3). 리뷰 실측: 'KODEX200TR' → 'KODEX200'(유사도 0.95) 다른 상품 치환.
        if stem in cand or cand in stem or re.findall(r"\d+", stem) != re.findall(r"\d+", cand):
            return tok
        # 'TR'·'U' 처럼 글자가 **끼어들거나 빠진** 짝(KODEX200TR / UH)은 중간 삽입이라 위 검사에 안 걸린다 —
        # 오타형(FOSS→FOCUS)은 replace 만으로 이뤄지므로 insert/delete 가 하나라도 있으면 별개 상품으로 본다.
        if any(op in ("insert", "delete") for op, *_ in difflib.SequenceMatcher(None, stem, cand).get_opcodes()):
            return tok
        fixes.append(f"'{stem}' → '{cand}'")
        return cand + particle

    out = _NAME_TOKEN.sub(_fix, answer)
    return (out, fixes) if fixes else (answer, [])


def ensure_enum_value_fix(sql: str, ctx) -> tuple[str, bool]:
    """WHERE 리터럴이 실제 enum 값과 접미사·공백만 다르면 실제 값으로 치환. (보정된 SQL, 보정했는지)

    FND-024 실측 처방 — 값 검사 기각 → 재생성 실패 → 거절 경로를 애초에 없앤다.
    guard.nearest_enum_value 가 유일 후보일 때만 값을 돌려주므로 의미가 갈리는 치환은 일어나지 않는다.
    """
    index = getattr(ctx, "value_index", None) or {}
    if not index:
        return sql, False
    changed = False
    for v in guard.check_values(sql, ctx):
        if v.owner:                      # 컬럼 오선택은 재생성 사유로 넘긴다 (§6-2e)
            continue
        near = guard.nearest_enum_value(index, v.table, v.column, v.literal)
        if near and near != v.literal:
            sql = re.sub(rf"'{re.escape(v.literal)}'", f"'{near}'", sql)
            changed = True
    return sql, changed


# 분포 집계의 GROUP BY 축이 될 수 있는 서술 컬럼 — NULL 이 정상적으로 존재한다
_NULLABLE_GROUP_COLS = ("zrin_btyp_nm", "zrin_ptn_nm", "or_attr_desc", "fd_ivst_rgn_desc",
                        "ovrs_fd_desc", "pers_corp_desc", "han_clas_nm", "han_clas_fee_type",
                        "han_clas_sales_channel", "bmrk_nm", "curr_cd")


def ensure_group_null_label(sql: str) -> tuple[str, bool]:
    """분포 집계의 GROUP BY 축이 NULL 일 때 이름을 붙인다. (보정된 SQL, 보정했는지)

    2026-09-01 실측(FND-038): `GROUP BY zrin_btyp_nm` 결과에 NULL 그룹(418행·308펀드)이 나왔지만
    라벨이 빈칸이라 답변기가 그 행을 **통째로 빠뜨렸다**(합계가 8,469 로 500 부족).
    이름이 없으면 말할 수 없다 — FND-016(이름 소실)·R09(근거 컬럼 부재)와 같은 뿌리다.
    COALESCE 로 '(미수록)' 라벨을 주어 결측도 하나의 범주로 답에 실리게 한다.
    """
    if not _FUND_TBL.search(sql) or "COALESCE" in sql.upper():
        return sql, False
    m = re.search(r"\bgroup\s+by\s+([A-Za-z_]\w*)", sql, re.I)
    if not m or m.group(1).lower() not in _NULLABLE_GROUP_COLS:
        return sql, False
    col = m.group(1)
    frm = re.search(r"\bfrom\b", sql, re.I)
    if not frm:
        return sql, False
    head = sql[:frm.start()]
    fixed = re.sub(rf"(?<![.\w(]){col}\b(?!\s*\))", f"COALESCE({col},'(미수록)')", head, count=1)
    if fixed == head:
        return sql, False
    return fixed + sql[frm.start():], True


def ensure_fund_distribution_fund_count(sql: str) -> tuple[str, bool]:
    """분포 집계(라벨 · COUNT(*))에 COUNT(DISTINCT 펀드키) AS 펀드수 를 3번째로 병기. (보정된 SQL, 보정했는지)

    2026-09-02 R1 재검: 분포 답변의 '건' 이 **클래스 행 수**인데 클래스/펀드 구분이 답에 없다(7~9번째 재발).
    yaml `유형별분포` 규칙("클래스 수와 펀드 수를 함께")이 조립기(2열 전용)에 내려가 있지 않았다.
    발동 조건: ① public_funds 단독(JOIN·UNION 없음) ② GROUP BY 존재 ③ SELECT 가 정확히 (라벨, COUNT(*)) 2항목.
    끝에 붙이므로 위치 ORDER BY 번호는 안 흔들린다. 조립기 _distribution_answer 가 3열을 받아 옮긴다.
    """
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union)\b", sql, re.I):
        return sql, False
    if not re.search(r"\bgroup\s+by\b", sql, re.I) or "펀드수" in sql:
        return sql, False
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()]
    items = _split_select_items(re.sub(r"^\s*select\s+(distinct\s+)?", "", head, flags=re.I))
    if len(items) != 2 or not re.match(r"\s*count\s*\(\s*\*\s*\)", items[1], re.I):
        return sql, False
    if _is_topn_or_entity_axis(sql, items[0]):
        return sql, False
    return head.rstrip() + f', COUNT(DISTINCT {_FUND_KEY_EXPR}) AS "펀드수" ' + sql[frm.start():], True


# 분포의 축이 아니라 **개체 식별자**인 컬럼 — 이것으로 GROUP BY 한 COUNT 는 운용사·펀드 top-N 이지 분포가 아니다
_ENTITY_AXIS = re.compile(r"\b(?:or_co_xtn_itt_cd|tt_co_xtn_itt_cd|itm_no|mtco_itm_no|rptt_ksd_itm_no|itm_nm|itm_abrv_nm|\w+_itt_cd)\b", re.I)


def _is_topn_or_entity_axis(sql: str, axis_item: str) -> bool:
    """GROUP BY COUNT 가 분포가 아닌 경우 — ⓐ ORDER BY + 명시 LIMIT k < MAX_ROWS(top-N 꼴) ⓑ 축이 개체 식별 컬럼.

    2026-09-02 리뷰 ②-2: 운용사 top5(`SELECT or_co_xtn_itt_cd, COUNT(*) … GROUP BY 1 ORDER BY 2 DESC LIMIT 5`,
    JOIN 없는 R2 형)에 3열이 붙고 조립기가 "5개 범주 · 펀드 3,040개 · 복수 범주 1,632건" 조작 통계를 만들었다.
    """
    m_lim = re.search(r"\blimit\s+(\d+)", sql, re.I)
    if re.search(r"\border\s+by\b", sql, re.I) and m_lim and int(m_lim.group(1)) < MAX_ROWS:
        return True
    return bool(_ENTITY_AXIS.search(axis_item))


_SAFE_Q = re.compile(r"안전|안정적|안정형")
# 뒤집힘은 등호만이 아니다 — 9/1 서버 실측: BETWEEN 1 AND 3 으로 우회해 높은위험 30행이
# 조회됐다. '낮은 숫자 = 안전' 오해의 표현형 전부(=1·2, BETWEEN 1~n<6, <=3, IN(1..3))를 잡는다.
_GCD_HIGHRISK = re.compile(
    r"zrin_fd_ivst_risk_gcd\s*(?:"
    r"=\s*'?[12](?:\.0)?'?"
    r"|BETWEEN\s+'?1(?:\.0)?'?\s+AND\s+'?[1-5](?:\.0)?'?"
    r"|<=?\s*'?[1-3](?:\.0)?'?"
    r"|IN\s*\(\s*'?[123](?:\.0)?'?(?:\s*,\s*'?[123](?:\.0)?'?)*\s*\)"
    r")",
    re.I,
)


def ensure_fund_safe_grade_direction(sql: str, question: str) -> tuple[str, bool]:
    """'안전' 질의의 위험등급 필터가 1·2(고위험)로 뒤집혔으면 6(매우 낮은 위험)으로 교정.

    2026-08-31 밤 실측(FND-C03 "안전한 펀드 추천해줘"): 플래너가 안전=1등급으로 방향 반전한 SQL 을 내
    '매우 높은 위험' 5행이 조회됐고, 답변 생성기는 그 5행만 보고 "모든 펀드가 매우 높은 위험" 이라는
    거짓 전칭 서술로 도망갔다. 등급 방향(1=위험·6=안전)은 answer_rules 에 실려도 SQL 층에서 뒤집힌다.
    발동 조건: ① public_funds ② 질문에 '안전' 계열 어휘 ③ 질문이 등급 숫자를 명시하지 않음
    ('1등급 알려줘' 는 모델 의도 존중 — FND-002 회귀 보호) ④ SQL 의 등급 등호 필터가 1 또는 2.
    """
    if not _FUND_TBL.search(sql) or not _SAFE_Q.search(question):
        return sql, False
    if re.search(r"[1-6]\s*등급|등급\s*[1-6]", question):
        return sql, False
    m = _GCD_HIGHRISK.search(sql)
    if not m:
        return sql, False
    return sql[:m.start()] + "zrin_fd_ivst_risk_gcd = 6" + sql[m.end():], True


_MIXED_Q = re.compile(r"혼합형")
_MIXED_SPECIFIC_Q = re.compile(r"주식\s*혼합|채권\s*혼합|혼합\s*자산|해외\s*혼합")
_MIXED_FIX = "zrin_btyp_nm IN ('주식혼합형','채권혼합형')"
_FUND_TYPE_COND = re.compile(
    r"(?:\b\w+\.)?(?:or_attr_desc|zrin_btyp_nm)\s*(?:=\s*'[^']*'|IN\s*\([^)]*\))", re.I)


def ensure_fund_mixed_type(sql: str, question: str) -> tuple[str, bool]:
    """'혼합형' 질의의 유형 필터를 zrin 확정식(주식혼합형+채권혼합형)으로 교체. (보정된 SQL, 보정했는지)

    2026-09-01 FND-023 실측 2회: ① or_attr_desc='혼합형'(없는 값) 기각 → 재생성 REFUSE(오거절) ·
    ② 값 힌트 수리 후 재검은 첫 SQL 부터 or_attr_desc IN ('혼합자산','대출형','개발형') — 실제 값이라
    검사는 통과하지만 모수가 다르다(gold 주식혼합+채권혼합 top1 118.45 vs 혼합자산 32.6). HCX 비결정성이라
    규칙·힌트로는 못 박는다 — 채권 ensure_kind_filter 와 동형의 확정식 치환.
    발동 조건: ① public_funds ② 질문에 '혼합형' ③ 구체 유형(주식혼합·채권혼합·혼합자산·해외혼합) 명시
    없음 ④ SQL 의 유형 조건(or_attr_desc·zrin_btyp_nm)이 정확히 1개 (0개·2개 이상은 불개입 — 치환이
    다른 조건과 얽히면 0행을 만들 수 있다).
    """
    if not _FUND_TBL.search(sql) or not _MIXED_Q.search(question):
        return sql, False
    if _MIXED_SPECIFIC_Q.search(question):
        return sql, False
    conds = list(_FUND_TYPE_COND.finditer(sql))
    if len(conds) != 1:
        return sql, False
    m = conds[0]
    if re.sub(r"\s+", "", m.group(0)) == re.sub(r"\s+", "", _MIXED_FIX):
        return sql, False
    return sql[:m.start()] + _MIXED_FIX + sql[m.end():], True


# 면책 상투구가 든 문장 통째 — 문장 경계는 마침표·물음표·느낌표·줄바꿈 (쉼표는 문장 내부)
_DISCLAIMER = re.compile(
    r"[^.!?\n]*(?:금융\s*기관에\s*문의|해당\s*기관에\s*문의|전문가(?:와의?|의)?\s*(?:상담|조언|의견)"
    # 2026-09-02 R2 재검 — "추가 정보가 필요하시다면 관련 기관에 문의하시기 바랍니다" 가 '관련 기관' 이라 빠져나갔다
    r"|(?:관련|해당|금융|각)\s*기관(?:에|으로|을\s*통해)\s*(?:문의|확인|상담)|추가\s*정보가\s*필요"
    r"|자세한\s*(?:내용|사항)은[^.!?\n]*(?:문의|확인|상담|참고|참조))"
    r"[^.!?\n]*[.!?]?")
# 전수 집계 결과에 붙는 거짓 유보 — "더 있을 수 있습니다"(5행 전수인데) · "조회된 데이터를 기반으로 한 것이며" · "일부"
_FALSE_HEDGE = re.compile(
    r"[^.!?\n]*(?:더\s*많은[^.!?\n]*있을\s*수\s*있|조회된\s*데이터를\s*기반으로\s*한\s*것이|일부(?:입니다|일\s*수|만))"
    r"[^.!?\n]*[.!?]?")


def strip_false_hedge(text: str, sql: str, n: int) -> tuple[str, bool]:
    """전수 집계(GROUP BY·COUNT/SUM, 행수 < 상한) 답변에서 '더 있을 수 있음' 류 거짓 유보 문장을 걷어낸다.

    2026-09-02 R2 재검: 운용사 top5 (전수 집계 5행) 에 "이 순위는 조회된 데이터를 기반으로 한 것이며, 더 많은
    펀드를 운용하는 곳이 있을 수 있습니다" — 집계가 전수라 유보가 거짓이다. 목록이 LIMIT 에 잘린 경우(커버리지
    병기)는 유보가 정당하므로 불개입. 전부 지워지면 원문 유지.
    """
    if n >= MAX_ROWS or not re.search(r"\bgroup\s+by\b|\b(?:count|sum)\s*\(", sql, re.I):
        return text, False
    out = _FALSE_HEDGE.sub("", text)
    if out == text:
        return text, False
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return (out, True) if out else (text, False)


def strip_disclaimer(text: str) -> tuple[str, bool]:
    """답변에서 면책 상투구 문장을 걷어낸다. (정리된 답변, 제거했는지)

    2026-09-01 실측 — answer_rules 의 면책 금지가 하루 5회 재발("금융기관에 문의"·"전문가와
    상담"): 규칙이 실려도 답변기가 습관적으로 붙인다(법칙 1). 값·목록은 그대로 두고 해당 문장만
    통째로 제거. 전부 지워지면(면책 한 줄짜리 답) 원문 유지 — 빈 답변이 더 나쁘다.
    """
    out = _DISCLAIMER.sub("", text)
    if out == text:
        return text, False
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return (out, True) if out else (text, False)


_PDNO_TOKEN = re.compile(r"\bKR[0-9A-Z]{10}\b")


def ensure_top_row_cited(answer: str, sql: str, rows: str) -> tuple[str, bool]:
    """정렬 목록 답변이 결과 하위 행을 인용하며 상위 행을 건너뛰면 누락 행을 답변에 되살린다.

    2026-09-02 서버 실측: '1년만 굴릴 건데 어떤 채권 사면 돼?' — ORDER BY applied_yield DESC
    결과의 2·4·5·6·7위만 나열, 1위(MBS2022-9 3.986%)·3위(평택도시공사 3.94%) 증발.
    무정렬 LIMIT 30 시뮬레이션으로 '임의 행' 가설 기각 — 결과셋에 1위가 있었는데 답변층이
    떨어뜨렸다. 값이 전부 실제 행이라 환각 검사에 안 걸리는 선별 누락이고, 추천·목록에서
    1위 누락은 그 자체로 오답이다. 목록 전사는 LLM 에게 맡길 수 없다(_distribution_answer 와
    같은 교훈)의 목록판 — 전면 기계 조립 전의 최소 보정.
    발동(전부): ① ORDER BY 존재 ② GROUP BY·COUNT 없음 ③ 결과 2행 이상에 pd_no 수록
    ④ 답변이 결과 pd_no 를 2개 이상 인용 ⑤ 인용된 최하위 순위 위의 행 중 미인용이 있음.
    보정: 누락 행을 순위와 함께 답변 끝에 덧붙인다(결과 원문 행 그대로 — 창작 없음, 최대 5행).
    이름만 인용한 답변(pd_no 0~1개)에는 불개입 — 오폭보다 미개입."""
    if not re.search(r"\bORDER\s+BY\b", sql, re.I) or re.search(
            r"\bGROUP\s+BY\b|\bCOUNT\s*\(", sql, re.I):
        return answer, False
    ranked = []
    for ln in rows.splitlines()[1:]:
        m = _PDNO_TOKEN.search(ln)
        if m:
            ranked.append((m.group(0), ln.strip()))
    if len(ranked) < 2:
        return answer, False
    cited = set(_PDNO_TOKEN.findall(answer))
    idx_cited = [i for i, (p, _) in enumerate(ranked) if p in cited]
    if len(idx_cited) < 2:
        return answer, False
    missing = [(i, ln) for i, (p, ln) in enumerate(ranked[:max(idx_cited)])
               if p not in cited][:5]
    if not missing:
        return answer, False
    lines = [f"- {i + 1}위: {ln}" for i, ln in missing]
    return (answer.rstrip()
            + "\n\n(보정) 조회 결과 순위에서 위 목록에 빠진 상위 행을 추가합니다:\n"
            + "\n".join(lines)), True


_REFUSAL_ANSWER = re.compile(
    r"정보가?\s*(?:포함되어\s*있지\s*않|없)|답변(?:을|이)?\s*드릴\s*수\s*없|확인(?:할|이)\s*(?:수\s*)?(?:없|불가)|알\s*수\s*없")
_EXIST_Q = re.compile(r"있(?:어|나|습니까|나요|는지)")


def ensure_positive_count_answered(answer: str, sql: str, rows: str, n: int,
                                   question: str) -> tuple[str, bool]:
    """양수 단일 집계 결과를 받고도 '정보 없음' 으로 오거절한 답변을 기계 조립으로 교체한다.

    2026-09-02 서버 실측: '퇴직연금으로 살 수 있는 채권 있어?' — SQL 은 pd_pen_tr_yn='Y' +
    구매가능 모수로 정확했고 COUNT(*)=1,929 가 정상 반환됐는데, 답변기가 "정보가 포함되어
    있지 않습니다" 오거절. crd_grd 오거절(SELECT 누락)과 달리 이번엔 숫자가 결과에 있는데도
    집계 1행을 '정보 없음' 으로 오독했다 — 집계 해석은 LLM 에 맡길 수 없다(_count_answer ·
    _distribution_answer 와 같은 교훈). 0행 '확인 불가' 는 compose 전 조기 반환 경로라 이
    가드에 오지 않는다 — 여기 오는 답변은 항상 결과가 있다.
    발동(전부): ① 단일행 결과 ② SELECT 가 집계 1항목 ③ 값이 양수 ④ 답변이 거절 문구.
    값 0 이면 불개입('없다' 답이 옳을 수 있다). 교체문은 결과 원문 수치만 쓴다 — 창작 없음."""
    if n != 1 or not _REFUSAL_ANSWER.search(answer):
        return answer, False
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm:
        return answer, False
    head = re.sub(r"^\s*SELECT\s+", "", sql[:frm.start()], flags=re.I)
    if not re.match(r"\s*(?:COUNT|SUM)\s*\(", head, re.I) or "," in head.split("AS")[0]:
        return answer, False
    body = rows.splitlines()[1:]
    if len(body) != 1:
        return answer, False
    try:
        val = int(float(body[0].split(" | ")[0].strip()))
    except ValueError:
        return answer, False
    if val <= 0:
        return answer, False
    unit = "종목" if re.search(r"DISTINCT\s+pd_no", sql, re.I) else "건(행 기준 — 종목 수와 다를 수 있음)"
    prefix = "네, 있습니다 — " if _EXIST_Q.search(question) else ""
    return f"{prefix}조회 결과 {val:,}{unit}입니다 (기준일 2026-08-22).", True


def _distribution_answer(sql: str, rows: str, n: int) -> str | None:
    """2열(범주 라벨 · COUNT(*)) GROUP BY 분포 결과의 답변을 기계 조립한다. 아니면 None.

    발동 조건(전부): GROUP BY 존재 · JOIN 없음 · SELECT 가 정확히 2항목이고 둘째가 COUNT(*) ·
    행 2개 이상 · 전 행이 '라벨 | 정수' 형태. 합계·범주 수를 함께 낸다 — 오계수·행 생략·
    전칭('일부') 서술이 이 모양의 질의에서 원천적으로 사라진다.
    """
    if n < 2 or not re.search(r"\bgroup\s+by\b", sql, re.I) or re.search(r"\bjoin\b", sql, re.I):
        return None
    frm = re.search(r"\bfrom\b", sql, re.I)
    if not frm:
        return None
    sel = re.sub(r"^\s*select\s+(distinct\s+)?", "", sql[:frm.start()], flags=re.I)
    items = _split_select_items(sel)
    if len(items) not in (2, 3) or not re.match(r"\s*count\s*\(\s*\*\s*\)", items[1], re.I):
        return None
    if _is_topn_or_entity_axis(sql, items[0]):
        return None                       # 운용사·펀드 top-N 은 분포가 아니다 — HCX 답변기로 (리뷰 ②-2)
    # 3열 — ensure_fund_distribution_fund_count 가 붙인 COUNT(DISTINCT 펀드키) AS 펀드수 (2026-09-02 R1 재검)
    with_funds = len(items) == 3
    if with_funds and not re.match(r"\s*count\s*\(\s*distinct\b", items[2], re.I):
        return None
    body = rows.splitlines()[1:]
    if len(body) != n:
        return None
    pairs = []
    for ln in body:
        parts = ln.split(" | ")
        if len(parts) != len(items):
            return None
        try:
            cnt = int(float(parts[1]))
            funds = int(float(parts[2])) if with_funds else None
        except ValueError:
            return None
        pairs.append((parts[0].strip(), cnt, funds))
    total = sum(c for _, c, _ in pairs)
    if not with_funds:
        lines = [f"조회 결과 {len(pairs)}개 범주, 합계 {total:,}건입니다 (기준일 {gate.DATA_CUTOFF}).", ""]
        lines += [f"- {lab}: {c:,}건" for lab, c, _ in pairs]
        return "\n".join(lines)
    # 🔴 유형별 펀드 수의 단순 합(3,222)은 전체 펀드 수(3,040)가 아니다 — 실측 182펀드가 클래스별로 유형이 갈린다
    #    (176건은 일부 클래스만 평가 미수록·6건은 실제 상이). 전체는 같은 WHERE 로 COUNT(DISTINCT 펀드키) 를
    #    따로 세고(SQLite 1회), 차이를 문자열로 굽는다 — 모델이 산술하지 않게.
    fund_sum = sum(f for _, _, f in pairs)
    if n >= MAX_ROWS:
        # 절단된 분포 — 전체 DISTINCT·복수 범주 설명은 거짓이 된다(표시 밖 범주가 있다). 상위 n 개만 그대로 옮긴다.
        lines = [f"조회 결과 상위 {len(pairs)}개 범주(전체 중 일부) · 표시분 클래스 {total:,}개 (기준일 {gate.DATA_CUTOFF}).", ""]
        lines += [f"- {lab}: 펀드 {f:,}개 (클래스 {c:,}개)" for lab, c, f in pairs]
        return "\n".join(lines)
    distinct = None
    m_fw = _SIMPLE_FROM_WHERE.search(sql)
    if m_fw:
        con = connect_readonly()
        try:
            distinct = con.execute(f"SELECT COUNT(DISTINCT {_FUND_KEY_EXPR}) FROM {m_fw.group(1).strip()}").fetchone()[0]
        except sqlite3.Error:
            distinct = None
        finally:
            con.close()
    head = f"조회 결과 {len(pairs)}개 범주 · 클래스 {total:,}개 · 펀드 {(distinct if distinct is not None else fund_sum):,}개 (기준일 {gate.DATA_CUTOFF})."
    lines = [head, ""]
    lines += [f"- {lab}: 펀드 {f:,}개 (클래스 {c:,}개)" for lab, c, f in pairs]
    if distinct is not None and fund_sum != distinct:
        lines += ["", f"클래스별 유형이 갈리는 펀드 {abs(fund_sum - distinct):,}건은 복수 범주에 계수되어 범주별 펀드 수의 합({fund_sum:,})은 전체 펀드 수({distinct:,})와 다릅니다."]
    return "\n".join(lines)


_ORG_CODES = re.compile(r"or_co_xtn_itt_cd='(\d+)'")


def _count_answer(sql: str, rows: str, n: int, ground_lines: list[str]) -> str | None:
    """`펀드수 | 클래스수` 1행(ensure_fund_distinct_count 결과)의 답변을 기계 조립한다. 아니면 None.

    2026-09-02 R5 재검: 가드가 143 | 541 을 정확히 만들었는데 답변기가 클래스 열을 버렸다("클래스 수를 제외한
    순수하게 펀드만") — 034 재검은 병기·R5 는 삭제, 비결정. HCX 0회. 모수 표기는 SQL 의 조건에서 읽고,
    KG 가 한 운용사에 코드를 2건 이상 병합했으면(Org_00040024 = 00040024·00040105) 합산 사실을 한 줄 붙인다.
    """
    if n != 1:
        return None
    lines = rows.splitlines()
    if len(lines) != 2 or [c.strip() for c in lines[0].split(" | ")] != ["펀드수", "클래스수"]:
        return None
    try:
        funds, classes = (int(float(v)) for v in lines[1].split(" | "))
    except ValueError:
        return None
    # 🔴 라벨은 SQL 의 prvo_pbff_desc 조건에서 읽는다 — 2026-09-02 리뷰 ②-3: "한국투자신탁운용 사모펀드는 몇 개야?" 에
    #    SQL 은 ='사모' 인데 답은 "공모펀드는 265개" 로 나갔다. 조건이 없으면 '펀드'(마스터에 사모 행 1,993개가 있다).
    m_pop = re.search(r"prvo_pbff_desc\s*=\s*'(공모|사모)'", sql, re.I)
    label = f"{m_pop.group(1)}펀드" if m_pop else "펀드"
    basis = [w for w, pat in (("판매중", r"sale_yn\s*=\s*'판매중'"), ("공모", r"prvo_pbff_desc\s*=\s*'공모'"),
                              ("사모", r"prvo_pbff_desc\s*=\s*'사모'"))
             if re.search(pat, sql, re.I)]
    scope = f" ({'·'.join(basis)} 기준, 기준일 {gate.DATA_CUTOFF})" if basis else f" (기준일 {gate.DATA_CUTOFF})"
    # 운용사 주어 + 합산 문장 — ground 의 Org 코드 중 **SQL 에 실제로 실린 코드**만 센다(KG 2코드 · SQL 1코드면 합산 아님)
    subject, used_codes = "조회 조건에 해당하는", []
    for line in ground_lines:
        codes = [c for c in _ORG_CODES.findall(line) if c in sql]
        m_lab = re.match(r"'([^']+)'\s*→\s*Org_", line)
        if "Organization" in line and codes and m_lab:
            name = m_lab.group(1)
            last = name[-1]
            particle = "이" if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 else "가"
            subject, used_codes = f"{name}{particle} 운용하는", codes
            break
    out = f"{subject} {label}는 {funds:,}개(클래스 {classes:,}개)입니다{scope}."
    if len(used_codes) >= 2:
        out += f"\n운용사 코드 {len(used_codes)}건({'·'.join(used_codes)})을 합산했습니다."
    offshore = _offshore_sibling_note(subject, used_codes, sql)
    if offshore:
        out += "\n" + offshore
    return out


_OFFSHORE_CLASS = "0013"     # 대외기관코드 종별(앞 4자) — 해외 운용법인(역외펀드 FIL·슈로더·프랭클린 계열). 코드북: 국내 법인 코드 아님


def _offshore_sibling_note(subject: str, used_codes: list[str], sql: str) -> str | None:
    """국내 운용사 개수 답변에 같은 브랜드 이름의 **역외 코드(종별 0013)** 행수를 별도 병기. 없으면 None.

    일반 규칙(2R Q7): KG 는 역외 운용법인을 국내 운용사에 병합하지 않는다(코드북 종별이 다르다 — 옳다). 다만 답이 "106개" 로
    끝나면 브랜드 이름 펀드 전부로 읽히므로(S9 피델리티: 00080029 106펀드 + 역외 00130001 47행), 종목명이 그 브랜드로 시작하는
    0013 계열 행수를 세어 "별도이며 포함하지 않았다" 를 굽는다. 특정 운용사 하드코딩 없이 코드 종별 + 이름 접두로 판정(SQLite 1회).
    """
    if not used_codes or any(c.startswith(_OFFSHORE_CLASS) for c in used_codes):
        return None
    m = re.match(r"(.+?)(?:이|가) 운용하는$", subject)
    if not m:
        return None
    brand = re.sub(r"(?:자산운용|투자신탁운용|운용)$", "", m.group(1)).replace(" ", "")
    if len(brand) < 2:
        return None
    conds = [f"TRIM(or_co_xtn_itt_cd) LIKE '{_OFFSHORE_CLASS}%'", f"REPLACE(itm_nm,' ','') LIKE '{brand}%'"]
    for pat in (r"sale_yn\s*=\s*'판매중'", r"prvo_pbff_desc\s*=\s*'(?:공모|사모)'"):
        mm = re.search(pat, sql, re.I)
        if mm:
            conds.append(mm.group(0))
    con = connect_readonly()
    try:
        n, f, codes = con.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT {_FUND_KEY_EXPR}), GROUP_CONCAT(DISTINCT TRIM(or_co_xtn_itt_cd)) "
            f"FROM public_funds WHERE {' AND '.join(conds)}").fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    if not n:
        return None
    return (f"종목명이 '{brand}' 로 시작하는 역외펀드 {f:,}개(클래스 {n:,}개, 해외 운용법인 코드 {codes.replace(',', '·')})는 "
            "별도 법인이라 이 수에 포함하지 않았습니다.")


@lru_cache(maxsize=1)
def _minority_mgmt_names() -> tuple[str, ...]:
    """합병 이력 코드(이름 2종 이상)의 소수 이름 목록 — DB 실측으로 계산, 하드코딩 아님.

    2026-09-01 FND-035 재검: MAX(mgmt_co_nm) 이 사전순으로 구명칭을 뽑았다
    (00040007: 우리자산운용 373행 vs 프랭클린템플턴 10행 — 'ㅍ' > 'ㅇ'). 코드가 정본이고
    이름은 참고 병기인데 참고가 틀리면 답이 틀려 보인다. 코드별 최빈 이름만 남긴다.
    """
    con = connect_readonly()
    try:
        rows = con.execute(
            "SELECT printf('%08d', CAST(p.or_co_xtn_itt_cd AS INTEGER)), e.mgmt_co_nm, COUNT(*) "
            "FROM public_funds p JOIN ext_fund_page e ON e.itm_no = p.itm_no "
            "WHERE e.mgmt_co_nm IS NOT NULL AND TRIM(e.mgmt_co_nm) <> '' "
            "GROUP BY 1, 2").fetchall()
    finally:
        con.close()
    by_code: dict[str, list] = {}
    for code, nm, c in rows:
        by_code.setdefault(code, []).append((c, nm))
    minority = set()
    for code, lst in by_code.items():
        if len(lst) > 1:
            lst.sort(reverse=True)
            # 🔴 코드/이름 **쌍**으로 제외한다 — 전역 이름 목록은 오답이다: '우리자산운용' 은
            #    00040007 에선 다수(413행)지만 00040023 에선 소수(1행)다 (2026-09-02 실측).
            minority.update(f"{code}/{nm}" for _, nm in lst[1:])
    return tuple(sorted(minority))


_FROM_FUND = re.compile(r"\bfrom\s+public_funds\b(?:\s+(?:as\s+)?(?!(?:left|inner|join|where|group|order|limit|on)\b)(\w+))?", re.I)


_SQL_LITERAL = re.compile(r"'(?:[^']|'')*'")
_FROM_MASTER = re.compile(r"\bfrom\s+(\w+)(?:\s+(?:as\s+)?(?!(?:left|inner|join|where|group|order|limit|on)\b)(\w+))?", re.I)
# 행 1:1 로 붙는 외부 테이블만 자동 주입 대상 — 구성종목 3종(ext_*_holdings)은 JOIN_KEYS 주석대로 팬아웃이라 COUNT 의미가 바뀐다
_EXT_ONE_TO_ONE = frozenset({"ext_fund_page"})


def ensure_ext_join(sql: str, ctx) -> tuple[str, list[str]]:
    """마스터 단독 SQL 이 1:1 외부 테이블 **전용 컬럼**을 쓰면 JOIN_KEYS 의 짝 ON 절로 LEFT JOIN 을 기계 주입. (보정된 SQL, 조치 목록)

    일반 규칙(2R Q1-c): "스키마상 외부 테이블에만 있는 컬럼 사용 = 그 테이블과의 JOIN 의도" 로 읽어 기각 대신 주입한다.
    존재하지 않는 컬럼(환각)이 그 외부 테이블 전용 컬럼의 **유일 근사**(difflib 0.8 이상, 후보 1개)면 그 컬럼으로 치환한다 —
    2026-09-02 R2·S11 재검: `mtco_nm`(없는 컬럼) 환각이 3라운드 연속 1차 SQL 을 기각시켜 재생성 예산을 소진했고, S11 은
    재생성마저 `mgmt_co_nm` 을 JOIN 없이 써 재기각 → 거절. 워크드 예시가 실려도 무시된다(법칙 1). 컬럼명·테이블명은
    전부 스키마(ctx.schema)·JOIN_KEYS·_EXT_PAIR 에서 읽는다 — 특정 컬럼 하드코딩 없음. 이후 MAX(mgmt_co_nm) 은 최빈 이름
    가드가, 비한정 itm_no 는 qualify_join_columns 가 받는다.
    """
    m = _FROM_MASTER.search(sql)
    if not m or m.group(1).lower() not in TABLES or re.search(r"\bunion\b", sql, re.I):
        return sql, []
    master, alias = m.group(1).lower(), m.group(2)
    schema = getattr(ctx, "schema", {}) or {}
    mcols = {c.lower() for c, *_ in schema.get(master, ())}
    notes: list[str] = []
    for ext, on in JOIN_KEYS:
        if _EXT_PAIR.get(ext) != master or ext not in _EXT_ONE_TO_ONE:
            continue
        excl = sorted({c.lower() for c, *_ in schema.get(ext, ())} - mcols)
        if not excl:
            continue
        for u in guard.unknown_columns(sql, ctx):
            close = difflib.get_close_matches(u.lower(), excl, n=2, cutoff=0.8)
            if len(close) == 1:
                sql = re.sub(rf"(?<![\w.]){re.escape(u)}\b", close[0], sql, flags=re.I)
                notes.append(f"{u} → {close[0]}(유일 근사)")
        if re.search(rf"\b{ext}\b", sql, re.I):
            continue
        masked = _SQL_LITERAL.sub("''", sql)
        used = [c for c in excl if re.search(rf"(?<![\w.]){c}\b", masked, re.I)]
        if not used:
            continue
        on_clause = on.replace(f"{master}.", f"{alias}.") if alias else on
        mm = _FROM_MASTER.search(sql)
        sql = sql[:mm.end()] + f" LEFT JOIN {ext} ON {on_clause}" + sql[mm.end():]
        notes.append(f"{', '.join(used)} 은 {ext} 컬럼 → LEFT JOIN 주입")
    return sql, notes


def qualify_join_columns(sql: str, ctx) -> tuple[str, list[str]]:
    """JOIN 의 비한정 모호 컬럼을 FROM 테이블(별칭)로 기계 한정한다. (보정된 SQL, 한정한 컬럼)

    2026-09-02 R2 재검 회귀 — 재생성 SQL 이 `펀드단위` 규칙의 `COALESCE(…, itm_no)` 를 LEFT JOIN ext_fund_page 문에
    그대로 옮겨 `guard.ambiguous_columns` 가 기각 → 재생성 예산은 1차(mtco_nm)에서 이미 소진 → 거절.
    검사기의 전제("실행 전에 잡아 재생성 1회를 준다")가 예산 소진 뒤엔 기각 = 거절이다. ext_* 는 itm_no 로만 마스터와
    겹치고 정답 한정은 항상 FROM 테이블이므로 기각이 아니라 한정이 맞다. 문자열 리터럴 밖의 등장만 바꾸고,
    판정 정규식(`(?<![\w.])col\b`)은 검사기와 같다. 기존 기각 분기는 가드 뒤에도 남는 경우의 안전망으로 유지.
    """
    if not re.search(r"\bjoin\b", sql, re.I):
        return sql, []
    amb = guard.ambiguous_columns(sql, ctx)
    if not amb:
        return sql, []
    m = re.search(r"\bfrom\s+(\w+)(?:\s+(?:as\s+)?(?!(?:left|inner|join|where|group|order|limit|on)\b)(\w+))?", sql, re.I)
    if not m:
        return sql, []
    qual = m.group(2) or m.group(1)
    parts = _SQL_LITERAL.split(sql)
    lits = _SQL_LITERAL.findall(sql)
    for col in amb:
        parts = [re.sub(rf"(?<![\w.]){col}\b(?!\s*\()", f"{qual}.{col}", p, flags=re.I) for p in parts]
    out = parts[0]
    for lit, p in zip(lits, parts[1:]):
        out += lit + p
    return out, amb


_MGR_Q = re.compile(r"운용사|자산운용")
_MGR_RANK_Q = re.compile(r"상위|가장|많이|많은|큰|top", re.I)
_MGR_SQL_COL = re.compile(r"\b(?:mgmt_co_nm|mtco_nm|or_co_xtn_itt_cd)\b", re.I)
_MGR_COLS = ["운용사코드", "운용사명", "펀드수", "클래스수", "순자산_억원"]
_MGR_SKIP_CONJ = re.compile(r"\b(?:sale_yn|prvo_pbff_desc|mgmt_co_nm|mtco_nm|ext_fund_page)\b", re.I)


def ensure_fund_manager_ranking(sql: str, question: str) -> tuple[str, bool]:
    """운용사 집계 질의의 SQL 을 확정 템플릿으로 교체. (보정된 SQL, 보정했는지)

    2026-09-02 S11 재검 — HCX 가 두 번 다 **이름 컬럼 GROUP BY**(합병 코드가 갈린다) + **COUNT(*)**(순자산 질의를 오해)
    를 냈고 mtco_nm 환각은 3라운드째. 워크드 예시로는 못 막는다(법칙 1). 발동: ① FROM public_funds ② 질문에
    운용사/자산운용 + 랭킹어(상위·가장·많이·큰·top) ③ SQL 의 SELECT 또는 GROUP BY 에 운용사 컬럼
    ④ 질문에 '클래스' 없음 · _POP_WIDEN 없음. 조치: 코드 GROUP BY · MAX(e.mgmt_co_nm)(→ 최빈 이름 가드가 받음) ·
    펀드수(펀드키 DISTINCT) · 클래스수 · 순자산 억원 템플릿. 축: 질문에 순자산·규모·자산 → SUM(순자산), 그 외 펀드수.
    원 WHERE 의 부가 조건(유형 등)은 p. 한정으로 옮겨 보존한다. LIMIT 은 원 값(없으면 상한).
    """
    if not _FUND_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I):
        return sql, False
    if not (_MGR_Q.search(question) and _MGR_RANK_Q.search(question)) or "클래스" in question:
        return sql, False
    if any(t in question for t in _POP_WIDEN) or '"순자산_억원"' in sql:
        return sql, False
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()]
    grp = re.search(r"\bgroup\s+by\b(.*?)(?=\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not (_MGR_SQL_COL.search(head) or (grp and _MGR_SQL_COL.search(grp.group(1)))):
        return sql, False
    m_alias = _FROM_FUND.search(sql)
    old_alias = m_alias.group(1) if m_alias else None
    extra = []
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if m_w:
        for c in guard.split_conjuncts(m_w.group(1)):
            if _MGR_SKIP_CONJ.search(c):
                continue
            c = re.sub(r"\bpublic_funds\.", "p.", c)
            if old_alias:
                c = re.sub(rf"\b{re.escape(old_alias)}\.", "p.", c)
            c = re.sub(r"(?<![\w.])itm_no\b", "p.itm_no", c)
            extra.append(c.strip())
    key = (_FUND_KEY_EXPR.replace("or_co_xtn_itt_cd", "p.or_co_xtn_itt_cd")
           .replace("mtco_itm_no", "p.mtco_itm_no").replace(", itm_no)", ", p.itm_no)"))
    by_assets = bool(re.search(r"순자산|규모|자산\s*총|자산이", question))
    order = "SUM(p.fd_nast_suma) DESC" if by_assets else "3 DESC"
    m_lim = re.search(r"\blimit\s+(\d+)", sql, re.I)
    k = m_lim.group(1) if m_lim else MAX_ROWS
    where = " AND ".join(["p.sale_yn = '판매중'", "p.prvo_pbff_desc = '공모'"] + extra)
    return (f"SELECT printf('%08d', CAST(p.or_co_xtn_itt_cd AS INTEGER)) AS \"운용사코드\", MAX(e.mgmt_co_nm) AS \"운용사명\", "
            f"COUNT(DISTINCT {key}) AS \"펀드수\", COUNT(*) AS \"클래스수\", "
            f"CAST(SUM(p.fd_nast_suma)/100000000 AS INTEGER) || '억원' AS \"순자산_억원\" "
            f"FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no "
            f"WHERE {where} GROUP BY 1 ORDER BY {order} LIMIT {k}"), True


def _manager_rank_answer(sql: str, rows: str, n: int) -> str | None:
    """운용사 집계 템플릿 결과(운용사코드·운용사명·펀드수·클래스수·순자산_억원)의 답변을 기계 조립한다. 아니면 None."""
    lines = rows.splitlines()
    if n < 1 or len(lines) != n + 1 or [c.strip() for c in lines[0].split(" | ")] != _MGR_COLS:
        return None
    by_assets = "SUM(p.fd_nast_suma)" in (re.search(r"\border\s+by\b.*$", sql, re.I | re.S) or re.match("", "")).group(0)
    basis = [w for w, pat in (("판매중", r"sale_yn\s*=\s*'판매중'"), ("공모", r"prvo_pbff_desc\s*=\s*'공모'"))
             if re.search(pat, sql, re.I)]
    scope = ("·".join(basis) + " 기준, " if basis else "") + f"펀드 = 운용사 종목번호 기준, 클래스 = 판매 단위, 기준일 {gate.DATA_CUTOFF}"
    out = [f"조회 결과 {'순자산' if by_assets else '펀드 수'} 상위 {n}개 운용사입니다 ({scope}).", ""]
    for i, ln in enumerate(lines[1:], 1):
        code, name, funds, classes, eok = [p.strip() for p in ln.split(" | ")]
        try:
            f_, c_ = int(float(funds)), int(float(classes))
        except ValueError:
            return None
        fund_part, asset_part = f"펀드 {f_:,}개(클래스 {c_:,}개)", f"순자산 {int(eok.replace('억원', '')):,}억원" if eok.endswith("억원") else f"순자산 {eok}"
        first, second = (asset_part, fund_part) if by_assets else (fund_part, asset_part)
        out.append(f"{i}. {name or '(이름 미수록)'}({code}): {first} · {second}")
    return "\n".join(out)


_MGMT_MAX = re.compile(r"MAX\(\s*((?:\w+\.)?mgmt_co_nm)\s*\)", re.I)
_OR_CO_KEY = "printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER))"


def ensure_fund_mgmt_modal_name(sql: str) -> tuple[str, bool]:
    """MAX(mgmt_co_nm) 이 합병 구명칭을 뽑지 않게 코드/이름 쌍으로 소수 이름을 제외한다."""
    m = _MGMT_MAX.search(sql)
    if not m:
        return sql, False
    pairs = _minority_mgmt_names()
    if not pairs:
        return sql, False
    lst = ", ".join(f"'{p}'" for p in pairs)
    col = m.group(1)
    return _MGMT_MAX.sub(
        f"MAX(CASE WHEN {_OR_CO_KEY} || '/' || {col} NOT IN ({lst}) THEN {col} END)", sql), True


# 국가태그 규칙의 확정 대응 (한국·국내는 제외 — 상장/국내 질의와 충돌)
_COUNTRY_TAGS = {"중국": "CHN", "차이나": "CHN", "미국": "USA", "베트남": "VNM", "일본": "JPN",
                 "러시아": "RUS", "브라질": "BRA", "홍콩": "HKG", "독일": "DEU",
                 "인도네시아": "IDN", "인도": "IND"}


def ensure_fund_country_tag(sql: str, question: str) -> tuple[str, bool]:
    """국가 질의의 지역 컬럼 오용을 태그 확정식으로 교체. (보정된 SQL, 보정했는지)

    2026-09-01 FND-026 재검 실측 — 국가태그 규칙이 실려도 플래너가 ① fd_ivst_rgn_desc='중국'
    (없는 값 — 기각) ② 재생성서 ='글로벌' (있는 값 — 통과·오모수: 중국 아닌 글로벌 펀드가 LIMIT 을
    도배) ③ 태그를 써도 wrap 없는 LIKE '%,CHN,%' 로 목록 처음·끝의 태그 98/560행을 놓친다.
    조치: 질문의 국가어에 대해 ① fd_ivst_rgn_desc 등호 조건을 정식 태그식으로 교체
    ② wrap 없는 태그 LIKE 를 ','||…||',' 정식형으로 교정. 국가어 없는 질의·지역어 질의는 불개입.
    """
    if not _FUND_TBL.search(sql):
        return sql, False
    word, tag = next(((w, t) for w, t in _COUNTRY_TAGS.items() if w in question), (None, None))
    if not tag:
        return sql, False
    canon = f"',' || prfd_attr_cds || ',' LIKE '%,{tag},%'"
    fixed = False
    m = re.search(r"(?:\b\w+\.)?fd_ivst_rgn_desc\s*=\s*'[^']*'", sql)
    if m:
        sql = sql[:m.start()] + canon + sql[m.end():]
        fixed = True
    # 🔴 2026-09-02 S6 재검 — HCX 표현형 2종이 정규식 밖이라 가드가 안 돌았다: ① `prfd_attr_cds LIKE '%IND%'`(콤마 없음 —
    #    S6·S7 둘째 절) ② `zrin_attr_nms LIKE '%인도%'`('인도' 가 '인도네시아' 를 삼켜 7행 혼입 → 142행/59펀드 vs gold 135/58).
    bare = re.compile(rf"(?<!\|\| ')(?:\b\w+\.)?prfd_attr_cds\s+LIKE\s+'%,?{tag},?%'", re.I)
    nms = re.compile(rf"(?:\b\w+\.)?zrin_attr_nms\s+LIKE\s+'%{re.escape(word)}%'", re.I)
    for pat in (bare, nms):
        if pat.search(sql):
            sql = pat.sub(canon, sql)
            fixed = True
    if fixed:
        # 같은 정식형이 OR 로 중복되면 하나로 접는다 — `(canon OR canon)` / `canon OR canon`
        c = re.escape(canon)
        sql = re.sub(rf"\(\s*{c}\s+OR\s+{c}\s*\)", canon, sql, flags=re.I)
        sql = re.sub(rf"{c}\s+OR\s+{c}", canon, sql, flags=re.I)
    return sql, fixed


_Q_FUND_COUNT = re.compile(r"펀드[^?]{0,20}(?:몇\s*개|몇개|개수|몇\s*종)")
# 펀드키 = 운용사코드 / zero-pad 모펀드번호. 🔴 `COALESCE(…, itm_no)` 가 필수다 — 2026-09-02 재검 부수 발견:
#    역외펀드 110행은 mtco_itm_no 가 NULL 이라 키가 NULL 하나로 뭉쳐 COUNT(DISTINCT) 에서 통째로 빠졌다
#    (기본모수 distinct 2,930 vs gold 키 3,040). 정본은 eval gold_sql 의 키 형태 그대로.
_FUND_KEY_EXPR = ("printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || "
                  "COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) "
                  "ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)")


def ensure_fund_distinct_count(sql: str, question: str) -> tuple[str, bool]:
    """펀드 개수 질의의 COUNT(*) 를 펀드단위 COUNT(DISTINCT 키)+클래스수 병기로 교체.

    2026-09-01 FND-034 실측 — 클래스/펀드 구분 누락 6번째 재발: Ground·코드·기본모수 전부
    맞았는데 COUNT(*) 가 클래스 850 을 '펀드 850개' 로 답했다(정답 207펀드). 운용사질의 규칙에
    워크드 예시까지 실려도 무시된다 — HANDOFF 대기 항목 '반복되면 기계 주입' 발동.
    발동 조건: ① public_funds 단일 테이블(JOIN·GROUP BY 없음) ② SELECT 가 COUNT(*) 단독
    ③ 질문이 '펀드 … 몇 개/개수' 형 ④ 질문에 '클래스' 없음(클래스 수를 물으면 불개입).
    클래스 수는 지우지 않고 병기한다 — 답변기가 두 기준을 함께 말할 재료.
    """
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union|group\s+by)\b", sql, re.I):
        return sql, False
    if not _Q_FUND_COUNT.search(question) or "클래스" in question:
        return sql, False
    m = re.match(r"(\s*SELECT\s+)COUNT\(\s*\*\s*\)(?:\s+AS\s+\w+)?(\s+FROM\b)", sql, re.I)
    if not m:
        return sql, False
    head = (f'COUNT(DISTINCT {_FUND_KEY_EXPR}) AS "펀드수", COUNT(*) AS "클래스수"')
    return sql[:m.end(1)] + head + sql[m.start(2):], True


def ensure_fund_series_boundary(sql: str, question: str) -> tuple[str, bool]:
    """N호 질의의 이름 검색에 호 경계식을 기계 주입. (보정된 SQL, 보정했는지)

    2026-09-01 FND-032 실측 2회: ① 미특정 라우팅 수리 후 HCX 가 이름 검색까진 왔는데 호 경계를
    `'2호' IN (a LIKE .. OR b LIKE ..)` 로 옮겨 적음 — 문법상 유효하나 항상 거짓이라 0행 오거절.
    LIKE 에 [^0-9] 문자클래스를 쓰는 등 경계식은 HCX 가 반복적으로 망가뜨린다 — 규칙(종목명검색)에
    정확식이 실려 있어도 소용없어 결정층으로 내린다. GLOB '*[^0-9]N호*' 하나로 '제N호'·'…신탁N호'
    전부 잡히고 12호·32호는 앞 숫자 때문에 배제된다(디스커버리 2호 2행 정확 일치 실측).
    발동 조건: ① public_funds ② 질문의 호수가 정확히 1종 ③ SQL 에 itm_nm 이름 검색 존재
    ④ 올바른 경계식(GLOB [^0-9]N호)이 아직 없음. 조치: 'N호' 를 언급하는 최상위 AND 절을 걷어내고
    (망가진 시도 제거) 경계식 한 절을 주입한다.
    """
    if not _FUND_TBL.search(sql):
        return sql, False
    nos = set(_Q_SERIES_NO.findall(question))
    if len(nos) != 1:
        return sql, False
    n = nos.pop()
    if not re.search(r"\bitm_nm\b", sql, re.I):
        return sql, False
    # 일반 규칙(2R Q6): 호수 표기는 'N호' 와 **'N(자산유형)' / 'N[자산유형]'** 두 형이 공존한다(실측 546행/207 대표번호 —
    #    솔로몬 3호는 한 펀드에 두 표기가 4+4). 앞 글자가 숫자·소수점이 아니어야 12호·1.5배·2.2배가 배제된다.
    bound = (f"(REPLACE(itm_nm,' ','') GLOB '*[^0-9.]{n}호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]{n}[([]*')")
    if f"[^0-9.]{n}호*'" in sql:
        return sql, False
    m = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m:
        return sql, False
    body = m.group(1)
    kept = [c for c in guard.split_conjuncts(body) if f"{n}호" not in c]
    new_body = " " + " AND ".join(kept + [bound]) + " "
    return sql[:m.start(1)] + new_body + sql[m.end(1):], True


def expand_grade_comparison(sql: str, question: str) -> tuple[str, bool]:
    """질문의 '등급 이상/이하' 를 crd_grd 서열 IN 목록으로 확장. (보정된 SQL, 보정했는지)

    2026-08-31 서버 실측: 'A등급 이상 회사채 중 표면금리 5% 넘는' 질의가 crd_grd='A-' 단일
    등급으로 나가 모수 599종목 중 49행만 조회됐다(등급서열 규칙은 실렸으나 무시됨 — c788893 계열).
    발동 조건(전부 만족할 때만 — align_maturity_year 원칙):
      ① 질문의 등급+이상/이하 표기가 정확히 1개 ('A 이상 AA 이하' 범위 질의는 제외)
      ② SQL 의 crd_grd 리터럴 비교(=·부등호)가 정확히 1개이고 IN 은 없다
    부등호도 치환 대상이다 — crd_grd >= 'A-' 는 문자열 사전순이지 서열이 아니다.
    접미사 없는 통칭(A등급)은 그 급 전체를 포함한다: 'A 이상' = A- 부터 위로 7종 (등급서열 규칙).
    """
    hits = _Q_GRADE_CMP.findall(question)
    if len(hits) != 1:
        return sql, False
    letter, suffix, direction = hits[0]
    letter = letter.upper()
    if suffix:
        notch = letter + suffix
    elif direction == "이상":                    # 급 전체 포함 — 그 급의 최하단 표기부터
        notch = next((g for g in reversed(_GRADE_SCALE) if g in (letter + "-", letter + "0", letter)), None)
    else:                                        # 이하 — 그 급의 최상단 표기부터
        notch = next((g for g in _GRADE_SCALE if g in (letter + "+", letter + "0", letter)), None)
    if notch not in _GRADE_SCALE:
        return sql, False
    idx = _GRADE_SCALE.index(notch)
    grades = _GRADE_SCALE[: idx + 1] if direction == "이상" else _GRADE_SCALE[idx:]
    repl = "TRIM(crd_grd) IN (" + ", ".join(f"'{g}'" for g in grades) + ")"
    preds = list(_SQL_GRADE_CMP.finditer(sql))
    ins = list(_SQL_GRADE_IN_FULL.finditer(sql))
    if not preds and len(ins) == 1:
        # 불완전 IN 목록 교정 — 2026-08-31 밤 서버 실측: 'A등급 이상' 이 IN ('AA-','AA0',…) 으로 나가
        # 서열 확장이 어긋났고(단일 리터럴만 잡던 기존 발동 조건의 사각) 상위 표면금리 209종목이 누락됐다.
        got = {v.strip() for v in re.findall(r"'([^']*)'", ins[0].group(1))}
        if got == set(grades):
            return sql, False
        m0 = ins[0]
        return sql[:m0.start()] + repl + sql[m0.end():], True
    if len(preds) != 1 or ins:
        return sql, False
    if len(grades) == 1 and preds[0].group(1) == "=" and preds[0].group(2) == grades[0]:
        return sql, False                        # 'AAA 이상' = 'AAA' — 이미 맞다
    s, e = preds[0].span()
    return sql[:s] + repl + sql[e:], True


_BACKSTOP_Q = re.compile(r"(?:정부|나라|국가)\s*(?:가|이|의|에서)?\s*(?:책임|보증|갚|지급)|정부\s*보증")
_BACKSTOP_ANCHOR = re.compile(r"(?:TRIM\(\s*)?std_pd_mcls_nm\s*\)?\s*=\s*'국공채'", re.I)
_BACKSTOP_PARTS = [                              # (SQL 에 이미 있는지 볼 토큰, 주입식) — 신용보강 규칙의 A~C층
    ("한국은행", "COALESCE(TRIM(pd_pbcm),'')='한국은행'"),
    ("(정부보증)", "pd_nm LIKE '%(정부보증)%'"),
    ("한국주택금융공사", "TRIM(pd_pbcm) IN ('한국주택금융공사','한국토지주택공사','한국산업은행','(주)중소기업은행')"),
]
_RANK_Q = re.compile(r"추천|순으로|순위|톱|top\s*\d|골라|\d+\s*(?:개|종목|가지)", re.I)
_WHERE_TAIL = re.compile(r"\b(?:GROUP\s+BY|ORDER\s+BY|LIMIT)\b", re.I)


def ensure_credit_backstop(sql: str, question: str) -> tuple[str, bool]:
    """'정부가 책임지는/보증하는' 질의 SQL 에 신용보강 필터의 빠진 층을 주입. (보정된 SQL, 보정했는지)

    2026-08-31 저녁 서버 실측 재발: fbc7e4d 에서 지시문+복사용 WHERE 로 승격했는데도 HCX 가
    C층(주금공·LH·산은·기은) OR 절만 또 빼먹어 1위 토지주택채권 330(변) 5.859% 가 다시 누락됐다.
    긴 OR 절은 프롬프트 층만으로 안정 재현이 안 된다 — expand_grade_comparison 과 같은 결정 층.
    발동 조건: ① 질문이 정부보강 어휘에 걸리고 ② SQL 에 국공채 대분류 필터(앵커)가 있다.
    앵커를 괄호로 감싸 빠진 층만 OR 주입(이미 있는 층은 건드리지 않음 — OR 는 멱등이지만 중복 방지).
    질문에 랭킹 신호(추천·순으로·N개)가 함께 있으면 고위험제외·수익률정상 조건도 WHERE 끝에 AND 주입
    — 같은 실측에서 이 절들도 통째로 빠져 사모/1등급 14.05% 가 1위로 올라왔다. 랭킹 신호가 없으면
    (사실확인·집계 질의) 제외를 주입하지 않는다: 조회에서는 제외하지 않는다는 고위험제외 규칙 그대로.
    """
    if not _BACKSTOP_Q.search(question):
        return sql, False
    m = _BACKSTOP_ANCHOR.search(sql)
    if not m:
        return sql, False
    changed = False
    missing = [expr for token, expr in _BACKSTOP_PARTS if token not in sql]
    if missing:
        s, e = m.span()
        sql = f"{sql[:s]}({sql[s:e]} OR " + " OR ".join(missing) + f"){sql[e:]}"
        changed = True
    if _RANK_Q.search(question):
        sql, excl_changed = _append_exclusions(sql, _rank_exclusions(sql, question))
        changed = changed or excl_changed
    return sql, changed


def _rank_exclusions(sql: str, question: str) -> list[str]:
    """고위험제외·수익률정상 중 SQL 에 빠진 절 — 질문이 그 범주를 명시하면 그 절은 건너뛴다.

    '사모 채권 추천'·'위험 높은 채권 순위'·'C0 등급' 처럼 사용자가 제외 대상을 콕 집으면
    그 절을 주입하는 순간 정답 모수가 통째로 사라진다 — 범주 언급 = 우회."""
    excl = []
    if re.search(r"applied_yield", sql, re.I) and not re.search(r"applied_yield\s*>\s*0", sql):
        excl.append("applied_yield > 0")
    if "'11'" not in sql and not re.search(r"위험\s*(?:이|가)?\s*높|고위험|[1-3]\s*등급", question):
        excl.append("pd_risk_gcd <> '11'")
    if "C0" not in sql and not re.search(r"C0|투기|부실", question, re.I):
        excl.append("COALESCE(TRIM(crd_grd),'') <> 'C0'")
    if "사모" not in sql and "사모" not in question:
        excl.append("bd_ofr_tcd <> '사모'")
    return excl


def _append_exclusions(sql: str, excl: list[str]) -> tuple[str, bool]:
    """WHERE 끝(GROUP/ORDER/LIMIT 앞)에 AND 로 잇는다 — 최상위 결합이라 기존 OR 그룹을 깨지 않는다."""
    if not excl:
        return sql, False
    t = _WHERE_TAIL.search(sql)
    pos = t.start() if t else len(sql)
    joiner = " AND " if re.search(r"\bWHERE\b", sql, re.I) else " WHERE "
    return sql[:pos].rstrip() + joiner + " AND ".join(excl) + " " + sql[pos:], True


_RECO_Q = re.compile(r"추천|랭킹|순위|톱|top|골라|(?:높은|낮은)\s*순", re.I)   # '골라줘' 는 추천 신호 (BND-S-002 · 2026-09-01 실측)


def ensure_reco_exclusions(sql: str, question: str) -> tuple[str, bool]:
    """추천·랭킹 채권 질의 SQL 에 고위험제외·수익률정상을 주입. (보정된 SQL, 보정했는지)

    2026-08-31 저녁 서버 실측: 'AA등급 이상 회사채 표면금리 높은 순 5개 추천' 에 사모 3건이
    1~3위로 혼입 — 고위험제외 규칙이 또 무시됐다(신용보강 가드는 정부보강 질의만 커버).
    발동 조건: ① SQL 이 domestic_bonds 단독 조회 ② 질문에 추천·랭킹 신호(추천/순위/높은·낮은 순).
    개수 요청('5개')만으로는 발동하지 않는다 — 조회·사실확인 질의는 제외하지 않는다는 규칙 유지.
    범주를 명시한 질문(사모·C0·투기·위험 높은)은 해당 절을 건너뛴다 (_rank_exclusions)."""
    if "domestic_bonds" not in sql or not _RECO_Q.search(question):
        return sql, False
    return _append_exclusions(sql, _rank_exclusions(sql, question))


_OTHER_AXIS_Q = re.compile(r"만기|잔존|듀레이션|표면|이표|단가|가격|짧|긴|길")


def ensure_reco_sort(sql: str, question: str) -> tuple[str, bool]:
    """추천 질의에 ORDER BY 가 통째로 없으면 기본 정렬(applied_yield DESC)을 주입. (보정된 SQL, 보정했는지)

    2026-09-01 서버 실측: '망하지 않을 회사가 발행한 채권만 골라줘' 가 정렬 없는 임의 5행으로
    나감(3.1~4.1% 비정렬 — 같은 모수의 상위 6.23% 누락). 추천개수정렬 규칙의 '정렬 없는 임의
    N행은 추천이 아니다' 를 결정층이 받는다. 발동 조건 좁게: ① domestic_bonds ② 추천 신호
    ③ ORDER BY 부재 ④ SELECT 에 applied_yield (DISTINCT 는 미선택 컬럼 정렬이 SQLite 제약)
    ⑤ 질문이 다른 정렬 축(만기·표면금리·단가 등)을 말하지 않음 ⑥ 집계(COUNT) 아님."""
    if "domestic_bonds" not in sql or not _RECO_Q.search(question):
        return sql, False
    if re.search(r"\bORDER\s+BY\b|\bCOUNT\s*\(", sql, re.I) or _OTHER_AXIS_Q.search(question):
        return sql, False
    fm = re.search(r"\bFROM\b", sql, re.I)
    if not fm or "applied_yield" not in sql[:fm.start()]:
        return sql, False
    lm = re.search(r"\s*\bLIMIT\b", sql, re.I)
    pos = lm.start() if lm else len(sql)
    return sql[:pos].rstrip() + " ORDER BY applied_yield DESC" + sql[pos:], True


_KTB_Q = re.compile(r"국고채|(?<![가-힣])국채")
_MCLS_EQ = re.compile(r"(?:TRIM\(\s*)?std_pd_mcls_nm\s*\)?\s*=\s*'국공채'", re.I)
_MCLS_IN = re.compile(r"(?:TRIM\(\s*)?std_pd_mcls_nm\s*\)?\s*IN\s*\([^)]*'국공채'[^)]*\)", re.I)
_KTB_FILTER = ("(TRIM(bd_knd)='국고채권' OR (COALESCE(TRIM(bd_knd),'')='' "
               "AND TRIM(std_pd_scls_nm)='국고채'))")
_KTB_PLAIN = "TRIM(bd_knd)='국고채권'"
# STRIPS 인지 신호 — 이 낱말이 질문에 있으면 사용자가 그 개념을 알고 콕 집은 것: STRIPS 주입을 물린다.
# '제외·빼고' 같은 일반 낱말은 신호로 쓰지 않는다 — '사모 빼고 국고채' 가 오폭당한다 (2026-08-31 리드 결정).
_STRIPS_Q = re.compile(r"스트립|STRIPS|원금이자분리", re.I)


_KTB_BDKND = re.compile(r"(?:TRIM\(\s*)?bd_knd\s*\)?\s*=\s*'국고채권'", re.I)
_PBCM_CONJ = re.compile(r"\s+AND\s+(?:TRIM\(\s*)?pd_pbcm\s*\)?\s*=\s*'([^']*)'"
                        r"|(?:TRIM\(\s*)?pd_pbcm\s*\)?\s*=\s*'([^']*)'\s+AND\s+", re.I)


def ensure_ktb_kind(sql: str, question: str) -> tuple[str, bool]:
    """'국고채·국채' 질의의 종류 필터 3결함을 교정. (보정된 SQL, 보정했는지)

    ① 날조 발행사 제거 — 2026-08-31 밤 서버 실측: '국고채 몇 종목' 에 TRIM(pd_pbcm)='한국은행' 이
       붙어 0행 '미수록' 오답. 국고채권 발행사는 전부 '대한민국'(356행 실측) — 한국은행은 통안채다.
       질문에 그 발행사 낱말이 없으면 pd_pbcm 등호 절을 제거한다(질문이 명시하면 의도 존중).
    ② 대분류 뭉개기 교체 — 2026-08-31 저녁 실측: std_pd_mcls_nm='국공채' COUNT = 2,840(지방채·통안채
       혼입) 오답 → 종류필터 ① 확정식으로 교체.
    ③ STRIPS 회수 — bd_knd='국고채권' 단독은 274종목: 종류 결측 STRIPS 21종목이 빠진다(리드 결정
       08-31: 국고채 = 295종목, gold BND-D-029) → 확정식으로 확장.
    발동 조건: 질문에 '국고채' 또는 단독 '국채'(미국채·한국채권 등 합성어 제외).
    STRIPS 탈출구(리드 결정 08-31 밤): 질문에 스트립·STRIPS·원금이자분리가 등장하면 ③을 건너뛰고
    ②도 bd_knd 단독식으로만 교체 — 'STRIPS 제외' 초정밀 질의에서 가드가 넘겨짚지 않는다.
    ⚠ 알려진 한계(감수 결정): '국고채를 포함한 국공채 전체 몇 종목' 류 — 질문에 국고채가 언급되면
       정당한 국공채 대분류 필터도 ②가 국고채로 좁힌다. 뭉개기 오답은 실측(2,840), 이 질의형은 가설이라
       현행 유지 (docs/review_2026-08-26/채권_프로브10_실측_2026-08-31_밤.md §4-3)."""
    if not _KTB_Q.search(question):
        return sql, False
    strips_aware = bool(_STRIPS_Q.search(question))
    changed = False
    m = _PBCM_CONJ.search(sql)
    if m:
        lit = (m.group(1) or m.group(2) or "").strip()
        if lit and lit not in question:
            sql = sql[:m.start()] + sql[m.end():]
            changed = True
    if "국고채권" not in sql:
        m = _MCLS_EQ.search(sql) or _MCLS_IN.search(sql)
        if not m:
            return sql, changed
        return sql[:m.start()] + (_KTB_PLAIN if strips_aware else _KTB_FILTER) + sql[m.end():], True
    if "std_pd_scls_nm" not in sql and not strips_aware:
        m = _KTB_BDKND.search(sql)
        if m:
            sql = sql[:m.start()] + _KTB_FILTER + sql[m.end():]
            changed = True
    return sql, changed


_BOND_COLS = ("bd_knd", "crd_grd", "srfc_irt", "applied_yield", "std_pd_mcls_nm",
              "pd_risk_gcd", "bd_intp_tcd", "bd_ofr_tcd", "pd_pbcm", "remaining_days", "mat_dt")


def normalize_table_names(sql: str) -> tuple[str, bool]:
    """화이트리스트 밖 테이블명이 채권 전용 컬럼과 함께 쓰였으면 domestic_bonds 로 교정.

    2026-08-31 저녁 서버 실측: '은행채 top5' 가 존재하지 않는 bonds_master 로 나가
    validate_sql 기각 → 재생성도 실패 → 무응답. 조건식(bd_knd 2종 IN)은 정확했다 —
    테이블 이름 하나 때문에 정답을 버리는 것은 기각이 아니라 보정 대상(ensure_limit 원칙)."""
    ctes = {n.lower() for n in re.findall(r"\b([A-Za-z_]\w*)\s+as\s*\(", sql, re.I)}
    changed = False
    for t in set(re.findall(r"\b(?:from|join)\s+([A-Za-z_]\w*)", sql, re.I)):
        if t.lower() in TABLES or t.lower() in EXT_TABLES or t.lower() in ctes:
            continue
        if any(c in sql for c in _BOND_COLS):
            sql = re.sub(rf"\b{re.escape(t)}\b", "domestic_bonds", sql)
            changed = True
    return sql, changed


# 2026-08-31 전수 실측 — 고정폭 패딩(뒤 공백)이 있어 무TRIM 등호 비교가 0행이 되는 컬럼.
# 채권: bd_knd 21,682 · pd_pbcm 21,282.
# 🔴 펀드도 같은 문제가 있었다(밤 실측 FND-030): KG 가 준 값 '0016022' 로 = 비교하면 0행,
#    DB 원값은 '0016022 '(8자, 202행)이라 TRIM 해야 맞는다. yaml normalization.trim_columns 에
#    적혀 있어도 플래너가 적용하지 않는다 — 결정 층으로 내린다.
_PADDED_COLS = ("bd_knd", "pd_pbcm",
                "trusc_xtn_itt_cd", "or_co_xtn_itt_cd", "std_itm_no", "ksd_itm_no",
                "rptt_ksd_itm_no", "kofia_fd_ccd", "itm_abrv_nm", "han_clas_nm")


def ensure_trimmed_compare(sql: str) -> tuple[str, bool]:
    """패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 등호·IN 비교를 TRIM 비교로 교정.

    2026-08-31 저녁 서버 실측: bd_knd IN ('일반은행채','특수은행채') 무TRIM 이 16행만 통과
    (TRIM 시 2,031행) — 문자열비교 규칙 무시. LIKE 는 % 와일드카드가 패딩을 흡수하므로 불개입."""
    changed = False
    for col in _PADDED_COLS:
        pat = re.compile(rf"(?<!TRIM\()\b{col}\b(\s*(?:=|<>|IN)\s*)", re.I)
        new = pat.sub(rf"TRIM({col})\1", sql)
        if new != sql:
            sql, changed = new, True
    return sql, changed


_KIND_FILTERS = [   # 질문 낱말(긴 것부터 소진 탐색) → 확정 필터. 같은 필터로 모이는 낱말은 dedupe
    ("일반회사채", "TRIM(bd_knd)='일반회사채'"),
    ("일반은행채", "TRIM(bd_knd)='일반은행채'"),
    ("특수은행채", "TRIM(bd_knd)='특수은행채'"),
    ("통화안정채권", "TRIM(bd_knd)='통화안정채권'"),
    ("통화안정증권", "TRIM(bd_knd)='통화안정채권'"),
    ("통안채", "TRIM(bd_knd)='통화안정채권'"),
    ("신용카드채", "TRIM(bd_knd)='신용카드채'"),
    ("카드채", "TRIM(bd_knd)='신용카드채'"),
    ("국고채", _KTB_FILTER),
    ("국공채", "TRIM(std_pd_mcls_nm)='국공채'"),
    ("특수채", "TRIM(std_pd_mcls_nm)='특수채'"),
    ("지방채", "TRIM(bd_knd) IN ('모집지방채','지역개발채','도시철도공채')"),
    ("은행채", "TRIM(bd_knd) IN ('일반은행채','특수은행채')"),
    ("회사채", "TRIM(std_pd_mcls_nm)='회사채'"),
    ("MBS", "TRIM(bd_knd)='MBS'"),
]


_P = r"[가이은는의에서들\s]{0,4}발행"       # 조사 + '발행' — '~가 발행한 채권' 서술형
_KIND_PARAPHRASES = [   # 발행 주체를 풀어 쓴 질의 (2026-08-31 리드 지적: '회사채' 낱말 없이 '회사에서 발행한 채권').
    # 🔴 순서 = 소진 순서 — '한국은행이 발행' 이 '은행이 발행' 으로, '카드회사가 발행' 이 '회사가 발행' 으로 잡히지 않게 구체적인 것 먼저
    (re.compile(r"한국은행" + _P), "TRIM(bd_knd)='통화안정채권'"),
    (re.compile(r"(?:지자체|지방자치단체|지방\s*정부)" + _P), "TRIM(bd_knd) IN ('모집지방채','지역개발채','도시철도공채')"),
    (re.compile(r"카드[사회]?[사]?" + _P), "TRIM(bd_knd)='신용카드채'"),
    (re.compile(r"캐피[탈털][사회]?[사]?" + _P), "TRIM(bd_knd)='할부금융채'"),
    (re.compile(r"보험[사회]?[사]?" + _P), "TRIM(bd_knd)='보험회사채'"),
    (re.compile(r"증권[사회]?[사]?" + _P), "TRIM(bd_knd)='투자매매.중개채'"),
    (re.compile(r"은행" + _P), "TRIM(bd_knd) IN ('일반은행채','특수은행채')"),
    (re.compile(r"(?:정부|나라|국가)" + _P), "TRIM(std_pd_mcls_nm)='국공채'"),
    (re.compile(r"(?:회사|기업)" + _P), "TRIM(std_pd_mcls_nm)='회사채'"),
]


def _question_kind_filters(question: str) -> set[str]:
    q = question
    found = set()
    for tok, flt in _KIND_FILTERS:
        if tok in q:
            found.add(flt)
            q = q.replace(tok, "◌")        # 긴 낱말 소진 — '일반은행채' 뒤에 '은행채' 가 또 걸리지 않게
    if re.search(r"(?<![가-힣])국채", q):   # 단독 '국채' 만 — 미국채·한국채권 등 합성어 제외
        found.add(_KTB_FILTER)
        q = re.sub(r"(?<![가-힣])국채", "◌", q)
    for pat, flt in _KIND_PARAPHRASES:      # 서술형은 낱말 소진 뒤에 — '회사채' 가 이미 잡혔으면 중복 무해(같은 필터로 dedupe)
        if pat.search(q):
            found.add(flt)
            q = pat.sub("◌", q)
    return found


def ensure_kind_filter(sql: str, question: str) -> tuple[str, bool]:
    """질문의 종류 낱말이 SQL 에 전혀 필터되지 않았으면 동의어 확정식을 주입. (보정된 SQL, 보정했는지)

    2026-08-31 저녁 서버 실측: 'AA등급 이상 회사채 top5' 에 종류 조건 통째 부재 —
    'A등급 이상 회사채' 사고 ②(617160d)와 동일 결함의 재발. 등급 보유 채권이 우연히
    대부분 회사채라 티가 덜 났을 뿐, 특수채 AA 가 섞일 수 있는 모수다.
    발동 조건: ① domestic_bonds 조회 ② SQL 에 종류 컬럼(bd_knd·대분류·소분류)도 발행사
    필터(pd_pbcm)도 없음 — '삼성전자라는 회사가 발행한' 처럼 특정 발행사를 지칭하는 질의에
    회사채 필터를 덧씌우지 않는다(발행사조회 영역) ③ 질문의 종류 낱말·발행주체 서술이 정확히
    한 가지('국고채와 회사채 비교' 류 복수 종류는 불개입). 서술형('회사에서 발행한 채권')은
    _KIND_PARAPHRASES 가 받는다 — 낱말이 없어도 발행 주체 표현으로 종류를 특정.
    ⛑ 2026-09-01 서버 실측: ② 검사가 SQL 전문 대상이라 SELECT 의 TRIM(pd_pbcm) AS 발행기관
    표시 컬럼에 걸려 불개입 — '망하지 않을 회사가 발행한 채권' 이 종류 필터 없이 지방채·국공채로
    나감. 필터 여부는 WHERE 범위에서만 본다(표시·정렬 컬럼은 필터가 아니다)."""
    if "domestic_bonds" not in sql:
        return sql, False
    wm = re.search(r"\bWHERE\b", sql, re.I)
    if wm:
        tail = _WHERE_TAIL.search(sql, wm.end())
        scope = sql[wm.end():tail.start() if tail else len(sql)]
        if re.search(r"bd_knd|std_pd_mcls_nm|std_pd_scls_nm|pd_pbcm", scope, re.I):
            return sql, False
    filters = _question_kind_filters(question)
    if len(filters) != 1:
        return sql, False
    return _append_exclusions(sql, [next(iter(filters))])


_SUP = r"(?:가장|제일|젤|최고로?)"                       # 최상급 수식어
_RISKW = r"(?:위험|리스크)(?:도|성)?[이가은는]?"           # 위험 명사 + 조사 ('위험도가' 꼴 포함)
_TOP_SAFE_Q = re.compile(
    rf"{_SUP}\s*안전|안전(?:성|도)?[이가은는]?\s*{_SUP}\s*높|{_SUP}\s*덜\s*위험"
    rf"|{_RISKW}\s*(?:{_SUP}|매우|아주)\s*낮|{_SUP}\s*{_RISKW}\s*낮"
    rf"|매우\s*낮은\s*위험|{_RISKW}\s*최소|원금\s*(?:이\s*)?최우선|안정형"
    # 부도-공포 서술형 (2026-09-01 실측: '망하지 않을 회사' 가 어휘 밖 — S-009 '원금 잃기 싫은데' 사각과 같은 계열.
    # 원금 보전 최우선 의도 = '16' 단독. '잃' 은 잃기 싫/잃으면 안/잃지 않 꼴만 — '원금을 잃을 수도 있나' 사실확인 오폭 방지)
    r"|망하지\s*않|망할\s*(?:걱정|염려)|(?:돈|원금)[을\s]*(?:떼|뗄|잃(?:기\s*싫|으면\s*안|지\s*않))"
    r"|부도\s*(?:걱정|염려)\s*없")
_TOP_RISK_Q = re.compile(                                # 반대 방향 최상급 — 동반되면 비교 질의라 불개입
    rf"{_SUP}\s*위험한|{_RISKW}\s*(?:{_SUP}|매우|아주)\s*높|{_SUP}\s*안\s*좋")
_YIELD_DEMAND_Q = re.compile(r"[\d.]+\s*(?:%|퍼센트|프로)\s*(?:이상|넘|초과)")
_SAFE16_KINDS = {   # 6등급(매우낮은위험)이 실존하는 종류 확정식 — 2026-08-31 전수 실측 (구매가능 모수 기준 16등급 행수)
    _KTB_FILTER,                                                   # 377 (전부 16)
    "TRIM(std_pd_mcls_nm)='국공채'",                                # 2,838
    "TRIM(std_pd_mcls_nm)='특수채'",                                # 6,077
    "TRIM(bd_knd) IN ('모집지방채','지역개발채','도시철도공채')",        # 2,239 (전부 16)
    "TRIM(bd_knd)='통화안정채권'",                                   # 33 (전부 16)
    "TRIM(bd_knd)='MBS'",                                          # 1,394
    "TRIM(bd_knd) IN ('일반은행채','특수은행채')",                     # 1,241 (특수은행채 몫 — '가장 안전한 은행채' 는 16 강제가 맞다)
    "TRIM(bd_knd)='특수은행채'",                                     # 1,241
}   # 밖에 남는 것(16 = 0 실측): 회사채·일반회사채·일반은행채·신용카드채·할부금융채·보험회사채·투자매매.중개채
_RISK_POS = re.compile(r"pd_risk_gcd\s*(?:IN\s*\(([^)]*)\)|=\s*'(\d+)')", re.I)


def ensure_top_safety(sql: str, question: str) -> tuple[str, bool]:
    """'가장 안전한' 류 최상급 질의의 위험등급 필터를 '16' 단독으로 교정·주입. (보정된 SQL, 보정했는지)

    2026-08-31 실측: '가장 안전한 채권 3개 추천' 이 IN ('15','16') + ORDER BY applied_yield DESC
    로 나가 5등급 SC은행 콜옵션부 7.1% 가 1~3위 — 안전 버킷에서 가장 덜 안전한 구석이 정답을
    밀어냈다. 위험등급방향 규칙의 "'가장 안전한' 만 '16' 단독" 분기가 900자 문장에 파묻혀 미적용.
    '16' 단독이면 전 행 동급이라 수익률 정렬은 동점자 처리가 되므로 ORDER BY 는 건드리지 않는다.
    불개입 2종 — 규칙의 폴백·비교 답변이 정답인 영역: ① 수익률 하한 요구(6등급 최고 6.23%)
    ② 반대 방향 최상급 동반('가장 안전한 것과 가장 위험한 것') — 비교 질의.
    역방향 완화 1종: 6등급이 없는 종류(회사채·카드채 등) 지목 + SQL 이 '16' 단독이면
    IN ('15','16') 폴백으로 완화한다 — 16 강제도, 방치도 아닌 규칙의 폴백 조항 그대로.
    치환은 WHERE 절 범위에서만 — 구조표시 규칙의 SELECT CASE 에 pd_risk_gcd IN ('11','12','13')
    이 실리므로(은행 자본성증권 판정) 전문 치환은 그 CASE 를 파손한다 (2026-08-31 전수조사 실측)."""
    if "domestic_bonds" not in sql or not _TOP_SAFE_Q.search(question):
        return sql, False
    if _TOP_RISK_Q.search(question) or _YIELD_DEMAND_Q.search(question):
        return sql, False
    wm = re.search(r"\bWHERE\b", sql, re.I)
    lo = wm.end() if wm else len(sql)
    tail = _WHERE_TAIL.search(sql, lo)
    m = _RISK_POS.search(sql, lo, tail.start() if tail else len(sql))
    vals = set(re.findall(r"\d+", m.group(1) or m.group(2))) if m else None
    if _question_kind_filters(question) - _SAFE16_KINDS:
        # 6등급이 없는 종류(회사채·카드채 등)를 지목 — '16' 단독이면 폴백 IN ('15','16') 으로 완화.
        # 2026-08-31 밤 서버 실측: '가장 안전한 회사채 3개' 에 HCX 가 = '16' 을 내 0행 '확인 불가' 오답
        # (16 단독 규칙은 따랐는데 폴백 조항을 놓침 — 정답은 5등급 3종 + '6등급엔 회사채 없음' 명시).
        if m and vals == {"16"}:
            return sql[:m.start()] + "pd_risk_gcd IN ('15','16')" + sql[m.end():], True
        return sql, False
    if not m:
        return _append_exclusions(sql, ["pd_risk_gcd = '16'"])
    if vals == {"16"}:
        return sql, False
    return sql[:m.start()] + "pd_risk_gcd = '16'" + sql[m.end():], True


_TOP_YIELD_Q = re.compile(
    rf"(?:수익률|표면금리|이자율|이율|금리|이자)[이가은는도의]?\s*{_SUP}\s*(?:높|낮)"
    rf"|{_SUP}\s*(?:높|낮)은\s*(?:수익률|표면금리|이자율|이율|금리|이자)")
_RISK_VOCAB = re.compile(r"위험|리스크|안전|안정|원금|성향|등급")
# 구매 의향 문형 — 추천 신호(_RECO_Q) 밖의 사각 (2026-09-02 서버 실측: '1년만 굴릴 건데 어떤 채권
# 사면 돼?' 가 추천·최상급 어느 정규식에도 안 걸려 날조 '16' 이 통과 — 6등급 2·4·5·6·7위 답변)
_BUY_INTENT_Q = re.compile(r"사면|사고\s*싶|살까|살\s*만한?|매수하|뭐\s*사|뭘\s*사")


def strip_fabricated_risk_filter(sql: str, question: str) -> tuple[str, bool]:
    """수익률 최상급·추천·구매의향 조회 SQL 에서 질문에 없는 위험등급 필터를 떼어낸다. (보정된 SQL, 보정했는지)

    2026-09-01 서버 실측: '수익률이 제일 높은 채권' 에 HCX 가 pd_risk_gcd = '16' 을 끼워
    6등급 최고(한국수출입금융 6.231%)를 답함 — 진짜 최고는 신보 유동화 728.524%(C0·1등급)다.
    '가장/제일' 최상급을 보고 위험등급방향의 '16 단독' 을 수익률 축에 옮겨 붙인 조건 날조
    (_TOP_SAFE_Q 는 이 질문에 매치되지 않음 — 가드 주입분 아님, 로컬 재현 확인). 조회는
    제외하지 않는다는 고위험제외 규칙 그대로, 위험 어휘가 질문에 없으면 위험등급 절을 제거한다.
    2026-09-02 서버 실측으로 발동 범위 확장: '1년만 굴릴 건데 어떤 채권 사면 돼?' (최상급도
    _RECO_Q 도 아닌 구매 의향 문형)에 같은 날조 '16' — 창 내 수익률 ≥3.861 이 정확히 7행이
    되는 필터는 '16' 단독뿐임을 배타 증명. 추천(_RECO_Q)·구매의향(_BUY_INTENT_Q)까지 받는다.
    불개입 4종: ① 질문에 위험·리스크·안전·안정·원금·성향·등급(그 필터를 정당화하는 어휘)
    ①' 부도-공포 서술형(_TOP_SAFE_Q — '망하지 않을 회사' 류는 _RISK_VOCAB 밖인데 '16' 이 정답:
    확장 전에도 '망하지 않을 회사 중 수익률 최고' 가 오폭 경로였다 — 함께 봉인)
    ② WHERE 에 OR 가 있으면 — 절 제거가 그룹 논리를 바꾼다 ③ 최상위 AND 결합이 아니면.
    추천 질의의 고위험제외(<> '11' 꼴)는 _RISK_POS 에 안 걸려 건드리지 않고, 떼어낸 경우에도
    ensure_reco_exclusions 가 필요분을 다시 넣는다."""
    if "domestic_bonds" not in sql or not (
            _TOP_YIELD_Q.search(question) or _RECO_Q.search(question)
            or _BUY_INTENT_Q.search(question)):
        return sql, False
    if _RISK_VOCAB.search(question) or _TOP_SAFE_Q.search(question):
        return sql, False
    wm = re.search(r"\bWHERE\b", sql, re.I)
    if not wm:
        return sql, False
    lo = wm.end()
    tail = _WHERE_TAIL.search(sql, lo)
    hi = tail.start() if tail else len(sql)
    if re.search(r"\bOR\b", sql[lo:hi], re.I):
        return sql, False
    m = _RISK_POS.search(sql, lo, hi)
    if not m:
        return sql, False
    before, after = sql[lo:m.start()], sql[m.end():hi]
    if not before.strip() and not after.strip():
        return sql[:wm.start()] + sql[hi:], True            # WHERE 가 이 절뿐 — 통째 제거
    pm = re.search(r"\s+AND\s+\Z", before, re.I)
    if pm:
        return sql[:lo + pm.start()] + sql[m.end():], True  # 앞의 AND 와 함께 제거
    nm = re.match(r"\s+AND\s+", after, re.I)
    if nm:
        return sql[:m.start()] + sql[m.end() + nm.end():], True  # 뒤의 AND 와 함께 제거
    return sql, False


_MAT_SORT_Q = re.compile(r"만기[가는이도]?\s*(?:까지)?\s*(?:가장|제일|젤)?\s*(?:긴|길|멀|먼|늦|짧|빠(?:른|르)|오래)"
                         r"|(?:가장|제일|젤)\s*(?:긴|짧은|빠른|늦은|먼)\s*만기")
_ORDER_DUR = re.compile(r"(ORDER\s+BY\s+)(?:\w+\.)?(?:ndy_)?dur\b", re.I)


def ensure_maturity_sort(sql: str, question: str) -> tuple[str, bool]:
    """'만기가 가장 긴/짧은' 질의의 ORDER BY dur 를 mat_dt 로 교체. (보정된 SQL, 보정했는지)

    2026-08-31 서버 실측: '한전 채권 중 만기가 가장 긴' 이 ORDER BY dur DESC 로 나가
    한국전력공사채권999(만기 2049-10-24)를 답함 — 실제 최장은 1184(2052-04-21). 이표율 차이로
    듀레이션 순위와 만기 순위는 역전된다(dur 은 잔존일수도 만기도 아니다 — 만기윈도우 규칙).
    교체 후 mat_dt 하한이 없으면 mat_dt >= 기준일 을 주입 — 만기 짧은 순(ASC)에서 만기일
    미수록 0값 4행·만기 경과 49행이 1위로 오는 것을 막는다(만기 긴 순에도 무해).
    >= 인 이유: 당일 만기 7종목(잔존 1일)이 진짜 최단이다 (2026-09-01 실측: > 가 누락)."""
    if "domestic_bonds" not in sql or not _MAT_SORT_Q.search(question):
        return sql, False
    new = _ORDER_DUR.sub(r"\1mat_dt", sql)
    if new == sql:
        return sql, False
    if not re.search(r"mat_dt\s*>=?\s*\d", new):
        # >= — 당일 만기(잔존 1일)는 모수다. 0값·만기 경과 배제라는 원래 목적엔 >= 로 충분 (2026-09-01)
        new, _ = _append_exclusions(new, [f"mat_dt >= {CUTOFF_INT}"])
    return new, True


_CHEAP_Q = re.compile(r"저렴|(?<![가-힣])비?[싸싼]")
_CHEAP_CUE = re.compile(r"가격|단가|평가|수익률|금리|이자|비용|보수|수수료")
CHEAP_CLARIFY = ("'싸다'는 채권에서 두 가지 뜻으로 해석될 수 있어 확인이 필요합니다. "
                 "① 가격(민평 평가단가)이 낮은 채권 — 만기가 먼 할인채가 상위에 옵니다. "
                 "② 수익률이 높아 같은 금액으로 더 높은 이자를 받는 채권 — 위험이 큰 채권이 상위에 옵니다. "
                 "두 해석은 정반대 목록이 됩니다. 가격 기준과 수익률 기준 중 어느 쪽으로 찾아드릴까요?")


def price_ambiguity_clarify(question: str, tables: list[str]) -> str | None:
    """'싸다·저렴·비싸다' 채권 질의의 결정층 되묻기 — 해당하면 되묻는 문장, 아니면 None.

    2026-08-31 서버 실측: '제일 싼 채권' 에 HCX 가 되묻지 않고 가격 해석으로 단정
    (근거 없는 15·16 필터까지 끼움) — clarify.다의어.싸다 는 🔴 기본값 금지·되묻기 대상이고
    되묻기는 유효 답변이다(주최 8/25). 프롬프트 층(플래너 CLARIFY:)만으로 재현이 안 되므로
    결정층이 받는다. 가격·수익률 등 단서 낱말이 질문에 있으면 되묻지 않는다(규칙 그대로)."""
    if "domestic_bonds" not in tables or not _CHEAP_Q.search(question):
        return None
    if _CHEAP_CUE.search(question):
        return None
    return CHEAP_CLARIFY


_COUNT_Q = re.compile(r"몇\s*(?:개|종목|건|가지)[가-힣]*\s*(?:야|이야|인가|인지|입니|일까|있|없|되|돼)|종목\s*수|개수")
_COUNT_SKIP_Q = re.compile(r"골라|추천|보여|알려\s*줘")   # '몇 개만 골라줘' 는 추천(개수 지정)이지 개수 질문이 아니다


def ensure_count_query(sql: str, question: str) -> tuple[str, bool]:
    """개수 질문('몇 개야·몇 종목이야')의 목록 SELECT 를 COUNT(DISTINCT pd_no) 집계로 교체. (보정된 SQL, 보정했는지)

    2026-09-01 서버 실측: '지금 살 수 있는 채권 중에 수익률 5% 넘는 건 몇 개야?' 에 COUNT 없는
    목록 SELECT + 잔존일수 오름차순 상위 3행이 나감 — 정답 1,406종목은 어디에도 없다. LIMIT 상한
    (30행) 아래서는 답변기가 행을 세어도 개수가 될 수 없으므로 SQL 층에서 집계로 바꿔야 한다.
    ensure_distinct_count 는 COUNT(*) 가 이미 있을 때의 종목 수 교정 — COUNT 자체가 없는 형태는
    이 가드가 받는다. 발동 조건 좁게: ① domestic_bonds ② 개수 의문 어구(추천·목록 신호가 있으면
    불개입 — '몇 개만 골라줘') ③ 단일 평문 SELECT (COUNT·GROUP BY·UNION·중첩 SELECT 없음).
    교체 시 ORDER BY·LIMIT 은 버린다(집계에 무의미)."""
    if "domestic_bonds" not in sql or not _COUNT_Q.search(question) or _COUNT_SKIP_Q.search(question):
        return sql, False
    if re.search(r"\bCOUNT\s*\(|\bGROUP\s+BY\b|\bUNION\b", sql, re.I) or sql.upper().count("SELECT") != 1:
        return sql, False
    fm = re.search(r"\bFROM\b", sql, re.I)
    if not fm:
        return sql, False
    body = sql[fm.start():]
    cut = re.search(r"\s*\b(?:ORDER\s+BY|LIMIT)\b", body, re.I)
    if cut:
        body = body[:cut.start()]
    return "SELECT COUNT(DISTINCT pd_no) AS 종목수 " + body.strip(), True


def ensure_distinct_count(sql: str, question: str) -> tuple[str, bool]:
    """종목 수 질의의 COUNT(*) 를 COUNT(DISTINCT pd_no) 로 교정. (보정된 SQL, 보정했는지)

    채권은 1,078종목이 장내·장외 2~4행이라 COUNT(*) 는 종목 수가 아니다(대표행 규칙).
    2026-08-31 저녁 실측: '국고채 몇 종목' 에 행수가 나감. 질문에 종목·몇 개·개수가 있을 때만.
    2026-09-02 확장 — 존재 질문('~채권 있어?')도 받는다: '퇴직연금으로 살 수 있는 채권 있어?' 에
    HCX 가 스스로 COUNT(*) 를 썼는데 트리거 어휘 밖이라 행수 1,929 가 그대로 남았다(종목 843).
    COUNT(*) 가 이미 있을 때만 치환하는 가드라 어휘 확장의 부작용이 없다 — COUNT 없는 목록
    SELECT 는 건드리지 않으므로 존재 질문의 예시 목록 답변은 그대로 산다(ensure_count_query 의
    _COUNT_Q 는 이 확장에서 제외 — 목록→집계 변환까지 존재 질문에 걸면 예시가 사라진다)."""
    if "domestic_bonds" not in sql or not re.search(r"종목|몇\s*개|개수|있(?:어|나|습니까|나요|는지)", question):
        return sql, False
    fixed = re.sub(r"COUNT\(\s*\*\s*\)", "COUNT(DISTINCT pd_no)", sql, flags=re.I)
    return (fixed, fixed != sql)


def ensure_risk_name_column(sql: str) -> tuple[str, bool]:
    """SELECT 에 위험등급 코드(pd_risk_gcd)만 있으면 이름(pd_risk_nm)을 나란히 붙인다.

    2026-08-31 저녁 서버 실측: 코드만 SELECT 되자 답변기가 '16' 을 "위험등급 16등급" 으로 그대로
    노출(존재하지 않는 등급). pd_risk_nm 은 DB 원본 컬럼이고 코드와 1:1 — 답변은 이름 문구를
    인용하라는 규칙(위험등급방향)을 SELECT 단계에서 결정적으로 보장한다. COUNT(pd_risk_gcd) 처럼
    함수 인자인 경우·이미 pd_risk_nm 이 있는 경우는 불개입.
    """
    if "pd_risk_nm" in sql:
        return sql, False
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm:
        return sql, False
    head = sql[: frm.start()]
    m = re.search(r"\bpd_risk_gcd\b", head)
    if not m or (m.start() > 0 and head[m.start() - 1] == "("):
        return sql, False
    return sql[: m.end()] + ", pd_risk_nm" + sql[m.end():], True


_AGG_HEAD = re.compile(r"\b(?:COUNT|AVG|SUM|MIN|MAX|GROUP_CONCAT)\s*\(", re.I)


def ensure_grade_select_column(sql: str) -> tuple[str, bool]:
    """WHERE 에 신용등급(crd_grd) 조건을 쓰고 SELECT 에는 안 실은 목록 조회에 crd_grd 를 주입.

    2026-09-02 서버 실측: '등급 높은 채권으로 골라줘' 가 crd_grd IN ('AAA'..'AA-') 로
    15,845종목을 제대로 필터하고도 SELECT 가 pd_no·pd_nm 뿐이라, 답변기가 결과만 보고
    "등급 정보가 포함되어 있지 않다" 오거절 — 데이터가 있는데 없다고 말한 사실 왜곡.
    ensure_risk_name_column(위험등급판)과 같은 계열: 답변기는 SELECT 된 컬럼만 본다 —
    필터에 쓴 판단 근거는 접시에 올려야 인용할 수 있다.
    불개입: 집계 SELECT(COUNT·AVG…)·GROUP BY — 컬럼 주입이 집계 형태를 깬다.
    crd_grd_dt 는 \\b 경계로 매치되지 않는다(등급일사용금지 규칙과 무관하게 별개 컬럼)."""
    if "domestic_bonds" not in sql:
        return sql, False
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm:
        return sql, False
    head, rest = sql[:frm.start()], sql[frm.start():]
    if not re.search(r"\bcrd_grd\b", rest) or re.search(r"\bcrd_grd\b", head):
        return sql, False
    if _AGG_HEAD.search(head) or re.search(r"\bGROUP\s+BY\b", sql, re.I):
        return sql, False
    return head.rstrip() + ", TRIM(crd_grd) AS crd_grd " + rest, True


# ── 엣지케이스 가드 2건 (리드 서버 실검증 2026-08-31 · ask_lead_2026-08-31_reply.md) ─────────
_CORP_SUFFIX = re.compile(
    r"(?:[\s,]+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|PLC|LLC|LP|Holdings?|"
    r"Group|ADR|Class\s+[A-C]|Cl\s+[A-C])\.?)+$",
    re.I,
)


@lru_cache(maxsize=None)
def _short_label(label: str) -> str | None:
    """법인 접미어를 뗀 보조 키 — 'Li Auto Inc' → 'Li Auto'.

    🔴 매칭은 `label in question` 방향이라 사람이 짧게 부르면 통째로 놓친다
       (리드 실검증: "Li Auto를 담은 국내 ETF" → 라벨 'Li Auto Inc' 미매칭 → Ground 0건).
    접미어를 뗀 형태를 **보조 키로만** 추가한다. 정식 라벨은 그대로 두므로 기존 매칭은 영향 없다.
    실측(2026-08-31): 전체 라벨 40,171 중 접미어 보유 7,861. 뗀 형태가 다른 노드와 겹치는 것이
    1,762건 있으나 전부 같은 회사의 주식·회사채·지수라 정렬(대상 alias > 긴 라벨 > 값 많은 노드)이
    정본을 고른다. SA·AG·NV·NA 는 회사명 본체와 헷갈려 **일부러 뺐다**(예: 'Visa' 계열 오탐).
    """
    s = _CORP_SUFFIX.sub("", label).strip(" .,")
    return s if s and s != label else None


# 한국어는 체언 뒤에 조사가 **붙어서** 온다 — '하이닉스가'·'기아를'·'삼성전자는'.
# 그래서 "뒤에 한글이 없어야 한다" 로만 보면 정상 문장이 전부 탈락한다.
# 조사 하나까지는 허용하되, 그 뒤에 또 한글이 오면 낱말이 이어지는 것이므로 기각한다
# ('농심라면' → 농심+라 는 조사처럼 보이나 뒤에 '면' 이 붙어 탈락).
_JOSA = (r"(?:이라고|이라는|이라|으로는|으로도|으로|에서는|에서도|에서|에게는|에게|한테|께서|께"
         r"|이랑|랑|와|과|이나|나|이며|며|이고|고|까지|부터|보다|처럼|같이|밖에|조차|마저"
         r"|이는|이가|이를|이도|이만|은|는|이|가|을|를|의|에|도|만|랑)?")


def _boundary_hit(label: str, text: str) -> bool:
    """라벨이 낱말로 들어 있는가.

    🔴 언어를 가려야 한다 — 영숫자 경계로만 보면 '기아' 가 '기아자동차' 에 붙고,
       한글 경계로만 보면 '하이닉스가' 의 조사 때문에 정상 질문이 탈락한다.
    """
    esc = re.escape(label)
    if re.search(r"[가-힣]", label):
        return re.search(rf"(?<![가-힣]){esc}{_JOSA}(?![가-힣])", text) is not None
    return re.search(rf"(?<![A-Za-z0-9]){esc}(?![A-Za-z0-9])", text) is not None


# 짧은 라벨의 하한 — 이 길이 이상이면 **단어경계 검사를 조건으로** 매칭을 허용한다.
# 🔴 2026-08-31 로컬 Ground 일제점검: 편입 상위 28종 중 8종이 매칭 0이었다 —
#    기아(2자)·현대차·카카오·테슬라·애플·네이버 가 Sec_ 하한(한글 4·영문 6)에 통째로 걸렸다.
#    기아는 170개 ETF, 현대차는 168개에 편입돼 있어 질의 가능성이 매우 높다.
#    경계 검사를 붙이면 '나노' 가 '나노기술' 에 안 붙으므로 하한을 내려도 안전하다
#    (한글 2자 Security 라벨 107개는 전부 실재 기업명 — 경방·고영·금양·나노·남성·농심·대덕).
#    영문은 5자까지만 내린다 — 4자는 티커류(BIDU·CXMT·DKME)라 위험하다.
_SHORT_MIN_KO = 2
_SHORT_MIN_EN = 5
# 결합 라벨 — 'A/B' 한 칸에 두 표기가 들어 있다(네이버/NAVER · POSCO홀딩스/포스코홀딩스 · 테슬라/Tesla Inc).
# Security 라벨 1,262개가 이 꼴이라 한쪽 표기로 물으면 통째로 못 잡았다.
_LABEL_SPLIT = re.compile(r"\s*/\s*")

_MATCH_KEYS: dict[int, list] = {}   # id(ctx) -> [(키, 노드, 경계검사)] · 질문과 무관해 1회만 만든다
_SYN_KEYS: dict[int, dict] = {}     # id(ctx) -> {정식 표기: [사용자 통칭 …]}


def _synonym_keys(ctx) -> dict:
    """yaml `synonyms` 를 Ground 의 보조 매칭 키로. {DB 표기: [통칭 …]}.

    🔴 `synonyms` 는 여태 planner_context(프롬프트)와 라우팅 어휘에만 쓰이고 **Ground 에서는 쓰이지 않았다.**
       그래서 '하이닉스'·'삼전'·'곱버스' 를 yaml 에 적어 두고도 개체 매핑이 0건이었다
       (2026-08-31 서버 실측: "국내 etf중 하이닉스가 가장많이 편입된상품" → KG 매칭 없음 →
        HCX 가 컬럼명을 추측해 holding_nm 을 만들어 냄. ext_etf_holdings 의 실제 컬럼은 constituent 다).

    🔴 접두사를 기계적으로 떼는 방식은 **채택하지 않았다.** 실측 결과 위험하다 —
       Sec_ 노드 한글 라벨 309건에서 GS글로벌→'글로벌'(다른 라벨로 실재) · 한화손해보험→'손해보험'(일반명사) ·
       HLB글로벌→'B글로벌'(깨짐) · 현대차증권→'차증권'(무의미)이 나온다.
       사람이 고른 통칭만 쓴다 — 그게 yaml synonyms 가 있는 이유다.
    """
    out = _SYN_KEYS.get(id(ctx))
    if out is None:
        out = {}
        for doc in (ctx.enums or {}).values():
            for term, canon in ((doc or {}).get("synonyms") or {}).items():
                if isinstance(canon, str) and canon and canon != term and len(term) >= 2:
                    out.setdefault(canon, []).append(term)
        _SYN_KEYS[id(ctx)] = out
    return out
# '국내' 가 **상장 시장**을 뜻하는 자리 — 투자지역(wu_inv_rgn)이 아니다.
# 리드 실검증: "Li Auto를 담은 국내 ETF" 에서 '국내' 가 Region_Korea 로 잡혀 wu_inv_rgn='국내' 필터가 붙었다.
# 그러면 중국 기업을 담은 상품이 전부 빠진다. clarify.국내 에 기록돼 있으나 그건 플래너용이라 Ground 엔 안 걸린다.
_KR_LISTING = re.compile(r"국내\s*(?:상장|증시|시장)?\s*(?:ETF|ETN|etf|etn|상품|종목)")


# '미래에셋증권에서 살 수 있는' 은 **판매사** 질의다 — KG 의 수탁사 노드(Org_trustee_*)를 물어오면
# trusc_xtn_itt_cd 필터가 붙어 모수가 엉뚱하게 좁아진다(2026-08-31 밤 FND-030 실측: 2,908펀드 → 14개).
# Region_Korea 억제와 같은 계열의 처방. 수탁을 명시한 질의는 예외로 둔다.
_SALE_CHANNEL_Q = re.compile(r"살\s*수\s*있|판매하|취급|파는|구매\s*가능|판매사")
_TRUSTEE_Q = re.compile(r"수탁|보관")


def _drop_trustee_node(question: str) -> bool:
    """판매 경로를 묻는 질의인가 — 그렇다면 수탁사 노드는 답이 아니다."""
    return bool(_SALE_CHANNEL_Q.search(question)) and not _TRUSTEE_Q.search(question)


def _region_korea_is_listing(question: str) -> bool:
    """'국내 ETF'·'국내 상장 ETF' 처럼 국내가 상장 시장을 가리키면 True.

    domestic_etfs 는 이미 전건이 국내 상장이라 별도 필터가 필요 없다.
    '국내에 투자하는'·'국내 주식' 처럼 투자 대상을 가리키는 자리는 걸리지 않는다.
    """
    return bool(_KR_LISTING.search(question))


_Q_SERIES_NO = re.compile(r"(\d+)\s*호")


def _ground(
    question: str, ctx: RuntimeContext, tables: list[str] | None = None, cross: bool = False
) -> tuple[list, list[str]]:
    """KG 개체 매핑 — 질의 문자열에서 노드 레이블을 찾는다.

    우선순위는 ① 질의가 가리키는 테이블에 alias 가 있는 노드 ② 긴 레이블 ③ 값이 많은 노드(정본) 순이다.

    🔴 ①이 없으면 틀린다. '미래에셋자산운용' 은 채권 발행사 노드(domestic_bonds.pd_pbcm)와
       ETF 운용사 노드(domestic_etfs.cu_fund_mgmt_co, Org_00080008) 양쪽에 걸린다.
       레이블 길이만 보면 국내ETF 질의에 채권 발행사 노드를 물어와 조회가 0건이 된다
       (2026-08-26 실측: "미래에셋자산운용이 운용하는 국내 ETF" → 0행).

    🔴 대상 테이블이 정해졌으면 거기에 alias 가 없는 노드는 **버린다** (2026-08-30 E).
       예전엔 다른 테이블 alias 로 fallback 해 "한국전력 채권" 에 주식 노드의
       ext_etf_holdings.constituent='한국전력' 이 실렸고, 플래너가 구성종목 테이블을 JOIN 하려 들었다.
       교차질의면 ext_* 도 대상이다 — 종목 노드의 alias 는 전부 ext_* 에만 있기 때문이다.
    """
    target = set(tables or ())
    if cross and target:
        target |= set(EXT_TABLES)
    relations = _asks_subsidiaries(question)
    hits, lines = [], []
    # 자동 생성 노드(Idx_a_/Idx_v_/Org_issuer_)는 수천 개라 짧은 라벨의 오매칭을 막기 위해 길이 하한을 높인다
    def _min_len(node, label):
        if node.node_id.startswith("Sec_"):
            # Security(종목) 자동 노드 수만 개 — 영문 라벨은 6자 이상만 (AAPL·NVDA 류 짧은 토큰 오탐 방지), 한글은 4자
            return 6 if not re.search(r"[가-힣]", label) else 4
        # 🔴 2026-08-30 — 한국어 지역·통화·신용등급은 2자가 정상이라 3자 하한에 통째로 걸렸다.
        #    실측: '미국' '중국' '일본' '인도' '국내' '북미' '남미' '유럽' '영국' '대만' … Region 16개 ·
        #    Curr 2개(원화·유로) · CG 18개(AA·A+·BB…) 가 매칭 자체에서 제외돼 있었다.
        #    → "미국에 투자하는 레버리지 ETF" 에서 Region_US 가 안 잡혔다(로컬 Ground 실측).
        #    이 셋은 **사람이 관리하는 닫힌 목록**(합 36개)이라 하한을 2자로 내려도 오탐이 없다 —
        #    Sec_/Org_ 자동 노드와 라벨이 겹치는 것은 0건으로 확인했다.
        #    ⚠️ AssetClass_ 는 **일부러 제외**했다. '기타'(AssetClass_Other)가 '기타비용'(수수료 항목)에
        #       부분일치해 오탐이 난다. '주식'·'채권' 은 맞는 매칭이나 '기타' 하나 때문에 통째로 뺀다.
        if node.node_id.startswith(("Region_", "Curr_", "CG_")):
            return 2
        return 4 if node.node_id.startswith(("Idx_a_", "Idx_v_", "Org_issuer_")) else 3

    # 후보가 수만 개라 노드당 한 번만 편다
    _memo: dict[str, list] = {}

    def _members(node) -> list:
        if node.node_id not in _memo:
            _memo[node.node_id] = _member_aliases(ctx, node.node_id, relations)
        return _memo[node.node_id]

    def _in_target(node) -> bool:
        if not target:
            return False
        return any(t in target for t, _, _ in _members(node))

    syn_keys = _synonym_keys(ctx)

    def _short_ok(node, key: str) -> bool:
        """하한 미만이지만 단어경계를 조건으로 허용할 만한 짧은 라벨인가 — Security 노드에만."""
        if not node.node_id.startswith("Sec_"):
            return False
        lo = _SHORT_MIN_KO if re.search(r"[가-힣]", key) else _SHORT_MIN_EN
        return len(key) >= lo

    def _keys(node):
        """노드의 매칭 키 — 정식 라벨 + 접미어 제거 + 결합 라벨 조각 + yaml 동의어. (키, 경계검사여부)"""
        for label in node.labels:
            if len(label) >= _min_len(node, label):
                yield label, False
            elif _short_ok(node, label):
                yield label, True          # 짧은 라벨은 경계 검사를 조건으로 허용
            short = _short_label(label)
            if short and (len(short) >= _min_len(node, short) or _short_ok(node, short)):
                yield short, True
            if "/" in label:               # '네이버/NAVER' → 네이버 · NAVER
                for piece in _LABEL_SPLIT.split(label):
                    piece = piece.strip()
                    if piece and piece != label and (
                            len(piece) >= _min_len(node, piece) or _short_ok(node, piece)):
                        yield piece, True
            for alias in syn_keys.get(label, ()):
                yield alias, True

    drop_kr = _region_korea_is_listing(question)
    drop_trustee = _drop_trustee_node(question)
    # (키, 노드, 경계검사) 목록은 질문과 무관하다 — 프로세스당 1회만 만든다.
    # 정렬만 질문마다 다시 한다(_in_target 이 대상 테이블에 걸려 있어서).
    pairs = _MATCH_KEYS.get(id(ctx))
    if pairs is None:
        seen_keys: set = set()
        pairs = []
        for node in ctx.kg_nodes:
            for key, bounded in _keys(node):
                if (node.node_id, key) in seen_keys:
                    continue
                seen_keys.add((node.node_id, key))
                pairs.append((key, node, bounded))
        _MATCH_KEYS[id(ctx)] = pairs
    candidates = sorted(pairs, key=lambda x: (not _in_target(x[1]), -len(x[0]), -len(_members(x[1]))))
    consumed = question
    for label, node, bounded in candidates:
        if label not in consumed:
            continue
        if bounded and not _boundary_hit(label, consumed):
            # 보조 키는 단어 경계까지 본다 — 'Apple' 이 'Pineapple' 에 붙는 것을 막는다
            continue
        if drop_trustee and node.node_id.startswith("Org_trustee_"):
            # 판매사 질의에 수탁사 노드를 물어오면 모수가 엉뚱해진다 — 라벨은 소비해 같은 자리에서 다시 안 잡히게 둔다
            consumed = consumed.replace(label, " ")
            lines.append(f"'{label}' → (건너뜀) 판매 경로 질의 — 수탁사 노드는 답이 아니다 (당사판매 thco_sale_yn 로 푼다)")
            continue
        if drop_kr and node.node_id == "Region_Korea":
            # '국내 ETF' 의 '국내' 는 상장 시장이다. 라벨은 소비해 같은 자리에서 다시 잡히지 않게 둔다
            consumed = consumed.replace(label, " ")
            lines.append(f"'{label}' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다")
            continue
        aliases = target_aliases(ctx, node, target, relations)
        if target and not aliases:
            # E — 대상 테이블에 값이 없는 노드. 레이블을 소비하지 않아 같은 표기의 다른 노드가 잡힐 수 있게 둔다
            continue
        # 🔴 Fund 노드 호수 불일치 (2026-09-01 FND-032 실측) — '미래에셋디스커버리증권투자신탁' 노드의
        #    rptt 코드는 4호를 가리키는데 질문은 2호였다. 호가 다르면 다른 펀드다 — 코드 매핑을 실으면
        #    플래너가 4호 값을 2호의 답으로 낼 수 있다. 라벨은 소비하고 코드 대신 이름 검색을 지시한다.
        ho = _Q_SERIES_NO.search(question)
        if (node.node_id.startswith("Fund_") and ho
                and not any(ho.group(1) + "호" in lb.replace(" ", "") for lb in node.labels)):
            consumed = consumed.replace(label, " ")
            lines.append(
                f"'{label}' → {node.node_id} (Fund) — ⚠️ 질문의 '{ho.group(1)}호' 와 이 노드의 코드가 "
                f"가리키는 펀드가 다를 수 있어 코드 매핑을 싣지 않는다. public_funds.itm_nm 공백무시 LIKE "
                f"+ 호 경계(종목명검색 규칙)로 푼다")
            continue
        hits.append(node)
        consumed = consumed.replace(label, " ")
        members = expand_node(ctx, node.node_id, relations)
        where = " · ".join(f"{t}.{c}={raw!r}" for t, c, raw in aliases[:4])
        if len(aliases) > 4:
            where += f" … 외 {len(aliases) - 4}종"
        via = ""
        if len(members) > 1:
            shown = ", ".join(members[1:4]) + (" …" if len(members) > 4 else "")
            via = f" [+후손 {len(members) - 1}: {shown}]"
        lines.append(f"'{label}' → {node.node_id} ({node.node_type}){via} → {where}")
    return hits, lines


# ── 잔여 고유명 검출 (2026-08-31 밤 — FND-016 실측, §6-2d) ────────────────────
# 🔴 최악 등급 사고: "미래에셋코어테크 펀드 1년 수익률" 에서 KG 가 '미래에셋'(운용사)만 잡고
#    '코어테크' 는 소실 → 플래너가 운용사 코드만 필터한 SQL(모수 1,512행)에 LIMIT 1 을 걸어
#    **무관한 펀드(미래에셋인디아솔로몬 -9.73%)의 값을 코어테크의 값으로 단언**했다.
#    실제 코어테크는 187~190%. 문법·테이블·값 검사는 전부 통과 — 질문의 고유명사가 SQL 에
#    반영됐는지 보는 검사가 없었다.
# 발동을 '라벨에 **붙어 있는**(공백 없는) 잔여 토큰' 으로 좁힌 이유: 브랜드+상품명 합성어가
# 정확히 이 사고의 형태이고, '삼성 펀드 보수'(FND-C02 · 되묻기가 정답)처럼 띄어 쓴 질의는
# 건드리면 안 되기 때문이다.
_PARTICLE = re.compile(r"(?:에서|으로|에게|까지|부터|이라는|라는|이란|란|은|는|이|가|을|를|의|에|로|와|과|도|만|의)$")
_GENERIC_NAME_TOKEN = {          # 상품 고유명이 아니라 도메인 일반어 — 이름 검색에 쓰면 모수가 통째로 걸린다
    "증권", "투자신탁", "자산운용", "운용사", "판매사", "수익률", "순자산", "위험등급", "신용등급",
    "클래스", "종류", "보수", "총보수", "수수료", "분배금", "분배율", "벤치마크", "기준가", "설정일",
    "환매", "펀드", "상품", "종목", "주식형", "채권형", "혼합형", "재간접", "파생형", "레버리지",
    "연금", "퇴직연금", "개인연금", "온라인", "오프라인", "공모", "사모", "국내", "해외", "판매중",
}


def residual_name_token(question: str, ground_lines: list[str]) -> str | None:
    """KG 라벨에 붙어 있는데 매핑되지 않은 상품 고유명 — 이름 검색을 강제할 토큰.

    ground_lines 의 각 줄은 `'라벨' → …` 형태라 소비된 라벨을 그대로 읽을 수 있다.
    라벨 **바로 뒤에 공백 없이** 이어지는 한글·영숫자 덩어리에서 조사를 떼고, 길이 3 이상 ·
    도메인 일반어가 아닌 것만 돌려준다. 없으면 None (대부분의 질의가 여기 해당 — 불개입).
    """
    for line in ground_lines:
        m = re.match(r"'([^']+)'\s*→", line)
        if not m:
            continue
        label = m.group(1)
        for tail in re.findall(rf"{re.escape(label)}([0-9A-Za-z가-힣]+)", question):
            tok = _PARTICLE.sub("", tail).strip()
            if len(tok) >= 3 and tok not in _GENERIC_NAME_TOKEN:
                return tok
    return None


# 2026-09-02 리뷰 ②-1 부수 — 40자 창 대신 좌변 itm_nm 판정(_NAME_FILTER)으로 통일. WHERE 절(FROM 뒤)만 본다.
_ITM_NM_LIKE = _NAME_FILTER


def ensure_fund_name_filter(sql: str, token: str | None) -> tuple[str, bool]:
    """질문의 상품 고유명이 SQL 에 반영되지 않았으면 itm_nm LIKE 를 주입. (보정된 SQL, 보정했는지)

    FND-016 사고의 결정 층 처방. 발동 조건: ① 잔여 고유명 토큰이 있고 ② public_funds 조회이며
    ③ SQL 에 itm_nm LIKE 가 전혀 없다(모델이 이미 이름으로 풀었으면 존중).
    0행이 나오면 그것이 정답이다 — 없는 상품을 물었으면 '없음' 이 맞고(FND-R05 계열),
    조건을 완화해 아무 행이나 집어오는 것이 바로 이 사고였다.
    """
    if not token or not _FUND_TBL.search(sql) or _has_name_filter(sql):
        return sql, False
    sql, _ = _append_exclusions(sql, [f"itm_nm LIKE '%{token}%'"])
    # 🔴 LIMIT 1 도 함께 푼다 — 이름으로 좁힌 개별 조회는 클래스가 여럿이다(코어테크 10클래스).
    #    1행만 보면 답변이 "클래스 n개" 를 말할 수 없고, 어느 클래스인지도 임의가 된다.
    if re.search(r"\blimit\s+1\s*$", sql, re.I) and not re.search(r"\bcount\s*\(", sql, re.I):
        sql = re.sub(r"\blimit\s+1\s*$", f"LIMIT {MAX_ROWS}", sql, flags=re.I)
    return sql, True


_SUBSIDIARY_HINT = re.compile(r"자회사|계열사|계열회사|종속회사")


def _asks_subsidiaries(question: str) -> bool:
    """질의가 관계(자회사)를 묻는가 — 관계 확장은 이때만. '에코프로 편입 ETF' 는 본체만 뜻한다."""
    return bool(_SUBSIDIARY_HINT.search(question))


def expand_node(ctx: RuntimeContext, node_id: str, relations: bool = False) -> list[str]:
    """노드 하나를 실물 노드 집합으로 편다 — 자신 + kg_closure 후손 (+ 관계를 물으면 자회사와 그 후손).

    kg_closure 는 build_ontology 가 이행적으로 만들어 두므로 한 단계만 읽는다.
    2026-08-30 실측: 정본 18개(Sec_m_*) 전부 alias 0 · closure 9,919행 — 엔비디아 정본 → 주식·회사채·LEI 노드 3개,
    투자등급 → AAA~BBB- 10종, 캠브리콘 → 펀드 보유 ISIN 노드. 이걸 안 펴면 정본에 매칭될수록 답이 비었다.
    """
    seeds = [node_id]
    if relations:
        seeds += ctx.kg_subsidiaries.get(node_id, [])
    out: list[str] = []
    for s in seeds:
        for n in [s, *ctx.kg_closure.get(s, [])]:
            if n not in out:
                out.append(n)
    return out


def _member_aliases(ctx: RuntimeContext, node_id: str, relations: bool = False) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    seen: set = set()
    for n in expand_node(ctx, node_id, relations):
        for a in ctx.kg_aliases.get(n, ()):
            if a not in seen:
                seen.add(a)
                out.append(a)
    return out


def target_aliases(
    ctx: RuntimeContext, node, target: set, relations: bool = False
) -> list[tuple[str, str, str]]:
    """노드(와 그 후손)의 alias 중 질의 대상 테이블 것만. 대상이 없으면 전부.

    🔴 다른 테이블 alias 로 fallback 하지 않는다 (2026-08-30 E). 대상에 값이 없으면 빈 목록이고,
       호출부(_ground)가 그 노드를 버린다.
    """
    aliases = _member_aliases(ctx, node.node_id, relations)
    if not target:
        return aliases
    return [a for a in aliases if a[0] in target]


MAX_ALIAS_VALUES = 60   # 한 컬럼에 실을 값 상한. 병목이 rate limit 이라 토큰이 곧 처리량이다

# 교차질의 조인 키 — 마스터 ↔ 외부 수집 테이블.
# 출처: eval/questions_*.jsonl 의 gold_sql. 2026-08-26 2차 DB 실측으로 행수 확인
# (75,859 / 910,997 / 179,333 / 10,565행). 🔴 해외는 같은 ISIN 이 상장시장별로 여러 행이라
# 조인 시 팬아웃이 있다 — 개수를 셀 때는 DISTINCT 를 쓴다.
JOIN_KEYS: list[tuple[str, str]] = [
    ("ext_etf_holdings", "ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no"),
    # 🔴 2026-08-31 — isin 조인 폐기. pd_isin_cd 가 두 상품에 걸린 63종에서 다른 ETF 의 구성종목이
    #    붙는다(오배정 8건 실증: FILL.K 에 POWR 구성종목 69행 — overseas_etfs.yaml external_join 참조).
    ("ext_ovs_etf_holdings",
     "ext_ovs_etf_holdings.etf_ticker = replace(replace(overseas_etfs.pd_itm_no,'.K',''),'.O','')"),
    # 🔴 2026-08-30 A-3-03 — grp 단독 금지. grp(=mtco_itm_no)는 운용사 안에서만 유일하다.
    #    단독 조인 시 103개 grp 가 복수 운용사에 걸려 쌍 179,333 중 5,099(2.84%) 오부착(최악 grp='00' → 운용사 34곳).
    #    itm_no 단독으로 바꾸면 형제 클래스 확장(정당 174,234 쌍)이 사라지므로, or_co 를 더한 복합키를 쓴다.
    ("ext_fund_holdings",
     "ext_fund_holdings.grp = public_funds.mtco_itm_no AND ext_fund_holdings.or_co = public_funds.or_co_xtn_itt_cd"),
    ("ext_fund_page", "ext_fund_page.itm_no = public_funds.itm_no"),
]


def _mapping_block(ctx: RuntimeContext, hits: list, target: set, relations: bool = False) -> str:
    """플래너에 넘길 개체 매핑 — **DB 실제 값만** 싣는다.

    🔴 개체 ID(Org_…·Idx_…)를 넘기지 않는다. 넘기면 모델이 그걸 값으로 착각해
       `cu_fund_mgmt_co = 'Org_issuer_97e46cada6'` 같은 SQL 을 쓴다 (2026-08-26 실측).
       ID 는 think_trace 에만 남긴다 — 근거 추적은 사람이 하고, SQL 은 값으로 쓴다.
    """
    out: list[str] = []
    for node in hits:
        name = node.label_ko or node.label_en or node.node_id
        groups: dict[tuple[str, str], list[str]] = {}
        for t, c, raw in target_aliases(ctx, node, target, relations):
            groups.setdefault((t, c), []).append(raw)
        for (t, c), vals in groups.items():
            uniq = sorted(set(vals), key=lambda v: (len(v), v))
            shown = uniq[:MAX_ALIAS_VALUES]
            more = "" if len(uniq) <= len(shown) else f" … 외 {len(uniq) - len(shown)}종"
            out.append(
                f"- {name} ({node.node_type}) → {t}.{c} 의 값: "
                + ", ".join(f"'{v}'" for v in shown) + more
            )
    return "\n".join(out)


def build_grounding(
    ctx: RuntimeContext,
    hits: list,
    tables: list[str],
    cross: bool,
    question: str = "",
    future: list[str] | None = None,
    name_token: str | None = None,
) -> str:
    """플래너에 넘길 근거문서 — KG 매핑 + 도메인 규칙 + 스키마.

    🔴 여기 실린 것만이 SQL 생성의 근거다. 규칙(yaml)을 고치면 이 문서가 바뀌고,
       그래서 프롬프트가 바뀐다 — 판정을 문서가 아니라 yaml 에 적어야 하는 이유다.

    테이블을 탐지하지 못하면 마스터 4개를 다 싣는다. 프롬프트는 커지지만, 엉뚱한 테이블만
    싣고 "컬럼이 없다" 로 실패하는 것보다 낫다.
    """
    target = list(tables) or list(TABLES)
    if cross:
        target += [t for t in EXT_TABLES if t not in target]

    parts: list[str] = []
    mapping = _mapping_block(ctx, hits, set(target), _asks_subsidiaries(question))
    if mapping:
        parts.append(
            "# KG 개체 매핑 — 질의의 표기를 DB 실제 값으로 옮긴 것\n"
            "# 한 개체에 값이 여럿이면 전부 같은 개체다. 하나만 고르지 말고 IN 으로 모두 넣는다.\n"
            + mapping
        )
    if name_token:
        # 🔴 FND-016 사고(§6-2d) — KG 가 브랜드만 잡고 상품 고유명을 흘리면, 위 매핑(운용사 코드)만으로
        #    SQL 이 만들어져 **무관한 펀드의 값**이 답으로 나간다. 매핑 블록 바로 뒤에 둬서 같은 무게로 읽히게 한다.
        parts.append(
            f"# 🔴 상품 고유명 — 질문의 '{name_token}' 은 위 개체 매핑에 없는 **상품 이름**이다\n"
            f"# 위 매핑(운용사·지역 등)만으로 풀지 말 것. WHERE 에 itm_nm LIKE '%{name_token}%' 를 반드시 함께 넣는다.\n"
            f"# 이름으로 좁히면 클래스가 여럿 나온다 — LIMIT 1 로 한 행만 고르지 말고 전부 조회한다."
        )
    if cross:
        # 구성종목·설명서 조건은 ext_* 에 있고 마스터에는 없다. 조인 키를 주지 않으면
        # 모델이 마스터에 없는 컬럼(constituent 등)을 WHERE 에 써서 실행이 깨진다
        # (2026-08-26 실측: "삼성전자를 보유한 국내 ETF" → OperationalError).
        parts.append(
            "# 교차질의 조인 키 — 구성종목·설명서 조건은 아래 외부 테이블에 있다. 반드시 JOIN 해서 쓴다\n"
            "# 🔴 조인 키는 **짝이 정해져 있다.** 아래 줄의 왼쪽 ext_ 테이블은 오른쪽 마스터에만 붙는다 —\n"
            "#    다른 마스터에 갖다 쓰면 없는 컬럼이 되어 실행이 깨진다\n"
            "#    (2026-08-31 실측: public_funds.pd_itm_no 로 ext_etf_holdings 를 조인하려다 두 번 기각).\n"
            "# 🔴 상품군이 둘 이상이면(\"ETF나 펀드\", \"ETF와 공모펀드\") **한 테이블에 뭉치지 말고\n"
            "#    상품군별 SELECT 를 UNION ALL 로 합친다.** 상품군마다 마스터·조인키·수익률 컬럼이 다르다:\n"
            "#      SELECT '국내ETF' AS 구분, e.pd_abrv_nm, e.du_er_1y FROM domestic_etfs e\n"
            "#        JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no WHERE h.constituent='…'\n"
            "#      UNION ALL\n"
            "#      SELECT '공모펀드', p.itm_nm, p.fd_yr1_ern_r FROM public_funds p\n"
            "#        JOIN ext_fund_holdings f ON f.grp = p.mtco_itm_no AND f.or_co = p.or_co_xtn_itt_cd\n"
            "#        WHERE f.holding_nm='…'\n"
            "#    정렬·LIMIT 은 UNION 전체를 감싼 바깥에서 한 번만 건다. 답변에는 구분 열을 함께 밝힌다.\n"
            + "\n".join(f"- {k}" for t, k in JOIN_KEYS if t in target)
        )
    # R-2: triggered 규칙은 질문 어휘가 있을 때만. RULES_MODE=full 이면 종전처럼 전부 (eval/run_paired.py 의 대조군)
    layered = os.environ.get("RULES_MODE", "layered") != "full"
    rules = ctx.planner_context(target, question if (question and layered) else None)
    if rules:
        parts.append("# 도메인 규칙 (ontology/*.yaml — 조건식이 있으면 그대로 쓴다. 일부는 이 질문과 무관할 수 있다)\n" + rules)
    if future:
        # 기준일 이후 연도는 만기일 조건으로만 정당하다 (gate §③ — 사후 검사와 짝)
        parts.append(
            f"# 시점 주의 — 질문의 {', '.join(future)} 은(는) 데이터 기준일({gate.DATA_CUTOFF}) 이후다\n"
            "# 데이터에서 미래 날짜는 mat_dt(만기일)에만 있다 — 만기 조건으로만 쓸 수 있고, 그 시점의 가격·수익률·전망은 없다."
        )
    clarify = ctx.clarify_context(target)
    if clarify:
        parts.append(
            "# 되묻기 규칙 (ontology/*.yaml clarify) — 아래 낱말이 질문에 있고 어느 뜻인지 단서가 없으면 SQL 대신 CLARIFY: 로 되묻는다\n"
            + clarify
        )
    refusal = ctx.refusal_context()
    if refusal:
        # R-5 ② 층 — 범위 밖(실시간·전망·DB 밖·인과)은 SQL 대신 REFUSE:. 가드: SQL 로 조금이라도 답할 수 있으면 SQL (PROJECT.md 모호 질의 최소)
        parts.append(
            "# 답변불가 규칙 (ontology/enums/_refusal.yaml) — 아래 사유에 해당하면 SQL 대신 REFUSE: <사유> 한 줄. 해당하지 않으면 SQL\n"
            + refusal
        )
    schema = ctx.schema_text(target)
    if schema:
        parts.append("# 스키마 — 여기 없는 컬럼은 존재하지 않는다\n" + schema)
    return "\n\n".join(parts)



_NAME_LOOKUP = re.compile(r"TRIM\((?:\w+\.)?(pd_abrv_nm|pd_nm)\)\s*=\s*'([^']+)'", re.I)
_TOKEN_SPLIT = re.compile(r"[A-Za-z0-9]+|[가-힣]+")


def _suggest_similar_products(sql: str) -> list[str]:
    """개별 상품 완전일치 조회가 0행일 때 유사 후보를 찾는다 — clarify.존재하지_않는_개체 의 되묻기 재료.

    'KODEX AI로봇' → 토큰(KODEX·AI·로봇) 중 첫 토큰(브랜드)을 필수로, 나머지 중 하나 이상이
    들어간 상품을 순자산 순으로 최대 4개. 실측(2026-09-01): KODEX 로봇액티브·글로벌로봇(합성)·
    차이나/미국휴머노이드로봇 이 이 방식으로 나온다. LLM 없이 SQLite 재조회 한 번이다.
    """
    m = _NAME_LOOKUP.search(sql)
    if not m:
        return []
    name = m.group(2)
    toks = _TOKEN_SPLIT.findall(name)
    if len(toks) < 2:
        return []
    table = "overseas_etfs" if "overseas_etfs" in sql.lower() else "domestic_etfs"
    first, rest = toks[0], [t for t in toks[1:] if len(t) >= 2]
    if not rest:
        return []
    cond = " OR ".join("replace(pd_abrv_nm,' ','') LIKE ?" for _ in rest)
    args = [f"%{first}%"] + [f"%{t}%" for t in rest]
    q = (f"SELECT DISTINCT TRIM(pd_abrv_nm) FROM {table} "
         f"WHERE replace(pd_abrv_nm,' ','') LIKE ? AND ({cond}) "
         f"ORDER BY du_last_aum DESC LIMIT 4")
    try:
        with connect_readonly() as con:
            return [r[0] for r in con.execute(q, args)]
    except sqlite3.Error:
        return []

def _grounding_blocks(grounding: str) -> list[str]:
    """근거문서에 실제로 실린 블록 이름 — trace 에 글자 수만 적으면 무엇이 실렸는지 알 수 없다.

    블록은 `\n\n` 으로 이어 붙이고 첫 줄이 제목이다. 블록 **안쪽**에도 `#` 주석(모델 지시문)이
    있으므로 전체에서 `#` 줄을 긁으면 요약이 아니라 프롬프트 복사가 된다.
    """
    names = []
    for part in grounding.split("\n\n"):
        head = part.splitlines()[0] if part.strip() else ""
        if head.startswith("# "):
            names.append(re.split(r"\s+[—(]", head[2:].strip())[0].strip())
    return names


def _cell(v, col: str) -> str:
    """조회 결과 한 칸을 답변 생성기가 읽을 글자로.

    🔴 날짜 컬럼(*_dt)은 원본 엑셀이 숫자라 DB 에 REAL 로 들어 있다 — 그대로 str() 하면 '20271231.0' 이 답변에 실린다
       (2026-08-30 밤 실측: 채권 mat_dt·isu_dt·crd_grd_dt·sale_yield_base_dt 전부). 정수값 실수는 정수로 적는다.
    문자열은 양끝 공백을 뗀다 — pd_nm·pd_pbcm 은 고정폭 패딩(최대 98자)이라 retrieved_context 만 부풀리고 답변엔 공백이 따라붙는다.
    """
    if v is None:
        return ""
    if col.endswith("remaining_days") and isinstance(v, (int, float)) and v > 0:
        # 단위를 칸에 박는다 — 2026-08-31 밤 서버 실측: 답변기가 9,375(일)를 "약 93.75년" 으로 환산 환각.
        # 1년 미만은 '6일(약 0.0년)' 이 아니라 '6일' — 2026-09-01 서버 답변에 0.0년 병기 관측.
        return f"{int(v)}일(약 {v / 365:.1f}년)" if v >= 365 else f"{int(v)}일"
    if isinstance(v, float) and v.is_integer() and ("_dt" in col or col.endswith("dt") or "date" in col):
        return str(int(v))
    # 코드 컬럼(*_gcd·*_cd)도 REAL 로 들어 있다 — 2026-09-02 R6·S5 재검: '2.0' 이 "등급 지수는 2.0" 으로 나갔다(정본 "2등급")
    if isinstance(v, float) and v.is_integer() and (col.endswith("_gcd") or col.endswith("_cd")):
        return str(int(v))
    if isinstance(v, str):
        return v.strip()
    return str(v)


def _execute(sql: str) -> tuple[str, int]:
    con = connect_readonly()
    try:
        con.execute(f"pragma busy_timeout={int(SQL_TIMEOUT_S * 1000)}")
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS)
        head = " | ".join(cols)
        body = "\n".join(" | ".join(_cell(v, c) for v, c in zip(r, cols)) for r in rows)
        return f"{head}\n{body}", len(rows)
    finally:
        con.close()


def _apply_sql_guards(sql: str, q: str, name_token: str | None, future, step, ctx) -> str:
    """플래너가 낸 SQL 에 기계 보정 가드를 전부 적용한다.

    🔴 **재생성 SQL 도 반드시 이 체인을 타야 한다** — 2026-08-31 밤 FND-R09 실측:
       금지 컬럼 기각 → 재생성이 han_clas_policies 로 정확히 고쳤는데, 재생성 경로가
       ensure_limit 만 거쳐 근거컬럼 보강을 건너뛰었다. 필터 컬럼이 SELECT 에 없으니
       답변기가 27행을 조회하고도 "정보를 찾을 수 없습니다" 로 버렸다.
       가드를 한 곳에 모아 두 경로가 같은 보정을 받게 한다.
    """
    sql, lb = ensure_maturity_lower_bound(sql)
    if lb:
        step(f"[Guard] 만기 하한 보정 — mat_dt >= {CUTOFF_INT} 주입 (만기일 미수록 0값·만기 경과 행 제외, 당일 만기는 모수)")
    sql, incl = ensure_cutoff_inclusive(sql)
    if incl:
        step(f"[Guard] 기준일 경계 교정 — mat_dt > {CUTOFF_INT} 를 >= 로 (2026-09-01 서버 실측: '만기 가장 짧은' 이 당일 만기 7종목(잔존 1일)을 건너뛰고 8/23 채권을 답함)")
    sql, pop_fixed = ensure_fund_base_population(sql, q)
    if pop_fixed:
        step("[Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)")
    sql, name_fixed = ensure_fund_name_filter(sql, name_token)
    if name_fixed:
        step(f"[Guard] 상품명 필터 주입 — 질문의 고유명 '{name_token}' 이 SQL 에 없어 itm_nm LIKE 주입 + LIMIT 1 해제 "
             "(2026-08-31 밤 FND-016 실측: 운용사 코드만 필터한 모수 1,512행에서 임의 1행이 답으로 나갔다)")
    had_group = bool(re.search(r"\bgroup\s+by\b", sql, re.I))
    sql, rank_fixed = ensure_fund_rank_representative(sql, q)
    if rank_fixed and had_group:
        step("[Guard] 펀드 대표행 보정 — 펀드단위 GROUP BY 랭킹의 bare 정렬 컬럼을 MAX/MIN 으로 감쌈 (2026-08-31 밤 FND-015 채점: TOP5 값 5건 전부 임의 클래스 행 실측)")
    elif rank_fixed:
        step("[Guard] 펀드 대표행 보정 — GROUP BY 펀드키 주입 + MAX/MIN 감싸기 + 클래스수 병기 "
             "(2026-09-02 R7 실측: 미특정 경로에서 HCX 가 GROUP BY 를 버려 한화2.2배 3클래스 도배 — gold 는 NH-Amundi·삼성KOSPI200)")
    sql, err3_fixed = ensure_fund_return_error_exclusion(sql)
    if err3_fixed:
        step("[Guard] 기점오류 제외 주입 — 18개월 이상 수익률 랭킹에 검증 3클래스 NOT IN 주입 (수익률기점오류_제외 규칙 미반영 실측 — 단기·개별 조회엔 미적용)")
    sql, ext_notes = ensure_ext_join(sql, ctx)
    if ext_notes:
        step(f"[Guard] 외부 테이블 JOIN 주입 — {' · '.join(ext_notes)} "
             "(2026-09-02 R2·S11 재검: mtco_nm 환각 3라운드 연속 1차 기각으로 재생성 예산 소진 → 거절)")
    sql, mgr_fixed = ensure_fund_manager_ranking(sql, q)
    if mgr_fixed:
        step("[Guard] 운용사 집계 확정식 — 코드 GROUP BY + 최빈 이름 + 펀드수·클래스수·순자산 억원 템플릿 "
             "(2026-09-02 S11: 이름 GROUP BY + COUNT(*) 로 순자산 질의를 오해 · mtco_nm 3라운드)")
    sql, modal_fixed = ensure_fund_mgmt_modal_name(sql)
    if modal_fixed:
        step("[Guard] 운용사 최빈 이름 — MAX(mgmt_co_nm) 이 합병 코드의 구명칭을 사전순으로 뽑던 것을 "
             "소수 이름 제외로 교정 (2026-09-01 FND-035 재검: 00040007 이 프랭클린템플턴(10행)으로 표기 — 정본은 우리자산운용 373행)")
    sql, ctag_fixed = ensure_fund_country_tag(sql, q)
    if ctag_fixed:
        step("[Guard] 국가 태그 확정식 — 지역 컬럼 등호·미래핑 태그 LIKE 를 ','||prfd_attr_cds||',' 정식형으로 교체 "
             "(2026-09-01 FND-026 재검: ='글로벌' 오모수 + wrap 없는 LIKE 가 98/560행 누락)")
    sql, fcnt_fixed = ensure_fund_distinct_count(sql, q)
    if fcnt_fixed:
        step("[Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 "
             "(2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)")
    sql, series_fixed = ensure_fund_series_boundary(sql, q)
    if series_fixed:
        step("[Guard] 호수 경계 주입 — N호 조건을 GLOB '*[^0-9]N호*' 확정식으로 교체 "
             "(2026-09-01 FND-032 실측: HCX 가 경계식을 `'2호' IN (a OR b)` 로 옮겨 항상-거짓 0행)")
    sql, mixed_fixed = ensure_fund_mixed_type(sql, q)
    if mixed_fixed:
        step("[Guard] 혼합형 확정식 치환 — 유형 조건을 zrin_btyp_nm IN (주식혼합형·채권혼합형) 으로 교체 "
             "(2026-09-01 FND-023 실측 2회: '혼합형' 이 없는 값 기각→오거절, 재검은 혼합자산·대출형·개발형 오모수)")
    sql, gnull_fixed = ensure_group_null_label(sql)
    if gnull_fixed:
        step("[Guard] 분포 결측 라벨 — GROUP BY 축의 NULL 에 '(미수록)' 이름 부여 "
             "(2026-09-01 FND-038 실측: 라벨이 빈칸이라 답변기가 418행 그룹을 통째로 빠뜨렸다)")
    sql, fdist_fixed = ensure_fund_distribution_fund_count(sql)
    if fdist_fixed:
        step("[Guard] 분포 펀드수 병기 — COUNT(DISTINCT 펀드키) 3열 주입 "
             "(2026-09-02 R1 재검: '건' 이 클래스 행 수임을 답이 밝히지 못함 — 클래스/펀드 구분 누락 7번째)")
    sql, enum_fixed = ensure_enum_value_fix(sql, ctx)
    if enum_fixed:
        step("[Guard] enum 표기 교정 — 접미사·공백만 다른 실제 값으로 치환 "
             "(2026-08-31 밤 FND-024 실측: '재간접형' → 실제 값 '재간접'. 기각·재생성으로는 못 고쳐 거절로 나갔다)")
    sql, space_fixed = ensure_spaceless_name_match(sql)
    if space_fixed:
        step("[Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 "
             "(2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)")
    sql, lookup_fixed = ensure_fund_lookup_grouping(sql, q)
    if lookup_fixed:
        step("[Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 "
             "(2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)")
    sql, flist_fixed = ensure_fund_list_grouping(sql, q)
    if flist_fixed:
        step("[Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 "
             "(2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)")
    sql, ev_fixed = ensure_fund_evidence_columns(sql)
    if ev_fixed:
        step("[Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)")
    sql, safe_fixed = ensure_fund_safe_grade_direction(sql, q)
    if safe_fixed:
        step("[Guard] 위험등급 방향 교정 — '안전' 질의의 등급 필터가 1·2(고위험)로 뒤집혀 6(매우 낮은 위험)으로 교체 (2026-08-31 밤 FND-C03 실측: 안전=1등급 반전 조회)")
    sql, grades_fixed = expand_grade_comparison(sql, q)
    if grades_fixed:
        step("[Guard] 등급 서열 확장 — 질문의 '이상/이하' 등급 조건이 단일 등급 비교로 좁혀져 TRIM(crd_grd) IN (서열 목록) 으로 확장 (2026-08-31 'A등급 이상'→crd_grd='A-' 실측)")
    sql, kind_fixed = ensure_kind_filter(sql, q)
    if kind_fixed:
        step("[Guard] 종류 조건 주입 — 질문의 채권 종류 낱말이 SQL 에 필터되지 않아 동의어 확정식을 주입 (2026-08-31 저녁 'AA등급 이상 회사채'에 종류 조건 부재 실측 — 617160d 사고 ② 재발)")
    sql, ktb_fixed = ensure_ktb_kind(sql, q)
    if ktb_fixed:
        step("[Guard] 국고채 종류 교정 — 대분류 국공채(지방채·통안채 혼입)로 뭉개진 필터를 국고채 확정식(bd_knd='국고채권' + STRIPS 결측 회수)으로 교체 (2026-08-31 저녁 '국고채 몇 종목'→2,840 실측)")
    sql, backstop_fixed = ensure_credit_backstop(sql, q)
    if backstop_fixed:
        step("[Guard] 신용보강 층 주입 — 정부보강 질의의 WHERE 에서 빠진 층(C 법정 손실보전 기관 등)·랭킹 제외 조건을 주입 (2026-08-31 저녁 재발 실측: C층 탈락으로 1위 5.859% 누락 + 사모/1등급 14.05% 혼입)")
    sql, reco_fixed = ensure_reco_exclusions(sql, q)
    if reco_fixed:
        step("[Guard] 추천 제외 주입 — 추천·랭킹 질의의 WHERE 에 고위험제외(사모·1등급·C0)·수익률정상 조건을 주입 (2026-08-31 저녁 'AA등급 이상 추천'에 사모 3건 혼입 실측. 질문이 그 범주를 명시하면 건너뜀)")
    sql, recosort_fixed = ensure_reco_sort(sql, q)
    if recosort_fixed:
        step("[Guard] 추천 정렬 주입 — 추천 질의에 ORDER BY 가 없어 기본 정렬 applied_yield DESC 를 주입 (2026-09-01 서버 실측: '망하지 않을 회사 채권 골라줘' 가 정렬 없는 임의 5행 — 상위 수익률 누락)")
    sql, riskstrip_fixed = strip_fabricated_risk_filter(sql, q)
    if riskstrip_fixed:
        step("[Guard] 날조 위험필터 제거 — 수익률·금리 최상급 조회에 질문에 없는 위험등급 절이 끼어 제거 (2026-09-01 서버 실측: '수익률이 제일 높은 채권' 에 pd_risk_gcd='16' 날조 → 6등급 최고 6.231% 오답, 실제 최고 728.524% C0)")
    sql, topsafe_fixed = ensure_top_safety(sql, q)
    if topsafe_fixed:
        step("[Guard] 최상급 안전 교정 — '가장 안전한' 질의의 위험등급 필터를 '16'(매우낮은위험) 단독으로 교정 (2026-08-31 실측: IN ('15','16')+수익률 내림차순이 5등급 콜옵션부 7.1% 를 1~3위로 올림 — 위험등급방향 규칙의 '16 단독' 분기 미적용)")
    sql, matsort_fixed = ensure_maturity_sort(sql, q)
    if matsort_fixed:
        step("[Guard] 만기 정렬 교정 — '만기 가장 긴/짧은' 질의의 ORDER BY dur 를 mat_dt 로 교체 (2026-08-31 서버 실측: 한전 만기 최장이 dur 정렬로 2049년 채권 오답 — 실제 최장 2052년. 듀레이션·만기 순위는 이표율로 역전된다)")
    sql, countq_fixed = ensure_count_query(sql, q)
    if countq_fixed:
        step("[Guard] 개수 질문 집계 교체 — '몇 개/몇 종목' 질문의 목록 SELECT 를 COUNT(DISTINCT pd_no) 로 교체 (2026-09-01 서버 실측: '5% 넘는 건 몇 개야' 에 잔존일수순 임의 3행 목록 — 정답 1,406종목 부재)")
    sql, distinct_fixed = ensure_distinct_count(sql, q)
    if distinct_fixed:
        step("[Guard] 종목 수 교정 — COUNT(*) 를 COUNT(DISTINCT pd_no) 로 교체 (1,078종목이 장내·장외 복수 행 — 행수는 종목 수가 아니다)")
    sql, riskname_fixed = ensure_risk_name_column(sql)
    if riskname_fixed:
        step("[Guard] 위험등급 이름 보강 — SELECT 의 pd_risk_gcd 옆에 pd_risk_nm 추가 (코드 '16' 이 '위험등급 16등급' 으로 노출된 실측 오답 차단 — 답변은 pd_risk_nm 문구 인용)")
    sql, gradecol_fixed = ensure_grade_select_column(sql)
    if gradecol_fixed:
        step("[Guard] 신용등급 컬럼 보강 — WHERE 의 crd_grd 조건이 SELECT 에 없어 주입 (2026-09-02 서버 실측: '등급 높은 채권' 이 AA- 이상 15,845종목을 필터하고도 SELECT 미포함으로 '등급 정보가 없다' 오거절)")
    sql, qualified = qualify_join_columns(sql, ctx)
    if qualified:
        step(f"[Guard] JOIN 모호 컬럼 한정 — {', '.join(qualified)} → FROM 테이블 한정 "
             "(2026-09-02 R2 재검: 재생성 SQL 이 펀드단위 규칙의 COALESCE(…, itm_no) 를 JOIN 에 그대로 옮겨 기각 → 거절)")
    sql, limited = ensure_limit(sql)
    if limited:
        step(f"[Guard] LIMIT 누락 — 상한 {MAX_ROWS} 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)")
    return sql


def answer_question(
    question_id: str,
    question: str,
    *,
    planner: Planner | None = None,
    ctx: RuntimeContext | None = None,
) -> PipelineResult:
    ctx = ctx or load_context()
    trace: list[str] = []
    step: Callable[[str], None] = lambda msg: trace.append(f"{len(trace) + 1}. {msg}")
    result = PipelineResult(question_id=question_id, question=question)

    q = question.strip()
    step(f"[Normalize] 질의 정규화 — 길이 {len(q)}")

    # Route — 상품군을 Ground 보다 먼저 정한다. 같은 표기가 여러 도메인에 걸릴 때 어느 노드를 고를지가
    # 여기서 갈린다. 단어 목록이 아니라 문장 구조 + 온톨로지 값으로 정한다 (router.py, 2026-08-30 F)
    r = route(q, ctx)
    tables = r.tables if r.decided else []          # 미특정이면 빈 목록 = 종전 의미(마스터 4테이블)
    step(f"[Route] 상품군 — {', '.join(tables) or '미특정'} · 근거: {r.why}")
    cross = gate.is_cross_query(q, tables, r.groups) and tables != ["domestic_bonds"]   # 채권엔 ext_* 가 없다
    if not cross and tables == ["public_funds"] and _FUND_EXT_HINTS.search(q):
        # 🔴 2026-08-31 밤 — 설정일·환매조건은 마스터에 없고 ext_fund_page(설명서 수집분)에 있다.
        #    그런데 조인 키는 cross 일 때만 근거문서에 실려서, 단일 도메인 질의는 그 테이블의 존재조차
        #    모른 채 "확인할 수 없음" 으로 나갔다. 설명서 어휘가 있으면 외부 테이블을 열어 준다.
        cross = True
        step("[Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함")

    # Ground — 기각 여부와 무관하게 매핑 결과는 근거로 남긴다 (교차질의면 _ground 가 ext_* 도 대상에 넣는다 — ㉡·E)
    hits, ground_lines = _ground(q, ctx, tables, cross)
    if ground_lines:
        step("[Ground] KG 개체 매핑 — " + " / ".join(ground_lines))
    else:
        step("[Ground] KG 개체 매핑 — 매칭 없음" + (" (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)" if tables else ""))

    # 🔴 미특정 라우팅 보정 (2026-09-01 FND-032 실측) — "…증권투자신탁 2호 위험등급" 은 '펀드' 명사가
    #    없어 미특정 → 4테이블로 빠졌고, KG 가 public_funds 매핑을 찾아 근거문서에 실었는데도 HCX 는
    #    FROM domestic_bonds 완전일치 SQL 을 내 0행 오거절. Ground 가 테이블을 알아냈으면 라우팅이
    #    그것을 쓴다 — 매핑이 단일 상품군만 가리킬 때만 좁힌다(지역·등급 노드처럼 여러 테이블에
    #    걸리면 불개입). §7 구조 리스크 1(미특정 경로 가드 우회)의 부분 해소이기도 하다.
    if not tables and ground_lines:
        seen = set(re.findall(r"\b(domestic_bonds|domestic_etfs|overseas_etfs|public_funds)\.",
                              " ".join(ground_lines)))
        if len(seen) == 1:
            tables = [seen.pop()]
            step(f"[Route] 미특정 보정 — KG 매핑이 {tables[0]} 만 가리켜 그 상품군으로 좁힌다 "
                 "(2026-09-01 FND-032 실측: 미특정 → 채권 테이블 SQL → 0행 오거절)")
            cross = gate.is_cross_query(q, tables, r.groups) and tables != ["domestic_bonds"]
            if not cross and tables == ["public_funds"] and _FUND_EXT_HINTS.search(q):
                cross = True
                step("[Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함")
            hits, ground_lines = _ground(q, ctx, tables, cross)

    # Gate — HCX 호출 0회 기각 경로
    g = gate.check(q, ctx, tables)
    if g.rejected:
        step(f"[Gate] 기각 — {g.reason}")
        step("[Decision] HCX 호출 없이 종료 (근거는 Gate 단계)")
        result.think_trace = "\n".join(trace)
        result.answer = g.answer
        return result
    future = gate.future_tokens(q)
    step(f"[Gate] 통과 — 대상 테이블 {tables or '미특정'}"
         + (" · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)" if cross else "")
         + (f" · 기준일 이후 시점 {future} 포함 → SQL 의 mat_dt 사용 여부로 사후 판정" if future else ""))

    ask = price_ambiguity_clarify(q, tables)
    if ask:
        # 결정층 되묻기 — '싸다' 는 기본값 금지 다의어 (가격 낮음/수익률 높음 정반대). HCX 호출 없이 즉시.
        step("[Clarify] 되묻기(결정층) — '싸다·저렴' 은 기본값 금지 다의어(clarify.다의어.싸다: 가격 낮음/수익률 높음 정반대) · 질문에 단서 없음 → HCX 호출 없이 되묻는다 (역질문은 유효 답변 — 주최 8/25)")
        result.think_trace = "\n".join(trace)
        result.answer = ask
        return result

    if planner is None:
        if future:
            # SQL 이 없으면 해석을 검사할 수 없다 — 기준일 안내로 보수적으로 끝낸다
            step(f"[Decision] SQL 생성기 미연결 상태에서 기준일({gate.DATA_CUTOFF}) 이후 시점 질의 — 확인 불가")
            result.think_trace = "\n".join(trace)
            result.answer = f"제공된 데이터의 기준일은 {gate.DATA_CUTOFF}입니다. 이후 시점의 정보는 확인할 수 없습니다."
            return result
        step("[Plan] SQL 생성기 미연결 — 답변 보류 (Ground·Gate 결과는 유효)")
        result.think_trace = "\n".join(trace)
        result.answer = "현재 시스템 구축 중으로 이 질의에는 답변을 제공할 수 없습니다."
        return result

    name_token = residual_name_token(q, ground_lines) if tables == ["public_funds"] else None
    if name_token:
        step(f"[Ground] 잔여 상품 고유명 '{name_token}' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 "
             "(2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)")
    grounding = build_grounding(ctx, hits, tables, cross, q, future, name_token)
    result.grounding = grounding
    blocks = " + ".join(_grounding_blocks(grounding)) or "없음"
    step(f"[Plan] 근거문서 조립 — 대상 {', '.join(tables) or '마스터 4테이블'} · "
         f"{len(grounding):,}자 · 구성: {blocks}")
    t0 = time.monotonic()
    raw_sql = planner.plan_sql(q, grounding)

    if raw_sql.strip().upper().startswith(REFUSE_PREFIX):
        # R-5 ② — 플래너가 답변불가 규칙에 걸렸다고 선언. SQL 없이 종료 (실행·답변 생성 호출 없음)
        why = raw_sql.strip()[len(REFUSE_PREFIX):].strip()
        step(f"[Refuse] 답변불가 — 플래너 판정 (근거: 답변불가 규칙 블록) · 사유: {why}")
        step("[Decision] 데이터 범위 밖 — HCX 답변 생성 없이 종료")
        result.think_trace = "\n".join(trace)
        result.answer = f"요청하신 내용은 제공된 데이터(기준일 {gate.DATA_CUTOFF})로 확인할 수 없습니다. {why}"
        return result

    if raw_sql.strip().upper().startswith(CLARIFY_PREFIX):
        # 되묻기 — yaml clarify 규칙의 다의어에 단서가 없을 때. 추정으로 답하는 것보다 낫다 (역질문은 유효 답변)
        ask = raw_sql.strip()[len(CLARIFY_PREFIX):].strip()
        step(f"[Clarify] 되묻기 — 플래너가 다의어에 단서가 없다고 판단 (근거: 되묻기 규칙 블록)\n{ask}")
        result.think_trace = "\n".join(trace)
        result.answer = ask
        return result

    # 곱슬따옴표 정규화 — HCX 가 리터럴을 '국고채권' 처럼 타이포그래피 따옴표로 낼 때가 있다
    # (2026-08-31 paired v2 실측: BND-D-007 실행 실패). SQLite 문법 오류 = 통째로 실패라 먼저 편다.
    if any(c in raw_sql for c in "‘’“”"):
        raw_sql = raw_sql.replace("‘", "'").replace("’", "'").replace("“", "'").replace("”", "'")
        step("[Guard] 따옴표 정규화 — 타이포그래피 따옴표(' ' “ ”)를 표준 작은따옴표로 치환")

    sql, dates_fixed = normalize_date_literals(raw_sql)
    if dates_fixed:
        step("[Guard] 날짜 리터럴 보정 — 하이픈 날짜를 정수 YYYYMMDD 로 치환 (SQLite 는 2029-08-22 를 뺄셈=1999 로 계산한다)")
    sql, table_fixed = normalize_table_names(sql)
    if table_fixed:
        step("[Guard] 테이블명 교정 — 화이트리스트 밖 테이블이 채권 전용 컬럼과 함께 쓰여 domestic_bonds 로 교체 (2026-08-31 저녁 'bonds_master' 환각으로 기각→무응답 실측)")
    if len(tables) != 1:
        # 🔴 SQL 사후 라우팅 보정 (2026-09-02 R7 재검) — 라우터가 못 잡는 표현형(오타·외래어·띄어쓰기)으로 미특정이
        #    됐어도 HCX 가 FROM 을 하나로 정했으면 그 상품군이다. 미특정 경로에서 남는 우회 지점은 답변 규칙
        #    (4도메인 12,443자로 희석)과 residual_name_token(tables == ["public_funds"] 조건이라 이름 필터가 꺼짐) —
        #    둘 다 여기서 되살린다. SQL 가드 자체는 FROM 기준이라 이미 적용되고 있었다.
        #    2R Q2-d: 복수 테이블(운용사 3테이블 등)도 같은 처방이고, **재생성 문서**도 그 상품군으로 다시 만든다 —
        #    S11 은 보정이 답변 규칙만 살리고 재생성 피드백엔 4테이블 51,788자를 그대로 붙였다.
        used = {t for t in TABLES if re.search(rf"\b(?:from|join)\s+{t}\b", sql, re.I)}
        if len(used) == 1:
            tables = [used.pop()]
            step(f"[Route] SQL 사후 보정 — FROM {tables[0]} → 그 상품군의 답변 규칙·이름 필터 적용 · 재생성 문서도 그 상품군으로 "
                 "(2026-09-02 R7 재검: 미특정 경로는 답변 규칙이 4도메인으로 희석되고 상품명 필터 가드가 꺼진다)")
            if tables == ["public_funds"] and not name_token:
                name_token = residual_name_token(q, ground_lines)
                if name_token:
                    step(f"[Ground] 잔여 상품 고유명 '{name_token}' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (사후 보정 경로)")
            grounding = build_grounding(ctx, hits, tables, cross, q, future, name_token)
    sql, trim_fixed = ensure_trimmed_compare(sql)
    if trim_fixed:
        step("[Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)")
    if future:
        sql, yr_fixed = align_maturity_year(sql, future)
        if yr_fixed:
            step(f"[Guard] 만기 연도 교정 — 질문의 연도({', '.join(future)})와 SQL 만기 상한의 연도가 달라 상한을 질문 연도로 교정 (2026-08-31 '28년 12월'→20291231 오기 실측)")

    if future and not gate.sql_uses_as_maturity(sql, future):
        # ③ cutoff 사후 검사 — 연도가 mat_dt 조건에 안 쓰였으면 시점·전망 질의다 (gate §③)
        # 🔴 날짜 치환·연도 교정 **뒤에** 검사한다 — 교정 전 SQL 로 검사하면 두 자리 연도('28년') 질의가
        #    "SQL 에 2028 이 없다" 며 억울하게 기각된다 (검사 대상과 실행 대상이 같은 SQL 이어야 한다)
        step(f"[Guard] 기준일 이후 시점 {future} 이(가) SQL 의 mat_dt 조건에 쓰이지 않음 → 만기 질의가 아닌 시점·전망 질의로 판정")
        result.sql = sql
        step("[Decision] HCX SQL 은 만들었으나 기준일 이후 근거가 DB 에 없어 종료")
        result.think_trace = "\n".join(trace)
        result.answer = f"제공된 데이터의 기준일은 {gate.DATA_CUTOFF}입니다. 이후 시점의 정보는 확인할 수 없습니다."
        return result

    sql = _apply_sql_guards(sql, q, name_token, future, step, ctx)
    result.sql = sql
    # 🔴 SQL 은 자르지 않는다. 잘린 SQL 로는 조건식이 틀렸는지 KG 매핑이 틀렸는지 구분할 수 없고,
    #    그 구분이 곧 팀이 챗봇을 검토하는 방법이다 (2026-08-30). 채점자에게도 근거가 된다.
    step("[Plan] SQL 생성 — 아래 문장을 실행합니다\n" + sql)

    err = validate_sql(sql) or forbidden_column_use(sql)
    if not err:
        # ①-b 컬럼 환각(remaining_days 류) — 실행 전 검출해 재생성 기회를 준다 (2026-08-31 paired v2: 실행 실패 8/80)
        unk = guard.unknown_columns(sql, ctx)
        if unk:
            err = "스키마에 없는 컬럼: " + _name_owners(unk[:5], ctx)
    if not err:
        # 🔴 JOIN 의 모호 컬럼 — 실행 오류는 재생성 경로가 없어 그대로 "조회 중 오류" 가 나간다
        amb = guard.ambiguous_columns(sql, ctx)
        if amb:
            err = ("여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): "
                   + ", ".join(amb[:5]) + " — 테이블 별칭을 붙이고 p.itm_no 처럼 모두 한정한다")
    violations = [] if err else guard.check_values(sql, ctx)
    if err or violations:
        # R-4 — 재생성 1회: SQL 기각 또는 WHERE 값이 DB 에 없을 때만. 예산(누적 12초) 안일 때만. 0행은 여기 오지 않는다.
        problem = err or "; ".join(str(v) for v in violations)
        step(f"[Guard] {'SQL 기각' if err else '값 검사 실패'} — {problem}")
        elapsed = time.monotonic() - t0
        if elapsed < REGEN_BUDGET_S:
            feedback = (grounding + "\n\n# 이전 SQL 의 문제 — 아래를 고쳐 다시 SQL 한 문장만 낸다\n"
                        f"- 이전 SQL: {sql}\n- 문제: {problem}\n"
                        "- 값은 'KG 개체 매핑'·'범주형 컬럼의 실제 값' 목록의 표기 그대로만 쓴다. 없는 값이면 그 조건을 빼지 말고 REFUSE: 로 답한다.")
            step(f"[Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 {elapsed:.1f}s)")
            raw2 = planner.plan_sql(q, feedback)
            if raw2.strip().upper().startswith(REFUSE_PREFIX):
                why = raw2.strip()[len(REFUSE_PREFIX):].strip()
                step(f"[Refuse] 재생성에서 답변불가 선언 · 사유: {why}")
                result.think_trace = "\n".join(trace)
                result.answer = f"요청하신 조건의 값이 데이터에 없어 확인할 수 없습니다. {why}"
                return result
            # 🔴 재생성 SQL 도 같은 가드 체인을 태운다 — 안 태우면 재생성이 조건식을 정확히 고쳐도
            #    근거컬럼·대표행 보정이 빠져 답변이 무너진다 (FND-R09 실측: 27행 조회 후 "찾을 수 없음")
            sql, _ = normalize_date_literals(raw2)
            sql = _apply_sql_guards(sql, q, name_token, future, step, ctx)
            result.sql = sql
            step("[Plan] 재생성 SQL — 아래 문장을 실행합니다\n" + sql)
            err = validate_sql(sql) or forbidden_column_use(sql)
            if not err:
                unk = guard.unknown_columns(sql, ctx)
                if unk:
                    err = "스키마에 없는 컬럼: " + _name_owners(unk[:5], ctx)
                elif guard.ambiguous_columns(sql, ctx):
                    err = "한정되지 않은 모호 컬럼: " + ", ".join(guard.ambiguous_columns(sql, ctx)[:5])
            violations = [] if err else guard.check_values(sql, ctx)
        if err or violations:
            step(f"[Guard] 재생성 후에도 실패 — {err or '; '.join(str(v) for v in violations)}")
            step("[Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)")
            result.think_trace = "\n".join(trace)
            result.answer = ("요청하신 조건의 값이 데이터에 없어 확인할 수 없습니다." if violations
                             else "질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.")
            return result
    step("[Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)")

    try:
        rows, n = _execute(sql)
    except sqlite3.Error as e:
        step(f"[Execute] 실행 실패 — {type(e).__name__}")
        result.think_trace = "\n".join(trace)
        result.answer = "데이터 조회 중 오류가 발생해 확인할 수 없습니다."
        return result
    step(f"[Execute] {n}행 조회 (상한 {MAX_ROWS})")
    result.retrieved_context = rows

    if n == 0:
        # 규칙 §3 — 조회 0건이면 지어내지 않고 즉시 확인 불가.
        # R-4 — 어느 조건 때문인지 조건별 건수를 센다(SQLite 재실행뿐, HCX 0회). 조건을 완화해 다시 답하지는 않는다.
        # 🆕 2026-09-01 — 개별 상품 조회(약어명/상품명 완전일치)가 0행이면 **유사 후보를 되묻기 형태로** 붙인다.
        #    clarify.존재하지_않는_개체 의 정답 형태다("혹시 △△ 를 말씀하신 건가요?" 가 정답 처리).
        #    서버 실측(공식 예시 NA-3 "KODEX AI로봇"): '확인되지 않습니다' 단문으로 끝나 후보 4종을 버렸다.
        #    LLM 을 거치지 않는 결정 층이다 — 후보는 SQLite 재조회로만 찾는다.
        answer = "조건에 해당하는 상품이 데이터에서 확인되지 않습니다."
        cand = _suggest_similar_products(sql)
        if cand:
            names = " / ".join(cand)
            answer = (f"요청하신 상품은 제공된 데이터에 없습니다. "
                      f"혹시 다음 상품을 말씀하신 건가요? — {names}")
            step(f"[Suggest] 정확 일치 0건 — 유사 후보 {len(cand)}건 되묻기 (clarify.존재하지_않는_개체)")
        try:
            # 후보 되묻기가 이미 사유를 대신한다 — 이름 조건 하나짜리 진단을 겹쳐 붙이지 않는다
            diag = None if cand else guard.diagnose_zero_rows(sql)
        except sqlite3.Error:
            diag = None
        if diag and diag.text():
            # 개발자용 진단("조건별 단독 조회: …")은 think_trace 에만 남긴다 (2026-08-31 밤 실측:
            # 답변에 그대로 노출돼 가독성 훼손). 사용자 답변에는 같은 진단의 자연어 사유만 붙인다
            # — 리드 결정: 사유는 넣되 개발자 표기 금지 (guard.ZeroRowDiagnosis.user_text).
            step(f"[Diagnose] 0행 원인 — {diag.text()}")
            reason = diag.user_text()
            if reason:
                answer += " " + reason
        step("[Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'")
        result.think_trace = "\n".join(trace)
        result.answer = answer
        return result

    # 🔴 분포(2열 GROUP BY COUNT) 답변은 기계 조립 — HCX 0회 (2026-09-01 FND-038 재검 실측:
    #    행수 병기 후에도 19행 중 17행만 나열 + 금지된 '일부' 서술 재발. 목록 전사는 LLM 에게
    #    맡길 수 없다 — 결정층에서 전 행을 그대로 옮긴다).
    dist = _distribution_answer(sql, rows, n)
    if dist is not None:
        step("[Answer] 분포 답변 기계 조립 — 2열(범주·건수) GROUP BY 결과는 HCX 없이 전 행을 그대로 옮긴다 "
             "(2026-09-01 FND-038 재검: 19행 중 17행 나열 + '일부' 서술 재발)")
        result.think_trace = "\n".join(trace)
        result.answer = dist
        return result
    cnt = _count_answer(sql, rows, n, ground_lines)
    if cnt is not None:
        step("[Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 "
             "(2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)")
        result.think_trace = "\n".join(trace)
        result.answer = cnt
        return result
    mgr = _manager_rank_answer(sql, rows, n)
    if mgr is not None:
        step("[Answer] 운용사 집계 답변 기계 조립 — 템플릿 5열은 HCX 없이 옮긴다 "
             "(2026-09-02 R2·S11 재검: 면책·유보 문장 계열도 함께 소멸)")
        result.think_trace = "\n".join(trace)
        result.answer = mgr
        return result
    lk = _lookup_answer(sql, rows, n, name_token)
    if lk is not None:
        step("[Answer] 개별 조회 답변 기계 조립 — 대표명의 클래스 접미를 떼고 범위·클래스수·판매상태를 옮긴다 "
             "(2026-09-02 R4·S3: '종류A: 최고 189.77%' — 종류A 실값 187.94 · 같은 대표번호 행은 한 줄로)")
        result.think_trace = "\n".join(trace)
        result.answer = lk
        return result
    lst = _list_answer(sql, rows, n)
    if lst is not None:
        step("[Answer] 목록 답변 기계 조립 — 순자산순 펀드 목록 전 행 + 총량 머리줄 "
             "(2026-09-02 R3·S7: 30행 중 5·10행만 옮김 · S6: 총량 대신 '더 있을 수 있음')")
        result.think_trace = "\n".join(trace)
        result.answer = lst
        return result

    answer_rules = ctx.answer_context(tables or list(TABLES))
    # 🔴 행 개수를 데이터에 구워 넣는다 — 2026-09-01 FND-033 실측: 답변기가 11행을 나열해 놓고
    #    "총 10개" 라고 셌다. 순자산 자릿수 훼손과 같은 계열 — 모델에게 산술(개수 세기)을 시키지
    #    말고 복사만 하게 한다. retrieved_context(조회 원문)는 건드리지 않고 답변 입력에만 붙인다.
    answer_rows, hidden = _hide_answer_columns(rows)
    if hidden:
        step(f"[Answer] 내부 코드 컬럼 숨김 — {', '.join(hidden)} (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)")
    header = f"(조회 결과: 총 {n}행)"
    if n >= MAX_ROWS:
        # 🔴 LIMIT 에 잘린 목록은 전체 규모를 굽는다 — 2026-09-02 R3 재검: 30행 중 5행만 옮기고 "다음과 같습니다" 전칭,
        #    총량(560행/248펀드) 미고지. SQLite 재실행 1회·HCX 0회 — 모델이 세지 않게 문자열로 준다.
        cov = _coverage_counts(sql)
        if cov and (cov[1] if cov[2] else cov[0]) > n:
            total, funds, grouped = cov
            scope = f"전체 {total:,}행" + (f" / {funds:,}펀드" if funds is not None else "")
            unit = "펀드" if grouped else "행"
            header = f"(조회 결과: {scope} 중 {n}{unit} 표시 — 나머지는 표시되지 않았으므로 전체를 나열한 것처럼 말하지 않는다)"
            step(f"[Answer] 커버리지 병기 — LIMIT 도달, {scope} 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)")
    rows_for_answer = f"{header}\n{answer_rows}"
    # 옛 2인자 플래너(테스트 프로브 등)와 호환 — answer_rules 를 받지 않으면 넘기지 않는다
    if _accepts_answer_rules(planner):
        result.answer = planner.compose_answer(q, rows_for_answer, answer_rules)
    else:
        result.answer = planner.compose_answer(q, rows_for_answer)
    result.answer, stripped = strip_disclaimer(result.answer)
    if stripped:
        step("[Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 "
             "(answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)")
    result.answer, hedged = strip_false_hedge(result.answer, sql, n)
    if hedged:
        step(f"[Guard] 거짓 유보 제거 — 전수 집계({n}행 < 상한 {MAX_ROWS})에 '더 있을 수 있음·일부' 문장 "
             "(2026-09-02 R2 재검: 운용사 top5 전수 집계에 '더 많은 곳이 있을 수 있습니다')")
    result.answer, name_fixes = verify_product_names(result.answer, rows)
    if name_fixes:
        step(f"[Guard] 상품명 전사 교정 — {' · '.join(name_fixes[:3])} (조회 원문 밖 이름 {len(name_fixes)}건 — "
             "2026-09-02 R3 재검: '삼성중국본토중소형FOSS' 는 DB 에 0행, 실제 FOCUS)")
    result.answer, topcited_fixed = ensure_top_row_cited(result.answer, sql, rows)
    if topcited_fixed:
        step("[Guard] 목록 상위 행 복원 — 답변이 정렬 결과의 하위 행을 인용하며 상위 행을 건너뛰어 누락 행을 덧붙임 "
             "(2026-09-02 서버 실측: '1년만 굴릴 건데' 답변에서 6등급 정렬 1·3위 증발 — 값이 전부 실제 행이라 환각 검사 밖)")
    result.answer, cntfix = ensure_positive_count_answered(result.answer, sql, rows, n, q)
    if cntfix:
        step("[Guard] 집계 오거절 교정 — 양수 COUNT 결과를 '정보 없음' 으로 오독한 답변을 기계 조립으로 교체 "
             "(2026-09-02 서버 실측: '퇴직연금으로 살 수 있는 채권 있어?' 에 COUNT 1,929 반환에도 오거절)")
    step("[Answer] 답변 생성 완료" + (f" — 답변 규칙 {len(answer_rules):,}자 적용 ({', '.join(tables) or '전체'})" if answer_rules else ""))
    result.think_trace = "\n".join(trace)
    return result
