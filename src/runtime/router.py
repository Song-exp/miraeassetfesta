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
    # 🔴 오타 흡수 — 2026-09-02 R7 재검: "공모펌드 중 1년 수익률…" 이 미특정 → 4테이블 49,634자 근거문서로 빠져
    #    답변 규칙이 12,443자로 희석되고 residual_name_token(이름 필터)이 꺼졌다. 결정층 본체는 pipeline 의
    #    SQL 사후 라우팅 보정이고 이것은 벨트-멜빵(비용 0). 표현형은 무한하므로 이것으로 닫았다고 보지 않는다.
    "펌드": frozenset({"public_funds"}),
    # 3R A-3 — 도메인 정식 용어(§3.3 법적형태): 기본모수 8,969행 중 '투자신탁' 8,629 · '투자회사' 87. '…증권자투자신탁 1년 수익률' 처럼
    #    '펀드' 명사 없이 정식명만 적은 질의(T7)가 미특정 4테이블로 빠지는 것을 막는다. '상장지수투자신탁' 은 ETF 의 정식명(긴 키 우선).
    "투자신탁": frozenset({"public_funds"}),
    "투자회사": frozenset({"public_funds"}),
    "상장지수투자신탁": _ETF_TABLES,
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
_MANAGER_WORD = re.compile(r"운용사|자산운용")
# 3R B-2 정정 — 2R 의 3테이블은 실측 2/2(S11·T2)에서 HCX 가 ETF 를 골라 템플릿이 불발했다. 운용사 코드·순자산·펀드수를 다 가진
#    테이블은 public_funds 뿐(ETF cu_fund_mgmt_co 는 브랜드 약칭 — 법인 집계 축이 못 된다). 상품 명사가 있으면 그것이 머리(변경 없음).
_MANAGER_TABLES = frozenset({"public_funds"})
# 병렬 표지 — 한국어 접속 조사·접속사.
# 🔴 받침 없는 체언 뒤의 `나` 를 빼먹고 있었다 (`이나` 만 있었다).
#    2026-08-31 서버 실측: "삼성전자가 들어 있는 ETF나 펀드 중에…" 가 'ETF나' 를 병렬로 못 읽어
#    머리명사를 '펀드' 하나로 잡았고, ETF 가 통째로 빠진 채 public_funds 만 조회했다.
#    여기 쓰이는 자리는 '상품 명사 바로 뒤 3글자' 뿐이라 `나` 단독을 넣어도 오탐 위험이 없다.
_CONJ = re.compile(r"\s*(이랑|랑|와|과|및|하고|이나|나|또는|혹은|vs\.?|,|/|\+)\s*")
_QUAL_WINDOW = 8          # 머리 명사 앞에서 수식어를 찾는 글자 수 ('삼성전자를 보유한 국내/해외 ETF')
_SCORE_KEEP = 0.7         # ② 겹에서 최고점의 70% 이상인 테이블은 함께 넘긴다 (HCX 가 고르게 둔다)
_LONG_TERM = 5            # 이 길이 이상의 값(상품명)은 공백 무시 부분 일치를 허용 ('KODEX 국고채3년')
# 한글 값 뒤에 붙어도 값의 끝으로 인정하는 조사 — 뒤에 한글이 더 오면 조사가 아니다 (2026-09-02: '국고채는' 미특정 실측)
_PARTICLE = r"(?:은|는|이|가|을|를|의|에|에서|에게|로|으로|도|만|과|와|랑|이랑|부터|까지|처럼|보다|밖에|마다|조차|이나|나|든지|든|이란|란)"


@dataclass
class Route:
    tables: list[str]      # TABLES 순서. 못 정하면 4개 전부
    why: str               # think_trace 용 근거 문장
    decided: bool          # False 면 ④ (미특정 — HCX 판단)
    groups: int = 0        # 서로 다른 상품군의 수 — '채권과 ETF' 2 · '채권형 ETF'(국내/해외 미결) 1 · 미특정 0. 교차질의 판정용


def _canon(word: str) -> str:
    """질문에 나온 상품 명사를 PRODUCT 표의 정본 표기로. 'etf'·'Etf' → 'ETF'."""
    return word.upper() if word.upper() in PRODUCT else word


