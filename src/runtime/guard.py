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
from functools import lru_cache
from dataclasses import dataclass

from .loader import EXT_TABLES, TABLES, RuntimeContext, connect_readonly
from .gate import BUYABLE_CUTOFF

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
    owner_counts: tuple = ()   # 후보가 둘 이상일 때 (컬럼, 행수) 내림차순 — 2026-09-04 #61

    def __str__(self) -> str:
        ex = " · ".join(h[:40] for h in self.hint[:_MAX_HINT])
        msg = f"{self.table}.{self.column} = '{self.literal}' 은(는) DB 에 없는 값"
        if self.owner:
            # 🔴 컬럼을 잘못 고른 것이지 값이 없는 게 아니다 — 이 구분이 없으면 재생성이 같은 실수를 반복하고
            #    파이프라인이 답변 가능한 질의를 거절한다 (FND-026 실측: '해외주식형' 은 zrin_btyp_nm 의 값인데
            #    or_attr_desc 에 써서 기각 → 재생성도 같은 값 유지 → 중국 펀드 560행이 있는데 '확인 불가' 응답).
            # 🔴 후보가 둘 이상이면 **행수와 함께** 전부 준다 (2026-09-04 #61 실측: '국고채권' 은 bd_knd 356행이
            #    주인인데 오염 1행짜리 pd_pbcm 이 지목돼 재생성이 같은 SQL 을 되풀이하고 오거절로 끝났다).
            spread = (" (" + " · ".join(f"{c} {n:,}행" for c, n in self.owner_counts) + ")"
                      if len(self.owner_counts) > 1 else "")
            return (msg + f" — 이 값은 같은 테이블의 **{self.owner}** 컬럼 값이다{spread}. "
                    f"컬럼을 {self.owner} 로 바꾸거나 그 조건을 다른 축으로 다시 세워라")
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


def _owner_column(index: dict, table: str, column: str, literal: str) -> tuple[str, tuple]:
    """이 리터럴이 같은 테이블의 **다른** 컬럼 값이면 (주인 컬럼, 후보별 행수) — 아니면 ("", ()).

    2026-08-31 밤 FND-026 실측 처방: 값 위반의 태반이 '없는 값' 이 아니라 **컬럼 오선택**이다
    ('해외주식형' 은 zrin_btyp_nm 의 값인데 or_attr_desc 에 썼다). 사유에 이걸 적어야 재생성이
    같은 값을 되풀이하지 않는다 — 실측에서는 재생성도 실패해 답변 가능한 질의가 거절로 나갔다.

    🔴 2026-09-04 #61 — 후보가 둘이면 **행수가 많은 컬럼**이 주인이다. '국고채권' 은 bd_knd 356행 ·
    pd_pbcm 1행(국고채원금분리채권의 발행사 칸에 종류명이 들어간 오염 1행)인데, 사전 순회 순서대로
    pd_pbcm 을 지목해 재생성이 같은 SQL 을 되풀이했고 답변 가능한 질의가 오거절로 끝났다.
    행수는 위반 경로에서만 세므로(질의당 최대 1회 스캔) 정상 경로 비용은 0이다."""
    n = _norm(literal)
    cands = [key[1] for key, vals in index.items()
             if len(key) == 2 and key[0] == table and key[1] != column and n in vals]
    if len(cands) < 2:
        return (cands[0] if cands else ""), ()
    counts = _literal_row_counts(table, cands, literal)
    if not counts:
        return cands[0], ()
    ranked = tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return ranked[0][0], ranked


