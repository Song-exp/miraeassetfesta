# -*- coding: utf-8 -*-
"""공모펀드 — DB ↔ yaml ↔ KG 삼각 대조. yaml 의 수치 주장·규칙 참조 컬럼·KG alias 를 2차 DB 로 재현하고 불일치만 앞에 모은다.

실행: python scripts/audit_funds_claims.py        (채권 scripts/audit_bonds_claims.py 와 같은 형식)
원칙: 어림하지 않고 yaml 에 적힌 조건식을 그대로 실행한다. 불일치는 "yaml 이 틀렸다" 가 아니라 "둘 중 하나를 고쳐야 한다" 는 신호다.
"""
import io
import re
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
c = sqlite3.connect(f"{(ROOT / 'data' / 'financial_products.db').as_uri()}?mode=ro", uri=True)
c.create_function("REGEXP", 2, lambda p, s: 1 if (s is not None and re.search(p, s)) else 0)
Y = yaml.safe_load(io.open(ROOT / "ontology/enums/public_funds.yaml", encoding="utf-8"))
COLS = {r[1]: r[2] for r in c.execute("pragma table_info(public_funds)")}
EXT_COLS = {r[1] for t in ("ext_fund_holdings", "ext_fund_page") for r in c.execute(f"pragma table_info({t})")}

results = []  # (id, claim, expected, actual, ok)


def _eq(a, b, tol):
    if a is None or b is None:
        return a == b
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def chk(id_, claim, sql, expected, tol=0.0):
    try:
        got = c.execute(sql).fetchone()
        got = got[0] if len(got) == 1 else tuple(got)
    except Exception as e:  # noqa: BLE001
        got = f"ERR {e}"
    if isinstance(expected, tuple):
        ok = isinstance(got, tuple) and len(got) == len(expected) and all(_eq(a, b, tol) for a, b in zip(got, expected))
    else:
        ok = _eq(got, expected, tol)
    results.append((id_, claim, expected, got, ok))


F = "FROM public_funds"
BASE = "sale_yn='판매중' AND prvo_pbff_desc='공모'"

# ── 1. 모수 ───────────────────────────────────────────────────────────────
chk("RG-1", "행 23,676 · 공모 14,716 · 판매중 10,962 · 판매중·공모 8,969",
    f"SELECT COUNT(*), SUM(prvo_pbff_desc='공모'), SUM(sale_yn='판매중'), SUM({BASE}) {F}", (23676, 14716, 10962, 8969))
chk("RG-2", "사모 8,960 · 판매완료 12,714", f"SELECT SUM(prvo_pbff_desc='사모'), SUM(sale_yn='판매완료') {F}", (8960, 12714))
chk("RG-3", "itm_no 행 단위 PK (distinct = 행)", f"SELECT COUNT(*) - COUNT(DISTINCT itm_no) {F}", 0)

# ── 2. normalization — 더미·길이·코드폭·0값·상수·이탈값 ──────────────────────
norm = Y["normalization"]
dummy_sql = norm["dummy_as_missing"]["sql"]
for col, n in [("fss_itm_no", 11655), ("kofia_fd_ccd", 11476), ("rptt_ksd_itm_no", 7086),
               ("std_itm_no", 4668), ("ksd_itm_no", 2370), ("mtco_itm_no", 1057)]:
    chk(f"DM-{col}", f"dummy_as_missing {col} = {n:,} (실측_2026-08-29)",
        f"SELECT SUM({dummy_sql.replace('C', col)}) {F}", n)
chk("CW-1", "code_width trusc '0016022' 202행(판매중 178)",
    f"SELECT SUM(trim(trusc_xtn_itt_cd)='0016022'), SUM(trim(trusc_xtn_itt_cd)='0016022' AND sale_yn='판매중') {F}", (202, 178))
chk("CW-2", "code_width or_co '0040106' 2행", f"SELECT SUM(trim(or_co_xtn_itt_cd)='0040106') {F}", 2)
mal = norm["malformed_as_missing"]["sql"]
for col, n in [("std_itm_no", 127), ("ksd_itm_no", 67), ("rptt_ksd_itm_no", 16), ("fss_itm_no", 0)]:
    chk(f"MF-{col}", f"malformed {col} 길이≠12 = {n} (유효값 중)",
        f"SELECT SUM({mal.replace('C', col)}) {F} WHERE NOT ({dummy_sql.replace('C', col)})", n)
