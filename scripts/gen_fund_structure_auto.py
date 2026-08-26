# -*- coding: utf-8 -*-
"""공모펀드 상품 간 관계 → KG (Fund 노드 + feedsInto edge) 자동 생성

생성물: ontology/shared/fund_structure_auto.yaml  (GENERATED — 편집 금지)
원천:   public_funds (마스터) + ext_fund_page.mother_fund_names_raw (설명서 텍스트)
사용:   python scripts/gen_fund_structure_auto.py

키 구조 실측 (2026-08-25, 2차 DB 23,676행) — 어떤 컬럼이 "펀드 묶음"인가
  · rptt_ksd_itm_no (대표펀드 KSD 코드, 6,886종 · NULL 116) = KSD 운용사 5자리 + 운용사 종목번호 7자리.
    같은 값끼리 묶었을 때 종목명 공통접두 비율 중앙값 0.96 (≥2 클래스 2,531묶음, 불일치 <0.5 는 147 — 사모·구형 묶음)
    → 🔴 **Fund 노드 키 = rptt_ksd_itm_no**.
  · mtco_itm_no (14,060) 는 운용사 내부 종목번호라 **운용사 간 충돌** (공통접두 <0.5 가 616묶음) — 단독 키 부적합.
    (or_co_xtn_itt_cd, mtco_itm_no) 복합키(14,659)도 rptt 보다 응집이 낮다.
  · 대표펀드(rptt) 자체가 마스터 행(ksd_itm_no)인 경우 0.1% — 대표 클래스는 사실상 마스터 밖(운용펀드).
    → representedBy edge 는 만들 수 없고, rptt 가 곧 노드 키로 그 역할을 흡수한다.
  · std_itm_no: 묶음당 1종 11,366 / 2종+ 1,635 — 클래스 하위 식별자, 노드 키 아님.
  · M111(종류형 클래스펀드) 10,510행 = 3,954 묶음, 그중 1,659 묶음이 클래스 ≥2 — 클래스 → 묶음(classOf) 은
    마스터 컬럼(rptt_ksd_itm_no) 이 이미 담고 있어 edge 로 만들지 않는다.
  · 모펀드: ext_fund_page.mother_fund_names_raw 4,185행(전부 마스터 조인) 에서 '모투자신탁/모투자회사' 명 추출.
    마스터 itm_nm 과 정규화 완전일치는 3건뿐 → 모펀드는 마스터 밖 개체(MotherFund_*) 로 생성하고 feedsInto 로 잇는다.
  · M112 FoFs 2,052행: 편입 대상 펀드 식별 불가(텍스트 없음) → 노드 속성 structure=FoFs 만.
"""
import csv, hashlib, os, re, sqlite3, sys, collections
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "financial_products.db")
OUT = os.path.join(ROOT, "ontology", "shared", "fund_structure_auto.yaml")
AS_OF = "2026-08-22"
SRC = "scripts/gen_fund_structure_auto.py — public_funds.rptt_ksd_itm_no 묶음 + ext_fund_page 모펀드 텍스트 (2026-08-25)"

# 클래스 접미 제거 규칙 — 실측 상위 접미: A · C · C-Pe · C-e · C-P · C1 · A-e · C2 · Ce · C3 · Ae · e · C-P2 · C-I · C-F · C-E · A) ·
#   1종/2종 · 종류A · 종류C · A클래스 · C클래스 · C-P2e(퇴직연금) · Class Af · ClassC-Pe …
_SUFFIX = re.compile(
    r"""(\s*(종류|Class|클래스)\s*)?          # 접두어
        [ACDEFIPSWKB]\s?(-?\s?[A-Za-z0-9]{1,4})?  # 클래스 문자 + 세부 (C-P2e, Af, A1 …)
        (\s*\(퇴직연금\)|\s*\(개인연금\)|\s*클래스|\s*형)?\s*[\)\]]?\s*$""", re.X)
_SUFFIX2 = re.compile(r"\s*\d종\s*$|\s*[-_]?e\s*$|\s*\(?(Class|종류형|종류|클래스)\s*[A-Za-z0-9\-]*\)?\s*$")