def _literal_row_counts(table: str, columns: list[str], literal: str) -> dict:
    """각 후보 컬럼에서 이 리터럴이 몇 행인가 — 한 번의 스캔. 실패하면 빈 dict(호출자가 종전 순서로 물러선다)."""
    if not columns or not re.fullmatch(r"\w+", table or ""):
        return {}
    cols = [c for c in columns if re.fullmatch(r"\w+", c or "")]
    if not cols:
        return {}
    sel = ", ".join(f"SUM(CASE WHEN LOWER(TRIM({c})) = LOWER(?) THEN 1 ELSE 0 END)" for c in cols)
    try:
        con = connect_readonly()
        try:
            row = con.execute(f"SELECT {sel} FROM {table}", [literal] * len(cols)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return {}
    return {c: int(v or 0) for c, v in zip(cols, row)}


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
    if not cands:
        # 🔴 **내부 공백**만 다른 경우 (2026-09-03 17R · KG-026 실측).
        #    DB 값 `'KOSPI200 5% +  회사채I-BBB종합 02Y  95%'` 는 `+` 뒤와 `95%` 앞이 **두 칸**인데
        #    HCX 는 한 칸으로 썼다. 값은 48행 실재하는데 검사기가 기각하고 재생성도 같은 문장을 내
        #    문장 전체가 죽었다(축·모수는 이미 맞았는데 이 한 겹에서 끝났다).
        #    이 함수의 계약이 원래 "접미사·**공백**만 다르면" 이므로 그 공백을 내부까지 넓힌다.
        #    유일 후보일 때만 돌려주는 규칙은 그대로 — 의미가 갈리는 치환은 여전히 일어나지 않는다.
        squash = re.sub(r"\s+", " ", base)
        cands = {v for v in raw if re.sub(r"\s+", " ", _norm(v).strip()) == squash}
    return next(iter(cands)) if len(cands) == 1 else None


_MASTER_FROM = re.compile(r"\bfrom\s+(" + "|".join(TABLES) + r")\b", re.I)
_INNER_EXT_JOIN = re.compile(r"\b(?<!left )(?<!outer )(?:inner\s+)?join\s+(" + "|".join(EXT_TABLES) + r")\b", re.I)


def ensure_ext_left_join(sql: str) -> tuple[str, list[str]]:
    """마스터가 FROM 인데 `ext_*` 를 **INNER** 로 붙인 것을 LEFT 로 바꾼다. (SQL, 바꾼 테이블)

    2026-09-04 KG-005 실측 — `ext_fund_page` 커버리지는 판매중·공모 **8,408/8,969 = 93.7%** 다.
    INNER JOIN 이면 나머지 **561클래스가 조용히 사라진다**. 실제로 "이름이 삼성으로 시작하는
    공모펀드" 가 217펀드/906클래스인데 217→**215**, 906→**868** 로 줄어든 채 답이 나갔다.
    모수가 깎인 것을 답변 어디에도 밝히지 않으므로 사용자는 알 수 없다.

    🔴 안전성: ext 컬럼이 WHERE 에 조건으로 있으면 LEFT 로 바꿔도 **결과가 같다** — 짝이 없는
       행은 그 컬럼이 NULL 이라 어떤 비교도 통과하지 못한다(실측 확인: 868행 = 868행).
       조건이 없을 때만 달라지고, 그때는 **마스터 모수를 지키는 LEFT 가 옳다.**
    불개입: FROM 이 마스터가 아님 · 이미 LEFT · ext_* 가 아닌 조인.
    """
    if not _MASTER_FROM.search(sql):
        return sql, []
    changed: list[str] = []
    out = sql
    for m in list(_INNER_EXT_JOIN.finditer(sql)):
        out = out.replace(m.group(0), "LEFT JOIN " + m.group(1), 1)
        changed.append(m.group(1))
    return out, changed


_EXT_JOIN_CLAUSE = re.compile(
    r"\s+LEFT\s+JOIN\s+(" + "|".join(EXT_TABLES) + r")(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?\s+ON\s+.*?"
    r"(?=\s+(?:LEFT\s+JOIN|JOIN|WHERE|GROUP\s+BY|ORDER\s+BY|LIMIT)\b|$)", re.I | re.S)


# 질문이 값을 이름으로 부르는 축들 — 이 컬럼의 IN 목록만 좁힌다. 코드·이름 컬럼은 대상이 아니다.
_NAMED_ENUM_COLS = ("or_attr_desc", "zrin_btyp_nm", "zrin_ptn_nm")


_EXCLUDE_ASK = re.compile(r"([가-힣A-Za-z0-9][가-힣A-Za-z0-9 ]{0,18}?)\s*(?:은|는|을|를|이|가)?\s*"
                          r"(?:제외하고|제외한|제외하면|제외|빼고|뺀|말고|아닌)")


@lru_cache(maxsize=1)
def _named_enum_domain() -> dict:
    """이름 축들의 실제 값 — DB 실측. 값 사전(`value_index`)은 접지된 컬럼만 담아
    `zrin_ptn_nm`(alias 0)이 통째로 비어 있다(2026-09-05 실측: _raw 0건)."""
    con = connect_readonly()
    try:
        return {col: sorted({str(r[0]).strip() for r in
                             con.execute(f"SELECT DISTINCT {col} FROM public_funds "
                                         f"WHERE {col} IS NOT NULL AND TRIM({col}) <> ''")})
                for col in _NAMED_ENUM_COLS}
    finally:
        con.close()


def _enum_values_containing(ctx, token: str) -> dict:
    """`token` 을 낱말로 품은 값들을 축별로 모은다 — 배제식을 **데이터에서 유도**한다.

    하드코딩하지 않는 이유: 'MMF' 하나를 배제하려면 `zrin_ptn_nm` 의 'MMF'·'외화 MMF(USD)' 와
    `zrin_btyp_nm` 의 'MMF'·'외화 MMF' 를 모두 걸어야 한다(2026-09-05 실측: 한 축만 걸면
    한국투자법인용달러MMF 1.04조가 2위로 샌다). 축과 표기가 늘어도 코드는 그대로여야 한다.
    """
    out: dict = {}
    pat = re.compile(rf"(?<![0-9A-Za-z]){re.escape(token)}(?![0-9A-Za-z])", re.I)
    for col, vals in _named_enum_domain().items():
        hits = [v for v in vals if pat.search(v.replace(" ", ""))]
        if hits:
            out[col] = hits
    return out


def ensure_excluded_value(sql: str, question: str, ctx: RuntimeContext) -> tuple[str, str | None]:
    """질문의 **배제 낱말**을 부정 조건으로 세운다. (SQL, 배제한 낱말)

    2026-09-04·05 FND-006 — "**MMF를 제외하고** 순자산이 가장 큰 공모펀드 5개" 가 세 회차 내리

        WHERE zrin_ptn_nm = 'MMF' …        ← 정반대다

    로 나갔다. 접지는 성공했고(MMF 를 찾았다) **연산자만 뒤집혔다.** 그래서 답이 MMF 목록이
    되었는데 숫자가 그럴듯해 오답인 줄도 모른다 — 틀린 답을 자신 있게 내놓는 부류다.
    `query_rules.부정조건` 이 문안까지 정확히 적어 두었는데도 세 회차 모두 안 지켜졌다.

    조치: 배제 낱말이 가리키는 값을 **모든 이름 축에서** 유도해 `NOT IN` 으로 세우고, 같은
    낱말의 **긍정 조건은 걷어낸다**. `COALESCE` 로 감싸 미수록(NULL) 행이 함께 사라지지 않게 한다.
    불개입: 배제 낱말 없음 · 그 낱말이 어느 이름 축에도 없음 · public_funds 아님.
    """
    if "public_funds" not in sql_tables(sql):
        return sql, None
    m = _EXCLUDE_ASK.search(question)
    if not m:
        return sql, None
    token = m.group(1).strip()
    vals = _enum_values_containing(ctx, token)
    if not vals:
        return sql, None
    lits = {v for vs in vals.values() for v in vs}
    out = sql
    # ① 같은 낱말의 긍정 조건을 걷어낸다 — 남으면 배제식과 교집합이 0 이 된다
    for pat in (_EQ, _IN):
        for mm in list(pat.finditer(out)):
            col = (mm.group(2) or "").lower()
            if col in _NAMED_ENUM_COLS and set(_LIT.findall(mm.group(0))) & lits:
                out = re.sub(r"\s*(?:AND|OR)?\s*" + re.escape(mm.group(0)), " ", out, count=1, flags=re.I)
    # 제거 뒤 남은 접속사를 정리한다 — `WHERE AND x` · `x AND AND y` 는 문법 오류다
    out = re.sub(r"\s*\b(AND|OR)\s+\1\b", r" \1", out, flags=re.I)
    out = re.sub(r"\bWHERE\s+(?:AND|OR)\b", "WHERE", out, flags=re.I)
    out = re.sub(r"\s*\b(?:AND|OR)\s+(?=\b(?:GROUP\s+BY|ORDER\s+BY|LIMIT)\b|$)", " ", out, flags=re.I)
    cond = " AND ".join(f"COALESCE({c},'') NOT IN (" + ", ".join("'" + v.replace("'", "''") + "'" for v in vs) + ")"
                        for c, vs in vals.items())
    if cond in out:
        return sql, None
    m_w = re.search(r"\bwhere\b", out, re.I)
    if m_w:
        out = out[:m_w.end()] + " " + cond + " AND " + out[m_w.end():]
    else:
        m_t = re.search(r"\b(?:group\s+by|order\s+by|limit)\b", out, re.I)
        cut = m_t.start() if m_t else len(out)
        out = out[:cut] + " WHERE " + cond + " " + out[cut:]
    return re.sub(r"\s+", " ", out).strip(), token


def drop_unasked_enum_values(sql: str, question: str) -> tuple[str, list[str]]:
    """IN 목록에서 **질문이 부르지 않은 값**을 걷어낸다. (SQL, 걷어낸 값)

    2026-09-05 DOM-05 실측("파생상품 유형 공모펀드 중 순자산 큰 3개 알려줘"):

        or_attr_desc IN ('재간접', '파생상품')
                          ↑ 질문에 없다

    그 결과 1위가 피델리티글로벌테크놀로지(**재간접형**)로 바뀌었다 — 정답 1위는 NH-Amundi
    코리아2배레버리지(파생형) 7,333억이다. 머리줄에도 '재간접·파생상품 기준' 이라 적혀 답을
    읽는 사람이 모수가 넓어진 것을 알 수는 있으나, **묻지 않은 것을 답한 것**이다.

    🔴 발동은 좁게 — **질문이 그 목록의 값을 하나라도 이름으로 불렀을 때만** 나머지를 걷는다.
       하나도 안 불렀으면 총칭어 질의다(`혼합형` → `IN ('주식혼합형','채권혼합형')` 은 `혼합형
       확정식 치환` 이 일부러 넓힌 것이다). 그 자리를 건드리면 안 되므로 불개입한다.
    """
    q = question.replace(" ", "").casefold()
    dropped: list[str] = []
    out = sql
    for m in list(_IN.finditer(sql)):
        col, body = (m.group(2) or "").lower(), m.group(3)
        if col not in _NAMED_ENUM_COLS:
            continue
        lits = _LIT.findall(body)
        if len(lits) < 2:
            continue
        keep = [l for l in lits if l.replace(" ", "").casefold() in q]
        if not keep or len(keep) == len(lits):
            continue                                  # 아무것도 안 불렀으면 총칭어 질의 — 불개입
        dropped += [l for l in lits if l not in keep]
        body_new = ", ".join("'" + l + "'" for l in keep)
        out = out.replace(m.group(0), m.group(0).replace(body, body_new), 1)
    return out, dropped


def drop_unused_ext_join(sql: str) -> tuple[str, list[str]]:
    """쓰이지 않는 `ext_*` LEFT JOIN 을 걷어낸다. (SQL, 걷어낸 테이블)

    2026-09-05 FND-007 실측 — HCX 가 조인만 걸고 **그 테이블 컬럼을 하나도 안 썼다**:

        SELECT DISTINCT p.itm_no, …, p.fd_nast_suma  FROM public_funds p
        LEFT JOIN ext_fund_page e ON p.itm_no = e.itm_no  WHERE … ORDER BY p.fd_nast_suma DESC

    결과에는 영향이 없지만 **뒤따르는 가드가 통째로 비켜간다** — `ensure_fund_rank_representative`
    는 `join|union` 이 보이면 무조건 빠진다. 그래서 GROUP BY 펀드키가 주입되지 않았고, 답변이
    클래스명을 펀드명처럼 나열했다(`삼성MMF법인제1호 C 클래스`). 2차엔 조인이 없어 기계 조립이 탔다.

    🔴 안전성: `ext_*` 는 `itm_no` **1:1**(ext_fund_page 10,565행 = distinct itm_no 10,565)이라
       LEFT JOIN 이 행을 늘리지 않고, 컬럼을 안 쓰면 결과에 기여하지도 않는다 — 제거는 무해하다.
       **INNER 는 대상이 아니다**(짝 없는 행을 거르므로 제거하면 모수가 넓어진다). 앞선
       `ensure_ext_left_join` 이 INNER 를 LEFT 로 바꾼 **뒤에** 돌아야 한다.
    """
    dropped: list[str] = []
    out = sql
    for m in list(_EXT_JOIN_CLAUSE.finditer(sql)):
        tbl, alias = m.group(1), m.group(2)
        rest = out.replace(m.group(0), " ", 1)
        if re.search(rf"\b{re.escape(alias or tbl)}\.\w+", rest, re.I):
            continue
        out, _ = rest, dropped.append(tbl)
    return out, dropped


def prune_dead_in_literals(sql: str, ctx: RuntimeContext) -> tuple[str, list[str]]:
    """IN 목록에서 **그 컬럼에 없는 값**만 걷어낸다. (보정된 SQL, 걷어낸 값 목록)

    2026-09-04 KG-012 실측 — 재생성 SQL 이 이랬다:

        zrin_ptn_nm = '중국주식' AND zrin_btyp_nm IN ('해외주식형', '국내외혼합')

    `'국내외혼합'` 은 `ovrs_fd_desc` 의 값이라 `zrin_btyp_nm` 에선 **0행에 매칭된다.** 그런데 값 검사가
    이걸 기각해 답변이 통째로 죽었다 — 실측하면 그 SQL 이 낸 답(205펀드/522클래스)이 **정답이었다.**

    🔴 안전성의 근거: OR 가지(=IN 목록)에서 **0행 매칭 값을 빼는 것은 결과를 바꾸지 않는다.** 증명 가능하게
       결과 보존적이라 조용한 오답을 만들 수 없다.
    🔴 불개입: 유효한 값이 하나도 안 남으면 손대지 않는다. 그건 빼는 순간 **모수가 넓어져** 조용한 오답이
       되므로 종전대로 기각해야 한다(단독 등호 `col = '없는값'` 도 같은 이유로 대상이 아니다).
    """
    index = getattr(ctx, "value_index", None) or {}
    if not index:
        return sql, []
    tables = sql_tables(sql)
    dropped: list[str] = []
    out = sql
    for m in list(_IN.finditer(sql)):
        tbl, col, body = m.group(1), m.group(2), m.group(3)
        col_l = col.lower()
        t = next((x for x in ([tbl.lower()] if tbl else tables) if (x, col_l) in index), None)
        if t is None:
            continue
        vals = index.get((t, col_l))
        if vals is None:
            continue
        lits = _LIT.findall(body)
        if len(lits) < 2:
            continue                                  # 단독 값은 빼면 모수가 넓어진다 — 불개입
        keep = [l for l in lits if _norm(l) in vals]
        if not keep or len(keep) == len(lits):
            continue                                  # 전부 죽었으면 기각이 옳다 · 전부 살았으면 할 일 없음
        dropped += [l for l in lits if _norm(l) not in vals]
        body_new = ", ".join("'" + l + "'" for l in keep)
        out = out.replace(m.group(0), m.group(0).replace(body, body_new), 1)
    return out, dropped


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
            own, spread = _owner_column(index, t, col_l, lit.strip("%"))
            out.append(ValueViolation(t, col_l, lit, hint, own, spread))
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
            own, spread = _owner_column(index, t, col_l, lit)
            out.append(ValueViolation(t, col_l, lit, hint, own, spread))
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
class DateGap:
    """날짜 컬럼 창이 0행일 때의 수록 범위 — 창 양옆에 실제로 있는 가장 가까운 값과, 창이 판정일 이전이면 남은 경과분 수.

    2026-09-05 #68 — "지난달에 만기된 채권" 의 창(20260701~20260731)은 컬럼 전체 범위(20260628~20830605) **안**이라
    min/max 대조로는 사유가 안 나온다. 창 바로 아래·위의 실제 값(20260628 · 20260820)을 보이면 사용자가 빈 자리를 본다.
    만기 경과 종목이 61종목만 남은 것은 마스터 정리(domestic_bonds.yaml §mat_dt: 소멸 25,429종목 중 67.5%가 경과분)의 결과다.
    """
    col: str
    lo: int
    hi: int
    below: int | None                      # 창 아래에서 가장 가까운 실제 값 (없으면 None)
    above: int | None                      # 창 위에서 가장 가까운 실제 값
    past_kept: int | None = None           # 창이 판정일 이전일 때 — 판정일 이전 값이 남아 있는 종목 수 (mat_dt 만)


@dataclass
class ZeroRowDiagnosis:
    counts: list[tuple[str, int]]          # (조건, 단독 적용 시 건수)
    total: int                             # 조건 없이 (FROM 만) 건수
    gaps: list[DateGap] | None = None      # 0행인 날짜 창의 수록 범위 (#68)

    def text(self) -> str:
        gap_txt = " ".join(
            f"[{g.col} {g.lo}~{g.hi} 수록 없음 — 가장 가까운 값 아래 {g.below} · 위 {g.above}"
            + (f" · 판정일 이전 잔존 {g.past_kept}종목" if g.past_kept is not None else "") + "]"
            for g in (self.gaps or []))
        if not self.counts:
            return gap_txt
        alive = [(c, n) for c, n in self.counts if n > 0]
        dead = [(c, n) for c, n in self.counts if n == 0]
        bits = [f"{c} → {n:,}건" for c, n in self.counts]
        head = "조건별 단독 조회: " + " / ".join(bits)
        if gap_txt:
            head += " " + gap_txt
        if dead:
            return head + f". 값 자체가 없는 조건: {', '.join(c for c, _ in dead)}."
        if len(alive) >= 2:
            return head + ". 각 조건은 존재하나 동시에 만족하는 상품이 없습니다."
        return head

    def gap_text(self) -> str | None:
        """날짜 창 공백 사유 — 사용자 문장. 창은 표기용 날짜로, 가장 가까운 실제 값을 병기한다."""
        if not self.gaps:
            return None
        out = []
        for g in self.gaps:
            lab = _COL_KO.get(g.col, g.col)
            win = _ymd_text(g.lo) if g.lo == g.hi else f"{_ymd_text(g.lo)}~{_ymd_text(g.hi)}"
            near = " · ".join(_ymd_text(v) for v in (g.below, g.above) if v is not None)
            s = f"{lab}{_ga(lab)} {win}인 상품은 수록되어 있지 않습니다"
            s += f" (수록된 가장 가까운 {lab}: {near})." if near else "."
            if g.past_kept is not None and g.col == "mat_dt":
                s += (f" 판정일 {BUYABLE_CUTOFF} 이전에 만기된 종목은 데이터에 {g.past_kept:,}종목만 남아 있고"
                      "(만기 경과분은 마스터에서 정리됩니다), 만기 후 상환 여부 같은 사후 상태는 수록되어 있지 않습니다.")
            out.append(s)
        return " ".join(out)

    def user_text(self) -> str | None:
        """사용자 답변에 붙일 자연어 사유 한 문장 — 개발자 표기(SQL 조각) 금지.

        2026-08-31 밤 리드 결정: 0행 사유는 답변에 싣되 '조건별 단독 조회: …' 류 개발자
        텍스트로는 내보내지 않는다. SQL 조각을 한국어로 옮기지 못하는 조건이 하나라도 끼면
        구체 서술을 포기하고 일반 문장으로 낮춘다 — 어색한 반역(半譯)보다 안전하다.
        <> 제외절(고위험제외·수익률정상 주입분)은 사용자가 물은 조건이 아니므로 열거에서 뺀다.
        날짜 창 공백(#68)이 있으면 그것이 사유다 — 창 옆의 실제 값을 보이는 문장이 '동시에 만족하는 상품이 없다' 보다 정확하다."""
        if self.gaps:
            return self.gap_text()
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
    "isu_dt": "발행일", "crd_grd_dt": "신용등급 부여일",
}


