# -*- coding: utf-8 -*-
"""접지 스냅샷 — 문항별 Route·Ground·Gate 를 HCX 0회로 찍는다.

    python eval/ground_snapshot.py                      # 현재 접지를 찍어 비교
    python eval/ground_snapshot.py --write               # 기준선으로 저장
    python eval/ground_snapshot.py --qid KG-012,Z10      # 몇 개만

왜 있나 — 78문항 서버 실측은 16분 + HCX 비용이라 수정마다 돌릴 수 없다. 그런데 2026-09-04
2차 재실측에서 **회귀 9건 중 Ground·Gate 가 1차와 다른 것은 0건**이었다. 회귀는 전부 접지
이후 계획 단계(HCX)에서 났고, 접지 계층은 결정적이다. 따라서 **KG·온톨로지를 고칠 때는
이 스냅샷만 보면 영향 범위가 확정된다** — 달라진 문항만 서버로 보내면 된다.

M108 사고(2026-09-04)가 이 도구가 없어서 났다: `FundAttr_M108 '모펀드'` 를 등록하니
"…의 모펀드는 뭐야?" 가 그 태그로 접지돼 0행이 됐는데, 등록 전에 질문 어휘와 대조하지
않았다. 이 스냅샷을 등록 전후로 찍으면 그 문항이 바로 뜬다.
"""
import argparse, io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QFILE = os.path.join(ROOT, "eval", "probe_funds_2026-09-04_core.txt")
SNAP = os.path.join(ROOT, "eval", "ground_snapshot_funds.json")

_KEEP = re.compile(r"^\s*\d+\.\s*\[(Route|Ground|Gate|Refuse)\]")


class _Stub:
    """플래너를 부르지 않는다 — Route·Ground·Gate 는 plan_sql 이전에 끝난다."""
    def plan_sql(self, q, g):
        return "SELECT itm_no FROM public_funds LIMIT 1"

    def compose_answer(self, q, rows, answer_rules=""):
        return ""


def questions():
    out = {}
    for ln in io.open(QFILE, encoding="utf-8"):
        if ln.strip() and not ln.startswith("#") and "\t" in ln:
            q, t = ln.split("\t", 1)
            out[q.strip()] = t.strip()
    return out


def capture(ctx, qid, text):
    from src.runtime.pipeline import answer_question
    r = answer_question(qid, text, planner=_Stub(), ctx=ctx)
    lines = [re.sub(r"^\s*\d+\.\s*", "", l).strip() for l in r.think_trace.splitlines() if _KEEP.match(l)]
    # 근거문서 크기 — 규칙을 늘리면 여기가 먼저 움직인다
    m = re.search(r"근거문서 조립 — 대상 \w+ · ([\d,]+)자", r.think_trace)
    nodes = sorted(set(re.findall(r"→ ((?:Org|Fund|Country|FundAttr|Region|RiskGrade|Idx|AssetClass|CG|Curr|Sec)_[\w]+) \(", r.think_trace)))
    return {"nodes": nodes, "steps": lines, "doc": int(m.group(1).replace(",", "")) if m else 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--qid", default="")
    g = ap.parse_args()
    from src.runtime.loader import load_context
    ctx = load_context()
    qs = questions()
    want = [q.strip() for q in g.qid.split(",") if q.strip()] or list(qs)
    cur = {q: capture(ctx, q, qs[q]) for q in want}

    if g.write or not os.path.exists(SNAP):
        base = json.load(io.open(SNAP, encoding="utf-8")) if os.path.exists(SNAP) else {}
        base.update(cur)
        json.dump(base, io.open(SNAP, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        print(f"기준선 저장 {SNAP} · {len(cur)}문항")
        return

    base = json.load(io.open(SNAP, encoding="utf-8"))
    diff = {q: (base.get(q), cur[q]) for q in want if base.get(q) != cur[q]}
    doc = sum(c["doc"] for c in cur.values()) / max(len(cur), 1)
    bdoc = sum(base[q]["doc"] for q in want if q in base) / max(len(want), 1)
    print(f"문항 {len(want)} · 접지 변화 {len(diff)} · 근거문서 평균 {bdoc:.0f} → {doc:.0f}자")
    for q, (b, c) in diff.items():
        print(f"\n=== {q} — {qs[q]}")
        if b is None:
            print("   (기준선에 없음)"); continue
        if b["nodes"] != c["nodes"]:
            print(f"   노드  {b['nodes']} → {c['nodes']}")
        for x in [s for s in c["steps"] if s not in b["steps"]]:
            print(f"   +  {x[:150]}")
        for x in [s for s in b["steps"] if s not in c["steps"]]:
            print(f"   -  {x[:150]}")
    if not diff:
        print("접지 동일 — 이 변경은 KG 층에서 아무 문항도 건드리지 않았다.")
    print(f"\n→ 서버 실측이 필요한 문항: {' '.join(diff) if diff else '없음'}")


if __name__ == "__main__":
    main()
