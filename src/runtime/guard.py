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
# 🔴 TRIM(col) = 'lit' · COALESCE(TRIM(col),'') = 'lit' 도 잡는다 — 2026-09-02 실측: ensure_trimmed_compare 가
#    pd_pbcm·bd_knd 등호를 전부 TRIM 으로 감싼 뒤에 이 검사가 돌아, 발행사·종류·등급 리터럴 검사가 사실상 0건이었다
#    (TRIM(pd_pbcm)='삼성전자'·TRIM(crd_grd)='AAAA'·TRIM(pd_pbcm)='한국전력공사'(주 누락) 전부 통과 → 0행 오거절).
#    안전성: 검증 gold SQL 109개에 적용해 위반 0건, pd_pbcm 값 사전은 DB distinct 1,818 = 100% 커버.
_WRAP = r"(?:COALESCE\(\s*)?(?:TRIM\(\s*)?"
_UNWRAP = r"\s*\)?(?:\s*,\s*''\s*\))?"
_EQ = re.compile(_WRAP + r"(?:\b([A-Za-z_]\w*)\.)?\b([A-Za-z_]\w*)" + _UNWRAP + r"\s*=\s*'((?:[^']|'')*)'", re.I)
_IN = re.compile(_WRAP + r"(?:\b([A-Za-z_]\w*)\.)?\b([A-Za-z_]\w*)" + _UNWRAP + r"\s+IN\s*\(([^)]*)\)", re.I)
_LIT = re.compile(r"'((?:[^']|'')*)'")
_LIKE = re.compile(r"(?:\b([A-Za-z_]\w*)\.)?\b([A-Za-z_]\w*)\s+LIKE\s+'((?:[^']|'')*)'", re.I)
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
    if not sql_tables(body):
        return []
    schema = getattr(ctx, "schema", {}) or {}
    # 별칭은 문장 전역에서 모은다 — 바깥 ORDER BY 가 안쪽 별칭을 부를 수 있다
    aliases = {a.lower() for a in _AS_ALIAS.findall(body)}
    out, seen = [], set()
    # 🔴 14R KG ③-11 — **컬럼 존재 검사도 그 컬럼이 등장한 스코프의 `FROM` 기준**이다(11R ③-2 잔여).
    #    종전엔 문장 전체 테이블의 합집합으로 판정해, UNION 의 `public_funds` 가지에 있는 `wu_inv_rgn`(ETF 컬럼)이
    #    "다른 가지에 있으니 존재한다" 로 통과했고 실행 시 OperationalError → "데이터 조회 중 오류" 가 나갔다(X15).
    #    `sql_scopes` 가 이미 UNION 가지·괄호 서브쿼리를 갈라 준다(가드 중복 0).
    for scope in sql_scopes(body):
        used = sql_tables(scope)
        if not used:
            continue
        known = {c.lower() for t in used for c, _, _ in (schema.get(t) or [])}
        if not known:
            continue
        known |= set(TABLES) | set(EXT_TABLES) | _SQL_FUNCS | aliases
        for tok in _SNAKE.findall(scope):
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
_UNION = re.compile(r"^union(?:\s+all)?\b", re.I)
_SUBSELECT = re.compile(r"\(\s*select\b", re.I)


def sql_scopes(sql: str) -> list[str]:
    """SQL 을 **독립 스코프**(UNION 가지 · 괄호 서브쿼리)로 가른다.

    🔴 10R KG 부류 Q — 문장 전역 검사는 스코프를 넘어 매칭한다: `FROM ext_fund_page WHERE itm_no IN
       (SELECT itm_no FROM public_funds …)` 는 SQLite 에서 모호하지 않은데 "테이블 2개 + 공유 컬럼 itm_no" 로
       판정돼 기각됐고(X8·X9·X15·KG-025·KG-026 오거절), UNION 둘째 가지도 첫 가지의 WHERE 로 읽혔다.
    """
    body = _SQL_STR.sub("''", sql)
    scopes, cur, depth, i = [], [], 0, 0
    while i < len(body):
        ch = body[i]
        if ch == "(":
            if depth == 0 and _SUBSELECT.match(body[i:]):
                # 괄호 서브쿼리 — 통째로 떼어 별도 스코프로 (재귀적으로 다시 가른다)
                d, j = 0, i
                while j < len(body):
                    if body[j] == "(":
                        d += 1
                    elif body[j] == ")":
                        d -= 1
                        if d == 0:
                            break
                    j += 1
                scopes += sql_scopes(body[i + 1:j])
                cur.append(" ")
                i = j + 1
                continue
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and (i == 0 or not body[i - 1].isalnum() and body[i - 1] != "_"):
            m = _UNION.match(body[i:])
            if m:
                scopes.append("".join(cur))
                cur = []
                i += m.end()
                continue
        cur.append(ch)
        i += 1
    scopes.append("".join(cur))
    return [s for s in scopes if s.strip()]


