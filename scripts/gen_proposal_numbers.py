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
n_prv = pf("prvo_pbff_desc='사모'")      # 3.11 호환: f-string 안 동일 따옴표 중첩 금지
n_onsale = pf("sale_yn='판매중'")
L.append(f"| 사모 행 | {n_prv:,} |")
L.append(f"| 판매중 행 | {n_onsale:,} |")
L.append(f"| **기본모수 행** (판매중 AND 공모) | **{pf(BASE):,}** |")
L.append(f"| **기본모수 펀드** (펀드단위 키) | **{fk(BASE):,}** |")
L.append(f"| 펀드단위 키 distinct — 전체 (더미 제외) | {fk('NOT ' + DUMMY.format('mtco_itm_no')):,} |")
fk_onsale = fk("sale_yn='판매중' AND NOT " + DUMMY.format("mtco_itm_no"))
L.append(f"| 펀드단위 키 distinct — 판매중 (더미 제외) | {fk_onsale:,} |")
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

L.append("### 국내채권 기본모수 · 등급 · 판정 컬럼")
L.append("")
# 🔴 04_도메인_채권.md §A·§B·§E 와 03_구성도(그림 B-1) 가 같은 값을 인용한다 — 템플릿에 1차 수치(결측 41.1%)가 남아 있던 사고(09-03) 재발 방지.
# 구매가능 정본식 = enums/domestic_bonds.yaml query_rules.구매가능 · 판정 기준일 8/24(리드 결정 09-02)
BUY = "curr_cd='KRW' AND mat_dt >= 20260824"
MAT = "mat_dt >= 20260824"
GRADE_AAm = "TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-')"
NOGRADE = "(crd_grd IS NULL OR TRIM(crd_grd)='')"
PERP = "(pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%')"
b = lambda w: q(f"select count(*) from domestic_bonds where {w}")[0]
bd = lambda w: q(f"select count(distinct pd_no) from domestic_bonds where {w}")[0]
n_b = rows("domestic_bonds")
n_bd = q("select count(distinct pd_no) from domestic_bonds")[0]
n_dup = q("select count(*) from (select pd_no from domestic_bonds group by pd_no having count(*)>=2)")[0]
n_nog = b(NOGRADE)
_mc = dict(con.execute(f"select trim(std_pd_mcls_nm), count(*) from domestic_bonds where {NOGRADE} group by 1").fetchall())
n_grades = q("select count(distinct trim(crd_grd)) from domestic_bonds where trim(crd_grd)<>''")[0]
n_r00, n_r16 = b("pd_risk_gcd='00'"), b("pd_risk_gcd='16'")
n_issuer = q("select count(distinct trim(pd_pbcm)) from domestic_bonds where trim(pd_pbcm)<>''")[0]
n_disc, n_disc_pos = b("bd_intp_tcd='할인채'"), b("bd_intp_tcd='할인채' AND srfc_irt>0")
L.append("| 항목 | 값 |")
L.append("| :-- | --: |")
L.append(f"| 전체 행 / 종목 (`pd_no` distinct) | {n_b:,} / {n_bd:,} |")
L.append(f"| 장내·장외 2~4행 중복 종목 | {n_dup:,} |")
L.append(f"| **구매가능 행 / 종목** (`{BUY}`) | **{b(BUY):,} / {bd(BUY):,}** |")
L.append(f"| 판정 기준일 경계 — 8/22·8/23 만기 종목 (모수 밖) / 8/24 당일 만기 (모수) | {bd('mat_dt IN (20260822,20260823)'):,} / {bd('mat_dt = 20260824'):,} |")
L.append(f"| **공식 예시 #1 모수** — 구매가능 AND AA- 이상 (종목) | **{bd(BUY + ' AND ' + GRADE_AAm):,}** |")
L.append(f"| 신용등급 결측 행 / 비율 | {n_nog:,} / {n_nog/n_b*100:.1f}% |")
L.append(f"| 신용등급 결측 분해 — 국공채(미부여) / 특수채 / 회사채(미수록) | {_mc.get('국공채',0):,} / {_mc.get('특수채',0):,} / {_mc.get('회사채',0):,} |")
L.append(f"| 신용등급 있는 행 (등급 조건 질의 모수 · yaml `answerable_n`) | {n_b-n_nog:,} |")
L.append(f"| 신용등급 표기 종수 (데이터 실재) | {n_grades} |")
L.append(f"| 위험등급 `'00'`(해당없음) 행 / 6등급 `'16'` 행 | {n_r00:,} / {n_r16:,} ({n_r16/n_b*100:.1f}%) |")
L.append(f"| 발행사 `pd_pbcm` distinct (TRIM) | {n_issuer:,} |")
KR_ROW, KRW_ROW = b("pd_ctry_cd='KR'"), b("curr_cd='KRW'")
L.append(f"| 발행국 KR / 통화 KRW 행 | {KR_ROW:,} / {KRW_ROW:,} |")
L.append(f"| 할인채 행 (`bd_intp_tcd`) / 그중 `srfc_irt`>0 | {n_disc:,} / {n_disc_pos:,} |")
L.append(f"| 영구채 행 / 종목 (종목명 신종·영구) | {b(PERP):,} / {bd(PERP):,} |")
n_r1, n_c0 = bd(MAT + " AND pd_risk_gcd='11'"), bd(MAT + " AND TRIM(crd_grd)='C0'")
L.append(f"| 되묻기 규모 — 구매가능 1등급 종목 / C0 종목 | {n_r1:,} / {n_c0:,} |")
L.append("")
L.append("> 신용등급 결측 41.1%·41.6% 는 **1차(7/11) 데이터** 수치다 — 2차는 위 값. 국공채는 등급 '미부여'(정상), 특수채·회사채 결측은 '미수록' 으로 말한다.")
L.append("")