chk("MF-sel", "malformed std 판매중 3", f"SELECT SUM({mal.replace('C', 'std_itm_no')} AND sale_yn='판매중') {F} WHERE NOT ({dummy_sql.replace('C', 'std_itm_no')})", 3)
fee0 = norm["zero_as_missing"]["보수_3종전부0"]["sql"]
chk("Z0-1", "보수 3종 동시 0 — 판매중 101 · 판매중·공모 29", f"SELECT SUM({fee0} AND sale_yn='판매중'), SUM({fee0} AND {BASE}) {F}", (101, 29))
chk("Z0-2", "fd_last_dstb_r = -100 센티넬 73행, 전부 판매완료",
    f"SELECT SUM(fd_last_dstb_r=-100), SUM(fd_last_dstb_r=-100 AND sale_yn<>'판매완료') {F}", (73, 0))
chk("Z0-3", "수익률 8기간 < -100 오류값 0건",
    "SELECT SUM(" + " OR ".join(f"{k} < -100" for k in ["fd_mm1_ern_r", "fd_mm3_ern_r", "fd_mm6_ern_r", "fd_mm18_ern_r", "fd_yr1_ern_r", "fd_yr2_ern_r", "fd_yr3_ern_r", "fd_yr5_ern_r"]) + f") {F}", 0)
chk("Z0-4", "1차 규칙 삭제 근거 — 판매중 fd_nast_suma=0 0건 · 8기간 전부 0 인 행 0건",
    f"SELECT SUM(fd_nast_suma=0 AND sale_yn='판매중'), SUM(fd_mm1_ern_r=0 AND fd_mm3_ern_r=0 AND fd_mm6_ern_r=0 AND fd_yr1_ern_r=0) {F}", (0, 0))
chk("CT-1", "contaminated_rows 감지 0", f"SELECT SUM({norm['contaminated_rows']['감지']}) {F}", 0)
chk("VV-1", "value_variants '높은위험' 20 · '보통위험' 8",
    f"SELECT SUM(zrin_fd_ivst_risk_grd_nm='높은위험'), SUM(zrin_fd_ivst_risk_grd_nm='보통위험') {F}", (20, 8))
chk("IV-1", "'00080008' 4,536행(판매중 2,306) = 미래에셋자산운용",
    f"SELECT SUM(or_co_xtn_itt_cd='00080008'), SUM(or_co_xtn_itt_cd='00080008' AND sale_yn='판매중') {F}", (4536, 2306))
chk("IV-2", "'KRZ50226929C' 1행", f"SELECT SUM(trim(ksd_itm_no)='KRZ50226929C') {F}", 1)
chk("CC-1", "hdge_fd_yn 0:23,466/1:210 · 공모 1 = 0", f"SELECT SUM(hdge_fd_yn=0), SUM(hdge_fd_yn=1), SUM(hdge_fd_yn=1 AND prvo_pbff_desc='공모') {F}", (23466, 210, 0))
chk("CC-2", "ofsfd_yn 0:23,560/1:116 · 공모 1 = 110", f"SELECT SUM(ofsfd_yn=0), SUM(ofsfd_yn=1), SUM(ofsfd_yn=1 AND prvo_pbff_desc='공모') {F}", (23560, 116, 110))
chk("CC-3", "frc_bpr_itm_yn 1:413 · 공모 1:90", f"SELECT SUM(frc_bpr_itm_yn=1), SUM(frc_bpr_itm_yn=1 AND prvo_pbff_desc='공모') {F}", (413, 90))
chk("TR-1", "trim — std_itm_no '00000       '(12자) 패딩 145 · itm_abrv_nm 꼬리공백 45(판매중 44)",
    f"SELECT SUM(std_itm_no='00000       '), SUM(itm_abrv_nm<>trim(itm_abrv_nm)), SUM(itm_abrv_nm<>trim(itm_abrv_nm) AND sale_yn='판매중') {F}", (145, 45, 44))
chk("DS-1", "화이트리스트 반례 — fd_estb_ctry_cd '000' 23,055 · pfiv_sale_cntl_tcd '00' 22,263 · fd_set_pcd '00' 1,967",
    f"SELECT SUM(fd_estb_ctry_cd='000'), SUM(pfiv_sale_cntl_tcd='00'), SUM(fd_set_pcd='00') {F}", (23055, 22263, 1967))