def ambiguous_columns(sql: str, ctx: RuntimeContext) -> list[str]:
    """JOIN 질의에서 **한정되지 않은** 채 여러 테이블에 존재하는 컬럼 — 실행하면 ambiguous 오류다.

    2026-08-31 밤 실측(설정일 질의): public_funds JOIN ext_fund_page 에서 SELECT itm_no 가
    양쪽에 있어 "ambiguous column name: itm_no" 로 죽었다. 실행 오류는 재생성 경로가 없어
    그대로 "조회 중 오류" 응답이 나간다 — 실행 전에 잡아 재생성 1회를 준다.
    🔴 10R KG 부류 Q — 판정 단위는 문장이 아니라 **스코프**다(`sql_scopes`).
    """
    schema = getattr(ctx, "schema", {}) or {}
    out: list[str] = []
    for body in sql_scopes(sql):
        used = sql_tables(body)
        if len(used) < 2:
            continue
        owners: dict[str, set] = {}
        for t in used:
            for c, *_ in (schema.get(t) or ()):
                owners.setdefault(c.lower(), set()).add(t)
        shared = {c for c, ts in owners.items() if len(ts) > 1}
        if not shared:
            continue
        aliases = {a.lower() for a in _AS_ALIAS.findall(body)}
        for c in sorted(shared):
            if c in aliases or c in out:
                continue
            # 🔴 이름이 아니라 **등장 위치**로 판정한다 — `public_funds.itm_no` 가 한 번 있다고 해서
            #    SELECT 의 맨 itm_no 가 한정된 것은 아니다(앞의 점 없는 등장이 곧 모호 컬럼이다).
            if re.search(rf"(?<![\w.]){c}\b", body, re.I):
                out.append(c)
    return sorted(out)


_SUFFIX_NOISE = ("형", "型", "펀드", " ", "(주)")   # '(주)' — 발행사 법인 접미(2026-09-02: '한국전력공사' → '한국전력공사(주)' 유일 후보)


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
    # 6R F4 — LIKE 리터럴도 값사전 대조: 전 값을 아는 컬럼(지역·유형 enum)에 `LIKE '%중국%'` 처럼 어느 값의 부분열도 아닌 리터럴은 기각
    #    (KG-012: fd_ivst_rgn_desc LIKE '%중국%' 가 통과해 0행 "0개" — 값은 국내·아시아·글로벌…). 이름·자유 텍스트 컬럼은 사전에 없어 불개입.
    #    🔴 대조 대상은 **enum 어휘(value_vocab) 컬럼**뿐 — alias 커버리지로 들어온 이름형 컬럼(ref_fund_mgmt_co 등)에 LIKE 는 정당한 부분일치다
    #    (gold ETF-O-014 'BlackRock' 오탐 실측).
    vocab_cols = set(getattr(ctx, "value_vocab", {}) or {})
    like_pairs = [(tbl or None, col, lit) for tbl, col, lit in _LIKE.findall(sql) if lit.strip("%").strip()]
    for tbl, col, lit in like_pairs:
        col_l = col.lower()
        needle = _norm(lit.strip("%"))
        for t in ([tbl.lower()] if tbl else [t for t in tables if (t, col_l) in index]):
            vals = index.get((t, col_l))
            if vals is None or (t, col_l) not in vocab_cols:
                continue
            if any(needle in v for v in vals):
                break
            hint = _value_hints(index.get(("_raw", t, col_l), ()), lit.strip("%"))
            out.append(ValueViolation(t, col_l, lit, hint, _owner_column(index, t, col_l, lit.strip("%"))))
            break
    for tbl, col, lit in pairs:
        # `col = ''` 은 값 조회가 아니라 **결측 관용구**다 (IS NULL OR col='') — 값 사전에 빈 문자열이
        # 있을 리 없으니 검사하면 무조건 오탐 기각이 된다 (2026-09-01 FND-037 실측: 벤치마크 결측
        # 건수 질의가 답변 가능한데 가드가 만든 오거절로 나감)
        if not lit.strip():
            continue
        col_l = col.lower()
        candidates = [tbl.lower()] if tbl else [t for t in tables if (t, col_l) in index]
        for t in candidates:
            vals = index.get((t, col_l))
            if vals is None:
                continue
            if _norm(lit) in vals:
                break
            hint = _value_hints(index.get(("_raw", t, col_l), ()), lit)
            out.append(ValueViolation(t, col_l, lit, hint, _owner_column(index, t, col_l, lit)))
            break
    return out


