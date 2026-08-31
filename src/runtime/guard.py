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


_SUFFIX_NOISE = ("형", "型", "펀드", " ")


def nearest_enum_value(index: dict, table: str, column: str, literal: str) -> str | None:
    """리터럴과 **접미사·공백만 다른** 실제 값이 유일하면 그 값 — 아니면 None.

    2026-08-31 밤 FND-024 실측: 플래너가 '재간접형' 을 썼는데 실제 값은 '재간접'(형 없음).
    값 검사가 기각하고 사유에 "실제 값 예: MMF · 기타 · 임대형 · 재간접" 을 보여줬는데도
    재생성은 '재간접형' 을 유지한 채 **예시 4개를 그대로 IN 에 넣었다** — 예시 나열이
    정답 후보로 오해된 것이다. 답변 가능한 질의(2,594행)가 거절로 나갔다.
    사람이 '재간접형·주식형' 처럼 부르는 것은 자연스러우므로, 명백한 표기 차이는 기계가 흡수한다.
    🔴 후보가 둘 이상이면 손대지 않는다 — 의미가 갈리는 치환은 값 검사에 맡긴다.
    """
    raw = index.get(("_raw", table, column)) or ()
    if not raw:
        return None
    base = _norm(literal)
    for s in _SUFFIX_NOISE:
        base = base.removesuffix(s)
    base = base.strip()
    if not base:
        return None
    cands = {v for v in raw if _norm(v).strip() == base}
    if not cands:                       # 반대 방향 — 사람이 짧게 부르고 실제 값에 접미사가 붙은 경우
        cands = {v for v in raw
                 if any(_norm(v).strip() == base + s for s in _SUFFIX_NOISE if s.strip())}
    return next(iter(cands)) if len(cands) == 1 else None


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

    def user_text(self) -> str | None:
        """사용자 답변에 붙일 자연어 사유 한 문장 — 개발자 표기(SQL 조각) 금지.

        2026-08-31 밤 리드 결정: 0행 사유는 답변에 싣되 '조건별 단독 조회: …' 류 개발자
        텍스트로는 내보내지 않는다. SQL 조각을 한국어로 옮기지 못하는 조건이 하나라도 끼면
        구체 서술을 포기하고 일반 문장으로 낮춘다 — 어색한 반역(半譯)보다 안전하다.
        <> 제외절(고위험제외·수익률정상 주입분)은 사용자가 물은 조건이 아니므로 열거에서 뺀다."""
        if not self.counts:
            return None
        dead = [c for c, n in self.counts if n == 0]
        if dead:
            descs = [_humanize_cond(c) for c in dead]
            if all(descs):
                return "수록된 데이터에는 " + " · ".join(f"{d}인 상품" for d in descs) + " 자체가 없습니다."
            return "조건 중 일부는 수록된 데이터에 해당하는 상품 자체가 없습니다."
        pos = [(c, n) for c, n in self.counts if "<>" not in c]
        descs = [(_humanize_cond(c), n) for c, n in pos]
        if pos and len(pos) <= 3 and all(d for d, _ in descs):
            joined = " · ".join(f"{d}인 상품 {n:,}건" for d, n in descs)
            return joined + "은 각각 수록되어 있으나, 질문의 조건을 모두 동시에 만족하는 상품은 없습니다."
        return "조건 각각에 해당하는 상품은 있으나, 모든 조건을 동시에 만족하는 상품은 없습니다."


# ── ②-b 0행 사유 한국어화 — LLM 호출 0회, 옮길 수 있는 패턴만 (못 옮기면 None → 일반 문장) ──