def _ymd_text(v: int) -> str:
    s = str(int(v))
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 else s


# 날짜 창 조건 — `col BETWEEN a AND b` / `col op v` / `col = v` (정수 YYYYMMDD). 컬럼은 *_dt 관례로 판정한다.
_H_DATE_BETWEEN = re.compile(r"^([A-Za-z_]\w*_dt)\s+BETWEEN\s+(\d{8})(?:\.0)?\s+AND\s+(\d{8})(?:\.0)?$", re.I)
_H_DATE_CMP = re.compile(r"^([A-Za-z_]\w*_dt)\s*(>=|<=|=|<|>)\s*(\d{8})(?:\.0)?$", re.I)


def _date_window_of(cond: str) -> tuple[str, int, int] | None:
    """조건 하나를 (컬럼, lo, hi) 창으로. 한쪽만 있는 부등호는 반대쪽을 0/99999999 로 연다."""
    c = _H_TRIM.sub(r"\1", cond.strip())
    m = _H_DATE_BETWEEN.match(c)
    if m:
        return m.group(1).lower(), int(m.group(2)), int(m.group(3))
    m = _H_DATE_CMP.match(c)
    if not m:
        return None
    col, op, v = m.group(1).lower(), m.group(2), int(m.group(3))
    if op == "=":
        return col, v, v
    if op in (">=", ">"):
        return col, v + (op == ">"), 99999999
    return col, 0, v - (op == "<")


