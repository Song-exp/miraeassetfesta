# -*- coding: utf-8 -*-
"""엔티티 구조도 생성 — yaml(판정) + auto.yaml(사실) + DB 에서 직접 뽑는다.
손으로 옮겨 적으면 낡으므로 재생성 가능하게 둔다."""
import yaml, re, sqlite3, pandas as pd
from pathlib import Path

D = yaml.safe_load(Path("ontology/enums/public_funds.yaml").read_text(encoding="utf-8"))
A = yaml.safe_load(Path("ontology/enums/public_funds.auto.yaml").read_text(encoding="utf-8"))
conn = sqlite3.connect(f"{Path('data/financial_products.db').resolve().as_uri()}?mode=ro", uri=True)
COLS, TOTAL = list(A["columns"]), A["meta"]["row_count"]

owner = {}
for k, v in D["entities"].items():
    for t in re.findall(r"[A-Za-z_]\w*", str((v or {}).get("source") or "")):
        if t in COLS: owner.setdefault(t, []).append(f"**{k}**")
for k, v in D["derivation_rules"].items():
    if k.startswith("_"): continue
    for t in re.findall(r"[A-Za-z_]\w*", f"{(v or {}).get('규칙','')} {(v or {}).get('축','')}"):
        if t in COLS: owner.setdefault(t, []).append(f"rule:`{k}`")
for g, cs in D["attributes"].items():
    if not g.startswith("_"):
        for c in cs or []: owner.setdefault(c, []).append(f"속성:{g}")
assert len(owner) == len(COLS), f"미배정 {[c for c in COLS if c not in owner]}"

# 엔티티 단위 distinct (행이 아니라 종목 기준)
ENT_N = {k: v.get("count") for k, v in D["entities"].items()}
# 🔴 Fund 는 문자열로 박아두면 낡는다 — yaml 에서 읽는다 (2026-08-17: 모펀드 4,660 오기 정정)
FUND = D["entities"]["Fund"]
FUND_N, FUND_SRC = FUND.get("count"), FUND.get("source", "")
q = lambda sql: conn.execute(sql).fetchone()[0]
N_ITM = q("select count(distinct itm_no) from public_funds")
N_PUB_SELL = q("select count(*) from public_funds where sale_yn='판매중' and prvo_pbff_desc='공모'")
N_PRIV = q("select count(*) from public_funds where prvo_pbff_desc='사모'")
N_STD_MULTI = q("select count(*) from (select std_itm_no from public_funds where std_itm_no is not null and trim(std_itm_no) not in ('','00000') group by 1 having count(distinct itm_no)>1)")
CTRY_COV = q("select avg(case when prfd_attr_search_text glob '*[A-Z][A-Z][A-Z] *' then 1.0 else 0 end) from public_funds where prfd_attr_search_text is not null")
ABRV_N = A["columns"]["itm_abrv_nm"]["distinct_count"]
ASOF = A["meta"].get("data_asof", "")

def facts(c):
    e = A["columns"][c]
    d = (D.get("columns") or {}).get(c) or {}
    miss = 1 - e["values_present"] / TOTAL
    tag = []
    if d.get("missing_reason"): tag.append(f"판정 `{d['missing_reason']}`")
    if d.get("evidence_grade"): tag.append(f"근거 `{d['evidence_grade']}`")
    if d.get("missing_semantics"): tag.append("값단위 판정")
    if d.get("unit"): tag.append(f"단위 `{d['unit']}`")
    if d.get("trap") or d.get("answer_policy"): tag.append("⚠️ trap/정책")
    for f in e.get("findings", []):
        if f["detector"] == "placeholder_value": tag.append("🔴 더미값")
        if f["detector"] == "empty_column": tag.append("🔴 전결측")
    return e["korean_name"] or "", e["kind"], e["distinct_count"], miss, " · ".join(dict.fromkeys(tag))

