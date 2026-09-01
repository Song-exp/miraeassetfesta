"""네거티브 게이트 — HCX 호출 **전에** 기각할 질의를 기각한다.

규칙 §3: DB 근거가 없거나 기준일 이후면 HCX 를 건너뛰고 즉시 반환.
기각 사유는 문장으로 만들어 think_trace 에 남긴다 — 근거 제시 배점 (BUILD_PLAN §5⑤).

세 게이트:
  ① absent  — 온톨로지 속성 부재 ("위험등급 낮은 해외ETF")
  ② enum    — 신용등급은 **표준표**(credit_grade_scale.csv)로 판정 ("AAAA" 는 표에 없는 등급 · "BB+" 는 표에 있으나 데이터 0건 · "CB" 는 등급 모양이 아님)
              위험등급은 0~6
  ③ cutoff  — 데이터 기준일(2026-08-22) 이후 시점 질의.
              🔴 2026-08-30: 여기서 **미리 기각하지 않는다**. "2027년 만기 채권" 은 만기 질문이고 채권에서 가장 흔한데
              연도만 보고 막으면 전부 죽는다(전수조사 §2-B). 미래 날짜를 가진 컬럼은 이 DB 에서 mat_dt 하나뿐이므로,
              HCX 가 쓴 SQL 에서 그 연도가 mat_dt 조건에 쓰였는지를 pipeline 이 **사후 검사**한다
              (future_tokens · sql_uses_as_maturity). 추가 호출 0회, 역질문 없음.

상품군 탐지(종전 _TABLE_HINTS 단어 11개)는 router.route 로 옮겼다 — 단어 목록으로 판정하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .loader import RuntimeContext

DATA_CUTOFF = "2026-08-22"

# 교차질의 힌트 — 구성종목 보유 조건은 외부 Holdings 테이블(ext_*)을 함께 본다는 신호.
# 테이블을 "하나 고르기"가 아니라 "해당하는 전부"로 라우팅한다 (주최 8/24: 교차질의는 한 호출에서 복수 상품군).
_CROSS_HINTS = ("보유한", "보유중", "편입", "구성종목", "담고 있는", "포함된", "들어있는",
                # 🔴 2026-08-31 서버 실측 — "Li Auto 담은 국내 ETF" 가 교차로 안 잡혀 종목 노드가
                #    규칙 E(대상 테이블 alias 없음)에 걸려 버려졌다. '담은' 계열 표면형 보강.
                "담은", "담긴", "포함한", "보유하")


def detect_tables(question: str, ctx: RuntimeContext | None = None) -> list[str]:
    """호환용 — router.route 의 결과. 미특정이면 빈 목록(종전 의미 유지)."""
    from .loader import load_context
    from .router import route

    r = route(question, ctx or load_context())
    return r.tables if r.decided else []


def is_cross_query(question: str, tables: list[str], groups: int | None = None) -> bool:
    """`tables` 는 라우터가 **정한** 테이블만 (미특정 4테이블을 넘기면 안 된다).
    `groups` 는 서로 다른 상품군의 수(router.Route.groups) — '채권형 ETF' 가 국내/해외 둘로 남은 것은 교차가 아니다."""
    n = len(tables) if groups is None else groups
    return any(h in question for h in _CROSS_HINTS) or n >= 2


# 질의 문구 → shared 개체 축. absent 검사의 좌변
_ENTITY_HINTS: list[tuple[str, str]] = [
    ("위험등급", "RiskGrade"),
    # 2026-08-30 — 이 항목이 없어 absent(CreditGrade, public_funds/ETF) 선언이 한 번도 발동하지 않았다 (검토표 D-4-04).
    #   채권은 absent 에 없으므로 ① 을 지나 ② enum 검사로 간다.
    ("신용등급", "CreditGrade"),
    ("기초지수", "Index"),
    ("벤치마크", "Index"),
    ("추종", "Index"),
    ("자산군", "AssetClass"),
    ("투자지역", "Region"),
]

# 신용등급 토큰 후보 — 한글 사이의 대문자 시퀀스 (AAAA·AA+·CB 등)
# 🔴 \b 를 쓰면 안 된다. 파이썬 re 에서 한글은 단어 문자라 'AAAA인'·'AAAA등급' 의 A 와 '인' 사이에
#    경계가 서지 않아 토큰을 통째로 놓친다 (2026-08-26 실측: "신용등급 AAAA인 채권" 이 게이트를
#    통과해 HCX 를 호출했다). ASCII 영숫자만 경계로 본다.
_CRD_TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-D]{1,4}[+\-0]?)(?![A-Za-z0-9+\-])")   # 꼬리에 +/- 가 더 붙으면(A++) 토큰이 아니라 오기
# 등급의 '모양' — 표준표(AAA·AA+·BBB-·CCC·C …)의 구조: 같은 글자의 반복 + 선택 접미(+/-/0).
# 목록이 아니라 표의 형태에서 온 규칙이다 — 'CB'(전환사채)·'DC'(퇴직연금형) 는 글자가 섞여 등급이 아니고,
# 'AAAA' 는 모양은 맞지만 표에 없다. loader 가 표준표 전체가 이 모양임을 보장한다.
_GRADE_SHAPE = re.compile(r"^([A-D])\1{0,3}[+\-0]?$")
_RISK_GRADE = re.compile(r"(?:위험\s*등급|위험등급)\s*(\d+)\s*등급|(\d+)\s*등급")
# 기준일 2026-08-22 — 2026년 8월은 기준일 포함 월이라 허용, 9월 이후만 미래 (2차 데이터 전환 2026-08-25)
# 연도: '2027년' · '2027.' · '2027-' · '2027/' · '20270101' — 월: '2026년 9월' · '2026-09' · '2026.10'
_FUTURE = re.compile(
    r"(?<!\d)(202[7-9]|20[3-9]\d)(?:\s*년|(?=[.\-/]\d)|(?=\d{4}(?!\d)))"
    r"|(?<!\d)2026(?:\s*년\s*|[.\-/])(?:0?(9)|(1[0-2]))(?:\s*월|(?!\d))"
    # 두 자리 연도 — '28년 12월'·'28년까지'·'28년에 만기' 처럼 연도임이 분명한 꼴만.
    # '잔존만기 28년'·'10년 만기 채권' 의 28년·10년은 기간이라 잡으면 안 된다 (2026-08-31 실측: '28년 12월까지' 를 미탐지 → 연도 오기 20291231 을 못 잡음)
    r"|(?<!\d)(2[7-9]|[3-9]\d)\s*년(?=\s*\d{1,2}\s*월|까지|에\s*만기)"
)
# 상대 시점 — 기준일 2026-08-22 기준. '올해' 는 미래가 아니다
_RELATIVE_FUTURE = {"내년": "2027", "내후년": "2028", "후년": "2028"}
_MAT_DT_WINDOW = 60      # SQL 에서 mat_dt 와 연도 사이의 허용 거리(글자) — BETWEEN·SUBSTR·CAST 어느 형태든 이 안에 든다


@dataclass
class GateResult:
    rejected: bool
    reason: str = ""       # think_trace 용 — 기각 근거 문장
    answer: str = ""       # 사용자에게 나갈 답


def detect_entities(question: str) -> list[str]:
    return [e for hint, e in _ENTITY_HINTS if hint in question]


# ── ③ cutoff — 사후 검사용 도구 (pipeline 이 SQL 생성 뒤에 부른다) ─────────────

def future_tokens(question: str) -> list[str]:
    """질문 속 기준일 이후 시점 — 연도는 'YYYY', 2026년 9~12월은 'YYYYMM'."""
    toks: list[str] = []
    for m in _FUTURE.finditer(question):
        if m.group(1):
            toks.append(m.group(1))
        elif m.group(4):                     # 두 자리 연도 '28년' → 2028
            toks.append(f"20{m.group(4)}")
        else:
            toks.append(f"2026{int(m.group(2) or m.group(3)):02d}")
    for word, year in _RELATIVE_FUTURE.items():
        if word in question and year not in toks:
            toks.append(year)
    return toks


def sql_uses_as_maturity(sql: str, tokens: list[str]) -> bool:
    """토큰 전부가 SQL 의 mat_dt 조건 근처(±60자)에 쓰였는가 = HCX 가 '만기' 로 해석했는가.

    이 DB 에서 미래 날짜를 가진 컬럼은 mat_dt(만기일, 최대 2083-06-05) 하나뿐이다 — 발행일 최대 2026-09-10,
    등급일·종가일 최대 2026-08-21. 그래서 미래 연도가 정당하게 들어갈 자리는 mat_dt 조건밖에 없다.
    """
    anchors = [m.start() for m in re.finditer(r"mat_dt", sql, re.I)]
    if not anchors:
        return False
    for tok in tokens:
        pat = re.escape(tok) if len(tok) == 4 else rf"{tok[:4]}-?{tok[4:]}"   # 'YYYYMM' 은 'YYYY-MM' 표기도 허용
        hit = any(abs(m.start() - a) <= _MAT_DT_WINDOW for m in re.finditer(pat, sql) for a in anchors)
        if not hit:
            return False
    return True


# ── ② enum — 신용등급 판정 ──────────────────────────────────────────────

def classify_grade_token(tok: str, ctx: RuntimeContext) -> str:
    """'not_grade'(등급 모양 아님 — 무시) · 'unknown'(표준표에 없음 — 존재하지 않는 등급) ·
    'no_data'(표준 등급이나 2차 데이터 0건) · 'ok'."""
    if not _GRADE_SHAPE.match(tok):
        return "not_grade"
    if ctx.std_grades and tok not in ctx.std_grades:
        return "unknown"
    if tok in ctx.crd_grades:
        return "ok"
    return "no_data" if ctx.std_grades else "unknown"    # 표준표가 없으면 종전대로 데이터 값만으로 판정


def check(question: str, ctx: RuntimeContext, tables: list[str]) -> GateResult:
    """`tables` 는 라우터가 정한 테이블(미특정이면 빈 목록)."""
    entities = detect_entities(question)

    # ① absent — 온톨로지 속성 부재 (질의가 특정 테이블 하나로 좁혀질 때만 기각)
    if len(tables) == 1:
        for entity in entities:
            why = ctx.absent.get((entity, tables[0]))
            if why:
                prop = ctx.entity_property.get(entity, entity)
                return GateResult(
                    rejected=True,
                    reason=f"온톨로지상 {tables[0]} 클래스에 {prop} 속성이 정의되어 있지 않음 — {why}",
                    answer=f"해당 상품군에는 요청하신 속성이 제공되지 않습니다. ({why.split('→')[0].strip()})",
                )

    # ② enum — 신용등급 (채권 문맥 또는 '신용등급' 명시)
    if ctx.crd_grades and ("신용등급" in question or "domestic_bonds" in tables):
        for tok in _CRD_TOKEN.findall(question):
            kind = classify_grade_token(tok, ctx)
            if kind == "unknown":
                return GateResult(
                    rejected=True,
                    reason=f"'{tok}' 는 신용등급 표준표({len(ctx.std_grades) or len(ctx.crd_grades)}종)에 없음 — 존재하지 않는 등급",
                    answer=f"'{tok}'는 존재하지 않는 신용등급이라 확인할 수 없습니다. 유효 등급은 AAA~C 체계입니다.",
                )
            if kind == "no_data":
                # 기각이 아니라 DB 근거의 즉답 — 표준 등급이지만 2차 데이터에 해당 채권이 없다 (등급서열 규칙)
                return GateResult(
                    rejected=True,
                    reason=f"'{tok}' 는 표준 등급이나 2차 데이터에 0건 — HCX 없이 즉답 (등급서열 규칙)",
                    answer=f"'{tok}' 등급은 신용등급 체계에 있으나, 기준일 {DATA_CUTOFF} 데이터에 해당 등급의 채권이 없습니다.",
                )

    # ④ constant — 상수 컬럼 위반 (2026-08-30 R-5 ① 층). 그 테이블 하나로 라우팅됐을 때만. 규칙은 yaml gate_constants,
    #    triggers 는 정규식(경계 포함 — '유로스탁스50' 지수명은 '유로 거래' 가 아니다)
    if len(tables) == 1:
        for item in ctx.gate_constants.get(tables[0], []):
            for pat in item.get("triggers") or []:
                hit = re.search(pat, question)
                if hit:
                    return GateResult(
                        rejected=True,
                        # reason 키가 있으면 그대로 쓴다 — '상수 컬럼' 서술이 안 맞는 부재형 항목용 (연평균 등)
                        reason=item.get("reason") or f"{tables[0]}.{item['column']} 은(는) 전건 '{item['value']}' 인 상수 컬럼 — 질문의 '{hit.group(0)}' 조건은 데이터에 존재하지 않음 (yaml gate_constants)",
                        answer=item.get("answer") or f"해당 상품군의 {item['column']} 은(는) 전부 '{item['value']}' 이라 요청하신 조건의 상품은 수록되어 있지 않습니다.",
                    )

    # ② enum — 위험등급 범위 0~6 (규칙 §4: 1~5 제약은 오류)
    if "위험등급" in question:
        m = _RISK_GRADE.search(question)
        grade = next((g for g in (m.groups() if m else ()) if g), None)
        if grade is not None and not 0 <= int(grade) <= 6:
            return GateResult(
                rejected=True,
                reason=f"위험등급 {grade} 는 정의 범위(0~6)를 벗어남",
                answer=f"위험등급은 0~6 범위로 정의되어 있습니다. {grade}등급은 존재하지 않습니다.",
            )

    return GateResult(rejected=False)
