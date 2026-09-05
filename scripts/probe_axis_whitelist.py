# -*- coding: utf-8 -*-
"""G1 축 화이트리스트 — **진단 모드**. 차단하지 않고 오폭률만 잰다.

지금 부재축 방어는 블랙리스트다 — `absent_properties` 가 "없는 축" 을 하나씩 센다. 없는 축은 무한하니
영원히 안 닫히고, 실제로 등급이력·금리이력·업종·이자주기는 **사고를 한 번씩 맞고 나서** 정규식을 손으로
써서 막았다. 있는 축은 유한하다(테이블당 컬럼 수). 뒤집으면 닫힌다.

화이트리스트의 원천은 전부 **선언**이다 — 손으로 쓴 목록이 0이어야 한다:
  · schema_metadata.korean_name  (주최가 준 원본 스키마)
  · enums/<table>.yaml columns.*.korean_name
  · enums/<table>.yaml synonyms 키
  · 값 사전(vocab)의 값 — '고정금리'·'이표채' 처럼 값 자체가 축 낱말로 쓰인다

판정: 질문에서 **축 낱말꼴**을 뽑아, 하나도 화이트리스트에 안 닿으면 '수록 범위 밖 후보'.
차단이 아니라 되묻기로 착지할 자리이므로, 여기서는 그 후보가 몇 건이고 그중 몇 건이
**답할 수 있는 질문**(=오폭)인지만 센다.

사용: python scripts/probe_axis_whitelist.py
"""
import os
import sys
import re
import json
import glob

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")

from runtime.loader import load_context      # noqa: E402
from runtime.router import route             # noqa: E402
from runtime import gate                     # noqa: E402

ctx = load_context()
TABLES = ["domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"]
_SPLIT = re.compile(r"[/(),·\s]+")


def whitelist(table: str) -> set[str]:
    """이 테이블이 답할 수 있는 축 낱말 — 전부 선언에서 자동 생성."""
    wl: set[str] = set()
    for _col, ko, _t in (ctx.schema.get(table) or []):
        wl |= {w for w in _SPLIT.split(ko or "") if len(w) >= 2}
    enums = (ctx.enums or {}).get(table) or {}
    for spec in (enums.get("columns") or {}).values():
        ko = (spec.get("korean_name") if isinstance(spec, dict) else "") or ""
        wl |= {w for w in _SPLIT.split(ko) if len(w) >= 2}
    wl |= {str(k) for k in (enums.get("synonyms") or {}) if len(str(k)) >= 2}
    for spec in ((enums.get("value_vocab") or {}) or {}).values():
        if isinstance(spec, dict):
            wl |= {str(v) for v in (spec.get("values") or []) if len(str(v)) >= 2}
            ko = str(spec.get("korean_name") or "")
            wl |= {w for w in _SPLIT.split(ko) if len(w) >= 2}
    return wl


WL = {t: whitelist(t) for t in TABLES}

# ── 축 낱말꼴 — "무엇을 재는가" 를 가리키는 명사. 이름·값이 아니라 **축**만 뽑는다.
#    보수적으로: 조사·어미를 떼고 남은 2자 이상 한글 명사 중, 흔한 기능어를 뺀 것.
_STOP = set("""
채권 펀드 상품 종목 알려줘 알려 려줘 추천 추천해 얼마 얼마나 어떻게 어디 무엇 뭐야 뭐가 있어 있나 있는 없는
가장 제일 가지 정도 경우 기준 조건 관련 대해 대한 어떤 무슨 그리고 그런 이런 저런 우리 지금 현재 오늘 내일
개수 종류 목록 순서 순위 위주 정리 비교 설명 확인 조회 검색 소개 선택 고르 골라 찾아 보여 보여줘 주세요 해줘
이상 이하 초과 미만 이내 안에 부터 까지 사이 위험 안전 좋은 나쁜 높은 낮은 많은 적은 크게 작은 최고 최저
사람 투자 매수 매도 구매 판매 가능 하는 되는 이거 저거 그거 다른 모든 전체 각각 여러 하나 둘째
""".split())
_NOUN = re.compile(r"[가-힣]{2,}")
_PARTICLE = re.compile(r"(?:은|는|이|가|을|를|의|에|에서|로|으로|도|만|과|와|랑|이랑|부터|까지|보다|처럼|마다|나|이나)$")


