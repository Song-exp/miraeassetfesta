# -*- coding: utf-8 -*-
"""검토 채움표 생성 — 데이터 정합성 → 피처 의미 → 결측 의미 → 온톨로지 관계 → 지식그래프.

검토할 항목을 손으로 옮겨 적으면 빠지고, 배포본이 바뀌면 낡는다.
DB·yaml 에서 **전수로 뽑아** 판정 칸이 빈 표로 만든다. 사람은 `판정`·`근거·조치` 두 칸만 채운다.

출력: docs/review_2026-08-26/{README,A_정합성,B_피처의미,C_결측의미,D_온톨로지관계,E_지식그래프}.md
사용: python scripts/gen_review_workbook.py

⚠️ 재생성하면 **채워 넣은 판정이 사라진다.** 채우기 시작한 뒤에는 재생성하지 말 것.
   (항목이 바뀌었으면 새 날짜 폴더로 뽑아 이전 판정을 옮긴다.)
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
OUT = ROOT / "docs" / "review_2026-08-26"
DOM = ["domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"]
KO = {"domestic_bonds": "채권", "domestic_etfs": "국내ETF",
      "overseas_etfs": "해외ETF", "public_funds": "펀드"}
EXT = ["ext_etf_holdings", "ext_ovs_etf_holdings", "ext_fund_holdings", "ext_fund_page"]
OWNER = {"ext_etf_holdings": "domestic_etfs", "ext_ovs_etf_holdings": "overseas_etfs",
         "ext_fund_holdings": "public_funds", "ext_fund_page": "public_funds"}
KEYS = {"ext_etf_holdings": ("etf_code", "pd_itm_no"), "ext_ovs_etf_holdings": ("isin", "pd_isin_cd"),
        "ext_fund_holdings": ("grp", "mtco_itm_no"), "ext_fund_page": ("itm_no", "itm_no")}

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
D = {d: yaml.safe_load((ROOT / "ontology" / "enums" / f"{d}.yaml").read_text(encoding="utf-8")) for d in DOM}
S = {}
for p in sorted(glob.glob(str(ROOT / "ontology" / "shared" / "*.yaml"))):
    if "auto" not in os.path.basename(p):
        S[os.path.basename(p)[:-5]] = yaml.safe_load(Path(p).read_text(encoding="utf-8"))

fmt = lambda n: f"{n:,}" if isinstance(n, int) else str(n)
def cl(v, n=200):
    return "" if v is None else str(v).replace("|", "\\|").replace("\n", " ").strip()[:n]


def merged(dom):
    """applies_to 상속을 반영한 판정 + DB 컬럼 목록."""
    j = dict(D[dom].get("columns") or {})
    dbc = [r[1] for r in con.execute(f"pragma table_info({dom})")]
    for src, v in list(j.items()):
        if isinstance(v, dict):
            for t in (v.get("applies_to") or []):
                if t in dbc and t not in j:
                    j[t] = dict(v, _inh=src)
    return j, dbc


META = {}
for t, c, ko, dt, nu in con.execute(
        "select table_name,column_name,korean_name,data_type,nullable from schema_metadata"):
    META.setdefault(t, {})[c] = (ko, dt, nu)

COUNT = collections.Counter()


def table(items, cols=("대상", "확인할 것", "자동 수집 근거")):
    """채움표 — 마지막 두 칸(판정·근거·조치)은 비워 둔다."""
    L = ["| ID | " + " | ".join(cols) + " | 판정 | 근거·조치 |",
         "| :-: | " + " | ".join([":--"] * len(cols)) + " | :-: | :-- |"]
    for it in items:
        L.append("| " + it[0] + " | " + " | ".join(cl(x, 320) for x in it[1:]) + " | ☐ |  |")
    return L


def head(title, sub, why, how, owner):
    return [f"# {title}", "", f"> {sub}", "",
            "| | |", "| :-- | :-- |",
            f"| **왜 보나** | {why} |",
            f"| **어떻게** | {how} |",
            f"| **담당** | {owner} |", "",
            "> `판정` 칸에 **✅ 이상없음 · ⚠️ 확인필요 · ❌ 고쳐야함** 중 하나를, "
            "`근거·조치` 칸에 판단 근거와 고칠 곳(`ontology/enums/*.yaml` 등)을 적습니다.", "",
            "---", ""]


# ── A. 데이터 정합성 ─────────────────────────────────────────────────────
def part_a():
    L = head("A. 데이터 정합성", "값이 서로 말이 되는가 — 판정과 실측, 행 단위, 외부 대조, 기준일.",
             "여기가 틀리면 아래 모든 판정이 잘못된 수치 위에 세워진다.",
             "표의 자동 근거를 보고 어긋난 쪽이 판정인지 데이터인지 가른다.",
             "도메인 담당 4인 분담")

    L += ["## A-1. 판정 ↔ 실측 불일치", "",
          "yaml 판정은 사람이 쓰고 수치는 배포본마다 바뀌므로 조용히 어긋난다. "
          "어긋난 채로 두면 **답변 모수가 틀린다.**", ""]
    items = []
    k = 0
    for dom in DOM:
        j, dbc = merged(dom)
        n = con.execute(f"select count(*) from {dom}").fetchone()[0]
        for c in dbc:
            v = j.get(c)
            if not isinstance(v, dict):
                continue
            miss = con.execute(
                f'''select sum(case when "{c}" is null or trim(cast("{c}" as text))='' then 1 else 0 end)
                    from "{dom}"''').fetchone()[0] or 0
            mr = str(v.get("missing_reason"))
            if mr in ("none", "present") and miss > 0:
                k += 1
                items.append((f"A-1-{k:02d}", f"{KO[dom]} `{c}`",
                              f"판정 `{mr}`(결측 없음)를 유지할지, 결측 사유를 적을지",
                              f"실측 결측 **{fmt(miss)}**행 / {fmt(n)}"))
            an = v.get("answerable_n")
            if isinstance(an, int):
                live = n - miss
                if abs(live - an) > max(5, an * 0.01):
                    k += 1
                    items.append((f"A-1-{k:02d}", f"{KO[dom]} `{c}`",
                                  "`answerable_n` 이 도메인 조건 포함 모수인지, 단순 non-null 인지",
                                  f"기재 **{fmt(an)}** vs 실측 non-null **{fmt(live)}**"))
    COUNT["A-1"] = len(items)
    L += table(items)

    L += ["", "## A-2. 행 단위(grain) — `COUNT(*)` 가 개체 수인가", ""]
    items = []
    for i, (dom, key) in enumerate([("domestic_bonds", "pd_no"), ("domestic_etfs", "pd_itm_no"),
                                    ("overseas_etfs", "pd_isin_cd"), ("public_funds", "itm_no")], 1):
        r, k2 = con.execute(f'select count(*), count(distinct "{key}") from {dom}').fetchone()
        items.append((f"A-2-{i:02d}", f"{KO[dom]} (`{key}`)",
                      "집계 질의가 행이 아니라 개체를 세도록 규칙이 걸려 있는가",
                      f"행 **{fmt(r)}** / 개체 **{fmt(k2)}** · 중복 {fmt(r - k2)}"))
    COUNT["A-2"] = len(items)
    L += table(items)

    L += ["", "## A-3. 외부 대조 — 조인이 실제로 붙는가", ""]
    items = []
    for i, t in enumerate(EXT, 1):
        ek, mk = KEYS[t]
        own = OWNER[t]
        got = con.execute(f'select count(distinct "{ek}") from {t}').fetchone()[0]
        hit = con.execute(
            f'select count(distinct h."{ek}") from {t} h join {own} m on m."{mk}"=h."{ek}"').fetchone()[0]
        items.append((f"A-3-{i:02d}", f"`{t}` → `{own}`",
                      "안 붙는 키가 보완 가능한지, 커버리지를 답변에 어떻게 밝힐지",
                      f"수집 키 **{fmt(got)}** · 마스터 조인 **{fmt(hit)}** ({hit/max(1,got)*100:.1f}%) · 키 `{ek}`=`{mk}`"))
    COUNT["A-3"] = len(items)
    L += table(items)

    L += ["", "## A-4. 기준일 — 언제 기준의 사실인가", ""]
    items = []
    src = [("마스터 4테이블", "select as_of from build_info limit 1"),
           ("채권 `info_base_dt`", "select cast(min(info_base_dt) as text)||' ~ '||cast(max(info_base_dt) as text) from domestic_bonds"),
           ("`ext_etf_holdings.as_of`", "select min(as_of)||' ~ '||max(as_of) from ext_etf_holdings"),
           ("`ext_ovs_etf_holdings.report_date`", "select min(report_date)||' ~ '||max(report_date) from ext_ovs_etf_holdings"),
           ("`ext_fund_holdings.bas_dt`", "select min(bas_dt)||' ~ '||max(bas_dt) from ext_fund_holdings"),
           ("`ext_fund_page.retrieved_at`", "select min(retrieved_at)||' ~ '||max(retrieved_at) from ext_fund_page")]
    for i, (nm, q) in enumerate(src, 1):
        try:
            v = con.execute(q).fetchone()[0]
        except sqlite3.Error as e:
            v = f"조회 실패 {e}"
        items.append((f"A-4-{i:02d}", nm, "답변에 이 기준일을 병기하는 규칙이 있는가", f"`{cl(v,60)}`"))
    COUNT["A-4"] = len(items)
    L += table(items)
    return L


# ── B. 피처 의미 ─────────────────────────────────────────────────────────
def part_b():
    L = head("B. 피처 의미", "컬럼 하나하나가 정말 그 뜻인가 — 판정이 없는 것, 물려받은 것, 단위가 없는 것.",
             "판정이 없는 컬럼은 **질의에 쓰면 안 되는** 상태다. 단위가 없으면 비교·정렬 답변을 만들 수 없다.",
             "주최 한글명과 실측 값 분포를 보고 결측 사유·답변 정책을 정한다.",
             "도메인 담당 4인 분담")

    L += ["## B-1. 판정이 없는 컬럼 — 결측 사유·답변 정책을 정할 것", "",
          "주최가 준 한글명과 실측만 있고 우리 판정이 없다. 채우는 것이 각 도메인의 남은 작업.", ""]
    items = []
    k = 0
    for dom in DOM:
        j, dbc = merged(dom)
        n = con.execute(f"select count(*) from {dom}").fetchone()[0]
        for c in dbc:
            if c in j:
                continue
            k += 1
            ko, dt, nu = META.get(dom, {}).get(c, (None, None, None))
            miss, dis = con.execute(
                f'''select sum(case when "{c}" is null or trim(cast("{c}" as text))='' then 1 else 0 end),
                           count(distinct "{c}") from "{dom}"''').fetchone()
            top = [str(v) for v, _ in con.execute(
                f'''select cast("{c}" as text), count(*) from "{dom}"
                    where "{c}" is not null and trim(cast("{c}" as text))<>''
                    group by 1 order by 2 desc limit 4''')]
            items.append((f"B-1-{k:02d}", f"{KO[dom]} `{c}`",
                          f"{cl(ko,40) or '한글명 없음'} — 결측 사유 4분류 중 무엇인가",
                          f"`{cl(dt,24)}` · 결측 {fmt(miss or 0)}/{fmt(n)} · distinct {fmt(dis)} · "
                          f"값 {cl(' · '.join(top[:3]), 90)}"))
    COUNT["B-1"] = len(items)
    L += table(items)

    L += ["", "## B-2. 판정을 물려받은 컬럼 — 상속이 타당한가", "",
          "다른 컬럼의 `applies_to` 로 공통 판정을 물려받았다. 실측이 다르면 따로 판정해야 한다.", ""]
    items = []
    k = 0
    for dom in DOM:
        j, dbc = merged(dom)
        n = con.execute(f"select count(*) from {dom}").fetchone()[0]
        for c in dbc:
            v = j.get(c)
            if isinstance(v, dict) and v.get("_inh"):
                k += 1
                miss = con.execute(
                    f'''select sum(case when "{c}" is null or trim(cast("{c}" as text))='' then 1 else 0 end)
                        from "{dom}"''').fetchone()[0] or 0
                items.append((f"B-2-{k:02d}", f"{KO[dom]} `{c}`",
                              f"`{v['_inh']}` 의 판정을 그대로 써도 되는가",
                              f"결측 {fmt(miss)}/{fmt(n)} · 물려받은 사유 `{v.get('missing_reason')}`"))
    COUNT["B-2"] = len(items)
    L += table(items)

    L += ["", "## B-3. 단위가 없는 수치 컬럼 — 비교·정렬 답변에 쓸 수 없다", ""]
    items = []
    k = 0
    for dom in DOM:
        j, _ = merged(dom)
        for c, (ko, dt, nu) in sorted(META.get(dom, {}).items()):
            if not any(x in (dt or "").lower() for x in ("int", "double", "numeric", "real", "decimal", "float")):
                continue
            if (j.get(c) or {}).get("unit"):
                continue
            k += 1
            mn, mx = con.execute(f'select min("{c}"), max("{c}") from "{dom}"').fetchone()
            items.append((f"B-3-{k:02d}", f"{KO[dom]} `{c}`",
                          f"{cl(ko,36)} — 단위가 무엇인가 (%· ‰ ·원·일·배…)",
                          f"범위 {cl(mn,18)} ~ {cl(mx,18)}"))
    COUNT["B-3"] = len(items)
    L += table(items)

    L += ["", "## B-4. 단위 표기 통일", ""]
    u = collections.defaultdict(list)
    for dom in DOM:
        j, _ = merged(dom)
        for c, v in j.items():
            if isinstance(v, dict) and v.get("unit"):
                u[str(v["unit"])].append(f"{KO[dom]}.`{c}`")
    items = []
    for i, (k2, v) in enumerate(sorted(u.items(), key=lambda x: -len(x[1])), 1):
        items.append((f"B-4-{i:02d}", f"`{cl(k2,60)}`",
                      "표기를 고정 어휘(enum)로 통일할 것인가 · 형식(format)과 단위를 나눌 것인가",
                      f"{len(v)}개 컬럼 — {cl(', '.join(v[:5]), 120)}"))
    COUNT["B-4"] = len(items)
    L += table(items)
    return L


# ── C. 결측치 의미 ───────────────────────────────────────────────────────
def part_c():
    L = head("C. 결측치 의미", "비어 있음이 무슨 뜻인가 — 답변 문장이 여기서 갈린다.",
             "`not_applicable` 을 “모릅니다” 로 답하면 오답이다. 분해가 없으면 문장을 고를 수 없다.",
             "값별 분포를 보고 어느 값이 어떤 뜻인지 가른다.",
             "도메인 담당 4인 분담")
    L += ["> **4분류** — `not_applicable`(해당 없음) · `missing`(미수록) · `present`/`none`(정상) · `mixed`(행마다 다름)", ""]

    L += ["## C-1. `mixed` 인데 값별 분해가 없는 컬럼", "",
          "`mixed` 는 '행마다 이유가 다름' 이라는 선언이므로 `missing_semantics` 로 분해해야 "
          "답변 문장을 고를 수 있다. **판정만 있고 답변 규칙은 없는 상태.**", ""]
    items = []
    k = 0
    for dom in DOM:
        j, dbc = merged(dom)
        n = con.execute(f"select count(*) from {dom}").fetchone()[0]
        for c in dbc:
            v = j.get(c)
            if not (isinstance(v, dict) and str(v.get("missing_reason")) == "mixed"
                    and not v.get("missing_semantics")):
                continue
            k += 1
            miss, zero = con.execute(
                f'''select sum(case when "{c}" is null or trim(cast("{c}" as text))='' then 1 else 0 end),
                           sum(case when trim(cast("{c}" as text))='0' then 1 else 0 end) from "{dom}"''').fetchone()
            items.append((f"C-1-{k:02d}", f"{KO[dom]} `{c}`",
                          f"{cl(v.get('korean_name'),34)} — NULL·0·특정값이 각각 무슨 뜻인가",
                          f"결측 {fmt(miss or 0)}/{fmt(n)} · 값 0 이 {fmt(zero or 0)}"
                          + (" · 상속" if v.get("_inh") else "")))
    COUNT["C-1"] = len(items)
    L += table(items)

    L += ["", "## C-2. 4분류 밖 판정 — 답변 규칙이 없는 상태", ""]
    items = []
    k = 0
    for dom in DOM:
        j, dbc = merged(dom)
        for c in dbc:
            v = j.get(c)
            if not isinstance(v, dict):
                continue
            mr = v.get("missing_reason")
            if str(mr) in ("not_applicable", "missing", "present", "none", "mixed"):
                continue
            k += 1
            items.append((f"C-2-{k:02d}", f"{KO[dom]} `{c}`",
                          "4분류 중 무엇으로 확정할 것인가 (또는 분류를 늘릴 것인가)",
                          f"현재 값 `{mr}` · {cl(v.get('korean_name'),36)}"))
    COUNT["C-2"] = len(items)
    L += table(items)

    L += ["", "## C-3. `zero_is_value` 예외 — 0 을 배제하지 않는 컬럼", "",
          "주최 8/26 답변: *“수익률·총보수 같은 컬럼을 질의했을 때 값이 0 인 행은 아예 포함하지 않는 게 맞다”*. "
          "예외로 남길 근거가 있는지 하나씩 확인한다.", ""]
    items = []
    k = 0
    for dom in DOM:
        j, dbc = merged(dom)
        n = con.execute(f"select count(*) from {dom}").fetchone()[0]
        for c in dbc:
            v = j.get(c)
            if not (isinstance(v, dict) and v.get("zero_is_value")):
                continue
            k += 1
            z = con.execute(f'''select sum(case when trim(cast("{c}" as text))='0' then 1 else 0 end)
                                from "{dom}"''').fetchone()[0] or 0
            items.append((f"C-3-{k:02d}", f"{KO[dom]} `{c}`",
                          "0 이 랭킹 축인가, 분류 정보·합산 성분인가 — 예외 유지 여부",
                          f"{cl(v.get('korean_name'),34)} · 값 0 이 {fmt(z)}/{fmt(n)}"))
    COUNT["C-3"] = len(items)
    L += table(items)

    L += ["", "## C-4. 위장결측·센티넬 선언 — 2차 데이터에서도 유효한가", ""]
    items = []
    k = 0
    for dom in DOM:
        nm = D[dom].get("normalization") or {}
        for key in ("dummy_as_missing", "invalid_values", "contaminated_rows", "zero_as_missing", "constant_columns"):
            if key in nm:
                k += 1
                items.append((f"C-4-{k:02d}", f"{KO[dom]} `{key}`",
                              "선언한 조건식이 2차 데이터에서도 같은 행을 잡는가",
                              cl(nm[key], 300)))
    COUNT["C-4"] = len(items)
    L += table(items)
    return L


# ── D. 온톨로지 관계 ─────────────────────────────────────────────────────
def part_d():
    L = head("D. 온톨로지 관계", "규칙과 축이 옳게 잡혔는가 — 파생·배타·계층·부재, 그리고 규칙이 실제로 강제되는가.",
             "규칙이 문서에만 있고 기계가 강제하지 않으면 지켜진다는 보장이 없다.",
             "규칙 원문과 실측 분포를 대조한다. 세부는 `docs/ontology_rules/` 12문서 참조.",
             "리드 1인 + 도메인 담당 보조")

    L += ["## D-1. 파생 규칙 — 없는 축을 만들어 내는 규칙이 옳은가", ""]
    items = []
    k = 0
    for dom in DOM:
        for key in ("derivation_rules", "axis_derivation"):
            blk = D[dom].get(key)
            if not isinstance(blk, dict):
                continue
            for name, body in blk.items():
                if name.startswith("_"):
                    continue
                k += 1
                items.append((f"D-1-{k:02d}", f"{KO[dom]} `{key}.{name}`",
                              "규칙이 오탐·누락을 얼마나 내는가 · 답변에 ‘추정’ 을 병기하는가",
                              cl(body, 300)))
    COUNT["D-1"] = len(items)
    L += table(items)

    L += ["", "## D-2. 배타·분리·금지 규칙 — 기계가 강제하는가, 문구뿐인가", ""]
    items = []
    k = 0
    for dom in DOM:
        for key, v in (D[dom].get("query_rules") or {}).items():
            if not any(w in key for w in ("금지", "분리", "제외", "배제")):
                continue
            k += 1
            items.append((f"D-2-{k:02d}", f"{KO[dom]} `{key}`",
                          "`validate_sql` 이 차단하는가, 프롬프트 문구뿐인가",
                          cl(v, 300)))
    COUNT["D-2"] = len(items)
    L += table(items)

    L += ["", "## D-3. 계층 — 개체에 `parent` 가 있는가", "",
          "계층이 없으면 ‘아시아 투자 ETF’ 처럼 상위 개념으로 묻는 질의가 0건을 반환한다.", ""]
    items = []
    for i, (name, doc) in enumerate(sorted(S.items()), 1):
        nodes = doc.get("nodes") or {}
        par = sum(1 for v in nodes.values() if isinstance(v, dict) and v.get("parent"))
        kg = con.execute("select count(*) from kg_node where node_type=?", (doc.get("entity", name),)).fetchone()[0]
        items.append((f"D-3-{i:02d}", f"`{doc.get('entity', name)}`",
                      "계층이 필요한 개체인가 — 필요하면 어떤 축으로 세울 것인가",
                      f"yaml 노드 {fmt(len(nodes))} · KG {fmt(kg)} · `parent` **{fmt(par)}**"
                      + ("" if par else " ← 계층 없음")))
    COUNT["D-3"] = len(items)
    L += table(items)

    L += ["", "## D-4. 부재 선언 — 컬럼이 없다는 사실", ""]
    items = []
    k = 0
    for name, doc in sorted(S.items()):
        for dom, why in (doc.get("absent_in") or {}).items():
            k += 1
            items.append((f"D-4-{k:02d}", f"`{doc.get('entity', name)}` × {KO.get(dom, dom)}",
                          "게이트가 이 선언으로 실제 기각하는가 · 회귀 테스트가 있는가", cl(why, 260)))
    k += 1
    items.append((f"D-4-{k:02d}", "컬럼 수준 부재",
                  "해외ETF 기간수익률처럼 **컬럼 자체가 없는** 사실을 어디에 선언할 것인가",
                  "`_absent_columns` 가 도메인 yaml 에 없다 — 개체 수준 `absent_in` 만 존재"))
    COUNT["D-4"] = len(items)
    L += table(items)
    return L


# ── E. 지식그래프 ────────────────────────────────────────────────────────
def part_e():
    L = head("E. 지식그래프", "개체가 옳게 잡혔는가 — 라벨·동일성·별칭·관계. **노드가 틀리면 관계 검토는 무의미하다.**",
             "라벨은 답변에 그대로 노출되고, 관계의 99% 가 규칙 유도(추정)다.",
             "탐색기(`build/kg.html`)의 **이웃 모드**로 개체 하나씩 펼쳐 본다.",
             "리드 1인 (개체가 도메인을 가로지르므로)")

    L += ["## E-1. 라벨 — 답변 노출면", ""]
    items = []
    for i, (t, n) in enumerate(con.execute(
            "select node_type,count(*) from kg_node group by 1 order by 2 desc"), 1):
        ko, en = con.execute(
            """select sum(case when label_ko is not null and trim(label_ko)<>'' then 1 else 0 end),
                      sum(case when label_en is not null and trim(label_en)<>'' then 1 else 0 end)
               from kg_node where node_type=?""", (t,)).fetchone()
        flag = " 🔴 한글 라벨 대부분 비어 있음" if ko < n * 0.5 else ""
        items.append((f"E-1-{i:02d}", f"`{t}`",
                      "답변에 쓸 이름이 올바른 필드에 있는가 · 언어가 섞이지 않았는가",
                      f"노드 {fmt(n)} · `label_ko` {fmt(ko)} · `label_en` {fmt(en)}{flag}"))
    COUNT["E-1"] = len(items)
    L += table(items)

    L += ["", "## E-2. 개체 동일성 — 같은 종류 안에서 라벨이 겹치는 노드", "",
          "`build_ontology.py` V2 는 *잘못 묶인 것*(한 원시값이 두 노드에 걸림)만 잡는다. "
          "**묶여야 하는데 안 묶인 것**은 검증기가 못 보므로 사람이 판정해야 한다.", ""]
    items = []
    k = 0
    for t, lab, cnt in con.execute(
            """select node_type, label_ko, count(*) c from kg_node
               where label_ko is not null and trim(label_ko)<>''
               group by 1,2 having c>1 order by c desc, 1, 2"""):
        k += 1
        ids = [r[0] for r in con.execute(
            "select node_id from kg_node where node_type=? and label_ko=? limit 6", (t, lab))]
        al = con.execute(
            """select count(*) from kg_alias where node_id in
               (select node_id from kg_node where node_type=? and label_ko=?)""", (t, lab)).fetchone()[0]
        items.append((f"E-2-{k:02d}", f"`{t}` · `{cl(lab,40)}`",
                      "같은 실체인가(합쳐야) · 다른 실체인가(라벨을 구분해야)",
                      f"**{cnt}노드** · 별칭 {fmt(al)} — {cl(', '.join(ids[:3]),80)}"))
    COUNT["E-2"] = len(items)
    L += table(items)

    L += ["", "## E-2b. 종류를 넘는 라벨 충돌 — 개념 결정", "",
          "회사(`Organization`)와 그 상장 종목(`Security`)이 같은 이름을 갖는 것은 **정상**이다. "
          "판정할 것은 개별 사례가 아니라 **둘을 관계로 이을 것인가**다.", ""]
    pairs = collections.defaultdict(list)
    for lab, in con.execute(
            """select label_ko from kg_node where label_ko is not null and trim(label_ko)<>''
               group by 1 having count(distinct node_type)>1"""):
        ts = tuple(sorted(r[0] for r in con.execute(
            "select distinct node_type from kg_node where label_ko=?", (lab,))))
        pairs[ts].append(lab)
    items = []
    for i, (ts, labs) in enumerate(sorted(pairs.items(), key=lambda x: -len(x[1])), 1):
        items.append((f"E-2b-{i:02d}", " × ".join(f"`{t}`" for t in ts),
                      "두 개체를 관계로 이을 것인가 (예: 회사 → 발행 종목) · 아니면 별개로 둘 것인가",
                      f"라벨 **{fmt(len(labs))}개**가 겹침 — 예: {cl(' · '.join(labs[:4]),80)}"))
    COUNT["E-2b"] = len(items)
    L += table(items)

    L += ["", "## E-3. 별칭 — 어느 컬럼의 값이 개체로 이어졌나", ""]
    items = []
    for i, (tb, cl_, n) in enumerate(con.execute(
            "select table_name,column_name,count(*) from kg_alias group by 1,2 order by 3 desc limit 25"), 1):
        nd = con.execute("select count(distinct node_id) from kg_alias where table_name=? and column_name=?",
                         (tb, cl_)).fetchone()[0]
        items.append((f"E-3-{i:02d}", f"`{tb}`.`{cl_}`",
                      "붙지 않은 값이 남아 있는가 · 오매칭 표본이 있는가",
                      f"별칭 {fmt(n)} → 노드 {fmt(nd)}"))
    COUNT["E-3"] = len(items)
    L += table(items)

    L += ["", "## E-4. 관계 — 규칙이 옳은가", "",
          "관계는 전량 규칙 유도(추정)라 답변에 “추정” 을 병기한다. 표본으로 규칙의 적중률을 본다.", ""]
    items = []
    k = 0
    for src, pred, n in con.execute(
            "select source,predicate,count(*) from kg_edge group by 1,2 order by 3 desc"):
        k += 1
        items.append((f"E-4-{k:02d}", f"`{pred}` · source `{cl(src,28)}`",
                      "규칙 적중률 — 상위 연결 표본에서 오탐이 몇 건인가",
                      f"{fmt(n)}건"))
    k += 1
    items.append((f"E-4-{k:02d}", "관계가 아예 없는 축",
                  "발행사→업종·담보 등 재료가 있는데 미연결인 축을 만들 것인가",
                  "`issuer_industry_map.csv` · `collateral_type_map.csv` 존재 · edge 0"))
    COUNT["E-4"] = len(items)
    L += table(items)

    L += ["", "## E-5. 커버리지 공백 — 노드가 없는 것", ""]
    items = [
        ("E-5-01", "펀드 대표코드 위장결측",
         "Fund 노드를 못 만든 행을 어떻게 답할 것인가",
         f"`rptt_ksd_itm_no` NULL/0계열 "
         f"{fmt(con.execute('''select sum(case when rptt_ksd_itm_no is null or trim(rptt_ksd_itm_no)='' or cast(rptt_ksd_itm_no as integer)=0 then 1 else 0 end) from public_funds''').fetchone()[0])}행"),
        ("E-5-02", "Security 편입비중 하위 종목",
         "상위 50 밖 종목은 노드가 없고 `ext_*` 조인으로만 조회된다 — 답변에 밝히는가",
         "`gen_security_auto.py` 의 상위 N 절단"),
        ("E-5-03", "모펀드",
         "마스터 밖 개체를 노드로 만들 것인가",
         "`ext_fund_page.mother_fund_names_raw` — 정규화 전 원문"),
    ]
    COUNT["E-5"] = len(items)
    L += table(items)
    return L


# ── 색인 ─────────────────────────────────────────────────────────────────
def readme(parts):
    tot = sum(COUNT.values())
    L = ["# 🔎 온톨로지 · 지식그래프 검토 채움표", "",
         f"> 전수로 뽑은 검토 항목 **{tot}건**. 표의 `판정`·`근거·조치` 두 칸을 채우면 됩니다.",
         f"> 기준: DB `{con.execute('select as_of from build_info limit 1').fetchone()[0]}` · 생성 2026-08-26", "",
         "## 순서", "",
         "```",
         "A 데이터 정합성  ─▶  B 피처 의미  ─▶  C 결측 의미",
         "                                        │",
         "                     E 지식그래프  ◀─  D 온톨로지 관계",
         "```", "",
         "A 가 먼저인 이유: 수치가 틀리면 아래 판정이 잘못된 근거 위에 세워집니다.",
         "E 안에서는 **라벨·동일성(E-1·E-2)이 관계(E-4)보다 먼저**입니다 — 노드가 틀리면 관계 검토가 무의미합니다.", "",
         "## 문서", "",
         "| 문서 | 다루는 것 | 항목 | 담당 |", "| :-- | :-- | --: | :-- |"]
    meta = [("A_정합성", "판정↔실측 · 행 단위 · 외부 조인 · 기준일", "도메인 4인"),
            ("B_피처의미", "미판정 컬럼 · 판정 상속 · 단위", "도메인 4인"),
            ("C_결측의미", "mixed 분해 · 분류밖 · 0 예외 · 위장결측", "도메인 4인"),
            ("D_온톨로지관계", "파생 · 배타/금지 · 계층 · 부재", "리드 + 보조"),
            ("E_지식그래프", "라벨 · 동일성 · 별칭 · 관계 · 공백", "리드 1인")]
    for f, what, who in meta:
        n = sum(v for k, v in COUNT.items() if k.startswith(f.split("_")[0]))
        L.append(f"| [`{f}.md`]({f}.md) | {what} | **{n}** | {who} |")
    L += ["", "## 절별 항목 수", "", "| 절 | 항목 |", "| :-- | --: |"]
    LABEL = {"A-1": "판정↔실측 불일치", "A-2": "행 단위", "A-3": "외부 조인", "A-4": "기준일",
             "B-1": "판정 없는 컬럼", "B-2": "판정 상속", "B-3": "단위 없는 수치", "B-4": "단위 표기",
             "C-1": "mixed 분해 없음", "C-2": "4분류 밖", "C-3": "0 예외", "C-4": "위장결측·센티넬",
             "D-1": "파생 규칙", "D-2": "배타·금지", "D-3": "계층", "D-4": "부재 선언",
             "E-1": "라벨", "E-2": "동일성 — 같은 종류 안 중복", "E-2b": "종류 넘는 라벨 충돌", "E-3": "별칭", "E-4": "관계", "E-5": "커버리지 공백"}
    for k in LABEL:
        if COUNT.get(k):
            L.append(f"| {k} {LABEL[k]} | {COUNT[k]} |")
    L += ["", f"| **합계** | **{tot}** |", "",
          "## 채우는 법", "",
          "| 칸 | 적을 것 |", "| :-- | :-- |",
          "| `판정` | **✅ 이상없음** · **⚠️ 확인필요** · **❌ 고쳐야함** |",
          "| `근거·조치` | 그렇게 본 근거와, 고칠 파일·위치 |", "",
          "판정이 바뀌면 **원본을 고칩니다** — `ontology/enums/*.yaml`(컬럼 판정·질의 규칙) 또는 "
          "`ontology/shared/*.yaml`(개체·계층·부재). yaml 은 `loader.planner_context()` 를 통해 "
          "**플래너 프롬프트로 그대로 전달**되므로 판정을 고치면 답변 동작이 바뀝니다.", "",
          "## 도구", "",
          "| 항목 | 쓸 것 |", "| :-- | :-- |",
          "| A·B·C | `build/ontology.html` — 전수표 · 값 전체 목록 · 미판정 표시 |",
          "| E | `build/kg.html` — 이웃 모드로 개체 하나씩 펼쳐 보기 |",
          "| 배경 | `docs/ontology_rules/` 규칙 12문서 · `docs/data_dictionary/` 컬럼 사전 |", "",
          "> ⚠️ **재생성하면 채워 넣은 판정이 사라집니다.** 채우기 시작한 뒤에는 "
          "`python scripts/gen_review_workbook.py` 를 다시 돌리지 마세요. "
          "항목이 바뀌었으면 새 날짜 폴더로 뽑아 이전 판정을 옮깁니다.", ""]
    return L


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    parts = [("A_정합성", part_a), ("B_피처의미", part_b), ("C_결측의미", part_c),
             ("D_온톨로지관계", part_d), ("E_지식그래프", part_e)]
    for name, fn in parts:
        (OUT / f"{name}.md").write_text("\n".join(fn()), encoding="utf-8")
        print(f"  ✅ {name}.md")
    (OUT / "README.md").write_text("\n".join(readme(parts)), encoding="utf-8")
    print(f"  ✅ README.md\n\n검토 항목 총 {sum(COUNT.values())}건")


if __name__ == "__main__":
    main()
