# -*- coding: utf-8 -*-
"""온톨로지 규칙 검토 문서 — 규칙 1개당 파일 1개.

전수조사에서 나온 규칙이므로 **규칙 단위로 검토**할 수 있어야 한다. 파일마다:

  1. 요약 — 이 규칙이 무엇을 막는가
  2. 데이터가 이랬다 → 그래서 이렇게 정했다   (서술: 이 파일 안 RULES)
  3. **전수 인벤토리** — 이 규칙이 실제로 어디에 몇 개 선언돼 있나 (yaml 에서 추출)
  4. **근거(실측)** — 라이브 DB 질의 결과
  5. **검토 체크리스트** — 사람이 판정할 것
  6. **공백·불일치** — 규칙이 있어야 하는데 없는 곳

서술과 체크리스트만 사람이 쓰고, 목록·수치는 매번 yaml·DB 에서 새로 뽑는다.

출력: docs/ontology_rules/NN_<slug>.md + README.md
사용:
    python scripts/gen_ontology_rules_doc.py          # 12개 전부
    python scripts/gen_ontology_rules_doc.py 2 8      # 특정 규칙만
"""
from __future__ import annotations

import collections
import glob
import os
import sqlite3
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "financial_products.db"
OUT = ROOT / "docs" / "ontology_rules"
DOMAINS = ["domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"]
KO = {"domestic_bonds": "채권", "domestic_etfs": "국내ETF",
      "overseas_etfs": "해외ETF", "public_funds": "펀드"}

D: dict = {}   # 도메인 yaml
S: dict = {}   # shared 개체 yaml


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────
def clean(v, n: int = 500) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ").strip()[:n]


def qr_table(pred, note: str = "") -> list[str]:
    """query_rules 중 조건에 맞는 것을 도메인 횡단으로 전수 나열."""
    L = ["| 도메인 | 규칙 | 내용 |", "| :-- | :-- | :-- |"]
    n = 0
    for dom in DOMAINS:
        for k, v in (D[dom].get("query_rules") or {}).items():
            if pred(k, v):
                L.append(f"| {KO[dom]} | `{k}` | {clean(v)} |")
                n += 1
    if n == 0:
        return ["> (해당 규칙 없음)", ""]
    L.append("")
    if note:
        L += [note, ""]
    return L


def col_table(pred, cols: list[str]) -> list[str]:
    """columns.<컬럼> 중 조건에 맞는 것을 전수 나열. cols = 보여줄 필드."""
    head = ["도메인", "컬럼", "한글명"] + cols
    L = ["| " + " | ".join(head) + " |", "| " + " | ".join([":--"] * len(head)) + " |"]
    n = 0
    for dom in DOMAINS:
        for c, v in (D[dom].get("columns") or {}).items():
            if isinstance(v, dict) and pred(c, v):
                row = [KO[dom], f"`{c}`", clean(v.get("korean_name", ""), 30)]
                row += [clean(v.get(f, ""), 220) or "—" for f in cols]
                L.append("| " + " | ".join(row) + " |")
                n += 1
    if n == 0:
        return ["> (해당 컬럼 없음)", ""]
    L.append("")
    L.append(f"— 총 **{n}개 컬럼**")
    L.append("")
    return L


def run_table(con: sqlite3.Connection, sql: str) -> list[str]:
    try:
        cur = con.execute(sql)
    except sqlite3.Error as e:
        return [f"> ❌ 질의 실패: `{e}`", ""]
    names = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if not rows:
        return ["> (결과 없음)", ""]
    L = ["| " + " | ".join(str(c) for c in names) + " |",
         "| " + " | ".join("--:" if i else ":--" for i, _ in enumerate(names)) + " |"]
    for r in rows[:15]:
        L.append("| " + " | ".join(
            f"{v:,}" if isinstance(v, int) else ("—" if v is None else clean(v, 60))
            for v in r) + " |")
    if len(rows) > 15:
        L.append(f"| … | 총 {len(rows)}행 |")
    L.append("")
    return L