def _date_gap(con: sqlite3.Connection, frm: str, col: str, lo: int, hi: int) -> DateGap:
    """창 양옆의 실제 값 + (창이 판정일 이전이면) 판정일 이전 잔존 종목 수. 0값(미수록)은 값으로 세지 않는다."""
    below = con.execute(f"SELECT MAX({col}) FROM {frm} WHERE {col} > 0 AND {col} < ?", (lo,)).fetchone()[0]
    above = con.execute(f"SELECT MIN({col}) FROM {frm} WHERE {col} > ?", (hi,)).fetchone()[0]
    cutoff = int(BUYABLE_CUTOFF.replace("-", ""))
    kept = None
    if col == "mat_dt" and hi < cutoff:
        kept = con.execute(f"SELECT COUNT(DISTINCT pd_no) FROM {frm} WHERE mat_dt > 0 AND mat_dt < ?", (cutoff,)).fetchone()[0]
    return DateGap(col, lo, hi, int(below) if below else None, int(above) if above else None, kept)
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
        word = (_CMP_DATE_KO if (col in _DATE_COLS or col.endswith("_dt")) else _CMP_KO)[op]
        return f"{lab}{_ga(lab)} {val} {word}"
    m = _H_LIKE.match(c)
    if m:
        col = m.group(1).lower()
        return f"{_COL_KO[col]}에 '{m.group(2)}' 포함" if col in _COL_KO else None
    return None