L = []
w = L.append
w("# 🧬 공모펀드 엔티티 구조도 — 컬럼 단위 배정표\n")
w("> **자동 생성 문서입니다.** 근거: `ontology/enums/public_funds.yaml`(판정) + "
  "`ontology/enums/public_funds.auto.yaml`(사실) + DB 실측\n>")
w(f"> 테이블 `public_funds` · {TOTAL:,}행 × {len(COLS)}컬럼 · 종목(`itm_no`) {ENT_N['FundClass']:,}개\n")
w("> 재생성: 이 문서를 만든 스크립트는 노트북 「🧬 엔티티 탐색」 절의 배정 검증 셀과 같은 로직을 씁니다.\n")
w("\n---\n")

w("## 1. 한눈에 — 무엇이 개체이고 무엇이 속성인가\n")
w(f"""```
                    ┌─────────────────┐
                    │  AssetManager   │ {ENT_N["AssetManager"]:,}  운용사 (or_co_xtn_itt_cd)
                    │  Custodian      │ {ENT_N["Custodian"]:,}   수탁사 (trusc_xtn_itt_cd)
                    └────────▲────────┘
                             │ managedBy / custodiedBy
              ┌──────────────┴──────────────┐
              │           Fund              │ {FUND_N:,}   펀드 = 운용 단위 (모펀드 아님)
              │  (or_co, mtco) 합성키        │          순자산 합계가 이 단위
              └──────────────▲──────────────┘
                             │ belongsToFund
              ┌──────────────┴──────────────┐
              │        FundClass            │ {ENT_N["FundClass"]:,}   ★ 주 노드 = 판매 단위 = 행 (itm_no PK)
              │           itm_no            │          속성 {len(COLS)-1}컬럼이 여기 붙음
              └───┬────────┬─────────┬──────┘
        hasShare  │        │         │  hasAttribute / investsIn / benchmarkedTo
          Class   ▼        ▼         ▼
      ┌───────────┐ ┌────────────┐ ┌──────────┐ ┌────────────┐
      │ShareClass │ │FundAttribute│ │ Country  │ │ Benchmark  │
      │   {ENT_N["ShareClass"]:>4}    │ │  {ENT_N["FundAttribute"]:>4} (15축)│ │   {ENT_N["Country"]:>3}    │ │    {ENT_N["Benchmark"]:>4}    │
      │itm_nm 파싱│ │prfd_attr_cds│ │prfd_attr │ │  bmrk_nm   │
      └───────────┘ └────────────┘ └──────────┘ └────────────┘
                                                  🔵 국내ETF와 17종 통용

  ※ 행({TOTAL:,}) = FundClass({N_ITM:,}) — 2차 데이터(기준일 {ASOF})부터 itm_no 가 행 단위 PK.
     속성태그는 prfd_attr_cds(쉼표 목록) 한 컬럼에 집약 → {len(COLS)}컬럼 전부 FundClass 속성.
     std_itm_no 는 클래스 묶음 키가 아니다(2개 이상 itm_no 를 가리키는 값 {N_STD_MULTI}개뿐) — 펀드 단위 키는 (or_co, mtco) 합성키.
  🔴 기본 모수 = 판매중 AND 공모 {N_PUB_SELL:,}행 — 사모 {N_PRIV:,}행이 섞여 있다(prvo_pbff_desc). 개수·Top-N 질의는 모수를 밝힐 것.
  🔴 Fund 는 '모펀드' 가 아니다 — 클래스를 걷어낸 펀드 단위다. 모자형 모펀드는 이 테이블에 없다
     (모투자신탁·모투자회사 0건). mtco 단독 조인 금지 — 65종이 여러 운용사에 걸친다
```\n""")