# ── 규칙별 전수 인벤토리 ─────────────────────────────────────────────────
def inv_naming(con):
    L = ["#### (1) `normalization` 의 지칭 정리 항목 — 도메인 전수", "",
         "| 도메인 | 항목 | 내용 |", "| :-- | :-- | :-- |"]
    keys = ("trim_columns", "grade_suffix", "issuer", "bd_knd_alias", "value_variants", "language_note")
    for dom in DOMAINS:
        nm = D[dom].get("normalization") or {}
        for k in keys:
            if k in nm:
                v = nm[k]
                desc = f"{len(v)}개 컬럼" if k == "trim_columns" and isinstance(v, list) else clean(v, 300)
                L.append(f"| {KO[dom]} | `{k}` | {desc} |")
    L += ["", "#### (2) `kg_alias` — 어느 테이블·컬럼이 개체로 이어져 있나", ""]
    L += run_table(con, "select table_name as 테이블, column_name as 컬럼, count(*) as alias수, "
                        "count(distinct node_id) as 노드수 from kg_alias group by 1,2 order by 3 desc limit 15")
    L += ["#### (3) 코드북 — 사람이 확정한 정본", ""]
    cb = sorted(glob.glob(str(ROOT / "ontology" / "codebooks" / "*.csv")))
    L += ["| 코드북 | 행 |", "| :-- | --: |"]
    for p in cb:
        n = sum(1 for _ in open(p, encoding="utf-8")) - 1
        L.append(f"| `{os.path.basename(p)}` | {n:,} |")
    L.append("")
    return L


def inv_missing(con):
    L = ["#### (1) `missing_reason` 분포 — 도메인 × 분류", ""]
    x = collections.defaultdict(collections.Counter)
    allr = collections.Counter()
    for dom in DOMAINS:
        for c, v in (D[dom].get("columns") or {}).items():
            if isinstance(v, dict):
                r = str(v.get("missing_reason"))
                x[dom][r] += 1
                allr[r] += 1
    reasons = [r for r, _ in allr.most_common()]
    L += ["| 도메인 | " + " | ".join(f"`{r}`" for r in reasons) + " | 계 |",
          "| :-- | " + " | ".join("--:" for _ in reasons) + " | --: |"]
    for dom in DOMAINS:
        tot = sum(x[dom].values())
        L.append(f"| {KO[dom]} | " + " | ".join(str(x[dom].get(r, 0)) for r in reasons) + f" | {tot} |")
    L.append("")
    extra = [r for r in reasons if r not in ("not_applicable", "missing", "present", "none", "mixed")]
    if extra:
        L += [f"> 🔴 **문서화된 4분류 밖의 값이 있다** — {', '.join('`'+r+'`' for r in extra)}. "
              "`None` 은 필드 자체가 비어 있는 것이고, 그 외는 정의되지 않은 분류다. "
              "답변 문장이 분류에서 나오므로 **분류 밖 값은 답변 규칙이 없는 상태**다.", ""]
    # mixed 인데 값별 분해가 없는 컬럼 = 답변이 애매해지는 지점
    mix = nomix = 0
    holes = []
    for dom in DOMAINS:
        for c, v in (D[dom].get("columns") or {}).items():
            if isinstance(v, dict) and str(v.get("missing_reason")) == "mixed":
                mix += 1
                if not v.get("missing_semantics"):
                    nomix += 1
                    holes.append(f"{KO[dom]}.`{c}`")
    L += [f"#### (2) `mixed` 판정 {mix}개 중 **값별 분해가 없는 것 {nomix}개**", "",
          "`mixed` 는 '행마다 이유가 다름' 이라는 선언이므로 `missing_semantics` 로 값별 분해가 있어야 "
          "답변 문장을 고를 수 있다. 분해가 없으면 **판정만 있고 답변 규칙은 없는 상태**다.", ""]
    if holes:
        L += [f"> 🔴 분해 없는 컬럼 {nomix}개 — {clean(', '.join(holes), 1200)}", ""]
    L += col_table(lambda c, v: str(v.get("missing_reason")) == "mixed" and v.get("missing_semantics"),
                   ["missing_semantics"])
    L += ["#### (3) 위장결측·센티넬 선언", ""]
    for dom in DOMAINS:
        nm = D[dom].get("normalization") or {}
        for k in ("dummy_as_missing", "invalid_values", "contaminated_rows", "zero_as_missing"):
            if k in nm:
                L.append(f"- **{KO[dom]}** `{k}` — {clean(nm[k], 420)}")
    L.append("")
    return L


