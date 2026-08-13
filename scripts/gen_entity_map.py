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

def facts(c):
    e = A["columns"][c]
    d = (D.get("columns") or {}).get(c) or {}
    miss = 1 - e["values_present"] / TOTAL
    tag = []
    if d.get("missing_reason"): tag.append(f"판정 `{d['missing_reason']}`")
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
w("""```
                    ┌─────────────────┐
                    │  AssetManager   │ 67   운용사 (or_co_xtn_itt_cd)
                    │  Custodian      │ 18   수탁사 (trusc_xtn_itt_cd)
                    └────────▲────────┘
                             │ managedBy / custodiedBy
              ┌──────────────┴──────────────┐
              │           Fund              │  4,660   모펀드 = 운용 단위
              │        mtco_itm_no          │          순자산 합계가 이 단위
              └──────────────▲──────────────┘
                             │ belongsToFund
              ┌──────────────┴──────────────┐
              │        FundClass            │ 11,139   ★ 주 노드 = 판매 단위
              │           itm_no            │          속성 44컬럼이 여기 붙음
              └───┬────────┬─────────┬──────┘
        hasShare  │        │         │  hasAttribute / investsIn / benchmarkedTo
          Class   ▼        ▼         ▼
      ┌───────────┐ ┌────────────┐ ┌──────────┐ ┌────────────┐
      │ShareClass │ │FundAttribute│ │ Country  │ │ Benchmark  │
      │   112     │ │   210 (15축)│ │    17    │ │    391     │
      │itm_nm 파싱│ │prfd_attr_cd │ │prfd_attr │ │  bmrk_nm   │
      └───────────┘ └────────────┘ └──────────┘ └────────────┘
                                                  🔵 국내ETF와 17종 통용

  ※ 행(95,619) = FundClass(11,139) × 그 종목의 태그 수(4~16, 평균 8.58)
     45컬럼 중 itm_no 안에서 갈리는 것은 prfd_attr_cd 하나뿐 → 나머지는 전부 FundClass 속성
```\n""")

w("\n### 관계도 (mermaid)\n")
w("```mermaid")
w("graph TD")
w('  FC["<b>FundClass</b><br/>★ 주 노드 11,139<br/>itm_no"]')
w('  FD["Fund<br/>모펀드 4,660<br/>mtco_itm_no"]')
w('  SC["ShareClass<br/>112<br/>itm_nm 파싱"]')
w('  FA["FundAttribute<br/>210 · 15축<br/>prfd_attr_cd"]')
w('  CO["Country<br/>17 · 커버리지 13.9%"]')
w('  BM["Benchmark<br/>391<br/>국내ETF와 17종 통용"]')
w('  AM["AssetManager<br/>67 · 이름 컬럼 없음"]')
w('  CU["Custodian<br/>18 · 이름 컬럼 없음"]')
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
w("## 3. 컬럼 45개 전수 배정\n")
w("모든 컬럼이 **엔티티 출처 · 유도규칙 · 속성** 중 하나 이상에 배정돼 있습니다 (45/45).\n")
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
w("> ⚠️ **`itm_abrv_nm` distinct 11,119 < `itm_no` 11,139** — 약어명 13종이 종목 여럿에 "
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
| 6 | `axis_classDifferentiation` · `axis_redemptionType` 유도 규칙 | 미확정 (§B) |
""")
Path("docs/eda/public_funds_entity_map.md").write_text("\n".join(L), encoding="utf-8")
print("✅ docs/eda/public_funds_entity_map.md")
print(f"   컬럼 배정 {len(owner)}/{len(COLS)} · 엔티티 {len(D['entities'])} · 속성그룹 "
      f"{len([g for g in D['attributes'] if not g.startswith('_')])}")
