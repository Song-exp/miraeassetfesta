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
import csv
import hashlib, os, re, sqlite3, sys, unicodedata, collections
import yaml

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "financial_products.db")
SHARED = os.path.join(ROOT, "ontology", "shared")
OUT_IDX = os.path.join(SHARED, "index_auto.yaml")
OUT_ISS = os.path.join(SHARED, "organization_issuer_auto.yaml")
OUT_MGR = os.path.join(SHARED, "organization_manager_auto.yaml")
CODEBOOKS = os.path.join(ROOT, "ontology", "codebooks")
LOOKUPS = os.path.join(ROOT, "data", "external", "lookups")
AS_OF = "2026-08-22"
SOURCE = "scripts/gen_shared_auto.py — 2차 DB distinct 자동 등록 (2026-08-25)"

SENTINELS = ("Index is not provided", "Index is not available")


def norm(v):
    return unicodedata.normalize("NFC", str(v).strip())


def hid(prefix, key):
    return prefix + hashlib.sha1(norm(key).lower().encode("utf-8")).hexdigest()[:10]


def ihid(prefix, key):
    """지수 노드 키 — 공백을 접고 대소문자를 무시한다.

    🔴 2026-09-04 — SQL 조회는 공백을 무시하는데(query_rules.어휘_표기정규화: replace(...,' ','')로
       KOSPI200 0→95행) 노드 키는 공백으로 갈려 'KRX 300'/'KRX300' · 'MSCI CHINA'/'MSCI China' ·
       'KOSDAQ 150'/'KOSDAQ150' 이 서로 다른 노드가 됐다. 두 층의 정규화를 맞춘다.
       ⚠️ 숫자·기호는 지우지 않는다 — 'ICE BofA 1-5 Year' 와 '15+ Year' 는 **다른 지수**다."""
    return prefix + hashlib.sha1(re.sub(r"\s+", "", norm(key)).lower().encode("utf-8")).hexdigest()[:10]


# ── 지수 패밀리 정규화 ────────────────────────────────────────────────
_SUFFIX_TOKENS = {"TR", "NR", "CR", "PR", "GTR", "NTR", "GR", "NTR.", "USD", "KRW", "JPY", "EUR", "HKD",
                  "CNY", "GBP", "CHF", "AUD", "CAD", "TWD", "INR", "SGD", "INDEX", "DAILY", "HEDGED",
                  "(H)", "(UH)", "H", "UH", "TOTAL", "RETURN", "NET", "PRICE", "GROSS", "지수"}
_LEV = re.compile(r"(?:\s|^)(?:-?\d+(?:\.\d+)?\s*[xX]|\d{2,3}%|inverse|leveraged|2배|인버스|레버리지)(?=\s|$)", re.I)
_PAREN_HEDGE = re.compile(r"\((?:KRW|USD|JPY|EUR)?\s*(?:HEDGED|H|UH)\)", re.I)