def strip_class(name: str) -> str:
    s = name.strip()
    # 괄호로 닫힌 유형 표기 뒤의 클래스 접미만 제거: '...(주식)C3' → '...(주식)', '...[채권]종류CF' → '...[채권]'
    m = re.search(r"[\)\]]", s[::-1])
    if m:
        cut = len(s) - m.start()          # 마지막 ')' 또는 ']' 다음 위치
        tail = s[cut:]
        if tail and (_SUFFIX.fullmatch(tail) or _SUFFIX2.fullmatch(tail)):
            return s[:cut].strip()
    # 괄호가 없으면 명백한 접미만 (' A', ' C-e', ' 종류A', 'ClassC' …)
    m2 = re.search(r"\s*(종류형|종류|Class|클래스)\s*[A-Za-z0-9\-]{0,6}$", s) or re.search(r"\s+[ACDEFIPSW](-?[A-Za-z0-9]{0,4})?(클래스)?$", s)
    if m2 and len(s) - m2.start() <= 12:
        return s[:m2.start()].strip()
    return s


def common_label(names):
    names = [n for n in names if n]
    if len(names) == 1:
        return strip_class(names[0])
    pre = os.path.commonprefix(names).rstrip(" -_(")
    if pre.count("(") > pre.count(")"):      # 접두가 괄호 중간에서 잘린 경우 '(' 앞까지
        pre = pre[:pre.rfind("(")].rstrip()
    if pre.count("[") > pre.count("]"):
        pre = pre[:pre.rfind("[")].rstrip()
    if len(pre) >= 6:
        return strip_class(pre) or pre
    return strip_class(collections.Counter(names).most_common(1)[0][0])


def sid(prefix, key):
    return f"{prefix}{hashlib.sha1(key.encode('utf-8')).hexdigest()[:10]}"


