"""파이프라인 오케스트레이터 — 단계별 실행 + think_trace 조립.

think_trace 는 각 단계가 **실제로 한 일**의 로그다 (LLM 생성물 아님 — hcx/client.py 원칙).
Plan(SQL 생성)·Answer(문장 생성)는 planner 인터페이스 뒤에 있다 — HCX 미연결 환경에서도
Ground·Gate·Guard·Execute 는 전부 동작·테스트 가능하다.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Protocol

from . import gate
from .loader import EXT_TABLES, TABLES, RuntimeContext, connect_readonly, load_context
from .router import route

MAX_ROWS = 30            # retrieved_context 폭주 방지 — 근거는 표본이면 충분하다
# 플래너가 SQL 대신 되묻기를 돌려줄 때의 접두어 — yaml `clarify` 규칙이 근거. 되묻기는 답변불가 문항의 정답 형태다 (주최 8/25)
CLARIFY_PREFIX = "CLARIFY:"
SQL_TIMEOUT_S = 10.0


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


# ── SQL 사후 검사 — LLM 이 만든 SQL 을 신뢰하지 않는다 ──────────────────
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|pragma|vacuum|replace)\b", re.I
)


def validate_sql(sql: str) -> str | None:
    """위반 사유를 반환. None 이면 통과."""
    s = sql.strip().rstrip(";")
    if ";" in s:
        return "다중 문장 금지"
    if not re.match(r"^\s*select\b", s, re.I):
        return "SELECT 만 허용"
    if _FORBIDDEN.search(s):
        return "금지 키워드 포함"
    used = {t for t in TABLES if re.search(rf"\b{t}\b", s, re.I)}
    if not used:
        m = re.search(r"\bfrom\s+([\w.]+)", s, re.I)
        return f"허용 테이블 밖: {m.group(1) if m else '?'}"
    # FROM/JOIN 에 등장하는 모든 테이블이 마스터 4 + 외부 ext_* 안에 있어야 한다 (교차질의 조인 허용, 그 외 차단)
    for t in re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", s, re.I):
        if t.lower() not in TABLES and t.lower() not in EXT_TABLES:
            return f"허용 테이블 밖: {t}"
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

    candidates = sorted(
        ((label, node) for node in ctx.kg_nodes for label in node.labels if len(label) >= _min_len(node, label)),
        key=lambda x: (not _in_target(x[1]), -len(x[0]), -len(_members(x[1]))),
    )
    consumed = question
    for label, node in candidates:
        if label not in consumed:
            continue
        aliases = target_aliases(ctx, node, target, relations)
        if target and not aliases:
            # E — 대상 테이블에 값이 없는 노드. 레이블을 소비하지 않아 같은 표기의 다른 노드가 잡힐 수 있게 둔다
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
    ("ext_ovs_etf_holdings", "ext_ovs_etf_holdings.isin = overseas_etfs.pd_isin_cd"),
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
    if cross:
        # 구성종목·설명서 조건은 ext_* 에 있고 마스터에는 없다. 조인 키를 주지 않으면
        # 모델이 마스터에 없는 컬럼(constituent 등)을 WHERE 에 써서 실행이 깨진다
        # (2026-08-26 실측: "삼성전자를 보유한 국내 ETF" → OperationalError).
        parts.append(
            "# 교차질의 조인 키 — 구성종목·설명서 조건은 아래 외부 테이블에 있다. 반드시 JOIN 해서 쓴다\n"
            + "\n".join(f"- {k}" for t, k in JOIN_KEYS if t in target)
        )
    rules = ctx.planner_context(target)
    if rules:
        parts.append("# 도메인 규칙 (ontology/*.yaml — 조건식이 있으면 그대로 쓴다)\n" + rules)
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
    schema = ctx.schema_text(target)
    if schema:
        parts.append("# 스키마 — 여기 없는 컬럼은 존재하지 않는다\n" + schema)
    return "\n\n".join(parts)


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


def _execute(sql: str) -> tuple[str, int]:
    con = connect_readonly()
    try:
        con.execute(f"pragma busy_timeout={int(SQL_TIMEOUT_S * 1000)}")
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS)
        head = " | ".join(cols)
        body = "\n".join(" | ".join("" if v is None else str(v) for v in r) for r in rows)
        return f"{head}\n{body}", len(rows)
    finally:
        con.close()


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
    cross = gate.is_cross_query(q, tables, r.groups)

    # Ground — 기각 여부와 무관하게 매핑 결과는 근거로 남긴다 (교차질의면 _ground 가 ext_* 도 대상에 넣는다 — ㉡·E)
    hits, ground_lines = _ground(q, ctx, tables, cross)
    if ground_lines:
        step("[Ground] KG 개체 매핑 — " + " / ".join(ground_lines))
    else:
        step("[Ground] KG 개체 매핑 — 매칭 없음" + (" (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)" if tables else ""))

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

    grounding = build_grounding(ctx, hits, tables, cross, q, future)
    result.grounding = grounding
    blocks = " + ".join(_grounding_blocks(grounding)) or "없음"
    step(f"[Plan] 근거문서 조립 — 대상 {', '.join(tables) or '마스터 4테이블'} · "
         f"{len(grounding):,}자 · 구성: {blocks}")
    raw_sql = planner.plan_sql(q, grounding)

    if raw_sql.strip().upper().startswith(CLARIFY_PREFIX):
        # 되묻기 — yaml clarify 규칙의 다의어에 단서가 없을 때. 추정으로 답하는 것보다 낫다 (역질문은 유효 답변)
        ask = raw_sql.strip()[len(CLARIFY_PREFIX):].strip()
        step(f"[Clarify] 되묻기 — 플래너가 다의어에 단서가 없다고 판단 (근거: 되묻기 규칙 블록)\n{ask}")
        result.think_trace = "\n".join(trace)
        result.answer = ask
        return result

    if future and not gate.sql_uses_as_maturity(raw_sql, future):
        # ③ cutoff 사후 검사 — 연도가 mat_dt 조건에 안 쓰였으면 시점·전망 질의다 (gate §③)
        step(f"[Guard] 기준일 이후 시점 {future} 이(가) SQL 의 mat_dt 조건에 쓰이지 않음 → 만기 질의가 아닌 시점·전망 질의로 판정")
        result.sql = raw_sql
        step("[Decision] HCX SQL 은 만들었으나 기준일 이후 근거가 DB 에 없어 종료")
        result.think_trace = "\n".join(trace)
        result.answer = f"제공된 데이터의 기준일은 {gate.DATA_CUTOFF}입니다. 이후 시점의 정보는 확인할 수 없습니다."
        return result

    sql, limited = ensure_limit(raw_sql)
    if limited:
        step(f"[Guard] LIMIT 누락 — 상한 {MAX_ROWS} 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)")
    result.sql = sql
    # 🔴 SQL 은 자르지 않는다. 잘린 SQL 로는 조건식이 틀렸는지 KG 매핑이 틀렸는지 구분할 수 없고,
    #    그 구분이 곧 팀이 챗봇을 검토하는 방법이다 (2026-08-30). 채점자에게도 근거가 된다.
    step("[Plan] SQL 생성 — 아래 문장을 실행합니다\n" + sql)

    err = validate_sql(sql)
    if err:
        step(f"[Guard] SQL 기각 — {err}")
        result.think_trace = "\n".join(trace)
        result.answer = "질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다."
        return result
    step("[Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT)")

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
        # 규칙 §3 — 조회 0건이면 지어내지 않고 즉시 확인 불가
        step("[Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'")
        result.think_trace = "\n".join(trace)
        result.answer = "조건에 해당하는 상품이 데이터에서 확인되지 않습니다."
        return result

    answer_rules = ctx.answer_context(tables or list(TABLES))
    result.answer = planner.compose_answer(q, rows, answer_rules)
    step("[Answer] 답변 생성 완료" + (f" — 답변 규칙 {len(answer_rules):,}자 적용 ({', '.join(tables) or '전체'})" if answer_rules else ""))
    result.think_trace = "\n".join(trace)
    return result
