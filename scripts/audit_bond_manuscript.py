# 채권 최종 원고(docs/기술제안서/28_채권_최종원고.md)가 인용한 수치를 층별로 재실측한다.
#
# 왜 있나 — 같은 수치가 28 · 04 · NUMBERS.md · 회신 네 곳에 흩어져 있어서,
#          yaml·온톨로지를 고칠 때마다 손으로 훑으면 반드시 하나를 놓친다.
#          이 스크립트는 어긋난 칸만 찍는다. 찍힌 칸만 고치면 된다.
#
# 쓰는 법  ./.venv/Scripts/python.exe scripts/audit_bond_manuscript.py
#          --quiet  불일치만 출력
#
# 층 여섯  ① DB 실측  ② yaml·ttl 선언  ③ KG  ④ 프롬프트 분량  ⑤ 결정층 가드  ⑥ 외부 수집·평가셋
#
# 🔴 KG(③)와 ttl(②)은 `build_ontology.py` 를 다시 돌려야 값이 바뀐다.
#    yaml 만 고쳤다면 ②의 선언 수와 ④의 프롬프트 분량만 움직인다.
import io, os, re, sys, glob, json, sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, "src")
sys.path.insert(0, ".")
QUIET = "--quiet" in sys.argv

DOC = "docs/기술제안서/28_채권_최종원고.md"
YAML = "ontology/enums/domestic_bonds.yaml"
TTL = "ontology/bond_kr.ttl"
DB = "data/financial_products.db"

rows = []  # (층, 항목, 문서값, 실측값, ok)


def chk(layer, name, doc_value, got):
    rows.append((layer, name, doc_value, got, doc_value == got))


# ─────────────────────────────────────────────────────────────
# ① DB 실측 — 원고 본문이 인용한 수치
# ─────────────────────────────────────────────────────────────
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
one = lambda s: c.execute(s).fetchone()[0]
B = "FROM domestic_bonds"
L = "①DB"

chk(L, "전체 행", 21882, one(f"SELECT COUNT(*) {B}"))
chk(L, "컬럼 수", 58, len(c.execute(f"SELECT * {B} LIMIT 1").description))
chk(L, "종목 수 COUNT(DISTINCT pd_no)", 20497, one(f"SELECT COUNT(DISTINCT pd_no) {B}"))
chk(L, "신용등급 결측 행", 4020, one(f"SELECT COUNT(*) {B} WHERE TRIM(COALESCE(crd_grd,''))=''"))
chk(L, "신용등급 결측률 %", 18.4, round(one(f"SELECT COUNT(*) {B} WHERE TRIM(COALESCE(crd_grd,''))='' ") / one(f"SELECT COUNT(*) {B}") * 100, 1))
chk(L, "crd_grd 실재 표기 종수", 15, one(f"SELECT COUNT(DISTINCT TRIM(crd_grd)) {B} WHERE TRIM(COALESCE(crd_grd,''))<>''"))
chk(L, "위험등급 '00' 행", 19, one(f"SELECT COUNT(*) {B} WHERE TRIM(pd_risk_gcd)='00'"))
chk(L, "6등급 행", 8929, one(f"SELECT COUNT(*) {B} WHERE TRIM(pd_risk_gcd)='16'"))
chk(L, "6등급 비율 %", 40.8, round(one(f"SELECT COUNT(*) {B} WHERE TRIM(pd_risk_gcd)='16'") / one(f"SELECT COUNT(*) {B}") * 100, 1))
chk(L, "장내 행", 17746, one(f"SELECT COUNT(*) {B} WHERE TRIM(pd_exg_mkt)='장내'"))
chk(L, "장외 행", 4136, one(f"SELECT COUNT(*) {B} WHERE TRIM(pd_exg_mkt)='장외'"))
chk(L, "장내 종가 유효", 1270, one(f"SELECT COUNT(*) {B} WHERE exg_close_price IS NOT NULL AND exg_close_price<>0"))
chk(L, "장내 종가 0값(거래없음)", 16476, one(f"SELECT COUNT(*) {B} WHERE exg_close_price=0"))
chk(L, "판매정보 있는 행(buy_yield)", 634, one(f"SELECT COUNT(*) {B} WHERE buy_yield IS NOT NULL"))
chk(L, "판매 축 종목", 326, one(f"SELECT COUNT(DISTINCT pd_no) {B} WHERE buy_yield IS NOT NULL"))
chk(L, "판매정보 통째 NULL 행", 21248, one(f"SELECT COUNT(*) {B} WHERE buy_yield IS NULL"))
chk(L, "평가정보 통째 NULL 행", 16, one(f"SELECT COUNT(*) {B} WHERE dur IS NULL AND cov IS NULL AND dirty IS NULL"))
chk(L, "고정금리", 20904, one(f"SELECT COUNT(*) {B} WHERE TRIM(bd_inrt_tcd)='고정금리'"))
chk(L, "변동금리", 830, one(f"SELECT COUNT(*) {B} WHERE TRIM(bd_inrt_tcd)='변동금리'"))
chk(L, "고정+변동금리", 148, one(f"SELECT COUNT(*) {B} WHERE TRIM(bd_inrt_tcd)='고정+변동금리'"))
chk(L, "할인채", 689, one(f"SELECT COUNT(*) {B} WHERE TRIM(bd_intp_tcd)='할인채'"))
chk(L, "srfc_irt = 0", 579, one(f"SELECT COUNT(*) {B} WHERE srfc_irt=0"))
chk(L, "pd_ctry_cd = KR", 21881, one(f"SELECT COUNT(*) {B} WHERE TRIM(pd_ctry_cd)='KR'"))
chk(L, "curr_cd = KRW", 21881, one(f"SELECT COUNT(*) {B} WHERE TRIM(curr_cd)='KRW'"))
chk(L, "구매가능 행", 21814, one(f"SELECT COUNT(*) {B} WHERE TRIM(curr_cd)='KRW' AND mat_dt>=20260824"))
chk(L, "구매가능 종목", 20431, one(f"SELECT COUNT(DISTINCT pd_no) {B} WHERE TRIM(curr_cd)='KRW' AND mat_dt>=20260824"))
chk(L, "공식예시#1 AA-이상 구매가능 종목", 15792,
    one(f"SELECT COUNT(DISTINCT pd_no) {B} WHERE TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-') AND TRIM(curr_cd)='KRW' AND mat_dt>=20260824"))