def inv_external(con):
    L = ["#### (1) `ext_*` 4테이블 — 조인 커버리지 실측", ""]
    L += run_table(con, """
      select 'ext_etf_holdings' as 테이블, (select count(distinct etf_code) from ext_etf_holdings) as 수집키,
             (select count(distinct h.etf_code) from ext_etf_holdings h join domestic_etfs e on e.pd_itm_no=h.etf_code) as 마스터조인,
             (select count(*) from domestic_etfs where pd_grp_no='ETF') as 마스터전체
      union all select 'ext_ovs_etf_holdings', (select count(distinct etf_ticker) from ext_ovs_etf_holdings),
             (select count(distinct h.isin) from ext_ovs_etf_holdings h join overseas_etfs e on e.pd_isin_cd=h.isin),
             (select count(*) from overseas_etfs where pd_grp_no='ETF')
      union all select 'ext_fund_holdings', (select count(distinct grp) from ext_fund_holdings),
             (select count(distinct h.grp) from ext_fund_holdings h join public_funds p on p.mtco_itm_no=h.grp),
             (select count(distinct mtco_itm_no) from public_funds)
      union all select 'ext_fund_page', (select count(*) from ext_fund_page),
             (select count(*) from ext_fund_page e join public_funds p on p.itm_no=e.itm_no),
             (select count(*) from public_funds)""")
    L += ["#### (2) 외부 사실을 참조하는 도메인 선언", ""]
    for dom in DOMAINS:
        if D[dom].get("external_facts"):
            L.append(f"- **{KO[dom]}** `external_facts` — {clean(D[dom]['external_facts'], 400)}")
    L += ["", "#### (3) 적재하지 않기로 한 것 (의도적 배제)", "",
          "- `ext_fund_page` — 순자산·수익률 등 **시계열 값은 적재 제외**. 8/18 관측치라 기준일(8/22)과 어긋나 근거로 못 쓴다.",
          "- 적재 대상은 설정일·보수 분해·환매 규칙·모펀드명 등 **불변 또는 준정적 사실**만.", ""]
    return L


def inv_grain(con):
    L = ["#### (1) `row_grain` — 도메인 전수 (4/4 선언)", "",
         "| 도메인 | 행 하나가 무엇인가 |", "| :-- | :-- |"]
    for dom in DOMAINS:
        L.append(f"| {KO[dom]} | {clean(D[dom].get('row_grain', '—'), 400)} |")
    L += ["", "#### (2) grain 관련 query_rules — 전수", ""]
    L += qr_table(lambda k, v: any(w in k for w in ("대표행", "종목단위", "펀드단위", "집계", "시장집계")))
    L += ["#### (3) 실측 — 행과 개체가 얼마나 어긋나나", ""]
    L += run_table(con, """
      select '채권' as 도메인, count(*) as 행, count(distinct pd_no) as 개체키, count(*)-count(distinct pd_no) as 중복 from domestic_bonds
      union all select '국내ETF', count(*), count(distinct pd_itm_no), count(*)-count(distinct pd_itm_no) from domestic_etfs
      union all select '해외ETF', count(*), count(distinct pd_isin_cd), count(*)-count(distinct pd_isin_cd) from overseas_etfs
      union all select '펀드(클래스)', count(*), count(distinct itm_no), count(*)-count(distinct itm_no) from public_funds""")
    return L


