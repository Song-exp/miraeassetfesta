# -*- coding: utf-8 -*-
"""제안서용 수치 단일 출처 생성 — docs/proposal/NUMBERS.md

제안서 문서마다 수치를 따로 적으면 데이터가 바뀔 때 어긋난다(8/25 초안이 실제로 그랬다).
이 스크립트가 DB 실측으로 표를 다시 찍고, 문서는 여기만 인용한다.

사용: python scripts/gen_proposal_numbers.py
"""
import os, sqlite3, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "financial_products.db")
OUT = os.path.join(ROOT, "docs", "proposal", "NUMBERS.md")

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
q = lambda s: con.execute(s).fetchone()


def rows(t):
    return con.execute(f"select count(*) from {t}").fetchone()[0]


build = con.execute("select table_name, source_file, row_count, col_count, data_version, as_of from build_info").fetchall()
L = []
L.append("# 📊 제안서 수치 — 단일 출처 (GENERATED)")
L.append("")
L.append("> `python scripts/gen_proposal_numbers.py` 로 재생성. **제안서 문서는 이 파일만 인용한다.**")
L.append("> 문서마다 수치를 따로 적으면 데이터 갱신 때 어긋난다 — 8/25 초안이 실제로 그렇게 낡았다.")
L.append(f"> 생성 시각 기준 DB: `{os.path.basename(DB)}`")
L.append("")

L.append("## 1. 마스터 (주최 제공)")
L.append("")
L.append("| 테이블 | 소스 파일 | 행 | 컬럼 | 버전 | 기준일 |")
L.append("| :-- | :-- | --: | --: | :-- | :-- |")
tot = 0
for t, src, n, c, v, a in build:
    tot += n
    L.append(f"| `{t}` | {src} | {n:,} | {c} | {v} | {a} |")
L.append(f"| **합계** | | **{tot:,}** | | | |")
L.append("")

L.append("### 상품군 구성")
L.append("")
for t in ("domestic_etfs", "overseas_etfs"):
    d = dict(con.execute(f"select trim(pd_grp_no), count(*) from {t} group by 1").fetchall())
    L.append(f"- `{t}`: " + " · ".join(f"{k} {v:,}" for k, v in sorted(d.items())))
L.append("")

L.append("### 공모펀드 기본모수 · 식별 키")
L.append("")
# 🔴 세 문서(06 §A·§B·§E, 09)가 같은 값을 인용한다 — 손으로 적으면 어긋난다(8/25 초안 fss 11,611 이 실제로 그랬다).
BASE = "sale_yn='판매중' AND prvo_pbff_desc='공모'"
# 펀드단위 정본식 = enums/public_funds.yaml query_rules.펀드단위 와 같은 식이어야 한다
FKEY = ("COALESCE(CASE WHEN length(trim(mtco_itm_no))>=7 THEN trim(mtco_itm_no) "
        "ELSE substr('0000000'||trim(mtco_itm_no),-7) END, itm_no)")
DUMMY = ("({0} IS NULL OR trim({0})='' OR replace(replace(trim({0}),'KR',''),'0','')='' "
         "OR (length(trim({0}))>1 AND replace(trim({0}), substr(trim({0}),1,1), '')=''))")
pf = lambda w: q(f"select count(*) from public_funds where {w}")[0]
fk = lambda w: q(f"select count(*) from (select distinct or_co_xtn_itt_cd, {FKEY} from public_funds where {w})")[0]
n_pf = rows("public_funds")
L.append("| 항목 | 값 |")
L.append("| :-- | --: |")
L.append(f"| 전체 행 (= 클래스) | {n_pf:,} |")
L.append(f"| 사모 행 | {pf("prvo_pbff_desc='사모'"):,} |")
L.append(f"| 판매중 행 | {pf("sale_yn='판매중'"):,} |")
L.append(f"| **기본모수 행** (판매중 AND 공모) | **{pf(BASE):,}** |")
L.append(f"| **기본모수 펀드** (펀드단위 키) | **{fk(BASE):,}** |")
L.append(f"| 펀드단위 키 distinct — 전체 (더미 제외) | {fk('NOT ' + DUMMY.format('mtco_itm_no')):,} |")
L.append(f"| 펀드단위 키 distinct — 판매중 (더미 제외) | {fk("sale_yn='판매중' AND NOT " + DUMMY.format('mtco_itm_no')):,} |")
L.append(f"| 위험등급 미수록 (NULL ≠ 0등급) | {pf('zrin_fd_ivst_risk_gcd IS NULL'):,} |")
L.append("")
L.append("**식별 코드 더미** — `NULL` 만 결측으로 보면 틀린다. 조인·개체 키에서 제외하는 행:")
L.append("")
L.append("| 컬럼 | 더미 행 | 비율 |")
L.append("| :-- | --: | --: |")
for col in ("fss_itm_no", "kofia_fd_ccd", "rptt_ksd_itm_no", "std_itm_no", "ksd_itm_no", "mtco_itm_no"):
    d = pf(DUMMY.format(col))
    L.append(f"| `{col}` | {d:,} | {d/n_pf*100:.1f}% |")
L.append("")
# mtco 단독 조인이 남의 운용사 펀드에 붙는 비율 — 자기조인은 느려서 집계식으로 센다
_g = con.execute(f"select {FKEY} k, or_co_xtn_itt_cd o, count(*) n from public_funds "
                 f"where NOT {DUMMY.format('mtco_itm_no')} group by 1,2").fetchall()