chk(L, "중복 종목(2~4행)", 1078, one(f"SELECT COUNT(*) FROM (SELECT pd_no {B} GROUP BY pd_no HAVING COUNT(*)>1)"))
chk(L, "중복 중 값이 다른 종목", 8, one(f"SELECT COUNT(*) FROM (SELECT pd_no {B} GROUP BY pd_no HAVING COUNT(*)>=2 AND COUNT(DISTINCT eval_price)>1)"))
chk(L, "중복 중 값이 같은 종목", 1070, one(f"SELECT COUNT(*) FROM (SELECT pd_no {B} GROUP BY pd_no HAVING COUNT(*)>=2 AND COUNT(DISTINCT eval_price)=1)"))
chk(L, "1등급 종목(구매가능)", 1394, one(f"SELECT COUNT(DISTINCT pd_no) {B} WHERE TRIM(pd_risk_gcd)='11' AND TRIM(curr_cd)='KRW' AND mat_dt>=20260824"))
chk(L, "C0 종목", 103, one(f"SELECT COUNT(DISTINCT pd_no) {B} WHERE TRIM(crd_grd)='C0'"))
chk(L, "발행사 DB distinct TRIM", 1818, one(f"SELECT COUNT(DISTINCT TRIM(pd_pbcm)) {B} WHERE TRIM(COALESCE(pd_pbcm,''))<>''"))
chk(L, "영구채 행(신종|영구)", 266, one(f"SELECT COUNT(*) {B} WHERE pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%'"))
chk(L, "dirty = eval_price", 21655, one(f"SELECT COUNT(*) {B} WHERE dirty IS NOT NULL AND dirty=eval_price"))
chk(L, "pd_pbcm 패딩 행", 21282, one(f"SELECT COUNT(*) {B} WHERE pd_pbcm<>TRIM(pd_pbcm)"))
chk(L, "종목명 distinct TRIM(이름은 식별자 아님)", 20499, one(f"SELECT COUNT(DISTINCT TRIM(pd_nm)) {B}"))
# 패딩 사례 — 은행채 2종 IN: TRIM 없으면 거의 다 놓친다
chk(L, "은행채 2종 IN — 무TRIM", 16, one(f"SELECT COUNT(*) {B} WHERE bd_knd IN ('일반은행채','특수은행채')"))
chk(L, "은행채 2종 IN — TRIM", 2031, one(f"SELECT COUNT(*) {B} WHERE TRIM(bd_knd) IN ('일반은행채','특수은행채')"))
# 부재 선언의 반례 — 지급주기 축은 국내ETF 에는 실재한다(테이블 단위 선언의 근거)
for v, exp in [("Q", 698), ("A", 306), ("M", 196), ("S", 8)]:
    chk(L, f"ETF pd_dvid_cycl '{v}'", exp, one(f"SELECT COUNT(*) FROM domestic_etfs WHERE TRIM(pd_dvid_cycl)='{v}'"))