w("\n### 관계도 (mermaid)\n")
w("```mermaid")
w("graph TD")
w(f'  FC["<b>FundClass</b><br/>★ 주 노드 {ENT_N["FundClass"]:,}<br/>itm_no (행 PK)"]')
w(f'  FD["Fund<br/>펀드 {FUND_N:,} (모펀드 아님)<br/>(or_co, mtco) 합성키"]')
w(f'  SC["ShareClass<br/>{ENT_N["ShareClass"]}<br/>itm_nm 파싱 + han_clas_nm"]')
w(f'  FA["FundAttribute<br/>{ENT_N["FundAttribute"]} · 15축<br/>prfd_attr_cds"]')
w(f'  CO["Country<br/>{ENT_N["Country"]} · 태그 커버리지 {CTRY_COV:.1%}"]')
w(f'  BM["Benchmark<br/>{ENT_N["Benchmark"]}<br/>국내ETF와 통용분 있음"]')
w(f'  AM["AssetManager<br/>{ENT_N["AssetManager"]} · 이름 컬럼 없음(코드북)"]')
w(f'  CU["Custodian<br/>{ENT_N["Custodian"]} · 이름 컬럼 없음(코드북)"]')
w("  FC -->|belongsToFund| FD")
w("  FD -->|managedBy| AM")
w("  FD -->|custodiedBy| CU")
w("  FD -->|establishedIn| CO")
w("  FC -->|hasShareClass| SC")
w("  FC -->|hasAttribute| FA")
w("  FC -->|investsIn| CO")
w("  FC -->|benchmarkedTo| BM")
w("```\n")

w("\n---\n")
w("## 2. 엔티티 8종\n")
w("| 엔티티 | 출처 컬럼 | 개수 | 레이블 | 관계 | 상태 |")
w("| :--- | :--- | ---: | :--- | :--- | :--- |")
for k, v in D["entities"].items():
    src = ", ".join(f"`{c}`" for c in COLS if f"**{k}**" in owner.get(c, [])) or "—"
    lab = f"`{v['label']}`" if v.get("label") else "🔴 없음"
    rel = (v.get("relation") or "—").replace("->", "→")
    st = "🔴 이름 컬럼 없음" if not v.get("label") and k in ("AssetManager", "Custodian") else ""
    if k == "FundAttribute": st = "🔶 의미 미해독 (12/15축 대응)"
    if k == "Country": st = f"커버리지 13.9%"
    w(f"| **{k}** | {src} | {v.get('count','')} | {lab} | {rel} | {st} |")

w("\n> 🔴 **`AssetManager`·`Custodian` 은 코드만 있고 이름 컬럼이 없습니다.** "
  "사용자가 *\"미래에셋자산운용\"* 이라고 물어도 이을 수 없습니다 (EDA_GUIDE §5-A 최우선 이슈).\n")

w("\n---\n")
w(f"## 3. 컬럼 {len(COLS)}개 전수 배정\n")
w(f"모든 컬럼이 **엔티티 출처 · 유도규칙 · 속성** 중 하나 이상에 배정돼 있습니다 ({len(COLS)}/{len(COLS)}).\n")
for g in ["_엔티티/규칙"] + [x for x in D["attributes"] if not x.startswith("_")]:
    if g == "_엔티티/규칙":
        sel = [c for c in COLS if any(o.startswith("**") or o.startswith("rule") for o in owner[c])
               and not any(o.startswith("속성") for o in owner[c])]
        w(f"\n### 3.0 엔티티·유도규칙에 직접 쓰이는 컬럼 ({len(sel)})\n")
    else:
        sel = [c for c in COLS if f"속성:{g}" in owner[c]]
        w(f"\n### 3.{list(D['attributes']).index(g)+1} 속성 · {g} ({len(sel)})\n")
    w("| 컬럼 | 한글명 | 배정 | 종류 | distinct | 결측률 | 비고 |")
    w("| :--- | :--- | :--- | :-: | ---: | ---: | :--- |")
    for c in sel:
        kn, kind, dis, miss, tag = facts(c)
        w(f"| `{c}` | {kn} | {' / '.join(owner[c])} | {kind} | {dis:,} | {miss:.1%} | {tag} |")