def _inside_longer_value(pos: int, length: int, spans) -> bool:
    """상품 명사가 **더 긴 온톨로지 값 안에 갇혀** 있는가 — 갇혀 있으면 머리 명사가 아니다.

    🔴 2026-09-06 분류 전수조사(scripts/audit_bonds_taxonomy.py) — 상품 명사를 경계 검사 없이 부분
    문자열로 잡아, 값 이름 안의 글자가 머리 명사로 승격되고 있었다. 전수 실측 255건:
      · '부동산투자회사채'(채권 35종목)·'집합투자회사채'(7종목) → 안의 '투자회사' 가 머리 → public_funds.
        실재하는 채권을 펀드 테이블에서 찾으니 "그런 상품 없습니다" 가 나간다.
      · 'ACE종합채권(AA-이상)액티브 총보수 얼마야?' → 안의 '채권' 이 머리 → domestic_bonds.
        총보수는 채권에 없는 컬럼이라 오거절하거나 없는 값을 지어낸다(ETF 상품명 142건·펀드 105건).
    ①(문장 구조) 겹이 ②(온톨로지 값) 겹을 무조건 이기는 구조라 onto_route 의 상품명 직격 매치 면제
    (2026-09-01)가 route() 에서 버려지고 있었다. 여기서 **긴 낱말 우선**을 ① 겹에도 적용한다 —
    kind_filters 의 소진 탐색·PRODUCT 표의 길이 역순 정렬과 같은 원칙이고, 어휘 목록을 새로 쓰지 않는다.
    """
    return any(s <= pos and pos + length <= e and (e - s) > length for s, e in spans)


def product_route(question: str, spans=()) -> tuple[set[str], str, int]:
    """① 문장 구조. (후보 테이블, 근거, 머리 명사 수). 상품 명사가 없으면 (∅, '', 0).

    spans — 질문 안에서 온톨로지 값이 차지하는 구간 (route() 가 ② 겹에서 넘긴다). 값 안에 갇힌
    상품 명사는 머리에서 뺀다. 구간이 없으면 종전과 완전히 같게 동작한다."""
    # '채권형'·'주식형' 의 상품 명사는 수식어(유형)다 — 머리가 아니다 ("채권형 상품 추천" 은 채권이 아니라 채권형 펀드·ETF)
    # 매칭은 대소문자 무시로 하되, 표는 정본 표기(ETF·ETN)로 찾는다 — 한글 키는 upper() 가 항등이다
    hits = [(_canon(m.group(0)), m.start(), question[m.end(): m.end() + 1] == "형")
            for m in _PRODUCT_TOKEN.finditer(question)
            if not _inside_longer_value(m.start(), m.end() - m.start(), spans)]
    toks = [(w, p) for w, p, is_qual in hits if not is_qual]
    # 🔴 'ETF형 상품' 은 ETF 를 뜻한다 — 다른 상품 명사가 없으면 이걸 머리로 쓴다.
    #    단 '채권형'·'주식형' 은 **자산 유형** 수식어라 여기 해당하지 않는다
    #    ("채권형 상품 추천" 은 채권이 아니라 채권형 펀드·ETF — tests/test_router.py:71).
    #    포장(ETF·ETN)을 가리키는 말만 예외로 둔다. (2026-08-31 로컬 일제점검)
    if not toks:
        toks = [(w, p) for w, p, _ in hits if PRODUCT[w] == _ETF_TABLES]
    if not toks and _MANAGER_WORD.search(question):
        # 🔴 '운용사'·'자산운용' 만 있는 질의(2026-09-02 S11 "순자산이 가장 큰 운용사 상위 3개") — 상품 명사가 없어
        #    미특정 4테이블 51,788자로 빠졌다. 운용사 컬럼은 펀드(or_co_xtn_itt_cd)·ETF(cu_fund_mgmt_co)에만 있고
        #    채권엔 없으므로 3테이블로 좁힌다(문서 1/3 감량). 상품 명사가 있으면 그것이 머리다("펀드를 … 운용사" → 펀드).
        return set(_MANAGER_TABLES), "운용사 표현 → 운용사 집계 정본 = 공모펀드 마스터(코드·순자산·펀드수 보유 유일 테이블)", 1
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
    # 🔴 한글 값의 뒤 경계는 조사를 허용한다 — 2026-09-02 gold 재투입 실측: '국고채는 총 몇 종목이야?' 가 '국고채'+'는' 으로
    #    경계에 걸려 미특정 → HCX FROM 판단 → 라우팅 범위 가드가 정답 SQL 을 기각했다. 조사 뒤에는 한글이 오지 않아야 한다
    #    ('국고채는' ✓ · '국고채권' ✗ — '권' 은 조사가 아니다 · '회사채는' 의 '채는' 은 '채' 가 값 끝이라 그대로 조사 처리).
    if re.search(rf"(?<![가-힣]){re.escape(term)}(?:(?![가-힣])|{_PARTICLE}(?![가-힣]))", question):
        return True
    return len(term) >= _LONG_TERM and term in squeezed   # 긴 값(상품명)은 공백 무시 부분 일치 허용