_COL_KO = {
    "bd_knd": "채권 종류", "std_pd_mcls_nm": "상품 대분류", "std_pd_scls_nm": "상품 소분류",
    "crd_grd": "신용등급", "pd_risk_gcd": "위험등급", "pd_risk_nm": "위험등급",
    "srfc_irt": "표면금리", "applied_yield": "수익률", "mat_dt": "만기일",
    "remaining_days": "잔존일수", "pd_pbcm": "발행기관", "bd_intp_tcd": "이자지급방식",
    "bd_inrt_tcd": "금리유형", "bd_ofr_tcd": "공모/사모 구분", "pd_nm": "상품명", "curr_cd": "통화",
}
_RISK_KO = {"11": "1등급(매우높은위험)", "12": "2등급(높은위험)", "13": "3등급(다소높은위험)",
            "14": "4등급(보통위험)", "15": "5등급(낮은위험)", "16": "6등급(매우낮은위험)",
            "00": "해당없음"}
_DATE_COLS = {"mat_dt"}
_CMP_KO = {">": "초과", ">=": "이상", "<": "미만", "<=": "이하"}
_CMP_DATE_KO = {">": "이후", ">=": "이후", "<": "이전", "<=": "이전"}

_H_TRIM = re.compile(r"TRIM\(\s*([A-Za-z_]\w*)\s*\)", re.I)
_H_COAL = re.compile(r"COALESCE\(\s*([A-Za-z_]\w*)\s*,\s*''\s*\)", re.I)
_H_EQ = re.compile(r"^([A-Za-z_]\w*)\s*=\s*'((?:[^']|'')*)'$")
_H_IN = re.compile(r"^([A-Za-z_]\w*)\s+IN\s*\(([^)]*)\)$", re.I)
_H_CMP = re.compile(r"^([A-Za-z_]\w*)\s*(>=|<=|>|<)\s*('?)([\w.\-]+)\3$")
_H_LIKE = re.compile(r"^([A-Za-z_]\w*)\s+LIKE\s+'%((?:[^']|'')*)%'$", re.I)


def _risk_or_quote(col: str, val: str) -> str:
    if col == "pd_risk_gcd" and val in _RISK_KO:
        return _RISK_KO[val]
    return f"'{val}'"


def _ga(word: str) -> str:
    """이/가 조사 — 마지막 글자 받침 유무로. 한글 아닌 끝글자는 '이(가)' 로 둔다."""
    ch = word[-1]
    if "가" <= ch <= "힣":
        return "이" if (ord(ch) - 0xAC00) % 28 else "가"
    return "이(가)"


def _humanize_cond(cond: str) -> str | None:
    """최상위 AND 조건 하나를 '위험등급이 6등급(매우낮은위험)' 꼴로. 못 옮기면 None."""
    c = _H_COAL.sub(r"\1", _H_TRIM.sub(r"\1", cond.strip()))
    if c.startswith("(") and c.endswith(")"):
        return None                                    # OR 그룹 — 한 문장으로 못 옮긴다
    m = _H_EQ.match(c)
    if m:
        col = m.group(1).lower()
        if col not in _COL_KO:
            return None
        lab = _COL_KO[col]
        return f"{lab}{_ga(lab)} {_risk_or_quote(col, m.group(2))}"
    m = _H_IN.match(c)
    if m:
        col = m.group(1).lower()
        vals = re.findall(r"'((?:[^']|'')*)'", m.group(2))
        if col not in _COL_KO or not vals:
            return None
        lab = _COL_KO[col]
        return f"{lab}{_ga(lab)} {'·'.join(_risk_or_quote(col, v) for v in vals)} 중 하나"
    m = _H_CMP.match(c)
    if m:
        col, op, val = m.group(1).lower(), m.group(2), m.group(4)
        if col not in _COL_KO:
            return None
        lab = _COL_KO[col]
        word = (_CMP_DATE_KO if col in _DATE_COLS else _CMP_KO)[op]
        return f"{lab}{_ga(lab)} {val} {word}"
    m = _H_LIKE.match(c)
    if m:
        col = m.group(1).lower()
        return f"{_COL_KO[col]}에 '{m.group(2)}' 포함" if col in _COL_KO else None
    return None


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
