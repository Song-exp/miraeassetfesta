# 시제품 — 상품군 라우팅 (전수조사 §9). 리드가 gate.detect_tables 교체 시 참고. 실행: python scripts/route_prototype.py
# 라우팅 시제품 2판 — ① 상품 명사의 문장 위치(머리 명사) ② 온톨로지 값 매칭(경계식·3자 이상) ③ 동의어는 yaml 소관
import sqlite3, re, sys, os
os.chdir(r"C:\Users\bella\Desktop\대학\공모전\트리플에이치\미래에셋"); sys.path.insert(0, ".")
c = sqlite3.connect("data/financial_products.db"); q = lambda s: c.execute(s).fetchall()
T = ["domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"]
short = {"domestic_bonds": "d.bonds", "domestic_etfs": "d.etfs", "overseas_etfs": "o.etfs", "public_funds": "p.funds"}

# ① 상품 명사 — 원천은 주최 파일 라벨(국내채권마스터·국내ETF마스터·해외ETF마스터·공모펀드마스터). 코드가 아니라 build_info/파일명에서 온다
PRODUCT = {"채권": {"domestic_bonds"}, "ETF": {"domestic_etfs", "overseas_etfs"}, "ETN": {"domestic_etfs", "overseas_etfs"}, "펀드": {"public_funds"}}
QUALIFIER = {"해외": {"overseas_etfs"}, "미국": {"overseas_etfs"}, "국내": {"domestic_etfs", "domestic_bonds", "public_funds"}}
CONJ = re.compile(r"\s*(와|과|및|랑|,|/|\+)\s*")

def product_route(qs):
    """머리 명사 규칙: 마지막 상품 명사가 머리. 접속사(와/과/및/,/)로 병렬이면 전부."""
    toks = [(m.group(0), m.start()) for m in re.finditer(r"채권|ETF|ETN|펀드", qs)]
    if not toks: return set(), "상품명사 없음"
    # 병렬: 상품명사 뒤에 접속사가 붙어 있으면 그것도 머리
    heads = []
    for w, pos in toks:
        after = qs[pos + len(w): pos + len(w) + 3]
        if CONJ.match(after): heads.append((w, pos))
    heads.append(toks[-1])
    tables = set()
    for w, pos in heads:
        cand = set(PRODUCT[w])
        # 바로 앞 수식어(해외/미국/국내)로 좁힌다
        before = qs[max(0, pos - 8):pos]
        quals = set()
        for qual, ts in QUALIFIER.items():
            if qual in before: quals |= ts
        if quals: cand &= quals                       # 수식어들의 합집합으로 좁힌다 ('국내/해외 ETF' → 둘 다)
        tables |= cand
    why = "머리명사 " + "/".join(w for w, _ in heads)
    # ETF 만으로는 국내/해외를 못 가르면 둘 다 (HCX 가 고르게 둠)
    return tables, why

# ② 온톨로지 값 매칭 — KG alias(테이블별) + 범주형 값. 경계식·3자 이상
vocab = {t: {} for t in T}
def add(t, term, w):
    term = re.sub(r"\(주\)|주식회사|\s+", "", (term or "")).strip()
    if len(term) < 3 or re.fullmatch(r"[\d\.\-/]+", term) or term in ("채권", "ETF", "ETN", "펀드"): return
    vocab[t][term] = max(vocab[t].get(term, 0), w)
for t, raw in q("select table_name, raw_value from kg_alias"):
    if t in vocab: add(t, raw, 3)
for t in T:
    for (col, typ) in [(r[1], r[2]) for r in q(f"pragma table_info({t})")]:
        if "text" not in (typ or "").lower(): continue
        if 1 < q(f"select count(distinct trim({col})) from {t}")[0][0] <= 60:
            for (v,) in q(f"select distinct trim({col}) from {t} where {col} is not null"): add(t, v, 2)
