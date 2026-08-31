"""상품군 라우팅 — "질문이 어느 마스터 테이블을 향하는가" 를 **단어 목록 없이** 정한다.

2026-08-30 전수조사 §9 (scripts/route_prototype.py 2판 36/36 을 그대로 이관).
종전 gate._TABLE_HINTS(단어 11개)는 '국고채·통안채·영구채' 를 못 알아듣고 '채권형 ETF' 를 채권으로 끌고 갔다.

세 겹, 어느 겹에도 사람이 쓴 어휘 목록이 없다:
  ① 문장 구조 — 한국어 수식 구조에서 **마지막 상품 명사가 머리**다 ("채권형 ETF" → ETF).
     접속사(와/과/및/,/ / /+)로 이어진 상품 명사는 전부 머리다 ("채권과 ETF" → 둘 다).
     머리 바로 앞의 국내/해외/미국 이 국내·해외 ETF 를 가른다.
     상품 명사 4개(채권·ETF·ETN·펀드)는 주최 마스터 4파일의 이름(국내채권·국내ETF·해외ETF·공모펀드)에서 온다.
  ② 온톨로지 값 — 상품 명사가 없으면 질문에 **어느 테이블의 값**(발행사·지수·종목명·대분류·채권종류 …)이 나오는지.
     어휘는 loader._build_route_vocab 이 DB·yaml 에서 자동 생성한다. 경계 검사(앞뒤 한글 없음)·3자 이상.
  ③ 동의어 — DB 에 글자가 없는 통칭(통안채→통화안정채권)은 각 도메인 yaml `synonyms` 가 소유하고 ② 어휘에 합쳐진다.
  ④ 어느 겹도 못 정하면 마스터 4테이블 전부 → HCX 가 FROM 으로 정한다 (종전 fallback 그대로).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .loader import TABLES, RuntimeContext

# ① 상품 명사 → 후보 테이블. 원천은 주최 마스터 파일 라벨 — 국내채권마스터·국내ETF마스터·해외ETF마스터·공모펀드마스터.
#    ETN 은 국내ETF마스터 안의 상품구분(pd_grp_no) 값이라 ETF 와 같은 테이블이다.
#    🔴 한글 음차 표기도 넣는다 — 사람이 '이티에프' 라고 쓰면 상품 명사로 안 잡혀
#       미특정 → 4테이블이 됐다(2026-08-31 로컬 일제점검).
_ETF_TABLES = frozenset({"domestic_etfs", "overseas_etfs"})
PRODUCT: dict[str, frozenset[str]] = {
    "채권": frozenset({"domestic_bonds"}),
    "ETF": _ETF_TABLES,
    "ETN": _ETF_TABLES,
    "이티에프": _ETF_TABLES,
    "이티엔": _ETF_TABLES,
    "상장지수펀드": _ETF_TABLES,
    "상장지수증권": _ETF_TABLES,
    "펀드": frozenset({"public_funds"}),
}
# 머리 명사 바로 앞의 지역 수식어 — 마스터 파일 이름의 '국내/해외' 그대로. '미국' 은 해외ETF 의 투자지역 값.
QUALIFIER: dict[str, frozenset[str]] = {
    "해외": frozenset({"overseas_etfs"}),
    "미국": frozenset({"overseas_etfs"}),
    "국내": frozenset({"domestic_etfs", "domestic_bonds", "public_funds"}),
}
# 🔴 대소문자를 가리지 않는다 — 사람은 'etf' 라고 쓴다.
#    2026-08-31 서버 실측: "안전한 etf상품 추천좀" 이 소문자라 상품 명사로 안 잡혀 '미특정 → 4테이블' 이 됐고,
#    근거문서가 39,403자로 불어나 HCX 가 펀드 컬럼(zrin_*)을 domestic_etfs 에 써서 재생성까지 실패했다.
# 긴 이름을 먼저 — '상장지수펀드' 가 '펀드' 로 잘리면 안 된다
_PRODUCT_TOKEN = re.compile("|".join(re.escape(w) for w in sorted(PRODUCT, key=len, reverse=True)), re.I)
# 병렬 표지 — 한국어 접속 조사·접속사.
# 🔴 받침 없는 체언 뒤의 `나` 를 빼먹고 있었다 (`이나` 만 있었다).
#    2026-08-31 서버 실측: "삼성전자가 들어 있는 ETF나 펀드 중에…" 가 'ETF나' 를 병렬로 못 읽어
#    머리명사를 '펀드' 하나로 잡았고, ETF 가 통째로 빠진 채 public_funds 만 조회했다.
#    여기 쓰이는 자리는 '상품 명사 바로 뒤 3글자' 뿐이라 `나` 단독을 넣어도 오탐 위험이 없다.
_CONJ = re.compile(r"\s*(이랑|랑|와|과|및|하고|이나|나|또는|혹은|vs\.?|,|/|\+)\s*")
_QUAL_WINDOW = 8          # 머리 명사 앞에서 수식어를 찾는 글자 수 ('삼성전자를 보유한 국내/해외 ETF')
_SCORE_KEEP = 0.7         # ② 겹에서 최고점의 70% 이상인 테이블은 함께 넘긴다 (HCX 가 고르게 둔다)
_LONG_TERM = 5            # 이 길이 이상의 값(상품명)은 공백 무시 부분 일치를 허용 ('KODEX 국고채3년')


@dataclass
class Route:
    tables: list[str]      # TABLES 순서. 못 정하면 4개 전부
    why: str               # think_trace 용 근거 문장
    decided: bool          # False 면 ④ (미특정 — HCX 판단)
    groups: int = 0        # 서로 다른 상품군의 수 — '채권과 ETF' 2 · '채권형 ETF'(국내/해외 미결) 1 · 미특정 0. 교차질의 판정용


def _canon(word: str) -> str:
    """질문에 나온 상품 명사를 PRODUCT 표의 정본 표기로. 'etf'·'Etf' → 'ETF'."""
    return word.upper() if word.upper() in PRODUCT else word


def product_route(question: str) -> tuple[set[str], str, int]:
    """① 문장 구조. (후보 테이블, 근거, 머리 명사 수). 상품 명사가 없으면 (∅, '', 0)."""
    # '채권형'·'주식형' 의 상품 명사는 수식어(유형)다 — 머리가 아니다 ("채권형 상품 추천" 은 채권이 아니라 채권형 펀드·ETF)
    # 매칭은 대소문자 무시로 하되, 표는 정본 표기(ETF·ETN)로 찾는다 — 한글 키는 upper() 가 항등이다
    hits = [(_canon(m.group(0)), m.start(), question[m.end(): m.end() + 1] == "형")
            for m in _PRODUCT_TOKEN.finditer(question)]
    toks = [(w, p) for w, p, is_qual in hits if not is_qual]
    # 🔴 'ETF형 상품' 은 ETF 를 뜻한다 — 다른 상품 명사가 없으면 이걸 머리로 쓴다.
    #    단 '채권형'·'주식형' 은 **자산 유형** 수식어라 여기 해당하지 않는다
    #    ("채권형 상품 추천" 은 채권이 아니라 채권형 펀드·ETF — tests/test_router.py:71).
    #    포장(ETF·ETN)을 가리키는 말만 예외로 둔다. (2026-08-31 로컬 일제점검)
    if not toks:
        toks = [(w, p) for w, p, _ in hits if PRODUCT[w] == _ETF_TABLES]
    if not toks:
        return set(), "", 0
    heads: list[tuple[str, int]] = []
    for w, pos in toks[:-1]:
        # 상품 명사 뒤에 접속사가 붙으면 병렬 — 그것도 머리다
        if _CONJ.match(question[pos + len(w): pos + len(w) + 3]):
            heads.append((w, pos))
    heads.append(toks[-1])                      # 마지막 상품 명사는 항상 머리
    tables: set[str] = set()
    for w, pos in heads:
        cand = set(PRODUCT[w])
        before = question[max(0, pos - _QUAL_WINDOW): pos]
        quals: set[str] = set()
        for qual, ts in QUALIFIER.items():
            if qual in before:
                quals |= ts
        if quals and cand & quals:
            cand &= quals                       # 수식어들의 합집합으로 좁힌다 ('국내/해외 ETF' → 둘 다)
        # 수식어가 상품과 안 맞으면('해외 채권') 상품 명사를 따른다 — 채권 규칙(외화채없음)이 답할 수 있게
        tables |= cand
    groups = len({PRODUCT[w] for w, _ in heads})   # ETF·ETN 은 같은 상품군
    return tables, "머리명사 " + "/".join(w for w, _ in heads), groups


def _bound_in(term: str, question: str, squeezed: str) -> bool:
    """값이 질문 안에 '낱말로' 있는가. 한글 값은 앞뒤에 한글이 없어야 하고(경계), 영문·숫자 값은 앞뒤에 영숫자가 없어야 한다."""
    # 값 16,000개 × 정규식은 비싸다 — 부분 문자열로 먼저 거른다 (없으면 경계 검사도 필요 없다)
    if term not in question and not (len(term) >= _LONG_TERM and term in squeezed):
        return False
    if not re.search(r"[가-힣]", term):
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", question):
            return True
        # 🔴 영문 값에도 한글과 같은 공백 무시 폴백을 준다. 어휘는 공백을 뗀 형태로 저장되는데
        #    (loader._VOCAB_STRIP) 사람은 띄어서 쓴다 — 'KODEX 200 알려줘' 가 어휘 'KODEX200' 에
        #    안 걸려 라우팅이 미특정으로 빠졌다(2026-08-31 로컬 일제점검).
        #    경계 검사는 squeezed 에서도 유지해 짧은 토큰의 오탐을 막는다.
        return len(term) >= _LONG_TERM and re.search(
            rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", squeezed) is not None
    if re.search(rf"(?<![가-힣]){re.escape(term)}(?![가-힣])", question):
        return True
    return len(term) >= _LONG_TERM and term in squeezed   # 긴 값(상품명)은 공백 무시 부분 일치 허용


def onto_route(question: str, ctx: RuntimeContext) -> tuple[set[str], dict[str, float], dict[str, list[str]]]:
    """② 온톨로지 값 매칭. (테이블 집합, 테이블별 점수, 테이블별 걸린 값 상위 3)."""
    squeezed = re.sub(r"\s+", "", question)
    score: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    for t in TABLES:
        s, h = 0.0, []
        for term, w in (ctx.route_vocab.get(t) or {}).items():
            if _bound_in(term, question, squeezed):
                s += w * (1 + 0.1 * len(term))    # 긴 값이 더 확실한 신호다
                h.append(term)
        score[t] = round(s, 1)
        hits[t] = sorted(h, key=len, reverse=True)[:3]
    best = max(score, key=score.get)
    if score[best] == 0:
        return set(), score, hits
    return {t for t in TABLES if score[t] >= _SCORE_KEEP * score[best]}, score, hits


def route(question: str, ctx: RuntimeContext) -> Route:
    p, why, groups = product_route(question)
    o, score, hits = onto_route(question, ctx)
    if p:
        tables = p
        # 상품 명사가 둘 이상 후보(ETF → 국내/해외)면 온톨로지 값으로 좁힌다
        if len(tables) > 1 and o & tables:
            tables = o & tables
        if o & tables:
            top = max(o & tables, key=lambda t: score[t])
            why += f" · 값 {hits[top]}"
        return Route([t for t in TABLES if t in tables], why, True, groups)
    if o:
        return Route([t for t in TABLES if t in o], "상품명사 없음 → 값 " + str([hits[t] for t in TABLES if t in o]), True, len(o))
    return Route(list(TABLES), "미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)", False, 0)