def inv_population(con):
    L = ["#### (1) 모수 관련 query_rules — 전수", ""]
    L += qr_table(lambda k, v: any(w in k for w in ("모수", "만", "구매가능", "제외", "판매행")))
    L += ["#### (2) 각 모수 조건의 실제 행수", ""]
    L += run_table(con, """
      select '펀드 기본모수(판매중·공모)' as 조건, count(*) as 행 from public_funds where sale_yn='판매중' and prvo_pbff_desc='공모'
      union all select '펀드 사모(질의 대상 아님)', count(*) from public_funds where prvo_pbff_desc='사모'
      union all select '펀드 판매완료(평가컬럼 99% 결측)', count(*) from public_funds where sale_yn<>'판매중'
      union all select '국내 ETF만', count(*) from domestic_etfs where pd_grp_no='ETF'
      union all select '국내 ETN(혼입)', count(*) from domestic_etfs where pd_grp_no='ETN'
      union all select '채권 만기 미경과(구매가능)', count(*) from domestic_bonds where mat_dt >= 20260822
      union all select '채권 판매조건 수록', count(*) from domestic_bonds where buy_yield is not null""")
    return L


def inv_derivation(con):
    L = ["#### (1) 파생 규칙 — 전수 원문", ""]
    n = 0
    for dom in DOMAINS:
        for key in ("derivation_rules", "axis_derivation"):
            blk = D[dom].get(key)
            if not isinstance(blk, dict):
                continue
            for name, body in blk.items():
                if name.startswith("_"):
                    continue
                L.append(f"**{KO[dom]} · `{key}.{name}`**")
                L.append("")
                if isinstance(body, dict):
                    L += ["| 항목 | 내용 |", "| :-- | :-- |"]
                    for k2, v2 in body.items():
                        L.append(f"| {k2} | {clean(v2, 400)} |")
                else:
                    L.append(f"> {clean(body, 500)}")
                L.append("")
                n += 1
    L.append(f"— 총 **{n}개 파생 규칙**")
    L += ["", "#### (2) 실측 — 파생이 실제로 몇 건을 만들어내나", ""]
    L += run_table(con, """
      select '이름에 인버스' as 판정축, count(*) as n from domestic_etfs where pd_abrv_nm like '%인버스%'
      union all select '부호가 음수(신뢰 불가)', count(*) from domestic_etfs where cu_lev_fector<0
      union all select '레버리지 ABS>1', count(*) from domestic_etfs where abs(cu_lev_fector)>1
      union all select '펀드 재간접 후보(펀드구성비>0)', count(*) from public_funds where zrin_fd_cmst_rt>0
      union all select '펀드 총보수 산출 가능', count(*) from public_funds
        where sale_yn='판매중' and prvo_pbff_desc='공모' and or_co_rwrd_r is not null""")
    return L


def inv_disjoint(con):
    L = ["#### (1) 배타·분리 관련 규칙 — 전수", ""]
    L += qr_table(lambda k, v: any(w in k for w in ("분리", "금지", "만", "유효")) and
                  any(w in str(v) for w in ("분리", "나눠", "섞", "한 축", "group-by", "혼입")))
    L += ["#### (2) DisjointWith · 상품군 선언", ""]
    for dom in DOMAINS:
        pg = D[dom].get("product_group")
        if pg:
            L.append(f"- **{KO[dom]}** `product_group` — {clean(pg, 400)}")
    L.append("")
    L += ["#### (3) 실측 — 한 컬럼에 섞여 있는 종류들", ""]
    L += run_table(con, "select trim(bd_intp_tcd) as 이자유형, count(*) as n, round(min(srfc_irt),2) as 최소, "
                        "round(max(srfc_irt),2) as 최대, round(avg(srfc_irt),2) as 평균 "
                        "from domestic_bonds group by 1 order by 2 desc")
    L += run_table(con, "select pd_grp_no as 상품군, count(*) as n, "
                        "sum(case when ref_base_index is null or trim(ref_base_index)='' then 1 else 0 end) as 기초지수없음 "
                        "from domestic_etfs group by 1")
    return L


