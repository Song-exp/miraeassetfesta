# -*- coding: utf-8 -*-
"""시각화용 데이터 추출 — 온톨로지(스키마) · 지식그래프(개체) 두 벌.

HTML 설명자료가 CDN 없이 자기완결적이어야 하므로 데이터를 통째로 임베드한다.
바이트를 줄이려고 문자열은 인터닝(사전 + 인덱스)해서 배열로 낸다.

출력:
  build/viz_ontology.json   스키마 — 도메인 4 · 컬럼 330 · 개체 · 규칙 · 범주값
  build/viz_kg.json         개체 — kg_node 39,677 · kg_alias 62,577 · kg_edge · kg_closure

사용: python scripts/gen_viz_payload.py
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "financial_products.db"
BUILD = ROOT / "build"
DOMAINS = ["domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"]
KO = {"domestic_bonds": "국내채권", "domestic_etfs": "국내ETF",
      "overseas_etfs": "해외ETF", "public_funds": "공모펀드"}
EXT = {"ext_etf_holdings": "국내ETF 구성종목", "ext_ovs_etf_holdings": "해외ETF 구성종목",
       "ext_fund_holdings": "펀드 구성종목", "ext_fund_page": "펀드 상세페이지"}
EXT_OWNER = {"ext_etf_holdings": "domestic_etfs", "ext_ovs_etf_holdings": "overseas_etfs",
             "ext_fund_holdings": "public_funds", "ext_fund_page": "public_funds"}

VALUE_CAP = 200      # distinct 가 이보다 크면 개체로 보고 값 목록 대신 표본만


def s(v, n=900):
    if v is None:
        return None
    return str(v).replace("\n", " ").strip()[:n] or None


# ── 온톨로지 ─────────────────────────────────────────────────────────────
def build_ontology(con) -> dict:
    D = {d: yaml.safe_load((ROOT / "ontology" / "enums" / f"{d}.yaml").read_text(encoding="utf-8"))
         for d in DOMAINS}
    S = {}
    for p in sorted(glob.glob(str(ROOT / "ontology" / "shared" / "*.yaml"))):
        if "auto" in os.path.basename(p):
            continue
        S[os.path.basename(p)[:-5]] = yaml.safe_load(Path(p).read_text(encoding="utf-8"))

    meta = {}
    for t, c, ko, dt, nu in con.execute(
            "select table_name,column_name,korean_name,data_type,nullable from schema_metadata"):
        meta.setdefault(t, {})[c] = (ko, dt, nu)

    cols = []
    for tbl in DOMAINS + list(EXT):
        is_ext = tbl in EXT
        y = D.get(tbl, {})
        judged = dict(y.get("columns") or {})
        dbcols = [r[1] for r in con.execute(f"pragma table_info({tbl})")]
        # applies_to 상속
        for src, v in list(judged.items()):
            if isinstance(v, dict):
                for tgt in (v.get("applies_to") or []):
                    if tgt in dbcols and tgt not in judged:
                        inh = {k: val for k, val in v.items()
                               if k not in ("applies_to", "answerable_n", "korean_name")}
                        inh["_inh"] = src
                        judged[tgt] = inh
        total = con.execute(f"select count(*) from {tbl}").fetchone()[0]
        for c in dbcols:
            mko, dt, nu = meta.get(tbl, {}).get(c, (None, None, None))
            j = judged.get(c) or {}
            miss, dis = con.execute(
                f'''select sum(case when "{c}" is null or trim(cast("{c}" as text))='' then 1 else 0 end),
                           count(distinct "{c}") from "{tbl}"''').fetchone()
            miss = miss or 0
            zero = con.execute(
                f'''select count(*) from "{tbl}" where trim(cast("{c}" as text))='0' ''').fetchone()[0]
            if dis <= VALUE_CAP:
                vals = [[s(v, 70), n] for v, n in con.execute(
                    f'''select cast("{c}" as text), count(*) from "{tbl}"
                        where "{c}" is not null and trim(cast("{c}" as text))<>''
                        group by 1 order by 2 desc''')]
                trunc = False
            else:
                vals = [[s(v, 70), n] for v, n in con.execute(
                    f'''select cast("{c}" as text), count(*) from "{tbl}"
                        where "{c}" is not null and trim(cast("{c}" as text))<>''
                        group by 1 order by 2 desc limit 15''')]
                trunc = True
            ms = j.get("missing_semantics")
            cols.append({
                "id": f"{tbl}.{c}", "tbl": tbl, "ext": is_ext, "name": c,
                "ko": s(j.get("korean_name") or mko, 60), "dt": dt, "nu": nu,
                "tot": total, "miss": miss, "zero": zero, "dis": dis,
                "reason": s(j.get("missing_reason"), 30) if j else None,
                "sem": s(json.dumps(ms, ensure_ascii=False), 300) if ms else None,
                "unit": s(j.get("unit"), 60), "zv": bool(j.get("zero_is_value")),
                "policy": s(j.get("answer_policy")), "trap": s(j.get("trap")),
                "note": s(j.get("note")), "ent": j.get("kg_entity"),
                "an": j.get("answerable_n") if isinstance(j.get("answerable_n"), int) else None,
                "inh": j.get("_inh"), "judged": bool(j),
                "vals": vals, "vtrunc": trunc,
            })

    ents = []
    for name, doc in sorted(S.items()):
        nodes = doc.get("nodes") or {}
        ents.append({
            "id": doc.get("entity", name), "file": name,
            "prop": doc.get("property"), "desc": s(doc.get("description"), 200),
            "n": len(nodes),
            "parents": sum(1 for v in nodes.values() if isinstance(v, dict) and v.get("parent")),
            "absent": {KO.get(k, k): s(v, 220) for k, v in (doc.get("absent_in") or {}).items()},
        })
    for t, n in con.execute("select node_type,count(*) from kg_node group by 1"):
        for e in ents:
            if e["id"] == t:
                e["kg"] = n

    qrules = [{"dom": d, "key": k, "text": s(v, 700)}
              for d in DOMAINS for k, v in (D[d].get("query_rules") or {}).items()]

    blocks = {d: [k for k in D[d] if k not in
                  ("domain", "row_grain", "columns", "normalization", "query_rules")
                  and not k.startswith("_")] for d in DOMAINS}

    doms = []
    for d in DOMAINS:
        n = con.execute(f"select count(*) from {d}").fetchone()[0]
        nc = len([r for r in con.execute(f"pragma table_info({d})")])
        doms.append({"id": d, "ko": KO[d], "rows": n, "cols": nc,
                     "grain": s(D[d].get("row_grain"), 400),
                     "nqr": len(D[d].get("query_rules") or {}),
                     "blocks": blocks[d]})
    for t, ko in EXT.items():
        n = con.execute(f"select count(*) from {t}").fetchone()[0]
        nc = len([r for r in con.execute(f"pragma table_info({t})")])
        doms.append({"id": t, "ko": ko, "rows": n, "cols": nc, "ext": True,
                     "owner": EXT_OWNER[t], "grain": None, "nqr": 0, "blocks": []})

    return {"meta": {"asOf": con.execute("select as_of from build_info limit 1").fetchone()[0],
                     "cols": len(cols), "doms": len(doms), "ents": len(ents), "qrules": len(qrules)},
            "domains": doms, "columns": cols, "entities": ents, "qrules": qrules}


# ── 지식그래프 ───────────────────────────────────────────────────────────
def build_kg(con) -> dict:
    types, tidx = [], {}
    for t, n in con.execute("select node_type,count(*) from kg_node group by 1 order by 2 desc"):
        tidx[t] = len(types)
        types.append([t, n])

    nodes, nidx = [], {}
    for nid, t, ko, en in con.execute(
            "select node_id,node_type,label_ko,label_en from kg_node"):
        nidx[nid] = len(nodes)
        nodes.append([tidx.get(t, 0), ko or "", (en or "") if en != ko else ""])

    tabs, tabi = [], {}
    cols, coli = [], {}
    alias = []
    for nid, tb, cl, raw, src in con.execute(
            "select node_id,table_name,column_name,raw_value,source from kg_alias"):
        if tb not in tabi:
            tabi[tb] = len(tabs); tabs.append(tb)
        if cl not in coli:
            coli[cl] = len(cols); cols.append(cl)
        i = nidx.get(nid)
        if i is not None:
            alias.append([i, tabi[tb], coli[cl], raw or ""])

    preds, pidx = [], {}
    edges = []
    for a, p, b, src in con.execute("select src_id,predicate,dst_id,source from kg_edge"):
        if p not in pidx:
            pidx[p] = len(preds); preds.append(p)
        ia, ib = nidx.get(a), nidx.get(b)
        if ia is not None and ib is not None:
            edges.append([ia, pidx[p], ib])

    clos = []
    for a, d in con.execute("select ancestor_id,descendant_id from kg_closure"):
        ia, ib = nidx.get(a), nidx.get(d)
        if ia is not None and ib is not None:
            clos.append([ia, ib])

    # 집계 — 개체 × 술어 × 개체
    agg = {}
    for ia, p, ib in edges:
        k = (nodes[ia][0], p, nodes[ib][0])
        agg[k] = agg.get(k, 0) + 1
    aggl = [[a, p, b, n] for (a, p, b), n in sorted(agg.items(), key=lambda x: -x[1])]

    # alias 가 붙은 테이블·컬럼 집계
    acov = {}
    for i, tb, cl, raw in alias:
        k = (tb, cl)
        acov[k] = acov.get(k, 0) + 1
    acovl = [[tb, cl, n] for (tb, cl), n in sorted(acov.items(), key=lambda x: -x[1])]

    return {"meta": {"nodes": len(nodes), "alias": len(alias), "edges": len(edges),
                     "closure": len(clos),
                     "asOf": con.execute("select as_of from build_info limit 1").fetchone()[0]},
            "types": types, "preds": preds, "tabs": tabs, "cols": cols,
            "nodes": nodes, "alias": alias, "edges": edges, "closure": clos,
            "agg": aggl, "aliasCov": acovl}


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    BUILD.mkdir(exist_ok=True)
    for name, fn in (("viz_ontology", build_ontology), ("viz_kg", build_kg)):
        data = fn(con)
        p = BUILD / f"{name}.json"
        p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"✅ {p.relative_to(ROOT)}  {p.stat().st_size/1024/1024:.2f} MB  "
              f"{json.dumps(data['meta'], ensure_ascii=False)}")
    con.close()


if __name__ == "__main__":
    main()
