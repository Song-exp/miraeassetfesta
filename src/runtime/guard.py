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

    def __str__(self) -> str:
        ex = " · ".join(h[:40] for h in self.hint[:_MAX_HINT])
        return f"{self.table}.{self.column} = '{self.literal}' 은(는) DB 에 없는 값" + (f" (실제 값 예: {ex})" if ex else "")


def sql_tables(sql: str) -> list[str]:
    return [t.lower() for t in _FROM.findall(sql) if t.lower() in TABLES or t.lower() in EXT_TABLES]


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
            out.append(ValueViolation(t, col_l, lit, hint))
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