def is_composite(name):
    # "A 50% + B 50%" 또는 "60% A/40% B" — 두 형태 모두 합성 벤치마크
    return "%" in name and ("+" in name or bool(re.search(r"\d+\s*%[^/]*/", name)))


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
# 2026-08-25 검수 B 정정: 부분문자열 오탐(MK→Mkt, SSE→Russell/Asset, CALL→Covered Call, YIELD→Dividend Yield,
# JAPAN→"ex Japan", S&P→S&P/ASX·BSE·TSX) 를 단어 경계·가드로 막고 국가 노드(region.yaml 2026-08-25 추가분)로 세분화.
# 규칙보다 codebooks/index_axis_override.csv 가 우선한다 (라벨 완전일치, 대소문자 무시).
_REGION_RULES = [  # (정규식, Region 노드 id) — 앞쪽이 우선
    (r"NORTH\s*AMERICA|북미", "Region_NorthAmerica"),
    (r"LATIN\s*AMERICA|LATAM|중남미|남미", "Region_LatinAmerica"),
    (r"WORLD\s*EX[- ]?USA?|ACWI\s*EX[- ]?USA?|EX[- ]?US\b|EX[- ]?USA\b|\bEAFE\b|DM\s*EX\s*NA|INTERNATIONAL\s*(EQUITY|DEVELOPED)|DEVELOPED\s*EX", "Region_GlobalExUS"),
    (r"MSCI\s*ACWI|MSCI\s*AC\s*WORLD|ALL[- ]?COUNTRY\s*WORLD|FTSE\s*ALL[- ]WORLD|FTSE\s*AW\b|MSCI\s*WORLD|MSCI\s*WI\b|WORLD|글로벌|GLOBAL|\bGBI\b|\bEMBI\b|\bGBL\b", "Region_Global"),
    (r"EMERGING|MSCI\s*EM\b|\bEM\s+(ASIA|EUROPE|LATIN|EMEA|LOCAL|BOND|BND)|신흥|이머징|BRIC|브릭스|FRONTIER\s*MARKET|GBI-EM", "Region_Emerging"),
    (r"\bASX\b|AUSTRALIA|호주", "Region_Australia"),
    (r"\bTSX\b|CANADA|캐나다", "Region_Canada"),
    (r"\bDAX\b|GERMANY|독일", "Region_Germany"),
    (r"\bCAC\b|FRANCE|프랑스", "Region_France"),
    (r"FTSE\s*(100|250|350)|\bUK\b|UNITED\s*KINGDOM|BRITAIN|영국", "Region_UK"),
    (r"\bIBEX\b|SPAIN|스페인", "Region_Spain"),
    (r"\bSMI\b|SWISS|SWITZERLAND|스위스", "Region_Switzerland"),
    (r"NETHERLANDS|네덜란드|\bAEX\b", "Region_Netherlands"),
    (r"ITALY|이탈리아|FTSE\s*MIB", "Region_Italy"),
    (r"EURO\s*STOXX|STOXX|EUROPE|유럽|EUROZONE|\bEMU\b|유로", "Region_Europe"),
    (r"BRAZIL|IBOVESPA|브라질", "Region_Brazil"),
    (r"MEXICO|멕시코", "Region_Mexico"),
    (r"ISRAEL|이스라엘|TA-?35|TA-?125", "Region_Israel"),
    (r"SAUDI|사우디", "Region_SaudiArabia"),
    (r"SOUTH\s*AFRICA|남아공", "Region_SouthAfrica"),
    (r"TURKEY|TURKIYE|튀르키예|터키", "Region_Turkey"),
    (r"MIDDLE\s*EAST|AFRICA|중동|아프리카|GULF|\bGCC\b|\bMENA\b", "Region_MEA"),
    (r"\bKOSPI|\bKRX\d*\b|\bKTOP\b|KOSDAQ|코스피|코스닥|\bKAP\b|종합채권|국공채|국고채|채권종합|\bKIS\b|\bKOFR\b|\bCD\s*금리|\bMKF?\b|FNGUIDE|\bFN\b|ISELECT|\bWISE\b|한국|KOREA|제로인|통안|\bKTB\b|\bLKTB\b|콜금리|(?<!COVERED\s)(?<!COVERED)\bCALL\b(?!\s*BALANCED)|회사채", "Region_Korea"),
    (r"HANG\s*SENG(?!.*(CHINA|ENTERPRISE|H-SHARE))|HONG\s*KONG|홍콩", "Region_HongKong"),
    (r"\bCSI[\s_]?\d|\bCSI\b|\bSSE\b|SZSE|ZHONG\s*HUA|HANG\s*SENG|HSCEI|항셍|중국|CHINA|CHINEXT|STAR\s*50|\bA50\b|심천|상해|상하이|차이나", "Region_China"),
    (r"TAIWAN|TWSE|TAIEX|대만", "Region_Taiwan"),
    (r"INDONESIA|인도네시아", "Region_Indonesia"),
    (r"THAILAND|태국", "Region_Thailand"),
    (r"MALAYSIA|말레이시아", "Region_Malaysia"),
    (r"PHILIPPINE|필리핀", "Region_Philippines"),
    (r"SINGAPORE|싱가포르|싱가폴", "Region_Singapore"),
    (r"VN\s*30|VN\s*INDEX|\bVN\b|VIETNAM|베트남|호치민", "Region_Vietnam"),
    (r"NIKKEI|TOPIX|\bJPX\b|(?<!EX\s)(?<!EX)JAPAN(?!\s*EX)|(?<!EX )일본", "Region_Japan"),
    (r"NIFTY|SENSEX|\bBSE\b|(?<!W\s)INDIA\b|인도", "Region_India"),
    (r"ASIA|아시아|ASEAN|동남아|\bJACI\b|PAN[- ]ASIA", "Region_Asia"),
    (r"S&P\s*5|S&P\s*4|S&P\s*6|S&P\s*1500|S&P\s*(MID|SMALL|LARGE)|SELECT\s*SECTOR|SELECT\s*INDUSTRY|RUSSELL|NASDAQ|나스닥|DOW\s*JONES|다우|\bDJ\s|DJIA|BLOOMBERG\s*U\.?S|BLOOMBERG\s*US\b|US\s*TREASURY|U\.S\.|\bUS\b|\bUSA\b|UNITED\s*STATES|MSCI\s*USA|CBOE|\bPHLX\b|SOFR|미국|(?<!LATIN\s)(?<!NORTH\s)(?<!SOUTH\s)AMERICA\b|NYSE|WILSHIRE|CRSP|MUNICIPAL|\bMUNI\b|ICE\s*BOFA\s*US|MORNINGSTAR\s*US|ICE\s*U\.S", "Region_US"),
    # 폴백: 위 규칙에 안 걸린 S&P·iBoxx USD·ICE BofA Core/Pref 는 미국 (S&P GSCI 원자재는 지역 없음)
    (r"S&P(?!\s*GSCI)|IBOXX\s*(USD|\$)|ICE\s*BOFA\s*(CORE|PREF|FIXED|ALL\s*CAP)", "Region_US"),
]
# 자산군 — 앞쪽이 우선. 주식 강제(광산·배당 등)는 채권·원자재 키워드보다 먼저 본다.
_ASSET_RULES = [
    (r"MINERS|MINING|광업|금광|PRODUCERS|EXPLORATION|EQUIPMENT|DIVIDEND|배당|SHAREHOLDER|EQUITY|STOCK|주식|\bETF\s*TRUST", "AssetClass_Equity"),
    (r"TREASURY\s*BALANCED|BALANCED\s*\d+|/\s*\d+\s*%|\d+\s*%\s*/|ALLOCATION|자산배분|혼합", "AssetClass_Mixed"),
    (r"BITCOIN|ETHER\b|ETHEREUM|CRYPTO|SOLANA|\bXRP\b|DIGITAL\s*ASSET|VOLATILITY|\bVIX\b|ALTERNATIVE|대안투자|절대수익|HEDGE\s*FUND|BUYWRITE|\bBXM\b|COVERED\s*CALL|커버드콜|MANAGED\s*FUTURES|LONG/SHORT", "AssetClass_Alternatives"),
    (r"COMMODITY|\bGOLD\b|SILVER|\bOIL\b|CRUDE|\bWTI\b|BRENT|NATURAL\s*GAS|COPPER|원자재|금\s*선물|골드|은\s*선물|ROGERS|GSCI|METALS?\b|AGRICULTURE|CARBON\s*CREDIT|URANIUM\s*(FUTURES|PRICE)|\bLBMA\b|PLATINUM|PALLADIUM|LITHIUM\s*PRICE", "AssetClass_Commodity"),
    (r"\bREITS?\b|리츠|REAL\s*ESTATE|부동산|PROPERTY", "AssetClass_RealEstate"),
    (r"\bMMF\b|MONEY\s*MARKET|\bCD\s*금리|\bCD\s+\d|콜금리|(?<!COVERED\s)(?<!COVERED)\bCALL\b(?!\s*BALANCED)|T-?BILLS?\b|\bBILLS?\b|SOFR|KOFR|단기자금|3-MONTH|1-3\s*MONTH", "AssetClass_MoneyMarket"),
    (r"\bBONDS?\b|\bAGG\b|AGGREGATE|TREASUR|MUNICIPAL|\bMUNI\b|\bCORP\b|CORPORATE|(?<!CARBON\s)CREDIT|HIGH\s*YI?E?I?LD|\bHY\b|\bMBS\b|\bTIPS\b|\bNOTES?\b|채권|국채|국고채|국공채|통안|회사채|\bKTB\b|\bLKTB\b|IBOXX|INVESTMENT\s*GRADE|\bIG\b|FLOATING|\bLOAN\b|FIXED\s*(RATE|INCOME)|PREF(ERRED)?\b|PREF\s*SEC|\bGBI\b|\bEMBI\b|\bJACI\b|INFLATION\s*LINKED|DURATION|YIELD|금리|GOVERNMENT", "AssetClass_Bond"),
    (r"USDKRW|KRWUSD|DOLLAR|\bDXY\b|CURRENCY|환율|달러|엔화|위안|BUYING\s*RATE|EXCHANGE\s*RATE|\bFX\b", "AssetClass_Currency"),
    # 양성 주식 규칙 — 지수 제공사·주식 전용 어휘. 기본값(Equity) 폴백을 "규칙 적중" 으로 바꿔 미확정 집계를 줄인다
    (r"MSCI|RUSSELL|S&P\s*\d|S&P\s*(MID|SMALL|LARGE|EQUAL|TOTAL|COMPOSITE)|NASDAQ|나스닥|KOSPI|KOSDAQ|코스피|코스닥|\bKRX\d*\b|KTOP|TOPIX|NIKKEI|NIFTY|SENSEX|\bCSI[\s_]?\d|\bSSE\b|HANG\s*SENG|항셍|FTSE|STOXX|\bDAX\b|\bCAC\b|IBEX|DOW\s*JONES|다우|WILSHIRE|CRSP|SOLACTIVE|INDXX|BITA|MORNINGSTAR|SELECT\s*SECTOR|GROWTH|VALUE|\bCAP\b|SMALL[- ]CAP|MID[- ]CAP|LARGE[- ]CAP|SEMICONDUCTOR|BIOTECH|HEALTH\s*CARE|FINANCIALS?\b|INFRASTRUCTURE|\bMLP\b|TECHNOLOGY|INTERNET|ROBOT|\bAI\b|ESG|호치민|VN\s*INDEX|\bVN\b", "AssetClass_Equity"),
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

OVERRIDE_CSV = os.path.join(ROOT, "ontology", "codebooks", "index_axis_override.csv")


def _load_override():
    """라벨 완전일치(정규화·대소문자 무시) → (region_node, asset_node). 규칙보다 우선."""
    ov = {}
    if os.path.exists(OVERRIDE_CSV):
        with open(OVERRIDE_CSV, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                ov[norm(r["index_label"]).casefold()] = (r.get("region_node") or None, r.get("asset_class_node") or None)
    return ov


_OVERRIDE = _load_override()


def rule_hit(rules, name):
    up = norm(name).upper()
    for pat, node in rules:
        if re.search(pat, up, re.I):
            return node
    return None


def asset_for(name):
    ov = _OVERRIDE.get(norm(name).casefold())
    if ov and ov[1]:
        return ov[1]
    if is_composite(name):
        return "AssetClass_Mixed"
    return rule_hit(_ASSET_RULES, name) or "AssetClass_Equity"   # 기본 Equity (규칙 미적중은 별도 집계)


def asset_is_default(name):
    """Equity 기본값으로 떨어진 것(override·합성·규칙 적중 아님)."""
    ov = _OVERRIDE.get(norm(name).casefold())
    return not (ov and ov[1]) and not is_composite(name) and rule_hit(_ASSET_RULES, name) is None


def region_for(name):
    ov = _OVERRIDE.get(norm(name).casefold())
    if ov and ov[0]:
        return ov[0]
    if is_composite(name):
        # 합성은 첫 구성요소 기준 ("60% A/40% B" 는 첫 % 뒤 이름)
        name = re.split(r"\+|/", name)[0]
        name = re.sub(r"^\s*\d+\s*%", "", name)
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
    m_raw_ns = {}                                  # 공백 접은 키 → 수동 노드 (라벨도 함께 등록)
    for _r, _nid in m_raw.items():
        m_raw_ns.setdefault(re.sub(r"\s+", "", _r).lower(), _nid)
    for _nid, _nd in (manual.get("nodes") or {}).items():
        for _lab in (_nd.get("label_ko"), _nd.get("label_en")):
            if _lab:
                m_raw_ns.setdefault(re.sub(r"\s+", "", norm(_lab)).lower(), _nid)
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
            # 🔴 2026-09-04 — 수동 노드 대조도 **공백을 접어서** 본다. 완전일치만 보면
            #    수동 'KRX 300' 과 DB 'KRX300' 이 남남이 되어 자동 노드가 따로 생긴다(실측).
            m_hit = m_raw.get(r) or m_raw_ns.get(re.sub(r"\s+", "", r).lower())
            if m_hit:
                ext[m_hit].append({"table": table, "column": col, "raw": r, "source": "rule",
                                   "evidence": f"수동 노드와 표기 일치(공백 무시) · {n}행"})
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
        if fam != r and (len(fam_members[fam]) >= 2 or ihid("Idx_a_", fam) in nodes):
            fid = ihid("Idx_a_", fam)
            nodes.setdefault(fid, {"label_ko": fam, "aliases": [], "auto": True, "family": True})
            nid = ihid("Idx_v_", r)
            node = nodes.setdefault(nid, {"label_ko": r, "parent": fid, "aliases": [], "auto": True})
        else:
            nid = ihid("Idx_a_", r)
            node = nodes.setdefault(nid, {"label_ko": r, "aliases": [], "auto": True})
            if composite:
                node["composite"] = True
        node["aliases"].append({"table": table, "column": col, "raw": r, "source": "rule",
                                "evidence": f"{table}.{col} distinct · {n}행"})
        stats["node_alias"] += 1

    # ── 복합 벤치마크 성분 alias (2026-08-31 R-7/P1-4 · E-3-12: KOSPI200 47%·MSCI ACWI 83% 손실) ──
    # 복합식 raw("KOSPI200 25% + 종합채권01Y 75%")를 성분 지수 노드에도 매달아, "KOSPI200 추종 펀드" 의
    # target_aliases 가 복합식 행을 덮게 한다.
    # 🔴 한 raw 가 여러 노드에 달리는 **의도적** 다중 매핑 — source='rule_component' 로 표시하고
    #    build_ontology V2(raw 충돌) 검증에서 면제한다.
    # 🔴 대상은 public_funds.bmrk_nm 만 — ETF 의 Blend·Covered Call 류는 지수추종_순수 규칙이
    #    일부러 배제하는 설계라(키움 대조 #6) 성분 부착이 그 설계와 충돌한다.
    def _comp_key(s):
        return re.sub(r"\s+", "", norm(s)).casefold()

    comp_lookup = {}
    for mid, mnode in (manual.get("nodes") or {}).items():
        for lab in (mnode.get("label_ko"), mnode.get("label_en")):
            if lab:
                comp_lookup.setdefault(_comp_key(lab), mid)
    for (_t, _c, _r), mid in m_key.items():
        comp_lookup.setdefault(_comp_key(_r), mid)
    for _nid, _node in nodes.items():
        if not _node.get("composite"):
            comp_lookup.setdefault(_comp_key(_node["label_ko"]), _nid)
            # 'MSCI EM (Emerging Markets)' 를 'MSCI EM' 키로도 — 성분 표기는 괄호 부연을 뺀 짧은 쪽이 많다
            _short = re.sub(r"\([^)]*\)", " ", _node["label_ko"]).strip()
            if _short and _short != _node["label_ko"]:
                comp_lookup.setdefault(_comp_key(_short), _nid)

    _WEIGHT = re.compile(r"[×xX]?\s*\d+(?:\.\d+)?\s*%")
    comp_seen, comp_unmatched = set(), collections.Counter()
    # 자동 경로(pending) + 🔴 수동 index.yaml 에 자기 노드로 등록된 복합식(Idx_Composite_* — 'MSCI ACWI CR 50%
    # + 종합채권01Y 50%' 816행처럼 대형 건이 이쪽이다. m_key 에 걸려 pending 을 안 타므로 따로 돈다)
    comp_candidates = [(t, c, r, n) for t, c, r, n in pending]
    for _mid, _mnode in (manual.get("nodes") or {}).items():
        for _mal in (_mnode.get("aliases") or []):
            if (_mal.get("table"), _mal.get("column")) == ("public_funds", "bmrk_nm"):
                comp_candidates.append(("public_funds", "bmrk_nm", norm(_mal.get("raw") or ""), 0))
    for table, col, r, n in comp_candidates:
        if (table, col) != ("public_funds", "bmrk_nm") or not is_composite(r) or r in comp_seen:
            continue
        comp_seen.add(r)
        for part in (r.split("+") if "+" in r else r.split("/")):
            name = re.sub(r"\s+", " ", _WEIGHT.sub(" ", part)).strip(" ·,-")   # 괄호는 벗기지 않는다 — '(KRW HEDGED)' 가 이름의 일부
            if not name:
                continue
            # 매칭 사다리: 표기 그대로 → 패밀리 라벨('MSCI ACWI CR'→'MSCI ACWI') → 꼬리 괄호 제거 → 그 패밀리
            target = None
            for cand in (name, family_label(name),
                         re.sub(r"\([^)]*\)\s*$", "", name).strip(),
                         family_label(re.sub(r"\([^)]*\)\s*$", "", name).strip())):
                if cand:
                    target = comp_lookup.get(_comp_key(cand))
                    if target:
                        break
            if not target:
                comp_unmatched[name] += 1
                continue
            al = {"table": table, "column": col, "raw": r, "source": "rule_component",
                  "evidence": f"복합식 성분 '{name}' — E-3-12 · {n}행"}
            (nodes[target]["aliases"] if target in nodes else ext[target]).append(al)
            stats["component_alias"] += 1

    # edge — 자동 노드 전부 (패밀리 포함)
    edges, miss_region, miss_asset_default = [], 0, 0
    # 수동 index.yaml 노드에도 같은 규칙/override 로 edge 를 만든다 (2026-08-25 검수 B — 상위 BM 대부분이 수동 노드였음)
    targets = [(nid, node["label_ko"]) for nid, node in nodes.items()] + \
              [(nid, node.get("label_ko") or node.get("label_en") or "") for nid, node in (manual.get("nodes") or {}).items()]
    for nid, lab in targets:
        reg = region_for(lab)
        src = "override" if _OVERRIDE.get(norm(lab).casefold()) else "rule"
        if reg and reg in region_ids:
            edges.append({"src": nid, "predicate": "coversRegion", "dst": reg, "source": src, "as_of": AS_OF})
        else:
            miss_region += 1
        ac = asset_for(lab)
        if ac in ac_ids:
            edges.append({"src": nid, "predicate": "hasAssetClass", "dst": ac, "source": src, "as_of": AS_OF})
        if asset_is_default(lab):
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
        f"# 복합식 성분 alias {stats['component_alias']} (복합식 {len(comp_seen)}종 · 미매칭 성분 {len(comp_unmatched)}종: "
        + " · ".join(f"{k}" for k, _ in comp_unmatched.most_common(6)) + ")\n"
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


def _kind_vocabulary(con):
    """채권 종류·분류 어휘 — 발행사 칸에 이 낱말이 들어 있으면 그것은 발행사가 아니라 오염값이다."""
    vocab = set()
    for col in ("bd_knd", "std_pd_mcls_nm", "std_pd_scls_nm"):
        for (v,) in con.execute(f"select distinct trim({col}) from domestic_bonds where {col} is not null and trim({col})<>''"):
            vocab.add(norm(v))
    return vocab


def build_issuers(con):
    rows = con.execute("select trim(pd_pbcm), count(*) from domestic_bonds where pd_pbcm is not null and trim(pd_pbcm)<>'' group by 1").fetchall()
    # 🔴 2026-09-04 서버 실측 #61 — pd_pbcm 에 종류명이 들어간 오염 1행('국고채권' · KRC035AP28C9
    #    국고채원금분리채권)이 Org_issuer 노드가 되는 바람에, '국고채' 질의가 **종류가 아니라 발행사**로
    #    접지되고 값 검사 힌트까지 그 컬럼을 지목해 "국공채 몇 종목" 이 오거절로 끝났다(정답 1,775).
    #    종류·분류 어휘와 겹치는 발행사명은 노드로 만들지 않는다 — 이름이 아니라 종류이기 때문이다.
    kinds = _kind_vocabulary(con)
    polluted = [(r, n) for r, n in rows if norm(r) in kinds]
    rows = [(r, n) for r, n in rows if norm(r) not in kinds]
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
        + (f"# 종류 어휘와 겹쳐 제외한 오염 표기 {len(polluted)}: "
           + " · ".join(f"{r}({n}행)" for r, n in polluted) + " — 2026-09-04 #61\n" if polluted else "")
        + "# 운용사 노드(organization.yaml Org_000…)와는 별개. property 는 hasIssuer (운용사 hasManager 와 구분)\n"
    )
    doc = {"entity": "Organization", "description": "채권 발행사 (자동 등록분, role=issuer)", "property": "hasIssuer",
           "generated": True, "source": SOURCE, "as_of": AS_OF, "nodes": nodes}
    with open(OUT_ISS, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + yaml_dump(doc))
    return {"nodes": len(nodes), "merged": merged, "distinct": len(rows), "polluted": polluted}


# ── 운용사·수탁사·ETN 발행사 (국내ETF·해외ETF·펀드 통합) ─────────────────
_LEGAL_EN = re.compile(
    r"\b(co\.?,?\s*ltd\.?|company|corporation|corp\.?|incorporated|inc\.?|l\.?l\.?c\.?|l\.?p\.?|limited|ltd\.?|plc|ag|sa|nv|gmbh|holdings?|group)\b",
    re.I)
_LEGAL_KO = re.compile(r"\(주\)|주식회사|㈜|자산운용|투자운용|투자자문|투자신탁운용|증권")


def manager_key(name):
    """운용사 그룹 키 — 법인 접미·구두점·공백·대소문자 제거. 한글은 자산운용/증권 접미 제거."""
    s = norm(name).lower()
    s = re.sub(r"[.,&'\u2019\"()\[\]/-]", " ", s)
    s = _LEGAL_EN.sub(" ", s)
    s = _LEGAL_KO.sub("", s)
    return re.sub(r"\s+", "", s)


def read_csv(path):
    import csv
    with open(path, encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(l for l in f if not l.startswith("#"))]


def write_manager_en_codebook(rows):
    """asset_manager_en.csv — 국내 운용사 한↔영 대응표 (근거: domestic_etfs 동일 행 ref_fund_mgmt_co ↔ cu_fund_mgmt_co 공기 + asset_manager.csv 법인명)"""
    import csv
    path = os.path.join(CODEBOOKS, "asset_manager_en.csv")
    base = ["code", "name_ko", "name_en", "brand_ko", "node_id", "n_rows", "source", "as_of"]
    # 🔴 기존 파일은 사람 검수본(status·name_en_lipper·출처 URL 등 추가 컬럼)일 수 있다 — 덮어쓰지 않는다.
    #    기존 행·컬럼을 그대로 두고, DB 에서 새로 나타난 코드만 뒤에 추가한다 (2026-08-25 검수 A 손실 사고 후 보존 규칙).
    existing, fields = [], base
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f); existing = list(rd); fields = list(rd.fieldnames or base)
    have = {r["code"] for r in existing}
    fresh = [r for r in rows if r["code"] not in have]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(existing); w.writerows({**{k: "" for k in fields}, **r} for r in fresh)
    return path