_t = {}
for k, o, n in _g:
    _t[k] = _t.get(k, 0) + n
_all = sum(v * v for v in _t.values())
_same = sum(n * n for _, _, n in _g)
_span = sum(1 for k in _t if sum(1 for a, b, _c in _g if a == k) > 1)
L.append(f"> `mtco_itm_no` **단독 조인 금지** — 펀드단위 키 기준 {_all:,}쌍 중 **{_all-_same:,}쌍({(_all-_same)/_all*100:.1f}%)** 이 다른 운용사의 펀드에 붙는다 "
         f"(2개 이상 운용사에 걸친 값 {_span:,}종). 키는 `(or_co_xtn_itt_cd, mtco_itm_no)` 복합키다.")
L.append("")

L.append("## 2. 외부 수집 (L2)")
L.append("")
L.append("| 수집물 | 행 | 커버리지 | 기준일 |")
L.append("| :-- | --: | :-- | :-- |")

n_dom = rows("ext_etf_holdings")
etf_dom = q("select count(distinct etf_code) from ext_etf_holdings")[0]
etf_tot = q("select count(*) from domestic_etfs where trim(pd_grp_no)='ETF'")[0]
as_of_dom = q("select min(as_of), max(as_of) from ext_etf_holdings")
dom_as = as_of_dom[0] if as_of_dom[0] == as_of_dom[1] else f"{as_of_dom[0]}~{as_of_dom[1]}"
L.append(f"| 국내 ETF 구성종목 | {n_dom:,} | ETF {etf_dom:,}/{etf_tot:,} ({etf_dom/etf_tot*100:.1f}%) | {dom_as} |")

n_ovs = rows("ext_ovs_etf_holdings")
etf_ovs = q("select count(distinct etf_ticker) from ext_ovs_etf_holdings")[0]
ovs_tot = q("select count(*) from overseas_etfs where trim(pd_grp_no)='ETF'")[0]
rd = q("select min(report_date), max(report_date), count(distinct report_date) from ext_ovs_etf_holdings")
L.append(f"| 해외 ETF 구성종목 | {n_ovs:,} | ETF {etf_ovs:,}/{ovs_tot:,} ({etf_ovs/ovs_tot*100:.1f}%) | {rd[0]}~{rd[1]} ({rd[2]}종) |")

n_fh = rows("ext_fund_holdings")
n_fp = rows("ext_fund_page")
L.append(f"| 펀드 구성종목 | {n_fh:,} | — | 행별 `bas_dt` |")
L.append(f"| 펀드 웹 페이지 | {n_fp:,} | — | — |")
L.append("")
L.append(f"> 🔴 해외 구성종목 보고기준일이 **{rd[0]}~{rd[1]} 로 {rd[2]}종** — 최대 8개월 시차. 답변에 `report_date` 병기 필수.")
L.append("")

L.append("## 3. 온톨로지 · 지식그래프")
L.append("")
L.append("| 항목 | 값 |")
L.append("| :-- | --: |")
for t in ("kg_node", "kg_alias", "kg_edge", "kg_closure"):
    L.append(f"| `{t}` | {rows(t):,} |")
L.append("")
L.append("### 개체 종류별 노드")
L.append("")
L.append("| 개체 | 노드 수 |")
L.append("| :-- | --: |")
for nt, n in con.execute("select node_type, count(*) c from kg_node group by 1 order by c desc"):
    L.append(f"| {nt} | {n:,} |")
L.append("")
mf = q("select count(*) from kg_node where node_type='Fund' and node_id like 'MotherFund_%'")[0]
fd = q("select count(*) from kg_node where node_type='Fund'")[0]
L.append(f"> KG `Fund` {fd:,} = `rptt_ksd_itm_no` 묶음 {fd-mf:,} + 마스터 밖 MotherFund {mf:,}. "
         "🔴 펀드단위 집계 키 `(or_co_xtn_itt_cd, mtco_itm_no)` 와는 **다른 축**이다 — 집계·순자산은 복합키, 개체 조회는 rptt.")
L.append("")
ttl_files = ["common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"]
L.append("### 제출 ttl 5분할 (규격 p.9)")
L.append("")
L.append("| 파일 | 줄 |")
L.append("| :-- | --: |")
for f in ttl_files:
    p = os.path.join(ROOT, "ontology", f)
    n = sum(1 for _ in open(p, encoding="utf-8")) if os.path.exists(p) else 0
    L.append(f"| `ontology/{f}` | {n:,} |")
L.append("")

L.append("## 4. 평가셋")
L.append("")
import glob, json
tot_q = ver = 0
for p in sorted(glob.glob(os.path.join(ROOT, "eval", "questions_*.jsonl"))):
    qs = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    v = sum(1 for x in qs if x.get("gold_verified"))
    tot_q += len(qs); ver += v
    L.append(f"- `{os.path.basename(p)}`: {len(qs)}문항 (사람 검증 {v})")
L.append("")
L.append(f"**합계 {tot_q}문항 · 사람 검증 {ver}건**")
L.append("")

with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(L) + "\n")
print(f"생성: {os.path.relpath(OUT, ROOT)} ({len(L)}줄)")