w("\n> 📌 **`itm_nm` 은 두 역할을 합니다** — `FundClass` 의 **레이블**이면서 "
  "`ShareClass`(종류X/클래스X 파싱)와 `assetClass`(괄호 표기) 유도의 **출처**입니다.\n>")
w("> 📌 **성과 9컬럼은 판정을 공유합니다** — `fd_yr1_ern_r` 의 `missing_patterns`"
  "(접미결측/전무/구멍)이 `applies_to` 로 9개 전체에 적용됩니다. 표에는 대표 컬럼에만 표시됩니다.\n>")
w(f"> ⚠️ **`itm_abrv_nm` distinct {ABRV_N:,} < `itm_no` {N_ITM:,}** — 약어명 {N_ITM-ABRV_N:,}건이 종목 여럿에 "
  "대응합니다. **이름은 유일키가 아닙니다** (노트 §D.11).\n")

w("\n---\n")
w("## 4. 클래스 계층 — 개체가 아니라 하위클래스\n")
w("> FIBO 원칙: 펀드 **유형**은 `owl:Class` 하위클래스이지 개체가 아닙니다. "
  "반면 **클래스(종류형)** 는 `FundShareClassUnit` 독립 개체입니다.\n")
w("```")
ch = D["class_hierarchy"].get("Fund", {})
w("Fund")
for i, (k, v) in enumerate(ch.items()):
    last = i == len(ch) - 1
    w(f" {'└─' if last else '├─'} {k}")
    for j, x in enumerate(v or []):
        w(f" {'   ' if last else ' │ '}  {'└─' if j == len(v) - 1 else '├─'} {x}")
w("```\n")
w("**유도 규칙**\n")
w("| 규칙 | 축 | 판정률/해당 |")
w("| :--- | :--- | :--- |")
for k, v in D["derivation_rules"].items():
    if k.startswith("_"): continue
    w(f"| `{k}` | {(v or {}).get('축','')} | {(v or {}).get('판정률') or (v or {}).get('해당','')} |")

w("\n---\n")
w("## 5. 아직 못 붙인 것 — 워크샵 결정 필요\n")
w("""| # | 항목 | 상태 |
| :-: | :--- | :--- |
| 1 | **운용사·수탁사 이름** — 코드 67·18종만 있고 이름 컬럼 없음 | 외부 매핑 필요 (금투협 공시) |
| 2 | **`FundAttribute` 축 15개의 의미** — 12축이 기존 컬럼과 대응 확인 | 세분축 `W`·`T`·`N`·`S` 만 값어치. 원본 코드표 필요 |
| 3 | **상장지수 펀드 23종이 국내ETF와 중복** — ID 로는 0건 | 같은 개체로 병합할지 (§G.1) |
| 4 | **Benchmark 를 독립 개체로 세울지** — 국내ETF와 17종 통용 | 세우면 펀드↔ETF 교차 질의 가능 |
| 5 | **Custodian 채택 여부** — 공모펀드에만 있는 관계 | 다른 3개 테이블에 대응 컬럼 없음 |
| 6 | `axis_classDifferentiation` 축의 정의 | 🔴 정답 라벨이 같은 펀드 안에서 갈림 → 주최 측 확인 필요 (§7) |
| 7 | `axis_issuanceType` 유도 규칙 | `fd_set_pcd '20'` 혼재 · UnitType 표본 1건으로 판정 불가 (§7) |
""")

