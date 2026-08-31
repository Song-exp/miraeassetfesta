"""SQL 사후 가드 — LLM 호출 0회로 하는 두 가지 검사 (2026-08-30 개선 R-4).

① check_values   — WHERE 의 리터럴이 그 컬럼의 **실제 값**인가. 실패의 절반이 필터 값 오류라는 근거(EntSQL Fig. 4)에서
                    왔다. 검사 대상 컬럼은 loader 가 만든 value_index(전 값을 아는 컬럼)뿐이다 — 값 사전이 부분적인
                    컬럼(이름·자유 텍스트)은 검사하지 않는다. LIKE 는 부분일치 규칙이 허용한 경로라 건너뛴다.
② diagnose_zero  — 0행이면 WHERE 의 최상위 AND 조건을 하나씩 떼어 각각 몇 건인지 센다. "확인되지 않습니다" 에
                    근거를 붙이기 위해서다 (SDE-SQL §3.3.1 의 규칙 분해기 — LLM 아님). 🔴 조건을 **완화해 다시 답하지
                    않는다** — 거절이 정답인 문항에서 환각 경로가 된다 (PROJECT.md §9).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from .loader import EXT_TABLES, TABLES, RuntimeContext, connect_readonly

# col = 'lit'  ·  tbl.col = 'lit'  ·  col IN ('a','b')  — 문자열 리터럴만 (숫자 비교는 값 사전 대상이 아니다)
_EQ = re.compile(r"(?:\b([A-Za-z_]\w*)\.)?\b([A-Za-z_]\w*)\s*=\s*'((?:[^']|'')*)'", re.I)
_IN = re.compile(r"(?:\b([A-Za-z_]\w*)\.)?\b([A-Za-z_]\w*)\s+IN\s*\(([^)]*)\)", re.I)
_LIT = re.compile(r"'((?:[^']|'')*)'")
_FROM = re.compile(r"\b(?:from|join)\s+([A-Za-z_]\w*)", re.I)
_MAX_HINT = 4


def _norm(v: str) -> str:
    return v.replace("''", "'").strip().casefold()


@dataclass
class ValueViolation:
    table: str
    column: str
    literal: str
    hint: list[str]
    owner: str = ""      # 이 값이 실제로 속한 다른 컬럼 (있으면) — 2026-08-31 밤 FND-026

    def __str__(self) -> str:
        ex = " · ".join(h[:40] for h in self.hint[:_MAX_HINT])
        msg = f"{self.table}.{self.column} = '{self.literal}' 은(는) DB 에 없는 값"
        if self.owner:
            # 🔴 컬럼을 잘못 고른 것이지 값이 없는 게 아니다 — 이 구분이 없으면 재생성이 같은 실수를 반복하고
            #    파이프라인이 답변 가능한 질의를 거절한다 (FND-026 실측: '해외주식형' 은 zrin_btyp_nm 의 값인데
            #    or_attr_desc 에 써서 기각 → 재생성도 같은 값 유지 → 중국 펀드 560행이 있는데 '확인 불가' 응답).
            return msg + f" — 이 값은 같은 테이블의 **{self.owner}** 컬럼 값이다. 컬럼을 {self.owner} 로 바꾸거나 그 조건을 다른 축으로 다시 세워라"
        return msg + (f" (실제 값 예: {ex})" if ex else "")


def sql_tables(sql: str) -> list[str]:
    return [t.lower() for t in _FROM.findall(sql) if t.lower() in TABLES or t.lower() in EXT_TABLES]


# ── ①-b 컬럼 실존 검사 (2026-08-31 — paired v2 실측: 실행 실패 8/80 이 remaining_days·after_tax_yield·
#     cu_last_aum 등 컬럼 환각. 스키마 서두("여기 없는 컬럼은 존재하지 않는다")를 플래너가 무시한다) ──
_SQL_STR = re.compile(r"'(?:[^']|'')*'")
_AS_ALIAS = re.compile(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
_SNAKE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
# 밑줄 든 SQLite 내장 함수 — 컬럼이 아니다
_SQL_FUNCS = {"group_concat", "json_extract", "json_each", "last_insert_rowid", "row_number", "char_length"}


def unknown_columns(sql: str, ctx: RuntimeContext) -> list[str]:
    """SQL 에 등장한 테이블들의 스키마에 없는 snake_case 식별자를 찾는다 — 실행하면 어차피
    OperationalError 로 죽으니 실행 전에 잡아 재생성 1회 기회를 준다.
    🔴 전역 컬럼 집합이 아니라 **그 SQL 의 테이블로 한정**한다 — 실측 환각이 교차 혼동이다
    (domestic_etfs 에 채권 컬럼 pd_risk_gcd · 해외 du_last_aum 을 cu_last_aum 으로 오기).
    문자열 리터럴·AS 별칭·테이블명·내장함수는 제외. schema_exclude 로 숨긴 컬럼(fd_wk1_ern_r 등)도
    걸린다 — 정책상 참조 금지이므로 의도된 동작."""
    body = _SQL_STR.sub("''", sql)
    used = sql_tables(body)
    if not used:
        return []
    schema = getattr(ctx, "schema", {}) or {}
    known = {c.lower() for t in used for c, _, _ in (schema.get(t) or [])}
    if not known:
        return []
    aliases = {a.lower() for a in _AS_ALIAS.findall(body)}
    known |= set(TABLES) | set(EXT_TABLES) | _SQL_FUNCS | aliases
    out, seen = [], set()
    for tok in _SNAKE.findall(body):
        t = tok.lower()
        if t in known or t in seen:
            continue
        seen.add(t)
        out.append(tok)
    return out


def _owner_column(index: dict, table: str, column: str, literal: str) -> str:
    """이 리터럴이 같은 테이블의 **다른** 컬럼 값이면 그 컬럼명 — 아니면 빈 문자열.

    2026-08-31 밤 FND-026 실측 처방: 값 위반의 태반이 '없는 값' 이 아니라 **컬럼 오선택**이다
    ('해외주식형' 은 zrin_btyp_nm 의 값인데 or_attr_desc 에 썼다). 사유에 이걸 적어야 재생성이
    같은 값을 되풀이하지 않는다 — 실측에서는 재생성도 실패해 답변 가능한 질의가 거절로 나갔다."""
    n = _norm(literal)
    for key, vals in index.items():
        if len(key) != 2 or key[0] != table or key[1] == column:
            continue
        if n in vals:
            return key[1]
    return ""


_QUALIFIED = re.compile(r"[A-Za-z_]\w*\s*\.\s*([A-Za-z_]\w*)")


def ambiguous_columns(sql: str, ctx: RuntimeContext) -> list[str]:
    """JOIN 질의에서 **한정되지 않은** 채 여러 테이블에 존재하는 컬럼 — 실행하면 ambiguous 오류다.

    2026-08-31 밤 실측(설정일 질의): public_funds JOIN ext_fund_page 에서 SELECT itm_no 가
    양쪽에 있어 "ambiguous column name: itm_no" 로 죽었다. 실행 오류는 재생성 경로가 없어
    그대로 "조회 중 오류" 응답이 나간다 — 실행 전에 잡아 재생성 1회를 준다.
    """
    body = _SQL_STR.sub("''", sql)
    used = sql_tables(body)
    if len(used) < 2:
        return []
    schema = getattr(ctx, "schema", {}) or {}
    owners: dict[str, set] = {}
    for t in used:
        for c, *_ in (schema.get(t) or ()):
            owners.setdefault(c.lower(), set()).add(t)
    shared = {c for c, ts in owners.items() if len(ts) > 1}
    if not shared:
        return []
    aliases = {a.lower() for a in _AS_ALIAS.findall(body)}
    out = []
    for c in sorted(shared):
        if c in aliases:
            continue
        # 🔴 이름이 아니라 **등장 위치**로 판정한다 — `public_funds.itm_no` 가 한 번 있다고 해서
        #    SELECT 의 맨 itm_no 가 한정된 것은 아니다(앞의 점 없는 등장이 곧 모호 컬럼이다).
        if re.search(rf"(?<![\w.]){c}\b", body, re.I):
            out.append(c)
    return out


def check_values(sql: str, ctx: RuntimeContext) -> list[ValueViolation]:
    """값 사전이 완전한 컬럼에 한해, WHERE 리터럴이 실제 값인지 검사한다."""
    index = getattr(ctx, "value_index", None) or {}
    if not index:
        return []
    tables = sql_tables(sql)
    out: list[ValueViolation] = []
    pairs: list[tuple[str | None, str, str]] = []
    for tbl, col, lit in _EQ.findall(sql):
        pairs.append((tbl or None, col, lit))
    for tbl, col, body in _IN.findall(sql):
        for lit in _LIT.findall(body):
            pairs.append((tbl or None, col, lit))
    for tbl, col, lit in pairs:
        col_l = col.lower()
        candidates = [tbl.lower()] if tbl else [t for t in tables if (t, col_l) in index]
        for t in candidates:
            vals = index.get((t, col_l))
            if vals is None:
                continue
            if _norm(lit) in vals:
                break
            hint = sorted(v for v in index.get(("_raw", t, col_l), ()) )[:_MAX_HINT]
            out.append(ValueViolation(t, col_l, lit, hint, _owner_column(index, t, col_l, lit)))
            break
    return out


# ── ② 0행 진단 ──────────────────────────────────────────────────────────

_SIMPLE = re.compile(r"^\s*select\b(?P<sel>.+?)\bfrom\b(?P<from>.+?)(?:\bwhere\b(?P<where>.+?))?(?:\b(?:group\s+by|order\s+by|limit)\b.*)?$", re.I | re.S)
_COMPLEX = re.compile(r"\(\s*select\b|\bunion\b|\bhaving\b|\bwith\b", re.I)


def split_conjuncts(where: str) -> list[str]:
    """최상위 AND 로만 가른다 — 괄호·따옴표 안의 AND 는 건드리지 않는다. OR 가 최상위에 있으면 통째로 한 조건."""
    parts, depth, buf, i, s = [], 0, [], 0, where
    in_q = False
    while i < len(s):
        ch = s[i]
        if ch == "'":
            in_q = not in_q
        elif not in_q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0 and s[i:i + 5].upper() == " AND " :
                parts.append("".join(buf).strip()); buf = []; i += 5; continue
        buf.append(ch); i += 1
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


@dataclass
class ZeroRowDiagnosis:
    counts: list[tuple[str, int]]          # (조건, 단독 적용 시 건수)
    total: int                             # 조건 없이 (FROM 만) 건수

    def text(self) -> str:
        if not self.counts:
            return ""
        alive = [(c, n) for c, n in self.counts if n > 0]
        dead = [(c, n) for c, n in self.counts if n == 0]
        bits = [f"{c} → {n:,}건" for c, n in self.counts]
        head = "조건별 단독 조회: " + " / ".join(bits)
        if dead:
            return head + f". 값 자체가 없는 조건: {', '.join(c for c, _ in dead)}."
        if len(alive) >= 2:
            return head + ". 각 조건은 존재하나 동시에 만족하는 상품이 없습니다."
        return head


def diagnose_zero_rows(sql: str, con: sqlite3.Connection | None = None) -> ZeroRowDiagnosis | None:
    """단순 SELECT(서브쿼리·UNION·HAVING 없음)만. 조건이 하나면 진단할 게 없다(None)."""
    if _COMPLEX.search(sql):
        return None
    m = _SIMPLE.match(sql.strip().rstrip(";"))
    if not m or not m.group("where"):
        return None
    conj = split_conjuncts(m.group("where").strip())
    if len(conj) < 2:
        return None
    frm = m.group("from").strip()
    own = con is None
    con = con or connect_readonly()
    try:
        total = con.execute(f"SELECT count(*) FROM {frm}").fetchone()[0]
        counts = []
        for c in conj:
            try:
                n = con.execute(f"SELECT count(*) FROM {frm} WHERE {c}").fetchone()[0]
            except sqlite3.Error:
                n = -1
            counts.append((c, n))
        return ZeroRowDiagnosis([(c, n) for c, n in counts if n >= 0], total)
    finally:
        if own:
            con.close()