def diagnose_zero_rows(sql: str, con: sqlite3.Connection | None = None) -> ZeroRowDiagnosis | None:
    """단순 SELECT(서브쿼리·UNION·HAVING 없음)만. 조건이 하나면 진단할 게 없다(None) — 단 날짜 창 공백(#68)은 예외."""
    if _COMPLEX.search(sql):
        return None
    m = _SIMPLE.match(sql.strip().rstrip(";"))
    if not m or not m.group("where"):
        return None
    # 🔴 2026-09-05 #68 — BETWEEN 의 AND 를 조건 경계로 갈랐다. `mat_dt BETWEEN 20260701 AND 20260731` 이
    #    "mat_dt BETWEEN 20260701"(오류 → 버림) 과 "20260731"(참 → 21,882건) 으로 갈려 "조건 각각은 있으나 동시엔 없다" 는
    #    **거짓 사유**가 나갔다(#67 과 같은 부류 — 사유 침묵이 아니라 사유 날조). BETWEEN 을 접고 가른다.
    fold = "\x01"
    folded = re.sub(r"(\bBETWEEN\s+\S+)\s+AND\s+(\S+)", rf"\1{fold}\2", m.group("where").strip(), flags=re.I)
    conj = [c.replace(fold, " AND ") for c in split_conjuncts(folded)]
    if len(conj) < 2:
        # 🔴 2026-09-05 #66 — 최상위가 OR 한 덩어리면 여기서 통째로 포기했다. "우주항공·방산 쪽 기업이 발행한
        #    채권" 이 `pd_pbcm LIKE '%우주항공%' OR pd_pbcm LIKE '%방산%'` 0행으로 끝났고, 사용자는 사유 없는
        #    "확인되지 않습니다" 한 줄만 받았다 — 어느 항목을 뒤졌는지조차 알 수 없다. OR 가지로 갈라 진단한다.
        #    (가지가 하나뿐이면 진단할 게 없다 — 단 그 하나가 날짜 창이면 아래 공백 진단이 사유가 된다.)
        head = (conj[0] if conj else "").strip()
        while head.startswith("(") and head.endswith(")") and len(split_disjuncts(head)) == 1:
            head = head[1:-1].strip()                       # 통째로 감싼 괄호만 벗긴다
        disj = [d.strip() for d in split_disjuncts(head) if d.strip()]
        if len(disj) >= 2:
            conj = disj
    frm = m.group("from").strip()
    own = con is None
    con = con or connect_readonly()
    try:
        # ── 날짜 창 공백(#68) — 창 조건이 단독으로 0행이면 창 옆의 실제 값을 잰다. 조건이 하나뿐이어도 이것은 사유다.
        gaps: list[DateGap] = []
        for c in conj:
            w = _date_window_of(c)
            if not w:
                continue
            try:
                if con.execute(f"SELECT count(*) FROM {frm} WHERE {c}").fetchone()[0] == 0:
                    gaps.append(_date_gap(con, frm, *w))
            except sqlite3.Error:
                continue
        if len(conj) < 2:
            return ZeroRowDiagnosis([], 0, gaps) if gaps else None
        total = con.execute(f"SELECT count(*) FROM {frm}").fetchone()[0]
        counts = []
        for c in conj:
            try:
                n = con.execute(f"SELECT count(*) FROM {frm} WHERE {c}").fetchone()[0]
            except sqlite3.Error:
                n = -1
            counts.append((c, n))
        return ZeroRowDiagnosis([(c, n) for c, n in counts if n >= 0], total, gaps or None)
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