_CODE_COL = re.compile(r"_itt_cd$", re.I)
_CODE_NUM_EQ = re.compile(r"(?:\b([A-Za-z_]\w*)\.)?\b([A-Za-z_]\w*_itt_cd)\s*=\s*(\d+)\b(?!\s*')", re.I)


def check_code_literals(sql: str, ctx: RuntimeContext) -> list[str]:
    """KG 1R R3 ①② — 기관코드 컬럼(`*_itt_cd`)의 리터럴은 DB 에 실재하는 코드여야 한다. 등호·IN 원소 전부 대조, 따옴표 없는
    숫자 비교(`= 80000000` — 코드는 문자열)도 기각. 값 사전(check_values)은 alias 커버리지 98% 컬럼만 보므로 코드 컬럼은
    여기서 직접 실존 조회(SQLite 1회/리터럴). KG-003 `'A011'` · KG-004 `80000000` · KG-025 `IN ('삼성','삼성KODEX')` 날조가
    검사기를 통과해 "0개"·"미수록" 단언으로 나갔다.
    """
    tables = [t for t in sql_tables(sql) if t in TABLES]
    if not tables:
        return []
    schema = getattr(ctx, "schema", {}) or {}
    problems: list[str] = []
    sql = re.sub(r"\bTRIM\(\s*((?:\w+\.)?\w+)\s*\)", r"\1", sql, flags=re.I)   # TRIM(col) = 'x' 도 등호 쌍으로 본다
    for tbl, col, num in _CODE_NUM_EQ.findall(sql):
        problems.append(f"{col} = {num} (따옴표 없는 숫자 — 코드는 '{num.zfill(8)}' 같은 문자열)")
    pairs: list[tuple[str, str]] = []
    for tbl, col, lit in _EQ.findall(sql):
        if _CODE_COL.search(col):
            pairs.append((col, lit))
    for tbl, col, body in _IN.findall(sql):
        if _CODE_COL.search(col):
            pairs += [(col, lit) for lit in _LIT.findall(body)]
    if not pairs:
        return problems
    con = None
    try:
        from .loader import connect_readonly
        con = connect_readonly()
        for col, lit in pairs:
            owner = next((t for t in tables if any(c.lower() == col.lower() for c, *_ in schema.get(t, ()))), None)
            if not owner or not lit.strip():
                continue
            row = con.execute(
                f"SELECT 1 FROM {owner} WHERE TRIM({col}) = ? OR printf('%08d', CAST({col} AS INTEGER)) = ? LIMIT 1",
                (lit.strip(), lit.strip().zfill(8))).fetchone()
            if row is None:
                problems.append(f"{col} = '{lit}' 은 데이터에 없는 코드")
    except Exception:  # noqa: BLE001 — 검사기 자체 오류로 실행을 막지 않는다
        return problems
    finally:
        if con is not None:
            con.close()
    return problems


