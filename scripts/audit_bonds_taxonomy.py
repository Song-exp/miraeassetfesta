# -*- coding: utf-8 -*-
"""채권 분류 전수조사 — "제대로 분류되지 않은 값" 을 찾는다.

audit_bonds_claims.py 는 columns 칸의 **문서 수치**를, audit_bonds_rules.py 는 안내판의 **조건식 수치**를 재현한다.
이 스크립트는 셋째 층을 본다 — **분류 도달성(reachability)**: DB 에 실재하는 값 하나하나가
라우팅·종류 확정식·동의어·구조 판정에 닿는가. 닿지 않는 값은 질문이 왔을 때
"그런 채권 없습니다"(사실 왜곡) 또는 없는 축을 있는 컬럼으로 메꾸는 답으로 나간다 — 환각의 최대 원천.

전수: 표본을 쓰지 않는다. 분류 컬럼의 distinct 값 전건 × 선언 전건.
사용: python scripts/audit_bonds_taxonomy.py   (불일치가 있으면 exit 1)
"""
import os
import sys
import re
import sqlite3
import yaml

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect("data/financial_products.db")
con.create_function("REGEXP", 2, lambda p, s: 1 if s is not None and re.search(p, s) else 0)
DOC = yaml.safe_load(open("ontology/enums/domestic_bonds.yaml", encoding="utf-8"))
VOCAB = yaml.safe_load(open("ontology/enums/domestic_bonds.vocab.yaml", encoding="utf-8"))["value_vocab"]
B = "domestic_bonds"

findings = []   # (심각도, 층, 항목, 사실)


def bad(sev, layer, item, fact):
    findings.append((sev, layer, item, fact))


def q1(sql, *a):
    return con.execute(sql, a).fetchone()[0]


def qall(sql, *a):
    return con.execute(sql, a).fetchall()


def _rule(v):
    if isinstance(v, dict):
        return " ".join(str(v.get(k, "")) for k in ("text", "evidence") if v.get(k))
    return v or ""


QR = {k: _rule(v) for k, v in DOC["query_rules"].items()}

# 분류 컬럼 — "이 값으로 채권을 고를 수 있어야 하는" 범주형 축 전부.
# 🔴 값을 어떻게 물어보는지가 컬럼마다 다르다. 종류 낱말은 사람이 홀로 말하지만("국고채 알려줘"),
#    속성 값은 상품 명사를 달고 말한다("AAA **채권** 알려줘" — "AAA 알려줘" 라고 묻는 사람은 없다).
#    문형을 하나로 통일하면 속성 컬럼이 전부 '미특정' 으로 잡혀 가짜 결함이 15건 나온다(2026-09-06 초판).
KIND_COLS = ["bd_knd", "std_pd_mcls_nm", "std_pd_scls_nm"]
ATTR_COLS = ["bd_intp_tcd", "bd_inrt_tcd", "bd_ofr_tcd", "pd_risk_nm",
             "pd_exg_mkt", "pd_pen_tr_yn", "crd_grd", "curr_cd", "pd_ctry_cd"]
CLASS_COLS = KIND_COLS + ATTR_COLS

print("=" * 100)
print("채권 분류 전수조사 — 도달성·정합성")
print("=" * 100)

# ══ T1. 라우팅 도달성 (전수) ═══════════════════════════════════════════════════
# 분류 컬럼의 값 전건 + synonyms 키 전건으로 "<값> 알려줘" 를 만들어 실제 라우터에 통과시킨다.
print("\n[T1] 라우팅 도달성 — 값 전건이 domestic_bonds 로 라우팅되는가")
from runtime.loader import load_context      # noqa: E402
from runtime.router import route             # noqa: E402

ctx = load_context()
terms = []
for c in CLASS_COLS:
    tail = " 알려줘" if c in KIND_COLS else " 채권 알려줘"
    for (v,) in qall(f"SELECT DISTINCT TRIM({c}) FROM {B} WHERE {c} IS NOT NULL AND TRIM({c})<>''"):
        terms.append((f"값:{c}", v, tail))
for k in (DOC.get("synonyms") or {}):
    terms.append(("동의어", str(k), " 알려줘"))
