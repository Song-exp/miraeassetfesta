# -*- coding: utf-8 -*-
"""그래프 탐색기(docs/viz/ontology_graph_ui.html)의 규칙 블록·KG 수치를 원천에서 다시 만든다.

이 페이지는 지금까지 손으로 갱신돼 왔고 그래서 두 번 낡았다(2026-09-04: ETF 규칙 10개 누락 ·
펀드 규칙 3개 누락 · kg_alias 수치 어긋남). 저장소 규약대로 — "손으로 옮겨 적으면 빠지고,
배포본이 바뀌면 낡는다" — 원천에서 뽑는다.

다시 만드는 것 (기계가 아는 것):
  · const RULES.domains  — ontology/enums/{domestic_bonds,domestic_etfs,overseas_etfs,public_funds}.yaml
                           의 query_rules (이름 · 본문 150자 · triggers · enforce 유무)
  · const RULES.codebooks — ontology/codebooks/*.csv 파일 목록
  · 본문에 박힌 KG 수치   — kg_node · kg_edge · kg_alias (data/financial_products.db 실측)

  · const RULES.shared   — ontology/shared/*.yaml 의 entity·description·scale·absent_in·nodes·parents.
                           🔴 이것도 전부 yaml 에 있는 값이다(HTML 손글씨가 아니다) —
                           2026-09-04 실측: scale 이 yaml 은 "rank 1(AAA) ~ 20(D)" 인데 페이지는
                           "~ 19(C)" 로 낡아 있었다. 원천이 하나여야 낡지 않는다.

건드리지 않는 것:
  🔴 페이지의 서술·레이아웃·SVG. 이 스크립트는 데이터 블록과 수치 문자열만 바꾼다.

사용: python scripts/gen_viz_rules.py                  # 제자리 갱신
      python scripts/gen_viz_rules.py --check          # 어긋난 곳만 보고, 파일은 안 고침
      python scripts/gen_viz_rules.py --db <경로>      # KG 수치를 읽을 DB 지정

🔴 --db 가 필요한 이유 — 워킹트리 DB 는 같은 저장소에서 병행 작업하는 다른 세션이 생성기를
   돌리면 미커밋 상태로 바뀐다(2026-09-04 실측: kg_node 41,580 ↔ 40,863 · edge 7,414 ↔ 5,710).
   페이지에 싣는 수치는 **배포된 것과 같아야** 하므로 커밋된 소스로 만든 DB 를 가리킨다.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "viz" / "ontology_graph_ui.html"
DB = ROOT / "data" / "financial_products.db"
TEXT_MAX = 150

DOMAINS = {                                        # 페이지의 탭 키 → 원천 yaml
    "bond": "domestic_bonds.yaml",
    "etf_kr": "domestic_etfs.yaml",
    "etf_gl": "overseas_etfs.yaml",
    "fund": "public_funds.yaml",
}


def rule_rows(path: Path) -> list[dict]:
    """query_rules 를 페이지가 쓰는 4필드로 편다. 주석 키(_로 시작)는 뺀다."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for name, rule in (doc.get("query_rules") or {}).items():
        if str(name).startswith("_"):
            continue
        if isinstance(rule, dict):
            body, trig = str(rule.get("text", "")), (rule.get("triggers") or None)
            enf = True if rule.get("enforce") else None
        else:
            body, trig, enf = str(rule), None, None
        body = " ".join(body.split())              # 줄바꿈·들여쓰기 접기
        if len(body) > TEXT_MAX:
            body = body[:TEXT_MAX] + "…"
        out.append({"n": name, "t": body, "trig": trig, "enf": enf})
    return out