def inv_unit(con):
    L = ["#### (1) `unit` 선언 — 전수", ""]
    u = collections.defaultdict(list)
    for dom in DOMAINS:
        for c, v in (D[dom].get("columns") or {}).items():
            if isinstance(v, dict) and v.get("unit"):
                u[str(v["unit"])].append(f"{KO[dom]}.`{c}`")
    L += ["| 단위 표기 | 컬럼 수 | 컬럼 |", "| :-- | --: | :-- |"]
    for k, v in sorted(u.items(), key=lambda x: -len(x[1])):
        L.append(f"| `{clean(k, 60)}` | {len(v)} | {clean(', '.join(v[:8]), 300)}{' …' if len(v) > 8 else ''} |")
    L.append("")
    permil = [k for k in u if "‰" in k]
    if len(permil) > 1:
        L += [f"> 🔴 **같은 단위인데 표기가 {len(permil)}가지다** — {', '.join('`'+clean(k,50)+'`' for k in permil)}. "
              "기계가 단위로 묶으려면 표기를 하나로 통일해야 한다.", ""]
    fmt = [k for k in u if "yyyymmdd" in k.lower()]
    if fmt:
        L += [f"> 🟡 `{fmt[0]}` 는 **단위가 아니라 형식**이다. `unit` 과 `format` 을 분리할지 검토 필요.", ""]
    L += ["#### (2) 단위 관련 query_rules", ""]
    L += qr_table(lambda k, v: any(w in k for w in ("환율", "정렬")) or "환산" in str(v))
    L += ["#### (3) 실측 — ‰ 확정의 근거", ""]
    L += run_table(con, """
      select round(avg(p.or_co_rwrd_r+p.sale_co_rwrd_r+p.trusc_rwrd_r+p.ofwk_trus_rwrd_r),3) as 마스터_보수합계,
             round(avg(e.total_fee_pct),3) as 설명서_총보수_pct,
             round(avg(p.or_co_rwrd_r+p.sale_co_rwrd_r+p.trusc_rwrd_r+p.ofwk_trus_rwrd_r)/avg(e.total_fee_pct),2) as 배수,
             count(*) as 대조행
      from public_funds p join ext_fund_page e on e.itm_no=p.itm_no where e.total_fee_pct>0""")
    return L


def inv_forbid(con):
    L = ["#### (1) 금지 규칙 — 전수", ""]
    L += qr_table(lambda k, v: "금지" in k)
    L += ["#### (2) 답변 정책에 '금지' 가 들어간 컬럼 — 전수", ""]
    L += col_table(lambda c, v: "금지" in str(v.get("answer_policy", "")), ["answer_policy"])
    L += ["#### (3) 실측 — 정말 못 쓰는 컬럼인가", ""]
    L += run_table(con, """
      select 'domestic_bonds.avg_annual_tax_yield' as 컬럼,
             sum(case when avg_annual_tax_yield is not null then 1 else 0 end) as non_null,
             sum(case when avg_annual_tax_yield=0 then 1 else 0 end) as 값이_0 from domestic_bonds
      union all select 'public_funds.fd_wk1_ern_r',
             sum(case when fd_wk1_ern_r is not null then 1 else 0 end), 0 from public_funds
      union all select 'domestic_etfs.cu_charge_etc_rt',
             sum(case when cu_charge_etc_rt is not null then 1 else 0 end),
             sum(case when cu_charge_etc_rt=0 then 1 else 0 end) from domestic_etfs""")
    return L


