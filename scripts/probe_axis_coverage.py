# -*- coding: utf-8 -*-
"""축 대체 환각 — **커버리지 측정**. "지금 어느 정도 잡히나" 에 숫자로 답하는 자리.

축 대체는 '축 + 한정어' 다(신용등급+오른 · 이자+주기 · 거래+량). 축은 무한하지만 **한정어 부류는 유한**하다.
그래서 커버리지는 (한정어 부류 × 축) 행렬로 잰다 — 행렬의 각 칸이 "이 조합을 물으면 막히나" 다.

두 겹을 따로 잰다:
  L1 게이트   — 질문 어휘(absent_properties.vocab). HCX 호출 0회로 끊는다.
  L2 별칭 자백 — 모델이 낸 SQL 의 한글 별칭. L1 을 비켜 간 뒤의 그물.
둘 중 하나라도 잡으면 '막힘' 이다(L2 는 재생성 사유를 돌려주므로 답이 그대로 나가지 않는다).

사용: python scripts/probe_axis_coverage.py
"""
import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")

from runtime.loader import load_context      # noqa: E402
from runtime.router import route             # noqa: E402
from runtime import gate                     # noqa: E402
from runtime.pipeline import axis_alias_confession   # noqa: E402

ctx = load_context()
B = "domestic_bonds"

# ── 행렬 ──────────────────────────────────────────────────────────────────────
# 한정어 부류 6개(지금까지 난 축 대체 사고가 전부 이 안에 든다) × 그 부류로 물을 만한 축.
# 각 칸: (질문, 모델이 낼 법한 대체 SQL 의 별칭). 별칭은 그 축을 흉내 낼 때 붙일 이름이다.
MATRIX = {
    "시계열(추이·변화)": [
        ("최근 6개월 사이에 신용등급이 오른 채권들 정리해줘", "등급변동일"),
        ("한전 채권 금리가 요즘 어떻게 움직였어?", "금리추이"),
        ("채권 가격이 작년보다 올랐어?", "가격변화"),
        ("발행잔액이 어떻게 변했어?", "발행잔액추이"),
        ("듀레이션 추이 알려줘", "듀레이션추이"),
        ("위험등급이 바뀐 채권 있어?", "위험등급변동"),
    ],
    "주기·빈도": [
        ("한국전력공사 채권은 이자를 몇 개월마다 줘?", "이자지급주기"),
        ("이자 언제 들어와?", "이자지급일"),
        ("1년에 몇 번 이자 받아?", "연간지급횟수"),
    ],
    "수량·양": [
        ("거래가 제일 활발한 채권 알려줘", "거래량"),
        ("거래량 많은 채권 5개", "거래량"),
        ("유동성 좋은 채권 추천해줘", "유동성"),
        ("발행 물량이 몇 좌야?", "발행좌수"),
        ("보유자가 몇 명이야?", "보유자수"),
    ],
    "단위·최소": [
        ("채권 최소 얼마부터 살 수 있어?", "최소투자금액"),
        ("최소 매수 단위가 어떻게 돼?", "매수단위"),
        ("액면 단위가 얼마야?", "액면단위"),
    ],
    "비용·세금": [
        ("채권 살 때 수수료 얼마야", "매매수수료"),
        ("채권 이자에 세금 얼마나 떼?", "이자소득세"),
        ("보수는 얼마나 되지?", "총보수"),
    ],
    "발행주체 상태": [
        ("한국전력 재무상태 어때", "재무상태"),
        ("이 발행사 부채비율 알려줘", "부채비율"),
        ("발행사 신용전망 어때?", "신용전망"),
        ("이 회사 망할 가능성 있어?", "부도확률"),
    ],
}

# 대조군 — 답할 수 있어야 하는 질문. 커버리지를 올리려다 이쪽을 죽이면 의미가 없다.
CONTROL = [
    ("국고채는 총 몇 종목이야?", "종목수"),
    ("수익률 높은 채권 5개 추천해줘", "민평수익률"),
    ("한국전력공사 채권 중에 만기가 제일 긴 것", "만기일"),
    ("A등급 이상 회사채 표면금리 높은 순 5개", "표면금리"),
    ("이자지급 방식이 뭐야?", "이자지급방식"),
    ("장내에서 거래된 가격이 가장 비싼 채권", "장내종가"),
    ("신용등급 적용일이 언제야?", "등급적용일"),
    ("퇴직연금으로 살 수 있는 채권 있어?", "퇴직연금편입"),
    ("변동금리 채권 몇 종목?", "금리구분"),
    ("발행잔액이 큰 채권 3개", "발행잔액"),
]


def probe(q, alias):
    """(L1 게이트가 잡나, L2 별칭이 잡나)."""
    tables = route(q, ctx).tables
    l1 = gate.check(q, ctx, tables).rejected
    sql = f"SELECT pd_nm, applied_yield AS {alias} FROM domestic_bonds LIMIT 5"
    l2 = axis_alias_confession(sql, ctx) is not None
    return l1, l2


print("=" * 96)
print("축 대체 환각 커버리지 — 한정어 부류 × 축")
print("=" * 96)
tot = blocked = only1 = only2 = both = 0
rows = []
for cls, items in MATRIX.items():
    c_tot = c_blk = 0
    for q, alias in items:
        l1, l2 = probe(q, alias)
        tot += 1
        c_tot += 1
        if l1 or l2:
            blocked += 1
            c_blk += 1
        both += 1 if (l1 and l2) else 0
        only1 += 1 if (l1 and not l2) else 0
        only2 += 1 if (l2 and not l1) else 0
        rows.append((cls, q, l1, l2))
    print(f"\n── {cls}  →  {c_blk}/{c_tot} 막힘")
    for cls2, q, l1, l2 in rows[-len(items):]:
        mark = "✅" if (l1 or l2) else "🔴 통과(막지 못함)"
        layers = ("L1게이트" if l1 else "") + ("+L2별칭" if l2 else "")
        print(f"   {mark:18s} {layers:14s} {q[:40]}")

print("\n" + "=" * 96)
print(f"막힌 것 {blocked}/{tot} ({blocked / tot * 100:.0f}%)  ·  L1만 {only1} · L2만 {only2} · 둘 다 {both}")

print("\n[대조군] 답할 수 있어야 하는 질문 — 하나라도 막히면 과교정")
bad = 0
for q, alias in CONTROL:
    l1, l2 = probe(q, alias)
    if l1 or l2:
        bad += 1
        print(f"   🔴 막힘({'L1' if l1 else ''}{'L2' if l2 else ''}) {q}")
print(f"   → {len(CONTROL) - bad}/{len(CONTROL)} 통과")
print("=" * 96)