def _value_hints(raw, literal: str) -> list[str]:
    """기각된 리터럴과 비슷한 실제 값을 예시 맨 앞에 놓는다.

    2026-09-01 FND-023 실측: '혼합형' 기각의 예시가 정렬 표본(MMF·기타·임대형·재간접)이라
    실제 값 '주식혼합'·'채권혼합' 이 안 보였고, 재생성은 힌트 0 으로 REFUSE — 답변 가능한
    질의(주식혼합+채권혼합 top5 실재)가 오거절로 나갔다. _name_owners 의 철자 유사 후보(FND-035)와
    동형 — 이번엔 컬럼이 아니라 값이다. 접미사 노이즈를 벗긴 어간의 포함 관계로 추린다.
    """
    base = _norm(literal)
    for s in _SUFFIX_NOISE:
        base = base.removesuffix(s)
    base = base.strip()
    sim = sorted(v for v in raw if base and base in _norm(v))
    rest = [v for v in sorted(raw) if v not in sim]
    return (sim + rest)[:_MAX_HINT]


# ── ② 0행 진단 ──────────────────────────────────────────────────────────

_SIMPLE = re.compile(r"^\s*select\b(?P<sel>.+?)\bfrom\b(?P<from>.+?)(?:\bwhere\b(?P<where>.+?))?(?:\b(?:group\s+by|order\s+by|limit)\b.*)?$", re.I | re.S)
_COMPLEX = re.compile(r"\(\s*select\b|\bunion\b|\bhaving\b|\bwith\b", re.I)


def _split_top_level(where: str, op: str) -> list[str]:
    """최상위 `op`(AND·OR)로만 가른다 — 괄호·따옴표 안은 건드리지 않는다."""
    tok, n = f" {op} ", len(op) + 2
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
            elif depth == 0 and s[i:i + n].upper() == tok:
                parts.append("".join(buf).strip()); buf = []; i += n; continue
        buf.append(ch); i += 1
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def split_conjuncts(where: str) -> list[str]:
    """최상위 AND 로만 가른다 — 괄호·따옴표 안의 AND 는 건드리지 않는다. OR 가 최상위에 있으면 통째로 한 조건."""
    return _split_top_level(where, "AND")


def split_disjuncts(where: str) -> list[str]:
    """최상위 OR 로만 가른다 — 확정식 치환을 **비교식 단위**로 하기 위한 짝(11R gold ③-3).

    OR 절을 통째로 버리면 반대편 가지(사용자 조건)까지 사라진다 —
    `cu_base_index LIKE '%우주%' OR pd_nm LIKE '%항공%'` 에서 이름 가지가 소멸한 계열(OFFICIAL-004).
    """
    return _split_top_level(where, "OR")


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


# ══════════════════════════════════════════════════════════════════════════
# enforce 슬롯 적용기 — docs/guard_to_yaml_migration_2026-09-03.md §2-3
# ══════════════════════════════════════════════════════════════════════════
# 코드 가드 `ensure_*` 20개는 각각 "발동 조건 + 확정식 + 동작" 이라는 같은 뼈대를 파이썬으로 다시 쓴 것이다.
# 뼈대가 같으니 데이터(yaml `query_rules.<name>.enforce`)로 쓰고, 적용기 하나가 읽는다.
#
# 🔴 이 함수가 가드보다 **먼저** 돌고, 발동하면 SQL 에 `/*M:<mark>*/` 표식을 남긴다.
#    같은 주제의 코드 가드는 그 표식을 보고 침묵한다(절차 §2-4). 가드 삭제는 두 라운드 뒤(§5).
# 🔴 UNION 은 가지별로 분해해 **각 가지에 독립 적용**한다 — 코드 가드가 `union` 을 보면 통째로
#    불개입하던 자리가 교차질의 오답의 원인이었다(절차 §0). 이것이 슬롯의 첫 이득이다.

# 지원 액션 — 여기 없는 값은 loader.validate_enforce 가 로드 시점에 거부한다.
# 절차 §1 인벤토리(docs/guard_migration_inventory_2026-09-03.md) 판정 A 9개가 쓰는 셋만 먼저 연다.
# 나머지(add_select·replace_order·remove_predicate)는 그 슬롯을 실제로 켤 때 함께 구현한다 — 쓰지 않는
# 액션을 미리 만들면 검증할 수 없는 코드가 남는다.
ENFORCE_ACTIONS = ("inject_where", "replace_expr", "replace_predicate")