def inv_absent(con):
    L = ["#### (1) `absent_in` — 개체별 부재 선언 전수", "",
         "> 컬럼이 **비어 있는 것**이 아니라 **아예 없는 것**. 게이트가 이걸 보고 HCX 호출 0회로 기각한다.", "",
         "| 개체 | 부재 도메인 | 사유 |", "| :-- | :-- | :-- |"]
    n = 0
    for name, doc in sorted(S.items()):
        for dom, why in (doc.get("absent_in") or {}).items():
            L.append(f"| `{doc.get('entity', name)}` | {KO.get(dom, dom)} | {clean(why, 300)} |")
            n += 1
    L += ["", f"— 총 **{n}건**", "",
          "#### (2) 실측 — 선언과 실제 스키마가 맞는가 (`build_ontology.py` V6 이 검사하는 것)", ""]
    L += run_table(con, """
      select '해외ETF 수익률 컬럼' as 확인, group_concat(name, ', ') as 실제컬럼
        from pragma_table_info('overseas_etfs') where name like 'du_er%'
      union all select '국내ETF 수익률 컬럼', group_concat(name, ', ')
        from pragma_table_info('domestic_etfs') where name like 'du_er%'
      union all select '해외ETF 위험등급 컬럼', coalesce(group_concat(name, ', '), '(없음 — 선언과 일치)')
        from pragma_table_info('overseas_etfs') where lower(name) like '%risk%'
      union all select '채권 기초지수 컬럼', coalesce(group_concat(name, ', '), '(없음 — 선언과 일치)')
        from pragma_table_info('domestic_bonds') where lower(name) like '%index%'""")
    return L


def inv_hierarchy(con):
    L = ["#### (1) 개체별 계층 선언 — 전수", "",
         "| 개체 | 노드 | `parent` 있는 노드 | 계층 |", "| :-- | --: | --: | :-- |"]
    for name, doc in sorted(S.items()):
        nodes = doc.get("nodes") or {}
        p = sum(1 for v in nodes.values() if isinstance(v, dict) and v.get("parent"))
        L.append(f"| `{doc.get('entity', name)}` | {len(nodes)} | {p} | {'✅ 있음' if p else '🔴 **없음**'} |")
    L += ["", "#### (2) 실측 — KG 에 올라간 계층", ""]
    L += run_table(con, "select node_type as 개체, count(*) as 노드수 from kg_node group by 1 order by 2 desc")
    L += run_table(con, "select count(*) as kg_closure_행, count(distinct ancestor_id) as 조상노드, "
                        "count(distinct descendant_id) as 자손노드 from kg_closure")
    return L


def inv_asof(con):
    L = ["#### (1) 기준일 관련 규칙 — 전수", ""]
    L += qr_table(lambda k, v: "기준일" in k or "기준일" in str(v)[:120])
    L += ["#### (2) 실측 — 테이블마다 기준일이 다르다", ""]
    L += run_table(con, "select table_name as 테이블, source_file as 원본, as_of as 대회기준일 from build_info")
    L += run_table(con, """
      select 'domestic_bonds.info_base_dt' as 컬럼, cast(min(info_base_dt) as text) as 최소, cast(max(info_base_dt) as text) as 최대 from domestic_bonds
      union all select 'ext_etf_holdings.as_of', min(as_of), max(as_of) from ext_etf_holdings
      union all select 'ext_ovs_etf_holdings.report_date', min(report_date), max(report_date) from ext_ovs_etf_holdings
      union all select 'ext_fund_holdings.bas_dt', min(bas_dt), max(bas_dt) from ext_fund_holdings
      union all select 'ext_fund_page.retrieved_at', min(retrieved_at), max(retrieved_at) from ext_fund_page""")
    return L