def _top_commas(expr: str) -> int:
    """괄호 밖 쉼표 수 — SELECT 항목 개수를 세는 데 쓴다."""
    depth = n = 0
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            n += 1
    return n


def _apply_one(sql: str, enf: dict, subs: dict, in_union: bool = False) -> tuple[str, bool]:
    """액션 하나를 SQL 한 가지(branch)에 적용. 대상이 정확히 잡힐 때만 손댄다(원자성).

    🔴 UNION 가지 안에서는 **SELECT 항목 수를 바꾸지 않는다.** 2026-09-03 P0-2a paired 실측:
       `COUNT(*)` → `COUNT(DISTINCT 펀드키) AS "펀드수", COUNT(*) AS "클래스수"` 가 한 가지에만
       적용돼 양쪽 열 수가 어긋났고 SQL 이 통째로 실행 불가가 됐다(KG-025·X8).
       코드 가드는 UNION 을 통째로 피해서 겪지 않던 문제다 — 가지별 적용의 대가다.
       슬롯이 `sql_union`(열 수 보존판)을 선언했으면 그것을 쓰고, 없으면 **불개입**한다.
    """
    action = enf.get("action")
    body = str(enf.get("sql") or "")
    if in_union and enf.get("sql_union"):
        body = str(enf["sql_union"])
    for k, v in subs.items():
        body = body.replace("{" + k + "}", str(v))
    if action == "inject_where":
        return _inject_where(sql, body)
    if action == "replace_expr":
        # 🔴 `from` 은 리터럴, `from_pattern` 은 정규식이다. 별칭이 따라붙는 표현
        #    (`COUNT(*) AS 개수` · `COUNT(*) as cnt`)은 리터럴로는 못 잡는다 —
        #    `COUNT(*)` 만 바꾸면 원래 별칭이 남아 `AS "펀드수" AS 개수` 로 문법이 깨진다.
        #    2026-09-03 P0-2a paired 실측(X9·X22). 코드 가드는 별칭까지 먹는 정규식을 쓰고 있었다.
        pat, src = enf.get("from_pattern"), str(enf.get("from") or "")
        if pat:
            ms = list(re.finditer(str(pat), sql, flags=re.I))
            if len(ms) != 1:
                return sql, False
            start, end, matched = ms[0].start(), ms[0].end(), ms[0].group(0)
        elif src and sql.lower().count(src.lower()) == 1:
            start = sql.lower().index(src.lower())
            end, matched = start + len(src), src
        else:
            return sql, False           # 0개면 대상 없음, 2개 이상이면 어느 쪽인지 모른다 → 불개입
        if in_union and _top_commas(body) != _top_commas(matched):
            return sql, False           # 열 수가 달라지면 UNION 이 깨진다 — 위 주석 참조
        return sql[:start] + body + sql[end:], True
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
            in_union = len(branches) > 1       # 최상위 UNION 이 있는가
            for i, part in enumerate(branches):
                if _ENF_UNION.fullmatch(part.strip()):
                    continue                   # 구분자는 건너뛴다
                if not _match_when(enf.get("when") or {}, part, question, tables, grounded):
                    continue
                new, ok = _apply_one(part, enf, subs, in_union)
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
