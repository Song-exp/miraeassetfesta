# -*- coding: utf-8 -*-
"""Security(종목) 개체 자동 생성 — ontology/shared/security_auto.yaml

왜: 교차질의("삼성전자를 보유한 국내/해외ETF·펀드", "캠브리콘 편입 ETF")는 전부 종목→상품 방향인데
    종목이 세 외부 테이블(ext_etf_holdings·ext_ovs_etf_holdings·ext_fund_holdings)의 문자열로만 존재한다.
    해외는 이름 LIKE 로 잡으면 'SAMSUNG ELECTRONICS' 와 'SAMSUNG ELECTRO-MECHANICS'(삼성전기)가 같이 걸린다.

원천·키 (2026-08-25 실측):
  ext_etf_holdings.ticker      6자리 KRX 티커('005930') — 국내 종목 키. 6자리가 아닌 값('000001 C2' = 중국 A주 등)은 별도 키
  ext_fund_holdings.isin       🔴 컬럼명은 isin 이지만 국내 주식은 6자리 티커('005930') — 국내 ETF 티커와 그대로 조인.
                               해외 종목은 진짜 ISIN(CNE1000041R8·US4…). 파생/ETF(asset_type) 는 종목 alias 에서 제외
  ext_ovs_etf_holdings.cusip   9자리. 결측 18%·'000000000' 플레이스홀더 多 / lei: 법인 식별자 (삼성전자 LEI 1개 ← cusip 7종·표기 8종)
  → 노드 키 우선순위: 국내 6자리 티커 > 유효 cusip(US ISIN 변환 가능) > LEI(법인 상위 노드) > 정규화 이름(폴백, status: name_fallback)

병합 규칙:
  · 자동 병합은 **동일 키(티커/cusip/LEI)** 일 때만. 이름만 같은 경우 병합 금지 (삼성전자↔삼성전기 회귀 테스트).
  · 한글↔영문 교차(삼성전자 ↔ Samsung Electronics) 는 codebooks/security_alias_manual.csv 의 수동 근거로만:
    CSV 한 행 = 정본 노드(Sec_m_<slug>), 같은 행의 kr_ticker/isin/cusip/lei 에 해당하는 자동 노드는 parent 로 매달린다.
  · 자회사 관계(에코프로 등)는 CSV parent_slug → edge Security —subsidiaryOf→ Security (근거 URL 기입).

상품→종목 관계(holds)는 행 수 100만 규모라 kg_edge 에 넣지 않는다 — ext_* 테이블 자체를 edge 테이블로 간주
(플래너는 kg_alias 로 종목 키를 얻은 뒤 ext_* 를 조인한다).

규모 제한: 어느 상품에서든 편입 비중 상위 TOP_RANK(50) 안에 한 번이라도 든 종목 + 수동 코드북 종목만 노드화.
           나머지는 노드 없이도 ext_* 조인으로 조회 가능.

사용: python scripts/gen_security_auto.py
"""
import csv, hashlib, os, re, sqlite3, sys, unicodedata, collections
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "financial_products.db")
OUT = os.path.join(ROOT, "ontology", "shared", "security_auto.yaml")
MANUAL = os.path.join(ROOT, "ontology", "codebooks", "security_alias_manual.csv")
AS_OF = "2026-08-22"
TOP_RANK = 50
SUFFIX = re.compile(r"\b(CO|COMPANY|LTD|LIMITED|INC|INCORPORATED|CORP|CORPORATION|PLC|SA|AG|NV|SE|SPA|AB|ASA|OYJ|KK|BHD|TBK|HOLDINGS?|GROUP|CLASS [A-C]|CL [A-C]|ORD|SHS|NPV|ADR|GDR|REGS|REG S|COMMON STOCK|COMMON)\b\.?", re.I)
PLACEHOLDER_CUSIP = {"000000000", "", None}


