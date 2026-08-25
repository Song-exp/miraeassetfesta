# -*- coding: utf-8 -*-
"""shared 자동 생성기 — KG 를 "매핑 사전"에서 "그래프"로 (2026-08-25)

생성물 (GENERATED — 편집 금지, 이 스크립트로 재생성):
  ontology/shared/index_auto.yaml               Index 노드 자동 등록 (3원천) + 패밀리 parent + edge 2종
  ontology/shared/organization_issuer_auto.yaml 채권 발행사 Organization 노드 (role: issuer)

원천:
  domestic_etfs.ref_base_index (ETF 만, 센티넬 제외) · overseas_etfs.cu_base_index (센티넬 제외) · public_funds.bmrk_nm
  domestic_bonds.pd_pbcm
  public_funds.zrin_btyp_nm → asset_class.yaml 기존 노드에 alias_extensions

원칙:
  · 수동 파일(index.yaml 등)에 이미 등록된 (table, column, raw) 는 자동 파일에 넣지 않는다 (V2 충돌 방지).
    단, 수동 노드와 raw 가 완전히 같은 값이 다른 컬럼에 있으면 `alias_extensions` 로 그 노드에 덧붙인다.
  · 노드 id 는 정규화명 sha1 앞 10자리 — 재생성해도 불변.
  · 패밀리: 접미(TR/NR/CR/PR/GTR/NTR/GR), 통화, Daily/Hedged/(H), 레버리지 배수, Index 어미를 벗긴 라벨.
    변형 노드는 parent 로 패밀리를 가리켜 kg_closure 에 전개된다. 합성 벤치마크('A 50% + B 50%')는 분해하지 않고 composite: true.
  · edge: coversRegion(Index→Region) · hasAssetClass(Index→AssetClass) — 이름 키워드 규칙, source: rule.

사용: python scripts/gen_shared_auto.py   →  python scripts/build_ontology.py
"""
import hashlib, os, re, sqlite3, sys, unicodedata, collections
import yaml

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "financial_products.db")
SHARED = os.path.join(ROOT, "ontology", "shared")
OUT_IDX = os.path.join(SHARED, "index_auto.yaml")
OUT_ISS = os.path.join(SHARED, "organization_issuer_auto.yaml")
AS_OF = "2026-08-22"
SOURCE = "scripts/gen_shared_auto.py — 2차 DB distinct 자동 등록 (2026-08-25)"

SENTINELS = ("Index is not provided", "Index is not available")


def norm(v):
    return unicodedata.normalize("NFC", str(v).strip())


def hid(prefix, key):
    return prefix + hashlib.sha1(norm(key).lower().encode("utf-8")).hexdigest()[:10]


# ── 지수 패밀리 정규화 ────────────────────────────────────────────────
_SUFFIX_TOKENS = {"TR", "NR", "CR", "PR", "GTR", "NTR", "GR", "NTR.", "USD", "KRW", "JPY", "EUR", "HKD",
                  "CNY", "GBP", "CHF", "AUD", "CAD", "TWD", "INR", "SGD", "INDEX", "DAILY", "HEDGED",
                  "(H)", "(UH)", "H", "UH", "TOTAL", "RETURN", "NET", "PRICE", "GROSS", "지수"}
_LEV = re.compile(r"(?:\s|^)(?:-?\d+(?:\.\d+)?\s*[xX]|\d{2,3}%|inverse|leveraged|2배|인버스|레버리지)(?=\s|$)", re.I)
_PAREN_HEDGE = re.compile(r"\((?:KRW|USD|JPY|EUR)?\s*(?:HEDGED|H|UH)\)", re.I)


def is_composite(name):
    return "+" in name and "%" in name


def family_label(name):
    """변형명 → 패밀리 라벨. 바뀐 게 없으면 name 그대로(=자기 자신이 패밀리)."""
    s = norm(name)
    if is_composite(s):
        return s
    s = _PAREN_HEDGE.sub(" ", s)
    s = _LEV.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = s.split(" ")
    # 뒤에서부터 접미 토큰 제거 (앞쪽 본체는 건드리지 않음)
    while len(toks) > 1 and toks[-1].upper().strip(",") in _SUFFIX_TOKENS:
        toks.pop()
    # 'Daily'/'Hedged' 가 중간에 오는 경우 ("S&P 500 Daily JPY Hedged CR")
    toks = [t for t in toks if t.upper() not in {"DAILY", "HEDGED", "UNHEDGED"}] or toks
    fam = " ".join(toks).strip(" -,")
    return fam if fam else s


