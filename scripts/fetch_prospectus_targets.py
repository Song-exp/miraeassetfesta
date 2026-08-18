# -*- coding: utf-8 -*-
"""투자설명서 표적 수집 (P2 선발대) — 문서 URL 은 결정적: funddoctor file_gb=R2/R3.

표적 3종
  (a) 수탁사 18코드 × 대표 2펀드 → 간이투자설명서(R3)에서 신탁업자(수탁사) 법인명 추출
  (b) fd_set_pcd='20' 표본 30 → 추가형/단위형 문구로 ⑬ 확정 시도
  (c) 펀드명 '국민성장' → 투자설명서(R2) — 예시질의 2번 대비

산출: data/external/miraeasset_web/prospectus/*.pdf (+.txt)
      trustee_names_observed.csv · issu20_doc_check.csv
"""
import re
import sqlite3
import time
from pathlib import Path

import pandas as pd
import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "miraeasset_web"
PDF_DIR = OUT / "prospectus"
PDF_DIR.mkdir(exist_ok=True)
URL = "https://file.funddoctor.co.kr/app/file_download.asp?memb_cd=7070&file_gb={gb}&pfund_cd={cd}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
SLEEP = 1.0

con = sqlite3.connect(ROOT / "data" / "financial_products.db")
S = requests.Session()
S.headers["User-Agent"] = UA


def fetch_pdf(itm_no, gb):
    p = PDF_DIR / f"{itm_no}_{gb}.pdf"
    if p.exists():
        return p
    r = S.get(URL.format(gb=gb, cd=itm_no), timeout=40)
    time.sleep(SLEEP)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    p.write_bytes(r.content)
    return p


def pdf_text(p, max_pages=12):
    try:
        rd = PdfReader(str(p))
        t = "\n".join((pg.extract_text() or "") for pg in rd.pages[:max_pages])
        (p.with_suffix(".txt")).write_text(t, encoding="utf-8")
        return t
    except Exception as e:
        print("  parse err", p.name, str(e)[:60])
        return ""


# (a) 수탁사 코드별 대표 2펀드
tr = pd.read_sql("""
with base as (
  select distinct trusc_xtn_itt_cd cd, itm_no, itm_abrv_nm, sale_yn,
         coalesce(thco_sale_yn,'') thco
  from public_funds where trusc_xtn_itt_cd is not null and itm_no like 'KR%'
), r as (
  select *, row_number() over (partition by cd
      order by (sale_yn='판매중') desc, (thco='Y') desc, itm_no) rn from base)
select * from r where rn <= 2""", con)
tr["cd"] = tr.cd.str.strip()

TRUST_RE = re.compile(
    r"(?:신탁업자|수탁회사|수탁은행)[^가-힣A-Za-z]{0,10}"
    r"([가-힣A-Za-z0-9 ]{2,30}?(?:은행|증권|공사))")

rows = []
for _, r in tr.iterrows():
    p = fetch_pdf(r.itm_no, "R3") or fetch_pdf(r.itm_no, "R2")
    name = ""
    if p:
        t = pdf_text(p)
        m = TRUST_RE.search(t)
        if m:
            name = m.group(1).strip()
    rows.append({"trusc_xtn_itt_cd": r.cd, "itm_no": r.itm_no,
                 "fund_nm": r.itm_abrv_nm, "trustee_observed": name,
                 "doc": p.name if p else "다운로드 실패"})
    print(f"(a) {r.cd} {r.itm_no} → {name or '미추출'}")
tdf = pd.DataFrame(rows)
tdf.to_csv(OUT / "trustee_names_observed.csv", index=False, encoding="utf-8-sig")

# (b) '20' 표본 30
s20 = pd.read_sql("""
select distinct itm_no, itm_abrv_nm from public_funds
where fd_set_pcd='20' and sale_yn='판매중' and thco_sale_yn='Y'
order by itm_no limit 30""", con)
rows = []
for _, r in s20.iterrows():
    p = fetch_pdf(r.itm_no, "R3") or fetch_pdf(r.itm_no, "R2")
    verdict = ""
    if p:
        t = pdf_text(p)
        has_unit = bool(re.search(r"단위형", t))
        has_add = bool(re.search(r"추가형", t))
        verdict = "단위형" if has_unit and not has_add else \
                  "추가형" if has_add and not has_unit else \
                  "양쪽언급" if has_unit and has_add else "미언급"
    rows.append({"itm_no": r.itm_no, "fund_nm": r.itm_abrv_nm,
                 "doc_verdict": verdict, "doc": p.name if p else "다운로드 실패"})
    print(f"(b) {r.itm_no} → {verdict}")
s20df = pd.DataFrame(rows)
s20df.to_csv(OUT / "issu20_doc_check.csv", index=False, encoding="utf-8-sig")
print("\n(b) 요약:", s20df.doc_verdict.value_counts().to_dict())

# (c) 국민성장 펀드 — 전 클래스 R2
km = pd.read_sql("""
select distinct itm_no, itm_abrv_nm from public_funds
where itm_nm like '%국민성장%' or itm_abrv_nm like '%국민성장%'""", con)
for _, r in km.iterrows():
    p = fetch_pdf(r.itm_no, "R2")
    if p:
        pdf_text(p, max_pages=40)
    print(f"(c) {r.itm_no} {r.itm_abrv_nm} → {'OK' if p else '실패'}")

print("\n수탁사 코드별 관측 요약:")
agg = tdf[tdf.trustee_observed != ""].groupby("trusc_xtn_itt_cd") \
    .trustee_observed.agg(lambda s: ";".join(sorted(set(s))))
print(agg.to_string())