def value_spans(question: str, ctx: RuntimeContext) -> list[tuple[int, int]]:
    """질문 안에서 온톨로지 값이 차지하는 구간 — ① 겹의 '갇힌 상품 명사' 판정에 쓴다.

    ② 겹이 실제로 매치한 값만 본다 — 어휘 목록을 새로 쓰지 않는다. 어휘는 공백을 뗀 형태로 저장되는데
    (loader._VOCAB_STRIP) 사람은 띄어서 쓰므로('KODEX 종합채권…' vs 어휘 'KODEX종합채권…') 공백 무시
    매치도 원문 위치로 되돌린다 — 안 그러면 띄어 쓴 상품명 안의 '채권' 이 그대로 머리 명사가 된다."""
    spans: list[tuple[int, int]] = []
    squeezed = re.sub(r"\s+", "", question)
    back = [i for i, ch in enumerate(question) if not ch.isspace()]   # 뗀 문자열 위치 → 원문 위치
    for t in TABLES:
        for term in (ctx.route_vocab.get(t) or {}):
            if len(term) <= 2 or not _bound_in(term, question, squeezed):
                continue
            i = question.find(term)
            while i >= 0:
                spans.append((i, i + len(term)))
                i = question.find(term, i + 1)
            j = squeezed.find(term)
            while j >= 0:
                spans.append((back[j], back[j + len(term) - 1] + 1))
                j = squeezed.find(term, j + 1)
    return spans


def onto_route(question: str, ctx: RuntimeContext) -> tuple[set[str], dict[str, float], dict[str, list[str]]]:
    """② 온톨로지 값 매칭. (테이블 집합, 테이블별 점수, 테이블별 걸린 값 상위 3)."""
    squeezed = re.sub(r"\s+", "", question)
    score: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    prod_tables: set[str] = set()
    for t in TABLES:
        s, h = 0.0, []
        prods = ctx.route_products.get(t) or ()
        for term, w in (ctx.route_vocab.get(t) or {}).items():
            if _bound_in(term, question, squeezed):
                s += w * (1 + 0.1 * len(term))    # 긴 값이 더 확실한 신호다
                h.append(term)
                if term in prods:
                    prod_tables.add(t)
        score[t] = round(s, 1)
        hits[t] = sorted(h, key=len, reverse=True)[:3]
    best = max(score, key=score.get)
    if score[best] == 0:
        return set(), score, hits
    # 🔴 상품명(약어명·티커) 직격 매치 테이블은 상대 점수컷 면제 — "TIGER 미국S&P500 이랑
    #    VOO 중 뭐가 나아" 에서 긴 국내 상품명이 점수를 부풀려 해외가 잘렸다(2026-09-01).
    return {t for t in TABLES if score[t] >= _SCORE_KEEP * score[best]} | prod_tables, score, hits


def route(question: str, ctx: RuntimeContext) -> Route:
    # ② 겹을 먼저 잰다 — ① 겹이 '값 안에 갇힌 상품 명사' 를 머리로 삼지 않게 구간을 넘기기 위해서다.
    #    onto_route 는 순수 함수라 순서를 바꿔도 결과가 달라지지 않는다.
    o, score, hits = onto_route(question, ctx)
    p, why, groups = product_route(question, value_spans(question, ctx))
    # 🔴 2026-09-06 ETF-B2 서버 실측 — "KODEX 200 운용사랑 기초지수 알려줘" 가 '운용사' 한 낱말로 public_funds 로 갔고
    #    KODEX 200 을 펀드 이름으로 찾다 0행 → "확인되지 않습니다" 오답. ① 겹의 운용사 폴백은 **상품 명사가 없을 때**
    #    쓰는 최후 수단인데, ② 겹은 그 사이 KODEX 200 을 국내 ETF 로 이미 접지하고 있었다.
    #    값이 다른 상품군을 특정하면 값이 이긴다 — 폴백은 값이 침묵할 때만 선다.
    if p == set(_MANAGER_TABLES) and why.startswith("운용사 표현") and o and not (o & p):
        return Route([t for t in TABLES if t in o],
                     "운용사 표현이 있으나 값이 상품군을 특정 — 값 " + str([hits[t] for t in TABLES if t in o]),
                     True, len(o))
    if p:
        tables = p
        # 상품 명사가 둘 이상 후보(ETF → 국내/해외)면 온톨로지 값으로 좁힌다.
        # 🔴 10R gold ③-B 1 — 단, **머리명사가 둘 이상(groups > 1)이면 좁히지 않는다**: 질문이 두 상품군을
        #    나란히 물은 것이라(국내 ETF **와** 해외 ETF) 값 하나로 한쪽을 지우면 비교 질의가 반쪽이 된다(CROSS-003).
        if len(tables) > 1 and groups <= 1 and o & tables:
            tables = o & tables
        if o & tables:
            top = max(o & tables, key=lambda t: score[t])
            why += f" · 값 {hits[top]}"
        return Route([t for t in TABLES if t in tables], why, True, groups)
    if o:
        return Route([t for t in TABLES if t in o], "상품명사 없음 → 값 " + str([hits[t] for t in TABLES if t in o]), True, len(o))
    return Route(list(TABLES), "미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)", False, 0)
