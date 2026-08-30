# -*- coding: utf-8 -*-
"""국내·해외 ETF — DB ↔ yaml ↔ KG 삼각 대조. yaml 의 수치 주장·규칙 조건식·KG alias 를 2차 DB 로 재현하고 불일치만 앞에 모은다.

실행: python scripts/audit_etf_claims.py     (audit_bonds_claims.py · audit_funds_claims.py 와 같은 형식)
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
YD = yaml.safe_load(io.open(ROOT / "ontology/enums/domestic_etfs.yaml", encoding="utf-8"))
YO = yaml.safe_load(io.open(ROOT / "ontology/enums/overseas_etfs.yaml", encoding="utf-8"))
COLS = {t: {r[1] for r in c.execute(f"pragma table_info({t})")} for t in ("domestic_etfs", "overseas_etfs")}
EXT_COLS = {r[1] for t in ("ext_etf_holdings", "ext_ovs_etf_holdings") for r in c.execute(f"pragma table_info({t})")}
results = []


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


def runnable(id_, claim, sql):
    try:
        c.execute(sql).fetchone()
        results.append((id_, claim, "실행됨", "실행됨", True))
    except Exception as e:  # noqa: BLE001
        results.append((id_, claim, "실행됨", f"ERR {e}", False))


D, O = "FROM domestic_etfs", "FROM overseas_etfs"

# ── 국내ETF ────────────────────────────────────────────────────────────────
chk("D-RG-1", "1,780행 = pd_itm_no 유일 · ETF 1,235 · ETN 545", f"SELECT COUNT(*), COUNT(DISTINCT pd_itm_no), SUM(pd_grp_no='ETF'), SUM(pd_grp_no='ETN') {D}", (1780, 1780, 1235, 545))
chk("D-buy", "구매가능(상폐 제외·판매중) ETF 1,160 · ETN 374", f"SELECT SUM(pd_grp_no='ETF'), SUM(pd_grp_no='ETN') {D} WHERE pd_lste_dt = 99991231 AND pd_sale_yn = 1", (1160, 374))
chk("D-fee", "보수유효 cu_charge_rt > 0 = 67", f"SELECT SUM(cu_charge_rt > 0) {D}", 67)
chk("D-sent", "-100 센티넬 1d 1 · 1m 16 · 3m 45 · 6m 66 · ytd 69 · 1y 110",
    f"SELECT SUM(du_er_1d=-100), SUM(du_er_1m=-100), SUM(du_er_3m=-100), SUM(du_er_6m=-100), SUM(du_er_ytd=-100), SUM(du_er_1y=-100) {D}", (1, 16, 45, 66, 69, 110))
chk("D-sent-2", "1y -100 110건 전건 du_clpr=0", f"SELECT SUM(du_er_1y=-100 AND du_clpr<>0) {D}", 0)
chk("D-clpr", "종가 0 = 192 (ETF 58 · ETN 134)", f"SELECT SUM(du_clpr=0), SUM(du_clpr=0 AND pd_grp_no='ETF'), SUM(du_clpr=0 AND pd_grp_no='ETN') {D}", (192, 58, 134))
for col in ["cu_charge_etc_rt", "pd_dvid_inc_dist", "fn_average_maturity", "fn_effective_duration", "fn_modified_duration"]:
    chk(f"D-zero-{col}", f"전부0컬럼금지 {col} — 유효(non-null·≠0) 0건", f"SELECT SUM({col} IS NOT NULL AND {col} <> 0) {D}", 0)
chk("D-div", "월분배 pd_dvid_cycl='M' 196", f"SELECT SUM(pd_dvid_cycl='M') {D}", 196)
chk("D-strat", "cu_strtegy 'C' 422 (전부 ETN)", f"SELECT SUM(cu_strtegy='C'), SUM(cu_strtegy='C' AND pd_grp_no<>'ETN') {D}", (422, 0))
chk("D-pad", "pd_dvid_cycl 공백 패딩 422 (ETN)", f"SELECT SUM(pd_dvid_cycl IS NOT NULL AND trim(pd_dvid_cycl)='' ) {D}", 422)
chk("D-inv", "상품명 '인버스' 225 (ETF 46 · ETN 179) · 그중 배수 음수 22 · 음수인데 이름 없음 1",
    f"SELECT SUM(pd_abrv_nm LIKE '%인버스%'), SUM(pd_abrv_nm LIKE '%인버스%' AND pd_grp_no='ETF'), SUM(pd_abrv_nm LIKE '%인버스%' AND pd_grp_no='ETN'), SUM(cu_lev_fector<0 AND pd_abrv_nm LIKE '%인버스%'), SUM(cu_lev_fector<0 AND pd_abrv_nm NOT LIKE '%인버스%') {D}", (225, 46, 179, 22, 1))
chk("D-lev", "cu_lev_fector 유효 1,598 (ETF 1,176 · ETN 422) · NULL 182",
    f"SELECT SUM(cu_lev_fector IS NOT NULL), SUM(cu_lev_fector IS NOT NULL AND pd_grp_no='ETF'), SUM(cu_lev_fector IS NOT NULL AND pd_grp_no='ETN'), SUM(cu_lev_fector IS NULL) {D}", (1598, 1176, 422, 182))
chk("D-lev-2", "레버리지 배수 신뢰 근거 — 이름 '2X'/'레버리지' 이고 |배수|≥2 인 314행 = |값|2 305 + |값|3 9 (derivation_rules.leverage_multiple)",
    f"SELECT COUNT(*), SUM(ABS(cu_lev_fector)=2), SUM(ABS(cu_lev_fector)=3) {D} WHERE ABS(cu_lev_fector)>=2 AND (pd_abrv_nm LIKE '%2X%' OR pd_abrv_nm LIKE '%레버리지%')", (314, 305, 9))
chk("D-join", "ext_etf_holdings: etf_code distinct 1,160 · 판매중 ETF 1,160 전건 커버 · as_of 단일 2026-08-21",
    f"SELECT (SELECT COUNT(DISTINCT etf_code) FROM ext_etf_holdings), (SELECT COUNT(*) {D} d WHERE pd_grp_no='ETF' AND pd_lste_dt=99991231 AND pd_sale_yn=1 AND NOT EXISTS (SELECT 1 FROM ext_etf_holdings h WHERE h.etf_code=d.pd_itm_no)), (SELECT COUNT(DISTINCT as_of) FROM ext_etf_holdings)", (1160, 0, 1))
chk("D-join-2", "ext_etf_holdings 75,859행", "SELECT COUNT(*) FROM ext_etf_holdings", 75859)

# ── 해외ETF ────────────────────────────────────────────────────────────────
chk("O-RG-1", "6,037행 = pd_itm_no 유일 · ISIN distinct 5,962 · ISIN NULL 12", f"SELECT COUNT(*), COUNT(DISTINCT pd_itm_no), COUNT(DISTINCT pd_isin_cd), SUM(pd_isin_cd IS NULL) {O}", (6037, 6037, 5962, 12))
chk("O-RG-2", "ISIN 63종이 2상품에 걸림 · lipper 63종", f"SELECT (SELECT COUNT(*) FROM (SELECT pd_isin_cd {O} WHERE pd_isin_cd IS NOT NULL GROUP BY 1 HAVING COUNT(*)=2)), (SELECT COUNT(*) FROM (SELECT pd_lipper_id {O} WHERE pd_lipper_id IS NOT NULL GROUP BY 1 HAVING COUNT(*)=2))", (63, 63))
chk("O-date", "du_clpr_base_dt 20260821 = 5,687 · 20260609 14 · 20260728 13", f"SELECT SUM(du_clpr_base_dt=20260821), SUM(du_clpr_base_dt=20260609), SUM(du_clpr_base_dt=20260728) {O}", (5687, 14, 13))
chk("O-const-1", "상수 — pd_sale_yn 유효 6,023 전부 1 · pd_tr_yn 전부 0", f"SELECT SUM(pd_sale_yn IS NOT NULL), SUM(pd_sale_yn=1), SUM(pd_tr_yn=0) {O}", (6023, 6023, 6023))
chk("O-const-2", "상수 — pd_trd_ccy 전부 USD · pd_mkt_id 전부 US", f"SELECT SUM(pd_trd_ccy<>'USD'), SUM(pd_mkt_id<>'US') {O}", (0, 0))
chk("O-const-3", "pd_lst_price 0 = 6,022 · cu_index_tracking_yn 유효 2,407 전부 Y", f"SELECT SUM(pd_lst_price=0), SUM(cu_index_tracking_yn IS NOT NULL), SUM(cu_index_tracking_yn='Y') {O}", (6022, 2407, 2407))
chk("O-repl", "cu_index_repl_mthd Optimized 1,826 · Swap 297 · Full 278 · Other 6", f"SELECT SUM(cu_index_repl_mthd='Optimized'), SUM(cu_index_repl_mthd='Swap'), SUM(cu_index_repl_mthd='Full'), SUM(cu_index_repl_mthd='Other') {O}", (1826, 297, 278, 6))
chk("O-zero", "zero_is_missing — cu_charge_rt 0: 419 · du_last_aum 0: 11 · pd_lstg_dt 0: 11", f"SELECT SUM(cu_charge_rt=0), SUM(du_last_aum=0), SUM(pd_lstg_dt=0) {O}", (419, 11, 11))
chk("O-lev", "cu_lev_fector NULL 5,136", f"SELECT SUM(cu_lev_fector IS NULL) {O}", 5136)
inv_rule = str(YO["query_rules"]["인버스숏"]).strip()
chk("O-inv", "인버스숏 규칙 = 191 (플래그 Y 183 포함, 누락 0)", f"SELECT SUM({inv_rule}), SUM(cu_inverse_short_yn='Y'), SUM(cu_inverse_short_yn='Y' AND NOT ({inv_rule})) {O}", (191, 183, 0))
chk("O-join", "티커 조인 1,358 상품 · 오배정 위험 base 티커 2행: JEMA·SHV 만",
    f"SELECT (SELECT COUNT(DISTINCT pd_itm_no) {O} o JOIN ext_ovs_etf_holdings h ON h.etf_ticker = replace(replace(o.pd_itm_no,'.K',''),'.O','')), (SELECT group_concat(b) FROM (SELECT replace(replace(pd_itm_no,'.K',''),'.O','') b {O} GROUP BY 1 HAVING COUNT(*)=2 AND EXISTS (SELECT 1 FROM ext_ovs_etf_holdings h WHERE h.etf_ticker=b) ORDER BY 1))", (1358, "JEMA,SHV"))
chk("O-join-2", "misassigned_if_isin 8 티커 전부 마스터에 존재", f"SELECT COUNT(*) {O} WHERE pd_itm_no IN ('CCMG.K','STXF.K','SIXG.O','GSWO.K','FILL.K','FIBR.K','IEQ','SPLG.K')", 8)
chk("O-join-3", "ext_ovs_etf_holdings 906,848행 · report_date 최빈 2026-04-30 463 ETF · 2026-05-31 404",
    "SELECT COUNT(*), (SELECT COUNT(DISTINCT etf_ticker) FROM ext_ovs_etf_holdings WHERE report_date='2026-04-30'), (SELECT COUNT(DISTINCT etf_ticker) FROM ext_ovs_etf_holdings WHERE report_date='2026-05-31') FROM ext_ovs_etf_holdings", (906848, 463, 404))

# ── query_rules 조건식 실행 · 참조 컬럼 실존 ───────────────────────────────
for dom, Yx, tbl in (("D", YD, "domestic_etfs"), ("O", YO, "overseas_etfs")):
    for name, rule in Yx["query_rules"].items():
        if not isinstance(rule, str) or "<" in rule or "{" in rule or "↔" in rule or "#" in rule.split("\n")[0] and "=" not in rule:
            continue
        cond = rule.split("#")[0].strip()
        if not re.search(r"[=<>]|LIKE|IN \(", cond) or "…" in cond or "—" in cond:
            continue
        runnable(f"{dom}-QR-{name}", f"{tbl} query_rules.{name} 조건식 실행 가능", f"SELECT COUNT(*) FROM {tbl} WHERE {cond} LIMIT 1")
    text = "\n".join(str(v) for v in Yx["query_rules"].values())
    toks = set(re.findall(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", text))
    known = COLS[tbl] | EXT_COLS | {"pd_itm_no", "fx_rate", "zero_is_value", "asset_manager", "fund_mgmt_co", "public_funds"}
    unknown = sorted(t for t in toks if t not in known and not re.fullmatch(r"du_er_\w+|inverse_direction|leverage_multiple|derivation_rules|normalization|zero_is_value_columns|ref_fund_mgmt_co", t))
    results.append((f"{dom}-QR-cols", f"{tbl} query_rules 가 가리키는 컬럼 실존", "미실존 0", unknown or 0, not unknown))

# ── KG ↔ DB ────────────────────────────────────────────────────────────────
for tbl in ("domestic_etfs", "overseas_etfs"):
    dead = []
    for (col,) in c.execute("SELECT DISTINCT column_name FROM kg_alias WHERE table_name=?", (tbl,)):
        if col not in COLS[tbl]:
            dead.append((col, "컬럼 없음")); continue
        n = c.execute(f"SELECT COUNT(*) FROM kg_alias a WHERE a.table_name=? AND a.column_name=? AND NOT EXISTS (SELECT 1 FROM {tbl} p WHERE trim(CAST(p.{col} AS TEXT))=a.raw_value)", (tbl, col)).fetchone()[0]
        if n:
            dead.append((col, n))
    results.append((f"KG-dead-{tbl}", f"kg_alias({tbl}) raw_value 가 DB 에 실재", "사어 0", dead or 0, not dead))
PLACEHOLDERS = {".", "Index is not available on Lipper Database"}
# shared/region.yaml 에 status: pending 으로 선언만 된 alias — 빌드가 건너뛴다 (리드 결정 대기). 미부착이 아니라 보류로 센다
YR = yaml.safe_load(io.open(ROOT / "ontology/shared/region.yaml", encoding="utf-8"))
PENDING = {(al["table"], al["column"], al["raw"]) for n in (YR.get("nodes") or {}).values() for al in (n.get("aliases") or []) if isinstance(al, dict) and al.get("status") == "pending"}
cov = []; pend = []
for tbl, col in [("domestic_etfs", "cu_fund_mgmt_co"), ("domestic_etfs", "ref_base_index"), ("domestic_etfs", "wu_inv_rgn"), ("domestic_etfs", "wu_inv_ast_type"), ("domestic_etfs", "pd_risk_cd"),
                 ("overseas_etfs", "cu_fund_mgmt_co"), ("overseas_etfs", "cu_base_index"), ("overseas_etfs", "wu_inv_rgn"), ("overseas_etfs", "wu_inv_ast_type")]:
    rows = [r[0] for r in c.execute(f"SELECT DISTINCT trim(CAST({col} AS TEXT)) FROM {tbl} WHERE {col} IS NOT NULL AND trim(CAST({col} AS TEXT))<>'' AND trim(CAST({col} AS TEXT)) NOT IN (SELECT raw_value FROM kg_alias WHERE table_name=? AND column_name=?)", (tbl, col))]
    rows = [r for r in rows if r not in PLACEHOLDERS and "not provided" not in r.lower() and "not available" not in r.lower()]
    pend += [(tbl, col, r) for r in rows if (tbl, col, r) in PENDING]
    rows = [r for r in rows if (tbl, col, r) not in PENDING]
    if rows:
        cov.append((tbl, col, len(rows), rows[:3]))
results.append(("KG-cov", "마스터 범주값이 KG alias 에 붙어 있는가 (플레이스홀더·pending 제외 · 9컬럼)", "미부착 0", cov or 0, not cov))
results.append(("KG-pend", "region.yaml status: pending 으로 보류된 alias (리드 결정 대기 — 결함 아님)", "보류 목록", pend, True))
chk("KG-sec-d", "국내 구성종목 rank≤50 티커 전부 Security 노드 (미부착 0)",
    "SELECT COUNT(*) FROM (SELECT DISTINCT ticker FROM ext_etf_holdings WHERE rank<=50) WHERE ticker NOT IN (SELECT raw_value FROM kg_alias WHERE table_name='ext_etf_holdings' AND column_name='ticker')", 0)
chk("KG-sec-o", "해외 구성종목 rank≤50 CUSIP 미부착 = 더미 '000000000' + 이름 없는 6건뿐",
    "SELECT COUNT(*), SUM(cusip='000000000') FROM (SELECT DISTINCT cusip FROM ext_ovs_etf_holdings WHERE rank<=50 AND cusip IS NOT NULL AND cusip<>'') WHERE cusip NOT IN (SELECT raw_value FROM kg_alias WHERE table_name='ext_ovs_etf_holdings' AND column_name='cusip')", (7, 1))
chk("KG-idx", "Idx_KOSPI200 이 국내ETF·펀드 양쪽 alias 를 가짐 (교차 재료)",
    "SELECT SUM(table_name='domestic_etfs')>0, SUM(table_name='public_funds')>0 FROM kg_alias WHERE node_id='Idx_KOSPI200'", (1, 1))
chk("KG-mirae", "Org_00080008 국내ETF alias ≥ 40 (미래에셋·TIGER 표기 변형)", "SELECT COUNT(*) >= 40 FROM kg_alias WHERE node_id='Org_00080008' AND table_name='domestic_etfs'", 1)

bad = [r for r in results if not r[4]]
print(f"ETF(국내·해외) DB↔yaml↔KG 대조 — 총 {len(results)}건 검사 · 불일치 {len(bad)}건\n")
print("=== 불일치 ===")
for id_, claim, exp, got, _ in bad:
    print(f"[{id_}] {claim}\n    yaml/기대={exp}\n    DB/실측  ={got}")
print("\n=== 일치 (id 만) ===")
print(", ".join(r[0] for r in results if r[4]))
