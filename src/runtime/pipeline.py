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
CUTOFF_INT = int(gate.DATA_CUTOFF.replace("-", ""))   # 20260824 — 표기 기준일(리드 결정 09-02). 날짜 컬럼은 정수 YYYYMMDD (REAL 적재)
# 🔴 만기 하한(구매가능)은 BUYABLE_INT(20260824) 를 쓴다 — as-of 와 판정일을 분리 (리드 결정 2026-09-02: 8/22·8/23 만기 14종목은 만기 경과).
BUYABLE_INT = int(gate.BUYABLE_CUTOFF.replace("-", ""))


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
    # 🔴 2026-09-03 — 가드·슬롯 **적용 전** HCX 원문. 로그·실험 전용이며 응답 5필드가 아니다.
    #    이것 없이는 "가드가 무엇을 고쳤는가" 를 사후에 재생할 수 없다 —
    #    enforce 슬롯 섀도(docs/guard_to_yaml_migration_2026-09-03.md 단계 2)가 요구한다.
    #    재생성이 돌면 그 원문으로 덮어쓴다(마지막으로 플래너가 낸 것).
    raw_sql: str = ""
    enforce_fired: list = field(default_factory=list)   # 발동한 enforce mark 목록


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
# 서버 실측 2026-09-02 "바이오 ETF 추천" — OR 사슬 뒤에 괄호 없이 AND 필터를 붙여
# 필터가 마지막 OR 가지에만 걸렸다(괄호를 치면 0행, 안 치면 모수 오염 — 어느 쪽도 오답).
# 말로 하는 규칙은 무시되므로 기계적으로 차단한다.
_WHERE_SEG = re.compile(r"(?<![A-Za-z_])WHERE(?![A-Za-z_])(.*?)(?=(?<![A-Za-z_])(?:GROUP|ORDER)\s+BY|(?<![A-Za-z_])LIMIT|(?<![A-Za-z_])UNION|$)", re.I | re.S)
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
    """위반 사유를 반환. None 이면 통과.

    🔴 10R gold N2 — **서로 독립인 위반은 전부 모아 한 문자열로 돌려준다.** 첫 사유에서 return 하면 재생성 1회가
       사유 하나만 고치고 다음 사유에 다시 걸려 예산이 소진된다(OFFICIAL-004: 1차 괄호 · 2차 테이블 참조 → 무응답).
       구조 게이트(다중문·SELECT 여부·완결성·EXPLAIN)만 조기 반환한다 — 이게 깨져 있으면 뒤 검사가 무의미하다.
    """
    s = sql.strip().rstrip(";")
    errs: list[str] = []
    if ";" in s:
        return "다중 문장 금지"
    if not re.match(r"^\s*(?:select|with)\b", s, re.I):
        # WITH(CTE)도 읽기 전용 단일문 — FROM/JOIN 테이블 검사는 CTE 본문까지 훑는다 (2026-08-31 저녁 오탐 방지)
        return "SELECT 만 허용"
    if _FORBIDDEN.search(s):
        return "금지 키워드 포함"
    for seg_m in _WHERE_SEG.finditer(s):
        seg = re.sub(r"'[^']*'", "''", seg_m.group(1))   # 문자열 리터럴 안의 OR/AND 무시
        # (WHERE 의 윈도우·집계 함수 기각은 _sql_precheck 의 6R P 검사(_WHERE_AGG)가 담당 — 2026-09-02 병합 시 중복 검사 제거)
        prev = None
        while prev != seg:                                # 괄호 안쪽부터 반복 제거 → 최상위만 남긴다
            prev, seg = seg, re.sub(r"\([^()]*\)", " ", seg)
        if re.search(r"\sOR\s", seg, re.I) and re.search(r"\sAND\s", seg, re.I):
            errs.append("WHERE 최상위에 괄호 없는 OR 와 AND 가 섞여 있다 — AND 가 먼저 묶여 "
                        "필터가 마지막 OR 가지에만 걸린다. OR 가지 전체를 괄호로 감싸라: (A OR B) AND 필터")
            break
    used = {t for t in TABLES if re.search(rf"\b{t}\b", s, re.I)}
    if not used:
        m = re.search(r"\bfrom\s+([\w.]+)", s, re.I)
        return f"허용 테이블 밖: {m.group(1) if m else '?'}"
    # FROM/JOIN 에 등장하는 모든 테이블이 마스터 4 + 외부 ext_* 안에 있어야 한다 (교차질의 조인 허용, 그 외 차단)
    ctes = {n.lower() for n in re.findall(r"\b([A-Za-z_]\w*)\s+as\s*\(", s, re.I)}  # WITH 별칭은 테이블이 아니다
    declared = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", s, re.I)} | ctes
    for t in sorted(declared - ctes):
        if t not in TABLES and t not in EXT_TABLES:
            errs.append(f"허용 테이블 밖: {t}")
            break
    # 🔴 FROM/JOIN 에 없는 테이블을 `테이블.컬럼` 으로 참조하면 실행 시 OperationalError 가 난다.
    #    2026-08-31 서버 실측 — "Li Auto를 담은 국내 ETF":
    #      SELECT pd_nm FROM domestic_etfs WHERE TRIM(ext_etf_holdings.ticker)='LI' … → 실행 실패.
    #    Guard 는 "검사 통과" 를 찍고 Execute 에서 죽어 답변이 '오류가 발생해 확인할 수 없습니다' 로 나갔다.
    #    여기서 기각하면 재생성 1회(R-4)가 사유를 받아 JOIN 을 붙일 기회를 얻는다.
    #    별칭(`d.pd_nm`)은 걸리지 않는다 — 아는 테이블 이름일 때만 본다.
    known = set(TABLES) | set(EXT_TABLES)
    for qual in sorted({m.group(1).lower() for m in _TABLE_QUALIFIER.finditer(s)}):
        if qual in known and qual not in declared:
            errs.append(f"FROM/JOIN 에 없는 테이블 참조: {qual} (JOIN 을 붙이거나 조건을 옮겨야 한다)")
            break
    # 🔴 ext_* 는 조인 짝이 정해져 있다 — 다른 마스터와 섞으면 의미가 틀린 조인이 된다.
    #    2026-09-01 서버 실측(공식 예시 #3): domestic_etfs 를 ext_fund_holdings(펀드 보유)와
    #    d.pd_itm_no = h.grp 로 조인 — 컬럼은 각자 실존해서 수식자 검사를 통과했지만 키가 남남이라 0행.
    #    ext_* 단독 사용(ext_etf_holdings.etf_name 만 조회 등)은 정상이므로,
    #    **다른 마스터가 선언돼 있는데 제 짝이 없을 때만** 기각한다.
    for ext, master in _EXT_PAIR.items():
        if ext in declared and master not in declared and (declared & set(TABLES)):
            errs.append(f"{ext} 의 조인 짝은 {master} 다 — 다른 마스터와 조인 금지"
                        f" (교차질의 조인 키 목록의 짝을 그대로 쓴다)")
            break
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
                errs.append(f"{t} 에 없는 컬럼: {col}{hint}")
                break
    # KG 1R R3 — 구조 검증 일반화: ③ 템플릿 자리표시자 잔재(`<코드>` 를 리터럴로 복사 — KG-012 `'%,<CHN>,%'` 0행 "0개") ·
    #    비-SQLite 토큰(`TOP n` — KG-028 OperationalError "오류"). 재생성 사유로 돌려준다.
    m_tpl = re.search(r"<[A-Za-z가-힣_][A-Za-z가-힣_ ]*>", s)
    if m_tpl:
        errs.append(f"템플릿 자리표시자 {m_tpl.group(0)} 잔재 — 규칙의 <…> 는 실제 값으로 치환해 쓴다")
    if re.search(r"\bselect\s+(?:distinct\s+)?top\s+\d+", s, re.I):
        errs.append("SQLite 문법이 아니다(TOP n) — LIMIT n 을 쓴다")
    if not re.search(r"\blimit\s+\d+", s, re.I):
        errs.append("LIMIT 누락")
    # KG 4R G6 — **실행 전에 파싱한다.** 여기까지 정규식 검사를 다 통과해도 문법이 깨져 있으면 실행 예외가
    #    "데이터 조회 중 오류가 발생해 확인할 수 없습니다" 로 사용자에게 나간다 — 오거절보다 나쁜 표면이다.
    #    Z13 실측: `… prvo_pbff_desc = '공모') UNION ALL (SELECT …` 괄호 불균형이 "[Guard] SQL 검사 통과" 뒤
    #    OperationalError: near ")" 로 죽었다. complete_statement 로 미완결문을, EXPLAIN 드라이런으로 문법을 잡고
    #    재생성 피드백으로 돌린다(실행은 하지 않는다 — EXPLAIN 은 계획만 낸다).
    if not sqlite3.complete_statement(s + ";"):
        errs.append("SQL 이 완결된 한 문장이 아니다(괄호·따옴표 불균형) — 괄호 짝과 따옴표를 맞춰 한 문장으로 낸다")
        return " / ".join(errs)          # 미완결문에 EXPLAIN 을 태우면 사유가 중복된다
    try:
        con = connect_readonly()
        try:
            con.execute("EXPLAIN " + s)
        finally:
            con.close()
    except sqlite3.OperationalError as e:
        # 🔴 **문법 오류만** 여기서 기각한다. 'no such column/table' 은 guard.unknown_columns·ambiguous_columns 가
        #    더 나은 사유(어느 테이블 컬럼인지)를 내는 자리이고, 스키마가 다른 환경에서 정답 SQL 을 버릴 수 있다
        #    (같은 목적 가드 중복 0 — 2026-09-02 실측: ext_etf_holdings 별칭 JOIN 이 오탐 기각됐다).
        if re.search(r'near "|unrecognized token|incomplete input|syntax error', str(e), re.I):
            errs.append(f"SQL 문법 오류(실행 전 파싱): {e}")
    except sqlite3.Error:
        pass                     # 파서 밖 오류(연결 등)로 정상 SQL 을 막지 않는다
    # 🔴 14R gold ③-5 (부류 AC) — **위치 `ORDER BY` 는 SELECT 열 수와 대조한다.** EXPLAIN 은 이걸 못 잡는다.
    #    OFFICIAL-005 실측: 재생성이 SELECT 를 6→5열로 줄이면서 `ORDER BY 6` 을 그대로 둬
    #    `1st ORDER BY term out of range` 로 죽었고, 사용자에겐 "데이터 조회 중 오류" 가 나갔다.
    over = _order_by_position_overflow(s)
    if over:
        errs.append(f"위치 ORDER BY 가 SELECT 열 수를 넘는다({over}) — "
                    "ORDER BY 는 위치 번호가 아니라 컬럼명·별칭으로 쓴다")
    return " / ".join(errs) if errs else None


_ORDER_BY_TERMS = re.compile(r"\border\s+by\b(.*?)(?=\blimit\b|$)", re.I | re.S)


def _order_by_position_overflow(sql: str) -> str | None:
    """위치 `ORDER BY n` 의 n 이 그 SELECT 의 항목 수를 넘으면 사람말 사유, 아니면 None.

    단일 SELECT 만 본다 — UNION 은 가지마다 항목 수가 같아야 하므로 첫 가지로 판정하면 오탐이 난다.
    """
    if not _single_select(sql):
        return None
    frm = re.search(r"\bfrom\b", sql, re.I)
    m_sel = _SELECT_HEAD.match(sql)
    m_ob = _ORDER_BY_TERMS.search(sql)
    if not (frm and m_sel and m_ob) or m_ob.start() < frm.start():
        return None
    n_items = len(_split_select_items(sql[m_sel.end():frm.start()]))
    for term in m_ob.group(1).split(","):
        pos = term.strip().split()[0] if term.strip() else ""
        if pos.isdigit() and not (1 <= int(pos) <= n_items):
            return f"ORDER BY {pos} · SELECT 항목 {n_items}개"
    return None


_WHERE_AGG = re.compile(r"\bOVER\s*\(|\b(?:SUM|COUNT|AVG|MIN|MAX|TOTAL|GROUP_CONCAT|ROW_NUMBER|RANK|DENSE_RANK)\s*\(", re.I)


def _strip_subselects(text: str) -> str:
    """괄호 균형을 세며 `(SELECT …)` 구간만 지운다 — WHERE 안의 서브쿼리 집계는 합법이라 검사 대상이 아니다."""
    out, depth, skip_from = [], 0, None
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
            if skip_from is None and re.match(r"\(\s*select\b", text[i:], re.I):
                skip_from = depth
        elif ch == ")":
            if skip_from == depth:
                skip_from = None
                depth -= 1
                i += 1
                continue
            depth -= 1
        if skip_from is None:
            out.append(ch)
        i += 1
    return "".join(out)


def where_window_or_aggregate(sql: str) -> str | None:
    """6R P (5R V5) — WHERE 최상위에 쓴 윈도우·집계 함수(`WHERE RANK() OVER(...) <= 5` · `WHERE COUNT(*) > 3`).
    SQLite 는 실행 시 'misuse of window function' / 'misuse of aggregate' 로 죽는다 — 실행 전에 잡아 재생성 1회를 준다.
    서브쿼리 안의 집계는 제외. 걸린 함수 표기를 돌려주고, 없으면 None.

    🔴 10R KG 부류 Q — WHERE 추출을 `_WHERE_SEG`(종료어에 **UNION 포함**)로 통일한다. 종전 정규식은 종료어에
       UNION 이 없어 `… WHERE … UNION ALL SELECT '국내 ETF', COUNT(*) FROM …` 에서 **둘째 가지의 SELECT 목록**까지
       WHERE 로 읽고 `COUNT(` 를 오탐 기각했다(X8·X9·X15·KG-025·KG-026 오거절 5건). UNION 가지는 각각 독립 스코프다.
    """
    for m_w in _WHERE_SEG.finditer(sql):
        m = _WHERE_AGG.search(_strip_subselects(m_w.group(1)))
        if m:
            return m.group(0).strip()
    return None


# ── 10R gold N1 — 최상위 OR/AND 혼용은 기각이 아니라 보정한다 ───────────────
def _split_top_level(where: str) -> list[str] | None:
    """WHERE 본문을 최상위 AND/OR 로 가른 [피연산자, 연산자, 피연산자, …]. 최상위 연산자가 없으면 None.
    괄호·문자열 리터럴 안은 건드리지 않는다(`split_conjuncts` 와 같은 주사 방식, OR 도 함께 본다)."""
    out, depth, buf, i, in_q = [], 0, [], 0, False
    while i < len(where):
        ch = where[i]
        if ch == "'":
            in_q = not in_q
        elif not in_q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0:
                for op in (" AND ", " OR "):
                    if where[i:i + len(op)].upper() == op:
                        out += ["".join(buf).strip(), op.strip().upper()]
                        buf, i = [], i + len(op)
                        break
                else:
                    buf.append(ch)
                    i += 1
                continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if not out or not tail:
        return None
    return out + [tail]


def ensure_or_group_parens(sql: str) -> tuple[str, bool]:
    """최상위에 괄호 없이 섞인 `A AND B OR C AND D` 를 `A AND (B OR C) AND D` 로 재괄호화. (SQL, 보정했는지)

    🔴 10R gold N1 — 8R 이 넣은 괄호 검사(`validate_sql`)가 **우리가 근거문서에 실은 규칙 원문**을 기각했다:
       `ontology/enums/public_funds.yaml:949 자산군_주식형` 이 바깥 괄호 없이 `A OR (B)` 로 정의돼 있고, 플래너가
       그대로 싣고 HCX 가 그대로 베껴 1·2차 모두 기각 → FND-009 무응답(회귀) · OFFICIAL-004 1차 소진.
       자연어 피드백으로는 못 고친다(모델이 베낀 원본이 우리 문장이다). yaml 을 고치지 않고 **런타임이 접는다.**
    규칙: OR 를 AND 보다 강하게 묶는다 = 가드 사유 문구("OR 가지 전체를 괄호로 감싸라: (A OR B) AND 필터")의 기계 구현.
    괄호가 이미 있어 최상위에 OR 와 AND 가 섞이지 않았으면 불개입 — 의도적인 `(A AND B) OR (C AND D)` 는 안 뒤집는다.
    체인 맨 앞에서 돈다: 뒤의 모든 가드가 `split_conjuncts`(최상위 AND 분해)를 전제하므로 여기서 접어야 안전하다.
    """
    out, changed = [], False
    last = 0
    for m_w in _WHERE_SEG.finditer(sql):
        parts = _split_top_level(m_w.group(1))
        if not parts or "OR" not in parts[1::2] or "AND" not in parts[1::2]:
            continue
        # OR 로 이어진 최대 연속 구간을 괄호로 묶는다 → 최상위에는 AND 만 남는다
        groups, cur = [], [parts[0]]
        for op, operand in zip(parts[1::2], parts[2::2]):
            if op == "OR":
                cur.append(operand)
            else:
                groups.append(cur)
                cur = [operand]
        groups.append(cur)
        body = " AND ".join(g[0] if len(g) == 1 else "(" + " OR ".join(g) + ")" for g in groups)
        out.append(sql[last:m_w.start(1)] + " " + body + " ")
        last = m_w.end(1)
        changed = True
    return ("".join(out) + sql[last:], True) if changed else (sql, False)


def _sql_precheck(sql: str, ctx, tables: list[str], cross: bool) -> str | None:
    """실행 전 기각 사유 — 문법·테이블·컬럼·모호 컬럼·라우팅 범위·코드 리터럴. None 이면 통과. 1차·재생성 공통(중복 코드 0).

    KG 1R R3 ④ 라우팅 대상 밖 테이블(KG-028: 펀드 질의에 domestic_etfs JOIN) — 교차 질의가 아니고 라우터가 정한 테이블이 있으면
    그 밖의 마스터 사용은 기각한다(사후 보정이 FROM 으로 tables 를 확정한 뒤라 단일 테이블만 남는다).
    """
    # 🔴 10R gold N2 — **위반을 전부 모아 한 번에 돌려준다.** 첫 사유에서 return 하면 재생성 1회가 사유 하나만
    #    고치고 다음 가드에 다시 걸려 예산이 소진된다(OFFICIAL-004 실측: 1차 괄호 가드 · 2차 테이블 참조로
    #    서로 다른 두 가드가 재생성 1회를 나눠 쓰고 무응답). 가드를 늘릴수록 이 곱셈이 나빠진다.
    errs = [e for e in (validate_sql(sql), forbidden_column_use(sql), forbidden_literal_use(sql)) if e]
    agg = where_window_or_aggregate(sql)
    if agg:
        errs.append(f"WHERE 절에 윈도우·집계 함수 사용({agg}) — 실행 시 misuse 오류. 집계 조건은 HAVING 으로, "
                    "순위·윈도우 조건은 서브쿼리(WITH … AS (SELECT …, RANK() OVER(…) rk …) SELECT … WHERE rk <= n) 로 옮긴다")
    err = None
    if tables:
        # 6R F3 — 테이블 범위를 컬럼 검사 **앞**에 둔다: 잘못된 테이블의 컬럼을 '없는 컬럼' 이라 하면 재생성이 컬럼만 고친다.
        # KG 2R N1 — 교차 판정이어도 허용 집합은 **라우터가 정한 마스터 + 그 짝 ext_***. `not cross` 로 검사를 끄면 펀드 질의에
        #    domestic_etfs + ext_etf_holdings 가 통과해 엉뚱한 ETF 종목이 답으로 나간다(KG-028 'IBK K-AI반도체코어테크' 57.12% 환각).
        #    다른 마스터는 질문에 그 상품군 명사가 있을 때 라우터가 이미 tables 에 넣었다.
        allowed = set(tables) | {e for e, m in _EXT_PAIR.items() if m in tables}
        outside = sorted(set(guard.sql_tables(sql)) - allowed)
        if outside:
            err = (f"라우팅 대상({', '.join(tables)} + 짝 ext_*) 밖 테이블 사용: {', '.join(outside)} — "
                   "질문의 상품군 테이블(과 그 외부 수집 테이블)로만 쓴다")
    if err:
        # 6R F3 — 테이블 범위가 틀렸으면 그 테이블의 컬럼 검사는 잡음이다(재생성이 컬럼만 고친다). 여기서 끊는다.
        errs.append(err)
    else:
        # ①-b 컬럼 환각(remaining_days 류) — 실행 전 검출해 재생성 기회를 준다 (2026-08-31 paired v2: 실행 실패 8/80)
        unk = guard.unknown_columns(sql, ctx)
        if unk:
            errs.append("스키마에 없는 컬럼: " + _name_owners(unk[:5], ctx))
        # 🔴 JOIN 의 모호 컬럼 — 실행 오류는 재생성 경로가 없어 그대로 "조회 중 오류" 가 나간다
        amb = guard.ambiguous_columns(sql, ctx)
        if amb:
            errs.append("여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): "
                        + ", ".join(amb[:5]) + " — 테이블 별칭을 붙이고 p.itm_no 처럼 모두 한정한다")
        bad = guard.check_code_literals(sql, ctx)
        if bad:
            errs.append("코드 컬럼 리터럴 검증 실패: " + "; ".join(bad[:3])
                        + " — 코드는 'KG 개체 매핑' 의 값만 쓴다. 매핑이 없으면 지어내지 말고 REFUSE: 로 답한다")
    # 재생성 프롬프트가 희석되지 않게 3사유까지만. 번호를 붙여 "전부 고쳐라" 를 명시한다.
    if not errs:
        return None
    return errs[0] if len(errs) == 1 else \
        "아래 " + str(min(len(errs), 3)) + "가지를 **한 번에** 고친다 — " + \
        " / ".join(f"({i}) {e}" for i, e in enumerate(errs[:3], 1))


# ── 기각 사유 → 사용자 문장 (2026-09-03 17R) ────────────────────────────────
# 재생성 뒤에도 SQL 이 기각되면 종전엔 "질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다." 만
# 나갔다 — 사용자는 **무엇이 왜 안 되는지 모른다.** 17R 실측에서 이 문구가 5건 → 7건으로 늘었고,
# Z10·AA6 은 15R 의 "값이 데이터에 없어"(이유 있음) 에서 이 문구(이유 없음)로 퇴행했다.
#
# 규칙 셋:
#   ① 문장 **끝**의 거절 어휘는 건드리지 않는다 — 환각 방지 판정이 이 어휘를 본다.
#   ② 컬럼명·테이블명 같은 **내부 식별자를 사용자 문장에 넣지 않는다**. 사유는 think_trace 에 이미 있다.
#   ③ 문항별 분기 금지 — 기각 부류 단위 매핑 하나다.
_REFUSAL_TAIL = "답변을 제공하지 못했습니다."
_REFUSAL_REASONS: tuple[tuple[str, str], ...] = (
    # (err 안에서 찾을 표지, 사용자에게 할 말) — 위에서부터 먼저 맞는 것 하나
    ("스키마에 없는 컬럼", "질문하신 항목이 이 상품 유형의 데이터에 없어"),
    ("라우팅 대상", "질문의 상품군 밖 자료를 함께 봐야 하는 조건이라"),
    ("허용 테이블 밖", "질문의 상품군 밖 자료를 함께 봐야 하는 조건이라"),
    ("여러 테이블에 있는 컬럼", "같은 이름의 항목이 여러 자료에 있어 어느 쪽인지 정하지 못해"),
    ("코드 컬럼 리터럴", "질문에 나온 대상을 데이터의 코드로 확정하지 못해"),
    ("WHERE 절에 윈도우", "요청하신 계산이 조회 조건으로는 표현되지 않아"),
    ("SQLite 문법이 아니다", "조회문을 규격에 맞게 만들지 못해"),
    ("다중 문장", "조회문을 규격에 맞게 만들지 못해"),
    ("SELECT 만 허용", "조회문을 규격에 맞게 만들지 못해"),
    ("금지 키워드", "조회문을 규격에 맞게 만들지 못해"),
    ("LIMIT 누락", "조회문을 규격에 맞게 만들지 못해"),
)


def refusal_reason_text(err: str | None) -> str:
    """기각 사유(내부 문자열) → 사용자 문장. 부류를 못 가리면 종전 문구 그대로."""
    for needle, human in _REFUSAL_REASONS:
        if err and needle in err:
            return f"{human} {_REFUSAL_TAIL}"
    return f"질의를 안전하게 실행할 수 없어 {_REFUSAL_TAIL}"


_TOP_N = re.compile(r"(\bselect\s+)(?:distinct\s+)?top\s+(\d+)\s+", re.I)


def rewrite_dialect_top(sql: str) -> tuple[str, bool]:
    """`SELECT TOP n` (T-SQL 방언)을 `SELECT … LIMIT n` 으로 기계 치환. (SQL, 치환했는지)

    🔴 10R 재검 ③-7(부류 U′) — U9 의 SQL 은 토큰 하나만 빼면 완전히 정상이고 `LIMIT 30` 도 이미 붙어 있었는데,
       가드가 사유 문장만 돌려주자 재생성이 같은 토큰을 또 냈다. 문법 기각은 **기계로 고칠 수 있으면 보정한다**
       (`ensure_limit` 원칙). 오거절은 감점 축이 가장 크다. TOP n 은 명시 상한이므로 기존 LIMIT 보다 우선한다.
    """
    m = _TOP_N.search(sql)
    if not m:
        return sql, False
    n = m.group(2)
    out = sql[:m.start()] + m.group(1) + sql[m.end():]
    out = re.sub(r"\blimit\s+\d+(\s+offset\s+\d+)?\s*$", "", out.strip(), flags=re.I).rstrip()
    return f"{out} LIMIT {n}", True


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


_BASIS_DT_COL = re.compile(r"\b(?:\w+\.)?\w*(?:_bas_dt|_base_dt)\b", re.I)


def strip_future_basis_date(sql: str) -> tuple[str, str | None]:
    """기준일 컬럼(`*_bas_dt`·`*_base_dt`)을 **기준일 이후 날짜**와 비교하는 절을 제거. (SQL, 제거한 절)

    🔴 10R gold N8 — 기준일 가드가 **질문 토큰만** 보고 SQL 리터럴은 안 봤다. FND-R02 실측:
       HCX 가 `fd_daily_bas_dt BETWEEN 20260915 AND 20260922` 로 기준일(2026-08-24) 이후 날짜를 지어내
       0행을 만들고, 그 0행을 "조건 교집합이 0" 이라는 **거짓 사유**로 포장해 거절했다. 값을 지어내진
       않았지만 사유를 지어낸 것이라 환각 방지 축의 다른 얼굴이다.
    만기(`mat_dt`)는 미래가 정상이므로 대상이 아니다 — 그쪽은 `ensure_maturity_lower_bound` 담당(중복 0).
    """
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        return sql, None
    fold = "\x01"
    body = re.sub(r"(BETWEEN\s+\S+)\s+AND\s+(\S+)", rf"\1{fold}\2", m_w.group(1), flags=re.I)
    kept, dropped = [], []
    for c in guard.split_conjuncts(body):
        lits = [int(x) for x in re.findall(r"\b(\d{8})(?:\.0)?\b", c)]
        if _BASIS_DT_COL.search(c) and lits and max(lits) > CUTOFF_INT:
            dropped.append(c.replace(fold, " AND ").strip())
            continue
        kept.append(c.replace(fold, " AND ").strip())
    if not dropped:
        return sql, None
    where = (" WHERE " + " AND ".join(kept) + " ") if kept else " "
    return sql[:m_w.start()] + where + sql[m_w.end():].lstrip(), " · ".join(dropped)


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
    if not m or int(m.group(1)) <= BUYABLE_INT:
        return sql, False
    s, e = m.span()
    return f"{sql[:s]}(mat_dt >= {BUYABLE_INT} AND {sql[s:e]}){sql[e:]}", True


# 옛 기준일(as-of 8/22 및 8/20~8/23) 하한 리터럴 — 초과(>)든 이상(>=)이든 구매가능 판정일 8/24 이상으로 교정한다.
_CUTOFF_STRICT = re.compile(r"\bmat_dt\s*>=?\s*2026082[0-3](?:\.0)?\b|\bmat_dt\s*>\s*20260824(?:\.0)?\b")


def ensure_cutoff_inclusive(sql: str) -> tuple[str, bool]:
    """기준일 하한의 초과(>)를 이상(>=)으로 교정. (보정된 SQL, 보정했는지)

    2026-09-01 서버 실측: '만기가 가장 짧은 채권 뭐야' 가 mat_dt > 20260822 로 나가
    기준일 당일 만기 7종목(잔존 1일 동률 — 진짜 최단)을 건너뛰고 8/23 채권(잔존 2일)을 답함.
    🔄 2026-09-02 리드 결정 — 구매가능 모수는 mat_dt >= 20260824(BUYABLE_INT) 다. as-of(8/22)·8/20~8/23 리터럴의 >·>= 하한을
    전부 8/24 이상으로 교정한다(HCX 는 yaml 옛 표기나 as-of 를 하한으로 쓰기 쉽다). 그 외 날짜의 부등호는 사용자 조건일 수 있어 불개입."""
    new = _CUTOFF_STRICT.sub(f"mat_dt >= {BUYABLE_INT}", sql)
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
    if not uppers:
        # BETWEEN 꼴 — 양 끝 연도가 모두 질문 연도와 다르면 그 해 전체 창으로 (2026-09-03 #51: '내년' 이
        #    BETWEEN 20280824 AND 20290824 로 나갔는데 이 가드가 `<=` 상한만 봐서 불개입이었다)
        bts = list(_MAT_BETWEEN.finditer(sql))
        if len(bts) == 1 and bts[0].group(1)[:4] != years[0] and bts[0].group(2)[:4] != years[0]:
            s, e = bts[0].span()
            return sql[:s] + f"mat_dt BETWEEN {years[0]}0101 AND {years[0]}1231" + sql[e:], True
        return sql, False
    if len(uppers) != 1:
        return sql, False
    lit = uppers[0].group(1)
    if lit[:4] == years[0]:
        return sql, False
    s, e = uppers[0].span(1)
    return sql[:s] + years[0] + lit[4:] + sql[e:], True


_MAT_BETWEEN = re.compile(r"\bmat_dt\s+BETWEEN\s+(\d{8})(?:\.0)?\s+AND\s+(\d{8})(?:\.0)?", re.I)
_MAT_PRED = re.compile(r"\bmat_dt\b\s*(?:BETWEEN\s+\d{8}(?:\.0)?\s+AND\s+\d{8}(?:\.0)?|(?:>=|<=|<>|!=|=|<|>)\s*\d{8}(?:\.0)?)", re.I)
_MAT_OR_REMAIN = re.compile(r"\b(?:mat_dt|remaining_days)\b", re.I)
# 구매가능 모수로 우리가 주입한 하한 — 사용자가 물은 만기 조건이 아니다. 창 발동 판정에서 뺀다(2026-09-05 #66)
_BUYABLE_FLOOR = re.compile(rf"^\s*mat_dt\s*>=?\s*{BUYABLE_INT}(?:\.0)?\s*$", re.I)
# 발행 시점 질의 — '만기' 축으로 갈아끼우면 안 되는 문형 (isu_dt 가 따로 있다)
_ISSUANCE_Q = re.compile(r"발행|신규|새로\s*(?:나온|나와|발행|출시)|출시")
_MATURITY_Q = re.compile(r"만기|상환|잔존")
_WHERE_BODY = re.compile(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", re.I | re.S)
_SQL_NOW = re.compile(r"'now'|\bCURRENT_DATE\b|\bCURRENT_TIMESTAMP\b|\bCURRENT_TIME\b", re.I)


def has_maturity_predicate(sql: str) -> bool:
    """SQL 에 mat_dt 날짜 조건(BETWEEN / 부등호 / 등호 + YYYYMMDD 리터럴)이 있는가 — 시점·전망 질의와 만기 질의를 가르는 기준."""
    return bool(_MAT_PRED.search(sql))


def pin_sql_now(sql: str) -> tuple[str, bool]:
    """SQLite 의 '지금'(`'now'`·CURRENT_DATE …)을 질문 시점 2026-08-24 로 고정. (보정된 SQL, 보정했는지)

    서버 실제 시각은 심사일이다 — HCX 가 `date('now')` 를 한 번이라도 쓰면 기준일이 심사 당일로 밀린다(프로브 전 json 에서
    사용 0건이지만 가드도 0건이었다 — 2026-09-03 #51 재점검). 'now' 만 바꾸므로 `strftime('%Y%m%d','now','+1 year')` 의 수식어는 산다.
    """
    def _sub(m: re.Match) -> str:
        t = m.group(0).upper()
        if t == "'NOW'" or t == "CURRENT_DATE":
            return f"'{gate.BUYABLE_CUTOFF}'"
        return f"'{gate.BUYABLE_CUTOFF} 00:00:00'"
    new = _SQL_NOW.sub(_sub, sql)
    return new, new != sql


def enforce_relative_window(sql: str, question: str, windows: list[tuple[str, int, int]]) -> tuple[str, str | None]:
    """질문의 상대 시점('내년'·'올해'·'3년 안에' …)이 확정한 만기 창을 SQL 에 강제한다. (보정된 SQL, 적용 설명 | None)

    🔴 2026-09-03 서버 실측(#51): '내년에 만기가 되는 회사채' 를 HCX 가 `mat_dt BETWEEN 20280824 AND 20290824` 로 냈다.
       질문 시점(8/24) 도, '내년' 의 뜻도 프롬프트에 없었다. 창은 결정층이 정한다(gate.resolve_relative_window) —
       여기서는 mat_dt·remaining_days 를 쓴 최상위 조건을 전부 걷어내고 확정 창 하나로 바꾼다.
    remaining_days 조건은 제거한다 — 8/21(info_base_dt) 기준이라 8/24 를 오늘로 두면 3일 어긋난다.
    발동(전부): ① domestic_bonds ② 확정 창이 정확히 하나 ③ 만기 경과 질의 아님 ④ 발행 시점 질의가 아님 ⑤ SQL 에
    (구매가능 하한을 뺀) mat_dt/remaining_days 조건이 있거나 질문이 '만기·상환·잔존' 을 말함(그렇지 않은
    '오늘 수익률 좋은 채권' 의 '오늘' 은 창이 아니다) ⑥ 걷어낼 조건이 다른 컬럼과 섞여 있지 않음.

    🔴 2026-09-05 서버 실측(#66) — "최근 6개월 안에 새로 발행된 회사채 중 표면금리 높은 5개" 가 답한 5종목의
       실제 발행일은 2023-09-15 ~ 2025-09-24 로 **전부 6개월 밖**이었다. 발행 축(isu_dt, 고유값 2,486)이 데이터에
       있는데도 창이 mat_dt 로 갔다 — 없는 축을 실재 컬럼으로 갈아끼운 #65 와 같은 부류이고, 이번엔 갈아끼운 것이
       HCX 가 아니라 이 가드다. 그래서 두 자리를 막는다:
         ④ 질문이 '발행·신규·새로 나온' 을 말하고 '만기·상환' 을 말하지 않으면 만기 창을 강제하지 않는다
            (HCX 가 `isu_dt BETWEEN …` 로 옳게 써도 종전엔 mat_dt 창이 덧붙어 '발행 AND 만기' 로 오염됐다).
         ⑤ `mat_dt >= 20260824` 는 우리가 주입한 구매가능 모수지 사용자가 물은 만기 조건이 아니다 — 이것 때문에
            만기를 한 번도 말하지 않은 "오늘 수익률 높은 채권" 이 `mat_dt = 20260824`(만기가 오늘) 로 좁혀졌다.
    """
    if "domestic_bonds" not in sql or not windows or _PAST_MATURITY_Q.search(question):
        return sql, None
    if len({(lo, hi) for _, lo, hi in windows}) != 1:
        return sql, None
    if _ISSUANCE_Q.search(question) and not _MATURITY_Q.search(question):
        return sql, None                                        # ④ 발행 시점 질의 — 만기 축으로 갈아끼우지 않는다
    label, lo, hi = windows[0]
    want = f"mat_dt = {lo}" if lo == hi else f"mat_dt BETWEEN {lo} AND {hi}"
    m_w = _WHERE_BODY.search(sql)
    body = m_w.group(1) if m_w else ""
    fold = "\x01"
    folded = re.sub(r"(BETWEEN\s+\S+)\s+AND\s+(\S+)", rf"\1{fold}\2", body, flags=re.I)
    conjuncts = [c.replace(fold, " AND ").strip() for c in guard.split_conjuncts(folded)]
    # ⑤ 구매가능 하한(mat_dt >= 판정일)만 있는 것은 '만기 조건이 있다' 로 세지 않는다
    has_pred = any(_MAT_OR_REMAIN.search(c) and not _BUYABLE_FLOOR.match(c) for c in conjuncts)
    if not has_pred and not _MATURITY_Q.search(question):
        return sql, None
    kept: list[str] = []
    for c in conjuncts:
        if not c:
            continue
        if _MAT_OR_REMAIN.search(c):
            others = {w.lower() for w in re.findall(r"[A-Za-z_]\w*", _SQL_LITERAL.sub("''", c))} - _SQL_WORDS - {"mat_dt", "remaining_days", "domestic_bonds", "between", "cast", "as", "integer", "real"}
            if others:
                return sql, None                                    # 다른 컬럼과 섞인 절 — 의도 불명, 불개입
            continue
        kept.append(c)
    if has_pred and re.sub(r"\s+", " ", body).strip() == re.sub(r"\s+", " ", " AND ".join(kept + [want])).strip():
        return sql, None
    new_where = " AND ".join(kept + [want])
    if m_w:
        new = sql[:m_w.start()] + "WHERE " + new_where + " " + sql[m_w.end():].lstrip()
    else:
        tail = re.search(r"\b(?:group\s+by|having|order\s+by|limit)\b", sql, re.I)
        pos = tail.start() if tail else len(sql.rstrip().rstrip(";"))
        new = sql[:pos].rstrip() + " WHERE " + new_where + " " + sql[pos:].lstrip()
    return new, f"'{label}' → {want} (질문 시점 {gate.BUYABLE_CUTOFF} 고정 · 확정표 gate._RELATIVE_WINDOW)"


def raise_maturity_floor(sql: str, question: str) -> tuple[str, bool]:
    """mat_dt 하한이 구매가능 판정일(20260824) 보다 앞이면 판정일로 올린다. (보정된 SQL, 보정했는지)

    '올해 만기'·'2026년에 만기' 를 HCX 가 `BETWEEN 20260101 AND 20261231` 로 쓰면 만기 경과 49행이 섞인다 —
    ensure_maturity_lower_bound 는 BETWEEN 불개입, ensure_cutoff_inclusive 는 8/20~8/23 리터럴만 봤다(2026-09-03 #51 재점검).
    만기 경과 질의(_PAST_MATURITY_Q)와 상한까지 과거인 창(전부 경과분을 묻는 것)은 건드리지 않는다.
    """
    if _PAST_MATURITY_Q.search(question):
        return sql, False
    changed = False

    def _lower(m: re.Match) -> str:
        nonlocal changed
        if int(m.group(1)) < BUYABLE_INT:
            changed = True
            return f"mat_dt >= {BUYABLE_INT}"
        return m.group(0)

    def _between(m: re.Match) -> str:
        nonlocal changed
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo < BUYABLE_INT <= hi:
            changed = True
            return f"mat_dt BETWEEN {BUYABLE_INT} AND {m.group(2)}"
        return m.group(0)

    new = re.sub(r"\bmat_dt\s*>=?\s*(\d{8})(?:\.0)?\b", _lower, sql, flags=re.I)
    new = _MAT_BETWEEN.sub(_between, new)
    return new, changed


def _grade_scale() -> list[str]:
    """신용등급 서열(우량→하위) — 선언에서 온다. loader.grade_scale() = 표준표 rank 순 ∩ 값 사전 실재.

    2026-09-04 — 종전엔 2차 데이터 실재 15종을 코드 상수로 적어 두었다(§B.3 한계 2). 그러면 표준표에
    있는 등급(CCC·D…)이 새 데이터에 들어와도 서열이 못 늘고, 반대로 값 사전과 이원화된다.
    순서는 코드북, 실재는 값 사전 — 코드는 둘을 합칠 뿐이다. 원천이 없으면 종전 목록으로 물러선다."""
    try:
        from .loader import grade_scale
        scale = list(grade_scale())
    except Exception:                                        # noqa: BLE001 — 원천 파손 시에도 가드는 살아 있어야 한다
        scale = []
    return scale or list(_GRADE_SCALE_FALLBACK)


_GRADE_SCALE_FALLBACK = ("AAA", "AA+", "AA0", "AA-", "A+", "A0", "A-",
                         "BBB+", "BBB0", "BBB-", "BB0", "BB-", "B+", "B-", "C0")
_Q_GRADE_CMP = re.compile(r"\b(AAA|AA|BBB|BB|A|B|C)\s*([+\-0])?\s*(?:등급|급)?\s*(이상|이하)", re.I)
_SQL_GRADE_CMP = re.compile(r"(?:TRIM\(\s*)?crd_grd\s*\)?\s*(=|>=|<=|>|<)\s*'([^']*)'", re.I)
_SQL_GRADE_IN = re.compile(r"crd_grd\s*\)?\s*(?:NOT\s+)?IN\s*\(", re.I)
_SQL_GRADE_IN_FULL = re.compile(r"(?:TRIM\(\s*)?crd_grd\s*\)?\s*IN\s*\(([^)]*)\)", re.I)   # NOT IN 은 구조상 매칭 안 됨


class _OuterFundTable:
    """`FROM public_funds` 를 **바깥 질의에서만** 인정한다 — 부질의 안의 것은 세지 않는다.

    2026-09-04 KG-006 실측("미래에셋코어테크 펀드의 운용사와 수탁사는 어디야?") — HCX 가

        SELECT … FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE …)

    를 냈는데, 종전 전제가 "from public_funds" 를 **아무 데서나 찾는 검색**이라 부질의 안의 것을 보고
    개별 조회 묶기 가드가 발동했다. 가드는 바깥 SELECT 에 `sale_yn`·`rptt_ksd_itm_no`·
    `or_co_xtn_itt_cd`·`mtco_itm_no` 를 주입했고, 그 컬럼들은 `ext_fund_page` 에 없어
    **가드가 만든 SQL 이 기각당했다**(재생성도 같은 실패 → 오거절).

    가드들은 예외 없이 바깥 SELECT/WHERE 를 고치므로, 판정도 바깥 FROM 이어야 한다.
    """

    _FIRST_FROM = re.compile(r"\bfrom\s+([A-Za-z_]\w*)", re.I)

    def search(self, sql: str):
        m = self._FIRST_FROM.search(sql or "")
        return m if m and m.group(1).lower() == "public_funds" else None


_FUND_TBL = _OuterFundTable()
_SQL_ANCHOR = re.compile(r"\bgroup\s+by\b|\border\s+by\b", re.I)
# 질문이 모수 밖을 명시하면 주입하지 않는다 — '사모 펀드 중 큰 것' 에 공모 필터를 박으면 정반대 오답
# 🔴 8R 부류 F (KG 1R R6) — 목록에서 '역외' 를 뺐다. 역외는 **운용사 코드 집합**을 넓히는 말이지 판매상태·공모여부를
#   넓히는 말이 아니다 — 7R KG-031 실측: '역외까지 포함' 이라는 낱말 하나로 `sale_yn` 이 통째로 빠져 판매완료가
#   섞였다(167/350, gold 153/293). 역외 코드 집합은 Ground 와 `_offshore_sibling_note` 가 따로 다룬다.
_POP_WIDEN = ("사모", "판매완료", "판매 완료", "판매중단", "판매 중단", "전체 펀드", "모든 펀드", "판매종료")


_BASE_STRICT = {"sale_yn": "sale_yn = '판매중'", "prvo_pbff_desc": "prvo_pbff_desc = '공모'"}
_SQL_WORDS = {"or", "and", "is", "not", "null", "in", "trim", "coalesce", "like", "upper", "lower"}


def _strictify_base_population(sql: str, strict_map: dict | None = None, tbl: str = "public_funds") -> tuple[str, bool]:
    """모수 컬럼 **만** 든 최상위 AND 절이 확정식이 아니면 확정식으로 교체. (SQL, 교체했는지)
    한정자(p.·public_funds.)는 유지한다. 서브쿼리·UNION 은 첫 WHERE 만 본다(보수적).

    🔴 10R 부류 Z — 이 "있으면 확인하고 아니면 교체" 형태가 확정식 가드의 **정본 형태**다. `not <절이 있는가>`
       술어는 HCX 가 그 절을 틀리게 쓰면 가드가 자기를 끈다(9R U2·Y7 회귀). ETF 모수도 같은 기계를 쓴다.
    """
    strict_map = strict_map or _BASE_STRICT
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        return sql, False
    conjs = guard.split_conjuncts(m_w.group(1))
    out, changed = [], False
    for c in conjs:
        new_c = c
        for col, strict in strict_map.items():
            if not re.search(rf"\b{col}\b", c, re.I):
                continue
            masked = _SQL_LITERAL.sub("''", c)
            idents = {w.lower() for w in re.findall(r"[A-Za-z_]\w*", masked)} - _SQL_WORDS - {col}
            idents = {w for w in idents if not re.fullmatch(rf"[a-z]\w{{0,3}}|{tbl}", w)}   # 별칭·테이블 한정자
            if idents:
                break                                            # 다른 컬럼과 섞인 절 — 의도 불명, 불개입
            m_val = re.search(r"=\s*'?([^']+?)'?\s*$", strict)
            strict_val = m_val.group(1) if m_val else ""
            if strict_val not in c and not re.search(r"IS\s+NULL|<>|!=|\bNOT\b", c, re.I):
                break                                            # 다른 단일 값(= '판매완료' · = '사모')은 의도적 별개 모수 — 존중
            m_q = re.search(rf"\b(\w+\.)?{col}\b", c, re.I)
            qual = m_q.group(1) or ""
            if re.fullmatch(rf"\(?\s*(?:{re.escape(qual)})?{col}\s*=\s*'?{re.escape(strict_val)}'?\s*\)?", c.strip(), re.I):
                break                                            # 이미 확정식
            new_c = qual + strict
            changed = True
            break
        out.append(new_c.strip())
    if not changed:
        return sql, False
    return sql[:m_w.start()] + " WHERE " + " AND ".join(out) + " " + sql[m_w.end():].lstrip(), True


_ESTB_Q = re.compile(r"설정(?:된|일|됐|되었|되는|한)|운용한\s*지|만들어진|출시(?:된|일)")
_ESTB_DATE_CONJ = re.compile(r"\b(?:\w+\.)?(?:estb_dt|fd_daily_bas_dt)\b", re.I)
_YEAR_Q = re.compile(r"((?:19|20)\d{2})\s*년")


def ensure_fund_estb_year(sql: str, question: str) -> tuple[str, bool]:
    """KG 4R G2 — '「YYYY년」에 설정된' 질의의 날짜 절은 컬럼과 표현식을 기계가 확정한다. (SQL, 교체했는지)

    설정일 정본은 `ext_fund_page.estb_dt`(TEXT 'YYYYMMDD', 10,565행 전건 수록)뿐이다. public_funds 의
    `fd_daily_bas_dt`(기준일)·`mat_dt`(만기)는 설정일이 아니다. 6R 실측 — 같은 문형 세 문항이 SQL 의 날짜 절만
    다르고 답이 갈렸다: Z22(2024년) `estb_dt` 범위 → 107/287 정답 · KG-035(2026년) `fd_daily_bas_dt BETWEEN
    20260000 AND 20269999` → 2,594 오답 · X19(2025년) `estb_dt <= 20250930` → 2,853 오답.
    조치: 설정 어휘 + 연도가 있으면 날짜 절을 전부 걷어내고 `estb_dt >= 'YYYY0101' AND estb_dt < '(YYYY+1)0101'`
    로 확정한다. 비교 리터럴은 **문자열** — estb_dt 는 TEXT 컬럼이다. LEFT JOIN 은 ensure_ext_join 이 받는다.
    """
    if not _FUND_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I):
        return sql, False
    m_y = _YEAR_Q.search(question)
    if not (_ESTB_Q.search(question) and m_y):
        return sql, False
    y = int(m_y.group(1))
    canon = f"estb_dt >= '{y}0101' AND estb_dt < '{y + 1}0101'"
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        anchor = _SQL_ANCHOR.search(sql) or re.search(r"\blimit\b", sql, re.I)
        return (f"{sql[:anchor.start()]}WHERE {canon} {sql[anchor.start():]}", True) if anchor else (sql, False)
    # `col BETWEEN a AND b` 는 최상위 AND 로 갈리면 `b` 만 남는 껍데기 절이 된다(KG-035 `AND 20269999`) —
    #    쪼개기 전에 통째로 한 토큰으로 접어 둔다.
    where_txt = re.sub(r"(?:\w+\.)?(?:estb_dt|fd_daily_bas_dt)\s+(?:NOT\s+)?BETWEEN\s+\S+\s+AND\s+\S+",
                       "estb_dt IS NOT NULL", m_w.group(1), flags=re.I)
    # 🔴 8R 부류 B — **주입은 교체다**: 이 축(설정일)의 다른 술어는 전부 걷어낸다. 종전엔 `canon in sql` 조기 반환이
    #    있어 체인 뒤에서 되살아난 잔여 술어를 못 걷어냈다 — 7R X19 실측: HCX 의 `fd_estb_dt <= 20250930` 이
    #    여기선 컬럼명이 달라 안 걸렸고, 그 뒤 `ensure_ext_join` 이 `estb_dt` 로 이름을 바꿔 놓아 10~12월이 잘렸다
    #    (82/224, gold 107/305). 이제 멱등 재작성이라 체인 끝에서 한 번 더 태우면 잔여가 사라진다.
    keep = [c for c in _flat_conjuncts(where_txt) if not _ESTB_DATE_CONJ.search(c)]
    # 멱등하려면 재작성이 공백까지 같은 문자열을 내야 한다 — 앞뒤 공백을 정규화한다
    new = sql[:m_w.start()].rstrip() + " WHERE " + " AND ".join([canon] + keep) + " " + sql[m_w.end():].lstrip()
    return (new, True) if new != sql else (sql, False)


_BASE_POP_CASE = re.compile(r"CASE\s+WHEN\b(?:(?!\bEND\b).)*?\bEND\b", re.I | re.S)
_BASE_POP_SALE = re.compile(r"\bsale_yn\s*=\s*'판매중'")
_BASE_POP_PUBLIC = re.compile(r"\bprvo_pbff_desc\s*=\s*'공모'")


def ensure_fund_base_population(sql: str, question: str, post: bool = False) -> tuple[str, bool]:
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

    🔴 2026-09-03 — enforce 슬롯(`public_funds.기본모수.enforce`, mark BASEPOP)이 먼저 같은 일을 한다.
       슬롯이 처리했으면 여기서는 **침묵**한다(절차 §2-4). 가드 삭제는 두 라운드 뒤(§5) —
       슬롯의 `when` 이 이 가드보다 좁아(모수 절 tightening 미포함) 아직 여기가 받는 문항이 있다.
       섀도 실측: 84문항 중 '가드만 발동' 7건.
    """
    if "M:BASEPOP" in sql:
        return sql, False
    if not _FUND_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I):
        return sql, False
    if re.search(r"\bjoin\b", sql, re.I) and re.search(
            r"\b(?:domestic_bonds|domestic_etfs|overseas_etfs)\b", sql, re.I):
        return sql, False
    # 🔴 랭킹(ORDER BY)뿐 아니라 **집계(COUNT/SUM/AVG)** 도 기본모수 대상이다 — 기본모수 규칙이
    #    "집계·Top-N" 을 함께 말한다. 2026-08-31 밤 FND-030 실측: COUNT 질의에 sale_yn 이 빠졌다.
    # 🔴 7R G1/F6′ — `post=True`(가드 체인 끝 재호출)는 이 **모양 조건을 보지 않는다.** 6R KG-018·W2·Y11 실측:
    #    HCX 원 SQL 에 정렬·집계가 없어 여기서 건너뛰었는데, 그 **뒤에** 묶기·목록 가드가 GROUP BY·ORDER BY·COUNT 를
    #    붙였다 — 기본모수 가드는 이미 지나간 뒤였다. 재작성된 모양으로 한 번 더 보는 것이 처방이고, 멱등이다.
    if not post and not re.search(r"\border\s+by\b", sql, re.I) and not re.search(r"\b(?:count|sum|avg)\s*\(", sql, re.I):
        return sql, False
    if any(t in question for t in _POP_WIDEN):
        return sql, False
    # 🔴 7R F6′ — 개별 조회(이름 LIKE·펀드키 핀)의 재작성 SQL 도 사후조건에서 기본모수를 받는다.
    #    6R W2 는 사모 3펀드가, Y11 은 판매완료가 개별 조회 결과에 섞였다. 처음엔 동결선 이탈(W5·X18 의 WHERE 텍스트)
    #    때문에 제외했으나, 동결선 대조 결과 **rows·assembler·answer_head·route·nodes 전부 불변이고 where 문자열만
    #    바뀐다** — 동결선은 값 회귀를 잡으려고 둔 것이지 SQL 문자열을 얼리려는 게 아니다. 스냅샷을 갱신하고 규칙을 살린다.
    # 🔴 질문이 '공모' 를 명시했는데 SQL 이 사모까지 포함하면 좁힌다 — 2026-09-01 FND-038 실측:
    #    "공모펀드는 유형별로 몇 개씩?" 에 prvo_pbff_desc IN ('공모','사모') 가 나가 사모 1,993개가
    #    답에 실렸다. 위 _POP_WIDEN 이 이미 '사모' 질문을 걸러내므로 여기 오는 것은 공모 질의뿐이다.
    # 🔴 **빠진 쪽만** 주입한다 — 예전엔 둘 중 하나라도 있으면 통째로 건너뛰어서, 한쪽만 쓴 SQL 이
    #    반쪽 모수로 나갔다(2026-08-31 밤 FND-030 실측: prvo_pbff_desc 만 있고 sale_yn 누락).
    #    모수를 넓히는 질의는 위 _POP_WIDEN 이 이미 막으므로 모델 의도를 해치지 않는다.
    # 6R F6 — 기본모수 판정은 **단독 절**(`sale_yn = '판매중'` 하나짜리 최상위 AND 절)로 한다. 컬럼 언급만으로 존중하면
    #    `(sale_yn = '판매중' OR sale_yn IS NULL)`·`sale_yn IN ('판매중','판매완료')`·`sale_yn <> '판매완료'` 가 모수를 넓혀 나갔다
    #    (5R X10·KG-005·KG-035). 그 컬럼**만** 든 절이면 확정식으로 교체하고, 다른 컬럼과 섞인 절은 손대지 않는다(의도 불명).
    #    모수 확장 질의(_POP_WIDEN)는 위에서 이미 돌려보냈다.
    sql, replaced = _strictify_base_population(sql)
    # 🔴 11R KG ③-9 보류 — 모수 존재 판정을 WHERE 절로 좁히면 AA16(`SUM(CASE WHEN sale_yn=…)` 만 있고 WHERE 가
    #    없는 SQL, 개체별 COUNT 가 전수 23,676행으로 부푼다)이 닫히지만, **개별 조회 경로가 이 전체 SQL 판정에
    #    의존한다**: 묶기 가드가 SELECT 에 싣는 `판매중클래스수` CASE 를 모수 언급으로 읽어 '판매중' 주입을 막고
    #    있다(그 경로는 판매완료 14,707행을 0행 오거절 없이 조회해야 한다). 좁히면 동결선 S5·W5·X18 의 where 가
    #    바뀐다 — 실측으로 확인했고 별도 판단 사안으로 보고한다(12R 보고 ②).
    # 🔴 14R KG ③-5 (보류 해제 · AA16) — **`SUM(CASE WHEN <기본모수> THEN 1 ELSE 0 END)` 로 모수를 흉내 낸
    #    SELECT 는 모수 절로 승격한다.** AA16 실측: WHERE 가 아예 없고 SELECT 의 CASE 하나가 모수를 흉내 내
    #    `GROUP BY trusc_xtn_itt_cd` 가 판매완료·사모까지 세었다 — 정렬축이 오염돼 3위가 1위보다 컸다.
    #    승격 판정은 **CASE 안에 기본모수 두 조건이 다 있을 때만**이다. 개별 조회 묶기가 심는
    #    `SUM(CASE WHEN sale_yn='판매중' THEN 1 ELSE 0 END) AS "판매중클래스수"` 는 sale_yn 하나뿐이라
    #    여기 걸리지 않는다 — 동결선 S5·W5·X18 의 `where` 는 한 글자도 바뀌지 않는다(심사관 실측 확인).
    scan = sql
    m_frm = re.search(r"\bfrom\b", sql, re.I)
    if m_frm:
        head = sql[:m_frm.start()]
        for m_case in _BASE_POP_CASE.finditer(head):
            if _BASE_POP_SALE.search(m_case.group(0)) and _BASE_POP_PUBLIC.search(m_case.group(0)):
                scan = head[:m_case.start()] + head[m_case.end():] + sql[m_frm.start():]
                break
    missing = [c for c, pat in (("sale_yn = '판매중'", r"\bsale_yn\b"),
                                ("prvo_pbff_desc = '공모'", r"\bprvo_pbff_desc\b"))
               if not re.search(pat, scan, re.I)]
    if not missing:
        return sql, replaced
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


# 🔴 11R gold ③-1 — **가드가 주입·치환한 술어의 표식.** SQL 주석이라 실행 의미는 0이고, 뒤 가드의
#    「날조 술어 제거」가 자기 앞 가드의 출력을 지우는 것을 막는다(가드 A 가 만든 리터럴을 가드 B 가
#    날조로 보고 지운 계열 — OFFICIAL-004 · Z19). 확정식을 새로 만드는 가드는 이 표식을 붙인다.
_GUARD_MARK = "/*g*/"


def marked_conjuncts(sql: str) -> list[str]:
    """WHERE 의 최상위 절 중 확정식 가드가 주입한 것(`_GUARD_MARK` 표식) — 체인 끝 사후조건의 재료.

    🔴 11R 1순위 — **확정식은 원자적이어야 한다.** 지우고 대체를 못 넣거나(Z19), 뒤 가드가 대체를
    날조로 보고 지우면(OFFICIAL-004) 질문의 의미 조건이 통째로 증발해 전수 조회가 그럴듯한 답으로 나간다.
    체인은 확정식이 만든 절을 기억했다가 끝에서 살아 있는지 검사한다 — 사라졌으면 되돌리고 트레이스에 남긴다.
    """
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    return [c for c in guard.split_conjuncts(m_w.group(1)) if _GUARD_MARK in c] if m_w else []


_ETF_TBL = re.compile(r"\bfrom\s+(?:domestic_etfs|overseas_etfs)\b", re.I)
_ETN_Q = re.compile(r"ETN|상장지수증권", re.I)
# 🔴 2026-09-05 변형 보강 — "상장폐지" 는 막혔는데 "폐지 예정인 ETF" 는 뚫렸다(로컬 실측).
#    폐지 예정 ETF 71건은 **전건 pd_sale_yn=0** 이라 기본모수를 주입하면 반드시 0행이 된다 —
#    주입 가드 자체가 과잉 필터가 되는 유일한 자리라 어휘를 넉넉히 잡는다.
_ETF_WIDEN = ("판매완료", "판매 완료", "판매중단", "판매 중단", "판매종료", "상장폐지", "상장 폐지",
              "폐지", "상폐", "거래정지", "거래 정지", "전체 ETF", "모든 ETF")
_ETF_BASE_STRICT = {"pd_grp_no": "pd_grp_no = 'ETF'", "pd_sale_yn": "pd_sale_yn = 1"}
_ETF_NAME_FILTER = re.compile(r"\b(?:\w+\.)?(?:pd_nm|pd_abrv_nm|etf_name)\b\s*\)?\s*(?:LIKE|GLOB|=)", re.I)
_KO_CHUNK = re.compile(r"[가-힣]{2,}")


def _col_ko_of(table: str, col: str) -> str:
    for c, ko, *_ in (getattr(_ev_ctx(), "schema", {}) or {}).get(table, ()):
        if c.lower() == col.lower():
            return ko or ""
    return ""


def _col_asked(table: str, col: str, question: str) -> bool:
    """질문의 어떤 낱말이 이 컬럼을 지목하는가 — 스키마 한글명과 질문이 2자 이상 조각을 공유하는가(DB 원천, 하드코딩 0).

    판별을 **넓게** 잡는다: 지우는 쪽이 위험하므로 조금이라도 대응하면 사용자 조건으로 존중한다.
    '총보수요율' → '보수' 가 질문에 있으면 유지 · '기초지수' → '지수' 가 있으면 유지."""
    ko = _col_ko_of(table, col)
    q = question.replace(" ", "")
    for word in _KO_CHUNK.findall(ko):
        for size in range(len(word), 1, -1):
            for i in range(len(word) - size + 1):
                if word[i:i + size] in q:
                    return True
    return False


def ensure_etf_base_population(sql: str, question: str) -> tuple[str, bool]:
    """ETF 랭킹·집계 SQL 에 상품군 확정식을 기계 주입. (보정된 SQL, 보정했는지) — `ensure_fund_base_population` 의 ETF 판.

    8R 부류 B-4″-b / KG 부류 F — `grep pd_sale_yn src/runtime` 이 0건이었다: ETF 쪽엔 기본모수 가드가 **아예 없었다.**
    7R U8 실측이 그 부재의 발현이다 — 모수 절이 없으니 HCX 가 `pd_sale_yn=1 AND cu_charge_rt>0 AND cu_base_index
    NOT LIKE '%not provided%'` 라는 **아무도 요구하지 않은 모수**를 지어냈다. AA22 는 `pd_sale_yn` 자체가 없어 49(gold 45).
    확정식 둘: `pd_grp_no='ETF'`(주최 규칙의 ETF/ETN 분리 — 두 테이블 다 ETN 행을 담고 있다) · `pd_sale_yn=1`(판매모수).
    발동 조건은 펀드판과 같다 — 랭킹(ORDER BY)이나 집계(COUNT/SUM/AVG) 꼴이고, 질문이 그 축을 명시적으로 넓히지 않았을 때만.
    """
    if not _ETF_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I):
        return sql, False
    # 🔴 11R KG ③-2 (부류 V) — 모수 확정식도 **자기 FROM 을 확인한다.** X8 실측: `FROM public_funds` 문장의
    #    서브쿼리에 ETF 테이블이 있다는 이유로 바깥 WHERE 에 `pd_sale_yn=1` 을 주입해 스키마 검사가 기각했다.
    #    어느 가지의 WHERE 인지 알 수 없는 혼합 문장에서는 불개입한다(오거절이 잘못된 주입보다 낫다).
    if re.search(r"\bfrom\s+(?!domestic_etfs\b|overseas_etfs\b)\w+", sql, re.I):
        return sql, False
    tbl = _ETF_TBL.search(sql).group(0).split()[-1].lower()
    orig = sql
    strict = dict(_ETF_BASE_STRICT)
    if _ETN_Q.search(question):
        strict.pop("pd_grp_no")                     # ETN 질의는 상품군을 좁히지 않는다
    # 모수 **주입**은 종전 발동 조건(랭킹·집계 꼴 · 질문이 모수를 넓히지 않음)을 그대로 쓴다.
    # 🔴 10R 부류 Z — **있으면 확인하고 아니면 교체.** 종전엔 컬럼 언급만으로 불개입해서 HCX 가
    #    `pd_sale_yn IN (0,1)`·`pd_grp_no <> 'ETF'` 를 쓰면 가드가 자기를 껐다(9R U2·Y7 과 같은 형태).
    if (re.search(r"\border\s+by\b", sql, re.I) or re.search(r"\b(?:count|sum|avg)\s*\(", sql, re.I)) \
            and not any(t in question for t in _ETF_WIDEN):
        sql, _ = _strictify_base_population(sql, strict, tbl)
        missing = [v for c, v in strict.items() if not re.search(rf"\b{c}\b", sql, re.I)]
        if missing:
            sql, _ = _append_exclusions(sql, missing)
    # 🔴 10R 재검 ③-5 (부류 B-4″-c) — 집계·랭킹 질의의 **날조 술어**를 제거한다. 판별식: 최상위 AND 절의
    #    컬럼이 ⓐ 모수 확정식 컬럼도 아니고 ⓑ SELECT·ORDER BY 가 쓰는 값 컬럼도 아니고 ⓒ 질문 낱말과
    #    대응하지도 않으면 사용자 조건이 아니다. 7R U8 실측: `cu_charge_rt > 0` 하나가 보수 0인 419행을
    #    떨어뜨려 순자산 합계를 4,252,800(gold 4,380,605)으로 만들었다. 개별 조회(이름 필터)에는 적용하지 않는다.
    if not _ETF_NAME_FILTER.search(sql):
        m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
        if m_w:
            frm = re.search(r"\bfrom\b", sql, re.I)
            head_tail = sql[:frm.start()] + sql[m_w.end():]        # SELECT 목록 + GROUP/ORDER BY
            order_by = re.search(r"\border\s+by\b.*$", sql, re.I | re.S)
            axis = order_by.group(0) if order_by else ""
            kept = []
            for c in guard.split_conjuncts(m_w.group(1)):
                # 🔴 11R gold ③-1 (부류 Z) — **가드가 주입한 술어는 날조 술어가 아니다.** 확정식이 만든 절에는
                #    `_GUARD_MARK` 가 붙어 있다. 종전엔 그 절을 HCX 원문과 구분하지 못해, 앞선 지수 확정식이 만든
                #    영문 지수명 canon 을 "질문에 근거 없는 술어" 로 판정해 지웠다(OFFICIAL-004 `Aerospace` ·
                #    Z19 나스닥100 → 판매중 ETF 전수 1,160). 날조 판별은 표식 없는 절에만 건다.
                if _GUARD_MARK in c:
                    kept.append(c)
                    continue
                cols = {w.lower() for w in re.findall(r"[A-Za-z_]\w*", _SQL_LITERAL.sub("''", c))}
                cols &= {x.lower() for x, *_ in (getattr(_ev_ctx(), "schema", {}) or {}).get(tbl, ())}
                # 술어의 **리터럴이 질문에 있으면** 사용자 조건이다(`ref_base_index LIKE '%S&P500%'`) — 컬럼
                # 한글명 대조만으로는 이걸 못 본다. 지우는 쪽이 위험하므로 두 축 중 하나만 걸려도 남긴다.
                lit_asked = any(re.sub(r"[%\s]", "", lit.strip("'")).casefold() in question.replace(" ", "").casefold()
                                for lit in _SQL_LITERAL.findall(c) if len(re.sub(r"[%\s']", "", lit)) >= 2)
                if cols and not (cols & set(strict)) and not lit_asked \
                        and not any(re.search(rf"\b{x}\b", head_tail, re.I) for x in cols) \
                        and not any(_col_asked(tbl, x, question) for x in cols):
                    continue                                       # 질문 어디에도 근거가 없는 술어 — 제거
                # 🔴 10R gold N6 — **결측·0 은 필터가 아니라 표시 규칙이다.** 주최 규칙 §2("0/빈 값은 의도된 것")를
                #    HCX 가 `> 0` 모수 필터로 번역해 CROSS-002 가 0행이 됐다(국내 S&P500 한정 cu_charge_rt>0 = 0건).
                #    SELECT 에 실린 표시 컬럼의 `> 0`·`<> 0` 은 그 컬럼이 **정렬 축일 때만** 남긴다.
                if re.fullmatch(r"\(?\s*(?:\w+\.)?(\w+)\s*(?:>|<>|!=)\s*0(?:\.0)?\s*\)?", c.strip()) \
                        and cols and not any(re.search(rf"\b{x}\b", axis, re.I) for x in cols) \
                        and any(re.search(rf"\b{x}\b", sql[:frm.start()], re.I) for x in cols):
                    continue
                kept.append(c)
            if len(kept) != len(guard.split_conjuncts(m_w.group(1))):
                sql = sql[:m_w.start(1)] + " " + " AND ".join(kept) + " " + sql[m_w.end(1):]
    return sql, sql != orig


# ── 펀드 랭킹 대표행·근거컬럼 가드 3종 (2026-08-31 밤 — FND-019·015 실측 채점 후속,
#    docs/question_design_public_funds_2026-08-31.md §4. 프롬프트에 실려도 무시되는 규칙의 결정 층) ──
_ETF_INDEX_COL = re.compile(r"\b(?:\w+\.)?(?:cu_base_index|ref_base_index)\b", re.I)


def ensure_etf_index_canon(sql: str) -> tuple[str, bool]:
    """국내 ETF 의 기초지수 절을 `ref_base_index` **순수추종 확정식**으로 교체. (SQL, 교체했는지)

    🔴 10R KG 부류 T — `cu_base_index` 는 오염 컬럼이다(DB 실측, `pd_grp_no='ETF'` 1,235행 중 **1,179행(95.5%)
       공백**이고 값이 있는 'KOSPI200' 9행은 전부 무관 상품 — KODEX 200·TIGER 200 은 이 컬럼이 공백).
       정본은 `ref_base_index`(결측 2.2%)다. 순수추종 = 지수명 그대로이거나 수익 유형 접미(CR·TR·PR)만 붙은 것:
       실측 KOSPI200 **34**(X7) · NASDAQ100 **16**(Z19) · S&P500 **24**(AA22) — 전부 gold 와 일치한다.
       파생·섹터 변형(`F-KOSPI 200`·`KOSPI 200 IT`·`KOSPI 200 Covered Call`)은 순수추종이 아니다.
    해외 ETF(`overseas_etfs`)는 `cu_base_index` 가 정상이라 대상이 아니다.

    🔴 11R gold ③-3 — **치환은 술어 단위가 아니라 비교식 단위다.** 종전엔 지수 컬럼이 낀 절을 통째로 버려
       OR 반대편 가지까지 사라졌다(`cu_base_index LIKE '%우주%' OR pd_nm LIKE '%항공%'` → 이름 가지 소멸).
    🔴 11R KG ③-2 (부류 V) — **확정식은 자기가 주입할 컬럼이 그 FROM 테이블에 있는지 먼저 확인한다.**
       X8 실측: `FROM public_funds` 문장에 ETF 컬럼을 주입해 바로 뒤 스키마 검사가 자기 출력을 기각했다(자가 오거절).
       테이블이 섞인 문장(UNION·JOIN·다른 FROM)에서는 어느 가지의 WHERE 인지 알 수 없으므로 불개입한다.
    """
    # 절차 §2-4 — enforce 슬롯(domestic_etfs.기초지수.enforce, mark IDXCANON)이 먼저 처리했으면 침묵.
    # 🔴 슬롯은 **단일 등호 비교** 하나만 받는다. OR 가지·다중 리터럴·부정(NOT)이 섞인 꼴은
    #    여기 아래 로직이 계속 담당한다 — 섀도 실측 '가드만 발동' 1건이 그 자리다.
    if "M:IDXCANON" in sql:
        return sql, False
    m_tbl = re.search(r"\b(?:from|join)\s+domestic_etfs\b(?:\s+(?:as\s+)?"
                      r"(?!(?:left|inner|outer|cross|join|where|group|order|limit|on|union)\b)(\w+))?", sql, re.I)
    if not m_tbl:
        return sql, False
    # 🔴 16R gold ③-7 (부류 V · `CROSS-002`) — 불개입 조건은 「JOIN·UNION 이 있다」가 아니라
    #    **「컬럼의 소속 테이블을 특정할 수 없다」** 다. 술어에 테이블 한정자(`domestic_etfs.ref_base_index`·
    #    별칭 `d.ref_base_index`)가 붙어 있으면 소속이 확정되므로 개입한다. 종전엔 `\bjoin\b` 만 보고 즉시
    #    반환해 `LIKE '%S&P500%'` 가 0행 → 오거절이었다(실측 국내 순수추종 24건 실재).
    alias = m_tbl.group(1) or "domestic_etfs"
    mixed = bool(re.search(r"\bunion\b|\bjoin\b", sql, re.I)
                 or re.search(r"\bfrom\s+(?!domestic_etfs\b)\w+", sql, re.I))
    qual = f"{alias}." if mixed else ""
    qual_rx = re.compile(rf"\b{re.escape(alias)}\s*\.\s*(?:cu_base_index|ref_base_index)\b", re.I)
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        return sql, False

    def _canon(lit: str) -> str:
        col = f"REPLACE({qual}ref_base_index,' ','')"
        return f"{_GUARD_MARK}({col} GLOB '{lit}' OR {col} GLOB '{lit}[CTP]R*')"

    out, changed = [], False
    for c in _flat_conjuncts(m_w.group(1)):
        if _GUARD_MARK in c or not _ETF_INDEX_COL.search(c):
            out.append(c)                                    # 이미 확정식이거나 지수 축이 아니다(멱등)
            continue
        branches, hit_any = [], False
        for b in guard.split_disjuncts(_outer_group(c.strip()) or c):
            # 지수 컬럼을 쓴 **가지**의 비교 리터럴(REPLACE 의 ' '·'' 인자는 제외)을 지수명으로 삼는다
            lits = [x.strip("'").strip("%") for x in _SQL_LITERAL.findall(b) if len(x.strip("'").strip("% ")) >= 2]
            hit = re.sub(r"\s+", "", lits[-1]) if lits else ""
            owned = qual_rx.search(b) if mixed else _ETF_INDEX_COL.search(b)
            if owned and hit and not re.search(r"\bNOT\b", b, re.I) \
                    and not re.search(r"[*?\[\]]", hit):
                branches.append(_canon(hit))
                hit_any = changed = True
            else:
                branches.append(b.strip())
        out.append(branches[0] if len(branches) == 1 else "(" + " OR ".join(branches) + ")")
        if not hit_any:
            out[-1] = c
    if not changed:
        return sql, False
    new = sql[:m_w.start(1)] + " " + " AND ".join(out) + " " + sql[m_w.end(1):]
    return (new, True) if new != sql else (sql, False)


_ETF_MGMT_PRED = re.compile(r"\(?\s*(?:TRIM\(\s*)?(?:\w+\.)?cu_fund_mgmt_co\s*\)?\s*"
                            r"(?:=|LIKE|GLOB|IN)\s*(\([^)]*\)|'(?:[^']|'')*')", re.I)


@lru_cache(maxsize=256)
def _ref_mgmt_of(lit: str) -> str | None:
    """오염 컬럼 값 → 정본 운용사명. DB 역조회 최빈값(하드코딩 0). 못 찾으면 None.

    🔴 **접두 LIKE 를 운용사 축에 쓰지 않는다** — `LIKE 'Samsung%'` 은 `Samsung Active Asset Management`
       (삼성액티브자산운용, 별개 법인·별개 Org 노드) 25행을 삼성자산운용 240행에 합산해 265 를 만든다.
       정본은 `ref_fund_mgmt_co` **정확일치**다(심사관 실측 240/243).
    """
    lit = re.sub(r"[%*]", "", lit.strip().strip("'")).strip()
    if len(lit) < 2:
        return None
    con = connect_readonly()
    try:
        row = con.execute(
            "SELECT ref_fund_mgmt_co FROM domestic_etfs WHERE TRIM(cu_fund_mgmt_co) = ? "
            "AND ref_fund_mgmt_co IS NOT NULL AND TRIM(ref_fund_mgmt_co) <> '' "
            "GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1", (lit,)).fetchone()
        if not row:                                  # 이미 정본값을 오염 컬럼에 실은 경우(AA21 혼합 IN)
            row = con.execute("SELECT ref_fund_mgmt_co FROM domestic_etfs WHERE TRIM(ref_fund_mgmt_co) = ? "
                              "LIMIT 1", (lit,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return str(row[0]).strip() if row and row[0] else None


_MGMT_TAIL_SEG = re.compile(
    r"((?<![A-Za-z_])(?:GROUP\s+BY|ORDER\s+BY|HAVING)(?![A-Za-z_]))"
    r"(.*?)(?=(?<![A-Za-z_])(?:GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|UNION)(?![A-Za-z_])|$)", re.I | re.S)


def ensure_etf_mgmt_canon(sql: str) -> tuple[str, bool]:
    """국내 ETF 운용사 절을 `ref_fund_mgmt_co` **정확일치**로 정본화. (SQL, 교체했는지)

    🔴 11R KG ③-4 (부류 T-2) — `cu_fund_mgmt_co` 는 판매사·브랜드·상품명이 섞인 오염 컬럼이다(DB 실측:
       '삼성' 227 · '삼성KODEX' 3 · '삼성증권(주)' 70 = 판매사 · 상품명 통째 13종). 이 컬럼으로는 운용사를 셀 수 없다.
       정본은 `ref_fund_mgmt_co` 이고 gold 는 240(판매중 ETF) / 243(전체)이다.
    매핑을 못 만들면 **아무것도 지우지 않는다** — 확정식 원자성(가드가 조건을 지우고 대체를 못 넣는 상태를 만들지 않는다).
    """
    if not re.search(r"\bfrom\s+domestic_etfs\b", sql, re.I) \
            or re.search(r"\bunion\b|\bjoin\b|\bfrom\s+(?!domestic_etfs\b)\w+", sql, re.I):
        return sql, False
    # 🔴 14R gold ③-20 — **폐기한 컬럼은 SELECT 목록에서도 폐기한다.** UNANS-001 실측: 운용사 절은 없었는데
    #    SELECT 에 `cu_fund_mgmt_co` 가 실려 답변이 "운용사: KB"·"운용사: 삼성액티브" 로 나갔다
    #    (정본은 `KB Asset Ltd`·`Samsung Active Asset Management`). 항목 수가 안 바뀌므로 위치 ORDER BY 는 안전하다.
    frm = re.search(r"\bfrom\b", sql, re.I)
    sel_fixed = False
    if frm and "ref_fund_mgmt_co" not in sql[:frm.start()]:
        head = re.sub(r"\bcu_fund_mgmt_co\b", "ref_fund_mgmt_co", sql[:frm.start()], flags=re.I)
        if head != sql[:frm.start()]:
            sql, sel_fixed = head + sql[frm.start():], True
    out, at = [], 0
    for m in _ETF_MGMT_PRED.finditer(sql):
        names = [n for n in (_ref_mgmt_of(l) for l in _SQL_LITERAL.findall(m.group(1)) or [m.group(1)]) if n]
        if not names:
            continue                                             # 대체를 못 만들면 원 술어를 남긴다
        uniq = sorted(dict.fromkeys(names))
        cond = (f"ref_fund_mgmt_co = '{uniq[0]}'" if len(uniq) == 1
                else "ref_fund_mgmt_co IN (" + ", ".join(f"'{n}'" for n in uniq) + ")")
        out.append(sql[at:m.start()] + " " + _GUARD_MARK + cond)
        at = m.end()
    if out:
        sql, sel_fixed = "".join(out) + sql[at:], True
    # 🔴 GROUP BY 도 정본으로 바꾼다 — 서버 실측 2026-09-04 FIN-06: SELECT 만 고쳐진
    #    `SELECT ref_fund_mgmt_co, COUNT(*) … GROUP BY cu_fund_mgmt_co` 가 나가 **개수가 틀렸다.**
    #    오염 컬럼은 같은 운용사를 브랜드별로 쪼갠다(집계 그룹 84 vs 정본 28) — 삼성 240→224,
    #    미래에셋 230→188, 한화 85→81. SQLite 는 bare column 을 허용해 오류 없이 조용히 틀린다.
    tail = _MGMT_TAIL_SEG.sub(
        lambda m: m.group(1) + re.sub(r"\bcu_fund_mgmt_co\b", "ref_fund_mgmt_co", m.group(2), flags=re.I), sql)
    if tail != sql:
        sql, sel_fixed = tail, True
    return sql, sel_fixed


@lru_cache(maxsize=1)
def _etf_brand_tokens() -> tuple[str, ...]:
    """국내 ETF 브랜드 접두 — `pd_abrv_nm` 의 첫 공백 앞 토큰 중 5행 이상. **DB 실측**, 이름 하드코딩 0.

    실측 2026-09-03: KODEX 243 · TIGER 237 · RISE 150 · ACE 120 · 메리츠 97 · PLUS 92 … 25종.
    5행 하한은 해외 ETF 의 티커(대부분 1행)가 브랜드로 오인되는 것을 막는 컷이다.
    """
    con = connect_readonly()
    try:
        rows = con.execute(
            "SELECT substr(TRIM(pd_abrv_nm), 1, instr(TRIM(pd_abrv_nm) || ' ', ' ') - 1), COUNT(*) "
            "FROM domestic_etfs WHERE pd_abrv_nm IS NOT NULL GROUP BY 1 HAVING COUNT(*) >= 5").fetchall()
    except sqlite3.Error:
        return ()
    finally:
        con.close()
    return tuple(sorted((str(b).strip() for b, _ in rows if len(str(b).strip()) >= 2), key=len, reverse=True))


def ensure_etf_brand_token(sql: str, question: str) -> tuple[str, bool]:
    """질문이 지목한 ETF 브랜드가 최종 SQL 의 이름 술어에서 사라졌으면 되돌려 주입. (SQL, 주입했는지)

    🔴 14R gold ③-1 (부류 Z″ · **감점 축**) — `UNANS-001` 실측: 'KODEX AI 로봇 ETF 알려줘' 의 최종 SQL 이
       `pd_nm LIKE '%AI%' AND pd_nm LIKE '%로봇%'` 로 **`KODEX` 가 통째로 빠진 채** 실행돼, 「찾을 수 없습니다」라
       말한 직후 실재 ETF 3종을 운용사·설정일·순자산까지 붙여 나열했다. 11R `OFFICIAL-004` 에서 닫은 부류 Z
       (사용자 조건 소실 → 그럴듯한 목록)가 상품명 축에서 재발한 것이다.
    조건이 지워진 채 나온 목록은 답이 아니다 — 되돌려 주입하면 0행이 되고, 0행 경로의 유사 상품 되묻기가 받는다.
    발동 조건: ① 국내 ETF 단독 조회(UNION 없음) ② SQL 에 이미 이름 축 필터가 있다(이름 질의라는 신호)
    ③ 질문에 **DB 실측 브랜드 접두가 정확히 하나** 있고 ④ 그 브랜드가 SQL 어디에도 없다.
    브랜드가 둘 이상이면 비교 질의라 불개입한다(AND 로 이으면 정답 모수가 0이 된다).
    """
    if not _ETF_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I) or not _ETF_NAME_FILTER.search(sql):
        return sql, False
    from .router import _bound_in
    squeezed = re.sub(r"\s+", "", question)
    hits = [b for b in _etf_brand_tokens() if _bound_in(b, question, squeezed)]
    # 긴 브랜드가 짧은 브랜드를 품는 경우(TIME ⊂ TIMEFOLIO)는 긴 쪽 하나로 본다 — 사전이 길이 내림차순이다
    hits = [b for i, b in enumerate(hits) if not any(b in h for h in hits[:i])]
    if len(hits) != 1:
        return sql, False
    brand = hits[0]
    if brand.casefold() in re.sub(r"\s+", "", sql).casefold():
        return sql, False
    col = "pd_nm" if re.search(r"\bpd_nm\b", sql, re.I) else "pd_abrv_nm"
    return _append_exclusions(sql, [f"REPLACE({col},' ','') LIKE '%{brand}%'"])[0], True


_FUND_RETURN_COLS = ("fd_mm1_ern_r", "fd_mm3_ern_r", "fd_mm6_ern_r", "fd_mm18_ern_r",
                     "fd_yr1_ern_r", "fd_yr2_ern_r", "fd_yr3_ern_r", "fd_yr5_ern_r")
# 🔴 10R gold ③-B 5 — 보수 4컬럼도 랭킹 축이다('총보수가 가장 낮은 펀드'). 종전엔 축 목록에 없어
#    대표행 보정·랭킹 기계 조립이 통째로 꺼졌고 FND-005 가 우연히 통과 중이었다. 오름차순이므로 MIN 이 대표값이다.
_FUND_FEE_COLS = ("or_co_rwrd_r", "sale_co_rwrd_r", "trusc_rwrd_r", "ofwk_trus_rwrd_r")
_FUND_RANK_COLS = _FUND_RETURN_COLS + ("fd_nast_suma",) + _FUND_FEE_COLS
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


def _order_by_select_pos(sql: str) -> int | None:
    """ORDER BY 가 위치 표기(`ORDER BY 3`)면 그 0-기반 SELECT 자리. 아니면 None.

    값 열이 별칭(`MIN(...) as total_commission`)이면 컬럼명으로는 결과 헤더에서 못 찾는다 — 자리로 찾는다.
    2026-09-04 FND-005: 총보수 랭킹이 이 때문에 기계 조립을 못 타고 HCX 산문으로 떨어져 번호(`2.3.4.`)가
    뭉개지고 단위가 10배 틀렸다."""
    m = _ORDER_BY_HEAD.search(sql)
    frm = re.search(r"\bfrom\b", sql, re.I)
    if not m or not frm or not m.group(1).strip().isdigit():
        return None
    i = int(m.group(1).strip()) - 1
    sel = re.sub(r"^\s*select\s+(distinct\s+)?", "", sql[:frm.start()], flags=re.I)
    return i if 0 <= i < len(_split_select_items(sel)) else None


_FUND_CNT_KEY = re.compile(r"COUNT\s*\(\s*DISTINCT\s+(.+?)\s*\)\s+AS\s+\"펀드수\"", re.I | re.S)
_SUM_CASE = re.compile(r"SUM\s*\(\s*CASE\s+WHEN\s+(.+?)\s+THEN\s+1\s+ELSE\s+0\s+END\s*\)"
                       r"(?:\s+AS\s+(?:\"([^\"]+)\"|([A-Za-z_]\w*)))?", re.I | re.S)


def ensure_fund_unit_subcount(sql: str) -> tuple[str, bool]:
    """펀드 단위 집계에 딸린 **부가 조건 집계**도 펀드 단위로 세고, 단위를 별칭에 굽는다. (SQL, 고쳤는지)

    2026-09-04 KG-005 실측 — "이름이 삼성으로 시작하는 공모펀드는 몇 개고, **그중 삼성자산운용이
    운용하는 건 몇 개**야?" 의 SQL 이 이랬다:

        COUNT(DISTINCT <펀드키>) AS "펀드수", COUNT(*) AS "클래스수",
        SUM(CASE WHEN mgmt_co_nm LIKE '삼성%' THEN 1 ELSE 0 END) as samsung_mgt_cnt
        → 215 | 868 | 868

    앞의 두 열은 펀드/클래스를 구분하는데 **세 번째만 행(=클래스)을 센다.** 별칭도 단위를 말하지
    않아, 답변이 "삼성자산운용이 운용하는 펀드는 **868개**" 로 나갔다 — 클래스를 펀드로 답하는
    15R 최다 오답의 재발이고, 통과 조건이 명시적으로 금지한 자리다.

    조치: 같은 조건의 **펀드 단위 쌍을 함께 낸다.** 펀드키는 SQL 에 이미 있는 `"펀드수"` 열에서
    그대로 떼어 쓴다 — JOIN 이 있어도 테이블 수식이 어긋나지 않는다.
    불개입: `"펀드수"` 열이 없음(펀드 단위 질의가 아니다) · `SUM(CASE …)` 가 없음.
    """
    m_key = _FUND_CNT_KEY.search(sql)
    if not m_key:
        return sql, False
    key = m_key.group(1).strip()
    out, fixed, seen = sql, False, 0
    for m in list(_SUM_CASE.finditer(sql)):
        cond, alias = m.group(1).strip(), (m.group(2) or m.group(3) or "").strip()
        if not cond or "펀드수" in (alias or ""):
            continue
        base = alias or f"조건{seen + 1}"
        seen += 1
        rep = (f'COUNT(DISTINCT CASE WHEN {cond} THEN {key} END) AS "{base}_펀드수", '
               f'SUM(CASE WHEN {cond} THEN 1 ELSE 0 END) AS "{base}_클래스수"')
        out = out.replace(m.group(0), rep, 1)
        fixed = True
    return out, fixed


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
    orig = sql
    col, direction = target
    agg = "MAX" if direction == "DESC" else "MIN"
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()]
    m_grp = re.search(r"\bgroup\s+by\b(.*?)(?=\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    tail = sql[frm.start():]
    if m_grp:
        # 🔴 10R 부류 Z + gold ③-B 6 — GROUP BY 를 **확인하고 아니면 교체**한다. 종전엔 축에
        #    `or_co_xtn_itt_cd` 가 있을 때만 개입하고 정본식인지는 안 봤다: HCX 자작 펀드키
        #    (`COALESCE(…, itm_no)` 없는 형)는 역외 110행의 mtco NULL 을 한 그룹으로 뭉쳐 랭킹을 흔들었고,
        #    조립기 `_fund_rank_answer` 의 `GROUP BY <정본식>` 리터럴 발동 조건도 비켜 갔다(②-4 미발동).
        #    **펀드 식별 컬럼만으로 된 GROUP BY** 일 때만 교체한다 — 분포(유형별·운용사별)의 축은 답의 축이라 존중한다.
        # 🔴 11R 재검 ③-4 (부류 AB) — 랭킹의 묶기 축은 **대표예탁원번호(_FUND_GROUP_EXPR)** 다. `_FUND_KEY_EXPR` 은
        #    398 rptt 그룹 / 2,686 클래스행에서 한 펀드를 클래스 단위로 쪼갠다(Y4 1위 "클래스 1개"인데 실제 9).
        #    심사관 둘이 A 의 10R 보류를 실측으로 반증: R1·T1·V5·R2·Y6 은 펀드 단위 GROUP BY 를 아예 쓰지 않으므로
        #    `COUNT(DISTINCT _FUND_KEY_EXPR)` = 3,040 은 안 움직인다. **모수 집계 축은 그대로 두고 랭킹 축만 바꾼다.**
        #    🔴 이미 **정본 축**(둘 중 하나)이면 존중한다 — 목록 묶기(`ensure_fund_list_grouping`)가 만든
        #    `_FUND_KEY_EXPR` 축을 여기서 다시 갈면 목록 조립기가 꺼지고 커버리지 고지(«전체 248개»)가 사라진다.
        #    목록 경로의 축은 재검 ③-7·③-11(리드 판단 대기)이라 이 라운드에서 건드리지 않는다.
        gexpr = m_grp.group(1).strip()
        if gexpr not in (_FUND_GROUP_EXPR, _FUND_KEY_EXPR):
            # 🔴 11R 재검 ③-3 (부류 V′) — **축 판정에서 기본모수 컬럼은 뺀다.** 전 행이 같은 값이라 축으로서
            #    정보가 0이다. U14 실측: 축이 {or_co_xtn_itt_cd, prvo_pbff_desc} 라 ⊆ _FUND_ID_COLS 가 깨져
            #    정본 교체를 못 하고 폴백으로 갔다가 `_wrap_sort_col` 이 False 를 돌려 가드가 통째로 비켜갔다
            #    (트레이스에 마커도 안 남는 무음 종료). 빼고 나면 {or_co_xtn_itt_cd} 라 정본 펀드키 교체가 걸린다.
            gcols = ({w.lower() for w in re.findall(r"[A-Za-z_]\w*", gexpr)} & set(_fund_col_types())) - set(_BASE_STRICT)
            if not gcols or not gcols <= _FUND_ID_COLS:
                # 축을 못 읽었거나(위치 표기) 펀드 식별 축이 아니다 — 종전 동작(정렬 컬럼만 감싼다)
                if not re.search(r"\bor_co_xtn_itt_cd\b", gexpr, re.I):
                    return sql, False
                head, wrapped, in_func = _wrap_sort_col(head, col, agg)
                if not wrapped:
                    return sql, False
                if in_func:
                    tail = _wrap_order_by_col(tail, col, agg)
                return head + tail, True
            sql = sql[:m_grp.start(1)] + " " + _FUND_GROUP_EXPR + " " + sql[m_grp.end(1):]
            head, tail = sql[:frm.start()], sql[frm.start():]
    else:
        # ── GROUP BY 부재: 펀드키 주입 ──
        if "클래스" in question or re.search(r"\b(?:count|sum|avg|total)\s*\(", head, re.I):
            return sql, False
        m_ob = re.search(r"\border\s+by\b", tail, re.I)
        if not m_ob:
            return sql, False
        tail = tail[:m_ob.start()].rstrip() + f" GROUP BY {_FUND_GROUP_EXPR} " + tail[m_ob.start():]
    # ── 여기부터는 GROUP BY 가 정본 펀드키다: 식별 컬럼·클래스수 병기 + 정렬 컬럼 감싸기 (③-3) ──
    add = []
    if "itm_nm" not in head and "itm_no" not in head:
        add += ["itm_no", "TRIM(itm_nm) AS itm_nm"]
    head, wrapped, in_func = _wrap_sort_col(head, col, agg)
    if not wrapped and not re.search(rf"\b{col}\b", head, re.I):
        add.append(f"{agg}({col}) AS {col}")     # 정렬 컬럼이 SELECT 에 없으면 별칭으로 실어 ORDER BY 이름을 살린다
    if "클래스수" not in head:
        add.append('COUNT(*) AS "클래스수"')
    if add:
        head = head.rstrip() + ", " + ", ".join(add) + " "
    if in_func:
        tail = _wrap_order_by_col(tail, col, agg)
    tail, _ = _reagg_class_axis(tail, col, agg)   # ORDER BY SUM(수익률) — 정렬 축에도 같은 규칙(U14)
    new = _class_count_off_value_predicate(head + tail, col, agg)
    return (new, True) if new != orig else (sql, False)          # 멱등


_VALUE_PRED = re.compile(r"^\(?\s*(?:\w+\.)?(\w+)\s*(?:(IS\s+NOT\s+NULL)|(<=|>=|<>|!=|<|>)\s*(-?[\d.]+))\s*\)?$", re.I)


def _class_count_off_value_predicate(sql: str, col: str, agg: str, null_only: bool = False) -> str:
    """재검 ③-2 / KG 부류 S — `COUNT(*) AS 클래스수` 의 모수를 **값 컬럼 술어에서 뗀다.**

    9R 실측: 기계 조립이 `COUNT(*)` 를 그대로 "클래스 N개" 로 옮기는데, 그 COUNT 는 HCX 가 붙인 값 술어
    (`IS NOT NULL`·`<0`·`<>0`) 아래에서 세어진 **부분 카운트**였다 — `삼성배당주장기 1[주식]` 을 "클래스 1개"(실제 12).
    조치: 정렬 컬럼에 걸린 단독 술어를 WHERE 에서 HAVING 으로 옮긴다(집계 인자로 감싼다). 그러면 COUNT 는
    기본모수 전체를 세고, 값 술어는 대표값에만 걸린다.
    🔴 **값이 안 바뀌는 형태만 옮긴다** — 정렬 방향과 부등호 방향이 같을 때(DESC/MAX 에 `>`·`>=`, ASC/MIN 에 `<`·`<=`)
       `agg(전체) = agg(술어 통과분)` 이 성립하고, `IS NOT NULL` 은 집계가 NULL 을 건너뛰므로 항상 성립한다.
       `<> 0` 은 방향 술어와 함께일 때만 따라 옮긴다(그때는 이미 함의된다). 그 밖은 손대지 않는다.
    """
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        return sql
    ok_ops = (">", ">=") if agg == "MAX" else ("<", "<=")
    conjs = guard.split_conjuncts(m_w.group(1))
    cand = []            # (원 절, HAVING 형, 방향 술어인가)
    for c in conjs:
        m = _VALUE_PRED.match(c.strip())
        if not m or m.group(1).lower() != col.lower():
            continue
        if m.group(2):
            cand.append((c, f"{agg}({col}) IS NOT NULL", False))
        elif null_only:
            continue     # 개별 조회는 **결측 술어만** 옮긴다 — 방향 술어를 옮기면 MIN 쪽 표시값이 오염된다
        elif m.group(3) in ok_ops:
            cand.append((c, f"{agg}({col}) {m.group(3)} {m.group(4)}", True))
        elif m.group(3) in ("<>", "!="):
            cand.append((c, f"{agg}({col}) {m.group(3)} {m.group(4)}", None))   # 방향 술어와 함께일 때만
    directional = any(d is True for _, _, d in cand)
    move = [(c, h) for c, h, d in cand if d is not None or directional]
    if not move:
        return sql
    keep = [c for c in conjs if c not in {c0 for c0, _ in move}]
    where = (" WHERE " + " AND ".join(keep) + " ") if keep else " "
    return sql[:m_w.start()] + where + _insert_having(sql[m_w.end():], [h for _, h in move])


def _insert_having(rest: str, conds: list[str]) -> str:
    """GROUP BY 뒤(ORDER BY/LIMIT 앞)에 HAVING 을 끼운다 — 이미 있으면 AND 로 잇는다.

    🔴 14R 재검 ③-2 — 이 가드가 스스로 만든 HAVING 을 불개입 사유로 삼아 두 번째 값 컬럼에서 자기를 껐다.
       값 컬럼이 여럿인 개별 조회에서 첫 컬럼만 모수가 교정된다.
    """
    m_h = re.search(r"\bhaving\b", rest, re.I)
    if m_h:
        stop = re.search(r"\border\s+by\b|\blimit\b", rest[m_h.end():], re.I)
        at = m_h.end() + (stop.start() if stop else len(rest) - m_h.end())
        return rest[:at].rstrip() + " AND " + " AND ".join(conds) + " " + rest[at:]
    m = re.search(r"\border\s+by\b|\blimit\b", rest, re.I)
    at = m.start() if m else len(rest)
    return rest[:at].rstrip() + " HAVING " + " AND ".join(conds) + " " + rest[at:]


def _reagg_class_axis(text: str, col: str, agg: str) -> tuple[str, bool]:
    """클래스 축을 감싼 `SUM`·`AVG`·`TOTAL` 을 방향에 맞는 `MAX`/`MIN` 으로 교체. (텍스트, 바꿨는지)

    🔴 11R gold ③-12 (부류 W) — 클래스 수익률·보수의 **합은 도메인상 아무 뜻이 없다.** FND-005 실측:
       `SUM(or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r)` 가 클래스 11개짜리
       다올전단채 보수를 11배로 부풀려 top5 밖으로 밀었다(MIN 으로 바꾸면 gold 5건 완전 일치).
    순자산(`fd_nast_suma`)만 SUM 축을 허용한다 — 이 DB 의 순자산은 클래스별 값이라 펀드 순자산이 합계다.
    """
    if col == "fd_nast_suma":
        return text, False
    m = re.search(rf"\b(sum|avg|total)\s*\((?:[^()]|\([^()]*\))*\b{col}\b", text, re.I)
    return (text[:m.start(1)] + agg + text[m.end(1):], True) if m else (text, False)


_SELECT_HEAD = re.compile(r"\s*select\s+(?:distinct\s+)?", re.I)
_ITEM_ALIAS = re.compile(r"(?is)^(.*?)\s+AS\s+(\"[^\"]+\"|\w+)\s*$")


def _single_select(sql: str) -> bool:
    """SELECT 목록을 문자열로 편집해도 되는 문장인가 — 단일 SELECT 인가.

    🔴 14R gold ③-4 (부류 AC) — `CROSS-003` 실측: 억원 병기 가드가 `(SELECT '국내 ETF') UNION ALL (SELECT …)`
       의 **선두 여는 괄호**를 못 읽어 SELECT 항목 분해가 통째로 실패했고, `CAST(ROUND(((SELECT '국내 ETF')
       /100000000.0) …) AS "구분, pd_abrv_nm, du_last_aum_억원"` 을 주입해 문장을 부쉈다.
       12R 이 UNION 괄호를 살린 이상 UNION SQL 이 가드 체인에 계속 들어온다 — 판정을 공통 헬퍼로 못 박는다.
    판정: ⓐ 공백을 지운 첫 토큰이 `SELECT` ⓑ `UNION`·`EXCEPT`·`INTERSECT` 가 없다.
    """
    return bool(re.match(r"\s*select\b", sql, re.I)) and not re.search(r"\b(?:union|except|intersect)\b", sql, re.I)


def _wrap_sort_col(head: str, col: str, agg: str) -> tuple[str, bool, bool]:
    """SELECT 목록에서 정렬 축이 실린 **항목 하나**를 agg 로 감싼다. (새 head, 감쌌는지, ORDER BY 이름도 감싸야 하는지)

    🔴 14R gold ③-3 (부류 AC) — 종전엔 SELECT 목록을 문자열로 보고 정렬 컬럼의 **첫 등장만** 감쌌다.
       13R 실측 무응답 2건이 전부 여기서 났다:
         `FND-005` `or_co_rwrd_r + sale_co_rwrd_r + … AS tot_commission_rate`
                   → `MIN(or_co_rwrd_r) AS or_co_rwrd_r + sale_co_rwrd_r …` (near "+": syntax error)
         `FND-010` `p.fd_nast_suma` → `p.MAX(fd_nast_suma) AS fd_nast_suma`  (near "(": syntax error)
       규칙: SELECT 를 **항목 단위**로 분해해
         ⓐ 항목 전체가 그 컬럼(테이블 별칭 포함)이면 `agg(<항목>) AS <원별칭|컬럼>`
         ⓑ 항목이 산술식·함수식이면 **항목 전체**를 감싼다 `agg(<식>) AS <원별칭|컬럼>`
         ⓒ 감쌀 수 없으면(서브쿼리·괄호 불균형·단일 SELECT 아님) 보정을 포기하고 원 head 를 돌려준다.
       절대 부분 치환하지 않는다.
    """
    # 🔴 11R gold ③-12 (부류 W) — **클래스 축 집계는 SUM 이 아니라 MAX/MIN 이다.** 종전엔 이미 집계 안에 있으면
    #    통과시켜, `SUM(or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r)` 가 클래스 11개짜리
    #    다올전단채 보수를 11배로 부풀려 top5 밖으로 밀었다(FND-005 — 심사관 실측: MIN 으로 바꾸면 gold 5건 완전 일치).
    #    클래스 수익률·보수의 합은 도메인상 아무 뜻이 없다. 순자산(fd_nast_suma)만 SUM 축을 허용한다.
    swapped, ok = _reagg_class_axis(head, col, agg)
    if ok:
        return swapped, True, False
    if re.search(rf"(?:max|min|avg|sum|total)\s*\((?:[^()]|\([^()]*\))*\b{col}\b", head, re.I):
        return head, False, False
    m_sel = _SELECT_HEAD.match(head)
    if not m_sel:
        return head, False, False
    items = _split_select_items(head[m_sel.end():])
    for i, item in enumerate(items):
        if not re.search(rf"\b{col}\b", item, re.I) or _DISPLAY_UNIT.search(item):
            continue          # 표시 열(억원·백만USD)은 값 축이 아니다 — 감싸면 문자열을 집계하게 된다
        core = item.strip()
        m_as = _ITEM_ALIAS.match(core)
        expr, alias = (m_as.group(1).strip(), m_as.group(2)) if m_as else (core, None)
        # ⓒ 감쌀 수 없는 형태 — 서브쿼리·괄호 불균형이면 손대지 않는다
        if re.search(r"\(\s*select\b", expr, re.I) or expr.count("(") != expr.count(")"):
            return head, False, False
        items[i] = f" {agg}({expr}) AS {alias or col} "
        # 별칭이 컬럼명과 다르면 이름 ORDER BY 는 여전히 원 컬럼을 가리킨다 — 호출자가 그쪽도 감싼다
        return head[:m_sel.end()] + ",".join(items), True, bool(alias) and alias.strip('"').lower() != col.lower()
    return head, False, False


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
    #    3R B-4 ⓒ: 집계 head(COUNT 외 SUM/AVG/MIN/MAX, GROUP BY 없음)에는 식별 컬럼을 붙이지 않는다 — T3 "임의 클래스 이름 + SUM" 은
    #    FND-016 형 오인(어느 상품의 값인지 답변기가 지어낸다)이다.
    agg_head = bool(re.search(r"\bcount\s*\(", head, re.I)) or (
        bool(re.search(r"\b(?:sum|avg|min|max|total)\s*\(", head, re.I)) and not re.search(r"\bgroup\s+by\b", sql, re.I))
    if "itm_nm" not in head and "itm_no" not in head and not agg_head:
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
    #    억원 병기는 4도메인 공통 함수 ensure_amount_eok_columns 가 맡는다(4R B-4 확장 — 펀드 전용 분기 제거, 중복 0)
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
    if add:
        sql = head.rstrip() + ", " + ", ".join(add) + " " + sql[frm.start():]
    sql, eok = ensure_amount_eok_columns(sql)     # 순자산(bare/집계) 억원 병기 — 공통 함수에 위임
    return sql, bool(add) or eok


_AMOUNT_COL_RX = re.compile(r"\b(fd_nast_suma|du_last_aum)\b", re.I)   # 최소 단위 금액 컬럼 — 펀드 순자산 · ETF 순자산
# 8R B-4″ — 사람이 읽는 **표시 열**의 단위 표기. 원화는 '억원', 외화는 '백만<통화코드>'.
_DISPLAY_UNIT = re.compile(r"억원|백만[A-Z]{3}")
_DISPLAY_AMOUNT = re.compile(r"(-?\d{4,})(억원|백만[A-Z]{3})")   # 표시 열 값 — 천 단위 구분자를 기계가 넣는다 (10R ③-6)


@lru_cache(maxsize=1)
def _overseas_currency() -> str | None:
    """overseas_etfs 의 표시 통화 — DB 실측 최빈값(하드코딩 아님). 못 읽으면 None → 표시 열을 붙이지 않는다."""
    con = connect_readonly()
    try:
        row = con.execute("SELECT pd_trd_ccy FROM overseas_etfs WHERE pd_trd_ccy IS NOT NULL "
                          "GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return str(row[0]).strip().upper() if row and row[0] else None


def _amount_select_items(sql: str) -> list[tuple[str, str, str]]:
    """SELECT 항목 중 최소 단위 금액을 품은 것 — (표현식, 결과 헤더명, 컬럼). 표시 열 자체는 제외. SQL 텍스트 기준(HCX 별칭 포함)."""
    frm = re.search(r"\bfrom\b", sql, re.I)
    if not frm:
        return []
    sel = re.sub(r"^\s*select\s+(distinct\s+)?", "", sql[:frm.start()], flags=re.I)
    out = []
    for it in _split_select_items(sel):
        it = it.strip()
        m_col = _AMOUNT_COL_RX.search(it)
        if not m_col or _DISPLAY_UNIT.search(it):
            continue
        m = re.match(r"(.*?)\s+AS\s+\"?([^\"]+?)\"?\s*$", it, re.I | re.S)
        expr, header = (m.group(1).strip(), m.group(2).strip()) if m else (it, it)
        out.append((expr, header, m_col.group(1)))
    return out


def ensure_amount_eok_columns(sql: str) -> tuple[str, bool]:
    """일반 규칙(3R/4R B-4 · 8R B-4″): SELECT 에 최소 단위 금액(순자산)이 실리면 — bare·집계·HCX 별칭 무관, **테이블 무관** —
    사람이 읽는 표시 열이 항상 함께 실린다. 원값 열은 _hide_answer_columns 가 답변 입력에서 숨긴다(V7 '164,377,105,967,341원').

    🔴 8R B-4″ — 종전엔 `public_funds|domestic_etfs` 화이트리스트라 `overseas_etfs` 에 표시 열도 통화 표기도 안 붙었고,
    13자리 원값(4,380,604,640,000)이 헤더 `총순자산USD` 하나만 달고 HCX 로 가 **배율이 지어졌다**(7R Y16 "43,806,464
    백만 달러" = 10배 과대 · U8 은 USD 를 '원' 으로 표기). 값을 숨기는 것도 맨값을 주는 것도 답이 아니고, 사람이 읽는
    형태로 확정해 주는 것만 답이다. 통화는 DB 실측 최빈값(`pd_trd_ccy`)이고 하드코딩이 아니다.
    이름: 컬럼 그대로면 '순자산_<단위>', SUM 무별칭이면 '순자산합계_<단위>', 별칭이면 '<별칭>_<단위>'.
    이미 같은 컬럼의 표시 열이 있으면 불개입."""
    m_tbl = re.search(r"\bfrom\s+(public_funds|domestic_etfs|overseas_etfs)\b", sql, re.I)
    # 🔴 14R gold ③-4 (부류 AC) — SELECT 목록을 문자열로 편집하는 가드는 **단일 SELECT 에서만** 발동한다.
    #    CROSS-003 실측: UNION 문장의 선두 `(` 때문에 항목 분해가 실패해 이 가드가 SQL 을 부쉈다.
    if not m_tbl or not _single_select(sql):
        return sql, False
    if m_tbl.group(1).lower() == "overseas_etfs":
        cur = _overseas_currency()
        if not cur:
            return sql, False          # 통화를 확정 못 하면 표시 열을 붙이지 않는다(단위 없는 수를 만들지 않는다)
        unit, div, base = f"백만{cur}", "1000000", "백만"
    else:
        unit, div, base = "억원", "100000000", "억"
    items = _amount_select_items(sql)
    if not items:
        return sql, False
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()]
    existing = [it for it in _split_select_items(re.sub(r"^\s*select\s+(distinct\s+)?", "", head, flags=re.I))
                if _DISPLAY_UNIT.search(it)]
    # 🔴 11R 재검 ③-10 — 부류 Z 형태(「있으면 불개입」)를 **「불일치 시 교체」**로 바꾼다. 다른 여섯 확정식
    #    가드는 이미 이 형태다(심사관이 코드로 전수 확인). 9R U2·Y7 이 정확히 이 형태에서 터졌다:
    #    HCX 가 분모·단위를 틀리게 쓰면 가드가 자기를 껐다. 확정식과 분모·단위가 다른 표시 열은 걷어낸다.
    stale = [it for it in existing
             if _AMOUNT_COL_RX.search(it) and not (f"/{div}" in it.replace(" ", "") and f"'{unit}'" in it)]
    for it in stale:
        head = head.replace(it, "", 1)
        existing.remove(it)
    head = re.sub(r",\s*,", ",", head)
    head = re.sub(r",\s*(?=\bFROM\b|$)", " ", head.rstrip(), flags=re.I)
    add = []
    for expr, header, col in items:
        if any(col in e or header in e for e in existing):
            continue
        if header == col or header == expr and expr.lower() == col.lower():
            name = f"순자산_{unit}"
            # 🔴 11R 재검 ③-6 — 억원 표시는 **전부 ROUND** 다. 종전엔 이 분기만 절사(CAST(x/1e8))라
            #    같은 33,109,784,036,579원을 경로에 따라 331,097(절사)/331,098(ROUND)로 달리 적었다(T3 vs T2·V5).
            e = f"CAST(ROUND({col}/{div}.0) AS INTEGER) || '{unit}' AS \"{name}\""
        elif header == expr:
            name = f"순자산합계_{unit}" if re.match(r"(?i)sum\s*\(", expr) else f"{col}_{unit}"
            e = f"CAST(ROUND(({expr})/{div}.0) AS INTEGER) || '{unit}' AS \"{name}\""
        else:
            name = f"{header}_{unit}"
            e = f"CAST(ROUND(({expr})/{div}.0) AS INTEGER) || '{unit}' AS \"{name}\""
        if name not in head:                       # 걷어낸 표시 열은 head 에서 이미 빠졌다(멱등 판정도 head 기준)
            add.append(e)
    if not add and not stale:
        return sql, False
    new = head.rstrip() + (", " + ", ".join(add) if add else "") + " " + sql[frm.start():]
    return (new, True) if new != sql else (sql, False)


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
        # 🔴 2026-09-04 DOM-12 — 구 힌트는 "전문투자자 조건은 han_clas_policies LIKE '%전문투자자%' 로 푼다"
        #    였는데 **그 27건이 오답이었다**(gold: 코드 의미 미제공이라 전용 여부 판정 불가).
        #    han_clas_policies 의 '전문투자자' 는 클래스 정책 서술이지 판매 제한이 아니다.
        #    전문투자자 질의 자체는 이제 gate_constants "(전문투자자 전용 여부)" 가 HCX 0회로 가로챈다.
        " — 전문투자자 전용 여부는 이 데이터로 판정할 수 없다. han_clas_policies 의 '전문투자자' 표기는"
        " 클래스 정책 서술이라 그것으로 '전용' 을 단정하지 않는다 (개인·법인 구분이나 연금 가입 가능 여부로 안내)",
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


# 2026-09-03 서버 실측: '달러로 발행된 채권 알려줘' → `curr_cd = '000'` — 값 사전에는 있으나(오염값 1행 실재) 규칙
#   외화채없음이 '사용 불가' 로 못 박은 리터럴. 값 검사가 통과시키므로 사용 금지 컬럼과 같은 자리에서 기각한다.
#   어휘 층(yaml gate_constants curr_cd)이 먼저 받고, 이 가드는 어휘를 비켜 간 SQL 의 뒷문이다.
# 🔴 2026-09-04 DOM-03 — **테이블을 함께 못 박는다.** 두 규칙 다 `domestic_bonds` 의 사실인데
#    테이블을 안 보고 컬럼명만 봐서 `public_funds` 의 정상 SQL 을 기각했다:
#    펀드 curr_cd 는 기본모수에 USD 152·EUR 29·JPY 4·SEK 1·AUD 1(비원화 187클래스/131펀드)이 실재하고
#    `curr_cd != 'KRW'` 가 정답 SQL 이다. 채권(KRW·000 뿐)과 컬럼명만 같고 사실이 정반대인 자리다.
#    부류: 여러 도메인이 같은 컬럼명을 쓰면 컬럼 단위 가드는 반드시 테이블로 한정한다.
_FORBIDDEN_LITERALS = [
    ("domestic_bonds", re.compile(r"curr_cd\s*(?:=|<>|!=)\s*'000'", re.I),
     "curr_cd='000' 은 통화 미수록 오염값 1행(BAC)이라 조건으로 쓸 수 없다 — 국내채권은 원화(KRW)만 수록, "
     "달러·외화 채권은 '수록되어 있지 않다' 로 답한다(통화 조건은 curr_cd='KRW' 만)"),
    ("domestic_bonds", re.compile(r"curr_cd\s*(?:<>|!=)\s*'KRW'", re.I),
     "curr_cd <> 'KRW' 는 오염값 '000' 1행만 남긴다 — 외화 채권은 수록 없음, 원화 외 통화 조건을 만들지 않는다"),
]


def forbidden_literal_use(sql: str) -> str | None:
    """사용 금지 리터럴(오염값)을 조건으로 쓴 SQL 의 기각 사유 — 없으면 None.

    🔴 규칙마다 소유 테이블이 있다. SQL 이 그 테이블을 쓰지 않으면 발동하지 않는다 — 같은 컬럼명이
    다른 도메인에서 정반대 사실을 가질 수 있다(2026-09-04 DOM-03: 채권용 curr_cd 규칙이 펀드를 기각)."""
    tables = set(guard.sql_tables(sql))
    for owner, pat, why in _FORBIDDEN_LITERALS:
        if owner in tables and pat.search(sql):
            return why
    return None


# 🔴 14R gold ③-12 (부류 R′) — **축을 바꿔 답했으면 반드시 밝힌다.** `FND-R02` 실측: 질문이 요구한
#    `fd_wk1_ern_r`(1주 수익률)이 23,676/23,676 전건 결측이라 SQL 이 기각되고, 재생성이 말없이 1개월로
#    갈아탄 뒤 답변이 그 사실을 한 글자도 밝히지 않았다(must_include `1주`·`없` 둘 다 미충족).
#    컬럼 정책 단위 고지문이다 — 문항별 예외가 아니다.
_MISSING_AXIS_NOTE = {
    "fd_wk1_ern_r": "요청하신 1주 수익률은 제공된 데이터에 없습니다(전건 미수록). "
                    "아래는 수록된 다른 기간 축으로 대신 답한 것입니다.",
}


def missing_axis_note(sql: str) -> str | None:
    """질문이 지목한 축이 전건 결측이라 다른 축으로 답할 때 머리줄에 기계로 적을 고지문 — 없으면 None."""
    for col, note in _MISSING_AXIS_NOTE.items():
        if re.search(rf"\b{col}\b", sql, re.I):
            return note
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


# 한정자(p.itm_nm)는 REPLACE 안으로 — 2026-09-02 KG-002 실측: `p.REPLACE(itm_nm,…)` OperationalError → "오류" 무응답
# 🔴 14R KG ③(X8) — 벤치마크 이름도 표기 공백이 제각각이다: `bmrk_nm LIKE '%S&P500%'` 는 32클래스만 잡고
#    `'S&P 500'` 표기를 통째로 놓친다(공백 무시 188클래스 / 펀드 57 = gold). 이름 축과 같은 병이라 같은 가드가 받는다.
#    등호(`_NAME_EQ`)는 확장하지 않는다 — KG 가 bmrk_nm 을 정확일치로 매핑하므로 LIKE 로 넓히면 정본이 흐려진다.
_NAME_LIKE = re.compile(r"(?<!REPLACE\()(?:TRIM\(\s*)?((?:\b\w+\.)?)\b(itm_nm|bmrk_nm)\b\s*\)?\s*((?:NOT\s+)?LIKE)\s*'((?:[^']|'')*)'", re.I)


def ensure_spaceless_name_match(sql: str, token: str | None = None) -> tuple[str, bool]:
    """종목명 LIKE 를 **공백 무시 매칭**으로 바꾼다. (보정된 SQL, 보정했는지)

    2026-08-31 밤 실측(FND-R05 후속): 사용자가 띄어 쓰면 있는 상품을 통째로 놓친다 —
    '미래에셋 코어테크' 그대로 0행 / 공백 제거 14행. 'AI 반도체' 도 0행 / 4행.
    종목명은 표기 공백이 제각각이라(삼성 베스트 MMF 법인 제1호) 양쪽 다 정규화해야 한다:
    REPLACE(itm_nm,' ','') LIKE '%<공백 제거 키워드>%'. 매칭을 넓히기만 하므로 안전하고,
    존재하지 않는 상품(FND-R05)은 여전히 0행이다.
    """
    def _fix(m: re.Match) -> str:
        pat = m.group(4).replace(" ", "")
        return f"REPLACE({m.group(1)}{m.group(2)},' ','') {m.group(3).upper()} '{pat}'"

    def _fix_eq(m: re.Match) -> str:
        # 3R A-1 — 이름 **등호**는 항상 0행이다: 기본모수 KR 8,859행 전부 클래스 접미(종류A·(C1)…)를 달고 있어 사용자가 부르는
        # 줄기 이름과 itm_nm 이 등호로 같을 수 있는 행이 0 (T7 오거절). 공백 무시 부분일치로 치환 — 넓히기만 한다.
        pat = m.group(3).replace(" ", "")
        return f"REPLACE({m.group(1)}{m.group(2)},' ','') LIKE '%{pat}%'"
    fixed = _NAME_LIKE.sub(_fix, sql)
    fixed = _NAME_EQ.sub(_fix_eq, fixed)
    if token:
        # 4R J-2 — HCX 가 이름 토큰을 조각내 AND 로 3개 이상 이어 붙인 것(미래에셋/차이나/솔로몬/증권투자신탁)은 리터럴들이
        #    토큰의 연속 부분열이면 한 토큰 LIKE 로 접는다(조각 LIKE 는 형제 펀드를 끌어온다).
        lits = re.findall(r"REPLACE\((?:\w+\.)?itm_nm,' ',''\) LIKE '%([^%']+)%'", fixed)
        tok = token.replace(" ", "")
        if len(lits) >= 3 and "".join(lits) in tok:
            first = True

            def _fold(m: re.Match) -> str:
                nonlocal first
                if first:
                    first = False
                    return f"REPLACE(itm_nm,' ','') LIKE '%{tok}%'"
                return "1=1"
            fixed = re.sub(r"REPLACE\((?:\w+\.)?itm_nm,' ',''\) LIKE '%[^%']+%'", _fold, fixed)
            fixed = re.sub(r"\s+AND\s+1=1", "", fixed)
    return fixed, fixed != sql


_NAME_EQ = re.compile(r"(?:TRIM\(\s*)?((?:\b\w+\.)?)\b(itm_nm)\b\s*\)?\s*=\s*'((?:[^']|'')*)'", re.I)


# 이름 조회 필터 — **좌변이 itm_nm** 인 LIKE/GLOB 만 (원형 · TRIM(itm_nm) · 공백무시 REPLACE 형).
# 🔴 2026-09-02 리뷰 ②-1: 종전 `itm_nm … {0,40}자 … LIKE` 40자 창이 SELECT 의 itm_nm 과 WHERE 의 다른 컬럼
#    LIKE(or_attr_desc·zrin_attr_nms)를 이름 조회로 오인 — "주식형 공모펀드" 목록이 개별 조회 묶기(최단 이름순)로
#    빠져 역외 1클래스 펀드 30개가 나갔다. `NOT LIKE` 는 제외 필터라 이름 조회가 아니다(NOT 이 끼면 불일치).
_NAME_FILTER = re.compile(
    r"(?:REPLACE\(\s*(?:\w+\.)?itm_nm\s*,\s*' '\s*,\s*''\s*\)|TRIM\(\s*(?:\w+\.)?itm_nm\s*\)|\b(?:\w+\.)?itm_nm\b)\s*(?:LIKE|GLOB)\b", re.I)


def _has_name_filter(sql: str) -> bool:
    """WHERE 절(FROM 뒤)에 좌변 itm_nm 의 LIKE/GLOB 이름 조회가 있는가.

    3R C-3: 이름 LIKE 가 **비-itm_nm 절과 OR 로 묶인 괄호 안**에 있으면 이름 조회가 아니다(태그 ∪ 이름 목록 — 개별 조회 묶기가
    아니라 목록 묶기 경로여야 한다). 판정: 그 LIKE 를 감싸는 최소 괄호 그룹에 OR 와 itm_nm 아닌 컬럼 조건이 함께 있음.
    """
    frm = re.search(r"\bfrom\b", sql, re.I)
    if not frm:
        return False
    # 🔴 10R — 괄호 짝 계산에서 **문자열 리터럴 안의 괄호**를 빼야 한다: 호수 경계 GLOB `'*[^0-9.]3[([]*'` 의
    #    `(` 가 깊이를 올려 감싸는 그룹이 문장 끝까지 번졌다(S5 — 이름 필터가 있는데 '없다' 로 판정돼 중복 주입).
    raw = sql[frm.end():]
    tail = _SQL_LITERAL.sub(lambda mm: mm.group(0).replace("(", "\x02").replace(")", "\x03"), raw)
    for m in _NAME_FILTER.finditer(tail):
        # 호수 경계 GLOB('*[^0-9.]3호*' — ensure_fund_series_boundary 산출)은 이름 조회가 아니다(4R J: T6 가 GLOB 만으로 '이름 필터 있음' 판정돼
        # 토큰 LIKE 가 주입되지 않았다)
        m_lit = re.match(r"\s*'([^']*)'", raw[m.end():])
        if m_lit and "[^" in m_lit.group(1):
            continue
        depth, start = 0, None
        for i in range(m.start() - 1, -1, -1):
            ch = tail[i]
            if ch == ")":
                depth += 1
            elif ch == "(":
                if depth == 0:
                    start = i
                    break
                depth -= 1
        if start is None:
            return True
        depth, end = 0, None
        for j in range(start + 1, len(tail)):
            ch = tail[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    end = j
                    break
                depth -= 1
        group = tail[start:end] if end else tail[start:]
        inner = re.sub(r"REPLACE\(\s*(?:\w+\.)?itm_nm\s*,\s*' '\s*,\s*''\s*\)", "itm_nm", group)
        # 🔴 10R — 다른 컬럼이 **비교 연산자 바로 앞**에 있어야 한다는 조건은 좁았다: KG-021 의
        #    `(',' || prfd_attr_cds || ',' LIKE '%,TWN,%' OR REPLACE(itm_nm,…) LIKE '%대만%')` 은 연결식이라
        #    컬럼이 LIKE 에 붙어 있지 않아 '이름 조회' 로 오판됐다(태그 ∪ 이름 목록 = 목록 경로여야 한다).
        #    판정은 SQL 낱말 목록이 아니라 **스키마 컬럼 대조**로 한다(하드코딩 0).
        # 🔴 14R 재검 ③-4 (Y14 실측 · 부류 AA′ 의 진짜 원인) — OR 판정은 **그 그룹의 최상위**여야 한다.
        #    종전엔 그룹 문자열 전체에서 OR 를 찾아, **중첩 그룹 안**의 OR 에 걸렸다:
        #      `(or_co = '00040067' AND itm_nm LIKE '%…%' AND (GLOB '*2호*' OR GLOB '*2(*'))`
        #    호수 경계 가드가 심은 중첩 OR 때문에 이름 조회가 아니라고 판정돼 개별 조회 조립기가 통째로
        #    꺼졌고(Y14: 클래스수·기준일·'클래스 합계' 축 고지 소멸 + HCX 마크다운 굵게), 가드가 하나 늘 때마다
        #    재발할 구조였다. 괄호 안쪽부터 지워 최상위만 남긴 뒤 판정한다(validate_sql 의 OR 검사와 같은 기계).
        top, prev = inner, None
        while prev != top:
            prev, top = top, re.sub(r"\([^()]*\)", " ", top)
        other = ({w.lower() for w in re.findall(r"[A-Za-z_]\w*", top)}
                 & set(_fund_col_types())) - {"itm_nm"}
        if not (re.search(r"\bOR\b", top, re.I) and other):
            return True
    return False
# 행(클래스) 단위가 정답인 질의 — **값이 클래스마다 갈리는 축**만. 🔴 10R(8R 보류 ③-1): '클래스' 를 뺐다.
# '클래스' 는 개수·열거를 묻는 말이라 펀드키 묶기가 정답이고, 종전엔 여기 있으면서 `and not m_grp` 라는
# 모양 조건으로 반쯤 예외를 뒀다 — 7R U3 실측: HCX 가 `SELECT DISTINCT … LIMIT 30` 을 내자 13행이
# 산문으로 가서 HCX 가 11개라고 셌다. 불개입은 질문 낱말만 본다.
_LOOKUP_ROW_UNIT = ("보수", "수수료")
# 클래스를 **열거**해 달라는 질의(어떤 클래스가 있어?)는 행 단위가 정답이다 — 개수 질의('몇 개')와 다르다.
_CLASS_LIST_Q = re.compile(r"클래스[가는들이]{0,2}\s*(?:어떤|어느|무슨|무엇|뭐)|(?:어떤|어느|무슨)\s*클래스"
                           r"|클래스\s*(?:목록|종류)|클래스[를을]?\s*(?:나열|열거)")
# 식별자·키 컬럼 — 이걸로 정렬한 것은 '랭킹' 이 아니라 모양 잡음이다 (7R M′)
_FUND_ID_COLS = frozenset({"itm_no", "itm_nm", "rptt_ksd_itm_no", "mtco_itm_no", "or_co_xtn_itt_cd", "itm_abrv_nm"})
# 🔴 우변은 **리터럴**이어야 한다 — JOIN 의 `ON e.itm_no = p.itm_no` 는 조인 조건이지 개별 조회의 핀이 아니다
#    (7R: 기본모수 F6′ 분기가 이걸 개별 조회로 오인해 ext_fund_page 조인 랭킹에서 판매중 주입이 꺼졌다)
_FUND_KEY_PIN = re.compile(r"\b(?:rptt_ksd_itm_no|itm_no|mtco_itm_no)\s*\)?\s*(?:=\s*'|IN\s*\(\s*')", re.I)


def _has_fund_key_pin(sql: str) -> bool:
    """WHERE 절에 펀드 키(대표예탁원번호·종목번호·운용사종목번호) 등호/IN 이 있는가 — 개별 조회의 또 다른 특정 조건 (4R M)."""
    frm = re.search(r"\bfrom\b", sql, re.I)
    return bool(frm) and bool(_FUND_KEY_PIN.search(sql[frm.end():]))
_FUND_KEY_COLS = ("rptt_ksd_itm_no", "itm_no", "mtco_itm_no")


@lru_cache(maxsize=512)
def _fund_key_owners(lit: str) -> tuple:
    """리터럴이 실재하는 펀드 키 컬럼들 — DB 실측(컬럼당 1행 조회). 이름·코드 하드코딩 0."""
    if not lit.strip():
        return ()
    con = connect_readonly()
    try:
        return tuple(c for c in _FUND_KEY_COLS
                     if con.execute(f"SELECT 1 FROM public_funds WHERE TRIM({c}) = ? LIMIT 1", (lit.strip(),)).fetchone())
    except sqlite3.Error:
        return ()
    finally:
        con.close()


def ensure_fund_key_column(sql: str) -> tuple[str, list[str]]:
    """7R S′ — 펀드 키 리터럴이 **다른 키 컬럼**에 실렸으면 실재하는 컬럼으로 교정. (보정된 SQL, 교정 목록)

    6R W11 실측: Ground 가 `public_funds.rptt_ksd_itm_no='030230002D36'` 을 핀했는데 HCX 는
    `itm_no IN ('030230002D36')` 을 썼다 — `check_code_literals` 는 `*_itt_cd` 만, `check_values` 는
    값 사전이 있는 컬럼만 보므로 둘 다 통과해 0행 오거절이 됐다(5R 은 HCX 가 우연히 옳은 컬럼을 써서 ✅ — 비결정).
    Ground 를 참조하지 않는다: **DB 실측만으로** "이 컬럼엔 0행, 형제 키 컬럼 정확히 하나에 실재" 가 판정된다.
    형제가 둘 이상이거나 어디에도 없으면 손대지 않는다(값 검사·0행 진단에 맡긴다).
    """
    if not _FUND_TBL.search(sql):
        return sql, []
    pairs: list[tuple[str, str]] = []
    for _t, col, lit in guard._EQ.findall(sql):
        if col.lower() in _FUND_KEY_COLS:
            pairs.append((col, lit))
    for _t, col, body in guard._IN.findall(sql):
        if col.lower() in _FUND_KEY_COLS:
            pairs += [(col, lit) for lit in guard._LIT.findall(body)]
    fixes = []
    for col, lit in pairs:
        owners = _fund_key_owners(lit)
        if len(owners) != 1 or owners[0] == col.lower():
            continue
        # 그 리터럴이 든 술어의 **좌변만** 바꾼다 (SELECT·GROUP BY 의 같은 컬럼명은 건드리지 않는다)
        pat = re.compile(rf"\b{re.escape(col)}\b(\s*(?:=\s*'{re.escape(lit)}'|IN\s*\([^)]*'{re.escape(lit)}'[^)]*\)))", re.I)
        new, cnt = pat.subn(owners[0] + r"\1", sql)
        if cnt:
            sql = new
            fixes.append(f"{col} → {owners[0]} ('{lit}')")
    return sql, fixes


# 클래스 표기 — '종류A' · 'A클래스' · '종류 C-P2e' · 'Ce클래스'. 하이픈·공백은 무시하고 맞춘다(질문 'Ce' ↔ DB '종류C-e')
_CLASS_NOTE_Q = re.compile(r"종류\s*([A-Za-z](?:\s*-?\s*[A-Za-z0-9]){0,4})|(?<![A-Za-z])([A-Za-z](?:-?[A-Za-z0-9]){0,4})\s*클래스")
_CLASS_NM_CONJ = re.compile(r"\b(?:\w+\.)?han_clas_nm\b", re.I)
_CLASS_NM_SUFFIX = "REPLACE(REPLACE(itm_nm,' ',''),'-','')"


@lru_cache(maxsize=128)
def _class_suffix_exists(tok: str) -> bool:
    """'종류<tok>' 로 끝나는 종목명이 실제로 있는가 — DB 실측. 질문의 우연한 영문 토큰('ETF 클래스')을 걸러낸다."""
    con = connect_readonly()
    try:
        return con.execute(f"SELECT 1 FROM public_funds WHERE {_CLASS_NM_SUFFIX} LIKE ? LIMIT 1",
                           (f"%종류{tok}",)).fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        con.close()


def _class_notation_in_question(question: str) -> str | None:
    """질문의 클래스 표기(하이픈·공백 제거, 대문자화). DB 에 실재하는 접미만 돌려준다."""
    for m in _CLASS_NOTE_Q.finditer(question):
        tok = re.sub(r"[\s-]", "", m.group(1) or m.group(2) or "")
        if tok and _class_suffix_exists(tok.upper()):
            return tok.upper()
    return None


def ensure_fund_class_notation(sql: str, question: str) -> tuple[str, bool]:
    """KG 4R G7 — '종류A·A클래스·Ce·C-P2' 는 수수료체계(`han_clas_nm`)가 아니라 **종목명 접미**다. (SQL, 교체했는지)

    6R Z1 실측: `TRIM(han_clas_nm) = '종류 A'` — 이 컬럼의 실제 값은 '수수료선취-오프라인' 류라 **0행**이다
    (DB 전수 확인: han_clas_nm 에 '종류 A' 0건 · itm_nm 접미 '종류A' 3건). 조치: han_clas_nm 절을 걷어내고
    `REPLACE(REPLACE(itm_nm,' ',''),'-','') LIKE '%종류X'` 확정식을 AND 로 넣는다. 그러면 F2 의 MIN~MAX 범위가
    그 단일 클래스 값으로 저절로 좁혀진다(묶기 가드가 뒤에서 받는다).
    """
    if not _FUND_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I):
        return sql, False
    tok = _class_notation_in_question(question)
    if not tok:
        return sql, False
    cond = f"{_CLASS_NM_SUFFIX} LIKE '%종류{tok}'"
    if cond in sql:
        return sql, False
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        anchor = _SQL_ANCHOR.search(sql) or re.search(r"\blimit\b", sql, re.I)
        return (f"{sql[:anchor.start()]}WHERE {cond} {sql[anchor.start():]}", True) if anchor else (sql, False)
    keep = [c for c in guard.split_conjuncts(m_w.group(1)) if not _CLASS_NM_CONJ.search(c)]
    return sql[:m_w.start()] + " WHERE " + " AND ".join([cond] + keep) + " " + sql[m_w.end():].lstrip(), True


_SELECT_PLAIN_ITEM = re.compile(r"(?:TRIM\(\s*)?([A-Za-z_]\w*)\s*\)?(?:\s+AS\s+(\w+))?", re.I)


@lru_cache(maxsize=1)
def _fund_col_types() -> dict[str, str]:
    """public_funds 컬럼 → SQL 타입(소문자). 스키마 원천(loader)에서 읽는다 — 하드코딩 아님."""
    return {c.lower(): (t or "").lower() for c, _, t, *_ in (getattr(_ev_ctx(), "schema", {}) or {}).get("public_funds", ())}


@lru_cache(maxsize=2)
def _class_dependent(numeric: bool = True) -> frozenset:
    """클래스 종속 컬럼 — 다클래스 펀드 그룹 중 값이 2종 이상인 비율이 30% 를 넘는 컬럼(DB 실측, 캐시).

    `numeric=True` 는 수치 컬럼(MIN~MAX 범위로 굽는다 — 6R F2), `False` 는 **문자 컬럼**이다.
    문자 클래스 종속 컬럼(`han_clas_nm` 0.985 · `han_clas_sales_channel` 0.856 …)은 펀드 단위 대표값이
    존재하지 않는다 — MAX 로 뽑으면 임의 클래스의 라벨이라 답변 재료가 아니다. 순자산·날짜는 별도 규칙.
    """
    types = _fund_col_types()
    num = ("numeric", "int", "real", "double", "float", "decimal")
    con = connect_readonly()
    out = set()
    try:
        for col, t in types.items():
            if t.startswith(num) != numeric or col.endswith("_dt") or col == "fd_nast_suma":
                continue
            row = con.execute(
                f"SELECT SUM(cnt > 1), COUNT(*) FROM (SELECT COUNT(DISTINCT {col}) AS cnt FROM public_funds "
                f"WHERE {col} IS NOT NULL GROUP BY {_FUND_GROUP_EXPR} HAVING COUNT(*) > 1)").fetchone()
            if row and row[1] and (row[0] or 0) / row[1] > 0.3:
                out.add(col)
    except sqlite3.Error:
        pass
    finally:
        con.close()
    return frozenset(out)


def _class_dependent_cols() -> frozenset:
    return _class_dependent(True)


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
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union|having)\b", sql, re.I):
        return sql, False
    # 🔴 7R M′/R′ — 불개입 사유에서 **HCX 의 모양 선택**(ORDER BY · SELECT 집계)을 뺀다. 6R 실측: S4 가 `ORDER BY itm_no ASC` 를,
    #    T14 가 `AVG(fd_nast_suma)` 를 쓰자 묶기가 통째로 비켜갔다(5R 은 HCX 가 그 모양을 안 써서 통과 — 비결정).
    #    개별 조회로 이미 판정된 뒤에 정렬·집계 선택을 존중할 근거가 없다: 정렬은 확정식 정렬로 덮고, 집계는 인자 컬럼만 꺼내 F2 로 재작성한다.
    #    GROUP BY 는 축을 본다 — `GROUP BY itm_no` 는 **클래스 단위 키**라 모든 그룹이 1이 되는 무의미한 축이므로 항상 교체 대상이고
    #    (6R V12 "모두 1개씩 … 총 30개" · W5 "1개"), 그 밖의 축(펀드키 묶기를 이미 마친 SQL 포함)은 종전대로 불개입이다.
    # 🔴 10R 부류 Z — GROUP BY 도 **확인하고 아니면 교체**한다. 종전엔 `GROUP BY itm_no` 한 형태만 교체 대상이라
    #    9R U2 처럼 HCX 가 위치 표기(`GROUP BY 1`)나 `or_co+mtco` 자작 키를 쓰면 가드가 자기를 껐다.
    #    교체 대상은 **펀드 식별 컬럼(또는 위치 표기)만으로 된 축**이다 — 분포·유형별 축은 답의 축이라 존중한다.
    m_grp = re.search(r"\bgroup\s+by\b(.*?)(?=\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if m_grp:
        gexpr = m_grp.group(1).strip()
        if gexpr in (_FUND_GROUP_EXPR, _FUND_KEY_EXPR):
            return sql, False                                   # 이미 펀드 단위로 묶었다
        gcols = {w.lower() for w in re.findall(r"[A-Za-z_]\w*", gexpr)} & set(_fund_col_types())
        if gcols - _FUND_ID_COLS or (not gcols and not re.fullmatch(r"[\d,\s]+", gexpr)):
            return sql, False
    # ORDER BY 는 **정렬 축**을 본다: 값 컬럼 정렬은 랭킹 의도라 종전대로 불개입(ensure_fund_rank_representative 담당),
    #   식별자·키·집계 별칭 정렬(S4 `ORDER BY itm_no ASC` · W5 `ORDER BY clas_count DESC`)은 모양 잡음이라 확정식 정렬로 덮는다.
    m_ord = _ORDER_BY_HEAD.search(sql)
    if m_ord and _fund_col_types().get(re.sub(r"^\w+\.", "", m_ord.group(1).strip()).lower()) is not None \
            and re.sub(r"^\w+\.", "", m_ord.group(1).strip()).lower() not in _FUND_ID_COLS:
        return sql, False
    # 4R 부류 M — 개별 조회의 판정은 "펀드를 하나로 특정하는 조건": 이름 LIKE **또는** 펀드 키 핀(rptt/itm_no/mtco 등호·IN — KG Fund 노드가
    #    코드를 핀한 정식명 질의 V4 'KB중국본토A주증권자투자신탁' → LIMIT 1 1클래스 답).
    if not (_has_name_filter(sql) or _has_fund_key_pin(sql)):
        return sql, False
    # `_LOOKUP_ROW_UNIT` 은 **값이 클래스마다 갈리는 질의**(보수·수수료)에만 불개입한다. '클래스' 는 개수·열거를 묻는 말이라
    #    펀드키 묶기가 정답이다 — 단, HCX 가 이미 펀드 단위로 물어보는 모양(GROUP BY itm_no)을 냈을 때만 개입해
    #    T6·R6 처럼 5R·6R 내내 통과한 열거 경로는 건드리지 않는다(동결선).
    if any(t in question for t in _LOOKUP_ROW_UNIT) or _CLASS_LIST_Q.search(question):
        return sql, False
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()]
    if "*" in re.sub(r"(?i)count\s*\(\s*\*\s*\)", "", head):
        return sql, False
    # 전체 집계 질의(GROUP BY 없는 COUNT — `펀드수/클래스수` 개수 답)는 개별 조회가 아니다.
    #   3R D(T11) '피델리티 이름이 들어간 공모펀드는 몇 개야?' 가 이름 필터를 갖고도 개수 답이어야 하는 자리다.
    if not m_grp and re.search(r"\bcount\s*\(", head, re.I):
        return sql, False
    sel = re.sub(r"^\s*select\s+(distinct\s+)?", "", head, flags=re.I)
    types = _fund_col_types()
    if not types:
        return sql, False
    # 🔴 14R 재검 ③-2 (부류 E) — **`COUNT(*) AS 클래스수` 의 모수는 값 컬럼 술어와 무관해야 한다.**
    #    S12 실측 교과서 사례: WHERE 의 `fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r > -100` 때문에
    #    클래스수가 NULL 수만큼 정확히 모자랐다(10→9 · 5→3 · 13→12). 수익률 NULL 은 신규 설정 클래스에서
    #    정상적으로 나오므로, 값 술어로 거르면 클래스수가 틀려지는 것이 데이터 구조상 필연이다.
    #    처방: 값 술어를 WHERE 에서 떼어 **집계 안쪽**(`MAX(CASE WHEN <술어> THEN col END)`)으로 옮긴다 —
    #    COUNT 는 기본모수 전체를 세고, 표시 범위(MIN~MAX)는 술어를 그대로 존중한다(HAVING 으로 옮기면
    #    걸러졌어야 할 클래스가 MIN 쪽에 들어온다).
    m_where = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    val_preds: dict[str, list[str]] = {}
    moved: list[str] = []
    if m_where:
        for c in guard.split_conjuncts(m_where.group(1)):
            mv = _VALUE_PRED.match(c.strip())
            if mv and (types.get(mv.group(1).lower()) or "").lower().startswith(("int", "real", "num", "dec", "float")):
                val_preds.setdefault(mv.group(1).lower(), []).append(c.strip().strip("()").strip())
                moved.append(c)

    def _agg(fn: str, col: str) -> str:
        p = val_preds.get(col)
        return f"{fn}(CASE WHEN {' AND '.join(p)} THEN {col} END)" if p else f"{fn}({col})"

    # 판매중클래스수 병기 (2026-09-02 리뷰 ②-7) — 이름 조회에 기본모수를 박으면 판매완료·사모 14,707행 개별 조회가
    # 0행 오거절이라 주입하지 않는 대신, "클래스 7개 중 판매중 7개" 재료를 0행 위험 없이 싣는다.
    new = ["MIN(itm_no) AS 대표_itm_no", "MIN(TRIM(itm_nm)) AS itm_nm", 'COUNT(*) AS "클래스수"',
           "SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS \"판매중클래스수\""]
    seen: set = set()
    for it in _split_select_items(sel):
        m = _SELECT_PLAIN_ITEM.fullmatch(it.strip())
        if m and types.get(m.group(1).lower()) is not None:
            pairs = [(m.group(1).lower(), m.group(2))]
        else:
            # 7R M′ — 집계·식 항목은 **인자 컬럼만** 꺼내 F2 규칙으로 다시 굽는다(T14 `AVG(fd_nast_suma)` → SUM).
            #    펀드 컬럼을 하나도 참조하지 않는 항목(`COUNT(*)`·리터럴)은 버린다 — 묶기가 클래스수를 이미 싣는다.
            pairs = [(c, None) for c in dict.fromkeys(w.lower() for w in re.findall(r"[A-Za-z_]\w*", it))
                     if types.get(c) is not None]
            if not pairs and m is None and not re.search(r"\b(?:count|sum|avg|min|max|total|cast|round)\s*\(|'", it, re.I):
                return sql, False          # 정체 모를 항목 — 종전대로 안전하게 불개입
    # (아래 루프 본문이 pairs 를 소비한다)
        for col, alias in pairs:
            if col in ("itm_no", "itm_nm") or col in seen:
                continue
            seen.add(col)
            t = types.get(col)
            if col == "fd_nast_suma":
                # 🔴 순자산은 SUM — 이 DB 의 fd_nast_suma 는 **클래스별 값**이라 펀드 순자산은 합계다 (2026-09-02 리뷰 ②-6 실측:
                #    코어테크 본체 10클래스 합 2조9,148억 vs 최대 클래스 7,348억 · 삼성MMF법인제1호 4클래스 12.4조/1,051억/…).
                #    정수 CAST 로 '.0' 노출을 없애고 억원을 직접 굽는다(자릿수 훼손 계열 — 021·022·031 재검과 같은 처방).
                new += [f"CAST({_agg('SUM', col)} AS INTEGER) AS fd_nast_suma",
                        f"CAST(ROUND({_agg('SUM', col)}/100000000.0) AS INTEGER) || '억원' AS \"순자산_억원\""]
            elif col in _FUND_RETURN_COLS or col in _class_dependent_cols():
                # 6R F2 — 클래스별로 값이 다른 컬럼(수익률·기준가·보수…)은 단일 MAX 로 대표하지 않는다: MIN~MAX 범위. 종속 여부는 DB 실측
                #   (다클래스 펀드에서 값이 갈리는 비율)로 판정 — X25: 종류A 라벨에 종류F 기준가가 붙었다
                new += [f'{_agg("MAX", col)} AS "{col}_최고"', f'{_agg("MIN", col)} AS "{col}_최저"']
            else:
                new.append(f"MAX({col}) AS {alias or col}")
    # 2R Q4-b — 대표예탁원번호(rptt_ksd_itm_no)를 **표시 단위**로만 싣는다: 조립기가 같은 대표번호 행을 한 줄로 접는다
    #    (R6 6행 → "클래스 7개" 1줄). 카운트·랭킹 gold 의 펀드키는 그대로다(리뷰 ④ 완화 ⓐ).
    new.append("MIN(rptt_ksd_itm_no) AS 대표번호")
    tail = sql[frm.start():].rstrip()
    # 7R M′ — HCX 의 GROUP BY(itm_no 축)·ORDER BY·LIMIT 은 확정식으로 덮어쓴다. 남겨 두면 두 번 붙어 문법이 깨진다.
    tail = re.sub(r"\blimit\s+\d+\s*$", "", tail, flags=re.I).rstrip()
    tail = re.sub(r"\border\s+by\b.*$", "", tail, flags=re.I | re.S).rstrip()
    tail = re.sub(r"\bgroup\s+by\b.*$", "", tail, flags=re.I | re.S).rstrip()
    if moved:
        m_t = re.search(r"\bwhere\b(.*)$", tail, re.I | re.S)     # tail 은 GROUP/ORDER/LIMIT 이 이미 잘려 있다
        if m_t:
            kept = [c for c in guard.split_conjuncts(m_t.group(1)) if c not in moved]
            tail = tail[:m_t.start()] + (" WHERE " + " AND ".join(kept) if kept else "")
    out = (f"SELECT {', '.join(new)} {tail} GROUP BY {_FUND_GROUP_EXPR} "
           f"ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT {MAX_ROWS}")
    # 🔴 14R 재검 ③-2 (부류 E) — **`COUNT(*) AS 클래스수` 의 모수는 값 컬럼 술어와 무관해야 한다.**
    #    S12 실측 교과서 사례: WHERE 의 `fd_yr1_ern_r IS NOT NULL` 때문에 클래스수가 NULL 수만큼 정확히
    #    모자랐다(10→9 · 5→3 · 13→12). 수익률 NULL 은 신규 설정 클래스에서 정상적으로 나오므로
    #    값 술어로 거르는 순간 클래스수가 틀려지는 것이 데이터 구조상 필연이다.
    #    랭킹 경로에 이미 도는 「값 술어를 WHERE→HAVING 으로」를 여기서도 부른다 — 단 **결측 술어만**
    #    옮긴다(방향 술어를 옮기면 MIN 쪽 표시값에 걸러졌어야 할 클래스가 들어온다).
    return out, True


# ── 개별 조회 답변 기계 조립 (2R Q4 — R4·S3·S4·S5·R6·S12) ──
def _qualify_fund_cols(expr: str, alias: str) -> str:
    """식 안의 비한정 public_funds 컬럼에 별칭을 붙인다 — JOIN 의 ambiguous 오류를 막는다(문자열 리터럴 제외)."""
    types = _fund_col_types()
    parts, out = _SQL_LITERAL.split(expr), []
    lits = _SQL_LITERAL.findall(expr)
    for i, seg in enumerate(parts):
        out.append(re.sub(r"(?<![\w.])([A-Za-z_]\w*)(?!\s*\()",
                          lambda m: f"{alias}.{m.group(1)}" if m.group(1).lower() in types else m.group(1), seg))
        if i < len(lits):
            out.append(lits[i])
    return "".join(out)


_ESTB_LOOKUP_COLS = ("최초설정일", "최근설정일")


def ensure_fund_estb_lookup(sql: str, question: str) -> tuple[str, bool]:
    """설정일 축 개별 조회를 **전용 확정식**으로 교체. (SQL, 교체했는지)

    🔴 10R KG 부류 E — 설정일 정본은 `ext_fund_page.estb_dt` 뿐인데, 그걸 실으려면 LEFT JOIN 이 따라오고
       `ensure_fund_lookup_grouping` 이 join 을 불개입 사유로 삼아 개별 조회 묶기가 통째로 꺼진다.
       그 결과 AA5 는 SELECT 에 없는 설정일을 **환각**했고(2011-06-20, gold 2011-03-22 · '약 12년' 은
       2011→2026 산술과도 모순), Z9 는 `LIMIT 1` 무정렬로 형제 펀드('청년소득공제')의 값을 답했다.
    처방(KG 심사관): 묶기 코드·산출 SQL 을 건드리지 않고 **설정일 축 질의만** 전용 확정식으로 바꾼다 —
    `MIN/MAX(e.estb_dt)` + 클래스수·판매중클래스수 병기 + `ORDER BY MIN(e.estb_dt)`.
    연도 질의('2025년에 설정된')는 `ensure_fund_estb_year`(목록 경로) 담당이라 여기 오지 않는다(중복 0).
    """
    if not _FUND_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I):
        return sql, False
    if not _ESTB_Q.search(question) or _YEAR_Q.search(question):
        return sql, False
    if not (_has_name_filter(sql) or _has_fund_key_pin(sql)) or _ESTB_LOOKUP_COLS[0] in sql:
        return sql, False
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        return sql, False
    where = _qualify_fund_cols(re.sub(r"\b\w+\.(?=\w)", "", m_w.group(1)).strip(), "p")
    key = _qualify_fund_cols(_FUND_GROUP_EXPR, "p")
    sel = ("MIN(p.itm_no) AS 대표_itm_no, MIN(TRIM(p.itm_nm)) AS itm_nm, COUNT(*) AS \"클래스수\", "
           "SUM(CASE WHEN p.sale_yn = '판매중' THEN 1 ELSE 0 END) AS \"판매중클래스수\", "
           "MIN(e.estb_dt) AS \"최초설정일\", MAX(e.estb_dt) AS \"최근설정일\", "
           "MIN(p.rptt_ksd_itm_no) AS 대표번호")
    return (f"SELECT {sel} FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no "
            f"WHERE {where} GROUP BY {key} ORDER BY MIN(e.estb_dt) ASC LIMIT {MAX_ROWS}"), True


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
    cut = m.group(1).strip() if m else (_STEM_CLASS_TAIL.sub("", n).strip() or n)
    # 🔴 14R gold ③-23 — 자르기가 괄호를 열어 둔 채 끝나거나(FND-001 7위 `신한BEST신종법인용MMFGS-2호(`)
    #    2자 이하로 줄면(10위 `하나`) 자르기를 취소한다. 표시 이름이 이름 구실을 못 한다.
    if cut.count("(") != cut.count(")") or cut.count("[") != cut.count("]") or len(cut) <= 2:
        return n
    return cut


def _fund_col_ko(col: str) -> str:
    """public_funds 컬럼의 한글명(스키마 원천) — 조립 문형의 라벨. 없으면 컬럼명."""
    for c, ko, *_ in (getattr(_ev_ctx(), "schema", {}) or {}).get("public_funds", ()):
        if c.lower() == col.lower():
            return ko or col
    return col


def _ymd_dash(v: str) -> str:
    return f"{v[:4]}-{v[4:6]}-{v[6:8]}"


def _since_text(v: str) -> str:
    """설정일부터 기준일까지의 기간 — 답변이 산술을 하지 않게 기계가 굽는다 (AA5: 2011→2026 을 '약 12년')."""
    y0, m0, d0 = int(v[:4]), int(v[4:6]), int(v[6:8])
    y1, m1, d1 = (int(x) for x in gate.DATA_CUTOFF.split("-"))
    months = (y1 - y0) * 12 + (m1 - m0) - (1 if d1 < d0 else 0)
    if months < 0:
        return "기준일 이후 설정"
    return f"약 {months // 12}년 {months % 12}개월" if months >= 12 else f"약 {months}개월"


def _pct(v: str) -> str:
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return s


def _fee_pct(v: float, already_percent: bool = False) -> str:
    """보수 값을 % 문자열로. ‰ 이면 ÷10 한다 — 마스터 보수 4종은 천분율 선언이다.

    2026-09-04 FND-005 실측: `0.015`(‰) 를 그대로 `0.015%` 로 적어 10배 틀렸다. yaml `보수단위` 규칙과
    answer_rules 두 곳에 적혀 있었는데도 답변기가 안 지켰다 — 말이 아니라 조립기가 환산해야 한다.
    🔴 다만 **환산은 한 번만** 일어나야 한다. 같은 규칙을 읽은 HCX 가 SQL 에서 이미
    `ROUND((…)/10.0, 4) AS "총보수_퍼센트"` 를 내면 조립기가 또 나눠 100배 작아진다(같은 날 서버 실측).
    `_pct` 는 소수 2자리라 0.0015 가 '0' 으로 뭉개진다 — 보수는 4자리로 남긴다."""
    return f"{v if already_percent else v / 10.0:.4f}".rstrip("0").rstrip(".") or "0"


def _fee_is_percent(sql: str, header: str, pos: int | None) -> bool:
    """그 값 열이 **이미 %** 인가 — 판정 기준은 **SQL 이 실제로 ÷10 을 했는가** 하나다.

    🔴 별칭 이름을 믿으면 안 된다. 2026-09-04 DOM-06 서버 실측:

        SELECT or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r AS "총보수_퍼센트"
        → 14.35                                            ↑ ÷10 이 없다. 값은 ‰ 다(=1.435%)

    별칭은 '퍼센트' 라고 말하는데 값은 천분율이다. 이름을 신뢰하면 조립기가 환산을 건너뛰어
    10배 틀린다. 그래서 **식을 본다** — 그 자리의 SELECT 항목이 10 으로 나눴을 때만 이미 % 다.
    자리를 못 찾을 때만(부질의·CTE 등) 별칭 이름을 마지막 단서로 쓴다.
    """
    frm = re.search(r"\bfrom\b", sql, re.I)
    if frm is not None and pos is not None:
        items = _split_select_items(re.sub(r"^\s*select\s+(distinct\s+)?", "", sql[:frm.start()], flags=re.I))
        if 0 <= pos < len(items):
            return re.search(r"/\s*10(?:\.0*)?\b", items[pos]) is not None
    return bool(re.search(r"퍼센트|percent|%", header or "", re.I))


def _lookup_answer(sql: str, rows: str, n: int, name_token: str | None = None,
                   ground_lines: list[str] | None = None) -> str | None:
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
    # 🔴 10R — 조립 문형이 "'X' 이름의 공모펀드 N개" 라 **개별 조회일 때만** 쓴다. 태그 ∪ 이름 목록(KG-021
    #    `prfd_attr_cds LIKE '%,TWN,%' OR itm_nm LIKE '%대만%'`)은 이름 조회가 아니다 — 종전엔 머리줄이
    #    "',TWN,' 이름의" 로 나갔다. 가드의 발동 판정(`_has_name_filter`)과 같은 술어를 쓴다(중복 0).
    if not (_has_name_filter(sql) or _has_fund_key_pin(sql)):
        return None
    recs = []
    for ln in lines[1:]:
        parts = [p.strip() for p in ln.split(" | ")]
        if len(parts) != len(cols):
            return None
        recs.append(dict(zip(cols, parts)))
    ret_cols = [c[:-3] for c in cols if c.endswith("_최고")]       # 수익률 8종 + F2 클래스 종속 컬럼(기준가·보수…)
    has_grade = "zrin_fd_ivst_risk_grd_nm" in cols or "zrin_fd_ivst_risk_gcd" in cols
    has_nast = "fd_nast_suma" in cols
    # 7R R′ — 클래스 **개수**만 묻는 질의(V12·W5)는 묶기 결과에 값 컬럼이 하나도 없다. 머리 4열 + 대표번호뿐이면
    #    그 자체가 답이므로 기계 조립한다("클래스 10개"). 값 컬럼이 따로 있는데 조립 문형이 없는 경우는 종전대로 HCX 에 넘긴다.
    # 🔴 10R(8R 보류 ③-1 의 짝) — **클래스 종속 문자 컬럼은 값 컬럼이 아니다.** `han_clas_nm`(수수료체계 이름)은
    #    펀드 단위 대표값이 없어 MAX 로 뽑아 봐야 임의 클래스의 라벨이다. 이것 하나 때문에 클래스 개수 질의가
    #    조립기를 못 받고 HCX 산문으로 갔다(W5 — HCX 가 7클래스를 세지 못했다). 판정은 DB 실측(`_class_dependent`).
    # 🔴 11R 재검 ③-1 (부류 AA) — **식별 컬럼도 잡음이다.** V12 회귀: SELECT 에 섞인 `MAX(mtco_itm_no)` 하나로
    #    class_only 판정이 꺼져 클래스 개수 질의가 조립기를 못 받고 HCX 산문으로 갔다. 식별 컬럼은 사용자가
    #    물은 값이 아니므로 조립을 막을 근거가 없다(`_FUND_ID_COLS` 는 이미 정의돼 있다).
    noise = {c for c in cols if c.lower() in _class_dependent(False) | _FUND_ID_COLS}
    has_estb = _ESTB_LOOKUP_COLS[0] in cols
    class_only = set(cols) - noise - set(_ESTB_LOOKUP_COLS) <= set(_LOOKUP_HEAD) | {"대표번호"}
    if not (ret_cols or has_grade or has_nast or has_estb or class_only):
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
            groups[key] = {"stem": stem, "n": 0, "m": 0, "grade": grade, "nast": 0, "eok": None, "estb": [],
                           "ret": {c: [None, None] for c in ret_cols}}
            order.append(key)
        g = groups[key]
        g["n"] += int(float(r["클래스수"] or 0))
        g["m"] += int(float(r["판매중클래스수"] or 0))
        if has_nast and r.get("fd_nast_suma"):
            g["nast"] += int(float(r["fd_nast_suma"]))
        # 🔴 14R 재검 ③-3 (부류 AD) — **금액을 억원으로 굽는 자리는 한 곳뿐이어야 한다.** SQL 이 이미
        #    `CAST(ROUND(SUM(fd_nast_suma)/1e8) AS INTEGER) || '억원'` 열을 구웠는데 조립기가 원 단위에서
        #    스스로 **절사** 나눗셈을 해 7문항이 1억씩 어긋났다(U1 1,911→1,912 · W11 3,344→3,345 · U11 2→3).
        #    구운 열이 있으면 그 값을 그대로 쓴다.
        raw_eok = (r.get("순자산_억원") or "").replace(",", "")
        if raw_eok.endswith("억원") and raw_eok[:-2].lstrip("-").isdigit():
            g["eok"] = (g["eok"] or 0) + int(raw_eok[:-2])
        g["estb"] += [v for c in _ESTB_LOOKUP_COLS for v in (r.get(c, "").strip(),) if re.fullmatch(r"\d{8}", v)]
        for c in ret_cols:
            lo, hi = r.get(f"{c}_최저", ""), r.get(f"{c}_최고", "")
            if lo != "" and hi != "":
                cur = g["ret"][c]
                g["ret"][c] = [float(lo) if cur[0] is None else min(cur[0], float(lo)),
                               float(hi) if cur[1] is None else max(cur[1], float(hi))]
    pop = "공모펀드" if re.search(r"prvo_pbff_desc\s*=\s*'공모'", sql, re.I) else "펀드"
    token = name_token
    if not token:
        # 🔴 10R — **itm_nm 의 리터럴만** 이름으로 쓴다. 종전엔 아무 LIKE 리터럴이나 집어 태그 코드가
        #    머리줄에 이름처럼 실렸다(KG-021 "',TWN,' 이름의 공모펀드").
        m_like = re.search(r"(?:REPLACE\(\s*(?:\w+\.)?itm_nm\s*,[^)]*\)|TRIM\(\s*(?:\w+\.)?itm_nm\s*\)"
                           r"|\b(?:\w+\.)?itm_nm\b)\s*(?:LIKE|GLOB)\s+'[%*]?([^'%*]+)[%*]?'", sql, re.I)
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
            if c in _RET_LABEL:
                label, unit, tail_note = f"{_RET_LABEL[c]} 수익률", "%", ", 누적"
                fmt = _pct
            else:
                label, unit, tail_note = _fund_col_ko(c), "", ""
                fmt = lambda v: f"{v:,.2f}".rstrip("0").rstrip(".")
            if lo is None:
                parts.append(f"{label} 미수록")
            elif lo == hi:
                parts.append(f"{label} {fmt(lo)}{unit}" + (" (누적)" if tail_note else ""))
            else:
                parts.append(f"{label} {fmt(lo)}{unit}~{fmt(hi)}{unit} (클래스에 따라 다름{tail_note})")
        if has_grade:
            nm, gcd = g["grade"]
            if gcd:
                parts.append(f"위험등급 {int(float(gcd))}등급" + (f"({nm})" if nm else ""))
            elif nm:
                parts.append(f"위험등급 {nm}")
            else:
                parts.append("위험등급 미수록")
        if has_nast:
            # 구운 열이 없을 때만 조립기가 굽고, 그때도 ROUND(절사 아님 — 재검 ③-3)
            eok = g["eok"] if g["eok"] is not None else (g["nast"] + 50_000_000) // 100_000_000
            parts.append(f"순자산 {eok:,}억원 (클래스 합계)")
        if has_estb:
            # 설정일은 **최초 클래스 기준**이다(뒤에 나온 클래스의 설정일은 그 클래스의 것). 기간은 기준일까지로 센다.
            parts.append(f"설정일 {_ymd_dash(min(g['estb']))} ({_since_text(min(g['estb']))})"
                         if g["estb"] else "설정일 미수록")
        tail = f"클래스 {g['n']}개" + ("(전부 판매중)" if g["m"] == g["n"] else f", 판매중 {g['m']}개")
        out.append(f"- {g['stem']}: " + " · ".join(parts + [tail]))     # 값 컬럼이 없는 개수 질의(V12·W5)는 앞이 비어 빈칸이 생겼다
    notes = ground_notes(ground_lines or [])
    if notes:
        out += [""] + notes                       # S1: 구상호·후계 법인 주석
    return "\n".join(out)


def _list_answer(sql: str, rows: str, n: int) -> str | None:
    """순자산순 펀드 목록(ensure_fund_list_grouping 형)의 답변을 기계 조립한다. 아니면 None. HCX 0회.

    2026-09-02 2R — 커버리지 가드가 "(전체 560행/248펀드 중 30펀드 표시)" 를 구웠는데 R3 는 5행·S7 은 10행만 옮기고
    "일부입니다", S6 는 30행을 다 옮기고도 총량 대신 "더 많은 펀드가 있을 수 있습니다". 목록 전사는 분포(FND-038)와 같은
    결론 — LLM 에 맡길 수 없다. 발동: SQL 에 `GROUP BY 펀드키` + `ORDER BY fd_nast_suma DESC`, 헤더에 itm_nm·클래스수·순자산_억원.
    """
    if n < 1 or f"GROUP BY {_FUND_GROUP_EXPR}" not in sql or not re.search(r"\border\s+by\s+fd_nast_suma\s+desc\b", sql, re.I):
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
    # 🔴 16R 재검 ③-1 (부류 AE) — 사후 접기 제거. 접기는 SQL 의 `GROUP BY _FUND_GROUP_EXPR` 이 이미 했다.
    #    사후 접기는 LIMIT 뒤에서 돌아 클래스수를 과소 집계했고, rptt 가 섞인 그룹에서 다른 펀드를 흡수했다(T10).
    shown = len(recs)
    cov = _coverage_counts(sql)
    pop = "공모펀드" if re.search(r"prvo_pbff_desc\s*=\s*'공모'", sql, re.I) else "펀드"
    # 4R ④-3 — 목록의 순자산 축은 대표 클래스(MAX) 기준(개별 조회는 SUM). 리드 판정 전엔 축을 바꾸지 않고 머리줄에 고지만.
    basis = f"기준일 {gate.DATA_CUTOFF}, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위·순자산 = 대표 클래스 기준(MAX)"
    # 🔴 16R 재검 ③-1/③-5 — 「전체 N개」는 펀드키 축(6R gold 통과분) 유지, 병기하는 「대표번호 기준 M건」은
    #    **화면 행 수가 아니라 전체값**(COUNT(DISTINCT rptt))이다. 상위 K 만 보였으면 그 사실을 함께 적는다.
    rptt_all = cov[2] if cov else None
    rptt_note = f"(대표번호 기준 {rptt_all:,}건)" if rptt_all is not None and cov[1] != rptt_all else ""
    if cov and cov[1] is not None and (rptt_all or cov[1]) > shown:
        head = (f"조건에 해당하는 {pop}는 전체 {cov[1]:,}개(클래스 {cov[0]:,}개){rptt_note}이며, "
                f"순자산 상위 {shown}개 표시는 다음과 같습니다 ({basis}).")
    else:
        total = f"(클래스 {cov[0]:,}개)" if cov else ""
        head = (f"조건에 해당하는 {pop}는 전체 {cov[1] if cov and cov[1] is not None else shown:,}개{total}{rptt_note}이며, "
                f"순자산 순으로 다음과 같습니다 ({basis}).")
    out = [head, ""]
    for i, r in enumerate(recs, 1):
        eok = r.get("순자산_억원", "")
        eok_txt = f"{int(eok.replace('억원', '')):,}억원" if eok.endswith("억원") and eok[:-2].lstrip("-").isdigit() else (eok or "미수록")
        out.append(f"{i}. {_fund_stem(r['itm_nm'])}: 순자산 {eok_txt} · 클래스 {int(float(r['클래스수'] or 0))}개")
    return "\n".join(out)


_HEAD_SKIP_COLS = frozenset({"sale_yn", "prvo_pbff_desc"}) | _FUND_ID_COLS


def _rank_filter_labels(sql: str) -> list[str]:
    """WHERE 의 값 필터를 사람이 읽는 라벨로 — `zrin_fd_ivst_risk_grd_nm='매우 낮은 위험'` → '매우 낮은 위험'.
    라벨은 스키마 한글명(loader 원천)에서 가져온다 — 이름 하드코딩 0. 모수·식별자 컬럼은 뺀다(이미 머리줄에 있다)."""
    out: list[str] = []
    types = _fund_col_types()
    # 🔴 14R gold ③-11 — ⓐ **무따옴표 수치 리터럴**(`zrin_fd_ivst_risk_gcd = 1.0`)도 읽는다. FND-002 실측:
    #    머리줄이 코드값 `1.0` 을 그대로 써 must_include `매우 높은 위험` 을 놓쳤다.
    numeric = [(c.lower(), [lit]) for c, lit in _BARE_NUM_EQ.findall(sql)]
    for col, lits in ([(c.lower(), [lit]) for _t, c, lit in guard._EQ.findall(sql)]
                      + [(c.lower(), guard._LIT.findall(body)) for _t, c, body in guard._IN.findall(sql)]
                      + numeric):
        if col in _HEAD_SKIP_COLS or types.get(col) is None or not lits:
            continue
        # ⓑ 코드 컬럼에 짝 이름 컬럼이 있으면 **이름 값**으로 라벨을 만든다(DB 실측 1회 — 이름 하드코딩 0)
        named = [_code_value_label(col, l) or l for l in lits]
        txt = "·".join(dict.fromkeys(named))
        # 값이 한글이면 그 자체가 라벨이다('매우 낮은 위험'·'주식형') — 코드 값일 때만 컬럼 한글명을 앞에 붙인다
        label = txt if re.search(r"[가-힣]", txt) else f"{_fund_col_ko(col)} {txt}"
        if label not in out:
            out.append(label)
    return out


# 무따옴표 수치 등호 — `zrin_fd_ivst_risk_gcd = 1.0` (guard._EQ 는 따옴표 리터럴만 본다)
_BARE_NUM_EQ = re.compile(r"\b(?:\w+\.)?(\w+)\s*=\s*(-?\d+(?:\.\d+)?)(?![\d.\w])")
# 코드 컬럼 → 짝 이름 컬럼의 접미 규약(스키마 명명 규칙 · 이름 하드코딩 0)
_CODE_NAME_SUFFIX = (("_gcd", "_grd_nm"), ("_gcd", "_nm"), ("_cd", "_nm"), ("_cds", "_nms"))


@lru_cache(maxsize=256)
def _code_value_label(col: str, lit: str) -> str | None:
    """코드 컬럼의 리터럴에 대응하는 **짝 이름 컬럼의 값** — DB 실측 1회. 없으면 None."""
    types = _fund_col_types()
    for a, b in _CODE_NAME_SUFFIX:
        if not col.endswith(a):
            continue
        sib = col[:-len(a)] + b
        if types.get(sib) is None:
            continue
        con = connect_readonly()
        try:
            row = con.execute(f"SELECT {sib} FROM public_funds WHERE {col} = CAST(? AS REAL) "
                              f"AND {sib} IS NOT NULL LIMIT 1", (lit,)).fetchone()
        except sqlite3.Error:
            row = None
        finally:
            con.close()
        if row and str(row[0]).strip():
            return str(row[0]).strip()
    return None


def _fund_rank_answer(sql: str, rows: str, n: int) -> str | None:
    """펀드 랭킹(대표행 가드 산출형)의 답변을 기계 조립한다. 아니면 None. HCX 0회.

    8R ③-10(F6″-b) — 값은 gold 전수인데 서술에서 감점이 나던 자리다. 7R 실측: SELECT 에 `클래스수` 가 실려 있는데
    HCX 가 옮기지 않았고(R7·S1·V16·Y1·Y3·Y4·Y5 = G-1), 순자산 랭킹은 MAX/SUM 축을 고지하지 않았으며(Y2·U13),
    머리 이름이 **클래스명**('… 종류Ce')이라 펀드가 아니라 클래스를 답한 것처럼 읽혔다. 게다가 HCX 산문 경로에만
    남은 꼬리 결함(S1 면책 · Y3 기준일 8/21 날조 + '모든 클래스를 합하여' 방법론 날조 · Y1 추측)이 매 라운드 재발했다.
    기계 조립은 HCX 를 안 부르므로 그 꼬리가 **구조적으로** 사라진다(S4·T14 가 64s→2.9s 로 준 것과 같은 효과).

    발동: ① `GROUP BY <펀드키>` ② 헤더에 이름 열(itm_nm 또는 TRIM(itm_nm))과 `클래스수` ③ ORDER BY 첫 키가
    랭킹 컬럼(수익률 8종·순자산). `_lookup_answer`(대표_itm_no 머리 4열)·`_list_answer`(리터럴 itm_nm)와 헤더로 배타다.
    """
    if n < 1 or f"GROUP BY {_FUND_GROUP_EXPR}" not in sql:
        return None
    lines = rows.splitlines()
    if len(lines) != n + 1:
        return None
    cols = [c.strip() for c in lines[0].split(" | ")]
    if "클래스수" not in cols:
        return None
    name_i = next((i for i, c in enumerate(cols) if c in ("itm_nm", "TRIM(itm_nm)", "TRIM(itm_nm) AS itm_nm")), None)
    target = _fund_sort_target(sql)
    if name_i is None or not target:
        return None
    col, direction = target
    cls_i = cols.index("클래스수")
    if col == "fd_nast_suma":
        val_i = next((i for i, c in enumerate(cols) if _DISPLAY_UNIT.search(c)), None)
        label = "순자산"
        # 실제 SQL 이 쓴 축을 그대로 고지한다 — 축이 바뀌면 순위가 바뀐다(U13 🟡 의 지적)
        axis = "클래스 합계(SUM)" if re.search(r"\bsum\s*\(\s*(?:\w+\.)?fd_nast_suma", sql, re.I) else "대표 클래스 기준(MAX)"
    elif col in _FUND_FEE_COLS:
        # 보수는 별칭(total_commission)으로 나오는 일이 잦아 컬럼명으로 못 찾는다 — ORDER BY 자리로 잡는다
        val_i = cols.index(col) if col in cols else _order_by_select_pos(sql)
        label = "총보수" if all(re.search(rf"\b{c}\b", sql, re.I) for c in _FUND_FEE_COLS) else _fund_col_ko(col)
        axis = "클래스 최고값(MAX)" if direction == "DESC" else "클래스 최저값(MIN)"
    else:
        val_i = cols.index(col) if col in cols else _order_by_select_pos(sql)
        label = f"{_RET_LABEL[col]} 수익률" if col in _RET_LABEL else _fund_col_ko(col)
        axis = "클래스 최고값(MAX)" if direction == "DESC" else "클래스 최저값(MIN)"
    if val_i is None:
        return None
    pop = "공모펀드" if re.search(r"prvo_pbff_desc\s*=\s*'공모'", sql, re.I) else "펀드"
    basis = [w for w, pat in (("판매중", r"sale_yn\s*=\s*'판매중'"), ("공모", r"prvo_pbff_desc\s*=\s*'공모'"))
             if re.search(pat, sql, re.I)]
    # 🔴 10R gold N3 — **WHERE 의 사람이 읽는 조건을 머리줄에 함께 굽는다.** 8R 기계 조립은 정렬축·모수만
    #    구웠고 값 필터는 안 구워서, HCX 작문 경로에 있던 '매우 낮은 위험'·'매우 높은 위험' 조건이 답변에서
    #    새로 사라졌다(FND-001·002·UNANS-006). 라벨은 스키마 한글명(원천)에서 가져온다.
    scope = ("·".join(basis + _rank_filter_labels(sql)) + " 기준, " if (basis or _rank_filter_labels(sql)) else "") + \
        f"펀드 = 대표예탁원번호 기준·클래스 = 판매 단위, {label} = {axis}, 기준일 {gate.DATA_CUTOFF}"
    out = [f"{label} {'상위' if direction == 'DESC' else '하위'} {n}개 {pop}입니다 ({scope}).", ""]
    fee_pct_already = col in _FUND_FEE_COLS and _fee_is_percent(sql, cols[val_i], val_i)
    extreme = False
    for i, ln in enumerate(lines[1:], 1):
        parts = [p.strip() for p in ln.split(" | ")]
        if len(parts) != len(cols):
            return None
        raw = parts[val_i]
        if col == "fd_nast_suma":
            num = raw[:-2] if raw.endswith("억원") else raw
            val = f"{int(num):,}억원" if num.lstrip("-").isdigit() else (raw or "미수록")
        elif col in _FUND_FEE_COLS:
            try:
                val = f"{_fee_pct(float(raw), fee_pct_already)}%"
            except ValueError:
                return None
        else:
            try:
                f = float(raw)
            except ValueError:
                return None
            extreme = extreme or abs(f) >= 100
            val = f"{_pct(f)}%"
        try:
            k = int(float(parts[cls_i] or 0))
        except ValueError:
            return None
        out.append(f"{i}. {_fund_stem(parts[name_i])}: {label} {val} · 클래스 {k}개")
    if extreme:
        # ontology/enums/public_funds.yaml `수익률극단값` — 8기간 수익률은 전부 누적이고 100% 초과 행에는 주의 문구를 붙인다
        out += ["", "※ 수익률 8기간 컬럼은 모두 누적 수익률이며 연 환산이 아닙니다. 100%를 넘는 값은 "
                    "파생·레버리지 전략에서 나오므로 손실도 같은 배율로 커질 수 있습니다."]
    return "\n".join(out)


_BOND_AXIS_KO = {"applied_yield": ("수익률", "높은 순", "낮은 순"), "after_tax_yield": ("세후수익률", "높은 순", "낮은 순"),
                 "corp_pretax_yield": ("법인 세전수익률", "높은 순", "낮은 순"), "srfc_irt": ("표면금리", "높은 순", "낮은 순"),
                 "buy_yield": ("매수수익률", "높은 순", "낮은 순"), "mat_dt": ("만기", "긴 순", "짧은 순"),
                 "remaining_days": ("잔존만기", "긴 순", "짧은 순"), "dur": ("듀레이션", "긴 순", "짧은 순"),
                 "eval_price": ("평가가", "높은 순", "낮은 순"), "isu_bal_amt": ("발행잔액", "많은 순", "적은 순")}
# 2026-09-03 서버 실측: SELECT * 결과를 그대로 옮겨 dirty·ndy_*·코드값(exrt_grte_ern_r_tcd 04)·pd_std_info_update 까지 노출.
#   사용 금지(dirty·ndy_dirty·avg_annual_tax_yield·buyable_quantity)·익일·내부 컬럼은 숨기고, 범주 컬럼은 한글 라벨로.
_BOND_HIDE = {"pd_no", "pd_risk_gcd", "curr_cd", "info_base_dt", "info_seq", "pd_exg_mkt",
              "dirty", "ndy_dirty", "ndy_eval_price", "ndy_applied_yield", "ndy_dur", "ndy_cov", "cov",
              "avg_annual_tax_yield", "buyable_quantity", "exrt_grte_ern_r", "exrt_grte_ern_r_tcd", "exrt_rpy_r",
              "pd_std_info_update", "pd_ctry_cd", "bdbns_abl_chnl_tcd", "sale_yield_base_dt", "exg_close_price_base_dt",
              "pd_abrv_nm", "pd_eng_nm", "pd_abrv_eng_nm", "crd_grd_dt"}
_BOND_COL_KO = {"bd_knd": "종류", "bd_inrt_tcd": "금리구분", "bd_intp_tcd": "이자지급", "bd_ofr_tcd": "모집",
                "std_pd_mcls_nm": "대분류", "std_pd_scls_nm": "소분류", "pd_pen_tr_yn": "퇴직연금편입", "isu_dt": "발행일",
                "bd_tisu_a": "총발행액", "isu_bal_amt": "발행잔액", "eval_price": "평가가", "trade_price": "매매단가",
                "dur": "듀레이션", "exg_close_price": "장내종가", "exg_close_yield": "장내종가수익률",
                "bdbns_abl_chnl_nm": "판매채널"}
_BOND_YIELD_COLS = ("applied_yield", "after_tax_yield", "corp_pretax_yield", "buy_yield", "srfc_irt")


def _fmt_ymd(v: str) -> str:
    s = v.strip().rstrip("0").rstrip(".") if re.fullmatch(r"\d{8}\.0+", v.strip()) else v.strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if re.fullmatch(r"\d{8}", s) else (s or "미수록")


def _bond_list_answer(sql: str, rows: str, n: int, question: str) -> str | None:
    """채권 목록(정렬 랭킹·조건 목록)의 답변을 기계 조립한다. 아니면 None. HCX 0회.

    2026-09-02 서버 실측(재배포 후): '수익률 높은 채권 추천해줘' — SQL·5행은 정확했는데 답변기가 "6% 초과라 추천이 어렵다" 며
    **종목명을 하나도 옮기지 않고**, 조회 결과에 없는 '6등급 최고 6.23%' 를 규칙 문구에서 끌어와 답했다. 주의 문구 규칙은 목록에
    붙이는 문장인데 목록 자체를 대체했다 — 분포(FND-038)·펀드 목록(R3)과 같은 결론: 목록 전사는 LLM 에게 맡길 수 없다.
    발동(전부): ① domestic_bonds 단독(JOIN·UNION·서브쿼리 없음) ② SELECT 에 집계 없음 ③ 헤더에 pd_nm ④ 1행 이상 ≤ 상한.
    머리줄: 커버리지(전체 N종목 중 상위 k) · 정렬 축·방향 · 기준일. 본문: 결과 행 그대로(수익률·신용등급·만기·잔존·구조/보강 열).
    꼬리: 규칙의 조건부 문구만 — 6% 초과·2/3등급이 있을 때 원금 주의, 추천 질의면 고위험(1등급)·사모 제외 고지(SQL 에 그 절이 있을 때만)."""
    if "domestic_bonds" not in sql or n < 1 or re.search(r"\b(?:join|union)\b|\(\s*select\b", sql, re.I):
        return None
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm or re.search(r"\b(?:COUNT|SUM|AVG|TOTAL|GROUP_CONCAT)\s*\(", sql[:frm.start()], re.I):
        return None
    lines = rows.splitlines()
    if len(lines) != n + 1:
        return None
    cols = [c.strip() for c in lines[0].split(" | ")]
    if "pd_nm" not in cols:
        return None
    recs = []
    for ln in lines[1:]:
        parts = [p.strip() for p in ln.split(" | ")]
        if len(parts) != len(cols):
            return None
        recs.append(dict(zip(cols, parts)))
    # 행 앞머리에 오는 값은 정렬 축이다 — SELECT 에 applied_yield 와 srfc_irt 가 함께 오면 고정 순서상
    # 수익률이 앞에 서서 '표면금리 높은 순' 머리줄과 어긋난다 (2026-09-04). ORDER BY 컬럼을 먼저 본다.
    osort = re.search(r"\bORDER\s+BY\s+(?:MAX|MIN)?\(?\s*([A-Za-z_]\w*)", sql, re.I)
    scol = osort.group(1).lower() if osort else None
    ycol = (scol if scol in _BOND_YIELD_COLS and scol in cols else
            next((c for c in _BOND_YIELD_COLS if c in cols), None))
    star = bool(re.search(r"\bSELECT\s+(?:DISTINCT\s+)?\*", sql, re.I))
    # 정렬 축 — ORDER BY 첫 키(MAX/MIN 감싼 대표행 형 포함)
    axis_txt = ""
    # 방향은 `\s*` 로 받는다 — `ORDER BY srfc_irt DESC`(감싸지 않은 형)에서 앞의 `\s*` 가 공백을 먹어
    # `\s+(ASC|DESC)` 가 빗나가면 DESC 목록이 '낮은 순' 으로 뒤집혀 나간다 (2026-09-04)
    m = re.search(r"\bORDER\s+BY\s+(?:MAX|MIN)?\(?\s*([A-Za-z_]\w*)\s*\)?\s*(ASC|DESC)?", sql, re.I)
    if m and m.group(1).lower() in _BOND_AXIS_KO:
        name, hi, lo = _BOND_AXIS_KO[m.group(1).lower()]
        axis_txt = f"{name} {hi if (m.group(2) or 'ASC').upper() == 'DESC' else lo}"
    cov = _bond_coverage_counts(sql)
    total = cov[1] if cov else None
    basis = f"기준일 {gate.DATA_CUTOFF}"
    # 만기 창을 머리줄에 굽는다 — 창이 틀리면 사용자가 바로 본다 (2026-09-03 #51: '내년' 이 2028~2029 로 나갔는데 어디에도 안 보였다)
    mw = _MAT_BETWEEN.search(sql)
    me = re.search(r"\bmat_dt\s*=\s*(\d{8})", sql, re.I)
    if mw:
        basis = f"만기 {_fmt_ymd(mw.group(1))}~{_fmt_ymd(mw.group(2))} · 질문 시점 {gate.DATA_CUTOFF} 기준"
    elif me:
        basis = f"만기 {_fmt_ymd(me.group(1))} · 질문 시점 {gate.DATA_CUTOFF} 기준"
    if total and total > n:
        head = (f"조건에 해당하는 채권은 전체 {total:,}종목이며, {axis_txt + ' ' if axis_txt else ''}상위 {n}개는 다음과 같습니다 ({basis})."
                if axis_txt else f"조건에 해당하는 채권은 전체 {total:,}종목이며, 그중 {n}개는 다음과 같습니다 ({basis}).")
    else:
        head = (f"조건에 해당하는 채권 {n}종목을 {axis_txt}으로 정렬했습니다 ({basis})." if axis_txt
                else f"조건에 해당하는 채권은 {n}종목입니다 ({basis}).")
    out = [head, ""]
    warn = False
    for i, r in enumerate(recs, 1):
        bits = []
        if ycol and r.get(ycol):
            try:
                yv = float(r[ycol])
            except ValueError:
                yv = None
            # 0 은 결측(주최 공지: 0·빈값은 의도된 값 → "없다" 로) — 2026-09-02 전환사채 목록에 "수익률 0.0%" 가 값처럼 나감
            bits.append(f"{_BOND_AXIS_KO.get(ycol, (ycol,))[0]} {'미수록' if yv == 0 else r[ycol] + '%'}")
        # 원금 주의 문구의 기준은 수익률이다(고위험제외 규칙: applied_yield > 6% 또는 위험등급 2·3등급).
        # 정렬 축이 표면금리여도 표면금리 7.5%(수익률 4.08%)에 위험 문구를 붙이지 않는다 (2026-09-04)
        for c in ("applied_yield", "after_tax_yield", "corp_pretax_yield", "buy_yield"):
            if c in cols and r.get(c):
                try:
                    warn = warn or float(r[c]) > 6
                except ValueError:
                    pass
        for c in _BOND_YIELD_COLS:
            if c != ycol and c in cols and r.get(c):
                bits.append(f"{_BOND_AXIS_KO.get(c, (c,))[0]} {r[c]}%")
        if "crd_grd" in cols:
            bits.append(f"신용등급 {r['crd_grd']}" if r.get("crd_grd") else "신용등급 미수록")
        if "pd_risk_nm" in cols and r.get("pd_risk_nm"):
            bits.append(f"위험등급 {r['pd_risk_nm']}")
        if r.get("pd_risk_gcd") in ("12", "13"):
            warn = True
        if "mat_dt" in cols and r.get("mat_dt"):
            bits.append(f"만기 {_fmt_ymd(r['mat_dt'])}")
            # 영구채(신종자본증권)의 mat_dt 는 1차 콜행사개시일 — answer_rules 의 '만기일 = 콜 개시일' 병기를 조립기가 보장한다
            # (2026-09-03 서버 실측: '신종자본증권 중 만기 가장 짧은' 답에 이 단서가 빠짐 — '구조' 열이 SELECT 에 없을 때의 사각)
            if re.search(r"신종|영구", r.get("pd_nm", "")):
                bits.append("만기일 = 콜 개시일(영구채)")
        if "remaining_days" in cols and r.get("remaining_days"):
            bits.append(f"잔존 {r['remaining_days']}")
        if "pd_pbcm" in cols and r.get("pd_pbcm"):
            bits.append(f"발행사 {r['pd_pbcm']}")
        # SELECT * 는 58컬럼 전부가 오므로 위 핵심 항목만 보이고 나머지는 옮기지 않는다(2026-09-03 BAC 행 실측)
        for c in ([] if star else cols):
            if c in _BOND_HIDE or c in ("pd_nm", "crd_grd", "pd_risk_nm", "mat_dt", "remaining_days", "pd_pbcm") or c in _BOND_YIELD_COLS:
                continue
            if r.get(c):
                bits.append(f"{_BOND_COL_KO.get(c, c)} {r[c]}")
        out.append(f"{i}. {r['pd_nm']}" + (" — " + " · ".join(bits) if bits else ""))
    tail = []
    if "remaining_days" in cols and any(r.get("remaining_days") for r in recs):
        # 컬럼 원값을 그대로 보이되 산출 기준일을 밝힌다 — 재계산하지 않는다(심사 gold 는 제공 컬럼값에서 나올 가능성이 높다 · 2026-09-03 결정)
        tail.append(f"잔존일수는 데이터 산출일 {gate.SNAPSHOT_DATE} 기준 값입니다(질문 시점 {gate.DATA_CUTOFF} 보다 3일 앞).")
    if warn:
        tail.append("수익률이 높은 채권은 원금을 돌려받지 못할 위험도 높을 수 있습니다. 신용등급·위험등급을 함께 확인하세요.")
    # 목록 안에 1차 축 동률이 있으면 무엇으로 갈랐는지 밝힌다 — 2차 키 없이 나간 순서는 재현되지 않는다
    # (2026-09-04 #62: 표면금리 7.5% 두 종목의 1·2위가 실측마다 뒤바뀜). ⛑ ensure_tie_break 가 SQL 쪽을 고정한다.
    if ycol and _ORDER_TIE_KEYS.search(sql):
        vals = [r.get(ycol) for r in recs if r.get(ycol)]
        if len(vals) != len(set(vals)):
            tail.append(f"{_BOND_AXIS_KO.get(ycol, (ycol,))[0]} {TIE_BREAK_NOTE}")
    # 이자유형분리로 축을 좁혔으면 그 사실을 밝힌다 — 모수가 그만큼 줄어든 목록이다 (gold BND-D-012 must_include '고정금리')
    if (_ORDER_SRFC.search(sql) and re.search(r"bd_intp_tcd\s*\)?\s*=\s*'이표채'", sql)
            and re.search(r"bd_inrt_tcd\s*\)?\s*=\s*'고정금리'", sql)):
        tail.append(COUPON_SPLIT_NOTE)
    if _RECO_Q.search(question) and "pd_risk_gcd <> '11'" in sql and "bd_ofr_tcd <> '사모'" in sql:
        tail.append("위험등급이 매우 높은(1등급) 채권과 사모 채권은 제외했습니다.")
    if tail:
        out += ["", " ".join(tail)]
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
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:join|union|having)\b", sql, re.I):
        return sql, False
    if _has_name_filter(sql) or "클래스" in question:
        return sql, False
    # 🔴 16R 재검 ③-1 — **주입만이 아니라 이관이다.** 이미 `GROUP BY _FUND_KEY_EXPR` 로 묶인 목록(HCX 가 옛
    #    형태를 그대로 복사해 오는 경로)도 rptt 축으로 옮긴다. 축이 둘로 갈리면 조립기가 꺼진다.
    if f"GROUP BY {_FUND_KEY_EXPR}" in sql:
        return sql.replace(f"GROUP BY {_FUND_KEY_EXPR}", f"GROUP BY {_FUND_GROUP_EXPR}"), True
    if re.search(r"\b(?:group\s+by|order\s+by)\b", sql, re.I):
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
    # 🔴 16R 재검 ③-1 (부류 AE) — **접기는 표시 층이 아니라 SQL 층에서 한다.** 14R 의 `MIN(rptt)` 사후 접기는
    #    ⓐ 한 `_FUND_KEY_EXPR` 그룹 안에 rptt 가 섞여 있으면 대표값 하나로 접어 **다른 펀드를 흡수**했고
    #      (T10 실측: 미래에셋삼바브라질 13억·5클래스가 mtco 0263021 공유로 하이인컴채권에 흡수돼 사라졌다)
    #    ⓑ `LIMIT` 이 접기보다 **먼저** 걸려 클래스수가 과소하게 나왔다(R3·S6·S7·T5·T13, S7 은 펀드 통째 누락).
    #    묶기 축을 랭킹·개별 조회가 12R 에 이미 옮긴 `_FUND_GROUP_EXPR`(rptt) 로 통일하면 LIMIT 이 접기 위에 걸린다.
    add = ('COUNT(*) AS "클래스수"'
           + (", MAX(fd_nast_suma) AS fd_nast_suma" if "fd_nast_suma" not in head else ""))
    return (f"{head.rstrip()}, {add} {body} GROUP BY {_FUND_GROUP_EXPR} ORDER BY fd_nast_suma DESC {lim}").rstrip(), True


# ── 답변 입력 조립 3종 (2026-09-02 R3 재검 — 목록 답변의 총량 병기·내부 코드 숨김·이름 전사 교정) ──
_HIDE_FROM_ANSWER = {"prfd_attr_cds"}      # 내부 태그 코드(C101·M109…) — 근거컬럼 가드는 명칭(zrin_attr_nms)을 병기하므로 답변 재료가 아니다
_RAW_AMOUNT_COL = re.compile(r"nast_suma|last_aum", re.I)   # 원 단위 금액 컬럼·집계 별칭 — 억원 병기가 있으면 답변 입력에서 숨긴다 (3R B-4)
_SIMPLE_FROM_WHERE = re.compile(r"\bfrom\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", re.I | re.S)


def _coverage_counts(sql: str) -> tuple[int, int | None, int | None, bool] | None:
    """LIMIT 에 잘린 목록의 전체 규모 — (전체 행수, 펀드수|None, 대표번호수|None, 펀드 단위로 묶인 SQL 인지).
    단순 SELECT 가 아니면 None.

    SQLite 재실행 1회·HCX 0회. public_funds 단독이면 펀드키 DISTINCT 도 센다. GROUP BY 는 펀드키 묶기
    (ensure_fund_list_grouping·lookup_grouping·대표행 가드가 만든 형태)만 허용 — 그때 표시 행은 펀드다.

    🔴 16R 재검 ③-1 — **대표번호 축 총계를 함께 센다.** 목록이 rptt 로 접힌 뒤 머리줄이 「대표번호 기준 M건」을
       **화면 행 수**로 적어 총계를 오도했다(중국 28 vs 실측 106 · 미국 28 vs 55 · 인도 19 vs 23).
    """
    if re.search(r"\b(?:union|having)\b|\(\s*select\b", sql, re.I):
        return None
    grouped = bool(re.search(r"\bgroup\s+by\b", sql, re.I))
    if grouped and not any(f"GROUP BY {e}" in sql for e in (_FUND_KEY_EXPR, _FUND_GROUP_EXPR)):
        return None
    m = _SIMPLE_FROM_WHERE.search(sql)
    if not m:
        return None
    frm = m.group(1).strip()
    fund_only = _FUND_TBL.search(sql) and not re.search(r"\bjoin\b", sql, re.I)
    cols = (f"COUNT(*), COUNT(DISTINCT {_FUND_KEY_EXPR}), COUNT(DISTINCT {_FUND_GROUP_EXPR})"
            if fund_only else "COUNT(*)")
    con = connect_readonly()
    try:
        row = con.execute(f"SELECT {cols} FROM {frm}").fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return int(row[0]), (int(row[1]) if fund_only else None), (int(row[2]) if fund_only else None), grouped


def _explicit_limit_hit(sql: str, n: int) -> bool:
    """명시 LIMIT k(< 상한)가 있는 정렬 목록이 k 행을 꽉 채웠는가 — 상위 k 만 보인 '잘린 목록' 판정.

    2026-09-02 실측: '한전 채권 수익률 높은 순' LIMIT 5 는 n(5) < MAX_ROWS 라 커버리지 병기가 발동하지 않아
    "전체 386종목 중 상위 5" 를 말할 재료가 없었고, 답 끝의 "이외에도 다양한…" 은 근거 없는 채움말이 됐다."""
    m = re.search(r"\bLIMIT\s+(\d+)\s*;?\s*$", sql, re.I)
    if not m or not re.search(r"\bORDER\s+BY\b", sql, re.I):
        return False
    k = int(m.group(1))
    return 0 < k < MAX_ROWS and n >= k


def _bond_coverage_counts(sql: str) -> tuple[int, int] | None:
    """채권 단순 목록의 전체 규모 — (전체 행수, 종목수 DISTINCT pd_no). GROUP BY pd_no(대표행 가드)는 허용. 아니면 None."""
    if "domestic_bonds" not in sql or re.search(r"\b(?:union|having|join)\b|\(\s*select\b", sql, re.I):
        return None
    if re.search(r"\bgroup\s+by\b(?!\s+pd_no\b)", sql, re.I):
        return None
    m = _SIMPLE_FROM_WHERE.search(sql)
    if not m:
        return None
    con = connect_readonly()
    try:
        row = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT pd_no) FROM {m.group(1).strip()}").fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return int(row[0]), int(row[1])


def _hide_answer_columns(rows: str, sql: str = "") -> tuple[str, list[str]]:
    """답변 입력에서 내부 코드 컬럼·원 단위 금액 컬럼을 뺀다 — retrieved_context 는 그대로. (정리된 표, 뺀 컬럼)"""
    lines = rows.splitlines()
    if not lines:
        return rows, []
    cols = lines[0].split(" | ")
    # 3R/4R B-4 — 원 단위 금액(fd_nast_suma·du_last_aum 및 그 집계·HCX 별칭 total_aum)은 억원 문자열이 함께 실리므로 13자리 원값은 숨긴다
    #    (021·022·031·T3·S11·V7 자릿수 훼손 계열). 별칭은 SQL 텍스트로 판정. 억원 컬럼('…억원')은 남긴다.
    amount_headers = {h.strip().lower() for _, h, _ in _amount_select_items(sql)} if sql else set()
    # 7R B-4′ — 숨김과 병기는 한 쌍이다. 대체 표시 열('…억원')이 결과에 **실제로 없으면** 원값을 숨기지 않는다.
    #    6R Y16 실측: 억원 병기 가드는 public_funds·domestic_etfs 만 다루는데 숨김은 전 테이블이라
    #    overseas_etfs 의 SUM(du_last_aum) 이 대체 열 없이 삭제 → 답변기에 숫자가 0개 → 환각·투자권유가 빈칸을 메웠다.
    has_display = any(_DISPLAY_UNIT.search(c) for c in cols)
    drop = [i for i, c in enumerate(cols)
            if c.strip().lower() in _HIDE_FROM_ANSWER
            or (has_display and not _DISPLAY_UNIT.search(c)
                and (_RAW_AMOUNT_COL.search(c) or c.strip().lower() in amount_headers))]
    if not drop or len(drop) == len(cols):
        return rows, []
    keep = [i for i in range(len(cols)) if i not in drop]
    out = []
    for ln in lines:
        parts = ln.split(" | ")
        out.append(" | ".join(parts[i] for i in keep if i < len(parts)))
    return "\n".join(out), [cols[i].strip() for i in drop]


_CODE_COL_RX = re.compile(r"\b(\w+_itt_cd)\b", re.I)


@lru_cache(maxsize=1)
def _code_label_map() -> dict:
    """(코드 컬럼, 8자리 코드) → 기관 정본 이름. 원천은 `kg_alias` × `kg_node.label_official` — 하드코딩 0."""
    ctx = _ev_ctx()
    out: dict = {}
    by_id = getattr(ctx, "kg_node_by_id", {}) or {}
    for nid, aliases in (getattr(ctx, "kg_aliases", {}) or {}).items():
        node = by_id.get(nid)
        name = (getattr(node, "label_official", None) or getattr(node, "label_ko", None)) if node else None
        if not name:
            continue
        for _t, col, raw in aliases:
            if col and col.lower().endswith("_itt_cd") and str(raw).strip():
                out.setdefault((col.lower(), str(raw).strip().zfill(8)), name)
    return out


@lru_cache(maxsize=1)
def _org_name_map() -> dict:
    """(이름 컬럼, DB 원값) → 기관 정본 이름. `kg_alias` × `COALESCE(label_official, label_ko, canonical_name)`.

    🔴 16R 재검 ③-2 (부류 AF) — `ref_fund_mgmt_co` 의 **영문 법인명**이 조립기를 거치지 않고 HCX 로 넘어가
       즉석 번역됐다. 같은 축의 질문 쌍에서 이름이 갈린다: `Mirae Asset Global Investments Co Ltd` 가
       V7 에선 '미래에셋 글로벌 자산운용', W10 에선 '미래에셋 글로벌 인베스트먼트'(둘 다 DB·KG 어디에도 없다).
       정본은 '미래에셋자산운용'. 코드 컬럼에 이미 도는 규칙(`_code_label_map`)을 이름 컬럼으로 넓힌 것뿐이다.
    해외 ETF 는 `label_official` 이 없고 `label_ko` 가 영문명 자신이라 **원값 그대로** 돌아온다 —
    `BlackRock Fund Advisors`(U8·Y16)는 번역되지 않는다.
    """
    ctx = _ev_ctx()
    by_id = getattr(ctx, "kg_node_by_id", {}) or {}
    out: dict = {}
    for nid, aliases in (getattr(ctx, "kg_aliases", {}) or {}).items():
        node = by_id.get(nid)
        if not node or getattr(node, "node_type", "") != "Organization":
            continue
        name = (getattr(node, "label_official", None) or getattr(node, "label_ko", None)
                or getattr(node, "canonical_name", None))
        if not name:
            continue
        for _t, col, raw in aliases:
            if col and not col.lower().endswith("_itt_cd") and str(raw).strip():
                out.setdefault((col.lower(), str(raw).strip()), name)
    return out


def label_code_columns(rows: str, sql: str, skip: list | None = None) -> tuple[str, list[str]]:
    """KG 4R G4 — 답변 입력의 **기관 코드 컬럼 값**을 기계가 확정 표기한다. (정리된 표, 표기한 컬럼)

    16R 재검 ③-2 — **기관 이름 컬럼**(`ref_fund_mgmt_co`·`cu_fund_mgmt_co` 등 KG 가 `Organization` 별칭으로
    아는 컬럼)도 같은 자리에서 정본으로 굽는다. 같은 목적의 가드를 옆에 하나 더 만들지 않는다.

    컬럼 판정은 **별칭이 아니라 SELECT 항목의 원 컬럼 표현식**으로 한다 — KG-008 실측:
    `trim(trusc_xtn_itt_cd) AS 수탁회사명` 이 이름 열처럼 보여 HCX 가 운용사 이름 3개를 통째로 날조했다.
    매핑이 있으면 `이름(코드)`, 없으면 `코드 00020088(기관명 미수록)` 으로 굽는다 — **숨기지 않는다**:
    숨김은 Z23("수탁사 정보가 수록되어 있지 않습니다") 처럼 값이 있는데 부재로 서술하는 결과를 낳았다.

    🔴 8R 부류 D — 전제(헤더 arity) 때문에 못 걸린 경우 `skip` 에 사유를 담는다. 7R 은 이 자리가 **무음 종료**라
    KG-008 이 "고쳤는데 안 고쳐진" 상태로 두 라운드를 돌았다 — 트레이스에 흔적이 없으면 다음 라운드도 헛돈다.
    """
    lines = rows.splitlines()
    frm = re.search(r"\bfrom\b", sql or "", re.I)
    if len(lines) < 2 or not frm:
        return rows, []
    cols = lines[0].split(" | ")
    items = _split_select_items(re.sub(r"^\s*select\s+(distinct\s+)?", "", sql[:frm.start()], flags=re.I))
    if len(items) != len(cols):
        if skip is not None and _CODE_COL_RX.search(" , ".join(items)):
            skip.append(f"SELECT 항목 {len(items)}개 ≠ 결과 열 {len(cols)}개 — 선행 가드가 열을 바꿨다")
        return rows, []
    # 🔴 14R — **집계 항목 안의 코드 컬럼은 코드 열이 아니다.** 가드가 심는 펀드키 식
    #    `COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd …)) || …) AS "펀드수"` 가 코드 열로 오인돼
    #    펀드수 714 가 "코드 714(기관명 미수록)" 로 구워졌다(KG-008 이 두 라운드를 헛돈 원인의 절반).
    plain = [it for it in items
             if not re.search(r"\b(?:count|sum|avg|total|group_concat)\s*\(", it, re.I)]
    code_cols = {i: m.group(1).lower() for i, it in enumerate(items)
                 if it in plain and (m := _CODE_COL_RX.search(it))}
    org_map = _org_name_map()
    org_slots = {c for c, _v in org_map}
    name_cols = {i: m.group(1).lower() for i, it in enumerate(items)
                 if i not in code_cols and it in plain
                 and (m := re.search(r"\b(" + "|".join(sorted(org_slots, key=len, reverse=True)) + r")\b", it, re.I))
                 } if org_slots else {}
    if not code_cols and not name_cols:
        return rows, []
    mapping = _code_label_map()
    out, touched = [lines[0]], []
    for ln in lines[1:]:
        parts = ln.split(" | ")
        for i, col in code_cols.items():
            if i >= len(parts):
                continue
            v = parts[i].strip()
            if not v or not v.isdigit():
                continue
            name = mapping.get((col, v.zfill(8)))
            parts[i] = f"{name}({v})" if name else f"코드 {v}(기관명 미수록)"
            if cols[i].strip() not in touched:
                touched.append(cols[i].strip())
        for i, col in name_cols.items():
            if i >= len(parts):
                continue
            v = parts[i].strip()
            canon = org_map.get((col, v))
            if not canon or canon == v:
                continue                      # KG 매핑이 없으면 DB 원값 그대로 — 번역하지 않는다
            parts[i] = canon
            if cols[i].strip() not in touched:
                touched.append(cols[i].strip())
        out.append(" | ".join(parts))
    return ("\n".join(out), touched) if touched else (rows, [])


_NAME_COL = re.compile(r"\b(?:itm_nm|itm_abrv_nm|pd_nm|pd_abrv_nm|etf_name)\b", re.I)
_NAME_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{8,}")


def verify_product_names(answer: str, rows: str, skip: list | None = None) -> tuple[str, list[str]]:
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
        # 🔴 8R 부류 C — 사전이 비면 교정이 아예 안 걸린다(무음). X18 실측: `SELECT DISTINCT mother_fund_names_raw` 가
        #    itm_nm 을 안 실어 `ext_fund_page` 원문 오염('코어텍')이 교정 없이 답변에 나갔다.
        if skip is not None and re.search(r"\b(?:mother_fund_names_raw|mgmt_co_nm|holding_nm)\b", rows.splitlines()[0], re.I):
            skip.append("결과에 정본 이름 열(itm_nm 등)이 없어 대조 사전이 비었다 — ext_* 원문 오염을 교정할 수 없다")
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
    r"[^.!?\n]*(?:전문가(?:와의?|의)?\s*(?:상담|조언|의견)"
    # 2026-09-02 R2 재검 — "추가 정보가 필요하시다면 관련 기관에 문의하시기 바랍니다" 가 '관련 기관' 이라 빠져나갔다
    # 7R B-5 — KG 4R Z21·Z23 실측: "금융 기관에 **직접** 문의" 처럼 부사가 끼면 빠져나갔다. 기관어와 동사 사이 부사를 허용한다
    r"|(?:관련|해당|금융|각|공식)?\s*(?:금융\s*)?기관(?:에|으로|을\s*통해)\s*(?:직접\s*|따로\s*)?(?:문의|확인|상담)|추가\s*정보가\s*필요"
    r"|자세한\s*(?:내용|사항)은[^.!?\n]*(?:문의|확인|상담|참고|참조)"
    # 7R B-5 — 투자권유형. 6R Y16 실측: 값이 통째로 숨겨진 자리를 "안정성과 성장성 … 긍정적으로 검토해볼 수 있을 것입니다" 가 메웠다.
    #   답변 규칙의 투자권유 금지가 HCX 문장에 맡겨져 재발한다(면책과 같은 계열 — 같은 함수가 처리한다)
    r"|긍정적으로\s*검토|검토해\s*볼\s*(?:만|수)|안정성과\s*성장성|투자를\s*(?:고려|권|추천)|매수를\s*(?:고려|권|추천)"
    # 🔴 11R 재검 ③-9 · KG ③-16 · gold ③-20 — 어휘 목록이 아니라 **문형**으로 판정한다. 사전이 '금융기관 문의·
    #   전문가 상담' 계열만 담아 U9 "투자 결정 전에 추가 정보를 확인하는 것을 **권장합니다**" 가 빠져나갔고,
    #   X13 꼬리 "**참고용으로만** 활용", OFFICIAL-003 "**유용한 정보를 제공**할 것" 이 매 라운드 재발한다.
    #   근거 없는 권유·주의 환기(서술어가 권장/권고/권유)와 유보형 상투구를 문형으로 걷는다.
    #   데이터에서 나온 주의 문구(수익률 누적 고지 등)는 조립기가 굽는 것이라 이 문형에 걸리지 않는다.
    r"|(?:권장|권고|권유)(?:합니다|드립니다|하는|할\s*것|하며|하시|됩니다)|참고용(?:으로|만)|유용한\s*정보를\s*제공"
    # 🔴 14R gold ③-18 — **산문 경로에 금지 문형 가드가 절반만 걸린다.** 13R 실측 두 건이 같은 꼬리를 달았다:
    #   `UNANS-001` "…충분히 이해하고 … 신중하게 고려하여 투자 결정을 내리시기 바랍니다"
    #   `OFFICIAL-004` "…손실이 발생할 수 있으므로 신중하게 결정해야 합니다" / "…수익을 추구합니다"
    #   어느 것도 조회 결과에서 나온 문장이 아니다(근거 밖 부연 + 투자권유). 문형으로 걷는다.
    r"|신중(?:하게|히)\s*(?:고려|검토|결정|판단|접근)|투자\s*(?:결정|판단)을\s*(?:내리|하시|해야)"
    r"|충분히\s*(?:이해|검토|고려|숙지)|손실이\s*발생할\s*수\s*있|수익을\s*추구합니다"
    # 11R KG ③-18 재발 — 내용 없는 마무리문("위의 정보를 통해 … 확인할 수 있습니다")
    r"|위(?:의|\s*정보)[^.!?\n]*(?:확인할\s*수\s*있습니다|알\s*수\s*있습니다)"
    # gold ③-17 — 거절문의 외부 출처 안내("금융기관의 공식 웹사이트나 관련 보고서를 통해 확인하실 수 있습니다")
    r"|(?:웹\s*사이트|홈페이지|공시|보고서|약관|설명서)[^.!?\n]*(?:통해|에서|를)\s*(?:확인|참고|조회|열람))"
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
    if _explicit_limit_hit(sql, n) and not re.search(r"\b(?:count|sum)\s*\(", sql, re.I):
        return text, False          # 상위 k 로 잘린 개체 목록(채권 대표행 GROUP BY pd_no + MAX/MIN) — '더 있다' 는 참이다.
                                    # COUNT/SUM 정렬 top-k(운용사 top5)는 전수 집계라 유보가 거짓 — 종전대로 걷어낸다.
    out = _FALSE_HEDGE.sub("", text)
    if out == text:
        return text, False
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return (out, True) if out else (text, False)


# 8R B-5′ — 답변 표면 금지 문형 셋을 더한다(제거만 하고 대체 문장을 만들지 않는다).
#   ⓐ 기준일 주장: '…을 기준으로 한 정보' 문장에 든 날짜가 gate.DATA_CUTOFF 와 다르면 그 문장을 통째로 버린다.
#      🔴 날짜가 든 문장을 무조건 버리면 안 된다 — 설정일·만기일은 정당한 답이다. **기준 주장 문형** 안의 날짜만 본다.
#      7R Y3 실측: "이 데이터는 2026년 8월 21일을 기준으로 한 정보이며" — 주최 규칙이 정한 기준일(2026-08-24)을
#      답변이 다른 날짜로 명시했다. 값 판정과 별개로 직접 감점 축이다.
#   ⓑ 집계 방법론 날조: "모든 클래스의 수익률을 합하여" — 결과는 클래스별 값이지 합산이 아니다(Y3).
#   ⓒ 데이터 품질 추측: "기준가 산정 오류가 있을 가능성" — HCX 가 근거 없이 지어낸 유보(Y1).
_EXCLUDE_Q = re.compile(r"제외|빼고|아닌|말고|이외|을?\s*뺀|없는")
_NOT_NAME_LIKE = re.compile(r"((?:REPLACE\(\s*(?:\w+\.)?itm_nm\s*,[^)]*\)|TRIM\(\s*(?:\w+\.)?itm_nm\s*\)"
                            r"|\b(?:\w+\.)?itm_nm\b)\s*)NOT\s+LIKE(\s*'%([^%']+)%')", re.I)


def fix_inverted_name_predicate(sql: str, question: str) -> tuple[str, bool]:
    """질문의 낱말을 **부정 술어**로 뒤집은 이름 절을 긍정으로 되돌린다. (SQL, 되돌렸는지)

    🔴 10R KG 부류 I — 값 검사가 실패해 축을 못 세우면 HCX 가 질문의 낱말을 `NOT LIKE` 로 뒤집는다.
       Z18 실측: "ETF로 자산배분하는 공모펀드" → `zrin_btyp_nm IN ('주식형','해외주식형') AND
       REPLACE(itm_nm,' ','') NOT LIKE '%ETF%'` — **질문의 정확한 반대**. 1,508펀드/4,551클래스가
       나가고 30건이 나열됐다(gold `itm_nm LIKE '%ETF%'` 20펀드/112클래스 · 형제 X16 이 정답 경로).
    질문에 제외 어휘(제외·빼고·아닌·말고)가 있으면 사용자 조건이므로 손대지 않는다(FND-006 'MMF 제외').
    """
    if _EXCLUDE_Q.search(question):
        return sql, False
    q = question.replace(" ", "").casefold()

    def _flip(m: re.Match) -> str:
        return m.group(1) + "LIKE" + m.group(2) if m.group(3).replace(" ", "").casefold() in q else m.group(0)
    fixed = _NOT_NAME_LIKE.sub(_flip, sql)
    return fixed, fixed != sql


_ESTB_WORD = re.compile(r"설정|설립|운용\s*(?:한\s*지|기간|되|중|해\s*온)")
_DURATION = re.compile(r"약\s*\d+\s*년|\d+\s*년\s*(?:간|째|동안|넘게|이상\s*운용)")


def strip_unsourced_estb_claim(answer: str, rows: str) -> tuple[str, bool]:
    """조회 결과에 날짜 축이 없는데 설정일·운용 기간을 단정한 문장을 제거. (답변, 제거했는지)

    🔴 10R KG 부류 E 부수 — AA5 실측: SELECT 에 `estb_dt` 가 **없는데**(있는 건 `fd_estb_ctry_cd='000'`)
       답변이 "설정일은 2011-06-20 · 약 12년" 이라 했다. 2011년부터 2026년이면 15년이라 자기 산술과도
       모순인데 어떤 가드도 안 잡았다. 일반 규칙: **답변이 말한 축이 retrieved_context 헤더에 없으면
       그 문장을 제거하고 '미조회' 로 강등한다.**
    """
    header = rows.splitlines()[0] if rows else ""
    if re.search(r"_dt\b|설정일|일자|date", header, re.I):
        return answer, False
    out, hit = [], False
    for sent in re.split(r"(?<=[.!?\n])", answer):
        if _ESTB_WORD.search(sent) and (_DATE_IN_TEXT.search(sent) or _DURATION.search(sent)):
            hit = True
            continue
        out.append(sent)
    if not hit:
        return answer, False
    return ("".join(out).strip() + "\n(설정일은 이번 조회 대상에 포함되지 않아 확인하지 못했습니다.)"), True


_PCT_IN_TEXT = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*%")
_NUM_IN_ROWS = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _num_key(v: str) -> str:
    """천 단위 구분자·후행 0 을 지운 수치 키 — 표기 차이('24.950' ↔ '24.95')로 오탐하지 않게."""
    v = v.replace(",", "")
    return v.rstrip("0").rstrip(".") if "." in v else v


def strip_unsourced_percent(answer: str, rows: str) -> tuple[str, list[str]]:
    """조회 결과에 없는 **백분율 수치**를 담은 문장을 제거한다. (답변, 제거한 값)

    🔴 16R KG ③-16 (`X1` 회귀) — 13R 에 소멸했던 자체 산술이 다시 나왔다: 24.95·15.9·7.96 세 행을 받아
       "이 세 종목이 전체 포트폴리오에서 차지하는 비중은 **약 48.81%**" 를 스스로 계산해 붙였다.
       규칙 텍스트에만 있는 금지는 재발한다 — 반환 직전에 기계로 걷는다(`strip_unsourced_estb_claim` 의 짝).
    기계 조립 경로는 조기 반환이라 여기 오지 않는다(HCX 산문 경로 전용). 전부 지워지면 원문을 유지한다.
    """
    have = {_num_key(v) for v in _NUM_IN_ROWS.findall(rows or "")}
    out, dropped = [], []
    # 소수점을 문장 끝으로 오인하지 않는 분할 — 마침표 뒤에 공백이 와야 문장이 끝난다('24.95%' 는 한 덩어리)
    for sent in re.split(r"(?<=[.!?])(?=\s)|(?<=\n)", answer):
        bad = [v for v in _PCT_IN_TEXT.findall(sent) if _num_key(v) not in have]
        if bad:
            dropped += bad
            continue
        out.append(sent)
    txt = "".join(out).strip()
    if not dropped or not re.search(r"\d", txt):        # 전부 지워지면 원문 — 빈 답변이 더 나쁘다
        return answer, []
    return re.sub(r"\n{3,}", "\n\n", txt), dropped


_CUTOFF_CLAIM = re.compile(r"[^.!?\n]*(?:기준일|기준\s*시점|(?:을|를)?\s*기준으로\s*한)[^.!?\n]*[.!?]?")
_DATE_IN_TEXT = re.compile(r"((?:19|20)\d{2})\s*[년\-]\s*(\d{1,2})\s*[월\-]\s*(\d{1,2})\s*일?")
_FAKE_BASIS = re.compile(
    r"[^.!?\n]*(?:모든\s*클래스[^.!?\n]*(?:합하여|합한|합산|더하여|더한)"
    r"|(?:기준가|수익률|순자산)\s*산정[^.!?\n]*오류가?\s*있을\s*가능성)[^.!?\n]*[.!?]?")


def _drop_wrong_cutoff(text: str) -> str:
    """기준일을 주장하는 문장에 정본(gate.DATA_CUTOFF)과 다른 날짜가 있으면 그 문장만 버린다."""
    def _cut(m: re.Match) -> str:
        for y, mo, d in _DATE_IN_TEXT.findall(m.group(0)):
            if f"{int(y):04d}-{int(mo):02d}-{int(d):02d}" != gate.DATA_CUTOFF:
                return ""
        return m.group(0)
    return _CUTOFF_CLAIM.sub(_cut, text)


def strip_disclaimer(text: str) -> tuple[str, bool]:
    """답변에서 면책 상투구·기준일 날조·방법론 날조 문장을 걷어낸다. (정리된 답변, 제거했는지)

    2026-09-01 실측 — answer_rules 의 면책 금지가 하루 5회 재발("금융기관에 문의"·"전문가와
    상담"): 규칙이 실려도 답변기가 습관적으로 붙인다(법칙 1). 값·목록은 그대로 두고 해당 문장만
    통째로 제거. 전부 지워지면(면책 한 줄짜리 답) 원문 유지 — 빈 답변이 더 나쁘다.
    8R B-5′ 로 기준일 주장·집계 방법론·품질 추측 문형이 같은 함수에 들어왔다(가드 중복 0).
    """
    out = _drop_wrong_cutoff(_FAKE_BASIS.sub("", _DISCLAIMER.sub("", text)))
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


_ETF_SCOPE = {"domestic_etfs": "국내 상장 ETF", "overseas_etfs": "해외 상장 ETF"}


def ensure_etf_scope_note(answer: str, sql: str) -> tuple[str, bool]:
    """ETF 집계·랭킹 답변의 머리줄에 **어느 모수를 봤는지** 기계로 표기. (답변, 붙였는지)

    🔴 10R 재검 ③-11(부류 B-4) — V7·W10 은 6R 에 있던 '국내' 표기가 7R·9R 엔 없다. 라운드마다 뒤집히는
       서술은 LLM 에게 맡길 수 없다(분포·목록 전사와 같은 결론). 답변이 이미 그 범위를 밝혔으면 불개입.
    """
    m = re.search(r"\bfrom\s+(domestic_etfs|overseas_etfs)\b", sql, re.I)
    if not m or not re.search(r"\b(?:count|sum|avg)\s*\(|\border\s+by\b", sql, re.I):
        return answer, False
    scope = _ETF_SCOPE[m.group(1).lower()]
    head = answer.split("\n", 1)[0]
    if scope in head or scope[:2] in head:
        return answer, False
    return f"({scope} 기준, 기준일 {gate.DATA_CUTOFF})\n" + answer, True


_REFUSAL_ANSWER = re.compile(
    r"정보가?\s*(?:포함되어\s*있지\s*않|없)|답변(?:을|이)?\s*드릴\s*수\s*없|확인(?:할|이)\s*(?:수\s*)?(?:없|불가)|알\s*수\s*없")
_EXIST_Q = re.compile(r"있(?:어|나|습니까|나요|는지)")


_HEADER_SHELL = re.compile(r"^\s*(?:TRIM|CAST|ROUND|MAX|MIN|SUM|AVG|COUNT|TOTAL)\s*\(\s*(?:\w+\.)?(\w+)", re.I)


def _answer_col_label(header: str) -> str:
    """결과 헤더 → 사람이 읽는 라벨. 식별자·내부코드 컬럼이면 빈 문자열(답변에서 뺀다).

    11R gold ③-8 — `TRIM(x)`·별칭 껍질을 벗기고 스키마 한글명(원천)을 붙인다. 이름 하드코딩 0.
    """
    h = header.strip().strip('"')
    m = re.match(r"(.*?)\s+AS\s+\"?([^\"]+)\"?$", h, re.I | re.S)
    if m:
        h = m.group(2).strip()
    col = (_HEADER_SHELL.match(h).group(1) if _HEADER_SHELL.match(h) else h).strip()
    if re.search(r"[가-힣]", col):
        return col                                   # 이미 사람이 읽는 별칭('클래스수'·'순자산_억원')
    if _NAME_COL.fullmatch(col):
        return "종목명"                               # 이름은 답의 핵심이라 항상 남긴다
    if col.lower() in _EVIDENCE_SKIP or col.lower().endswith("_itt_cd") or col.lower() in _FUND_ID_COLS:
        return ""                                    # 식별자·내부코드 — 사용자 화면에 낼 값이 아니다
    for cols in (getattr(_ev_ctx(), "schema", {}) or {}).values():     # 테이블 무관 — 스키마 한글명이 원천이다
        for c, ko, *_ in cols:
            if c.lower() == col.lower() and ko:
                return ko
    return col


# 플레이스홀더 값 — 답변에 옮기면 사용자에게 코드가 노출된다(KG ③-10 · Z18 `대표번호 KR0000000000`)
_SENTINEL_CELLS = frozenset({"KR0000000000", "None", "NULL", ""})


def ensure_rows_answered(answer: str, rows: str, n: int) -> tuple[str, bool]:
    """조회 결과가 있는데 결과를 **하나도 인용하지 않고** 거절한 답변을 기계 전사로 교체. (답변, 교체했는지)

    🔴 10R gold N7 — `[Execute]` 가 1행 이상을 돌려준 뒤에는 "정보가 없습니다" 를 낼 수 없다.
       OFFICIAL-005 실측: 1행을 받고도 거절문이 나갔다. 못 답하는 축이 있으면 그 축만 밝히면 된다.
    답변이 결과의 값을 하나라도 인용했으면 부분 유보이므로 불개입 — 여기서 걸리는 것은 전량 폐기뿐이다.
    """
    lines = rows.splitlines()
    if n < 1 or len(lines) < 2 or not _REFUSAL_ANSWER.search(answer):
        return answer, False
    cols = [c.strip() for c in lines[0].split(" | ")]
    body = [[v.strip() for v in ln.split(" | ")] for ln in lines[1:]]
    if any(len(v) >= 2 and v in answer for r in body for v in r):
        return answer, False
    # 🔴 11R gold ③-8 (부류 Y) — 전사는 **사람이 읽는 표**로 낸다. 종전엔 SQL 헤더 문자열을 그대로 써서
    #    `TRIM(itm_nm)`·`cu_lev_fector`·`fd_price_bas_dt` 가 사용자 화면에 나갔다(FND-R03·OFFICIAL-005).
    #    라벨은 스키마 한글명(loader 원천)이고, 식별자·내부코드 컬럼은 뺀다(`_EVIDENCE_SKIP` 과 같은 기준).
    labels = [_answer_col_label(c) for c in cols]
    keep = [i for i, c in enumerate(cols) if labels[i]]
    # 🔴 14R KG ③-10 (Z18 부작용 수리) — **전사 강제는 원시 행이 아니라 답변 스키마로 내보낸다.**
    #    종전엔 읽을 수 있는 라벨이 하나도 없으면 SQL 헤더를 그대로 썼다(`keep = 전체 · labels = cols`) —
    #    Z18 실측: `종목명 ㅊ`·`대표번호 KR0000000000`·`운용속성구분코드 설명` 이 사용자 화면에 나갔다.
    #    표시 축이 없으면 전사하지 않는다(거절문을 그대로 둔다 — 원시 덤프보다 낫다).
    if not keep:
        return answer, False
    out = [f"조회 결과 {n}행입니다 (기준일 {gate.DATA_CUTOFF})."]
    out += ["- " + " · ".join(f"{labels[i]} {r[i]}" for i in keep
                              if i < len(r) and r[i] and r[i] not in _SENTINEL_CELLS) for r in body[:10]]
    if n > 10:
        out.append(f"… 외 {n - 10}행")
    return "\n".join(out), True


def ensure_positive_count_answered(answer: str, sql: str, rows: str, n: int,
                                   question: str) -> tuple[str, bool]:
    """양수 단일 집계 결과를 받고도 '정보 없음' 으로 오거절한 답변을 기계 조립으로 교체한다.

    2026-09-02 서버 실측: '퇴직연금으로 살 수 있는 채권 있어?' — SQL 은 pd_pen_tr_yn='Y' +
    구매가능 모수로 정확했고 COUNT(*)=1,929 가 정상 반환됐는데, 답변기가 "정보가 포함되어
    있지 않습니다" 오거절. crd_grd 오거절(SELECT 누락)과 달리 이번엔 숫자가 결과에 있는데도
    집계 1행을 '정보 없음' 으로 오독했다 — 집계 해석은 LLM 에 맡길 수 없다(_count_answer ·
    _distribution_answer 와 같은 교훈). 0행 '확인 불가' 는 compose 전 조기 반환 경로라 이
    가드에 오지 않는다 — 여기 오는 답변은 항상 결과가 있다.
    발동(전부): ① 단일행 결과 ② SELECT 가 집계 1항목 ③ 값이 양수 ④ 답변이 거절 문구이거나
    — 2026-09-02 확장 — 값을 어디에도 인용하지 않은 '없습니다' 부정 단정('위험등급 0등급인 채권은
    없습니다' — COUNT 19 반환에도 단정. 거절 변종: 정보 없음이 아니라 사실 부정). 숫자를 인용한
    정상 답변('19종목 있습니다')은 조건 미충족으로 불개입.
    값 0 이면 불개입('없다' 답이 옳을 수 있다). 교체문은 결과 원문 수치만 쓴다 — 창작 없음."""
    if n != 1:
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
    misread = bool(_REFUSAL_ANSWER.search(answer)) or (
        re.search(r"없습니다|없는\s*것으로", answer) is not None
        and f"{val:,}" not in answer and str(val) not in answer)
    if not misread:
        return answer, False
    # KG 4R G5 — 단위는 SQL 이 센 것을 그대로 말한다(펀드/클래스 구분 누락 계열). 채권 전용이던 것을 4도메인 공통으로 넓혔다:
    #   X17 실측 — `SELECT COUNT(*) FROM public_funds …` 이 7 을 반환했는데 답변이 "클래스 개수는 확인할 수 없습니다".
    if re.search(r"DISTINCT\s+pd_no", sql, re.I):
        unit = "종목"
    elif _FUND_TBL.search(sql):
        unit = "펀드" if re.search(r"COUNT\s*\(\s*DISTINCT[^)]*or_co_xtn_itt_cd", sql, re.I) else "클래스(판매 단위)"
    else:
        unit = "건(행 기준 — 종목 수와 다를 수 있음)"
    prefix = "네, 있습니다 — " if _EXIST_Q.search(question) else ""
    # 8R ③-11(부류 X′) — 질의가 이름으로 특정한 대상이면 그 이름을 함께 싣는다. 7R U16 실측: "조회 결과 7클래스입니다"
    #   만으로는 같은 '인도네시아' 문자열에 붙은 판매완료 산은 시리즈 14클래스와 구분할 수 없어 검증이 불가능했다.
    #   이름은 창작하지 않고 **SQL 이 실제로 쓴 LIKE 리터럴 원문**을 그대로 쓴다.
    m_lit = _NAME_LIKE_LIT.search(sql)
    subject = f"'{m_lit.group(1)}' — " if m_lit else ""
    return f"{prefix}{subject}조회 결과 {val:,}{unit}입니다 (기준일 {gate.DATA_CUTOFF}).", True


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
    if len(items) not in (2, 3):
        return None
    is_star = bool(re.match(r"\s*count\s*\(\s*\*\s*\)", items[1], re.I))
    # 채권 2열 — COUNT(DISTINCT pd_no) 도 받는다 (2026-09-02 실측: '신용등급별 몇 종목' 이 조립기
    # 미발동으로 HCX 전사 — AA+ 2,516종목 통째 누락 · BB0→'B0' 라벨 뒤틀림 · 14/16줄 나열.
    # FND-038 과 동일 병인: 조립기의 2열째 인식이 COUNT(*) 로 좁았다)
    is_pdno = bool(re.match(r"\s*count\s*\(\s*distinct\s+pd_no\s*\)", items[1], re.I)) and len(items) == 2 and "domestic_bonds" in sql
    if not is_star and not is_pdno:
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
        unit = "종목" if is_pdno else "건"
        head = f"조회 결과 {len(pairs)}개 범주, 합계 {total:,}{unit}입니다 (기준일 {gate.DATA_CUTOFF})."
        if is_pdno:
            # 범주별 DISTINCT 합은 전체 DISTINCT 와 다를 수 있다(복수 범주 걸친 종목 — 등급별집계 규칙:
            # 위험등급 합 20,505 > 전체 20,497). 전체는 같은 WHERE 로 따로 세고 차이를 문자열로 굽는다.
            m_fw = _SIMPLE_FROM_WHERE.search(sql)
            if m_fw:
                try:
                    con = connect_readonly()
                    try:
                        overall = con.execute(
                            f"SELECT COUNT(DISTINCT pd_no) FROM {m_fw.group(1).strip()}").fetchone()[0]
                    finally:
                        con.close()
                    if overall != total:
                        head = (f"조회 결과 {len(pairs)}개 범주, 전체 {overall:,}종목입니다 (기준일 {gate.DATA_CUTOFF}). "
                                f"범주별 합은 {total:,}종목 — 복수 범주에 걸린 종목이 중복 집계되어 전체와 다릅니다.")
                except sqlite3.Error:
                    pass
        lines = [head, ""]
        lines += [f"- {lab if lab else '(미수록)'}: {c:,}{unit}" for lab, c, _ in pairs]
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


_BASE_POP_COND = re.compile(r"\b(?:sale_yn|prvo_pbff_desc)\b", re.I)
_NAME_LIKE_LIT = re.compile(r"(?:REPLACE\((?:\w+\.)?itm_nm,' ',''\)|(?:\b\w+\.)?itm_nm)\s+LIKE\s+'%([^%']+)%'", re.I)


def _nearest_fund_names(lit: str, limit: int = 3) -> list[str]:
    """식별 실패 리터럴의 가까운 종목명 줄기 — 리터럴의 가장 긴 토큰(3자+)으로 LIKE 재조회(SQLite 1회). 없으면 []."""
    toks = sorted(re.findall(r"[A-Za-z0-9]+|[가-힣]+", lit), key=len, reverse=True)
    toks = [t for t in toks if len(t) >= 2]
    if not toks:
        return []
    base = ("SELECT DISTINCT TRIM(itm_nm) FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' "
            "AND {} ORDER BY fd_nast_suma DESC LIMIT 12")
    con = connect_readonly()
    try:
        # 🔴 10R 재검 ③-10(부류 W1′) — **AND 조합부터** 시도한다. 종전엔 가장 긴 토큰 하나를 한 글자씩 줄이며
        #    첫 매치를 썼는데, 그러면 '삼성 베스트 MMF 법인 제1호' 에 '삼성아세안플러스베트남증권자투자신탁'
        #    같은 무관 상품이 후보로 나온다(U12·W1). 없는 상품을 물었는데 엉뚱한 상품을 권하는 형태다.
        #    성분을 다 만족하는 상품이 없을 때만 가장 긴 성분 하나로 내려간다. 축소 하한 3자.
        cands = [t for t in toks if len(t) >= 2][:4]
        if len(cands) >= 2:
            where = " AND ".join(["REPLACE(itm_nm,' ','') LIKE ?"] * len(cands))
            rows = con.execute(base.format(where), tuple(f"%{t}%" for t in cands)).fetchall()
            stems = list(dict.fromkeys(_fund_stem(r[0]) for r in rows))
            if stems:
                return stems[:limit]
        for tok in toks[:2]:
            # 오타는 뒤가 틀리기 쉽다('코어택') — 토큰 → 접두를 한 글자씩 줄이며 첫 매치를 쓴다.
            # 축소 하한은 **토큰의 2/3**(최소 2자): 긴 토큰을 두세 글자까지 깎으면 무관 상품이 후보가 된다(③-10).
            for k in range(len(tok), max(2, (len(tok) * 2 + 2) // 3) - 1, -1):
                rows = con.execute(base.format("REPLACE(itm_nm,' ','') LIKE ?"), (f"%{tok[:k]}%",)).fetchall()
                stems = list(dict.fromkeys(_fund_stem(r[0]) for r in rows))
                if stems:
                    return stems[:limit]
    except sqlite3.Error:
        pass
    finally:
        con.close()
    return []


def _zero_row_reason(sql: str) -> str:
    """0행의 실체를 리터럴 검증으로 가른 사용자 문장 (6R F4 = R1 정정).
    (c) 죽은 절의 리터럴이 검증 집합 밖(이름 LIKE 0행·값사전 밖) → "「X」를 데이터 표기로 식별하지 못했다(가까운 표기: …)" — '없다/실재' 금지
    (b) 절 단독은 있으나 기본모수(판매중·공모)와의 교집합 0 → "판매중·공모 기준 0 · 전체 n(판매완료·사모)"
    (a) 그 밖 → "각 조건은 실재하며 교집합이 0". public_funds 단순 SELECT 기준(서브쿼리·UNION 은 (a))."""
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    frm = re.search(r"\bfrom\s+(public_funds)\b", sql, re.I)
    if not m_w or not frm or re.search(r"\(\s*select\b|\bunion\b|\bjoin\b", sql, re.I):
        return "(각 조건의 개체·값은 데이터에 실재하며 그 교집합이 0입니다)"
    conjs = guard.split_conjuncts(m_w.group(1))
    base = [c for c in conjs if _BASE_POP_COND.search(c)]
    others = [c for c in conjs if not _BASE_POP_COND.search(c)]
    con = connect_readonly()
    try:
        for c in others:
            try:
                alone = con.execute(f"SELECT COUNT(*) FROM public_funds WHERE {c}").fetchone()[0]
            except sqlite3.Error:
                continue
            if alone == 0:
                m_nm = _NAME_LIKE_LIT.search(c)
                if m_nm:
                    near = _nearest_fund_names(m_nm.group(1))
                    return (f"질문의 「{m_nm.group(1)}」를 데이터의 종목명으로 식별하지 못했습니다"
                            + (f" (가까운 표기: {' · '.join(near)})" if near else "") + ".")
                # 7R S′ — 리터럴 추출은 `=`·`LIKE`·**`IN`** 세 형 전부. 어느 것도 못 뽑으면 사람말(_humanize_cond)만 쓰고
                #   그것도 없으면 (a) 갈래로 떨어뜨린다 — **절 원문을 사용자에게 보이지 않는다**.
                #   6R W11 실측: 답변에 「itm_no IN ('030230002D36')」 SQL 절이 그대로 나갔다(값 오류를 넘는 감점 축).
                lit = (next((m.group(3) for m in guard._EQ.finditer(c)), None)
                       or next((m.group(3).strip('%') for m in guard._LIKE.finditer(c)), None)
                       or next((v for m in guard._IN.finditer(c) for v in guard._LIT.findall(m.group(3))), None))
                desc = guard._humanize_cond(c)
                if not (lit or desc):
                    break
                return (f"질문의 「{lit or desc}」를 데이터 표기로 식별하지 못했습니다 — 값 사전·개체 매핑에 없는 표기입니다.")
            if base:
                try:
                    with_base = con.execute(f"SELECT COUNT(*) FROM public_funds WHERE {c} AND {' AND '.join(base)}").fetchone()[0]
                except sqlite3.Error:
                    continue
                if with_base == 0:
                    desc = guard._humanize_cond(c) or "해당 조건"
                    return (f"{desc}인 펀드는 판매중·공모 기준 0개이고, 전체(판매완료·사모 포함)로는 {alone:,}클래스가 있습니다.")
    finally:
        con.close()
    return "(각 조건의 개체·값은 데이터에 실재하며 그 교집합이 0입니다)"


_ORG_CODES = re.compile(r"or_co_xtn_itt_cd='(\d+)'")


def _count_answer(sql: str, rows: str, n: int, ground_lines: list[str], question: str | None = None) -> str | None:
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
    # KG 1R R1 — 주어는 Ground 의 **모든** 기관 개체를 역할(운용/수탁 — 코드 컬럼으로 판정)과 함께 반영한다.
    #    KG-011: "KB자산운용이 운용하는 공모펀드는 0개" — 수탁 조건(국민은행)이 빠져 거짓 문장(KB 운용은 129/625).
    parts, used_codes = [], []
    for line in ground_lines:
        m_lab = re.match(r"'([^']+)'\s*→\s*Org_\w+\s*\((?:Organization,\s*정식명\s+([^)]+)|Organization)", line)
        if "Organization" not in line or not m_lab:
            continue
        name = (m_lab.group(2) or m_lab.group(1)).strip()     # S1: 정식명 슬롯이 있으면 주어는 정식명('한국 투자 신탁 운용' → 한국투자신탁운용)
        last = name[-1]
        particle = "이" if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 else "가"
        mgr = [c for c in re.findall(r"or_co_xtn_itt_cd='(\d+)'", line) if c in sql]
        tru = [c for c in re.findall(r"trusc_xtn_itt_cd='(\d+)'", line) if c in sql]
        if mgr:
            parts.append(f"{name}{particle} 운용하")
            used_codes += mgr
        elif tru:
            parts.append(f"{name}{particle} 수탁하")
    subject = ("고 ".join(parts) + "는") if parts else "조회 조건에 해당하는"
    # 3R 부류 D — 이름 모드('이름이 들어간'): 축은 이름이다. 주어를 이름 토큰으로, 운용사 코드별 분해를 SQLite 1회로 병기
    # 4R K-2/L — 이름 모드 판정은 질문(_NAME_MODE_Q)으로, 토큰은 SQL 의 이름 LIKE 리터럴로(Ground 0 인 '삼성' 도 주어가 된다).
    #    Ground 의 ⚙ 줄은 코드 핀 생략 지시일 뿐 답변 재료가 아니다.
    name_tok = None
    if (question and _NAME_MODE_Q.search(question)) or any("이름 모드" in ln for ln in ground_lines):
        m_lit = re.search(r"(?:REPLACE\((?:\w+\.)?itm_nm,' ',''\)|itm_nm)\s+LIKE\s+'%([^%']+)%'", sql, re.I)
        name_tok = m_lit.group(1) if m_lit else None
    breakdown = ""
    if name_tok:
        subject, used_codes = f"'{name_tok}' 이름이 들어간", []
        m_fw = _SIMPLE_FROM_WHERE.search(sql)
        if m_fw and not re.search(r"\bgroup\s+by\b", sql, re.I):
            con = connect_readonly()
            try:
                rows_b = con.execute(
                    f"SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)), COUNT(DISTINCT {_FUND_KEY_EXPR}) FROM {m_fw.group(1).strip()} "
                    "GROUP BY 1 ORDER BY 2 DESC").fetchall()
            except sqlite3.Error:
                rows_b = []
            finally:
                con.close()
            if rows_b:
                breakdown = "\n운용사 코드별: " + " · ".join(
                    f"{c} {n:,}개" + ("(역외)" if c.startswith(_OFFSHORE_CLASS) else "") for c, n in rows_b)
    out = f"{subject} {label}는 {funds:,}개(클래스 {classes:,}개)입니다{scope}." + breakdown
    if funds == 0:
        # 0행 정책(6R F4): 세 갈래 — (a) 교집합 0 / (b) 기본모수 밖 / (c) 식별 실패 — 리터럴 검증으로 가른다
        out += "\n" + _zero_row_reason(sql)
    if len(used_codes) >= 2:
        out += f"\n운용사 코드 {len(used_codes)}건({'·'.join(used_codes)})을 합산했습니다."
    offshore = _offshore_sibling_note(subject, used_codes, sql)
    if offshore:
        out += "\n" + offshore
    for note in ground_notes(ground_lines):
        out += "\n" + note                       # S1: 구상호·후계 법인 주석은 답에 그대로 병기
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


_MGMT_SUFFIX = re.compile(r"(?:자산|투자신탁|투신|자산위탁|위탁|투자)?운용(?:주식회사|㈜|\(주\))?$")
_KO_TOKEN = re.compile(r"[가-힣A-Za-z]{2,}")


@lru_cache(maxsize=1)
def _mgmt_stem_codes() -> tuple:
    """운용사 **브랜드 어간** → (코드, 클래스수). DB 실측(`ext_fund_page.mgmt_co_nm` ⋈ `public_funds`), 하드코딩 0.

    🔴 11R KG ③-13 (부류 M) — KG 에 `Org_*` 매핑이 없는 운용사명이면 HCX 가 코드를 **매번 새로 날조**한다
       (`1001` → `80000000` → `60000000` → `10000000`, Z15·AA23·X12 가 재생성 예산을 3회 이상 태웠다).
       자연어 피드백으로는 안 고쳐지는 유형이라 결정층에서 재료를 준다.
    어간은 법인 접미(자산운용·투자신탁운용·투신운용…)를 뗀 앞부분이다: '슈로더자산운용' → '슈로더'.
    질문의 '슈로더투자신탁운용' 도 같은 어간이라 표기가 달라도 맞는다.
    """
    con = connect_readonly()
    try:
        rows = con.execute(
            "SELECT printf('%08d', CAST(p.or_co_xtn_itt_cd AS INTEGER)), e.mgmt_co_nm, COUNT(*) "
            "FROM public_funds p JOIN ext_fund_page e ON e.itm_no = p.itm_no "
            "WHERE e.mgmt_co_nm IS NOT NULL AND TRIM(e.mgmt_co_nm) <> '' GROUP BY 1, 2").fetchall()
    except sqlite3.Error:
        return ()
    finally:
        con.close()
    best: dict[str, tuple] = {}
    for code, nm, cnt in rows:
        stem = _MGMT_SUFFIX.sub("", str(nm).strip()).strip()
        if len(stem) < 2:
            continue
        if stem not in best or cnt > best[stem][1]:
            best[stem] = (code, cnt, str(nm).strip())
    return tuple(sorted(best.items()))


@lru_cache(maxsize=1)
def _org_names_by_code() -> dict:
    """`or_co` 코드 → 그 `Org_*` 노드의 이름 슬롯 전부(공백 제거). `kg_node` 실측 — 하드코딩 0.

    세 슬롯을 **모두** 본다. `COALESCE` 로 하나만 보면 구상호 브랜드를 잃는다 —
    실측 `Org_00040013` 은 `label_official='키움투자자산운용'` · `label_ko='키움슈로더'` 라
    정본만 보면 '슈로더' 질의(X12)가 이 코드를 못 찾는다.
    """
    ctx = _ev_ctx()
    by_id = getattr(ctx, "kg_node_by_id", {}) or {}
    out: dict = {}
    for nid, aliases in (getattr(ctx, "kg_aliases", {}) or {}).items():
        node = by_id.get(nid)
        if not node or getattr(node, "node_type", "") != "Organization":
            continue
        slots = tuple(s.replace(" ", "") for s in
                      (getattr(node, "label_official", None), getattr(node, "label_ko", None),
                       getattr(node, "canonical_name", None)) if s)
        for _t, col, raw in aliases:
            if col and col.lower() == "or_co_xtn_itt_cd" and str(raw).strip():
                out.setdefault(str(raw).strip().zfill(8), slots)
    return out


@lru_cache(maxsize=None)
def _brand_or_co_codes(stem: str, offshore: bool) -> tuple[str, ...]:
    """브랜드 어간으로 **시작하는** 종목명을 가진 운용사 코드 전부 — DB 실측(하드코딩 0).

    🔴 14R 재검 ③-1 — 브랜드 하나가 법인 코드 여럿에 걸린다. 실측 '삼성' 접두 = 00040010(삼성자산운용 850클래스)
       + 00080135(삼성액티브자산운용 56). 단일 등호가 `삼성코리아대표증권자투자신탁 제1호` 9클래스를 통째로
       잘랐다(S3 ❌). 같은 라운드 V11 이 스스로 `00040010 207 · 00080135 10 · …` 를 답에 싣고 있었다.
    역외 종별(0013)은 질문이 역외를 요구할 때만 넣는다 — S9·T11·KG-031 은 역외를 분리 고지하는 것이 gold 다.
    """
    con = connect_readonly()
    try:
        rows = con.execute(
            "SELECT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)), COUNT(*) FROM public_funds "
            "WHERE REPLACE(itm_nm,' ','') LIKE ? GROUP BY 1 ORDER BY 2 DESC", (f"{stem}%",)).fetchall()
    except sqlite3.Error:
        return ()
    finally:
        con.close()
    cand = tuple(c for c, _ in rows if offshore or not c.startswith(_OFFSHORE_CLASS))
    # 🔴 16R gold ③-3 (`FND-C02`) — **코드 후보는 운용사 라벨로 만든다. 상품명으로 코드를 유도하지 않는다.**
    #    실측: '삼성' 접두 상품명 3건을 가진 `00080032` 의 정본 이름은 **현대인베스트먼트자산운용** 이고 그 3건은
    #    전부 기본모수 밖인데도 IN 에 들어와 모수를 207펀드/850클래스 → 226/926 으로 오염시켰다(목록 3위가
    #    현대인베스트먼트 펀드). 라벨로 걸러진 후보가 하나라도 있으면 그것만 쓰고, 하나도 없을 때만
    #    상품명 후보로 되돌아간다 — 구상호 브랜드('슈로더' → 정본 '키움투자자산운용')를 잃지 않기 위해서다.
    names = _org_names_by_code()
    by_label = tuple(c for c in cand if any(stem in n for n in names.get(c, ())))
    return by_label or cand


_OR_CO_EQ = re.compile(r"(?:TRIM\(\s*)?(?:\w+\.)?\bor_co_xtn_itt_cd\b\s*\)?\s*=\s*'(\d+)'", re.I)
# 등호·IN 양쪽 — 형제 코드 합집합 확장(16R KG ③-5)이 쓴다. `NOT IN` 은 부호가 반대라 대상이 아니다.
_OR_CO_PRED = re.compile(r"(?:TRIM\(\s*)?(?:\w+\.)?\bor_co_xtn_itt_cd\b\s*\)?\s*"
                         r"(?:=\s*'\d+'|(?<!NOT )IN\s*\(\s*(?:'\d+'\s*,\s*)*'\d+'\s*\))", re.I)
_OFFSHORE_Q = re.compile(r"역외")


def ensure_mgmt_code_predicate(sql: str, question: str, mgmt: tuple | None) -> tuple[str, str | None]:
    """역조회로 확정한 운용사 코드를 SQL 술어로 어떻게 쓸지 **결정층이 못 박는다**. (SQL, 사람말 조치 또는 None)

    🔴 14R 재검 ③-1 (부류 AC) — 11R KG ③-13 의 역조회 자체는 옳다(HCX 코드 날조·재생성 3회+ 를 0으로 만들었다).
       **틀린 것은 단일 등호**다: 브랜드 하나가 법인 코드 여럿에 걸리는데 등호가 정답 행을 자른다.
    두 갈래:
      ⓐ 이름 리터럴이 브랜드 어간을 **이미 품으면** 코드 술어는 정보가 0이다 → 제거한다
         (`itm_nm LIKE '%삼성코리아대표%'` 가 이미 브랜드를 거른다 — S3).
      ⓑ 이름 리터럴에 브랜드가 없으면(W1 형) 등호가 아니라 **브랜드 어간 역조회 코드 전부의 `IN`** 으로 렌더한다.
    KG 가 `Organization` 으로 확정한 코드(U11·S9 계열)에는 개입하지 않는다 — 그 코드는 우리가 지어낸 것이 아니다.
    """
    if not mgmt or not _FUND_TBL.search(sql) or not _single_select(sql) or not _OR_CO_EQ.search(sql):
        return sql, None
    stem = mgmt[0].replace(" ", "")
    if any(stem in lit.replace(" ", "") for lit in _NAME_LIKE_LIT.findall(sql)):
        out = _OR_CO_EQ.sub("1=1", sql)
        out = re.sub(r"\s+AND\s+1=1\b", "", out)
        out = re.sub(r"\b1=1\s+AND\s+", "", out)
        return (out, f"이름 리터럴이 '{mgmt[0]}' 을 이미 품어 코드 등호 제거(정보 0 · 다코드 브랜드를 자른다)") \
            if out != sql else (sql, None)
    codes = _brand_or_co_codes(stem, bool(_OFFSHORE_Q.search(question)))
    if len(codes) < 2 or set(_OR_CO_EQ.findall(sql)) <= set(codes) and len(set(_OR_CO_EQ.findall(sql))) == len(codes):
        return sql, None
    cond = "TRIM(or_co_xtn_itt_cd) IN (" + ", ".join(f"'{c}'" for c in codes) + ")"
    return _OR_CO_EQ.sub(cond, sql), f"'{mgmt[0]}' 브랜드가 법인 코드 {len(codes)}개에 걸려 등호를 IN 으로 확장"


@lru_cache(maxsize=1)
def _org_label_code_groups() -> dict:
    """`or_co` 코드 → 같은 `label_official` 을 갖는 코드 전부(2개 이상일 때만). `kg_node` 실측, 하드코딩 0.

    🔴 14R KG ③-8 (Z16) — 한 운용사에 `or_co` 코드가 둘인 경우가 있다(합병·구상호). 실측 4쌍
       (키움투자자산운용 00080052·00040013 등). 코드 하나만 조회하면 부족값이 나온다 — gold 112펀드/354클래스.
    """
    ctx = _ev_ctx()
    by_label: dict[str, set] = {}
    for n in ctx.kg_nodes:
        if n.node_type != "Organization":
            continue
        lo = (getattr(n, "label_official", "") or "").strip()
        if not lo:
            continue
        by_label.setdefault(lo, set()).update(
            raw for t, c, raw in ctx.kg_aliases.get(n.node_id, ())
            if t == "public_funds" and c == "or_co_xtn_itt_cd")
    out: dict = {}
    for label, codes in by_label.items():
        if len(codes) > 1:
            for c in codes:
                out[c] = (label, tuple(sorted(codes)))
    return out


def ensure_org_label_codes(sql: str, question: str = "") -> tuple[str, bool]:
    """KG 가 확정한 운용사 코드가 **같은 정본 이름의 형제 코드**를 갖고 있으면 `IN` 으로 묶는다. (SQL, 바꿨는지)

    🔴 14R KG ③-8 — 운용사 질의는 `kg_node.label_official` 이 같은 모든 `Org_*` 노드의 코드를 함께 조회한다.

    🔴 16R KG ③-5 — **14R 은 반쪽만 이행됐다.** ⓐ 술어가 `IN ('00080052')` 한 원소 꼴이면 등호 정규식이
       못 봤고 ⓑ 역조회(`mgmt`)가 잡히면 통째로 조기 반환해 KG 개체 매핑 경로엔 아예 안 붙었다
       (`Z16` 97펀드/308클래스 — gold 112펀드/354클래스). 두 형태를 함께 보고, 확장은 **합집합**이라
       역조회가 만든 브랜드 `IN` 을 좁히지 않는다(`mgmt` 인자는 더 이상 불개입 조건이 아니다).
       형제 코드는 `kg_node` GROUP BY 실측이라 하드코딩이 0이다.
    """
    if not _FUND_TBL.search(sql):
        return sql, False
    groups = _org_label_code_groups()

    q = (question or "").replace(" ", "")

    def _fix(m: re.Match) -> str:
        codes = {c.strip("'") for c in _SQL_LITERAL.findall(m.group(0)) if c.strip("'").isdigit()}
        wide = set(codes)
        for c in codes:
            label, sibs = groups.get(c, ("", ()))
            # 🔴 질문이 그 그룹의 **정본 이름**을 부른 경우에만 넓힌다. 브랜드 어간 질의(X12 '슈로더')는
            #    정본 이름('키움투자자산운용')을 부르지 않으므로 형제 코드가 붙지 않는다 — 하드코딩 0.
            if label and label.replace(" ", "") in q:
                wide |= set(sibs)
        if wide == codes:
            return m.group(0)
        return "TRIM(or_co_xtn_itt_cd) IN (" + ", ".join(f"'{c}'" for c in sorted(wide)) + ")"
    out = _OR_CO_PRED.sub(_fix, sql)
    return (out, True) if out != sql else (sql, False)


def mgmt_code_from_question(question: str) -> tuple | None:
    """질문의 운용사 표기 → (어간, 코드, 정본 이름). KG 매핑이 없을 때의 DB 역조회 1회. 못 찾으면 None.

    가장 **긴 어간**부터 본다 — '키움슈로더' 가 '슈로더' 보다 먼저 걸려야 한다(부분 브랜드 오매칭 방지).
    """
    q = question.replace(" ", "")
    for stem, (code, _cnt, nm) in sorted(_mgmt_stem_codes(), key=lambda kv: -len(kv[0])):
        if stem in q:
            return stem, code, nm
    return None


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


_HOLD_Q = re.compile(r"보유\s*(?:종목|주식|자산|비중|하고|한)|담(?:은|고|았)|구성\s*종목|편입|포트폴리오|투자\s*(?:종목|하는\s*종목)|(?:상위|주요|많이\s*가진)\s*종목")


_ORDINAL_KO = {"첫": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}


def _outer_group(s: str) -> str | None:
    """`(...)` 하나로 통째 감싼 식이면 안쪽을, 아니면 None. `(a) OR (b)` 는 겉괄호가 짝이 아니라 None."""
    if not (s.startswith("(") and s.endswith(")")):
        return None
    depth, in_q = 0, False
    for i, ch in enumerate(s):
        if ch == "'":
            in_q = not in_q
        elif not in_q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return s[1:-1] if i == len(s) - 1 else None
    return None


def _flat_conjuncts(expr: str) -> list[str]:
    """최상위 AND 로 가르되 **괄호로 묶인 AND 그룹은 안으로 들어간다**. OR 가 든 그룹은 통째로 둔다(의미 보존).

    🔴 8R 뿌리 β — `ensure_fund_base_population` 은 모수를 주입할 때 원 WHERE 를 통째로 괄호로 감싼다
    (`WHERE 모수 AND (원문)` — L530, 'a OR b' 에 그냥 AND 를 붙이면 새기 때문). 그 뒤 절 단위로 술어를 고르는
    가드가 `guard.split_conjuncts` 를 쓰면 그 괄호가 **한 절**이라, 안에 버릴 컬럼이 하나만 있어도 같은 괄호의
    이름 필터까지 함께 버려진다. 7R Z7·AA18 실측: 구성종목 서브쿼리의 preds 가 기본모수 둘만 남아
    **전 우주 순자산 1위 펀드**의 종목이 답으로 나갔다(남의 펀드).
    """
    out: list[str] = []
    for c in guard.split_conjuncts(expr):
        s = c.strip()
        inner = _outer_group(s)
        if inner is not None and not re.search(r"\bOR\b", inner, re.I):
            out.extend(_flat_conjuncts(inner))
        else:
            out.append(s)
    return out


def ensure_fund_holdings_template(sql: str, question: str, ctx, name_token: str | None = None,
                                  route_fund: bool = False) -> tuple[str, bool]:
    """6R F3 — 특정 펀드의 **구성종목** 질의를 ext_fund_holdings JOIN 확정식으로 교체. (보정 SQL, 교체했는지)

    부류: 질문에 구성종목 트리거(보유 종목·담은·편입·포트폴리오…) + 펀드 개별 지정(_has_name_filter 또는 펀드키 핀) + SQL 이 아직
    ext_fund_holdings 를 쓰지 않음. 팬아웃(1:N)이라 ensure_ext_join(1:1 전용) 의 자동 주입 밖이었고, 플래너는 public_funds 만 조회하거나
    domestic_etfs·ext_etf_holdings 로 새어 나갔다(KG-028 'IBK K-AI반도체코어테크' ETF 종목 환각 · KG-034 · X1 · X2).
    확정식: 원문 WHERE 의 펀드 술어(p. 한정)로 펀드를 고르고, 그 펀드 그룹(grp+or_co = JOIN_KEYS)의 보유 목록이 실린 대표 클래스
    (순자산 최대) itm_no 하나의 종목을 비중순으로 낸다 — 클래스 팬아웃 없이 한 펀드 = 한 목록. 컬럼명은 스키마(ext_fund_holdings)에서."""
    # 🔴 7R F3 — 「이미 ext_fund_holdings 를 쓰고 있으면 손 떼기」를 그만둔다. 6R 실측: KG-028 은 정답 JOIN 까지 도달하고도
    #    `SELECT TOP 1`(SQLite 문법 아님)과 `f.weight_pct = 1.0`(무의미 절)이 남았고, Z8 은 FROM 이 holdings 쪽이라
    #    팬아웃 중복(VINCOM 5행)이 났다. FROM/JOIN 이 HCX 재량인 한 이 결함은 라운드마다 모양만 바꿔 재발한다 —
    #    확정식이 **이미 만든 SQL**(비중_pct 표기)일 때만 불개입한다(멱등).
    if not _HOLD_Q.search(question) or re.search(r"\bunion\b", sql, re.I) or '"비중_pct"' in sql:
        return sql, False
    on_funds = bool(re.search(r"\b(?:from|join)\s+public_funds\b", sql, re.I))
    # 🔴 8R 부류 A-b — 라우팅이 public_funds 인 구성종목 질의는 HCX 가 어느 테이블로 새어 나갔든(X1·X2·KG-028 은
    #    domestic_etfs + ext_etf_holdings 로 갔다가 테이블 화이트리스트 기각 → 오거절) 확정식으로 교체한다.
    #    그때 펀드를 고르는 재료는 Ground 의 잔여 상품 고유명뿐이다 — 없으면 종전대로 불개입.
    if not ((on_funds and (_has_name_filter(sql) or _has_fund_key_pin(sql))) or (route_fund and name_token)):
        return sql, False
    schema = getattr(ctx, "schema", {}) or {}
    hcols = {c.lower() for c, *_ in schema.get("ext_fund_holdings", ())}
    if not {"holding_nm", "weight_pct", "itm_no", "grp", "or_co"} <= hcols:
        return sql, False
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    m_f = re.search(r"\bfrom\s+public_funds\b(?:\s+(?:as\s+)?(?!(?:left|inner|join|where|group|order|limit|on)\b)(\w+))?", sql, re.I) \
        or re.search(r"\bjoin\s+public_funds\b(?:\s+(?:as\s+)?(?!(?:left|inner|join|where|group|order|limit|on)\b)(\w+))?", sql, re.I)
    alias = m_f.group(1) if m_f else None
    m_h = re.search(r"\b(?:from|join)\s+ext_fund_holdings\b(?:\s+(?:as\s+)?(?!(?:left|inner|join|where|group|order|limit|on)\b)(\w+))?", sql, re.I)
    h_alias = m_h.group(1) if m_h else None
    # 펀드 쪽 술어만 남긴다 — 보유 테이블 쪽 절(`f.weight_pct = 1.0`)은 HCX 가 지어낸 무의미 조건이라 버린다
    h_only = {c.lower() for c, *_ in schema.get("ext_fund_holdings", ())} - {c.lower() for c, *_ in schema.get("public_funds", ())}
    preds = []
    if on_funds and m_w:
        for c in _flat_conjuncts(m_w.group(1)):
            masked = _SQL_LITERAL.sub("''", c)
            if (h_alias and re.search(rf"\b{re.escape(h_alias)}\.", masked)) or "ext_fund_holdings." in masked.lower() \
                    or any(re.search(rf"(?<![\w.])({w})\b", masked, re.I) for w in h_only):
                continue
            c = re.sub(r"\bpublic_funds\.", "p.", c)
            if alias:
                c = re.sub(rf"\b{re.escape(alias)}\.", "p.", c)
            c = re.sub(r"(?<![\w.])itm_no\b", "p.itm_no", c)
            preds.append(c.strip())
    else:
        preds = ["p.sale_yn = '판매중'", "p.prvo_pbff_desc = '공모'"]   # 타 테이블에서 끌어온 경로 — 기본모수를 확정식으로
    # 🔴 8R 부류 A — 서브쿼리는 **펀드를 하나로 특정**해야 한다. 이름 필터·펀드키 핀이 살아남지 않았으면
    #    Ground 의 고유명으로 되살리고, 그것도 없으면 확정식을 쓰지 않는다 — 임의 펀드의 종목을 내보내는 것보다
    #    오거절이 낫다(7R Z7·AA18: 기본모수만 남아 전 우주 순자산 1위 펀드의 종목이 나갔다).
    joined = " AND ".join(preds)
    if not (_has_name_filter(f"FROM public_funds WHERE {joined}") or _has_fund_key_pin(joined)):
        if not name_token:
            return sql, False
        preds.append(f"REPLACE(p.itm_nm,' ','') LIKE '%{name_token.replace(' ', '')}%'")
    if not preds:
        return sql, False
    # 개수는 질문의 숫자('3개·5종목')가 우선 — 앞선 개별 조회 가드가 LIMIT 을 30 으로 올려둔 뒤라 SQL 의 LIMIT 은 믿을 수 없다
    m_q = re.search(r"(\d+)\s*(?:개|종목|가지|위)", question)
    m_lim = re.search(r"\blimit\s+(\d+)", sql, re.I)
    k = int(m_q.group(1)) if m_q else (int(m_lim.group(1)) if m_lim else 10)
    # 서수 질의('두 번째로 많이 담은')는 그 순위까지 실어야 답이 있다 — LIMIT 1 이면 1위만 보고 2위를 답할 수 없다(AA18)
    m_ord = re.search(r"(첫|두|세|네|다섯|여섯|일곱|여덟|아홉|열|\d+)\s*번째", question)
    if m_ord:
        w = m_ord.group(1)
        k = max(k, int(w) if w.isdigit() else _ORDINAL_KO[w])
    k = min(max(k, 1), MAX_ROWS)
    extra = ", h.asset_type AS \"자산유형\"" if "asset_type" in hcols else ""
    extra += ", h.bas_dt AS \"기준일\"" if "bas_dt" in hcols else ""
    return (f"SELECT h.holding_nm AS \"종목명\", h.weight_pct AS \"비중_pct\"{extra} "
            f"FROM ext_fund_holdings h "
            f"WHERE h.itm_no = (SELECT h2.itm_no FROM ext_fund_holdings h2 "
            f"JOIN public_funds p ON h2.grp = p.mtco_itm_no AND h2.or_co = p.or_co_xtn_itt_cd "
            f"WHERE {' AND '.join(preds)} ORDER BY p.fd_nast_suma DESC LIMIT 1) "
            f"ORDER BY h.weight_pct DESC LIMIT {k}"), True


def qualify_join_columns(sql: str, ctx) -> tuple[str, list[str]]:
    r"""JOIN 의 비한정 모호 컬럼을 FROM 테이블(별칭)로 기계 한정한다. (보정된 SQL, 한정한 컬럼)

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


_MGR_COMPLEX_CONJ = re.compile(r"\bOVER\s*\(|\b(?:SUM|COUNT|AVG|MIN|MAX|TOTAL|GROUP_CONCAT|ROW_NUMBER|RANK|DENSE_RANK)\s*\(|\bSELECT\b", re.I)


def ensure_fund_manager_ranking(sql: str, question: str, notes: list | None = None) -> tuple[str, bool]:
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
    # 🔴 10R gold ③-B 4 — 질의가 **운용사 하나로 핀돼 있으면** 운용사 랭킹이 아니다(그 운용사 안의 랭킹이다).
    #    FND-011 실측: Ground 가 코드 하나를 핀했는데 템플릿이 운용사 집계로 덮어 질문을 통째로 바꿨다.
    if re.search(r"\bor_co_xtn_itt_cd\s*\)?\s*=\s*'[^']+'", sql, re.I) \
            and not re.search(r"\bor_co_xtn_itt_cd\s*\)?\s*IN\s*\(", sql, re.I):
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
        for c in _flat_conjuncts(m_w.group(1)):     # 8R 뿌리 β — 기본모수 주입이 만든 괄호 안의 부가 절도 보존한다
            if _MGR_SKIP_CONJ.search(c):
                continue
            if _MGR_COMPLEX_CONJ.search(c):
                # 6R P (5R V5) — 윈도우·집계·서브쿼리 절은 템플릿의 GROUP BY 와 어긋나 실행 오류(misuse of window function)를 낸다.
                #    부가 절은 **단순 술어(col op 리터럴 · IN · LIKE · IS NULL)** 만 옮기고 나머지는 폐기·기록한다.
                if notes is not None:
                    notes.append(f"부가 절 폐기(단순 술어 아님): {c.strip()[:60]}")
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
            f"CAST(ROUND(SUM(p.fd_nast_suma)/100000000.0) AS INTEGER) || '억원' AS \"순자산_억원\" "
            f"FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no "
            f"WHERE {where} GROUP BY 1 ORDER BY {order} LIMIT {k}"), True


_COUNT_RANK_Q = re.compile(r"많이|많은|개수\s*(?:기준|순)|수\s*기준")
_AMOUNT_AXIS_Q = re.compile(r"순자산|규모|자산\s*총|자산이|금액")
_GROUP_AXIS = re.compile(r"\bgroup\s+by\b(.*?)(?=\bhaving\b|\border\s+by\b|\blimit\b|$)", re.I | re.S)


def ensure_fund_entity_count_ranking(sql: str, question: str) -> tuple[str, bool]:
    """개체(수탁사·판매사…) **개수 랭킹**의 정렬 축을 `COUNT(DISTINCT 펀드키)` 로. (SQL, 보정했는지)

    🔴 11R KG ③-10 (부류 D·G) — `KG-008`("공모펀드를 가장 많이 수탁하는 수탁사 상위 3개")이 개수 질문인데
       `ORDER BY SUM(fd_nast_suma)` 로 정렬하고, `COUNT(*)`(클래스수)를 "257개의 펀드" 라 명시했다(거짓값 2중).
       형제 `AA16` 은 질문이 명시적으로 '펀드 수 기준' 인데도 1,827·1,656·1,466(클래스수)을 답했다.
       gold 는 펀드수 축 — 홍콩상하이 **714** · 국민 **516** · 씨티 **465** · 하나 399 · 신한 307(DB 실측).
    운용사 축(`or_co_xtn_itt_cd`)은 `ensure_fund_manager_ranking` 템플릿이 먼저 처리한다(가드 중복 0 —
    그 템플릿이 이미 펀드수·클래스수를 싣고 나가므로 여기서는 `"펀드수"` 존재로 걸러진다).
    """
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:union|join)\b", sql, re.I) \
            or re.search(r'"펀드수"', sql):                   # 멱등
        return sql, False
    if not (_COUNT_RANK_Q.search(question) and _MGR_RANK_Q.search(question)) or _AMOUNT_AXIS_Q.search(question):
        return sql, False
    m_grp = _GROUP_AXIS.search(sql)
    m_ord = re.search(r"\border\s+by\b(.*?)(?=\blimit\b|$)", sql, re.I | re.S)
    if not m_grp or not m_ord:
        return sql, False
    axis = m_grp.group(1).strip()
    if axis.isdigit():                                  # 위치 표기 — SELECT 의 그 항목을 본다
        frm = re.search(r"\bfrom\b", sql, re.I)
        items = _split_select_items(re.sub(r"^\s*select\s+(distinct\s+)?", "", sql[:frm.start()], flags=re.I))
        axis = items[int(axis) - 1] if 0 < int(axis) <= len(items) else ""
    if not _ENTITY_AXIS.search(axis) or re.search(r"\b(?:itm_no|itm_nm|mtco_itm_no|rptt_ksd_itm_no)\b", axis, re.I):
        return sql, False                               # 펀드 식별 축은 개체 랭킹이 아니다(랭킹 가드 담당)
    frm = re.search(r"\bfrom\b", sql, re.I)
    head = sql[:frm.start()].rstrip()
    # 🔴 16R KG ③-3 — **별칭 유일화는 충돌한 원 항목을 지우는 것으로 끝낸다.** 14R 은 접미(`__g`)로 피했지만
    #    HCX 의 `COUNT(*) as 펀드수`(= 클래스수)가 결과에 남아 답변기가 그쪽을 읽었다(KG-008). 형제 `AA16` 은
    #    별칭 충돌이 없어서 같은 질문을 ✅ 로 답한다 — 축이 하나뿐이면 조립도 안 틀린다. 그러니 충돌 항목을 지운다.
    m_sel = _SELECT_HEAD.match(head)
    if m_sel:
        kept = [it for it in _split_select_items(head[m_sel.end():])
                if not re.search(r"\bAS\s+\"?(?:펀드수|클래스수)\"?\s*$", it.strip(), re.I)]
        head = head[:m_sel.end()] + ",".join(kept)
    add = (f', COUNT(DISTINCT {_FUND_KEY_EXPR}) AS "펀드수", COUNT(*) AS "클래스수" ')
    return head + add + sql[frm.start():m_ord.start()] + ' ORDER BY "펀드수" DESC ' + sql[m_ord.end():], True


_ENTITY_RANK_ALIAS = re.compile(r'AS\s+"(펀드수)"', re.I)


def _entity_count_rank_answer(sql: str, rows: str, n: int) -> str | None:
    """개체(수탁사·판매사) 개수 랭킹 답변을 기계 조립한다 — **SQL 행 순서를 그대로** 옮긴다. 아니면 None.

    🔴 14R KG ③-4 — `KG-008` 실측: SQL 이 gold 순서(714·516·465)를 돌려주는데 답변기가 `수탁금액` 순으로
       재정렬하고 숫자는 클래스수를 옮겼다. 랭킹 질의는 예외 없이 기계 조립 경로로 보낸다.
       값 축은 **가드가 심은 별칭만** 인정하고, 동명 컬럼이 둘이면 조립하지 않는다(KG ③-3).
    """
    m = _ENTITY_RANK_ALIAS.search(sql)
    grp = _GROUP_AXIS.search(sql)
    if n < 1 or not _FUND_TBL.search(sql) or not m or not grp:
        return None
    fund_col = m.group(1)
    cls_col = fund_col.replace("펀드수", "클래스수")
    lines = rows.splitlines()
    if len(lines) != n + 1:
        return None
    cols = [c.strip() for c in lines[0].split(" | ")]
    if cols.count(fund_col) != 1 or cls_col not in cols:
        return None                       # 동명 컬럼이 둘이면 값 축을 확정할 수 없다
    fi, ci = cols.index(fund_col), cols.index(cls_col)
    ei = next((i for i in range(len(cols)) if i not in (fi, ci)), None)
    if ei is None:
        return None
    labeled, _ = label_code_columns(rows, sql)      # 코드는 정본 이름(코드) 으로 굽는다
    body = labeled.splitlines()[1:] if len(labeled.splitlines()) == n + 1 else lines[1:]
    basis = [w for w, pat in (("판매중", r"sale_yn\s*=\s*'판매중'"), ("공모", r"prvo_pbff_desc\s*=\s*'공모'"))
             if re.search(pat, sql, re.I)]
    scope = ("·".join(basis) + " 기준, " if basis else "") + \
            f"펀드 = 운용사 종목번호 기준·클래스 = 판매 단위, 기준일 {gate.DATA_CUTOFF}"
    out = [f"조회 결과 펀드 수 상위 {n}개입니다 ({scope}).", ""]
    for i, ln in enumerate(body, 1):
        parts = [p.strip() for p in ln.split(" | ")]
        if len(parts) != len(cols):
            return None
        try:
            f_, c_ = int(float(parts[fi].replace(",", ""))), int(float(parts[ci].replace(",", "")))
        except ValueError:
            return None
        out.append(f"{i}. {parts[ei] or '(이름 미수록)'}: 펀드 {f_:,}개(클래스 {c_:,}개)")
    return "\n".join(out)


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
        # 10R ③-6 — 표시 열은 이미 천 단위 구분자가 찍혀 온다(`_cell`). 콤마를 떼고 다시 굽는다(멱등)
        eok_n = eok[:-2].replace(",", "") if eok.endswith("억원") else ""
        fund_part = f"펀드 {f_:,}개(클래스 {c_:,}개)"
        asset_part = f"순자산 {int(eok_n):,}억원" if eok_n.lstrip("-").isdigit() else f"순자산 {eok}"
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
# (KG 1R S3) 국가어 사전은 코드 상수가 아니라 KG Country 노드(shared/fund_country_auto.yaml, codebooks/fund_country_tag.csv)에서
#   읽는다 — _country_tag_map(). '대만·호주·말레이시아…' 코드북 17국 전부가 자동으로 확정식 대상이 된다(KG-021 사전 밖 오거절).


def ensure_fund_country_tag(sql: str, question: str, name_token: str | None = None) -> tuple[str, bool]:
    """국가 질의의 지역 컬럼 오용을 태그 확정식으로 교체. (보정된 SQL, 보정했는지)

    2026-09-01 FND-026 재검 실측 — 국가태그 규칙이 실려도 플래너가 ① fd_ivst_rgn_desc='중국'
    (없는 값 — 기각) ② 재생성서 ='글로벌' (있는 값 — 통과·오모수: 중국 아닌 글로벌 펀드가 LIMIT 을
    도배) ③ 태그를 써도 wrap 없는 LIKE '%,CHN,%' 로 목록 처음·끝의 태그 98/560행을 놓친다.
    조치: 질문의 국가어에 대해 ① fd_ivst_rgn_desc 등호 조건을 정식 태그식으로 교체
    ② wrap 없는 태그 LIKE 를 ','||…||',' 정식형으로 교정. 국가어 없는 질의·지역어 질의는 불개입.
    """
    if not _FUND_TBL.search(sql):
        return sql, False
    if name_token and _has_name_filter(sql):
        # 6R I′ — 이름 토큰이 실린 개별 조회엔 국가 태그를 싣지 않는다(태그는 클래스별 결측 — 이름이 특정한 펀드의 합계를 깬다, W2).
        #    HCX 가 이미 쓴 태그·속성명 절도 같은 이유로 걷어낸다(W3 'JPN' 절이 14클래스 → 1클래스).
        stripped = _strip_tag_predicates(sql)
        return (stripped, True) if stripped != sql else (sql, False)
    # 유형 축('중국주식 유형')은 국가어가 소분류 값 안에 붙어 있어 독립 낱말 판정을 통과하지 못한다 — R10 분기는 값 포함으로 판정
    ptn_q = _ptn_value_in_question(question) if "유형" in question else None
    hits = [(w, t, sp) for w, t, sp in _country_tag_map()
            if _country_in_question(w, question) or (ptn_q and w in ptn_q)]
    if not hits:
        return sql, False
    # 긴 낱말 우선 정렬이라 hits[0] 이 주 국가('인도네시아' > '인도'). 부분어 포함 관계의 짧은 낱말은 버린다.
    primary = hits[0]
    hits = [h for h in hits if h is primary or h[0] not in primary[0]]
    q_tags = {t: (w, sp) for w, t, sp in hits}

    def canon_of(tag: str) -> str:
        c = f"',' || prfd_attr_cds || ',' LIKE '%,{tag},%'"
        w, sp = q_tags[tag]
        return f"({c} OR REPLACE(itm_nm,' ','') LIKE '%{w}%')" if sp else c

    # R10 — '유형' 어휘 + 소분류 값(zrin_ptn_nm) 이 질문에 있으면 축은 **유형**이다(KG-012 '중국주식 유형' 205/522 ≠ CHN 태그 248)
    ptn = _ptn_value_in_question(question) if "유형" in question else None
    primary_canon = f"zrin_ptn_nm = '{ptn}'" if ptn else canon_of(primary[1])
    orig = sql

    def _tag_of(literal: str) -> str | None:
        tok = literal.strip("%,").strip()
        return tok if tok in q_tags else None

    # ⓐ 지역·설립국 컬럼 오용 → 주 canon (fd_estb_ctry_cd: KG-021 '대만' → 설립국 410=한국 69펀드)
    # 6R F4 — 등호뿐 아니라 LIKE 도(KG-012: `fd_ivst_rgn_desc LIKE '%중국%'` 이 통과해 0행 "0개")
    sql = re.sub(r"(?:\b\w+\.)?fd_ivst_rgn_desc\s*(?:=\s*'[^']*'|LIKE\s+'[^']*')", primary_canon, sql, flags=re.I)
    sql = re.sub(r"(?:\b\w+\.)?fd_estb_ctry_cd\s*=\s*'?\d+'?", primary_canon, sql)
    # ⓑ 태그 절 — HCX 가 **어떤 태그**를 썼든(T4: IND→IDN · S6 콤마 없는 LIKE · 템플릿 잔재 <CHN>) 질문의 국가로 접는다
    def _fix_tag(m: re.Match) -> str:
        t = _tag_of(m.group(1))
        return canon_of(t) if t and not ptn else primary_canon
    sql = re.sub(r"(?:',' \|\| )?(?:\b\w+\.)?prfd_attr_cds(?: \|\| ',')?\s+LIKE\s+'([^']*)'", _fix_tag, sql, flags=re.I)
    # ⓒ 속성 명칭 절(zrin_attr_nms LIKE '%인도%') — 낱말 무관하게 국가 조건이면 canon ('인도' 가 '인도네시아' 를 삼킨다)
    def _fix_nms(m: re.Match) -> str:
        w = m.group(1).strip("%,")
        t = next((t for t, (qw, _) in q_tags.items() if qw == w), None)
        return canon_of(t) if t and not ptn else (primary_canon if any(qw in w or w in qw for qw, _, _ in hits) else m.group(0))
    sql = re.sub(r"(?:',' \|\| )?(?:\b\w+\.)?zrin_attr_nms(?: \|\| ',')?\s+LIKE\s+'([^']*)'", _fix_nms, sql, flags=re.I)
    # ⓓ 국가어 이름절(itm_nm LIKE '%미국%')이 태그 절과 OR 로 묶여 있으면 이름절을 걷어낸다(3R C-2 — 통화 표기·역외 무태그 행 혼입,
    #    T13 미국 611 vs 태그 333). 희소 태그(canon 이 이미 이름 폴백을 품음)도 같은 접기로 수렴한다.
    for w, t, sp in hits:
        name = rf"(?:REPLACE\(\s*(?:\w+\.)?itm_nm\s*,\s*' '\s*,\s*''\s*\)|(?:\b\w+\.)?itm_nm)\s+LIKE\s+'%{re.escape(w)}%'"
        c = re.escape(primary_canon if (ptn or t == primary[1]) else canon_of(t))
        sql = re.sub(rf"\(\s*{c}\s+OR\s+{name}\s*\)", lambda m: primary_canon if (ptn or t == primary[1]) else canon_of(t), sql, flags=re.I)
        sql = re.sub(rf"\(\s*{name}\s+OR\s+{c}\s*\)", lambda m: primary_canon if (ptn or t == primary[1]) else canon_of(t), sql, flags=re.I)
    # 같은 정식형이 OR 로 중복되면 하나로 접는다 — `(canon OR canon)` / `canon OR canon`
    for c_txt in {primary_canon, *[canon_of(t) for t in q_tags]}:
        c = re.escape(c_txt)
        sql = re.sub(rf"\(\s*{c}\s+OR\s+{c}\s*\)", c_txt, sql, flags=re.I)
        sql = re.sub(rf"{c}\s+OR\s+{c}", c_txt, sql, flags=re.I)
    return sql, sql != orig


_TAG_PREDICATE = re.compile(
    r"(?:',' \|\| )?(?:\b\w+\.)?(?:prfd_attr_cds|zrin_attr_nms)(?: \|\| ',')?\s+LIKE\s+'[^']*'|(?:\b\w+\.)?fd_ivst_rgn_desc\s*(?:=\s*'[^']*'|LIKE\s+'[^']*')", re.I)


def _strip_tag_predicates(sql: str) -> str:
    """WHERE 의 태그·속성명·지역 술어만 걷어낸다(괄호 묶음의 다른 술어는 보존 — T14 '(코드 AND 태그 AND 이름)'). 빈 자리는 1=1 로 메운 뒤 정리."""
    frm = re.search(r"\bwhere\b", sql, re.I)
    if not frm:
        return sql
    head, body = sql[:frm.end()], sql[frm.end():]
    if not _TAG_PREDICATE.search(body):
        return sql
    body = _TAG_PREDICATE.sub("1=1", body)
    for _ in range(3):
        body = re.sub(r"\(\s*1=1\s*\)", "1=1", body)
        body = re.sub(r"\b1=1\s+(?:AND|OR)\s+", "", body, flags=re.I)
        body = re.sub(r"\s+(?:AND|OR)\s+1=1\b", "", body, flags=re.I)
    body = re.sub(r"\bwhere\s*1=1\s*(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", "", head[-5:] + body, flags=re.I) if False else body
    return head + body


@lru_cache(maxsize=1)
def _sparse_country_tags() -> frozenset:
    """기본모수(판매중·공모)에서 태그 행이 **0** 인 국가(대만·호주…) — 이름 폴백(itm_nm LIKE)을 병기한다. 태그가 1행이라도 있으면
    태그가 축이다(3R C-2: 이름절은 통화 표기·역외 무태그 행을 끌어온다). DB 실측, 하드코딩 아님."""
    ctx = _ev_ctx()
    tags = [raw for n in ctx.kg_nodes if n.node_type == "Country" for t, c, raw in ctx.kg_aliases.get(n.node_id, ()) if t == "public_funds"]
    con = connect_readonly()
    try:
        out = {tag for tag in tags if con.execute(
            "SELECT COUNT(*) FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' AND ','||prfd_attr_cds||',' LIKE ?",
            (f"%,{tag},%",)).fetchone()[0] == 0}
    finally:
        con.close()
    return frozenset(out)


@lru_cache(maxsize=1)
def _country_tag_map() -> tuple:
    """(질문 낱말, ISO3 태그, 희소 여부) — Country 노드(shared/fund_country_auto.yaml, token alias) 라벨 + enums 통칭. 긴 낱말 먼저.
    '한국'·'국내' 는 상장/국내 질의와 충돌하므로 제외(Region_Korea 규칙과 같은 결)."""
    ctx = _ev_ctx()
    syn = _synonym_keys(ctx)
    sparse = _sparse_country_tags()
    out = []
    for node in ctx.kg_nodes:
        if node.node_type != "Country":
            continue
        raws = [raw for t, c, raw in ctx.kg_aliases.get(node.node_id, ()) if t == "public_funds"]
        if not raws or not node.label_ko or node.label_ko in ("한국", "국내"):
            continue
        for w in [node.label_ko] + _syn_terms(ctx, node, node.label_ko):
            out.append((w, raws[0], raws[0] in sparse))
    return tuple(sorted(out, key=lambda x: -len(x[0])))


@lru_cache(maxsize=1)
def _ptn_values() -> tuple:
    con = connect_readonly()
    try:
        return tuple(sorted({r[0].strip() for r in con.execute("SELECT DISTINCT zrin_ptn_nm FROM public_funds WHERE zrin_ptn_nm IS NOT NULL") if r[0]},
                            key=len, reverse=True))
    finally:
        con.close()


def _ptn_value_in_question(question: str) -> str | None:
    """질문에 든 제로인 소분류(zrin_ptn_nm) 값 — 가장 긴 것. 없으면 None.

    🔴 16R KG ③-7 (`Z5` 회귀) — **공백을 지우고 대조하면 두 낱말이 붙어 없던 값이 생긴다.** 실측:
       "글로벌 주식형 공모펀드는 몇 개야?" 를 공백 없이 보면 `글로벌주식`(약관분류 값)이 걸려 자산군 축
       가드가 통째로 꺼졌고, 그 자리에 HCX 의 반쪽 인용(`= '주식형' OR (… IS NULL AND …)`)이 남아 53/73 이 됐다.
       약관분류 값은 **질문에 공백 없이 그대로** 나올 때만 그 축으로 읽는다("중국주식 유형"·"인도주식 유형인").
    """
    return next((v for v in _ptn_values() if len(v) >= 3 and v in question), None)


_BTYP_AXIS_COLS = re.compile(r"\b(?:zrin_btyp_nm|zrin_ptn_nm|zrin_pcd)\b", re.I)


@lru_cache(maxsize=1)
def _btyp_values() -> tuple:
    """유형(zrin_btyp_nm)의 실제 값 — 긴 것부터. 🔴 '…형' 으로 끝나는 3자 이상만 확정식 대상으로 쓴다:
    '기타'·'MMF'·'특별자산' 같은 값은 질문의 보통명사와 겹쳐 오주입을 낸다."""
    con = connect_readonly()
    try:
        vals = {r[0].strip() for r in con.execute(
            "SELECT DISTINCT zrin_btyp_nm FROM public_funds WHERE zrin_btyp_nm IS NOT NULL") if r[0]}
    finally:
        con.close()
    return tuple(sorted((v for v in vals if len(v) >= 3 and v.endswith("형")), key=len, reverse=True))


def _replace_axis_or_inject(sql: str, cond: str, axis_rx: str, lit: str) -> tuple[str, bool]:
    """확정식 `cond` 를 WHERE 에 심는다 — 같은 값 리터럴을 쓰던 최상위 절이 있으면 **그 자리를 교체**한다.

    HCX 가 없는 컬럼으로 축을 쓴 경우(`asset_class = '중국주식'`)에도 리터럴이 같으므로 교체가 성립한다 —
    컬럼 이름을 사전과 대조하지 않고도 환각 술어가 사라진다(가드 중복 0).
    """
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        anchor = _SQL_ANCHOR.search(sql) or re.search(r"\blimit\b", sql, re.I)
        return (f"{sql[:anchor.start()]}WHERE {cond} {sql[anchor.start():]}", True) if anchor else (sql, False)
    conjs = _flat_conjuncts(m_w.group(1))
    kept = [c for c in conjs if f"'{lit}'" not in c and not re.search(axis_rx, c, re.I)]
    if len(kept) == len(conjs):
        kept = conjs
    body = " " + " AND ".join([cond] + kept) + " "
    return sql[:m_w.start(1)] + body + sql[m_w.end(1):], True


def ensure_fund_type_axis(sql: str, question: str) -> tuple[str, bool]:
    """KG 4R G3 / 6R P′ — **질문이 고른 유형 축이 SQL 어디에도 없으면 확정식을 AND 로 주입한다.** (SQL, 주입했는지)

    확정식 가드들이 지금까지 「찾아 바꾸기」만 했다: 후보 절이 하나도 없으면 침묵한다. 6R Y7 실측 —
    "주식형 펀드 순자산이 가장 큰 운용사 3곳" 의 최종 SQL WHERE 가 `p.sale_yn AND p.prvo_pbff_desc` 뿐이라
    답변이 V5(전체 랭킹)와 바이트 단위로 같았다(trace 의 `[Route] … 값 ['주식형']` 은 라우터가 값을 알아봤다는 뜻).
    운용사 확정식이 부가 절을 **버린** 것이 아니라(notes 가 비어 있다) HCX 가 애초에 안 쓴 것이므로,
    처방은 '보존' 이 아니라 '주입' 이다.
    불개입: 유형 축 절이 이미 있음(zrin_btyp_nm·zrin_ptn_nm·zrin_pcd) · 개별 조회(이름·키로 이미 특정) ·
            public_funds 아님 · 질문에 유형 값 없음.
    """
    if not _FUND_TBL.search(sql) or re.search(r"\bunion\b", sql, re.I):
        return sql, False
    if _has_name_filter(sql) or _has_fund_key_pin(sql):
        return sql, False
    q = question.replace(" ", "")
    # 🔴 16R KG ③-6 (부류 H · Z11·Z10·AA6·AA7) — **약관분류(`zrin_ptn_nm`)는 유형 축보다 잘게 나눈 별개 축이고,
    #    질문이 그 값을 지명하면 확정식이 그 축이다.** 13R 의 ✅ 는 운이었다 — 못 박는 확정식이 없어 HCX 가
    #    매 라운드 새 컬럼을 지어냈고(`Z11` 15R: `asset_class='중국주식'` — 존재하지 않는 컬럼 → 오거절),
    #    14R 이 이 항을 자산군 `IN` 안건과 묶어 보류한 대가가 ✅ 1건이었다. 두 축은 분리해 집행한다.
    # 질문에 든 유형 값 — 긴 것부터. 긴 값에 포함되는 짧은 값('주식형' ⊂ '해외주식형')은 같은 낱말이다
    picked: list[str] = []
    for v in _btyp_values():
        if v in q and not any(v in p for p in picked):
            picked.append(v)
    ptn = _ptn_value_in_question(question)
    if ptn:
        if re.search(rf"\bzrin_ptn_nm\s*=\s*'{re.escape(ptn)}'", sql, re.I):
            return sql, False                                    # 멱등
        # 질문이 부르지 않은 유형 축 절은 함께 걷는다 — AA7 실측: HCX 의 `zrin_btyp_nm LIKE '%일본%'` 가
        # 남으면 확정식과 교집합이 0 이 된다. 질문이 부른 유형(Z10·AA6 '해외주식형')은 그대로 둔다.
        stale = None if picked else r"\b(?:zrin_btyp_nm|zrin_pcd)\b"
        return _replace_axis_or_inject(sql, f"zrin_ptn_nm = '{ptn}'",
                                       r"\bzrin_ptn_nm\b" + (f"|{stale}" if stale else ""), ptn)
    val = picked[0] if picked else None
    if not val:
        return sql, False
    cond = f"zrin_btyp_nm = '{val}'"
    # 🔴 10R 부류 Z + ③-4(축소) — 종전엔 유형 축 절이 **있기만 하면** 불개입이라, HCX 가 축을 넓게 쓰면
    #    (9R Y7 `zrin_btyp_nm IN ('주식형','해외주식형')`) 가드가 자기를 껐다. 질문에 열거값과 **정확히 일치하는
    #    낱말이 하나뿐**이면 그 값 하나가 확정식이고, 다른 btyp 절은 교체한다. 총칭어('주식 펀드')일 때는
    #    질문에 열거값이 없으므로 여기 오지 않는다 — 확장은 KG 자산군 노드가 계속 담당한다.
    #    약관분류(zrin_ptn_nm)는 더 잘게 나눈 별개 축이라 건드리지 않는다(KG 부류 H).
    if _BTYP_AXIS_COLS.search(sql):
        m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
        if not m_w or len(picked) != 1 or _ptn_value_in_question(question) \
                or re.search(r"\bzrin_ptn_nm\b", sql, re.I):
            return sql, False
        conjs = _flat_conjuncts(m_w.group(1))
        axis = [c for c in conjs if re.search(r"\b(?:zrin_btyp_nm|zrin_pcd)\b", c, re.I)]
        if not axis:
            return sql, False                                   # 축 절이 최상위에 없다(서브식 안) — 불개입
        m_q = re.search(r"\b(\w+\.)?zrin_btyp_nm\b", axis[0], re.I)
        qual = (m_q.group(1) or "") if m_q else ""
        if len(axis) == 1 and re.fullmatch(rf"\(?\s*(?:{re.escape(qual)})?zrin_btyp_nm\s*=\s*'{re.escape(val)}'\s*\)?",
                                           axis[0].strip(), re.I):
            return sql, False                                   # 이미 확정식(한정자 포함) — 손대지 않는다
        kept = [c for c in conjs if c not in axis]
        new = sql[:m_w.start(1)] + " " + " AND ".join([qual + cond] + kept) + " " + sql[m_w.end(1):]
        return (new, True) if new != sql else (sql, False)
    m = re.search(r"\bwhere\b", sql, re.I)
    if not m:
        anchor = _SQL_ANCHOR.search(sql) or re.search(r"\blimit\b", sql, re.I)
        return (f"{sql[:anchor.start()]}WHERE {cond} {sql[anchor.start():]}", True) if anchor else (sql, False)
    e = m.end()
    stop = _SQL_ANCHOR.search(sql[e:]) or re.search(r"\blimit\b", sql[e:], re.I)
    body, rest = (sql[e:e + stop.start()], sql[e + stop.start():]) if stop else (sql[e:], "")
    return f"{sql[:e]} {cond} AND ({body.strip()}) {rest}".rstrip(), True


_NAME_UNION_AXES = ("N", "O")     # 테마·섹터 축 — 태그가 이름보다 성기다(KG-024 반도체: 태그 50 + 이름만 14 + wrap 누락 14 = 78). 코드 첫 글자 = 축


@lru_cache(maxsize=1)
def _attr_word_map() -> tuple:
    """(질문 낱말, 태그 코드들, 이름 병기 여부, 경계검사 여부) — FundAttribute 노드 전 축 (KG 2R N4).
    · enums 통칭('개방형' 등)은 포함 판정, 라벨(3자+ '반도체'·'인덱스'…)은 독립 낱말(경계) 판정.
    · 같은 라벨의 노드 여럿(럭셔리 N118/N147 · 인프라 · 친환경)은 코드 집합으로 병합 → OR canon.
    · 테마(N)·섹터(O) 축은 `OR REPLACE(itm_nm,' ','') LIKE '%라벨%'` 이름 병기(국가 희소 폴백과 같은 기계)."""
    ctx = _ev_ctx()
    by_word: dict[str, dict] = {}
    for node in ctx.kg_nodes:
        if node.node_type != "FundAttribute" or not node.label_ko or getattr(node, "provenance", "") == "label_conflict":
            continue                       # F1: 라벨 충돌 노드는 확정식 어휘에서도 뺀다
        raws = [raw for t, c, raw in ctx.kg_aliases.get(node.node_id, ()) if t == "public_funds"]
        if not raws:
            continue
        code = raws[0]
        for w, bounded in [(node.label_ko, True)] + [(s, False) for s in _syn_terms(ctx, node, node.label_ko)]:
            if len(w) < 3:
                continue
            e = by_word.setdefault(w, {"codes": [], "name_union": False, "bounded": bounded})
            if code not in e["codes"]:
                e["codes"].append(code)
            e["name_union"] = e["name_union"] or code[:1] in _NAME_UNION_AXES
    out = [(w, tuple(e["codes"]), e["name_union"], e["bounded"]) for w, e in by_word.items()]
    return tuple(sorted(out, key=lambda x: -len(x[0])))


def ensure_fund_attr_tag(sql: str, question: str) -> tuple[str, bool]:
    """속성 태그 축(설정형태 등)의 질문 어휘를 token 확정식으로 주입하고, 같은 낱말을 다른 컬럼에 쓴 절은 걷어낸다.

    일반 규칙(KG 1R R11): FundAttribute 노드 통칭('개방형·폐쇄형·단위형·추가형' = 코드북 이름 + '형')이 질문에 있으면
    `','||prfd_attr_cds||',' LIKE '%,<code>,%'` 가 유일한 조건식이다. KG-017: yaml 오서술로 `han_clas_policies LIKE '%폐쇄형%'`(클래스 정책
    컬럼) → 0행 "0개" 단언(실재 3펀드/6클래스). KG-018: 단위∧개방 직교 축을 HCX 가 통째로 버림(31/189).
    """
    if not _FUND_TBL.search(sql):
        return sql, False
    hits = [(w, codes, nu) for w, codes, nu, bounded in _attr_word_map()
            if (_boundary_hit(w, question) if bounded else w in question)]
    if not hits:
        return sql, False
    orig = sql
    made: list[str] = []
    for w, codes, name_union in hits:
        parts = [f"',' || prfd_attr_cds || ',' LIKE '%,{c},%'" for c in codes]
        if name_union:
            parts.append(f"REPLACE(itm_nm,' ','') LIKE '%{w}%'")
        canon = parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"
        made.append(canon)
        if canon in sql:
            continue
        m = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
        if m:
            # 같은 낱말·같은 코드를 쓴 타 컬럼/wrap 없는 절은 걷어낸다(KG-024: `prfd_attr_cds LIKE '%,N144,%'` 첫 토큰 14클래스 누락)
            # 🔴 14R KG ③-2 — **같은 컬럼**의 잔여 술어도 걷는다(11R ③-5 의 나머지 반쪽). KG-017 실측 회귀:
            #    확정식이 `prfd_attr_cds` 에 C104 를 주입했는데 HCX 가 **같은 컬럼**에 넣은 `'%,폐쇄,%'`(DB 0행)를
            #    안 걷어 3/6 → 0 이 됐다. 이 가드가 이번 호출에서 만든 canon 은 남긴다(KG-018 직교 축 2회 주입).
            kept = [c for c in guard.split_conjuncts(m.group(1))
                    if c.strip() in made
                    or (w not in c and not any(code in c for code in codes)
                        and not re.search(r"\bprfd_attr_cds\b", c, re.I))]
            sql = sql[:m.start(1)] + " " + " AND ".join(kept + [canon]) + " " + sql[m.end(1):] if kept else \
                sql[:m.start(1)] + " " + canon + " " + sql[m.end(1):]
        else:
            sql, _ = _append_exclusions(sql, [canon])
    return sql, sql != orig


# 🔴 16R KG ③-1 — 창(窓)을 20 → 45 자로 넓힌다. 교차질의는 「공모펀드와 <ETF 수식어> 국내 ETF는 각각 몇 개야?」라
#    펀드와 '몇 개' 사이에 ETF 수식어가 끼어 20자를 넘는다(X8 24자·KG-026 31자 — 두 문항이 이 창 하나 때문에
#    펀드단위 집계 교체를 한 번도 못 받았다). 펀드 가지가 아닌 SQL 은 `_FUND_TBL`·`COUNT(*)` 항목 조건이 막는다.
_Q_FUND_COUNT = re.compile(r"펀드[^?]{0,45}(?:몇\s*개|몇개|개수|몇\s*종)")
# 펀드키 = 운용사코드 / zero-pad 모펀드번호. 🔴 `COALESCE(…, itm_no)` 가 필수다 — 2026-09-02 재검 부수 발견:
#    역외펀드 110행은 mtco_itm_no 가 NULL 이라 키가 NULL 하나로 뭉쳐 COUNT(DISTINCT) 에서 통째로 빠졌다
#    (기본모수 distinct 2,930 vs gold 키 3,040). 정본은 eval gold_sql 의 키 형태 그대로.
# 🔴 정의는 guard.FUND_KEY_EXPR 한 곳이다 — enforce 슬롯({fund_key})과 코드 가드가 **같은 식**을 써야
#    섀도에서 둘이 같은 SQL 을 낸다. 2026-09-03 섀도에서 갈라져 있던 것을 합쳤다.
_FUND_KEY_EXPR = guard.FUND_KEY_EXPR
# 🔴 10R 재검 ③-B — **개수·열거 축의 정본은 `rptt_ksd_itm_no`** 다. 도메인 정본(public_funds.md §4.1):
#    rptt = "같은 펀드 여러 클래스의 대표 번호" · mtco = "운용 단위(모펀드) 키". DB 실측으로 확증된다 —
#    mtco 는 398 rptt 그룹 / 2,686 클래스행(모수의 29%)에서 **클래스 단위로 발급**돼 있어(W5 솔로몬2호
#    rptt 031910531100 하나에 mtco 531101~531107) `_FUND_KEY_EXPR` 이 한 펀드를 클래스 수만큼 쪼갠다.
#    🔴 **랭킹·분포의 `COUNT(DISTINCT 펀드키)` 는 이 축으로 바꾸지 않는다** — 정본 펀드 수가 3,040 → 1,919 로
#    움직여 R1·T1·V5 의 gold 가 흔들린다. 축을 나눈다: **개수/열거 = rptt · 모수 집계 = 현행 펀드키.**
#    NULLIF 는 판매완료 구간의 플레이스홀더(KR0000000000)를, COALESCE 폴백은 rptt NULL(모수의 1.2%)을 받는다.
_FUND_GROUP_EXPR = f"COALESCE(NULLIF(TRIM(rptt_ksd_itm_no),'KR0000000000'), {_FUND_KEY_EXPR})"


def ensure_fund_distinct_count(sql: str, question: str) -> tuple[str, bool]:
    """펀드 개수 질의의 COUNT(*) 를 펀드단위 COUNT(DISTINCT 키)+클래스수 병기로 교체.

    2026-09-01 FND-034 실측 — 클래스/펀드 구분 누락 6번째 재발: Ground·코드·기본모수 전부
    맞았는데 COUNT(*) 가 클래스 850 을 '펀드 850개' 로 답했다(정답 207펀드). 운용사질의 규칙에
    워크드 예시까지 실려도 무시된다 — HANDOFF 대기 항목 '반복되면 기계 주입' 발동.
    발동 조건: ① public_funds 단일 테이블(JOIN·GROUP BY 없음) ② SELECT 가 COUNT(*) 단독
    ③ 질문이 '펀드 … 몇 개/개수' 형 ④ 질문에 '클래스' 없음(클래스 수를 물으면 불개입).
    클래스 수는 지우지 않고 병기한다 — 답변기가 두 기준을 함께 말할 재료.

    🔴 2026-09-03 — enforce 슬롯(`public_funds.펀드단위.enforce`, mark FUNDUNIT)이 먼저 같은 일을 한다.
       슬롯이 처리했으면 침묵한다(절차 §2-4). 가드 삭제는 두 라운드 뒤(§5).
       섀도 실측: 84문항 중 '둘 다·동일 SQL' 12 · '슬롯만 발동' 5(전부 UNION 가지) · '가드만 발동' 0.
    """
    if "M:FUNDUNIT" in sql:
        return sql, False
    if not _FUND_TBL.search(sql) or re.search(r"\b(?:union|group\s+by)\b", sql, re.I):
        return sql, False
    if not _Q_FUND_COUNT.search(question) or "클래스" in question:
        return sql, False
    # 6R F6 — JOIN 은 public_funds + 짝 ext_* 만(타 상품군 조인은 불개입). 키 식은 FROM 별칭으로 한정해 ambiguous 를 막는다 (X19·KG-035).
    joined = {t for t in guard.sql_tables(sql) if t != "public_funds"}
    if joined and not joined <= {e for e, m in _EXT_PAIR.items() if m == "public_funds"}:
        return sql, False
    # 🔴 16R KG ③-1 — **교체는 SELECT 항목 단위다.** 종전엔 `SELECT` 바로 뒤에 `COUNT(*)` 가 오는 문장만 잡아
    #    교차질의 가지(`SELECT '공모펀드' AS 구분, COUNT(*) …`)가 **라벨 리터럴에 막혀 한 번도 발화하지 않았다**
    #    (X8·X9·KG-025·KG-026 이 전부 클래스수를 '펀드' 로 답했다). 위치·앞선 라벨·별칭과 무관하게 찾는다.
    #    새 분해기를 만들지 않고 `_wrap_sort_col` 이 쓰는 `_split_select_items` 를 그대로 재사용한다.
    frm = re.search(r"\bfrom\b", sql, re.I)
    m_sel = _SELECT_HEAD.match(sql)
    if not frm or not m_sel or '"펀드수"' in sql:          # 멱등
        return sql, False
    items = _split_select_items(sql[m_sel.end():frm.start()])
    idx = next((i for i, it in enumerate(items)
                if re.fullmatch(r"\s*COUNT\s*\(\s*\*\s*\)(?:\s+AS\s+(?:\"[^\"]+\"|\w+))?\s*", it, re.I)), None)
    if idx is None:
        return sql, False
    qual = ""
    if joined:
        mm = _FROM_MASTER.search(sql)
        qual = ((mm.group(2) or mm.group(1)) + ".") if mm else "public_funds."
    key = (_FUND_KEY_EXPR.replace("or_co_xtn_itt_cd", qual + "or_co_xtn_itt_cd")
           .replace("mtco_itm_no", qual + "mtco_itm_no").replace(", itm_no)", f", {qual}itm_no)"))
    items[idx] = f' COUNT(DISTINCT {key}) AS "펀드수", COUNT(*) AS "클래스수" '
    return sql[:m_sel.end()] + ",".join(items) + sql[frm.start():], True


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
    kept = []
    # 🔴 8R 부류 B — **주입은 교체다**: 질문의 호수뿐 아니라 SQL 의 **모든 호수 술어**를 걷어낸다. 7R AA20 실측:
    #    3호 확정식을 넣었는데 HCX 의 `itm_no LIKE '%2호%'` 가 (기본모수 주입이 만든 괄호 안에서) 살아남아
    #    항상-거짓이 됐다 — 거짓 0(gold 8클래스). 괄호 그룹도 `_flat_conjuncts` 로 들어간다.
    for c in _flat_conjuncts(body):
        if not re.search(r"\d+\s*호", c):
            kept.append(c)
            continue
        # 6R J′ — 호수 절을 걷어낼 때 절 안의 **이름 LIKE 리터럴**은 호수만 떼어 보존한다(W6: HCX 의 이름+4호 결합 LIKE 를 통째로 제거해
        #    이름 필터가 사라지고 목록 경로로 빠졌다). 호 경계는 아래 GLOB 이 맡는다.
        m_like = re.search(r"((?:REPLACE\((?:\w+\.)?itm_nm,' ',''\)|(?:\b\w+\.)?itm_nm)\s+LIKE\s+')%([^%']*)%'", c, re.I)
        if m_like:
            lit = re.sub(r"\d+\s*호", "", m_like.group(2)).replace(" ", "").strip()
            if len(lit) >= 3:
                kept.append(f"{m_like.group(1)}%{lit}%'")
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
    scale = _grade_scale()                       # 선언에서 온 서열 — 코드 상수 아님 (2026-09-04)
    letter, suffix, direction = hits[0]
    letter = letter.upper()
    if suffix:
        notch = letter + suffix
    elif direction == "이상":                    # 급 전체 포함 — 그 급의 최하단 표기부터
        notch = next((g for g in reversed(scale) if g in (letter + "-", letter + "0", letter)), None)
    else:                                        # 이하 — 그 급의 최상단 표기부터
        notch = next((g for g in scale if g in (letter + "+", letter + "0", letter)), None)
    if notch not in scale:
        return sql, False
    idx = scale.index(notch)
    grades = scale[: idx + 1] if direction == "이상" else scale[idx:]
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


def _where_body(sql: str) -> str:
    """WHERE 절 본문(GROUP/ORDER/LIMIT 앞)만. 없으면 빈 문자열.

    "이 컬럼이 SQL 에 있나" 를 필터 유무로 읽으면 **SELECT 표시 컬럼**에 걸려 가드가 자기를 끈다
    (2026-09-04 #62: ensure_coupon_type_split · 2026-09-01 BND-S-010: kind 필터 검사). 판정은 여기서."""
    m = re.search(r"\bWHERE\b", sql, re.I)
    if not m:
        return ""
    t = _WHERE_TAIL.search(sql, m.end())
    return sql[m.end(): t.start() if t else len(sql)]


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


_PAST_MATURITY_Q = re.compile(r"만기\s*(?:가|이)?\s*(?:지난|경과|끝난|넘은|도래한)|과거\s*만기|상장\s*폐지|만기\s*된")


def _rank_exclusions(sql: str, question: str) -> list[str]:
    """고위험제외·수익률정상 중 SQL 에 빠진 절 — 질문이 그 범주를 명시하면 그 절은 건너뛴다.

    '사모 채권 추천'·'위험 높은 채권 순위'·'C0 등급' 처럼 사용자가 제외 대상을 콕 집으면
    그 절을 주입하는 순간 정답 모수가 통째로 사라진다 — 범주 언급 = 우회."""
    excl = []
    if re.search(r"applied_yield", sql, re.I) and not re.search(r"applied_yield\s*>\s*0", sql):
        excl.append("applied_yield > 0")
    # 구매가능 규칙 — 만기 경과 채권은 추천·랭킹 모수가 아니다. 2026-09-02 실측: '한전 채권 수익률 낮은 순' 에
    # 만기 2026-08-20 경과 1063호가 1·2위. 전체 만기 경과 49행(최대 5.699%). gold 채권 랭킹 19개 중 17개가 이미
    # 이 절을 쓴다(나머지 2개도 하한 있음). 질문이 만기 경과를 콕 집으면(범주 언급 = 우회) 건너뛴다.
    if not re.search(r"mat_dt\s*>=?\s*\d", sql) and not _PAST_MATURITY_Q.search(question):
        excl.append(f"mat_dt >= {BUYABLE_INT}")
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


# 표면금리 축 낱말 — 확정 낱말만 싣는다. 단독 '금리·이자율' 은 다의라 매핑하지 않는다
# (_TOP_YIELD_Q 가 수익률과 한 부류로 묶고, gold 채권 문항에 단독 '금리' 정렬 정본이 0건이다).
_SRFC_Q = re.compile(r"표면\s*(?:금리|이자율|이율)|쿠폰\s*(?:금리|이자율|이율)?|coupon", re.I)
_YIELD_AXIS_Q = re.compile(r"수익률|이자수익|연\s*환산")      # 두 축을 함께 말하면 불개입
_SRFC_LOW_Q = re.compile(r"낮은\s*순|(?:가장|제일|젤)\s*낮|최저|작은\s*순")
_ORDER_YIELD_COL = re.compile(
    r"(ORDER\s+BY\s+(?:MAX|MIN)?\(?\s*)(applied_yield|after_tax_yield|corp_pretax_yield|buy_yield)\b", re.I)


_ROLLUP_HEAD = re.compile(r"\b(?:COUNT|AVG|SUM|GROUP_CONCAT)\s*\(", re.I)


def _select_add_col(sql: str, col: str) -> str:
    """SELECT 목록에 컬럼 하나를 덧붙인다 — `*`·집계 롤업·이미 있으면 그대로.

    MAX/MIN 머리는 대표행 형(GROUP BY pd_no + 정렬 컬럼 극값)이라 목록 질의다 — GROUP BY 가 있으면
    맨 컬럼을 덧붙여도 되고(SQLite), 없으면 롤업이므로 손대지 않는다."""
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm:
        return sql
    head, rest = sql[:frm.start()], sql[frm.start():]
    if "*" in head or _ROLLUP_HEAD.search(head) or re.search(rf"\b{col}\b", head):
        return sql
    if re.search(r"\b(?:MAX|MIN)\s*\(", head, re.I) and not re.search(r"\bGROUP\s+BY\b", sql, re.I):
        return sql
    return head.rstrip() + ", " + col + " " + rest


def ensure_sort_axis(sql: str, question: str) -> tuple[str, bool]:
    """'표면금리' 질의의 정렬 축을 srfc_irt 로 맞춘다. (보정된 SQL, 보정했는지)

    2026-09-04 서버 실측: 'A등급 이상 회사채 중 표면금리 높은 순으로 5개' 가 ORDER BY MAX(applied_yield)
    로 나가 답변도 '수익률 높은 순' 으로 축을 바꿔 적었다 — 1·2위(스탠다드차타드 15-07·15-06)의 표면금리는
    7.1·3.0 으로 상위권이 아니다(정답 1위 우리금융캐피탈458 7.5). 값이 전부 실제 행이라 환각 검사에 안 걸린다.
    gold BND-D-012·BND-D-028 둘 다 ORDER BY srfc_irt 가 정본이다(정렬축 규칙).
    ② ORDER BY 자체가 없는 사각도 함께 받는다 — ensure_reco_sort 는 _OTHER_AXIS_Q('표면')에 걸려
    표면금리 질의에 정렬을 주입하지 않으므로, 그대로 두면 정렬 없는 임의 N행이 나간다.
    발동 조건: ① domestic_bonds ② 질문에 표면금리 낱말 ③ 질문이 수익률 축을 함께 말하지 않음
    (두 축 동시 언급은 불개입 — align_maturity_year 원칙) ④ 집계(COUNT) 아님.
    모수를 바꾸지 않는 축 교정이라 조회·랭킹 어느 쪽에서도 안전하다(제외 절 주입은 이자유형분리 몫)."""
    if "domestic_bonds" not in sql or not _SRFC_Q.search(question) or _YIELD_AXIS_Q.search(question):
        return sql, False
    if re.search(r"\bCOUNT\s*\(", sql, re.I):
        return sql, False
    m = _ORDER_YIELD_COL.search(sql)
    if m:                                        # ① 축 치환 — 방향(ASC/DESC)·MAX/MIN 감싸기는 그대로 둔다
        return _select_add_col(sql[:m.start()] + m.group(1) + "srfc_irt" + sql[m.end():], "srfc_irt"), True
    if re.search(r"\bORDER\s+BY\b", sql, re.I) or not _RECO_Q.search(question):
        return sql, False
    direction = "ASC" if _SRFC_LOW_Q.search(question) else "DESC"   # ② 정렬 부재 — 주입
    sql = _select_add_col(sql, "srfc_irt")
    if "srfc_irt" not in sql:                    # `*`·집계라 넣지 못했으면 정렬만 걸지 않는다
        return sql, False
    lm = re.search(r"\s*\bLIMIT\b", sql, re.I)
    pos = lm.start() if lm else len(sql)
    return sql[:pos].rstrip() + f" ORDER BY srfc_irt {direction}" + sql[pos:], True


_ORDER_SRFC = re.compile(r"ORDER\s+BY\s+(?:MAX|MIN)?\(?\s*srfc_irt\b", re.I)
# 사용자가 이자 유형을 콕 집으면 분리하지 않는다 — 그 축을 보겠다는 뜻이다
_INTP_NAMED_Q = re.compile(r"할인채|무이자|무이표|제로\s*쿠폰|변동\s*금리|복리채|단리채|이표채")
COUPON_SPLIT_NOTE = ("표면금리는 고정금리 이표채끼리만 비교했습니다 — 할인채는 표면금리 란이 발행 할인율이고 "
                     "변동금리는 스냅샷 값이라 같은 축에 놓지 않습니다(이자유형분리).")


def ensure_coupon_type_split(sql: str, question: str) -> tuple[str, bool]:
    """표면금리 랭킹 SQL 에 이자유형분리(고정금리 이표채) 절을 주입. (보정된 SQL, 보정했는지)

    이자유형분리 규칙 — 할인채 689행은 srfc_irt 가 발행 할인율이고 변동금리는 스냅샷이라 고정 이표채와
    한 축에 놓으면 순위가 뒤섞인다. gold BND-D-012('표면금리 높은 채권 추천')가 정본이다:
    bd_intp_tcd='이표채' AND bd_inrt_tcd='고정금리' AND srfc_irt > 0, must_not_include 할인채·변동금리.
    🔴 발동은 추천·랭킹(_RECO_Q)에서만 — 같은 srfc_irt 정렬이라도 조건검색은 주입하지 않는다.
    gold BND-D-028('A등급 이상 회사채 표면금리 5% 넘는 것')에 주입하면 599 → 497종목으로 102종목이
    사라진다(2026-09-04 실측). 고위험제외 규칙의 '조회는 제외하지 않는다' 와 같은 경계다.
    불개입: 질문이 이자 유형을 명시 · 이미 유형 **필터**가 있음 · 집계.
    🔴 2026-09-04 서버 실측 #62 — '이미 유형 절' 판정이 SQL **전문**을 훑어, HCX 가 `bd_intp_tcd` 를
    SELECT 표시 컬럼으로 넣자(필터컬럼표시 규칙대로) 가드가 자기를 껐다. 그 사이 HCX 가 스스로 넣은
    `bd_intp_tcd IN ('이표채','복리채')` 로 88종목(단리채 63·할인채 25)이 조용히 빠진 채 모수 10,057 이
    나갔다(정본 10,145 · 분리하면 9,532). 표시 컬럼은 필터가 아니다 — 판정은 WHERE 범위로 한정한다
    (BND-S-010 의 'kind 필터 검사 WHERE 범위 한정' 과 같은 처방)."""
    if "domestic_bonds" not in sql or not _RECO_Q.search(question):
        return sql, False
    if not _ORDER_SRFC.search(sql) or re.search(r"\bCOUNT\s*\(", sql, re.I):
        return sql, False
    if _INTP_NAMED_Q.search(question) or re.search(r"bd_intp_tcd|bd_inrt_tcd", _where_body(sql), re.I):
        return sql, False
    excl = ["TRIM(bd_intp_tcd)='이표채'", "TRIM(bd_inrt_tcd)='고정금리'"]
    if not re.search(r"srfc_irt\s*[><]", sql):
        excl.append("srfc_irt > 0")
    return _append_exclusions(sql, excl)


# ── 동률 2차 정렬 (2026-09-04 서버 실측 #62) ──────────────────────────────────
# 표면금리 7.5% 두 종목(우리금융캐피탈458 AA- · 엠캐피탈355 A0)의 순서가 실측마다 뒤바뀌었다 —
# ORDER BY 뒤에 2차 키가 없으면 등수는 SQLite 가 준 우연이고, 같은 질문에 두 번 다른 답이 나간다.
# 정책(규칙 정렬축): 1차 축 동률 → ① 신용등급 서열 높은 순(무등급 마지막) ② 만기 이른 순 ③ pd_no.
_TIE_AXES = ("applied_yield", "after_tax_yield", "corp_pretax_yield", "buy_yield", "srfc_irt",
             "mat_dt", "remaining_days", "dur", "eval_price", "isu_bal_amt")
_ORDER_CLAUSE = re.compile(r"\bORDER\s+BY\s+(.+?)(?=\s+\bLIMIT\b|$)", re.I | re.S)
_ORDER_FIRST_COL = re.compile(r"^\s*(?:MAX|MIN)?\s*\(?\s*([A-Za-z_]\w*)", re.I)
TIE_BREAK_NOTE = "동률은 신용등급 높은 순 → 만기 이른 순으로 정렬했습니다(정렬축 규칙)."
# 조립기가 "동률을 무엇으로 갈랐다" 를 말해도 되는지 — 2차 키가 실제로 SQL 에 붙어 있을 때만
_ORDER_TIE_KEYS = re.compile(r"ORDER\s+BY[\s\S]*\bpd_no\s+ASC", re.I)


def _grade_rank_case(col: str = "crd_grd") -> str:
    """신용등급 서열을 정렬용 정수로 — 서열은 선언에서 온다(loader.grade_scale, 2026-09-04 이관). 무등급은 마지막."""
    scale = _grade_scale()
    whens = " ".join(f"WHEN '{g}' THEN {i}" for i, g in enumerate(scale, 1))
    return f"CASE TRIM({col}) {whens} ELSE {len(scale) + 1} END"


def ensure_tie_break(sql: str, question: str = "") -> tuple[str, bool]:
    """채권 랭킹의 ORDER BY 에 동률 2차 키를 붙인다. (보정된 SQL, 보정했는지)

    2026-09-04 서버 실측 #62 — 'A등급 이상 회사채 표면금리 높은 순 5개' 를 두 번 물어 1·2위가 뒤바뀌었다.
    값·축·모수가 다 맞아도 **순서가 재현되지 않으면 오답**이다(같은 질문에 다른 등수). ETF `보수유효` 규칙엔
    동률 처리가 있는데 채권 정렬축 규칙엔 없었다.
    발동: ① domestic_bonds 단독 ② ORDER BY 의 1차 키가 랭킹 축(_TIE_AXES) ③ 2차 키가 아직 없음.
    GROUP BY 가 있으면(대표행 가드) 2차 키도 집계로 감싼다 — bare 컬럼은 어느 행이 올라올지 정해지지 않는다."""
    if "domestic_bonds" not in sql or re.search(r"\b(?:join|union)\b|\(\s*select\b", sql, re.I):
        return sql, False
    m = _ORDER_CLAUSE.search(sql)
    if not m or "," in m.group(1):                        # 2차 키가 이미 있으면 존중
        return sql, False
    first = _ORDER_FIRST_COL.match(m.group(1))
    if not first or first.group(1).lower() not in _TIE_AXES:
        return sql, False
    grouped = bool(re.search(r"\bGROUP\s+BY\b", sql, re.I))
    axis = first.group(1).lower()
    keys = []
    grade = _grade_rank_case()
    keys.append(f"MIN({grade}) ASC" if grouped else f"{grade} ASC")
    if axis != "mat_dt":
        keys.append("MIN(mat_dt) ASC" if grouped else "mat_dt ASC")
    keys.append("pd_no ASC")
    end = m.end(1)
    return sql[:end].rstrip() + ", " + ", ".join(keys) + sql[end:], True


_KTB_Q = re.compile(r"국고채|(?<![가-힣])국채")
# '국공채 중(가운데·에서·안에) … 국고채' — 국고채가 머리명사인 부분집합 질의. 그 밖에 '국공채' 가 있으면 국공채가 머리명사.
_GOV_SUBSET_Q = re.compile(r"국공채\s*(?:중|가운데|에서|안에|내에서|내)\s*[^.,?!]*?(?:국고채|(?<![가-힣])국채)")


def ktb_head_is_gov(question: str) -> bool:
    """질문의 머리명사가 국공채(대분류)인가 — 국고채는 포함·병렬 언급일 뿐인가.

    2026-09-03 서버 실측 #52: "국고채를 포함해서 국공채는 전부 몇 종목이야?" → 가드가 '국고채' 낱말만 보고 대분류를
    국고채 확정식으로 좁혀 295(정답 1,775). "사과를 포함해서 과일이 몇 개야?" 에 사과만 센 꼴이다.
    '국공채' 가 없으면 False(종전 동작). '국공채 중 국고채만' 처럼 국고채가 부분집합 머리명사면 False.
    """
    if "국공채" not in question:
        return False
    return not _GOV_SUBSET_Q.search(question)


_MCLS_EQ = re.compile(r"(?:TRIM\(\s*)?std_pd_mcls_nm\s*\)?\s*=\s*'국공채'", re.I)
_MCLS_IN = re.compile(r"(?:TRIM\(\s*)?std_pd_mcls_nm\s*\)?\s*IN\s*\([^)]*'국공채'[^)]*\)", re.I)
# 소분류 단독 경로 — 2026-09-04 서버 실측: '국고채는 신용등급이 어떻게 돼?' 가 std_pd_scls_nm='국고채'
# 단독(290종목/371행)으로 나갔다. 확정식은 295종목/377행 — bd_knd='국고채권' 인데 소분류가 '물가채' 인
# 물가연동국고채권 5종목이 빠진다. 이번 질문은 결론(등급 미부여)이 같았지만 '몇 종목' 이면 290 오답이다.
_SCLS_EQ = re.compile(r"(?:TRIM\(\s*)?std_pd_scls_nm\s*\)?\s*=\s*'국고채'", re.I)
_KTB_FILTER_FALLBACK = ("(TRIM(bd_knd)='국고채권' OR (COALESCE(TRIM(bd_knd),'')='' "
                        "AND TRIM(std_pd_scls_nm)='국고채'))")


def _decl_kind_sql(token: str, fallback: str) -> str:
    """종류 확정식 하나를 선언에서 꺼낸다 — enums `kind_filters.tokens`. 없으면 종전 상수 (2026-09-04)."""
    try:
        from .loader import kind_filter_decl
        toks, _ = kind_filter_decl("domestic_bonds", "")
        return next((sql for tok, sql in toks if tok == token), fallback)
    except Exception:                                        # noqa: BLE001
        return fallback


# 국고채·국채 확정식 — 선언(종류필터 ①)이 원천. STRIPS 21행 포함 295종목
_KTB_FILTER = _decl_kind_sql("국고채", _KTB_FILTER_FALLBACK)
_KTB_PLAIN = "TRIM(bd_knd)='국고채권'"
# STRIPS 인지 신호 — 이 낱말이 질문에 있으면 사용자가 그 개념을 알고 콕 집은 것: STRIPS 주입을 물린다.
# '제외·빼고' 같은 일반 낱말은 신호로 쓰지 않는다 — '사모 빼고 국고채' 가 오폭당한다 (2026-08-31 리드 결정).
_STRIPS_Q = re.compile(r"스트립|STRIPS|원금이자분리", re.I)


_KTB_BDKND = re.compile(r"(?:TRIM\(\s*)?bd_knd\s*\)?\s*=\s*'국고채권'", re.I)
_PBCM_CONJ = re.compile(r"\s+AND\s+(?:TRIM\(\s*)?pd_pbcm\s*\)?\s*=\s*'([^']*)'"
                        r"|(?:TRIM\(\s*)?pd_pbcm\s*\)?\s*=\s*'([^']*)'\s+AND\s+", re.I)


_MCLS_LIST = re.compile(r"((?:TRIM\(\s*)?std_pd_mcls_nm\s*\)?\s*IN\s*\()([^)]*)(\))", re.I)


@lru_cache(maxsize=8)
def _column_values(table: str, column: str) -> frozenset:
    """그 컬럼의 실재 값 집합 — 판정을 코드에 적지 않고 DB 에 묻는다. 실패하면 빈 집합(호출자가 불개입)."""
    if not re.fullmatch(r"\w+", table) or not re.fullmatch(r"\w+", column):
        return frozenset()
    try:
        con = connect_readonly()
        try:
            rows = con.execute(f"SELECT DISTINCT TRIM({column}) FROM {table} "
                               f"WHERE {column} IS NOT NULL AND TRIM({column}) <> ''").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return frozenset()
    return frozenset(str(r[0]) for r in rows)


def normalize_mcls_values(sql: str, question: str = "") -> tuple[str, bool]:
    """대분류 IN 목록에 섞인 **종류 값**을 떼어낸다. (보정된 SQL, 보정했는지)

    2026-09-04 서버 실측 #61 — '국고채 포함해서 국공채는 총 몇 종목이야?' 에 HCX 가
    `TRIM(std_pd_mcls_nm) IN ('국공채','국고채권')` 를 냈다. '국고채권' 은 대분류 값이 아니라 **종류(bd_knd)**
    값이라 값 검사에 걸렸고, 재생성이 같은 문장을 되풀이해 정답(1,775)을 아는 질문이 오거절로 끝났다.
    떼어낸 값은 **그 컬럼에서 한 행도 못 맞히는 값**이므로 결과가 바뀌지 않는다 — 없는 조건을 지우는 게
    아니라 잘못 놓인 조건을 지우는 것이고, 그래서 안전하다.
    🔴 좁게 연다: ① 대분류 컬럼(std_pd_mcls_nm)만 ② 뗄 값이 같은 테이블의 **종류·소분류 값일 때만**
    (어디에도 없는 값 'AAAA' 류는 그대로 기각돼야 한다 — gold UNANS 계열) ③ 대분류 값이 하나는 남을 때만.
    남은 종류 조건은 ensure_ktb_kind 가 머리명사 판정으로 따로 처리한다."""
    m = _MCLS_LIST.search(sql)
    if not m:
        return sql, False
    lits = re.findall(r"'((?:[^']|'')*)'", m.group(2))
    if len(lits) < 2:
        return sql, False
    mcls = _column_values("domestic_bonds", "std_pd_mcls_nm")
    sibling = _column_values("domestic_bonds", "bd_knd") | _column_values("domestic_bonds", "std_pd_scls_nm")
    if not mcls or not sibling:
        return sql, False
    keep = [v for v in lits if v.strip() in mcls]
    drop = [v for v in lits if v.strip() not in mcls]
    if not keep or not drop or any(v.strip() not in sibling for v in drop):
        return sql, False
    body = ", ".join(f"'{v}'" for v in keep)
    return sql[:m.start(2)] + body + sql[m.end(2):], True


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
    🔴 머리명사 판별(2026-09-03 서버 실측 #52 — 08-31 §4-3 의 "가설이라 현행 유지" 가 실현됐다):
       "국고채를 포함해서 국공채는 전부 몇 종목이야?" 에 HCX 는 std_pd_mcls_nm='국공채' 를 **맞게** 썼는데 ②가
       '국고채' 낱말만 보고 확정식으로 좁혀 295(정답 1,775)를 냈다. 질문에 '국공채' 가 있으면 국공채가 머리명사다 —
       ②③ 을 보류하고 ①만 남긴다(ktb_head_is_gov). '국공채 중 국고채만' 꼴은 국고채가 머리명사라 그대로 발동한다."""
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
    if ktb_head_is_gov(question):
        return sql, changed
    if "국고채권" not in sql:
        repl = _KTB_PLAIN if strips_aware else _KTB_FILTER
        m = _MCLS_EQ.search(sql) or _MCLS_IN.search(sql)
        if m:
            return sql[:m.start()] + repl + sql[m.end():], True
        # ④ 소분류 단독(std_pd_scls_nm='국고채') → 확정식. 이 분기는 확정식이 아직 없을 때만 도므로
        #    (확정식엔 '국고채권' 이 들어 있다) 재작성이 확정식을 깨지 않는다. 종류비교 CASE 처럼
        #    같은 절이 여러 번 나오면 전부 바꾼다 — 앞 하나만 고치면 절반만 정본이 된다.
        if _SCLS_EQ.search(sql):
            return _SCLS_EQ.sub(lambda _: repl, sql), True
        return sql, changed
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


# GROUP BY·ORDER BY 절 본문 — 다음 절 키워드 전까지. 집계·정렬 키의 TRIM 판정 범위다.
_KEY_CLAUSE = re.compile(
    r"\b(GROUP\s+BY|ORDER\s+BY)\s+(.*?)(?=\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|\bHAVING\b|\bUNION\b|$)",
    re.I | re.S)
# 패딩으로 **실제 쪼개지는** 컬럼만 집계·정렬 키 TRIM 대상 (2026-09-04 실측 — 위 주석 참조)
_KEY_TRIM_COLS = ("bd_knd", "pd_pbcm")
_KEY_TRIM_ALT = "|".join(_KEY_TRIM_COLS)


def ensure_trimmed_compare(sql: str) -> tuple[str, bool]:
    """패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교 **및 집계·정렬 키**를 TRIM 으로 교정.

    2026-08-31 저녁 서버 실측: bd_knd IN ('일반은행채','특수은행채') 무TRIM 이 16행만 통과
    (TRIM 시 2,031행) — 문자열비교 규칙 무시. LIKE 는 % 와일드카드가 패딩을 흡수하므로 불개입.

    🔴 2026-09-04 확장(오답기록 #63) — 비교(=·<>·IN)만 보던 탓에 **GROUP BY·ORDER BY 키**를
    놓쳤다. 서버 실측 `GROUP BY pd_pbcm` 이 고정폭 패딩으로 같은 기관을 갈라 한국산업은행 503→500,
    한국토지주택공사 499→498 이 되고 **2·3위 순서가 뒤바뀌었다**(ETF FIN-06 과 같은 병, 같은 컬럼).
    키 TRIM 의 대상은 **패딩으로 실제 쪼개지는 두 컬럼**(_KEY_TRIM_COLS = bd_knd·pd_pbcm)뿐이다 —
    pd_pbcm 1,837→1,818 · bd_knd 41→32. 펀드·ETF 쪽 후보는 raw = trim 이라 이득이 0 인데, 감싸면
    펀드단위 확정식이 달라져 뒤 가드가 못 알아본다(아래 주석 · 6R 고정선으로 잡았다).
    🔴 SELECT 의 같은 컬럼도 함께 감싼다 — GROUP BY 만 TRIM 하면 묶음은 맞아도 표시 이름이 패딩
    원문 중 아무 행에서나 뽑힌다(같은 병의 다른 얼굴 · FIN-06 은 이 어긋남이 오답의 정체였다).
    """
    changed = False
    for col in _PADDED_COLS:
        # 🔴 한정자(public_funds.·p.)는 함수 **안**에 둔다 — 2026-09-02 KG-002 실측: `public_funds.TRIM(or_co…)` 문법 오류 → 기각.
        #    일반 규칙: 가드가 컬럼을 함수로 감쌀 때 한정자는 컬럼과 함께 인자 자리에 남는다(ensure_spaceless_name_match 동일).
        pat = re.compile(rf"(?<!TRIM\()((?:\b\w+\.)?)\b{col}\b(\s*(?:=|<>|IN)\s*)", re.I)
        new = pat.sub(rf"TRIM(\1{col})\2", sql)
        if new != sql:
            sql, changed = new, True

    # ── 집계·정렬 키 (2026-09-04 확장 · 오답기록 #63) ──────────────────────
    #    🔴 대상은 _PADDED_COLS 전부가 아니라 **패딩으로 실제 쪼개지는 두 컬럼**(_KEY_TRIM_COLS)뿐이다.
    #       실측 2026-09-04: pd_pbcm raw 1,837 / trim 1,818 · bd_knd 41 / 32 로 갈리는 반면
    #       펀드·ETF 후보(or_co_xtn_itt_cd·itm_abrv_nm·han_clas_nm·kofia_fd_ccd·std_itm_no…)는
    #       raw = trim 이라 감싸도 값이 안 바뀐다. 그런데 **감싸면 해가 있다** — 펀드단위 확정식
    #       `printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER))` 안까지 TRIM 이 끼면 확정식 문자열이
    #       달라져 뒤따르는 슬롯·가드(FUNDUNIT·기본모수)가 같은 식을 못 알아본다 — 6R 고정선
    #       R4(기본모수 절 소실)·R6(6행→1행)·S12(`AS TRIM(...)` 문법 오류)가 이걸로 깨졌다.
    #       이득이 0 이고 손실이 실재하면 대상에서 뺀다.
    keyed: set[str] = set()
    bare = re.compile(rf"(?<!TRIM\()((?:\b\w+\.)?)\b({_KEY_TRIM_ALT})\b(?!\s*\()", re.I)

    def _fix_clause(m: "re.Match[str]") -> str:
        # 🔴 치환이 없으면 **원문 그대로 돌려준다** — 절을 재조립하면 공백·줄바꿈이 바뀌어
        #    뒤따르는 가드·스냅샷이 같은 SQL 을 다른 문자열로 본다.
        def _sub(mm: "re.Match[str]") -> str:
            keyed.add(mm.group(2).lower())
            return f"TRIM({mm.group(1)}{mm.group(2)})"
        body = bare.sub(_sub, m.group(2))
        return m.group(0) if body == m.group(2) else f"{m.group(1)} {body}"

    new = _KEY_CLAUSE.sub(_fix_clause, sql)
    if new != sql:
        sql, changed = new, True
        # SELECT 목록의 같은 컬럼도 감싼다 — 표시 이름과 묶음 키를 같은 값으로 맞춘다.
        # 🔴 별칭 자리는 건드리지 않는다 — `MAX(x) AS x` 뒤까지 감싸면 `AS TRIM(x)` 로 문법이 깨진다(S12).
        sel = re.match(r"(?is)^(\s*SELECT\s+(?:DISTINCT\s+)?)(.*?)(\s+FROM\b)", sql)
        if sel:
            body = ",".join(_wrap_expr_keep_alias(it, bare, keyed) for it in _top_split(sel.group(2), ","))
            if body != sel.group(2):
                sql = sql[:sel.start(2)] + body + sql[sel.end(2):]
    return sql, changed


def _top_split(expr: str, sep: str) -> list[str]:
    """괄호 깊이 0 의 구분자로만 나눈다 — 함수 인자 안의 쉼표는 건드리지 않는다."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == sep and depth == 0:
            out.append(expr[start:i])
            start = i + 1
    out.append(expr[start:])
    return out


def _wrap_expr_keep_alias(item: str, bare: "re.Pattern[str]", keyed: set) -> str:
    """SELECT 항목의 **표현식 부분만** TRIM 으로 감싼다. `AS 별칭` 은 그대로 둔다.
    괄호 깊이 0 의 ` AS ` 만 별칭 경계로 본다 — `CAST(x AS INTEGER)` 의 AS 는 경계가 아니다."""
    depth, cut = 0, None
    for m in re.finditer(r"[()]|\s+AS\s+", item, re.I):
        tok = m.group(0)
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        elif depth == 0:
            cut = m.start()
            break
    expr, tail = (item[:cut], item[cut:]) if cut is not None else (item, "")
    expr = bare.sub(lambda mm: (f"TRIM({mm.group(1)}{mm.group(2)})"
                                if mm.group(2).lower() in keyed else mm.group(0)), expr)
    return expr + tail


_KIND_FILTERS_FALLBACK = [   # 질문 낱말(긴 것부터 소진 탐색) → 확정 필터. 같은 필터로 모이는 낱말은 dedupe
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
_KIND_PARAPHRASES_FALLBACK = [   # 발행 주체를 풀어 쓴 질의 (2026-08-31 리드 지적: '회사채' 낱말 없이 '회사에서 발행한 채권').
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



def _kind_filters() -> tuple[list[tuple[str, str]], list[tuple[re.Pattern, str]]]:
    """종류 낱말·서술형 → 확정 필터식. 원천은 선언(enums/domestic_bonds.yaml `kind_filters`)이다.

    2026-09-04 — 종전엔 같은 표가 여기 코드 상수로도 있어 이원화돼 있었다(query_rules.종류필터 는 사람용 설명,
    이 표는 기계용). 새 종류(전단채·CP·해외채…)를 붙일 때 yaml 한 줄이면 되게 선언으로 옮긴다.
    선언이 없거나 깨지면 종전 표로 물러선다 — 가드가 죽는 것보다 낫다."""
    try:
        from .loader import kind_filter_decl
        toks, paras = kind_filter_decl("domestic_bonds", _P)
    except Exception:                                        # noqa: BLE001
        toks, paras = [], []
    return (toks or list(_KIND_FILTERS_FALLBACK)), (paras or list(_KIND_PARAPHRASES_FALLBACK))


def _question_kind_filters(question: str) -> set[str]:
    q = question
    found = set()
    kinds, paraphrases = _kind_filters()
    for tok, flt in kinds:
        if tok in q:
            found.add(flt)
            q = q.replace(tok, "◌")        # 긴 낱말 소진 — '일반은행채' 뒤에 '은행채' 가 또 걸리지 않게
    for pat, flt in paraphrases:           # 서술형은 낱말 소진 뒤에 — '회사채' 가 이미 잡혔으면 중복 무해(같은 필터로 dedupe)
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
# 6등급(매우낮은위험)이 그 종류에 실존하는가 — **열거하지 않고 데이터에 묻는다** (2026-09-04).
#   종전엔 8개 확정식을 코드에 적어 두었다(2026-08-31 전수 실측분). 종류가 늘거나 데이터가 바뀌면 그 목록이 조용히 틀린다.
#   지금은 종류 확정식 하나로 "이 종류에 16등급 구매가능 행이 있나" 를 1회 조회해 캐시한다 — 선언(kind_filters)이 종류를 정하고,
#   존재 여부는 데이터가 답한다. 조회 실패(파일 없음 등)면 '있다' 로 보수적으로 답해 종전 동작(16 단독 유지)을 지킨다.
@lru_cache(maxsize=64)
def _kind_has_safe_grade(kind_sql: str) -> bool:
    try:
        with connect_readonly() as con:
            row = con.execute(
                f"SELECT 1 FROM domestic_bonds WHERE ({kind_sql}) AND pd_risk_gcd='16' "
                f"AND mat_dt >= {BUYABLE_INT} LIMIT 1").fetchone()
        return row is not None
    except sqlite3.Error:
        return True


def _kinds_without_safe_grade(question: str) -> set[str]:
    """질문이 지목한 종류 중 6등급이 하나도 없는 것들 — 있으면 '16' 단독 강제를 IN ('15','16') 으로 완화한다."""
    return {f for f in _question_kind_filters(question) if not _kind_has_safe_grade(f)}


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
    if _kinds_without_safe_grade(question):
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
        new, _ = _append_exclusions(new, [f"mat_dt >= {BUYABLE_INT}"])
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


_RISKY_Q = re.compile(r"(?:가장|제일|최고로|최고|가장\s*많이)\s*위험|위험\s*(?:한|도가|이|성이)?\s*(?:높은|큰|많은)\s*(?:순|채권|것|거|걸)|위험\s*(?:순위|랭킹|순으로)|위험한\s*(?:채권|것|거|걸)\s*(?:추천|골라|알려|뭐|어떤)")
_RISK_CUE = re.compile(r"위험\s*등급|신용\s*등급|등급\s*(?:기준|으로|별)|수익률|금리|이자|듀레이션|만기|변동|부도|디폴트|원금|가격|단가|사모|공모|국공채|회사채|[1-6]\s*등급|C0|BBB|BB|CCC")


def risk_ambiguity_clarify(question: str, tables: list[str]) -> str | None:
    """'가장 위험한 채권' 류의 결정층 되묻기 — 축 단서가 없으면 되묻는 문장(+ 축별 실측 규모), 아니면 None.

    2026-09-02 서버 실측: '가장 위험한 채권 뭐야?' 에 HCX 가 위험등급 1등급 필터 + 수익률 내림차순으로 단정해 신보 유동화
    (728.524%·C0) 5종목을 답했다. 위험은 clarify.다의어.위험 대로 한 축이 아니다 — ① 투자위험등급(pd_risk_gcd, 1등급이 가장 위험)
    ② 신용등급(crd_grd, C0 가 최하위 — 부도위험) ③ 금리위험(듀레이션·잔존만기가 길수록) — ①과 ②는 겹치지만(C0 103종목은 전부 1등급)
    1등급은 1,394종목이라 그 안의 순서(수익률?)까지 정하면 임의가 된다. 리드 결정 2026-09-02: 축 단서가 없으면 되묻는다(주최 8/25:
    되묻기는 유효 답변). 위험등급·신용등급·수익률·듀레이션 등 단서 낱말이 있으면 되묻지 않는다. 규모는 DB 실측(HCX 0회)으로 채운다."""
    if "domestic_bonds" not in tables or not _RISKY_Q.search(question) or _RISK_CUE.search(question):
        return None
    try:
        with connect_readonly() as con:
            n_r1 = con.execute("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE pd_risk_gcd='11' AND mat_dt >= ?", (BUYABLE_INT,)).fetchone()[0]
            n_c0 = con.execute("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds WHERE TRIM(crd_grd)='C0' AND mat_dt >= ?", (BUYABLE_INT,)).fetchone()[0]
    except sqlite3.Error:
        n_r1 = n_c0 = None
    r1 = f"{n_r1:,}종목" if n_r1 is not None else "다수"
    c0 = f"{n_c0:,}종목" if n_c0 is not None else "소수"
    return ("'위험한 채권'은 데이터에서 세 가지 기준으로 해석될 수 있어 확인이 필요합니다 "
            f"(기준일 {gate.DATA_CUTOFF}). ① 투자위험등급 기준 — 1등급(매우높은위험) 채권 {r1}. "
            f"② 신용등급 기준 — 최하위 C0 등급 채권 {c0}(부도 위험). "
            "③ 금리위험 기준 — 듀레이션·잔존만기가 긴 채권(금리가 오르면 가격이 크게 떨어짐). "
            "①·②는 겹치지만 목록이 다르고 ③은 국공채 장기물이 상위에 옵니다. 어느 기준으로 찾아드릴까요? "
            "(예: '위험등급 1등급 채권', '신용등급 C0 채권', '듀레이션 긴 채권')")


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
    if "pd_risk_nm" in sql or not _single_select(sql):     # 14R gold ③-4 — SELECT 편집은 단일 SELECT 에서만
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
    if "domestic_bonds" not in sql or not _single_select(sql):   # 14R gold ③-4
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
        # 4R 부류 I — 한글 라벨의 경계도 **이름 문자 전체**([0-9A-Za-z가-힣])로 본다: 'KB차이나'·'NH-Amundi' 처럼 영문 브랜드
        #    접두가 붙은 상품명 성분('차이나')이 경계로 새어 Country 개체(투자국가 필터)로 잡혔다(S4·T14·V15 회귀). 조사 허용은 유지.
        return re.search(rf"(?<![0-9A-Za-z가-힣]){esc}{_JOSA}(?![0-9A-Za-z가-힣])", text) is not None
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

# (매칭 키·동의어 캐시는 ctx 객체 속성으로 옮겼다 — _synonym_keys()·_ground() 참조)


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
    # 🔴 캐시는 ctx **객체 속성**에 둔다 — 종전 모듈 dict + id(ctx) 키는 /reload 로 ctx 가
    #    교체될 때 옛 객체의 id 가 재활용되면 낡은 표를 돌려줄 수 있다(2026-09-01 자체 점검 §7).
    out = getattr(ctx, "_syn_keys_cache", None)
    if out is None:
        out = {}
        for domain, doc in (ctx.enums or {}).items():
            for term, canon in ((doc or {}).get("synonyms") or {}).items():
                if isinstance(canon, str) and canon and canon != term and len(term) >= 2:
                    out.setdefault(canon, []).append((term, domain))   # 4R I-3: 통칭은 **그 테이블** 노드에만 붙인다
        ctx._syn_keys_cache = out   # 병철 09-02: ctx 속성 캐시 (id 재활용 stale 방지)
    return out


def _colloquial_decl(ctx) -> dict:
    """발행사 통칭 생성 규칙 — enums `name_encoding.issuer_colloquial` (선언이 원천, 값은 데이터에서)."""
    for doc in (ctx.enums or {}).values():
        rule = ((doc or {}).get("name_encoding") or {}).get("issuer_colloquial")
        if rule:
            return rule
    return {}


def _other_type_labels(ctx, node_type: str) -> set:
    """다른 개체 타입의 라벨 집합 — 생성 통칭이 여기에 걸리면 만들지 않는다(모호해진다)."""
    cache = getattr(ctx, "_other_label_cache", None)
    if cache is None:
        cache = {}
        ctx._other_label_cache = cache
    if node_type not in cache:
        cache[node_type] = {(n.label_ko or "").replace(" ", "")
                            for n in ctx.kg_nodes if n.node_type != node_type and n.label_ko}
    return cache[node_type]


def _colloquial_terms(ctx, node, label: str) -> list[str]:
    """라벨에서 만든 발행사 통칭 — '한국산업은행'→'산업은행' · '한국전력공사'→'한국전력'.

    2026-09-04 실측: 대표 발행사 23표기 중 6표기('산업은행'·'기업은행'·'도로공사'·'수출입은행'·
    '토지주택공사'·'한국전력')가 KG 접지 0건이었다. 손으로 적은 통칭 6개(한전·산은·기은·LH·주금공·현대차)만
    커버돼 있었기 때문이다 — 통칭을 손으로 적는 대신 **변환 규칙을 선언하고 값은 데이터에서 만든다**.
    _synonym_keys 의 '접두 기계 제거는 위험하다'(Security 라벨 309건 실측)는 판단은 그대로 유효하다 —
    여기는 발행사(Organization + 채권 alias) 한정이고, 다른 개체 라벨과 겹치면 만들지 않는다."""
    rule = _colloquial_decl(ctx)
    if not rule or node.node_type != rule.get("node_type"):
        return []
    table = rule.get("alias_table")
    if table and table not in {t for t, _, _ in ctx.kg_aliases.get(node.node_id, ())}:
        return []
    n = label.replace(" ", "")
    out, low = [], int(rule.get("min_len") or 4)
    for pre in rule.get("drop_prefix") or ():
        if n.startswith(pre) and len(n) - len(pre) >= low:
            out.append(n[len(pre):])
    for suf in rule.get("drop_suffix") or ():
        if n.endswith(suf) and len(n) - len(suf) >= low:
            out.append(n[: -len(suf)])
    if rule.get("skip_if_other_type_label"):
        others = _other_type_labels(ctx, node.node_type)
        out = [t for t in out if t not in others]
    return [t for t in dict.fromkeys(out) if t != n]


def _syn_terms(ctx, node, label: str) -> list[str]:
    """노드 라벨의 yaml 통칭 — 노드가 alias 를 가진 테이블의 yaml 에 적힌 것만 (domestic_etfs.yaml 의 '차이나: 중국' 이
    펀드 Country 노드에 풀링돼 상품명 안 '차이나' 를 잡던 4R S4 회귀의 원인)."""
    tables = {t for t, _, _ in ctx.kg_aliases.get(node.node_id, ())}
    return [term for term, domain in _synonym_keys(ctx).get(label, ()) if not tables or domain in tables]
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
        if node.node_id.startswith(("Region_", "Curr_", "CG_", "Country_")):
            return 2          # Country_(KG 1R S3): 코드북 17국 — 닫힌 목록, '중국'·'대만' 2자
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
        """노드의 매칭 키 — 정식 라벨 + 접미어 제거 + 결합 라벨 조각 + yaml 동의어 + (S1) 구상호 · 이름형 alias raw.
        (키, 경계검사여부, 종류)  종류: label | short | former | alias | syn"""
        prov = getattr(node, "provenance", "curated")
        if prov in ("derived", "label_conflict"):
            # S1: 종목명 접두 최빈값 라벨(Org_fund_* 'Asset' 등) · F1: Region/상품군 명사와 충돌하는 FundAttribute 라벨('ETF'·'중국'·'국내')
            #   — 코드 alias 로만 산다 (KG-001 오매칭 · KG-023/025/026 회귀)
            return
        # FundAttribute(S3 태그 축 179노드 — '인덱스'·'배당주'…)·Country(4R I: 상품명 성분 '차이나'·'베트남')는 항상 경계 검사 조건부
        attr = node.node_type in ("FundAttribute", "Country")
        for label in node.labels:
            if len(label) >= _min_len(node, label):
                yield label, attr, "label"
            elif _short_ok(node, label):
                yield label, True, "label"   # 짧은 라벨은 경계 검사를 조건으로 허용
            short = _short_label(label)
            if short and (len(short) >= _min_len(node, short) or _short_ok(node, short)):
                yield short, True, "short"
            if node.node_type == "Organization":
                brand = _mgr_brand_en(short or label)     # 'Mirae Asset Global Investments' → 'Mirae Asset' (KG-001)
                if brand:
                    yield brand, True, "short"
            if "/" in label:               # '네이버/NAVER' → 네이버 · NAVER
                for piece in _LABEL_SPLIT.split(label):
                    piece = piece.strip()
                    if piece and piece != label and (
                            len(piece) >= _min_len(node, piece) or _short_ok(node, piece)):
                        yield piece, True, "label"
            for alias in _syn_terms(ctx, node, label):
                yield alias, True, "syn"
            for term in _colloquial_terms(ctx, node, label):
                yield term, True, "colloquial"   # 선언된 변환으로 만든 발행사 통칭 (name_encoding.issuer_colloquial)
        for fn in getattr(node, "former_names", None) or ():
            if len(fn) >= 3:
                yield fn, True, "former"   # 구상호 — 매칭되면 후계 법인 코드로 조회하고 '현재 X 가 운용' 을 굽는다 (KG-002·003)
        if prov == "curated" and node.node_type in _ALIAS_KEY_ENTITIES:
            # 사람이 관리하는 닫힌 축의 **이름형** alias raw 는 매칭 키다 — '높은위험'(RiskGrade_2 변형 alias)이 yaml·kg_alias 에
            # 있는데 키가 아니어서 Ground 0 → 정확일치 4/20 (KG-015). 코드형 컬럼(*_cd·*_no·*_gcd)은 제외.
            for t, c, raw in ctx.kg_aliases.get(node.node_id, ()):
                if _CODE_COLUMN.search(c) or raw in node.labels or len(raw) < _min_len(node, raw):
                    continue
                yield raw, True, "alias"

    drop_kr = _region_korea_is_listing(question)
    drop_trustee = _drop_trustee_node(question)
    name_mode = bool(_NAME_MODE_Q.search(question))
    # (키, 노드, 경계검사) 목록은 질문과 무관하다 — 프로세스당 1회만 만든다.
    # 정렬만 질문마다 다시 한다(_in_target 이 대상 테이블에 걸려 있어서).
    pairs = getattr(ctx, "_match_keys_cache", None)   # ctx 속성 캐시 — id 재활용 stale 방지(위와 동일)
    if pairs is None:
        seen_keys: set = set()
        pairs = []
        for node in ctx.kg_nodes:
            for key, bounded, kind in _keys(node):
                if (node.node_id, key) in seen_keys:
                    continue
                seen_keys.add((node.node_id, key))
                pairs.append((key, node, bounded, kind))
        ctx._match_keys_cache = pairs   # 병철 09-02: ctx 속성 캐시 (id 재활용 stale 방지)
    candidates = sorted(pairs, key=lambda x: (not _in_target(x[1]), -len(x[0]), -len(_members(x[1]))))
    consumed = question
    for label, node, bounded, kind in candidates:
        if label not in consumed:
            # S1 정규화 키 — curated 노드의 한글 4자+ 키는 질문의 **공백 삽입 표기**('한국 투자 신탁 운용')에도 맞춘다 (KG-004:
            #    무정규화 부분일치라 143펀드 실재 → "0개"). 매칭된 실제 구간을 라벨로 삼아 경계·소비를 그대로 태운다.
            span = _flex_match(label, node, consumed)
            if not span:
                continue
            label = span
        # 6R I′ — 경계 판정은 **원문 question** 기준: 앞 라벨의 소비(' ' 치환)가 뒤 라벨의 경계를 만들지 않는다(W2 '미래에셋베트남' 에서 Org 소비 뒤
        #    '베트남' 이 독립 낱말처럼 보여 Country 태그가 실렸다). 소비 중복 방지는 위 `label not in consumed` 가 이미 맡는다.
        if bounded and not _boundary_hit(label, question if label in question else consumed):
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
        # 3R 부류 D — '이름이 들어간/포함된' 질의는 축이 이름(itm_nm)이다. 기관·펀드 노드는 라벨만 소비하고 코드를 싣지 않는다
        #    (T11 피델리티: Org 코드 핀이 이름 154/301 을 106 으로 줄였다). 이름 검색 토큰 = 라벨.
        # 4R 일반 규칙 J — Ground 가 라벨을 소비하면서 **코드를 싣지 않기로 한 모든 분기**(이름 모드·호수 불일치·접두 절단·
        #    국가어 이름성분)는 한 문형으로 `이름 검색 토큰` 을 싣는다(⚙ = 파이프라인 지시, 답변 노출 금지 — 부류 L). 토큰은
        #    residual_name_token → ensure_fund_name_filter 가 itm_nm LIKE 로 강제한다(T6: 호수 분기가 토큰을 안 실어 GLOB 만 남아 오거절).
        if name_mode and node.node_type in ("Organization", "Fund"):
            consumed = consumed.replace(label, " ")
            lines.append(_skip_pin_line(label, node, "이름 모드 — 축은 이름(itm_nm)", label.replace(" ", "")))
            continue
        # 4R 부류 I — Country 라벨이 **상품명의 성분**이면(라벨±인접 낱말이 종목명 부분열: 'NH-Amundi 인도네시아 포커스') 투자국가
        #    필터가 아니다. 소비하되 코드를 싣지 않고, 성분을 이은 이름 토큰을 넘긴다.
        if node.node_type == "Country":
            comp = _country_name_component(label, question)
            if comp:
                consumed = consumed.replace(label, " ")
                lines.append(_skip_pin_line(label, node, f"상품명 성분(인접 '{comp[0]}') — 투자국가 필터로 쓰지 않는다", comp[1]))
                continue
        # 🔴 Fund 노드는 **라벨이 펀드 이름을 다 덮을 때만** 코드를 핀한다 (3R A-2 일반화 — 호수 불일치는 그 특수 사례).
        #    ⓐ 질문의 N호 ≠ 노드 라벨의 N호 (FND-032: 디스커버리 노드 rptt = 4호) ⓑ 라벨 바로 뒤에 잔여 고유명이 붙어 있다
        #    (T12: 자동 라벨 'NH-Amundi 1.5배' 는 클래스명 공통접두 절단 — 실체는 판매완료 3호. 잔여 '레버리지인덱스').
        #    라벨은 소비하고 라벨+잔여 결합 토큰으로 이름 검색을 지시한다 — 코드를 실으면 다른 호·배수·판매완료 펀드로 0행.
        ho = _Q_SERIES_NO.search(question)
        if node.node_id.startswith("Fund_"):
            tail = _label_tail_token(label, question)
            ho_mismatch = bool(ho) and not any(ho.group(1) + "호" in lb.replace(" ", "") for lb in node.labels)
            if ho_mismatch or tail:
                consumed = consumed.replace(label, " ")
                why = (f"질문의 '{ho.group(1)}호' 와 이 노드의 코드가 가리키는 펀드가 다를 수 있음 — 호 경계(종목명검색 규칙) 병용"
                       if ho_mismatch else f"접두 절단 라벨(잔여 고유명 '{tail}')")
                tok = (label + (tail or "")).replace(" ", "") if not ho_mismatch else label.replace(" ", "")
                lines.append(_skip_pin_line(label, node, why, tok))
                continue
        hits.append(node)
        consumed = consumed.replace(label, " ")
        members = expand_node(ctx, node.node_id, relations)
        aliases = _demote_product_name_raws(node, aliases)
        official = getattr(node, "label_official", None)
        note = ""
        if kind == "former":
            codes = [raw for _, c, raw in aliases if c.endswith("_itt_cd")]
            note = (f" ℹ '{label}' 은(는) 구상호 — 현재 {official or node.label_ko}"
                    + (f"(코드 {'·'.join(codes[:2])})" if codes else "") + " 기준으로 조회한다")
        succ = ctx.kg_node_by_id.get(getattr(node, "successor", None) or "")
        if succ is not None:
            # 후계 법인(합병·이관) — 구상호 노드의 코드는 판매중 0행일 수 있다. 후계 코드를 함께 싣고 답에 병기한다 (KG-002)
            succ_aliases = _demote_product_name_raws(succ, target_aliases(ctx, succ, target, relations))
            if succ_aliases:
                aliases = aliases + [a for a in succ_aliases if a not in aliases]
                hits.append(succ)
                s_off = getattr(succ, "label_official", None) or succ.label_ko
                note = f" ℹ '{label}' 은(는) 구상호 — 현재 {s_off}({succ.node_id.replace('Org_', '')})이 운용하며 후계 코드를 함께 조회한다"
        where = " · ".join(_alias_expr(ctx, t, c, raw) for t, c, raw in aliases[:4])
        if len(aliases) > 4:
            where += f" … 외 {len(aliases) - 4}종"
        via = ""
        if len(members) > 1:
            shown = ", ".join(members[1:4]) + (" …" if len(members) > 4 else "")
            via = f" [+후손 {len(members) - 1}: {shown}]"
        typ = node.node_type + (f", 정식명 {official}" if official and official != label else "")
        lines.append(f"'{label}' → {node.node_id} ({typ}){via} → {where}{note}")
    return hits, lines


# ── S1 라벨 슬롯 체계 보조 (KG 1R) ──
_ALIAS_KEY_ENTITIES = {"RiskGrade", "Region", "Currency", "CreditGrade"}   # 사람이 관리하는 닫힌 축 — 이름형 alias raw 를 매칭 키로 승격
_CODE_COLUMN = re.compile(r"(?:_cd|_no|_gcd|_pcd|_yn|_dt)$", re.I)
_PRODUCT_NAME_RAW = re.compile(r"투자신탁|상장지수|증권투자")               # 상품명 구조(§3.3) — 기관 alias 가 아니라 오염 raw
_MGR_DESCRIPTOR_EN = re.compile(
    r"\s+(?:Asset\s+Management|Global\s+Investments?|Investment\s+Management|Fund\s+Management|Investments?|Asset|Management|Securities)$", re.I)
_FLEX_RX: dict[str, re.Pattern] = {}


def _mgr_brand_en(label: str) -> str | None:
    """영문 운용사 라벨의 브랜드 부분 — 'Mirae Asset Global Investments' → 'Mirae Asset'. 서술어를 **뒤에서 한 토막씩** 떼되
    남는 말이 2단어 미만이 되면 멈춘다(1단어 'Samsung'·'Mirae' 는 종목명과 겹쳐 위험)."""
    if re.search(r"[가-힣]", label):
        return None
    brand = label.strip(" .,")
    while True:
        m = _MGR_DESCRIPTOR_EN.search(brand)
        if not m or len(brand[:m.start()].split()) < 2:
            break
        brand = brand[:m.start()].strip(" .,")
    return brand if brand != label.strip(" .,") else None


def _flex_match(label: str, node, text: str) -> str | None:
    """curated 노드의 한글 4자+ 키를 공백 삽입 표기에도 맞춘다 — 맞으면 질문 속 실제 구간, 아니면 None."""
    if getattr(node, "provenance", "curated") != "curated" or len(label) < 4 or " " in label \
            or not re.search(r"[가-힣]", label):
        return None
    rx = _FLEX_RX.get(label)
    if rx is None:
        rx = _FLEX_RX[label] = re.compile(r"\s*".join(re.escape(ch) for ch in label))
    m = rx.search(text)
    return m.group(0) if m and " " in m.group(0) else None


def _demote_product_name_raws(node, aliases: list) -> list:
    """Organization alias 중 상품명 구조 raw(cu_fund_mgmt_co='삼성KODEX…투자신탁[주식]')는 매핑 재료에서 뺀다 —
    KG-025: 오염 raw 13종이 근거문서에 실려 HCX 가 `or_co IN ('삼성','삼성KODEX')` 로 컬럼을 섞었다. 전부 오염이면 원본 유지."""
    if node.node_type != "Organization":
        return aliases
    kept = [a for a in aliases if not _PRODUCT_NAME_RAW.search(a[2])]
    return kept or aliases


_TOKEN_COLS: dict[int, set] = {}


def _is_token_column(ctx, t: str, c: str) -> bool:
    """(테이블, 컬럼)에 token 종류 alias 가 하나라도 있으면 그 컬럼은 다중값 콤마 컬럼이다 (kg_alias.match_kind — S3)."""
    cols = _TOKEN_COLS.get(id(ctx))
    if cols is None:
        cols = _TOKEN_COLS[id(ctx)] = {(t_, c_) for (_, t_, c_, _), k in (getattr(ctx, "kg_alias_kind", {}) or {}).items() if k == "token"}
    return (t, c) in cols


def _alias_expr(ctx, t: str, c: str, raw: str) -> str:
    """Ground 라인의 alias 표기 — 등호 컬럼은 `t.c='raw'`, token 컬럼은 확정식."""
    if _is_token_column(ctx, t, c):
        return f"',' || {t}.{c} || ',' LIKE '%,{raw},%'"
    return f"{t}.{c}={raw!r}"


def ground_notes(ground_lines: list[str]) -> list[str]:
    """Ground 라인의 ℹ 주석(구상호·후계 등) — 기계 조립 답변에 그대로 병기한다."""
    return [m.group(1).strip() for ln in ground_lines for m in [re.search(r"ℹ (.*)$", ln)] if m]


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


_NAME_MODE_Q = re.compile(r"(?:이름|명칭|종목명|상품명)[이가은는을를]?\s*(?:들어|포함|붙|있|쓰)")


def _skip_pin_line(label: str, node, why: str, token: str) -> str:
    """코드 핀을 생략하는 Ground 줄의 단일 문형(4R J) — ⚙ 는 파이프라인 지시(답변 노출 금지, ℹ 만 사용자 주석)."""
    return (f"'{label}' → {node.node_id} ({node.node_type}) — ⚙ {why} · 코드 매핑을 싣지 않는다 · "
            f"public_funds.itm_nm 공백무시 LIKE 로 푼다 · 이름 검색 토큰 '{token}'")


@lru_cache(maxsize=4096)
def _name_chunk_exists(chunk: str) -> bool:
    """공백 제거 덩어리가 어느 종목명의 부분열인가 — DB 실측(캐시). 상품명 성분 판정의 근거(이름 목록 하드코딩 아님)."""
    con = connect_readonly()
    try:
        return con.execute("SELECT 1 FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE ? LIMIT 1", (f"%{chunk}%",)).fetchone() is not None
    finally:
        con.close()


_QUESTION_WORD = re.compile(r"(?:투자하|운용하|알려|보여|추천|얼마|몇|어떤|무엇|뭐|있어|있나|있는|중에서|중$|기준|대비)")


def _country_name_component(label: str, question: str) -> tuple[str, str] | None:
    """Country 라벨이 상품명 성분인지 — (인접 낱말, 이름 검색 토큰) 또는 None (4R 부류 I).
    판정: ⓐ 라벨에 붙은 잔여(_label_tail_token) ⓑ 라벨 앞/뒤 한 낱말(상품 명사·의문어 제외)과 이은 덩어리가 종목명 부분열(DB)."""
    from .router import PRODUCT
    tail = _label_tail_token(label, question)
    if tail:
        return tail, (label + tail).replace(" ", "")
    words = re.findall(r"[0-9A-Za-z가-힣.\-]+", question)
    for i, w in enumerate(words):
        base = _PARTICLE.sub("", w).strip(".")
        if base != label and label in base and len(base) > len(label) and _name_chunk_exists(base):
            return base, base          # 6R I′ — 라벨을 **품은 낱말 전체**('미래에셋베트남'·'피델리티재팬')가 종목명 부분열이면 그 낱말이 토큰
        if w != label and base != label:
            continue
        for j in (i + 1, i - 1):
            if not 0 <= j < len(words):
                continue
            adj = _PARTICLE.sub("", words[j])
            if len(adj) < 2 or adj in PRODUCT or adj in _GENERIC_NAME_TOKEN or _QUESTION_WORD.search(adj):
                continue
            chunk = (label + adj) if j == i + 1 else (adj + label)
            if _name_chunk_exists(chunk):
                return adj, chunk
        break
    return None


def _country_in_question(word: str, question: str) -> bool:
    """국가 가드의 발동 판정 — Ground 와 같은 규칙: 독립 낱말(경계)이고 상품명 성분이 아닐 때만 (4R I-2)."""
    return _boundary_hit(word, question) and _country_name_component(word, question) is None


def _label_tail_token(label: str, question: str) -> str | None:
    """라벨 바로 뒤(공백 없이) 이어지는 잔여 고유명 — 조사 제거·3자 이상·도메인 일반어 제외. 없으면 None."""
    for tail in re.findall(rf"{re.escape(label)}([0-9A-Za-z가-힣.]+)", question):
        tok = _PARTICLE.sub("", tail).strip(".")
        if len(tok) >= 3 and tok not in _GENERIC_NAME_TOKEN:
            return tok
    return None


def residual_name_token(question: str, ground_lines: list[str]) -> str | None:
    """KG 라벨에 붙어 있는데 매핑되지 않은 상품 고유명 — 이름 검색을 강제할 토큰.

    ground_lines 의 각 줄은 `'라벨' → …` 형태라 소비된 라벨을 그대로 읽을 수 있다.
    라벨 **바로 뒤에 공백 없이** 이어지는 한글·영숫자 덩어리에서 조사를 떼고, 길이 3 이상 ·
    도메인 일반어가 아닌 것만 돌려준다. 없으면 None (대부분의 질의가 여기 해당 — 불개입).
    3R A-2/D: Ground 가 `이름 검색 토큰 '…'` 을 명시한 줄(접두 절단 라벨·이름 모드)이 있으면 그 결합 토큰이 우선이다.
    """
    for line in ground_lines:
        m_tok = re.search(r"이름 검색 토큰 '([^']+)'", line)
        if m_tok:
            return m_tok.group(1)
    for line in ground_lines:
        m = re.match(r"'([^']+)'\s*→", line)
        if not m:
            continue
        label = m.group(1)
        for tail in re.findall(rf"{re.escape(label)}([0-9A-Za-z가-힣]+)", question):
            tok = _PARTICLE.sub("", tail).strip()
            # 🔴 11R KG ③-12 (부류 U) — Ground 가 토큰을 **운용사로 확정했으면** 같은 토큰의 잔여를
            #    '상품 고유명' 으로 재해석하지 않는다. 법인 접미('…투자신탁운용')는 상품 이름이 아니다
            #    (`_standalone_name_token` 이 이미 쓰는 같은 사전 — 가드 중복 0).
            if tok in _GENERIC_NAME_TOKEN or len(tok) < 2 or tok.endswith("운용"):
                continue
            # 🔴 10R 재검 ③-A(접두 앵커) — **KG 가 브랜드 라벨을 소비했더라도 리터럴은 「라벨+잔여」 결합형**이다.
            #    종전엔 잔여만 리터럴로 써서(피델리티차이나→`차이나` · 한국투자베트남그로스→`베트남그로스`)
            #    `or_co` 절이 타사만 막고 **같은 운용사 안의 이름 변형이 전부 살아남았다**(X18·R4·T14·W9).
            #    결합형이 DB 에 실재할 때만 쓴다 — 사용자가 브랜드를 안 썼으면(S12 '코어테크') 여기 오지 않는다.
            #    6R I′(잔여 2자 '재팬')도 같은 규칙의 특수형이라 함께 닫힌다.
            whole = (label + tok).replace(" ", "")
            if _name_chunk_exists(whole):
                return whole
            if len(tok) >= 3:
                return tok
    if not ground_lines:
        return _standalone_name_token(question)
    return None


def _standalone_name_token(question: str) -> str | None:
    """4R 부류 K — Ground 매칭이 0 이어도 상품 고유명 후보는 있다: 상품 명사('펀드'·'투자신탁'…) **바로 앞/안의 덩어리**
    (브랜드+상품명 결합어 = FND-016 사고 문형). 띄어 쓴 2자 브랜드('삼성 펀드 보수')는 후보가 아니다(되묻기 유지)."""
    from .router import PRODUCT
    words = re.findall(r"[0-9A-Za-z가-힣.\-]+", question)
    for i, w in enumerate(words):
        base = _PARTICLE.sub("", w)
        inner = next((p for p in PRODUCT if p in base and not base.startswith(p)), None)
        if inner:                                   # '삼성코리아대표증권자투자신탁' — 명사가 낱말 안에
            cand = base
        elif base in PRODUCT and i > 0:             # '펀드' 가 낱말 — 바로 앞 낱말
            cand = _PARTICLE.sub("", words[i - 1])
        else:
            continue
        cand = cand.strip(".")
        if len(cand) < 3 or cand.endswith("운용") or re.fullmatch(r"[0-9.]+", cand):
            continue
        # 6R 부류 N — 일반어 제거 사전에 **PRODUCT 키(오타 '펌드'·정식 용어 '투자신탁' 포함)** 를 넣는다: 라우터가 머리명사로 소비한
        #    낱말은 후보가 아니다('공모펌드' → '' → 후보 없음 — R7·S1 오거절). 라우터와 결정층이 같은 사전을 본다.
        rest = cand
        for g in sorted(set(_GENERIC_NAME_TOKEN) | set(PRODUCT), key=len, reverse=True):
            rest = rest.replace(g, "")
        if len(rest) >= 2 and cand not in _GENERIC_NAME_TOKEN and cand not in PRODUCT:
            # 🔴 17R OFFICIAL-002 (공식 예시) — 상품 명사가 **꼬리에 붙은** 호칭이면 그것까지 이름으로 썼다:
            #    "국민성장펀드의 구조와…" → `LIKE '%국민성장펀드%'` → 0행.
            #    실제 이름은 `미래에셋국민참여형국민성장혼합자산투자신탁…` 이라 '펀드' 라는 글자가 없다.
            #    사람은 "○○펀드" 라고 부르지만 DB 이름엔 그 말이 없는 경우가 흔하다.
            #    🔴 그렇다고 꼬리 명사를 늘 떼면 안 된다 — '삼성코리아대표증권자투자신탁' 은 '투자신탁' 이
            #    이름의 일부다. 그래서 **DB 에 실재하는 형태를 고른다**(위 결합형 분기와 같은 규칙).
            if not _name_chunk_exists(cand):
                for p in sorted(PRODUCT, key=len, reverse=True):
                    if cand.endswith(p) and len(cand) - len(p) >= 2:
                        trimmed = cand[: -len(p)]
                        if _name_chunk_exists(trimmed):
                            return trimmed
                        break
            return cand
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
    if not token or not _FUND_TBL.search(sql):
        return sql, False
    if _has_name_filter(sql):
        # KG 2R N2 — 이름 리터럴이 Ground 의 고유명 토큰을 **포함하지 않으면** 토큰으로 치환한다(1회): 오타('코어텍' — KG-034 거짓 유보) ·
        #    절단('KB차이나' ⊂ 'KB차이나그로스' — 4R T8 형제 4펀드 혼입). 리터럴이 토큰보다 길면(정식명을 그대로 적음) 존중.
        tok = token.replace(" ", "")
        pat = re.compile(r"((?:REPLACE\((?:\w+\.)?itm_nm,' ',''\)|(?:\b\w+\.)?itm_nm)\s+LIKE\s+')%([^%']+)%'", re.I)
        lits = [m.group(2) for m in pat.finditer(sql)]
        if not lits or any(tok in lit.replace(" ", "") for lit in lits):
            return sql, False
        done = False

        def _swap(m: re.Match) -> str:
            nonlocal done
            if done:
                return m.group(0)
            done = True
            return f"{m.group(1)}%{tok}%'"
        return pat.sub(_swap, sql), True
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
    if target:
        aliases = [a for a in aliases if a[0] in target]
    return _drop_contaminated_slots(aliases)


def _drop_contaminated_slots(aliases: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """같은 테이블에 정본 `ref_X` 슬롯이 있으면 오염 `cu_X` 슬롯은 싣지 않는다 (11R KG ③-4).

    🔴 AA21 뿌리 — Ground 가 `cu_fund_mgmt_co='삼성'` 과 `ref_fund_mgmt_co='Samsung Asset Management Co Ltd'`
       를 **한 매핑 줄에 나란히** 실어 주니 HCX 가 `cu_fund_mgmt_co IN ('삼성','Samsung…')` 로 섞었고,
       값 검사가 2회 기각해 거절로 끝났다(9R 의 ✅ 240 이 날아갔다). `cu_fund_mgmt_co` 실태(DB 실측):
       '삼성' 227 · '삼성KODEX' 3 · **'삼성증권(주)' 70(판매사)** · 상품명이 통째로 든 값 13종 — 운용사 축이 아니다.
    컬럼 접두 규약(`cu_` 수집 / `ref_` 정본)으로만 판정한다 — 이름 하드코딩 0.
    """
    canon = {(t, c[4:].lower()) for t, c, _ in aliases if c.lower().startswith("ref_")}
    return [a for a in aliases if not (a[1].lower().startswith("cu_") and (a[0], a[1][3:].lower()) in canon)]


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


# 🔴 근거문서에 싣지 않는 식별자 컬럼 (2026-09-04 온톨로지 사용 감사).
#    kg_alias 에는 남긴다 — 개체 동일성의 근거이고 값 사전 규모의 일부다. 다만 **프롬프트에 실을 이유가 없다**:
#    ① 사람이 CUSIP·LEI 로 상품을 묻지 않는다(평가 질의는 상담형이다)
#    ② ETF yaml 규칙 109개 컬럼 중 이 둘을 쓰는 규칙이 **하나도 없다** — 조회 경로가 아예 없다
#    ③ 실측 해악: '삼성전자' 질의에서 cusip 7종·lei 1종이 매핑 블록에 실렸고, 그 목록이
#       "여럿이면 IN 으로 모두" 안내와 겹쳐 없는 표기 17종 창작(239→259)의 재료가 됐다(9/4 FIN-05 계열).
#    합계 17,362행(alias 의 26%)이 이 두 컬럼이다.
_OPAQUE_ID_COLS = frozenset({"cusip", "lei"})


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
        for t, c, raw in _demote_product_name_raws(node, target_aliases(ctx, node, target, relations)):
            if c in _OPAQUE_ID_COLS:
                continue                    # 사람이 그 값으로 묻지 않는 식별자 — 아래 주석
            groups.setdefault((t, c), []).append(raw)
        for (t, c), vals in groups.items():
            uniq = sorted(set(vals), key=lambda v: (len(v), v))
            shown = uniq[:MAX_ALIAS_VALUES]
            more = "" if len(uniq) <= len(shown) else f" … 외 {len(uniq) - len(shown)}종"
            if _is_token_column(ctx, t, c):
                # S3 token alias — 다중값 콤마 컬럼은 등호가 아니라 토큰 확정식이다. 조건식을 그대로 준다(모델은 복사만)
                conds = " OR ".join(f"',' || {c} || ',' LIKE '%,{v},%'" for v in shown)
                out.append(f"- {name} ({node.node_type}) → {t}.{c} 의 토큰 {', '.join(repr(v) for v in shown)}{more} — 조건식 그대로: {conds}")
                continue
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
    extra_mapping: list[str] | None = None,
) -> str:
    """플래너에 넘길 근거문서 — KG 매핑 + 도메인 규칙 + 스키마.

    🔴 여기 실린 것만이 SQL 생성의 근거다. 규칙(yaml)을 고치면 이 문서가 바뀌고,
       그래서 프롬프트가 바뀐다 — 판정을 문서가 아니라 yaml 에 적어야 하는 이유다.

    테이블을 탐지하지 못하면 마스터 4개를 다 싣는다. 프롬프트는 커지지만, 엉뚱한 테이블만
    싣고 "컬럼이 없다" 로 실패하는 것보다 낫다.
    """
    target = list(tables) or list(TABLES)
    if cross:
        # 🔴 짝이 맞는 ext_* 만 싣는다 — 검사기가 허용하는 집합(validate 의 `라우팅 대상 + 짝 ext_*`)과 같게.
        #    서버 실측 2026-09-04 FIN-05 "삼성전자를 편입한 국내 ETF와 공모펀드는 각각 몇 개야?" 가 **답변 실패**했다:
        #    라우팅은 domestic_etfs·public_funds 인데 근거문서 첫 줄에 `ext_ovs_etf_holdings.holding_name` 의
        #    영문 표기 6종이 실렸고, HCX 가 그 값들로 서브쿼리를 짜 검사기에 기각 → 재생성 → 재기각으로 끝났다.
        #    라우팅 대상 밖 테이블의 매핑은 근거가 아니라 **오답 유도**다.
        paired = [t for t in EXT_TABLES if _EXT_PAIR.get(t) in target]
        target += [t for t in (paired or EXT_TABLES) if t not in target]

    parts: list[str] = []
    mapping = _mapping_block(ctx, hits, set(target), _asks_subsidiaries(question))
    if extra_mapping:                 # 11R KG ③-13 — KG 미매핑 운용사의 DB 역조회 결과도 같은 블록에 싣는다
        mapping = chr(10).join([f"- {l}" for l in extra_mapping] + ([mapping] if mapping else []))
    if mapping:
        parts.append(
            "# KG 개체 매핑 — 질의의 표기를 DB 실제 값으로 옮긴 것\n"
            "# 한 개체에 값이 여럿이면 전부 같은 개체다. 하나만 고르지 말고 IN 으로 모두 넣는다.\n"
            "# 🔴 **여기 적힌 값만 쓴다 — 목록에 없는 표기를 지어내지 않는다.** 서버 실측 2026-09-04:\n"
            "#    '삼성전자' 매핑은 constituent '삼성전자' 하나뿐인데 SQL 이 '삼성전자우'·'삼성전자 (우)'·\n"
            "#    '삼성전자 (WTS)' 등 **17종을 창작**해 IN 에 넣었고, 우선주가 섞여 239개가 259개로 나갔다.\n"
            "#    우선주·WTS·해외 표기는 **다른 종목**이다. 질문이 그것을 묻지 않았으면 넣지 않는다.\n"
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
            "# 🔴 ext_ 테이블에는 **마스터의 컬럼 이름이 없다.** 조인 키 줄의 왼쪽 이름을 그대로 쓴다 —\n"
            "#    ext_etf_holdings 의 ETF 식별자는 `etf_code` 이지 `pd_itm_no` 가 아니다\n"
            "#    (서버 실측 2026-09-04: `IN (SELECT pd_itm_no FROM ext_etf_holdings …)` 가 '없는 컬럼' 으로 기각).\n"
            "# 🔴 **개수를 세는 교차질의도 JOIN 형식으로 쓴다** — 서브쿼리로 풀지 말 것. 형식:\n"
            "#      SELECT '국내ETF' AS 구분, COUNT(DISTINCT e.pd_itm_no) AS 개수\n"
            "#        FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no\n"
            "#        WHERE h.constituent = '…' AND e.pd_grp_no = 'ETF'\n"
            "#      UNION ALL\n"
            "#      SELECT '공모펀드', COUNT(DISTINCT p.mtco_itm_no || '/' || p.or_co_xtn_itt_cd)\n"
            "#        FROM public_funds p JOIN ext_fund_holdings f\n"
            "#          ON f.grp = p.mtco_itm_no AND f.or_co = p.or_co_xtn_itt_cd\n"
            "#        WHERE f.holding_nm = '…' AND p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모'\n"
            "#    🔴 두 테이블에 같은 이름의 컬럼(itm_no)이 있으므로 **모든 컬럼에 별칭을 붙인다** —\n"
            "#    한정하지 않으면 'ambiguous column name' 으로 실행 전에 죽는다.\n"
            + "\n".join(f"- {k}" for t, k in JOIN_KEYS if t in target)
        )
    # R-2: triggered 규칙은 질문 어휘가 있을 때만. RULES_MODE=full 이면 종전처럼 전부 (eval/run_paired.py 의 대조군)
    layered = os.environ.get("RULES_MODE", "layered") != "full"
    rules = ctx.planner_context(target, question if (question and layered) else None)
    if rules:
        parts.append("# 도메인 규칙 (ontology/*.yaml — 조건식이 있으면 그대로 쓴다. 일부는 이 질문과 무관할 수 있다)\n" + rules)
    bond_q = bool(question) and "domestic_bonds" in target
    issuance_q = bond_q and bool(_ISSUANCE_Q.search(question)) and not _MATURITY_Q.search(question)
    windows = gate.resolve_relative_window(question) if (bond_q and not issuance_q) else []
    if issuance_q:
        # 🔴 2026-09-05 #66 — 종전엔 발행 질의에도 "'6개월 안에' = mat_dt BETWEEN …" 를 실어 보냈다. 그 한 줄이
        #    "최근 6개월 안에 새로 발행된 회사채" 오답의 1차 원인이다(답한 5종목의 실제 발행일은 2023~2025년).
        #    발행 축은 isu_dt 고, '최근·지난' 은 과거 방향이다 — 둘 다 여기서 못박는다.
        past = gate.resolve_past_window(question)
        line = (f"# 질문 시점(오늘) = {gate.BUYABLE_CUTOFF}(월) 로 고정.\n"
                "# 🔴 이 질문은 **발행 시점** 질의다 — 발행일은 isu_dt 다. mat_dt(만기일)로 발행 시점을 대신하지 않는다.\n"
                "# isu_dt 는 0·NULL 이 미수록(26행)이므로 발행 시점 조건에는 isu_dt > 0 을 함께 넣는다.")
        if past:
            wins = " · ".join(f"'{l}' = isu_dt BETWEEN {lo} AND {hi}" for l, lo, hi in past)
            line += f"\n# 상대 시점 확정(과거 방향): {wins} — 이 창을 그대로 쓴다."
        parts.append(line)
    elif windows:
        # 질문 시점을 못 들으면 HCX 가 '내년' 을 제멋대로 센다(2026-09-03 #51: 20280824~20290824). 창은 결정층이 정하고 가드가 강제한다 —
        # 이 문장은 재생성 횟수를 줄이는 보조다.
        wins = " · ".join(f"'{l}' = {'mat_dt = ' + str(lo) if lo == hi else f'mat_dt BETWEEN {lo} AND {hi}'}" for l, lo, hi in windows)
        parts.append(
            f"# 질문 시점(오늘) = {gate.BUYABLE_CUTOFF}(월) 로 고정. 상대 시점 확정: {wins}\n"
            "# 이 창을 그대로 쓴다. remaining_days 로 창을 만들지 않는다(잔존일수는 8/21 기준이라 3일 어긋난다). 만기 조건은 mat_dt 정수 리터럴로만."
        )
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



# 3R A-4 — 펀드(itm_nm 등호·공백무시 LIKE)도 같은 되묻기 재료를 낸다. 같은 목적 함수를 둘로 만들지 않는다.
_NAME_LOOKUP = re.compile(
    r"(?:TRIM\()?(?:\w+\.)?(pd_abrv_nm|pd_nm)\)?\s*=\s*'([^']+)'|REPLACE\((?:\w+\.)?(itm_nm),' ',''\)\s+LIKE\s+'%([^%']+)%'", re.I)
# 🔴 14R gold ③-2 (부류 Z″) — **정확일치·유사 판정의 비교 키는 공백을 지운 문자열이다.** `UNANS-001` 실측:
#    'KODEX AI로봇'(공백 없음)은 `pd_abrv_nm =` 등호라 되묻기 경로가 켜졌고, 'KODEX AI 로봇'(공백 하나)은
#    HCX 가 LIKE 로 쪼개 등호가 없다는 이유로 되묻기가 꺼졌다 — 띄어쓰기 하나로 안전망이 사라졌다.
#    이름 축 LIKE(원형·공백무시형)도 같은 되묻기 재료로 읽는다. 리터럴은 등장 순서대로 이어 붙인다.
_ETF_NAME_LIKE_LIT = re.compile(
    r"(?:REPLACE\(\s*(?:\w+\.)?(?:pd_abrv_nm|pd_nm)\s*,\s*' '\s*,\s*''\s*\)|(?:TRIM\(\s*)?(?:\w+\.)?\b(?:pd_abrv_nm|pd_nm)\b\s*\)?)"
    r"\s+LIKE\s+'%([^%']+)%'", re.I)
_TOKEN_SPLIT = re.compile(r"[A-Za-z0-9]+|[가-힣]+")


def _lookup_name_literals(sql: str) -> tuple[str, bool]:
    """개별 상품 조회 리터럴 — (이름 문자열, 펀드인가). 없으면 ('', False).

    등호(`pd_abrv_nm = 'KODEX AI로봇'`)와 이름 LIKE 분해형(`pd_nm LIKE '%AI%' AND … LIKE '%KODEX%'`)을
    같은 재료로 본다(gold ③-2). 펀드는 종전대로 `REPLACE(itm_nm,' ','') LIKE` 하나만 읽는다.
    """
    m = _NAME_LOOKUP.search(sql)
    if m:
        return (m.group(2) or m.group(4)), bool(m.group(3))
    lits = _ETF_NAME_LIKE_LIT.findall(sql)
    return (" ".join(lits), False) if lits else ("", False)


def _suggest_similar_products(sql: str) -> list[str]:
    """개별 상품 완전일치 조회가 0행일 때 유사 후보를 찾는다 — clarify.존재하지_않는_개체 의 되묻기 재료.

    'KODEX AI로봇' → 토큰(KODEX·AI·로봇) 중 첫 토큰(브랜드)을 필수로, 나머지 중 하나 이상이
    들어간 상품을 순자산 순으로 최대 4개. 실측(2026-09-01): KODEX 로봇액티브·글로벌로봇(합성)·
    차이나/미국휴머노이드로봇 이 이 방식으로 나온다. LLM 없이 SQLite 재조회 한 번이다.
    """
    name, is_fund = _lookup_name_literals(sql)
    if not name:
        return []
    toks = _TOKEN_SPLIT.findall(name)
    if len(toks) < 2:
        return []
    if is_fund:        # 펀드 — 종목명 stem(자산유형 괄호까지) 을 후보로, 순자산 순
        table, col, order = "public_funds", "itm_nm", "fd_nast_suma"
    else:
        table, col, order = ("overseas_etfs" if "overseas_etfs" in sql.lower() else "domestic_etfs"), "pd_abrv_nm", "du_last_aum"
    if not is_fund:
        # 브랜드(필수 토큰)는 어느 자리에 적혔든 브랜드다 — 실측 브랜드 접두 사전에 있으면 필수 토큰으로 올린다
        # (LIKE 분해형은 리터럴 순서가 HCX 마음대로다 — 'AI'·'로봇'·'KODEX').
        brands = {b.casefold() for b in _etf_brand_tokens()}
        toks.sort(key=lambda t: t.casefold() not in brands)
    first, rest = toks[0], [t for t in toks[1:] if len(t) >= 2]
    if not rest:
        return []
    cond = " OR ".join(f"replace({col},' ','') LIKE ?" for _ in rest)
    args = [f"%{first}%"] + [f"%{t}%" for t in rest]
    q = (f"SELECT DISTINCT TRIM({col}) FROM {table} "
         f"WHERE replace({col},' ','') LIKE ? AND ({cond}) "
         f"ORDER BY {order} DESC LIMIT 4")
    try:
        with connect_readonly() as con:
            return [r[0] for r in con.execute(q, args)]
    except sqlite3.Error:
        return []

_ISSUER_LOOKUP = re.compile(r"TRIM\(\s*(?:\w+\.)?pd_pbcm\s*\)\s*=\s*'([^']+)'|\bpd_pbcm\s*=\s*'([^']+)'", re.I)
# 2026-09-03 서버 실측: 재생성 SQL 의 리터럴 '(주)삼성전자' — 앞의 (주) 가 안 벗겨져 어두가 '(주' 가 되어
#   되묻기 후보가 (주)중소기업은행·(주)KB국민카드… 전부 '(주)' 발행사로 나갔다. 앞·뒤 법인 표기를 모두 뗀다.
_ISSUER_SUFFIX = re.compile(r"^\((?:주|유|사|재)\)|\(?(?:주|유|사|재)\)?$|주식회사|\s+")


def _issuer_literal(sql: str) -> str | None:
    """SQL 의 발행사 등호 리터럴(TRIM(pd_pbcm)='X' / pd_pbcm='X') — 없으면 None."""
    m = _ISSUER_LOOKUP.search(sql)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip() or None


def _violated_issuer(violations) -> str | None:
    """값 위반 목록에서 pd_pbcm 위반의 리터럴 — 없으면 None (되묻기 재료)."""
    for v in violations or ():
        if getattr(v, "column", "") == "pd_pbcm":
            return v.literal
    return None


def _suggest_similar_issuers(literal: str | None) -> list[str]:
    """발행사 리터럴이 DB 에 없을 때 같은 어두(앞 2글자)의 실제 발행사를 종목수 순으로 최대 4곳 — 되묻기 재료.

    2026-09-02 실측: '삼성전자가 발행한 채권 있어?' 는 0종목이 정답인데, 삼성카드(323종목)·삼성증권(16)·
    삼성바이오로직스(3)… 가 있다. clarify.존재하지_않는_개체 의 정답 형태("혹시 △△ 를 말씀하신 건가요?")
    재료를 LLM 없이 SQLite 재조회 한 번으로 만든다. 🔴 이 후보는 **사용자 되묻기 전용**이다 — 재생성 힌트
    (guard._value_hints)에는 넣지 않는다: 힌트로 주면 HCX 가 삼성전자 → 삼성카드 로 조건을 바꿔 답할 위험.
    """
    if not literal:
        return []
    stem = _ISSUER_SUFFIX.sub("", literal).strip()
    if len(stem) < 2:
        return []
    # 어간 전체를 품은 발행사(한국전력공사 → 한국전력공사(주))를 먼저, 그다음 같은 어두(앞 2글자)를 종목수 순으로.
    # DB 쪽도 법인 접두를 벗기고 비교한다 — 발행사 1,818 중 431 이 '(주)포스코' 꼴 접두형이라(2026-09-03 실측)
    # TRIM(pd_pbcm) 그대로 LIKE '포스%' 로는 '(주)포스코' 가 영영 안 잡혔다('포스코건설' → 후보 0).
    core = ("CASE WHEN substr(TRIM(pd_pbcm),1,3) IN ('(주)','(유)','(사)','(재)') "
            "THEN substr(TRIM(pd_pbcm),4) ELSE TRIM(pd_pbcm) END")
    q = (f"SELECT TRIM(pd_pbcm), COUNT(DISTINCT pd_no) FROM domestic_bonds "
         f"WHERE {core} LIKE ? AND TRIM(pd_pbcm) <> ? GROUP BY 1 "
         f"ORDER BY ({core} LIKE ?) DESC, 2 DESC, 1 LIMIT 4")
    try:
        with connect_readonly() as con:
            return [f"{name}({cnt:,}종목)" for name, cnt in con.execute(q, (f"{stem[:2]}%", literal, f"%{stem}%"))]
    except sqlite3.Error:
        return []


def _issuer_clarify_text(literal: str | None) -> str:
    """발행사 0건·값 위반 공용 되묻기 문장. 후보가 없으면 빈 문자열."""
    cand = _suggest_similar_issuers(literal)
    if not cand:
        return ""
    return (f" 발행사 '{literal}' 의 채권은 기준일 {gate.DATA_CUTOFF} 국내채권 데이터에 없습니다. "
            f"혹시 다음 발행사의 채권을 말씀하신 건가요? — {' / '.join(cand)}")


_BOND_COUNT_SUBJECT = re.compile(r"^(.*?[가-힣)])\s*(?:은|는|이|가)\s*(?:전부|총|모두|다|현재|지금)?\s*몇\s*(?:개|종목|건)")


def _bond_count_answer(sql: str, rows: str, n: int, question: str) -> str | None:
    """domestic_bonds 단일 COUNT(1행 1열, 값 > 0)의 답변을 기계 조립한다. 아니면 None. HCX 0회.

    2026-09-03 서버 실측 #52: SQL 이 국고채 295 를 셌는데 HCX 가 질문 문언을 그대로 옮겨 "국고채를 포함한 국공채는 총 295종목"
    이라 답했다 — 답변기는 SQL 이 무엇을 셌는지 모른다(#37·#39 계열). 주어는 질문의 '~는 몇 종목' 앞 구절에서 읽고,
    질문이 국고채를 **포함 언급**한 국공채 질의(ktb_head_is_gov)면 같은 WHERE 의 대분류 절을 국고채 확정식으로 바꾼 COUNT 를
    결정층이 한 번 더 실행해 "그중 국고채 N종목" 을 병기한다(SQL 2회 · 같은 상수 _KTB_FILTER).
    발동(전부): ① domestic_bonds 단독(JOIN·UNION·서브쿼리·GROUP BY 없음) ② SELECT 가 COUNT 하나 ③ 1행 1열 ④ 값 > 0(0 은 _zero_count_answer).
    """
    if n != 1 or "domestic_bonds" not in sql or re.search(r"\b(?:join|union|group\s+by)\b|\(\s*select\b", sql, re.I):
        return None
    m_sel = re.match(r"\s*SELECT\s+(.*?)\s+FROM\b", sql, re.I | re.S)
    if not m_sel or not re.fullmatch(r"COUNT\s*\(\s*(?:DISTINCT\s+)?[\w.*]+\s*\)(?:\s+AS\s+\w+)?", m_sel.group(1).strip(), re.I):
        return None
    lines = rows.splitlines()
    if len(lines) != 2 or " | " in lines[1]:
        return None
    try:
        cnt = int(float(lines[1].strip()))
    except ValueError:
        return None
    if cnt <= 0:
        return None
    m_subj = _BOND_COUNT_SUBJECT.search(question)
    subj = m_subj.group(1).strip() if m_subj and len(m_subj.group(1).strip()) <= 30 else "조건에 해당하는 채권"
    subj = re.sub(r"^(?:지금|현재)\s*", "", subj) or "조건에 해당하는 채권"
    last = subj[-1]
    particle = "은" if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 else "는"
    unit = "종목" if re.search(r"DISTINCT\s+pd_no", m_sel.group(1), re.I) else "건"
    out = f"{subj}{particle} 총 {cnt:,}{unit}입니다 (기준일 {gate.DATA_CUTOFF})."
    if _KTB_Q.search(question) and ktb_head_is_gov(question) and (_MCLS_EQ.search(sql) or _MCLS_IN.search(sql)):
        m = _MCLS_EQ.search(sql) or _MCLS_IN.search(sql)
        sub_sql = sql[:m.start()] + _KTB_FILTER + sql[m.end():]
        con = connect_readonly()
        try:
            sub = con.execute(sub_sql).fetchone()
        except sqlite3.Error:
            sub = None
        finally:
            con.close()
        if sub and sub[0] is not None:
            out += f" 그중 국고채(국고채권 + STRIPS)는 {int(sub[0]):,}{unit}이고, 나머지는 지역개발채·도시철도공채·국민주택채·모집지방채 등 지방채·국민주택채입니다. 통안채는 대분류가 특수채라 국공채에 들지 않습니다."
    return out


def _zero_count_answer(sql: str, rows: str, n: int) -> str | None:
    """단일 집계(COUNT·SUM) 결과가 0 이면 HCX 없이 '없음' 을 기계 조립한다. 아니면 None.

    2026-09-02 실측: '삼성전자가 발행한 채권 있어?' 를 HCX 가 COUNT(DISTINCT pd_no) 로 내어 결과가 (0,) 1행 —
    0행 조기반환(n == 0)을 타지 않고 compose 로 넘어갔다. 이번엔 "없습니다" 로 맞게 썼지만 비결정.
    값 0 → "없다" 는 어떤 질의에서도 참이므로 고정 문구가 안전하다. ensure_positive_count_answered(양수) 의 짝.
    발행사 등호 리터럴이 있으면 되묻기 후보를 붙인다.
    """
    if n != 1:
        return None
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm:
        return None
    head = re.sub(r"^\s*SELECT\s+", "", sql[:frm.start()], flags=re.I)
    # 🔴 14R KG ③-9 (X22) — **집계 1행의 개수 축이 0 이면 '0개' 로 답한다.** 종전엔 SELECT 에 표시 열이
    #    하나라도 더 있으면 불개입이라, `COUNT(*) as cnt, COALESCE(trusc_xtn_itt_cd,'정보 없음')` 1행이
    #    HCX 로 넘어가 리터럴 '정보 없음' 을 값으로 되읽고 "정보가 없습니다" 오거절이 됐다.
    #    판정은 **첫 SELECT 항목이 집계인가**로 한다 — 첫 열이 0 이면 어떤 표시 열이 붙어도 '없음' 은 참이다.
    items = _split_select_items(head)
    if not items or not re.match(r"\s*(?:COUNT|SUM)\s*\(", items[0], re.I):
        return None
    body = rows.splitlines()[1:]
    if len(body) != 1:
        return None
    try:
        val = float(body[0].split(" | ")[0].strip())
    except ValueError:
        return None
    if val != 0:
        return None
    unit = "종목" if re.search(r"DISTINCT\s+pd_no", sql, re.I) else "건"
    return (f"조건에 해당하는 상품이 데이터에서 확인되지 않습니다 (조회 결과 0{unit}, 기준일 {gate.DATA_CUTOFF})."
            + _issuer_clarify_text(_issuer_literal(sql)))


_BOND_YIELD_SORT = re.compile(r"\border\s+by\s+(?:MAX|MIN)?\(?\s*(applied_yield|after_tax_yield|srfc_irt|buy_yield)\b", re.I)


def ensure_bond_evidence_columns(sql: str) -> tuple[str, bool]:
    """수익률·금리로 정렬한 채권 목록의 SELECT 에 mat_dt(만기일)·crd_grd(신용등급)를 병기. (보정된 SQL, 보정했는지)

    2026-09-02 실측: '한전 채권 수익률 높은 순' SELECT 가 pd_nm·applied_yield·crd_grd 뿐 — 5.051%(만기 2052)
    와 4.744%(만기 2038)가 만기 없이 나열돼 판단 재료가 없다. ensure_fund_evidence_columns(펀드)의 채권판.
    불개입: 집계·GROUP BY·JOIN·`*`. crd_grd 는 ensure_grade_select_column 과 같은 표기(TRIM … AS crd_grd)."""
    if "domestic_bonds" not in sql or re.search(r"\b(?:join|union)\b|\(\s*select\b", sql, re.I):
        return sql, False
    if not _BOND_YIELD_SORT.search(sql):
        return sql, False
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm:
        return sql, False
    head, rest = sql[:frm.start()], sql[frm.start():]
    if _AGG_HEAD.search(head) or "*" in head or re.search(r"\bGROUP\s+BY\b", sql, re.I):
        return sql, False
    add = []
    if not re.search(r"\bmat_dt\b", head):
        add.append("mat_dt")
    if not re.search(r"\bcrd_grd\b", head):
        add.append("TRIM(crd_grd) AS crd_grd")
    if not add:
        return sql, False
    return head.rstrip() + ", " + ", ".join(add) + " " + rest, True


def ensure_bond_representative(sql: str) -> tuple[str, bool]:
    """채권 목록 SELECT 를 종목(pd_no) 단위로 묶는다 — GROUP BY pd_no + 정렬 컬럼 MAX/MIN. (보정된 SQL, 보정했는지)

    대표행 규칙의 채권판. 채권은 1,078종목이 장내·장외 2~4행(중복행 1,385)이라 목록에 같은 종목이 두 번 나온다
    — 2026-09-02 실측: 발행사 39곳의 수익률 top5 에 같은 종목 2회, 한전 낮은순 1063호 ×2. gold 채권 SQL 38개 중
    37개가 GROUP BY pd_no / DISTINCT pd_no 를 쓴다 — 가드는 gold 관행을 서버 SQL 에 강제하는 것이다.
    중복행 간 값 차이: pd_exg_mkt(전부)·applied_yield/eval_price/pd_risk_gcd(8종목)·after_tax_yield/trade_price
    (307종목)·pd_nm 공백(2종목). 정렬 컬럼은 방향 극값(DESC→MAX, ASC→MIN)으로 대표행을 결정하고 나머지는 동일값.
    불개입: 집계·GROUP BY·DISTINCT·JOIN·`*`·SELECT 에 pd_exg_mkt(장내/장외를 묻는 질의)·pd_no 미포함이면 주입해 묶는다."""
    if "domestic_bonds" not in sql or re.search(r"\b(?:join|union)\b|\(\s*select\b", sql, re.I):
        return sql, False
    if re.search(r"\bGROUP\s+BY\b|\bDISTINCT\b|\bpd_exg_mkt\b", sql, re.I):
        return sql, False
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm:
        return sql, False
    head, rest = sql[:frm.start()], sql[frm.start():]
    if _AGG_HEAD.search(head) or "*" in head or not re.search(r"\b(?:pd_nm|pd_abrv_nm|pd_no)\b", head):
        return sql, False
    m = _ORDER_BY_HEAD.search(rest)
    if m:
        col, direction = m.group(1).strip(), (m.group(2) or "ASC").upper()
        if re.fullmatch(r"[A-Za-z_]\w*", col) and not col.isdigit():
            agg = "MAX" if direction == "DESC" else "MIN"
            head, _, _ = _wrap_sort_col(head, col, agg)
            rest = _wrap_order_by_col(rest, col, agg)
    t = re.search(r"\b(?:ORDER\s+BY|LIMIT)\b", rest, re.I)
    pos = t.start() if t else len(rest)
    rest = rest[:pos].rstrip() + " GROUP BY pd_no " + rest[pos:]
    return head.rstrip() + " " + rest, True


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
        v = v.strip()
        # 🔴 10R 재검 ③-6 — 표시 열 문자열은 **자릿수까지 완성**해서 내보낸다. 숫자와 단위만 붙여 주면
        #    HCX 가 콤마를 임의 위치에 찍는다(U8 `425,2800백만USD` — 왼쪽부터 · Y16 `4378085백만USD` 무구분).
        #    값이 없어 나던 환각 → 단위가 없어 나던 환각(8R) → **자릿수가 없어 나는 환각**. 같은 계열의 세 번째 얼굴.
        m_amt = _DISPLAY_AMOUNT.fullmatch(v)
        return f"{int(m_amt.group(1)):,}{m_amt.group(2)}" if m_amt else v
    return str(v)


_NUM_CMP = re.compile(r"^\(?\s*(?:MAX|MIN|AVG|SUM)?\(?\s*(?:\w+\.)?(\w+)\s*\)?\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)\s*\)?$", re.I | re.S)


def drop_unquestioned_numeric_clause(sql: str, question: str) -> tuple[str, str | None]:
    """6R O — 0행일 때, **질문에 없는 숫자**로 만든 수치 비교 절(`fd_yr3_ern_r < -100` 류)이 단독으로도 0행이면 그 절만 뗀다.
    부류: 단일 FROM · 최상위 AND 절 · `col (<|>|<=|>=) 숫자` 한 항 · 그 숫자(부호·소수 무시한 자릿수열)가 질문 어디에도 없음.
    질문의 숫자를 쓴 절(예: '수익률 10% 이상')은 사용자의 조건이므로 손대지 않는다 — 조건 완화 금지(§9)와 충돌하지 않는 유일한 경우다:
    플래너가 지어낸 임계값은 사용자 조건이 아니다 (5R S2: '3년 수익률 최하위 5개' → `< -100` 환각으로 0행 → 거절).
    (보정 SQL, 뗀 절) — 못 떼면 (원문, None)."""
    # 🔴 10R ③-2 부수 — 값 술어가 HAVING 으로 옮겨 갔어도(클래스수 모수 분리) 이 안전망은 살아 있어야 한다.
    #    `MIN(col) < -100` 은 `col < -100` 인 행이 하나도 없으면 절대 참이 될 수 없다 — 판정식이 같다.
    segs = [(m, "WHERE") for m in [re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)] if m]
    segs += [(m, "HAVING") for m in [re.search(r"\bhaving\b(.*?)(?=\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)] if m]
    frm = re.findall(r"\b(?:from|join)\s+([A-Za-z_]\w*)", sql, re.I)
    if not segs or len(frm) != 1 or re.search(r"\(\s*select\b|\bunion\b", sql, re.I):
        return sql, None
    q_digits = set(re.findall(r"\d+", question.replace(",", "")))
    con = connect_readonly()
    try:
        for m_w, kw in segs:
            conjs = guard.split_conjuncts(m_w.group(1))
            for c in conjs:
                m = _NUM_CMP.match(c.strip())
                if not m:
                    continue
                digits = re.sub(r"\.0+$", "", m.group(3).lstrip("-"))
                if digits in q_digits or any(digits in d for d in q_digits):
                    continue
                probe = f"{m.group(1)} {m.group(2)} {m.group(3)}"     # 집계 껍질을 벗긴 행 단위 술어
                try:
                    alone = con.execute(f"SELECT COUNT(*) FROM {frm[0]} WHERE {probe}").fetchone()[0]
                except sqlite3.Error:
                    continue
                if alone:
                    continue
                rest = [x for x in conjs if x is not c]
                body = (f" {kw} " + " AND ".join(x.strip() for x in rest) + " ") if rest else " "
                return sql[:m_w.start()] + body + sql[m_w.end():], c.strip()
    finally:
        con.close()
    return sql, None


_LABEL_COL = re.compile(r"^'(.+)'$")


def _restore_empty_label_rows(cols: list[str], rows: list) -> list:
    """UNION 라벨 가지가 0행이면 그 행을 0 으로 되살린다.

    2026-09-04 DOM-10 실측: `SELECT '이자형', COUNT(*) … GROUP BY 1 UNION ALL SELECT '배당형' …` 에서
    첫 가지가 0행이라 **헤더 `'이자형' | COUNT(*)` 만 남고 행이 통째로 사라졌다.** 답변기는 그 헤더를
    세어 "이자형 1개" 라고 지어냈다. 라벨은 헤더에 있는데 값이 없으면 답변기가 채워 넣는다 —
    집계 0 은 '없다'이지 '모른다'가 아니므로 **0 행으로 명시**한다.
    COUNT 가 아닌 집계(AVG·MAX 등)는 0 이 거짓이므로 빈칸(미수록)으로 둔다.
    """
    out = list(rows)
    for i, c in enumerate(cols):
        m = _LABEL_COL.match(c.strip())
        if not m:
            continue
        lit = m.group(1)
        if any(str(r[i]).strip() == lit for r in out):
            continue
        out.append(tuple(lit if j == i else (0 if re.search(r"count\s*\(", cc, re.I) else None)
                         for j, cc in enumerate(cols)))
    return out


def _execute(sql: str) -> tuple[str, int]:
    con = connect_readonly()
    try:
        con.execute(f"pragma busy_timeout={int(SQL_TIMEOUT_S * 1000)}")
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = _restore_empty_label_rows(cols, cur.fetchmany(MAX_ROWS))
        head = " | ".join(cols)
        body = "\n".join(" | ".join(_cell(v, c) for v, c in zip(r, cols)) for r in rows)
        return f"{head}\n{body}", len(rows)
    finally:
        con.close()


DEFAULT_TOPN = 5
_TOPN_RANK_Q = re.compile(r"추천|순으로|순위|랭킹|톱|top|골라|(?:높은|낮은|큰|작은|많은|적은|좋은|비싼|싼|긴|짧은)\s*순|순서대로|정렬", re.I)
_TOPN_NUM_Q = re.compile(r"\d+\s*(?:개|종목|가지|곳|위|등|건|펀드)|top\s*\d|톱\s*\d|상위\s*\d|(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:개|종목|가지|곳)|하나만|하나\s*(?:만|추천|골라)", re.I)
_TOPN_ALL_Q = re.compile(r"전체|모두|전부|모든|다\s*(?:알려|보여)|목록|리스트|몇\s*(?:개|종목|건|가지)")


def ensure_default_topn(sql: str, question: str) -> tuple[str, bool]:
    """개수를 말하지 않은 랭킹 질의의 LIMIT 을 기본 5로 맞춘다. (보정된 SQL, 보정했는지)

    리드 결정 2026-09-02: '한전 채권 수익률 낮은 순으로 알려줘' 에 HCX 가 상한 30행을 골라 30종목을 전사 —
    22.2초(목표 15초 초과)·가독성 저하. 개수 없는 랭킹은 상위 5개 + 커버리지("전체 N종목 중 상위 5") 로 답한다.
    발동(전부): ① ORDER BY 존재 ② 질문에 랭킹 신호(추천·순으로·순위·높은/낮은 순…) ③ 질문에 개수·서수 없음
    ④ 질문에 전체·모두·목록·'몇 개' 없음 ⑤ SELECT 가 COUNT/SUM 집계 아님(분포·개수 질의 불개입) ⑥ LIMIT 이 없거나 5 초과.
    '가장 ~한' 최상급은 동률(만기 최단 20종목)이 있어 여기서 자르지 않는다 — 랭킹 신호 목록에 넣지 않았다."""
    if not re.search(r"\bORDER\s+BY\b", sql, re.I) or not _TOPN_RANK_Q.search(question):
        return sql, False
    if _TOPN_NUM_Q.search(question) or _TOPN_ALL_Q.search(question):
        return sql, False
    frm = re.search(r"\bFROM\b", sql, re.I)
    if not frm or re.search(r"\b(?:COUNT|SUM)\s*\(", sql[:frm.start()], re.I):
        return sql, False
    m = re.search(r"\bLIMIT\s+(\d+)\s*;?\s*$", sql, re.I)
    if m and int(m.group(1)) <= DEFAULT_TOPN:
        return sql, False
    body = sql[:m.start()].rstrip() if m else sql.rstrip().rstrip(";")
    return f"{body} LIMIT {DEFAULT_TOPN}", True


_UNION_OP = re.compile(r"\b(UNION\s+ALL|UNION|EXCEPT|INTERSECT)\b", re.I)


def _split_union(sql: str) -> list[str] | None:
    """최상위 UNION/EXCEPT/INTERSECT 로 문장을 조각낸다 — [가지, 연결자, 가지, …]. 아니면 None.

    괄호 안(서브쿼리·괄호 친 가지)과 문자열 리터럴 안의 연결자는 건드리지 않는다.
    """
    masked = _SQL_LITERAL.sub(lambda m: "'" + "\x01" * (len(m.group(0)) - 2) + "'", sql)
    depth, cuts = 0, []
    for i, ch in enumerate(masked):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            m = _UNION_OP.match(masked, i)
            if m and (not cuts or i >= cuts[-1][1]):
                cuts.append((i, m.end()))
    if not cuts:
        return None
    out, at = [], 0
    for s, e in cuts:
        out += [sql[at:s], sql[s:e]]
        at = e
    return out + [sql[at:]]


# 가지마다 그 가지의 FROM 기준으로 1회씩 거는 확정식 — 컬럼 정본화 · 기본모수 · 펀드단위 집계 교체
def _branch_guards(branch: str, q: str) -> tuple[str, list[str]]:
    notes = []
    for fn, label in ((lambda s: ensure_etf_index_canon(s), "ETF 기초지수 정본 축"),
                      (lambda s: ensure_etf_mgmt_canon(s), "ETF 운용사 정본 축"),
                      (lambda s: ensure_etf_base_population(s, q), "ETF 기본모수"),
                      (lambda s: ensure_fund_base_population(s, q, post=True), "펀드 기본모수"),
                      (lambda s: ensure_fund_distinct_count(s, q), "펀드단위 집계 교체")):
        branch, done = fn(branch)
        if done:
            notes.append(label)
    return branch, notes


def _unwrap_branch_parens(branch: str) -> tuple[str | None, str]:
    """UNION 가지를 감싼 여분의 괄호를 벗긴다 — (내부, 괄호 뒤 꼬리) 또는 (None, '').

    꼬리는 마지막 가지의 `ORDER BY …`·`LIMIT n` 처럼 괄호 **밖**에 남는 부분이다.
    """
    s = branch.lstrip()
    lead = branch[:len(branch) - len(s)]
    if not s.startswith("("):
        return None, ""
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return lead + s[1:i], s[i + 1:]
    return None, ""


def apply_union_branch_guards(sql: str, q: str) -> tuple[str, list[str]]:
    """교차질의(UNION) 문장을 SQLite 문법으로 정규화하고 **가지마다** 확정식을 1회씩 건다. (SQL, 조치 목록)

    🔴 14R KG ③-1 (최대 효과 · 6문항) — 단일 상품군에서 닫힌 확정식 4종이 UNION 문장엔 **하나도 안 붙는다.**
       모든 확정식 가드가 진입에서 `union` 을 보면 불개입하기 때문이다(그 방어 자체는 옳다 — 어느 가지의
       WHERE 인지 알 수 없는 혼합 문장에 주입하면 스키마 검사가 기각한다). 처방은 불개입이 아니라 **분해**다:
       가지를 떼어 내면 각 가지는 단일 SELECT 이고 자기 FROM 이 하나뿐이라 기존 가드가 그대로 성립한다.

    🔴 16R KG ③-2 (`Z13`·gold ③-2 `CROSS-003`) — **괄호 친 UNION 가지는 SQLite 문법이 아니다.**
       실측: `sqlite3` 3.50.4 에서 `(SELECT 1) UNION ALL (SELECT 2)` 는 `near "(": syntax error` 다.
       그래서 처방을 「구조 게이트가 선두 괄호를 허용한다」로 두면 게이트만 통과하고 EXPLAIN 에서 다시
       죽는다(사용자에겐 '오류가 발생해' 로 나간다 — 오거절보다 나쁜 표면). 뿌리 수리는 **정규화**다:
       최상위 가지를 감싼 여분의 괄호를 벗겨 유효한 복합 SELECT 한 문장으로 만든다.
    닫히는 문항: X8 · X9 · KG-025 · KG-026 · Z13 · CROSS-003 · X15 보조.
    """
    parts = _split_union(sql)
    if not parts:
        return sql, []
    notes: list[str] = []
    unwrapped = False
    for i in range(0, len(parts), 2):
        inner, tail = _unwrap_branch_parens(parts[i])
        if inner is not None and _single_select(inner):
            parts[i] = " " + inner + " " + tail            # SQLite 문법 정규화 — 여분의 괄호 제거
            unwrapped = True
        if not _single_select(parts[i]):
            continue
        fixed, done = _branch_guards(parts[i], q)
        if done:
            parts[i] = fixed
            notes += [f"가지{i // 2 + 1}: {d}" for d in done]
    if unwrapped:
        notes.insert(0, "가지 괄호 제거(SQLite 복합 SELECT 문법)")
    if not notes:
        return sql, []
    # 🔴 16R KG ③-1 부수 — 확정식이 한 가지의 열을 늘리면(`COUNT(*)` → 펀드수+클래스수) UNION 열 수가 어긋나
    #    실행이 통째로 죽는다. 짧은 가지를 NULL 로 채워 열 수를 맞춘다 — ETF 가지엔 클래스 축이 없으므로
    #    NULL 이 의미상으로도 옳다(별칭은 SQLite 규칙상 첫 가지의 것을 쓴다).
    widths = []
    for i in range(0, len(parts), 2):
        m_sel = _SELECT_HEAD.match(parts[i])
        f_ = re.search(r"\bfrom\b", parts[i], re.I)
        widths.append(len(_split_select_items(parts[i][m_sel.end():f_.start()])) if (m_sel and f_) else None)
    if None not in widths and len(set(widths)) > 1:
        wide = max(widths)
        for j, w in enumerate(widths):
            if w == wide:
                continue
            i, f_ = j * 2, re.search(r"\bfrom\b", parts[j * 2], re.I)
            parts[i] = parts[i][:f_.start()].rstrip() + ", NULL" * (wide - w) + " " + parts[i][f_.start():]
        notes.append(f"UNION 열 수 정렬({wide}열)")
    return "".join(parts), notes


# 비교 연산자 앞에 오는 식별자 = 술어의 컬럼 자리 (문자열 리터럴·테이블 한정자 뒤는 제외)
_PRED_COL = re.compile(r"(?<![.\w'])([A-Za-z_]\w*)\s*(?:[=<>!]|\bLIKE\b|\bGLOB\b|\bIN\b|\bIS\b|\bBETWEEN\b)", re.I)


def drop_undeclared_table_or_branches(sql: str) -> tuple[str, list[str]]:
    """FROM/JOIN 에 없는 테이블을 참조하는 **OR 가지**를 걷는다 — 가지가 전부 사라지면 손대지 않는다.

    🔴 16R gold ③-1 (부류 V′ · `OFFICIAL-004` 회귀) — 실행 전 검사가 계산해 둔 조치를 **기계가 집행한다.**
       실측: `… OR replace(ext_etf_holdings.ticker,' ','') LIKE '%우주항공%' OR … '%Space%'` 두 가지 때문에
       문장 전체가 기각되고 재생성이 **완전히 같은 문장**을 돌려줘 무응답이 됐다. 그 두 가지만 걷으면
       13R 의 답이 그대로 나온다. OR 가지는 조건을 넓히는 자리라 걷어도 모수가 넓어지지 않는다
       (AND 절은 걷으면 모수가 넓어지므로 대상이 아니다 — 그쪽은 `drop_hallucinated_column_conjuncts` 가
       리터럴 중복이 확인될 때만 다룬다).
    """
    declared = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", sql, re.I)}
    bad = {t for t in (set(TABLES) | set(EXT_TABLES)) - declared
           if re.search(rf"\b{re.escape(t)}\s*\.", sql, re.I)}
    if not bad:
        return sql, []
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        return sql, []
    out, dropped = [], []
    for c in _flat_conjuncts(m_w.group(1)):
        if not any(re.search(rf"\b{re.escape(t)}\s*\.", c, re.I) for t in bad):
            out.append(c)
            continue
        branches = guard.split_disjuncts(_outer_group(c.strip()) or c)
        keep = [b for b in branches if not any(re.search(rf"\b{re.escape(t)}\s*\.", b, re.I) for t in bad)]
        if len(branches) < 2 or not keep:
            out.append(c)                        # 가지가 하나뿐이거나 전부 사라진다 — 기각으로 보낸다
            continue
        dropped += [b.strip()[:60] for b in branches if b not in keep]
        out.append(keep[0].strip() if len(keep) == 1 else "(" + " OR ".join(b.strip() for b in keep) + ")")
    if not dropped:
        return sql, []
    return sql[:m_w.start(1)] + " " + " AND ".join(out) + " " + sql[m_w.end(1):], dropped


def drop_hallucinated_column_conjuncts(sql: str) -> tuple[str, list[str]]:
    """스키마에 없는 컬럼을 쓴 최상위 AND 절을, **그 값 리터럴이 다른 절에 이미 걸려 있을 때만** 걷는다.

    🔴 16R KG ③-6 / gold ③-1 — `Z11` 실측: `asset_class='중국주식' AND fund_type='공모'` 두 환각 컬럼이
       실행 전 검사에 걸리고, 재생성이 **완전히 같은 문장**을 돌려줘 오거절로 끝났다(13R 205펀드/522클래스 회귀).
       확정식 가드가 `zrin_ptn_nm='중국주식'`·`prvo_pbff_desc='공모'` 를 이미 심었으므로 남은 환각 절은
       정보가 0 이다 — 지워도 모수가 넓어지지 않는다. **리터럴이 다른 곳에 없으면 지우지 않는다**(모수 확대 금지).
    """
    if not _COLUMNS_OF:
        return sql, []
    declared = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", sql, re.I)}
    known: set = set()
    for t in declared:
        known |= _COLUMNS_OF.get(t, set())
    if not known:
        return sql, []
    m_w = re.search(r"\bwhere\b(.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", sql, re.I | re.S)
    if not m_w:
        return sql, []
    conjs = _flat_conjuncts(m_w.group(1))
    kept, dropped = [], []
    for c in conjs:
        cols = {m.group(1).lower() for m in _PRED_COL.finditer(re.sub(r"'(?:[^']|'')*'", "''", c))}
        bad = sorted(x for x in cols if x not in known and x not in _SQL_WORDS)
        lits = _SQL_LITERAL.findall(c)
        others = " AND ".join(x for x in conjs if x is not c)
        if bad and lits and all(l in others for l in lits):
            dropped.append(f"{bad[0]} 절")
            continue
        kept.append(c)
    if not dropped:
        return sql, []
    return sql[:m_w.start(1)] + " " + " AND ".join(kept) + " " + sql[m_w.end(1):], dropped


def _apply_sql_guards(sql: str, q: str, name_token: str | None, future, step, ctx, tables: list | None = None,
                      mgmt: tuple | None = None, fired_out: list | None = None) -> str:
    """플래너가 낸 SQL 에 기계 보정 가드를 전부 적용한다.

    🔴 **재생성 SQL 도 반드시 이 체인을 타야 한다** — 2026-08-31 밤 FND-R09 실측:
       금지 컬럼 기각 → 재생성이 han_clas_policies 로 정확히 고쳤는데, 재생성 경로가
       ensure_limit 만 거쳐 근거컬럼 보강을 건너뛰었다. 필터 컬럼이 SELECT 에 없으니
       답변기가 27행을 조회하고도 "정보를 찾을 수 없습니다" 로 버렸다.
       가드를 한 곳에 모아 두 경로가 같은 보정을 받게 한다.
    """
    # 🔴 10R gold N1 — **체인 맨 앞.** 뒤의 모든 가드가 `split_conjuncts`(최상위 AND 분해)를 전제하므로
    #    최상위 bare OR 를 먼저 접어야 그 가드들이 조건을 잘못 자르지 않는다.
    sql, top_fixed = rewrite_dialect_top(sql)
    if top_fixed:
        step("[Guard] 방언 토큰 치환 — `SELECT TOP n` 을 `LIMIT n` 으로 (10R 재검 ③-7 · U9 실측: 토큰 하나 빼면 "
             "정상인 SQL 이 문법 기각 → 재생성이 같은 토큰 반복 → 오거절. 기계로 고칠 수 있으면 보정한다)")
    sql, or_fixed = ensure_or_group_parens(sql)
    if or_fixed:
        step("[Guard] 최상위 OR 재괄호화 — 괄호 없이 섞인 `A AND B OR C` 를 `A AND (B OR C)` 로 보정 "
             "(10R gold N1 · FND-009 실측: 기각당한 문장이 근거문서에 실은 우리 규칙 원문 enums:949 라 "
             "자연어 피드백으로는 1·2차 모두 못 고쳐 무응답)")

    # ── enforce 슬롯 (yaml query_rules.<name>.enforce) — 의미 가드들보다 먼저 ────────────
    # 절차 docs/guard_to_yaml_migration_2026-09-03.md §2-3. 발동하면 `/*M:<mark>*/` 표식을 남기고
    # 짝이 되는 코드 가드는 그 표식을 보고 침묵한다(§2-4). 가드 삭제는 두 라운드 뒤(§5).
    # 🔴 절차는 "체인 맨 앞" 이라 적었지만 **방언 치환·OR 재괄호화 뒤**에 둔다 — 그 둘은 보정이 아니라
    #    정규화이고, `SELECT TOP n`(비-SQLite) 상태에서 WHERE 를 끼우면 실행조차 안 돼 대조가 불가능하다
    #    (섀도 X2 실측). 의미를 고치는 가드들보다는 여전히 앞이다.
    if tables:
        sql, enf_fired = guard.apply_enforce(sql, q, list(tables), set(), ctx)
        for mark in enf_fired:
            step(f"[Guard] enforce 슬롯 {mark} — yaml 선언이 SQL 을 고쳤다 "
                 "(UNION 은 가지마다 독립 판정 — 코드 가드가 통째로 불개입하던 자리)")
        if fired_out is not None:
            fired_out.extend(enf_fired)
    sql, future_dt = strip_future_basis_date(sql)
    if future_dt:
        step(f"[Guard] 기준일 이후 SQL 리터럴 제거 — '{future_dt}' (10R gold N8 · FND-R02 실측: HCX 가 기준일"
             f"({gate.DATA_CUTOFF}) 이후 날짜를 지어내 0행을 만들고 '조건 교집합 0' 이라는 거짓 사유로 거절했다)")
    sql, lb = ensure_maturity_lower_bound(sql)
    if lb:
        step(f"[Guard] 만기 하한 보정 — mat_dt >= {BUYABLE_INT} 주입 (만기일 미수록 0값·만기 경과 행 제외 — 구매가능 판정일 8/24, as-of 8/22 와 분리)")
    sql, incl = ensure_cutoff_inclusive(sql)
    if incl:
        step(f"[Guard] 기준일 경계 교정 — 옛 기준일(8/20~8/23) 만기 하한을 mat_dt >= {BUYABLE_INT} 로 (2026-09-02 리드 결정: 8/22·8/23 만기 14종목은 8/24 에 만기 경과 — 2026-09-01 실측의 '당일 7종목' 도 이제 모수 밖)")
    sql, floor_fixed = raise_maturity_floor(sql, q)
    if floor_fixed:
        step(f"[Guard] 만기 하한 인상 — 판정일 이전 하한(BETWEEN 앞값 포함)을 mat_dt >= {BUYABLE_INT} 로 (만기 경과 49행 혼입 방지 — '올해·2026년 만기' 를 1/1 부터 잡는 SQL · 2026-09-03 #51 재점검)")
    sql, key_fixes = ensure_fund_key_column(sql)
    if key_fixes:
        step(f"[Guard] 펀드 키 컬럼 교정 — {' · '.join(key_fixes)} (7R S′ · 6R W11 실측: KG 가 rptt_ksd_itm_no 를 핀했는데 "
             "HCX 가 같은 값을 itm_no IN (…) 에 실어 0행 오거절 — 값 검사·코드 검사 둘 다 펀드 키 컬럼을 안 본다)")
    sql, estb_fixed = ensure_fund_estb_year(sql, q)
    if estb_fixed:
        step("[Guard] 설정연도 확정식 — 설정일 정본은 ext_fund_page.estb_dt 뿐이라 날짜 절을 연도 범위로 교체 "
             "(KG 4R G2 · KG-035 `fd_daily_bas_dt BETWEEN 20260000 AND 20269999` → 2,594 오답 · X19 `estb_dt <= 20250930` → 2,853 오답)")
    sql, pop_fixed = ensure_fund_base_population(sql, q)
    if pop_fixed:
        step("[Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)")
    # 🔴 지수 확정식이 **모수 가드보다 먼저** 돌아야 한다 — 모수 가드의 날조 술어 제거가 오염 컬럼의
    #    지수 절을 '근거 없는 술어' 로 보고 지워 버린다(순서가 뒤면 지수 조건이 통째로 사라진다).
    sql, idx_fixed = ensure_etf_index_canon(sql)
    sql, mgmt_fixed = ensure_etf_mgmt_canon(sql)
    if mgmt_fixed:
        step("[Guard] ETF 운용사 확정식 — 오염 컬럼 cu_fund_mgmt_co(판매사·브랜드·상품명 혼재: '삼성증권(주)' 70행 "
             "판매사 · 상품명 통째 13종)를 정본 ref_fund_mgmt_co **정확일치**로 교체 "
             "(11R KG ③-4 · 실측 삼성자산운용 240 = gold. 접두 LIKE 는 별개 법인 Samsung Active 25행을 합산해 265 를 만든다)")
    injected = marked_conjuncts(sql)          # 체인 끝 사후조건의 재료 (1순위 — 확정식 원자성)
    if idx_fixed:
        step("[Guard] ETF 기초지수 확정식 — 오염 컬럼 cu_base_index(95.5% 공백 · 값 있는 9행은 무관 상품)를 "
             "정본 ref_base_index 순수추종식(지수명 + CR/TR/PR 접미)으로 교체 "
             "(10R KG 부류 T · 실측 KOSPI200 34 · NASDAQ100 16 · S&P500 24 = gold)")
    sql, etf_pop = ensure_etf_base_population(sql, q)
    if etf_pop:
        step("[Guard] ETF 기본모수 주입 — 상품군 확정식(pd_grp_no='ETF' · pd_sale_yn=1)이 SQL 에 없어 주입 "
             "(8R B-4″-b · 7R U8 실측: 모수 절이 없으니 HCX 가 cu_charge_rt>0 · NOT LIKE '%not provided%' 라는 "
             "아무도 요구하지 않은 모수를 지어냈다 · AA22 49 vs gold 45)")
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
    mgr_notes: list[str] = []
    sql, mgr_fixed = ensure_fund_manager_ranking(sql, q, mgr_notes)
    if mgr_fixed:
        step("[Guard] 운용사 집계 확정식 — 코드 GROUP BY + 최빈 이름 + 펀드수·클래스수·순자산 억원 템플릿 "
             "(2026-09-02 S11: 이름 GROUP BY + COUNT(*) 로 순자산 질의를 오해 · mtco_nm 3라운드)"
             + (" · " + " · ".join(mgr_notes) if mgr_notes else ""))
    sql, ecnt_fixed = ensure_fund_entity_count_ranking(sql, q)
    if ecnt_fixed:
        step("[Guard] 개체 개수 랭킹 축 — '가장 많이 …하는' 랭킹의 정렬을 COUNT(DISTINCT 펀드키)로 바꾸고 펀드수·클래스수를 구분 병기 "
             "(11R KG ③-10 · KG-008 실측: 개수 질문인데 SUM(fd_nast_suma) 정렬 + COUNT(*)(클래스수)를 '257개의 펀드'로 명시 — "
             "gold 홍콩상하이 714 · 국민 516 · 씨티 465)")
    sql, ext_notes = ensure_ext_join(sql, ctx)
    if ext_notes:
        step(f"[Guard] 외부 테이블 JOIN 주입 — {' · '.join(ext_notes)} "
             "(2026-09-02 R2·S11 재검: mtco_nm 환각 3라운드 연속 1차 기각으로 재생성 예산 소진 → 거절)")
    sql, modal_fixed = ensure_fund_mgmt_modal_name(sql)
    if modal_fixed:
        step("[Guard] 운용사 최빈 이름 — MAX(mgmt_co_nm) 이 합병 코드의 구명칭을 사전순으로 뽑던 것을 "
             "소수 이름 제외로 교정 (2026-09-01 FND-035 재검: 00040007 이 프랭클린템플턴(10행)으로 표기 — 정본은 우리자산운용 373행)")
    before_ctag = sql
    sql, ctag_fixed = ensure_fund_country_tag(sql, q, name_token)
    if ctag_fixed:
        step("[Guard] 국가 태그 확정식 — 국가어 질의의 지역·설립국·태그·속성명·이름 OR 절을 KG Country 토큰 canon 하나로 접음 "
             f"(KG 1R S3·3R C: 어떤 태그를 썼든 교정 · '유형' 이면 zrin_ptn_nm) · 전: {before_ctag[before_ctag.upper().find('WHERE'):][:120]}")
    sql, attr_fixed = ensure_fund_attr_tag(sql, q)
    if attr_fixed:
        step("[Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 "
             "(KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)")
    # 🔴 부가 집계 병기보다 앞 — 모수를 먼저 되돌려야 그 위에서 센 수가 맞다.
    sql, ext_left = guard.ensure_ext_left_join(sql)
    if ext_left:
        step("[Guard] 외부표 LEFT 전환 — " + "·".join(ext_left) + " 을 INNER 에서 LEFT 로 "
             "(커버리지 93.7% — INNER 면 짝 없는 561클래스가 조용히 사라진다. ext 조건이 WHERE 에 "
             "있으면 결과 동일 · 2026-09-04 KG-005 실측)")
    sql, subc_fixed = ensure_fund_unit_subcount(sql)
    if subc_fixed:
        step("[Guard] 부가 집계 펀드 단위 병기 — 조건 집계(SUM CASE)를 펀드수·클래스수로 갈라 별칭에 단위를 굽는다 "
             "(2026-09-04 KG-005 실측: '삼성자산운용이 운용하는 펀드는 868개' — 868 은 클래스 수다. "
             "클래스를 펀드로 답하는 15R 최다 오답의 재발)")
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
    sql, btyp_fixed = ensure_fund_type_axis(sql, q)
    if btyp_fixed:
        step("[Guard] 유형 축 주입 — 질문이 고른 유형(zrin_btyp_nm) 절이 SQL 어디에도 없어 확정식을 AND 로 주입 "
             "(7R 뿌리⑥ = KG 4R G3 + 6R P′ · Y7 실측: '주식형 … 운용사 3곳' 답이 전체 랭킹 V5 와 바이트 단위로 같았다)")
    # 🔴 값 사전 대조(check_values)보다 앞 — 0행 매칭 값 하나가 정답 SQL 을 통째로 죽이던 자리.
    #    2026-09-04 KG-012: `zrin_btyp_nm IN ('해외주식형','국내외혼합')` 에서 뒤엣값이 그 컬럼에 없어
    #    기각당했는데, 실측하면 그 SQL 이 낸 205펀드/522클래스가 정답이었다.
    if tables:
        sql, dead = guard.prune_dead_in_literals(sql, ctx)
        if dead:
            step("[Guard] IN 목록 정리 — 그 컬럼에 없는 값 " + " · ".join(f"'{d}'" for d in dead)
                 + " 을 걷어냈다 (0행 매칭이라 결과 불변 · 유효값이 남을 때만 · 2026-09-04 KG-012)")
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
    sql, clsnote_fixed = ensure_fund_class_notation(sql, q)
    if clsnote_fixed:
        step("[Guard] 클래스 표기 확정식 — '종류A·Ce' 는 수수료체계(han_clas_nm)가 아니라 종목명 접미라 itm_nm 접미 LIKE 로 교체 "
             "(KG 4R G7 · Z1 실측: TRIM(han_clas_nm)='종류 A' 는 DB 에 0행 — 실제 값은 '수수료선취-오프라인' 류)")
    sql, space_fixed = ensure_spaceless_name_match(sql, name_token)
    if space_fixed:
        step("[Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 "
             "(2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)")
    sql, estb_lookup = ensure_fund_estb_lookup(sql, q)
    if estb_lookup:
        step("[Guard] 설정일 개별 조회 확정식 — ext_fund_page LEFT JOIN + MIN/MAX(estb_dt) + 클래스수 병기로 교체 "
             "(10R KG 부류 E · AA5 실측: SELECT 에 없는 설정일을 환각 · Z9: LIMIT 1 무정렬로 형제 펀드 값)")
    sql, unflip = fix_inverted_name_predicate(sql, q)
    if unflip:
        step("[Guard] 부정 이름 술어 교정 — 질문의 낱말을 NOT LIKE 로 뒤집은 절을 LIKE 로 되돌림 "
             "(10R KG 부류 I · Z18 실측: 'ETF로 자산배분하는 공모펀드' 가 NOT LIKE '%ETF%' 로 나가 "
             "1,508펀드 오답 목록 — gold 20펀드. 질문에 제외 어휘가 있으면 사용자 조건이라 불개입)")
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
    sql, eok_fixed = ensure_amount_eok_columns(sql)
    if eok_fixed:
        step("[Guard] 원 단위 금액 억원 병기 — SELECT 의 순자산(bare/집계/별칭)에 억원 문자열 열 주입, 원값은 답변 입력에서 숨김 "
             "(4R V7: ETF 운용사 집계 164,377,105,967,341원 자릿수 훼손 계열 · 펀드·ETF 공통)")
    sql, safe_fixed = ensure_fund_safe_grade_direction(sql, q)
    if safe_fixed:
        step("[Guard] 위험등급 방향 교정 — '안전' 질의의 등급 필터가 1·2(고위험)로 뒤집혀 6(매우 낮은 위험)으로 교체 (2026-08-31 밤 FND-C03 실측: 안전=1등급 반전 조회)")
    sql, grades_fixed = expand_grade_comparison(sql, q)
    if grades_fixed:
        step("[Guard] 등급 서열 확장 — 질문의 '이상/이하' 등급 조건이 단일 등급 비교로 좁혀져 TRIM(crd_grd) IN (서열 목록) 으로 확장 (2026-08-31 'A등급 이상'→crd_grd='A-' 실측)")
    sql, kind_fixed = ensure_kind_filter(sql, q)
    if kind_fixed:
        step("[Guard] 종류 조건 주입 — 질문의 채권 종류 낱말이 SQL 에 필터되지 않아 동의어 확정식을 주입 (2026-08-31 저녁 'AA등급 이상 회사채'에 종류 조건 부재 실측 — 617160d 사고 ② 재발)")
    sql, mcls_fixed = normalize_mcls_values(sql, q)
    if mcls_fixed:
        step("[Guard] 대분류 값 정리 — std_pd_mcls_nm IN 목록에 섞인 종류 값(bd_knd·소분류)을 떼어냈다 "
             "(2026-09-04 서버 실측 #61: IN ('국공채','국고채권') 이 값 검사에 걸려 재생성도 같은 문장 → "
             "정답 1,775 를 아는 질문이 오거절. 뗀 값은 그 컬럼에서 0행이라 결과는 바뀌지 않는다)")
    sql, ktb_fixed = ensure_ktb_kind(sql, q)
    if ktb_fixed:
        step("[Guard] 국고채 종류 교정 — 대분류 국공채(지방채·통안채 혼입)로 뭉개진 필터를 국고채 확정식(bd_knd='국고채권' + STRIPS 결측 회수)으로 교체 (2026-08-31 저녁 '국고채 몇 종목'→2,840 실측)")
    elif _KTB_Q.search(q) and ktb_head_is_gov(q) and (_MCLS_EQ.search(sql) or _MCLS_IN.search(sql)):
        step("[Guard] 국고채 종류 교정 보류 — 머리명사가 국공채(국고채는 포함·병렬 언급) · 대분류 필터 유지 "
             "(2026-09-03 서버 실측 #52: '국고채를 포함해서 국공채는 전부 몇 종목' 을 국고채 295 로 좁힌 오폭)")
    sql, backstop_fixed = ensure_credit_backstop(sql, q)
    if backstop_fixed:
        step("[Guard] 신용보강 층 주입 — 정부보강 질의의 WHERE 에서 빠진 층(C 법정 손실보전 기관 등)·랭킹 제외 조건을 주입 (2026-08-31 저녁 재발 실측: C층 탈락으로 1위 5.859% 누락 + 사모/1등급 14.05% 혼입)")
    sql, reco_fixed = ensure_reco_exclusions(sql, q)
    if reco_fixed:
        step("[Guard] 추천 제외 주입 — 추천·랭킹 질의의 WHERE 에 고위험제외(사모·1등급·C0)·수익률정상 조건을 주입 (2026-08-31 저녁 'AA등급 이상 추천'에 사모 3건 혼입 실측. 질문이 그 범주를 명시하면 건너뜀)")
    sql, recosort_fixed = ensure_reco_sort(sql, q)
    if recosort_fixed:
        step("[Guard] 추천 정렬 주입 — 추천 질의에 ORDER BY 가 없어 기본 정렬 applied_yield DESC 를 주입 (2026-09-01 서버 실측: '망하지 않을 회사 채권 골라줘' 가 정렬 없는 임의 5행 — 상위 수익률 누락)")
    sql, sortaxis_fixed = ensure_sort_axis(sql, q)
    if sortaxis_fixed:
        step("[Guard] 정렬 축 교정 — '표면금리' 질의의 정렬을 srfc_irt 로 맞추고 SELECT 에 병기 "
             "(2026-09-04 서버 실측: 'A등급 이상 회사채 표면금리 높은 순' 이 applied_yield 로 정렬돼 답변 축까지 '수익률' 로 바뀜 — 1·2위 표면금리 7.1·3.0)")
    sql, cpsplit_fixed = ensure_coupon_type_split(sql, q)
    if cpsplit_fixed:
        step("[Guard] 이자유형 분리 — 표면금리 랭킹에 고정금리 이표채 절 주입 (이자유형분리 규칙 · gold BND-D-012. 할인채는 srfc_irt 가 발행 할인율 · 조건검색에는 주입하지 않는다)")
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
    sql, bev_fixed = ensure_bond_evidence_columns(sql)
    if bev_fixed:
        step("[Guard] 채권 근거컬럼 보강 — 수익률·금리 정렬 목록의 SELECT 에 만기일·신용등급 병기 (2026-09-02 실측: 한전 수익률순 답이 5.051%(2052년 만기)와 4.744%(2038년)를 만기 없이 나열)")
    sql, brep_fixed = ensure_bond_representative(sql)
    if brep_fixed:
        step("[Guard] 채권 대표행 보정 — 목록 SELECT 를 GROUP BY pd_no 로 종목 단위 묶기 + 정렬 컬럼 MAX/MIN (2026-09-02 실측: 장내·장외 중복행으로 발행사 39곳 top5 에 같은 종목 2회 — gold 38개 중 37개가 GROUP BY pd_no)")
    sql, tie_fixed = ensure_tie_break(sql, q)
    if tie_fixed:
        step("[Guard] 동률 2차 정렬 주입 — ORDER BY 1차 축 뒤에 신용등급 서열 → 만기 이른 순 → pd_no 를 붙였다 "
             "(2026-09-04 서버 실측 #62: '표면금리 높은 순 5개' 를 두 번 물어 7.5% 동률 두 종목의 1·2위가 뒤바뀜 — "
             "2차 키가 없으면 등수는 DB 가 준 우연이다)")
    sql, hold_fixed = ensure_fund_holdings_template(sql, q, ctx, name_token, tables == ["public_funds"])
    if hold_fixed:
        step("[Guard] 구성종목 확정식 — 개별 펀드의 보유 종목 질의를 ext_fund_holdings(grp+or_co) JOIN 템플릿으로 교체, 대표 클래스 1개의 목록을 비중순으로 "
             "(5R KG-028·KG-034·X1·X2: public_funds 단독 조회 또는 ETF 구성종목 테이블로 이탈)")
    if name_token and _FUND_TBL.search(sql):
        # 6R J′ — 사후조건: 어느 가드가 절을 걷어냈든(호수 가드가 이름+N호 결합 LIKE 를 통째로 제거 — W6) 이름 토큰은 살아남는다. 멱등(N2 규칙 재사용)
        sql, post_fixed = ensure_fund_name_filter(sql, name_token)
        if post_fixed:
            step(f"[Guard] 이름 토큰 사후조건 — 체인 끝에 '{name_token}' 이 itm_nm LIKE 에 없어 다시 주입 (6R J′: 호수 가드가 이름+N호 결합 절을 제거)")
    sql, qualified = qualify_join_columns(sql, ctx)
    if qualified:
        step(f"[Guard] JOIN 모호 컬럼 한정 — {', '.join(qualified)} → FROM 테이블 한정 "
             "(2026-09-02 R2 재검: 재생성 SQL 이 펀드단위 규칙의 COALESCE(…, itm_no) 를 JOIN 에 그대로 옮겨 기각 → 거절)")
    sql, estb_post = ensure_fund_estb_year(sql, q)
    if estb_post:
        step("[Guard] 설정연도 확정식 사후조건 — 체인 끝에서 설정일 축의 잔여 술어를 다시 걷어냈다 "
             "(8R 부류 B · X19 실측: HCX 의 `fd_estb_dt <= 20250930` 이 초기 가드 때는 컬럼명이 달라 안 걸렸고 "
             "그 뒤 외부 JOIN 가드가 `estb_dt` 로 이름을 바꿔 놓아 10~12월이 잘렸다 — 82/224, gold 107/305)")
    sql, pop_post = ensure_fund_base_population(sql, q, post=True)
    if pop_post:
        step("[Guard] 펀드 기본모수 사후조건 — 재작성된 SQL 에 모수 절이 없어 체인 끝에서 주입(개별 조회는 '공모'만) "
             "(7R G1/F6′ · 6R KG-018 실측: HCX 원 SQL 에 정렬·집계가 없어 초기 가드를 건너뛴 뒤 목록 묶기가 "
             "ORDER BY·COUNT 를 붙여 96펀드가 판매완료 포함 모수로 나갔다 · W2 사모 3펀드 혼입)")
    # 🔴 11R 1순위 사후조건 — **확정식이 만든 조건은 체인 끝에 살아 있어야 한다.** 가드 A 의 출력을 가드 B 가
    #    날조로 보고 지우거나(OFFICIAL-004: 지수 조건이 사라진 전수 조회 30행 중 이름에 '우주항공' 이 든 1건을
    #    골라 답했다 — gold 48), 확정식이 지우고 대체를 못 넣으면(Z19: 판매중 ETF 전수 1,160) 질문의 의미 조건이
    #    증발한 채 그럴듯한 답이 나간다 — 무응답보다 나쁘다. 되돌려 0행 경로로 정직하게 보내고 트레이스에 남긴다.
    sql, union_notes = apply_union_branch_guards(sql, q)
    if union_notes:
        step(f"[Guard] 교차질의 가지별 확정식 — {' · '.join(union_notes)} "
             "(14R KG ③-1: 단일 상품군에서 닫힌 확정식 4종이 UNION 문장엔 하나도 안 붙었다 — "
             "가지를 떼면 각 가지는 단일 SELECT 이고 FROM 이 하나뿐이라 기존 가드가 그대로 성립한다)")
    sql, mgmt_note = ensure_mgmt_code_predicate(sql, q, mgmt)
    if mgmt_note:
        step(f"[Guard] 역조회 운용사 코드 술어 확정 — {mgmt_note} "
             "(14R 재검 ③-1 · S3 실측: '삼성' → 00040010 등호가 삼성액티브(00080135) 9클래스를 잘랐다. "
             "역조회는 코드 후보이지 필터가 아니다 — 술어로 쓸지·어떤 형태로 쓸지를 결정층이 못 박는다)")
    sql, org_codes_fixed = ensure_org_label_codes(sql, q)
    if org_codes_fixed:
        step("[Guard] 운용사 정본 이름 형제 코드 — 같은 label_official 을 갖는 or_co 코드를 IN 으로 묶었다 "
             "(14R KG ③-8 · Z16 실측: 키움투자자산운용은 00080052·00040013 둘인데 하나만 조회해 97/308 부족값 — gold 112/354)")
    sql, brand_fixed = ensure_etf_brand_token(sql, q)
    if brand_fixed:
        step("[Guard] ETF 브랜드 조건 사후조건 — 질문이 지목한 브랜드가 이름 술어에서 사라져 되돌려 주입 "
             "(14R gold ③-1 · UNANS-001 실측: 'KODEX AI 로봇' 이 `pd_nm LIKE '%AI%' AND '%로봇%'` 로 나가 "
             "KODEX 조건 없이 실재 ETF 3종을 나열 — 조건이 지워진 목록은 답이 아니다. 0행이면 유사 상품 되묻기가 받는다)")
    lost = [c for c in injected if c not in sql]
    if lost:
        sql, _ = _append_exclusions(sql, lost)
        step(f"[Guard] 확정식 조건 소실 사후조건 — 뒤 가드가 지운 확정식 {len(lost)}건을 되돌렸다: "
             f"{' · '.join(c[:70] for c in lost)} (11R 1순위: 조건이 증발한 전수 조회를 답으로 내지 않는다)")
    sql, topn_fixed = ensure_default_topn(sql, q)
    if topn_fixed:
        step(f"[Guard] 기본 TOP-N — 개수 없는 랭킹 질의의 LIMIT 을 {DEFAULT_TOPN} 으로 (2026-09-02 서버 실측: '한전 채권 수익률 낮은 순' 30행 전사 22.2초 — 리드 결정: 상위 5 + 전체 종목수 병기)")
    sql, limited = ensure_limit(sql)
    if limited:
        step(f"[Guard] LIMIT 누락 — 상한 {MAX_ROWS} 로 보정 (검사기가 LIMIT 을 요구한다 — 집계 1행에도 붙이며 결과엔 무해)")
    sql, undecl = drop_undeclared_table_or_branches(sql)
    if undecl:
        step(f"[Guard] 미선언 테이블 OR 가지 제거 — {' · '.join(undecl)} (16R gold ③-1 · OFFICIAL-004 실측: "
             "`ext_etf_holdings.ticker` OR 가지 2개 때문에 문장 전체가 기각되고 재생성이 완전히 같은 문장을 "
             "돌려줘 무응답이 됐다. OR 가지는 조건을 넓히는 자리라 걷어도 모수가 넓어지지 않는다)")
    sql, halluc = drop_hallucinated_column_conjuncts(sql)
    if halluc:
        step(f"[Guard] 환각 컬럼 술어 제거 — {' · '.join(halluc)} (16R KG ③-6 · gold ③-1: 스키마에 없는 컬럼을 쓴 "
             "최상위 절은, 그 절의 값 리터럴이 확정식으로 이미 걸려 있을 때만 걷는다. Z11 실측: "
             "`asset_class='중국주식' AND fund_type='공모'` 두 환각 컬럼이 기각 → 재생성 동일 SQL → 오거절을 냈다)")
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
    mgmt_fallback: list[str] = []
    mgmt_found: tuple | None = None      # 14R 재검 ③-1 — 역조회로 우리가 만든 코드일 때만 술어 확정 가드가 돈다
    if ground_lines:
        step("[Ground] KG 개체 매핑 — " + " / ".join(ground_lines))
    else:
        step("[Ground] KG 개체 매핑 — 매칭 없음" + (" (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)" if tables else ""))
        # 🔴 11R KG ③-13 (부류 M) — KG 매핑이 없는 운용사는 **코드를 지어내기 전에 역조회로 확정한다.**
        #    Z15·AA23·X12 는 HCX 가 `1001` → `80000000` → `60000000` → `10000000` 로 매번 새 코드를 날조하며
        #    재생성 예산을 3회 이상 태웠다(자연어 피드백이 이 계열에서 작동하지 않는다 → 기계 보정).
        #    역조회는 DB 실측 1회(`ext_fund_page.mgmt_co_nm` 어간 ⋈ `public_funds`)이고 이름 하드코딩 0이다.
        if tables == ["public_funds"]:
            found = mgmt_code_from_question(q)
            if found:
                stem, code, nm = found
                mgmt_found = found
                mgmt_fallback = [f"{nm} (Organization) → public_funds.or_co_xtn_itt_cd 의 값: '{code}' "
                                 f"— KG 미매핑이라 ext_fund_page.mgmt_co_nm 역조회로 확정한 코드다. "
                                 f"이 코드를 그대로 쓰고 다른 코드를 지어내지 않는다"]
                ground_lines = [f"'{stem}' → 운용사 {nm} → public_funds.or_co_xtn_itt_cd = '{code}'"]
                step(f"[Ground] 운용사 코드 역조회 — '{stem}' → {nm}({code}) "
                     "(11R KG ③-13: KG 미매핑 운용사에 HCX 가 매번 새 코드를 날조해 재생성 예산을 태웠다)")

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

    ask_risk = risk_ambiguity_clarify(q, tables)
    if ask_risk:
        # 결정층 되묻기 — '가장 위험한' 은 축이 셋(투자위험등급/신용등급/금리위험)이라 기본값 단정 금지 (리드 결정 2026-09-02). HCX 호출 없이 즉시.
        step("[Clarify] 되묻기(결정층) — '가장 위험한 채권' 은 clarify.다의어.위험 대상: 투자위험등급 1등급 / 신용등급 C0 / 금리위험(듀레이션) 세 축 "
             "(2026-09-02 서버 실측: 1등급+수익률 내림차순으로 단정해 신보 유동화 728% 5종목 답변) · 축 단서 낱말이 있으면 되묻지 않음")
        result.think_trace = "\n".join(trace)
        result.answer = ask_risk
        return result

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
    grounding = build_grounding(ctx, hits, tables, cross, q, future, name_token, mgmt_fallback)
    result.grounding = grounding
    blocks = " + ".join(_grounding_blocks(grounding)) or "없음"
    step(f"[Plan] 근거문서 조립 — 대상 {', '.join(tables) or '마스터 4테이블'} · "
         f"{len(grounding):,}자 · 구성: {blocks}")
    t0 = time.monotonic()
    raw_sql = planner.plan_sql(q, grounding)
    result.raw_sql = raw_sql          # 가드 적용 전 원문 — 섀도 재생용(로그 전용)

    if raw_sql.strip().upper().startswith(REFUSE_PREFIX):
        # R-5 ② — 플래너가 답변불가 규칙에 걸렸다고 선언. SQL 없이 종료 (실행·답변 생성 호출 없음)
        why = raw_sql.strip()[len(REFUSE_PREFIX):].strip()
        step(f"[Refuse] 답변불가 — 플래너 판정 (근거: 답변불가 규칙 블록) · 사유: {why}")
        # 🔴 14R gold ③-17·③-18 — **Refuse 경로도 금지 문형 가드를 탄다.** OFFICIAL-002 실측:
        #    거절 사유에 "금융기관의 공식 웹사이트나 관련 보고서를 통해 확인하실 수 있습니다" 가 그대로 나갔다.
        #    금지 문형 제거는 경로와 무관하게 답변 반환 직전 한 자리에서 건다.
        why, refuse_stripped = strip_disclaimer(why)
        if refuse_stripped:
            step("[Guard] 면책 문구 제거(Refuse 경로) — 거절문도 같은 문형 가드를 탄다 (14R gold ③-17)")
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
            grounding = build_grounding(ctx, hits, tables, cross, q, future, name_token, mgmt_fallback)
    sql, trim_fixed = ensure_trimmed_compare(sql)
    if trim_fixed:
        step("[Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교와 **집계·정렬 키**를 TRIM 으로 교체 "
             "(무TRIM IN 은 16행 vs TRIM 2,031행 · 2026-09-04 #63: 무TRIM GROUP BY pd_pbcm 이 한국산업은행 503→500 으로 갈라 2·3위가 뒤바뀌었다)")
    sql, pinned = pin_sql_now(sql)
    if pinned:
        step(f"[Guard] SQL 의 '지금' 고정 — 'now'·CURRENT_DATE 를 질문 시점 {gate.BUYABLE_CUTOFF} 로 치환 (서버 실제 시각은 심사일이다 — 2026-09-03 #51 재점검)")
    windows = gate.resolve_relative_window(q) if "domestic_bonds" in sql else []
    sql, win_note = enforce_relative_window(sql, q, windows)
    if win_note:
        step(f"[Guard] 상대 시점 창 확정 — {win_note} (2026-09-03 서버 실측 #51: HCX 가 '내년' 을 20280824~20290824 로 오계산 · "
             "remaining_days 는 8/21 기준이라 창에 쓰지 않는다)")
    elif len({(lo, hi) for _, lo, hi in windows}) > 1:
        step(f"[Guard] 상대 시점 낱말이 서로 다른 창을 가리켜 불개입 — {' · '.join(f'{l}={lo}~{hi}' for l, lo, hi in windows)}")
    if future:
        sql, yr_fixed = align_maturity_year(sql, future)
        if yr_fixed:
            step(f"[Guard] 만기 연도 교정 — 질문의 연도({', '.join(future)})와 SQL 만기 상한의 연도가 달라 상한을 질문 연도로 교정 (2026-08-31 '28년 12월'→20291231 오기 실측)")

    if future and not gate.sql_uses_as_maturity(sql, future):
        # ③ cutoff 사후 검사 — 연도가 mat_dt 조건에 안 쓰였으면 시점·전망 질의다 (gate §③)
        # 🔴 날짜 치환·연도 교정 **뒤에** 검사한다 — 교정 전 SQL 로 검사하면 두 자리 연도('28년') 질의가
        #    "SQL 에 2028 이 없다" 며 억울하게 기각된다 (검사 대상과 실행 대상이 같은 SQL 이어야 한다)
        # 🔴 2026-09-03 #51 — "질문 연도가 SQL 에 없다" 와 "SQL 에 만기 조건이 없다" 는 다른 일이다. mat_dt 날짜 조건이 있으면
        #    만기 질의다(창이 틀렸다면 위 가드가 고쳤고, 그래도 다르면 실행하고 머리줄에 실제 창을 굽는다). 기각은 조건이 없을 때만.
        if has_maturity_predicate(sql):
            step(f"[Guard] 질문 시점 {future} 이(가) SQL 의 만기 창과 다르지만 mat_dt 날짜 조건이 있어 만기 질의로 본다 — 실행하고 실제 창을 답변에 표기")
        else:
            step(f"[Guard] 기준일 이후 시점 {future} 이(가) SQL 의 mat_dt 조건에 쓰이지 않음 → 만기 질의가 아닌 시점·전망 질의로 판정")
            result.sql = sql
            step("[Decision] HCX SQL 은 만들었으나 기준일 이후 근거가 DB 에 없어 종료")
            result.think_trace = "\n".join(trace)
            result.answer = f"제공된 데이터의 기준일은 {gate.DATA_CUTOFF}입니다. 이후 시점의 정보는 확인할 수 없습니다."
            return result

    sql = _apply_sql_guards(sql, q, name_token, future, step, ctx, tables, mgmt_found,
                            fired_out=result.enforce_fired)
    result.sql = sql
    # 🔴 SQL 은 자르지 않는다. 잘린 SQL 로는 조건식이 틀렸는지 KG 매핑이 틀렸는지 구분할 수 없고,
    #    그 구분이 곧 팀이 챗봇을 검토하는 방법이다 (2026-08-30). 채점자에게도 근거가 된다.
    step("[Plan] SQL 생성 — 아래 문장을 실행합니다\n" + sql)

    err = _sql_precheck(sql, ctx, tables, cross)
    violations = [] if err else guard.check_values(sql, ctx)
    axis_note = missing_axis_note(sql)      # 14R gold ③-12 — 축을 바꿔 답하면 그 사실을 머리줄에 적는다
    regen_used = False

    def _regen(problem: str):
        """재생성 1회 — 문제를 근거문서에 붙여 다시 요청하고 같은 가드 체인·precheck 를 태운다.
        (sql, err, violations) 또는 REFUSE 면 그 사유 문자열. 예산(누적 12초) 밖·이미 썼으면 None. 기각·값 위반·실행 오류가 공유(중복 0)."""
        nonlocal regen_used
        elapsed = time.monotonic() - t0
        if regen_used or elapsed >= REGEN_BUDGET_S:
            return None
        regen_used = True
        feedback = (grounding + "\n\n# 이전 SQL 의 문제 — 아래를 고쳐 다시 SQL 한 문장만 낸다\n"
                    f"- 이전 SQL: {sql}\n- 문제: {problem}\n"
                    "- 값은 'KG 개체 매핑'·'범주형 컬럼의 실제 값' 목록의 표기 그대로만 쓴다. 없는 값이면 그 조건을 빼지 말고 REFUSE: 로 답한다.\n"
                    # 🔴 14R gold ③-5 — OFFICIAL-005 실측: 재생성이 SELECT 열을 줄이고 `ORDER BY 6` 을 그대로 둬 실행 오류.
                    "- ORDER BY 는 **위치 번호가 아니라 컬럼명·별칭**으로 쓴다(열 수가 바뀌어도 안 깨진다).")
        step(f"[Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 {elapsed:.1f}s)")
        raw2 = planner.plan_sql(q, feedback)
        result.raw_sql = raw2         # 재생성이 돌면 그 원문이 마지막 플래너 산출이다
        if raw2.strip().upper().startswith(REFUSE_PREFIX):
            return raw2.strip()[len(REFUSE_PREFIX):].strip()
        # 🔴 재생성 SQL 도 같은 가드 체인을 태운다 — 안 태우면 재생성이 조건식을 정확히 고쳐도
        #    근거컬럼·대표행 보정이 빠져 답변이 무너진다 (FND-R09 실측: 27행 조회 후 "찾을 수 없음")
        sql2, _ = normalize_date_literals(raw2)
        sql2 = _apply_sql_guards(sql2, q, name_token, future, step, ctx, tables, mgmt_found,
                                 fired_out=result.enforce_fired)
        result.sql = sql2
        step("[Plan] 재생성 SQL — 아래 문장을 실행합니다\n" + sql2)
        err2 = _sql_precheck(sql2, ctx, tables, cross)
        return sql2, err2, ([] if err2 else guard.check_values(sql2, ctx))

    if err or violations:
        # R-4 — 재생성 1회: SQL 기각 또는 WHERE 값이 DB 에 없을 때만. 예산(누적 12초) 안일 때만. 0행은 여기 오지 않는다.
        problem = err or "; ".join(str(v) for v in violations)
        step(f"[Guard] {'SQL 기각' if err else '값 검사 실패'} — {problem}")
        rg = _regen(problem)
        if isinstance(rg, str):
            step(f"[Refuse] 재생성에서 답변불가 선언 · 사유: {rg}")
            result.think_trace = "\n".join(trace)
            result.answer = (f"요청하신 조건의 값이 데이터에 없어 확인할 수 없습니다. {rg}"
                             + _issuer_clarify_text(_violated_issuer(violations)))
            return result
        if rg is not None:
            sql, err, violations = rg
        if err or violations:
            step(f"[Guard] 재생성 후에도 실패 — {err or '; '.join(str(v) for v in violations)}")
            step("[Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)")
            result.think_trace = "\n".join(trace)
            result.answer = ("요청하신 조건의 값이 데이터에 없어 확인할 수 없습니다." + _issuer_clarify_text(_violated_issuer(violations))
                             if violations else refusal_reason_text(err))
            return result
    step("[Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)")

    try:
        rows, n = _execute(sql)
    except sqlite3.Error as e:
        # 6R P (5R V5) — 실행 오류도 재생성 1회 경로를 탄다 (예산·횟수는 기각·값 위반과 공유). 재생성 SQL 은 같은 가드·precheck 후 실행.
        step(f"[Execute] 실행 실패 — {type(e).__name__}: {e}")
        rg = _regen(f"실행 오류 {type(e).__name__}: {e}")
        ok = False
        if isinstance(rg, str):
            step(f"[Refuse] 재생성에서 답변불가 선언 · 사유: {rg}")
        elif rg is not None:
            sql, err, violations = rg
            if err or violations:
                step(f"[Guard] 재생성 후에도 실패 — {err or '; '.join(str(v) for v in violations)}")
            else:
                try:
                    rows, n = _execute(sql)
                    ok = True
                except sqlite3.Error as e2:
                    step(f"[Execute] 재생성 SQL 도 실행 실패 — {type(e2).__name__}: {e2}")
        if not ok:
            result.think_trace = "\n".join(trace)
            result.answer = "데이터 조회 중 오류가 발생해 확인할 수 없습니다."
            return result
    step(f"[Execute] {n}행 조회 (상한 {MAX_ROWS})")
    if n == 0:
        # 6R O — 질문에 없는 숫자로 만든 수치 비교 절이 단독 0행이면 그 절만 떼고 **1회** 재실행 (5R S2 `fd_yr3_ern_r < -100`)
        sql_o, dropped = drop_unquestioned_numeric_clause(sql, q)
        if dropped:
            try:
                rows_o, n_o = _execute(sql_o)
            except sqlite3.Error:
                rows_o, n_o = rows, 0
            step(f"[Guard] 0행 — 질문에 없는 숫자의 수치 절 폐기 후 1회 재실행: '{dropped}' → {n_o}행 (플래너 임계값 환각은 사용자 조건이 아니다)")
            if n_o:
                sql, rows, n = sql_o, rows_o, n_o
                result.sql = sql
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
        else:
            # 발행사 등호 0행 — 같은 어두의 실제 발행사를 되묻는다 (2026-09-02 실측: 삼성전자 → 삼성카드 323·삼성증권 16…)
            issuer_text = _issuer_clarify_text(_issuer_literal(sql))
            if issuer_text:
                answer = "요청하신 발행사의 채권은 제공된 데이터에 없습니다." + issuer_text
                cand = ["issuer"]           # 아래 0행 진단을 겹쳐 붙이지 않는다 — 되묻기가 사유를 대신한다
                step("[Suggest] 발행사 등호 0건 — 같은 어두의 실제 발행사 되묻기 (clarify.존재하지_않는_개체)")
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
            # 6R F4 — 펀드는 리터럴 검증으로 세 갈래(교집합 0 / 기본모수 밖 / 식별 실패)를 가른다. '없다/실재' 단정은 검증된 리터럴에만
            reason = _zero_row_reason(sql) if _FUND_TBL.search(sql) else diag.user_text()
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
    cnt = _count_answer(sql, rows, n, ground_lines, q)
    if cnt is not None:
        step("[Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 "
             "(2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)")
        result.think_trace = "\n".join(trace)
        result.answer = cnt
        return result
    bcnt = _bond_count_answer(sql, rows, n, q)
    if bcnt is not None:
        step("[Answer] 채권 종목 수 답변 기계 조립 — 단일 COUNT 1행은 HCX 없이 옮기고, 질문이 국고채를 포함 언급하면 "
             "국고채 확정식 COUNT 를 결정층이 한 번 더 실행해 병기 (2026-09-03 서버 실측 #52: HCX 가 질문 문언을 옮겨 "
             "'국고채를 포함한 국공채는 295종목' — 국공채 = 국고채 로 읽히는 사실 왜곡)")
        result.think_trace = "\n".join(trace)
        result.answer = bcnt
        return result
    zero = _zero_count_answer(sql, rows, n)
    if zero is not None:
        step("[Answer] 0 집계 답변 기계 조립 — 단일 COUNT/SUM 결과 0 은 HCX 없이 '확인되지 않음' 으로 옮긴다 "
             "(2026-09-02 실측: '삼성전자가 발행한 채권 있어?' COUNT=0 1행이 0행 조기반환을 비켜 HCX 작문으로 나감)")
        result.think_trace = "\n".join(trace)
        result.answer = zero
        return result
    mgr = _manager_rank_answer(sql, rows, n)
    if mgr is not None:
        step("[Answer] 운용사 집계 답변 기계 조립 — 템플릿 5열은 HCX 없이 옮긴다 "
             "(2026-09-02 R2·S11 재검: 면책·유보 문장 계열도 함께 소멸)")
        result.think_trace = "\n".join(trace)
        result.answer = mgr
        return result
    ent = _entity_count_rank_answer(sql, rows, n)
    if ent is not None:
        step("[Answer] 개체 개수 랭킹 답변 기계 조립 — SQL 행 순서를 그대로 옮긴다, HCX 0회 "
             "(16R KG ③-4 · KG-008 실측: SQL 이 gold 순서(714·516·465)를 돌려주는데 답변기가 수탁금액 순으로 "
             "재정렬하고 숫자는 클래스수를 옮겼다. 14R 은 이 조립기를 정의만 하고 호출부에 배선하지 않았다)")
        result.think_trace = "\n".join(trace)
        result.answer = ent
        return result
    lk = _lookup_answer(sql, rows, n, name_token, ground_lines)
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
    rk = _fund_rank_answer(sql, rows, n)
    if rk is not None:
        step("[Answer] 랭킹 답변 기계 조립 — SELECT 에 실린 클래스수를 반드시 옮기고 값 축(MAX/SUM)을 머리줄에 굽는다, HCX 0회 "
             "(8R ③-10 · 7R 실측: R7·S1·Y3·Y4 는 클래스수 미표기 + 머리 이름이 클래스명 · Y2·U13 은 MAX 축 미고지 · "
             "Y3 꼬리에 기준일 8/21 날조 + '모든 클래스를 합하여' 방법론 날조 — 기계 조립은 HCX 를 안 부르므로 꼬리가 구조적으로 사라진다)")
        result.think_trace = "\n".join(trace)
        result.answer = rk
        return result
    bl = _bond_list_answer(sql, rows, n, q)
    if bl is not None:
        step("[Answer] 채권 목록 답변 기계 조립 — 결과 행 전부 + 커버리지·정렬축 머리줄 + 조건부 주의 문구, HCX 0회 "
             "(2026-09-02 재배포 후 실측: '수익률 높은 채권 추천해줘' 답변기가 종목명 0건 전사 + 규칙 문구의 6.23% 를 결과처럼 인용)")
        result.think_trace = "\n".join(trace)
        result.answer = bl
        return result

    answer_rules = ctx.answer_context(tables or list(TABLES))
    # 🔴 행 개수를 데이터에 구워 넣는다 — 2026-09-01 FND-033 실측: 답변기가 11행을 나열해 놓고
    #    "총 10개" 라고 셌다. 순자산 자릿수 훼손과 같은 계열 — 모델에게 산술(개수 세기)을 시키지
    #    말고 복사만 하게 한다. retrieved_context(조회 원문)는 건드리지 않고 답변 입력에만 붙인다.
    # 🔴 8R 부류 D — **표기가 먼저, 숨김이 나중.** 표기 가드는 원본 SQL 의 SELECT 항목과 결과 헤더가 1:1 일 때만
    #    성립하므로(별칭이 아니라 원 컬럼 표현식으로 판정한다) 체인의 맨 앞이 유일하게 안전한 자리다. 7R KG-008 실측:
    #    숨김이 `수탁금액` 열을 먼저 지워 4항목 vs 3열이 되자 표기 가드가 arity 검사에서 **무음 종료**했고, HCX 가
    #    `trim(trusc_xtn_itt_cd) AS 수탁회사명` 별칭에 속아 운용사 이름 3개를 날조했다(같은 상호배제에 Z21·AA15).
    #    숨김은 **헤더명**으로 판정하므로 표기가 값을 바꿔도 영향이 없다 — 순서를 뒤집어도 종전 동작이다.
    label_skip: list = []
    answer_rows, labeled = label_code_columns(rows, sql, label_skip)
    if labeled:
        step(f"[Answer] 기관 코드·이름 확정 표기 — {', '.join(labeled)} 를 정본 이름(kg_node.label_official→label_ko→canonical_name) "
             "또는 '코드 X(기관명 미수록)' 로 "
             "(KG 4R G4 · KG-008 실측: `trim(trusc_xtn_itt_cd) AS 수탁회사명` 별칭에 속아 운용사 이름 3개 날조 · Z23 은 값이 있는데 '미수록' 서술 · "
             "16R 재검 ③-2 · V7·W10 실측: 영문 법인명을 HCX 가 즉석 번역해 같은 축에서 '미래에셋 글로벌 자산운용' / '미래에셋 글로벌 인베스트먼트' 로 갈렸다)")
    elif label_skip:
        step(f"[Guard] 기관 코드 확정 표기 적용 불가 — {label_skip[0]} (8R 부류 D: 가드가 전제 때문에 스킵되면 트레이스에 남긴다)")
    answer_rows, hidden = _hide_answer_columns(answer_rows, sql)
    if hidden:
        step(f"[Answer] 내부 코드 컬럼 숨김 — {', '.join(hidden)} (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)")
    header = f"(조회 결과: 총 {n}행)"
    bond_cov = _bond_coverage_counts(sql) if (n >= MAX_ROWS or _explicit_limit_hit(sql, n)) else None
    if bond_cov and bond_cov[1] > n:
        # 채권 상위 k 목록 — 종목 총량을 굽는다 (2026-09-02 실측: '한전 수익률 높은 순' LIMIT 5 에 "386종목 중 상위 5" 재료 부재)
        total_rows, total_pdno = bond_cov
        header = (f"(조회 결과: 전체 {total_pdno:,}종목 중 상위 {n}종목 표시 — 나머지는 표시되지 않았으므로 "
                  f"전체를 나열한 것처럼 말하지 않는다. 답 첫 줄에 '전체 {total_pdno:,}종목 중 상위 {n}개' 를 밝힌다)")
        step(f"[Answer] 커버리지 병기 — 채권 상위 {n} 목록, 전체 {total_pdno:,}종목({total_rows:,}행)을 답변 입력에 굽는다")
    elif n >= MAX_ROWS:
        # 🔴 LIMIT 에 잘린 목록은 전체 규모를 굽는다 — 2026-09-02 R3 재검: 30행 중 5행만 옮기고 "다음과 같습니다" 전칭,
        #    총량(560행/248펀드) 미고지. SQLite 재실행 1회·HCX 0회 — 모델이 세지 않게 문자열로 준다.
        cov = _coverage_counts(sql)
        if cov and (cov[1] if cov[3] else cov[0]) > n:
            total, funds, _rptt, grouped = cov
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
    result.answer, etf_scope = ensure_etf_scope_note(result.answer, sql)
    if etf_scope:
        step("[Answer] ETF 모수 한정 고지 — 어느 테이블을 봤는지 머리줄에 기계 표기 "
             "(10R 재검 ③-11 · V7·W10 은 6R 에 있던 '국내' 가 7R·9R 엔 없다 — 라운드마다 뒤집히므로 고정한다)")
    result.answer, pct_dropped = strip_unsourced_percent(result.answer, rows)
    if pct_dropped:
        step(f"[Guard] 근거 밖 백분율 제거 — 조회 결과에 없는 값 {', '.join(pct_dropped[:3])}% 를 담은 문장을 걷어냄 "
             "(16R KG ③-16 · X1 실측: 24.95·15.9·7.96 을 받아 '세 종목 합계 약 48.81%' 를 스스로 계산해 붙였다 — "
             "13R 에 소멸했다 재발했으므로 규칙 텍스트가 아니라 반환 직전 후처리로 못 박는다)")
    result.answer, estb_stripped = strip_unsourced_estb_claim(result.answer, rows)
    if estb_stripped:
        step("[Guard] 미조회 축 문장 제거 — 조회 결과에 날짜 컬럼이 없는데 설정일·운용 기간을 단정한 문장을 걷어냄 "
             "(10R KG 부류 E 부수 · AA5 실측: SELECT 에 estb_dt 가 없는데 '설정일 2011-06-20 · 약 12년' — "
             "2011→2026 은 15년이라 자기 산술과도 모순)")
    name_skip: list = []
    result.answer, name_fixes = verify_product_names(result.answer, rows, name_skip)
    if name_fixes:
        step(f"[Guard] 상품명 전사 교정 — {' · '.join(name_fixes[:3])} (조회 원문 밖 이름 {len(name_fixes)}건 — "
             "2026-09-02 R3 재검: '삼성중국본토중소형FOSS' 는 DB 에 0행, 실제 FOCUS)")
    elif name_skip:
        step(f"[Guard] 상품명 전사 교정 적용 불가 — {name_skip[0]} (8R 부류 C · X18 실측)")
    # 3R ④-2 — 팀원 가드는 채권 문형(pd_no 순위 복원·단일 집계 오거절)이다. 펀드는 조립기가 받으므로 채권 SQL 에만(동작 불변, 범위만)
    result.answer, topcited_fixed = ensure_top_row_cited(result.answer, sql, rows) if "domestic_bonds" in sql else (result.answer, False)
    if topcited_fixed:
        step("[Guard] 목록 상위 행 복원 — 답변이 정렬 결과의 하위 행을 인용하며 상위 행을 건너뛰어 누락 행을 덧붙임 "
             "(2026-09-02 서버 실측: '1년만 굴릴 건데' 답변에서 6등급 정렬 1·3위 증발 — 값이 전부 실제 행이라 환각 검사 밖)")
    # KG 4R G5 — 조회 결과가 비어 있지 않은데 '없음/확인 불가' 로 서술하면 기각한다. 종전엔 채권 SQL 에만 걸려 있었으나
    #    X17 실측(`COUNT(*)` = 7 인데 "클래스 개수는 확인할 수 없습니다")로 4도메인 공통 규칙임이 드러났다.
    result.answer, cntfix = ensure_positive_count_answered(result.answer, sql, rows, n, q)
    if cntfix:
        step("[Guard] 집계 오거절 교정 — 양수 COUNT 결과를 '정보 없음' 으로 오독한 답변을 기계 조립으로 교체 "
             "(2026-09-02 서버 실측: '퇴직연금으로 살 수 있는 채권 있어?' 에 COUNT 1,929 반환에도 오거절 · "
             "KG 4R X17: 펀드 COUNT 7 에 '확인할 수 없습니다')")
    result.answer, rows_forced = ensure_rows_answered(result.answer, rows, n)
    if rows_forced:
        step("[Answer] 결과 전사 강제 — 1행 이상을 받고도 결과를 하나도 인용하지 않고 거절한 답변을 기계 전사로 교체 "
             "(10R gold N7 · OFFICIAL-005 실측: 1행을 받고도 '정보가 없습니다')")
    if axis_note and axis_note not in result.answer:
        result.answer = axis_note + "\n\n" + result.answer
        step("[Answer] 축 교체 고지 — 질문이 지목한 축이 전건 결측이라 다른 축으로 답한 사실을 머리줄에 기계로 적었다 "
             "(14R gold ③-12 · FND-R02 실측: fd_wk1_ern_r 23,676/23,676 결측인데 말없이 1개월로 갈아탔다)")
    step("[Answer] 답변 생성 완료" + (f" — 답변 규칙 {len(answer_rules):,}자 적용 ({', '.join(tables) or '전체'})" if answer_rules else ""))
    result.think_trace = "\n".join(trace)
    return result