# ── 6. 값 정규화 규칙 (런타임 가드레일이 읽는 것) ──────────────────────
NORM = D.get("normalization") or {}
w("\n---\n")
w("## 6. 값 정규화 규칙 — 조회 전에 적용해야 하는 것\n")
w("> 런타임 가드레일이 `normalization` 에서 읽습니다. **여기 없으면 적용되지 않습니다.**\n")
w(f"`trim_columns` {len(NORM.get('trim_columns') or [])}컬럼 (공백 제거)\n")
for key, title in [
    ("dummy_as_missing", "더미를 결측으로"),
    ("numeric_string_columns", "숫자형이 소수점 문자열로 저장됨"),
    ("contaminated_rows", "따옴표로 컬럼이 밀린 행"),
    ("value_variants", "같은 뜻인데 표기가 갈리는 값"),
    ("invalid_values", "도메인 범위를 벗어난 값"),
    ("constant_columns", "정보량이 0인 컬럼"),
]:
    v = NORM.get(key)
    if not isinstance(v, dict):
        continue
    w(f"\n### 6.{[k for k in NORM if k != 'trim_columns'].index(key)+1} `{key}` — {title}\n")
    if v.get("_note"):
        w("> " + str(v["_note"]).strip().replace("\n", "\n> ") + "\n")
    for k2, v2 in v.items():
        if k2 == "_note":
            continue
        if isinstance(v2, list):
            w(f"- **{k2}**: " + (", ".join(f"`{x}`" for x in v2) if v2 else "—"))
        elif isinstance(v2, dict):
            w(f"- **{k2}**:")
            for k3, v3 in v2.items():
                alt = ", ".join(f"`{x}`" for x in v3) if isinstance(v3, list) and v3 else "—"
                w(f"    - `{k3}` ← {alt}")
        else:
            w(f"- **{k2}**: {v2}")
    w("")

# ── 7. 주최 측 6축 매핑 ────────────────────────────────────────────────
AX = D.get("axis_mapping") or {}
if AX:
    w("\n---\n")
    w("## 7. 주최 측 6축 매핑 — 확정된 것만\n")
    if AX.get("_note"):
        w("> " + str(AX["_note"]).strip().replace("\n", "\n> ") + "\n")
    w("| 축 | 출처 | 순도 | 근거등급 | 상태 |")
    w("| :--- | :--- | :--- | :-: | :--- |")
    for k, v in AX.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        w(f"| `{k}` | {v.get('출처', '—')} | {v.get('순도', '—')} | "
          f"{v.get('evidence_grade', '—')} | {v.get('상태', '✅ 확정')} |")
    for k, v in AX.items():
        if k.startswith("_") or not isinstance(v, dict) or not v.get("매핑"):
            continue
        w(f"\n**`{k}` 매핑표**\n")
        w("| 축값 | 컬럼값 |")
        w("| :--- | :--- |")
        for tgt, vals in v["매핑"].items():
            shown = ", ".join("`NULL`" if x is None else f"`{x}`" for x in vals)
            w(f"| {tgt} | {shown} |")
        if v.get("주의"):
            w("\n> " + str(v["주의"]).strip().replace("\n", "\n> ") + "\n")
    if AX.get("_미확정"):
        w("\n### 7.x 미확정 — 규칙을 만들기 전 단계\n")
        for k, v in AX["_미확정"].items():
            w(f"- **`{k}`** — {str(v).strip()}")
        w("")

# ── 8. 질의 규칙 ───────────────────────────────────────────────────────
QR = D.get("query_rules") or {}
if QR:
    w("\n---\n")
    w("## 8. 질의 규칙 — SQL 조각\n")
    for k, v in QR.items():
        if k.endswith("_근거") or k.endswith("_검증") or k.endswith("_주의"):
            continue
        w(f"**{k}**\n")
        w("```sql")
        w(str(v).strip())
        w("```")
        for suf in ("_근거", "_검증", "_주의"):
            if QR.get(k + suf):
                w("> " + str(QR[k + suf]).strip().replace("\n", "\n> ") + "\n")
        w("")

Path("docs/eda/public_funds_entity_map.md").write_text("\n".join(L), encoding="utf-8")
print("✅ docs/eda/public_funds_entity_map.md")
print(f"   컬럼 배정 {len(owner)}/{len(COLS)} · 엔티티 {len(D['entities'])} · 속성그룹 "
      f"{len([g for g in D['attributes'] if not g.startswith('_')])}")