def build_managers(con):
    manual = load_manual("organization.yaml")
    by_key, _ = manual_alias_index(manual)
    mnodes = manual.get("nodes") or {}
    brand2node = {}   # domestic_etfs.cu_fund_mgmt_co raw -> manual node
    code2node = {}    # public_funds code -> manual node
    for nid, node in mnodes.items():
        for al in node.get("aliases") or []:
            if al["table"] == "domestic_etfs":
                brand2node[norm(al["raw"])] = nid
            elif al["table"] == "public_funds" and al["column"] == "or_co_xtn_itt_cd":
                code2node[norm(al["raw"])] = nid
    am = {r["code"]: r for r in read_csv(os.path.join(CODEBOOKS, "asset_manager.csv"))}
    ext = collections.defaultdict(list)
    nodes, stats = {}, collections.Counter()
    used = set(by_key)   # (table, column, raw) 이미 수동에 있음 -> 재등록 금지

    def add_alias(nid, table, col, raw, evidence, into_ext):
        key = (table, col, norm(raw))
        if key in used:
            return False
        used.add(key)
        al = {"table": table, "column": col, "raw": norm(raw), "source": "rule", "evidence": evidence}
        (ext[nid] if into_ext else nodes[nid]["aliases"]).append(al)
        return True

    # 1) 국내ETF: ref_fund_mgmt_co(영문 정규) <-> cu_fund_mgmt_co(브랜드/오염) 공기 -> 수동 노드에 alias 확장
    co = con.execute("""select trim(ref_fund_mgmt_co), trim(cu_fund_mgmt_co), count(*) from domestic_etfs
                        where pd_grp_no='ETF' and cu_fund_mgmt_co is not null group by 1,2""").fetchall()
    en_rows, unmapped_cu = [], collections.Counter()
    ref2node = {}
    label2node = {norm(nd.get("label_ko", "")): nid for nid, nd in mnodes.items()}
    for ref, cu, n in co:
        node = brand2node.get(norm(cu))
        if node is None:   # 수동 노드에 ETF alias 가 없어도 라벨(브랜드)이 같으면 같은 운용사 (예: 현대·디에스·더제이·한국밸류10년투자)
            node = label2node.get(norm(cu)) or next((nid for lb, nid in label2node.items() if lb and lb.startswith(norm(cu)) and len(norm(cu)) >= 2), None)
        if node is None and ref:
            for r2, c2, _ in co:
                if r2 == ref and norm(c2) in brand2node:
                    node = brand2node[norm(c2)]; break
        if node is None and ref is None:
            node = {"ACE": brand2node.get("한국투자"), "TIGER": brand2node.get("미래에셋")}.get(norm(cu))
        if node is None:
            unmapped_cu[cu] += n; continue
        if ref:
            ref2node.setdefault(ref, node)
            add_alias(node, "domestic_etfs", "ref_fund_mgmt_co", ref, "국내ETF 동일 행 공기 ref<->cu · %d행" % n, True)
        add_alias(node, "domestic_etfs", "cu_fund_mgmt_co", cu, "브랜드/오염 표기 -> %s · %d행" % (mnodes[node].get('label_ko'), n), True)
    for ref, nid in ref2node.items():
        code = next((c for c, nd in code2node.items() if nd == nid), "")
        en_rows.append({"code": code, "name_ko": am.get(code, {}).get("name", mnodes[nid].get("label_ko")),
                        "name_en": ref, "brand_ko": mnodes[nid].get("label_ko"), "node_id": nid,
                        "n_rows": sum(n for r, _, n in co if r == ref),
                        "source": "domestic_etfs 동일 행 ref_fund_mgmt_co<->cu_fund_mgmt_co 공기(2차 DB) + asset_manager.csv 법인명",
                        "as_of": AS_OF})
    write_manager_en_codebook(sorted(en_rows, key=lambda r: -r["n_rows"]))
    stats["etf_ext"] = sum(len(v) for v in ext.values())

    # 2) 해외ETF 운용사 -> 그룹 키로 자동 노드 (국내 ref 와 키가 같으면 수동 노드에 확장)
    ref_key = {manager_key(r): nid for r, nid in ref2node.items()}
    ovs = con.execute("""select trim(cu_fund_mgmt_co), count(*), group_concat(distinct pd_us_cik) from overseas_etfs
                         where cu_fund_mgmt_co is not null and trim(cu_fund_mgmt_co)<>'' group by 1 order by 2 desc""").fetchall()
    groups = collections.defaultdict(list)
    for raw, n, ciks in ovs:
        groups[manager_key(raw)].append((norm(raw), n, ciks))
    merged_kr = []
    for key, vs in groups.items():
        vs.sort(key=lambda x: -x[1])
        if key in ref_key:
            nid = ref_key[key]; merged_kr.append((mnodes[nid].get("label_ko"), vs[0][0]))
            for raw, n, _ in vs:
                add_alias(nid, "overseas_etfs", "cu_fund_mgmt_co", raw, "국내 ref_fund_mgmt_co 와 그룹 키 일치 · %d행" % n, True)
            continue
        nid = hid("Org_mgr_", key)
        nodes[nid] = {"label_en": vs[0][0], "label_ko": vs[0][0], "role": "manager", "auto": True,
                      "note": "SEC CIK(pd_us_cik, 운용사 단위 아닐 수 있음): %s" % vs[0][2], "aliases": []}
        for raw, n, _ in vs:
            add_alias(nid, "overseas_etfs", "cu_fund_mgmt_co", raw, "해외 운용사 표기 정규화 · %d행" % n, False)
        stats["ovs_nodes"] += 1; stats["ovs_merged_variants"] += len(vs) - 1

    # 3) ETN 발행 증권사
    etn = con.execute("""select trim(cu_fund_mgmt_co), count(*) from domestic_etfs where pd_grp_no='ETN'
                         and cu_fund_mgmt_co is not null group by 1""").fetchall()
    issuers = {}
    lp = os.path.join(LOOKUPS, "etn_issuers.csv")
    if os.path.exists(lp):
        for r in read_csv(lp):
            issuers[manager_key(r["legal_name"])] = (r["legal_name"], r["issuer_name"])
    for raw, n in etn:
        k = manager_key(re.sub(r"글로벌.*\(ETN\)$", "", raw))
        legal, short = issuers.get(k, (raw, raw))
        nid = hid("Org_etn_", k)
        if nid not in nodes:
            nodes[nid] = {"label_ko": legal, "short_name": short, "role": "etn_issuer", "auto": True,
                          "note": "ETN 발행 증권사 — 자산운용사 노드(Org_000…)와 별개 법인. lookups/etn_issuers.csv", "aliases": []}
            stats["etn_nodes"] += 1
        add_alias(nid, "domestic_etfs", "cu_fund_mgmt_co", raw, "ETN 발행사 표기 · %d행" % n, False)

    # 4) 펀드 운용사 코드 — 수동 노드 없는 코드는 asset_manager.csv 로 노드 생성
    codes = con.execute("select or_co_xtn_itt_cd, count(*) from public_funds where or_co_xtn_itt_cd is not null group by 1").fetchall()
    for code, n in codes:
        code = norm(code)
        key = code.rjust(8, "0")            # code_width — 폭 손실 흡수 (수동 노드 대조도 8자리 기준으로)
        if code in code2node or key in code2node:
            continue
        # 🔴 2026-08-30 — 센티넬 코드는 운용사가 아니다. 노드를 만들지 않는다.
        #    '99999999' 27행: asset_manager.csv 가 '현대와이즈03사'(종목명 접두 최빈값·점유 15%)로 등재해
        #    실재하지 않는 운용사 노드 Org_fund_99999999 가 만들어지고 있었다 — 코드북 source 스스로 '법인명 아님' 이라 적어 둔 값이다.
        if code in ("99999999", "00000000"):
            stats["fund_sentinel_skipped"] += 1
            continue
        # 🔴 2026-08-30 code_width — 선행 0 유실로 7자리인 값이 있다(실측 '0040106' 2행 · DS증권 사모펀드).
        #    수탁사 경로(아래 5번)는 rjust(8,'0') 폴백이 이미 있는데 이 경로엔 없어 라벨이 코드 숫자로 남았다 — 비대칭을 맞춘다.
        r = am.get(code) or am.get(key) or {}
        st = r.get("status", "unknown")
        label = r.get("name") or r.get("short_name") or key
        nid = "Org_fund_" + key
        nodes[nid] = {"label_ko": label, "role": "manager", "auto": True,
                      "note": "asset_manager.csv status=" + st + ("" if r.get("name") else " — 법인명 미확정(브랜드/코드 라벨)"),
                      "aliases": []}
        add_alias(nid, "public_funds", "or_co_xtn_itt_cd", code, "asset_manager.csv %s · %d행" % (st, n), False)
        stats["fund_" + st] += 1

    # 5) 수탁사 코드 — trustee.csv 는 법인명, 나머지 코드 라벨
    tr = {norm(r["code"]): r for r in read_csv(os.path.join(CODEBOOKS, "trustee.csv"))}
    tcodes = con.execute("select trusc_xtn_itt_cd, count(*) from public_funds where trusc_xtn_itt_cd is not null group by 1").fetchall()
    for code, n in tcodes:
        key = norm(code)
        r = tr.get(key) or tr.get(key.rjust(8, "0"))
        nid = "Org_trustee_" + key
        sentinel = key in ("99999999", "00000000")
        # 🔴 2026-08-30 — 센티넬은 '수탁사 미지정' 이라는 결측이지 개체가 아니다. note 만 달고 노드를 만들던 것을 제외로 바꾼다.
        #    (실측 '99999999' 598행 · '00000000' 74행 — trustee.csv 미등재. 정상 코드는 '00020081' 같은 8자리 체계.
        #     기존 동작은 label_ko 에 코드 숫자를 그대로 단 Organization 노드 2개를 만들고 있었다.)
        #    판정은 public_funds.yaml columns.trusc_xtn_itt_cd.missing_semantics 에 있다.
        if sentinel:
            stats["trustee_sentinel_skipped"] += 1
            continue
        nodes[nid] = {"label_ko": (r["name"] if r else key), "role": "trustee", "auto": True,
                      "note": ("trustee.csv 관측 법인명" if r else "코드북 미확정 — 라벨=코드"),
                      "aliases": []}
        add_alias(nid, "public_funds", "trusc_xtn_itt_cd", code, "수탁사 코드 · %d행" % n, False)
        stats["trustee_named" if r else "trustee_code_only"] += 1

    header = (
        "# GENERATED — 편집 금지. 재생성: python scripts/gen_shared_auto.py\n"
        "# source=" + SOURCE + "\n# as_of=" + AS_OF + "\n"
        "# 운용사 통합: 국내ETF ref_fund_mgmt_co(영문 정규)<->cu_fund_mgmt_co(브랜드) 공기 -> 수동 organization.yaml 노드에 alias_extensions\n"
        "#   · 해외ETF cu_fund_mgmt_co -> 법인 접미 제거 그룹 키로 자동 노드(Org_mgr_) · ETN 발행 증권사(Org_etn_)\n"
        "#   · 펀드 운용사 코드(수동 노드 없는 것, Org_fund_<code>) · 수탁사 코드(Org_trustee_<code>)\n"
        "# 판단: Global X 는 미래에셋 계열이나 별개 법인 -> 병합 안 함. 국내<->해외 그룹 키 완전일치만 병합.\n"
    )
    doc = {"entity": "Organization", "description": "운용사·ETN발행사·수탁사 (자동 등록분)", "property": "hasManager",
           "generated": True, "source": SOURCE, "as_of": AS_OF, "nodes": nodes, "alias_extensions": dict(ext)}
    with open(OUT_MGR, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + yaml_dump(doc))
    stats["unmapped_cu"] = dict(unmapped_cu); stats["merged_kr"] = merged_kr; stats["en_rows"] = len(en_rows)
    stats["nodes"] = len(nodes)
    return stats


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
    print(f"organization_issuer_auto.yaml: 노드 {iss['nodes']} · 표기 변형 병합 {iss['merged']} · 원 distinct {iss['distinct']}"
          + (f" · 종류 어휘 겹침 제외 {len(iss['polluted'])}({', '.join(r for r, _ in iss['polluted'])})" if iss['polluted'] else ""))
    mg = build_managers(con)
    print("organization_manager_auto.yaml: 노드 %d · 국내ETF 확장 alias %d · 한영표 %d · 해외 노드 %d(변형 병합 %d) · ETN %d · 펀드코드 노드 %d · 수탁사 %d+%d" % (
        mg['nodes'], mg['etf_ext'], mg['en_rows'], mg['ovs_nodes'], mg['ovs_merged_variants'], mg['etn_nodes'],
        sum(v for k, v in mg.items() if str(k).startswith('fund_')), mg['trustee_named'], mg['trustee_code_only']))
    print("국내<->해외 병합:", mg["merged_kr"], "| 국내ETF 미매핑 cu:", mg["unmapped_cu"])


if __name__ == "__main__":
    main()
