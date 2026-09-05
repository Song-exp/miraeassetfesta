"""고객 어투 — 거절·되묻기 답변의 문장 규칙 (2026-09-05).

배경: 거절 답변이 코드 10곳·yaml 3곳에 흩어져 각자 다른 어투였고, 여러 곳이 개발자용 사유(컬럼명·행수·원본 레코드명)를
답변에 그대로 붙였다. 고객에게 나가는 문장은 **결론 → 이유 → 대안** 세 문장이고, 개발자 표기는 think_trace 로 보낸다.

🔴 결론 문장은 반드시 `pipeline._REFUSAL_ANSWER` 가 잡는 표현('확인할 수 없습니다' 등)을 쓴다 — 오거절 교정 가드
   (ensure_rows_answered) 가 그 정규식으로 거절문을 알아본다. '확인해 드릴 수 없습니다' 는 안 잡힌다(2026-09-05 실측).
🔴 되묻기(Clarify)는 이 형식을 타지 않는다 — 역질문은 유효 답변이라 '확인할 수 없습니다' 로 시작하면 거절로 채점된다.
"""
from __future__ import annotations

import re

# 괄호 안에 snake_case 식별자(컬럼명)가 든 조각 — "(crd_grd)" · "기준가(bns_bpr, 기준일 단일 스냅샷)" · "(cu_charge_etc_rt)"
_IDENT_PAREN = re.compile(r"\s*\((?=[^()]*\b[a-z][a-z0-9]*_[a-z0-9_]+\b)[^()]*\)")
_SPACES = re.compile(r"[ \t]{2,}")


def customer_text(text: str) -> str:
    """개발자 표기를 뺀 고객 문장. 컬럼명 괄호만 뗀다 — 숫자·연도·통화 괄호("(KRW)"·"(1~6등급)")는 고객 정보라 남긴다."""
    if not text:
        return text
    out = _IDENT_PAREN.sub("", text)
    out = _SPACES.sub(" ", out)
    return out.replace(" .", ".").strip()


def refusal(conclusion: str, reason: str = "", alternative: str = "") -> str:
    """결론 → 이유 → 대안. 빈 조각은 건너뛰고, 문장 끝 마침표를 보장한다."""
    parts = []
    for p in (conclusion, reason, alternative):
        p = customer_text((p or "").strip())
        if not p:
            continue
        if p[-1] not in ".?!":
            p += "."
        parts.append(p)
    return " ".join(parts)


def after_cutoff(cutoff: str) -> str:
    """기준일 이후 시점 질의 — 결정층 두 자리(SQL 생성기 미연결 · 시점·전망 판정)가 같은 문장을 쓴다."""
    return refusal(
        f"요청하신 시점은 제공된 데이터의 기준일({cutoff}) 이후라 확인할 수 없습니다",
        "데이터는 기준일까지의 내용만 담고 있습니다",
        "기준일 이전 기간이나 만기일 기준으로 다시 질문해 주시면 조회해 드리겠습니다",
    )