# WHERE 를 새로 붙일 자리 — 이 앞에 꽂는다
_ENF_ANCHOR = re.compile(r"\b(?:group\s+by|order\s+by|limit|having)\b", re.I)
_ENF_UNION = re.compile(r"\bunion(?:\s+all)?\b", re.I)


def _split_union(sql: str) -> list[str]:
    """최상위 UNION 가지로 나눈다. 괄호 안의 UNION(서브쿼리)은 건드리지 않는다."""
    parts, depth, last = [], 0, 0
    for m in re.finditer(r"[()]|\bunion(?:\s+all)?\b", sql, re.I):
        tok = m.group(0)
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        elif depth == 0:
            parts.append(sql[last:m.start()])
            parts.append(m.group(0))          # 구분자도 보존해 그대로 재조립
            last = m.end()
    parts.append(sql[last:])
    return parts


def _inject_where(sql: str, cond: str) -> tuple[str, bool]:
    """WHERE 에 조건을 AND 로 더한다. 기존 조건은 괄호로 감싼다 —
    'WHERE a OR b' 에 그냥 AND 를 붙이면 (cond AND a) OR b 로 새기 때문이다."""
    m = re.search(r"\bwhere\b", sql, re.I)
    if m:
        e = m.end()
        tail = sql[e:]
        stop = _ENF_ANCHOR.search(tail)
        body, rest = (tail[:stop.start()], tail[stop.start():]) if stop else (tail, "")
        return f"{sql[:e]} {cond} AND ({body.strip()}) {rest}".rstrip(), True
    anchor = _ENF_ANCHOR.search(sql)
    if not anchor:
        return f"{sql.rstrip().rstrip(';')} WHERE {cond}", True
    s = anchor.start()
    return f"{sql[:s]}WHERE {cond} {sql[s:]}", True


def _match_when(spec: dict, sql: str, question: str, tables: list[str], grounded: set) -> bool:
    """다섯 축 판정 — tables / question / grounded / sql.has / sql.lacks (+ any_of_has).
    축 밖의 키가 있으면 **발동하지 않는다** (validate_enforce 가 로드에서 거르지만 이중 방어)."""
    want = spec.get("tables")
    if want:
        # 🔴 라우팅 테이블이 아니라 **이 SQL(가지)의 FROM/JOIN** 으로 판정한다 —
        #    절차 §2-1 의 "이 테이블이 FROM/JOIN 에 있으면 (UNION 가지 각각 독립 판정)" 그대로.
        #    2026-09-03 섀도에서 라우팅으로 보다가 public_funds 가 없는 holdings 조인 SQL
        #    (KG-028·X2·Z7·Z8)에 sale_yn 을 주입해 깨뜨렸다. 라우팅은 "질문이 어디를 향하는가" 고
        #    슬롯이 고치는 것은 "이 SQL 이 무엇을 읽는가" 라, 둘은 다른 축이다.
        in_sql = set(sql_tables(sql))
        if not (set(want) & in_sql):
            return False
    q = spec.get("question") or {}
    if q.get("any") and not any(str(w) in question for w in q["any"]):
        return False
    if q.get("not_any") and any(str(w) in question for w in q["not_any"]):
        return False
    g = spec.get("grounded")
    if g and str(g) not in grounded:
        return False
    s = spec.get("sql") or {}
    low = sql.lower()
    if any(str(t).lower() not in low for t in s.get("has") or []):
        return False
    if any(str(t).lower() in low for t in s.get("lacks") or []):
        return False
    aoh = s.get("any_of_has")
    if aoh and not any(str(t).lower() in low for t in aoh):
        return False
    return True