# ── 결측 유형 표(2차) — 04 §A "결측 판정 프로세스" 가 인용. 1차 EDA 노트(docs/eda/domestic_bonds_notes.md §B.2) 의 7유형을
#    2차 데이터에서 재실측한 것. ④ 복구 가능(pd_evco_crd_grd 병합)은 2차에 그 컬럼이 없어 소멸 — 유형 자체가 줄어든 것이 재검증 증거.
_cols = {r[1] for r in con.execute("PRAGMA table_info(domestic_bonds)")}
n_gov = b("TRIM(std_pd_mcls_nm)='국공채'")
n_gov_nog = b(NOGRADE + " AND TRIM(std_pd_mcls_nm)='국공채'")
n_buy_null, n_buy_has = b("buy_yield IS NULL"), b("buy_yield IS NOT NULL")
n_bq_pos = b("buyable_quantity > 0")
n_dur_null, n_rd_null, n_matured = b("dur IS NULL"), b("remaining_days IS NULL"), b("mat_dt < 20260824")
n_tax0 = b("avg_annual_tax_yield IS NULL OR avg_annual_tax_yield = 0")
n_cur000, n_dur99, n_mat0 = b("curr_cd='000'"), b("dur >= 90"), b("mat_dt IS NULL OR mat_dt = 0")
n_dirty_nz = b("dirty IS NOT NULL AND dirty <> 0")
n_dirty_copy = b("dirty IS NOT NULL AND dirty <> 0 AND dirty = eval_price")
n_srfc0 = b("srfc_irt = 0")
L.append("#### 국내채권 결측 유형 표 (2차 재실측) — 1차 EDA 7유형 대비")
L.append("")
L.append("| # | 유형 | 2차 실측 | 1차 EDA(7/11) | 판정 · 선언 자리 |")
L.append("| :-: | :-- | :-- | :-- | :-- |")
L.append(f"| ① | 구조적 부재 — 국공채 신용등급 (해당없음) | 국공채 {n_gov:,}행 중 결측 {n_gov_nog:,} (완벽 대응) / 전체 결측 {n_nog:,} | 16,044 | `crd_grd.missing_reason: not_applicable` · `answer_policy` |")
L.append(f"| ①′ | 같은 컬럼의 미수록 — 특수채·회사채 등급 결측 | {_mc.get('특수채',0):,} + {_mc.get('회사채',0):,} = {_mc.get('특수채',0)+_mc.get('회사채',0):,} | (미분리) | 같은 NULL 을 '미수록' 으로 따로 답함 |")
L.append(f"| ② | 상태 표현 — 매수수익률 없음 = 지금 매물 아님 | `buy_yield` NULL {n_buy_null:,} / 있음 {n_buy_has:,} (`buyable_quantity`>0 {n_bq_pos:,}) | 41,513 / 881 | `buyable_quantity` 무효 · 규칙 `구매가능` 은 만기로 판정 |")
L.append(f"| ③ | 미산출 — 만기 경과분의 듀레이션·잔존일수 | `dur` NULL {n_dur_null:,} · `remaining_days` NULL {n_rd_null:,} · 만기 경과(<8/24) {n_matured:,} | 13,376 / 10,645 | 2차는 만기 도래분이 빠져 사실상 소멸 — 규칙 `듀레이션정상` |")
L.append(f"| ④ | 복구 가능 — 평가사 등급 컬럼 병합 | {'컬럼 없음 → 소멸' if 'pd_evco_crd_grd' not in _cols else '컬럼 실재'} | 1,600 | 2차 스키마에서 유형 소멸 |")
L.append(f"| ⑤ | 센티넬·위장 결측 | `avg_annual_tax_yield` 0·NULL {n_tax0:,}(전량) · `curr_cd`='000' {n_cur000:,} · `dur`≥90 {n_dur99:,} · `mat_dt` 0 {n_mat0:,} | 전량 0 · 99 · 99991231 | `zero_as_missing` 11컬럼 · 게이트 `curr_cd` 상수 · 규칙 `외화채없음` |")
L.append(f"| ⑥ | 복사 위장 — `dirty` = `eval_price` | {n_dirty_copy:,} / {n_dirty_nz:,} | 27,430 | 금지 컬럼 (조립기 숨김) |")
L.append(f"| ⑦ | 정상값 오해 — 비어 보이지만 값 | `srfc_irt`=0 {n_srfc0:,} (할인채·주식연계) · `pd_risk_gcd`='00' {n_r00:,} | 2,758 | 규칙 `무이자질의` · `range_by_table` 0~6 |")
L.append("")
L.append("> 1차 열은 `docs/eda/domestic_bonds_notes.md` §B.2 의 42,394행 기준 값(재실측 아님) — 비교용으로만 싣는다. 판정 순서: ⑦ 정상값인가 → ⑤⑥ 위장인가 → ④ 복구 가능한가 → ①②③ 어떤 부재인가.")
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