# 리드 결정 대기 중인 도메인 간 다의어 — 숨기지 않고 '알려진 미결' 로 따로 센다 (workshop 절 참조)
ROUTING_KNOWN_AMBIGUOUS = {"MBS"}
t1_bad = t1_known = 0
for kind, term, tail in terms:
    r = route(f"{term}{tail}", ctx)
    if term in ROUTING_KNOWN_AMBIGUOUS and r.tables != [B]:
        t1_known += 1
        continue
    if not r.decided:
        bad("🔴", "T1 라우팅", f"{kind} '{term}'", "미특정 → 4테이블 (근거문서 희석·FROM 오판)")
        t1_bad += 1
    elif r.tables != [B]:
        bad("🟡", "T1 라우팅", f"{kind} '{term}'", f"→ {r.tables} ({r.why})")
        t1_bad += 1
print(f"  대상 {len(terms)}건 · 미달 {t1_bad}건 · 알려진 미결 {t1_known}건(MBS — workshop)")

# ══ T2. 동의어 생존 (전수) ════════════════════════════════════════════════════
# 치환값이 DB 에서 실제로 행을 잡는가. 0행이면 죽은 동의어 = "없습니다" 단정의 원천.
print("\n[T2] 동의어 생존 — 치환값이 DB 에서 행을 잡는가")
COLCHK = ["bd_knd", "std_pd_mcls_nm", "std_pd_scls_nm", "bd_intp_tcd", "bd_inrt_tcd",
          "bd_ofr_tcd", "crd_grd", "pd_pbcm"]
# 🔴 동의어에는 두 종류가 있다. **값 동의어**(통안채 → 통화안정채권)는 DB 값을 가리키므로 0행이면 죽은
#    동의어다. **축 동의어**(만기 → 상환일자 · 표면금리 → 표면이자율)는 컬럼의 한국어 이름을 가리키는
#    측정축 낱말이라 DB 값으로는 애초에 0행이다 — 이걸 결함으로 세면 안 된다(2026-09-06 초판이 5건 오탐).
AXIS_NAMES = {str(spec.get("korean_name", "")).split("(")[0].strip()
              for spec in (DOC.get("columns") or {}).values() if isinstance(spec, dict)}
AXIS_NAMES |= {"듀레이션", "잔존일수", "상환일자", "표면이자율", "적용신용등급"}
t2_bad = t2_axis = 0
for k, v in (DOC.get("synonyms") or {}).items():
    v = str(v)
    if v in AXIS_NAMES:
        t2_axis += 1
        continue
    hit = {}
    for c in COLCHK:
        n = q1(f"SELECT COUNT(*) FROM {B} WHERE TRIM({c})=?", v)
        if n:
            hit[c] = n
    n_nm = q1(f"SELECT COUNT(*) FROM {B} WHERE pd_nm LIKE ?", f"%{v}%")
    if n_nm:
        hit["pd_nm~"] = n_nm
    if not hit:
        bad("🔴", "T2 동의어", f"{k} → {v}", "어느 컬럼에도 0행 — 죽은 동의어")
        t2_bad += 1
print(f"  대상 {len(DOC.get('synonyms') or {})}건 (축 동의어 {t2_axis} 제외) · 죽은 것 {t2_bad}건")

# ══ T3. 종류 확정식 커버리지 (전수) ═══════════════════════════════════════════
# bd_knd 32값 + 소분류 13값이 kind_filters 확정식 어느 하나에는 잡히는가.
print("\n[T3] 종류 확정식 커버리지 — bd_knd·소분류 값 전건이 확정식에 잡히는가")
KF = DOC["kind_filters"]
sqls = [(t["token"], t["sql"]) for t in KF["tokens"]]
t3_bad = 0
for col in ("bd_knd", "std_pd_scls_nm"):
    vals = [v for (v,) in qall(
        f"SELECT DISTINCT TRIM({col}) FROM {B} WHERE {col} IS NOT NULL AND TRIM({col})<>''")]
    for v in vals:
        n_all = q1(f"SELECT COUNT(DISTINCT pd_no) FROM {B} WHERE TRIM({col})=?", v)
        covered = [tok for tok, s in sqls
                   if q1(f"SELECT COUNT(*) FROM {B} WHERE TRIM({col})=? AND ({s})", v)]
        by_name = [tok for tok, _ in sqls if tok in v]   # 질문에 값 이름을 그대로 썼을 때 잡히는 토큰
        if not covered and not by_name:
            bad("🟡", "T3 확정식", f"{col}='{v}' ({n_all}종목)",
                "kind_filters 어느 토큰에도 안 잡힘 — 강제 필터 미발동")
            t3_bad += 1