def _apply_one(sql: str, enf: dict, subs: dict) -> tuple[str, bool]:
    """액션 하나를 SQL 한 가지(branch)에 적용. 대상이 정확히 잡힐 때만 손댄다(원자성)."""
    action = enf.get("action")
    body = str(enf.get("sql") or "")
    for k, v in subs.items():
        body = body.replace("{" + k + "}", str(v))
    if action == "inject_where":
        return _inject_where(sql, body)
    if action == "replace_expr":
        src = str(enf.get("from") or "")
        if not src or sql.lower().count(src.lower()) != 1:
            return sql, False           # 0개면 대상 없음, 2개 이상이면 어느 쪽인지 모른다 → 불개입
        i = sql.lower().index(src.lower())
        return sql[:i] + body + sql[i + len(src):], True
    if action == "replace_predicate":
        pat = enf.get("from_pattern")
        if not pat:
            return sql, False
        ms = list(re.finditer(str(pat), sql, flags=re.I))
        if len(ms) != 1:
            return sql, False                            # 0개면 대상 없음, 2개 이상이면 불개입
        m = ms[0]
        # 🔴 캡처 그룹 치환 — 확정식이 **매치한 리터럴에 따라 달라지는** 규칙이 있다
        #    (ensure_etf_index_canon: 지수명 X → ref_base_index GLOB 'X' OR GLOB 'X[CTP]R*').
        #    고정 sql 로는 못 쓰고, 그렇다고 코드에 두면 같은 뼈대가 또 파이썬으로 간다.
        #    `{1}`·`{2}` 로 그룹을 받는다. 공백 제거형은 `{1:nospace}`.
        rep = body
        for i, g in enumerate(m.groups(), 1):
            v = "" if g is None else str(g)
            rep = rep.replace("{%d:nospace}" % i, re.sub(r"\s+", "", v)).replace("{%d}" % i, v)
        return sql[:m.start()] + rep + sql[m.end():], True
    return sql, False


def apply_enforce(sql: str, question: str, tables: list[str], grounded, ctx: RuntimeContext
                  ) -> tuple[str, list[str]]:
    """yaml `query_rules.<name>.enforce` 선언을 SQL 에 적용한다. (보정된 SQL, 발동한 mark 목록)

    선언 순서대로 1회 통과. UNION 은 가지별 독립 적용 후 재조립.
    발동하면 `/*M:<mark>*/` 를 SQL 끝에 남긴다 — 코드 가드의 침묵 판정과 체인 끝 사후조건이 이걸 본다.
    """
    grounded = set(grounded or ())
    fired: list[str] = []
    subs = {"fund_key": _FUND_KEY_SQL}
    branches = _split_union(sql)
    for t in tables:
        for name, rule in ((ctx.enums.get(t) or {}).get("query_rules") or {}).items():
            if not isinstance(rule, dict):
                continue
            enf = rule.get("enforce")
            # 🔴 키는 `enabled` 다 — `off` 로 쓰면 YAML 1.1 이 그것을 **불리언 키**로 읽어
            #    딕셔너리에 False 키가 생기고 enf.get("off") 가 영원히 None 이 된다(실측으로 잡음).
            if not isinstance(enf, dict) or enf.get("enabled", True) is False:
                continue
            mark = str(enf.get("mark") or name)
            if f"M:{mark}" in sql:
                continue                       # 멱등 — 이미 발동했다
            hit = False
            for i, part in enumerate(branches):
                if _ENF_UNION.fullmatch(part.strip()):
                    continue                   # 구분자는 건너뛴다
                if not _match_when(enf.get("when") or {}, part, question, tables, grounded):
                    continue
                new, ok = _apply_one(part, enf, subs)
                if ok:
                    branches[i], hit = new, True
            if hit:
                fired.append(mark)
                sql = "".join(branches) + f" /*M:{mark}*/"
                branches = _split_union(sql)
    return ("".join(branches) if not fired else sql), fired


# 펀드단위 키 — **정본은 여기 하나다.** pipeline._FUND_KEY_EXPR 도 이것을 쓴다(순환 import 방지:
# pipeline 이 guard 를 import 하므로 방향이 맞다). 슬롯 sql 은 {fund_key} 자리표시자로 받는다.
#
# 🔴 printf('%08d', CAST(... AS INTEGER)) 를 빼면 안 된다 — 운용사 코드가 7·8자 혼재라
#    정규화 없이는 같은 운용사가 두 키로 갈린다. 섀도(2026-09-03)에서 슬롯이 이걸 빠뜨려
#    가드와 다른 SQL 을 냈고, 그래서 정의를 한 곳으로 합쳤다.
#    trim 도 마찬가지 — mtco 에 패딩 공백이 있는 행이 있다.
FUND_KEY_EXPR = ("printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || "
                 "COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) "
                 "ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)")
_FUND_KEY_SQL = FUND_KEY_EXPR