INV = {"1": inv_naming, "2": inv_missing, "3": inv_external, "4": inv_grain,
       "5": inv_population, "6": inv_derivation, "7": inv_disjoint, "8": inv_unit,
       "9": inv_forbid, "10": inv_absent, "11": inv_hierarchy, "12": inv_asof}


# ── 서술은 별도 모듈에 (heredoc·인용부호 충돌 회피 + 사람이 고칠 곳을 한곳으로) ──
sys.path.insert(0, str(Path(__file__).parent))
from _ontology_rules_data import RULES  # noqa: E402


def render_rule(r: dict, con: sqlite3.Connection) -> str:
    L = [f"# 규칙 {r['n']}. {r['name']} — {r['sub']}", "",
         f"> {r['gist']}", "",
         "> 🔴 생성물입니다. 서술·체크리스트는 `scripts/_ontology_rules_data.py`,",
         "> 목록·수치는 `scripts/gen_ontology_rules_doc.py` 가 yaml·DB 에서 매번 새로 뽑습니다.", "",
         "| | |", "| :-- | :-- |",
         f"| 목록 | [규칙 12종 색인](README.md) |",
         f"| 컬럼 단위 상세 | [`../data_dictionary/`](../data_dictionary/README.md) |", "",
         "---", "",
         "## 1. 데이터가 이랬다", ""]
    L += [f"- {d}" for d in r["defect"]]
    L += ["", "## 2. 그래서 이렇게 정했다", ""]
    L += [f"- {x}" for x in r["rule"]]
    L += ["", "## 3. 전수 인벤토리 — 이 규칙이 실제로 어디에 선언돼 있나", ""]
    L += INV[r["n"]](con)
    L += ["## 4. 근거 (라이브 DB 실측)", ""]
    for label, sql in r["ev"]:
        L.append(label if "**" in label else f"**{label}**")
        L.append("")
        L += run_table(con, sql)
    L += ["## 5. 안 지키면", "", r["risk"], "",
          "## 6. 검토 체크리스트", "",
          "> 전수조사에서 나온 규칙이므로 **규칙 단위로 판정**한다. 각 항목에 결론과 근거를 적고,",
          "> 판정이 바뀌면 `ontology/enums/*.yaml` 또는 `ontology/shared/*.yaml` 을 고친 뒤 재생성한다.", "",
          "| # | 검토 항목 | 판정 | 근거·조치 |", "| :-: | :-- | :-- | :-- |"]
    for i, c in enumerate(r["check"], 1):
        L.append(f"| {i} | {c} |  |  |")
    L += ["", "---", "",
          f"← [색인으로](README.md)", ""]
    return "\n".join(L)