# ── edge 규칙 ─────────────────────────────────────────────────────────
_REGION_RULES = [  # (정규식, Region 노드 id) — 앞쪽이 우선
    (r"MSCI\s*(AC\s*)?WORLD\s*EX\s*USA|ACWI\s*EX\s*US|WORLD\s*EX\s*US", "Region_GlobalExUS"),
    (r"MSCI\s*ACWI|MSCI\s*AC\s*WORLD|FTSE\s*ALL[- ]WORLD|MSCI\s*WORLD|글로벌|GLOBAL|WORLD", "Region_Global"),
    (r"EMERGING|MSCI\s*EM\b|신흥|이머징|BRIC|브릭스|FRONTIER", "Region_Emerging"),
    (r"KOSPI|KRX|KOSDAQ|코스피|코스닥|KAP|종합채권|국공채|국고채|채권종합|KIS|KOFR|CD\s*금리|MK\s*|FnGuide|FN\s*|iSelect|WISE|한국|KOREA|제로인|CALL|통안", "Region_Korea"),
    (r"CSI|SSE|SZSE|HANG\s*SENG|HSCEI|항셍|중국|CHINA|CHINEXT|STAR\s*50|A50", "Region_China"),
    (r"NIKKEI|TOPIX|일본|JAPAN|JPX", "Region_Japan"),
    (r"NIFTY|SENSEX|인도|INDIA", "Region_India"),
    (r"VN\s*30|VIETNAM|베트남", "Region_Vietnam"),
    (r"EURO\s*STOXX|STOXX|EUROPE|유럽|DAX|FTSE\s*100|CAC|MSCI\s*EAFE|EMU", "Region_Europe"),
    (r"LATIN|BRAZIL|IBOVESPA|MEXICO|남미|중남미", "Region_LatinAmerica"),
    (r"ASIA|아시아|ASEAN|TAIWAN|TWSE|대만|INDONESIA|PHILIPPINE|THAILAND|MALAYSIA|SINGAPORE", "Region_Asia"),
    (r"MIDDLE\s*EAST|AFRICA|SAUDI|중동|아프리카", "Region_MEA"),
    (r"S&P|RUSSELL|NASDAQ|DOW\s*JONES|DJ\s|BLOOMBERG\s*U\.?S|US\s*TREASURY|U\.S\.|\bUS\b|MSCI\s*USA|CBOE|SOFR|미국|AMERICA|NYSE|WILSHIRE|CRSP|SOLACTIVE\s*US|ICE\s*BOFA\s*US|MORNINGSTAR\s*US", "Region_US"),
]
_ASSET_RULES = [
    (r"COMMODITY|GOLD|SILVER|OIL|CRUDE|WTI|BRENT|NATURAL\s*GAS|COPPER|원자재|금\s*선물|골드|은\s*선물|ROGERS|BLOOMBERG\s*COMMODITY|GSCI|METAL|AGRICULTURE", "AssetClass_Commodity"),
    (r"REIT|리츠|REAL\s*ESTATE|부동산|PROPERTY", "AssetClass_RealEstate"),
    (r"BOND|AGG|TREASURY|MUNICIPAL|CORP|CREDIT|HIGH\s*YIELD|MBS|TIPS|T-BILL|BILL|NOTE|채권|국채|국고채|국공채|통안|회사채|KTB|LKTB|CD\s*|CALL|SOFR|KOFR|MMF|MONEY\s*MARKET|CASH|단기자금|금리|FLOATING|LOAN|YIELD", "AssetClass_Bond"),
    (r"USDKRW|KRWUSD|DOLLAR|DXY|CURRENCY|환율|달러|엔화|위안", "AssetClass_Currency"),
    (r"VOLATILITY|VIX|ALTERNATIVE|대안투자|절대수익|HEDGE\s*FUND|BUYWRITE|BXM|COVERED\s*CALL|커버드콜", "AssetClass_Alternatives"),
]
_ZRIN_BTYP_TO_AC = {
    "주식형": "AssetClass_Equity", "해외주식형": "AssetClass_Equity",
    "채권형": "AssetClass_Bond", "해외채권형": "AssetClass_Bond",
    "주식혼합형": "AssetClass_Mixed", "채권혼합형": "AssetClass_Mixed",
    "해외주식혼합형": "AssetClass_Mixed", "해외채권혼합형": "AssetClass_Mixed",
    "MMF": "AssetClass_MoneyMarket", "외화 MMF": "AssetClass_MoneyMarket",
    "부동산형": "AssetClass_RealEstate", "해외부동산형": "AssetClass_RealEstate",
    "커머더티형": "AssetClass_Commodity",
    "특별자산": "AssetClass_Alternatives", "해외특별자산": "AssetClass_Alternatives",
    "절대수익추구형": "AssetClass_Alternatives",
    # '기타' · '해외기타' 는 의도적으로 미매핑 — 리포트에 남긴다
}


