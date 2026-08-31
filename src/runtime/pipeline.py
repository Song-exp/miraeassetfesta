"""파이프라인 오케스트레이터 — 단계별 실행 + think_trace 조립.

think_trace 는 각 단계가 **실제로 한 일**의 로그다 (LLM 생성물 아님 — hcx/client.py 원칙).
Plan(SQL 생성)·Answer(문장 생성)는 planner 인터페이스 뒤에 있다 — HCX 미연결 환경에서도
Ground·Gate·Guard·Execute 는 전부 동작·테스트 가능하다.
"""

from __future__ import annotations

import inspect
import os
import re
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
    """
    if _MAT_LOWER.search(sql):
        return sql, False
    m = _MAT_UPPER.search(sql)
    if not m or int(m.group(1)) <= CUTOFF_INT:
        return sql, False
    s, e = m.span()
    return f"{sql[:s]}(mat_dt > {CUTOFF_INT} AND {sql[s:e]}){sql[e:]}", True


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
    preds = list(_SQL_GRADE_CMP.finditer(sql))
    if len(preds) != 1 or _SQL_GRADE_IN.search(sql):
        return sql, False
    if len(grades) == 1 and preds[0].group(1) == "=" and preds[0].group(2) == grades[0]:
        return sql, False                        # 'AAA 이상' = 'AAA' — 이미 맞다
    s, e = preds[0].span()
    repl = "TRIM(crd_grd) IN (" + ", ".join(f"'{g}'" for g in grades) + ")"
    return sql[:s] + repl + sql[e:], True


_BACKSTOP_Q = re.compile(r"(?:정부|나라|국가)\s*(?:가|이|의|에서)?\s*(?:책임|보증|갚|지급)|정부\s*보증")
_BACKSTOP_ANCHOR = re.compile(r"(?:TRIM\(\s*)?std_pd_mcls_nm\s*\)?\s*=\s*'국공채'", re.I)
_BACKSTOP_PARTS = [                              # (SQL 에 이미 있는지 볼 토큰, 주입식) — 신용보강 규칙의 A~C층
    ("한국은행", "COALESCE(TRIM(pd_pbcm),'')='한국은행'"),
    ("(정부보증)", "pd_nm LIKE '%(정부보증)%'"),
    ("한국주택금융공사", "TRIM(pd_pbcm) IN ('한국주택금융공사','한국토지주택공사','한국산업은행','(주)중소기업은행')"),
]
_RANK_Q = re.compile(r"추천|순으로|순위|톱|top\s*\d|\d+\s*(?:개|종목|가지)", re.I)
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
        excl = []
        if re.search(r"applied_yield", sql, re.I) and not re.search(r"applied_yield\s*>\s*0", sql):
            excl.append("applied_yield > 0")
        if "'11'" not in sql:
            excl.append("pd_risk_gcd <> '11'")
        if "C0" not in sql:
            excl.append("COALESCE(TRIM(crd_grd),'') <> 'C0'")
        if "사모" not in sql:
            excl.append("bd_ofr_tcd <> '사모'")
        if excl:
            t = _WHERE_TAIL.search(sql)
            pos = t.start() if t else len(sql)
            sql = sql[:pos].rstrip() + " AND " + " AND ".join(excl) + " " + sql[pos:]
            changed = True
    return sql, changed


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
    if isinstance(v, float) and v.is_integer() and ("_dt" in col or col.endswith("dt") or "date" in col):
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

    sql, lb = ensure_maturity_lower_bound(sql)
    if lb:
        step(f"[Guard] 만기 하한 보정 — mat_dt > {CUTOFF_INT} 주입 (만기일 미수록 0값·만기 경과 행 제외)")
    sql, grades_fixed = expand_grade_comparison(sql, q)
    if grades_fixed:
        step("[Guard] 등급 서열 확장 — 질문의 '이상/이하' 등급 조건이 단일 등급 비교로 좁혀져 TRIM(crd_grd) IN (서열 목록) 으로 확장 (2026-08-31 'A등급 이상'→crd_grd='A-' 실측)")
    sql, backstop_fixed = ensure_credit_backstop(sql, q)
    if backstop_fixed:
        step("[Guard] 신용보강 층 주입 — 정부보강 질의의 WHERE 에서 빠진 층(C 법정 손실보전 기관 등)·랭킹 제외 조건을 주입 (2026-08-31 저녁 재발 실측: C층 탈락으로 1위 5.859% 누락 + 사모/1등급 14.05% 혼입)")
    sql, riskname_fixed = ensure_risk_name_column(sql)
    if riskname_fixed:
        step("[Guard] 위험등급 이름 보강 — SELECT 의 pd_risk_gcd 옆에 pd_risk_nm 추가 (코드 '16' 이 '위험등급 16등급' 으로 노출된 실측 오답 차단 — 답변은 pd_risk_nm 문구 인용)")
    sql, limited = ensure_limit(sql)
    if limited:
        step(f"[Guard] LIMIT 누락 — 상한 {MAX_ROWS} 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)")
    result.sql = sql
    # 🔴 SQL 은 자르지 않는다. 잘린 SQL 로는 조건식이 틀렸는지 KG 매핑이 틀렸는지 구분할 수 없고,
    #    그 구분이 곧 팀이 챗봇을 검토하는 방법이다 (2026-08-30). 채점자에게도 근거가 된다.
    step("[Plan] SQL 생성 — 아래 문장을 실행합니다\n" + sql)

    err = validate_sql(sql)
    if not err:
        # ①-b 컬럼 환각(remaining_days 류) — 실행 전 검출해 재생성 기회를 준다 (2026-08-31 paired v2: 실행 실패 8/80)
        unk = guard.unknown_columns(sql, ctx)
        if unk:
            err = "스키마에 없는 컬럼: " + ", ".join(unk[:5])
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
            sql, limited = ensure_limit(raw2)
            result.sql = sql
            step("[Plan] 재생성 SQL — 아래 문장을 실행합니다\n" + sql)
            err = validate_sql(sql)
            if not err:
                unk = guard.unknown_columns(sql, ctx)
                if unk:
                    err = "스키마에 없는 컬럼: " + ", ".join(unk[:5])
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
        answer = "조건에 해당하는 상품이 데이터에서 확인되지 않습니다."
        try:
            diag = guard.diagnose_zero_rows(sql)
        except sqlite3.Error:
            diag = None
        if diag and diag.text():
            step(f"[Diagnose] 0행 원인 — {diag.text()}")
            answer += " " + diag.text()
        step("[Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'")
        result.think_trace = "\n".join(trace)
        result.answer = answer
        return result

    answer_rules = ctx.answer_context(tables or list(TABLES))
    # 옛 2인자 플래너(테스트 프로브 등)와 호환 — answer_rules 를 받지 않으면 넘기지 않는다
    if _accepts_answer_rules(planner):
        result.answer = planner.compose_answer(q, rows, answer_rules)
    else:
        result.answer = planner.compose_answer(q, rows)
    step("[Answer] 답변 생성 완료" + (f" — 답변 규칙 {len(answer_rules):,}자 적용 ({', '.join(tables) or '전체'})" if answer_rules else ""))
    result.think_trace = "\n".join(trace)
    return result