def render_index(con: sqlite3.Connection) -> str:
    L = ["# 🧱 온톨로지 규칙 12종 — 규칙별 검토 문서", "",
         "> 전수조사에서 나온 규칙을 **규칙 하나당 문서 하나**로 갈라 두었다.",
         "> 문서마다 `데이터가 이랬다 → 그래서 이렇게 정했다 → 전수 인벤토리 → 실측 근거 → 안 지키면 → 검토 체크리스트`.",
         "> 3개 도메인(채권 · ETF · 펀드) 합본이며 외부 데이터(`ext_*`)를 포함한다.", "",
         "| # | 규칙 | 무엇을 막나 | 검토 항목 |", "| :-: | :-- | :-- | --: |"]
    for r in RULES:
        L.append(f"| {r['n']} | **[{r['name']}]({r['n'].zfill(2)}_{r['slug']}.md)** | {r['sub']} | {len(r['check'])} |")
    L += ["", f"— 검토 항목 총 **{sum(len(r['check']) for r in RULES)}개**", "",
          "## 이 문서들을 어떻게 쓰나", "",
          "| 목적 | 방법 |", "| :-- | :-- |",
          "| **검토** | 문서 §6 체크리스트의 `판정`·`근거·조치` 칸을 채운다. 규칙 단위라 담당을 나누기 쉽다 |",
          "| **제안서 §02** | §1~§2(결함→규칙)를 문단으로 풀고 §4 실측 표를 근거로 싣는다 |",
          "| **판정 변경** | `ontology/enums/*.yaml`·`shared/*.yaml` 을 고친 뒤 재생성. "
          "yaml 은 `loader.planner_context()` 를 통해 **플래너 프롬프트로 그대로 전달**되므로 답변 동작이 바뀐다 |",
          "", "## 재생성", "",
          "```bash",
          "python scripts/gen_ontology_rules_doc.py        # 12개 전부",
          "python scripts/gen_ontology_rules_doc.py 2 8    # 규칙 2·8 만",
          "```", "",
          "서술·체크리스트는 `scripts/_ontology_rules_data.py`, 인벤토리 추출기는 "
          "`scripts/gen_ontology_rules_doc.py` 의 `inv_*` 함수에 있다.", "",
          "## 규칙 적용의 불균형", "",
          "규칙은 12종이지만 **4개 도메인에 모두 선언된 최상위 키는 5개뿐**이다"
          "(`domain`·`row_grain`·`columns`·`normalization`·`query_rules`).", "",
          "| 도메인 | `query_rules` | 컬럼 판정 | 도메인 전용 블록 |", "| :-- | --: | :-- | :-- |"]
    for dom in DOMAINS:
        d = D[dom]
        nqr = len(d.get("query_rules") or {})
        jd = d.get("columns") or {}
        dbc = [x[1] for x in con.execute(f"pragma table_info({dom})")]
        extra = set()
        for k, v in jd.items():
            if isinstance(v, dict):
                for t in (v.get("applies_to") or []):
                    if t in dbc and t not in jd:
                        extra.add(t)
        cov = len([c for c in dbc if c in jd]) + len(extra)
        own = [k for k in d if k not in ("domain", "row_grain", "columns", "normalization", "query_rules")
               and not k.startswith("_")]
        L.append(f"| {KO[dom]} | {nqr} | {cov}/{len(dbc)} | {', '.join('`'+o+'`' for o in own) or '—'} |")
    L += ["", "**비어 있는 것** — 역질문 규칙(`clarify`)은 채권에만, 교차 도메인 규칙(`cross_domain`)은 펀드에만 있다. "
          "`shared/` 개체 7종의 수동 `edges` 는 전부 0 이라 `kg_edge` 는 **전량 `source: rule`(추정)** 이고, "
          "그래서 답변에 “추정” 을 병기한다. AssetClass · Currency · RiskGrade 는 `parent` 가 없어 계층 질의가 안 된다.", ""]
    return "\n".join(L)


def main() -> None:
    global D, S
    if not DB.exists():
        sys.exit(f"DB 없음: {DB}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    D = {d: yaml.safe_load((ROOT / "ontology" / "enums" / f"{d}.yaml").read_text(encoding="utf-8"))
         for d in DOMAINS}
    S = {}
    for p in sorted(glob.glob(str(ROOT / "ontology" / "shared" / "*.yaml"))):
        if "auto" in os.path.basename(p):
            continue
        S[os.path.basename(p)[:-5]] = yaml.safe_load(Path(p).read_text(encoding="utf-8"))

    want = set(sys.argv[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    made = 0
    for r in RULES:
        if want and r["n"] not in want:
            continue
        p = OUT / f"{r['n'].zfill(2)}_{r['slug']}.md"
        p.write_text(render_rule(r, con), encoding="utf-8")
        print(f"  ✅ {p.relative_to(ROOT)}  ({len(p.read_text(encoding='utf-8').splitlines()):,}줄)")
        made += 1
    idx = OUT / "README.md"
    idx.write_text(render_index(con), encoding="utf-8")
    print(f"  ✅ {idx.relative_to(ROOT)}")
    print(f"\n규칙 문서 {made}개 + 색인 생성 완료")
    con.close()


if __name__ == "__main__":
    main()
