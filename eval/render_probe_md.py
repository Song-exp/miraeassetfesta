# -*- coding: utf-8 -*-
"""probe JSON(여러 라운드) → 문항별 전/후 답변 대조 Markdown.

    python eval/render_probe_md.py \
        --round "1라운드(초기)=eval/probe_recheck_2026-09-02.json" \
        --round "2라운드(수리 후)=eval/probe_recheck_2026-09-02_r2.json" \
        --verdict eval/verdicts_2026-09-02.json \
        -o docs/recheck_loop_2026-09-02.md

라운드는 qid 로 묶는다. 판정 파일(선택)은 {qid: {round_label: "✅/🟡/❌ 요지"}} 형식.
answer 는 전문, think_trace 는 전문(접힘), retrieved_context 는 접힘 — 채점 근거가 전부 남아야 하므로 자르지 않는다.
"""
import argparse
import json
import sys
from collections import OrderedDict

sys.stdout.reconfigure(encoding="utf-8")


def load(path):
    return json.load(open(path, encoding="utf-8"))


def block(title, text, open_=False):
    if not text:
        return f"<details><summary>{title}: (없음)</summary></details>\n"
    return (f"<details{' open' if open_ else ''}><summary>{title}</summary>\n\n```text\n{text}\n```\n\n</details>\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", action="append", required=True, help="라벨=경로")
    ap.add_argument("--verdict", default=None)
    ap.add_argument("--title", default="재검 루프 실측 기록")
    ap.add_argument("--intro", default="")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    rounds = OrderedDict()
    for spec in a.round:
        label, _, path = spec.partition("=")
        rounds[label] = {r["qid"]: r for r in load(path)}
    verdicts = load(a.verdict) if a.verdict else {}

    qids = []
    for rs in rounds.values():
        for q in rs:
            if q not in qids:
                qids.append(q)

    out = [f"# {a.title}\n"]
    if a.intro:
        out.append(a.intro + "\n")
    out.append("## 판정 요약\n")
    out.append("| ID | 질문 | " + " | ".join(rounds) + " |")
    out.append("| :-- | :-- | " + " | ".join(":--" for _ in rounds) + " |")
    for q in qids:
        first = next(rs[q] for rs in rounds.values() if q in rs)
        cells = []
        for label, rs in rounds.items():
            v = verdicts.get(q, {}).get(label, "")
            if q not in rs:
                cells.append("—")
            else:
                cells.append(v or f"{rs[q]['http_status']} · {rs[q]['elapsed_s']}s")
        out.append(f"| {q} | {first['question']} | " + " | ".join(c.replace('|', '¦') for c in cells) + " |")
    out.append("")

    for q in qids:
        first = next(rs[q] for rs in rounds.values() if q in rs)
        out.append(f"---\n\n## {q}. {first['question']}\n")
        for label, rs in rounds.items():
            if q not in rs:
                continue
            r = rs[q]
            v = verdicts.get(q, {}).get(label)
            out.append(f"### {label} — HTTP {r['http_status']} · {r['elapsed_s']}s" + (f" · {v}" if v else ""))
            out.append("")
            if r.get("error"):
                out.append(f"**오류**: `{r['error']}`\n")
            out.append("**answer**\n")
            out.append("```text\n" + (r.get("answer") or "(없음)") + "\n```\n")
            out.append(block("think_trace", r.get("think_trace")))
            out.append(block("retrieved_context", r.get("retrieved_context")))
    open(a.out, "w", encoding="utf-8").write("\n".join(out))
    print(f"wrote {a.out} ({len(qids)} questions, {len(rounds)} rounds)")


if __name__ == "__main__":
    main()
