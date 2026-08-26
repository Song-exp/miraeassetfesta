"""네거티브 게이트 — HCX 호출 **전에** 기각할 질의를 기각한다.

규칙 §3: DB 근거가 없거나 기준일 이후면 HCX 를 건너뛰고 즉시 반환.
기각 사유는 문장으로 만들어 think_trace 에 남긴다 — 근거 제시 배점 (BUILD_PLAN §5⑤).

세 게이트:
  ① absent  — 온톨로지 속성 부재 ("위험등급 낮은 해외ETF")
  ② enum    — 화이트리스트 밖 값 ("신용등급 AAAA" · "위험등급 9등급")
  ③ cutoff  — 데이터 기준일(2026-08-22) 이후 시점 질의
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .loader import RuntimeContext

DATA_CUTOFF = "2026-08-22"

# 질의 문구 → 대상 테이블 후보. 🔴 '해외ETF' 가 'ETF' 보다 먼저 (부분 문자열)
_TABLE_HINTS: list[tuple[str, str]] = [
    ("해외ETF", "overseas_etfs"),
    ("해외 ETF", "overseas_etfs"),
    ("해외ETN", "overseas_etfs"),
    ("ETF", "domestic_etfs"),
    ("ETN", "domestic_etfs"),
    ("채권", "domestic_bonds"),
    ("국채", "domestic_bonds"),
    ("회사채", "domestic_bonds"),
    ("국공채", "domestic_bonds"),
    ("특수채", "domestic_bonds"),
    ("펀드", "public_funds"),
]

# 교차질의 힌트 — 구성종목 보유 조건은 외부 Holdings 테이블(ext_*)을 함께 본다는 신호.
# 테이블을 "하나 고르기"가 아니라 "해당하는 전부"로 라우팅한다 (주최 8/24: 교차질의는 한 호출에서 복수 상품군).
_CROSS_HINTS = ("보유한", "보유중", "편입", "구성종목", "담고 있는", "포함된", "들어있는")


def is_cross_query(question: str) -> bool:
    return any(h in question for h in _CROSS_HINTS) or len(detect_tables(question)) >= 2

# 질의 문구 → shared 개체 축. absent 검사의 좌변
_ENTITY_HINTS: list[tuple[str, str]] = [
    ("위험등급", "RiskGrade"),
    ("기초지수", "Index"),
    ("벤치마크", "Index"),
    ("추종", "Index"),
    ("자산군", "AssetClass"),
    ("투자지역", "Region"),
]

# 신용등급 토큰 — 한글 사이의 대문자 시퀀스 (AAAA·AA+ 등)
_CRD_TOKEN = re.compile(r"\b([A-D]{1,4}[+\-0]?)\b")
_RISK_GRADE = re.compile(r"(?:위험\s*등급|위험등급)\s*(\d+)\s*등급|(\d+)\s*등급")
# 기준일 2026-08-22 — 2026년 8월은 기준일 포함 월이라 허용, 9월 이후만 미래 (2차 데이터 전환 2026-08-25)
_FUTURE = re.compile(r"(202[7-9]|20[3-9]\d)\s*년|2026\s*년\s*(?:9|10|11|12)\s*월")


@dataclass
class GateResult:
    rejected: bool
    reason: str = ""       # think_trace 용 — 기각 근거 문장
    answer: str = ""       # 사용자에게 나갈 답


def detect_tables(question: str) -> list[str]:
    found: list[str] = []
    q = question
    for hint, table in _TABLE_HINTS:
        if hint in q and table not in found:
            found.append(table)
            q = q.replace(hint, " ")  # '해외ETF' 소진 후 'ETF' 재매칭 방지
    return found


def detect_entities(question: str) -> list[str]:
    return [e for hint, e in _ENTITY_HINTS if hint in question]


def check(question: str, ctx: RuntimeContext) -> GateResult:
    # ③ cutoff — 기준일 이후 시점을 묻는 질의
    if _FUTURE.search(question):
        return GateResult(
            rejected=True,
            reason=f"데이터 기준일({DATA_CUTOFF}) 이후 시점 질의 — DB 에 근거 없음",
            answer=f"제공된 데이터의 기준일은 {DATA_CUTOFF}입니다. 이후 시점의 정보는 확인할 수 없습니다.",
        )

    tables = detect_tables(question)
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

    # ② enum — 신용등급 화이트리스트 (채권 문맥 또는 '신용등급' 명시)
    if ctx.crd_grades and ("신용등급" in question or "domestic_bonds" in tables):
        for tok in _CRD_TOKEN.findall(question):
            if tok not in ctx.crd_grades:
                return GateResult(
                    rejected=True,
                    reason=f"'{tok}' 는 CRD_GRD enum {len(ctx.crd_grades)}종에 없음 — 존재하지 않는 등급",
                    answer=f"'{tok}'는 존재하지 않는 신용등급입니다. 유효 등급은 AAA~C 체계입니다.",
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
