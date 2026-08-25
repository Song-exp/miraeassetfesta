# -*- coding: utf-8 -*-
"""공모펀드 운용사 코드(or_co_xtn_itt_cd) ↔ 법인명 코드북 생성 — 2차 데이터(275종) 대응

원천 우선순위:
  1. 기존 `ontology/codebooks/asset_manager.csv` 의 확정 행 (금투협 회원사 코드·웹 관측) — 그대로 보존
  2. DB `ext_fund_page.mgmt_co_nm` (미래에셋증권 펀드상세 웹, 2026-08-18 관측) 을 itm_no 로 조인해
     코드별 최빈 법인명 채택 (점유율·표본수 기록)
  3. 둘 다 없으면 종목명 접두 최빈값(브랜드) — `status=derived` 로 표기, 법인명 아님

사용: python scripts/gen_asset_manager_codebook.py   (asset_manager.csv 를 덮어씀, 확정 행은 유지)
"""
import csv, sqlite3, collections, os, sys
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "financial_products.db")
OUT = os.path.join(ROOT, "ontology", "codebooks", "asset_manager.csv")
AS_OF = "2026-08-22"

existing = {}
with open(OUT, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        existing[r["code"]] = r

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = con.execute("""
    SELECT p.or_co_xtn_itt_cd, p.sale_yn, p.itm_nm, e.mgmt_co_nm
    FROM public_funds p LEFT JOIN ext_fund_page e ON e.itm_no = p.itm_no
""").fetchall()

by_code = collections.defaultdict(lambda: {"n": 0, "sel": 0, "web": collections.Counter(), "prefix": collections.Counter()})
for code, sale, nm, web in rows:
    b = by_code[code]; b["n"] += 1; b["sel"] += (sale == "판매중")
    if web: b["web"][web.strip()] += 1
    if nm: b["prefix"][nm.split()[0][:8]] += 1

out, stats = [], collections.Counter()
for code, b in sorted(by_code.items(), key=lambda x: -x[1]["n"]):
    if code in existing:
        r = dict(existing[code]); r["as_of"] = AS_OF
        r.setdefault("status", "confirmed"); r["status"] = r.get("status") or "confirmed"
        r["n_items"] = b["n"]; r["n_selling"] = b["sel"]
        out.append(r); stats["confirmed"] += 1; continue
    if b["web"]:
        name, cnt = b["web"].most_common(1)[0]; share = cnt / sum(b["web"].values())
        short = name.replace("자산운용", "").replace("(주)", "").replace("주식회사", "").strip()
        out.append({"code": code, "name": name, "short_name": short,
                    "source": f"미래에셋증권 펀드상세 웹 mgmt_co_nm 다수결 (표본 {sum(b['web'].values())}, 점유 {share:.0%}, 관측 2026-08-18)",
                    "as_of": AS_OF, "status": "web_majority" if share >= 0.8 else "web_ambiguous",
                    "n_items": b["n"], "n_selling": b["sel"]})
        stats["web"] += 1
    else:
        brand, cnt = (b["prefix"].most_common(1) or [("", 0)])[0]
        out.append({"code": code, "name": "", "short_name": brand,
                    "source": f"종목명 접두 최빈값 (점유 {cnt / max(b['n'],1):.0%}) — 법인명 아님", "as_of": AS_OF,
                    "status": "derived", "n_items": b["n"], "n_selling": b["sel"]})
        stats["derived"] += 1

fields = ["code", "name", "short_name", "source", "as_of", "status", "n_items", "n_selling"]
with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader()
    for r in out: w.writerow({k: r.get(k, "") for k in fields})
sel_cov = sum(r["n_selling"] for r in out if r["status"] != "derived") / max(sum(r["n_selling"] for r in out), 1)
print(f"코드 {len(out)}종 → confirmed {stats['confirmed']} · web {stats['web']} · derived {stats['derived']}")
print(f"판매중 행 기준 법인명 커버리지: {sel_cov:.1%}")
print("derived(법인명 없음):", [(r['code'], r['short_name'], r['n_selling']) for r in out if r['status']=='derived' and r['n_selling']][:20])