def rule_hit(rules, name):
    up = norm(name).upper()
    for pat, node in rules:
        if re.search(pat, up, re.I):
            return node
    return None


def asset_for(name):
    if is_composite(name):
        return "AssetClass_Mixed"
    return rule_hit(_ASSET_RULES, name) or "AssetClass_Equity"   # 기본 Equity (규칙 미적중은 별도 집계)


def region_for(name):
    if is_composite(name):
        # 합성은 첫 구성요소 기준
        name = name.split("+")[0]
    return rule_hit(_REGION_RULES, name)


# ── 수동 shared 읽기 ───────────────────────────────────────────────────
def load_manual(name):
    with open(os.path.join(SHARED, name), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def manual_alias_index(doc):
    """(table, column, norm(raw)) → node_id  /  norm(raw) → node_id (표기 완전일치용)"""
    by_key, by_raw = {}, {}
    for nid, node in (doc.get("nodes") or {}).items():
        for al in node.get("aliases") or []:
            if al.get("status", "confirmed") != "confirmed":
                continue
            by_key[(al["table"], al["column"], norm(al["raw"]))] = nid
            by_raw.setdefault(norm(al["raw"]), nid)
    return by_key, by_raw


def yaml_dump(doc):
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200)


# ── Index ─────────────────────────────────────────────────────────────
def build_index(con):
    manual = load_manual("index.yaml")
    m_key, m_raw = manual_alias_index(manual)
    region_ids = set((load_manual("region.yaml").get("nodes") or {}).keys())
    ac_ids = set((load_manual("asset_class.yaml").get("nodes") or {}).keys())

    sources = [
        ("domestic_etfs", "ref_base_index",
         "select ref_base_index, count(*) from domestic_etfs where pd_grp_no='ETF' and ref_base_index is not null and trim(ref_base_index)<>'' group by 1"),
        ("overseas_etfs", "cu_base_index",
         "select cu_base_index, count(*) from overseas_etfs where cu_base_index is not null and trim(cu_base_index)<>'' group by 1"),
        ("public_funds", "bmrk_nm",
         "select bmrk_nm, count(*) from public_funds where bmrk_nm is not null and trim(bmrk_nm)<>'' group by 1"),
    ]
    nodes = {}          # node_id → node dict
    pending = []        # (table, col, raw, n) — 패밀리 집계 후 노드화
    ext = collections.defaultdict(list)   # manual node_id → [alias]
    stats = collections.Counter()
    for table, col, sql in sources:
        for raw, n in con.execute(sql):
            r = norm(raw)
            if any(r.startswith(s) for s in SENTINELS):
                stats["sentinel"] += 1
                continue
            if (table, col, r) in m_key:
                stats["manual_exists"] += 1
                continue
            if r in m_raw:   # 같은 표기가 수동 노드에 다른 컬럼으로 등록 → 확장
                ext[m_raw[r]].append({"table": table, "column": col, "raw": r, "source": "rule",
                                      "evidence": f"수동 노드와 표기 완전일치 · {n}행"})
                stats["extension"] += 1
                continue
            pending.append((table, col, r, n))
    # 패밀리는 변형이 2개 이상 모일 때만 만든다 (단독 변형은 자기 자신이 노드 — 싱글턴 패밀리 폭증 방지)
    fam_members = collections.defaultdict(set)
    for table, col, r, n in pending:
        fam = family_label(r)
        if fam != r:
            fam_members[fam].add(r)
    for table, col, r, n in pending:
        fam = family_label(r)
        composite = is_composite(r)
        if fam != r and (len(fam_members[fam]) >= 2 or hid("Idx_a_", fam) in nodes):
            fid = hid("Idx_a_", fam)
            nodes.setdefault(fid, {"label_ko": fam, "aliases": [], "auto": True, "family": True})
            nid = hid("Idx_v_", r)
            node = nodes.setdefault(nid, {"label_ko": r, "parent": fid, "aliases": [], "auto": True})
        else:
            nid = hid("Idx_a_", r)
            node = nodes.setdefault(nid, {"label_ko": r, "aliases": [], "auto": True})
            if composite:
                node["composite"] = True
        node["aliases"].append({"table": table, "column": col, "raw": r, "source": "rule",
                                "evidence": f"{table}.{col} distinct · {n}행"})
        stats["node_alias"] += 1

    # edge — 자동 노드 전부 (패밀리 포함)
    edges, miss_region, miss_asset_default = [], 0, 0
    for nid, node in nodes.items():
        lab = node["label_ko"]
        reg = region_for(lab)
        if reg and reg in region_ids:
            edges.append({"src": nid, "predicate": "coversRegion", "dst": reg, "source": "rule", "as_of": AS_OF})
        else:
            miss_region += 1
        ac = asset_for(lab)
        if ac in ac_ids:
            edges.append({"src": nid, "predicate": "hasAssetClass", "dst": ac, "source": "rule", "as_of": AS_OF})
        if not is_composite(lab) and rule_hit(_ASSET_RULES, lab) is None:
            miss_asset_default += 1   # Equity 기본값으로 떨어진 건수

    # zrin_btyp_nm → AssetClass 확장 (asset_class.yaml 기존 노드)
    ac_ext = collections.defaultdict(list)
    ac_manual = load_manual("asset_class.yaml")
    ac_key, _ = manual_alias_index(ac_manual)
    n_btyp = 0
    for raw, n in con.execute("select zrin_btyp_nm, count(*) from public_funds where zrin_btyp_nm is not null group by 1"):
        r = norm(raw)
        target = _ZRIN_BTYP_TO_AC.get(r)
        if not target or target not in ac_ids or ("public_funds", "zrin_btyp_nm", r) in ac_key:
            continue
        ac_ext[target].append({"table": "public_funds", "column": "zrin_btyp_nm", "raw": r, "source": "rule",
                               "evidence": f"제로인 대분류 규칙 매핑 · {n}행"})
        n_btyp += 1

    fam_n = sum(1 for v in nodes.values() if v.get("family"))
    var_n = sum(1 for v in nodes.values() if v.get("parent"))
    header = (
        "# GENERATED — 편집 금지. 재생성: python scripts/gen_shared_auto.py\n"
        f"# source={SOURCE}\n# as_of={AS_OF}\n"
        "# Index 자동 등록: domestic_etfs.ref_base_index(ETF) · overseas_etfs.cu_base_index(센티넬 제외) · public_funds.bmrk_nm\n"
        f"# 노드 {len(nodes)} (패밀리 {fam_n} · 변형 {var_n} · 단독 {len(nodes)-fam_n-var_n}) · alias {stats['node_alias']} · "
        f"수동 노드 확장 {stats['extension']} · 수동 중복 제외 {stats['manual_exists']} · 센티넬 제외 {stats['sentinel']}\n"
        f"# edge {len(edges)} (coversRegion 미적중 {miss_region} · hasAssetClass 기본값(Equity) {miss_asset_default})\n"
        "# 수동 index.yaml 과 같은 entity 를 선언한다 — build_ontology 가 class/property 중복 선언을 억제한다.\n"
    )
    doc = {
        "entity": "Index", "description": "기초지수·벤치마크 (자동 등록분)", "property": "tracksIndex",
        "generated": True, "source": SOURCE, "as_of": AS_OF,
        "nodes": nodes,
        "alias_extensions": dict(ext),
        "edges": edges,
    }
    ac_doc_ext = dict(ac_ext)
    with open(OUT_IDX, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + yaml_dump(doc))
    return {"nodes": len(nodes), "family": fam_n, "variant": var_n, "alias": stats["node_alias"],
            "ext": stats["extension"], "edges": len(edges), "miss_region": miss_region,
            "asset_default": miss_asset_default, "btyp_ext": n_btyp, "ac_ext": ac_doc_ext,
            "family_examples": sorted([(v["label_ko"], [nodes[k]["label_ko"] for k in nodes if nodes[k].get("parent") == nid])
                                for nid, v in nodes.items() if v.get("family")], key=lambda x: -len(x[1]))[:8]}