# ─────────────────────────────────────────────────────────────
# ② yaml · ttl 선언
# ─────────────────────────────────────────────────────────────
L = "②선언"
import yaml as _yaml

raw = io.open(YAML, encoding="utf-8").read()
d = _yaml.safe_load(raw)
n = lambda k: len(d.get(k) or [])

chk(L, "yaml 줄 수", 1361, len(raw.splitlines()))
chk(L, "columns", 58, n("columns"))
chk(L, "query_rules", 49, n("query_rules"))
chk(L, "answer_rules", 21, n("answer_rules"))
cl = d.get("clarify") or {}
chk(L, "clarify 최상위 키", 4, len(cl))
chk(L, "clarify 항목 합", 14, sum(len(v) for v in cl.values()))
chk(L, "absent_properties", 8, n("absent_properties"))
chk(L, "forbidden_columns", 4, n("forbidden_columns"))
chk(L, "similarity_axes 축", 5, n("similarity_axes"))
chk(L, "gate_constants", 1, n("gate_constants"))
chk(L, "synonyms", 57, n("synonyms"))
qr = d.get("query_rules") or {}
chk(L, "query_rules 중 text/evidence 분리", 35,
    sum(1 for v in qr.values() if isinstance(v, dict) and "text" in v and "evidence" in v))
chk(L, "query_rules 중 enforce 슬롯", 2,
    sum(1 for v in qr.values() if isinstance(v, dict) and "enforce" in v))

t = io.open(TTL, encoding="utf-8").read()
chk(L, "bond_kr.ttl 줄 수", 50, len(t.splitlines()))
chk(L, "bond_kr.ttl 글자 수", 5866, len(t))
chk(L, "bond_kr.ttl ABSENT 줄", 11, t.count("# ABSENT"))

# ─────────────────────────────────────────────────────────────
# ③ KG — build_ontology.py 를 다시 돌려야 바뀐다
# ─────────────────────────────────────────────────────────────
L = "③KG"
kga = "FROM kg_alias WHERE table_name='domestic_bonds'"
chk(L, "채권 alias", 1840, one(f"SELECT COUNT(*) {kga}"))
chk(L, "채권 노드(distinct node_id)", 1839, one(f"SELECT COUNT(DISTINCT node_id) {kga}"))
chk(L, "발행사 alias", 1817, one(f"SELECT COUNT(*) {kga} AND column_name='pd_pbcm'"))
chk(L, "발행사 노드", 1816, one(f"SELECT COUNT(DISTINCT node_id) {kga} AND column_name='pd_pbcm'"))
chk(L, "신용등급 alias(접지)", 15, one(f"SELECT COUNT(*) {kga} AND column_name='crd_grd'"))
chk(L, "위험등급 alias", 7, one(f"SELECT COUNT(*) {kga} AND column_name='pd_risk_gcd'"))
chk(L, "통화 alias", 1, one(f"SELECT COUNT(*) {kga} AND column_name='curr_cd'"))
chk(L, "CreditGrade 선언 노드", 22, one("SELECT COUNT(*) FROM kg_node WHERE node_type='CreditGrade'"))
chk(L, "CreditGrade closure", 20, one(
    "SELECT COUNT(*) FROM kg_closure cl JOIN kg_node n ON cl.ancestor_id=n.node_id WHERE n.node_type='CreditGrade'"))
chk(L, "종목→발행사 closure", 2, one(
    "SELECT COUNT(*) FROM kg_closure cl JOIN kg_node a ON cl.ancestor_id=a.node_id "
    "JOIN kg_node dd ON cl.descendant_id=dd.node_id WHERE a.node_type='Security' AND dd.node_type='Organization'"))

# ─────────────────────────────────────────────────────────────
# ④ 프롬프트 분량 — yaml 을 고치면 여기가 먼저 움직인다
# ─────────────────────────────────────────────────────────────
L = "④프롬프트"
try:
    try:
        from runtime import loader
    except ImportError:
        from src.runtime import loader
    ctx = loader.load_context()
    T = ["domestic_bonds"]
    chk(L, "planner_context 자", 25750, len(ctx.planner_context(T)))
    chk(L, "answer_context 자", 3390, len(ctx.answer_context(T)))
    chk(L, "clarify_context 자", 1489, len(ctx.clarify_context(T)))
except Exception as e:
    rows.append((L, "런타임 로드", "측정", f"ERR {type(e).__name__}: {e}", False))