def axis_words(q: str) -> list[str]:
    out = []
    for w in _NOUN.findall(q):
        w2 = _PARTICLE.sub("", w)
        for cand in {w, w2}:
            if len(cand) >= 2 and cand not in _STOP:
                out.append(cand)
    return sorted(set(out))


def verdict(q: str):
    """(라우팅 테이블, 축 낱말, 닿은 낱말) — 닿은 게 하나도 없으면 '수록 범위 밖 후보'."""
    tables = route(q, ctx).tables
    wl = set().union(*(WL[t] for t in tables if t in WL)) if tables else set()
    words = axis_words(q)
    hit = [w for w in words if any(w in v or v in w for v in wl)]
    return tables, words, hit


print("=" * 100)
print("G1 축 화이트리스트 — 진단 모드 (차단 없음)")
print("=" * 100)
for t in TABLES:
    print(f"  {t:16s} 축 낱말 {len(WL[t]):4d}개 (선언에서 자동 생성)")

# ── ① 막아야 하는 것: 이미 사고가 난 축 대체 4건 + 오늘 선언한 2건 + 아직 못 막는 것들 ──
SHOULD_FLAG = [
    "최근 6개월 사이에 신용등급이 오른 채권들 정리해줘",     # #65 등급이력
    "한전 채권 금리가 요즘 어떻게 움직였어?",                 # #72 금리이력
    "우주항공 관련 발행사가 발행한 채권 정리해줘",             # #67 업종
    "한국전력공사 채권은 이자를 몇 개월마다 줘?",             # #77 이자주기
    "거래가 제일 활발한 채권 알려줘",                         # #81 거래량
    "채권 최소 얼마부터 살 수 있어?",                         # #81 최소금액
    "채권 이자에 세금 얼마나 떼?",                            # 미선언
    "채권 살 때 수수료 얼마야",                               # 미선언
    "한국전력 재무상태 어때",                                 # 미선언
    "채권 유동성 회전율 알려줘",                              # 미선언
]

print("\n[①] 막아야 하는 축 — 화이트리스트에 안 닿아야 한다")
n_ok = 0
for q in SHOULD_FLAG:
    tables, words, hit = verdict(q)
    mark = "✅ 안 닿음" if not hit else f"❌ 닿음 {hit}"
    if not hit:
        n_ok += 1
    print(f"  {mark:26s} | {q[:38]}")
print(f"  → {n_ok}/{len(SHOULD_FLAG)}")

# ── ② 오폭 측정: 기존 문항 전수 — 답할 수 있는 질문이 '범위 밖 후보' 로 잡히면 오폭 ──
print("\n[②] 오폭 — eval 전건에서 '범위 밖 후보' 로 잡히는 문항")
n_q = n_flag = 0
flagged = []
for path in sorted(glob.glob("eval/*.jsonl")):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        q = (rec.get("question") or "").strip()
        if not q:
            continue
        n_q += 1
        tables, words, hit = verdict(q)
        if words and not hit:
            n_flag += 1
            flagged.append((os.path.basename(path), q, words))
for f in flagged:
    print(f"  ⚠ [{f[0]}] {f[1][:52]}  ← 축 낱말 {f[2][:5]}")
print(f"  → eval {n_q}문항 중 {n_flag}건 ({n_flag / max(n_q, 1) * 100:.1f}%)")

print("\n" + "=" * 100)
print(f"판정: 미탐 {len(SHOULD_FLAG) - n_ok}건 · 오폭 {n_flag}건 / {n_q}문항")
print("오폭이 0 이 되면 되묻기로 착지시켜 켤 수 있다. 0 이 아니면 축 낱말 추출을 더 좁힌다.")