n_null = q1(f"SELECT COUNT(*) FROM {B} WHERE COALESCE(TRIM(bd_knd),'')=''")
print(f"  미달 {t3_bad}건 · bd_knd 결측 {n_null}행(별도 판정)")

# ══ T4. 3중 분류 정합 (전수) ══════════════════════════════════════════════════
print("\n[T4] 3중 분류 정합 — 대분류 vs ISIN 접두")
PREFIX = DOC["name_encoding"]["isin_prefix"]
# 알려진 예외는 선언에서 읽는다 — 감사가 "새로 생긴 어긋남"만 남기도록 (name_encoding.isin_prefix_exceptions)
EXC = {(e["prefix"], e["mcls"]): e for e in (DOC["name_encoding"].get("isin_prefix_exceptions") or [])}
t4_bad = 0
for pre, expect in PREFIX.items():
    for got, n in qall(f"SELECT TRIM(std_pd_mcls_nm), COUNT(*) FROM {B} WHERE SUBSTR(pd_no,1,3)=? GROUP BY 1", pre):
        e = EXC.get((pre, got))
        if e is not None:
            if e.get("rows") != n:
                bad("🟡", "T4 정합", f"ISIN {pre} 예외 '{got}' 선언 {e.get('rows')}행", f"실측 {n}행")
                t4_bad += 1
        elif got != expect:
            bad("🟡", "T4 정합", f"ISIN {pre} → 선언 '{expect}'", f"실제 '{got}' {n}행")
            t4_bad += 1
holes = ",".join("?" * len(PREFIX))
for (p,) in qall(f"SELECT DISTINCT SUBSTR(pd_no,1,3) FROM {B} WHERE SUBSTR(pd_no,1,3) NOT IN ({holes})", *PREFIX):
    bad("🔴", "T4 정합", f"ISIN 접두 '{p}'", "선언표에 없는 접두 — 대분류 보완 불가")
    t4_bad += 1
print(f"  불일치 {t4_bad}건 (KR3 예외 3행은 선언에 기재됨)")

# ══ T5. 구조표시 CASE 커버리지 (전수) ═════════════════════════════════════════
print("\n[T5] 구조 판정 커버리지 — 특수구조 표기가 CASE 에 잡히는가")
m = re.search(r"CASE WHEN .*? END", QR["구조표시"], re.S)
CASE = m.group(0) if m else None
t5_bad = 0
if CASE:
    for flag, spec in DOC["name_encoding"]["special_structure_flags"].items():
        pat, exp = spec["pattern"], spec["count"]
        got = q1(f"SELECT COUNT(*) FROM {B} WHERE pd_nm REGEXP ?", pat)
        if got != exp:
            bad("🟡", "T5 구조", f"{flag} 선언 {exp}", f"실측 {got}")
            t5_bad += 1
        miss = q1(f"SELECT COUNT(*) FROM {B} WHERE pd_nm REGEXP ? AND ({CASE})=''", pat)
        if miss:
            ex = qall(f"SELECT TRIM(pd_nm) FROM {B} WHERE pd_nm REGEXP ? AND ({CASE})='' LIMIT 3", pat)
            bad("🔴", "T5 구조", f"{flag} {miss}행",
                f"패턴엔 걸리나 CASE 는 '' — 예: {[e[0] for e in ex]}")
            t5_bad += 1
    for flag, spec in DOC["name_encoding"]["esg_labels"].items():
        if not isinstance(spec, dict) or "pattern" not in spec:
            continue
        got = q1(f"SELECT COUNT(*) FROM {B} WHERE pd_nm REGEXP ?", spec["pattern"])
        if got != spec["count"]:
            bad("🟡", "T5 ESG", f"{flag} 선언 {spec['count']}", f"실측 {got}")
            t5_bad += 1
else:
    bad("🔴", "T5 구조", "구조표시 CASE", "규칙에서 CASE 를 못 꺼냄")
print(f"  불일치 {t5_bad}건")