for (v,) in q("select distinct trim(pd_abrv_nm) from domestic_etfs where pd_abrv_nm is not null"): add("domestic_etfs", v, 3)
for (v,) in q("select distinct trim(pd_abrv_nm) from overseas_etfs where pd_abrv_nm is not null"): add("overseas_etfs", v, 3)
# ③ 동의어 — 코드가 아니라 yaml(value_semantics/name_encoding 의 synonyms) 에 둘 것. 여기선 그 형태를 흉내낸다
SYN = {"domestic_bonds": {"통안채": "통화안정채권", "지방채": "모집지방채", "영구채": "신종", "코코본드": "조건부자본", "은행채": "일반은행채", "카드채": "신용카드채",
                          "국고채": "국고채권", "회사채": "일반회사채", "특수채": "특수채", "국공채": "국공채", "MBS": "MBS", "신용등급": "적용신용등급", "듀레이션": "듀레이션", "표면금리": "표면금리", "잔존만기": "잔존일수", "만기": "상환일자"},
       "domestic_etfs": {"총보수": "총보수", "순자산": "순자산", "추종": "기초지수", "기초지수": "기초지수"},
       "overseas_etfs": {"총보수": "총보수", "추종": "기초지수"},
       "public_funds": {"설정액": "설정액", "운용사": "운용사", "판매사": "판매사"}}
for t, d in SYN.items():
    for k in d: add(t, k, 2)

def bound_in(term, s):
    s0 = re.sub(r"\s+", "", s)                       # 공백 무시 비교용 (상품명 'KODEX 국고채3년')
    if not re.search(r"[가-힣]", term):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", s) is not None
    if re.search(rf"(?<![가-힣]){re.escape(term)}(?![가-힣])", s): return True   # 원문에서 경계 검사
    return len(term) >= 5 and term in s0             # 긴 값(상품명 등)은 공백 무시 부분 일치 허용

def onto_route(qs):
    score, hits = {}, {}
    for t, terms in vocab.items():
        s, h = 0, []
        for term, w in terms.items():
            if bound_in(term, qs): s += w * (1 + 0.1 * len(term)); h.append(term)
        score[t], hits[t] = round(s, 1), sorted(h, key=len, reverse=True)[:3]
    best = max(score, key=score.get)
    if score[best] == 0: return set(), score, hits
    return {t for t in T if score[t] >= 0.7 * score[best]}, score, hits

def route(qs):
    p, why = product_route(qs)
    o, score, hits = onto_route(qs)
    if p:
        tables = p
        # 상품 명사가 둘 이상 후보(ETF → 국내/해외)면 온톨로지 값으로 좁힌다
        if len(tables) > 1 and o & tables: tables = o & tables
        return tables, f"{why}" + (f" · 값 {hits[max(o, key=lambda t: score[t])]}" if o and (o & tables) else "")
    if o: return o, f"상품명사 없음 → 값 {[hits[t] for t in o]}"
    return set(T), "미특정 → 4테이블(HCX 판단)"

from src.runtime import gate
qs = ["신용등급 AA- 이상 채권 알려줘", "국고채 수익률 알려줘", "통안채 몇 개 있어?", "지방채 알려줘", "은행채 중 AAA", "MBS 채권 수익률", "카드채 수익률",
      "한국전력 채권 알려줘", "LH 채권", "산업은행 채권", "삼성전자 채권", "현대카드 채권 수익률", "영구채 알려줘", "코코본드 알려줘", "듀레이션 짧은 채권", "표면금리 높은 채권",
      "위험등급 낮은 채권", "만기 2027년 채권", "잔존만기 1년 이내 채권",
      "채권형 ETF 추천", "채권 ETF 중 수익률 높은 것", "KODEX 국고채3년 알려줘", "국고채 ETF 순자산 큰 순", "TIGER 미국S&P500 총보수", "총보수 낮은 ETF",
      "미국 나스닥 추종 해외 ETF", "QQQ 알려줘", "해외 채권 ETF 중 총보수 낮은 것",
      "삼성전자 보유한 펀드 알려줘", "채권형 펀드 중 1년 수익률 높은 것", "미래에셋자산운용 펀드", "설정액 큰 펀드",
      "삼성전자를 보유한 국내/해외 ETF 와 공모펀드를 연수익률 기준 TOP10", "수익률 높은 상품 추천해줘", "채권과 ETF 중 뭐가 안전해?", "한국전력공사가 발행한 채권"]
ok = 0
print(f"{'질문':<40} | 2판 라우팅 | 현행 | 근거")
for qq in qs:
    tables, why = route(qq)
    cur = ",".join(short[t] for t in gate.detect_tables(qq)) or "-"
    print(f"{qq:<40} | {','.join(short[t] for t in sorted(tables)):<22} | {cur:<14} | {why[:60]}")