# ── 3. entities 블록 count ──────────────────────────────────────────────────
grp_key = "or_co_xtn_itt_cd || '|' || CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no ELSE substr('0000000' || mtco_itm_no, -7) END"
chk("EN-Fund", "Fund 합성키 원값 distinct 14,467(더미 배제) · 판매중 4,340",
    f"SELECT COUNT(DISTINCT or_co_xtn_itt_cd||'|'||mtco_itm_no), COUNT(DISTINCT CASE WHEN sale_yn='판매중' THEN or_co_xtn_itt_cd||'|'||mtco_itm_no END) {F} WHERE NOT ({dummy_sql.replace('C', 'mtco_itm_no')})", (14467, 4340))
chk("EN-Fund-pad", "Fund 합성키 zero-pad distinct 14,409 · 판매중 4,305 (펀드단위 규칙 기준)",
    f"SELECT COUNT(DISTINCT {grp_key}), COUNT(DISTINCT CASE WHEN sale_yn='판매중' THEN {grp_key} END) {F} WHERE NOT ({dummy_sql.replace('C', 'mtco_itm_no')})", (14409, 4305))
chk("EN-Share", "ShareClass han_clas_nm 195종", f"SELECT COUNT(DISTINCT han_clas_nm) {F} WHERE han_clas_nm IS NOT NULL", 195)
chk("EN-Mgr", "AssetManager or_co 275종(판매중 226)",
    f"SELECT COUNT(DISTINCT or_co_xtn_itt_cd), COUNT(DISTINCT CASE WHEN sale_yn='판매중' THEN or_co_xtn_itt_cd END) {F}", (275, 226))
chk("EN-Cust", "Custodian trusc 50종", f"SELECT COUNT(DISTINCT trusc_xtn_itt_cd) {F} WHERE trusc_xtn_itt_cd IS NOT NULL", 50)
chk("EN-Bmk", "Benchmark bmrk_nm 389종", f"SELECT COUNT(DISTINCT bmrk_nm) {F} WHERE bmrk_nm IS NOT NULL", 389)
chk("EN-Attr", "FundAttribute 태그 보유 11,280(판매중 8,550)",
    f"SELECT SUM(prfd_attr_cds IS NOT NULL AND prfd_attr_cds<>''), SUM(prfd_attr_cds IS NOT NULL AND prfd_attr_cds<>'' AND sale_yn='판매중') {F}", (11280, 8550))
tags = set()
for (v,) in c.execute(f"SELECT prfd_attr_cds {F} WHERE prfd_attr_cds IS NOT NULL AND prfd_attr_cds<>''"):
    tags.update(t.strip() for t in v.split(","))
attr_tags = {t for t in tags if re.fullmatch(r"[A-Z]\d{3}", t)}
iso_tags = {t for t in tags if re.fullmatch(r"[A-Z]{3}", t)}
results.append(("EN-Tag", "속성코드 210종 · 국가코드 17종 (prfd_attr_cds 토큰)", (210, 17), (len(attr_tags), len(iso_tags)), (len(attr_tags), len(iso_tags)) == (210, 17)))
cb = {r.split(",")[0] for r in io.open(ROOT / "ontology/codebooks/fund_attr_code.csv", encoding="utf-8-sig").read().splitlines()[1:] if r}
results.append(("EN-CB", "코드북 fund_attr_code.csv 가 DB 속성코드를 전부 덮음", 0, len(attr_tags - cb), attr_tags <= cb))

# ── 4. columns.answerable_n ↔ 기본모수 non-null ─────────────────────────────
an_mismatch = []
for col, v in Y["columns"].items():
    if not isinstance(v, dict) or v.get("answerable_n") is None or col not in COLS:
        continue
    if any(str(k).startswith("sql_") for k in v):   # 자체 정의(sql_영문실재 등)가 있는 컬럼은 non-null 이 기준이 아니다
        continue
    nn = c.execute(f"SELECT SUM({col} IS NOT NULL AND trim(CAST({col} AS TEXT))<>'') {F} WHERE {BASE}").fetchone()[0] or 0
    tot = c.execute(f"SELECT SUM({col} IS NOT NULL AND trim(CAST({col} AS TEXT))<>'') {F}").fetchone()[0] or 0
    an = int(str(v["answerable_n"]).replace(",", ""))
    if an not in (nn, tot):
        an_mismatch.append((col, an, nn, tot))
results.append(("AN-*", f"answerable_n = 기본모수 non-null 또는 전체 non-null ({len([1 for v in Y['columns'].values() if isinstance(v, dict) and v.get('answerable_n') is not None])}컬럼)",
                "불일치 0", an_mismatch or 0, not an_mismatch))