# ── 채권 발행사 ────────────────────────────────────────────────────────
_CORP = re.compile(r"\(주\)|주식회사|㈜|\(유\)|유한회사|\s+")


def issuer_key(name):
    s = norm(name)
    s = re.sub(r"\($", "", s)          # 잘린 괄호 '…유동화전문('
    return _CORP.sub("", s)


def build_issuers(con):
    rows = con.execute("select trim(pd_pbcm), count(*) from domestic_bonds where pd_pbcm is not null and trim(pd_pbcm)<>'' group by 1").fetchall()
    groups = collections.defaultdict(list)
    for raw, n in rows:
        groups[issuer_key(raw)].append((norm(raw), n))
    nodes = {}
    merged = 0
    for key, vs in groups.items():
        if not key:
            continue
        vs.sort(key=lambda x: -x[1])
        label = re.sub(r"\(주\)|주식회사|㈜", "", vs[0][0]).strip().rstrip("(")
        nid = hid("Org_issuer_", key)
        nodes[nid] = {"label_ko": label or key, "role": "issuer", "auto": True,
                      "aliases": [{"table": "domestic_bonds", "column": "pd_pbcm", "raw": r, "source": "rule",
                                   "evidence": f"발행사명 정규화 · {n}행"} for r, n in vs]}
        merged += len(vs) - 1
    header = (
        "# GENERATED — 편집 금지. 재생성: python scripts/gen_shared_auto.py\n"
        f"# source={SOURCE}\n# as_of={AS_OF}\n"
        "# 채권 발행사: domestic_bonds.pd_pbcm distinct → '(주)'/'주식회사'/공백 제거 키로 법인 단위 병합. role: issuer\n"
        f"# 노드 {len(nodes)} · 표기 변형 병합 {merged} · 원 distinct {len(rows)}\n"
        "# 운용사 노드(organization.yaml Org_000…)와는 별개. property 는 hasIssuer (운용사 hasManager 와 구분)\n"
    )
    doc = {"entity": "Organization", "description": "채권 발행사 (자동 등록분, role=issuer)", "property": "hasIssuer",
           "generated": True, "source": SOURCE, "as_of": AS_OF, "nodes": nodes}
    with open(OUT_ISS, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + yaml_dump(doc))
    return {"nodes": len(nodes), "merged": merged, "distinct": len(rows)}


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ix = build_index(con)
    iss = build_issuers(con)
    # AssetClass 확장은 index_auto.yaml 에 같이 싣는다 (alias_extensions 는 어느 파일에 있어도 대상 노드로 귀속)
    with open(OUT_IDX, encoding="utf-8") as f:
        doc_text = f.read()
    doc = yaml.safe_load(doc_text)
    doc["alias_extensions"].update(ix["ac_ext"])
    head = "\n".join(l for l in doc_text.splitlines() if l.startswith("#")) + "\n"
    with open(OUT_IDX, "w", encoding="utf-8", newline="\n") as f:
        f.write(head + yaml_dump(doc))
    print(f"index_auto.yaml: 노드 {ix['nodes']} (패밀리 {ix['family']} · 변형 {ix['variant']}) · alias {ix['alias']} · "
          f"수동확장 {ix['ext']} · edge {ix['edges']} · coversRegion 미적중 {ix['miss_region']} · Equity 기본값 {ix['asset_default']} · zrin_btyp 확장 {ix['btyp_ext']}")
    print("패밀리 예시:", ix["family_examples"][:6])
    print(f"organization_issuer_auto.yaml: 노드 {iss['nodes']} · 표기 변형 병합 {iss['merged']} · 원 distinct {iss['distinct']}")


if __name__ == "__main__":
    main()