def shared_rows() -> dict[str, dict]:
    """shared/*.yaml → 페이지의 shared 항목(개체·서술·범위·부재선언·개체수)."""
    counts = {}
    for p in sorted((ROOT / "ontology" / "shared").glob("*.yaml")):
        if p.name.endswith("_auto.yaml"):          # 생성물은 페이지 대상이 아니다
            continue
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        # 🔴 `nodes` 키를 명시적으로 읽는다 — "첫 dict 값" 휴리스틱은 risk_grade.yaml 의
        #    range_by_table(3테이블)을 개체 목록으로 오인했다(7 → 3 오보고, 2026-09-04).
        nodes = doc.get("nodes")
        if not isinstance(nodes, dict):
            continue
        counts[p.name] = {
            "entity": doc.get("entity", ""),
            "nodes": len(nodes),
            "parents": sum(1 for v in nodes.values()
                           if isinstance(v, dict) and v.get("parent")),
            "absent_in": doc.get("absent_in") or {},
            "range": doc.get("range_by_table") or {},
            "desc": doc.get("description", ""),
            "scale": doc.get("scale", ""),
        }
    return counts


def kg_counts(db: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {t: con.execute(f"select count(*) from kg_{t}").fetchone()[0]
                for t in ("node", "alias", "edge")}
    finally:
        con.close()


def main() -> int:
    check = "--check" in sys.argv
    db = DB
    if "--db" in sys.argv:
        db = Path(sys.argv[sys.argv.index("--db") + 1]).resolve()
    if not db.exists():
        print(f"❌ DB 없음: {db}")
        return 1
    html = HTML.read_text(encoding="utf-8")
    m = re.search(r"(const RULES=)(\{.*?\})(;)", html, re.S)
    if not m:
        print("❌ const RULES 블록을 찾지 못했다 — 페이지 구조가 바뀌었다")
        return 1
    rules = json.loads(m.group(2))

    diffs: list[str] = []
    for key, fname in DOMAINS.items():
        rows = rule_rows(ROOT / "ontology" / "enums" / fname)
        before = len(rules["domains"].get(key, {}).get("rules", []))
        if before != len(rows):
            diffs.append(f"규칙 {key}: {before} → {len(rows)}")
        rules["domains"][key] = {"file": f"ontology/enums/{fname}", "rules": rows}

    books = sorted(p.name for p in (ROOT / "ontology" / "codebooks").glob("*.csv"))
    if books != rules.get("codebooks"):
        diffs.append(f"코드북: {len(rules.get('codebooks') or [])} → {len(books)}")
    rules["codebooks"] = books

    sr = shared_rows()
    for item in rules.get("shared", []):           # 파일별 항목을 yaml 값으로 덮는다
        row = sr.get(item.get("file"))
        if not row:
            continue
        for k, v in row.items():
            if item.get(k) != v:
                a, b = str(item.get(k))[:40], str(v)[:40]
                diffs.append(f"shared {item['file']}.{k}: {a} → {b}")
            item[k] = v

    html = html[:m.start(2)] + json.dumps(rules, ensure_ascii=False) + html[m.end(2):]

    kg = kg_counts(db)
    subs = [(r"노드 [\d,]+ · 간선 [\d,]+", f"노드 {kg['node']:,} · 간선 {kg['edge']:,}"),
            (r"<code>kg_alias</code> [\d,]+건", f"<code>kg_alias</code> {kg['alias']:,}건"),
            (r"\(현재 [\d,]+\)", f"(현재 {kg['node']:,})")]
    for pat, rep in subs:
        html, n = re.subn(pat, rep, html)
        if not n:
            diffs.append(f"⚠ 수치 자리를 못 찾음: {pat}")

    if check:
        print("\n".join(diffs) if diffs else "어긋난 곳 없음")
        return 0
    HTML.write_text(html, encoding="utf-8")
    total = sum(len(v["rules"]) for v in rules["domains"].values())
    print(f"✅ {HTML.relative_to(ROOT)} 갱신 — 규칙 {total}개 "
          + " · ".join(f"{k} {len(v['rules'])}" for k, v in rules["domains"].items()))
    print(f"   KG 수치 — 노드 {kg['node']:,} · 간선 {kg['edge']:,} · alias {kg['alias']:,}  (원천 {db})")
    for d in diffs:
        print("   변경:", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