# ── 5. value_semantics 키가 DB 에 실재하는가 ────────────────────────────────
vs_missing = []
for col, v in Y["columns"].items():
    if not isinstance(v, dict) or col not in COLS or not isinstance(v.get("value_semantics"), dict):
        continue
    vals = {str(r[0]) for r in c.execute(f"SELECT DISTINCT {col} {F}") if r[0] is not None}
    vals |= {s.rstrip("0").rstrip(".") for s in vals} | {s.replace(".0", "") for s in vals}
    for k in v["value_semantics"]:
        if k is None or str(k).startswith("_"):
            continue
        if str(k) not in vals and str(k).strip() not in vals:
            vs_missing.append((col, k))
results.append(("VS-*", "value_semantics 키 실재", "누락 0", vs_missing or 0, not vs_missing))

# ── 6. query_rules 가 가리키는 컬럼 실존 + 순수 SQL 규칙 실행 ───────────────
rule_text = "\n".join(str(v) for k, v in Y["query_rules"].items()) + "\n" + "\n".join(Y.get("answer_rules") or [])
tokens = set(re.findall(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", rule_text))
known = set(COLS) | EXT_COLS | {"public_funds", "domestic_etfs", "ext_fund_holdings", "ext_fund_page", "zero_is_value", "zero_as_missing",
                                "query_rules", "dummy_as_missing", "kg_alias", "or_co", "mtco", "pd_itm_no", "ref_base_index", "sale_co", "ofwk_trus"}
unknown = sorted(t for t in tokens if t not in known and not re.fullmatch(r"fd_\w*_ern_r", t))
results.append(("QR-cols", "query_rules·answer_rules 가 가리키는 컬럼이 전부 실존", "미실존 0", unknown or 0, not unknown))
qr = Y["query_rules"]
for name in ["판매중만", "구매가능", "공모만", "기본모수", "ETF제외", "자산군_주식형"]:
    cond = str(qr[name]).split("#")[0].strip()
    chk(f"QR-{name}", f"query_rules.{name} 조건식 실행 가능", f"SELECT COUNT(*) {F} WHERE {cond} LIMIT 1", None, tol=1e18)
    results[-1] = (results[-1][0], results[-1][1], "실행됨", results[-1][3], not str(results[-1][3]).startswith("ERR"))
chk("QR-펀드단위", "펀드단위 GROUP BY 실행 가능", f"SELECT COUNT(*) FROM (SELECT 1 {F} WHERE {BASE} {qr['펀드단위'].strip()})", None, tol=1e18)
results[-1] = (results[-1][0], results[-1][1], "실행됨", results[-1][3], not str(results[-1][3]).startswith("ERR"))
chk("QR-대표행", "대표행 — 한화2.2배레버리지 6클래스가 grp 하나로 묶임",
    f"SELECT COUNT(*), COUNT(DISTINCT {grp_key}) {F} WHERE itm_nm LIKE '한화2.2배레버리지%' AND {BASE}", (6, 1))

# ── 7. KG ↔ DB — alias 사어 · 커버리지 · 가짜 노드 ─────────────────────────
dead = []
for col, in c.execute("SELECT DISTINCT column_name FROM kg_alias WHERE table_name='public_funds'"):
    if col not in COLS:
        dead.append((col, "컬럼 없음")); continue
    # match_kind='token'(KG 1R S3, c82bf50) 은 콤마 목록 안의 태그 코드라 셀 등호가 아니라 ',raw,' 포함으로 실재를 본다
    #   (2026-09-02 전수 재검증: prfd_attr_cds token alias 196건이 등호 검사에서 전부 '사어' 오탐).
    n = c.execute(f"""SELECT COUNT(*) FROM kg_alias a WHERE a.table_name='public_funds' AND a.column_name=?
                      AND NOT EXISTS (SELECT 1 {F} p WHERE CASE WHEN a.match_kind='token'
                                          THEN ',' || CAST(p.{col} AS TEXT) || ',' LIKE '%,' || a.raw_value || ',%'
                                          ELSE trim(CAST(p.{col} AS TEXT)) = a.raw_value END)""", (col,)).fetchone()[0]
    if n:
        dead.append((col, n))
results.append(("KG-dead", "kg_alias(public_funds) raw_value 가 DB 에 실재", "사어 0", dead or 0, not dead))
cov = []
for col in ["or_co_xtn_itt_cd", "trusc_xtn_itt_cd", "bmrk_nm", "zrin_btyp_nm", "zrin_fd_ivst_risk_grd_nm", "curr_cd", "fd_ivst_rgn_desc"]:
    sentinels = [str(k) for k in ((Y["columns"].get(col) or {}).get("missing_semantics") or {}) if k and str(k) != "null"]
    rows = c.execute(f"SELECT DISTINCT trim(CAST({col} AS TEXT)) {F} WHERE {BASE} AND {col} IS NOT NULL AND trim(CAST({col} AS TEXT))<>'' "
                     + "".join(f" AND trim(CAST({col} AS TEXT)) <> '{sv}'" for sv in sentinels)
                     + f" AND trim(CAST({col} AS TEXT)) NOT IN (SELECT raw_value FROM kg_alias WHERE table_name='public_funds' AND column_name=?)", (col,)).fetchall()
    if rows:
        cov.append((col, len(rows), [r[0] for r in rows[:4]]))
results.append(("KG-cov", "기본모수의 값이 KG alias 에 빠짐없이 붙어 있는가 (7컬럼 · 선언된 센티넬 제외)", "미부착 0", cov or 0, not cov))
chk("KG-Fund", "Fund 노드 alias 6,867 = rptt 유효값(더미·길이이탈 제외) distinct",
    f"SELECT (SELECT COUNT(*) FROM kg_alias WHERE table_name='public_funds' AND column_name='rptt_ksd_itm_no'), COUNT(DISTINCT trim(rptt_ksd_itm_no)) {F} WHERE NOT ({dummy_sql.replace('C', 'rptt_ksd_itm_no')}) AND NOT ({mal.replace('C', 'rptt_ksd_itm_no')})", (6867, 6867))
chk("KG-fake", "Fund alias 중 더미·길이이탈 값 0 (가짜 노드 재검)",
    f"SELECT SUM(({dummy_sql.replace('C', 'raw_value')}) OR ({mal.replace('C', 'raw_value')})) FROM kg_alias WHERE table_name='public_funds' AND column_name='rptt_ksd_itm_no'", 0)
chk("KG-sent", "센티넬 Organization 노드 부재 (99999999 · 00000000)",
    "SELECT COUNT(*) FROM kg_node WHERE node_id IN ('Org_fund_99999999','Org_trustee_99999999','Org_trustee_00000000','Org_99999999')", 0)
chk("KG-mgr", "운용사 노드 label 결손 — Org_ 노드 중 label_ko 없는 것",
    "SELECT COUNT(*) FROM kg_node n WHERE node_type='Organization' AND EXISTS (SELECT 1 FROM kg_alias a WHERE a.node_id=n.node_id AND a.column_name='or_co_xtn_itt_cd') AND (label_ko IS NULL OR label_ko='')", 0)
chk("KG-mirae", "Org_00080008 label 미래에셋(코드북 약칭), 펀드 alias 1 + ETF alias ≥ 40",
    "SELECT (SELECT label_ko FROM kg_node WHERE node_id='Org_00080008'), SUM(table_name='public_funds'), SUM(table_name='domestic_etfs') >= 40 FROM kg_alias WHERE node_id='Org_00080008'", ("미래에셋", 1, 1))
chk("KG-mother", "MotherFund 717 · feedsInto 1,704 · ext_fund_page 모펀드명 보유 행",
    "SELECT (SELECT COUNT(*) FROM kg_node WHERE node_id LIKE 'MotherFund_%'), (SELECT COUNT(*) FROM kg_edge WHERE predicate='feedsInto'), (SELECT COUNT(*) FROM ext_fund_page WHERE mother_fund_names_raw IS NOT NULL AND mother_fund_names_raw<>'') > 0", (717, 1704, 1))
chk("KG-risk", "RiskGrade alias 가 value_variants 표기('높은위험'·'보통위험')를 포함",
    "SELECT SUM(raw_value='높은위험'), SUM(raw_value='보통위험') FROM kg_alias WHERE table_name='public_funds' AND column_name='zrin_fd_ivst_risk_grd_nm'", (1, 1))

# ── 출력 ────────────────────────────────────────────────────────────────────
bad = [r for r in results if not r[4]]
print(f"공모펀드 DB↔yaml↔KG 대조 — 총 {len(results)}건 검사 · 불일치 {len(bad)}건\n")
print("=== 불일치 ===")
for id_, claim, exp, got, _ in bad:
    print(f"[{id_}] {claim}\n    yaml/기대={exp}\n    DB/실측  ={got}")
print("\n=== 일치 (id 만) ===")
print(", ".join(r[0] for r in results if r[4]))
