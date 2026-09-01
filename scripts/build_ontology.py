# -*- coding: utf-8 -*-
"""
온톨로지·KG 생성 파이프라인 — yaml(진실의 원천) → .ttl + kg_* 테이블

  ontology/enums/*.yaml  ┐
  ontology/shared/*.yaml ├──▶  이 스크립트  ──┬──▶ ontology/{common,bond_kr,etf_kr,etf_gl,fund_pub}.ttl (제출물 5분할, 생성물)
  ontology/codebooks/*.csv ┘                  └──▶ data/…db  kg_* 4테이블  (런타임 조회용)

설계 근거: docs/ONTOLOGY_BUILD_PLAN.md §2.5·§4 — ".ttl 과 KG 는 손으로 쓰지 않습니다"

동작 4단계:
  [1 Load]     enums/shared yaml + codebooks 파싱
  [2 Validate] 죽은 alias·raw값 충돌·깨진 포인터·codebook 규정 검사 — 실패 시 산출물 생성 안 함
  [3 Emit]     kg_node/kg_alias/kg_edge/kg_closure 전체 재생성(멱등) + ttl 5분할(규격 p.9)
  [4 Report]   축별 미매핑 distinct 리포트 → 다음 EDA 우선순위

사용:
  python scripts/build_ontology.py           # 전체 (검증 → 생성 → 리포트)
  python scripts/build_ontology.py --check   # 검증 + 리포트만 (산출물 안 만듦)
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
import unicodedata

import yaml

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENUMS_DIR = os.path.join(PROJECT_ROOT, "ontology", "enums")
SHARED_DIR = os.path.join(PROJECT_ROOT, "ontology", "shared")
CODEBOOKS_DIR = os.path.join(PROJECT_ROOT, "ontology", "codebooks")
# 제출 규격 (참여자공유용 과제설명 p.9 — "필수 도메인별 Ontology.ttl 제출 기준"):
#   ontology/common.ttl + bond_kr.ttl + etf_kr.ttl + etf_gl.ttl + fund_pub.ttl 5분할,
#   네임스페이스 fp: <http://mafest.ai/product#> (원문 제시 그대로 — 임의 변경 금지).
#   단일 ontology.ttl 은 요건 미충족 (PROJECT.md §5 CAUTION).
TTL_DIR = os.path.join(PROJECT_ROOT, "ontology")
TTL_FILES = {                       # 파일 key → (파일명, 담당 테이블 or None=공통)
    "common":   ("common.ttl", None),
    "bond_kr":  ("bond_kr.ttl", "domestic_bonds"),
    "etf_kr":   ("etf_kr.ttl", "domestic_etfs"),
    "etf_gl":   ("etf_gl.ttl", "overseas_etfs"),
    "fund_pub": ("fund_pub.ttl", "public_funds"),
}
TABLE_TTL = {t: k for k, (_, t) in TTL_FILES.items() if t}   # 테이블 → 파일 key
DB_PATH = os.path.join(PROJECT_ROOT, "data", "financial_products.db")
REPORT_PATH = os.path.join(PROJECT_ROOT, "data", "kg_coverage_report.md")

DATA_CUTOFF = "2026-08-24"  # 대회 규정(8/24 공지) — 이후 발행 외부 데이터 반입 금지

# 테이블 ↔ 온톨로지 클래스 (masters 4종 고정)
TABLE_CLASS = {
    "domestic_bonds": "DomesticBond",
    "domestic_etfs": "DomesticETF",
    "overseas_etfs": "OverseasETF",
    "public_funds": "PublicFund",
}
# 외부 수집 보조 테이블 — Security(종목) alias 의 원천. 마스터가 아니므로 상품 클래스가 아닌 보조 클래스로 ttl 에 표기.
# (상품→종목 관계 자체는 행 수 100만 규모라 kg_edge 가 아니라 이 테이블을 edge 테이블로 간주한다 — security_auto.yaml 주석)
EXT_CLASS = {
    "ext_etf_holdings": "ExternalHoldings",
    "ext_ovs_etf_holdings": "ExternalHoldings",
    "ext_fund_holdings": "ExternalHoldings",
    "ext_fund_page": "ExternalFundPage",
}
ALIAS_TABLE_CLASS = {**TABLE_CLASS, **EXT_CLASS}


def norm(v):
    """비교용 정규화 — trim + NFC (자소분리·공백 차이로 인한 죽은 alias 방지)"""
    return unicodedata.normalize("NFC", str(v).strip())


# ──────────────────────────────────────────────
# [1] Load
# ──────────────────────────────────────────────

def load_yaml_dir(path):
    out = {}
    if not os.path.isdir(path):
        return out
    for f in sorted(os.listdir(path)):
        if f.endswith((".yaml", ".yml")):
            with open(os.path.join(path, f), encoding="utf-8") as fh:
                out[f] = yaml.safe_load(fh) or {}
    return out


def load_codebooks(path):
    """codebook 은 내용이 아니라 규정 준수(source·as_of) 검사 대상으로만 로드.
    두 형식을 인정한다: ① 머리 주석에 source=/as_of= ② source·as_of CSV 컬럼 (행 단위)"""
    out = {}
    if not os.path.isdir(path):
        return out
    for f in sorted(os.listdir(path)):
        if f.endswith(".csv"):
            with open(os.path.join(path, f), encoding="utf-8-sig") as fh:
                header_comments, csv_header, as_of_values = [], "", []
                reader = None
                for line in fh:
                    if line.startswith("#"):
                        header_comments.append(line)
                    elif not csv_header:
                        csv_header = line
                        cols = [c.strip() for c in line.rstrip("\n").split(",")]
                        if "as_of" in cols and "source" in cols:
                            reader = csv.DictReader(fh, fieldnames=cols)
                    elif reader is not None:
                        break
                if reader is not None:
                    fh.seek(0)
                    rows = csv.DictReader(l for l in fh if not l.startswith("#"))
                    as_of_values = [r.get("as_of", "") for r in rows if r.get("as_of")]
            out[f] = {"comments": "".join(header_comments), "csv_header": csv_header,
                      "as_of_values": as_of_values}
    return out


def apply_alias_extensions(shared):
    """`alias_extensions: {node_id: [alias…]}` — 다른 파일(주로 자동 생성분)이 기존 노드에 alias 만 덧붙인다.
    대상 노드가 어느 파일에도 없으면 오류 목록으로 반환. 적용 후엔 일반 alias 와 동일하게 검증·생성·리포트된다."""
    owner = {}
    for fname, doc in shared.items():
        for nid in (doc.get("nodes") or {}):
            owner[nid] = fname
    errors, n = [], 0
    for fname, doc in shared.items():
        for nid, als in (doc.get("alias_extensions") or {}).items():
            if nid not in owner:
                errors.append(f"[V7] alias_extensions 대상 노드 없음: {fname} → {nid}")
                continue
            node = shared[owner[nid]]["nodes"][nid]
            node.setdefault("aliases", [])
            for al in als or []:
                al = dict(al); al.setdefault("source", "extension")
                node["aliases"].append(al); n += 1
    return errors, n


def iter_aliases(shared):
    """모든 shared 파일의 alias 를 (파일, entity, node_id, alias dict) 로 평탄화"""
    for fname, doc in shared.items():
        for node_id, node in (doc.get("nodes") or {}).items():
            for al in node.get("aliases") or []:
                yield fname, doc.get("entity", "?"), node_id, al


# ──────────────────────────────────────────────
# [2] Validate — 실패 시 산출물을 만들지 않는다
# ──────────────────────────────────────────────

def db_columns(con, table):
    # 소문자 정규화 — SQLite 컬럼명은 대소문자를 구분하지 않으며,
    # 1차 채권은 대문자·2차 배포본(2026-08-24)은 전부 소문자라 yaml 표기가 섞여 있다.
    return [c[1].lower() for c in con.execute(f"pragma table_info({table})")]


def db_distinct(con, table, column):
    """컬럼의 distinct 값 → {정규화값: 행수}. NULL·공백 제외"""
    rows = con.execute(
        f"select cast({column} as text), count(*) from {table} "
        f"where {column} is not null group by 1"
    ).fetchall()
    out = {}
    for v, n in rows:
        nv = norm(v)
        if nv == "":
            continue
        out[nv] = out.get(nv, 0) + n
    return out


def validate(con, enums, shared, codebooks):
    errors, warnings = [], []
    entity_names = {doc.get("entity") for doc in shared.values()}
    distinct_cache = {}

    def distinct(table, column):
        key = (table, column)
        if key not in distinct_cache:
            distinct_cache[key] = db_distinct(con, table, column)
        return distinct_cache[key]

    # V5+V1: 테이블·컬럼 실존 → raw 값 실존 (죽은 alias 검출)
    seen = {}  # (table, column, raw정규화) → [node_id...] — V2 충돌 검사용
    for fname, entity, node_id, al in iter_aliases(shared):
        t, c, raw = al.get("table"), al.get("column"), al.get("raw")
        status = al.get("status", "confirmed")
        where = f"{fname} {node_id} ({t}.{c} = {raw!r})"
        if t not in ALIAS_TABLE_CLASS:
            errors.append(f"[V5] 미지의 테이블: {where}")
            continue
        if (c or "").lower() not in db_columns(con, t):
            errors.append(f"[V5] 컬럼 없음: {where}")
            continue
        nraw = norm(raw)
        if nraw not in distinct(t, c):
            msg = f"[V1] 죽은 alias — DB distinct 에 없는 값: {where}"
            (warnings if status == "pending" else errors).append(msg)
        if al.get("source") == "rule_component":
            # 복합 벤치마크 성분 부착(2026-08-31) — 한 raw 를 성분 노드 여럿에 다는 **의도적** 다중 매핑.
            # V1(실존)·V5(컬럼)는 위에서 이미 검사했고, V2(판정 충돌)만 면제한다.
            continue
        seen.setdefault((t, c, nraw), []).append(f"{entity}.{node_id}")

    # V2: 한 raw 값이 두 노드에 매달림 (판정 충돌)
    for (t, c, nraw), nodes in seen.items():
        if len(set(nodes)) > 1:
            errors.append(f"[V2] raw 값 충돌: {t}.{c} = {nraw!r} → {sorted(set(nodes))}")

    # V3: enums 의 kg_entity 포인터가 shared 에 실존하는가
    #     경고로 둔다 — shared 파일보다 kg_entity 기입이 먼저 오는 게 정상 순서(선행 기입 후 shared 작성)
    for fname, doc in enums.items():
        for col, spec in (doc.get("columns") or {}).items():
            ke = (spec or {}).get("kg_entity")
            if ke and ke not in entity_names:
                warnings.append(f"[V3] 미완 kg_entity 포인터: enums/{fname} {col} → {ke!r} (shared 미작성 — 할 일)")

    # V4: codebook 규정 — source · as_of(≤ 기준일) 필수. 주석 형식/CSV 컬럼 형식 모두 인정
    for fname, cb in codebooks.items():
        header = cb["comments"]
        cols = [c.strip() for c in cb["csv_header"].rstrip("\n").split(",")]
        has_cols = "source" in cols and "as_of" in cols
        if not has_cols and "source=" not in header and "source =" not in header:
            errors.append(f"[V4] codebooks/{fname}: source 없음 (주석에도 컬럼에도)")
        if has_cols:
            bad = [v for v in cb["as_of_values"] if v > DATA_CUTOFF]
            if bad:
                errors.append(f"[V4] codebooks/{fname}: as_of {max(bad)} > 기준일 {DATA_CUTOFF} — 규정 위반 {len(bad)}행")
        else:
            m = re.search(r"as_of\s*=\s*(\d{4}-\d{2}-\d{2})", header)
            if not m:
                errors.append(f"[V4] codebooks/{fname}: as_of 없음 (주석에도 컬럼에도)")
            elif m.group(1) > DATA_CUTOFF:
                errors.append(f"[V4] codebooks/{fname}: as_of {m.group(1)} > 기준일 {DATA_CUTOFF} — 규정 위반")

    # V6: absent_in 선언인데 실제로는 컬럼이 있는 경우 (선언 자체가 죽음)
    for fname, doc in shared.items():
        prop = doc.get("property", "?")
        for t in (doc.get("absent_in") or {}):
            if t not in TABLE_CLASS:
                errors.append(f"[V6] {fname} absent_in 미지의 테이블: {t}")

    return errors, warnings, distinct_cache


# ──────────────────────────────────────────────
# [3] Emit — kg_* 4테이블 전체 재생성(멱등) + ontology.ttl
# ──────────────────────────────────────────────

def emit_kg(con, shared):
    cur = con.cursor()
    for t in ("kg_node", "kg_alias", "kg_edge", "kg_closure"):
        cur.execute(f"drop table if exists {t}")
    cur.execute("""create table kg_node (
        node_id TEXT PRIMARY KEY, node_type TEXT, canonical_name TEXT,
        label_ko TEXT, label_en TEXT)""")
    cur.execute("""create table kg_alias (
        node_id TEXT, table_name TEXT, column_name TEXT, raw_value TEXT, source TEXT)""")
    cur.execute("""create table kg_edge (
        src_id TEXT, predicate TEXT, dst_id TEXT, source TEXT, as_of TEXT)""")
    cur.execute("create table kg_closure (ancestor_id TEXT, descendant_id TEXT)")

    # 🔴 운용사 정식명 라벨 보강 (2026-09-01 FND-034 실측) — organization.yaml 의 label_ko 는
    #    약칭('삼성')이라 매칭 하한(한글 3자)에 걸려 '삼성자산운용' 질의가 Ground 매칭 0 이 됐다
    #    (미래에셋은 4자라 우연히 통과). public_funds 운용사 코드 alias 를 가진 노드에
    #    asset_manager.csv 의 정식명을 '/' 라벨 조각으로 병합한다 — 런타임 _keys 가 '/' 를 갈라
    #    조각마다 단어경계 매칭을 하므로 '삼성'(2자)은 계속 걸러지고 정식명만 매칭에 참여한다.
    mgr_names = {}
    _am = os.path.join(PROJECT_ROOT, "ontology", "codebooks", "asset_manager.csv")
    with open(_am, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            nm = (r.get("name") or "").replace("(주)", "").strip()
            if nm:
                mgr_names[r["code"].strip()] = nm

    n_node = n_alias = n_edge = n_closure = 0
    for fname, doc in shared.items():
        entity = doc.get("entity")
        parents = {}
        for node_id, node in (doc.get("nodes") or {}).items():
            # 🔴 label_ko 에 '/' 병합하면 안 된다 — 런타임 _keys 가 '/' 조각에 단어경계 검사를 붙여
            #    '미래에셋코어테크' 같은 브랜드+상품명 합성어 매칭이 통째로 죽는다(2026-09-01 저녁
            #    FND-016 재검 실측: Ground 매칭 없음 회귀). 정식명은 **빈 label_en 슬롯**에 넣는다 —
            #    전체 라벨은 무경계 부분일치라 '삼성자산운용이…' 도 매칭되고 합성어도 다치지 않는다.
            label_en = node.get("label_en")
            for al in node.get("aliases") or []:
                if al.get("table") == "public_funds" and al.get("column") == "or_co_xtn_itt_cd":
                    nm = mgr_names.get(str(al.get("raw", "")).strip())
                    if nm and not label_en and nm != node.get("label_ko"):
                        label_en = nm
                    break
            cur.execute("insert into kg_node values (?,?,?,?,?)",
                        (node_id, entity, node.get("label_ko"),
                         node.get("label_ko"), label_en))
            n_node += 1
            if node.get("parent"):
                parents[node_id] = node["parent"]
            for al in node.get("aliases") or []:
                if al.get("status", "confirmed") != "confirmed":
                    continue  # pending 은 KG 에 넣지 않는다 — 리포트에만 표시
                cur.execute("insert into kg_alias values (?,?,?,?,?)",
                            (node_id, al["table"], al["column"], norm(al["raw"]),
                             al.get("source", "manual")))
                n_alias += 1
        # 계층 closure 전개 (지역 등) — 런타임 비용 0 을 위해 빌드 타임에 조상 전부 풀어둠
        for child, parent in parents.items():
            anc = parent
            while anc:
                cur.execute("insert into kg_closure values (?,?)", (anc, child))
                n_closure += 1
                anc = parents.get(anc)
        for e in doc.get("edges") or []:
            cur.execute("insert into kg_edge values (?,?,?,?,?)",
                        (e["src"], e["predicate"], e["dst"],
                         e.get("source", "manual"), e.get("as_of")))
            n_edge += 1

    cur.execute("create index if not exists idx_kg_alias_raw on kg_alias(table_name, column_name, raw_value)")
    cur.execute("create index if not exists idx_kg_alias_node on kg_alias(node_id)")
    con.commit()
    return n_node, n_alias, n_edge, n_closure


def product_kind_counts(con):
    """ETF 마스터 테이블별 pd_grp_no 실측 — 상품종류 클래스 주석의 근거 수치"""
    out = {}
    for t in ("domestic_etfs", "overseas_etfs"):
        try:
            rows = con.execute(
                f"select trim(pd_grp_no), count(*) from {t} group by 1"
            ).fetchall()
            out[t] = {norm(k): n for k, n in rows if k is not None}
        except sqlite3.Error:
            out[t] = {}
    return out


# Turtle PN_LOCAL 에서 백슬래시 이스케이프로 살릴 수 있는 문자 (Turtle 문법 PN_LOCAL_ESC)
_PN_ESCAPABLE = set("~.-!$&'()*+,;=/?#@%_")


def ttl_local(name):
    """노드 ID → Turtle 로컬네임. 자동 생성 ID 에 CUSIP '*' 등 불법 문자가 실재해(예: Sec_o_74751*AK2)
    이스케이프 없이 내보내면 ttl 전체가 파싱 불가가 된다 (2026-08-26 rdflib 검증에서 발견 — main 에도 있던 버그)."""
    out = []
    for i, ch in enumerate(str(name)):
        if ch.isalnum() or ch == "_" or ord(ch) > 0x00C0:
            out.append(ch)
        elif ch in "-." and 0 < i < len(str(name)) - 1:
            out.append(ch)                    # '-'·'.' 은 중간에서만 허용
        elif ch in _PN_ESCAPABLE:
            out.append("\\" + ch)             # PN_LOCAL_ESC
        else:
            out.append("_")                   # 이스케이프 불가 문자(공백 등)는 '_' 치환
    return "".join(out)


def ttl_str(text):
    """리터럴 문자열 이스케이프 — 라벨·주석의 '"'·'\\' 가 문자열을 깨뜨리지 않게."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def _ttl_header(what):
    return [
        "# GENERATED by scripts/build_ontology.py — DO NOT EDIT",
        "# 원천: ontology/enums/*.yaml + ontology/shared/*.yaml — 고칠 것은 yaml 이다",
        f"# {what}",
        "@prefix fp:   <http://mafest.ai/product#> .",   # 제출 규격 p.9 원문 그대로 — 임의 변경 금지
        "@prefix owl:  <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]


# 도메인 파일별 대표 DatatypeProperty — "값은 RDB 컬럼에 있고, 스키마상 의미를 ttl 로 선언"
# (fp:expenseRatio 는 규격 p.9 etf_gl.ttl 예시 그대로. 값 자체는 SQLite 가 정본 — 여기엔 사상 관계만)
DATATYPE_PROPS = {
    "bond_kr": [
        ("couponRate", "fp:DomesticBond", "xsd:decimal", "표면금리(%) — 컬럼 srfc_irt. 할인채 172건은 이 란에 할인율이 기재됨(검토 B6)"),
        ("duration", "fp:DomesticBond", "xsd:decimal", "듀레이션(년) — 컬럼 dur. 조기상환권부는 산출 불능이라 0 표기(검토 B5, 98.0%)"),
    ],
    "etf_kr": [
        ("aum", "fp:DomesticETF", "xsd:decimal", "순자산총액 — 컬럼 du_last_aum, 단위 KRW(원). 해외ETF(USD)와 통합 정렬 금지"),
        ("leverageMultiple", "fp:DomesticETF", "xsd:decimal", "레버리지 배수 — 컬럼 cu_lev_fector. 2차에서 부호 소실: 방향은 상품명 '인버스' 로 판정(derivation_rules.inverse_direction)"),
    ],
    "etf_gl": [
        ("expenseRatio", "fp:ETF", "xsd:decimal", "총보수(%) — 컬럼 cu_charge_rt. 규격 p.9 예시 속성. 국내ETF 는 유효 67건뿐(0=미입력)"),
    ],
    "fund_pub": [
        ("navTotal", "fp:PublicFund", "xsd:decimal", "순자산 — 컬럼 fd_nast_suma. 클래스별 중복 기재라 SUM 금지, 펀드 단위 MAX 집계"),
    ],
}


def emit_ttl(shared, con=None):
    """제출 규격 5분할 출력 — common.ttl(공통 클래스·공유 개체) + 도메인 4파일.

    분할 원칙:
      · fp:Product 계층·상품종류(ETF/ETN)·공유 개체 6축(지수·지역·기관·등급·통화·자산군 등)은 common.ttl —
        도메인 파일로 쪼개면 "같은 지수 추종 ETF+펀드" 교차질의 연결이 끊긴다.
      · 각 도메인 파일: 테이블 클래스 + 그 테이블의 속성 부재(ABSENT) 선언 + 대표 DatatypeProperty.
    """
    F = {k: _ttl_header({
            "common":   "common.ttl — 공통 상위 클래스(fp:Product)·상품종류·공유 개체 (제출 규격 p.9: 공통 상위 클래스는 common.ttl 로 분리)",
            "bond_kr":  "bond_kr.ttl — 국내채권 (SQLite domestic_bonds)",
            "etf_kr":   "etf_kr.ttl — 국내 ETF (SQLite domestic_etfs)",
            "etf_gl":   "etf_gl.ttl — 해외 ETF (SQLite overseas_etfs)",
            "fund_pub": "fund_pub.ttl — 공모펀드 (SQLite public_funds)",
        }[k]) for k in TTL_FILES}
    C = F["common"]

    # ── common: fp:Product 계층 + 상품종류 ──
    C.append("# ── 상품 클래스 계층 ──")
    C.append("# 축이 둘이다. 섞으면 안 된다:")
    C.append("#   (a) 테이블 클래스 — 데이터가 어느 마스터에서 왔나 (fp:DomesticETF … — 각 도메인 ttl 에서 선언)")
    C.append("#   (b) 상품종류 클래스 — 그 상품이 ETF 인가 ETN 인가 (fp:ETF / fp:ETN)")
    C.append("# 두 ETF 마스터에는 ETN 이 섞여 있어 (a) 는 (b) 의 하위가 아니다 —")
    C.append("# fp:DomesticETF rdfs:subClassOf fp:ETF 로 두면 ETN 행까지 ETF 로 단정해 disjointWith 와 모순이 된다.")
    C.append("fp:Product a owl:Class ; rdfs:comment \"금융상품 공통 상위 클래스 — 제출 규격 p.9 의 fp:Product\"@ko .")
    C.append("")
    C.append("# 상품종류 — ETF ⊥ ETN")
    C.append("fp:ETF rdfs:subClassOf fp:Product ; rdfs:comment \"상장지수펀드 — 운용사가 설정한 펀드\"@ko .")
    C.append("fp:ETN rdfs:subClassOf fp:Product ; rdfs:comment \"상장지수증권 — 증권사가 발행한 채무증권. 발행사 신용위험이 있고 구성종목 개념이 없다\"@ko .")
    C.append("fp:ETF owl:disjointWith fp:ETN .  # 한 상품이 둘 다일 수 없다 — 'ETF' 질의에 ETN 이 섞이면 오답")
    counts = product_kind_counts(con) if con is not None else {}
    for t in ("domestic_etfs", "overseas_etfs"):
        c = counts.get(t) or {}
        if c:
            detail = " · ".join(f"{k} {n:,}건" for k, n in sorted(c.items()))
            C.append(f"# 판별자: {t}.pd_grp_no → {detail} (실측). fp:ETF 질의는 pd_grp_no='ETF' 필터 필수")
    C.append("")
    C.append("# ── 외부 수집 보조 테이블 (마스터 아님 — Security alias 원천, 상품→종목 관계는 이 테이블이 edge 역할) ──")
    for cls in dict.fromkeys(EXT_CLASS.values()):
        tables = ", ".join(t for t, c in EXT_CLASS.items() if c == cls)
        C.append(f"fp:{cls} a owl:Class ; rdfs:comment \"외부 수집 테이블 {tables} (발행일 ≤ {DATA_CUTOFF})\"@ko .")
    C.append("")
    C.append("# ── 역관계 (규격 작성 팁: inverseOf — '운용사가 상품을 운용한다' ↔ '상품이 운용사에 의해 운용된다') ──")
    C.append("fp:manages a owl:ObjectProperty ; owl:inverseOf fp:hasManager ; rdfs:comment \"운용사 → 상품 (fp:hasManager 의 역)\"@ko .")
    C.append("fp:issues a owl:ObjectProperty ; owl:inverseOf fp:hasIssuer ; rdfs:comment \"발행사 → 상품 (fp:hasIssuer 의 역)\"@ko .")
    C.append("fp:isHeldBy a owl:ObjectProperty ; owl:inverseOf fp:holds ; rdfs:comment \"종목 → 그 종목을 편입한 상품 (fp:holds 의 역) — '삼성전자 편입 ETF' 질의의 탐색 방향\"@ko .")
    C.append("")
    C.append("# ── 위험등급 값 제약 (규격 작성 팁: riskGrade 0~6 — 1~5 로 제약하면 실데이터가 차단된다: 6등급 채권 24.6%·0등급 존재) ──")
    C.append("fp:riskGradeValue a owl:DatatypeProperty ;")
    C.append("    rdfs:domain [ owl:unionOf ( fp:DomesticBond fp:DomesticETF fp:PublicFund ) ] ;  # 해외ETF 는 위험등급 컬럼 자체가 없음(ABSENT — etf_gl.ttl)")
    C.append("    rdfs:range [ a rdfs:Datatype ; owl:onDatatype xsd:integer ;")
    C.append("                 owl:withRestrictions ( [ xsd:minInclusive 0 ] [ xsd:maxInclusive 6 ] ) ] ;")
    C.append("    rdfs:comment \"위험등급 정수값 0~6 — 개체 표현은 fp:hasRiskGrade → fp:RiskGrade 노드\"@ko .")
    C.append("")

    # ── 도메인 4파일: 테이블 클래스 + 대표 DatatypeProperty ──
    for key, (_, table) in TTL_FILES.items():
        if not table:
            continue
        D = F[key]
        cls = TABLE_CLASS[table]
        D.append(f"fp:{cls} rdfs:subClassOf fp:Product ; rdfs:comment \"SQLite 테이블 {table}\"@ko .")
        if key == "etf_gl":
            D.append("fp:ForeignETF rdfs:subClassOf fp:ETF ; rdfs:comment \"해외 상장 ETF — 제출 규격 p.9 예시 클래스. 데이터상 fp:OverseasETF 중 pd_grp_no='ETF' 인 5,972건이 해당\"@ko .")
        D.append("")
        for name, domain, rng, comment in DATATYPE_PROPS.get(key, []):
            D.append(f"fp:{name} a owl:DatatypeProperty ;")
            D.append(f"    rdfs:domain {domain} ;")
            D.append(f"    rdfs:range  {rng} ;")
            D.append(f"    rdfs:comment \"{comment}\"@ko .")
        D.append("")

    # ── 공유 개체 6축 (+자동 생성분) → common · ABSENT 선언 → 해당 도메인 파일 ──
    declared_cls, declared_prop = set(), set()
    for fname, doc in shared.items():
        entity = doc.get("entity")
        prop_orig = doc.get("property")
        prop = prop_orig
        absent = doc.get("absent_in") or {}
        have_tables = sorted({al["table"] for _, _, _, al in iter_aliases({fname: doc})
                              if al.get("status", "confirmed") == "confirmed"})
        C.append(f"# ── {entity} (shared/{fname}) ──")
        if entity not in declared_cls:   # 같은 entity 를 여러 파일(수동 + 자동 생성)이 선언할 수 있다 — 한 번만
            C.append(f"fp:{entity} a owl:Class .")
            declared_cls.add(entity)
        if prop and prop in declared_prop:
            prop = None
        if prop:
            declared_prop.add(prop)
            domains = " ".join(f"fp:{c}" for c in dict.fromkeys(ALIAS_TABLE_CLASS[t] for t in have_tables))
            C.append(f"fp:{prop} a owl:ObjectProperty ;")
            C.append(f"    rdfs:domain [ owl:unionOf ( {domains} ) ] ;")
            C.append(f"    rdfs:range fp:{entity} ;")
            comment = doc.get("description", "")
            if doc.get("scale"):
                comment += f" | scale: {doc['scale']} | direction: {doc.get('direction','')}"
            C.append(f"    rdfs:comment \"{ttl_str(comment.strip())}\"@ko .")
        for t, why in absent.items():
            # 속성 부재 선언 — "없다"가 네거티브 질의 기각의 근거. 그 테이블의 도메인 ttl 에 둔다.
            D = F[TABLE_TTL[t]]
            D.append(f"# ABSENT: fp:{TABLE_CLASS[t]} 에는 fp:{prop_orig} 없음 — {why}")
            D.append(f"fp:{TABLE_CLASS[t]} rdfs:comment \"{ttl_str(f'{prop_orig} 속성 없음: {why}')}\"@ko .")
        for node_id, node in (doc.get("nodes") or {}).items():
            nid = ttl_local(node_id)
            labels = [f"\"{ttl_str(node['label_ko'])}\"@ko"] if node.get("label_ko") else []
            if node.get("label_en"):
                labels.append(f"\"{ttl_str(node['label_en'])}\"@en")
            lab = f" ; skos:prefLabel {', '.join(labels)}" if labels else ""
            C.append(f"fp:{nid} a fp:{entity}{lab} .")
            if node.get("parent"):
                C.append(f"fp:{nid} skos:broader fp:{ttl_local(node['parent'])} .")
        for e in doc.get("edges") or []:
            C.append(f"fp:{ttl_local(e['src'])} fp:{e['predicate']} fp:{ttl_local(e['dst'])} .")
        C.append("")

    out = {}
    for key, (fname, _) in TTL_FILES.items():
        path = os.path.join(TTL_DIR, fname)
        with open(path, "w", encoding="utf-8", newline="\n") as f:  # 커밋 대상 — LF 고정 (CRLF 상태 노이즈 방지)
            f.write("\n".join(F[key]) + "\n")
        out[fname] = len(F[key])
    return out


# ──────────────────────────────────────────────
# [4] Report — 미매핑 distinct 가 다음 EDA 의 할 일 목록이다
# ──────────────────────────────────────────────

def report(con, enums, shared, distinct_cache, warnings):
    lines = ["# KG coverage report (GENERATED by build_ontology.py)", ""]
    pendings = []
    # enums 의 kg_entity 포인터 → 해당 컬럼도 그 entity 의 커버리지 대상이다 (alias 0건이어도 표시)
    pointer_cols = {}  # entity → {(table, column)}
    for fname, doc in enums.items():
        t = doc.get("domain")
        for col, spec in (doc.get("columns") or {}).items():
            ke = (spec or {}).get("kg_entity")
            if ke and t in TABLE_CLASS:
                pointer_cols.setdefault(ke, set()).add((t, col))
    # entity 단위로 집계 — 수동 파일(index.yaml)과 자동 파일(index_auto.yaml)이 같은 entity·컬럼을 나눠 가지므로
    # 파일별로 찍으면 "1/905" 같은 오해를 낳는다 (2026-08-25). 매핑 집합은 entity 안에서 합산하고 파일 목록만 병기.
    by_entity = {}   # entity → {"files": [...], "cols": {(t,c): set(raw)}, "absent": {t: why}, "alias_ext": int}
    for fname, doc in shared.items():
        entity = doc.get("entity")
        e = by_entity.setdefault(entity, {"files": [], "cols": {}, "absent": {}})
        e["files"].append(fname)
        for key in pointer_cols.get(entity, set()):
            e["cols"].setdefault(key, set())
        for _, _, node_id, al in iter_aliases({fname: doc}):
            key = (al["table"], al["column"])
            status = al.get("status", "confirmed")
            e["cols"].setdefault(key, set())
            if status == "confirmed":
                e["cols"][key].add(norm(al["raw"]))
            else:
                pendings.append((entity, node_id, al))
        for t, why in (doc.get("absent_in") or {}).items():
            e["absent"][t] = why
    for entity, e in by_entity.items():
        lines.append(f"## {entity}  (shared/{' + '.join(e['files'])})")
        for (t, c), mapped in sorted(e["cols"].items()):
            dist = distinct_cache.get((t, c))
            if dist is None:
                dist = db_distinct(con, t, c)
            unmapped = {v: n for v, n in dist.items() if v not in mapped}
            mark = "✅" if not unmapped else "→"
            lines.append(f"- {t}.{c} : {len(mapped)}/{len(dist)} 매핑 {mark}")
            for v, n in sorted(unmapped.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"    - 미매핑 {v!r}  ({n:,}행)")
            if len(unmapped) > 5:
                lines.append(f"    - … 외 {len(unmapped)-5}종")
        for t, why in e["absent"].items():
            lines.append(f"- {t} : absent ({why})")
        lines.append("")
    if pendings:
        lines.append(f"## pending 보류 {len(pendings)}건 — KG 미반영, 워크샵 안건")
        for entity, node_id, al in pendings:
            lines.append(f"- {entity}.{node_id} : {al['table']}.{al['column']} = {al['raw']!r}  ({al.get('evidence','')})")
        lines.append("")
    if warnings:
        lines.append(f"## warnings {len(warnings)}건")
        lines.extend(f"- {w}" for w in warnings)
    text = "\n".join(lines)
    with open(REPORT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")
    return text


def main():
    ap = argparse.ArgumentParser(description="yaml → ontology.ttl + kg_* 생성")
    ap.add_argument("--check", action="store_true", help="검증·리포트만 (산출물 생성 안 함)")
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()

    print("=" * 60)
    print("🕸️  온톨로지·KG 생성 파이프라인")
    print("=" * 60)

    if not os.path.exists(args.db):
        print(f"❌ DB 없음: {args.db} — 먼저 scripts/build_db.py 를 실행하세요")
        sys.exit(1)

    enums = load_yaml_dir(ENUMS_DIR)
    shared = load_yaml_dir(SHARED_DIR)
    codebooks = load_codebooks(CODEBOOKS_DIR)
    print(f"📥 [1 Load] enums {len(enums)} · shared {len(shared)} · codebooks {len(codebooks)}")
    if not shared:
        print("⚠️  shared/*.yaml 이 없습니다 — 만들 KG 가 없습니다")
        sys.exit(1)

    ext_errors, n_ext = apply_alias_extensions(shared)
    if n_ext:
        print(f"           alias_extensions 적용 {n_ext}건")
    con = sqlite3.connect(args.db)
    errors, warnings, distinct_cache = validate(con, enums, shared, codebooks)
    errors = ext_errors + errors
    print(f"🔍 [2 Validate] 오류 {len(errors)} · 경고 {len(warnings)}")
    for e in errors:
        print(f"   ❌ {e}")
    for w in warnings:
        print(f"   ⚠️  {w}")
    if errors:
        print("\n❌ 검증 실패 — 산출물을 생성하지 않습니다. yaml 을 고치고 다시 실행하세요.")
        sys.exit(1)

    if args.check:
        print("✅ 검증 통과 (--check 모드 — 산출물 생성 생략)")
    else:
        n_node, n_alias, n_edge, n_closure = emit_kg(con, shared)
        ttl_out = emit_ttl(shared, con)
        print(f"📦 [3 Emit] kg_node {n_node} · kg_alias {n_alias} · kg_edge {n_edge} · kg_closure {n_closure}")
        detail = " · ".join(f"{name} {n:,}줄" for name, n in ttl_out.items())
        print(f"           ttl 5분할(제출 규격 p.9) → ontology/ — {detail}")

    print(f"\n📊 [4 Report] → {os.path.relpath(REPORT_PATH, PROJECT_ROOT)}")
    print(report(con, enums, shared, distinct_cache, warnings))
    con.close()


if __name__ == "__main__":
    main()
