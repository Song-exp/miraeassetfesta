# -*- coding: utf-8 -*-
"""코드북(fund_country_tag.csv · fund_attr_code.csv) → shared/fund_country_auto.yaml · shared/fund_attribute_auto.yaml (생성물).

KG 1R S3 — 펀드별속성 태그 축(prfd_attr_cds, 다중값 콤마 컬럼)을 KG 개체로. alias 는 `match: token`(빌더가
','||col||',' LIKE '%,raw,%' 확정식으로 검증·사영). 국가 노드는 태그 유무와 무관하게 코드북 전 국가에 존재하고,
기본모수(판매중·공모)에서 태그가 0행이면 `tag_sparse: true` — 런타임이 이름 폴백(itm_nm LIKE)을 병기한다.
설정형태 축(C)은 사용자 어휘가 '개방형·폐쇄형·단위형·추가형' 이라 `synonyms` 에 이름+'형' 을 둔다(축 규칙, 이름 하드코딩 아님).

    python scripts/gen_fund_attribute_yaml.py
"""
import csv
import os
import sqlite3
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CB = os.path.join(ROOT, "ontology", "codebooks")
SHARED = os.path.join(ROOT, "ontology", "shared")
DB = os.path.join(ROOT, "data", "financial_products.db")
SPARSE_ROWS = 1
AS_OF = "2026-08-22"
BASE = "sale_yn='판매중' AND prvo_pbff_desc='공모'"


def base_count(con, tag):
    return con.execute(f"select count(*) from public_funds where {BASE} and ','||prfd_attr_cds||',' like ?",
                       (f"%,{tag},%",)).fetchone()[0]


def alias(raw):
    return {"table": "public_funds", "column": "prfd_attr_cds", "raw": raw, "match": "token", "source": "codebook",
            "evidence": "fund_attr_code/fund_country_tag.csv (prfd_attr_search_text 인접쌍 도출, zrin_attr_nms 검증)"}


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    countries = {}
    with open(os.path.join(CB, "fund_country_tag.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            iso, name = r["iso3"].strip(), r["name_ko"].strip()
            n = base_count(con, iso)
            countries[f"Country_{iso}"] = {
                "label_ko": name, "label_en": iso, "axis": "country", "n_rows_all": int(r["n_rows"]),
                "n_rows_base": n, "tag_sparse": n < SPARSE_ROWS, "aliases": [alias(iso)]}
    attrs = {}
    for r in csv.DictReader(open(os.path.join(CB, "fund_attr_code.csv"), encoding="utf-8-sig")):
        # 🔴 2026-09-04 — `confirmed_low_n`(표본 적으나 검증률 1.000)도 등록한다. 종전 완전일치 비교가
        #    이름에 confirmed 가 든 이 상태까지 잘라내, 판매중·공모에서 실제로 쓰이는 태그 12종이
        #    접지되지 않았다(물 4행·조선(해운/선박) 4행·에너지(수소) 2행 …). 표본이 적은 태그일수록
        #    이름으로 못 찾으므로 접지를 빼는 이유가 아니라 더 필요한 이유다. 반영 후 실사용 192/192 접지.
        # 🔴 2026-09-04 — `confirmed_low_n` 은 **기본모수에서 실제로 쓰이는 것만** 등록한다.
        #    ⓐ 종전 완전일치 비교가 이 상태를 통째로 잘라, 판매중·공모에서 쓰이는 태그 12종이
        #       접지되지 않았다(물 4행·조선(해운/선박) 4행·에너지(수소) 2행 …).
        #    ⓑ 그렇다고 31종 전부 받으면 안 된다 — n_selling=0 인 태그는 걸어봐야 0행인데
        #       라벨이 흔한 낱말이면 질문을 가로챈다(실측: M108 '모펀드' 가 "…의 모펀드는 뭐야?" 를
        #       태그 필터로 접지해 결과 0행 · test_snapshot_round6 고정선 이탈).
        _st = r.get("status", "confirmed")
        if not _st.startswith("confirmed") or (_st != "confirmed" and int(r.get("n_selling") or 0) == 0):
            continue
        code, name, axis = r["code"].strip(), r["name"].strip(), r["axis"].strip()
        node = {"label_ko": name, "axis": axis, "axis_name": r["axis_name"].strip(),
                "n_rows_selling": int(r["n_selling"] or 0), "aliases": [alias(code)]}
        if axis == "C":
            node["synonyms"] = [name + "형"]
        attrs[f"FundAttr_{code}"] = node
    head = ("# GENERATED — 편집 금지. 재생성: python scripts/gen_fund_attribute_yaml.py\n"
            f"# source=ontology/codebooks/fund_country_tag.csv · fund_attr_code.csv — as_of={AS_OF}\n")
    docs = {
        "fund_country_auto.yaml": {
            "entity": "Country",
            "description": "펀드 투자국가 태그(prfd_attr_cds ISO3 토큰) — 지역 계층(Region)과 별개 축. closure 대상 아님(권역 후손 전개는 Region 이 맡는다)",
            "property": "investsInCountry", "generated": True, "as_of": AS_OF, "nodes": countries},
        "fund_attribute_auto.yaml": {
            "entity": "FundAttribute",
            "description": "펀드별속성 태그(prfd_attr_cds) 15축 — 설정형태(C)·판매채널(D)·세제(F/G)·구조(M)·테마(N)·섹터(O)·스타일(P)·전략(S)·TDF(T)·지역구분(V/W)",
            "property": "hasAttribute", "generated": True, "as_of": AS_OF, "nodes": attrs},
    }
    for fname, doc in docs.items():
        path = os.path.join(SHARED, fname)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(head)
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=200)
        print(f"{fname}: nodes {len(doc['nodes'])}")


if __name__ == "__main__":
    main()
