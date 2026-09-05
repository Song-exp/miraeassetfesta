# -*- coding: utf-8 -*-
"""부재축 선언 어휘 검증 — 미탐(문형 전건 기각) · 오폭(답할 수 있는 질문 전건 통과) · 기존 문항 전수 대조.

2026-09-06 분류 전수조사에서 신설한 hasTradingVolume · hasMinimumInvestment 를 재는 자리.
기존 넷(등급이력·금리이력·업종·이자주기)이 쓴 검증 형식을 그대로 따른다 — 문형을 곱해서 세고,
오폭 후보를 따로 세고, eval/*.jsonl 전건에서 신규 기각이 0 인지 본다.
"""
import os
import sys
import json
import glob

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")

from runtime.loader import load_context   # noqa: E402
from runtime import gate                  # noqa: E402

ctx = load_context()
BOND = ["domestic_bonds"]

# ── 기각돼야 하는 문형 (미탐 검사) ──────────────────────────────────────────────
MUST_REJECT = {
    "hasTradingVolume": [
        "거래가 제일 활발한 채권 알려줘",
        "거래 많이 되는 채권 뭐야",
        "거래가 활발한 채권 5개 추천해줘",
        "유동성 좋은 채권 추천해줘",
        "유동성이 풍부한 채권은 뭐가 있어?",
        "환금성 좋은 채권 알려줘",
        "거래량 많은 채권 5개",
        "거래대금이 큰 채권 알려줘",
        "체결 건수가 많은 채권은?",
        "거래 회전율 높은 채권 뭐야",
        "매매가 활발한 채권 알려줘",
        "거래가 잘 안 되는 채권은 뭐야",
        "거래가 뜸한 채권 알려줘",
        "하루에 얼마나 거래돼?",
        "몇 번이나 거래되는지 알려줘",
        "거래 빈도 높은 채권 5개",
    ],
    "hasMinimumInvestment": [
        "채권 최소 얼마부터 살 수 있어?",
        "최소 투자금액이 얼마야",
        "최소투자금액 알려줘",
        "최소 매수 단위가 어떻게 돼?",
        "매수 단위 알려줘",
        "채권 거래 단위가 뭐야",
        "몇 원부터 살 수 있어?",
        "얼마부터 매수할 수 있어?",
        "얼마 이상부터 투자할 수 있나요",
        "최소 가입금액 얼마야",
        "최소 매수 수량이 몇 개야",
    ],
}

# ── 통과해야 하는 오폭 후보 (답할 수 있는 질문) ─────────────────────────────────
MUST_PASS = [
    # 거래 계열 — 거래구분(장내/장외)·거래된 가격은 전부 답할 수 있다
    "장내에서 실제 거래된 가격이 가장 비싼 채권이 뭐야?",   # 사고 #79 — 가격 축
    "장내에서 거래되는 채권 몇 종목이야",
    "장외 채권 알려줘",
    "거래구분이 장내인 채권 알려줘",
    "장내 종가 알려줘",
    "매매단가 높은 채권 5개",
    "지금 살 수 있는 채권 중 수익률 5% 넘는 건 몇 개야?",
    "채권 거래할 때 장내랑 장외 차이가 뭐야",
    # 금액 계열 — 예산을 말하며 추천을 구하는 꼴은 답한다(#78: 금액으로 안 좁혔다는 고지를 달고 추천)
    "100만원으로 살 수 있는 채권 추천해줘",
    "1000만원으로 채권 사려는데 추천해줘",
    "1억으로 살 수 있는 안전한 채권 알려줘",
    # '최소' 가 금액이 아닌 축에 붙는 꼴
    "최소 만기가 몇 년이야?",
    "잔존만기 최소인 채권 알려줘",
    "최소 5% 이상 수익률 채권 알려줘",
    "표면금리 최소값이 얼마야",
    "수익률 얼마야",
    "제일 싼 채권 알려줘",
    "채권 가격 얼마야",
]


def rejected(q):
    r = gate.check(q, ctx, BOND)
    return (r.rejected, r.reason)


print("=" * 96)
print("부재축 어휘 검증 — 2026-09-06")
print("=" * 96)

fail = 0
for prop, qs in MUST_REJECT.items():
    ok = 0
    for q in qs:
        rej, why = rejected(q)
        if rej and prop in why:
            ok += 1
        else:
            print(f"  ❌ 미탐 [{prop}] {q}  →  {'다른 선언이 잡음: ' + why[:60] if rej else '통과(기각 안 됨)'}")
            fail += 1
    print(f"[미탐] {prop}: {ok}/{len(qs)} 기각")

ok = 0
for q in MUST_PASS:
    rej, why = rejected(q)
    if rej:
        print(f"  ❌ 오폭 {q}  →  {why[:90]}")
        fail += 1
    else:
        ok += 1
print(f"[오폭] 답할 수 있는 질문: {ok}/{len(MUST_PASS)} 통과")

# ── 기존 문항 전수 대조 — 신규 기각 0 이어야 한다 ──────────────────────────────
# 🔴 실제 라우팅을 태운다. 게이트의 absent 분기는 테이블이 하나로 좁혀질 때만 도는데(gate.check ①-0),
#    테이블을 손으로 채권이라 못박고 재면 다른 상품군 문항("거래 제일 활발한 ETF")까지 채권 선언에
#    걸려 오폭으로 잡힌다 — 측정 도구가 만든 가짜다. 라우터가 정한 테이블로 재야 서비스와 같다.
from runtime.router import route          # noqa: E402

NEW = ("hasTradingVolume", "hasMinimumInvestment")
n_q = n_bond = n_new = 0
for path in sorted(glob.glob("eval/*.jsonl")):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        q = (json.loads(line).get("question") or "").strip()
        if not q:
            continue
        n_q += 1
        tables = route(q, ctx).tables
        if tables == BOND:
            n_bond += 1
        r = gate.check(q, ctx, tables)
        if r.rejected and any(p in r.reason for p in NEW):
            print(f"  ❌ 신규 기각 [{path}] {q}  →  {r.reason[:80]}")
            n_new += 1
            fail += 1
print(f"[전수] eval {n_q}문항(채권 라우팅 {n_bond}) · 새 선언에 걸린 기존 문항 {n_new}건")

print("=" * 96)
print("✅ 전건 통과" if not fail else f"❌ 실패 {fail}건")
sys.exit(1 if fail else 0)