def norm_name(s):
    s = unicodedata.normalize("NFKC", str(s or "")).upper()
    s = re.sub(r"[.,'’`\"()\[\]/&+]", " ", s)
    s = SUFFIX.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def sha(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def cusip_to_isin(cusip):
    """US ISIN = 'US' + cusip + 체크디지트 (Luhn 변형). 문자 → 숫자(A=10…) 전개 후 Luhn."""
    if not cusip or len(cusip) != 9 or cusip in PLACEHOLDER_CUSIP:
        return None
    if not cusip[0].isdigit():      # CINS(첫 글자 알파벳) 은 미국 외 발행 — US ISIN 아님
        return None
    if not cusip.isalnum():         # '*'·'@'·'#' 는 사모 발행 PPN 표기 — ISIN 변환 대상 아님
        return None
    body = "US" + cusip
    digits = "".join(str(int(ch, 36)) for ch in body)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return body + str((10 - total % 10) % 10)


def yq(s):
    """yaml 큰따옴표 문자열"""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    assert cusip_to_isin("67066G104") == "US67066G1040", "ISIN 변환 자체검증 실패(NVIDIA)"
    assert cusip_to_isin("037833100") == "US0378331005", "ISIN 변환 자체검증 실패(Apple)"
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = lambda s, *a: con.execute(s, a).fetchall()

    nodes = {}      # node_id -> dict(label_ko, label_en, aliases[list of (table,col,raw)], parent, status, note)
    def node(nid, **kw):
        n = nodes.setdefault(nid, {"aliases": [], "alias_set": set()})
        for k, v in kw.items():
            if v is not None and (k not in n or not n[k]):
                n[k] = v
        return n
    def alias(n, t, c, raw):
        key = (t, c, raw)
        if raw is None or str(raw).strip() == "" or key in n["alias_set"]:
            return
        n["alias_set"].add(key); n["aliases"].append(key)

    # ── 1. 국내 ETF 구성종목 (TOP_RANK 내) ──
    dom = q("select ticker, constituent, count(*) n from ext_etf_holdings where rank<=? and ticker is not null and ticker<>'' group by 1,2", TOP_RANK)
    kr_ids = {}
    for tk, nm, n in dom:
        tk = tk.strip()
        if re.fullmatch(r"\d{6}", tk):
            nid = f"Sec_kr_{tk}"; node(nid, label_ko=nm.strip(), status="kr_ticker")
        else:
            nid = f"Sec_d_{sha(tk)}"; node(nid, label_en=nm.strip(), status="dom_foreign_ticker", note=f"ticker={tk}")
        nn = nodes[nid]; alias(nn, "ext_etf_holdings", "ticker", tk); alias(nn, "ext_etf_holdings", "constituent", nm)
        kr_ids[tk] = nid
    n_dom = len(nodes)

    # ── 2. 펀드 구성종목 (주식·채권만, 그룹 내 비중 상위 TOP_RANK) ──
    fund = q("""select isin, holding_nm, asset_type from (
                 select isin, holding_nm, asset_type,
                        row_number() over (partition by grp, bas_dt order by weight_pct desc) rk
                 from ext_fund_holdings where isin is not null and isin<>'' and asset_type in ('주식','채권'))
               where rk<=? group by 1,2,3""", TOP_RANK)
    n_fund_new = 0
    n_kr7 = 0
    for isin, nm, at in fund:
        isin = isin.strip()
        m_kr7 = re.fullmatch(r"KR7(\d{6})\d{3}", isin)   # 진짜 KR ISIN 표기 → 6자리 티커 노드에 병합 (같은 종목이 두 표기로 옴: KR7285130001 / 285130)
        if m_kr7:
            n_kr7 += 1
        if re.fullmatch(r"\d{6}", isin) or m_kr7:
            nid = f"Sec_kr_{m_kr7.group(1) if m_kr7 else isin}"
            if nid not in nodes: n_fund_new += 1
            node(nid, label_ko=nm.strip(), status="kr_ticker")
        else:
            nid = f"Sec_f_{re.sub(r'[^A-Za-z0-9]', '', isin)}"
            if nid not in nodes: n_fund_new += 1
            node(nid, label_en=nm.strip() if not re.search(r"[가-힣]", nm) else None,
                 label_ko=nm.strip() if re.search(r"[가-힣]", nm) else None, status="fund_isin", note=f"asset_type={at}")
        nn = nodes[nid]; alias(nn, "ext_fund_holdings", "isin", isin); alias(nn, "ext_fund_holdings", "holding_nm", nm)

    # ── 3. 해외 ETF 구성종목 (TOP_RANK 내): cusip → 노드, LEI → 상위(발행 법인) 노드 ──
    ovs = q("select cusip, lei, holding_name, count(*) n from ext_ovs_etf_holdings where rank<=? group by 1,2,3", TOP_RANK)
    lei_names = collections.defaultdict(collections.Counter)
    n_name_fb = 0
    for cusip, lei, nm, n in ovs:
        cusip = (cusip or "").strip(); lei = (lei or "").strip(); nm = (nm or "").strip()
        if not nm: continue
        if cusip not in PLACEHOLDER_CUSIP:
            nid = f"Sec_o_{cusip}"; st = "cusip"
            isin = cusip_to_isin(cusip)
            node(nid, label_en=nm, status=st, note=(f"isin={isin}" if isin else "CINS(미국 외) — US ISIN 변환 불가"))
        elif lei:
            nid = f"Sec_lei_{lei}"; node(nid, label_en=nm, status="lei_only")
        else:
            nid = f"Sec_on_{sha(norm_name(nm))}"; node(nid, label_en=nm, status="name_fallback"); n_name_fb += 1
        nn = nodes[nid]
        if cusip not in PLACEHOLDER_CUSIP: alias(nn, "ext_ovs_etf_holdings", "cusip", cusip)
        alias(nn, "ext_ovs_etf_holdings", "holding_name", nm)
        if lei:
            lei_names[lei][nm] += n
            if nid != f"Sec_lei_{lei}":
                nn.setdefault("parent", f"Sec_lei_{lei}")
    for lei, cnt in lei_names.items():
        pn = node(f"Sec_lei_{lei}", label_en=cnt.most_common(1)[0][0], status="lei_issuer", note=f"LEI={lei} (발행 법인 — 하위 노드는 증권 단위)")
        alias(pn, "ext_ovs_etf_holdings", "lei", lei)

    # ── 4. 수동 코드북 — 한글↔영문 교차·자회사 ──
    edges = []
    manual = list(csv.DictReader(open(MANUAL, encoding="utf-8-sig"))) if os.path.exists(MANUAL) else []
    slug_id = {}
    for r in manual:
        mid = f"Sec_m_{r['slug']}"; slug_id[r["slug"]] = mid
        m = node(mid, label_ko=r.get("name_ko") or None, label_en=r.get("name_en") or None, status="manual",
                 note=f"수동 정본 — {r.get('source','')}")
        targets = []
        if r.get("kr_ticker"): targets.append(f"Sec_kr_{r['kr_ticker'].strip()}")
        if r.get("isin"): targets.append(f"Sec_f_{re.sub(r'[^A-Za-z0-9]', '', r['isin'])}")
        for cu in (r.get("cusip") or "").split("|"):
            if cu.strip(): targets.append(f"Sec_o_{cu.strip()}")
        if r.get("lei"): targets.append(f"Sec_lei_{r['lei'].strip()}")
        for t in targets:
            if t in nodes and t != mid:
                nodes[t]["parent"] = mid
                # 하위 증권 노드들이 LEI 노드에 매달려 있으면 LEI 노드만 옮긴다 (2단 계층 유지)
        # 자동 노드가 없어도 정본에 검색 alias 가 있어야 하므로 raw 존재 여부는 build_ontology V1 이 검증
        for t in targets:
            if t not in nodes and t.startswith("Sec_kr_"):
                tk = t[7:]
                if q("select 1 from ext_etf_holdings where ticker=? limit 1", tk) or q("select 1 from ext_fund_holdings where isin=? limit 1", tk):
                    node(t, label_ko=r.get("name_ko"), status="kr_ticker", parent=mid)
                    nn = nodes[t]
                    if q("select 1 from ext_etf_holdings where ticker=? limit 1", tk): alias(nn, "ext_etf_holdings", "ticker", tk)
                    if q("select 1 from ext_fund_holdings where isin=? limit 1", tk): alias(nn, "ext_fund_holdings", "isin", tk)
    for r in manual:
        if r.get("parent_slug") and r["parent_slug"] in slug_id:
            edges.append((slug_id[r["slug"]], "subsidiaryOf", slug_id[r["parent_slug"]], r.get("source", "manual")))

    # ── 4b. 이름 alias 유일성 — 같은 (table,column) 의 raw 가 두 노드 이상에 붙으면 이름 alias 는 전부 제거 ──
    #        (예: '오리온' = 001800·271560, 'Midea Group' = A주·H주). 키(ticker/cusip/lei/isin) alias 는 유지.
    #        build_ontology V2(raw 충돌) 를 통과시키기 위한 규칙 — 모호한 이름은 노드가 아니라 ext_* LIKE 조회로 남긴다.
    NAME_COLS = {"constituent", "holding_nm", "holding_name"}
    owner = collections.defaultdict(set)
    for nid, n in nodes.items():
        for t, c, raw in n["aliases"]:
            owner[(t, c, raw)].add(nid)
    n_amb = n_lift = 0
    lift_target = {}   # (t,c,raw) → 이름 alias 를 대신 보유할 상위 노드 (모든 소유 노드가 같은 parent 일 때)
    for key, owners in owner.items():
        if key[1] in NAME_COLS and len(owners) > 1:
            parents = {nodes[o].get("parent") for o in owners}
            if len(parents) == 1 and None not in parents:
                lift_target[key] = next(iter(parents))
    for key, par_id in lift_target.items():
        par = nodes[par_id]
        if key not in par["alias_set"]:
            par["alias_set"].add(key); par["aliases"].append(key)
        n_lift += 1
    for nid, n in nodes.items():
        keep = []
        for key in n["aliases"]:
            t, c, raw = key
            if c in NAME_COLS and len(owner[key]) > 1 and lift_target.get(key) != nid:
                n_amb += 1; n.setdefault("ambiguous_names", []).append(raw)
                continue
            keep.append(key)
        n["aliases"] = keep
    # 키 alias 도 충돌하면(같은 cusip 이 두 노드 = 불가능하나 방어) 첫 노드만
    # ── 5. 라벨 보정: label 없는 노드는 alias 이름으로 ──
    for nid, n in nodes.items():
        if not n.get("label_ko") and not n.get("label_en"):
            names = [raw for t, c, raw in n["aliases"] if c in ("constituent", "holding_nm", "holding_name")]
            if names: n["label_en" if not re.search(r"[가-힣]", names[0]) else "label_ko"] = names[0]

    # ── 6. 출력 ──
    L = []
    L.append("# GENERATED by scripts/gen_security_auto.py — 편집 금지. 재생성: python scripts/gen_security_auto.py")
    L.append(f"# source: ext_etf_holdings·ext_fund_holdings·ext_ovs_etf_holdings (편입 비중 TOP {TOP_RANK}) + codebooks/security_alias_manual.csv · as_of={AS_OF}")
    L.append("# 상품→종목(holds) 관계는 kg_edge 에 없다 — ext_* 테이블이 edge 테이블 (행 100만). 플래너는 kg_alias 키로 ext_* 를 조인한다.")
    L.append("# 병합: 동일 키(티커/cusip/LEI)만 자동. 이름 동일은 병합하지 않는다 (삼성전자 ≠ 삼성전기). 한↔영 교차는 수동 코드북 parent 로만.")
    L.append("entity: Security")
    L.append("description: 종목(주식·채권 등 편입 증권). 키 = 국내 6자리 티커 / 해외 cusip(US ISIN 변환) / LEI(발행 법인, 상위) / 수동 정본")
    L.append("property: holds")
    L.append("absent_in: {}")
    L.append("nodes:")
    for nid, n in nodes.items():
        L.append(f"  {nid}:")
        if n.get("label_ko"): L.append(f"    label_ko: {yq(n['label_ko'])}")
        if n.get("label_en"): L.append(f"    label_en: {yq(n['label_en'])}")
        if n.get("parent"): L.append(f"    parent: {n['parent']}")
        L.append(f"    status: {n.get('status','auto')}")
        if n.get("note"): L.append(f"    note: {yq(n['note'])}")
        if n.get("ambiguous_names"): L.append(f"    ambiguous_names: {yq('; '.join(dict.fromkeys(n['ambiguous_names'])))}   # 이름이 다른 종목과 겹쳐 alias 제외 — 키(ticker/cusip)로만 매칭")
        if n["aliases"]:
            L.append("    aliases:")
            for t, c, raw in n["aliases"]:
                L.append(f"      - {{table: {t}, column: {c}, raw: {yq(raw)}, source: rule}}")
    if edges:
        L.append("edges:")
        for s, p, d, src in edges:
            L.append(f"  - {{src: {s}, predicate: {p}, dst: {d}, source: {yq(src)}, as_of: {yq(AS_OF)}}}")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")

    st = collections.Counter(n.get("status") for n in nodes.values())
    n_parent = sum(1 for n in nodes.values() if n.get("parent"))
    isin_ok = sum(1 for n in nodes.values() if n.get("note", "").startswith("isin="))
    print(f"Security 노드 {len(nodes):,} → {dict(st)}")
    print(f"  국내 티커 노드 {n_dom:,} (펀드에서 추가 {n_fund_new:,}) · LEI 상위 노드 {len(lei_names):,} · parent 연결 {n_parent:,} · US ISIN 변환 {isin_ok:,} · 이름 폴백 {n_name_fb:,}")
    print(f"  이름 alias 모호로 제외 {n_amb:,} (그중 LEI 법인 노드로 승격 {n_lift:,}) · 펀드 KR7 ISIN→티커 병합 {n_kr7:,}")
    print(f"  수동 코드북 {len(manual)}종 · subsidiaryOf edge {len(edges)} · alias {sum(len(n['aliases']) for n in nodes.values()):,} → {OUT}")


if __name__ == "__main__":
    main()