# ══ T6. 값 사전 드리프트 (전수) ═══════════════════════════════════════════════
print("\n[T6] 값 사전 드리프트 — vocab.yaml vs DB distinct")
t6_bad = 0
for col, spec in VOCAB.items():
    declared = [str(v) for v in spec["values"]]
    actual = [str(v) for (v,) in qall(
        f"SELECT DISTINCT TRIM({col}) FROM {B} WHERE {col} IS NOT NULL AND TRIM({col})<>''")]
    for v in actual:
        if v not in declared:
            n = q1(f"SELECT COUNT(*) FROM {B} WHERE TRIM({col})=?", v)
            bad("🔴", "T6 값사전", f"{col}='{v}'", f"DB 에 있는데 vocab 미등재 ({n}행)")
            t6_bad += 1
    for v in declared:
        if v not in actual:
            bad("🟡", "T6 값사전", f"{col}='{v}'", "vocab 에 있는데 DB 0행")
            t6_bad += 1
    for v, n in (spec.get("counts") or {}).items():
        got = q1(f"SELECT COUNT(*) FROM {B} WHERE TRIM({col})=?", str(v))
        if got != n:
            bad("🟡", "T6 값사전", f"{col}='{v}' 선언 {n}", f"실측 {got}")
            t6_bad += 1
print(f"  불일치 {t6_bad}건 · 대상 컬럼 {len(VOCAB)}")

# ══ T7. 등급 표기 (전수) ══════════════════════════════════════════════════════
print("\n[T7] 신용등급 표기 — DB distinct vs 표준표")
CG = yaml.safe_load(open("ontology/shared/credit_grade.yaml", encoding="utf-8"))["nodes"]
std = {a["raw"] for n in CG.values() for a in (n.get("aliases") or [])}
t7_bad = 0
for (v,) in qall(f"SELECT DISTINCT TRIM(crd_grd) FROM {B} WHERE crd_grd IS NOT NULL AND TRIM(crd_grd)<>''"):
    if v not in std:
        n = q1(f"SELECT COUNT(*) FROM {B} WHERE TRIM(crd_grd)=?", v)
        bad("🔴", "T7 등급", f"crd_grd='{v}'", f"표준표에 없는 표기 ({n}행)")
        t7_bad += 1
print(f"  비표준 표기 {t7_bad}건")

# ══ T8. 위험등급 정합 (전수) ══════════════════════════════════════════════════
print("\n[T8] 위험등급 정합 — 코드 ↔ 이름 1:1")
EXP = {"11": "매우높은위험(1등급)", "12": "높은위험(2등급)", "13": "다소높은위험(3등급)",
       "14": "보통위험(4등급)", "15": "낮은위험(5등급)", "16": "매우낮은위험(6등급)", "00": "해당없음"}
t8_bad = 0
for gcd, nm, n in qall(f"SELECT TRIM(pd_risk_gcd), TRIM(pd_risk_nm), COUNT(*) FROM {B} GROUP BY 1,2"):
    if gcd not in EXP:
        bad("🔴", "T8 위험등급", f"코드 '{gcd}' {n}행", "선언(risk_grade 0~6)에 없는 코드")
        t8_bad += 1
    elif nm != EXP[gcd]:
        bad("🔴", "T8 위험등급", f"{gcd} ↔ '{nm}' {n}행", f"선언 대응은 '{EXP[gcd]}'")
        t8_bad += 1
for g, c in qall(f"SELECT TRIM(pd_risk_gcd), COUNT(DISTINCT TRIM(pd_risk_nm)) c FROM {B} GROUP BY 1 HAVING c>1"):
    bad("🔴", "T8 위험등급", f"코드 {g}", f"이름이 {c}종 — 1:1 위반")
    t8_bad += 1
print(f"  불일치 {t8_bad}건")

# ══ 보고 ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
if not findings:
    print("✅ 전수 도달성·정합성 불일치 0건")
    sys.exit(0)
red = [f for f in findings if f[0] == "🔴"]
print(f"불일치 {len(findings)}건 (🔴 {len(red)} · 🟡 {len(findings) - len(red)})")
print("=" * 100)
cur = None
for sev, layer, item, fact in sorted(findings, key=lambda x: (x[0] != "🔴", x[1])):
    if layer != cur:
        print(f"\n── {layer} ──")
        cur = layer
    print(f"  {sev} {item}  →  {fact}")
sys.exit(1)