def norm_name(s):
    return re.sub(r"[\s\(\)\[\]\-_·,./]", "", str(s))


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    p = pd.read_sql("select itm_no, rptt_ksd_itm_no rp, itm_nm, sale_yn, prvo_pbff_desc, prfd_attr_cds, or_co_xtn_itt_cd oc from public_funds", con)
    e = pd.read_sql("select itm_no, mother_fund_names_raw m from ext_fund_page where mother_fund_names_raw is not null and mother_fund_names_raw <> ''", con)
    p = p[p.rp.notna() & (p.rp.str.strip() != "")]
    # 🔴 위장결측 대표코드: 'KR0000000000'(5,308행) · '000000000000'(1,645행) — 대표펀드 정보 없음(사모·구형 다수).
    #    묶음이 아니므로 노드를 만들지 않는다 (만들면 운용사 69곳 5,308 클래스가 한 노드에 묶임).
    sentinel = p.rp.str.fullmatch(r"(KR)?0+")
    excluded = int(sentinel.sum())
    p = p[~sentinel]
    groups = p.groupby("rp")

    nodes, edges = {}, []
    stat = collections.Counter()
    stat["excluded_sentinel_rows"] = excluded
    fund_id = {}
    for rp, g in groups:
        nid = sid("Fund_", rp)
        fund_id[rp] = nid
        label = common_label(g.itm_nm.tolist())
        selling = int((g.sale_yn == "판매중").sum())
        attrs = " ".join(g.prfd_attr_cds.dropna().astype(str))
        node = {
            "label_ko": label,
            "auto": True,
            "n_classes": int(len(g)),
            "n_selling": selling,
            "offer_type": "공모" if (g.prvo_pbff_desc == "공모").any() else "사모",
            "aliases": [{"table": "public_funds", "column": "rptt_ksd_itm_no", "raw": rp,
                         "source": "rule", "evidence": f"대표펀드 KSD 코드 · 클래스 {len(g)}"}],
        }
        if selling == 0:
            node["all_closed"] = True; stat["all_closed"] += 1
        if "M112" in attrs:
            node["structure"] = "FoFs"; stat["fofs"] += 1
        if "M109" in attrs:
            node["structure"] = (node.get("structure", "") + "|자펀드").strip("|"); stat["child"] += 1
        if "M111" in attrs and len(g) >= 2:
            node["multi_class"] = True; stat["multi_class"] += 1
        nodes[nid] = node
        stat["fund"] += 1

    # 모펀드 — 설명서 텍스트에서 추출
    itm2rp = dict(zip(p.itm_no, p.rp))
    master_norm = {norm_name(n): rp for n, rp in zip(p.itm_nm, p.rp)}
    mother_nodes, seen_pairs = {}, set()
    cand_total = matched_master = 0
    for itm, raw in zip(e.itm_no, e.m):
        rp = itm2rp.get(itm)
        if not rp:
            continue
        for tok in str(raw).split(";"):
            t = tok.strip()
            if not (6 <= len(t) <= 60) or ("모투자" not in t) or t.startswith("각모") or "이투자신탁" in t or "대부분" in t:
                continue
            cand_total += 1
            key = norm_name(t)
            if key in master_norm:              # 마스터 안에 있는 모펀드 (드묾)
                matched_master += 1
                dst = fund_id[master_norm[key]]
            else:
                dst = sid("MotherFund_", key)
                if dst not in mother_nodes:
                    mother_nodes[dst] = {"label_ko": t, "auto": True, "role": "mother",
                                         "note": "마스터 밖 — 간이투자설명서 텍스트(ext_fund_page.mother_fund_names_raw)에서 추출"}
            pair = (fund_id[rp], dst)
            if pair in seen_pairs or pair[0] == pair[1]:
                continue
            seen_pairs.add(pair)
            edges.append({"src": pair[0], "predicate": "feedsInto", "dst": dst, "source": "rule", "as_of": AS_OF})
    nodes.update(mother_nodes)

    # yaml 직렬화 (yaml.dump 는 느리고 큰 파일에 부적합 — 수동 기록, 값은 따옴표로 안전화)
    def q(v):
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
    L = [
        "# GENERATED — 편집 금지. 재생성: python scripts/gen_fund_structure_auto.py",
        f"# source={SRC}", f"# as_of={AS_OF}",
        "# 키 구조 실측·설계 근거는 생성 스크립트 상단 docstring 참조.",
        f"# Fund 노드 {stat['fund']} (rptt_ksd_itm_no 단위 · all_closed {stat['all_closed']} · 복수클래스 {stat['multi_class']} · FoFs {stat['fofs']} · 자펀드 {stat['child']})",
        f"# 제외: rptt 위장결측('KR0000000000'·'000000000000') {excluded}행 — 대표펀드 정보 없음, 노드 없음 (클래스 단독 조회는 마스터로)",
        f"# MotherFund 노드 {len(mother_nodes)} · feedsInto edge {len(edges)} (모펀드 후보 {cand_total} · 마스터 내 매칭 {matched_master})",
        "# classOf(클래스→묶음) 는 edge 로 만들지 않는다 — public_funds.rptt_ksd_itm_no 컬럼이 그 관계 자체.",
        "# representedBy 는 만들 수 없다 — 대표 클래스가 마스터 행인 경우 0.1%. rptt 가 노드 키로 그 역할을 흡수.",
        "entity: Fund",
        "description: 공모펀드 묶음(대표펀드 KSD 코드 단위) 및 모펀드 — 클래스 행(itm_no)은 rptt_ksd_itm_no 로 이 노드에 매달린다",
        "property: belongsToFund",
        "generated: true",
        f"source: {q(SRC)}", f"as_of: '{AS_OF}'",
        "nodes:",
    ]
    for nid, n in nodes.items():
        L.append(f"  {nid}:")
        L.append(f"    label_ko: {q(n['label_ko'])}")
        for k in ("auto", "n_classes", "n_selling", "offer_type", "all_closed", "structure", "multi_class", "role"):
            if k in n:
                v = n[k]
                L.append(f"    {k}: {str(v).lower() if isinstance(v, bool) else (v if isinstance(v, int) else q(v))}")
        if "note" in n:
            L.append(f"    note: {q(n['note'])}")
        if n.get("aliases"):
            L.append("    aliases:")
            for a in n["aliases"]:
                L.append(f"    - {{table: {a['table']}, column: {a['column']}, raw: {q(a['raw'])}, source: {a['source']}, evidence: {q(a['evidence'])}}}")
    L.append("edges:")
    for ed in edges:
        L.append(f"- {{src: {ed['src']}, predicate: {ed['predicate']}, dst: {ed['dst']}, source: rule, as_of: '{AS_OF}'}}")
    L.append("absent_in: {}")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print(f"Fund 노드 {stat['fund']} (all_closed {stat['all_closed']} · multi_class {stat['multi_class']} · FoFs {stat['fofs']} · 자펀드 {stat['child']}) · 위장결측 제외 {excluded}행")
    print(f"MotherFund 노드 {len(mother_nodes)} · feedsInto {len(edges)} · 모펀드 후보 {cand_total} · 마스터 내 매칭 {matched_master}")
    # 라벨 품질 표본
    sample = [(n["label_ko"], n["n_classes"]) for n in list(nodes.values()) if n.get("n_classes", 0) >= 4][:8]
    print("라벨 표본(클래스≥4):", sample)
    print("→", OUT)


if __name__ == "__main__":
    main()
