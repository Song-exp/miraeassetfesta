# -*- coding: utf-8 -*-
"""두 회차 프로브를 문항별로 견준다 — 무엇이 달라졌고 무엇이 그대로인가.

    python eval/diff_rounds.py A.json B.json [--changed|--same|--qid Q1,Q2]

채점 비용을 줄이려고 만든다. 답변이 **글자까지 같으면** 이전 판정을 그대로 옮기고,
달라진 문항과 이전에 ❌·🟡 였던 문항만 손으로 다시 본다.
"""
import argparse, io, json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    p = p if os.path.isabs(p) else os.path.join(ROOT, p)
    return {r["qid"]: r for r in json.load(io.open(p, encoding="utf-8"))}


def norm(s):
    """비교용 정규화 — 공백만 접는다. 숫자·문장은 그대로 본다."""
    return re.sub(r"\s+", " ", (s or "").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--verdicts", default="eval/verdicts_funds_2026-09-04.json")
    ap.add_argument("--changed", action="store_true"); ap.add_argument("--same", action="store_true")
    ap.add_argument("--qid", default=""); ap.add_argument("--full", action="store_true")
    g = ap.parse_args()

    A, B = load(g.a), load(g.b)
    vf = os.path.join(ROOT, g.verdicts)
    V = json.load(io.open(vf, encoding="utf-8")) if os.path.exists(vf) else {}
    MARK = {"O": "✅", "△": "🟡", "X": "❌", "?": "⬜"}

    want = [q.strip() for q in g.qid.split(",") if q.strip()]
    same, changed = [], []
    for q in B:
        (same if q in A and norm(A[q].get("answer")) == norm(B[q].get("answer")) else changed).append(q)

    if not (g.changed or g.same or want):
        print(f"동일 {len(same)} · 변경 {len(changed)} · 총 {len(B)}")
        print("\n[변경된 문항]  " + " ".join(f"{MARK[V.get(q,['?'])[0]]}{q}" for q in changed))
        print("\n[그대로]      " + " ".join(f"{MARK[V.get(q,['?'])[0]]}{q}" for q in same))
        print("\n※ 그대로인 문항 중 1차 판정이 ✅ 인 것은 판정을 옮기면 된다.")
        return

    qs = want or (changed if g.changed else same)
    lim = 100000 if g.full else 700
    for q in qs:
        v = V.get(q, ["?", ""])
        print("=" * 100)
        print(f"### {MARK[v[0]]} {q} — {B.get(q, A.get(q, {})).get('question', '')}")
        if v[1]:
            print(f"1차 판정: {v[1]}")
        if q in A and q not in same:
            print("--- 1차 ---"); print((A[q].get("answer") or "")[:lim])
        print("--- 2차 ---" if q not in same else "--- 양쪽 동일 ---")
        print((B.get(q, {}).get("answer") or "")[:lim])
        print()


if __name__ == "__main__":
    main()