# ─────────────────────────────────────────────────────────────
# ⑤ 결정층 가드 — yaml 이 이름으로 지목한 pipeline.py 함수
#    (조립 헬퍼 3개는 제외한다. 세는 법을 여기 못박아 둔다.)
# ─────────────────────────────────────────────────────────────
L = "⑤가드"
HELPERS = {"build_grounding", "compose_answer", "normalize_table_names"}
src = io.open("src/runtime/pipeline.py", encoding="utf-8").read()
defined = set(re.findall(r"^\s*def\s+(\w+)", src, re.M))
named = set(re.findall(r"\b([a-z_]{6,})\b", raw))
guards = sorted(f for f in defined if f in named and not f.startswith("_") and f not in HELPERS)
chk(L, "가드(지목 함수 − 조립 헬퍼 3)", 36, len(guards))

# ─────────────────────────────────────────────────────────────
# ⑥ 외부 수집 · 평가셋
# ─────────────────────────────────────────────────────────────
L = "⑥재료"
ext = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ext_%'")]
chk(L, "외부 수집 합계 행", 1052478, sum(one(f"SELECT COUNT(*) FROM {t_}") for t_ in ext))
chk(L, "ext_etf_holdings", 75859, one("SELECT COUNT(*) FROM ext_etf_holdings"))
chk(L, "ext_ovs_etf_holdings", 906848, one("SELECT COUNT(*) FROM ext_ovs_etf_holdings"))
chk(L, "ext_fund_holdings", 59206, one("SELECT COUNT(*) FROM ext_fund_holdings"))
chk(L, "채권 몫 외부 테이블", 0, len([t_ for t_ in ext if "bond" in t_]))

tot = gold = zero = 0
for f in sorted(glob.glob("eval/*.jsonl")):
    for ln in io.open(f, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        j = json.loads(ln)
        tot += 1
        if j.get("gold_sql"):
            gold += 1
            if j.get("gold_rows") == 0:
                zero += 1
# 오답기록 사고 건수 — 원고 §1.5·§4.4 가 인용한다. 총괄표 행을 센다.
REC = "docs/기술제안서/채권_오답기록_2026-09-03.md"
try:
    rec = io.open(REC, encoding="utf-8").read()
    body = rec[rec.index("## §1."):rec.index("## §2.")]
    inc = len(re.findall(r"^\| \d+ \|", body, re.M))
    chk(L, "오답기록 사고 건수", 82, inc)
except Exception as e:
    rows.append((L, "오답기록 사고 건수", 82, f"ERR {type(e).__name__}", False))

chk(L, "평가셋 문항", 226, tot)
chk(L, "gold_sql 붙은 문항", 163, gold)
chk(L, "의도된 0행 문항(gold_rows=0)", 3, zero)

# gold_sql 전건 실행
okc = err = 0
for f in sorted(glob.glob("eval/*.jsonl")):
    for ln in io.open(f, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        s = json.loads(ln).get("gold_sql")
        if not s:
            continue
        try:
            c.execute(s).fetchall()
            okc += 1
        except Exception:
            err += 1
chk(L, "gold_sql 실행 성공", 163, okc)
chk(L, "gold_sql 실행 실패", 0, err)

# ─────────────────────────────────────────────────────────────
# 출력
# ─────────────────────────────────────────────────────────────
bad = [r for r in rows if not r[4]]
if not QUIET:
    cur = None
    for layer, name, doc, got, ok in rows:
        if layer != cur:
            print(f"\n── {layer} " + "─" * 40)
            cur = layer
        print(("  OK  " if ok else "  ⚠️  ") + f"{name:<38} 문서={doc:<12} 실측={got}")

print("\n" + "=" * 62)
if bad:
    print(f"⚠️  불일치 {len(bad)} / {len(rows)} — 원고의 아래 칸을 고칠 것\n")
    for layer, name, doc, got, _ in bad:
        print(f"   [{layer}] {name}:  문서 {doc}  →  실측 {got}")
    print(f"\n   고칠 자리: {DOC}  (같은 수치가 04_도메인_채권.md · docs/proposal/NUMBERS.md 에도 있으면 함께)")
    sys.exit(1)
print(f"✅ 원고 수치 전건 일치 — {len(rows)}건 검사 · 불일치 0")
print(f"   ① DB {sum(1 for r in rows if r[0]=='①DB')} · ② 선언 {sum(1 for r in rows if r[0]=='②선언')}"
      f" · ③ KG {sum(1 for r in rows if r[0]=='③KG')} · ④ 프롬프트 {sum(1 for r in rows if r[0]=='④프롬프트')}"
      f" · ⑤ 가드 {sum(1 for r in rows if r[0]=='⑤가드')} · ⑥ 재료 {sum(1 for r in rows if r[0]=='⑥재료')}")
