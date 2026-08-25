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

MAX_ROWS = 30            # retrieved_context 폭주 방지 — 근거는 표본이면 충분하다
SQL_TIMEOUT_S = 10.0


@dataclass
class PipelineResult:
    question_id: str
    question: str
    retrieved_context: str = ""
    think_trace: str = ""
    answer: str = ""


class Planner(Protocol):
    """SQL·답변 생성기 — HCX 구현체를 여기 꽂는다. 시그니처 외에 아무것도 가정하지 않는다."""

    def plan_sql(self, question: str, grounding: str) -> str: ...
    def compose_answer(self, question: str, rows: str) -> str: ...


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


def _ground(question: str, ctx: RuntimeContext) -> tuple[list, list[str]]:
    """KG 개체 매핑 — 질의 문자열에서 노드 레이블을 찾는다 (긴 레이블 우선)."""
    hits, lines = [], []
    # 자동 생성 노드(Idx_a_/Idx_v_/Org_issuer_)는 수천 개라 짧은 라벨의 오매칭을 막기 위해 길이 하한을 높인다
    def _min_len(node):
        return 4 if node.node_id.startswith(("Idx_a_", "Idx_v_", "Org_issuer_")) else 3

    candidates = sorted(
        ((label, node) for node in ctx.kg_nodes for label in node.labels if len(label) >= _min_len(node)),
        key=lambda x: -len(x[0]),
    )
    consumed = question
    for label, node in candidates:
        if label in consumed:
            hits.append(node)
            consumed = consumed.replace(label, " ")
            aliases = ctx.kg_aliases.get(node.node_id, [])
            where = " · ".join(f"{t}.{c}={raw!r}" for t, c, raw in aliases[:4])
            lines.append(f"'{label}' → {node.node_id} ({node.node_type}) → {where}")
    return hits, lines


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

    # Ground — 기각 여부와 무관하게 매핑 결과는 근거로 남긴다
    hits, ground_lines = _ground(q, ctx)
    if ground_lines:
        step("[Ground] KG 개체 매핑 — " + " / ".join(ground_lines))
    else:
        step("[Ground] KG 개체 매핑 — 매칭 없음")

    # Gate — HCX 호출 0회 기각 경로
    g = gate.check(q, ctx)
    if g.rejected:
        step(f"[Gate] 기각 — {g.reason}")
        step("[Decision] HCX 호출 없이 종료 (근거는 Gate 단계)")
        result.think_trace = "\n".join(trace)
        result.answer = g.answer
        return result
    tables = gate.detect_tables(q)
    cross = gate.is_cross_query(q)
    step(f"[Gate] 통과 — 대상 테이블 추정 {tables or '미특정'}"
         + (" · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)" if cross else ""))

    if planner is None:
        step("[Plan] SQL 생성기 미연결 — 답변 보류 (Ground·Gate 결과는 유효)")
        result.think_trace = "\n".join(trace)
        result.answer = "현재 시스템 구축 중으로 이 질의에는 답변을 제공할 수 없습니다."
        return result

    grounding = "\n".join(ground_lines)
    sql = planner.plan_sql(q, grounding)
    step(f"[Plan] SQL 생성 — {sql[:120]}")

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

    result.answer = planner.compose_answer(q, rows)
    step("[Answer] 답변 생성 완료")
    result.think_trace = "\n".join(trace)
    return result
