# -*- coding: utf-8 -*-
"""공모펀드 78문항 결과 보고서 생성 — 예상 답변 · 실제 답변 · 판정을 md 하나로.

    python eval/render_funds_report.py            # 판정 없이 검토용 덤프
    python eval/render_funds_report.py --final    # verdicts.json 을 읽어 최종 md

판정은 eval/verdicts_funds_2026-09-04.json 에 {qid: [판정, 사유]} 로 둔다.
판정값: O(통과) · △(부분) · X(실패)
"""
import io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from expected_funds_2026_09_04 import EXPECTED

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "eval", "probe_funds_2026-09-04_core.json")
QFILE = os.path.join(ROOT, "eval", "probe_funds_2026-09-04_core.txt")
VFILE = os.path.join(ROOT, "eval", "verdicts_funds_2026-09-04.json")
OUT = os.path.join(ROOT, "docs", "funds_test_result_2026-09-04.md")

MARK = {"O": "✅", "△": "🟡", "X": "❌", "?": "⬜"}


def blocks():
    """문항 파일의 `# --- 제목 (n) ---` 주석으로 블록을 복원한다."""
    out, cur = [], None
    for line in io.open(QFILE, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"#\s*---\s*(.+?)\s*\(\d+\)\s*---", line)
        if m:
            cur = m.group(1)
            out.append((cur, []))
        elif line.strip() and not line.startswith("#") and "\t" in line:
            out[-1][1].append(line.split("\t", 1)[0])
    return out


def sql_of(trace, answer):
    """trace 에서 최종 실행 SQL 을 뽑는다. 재생성이 있으면 그것이 최종이다."""
    if not trace:
        return ""
    hits = re.findall(r"(?:재생성 SQL|SQL 생성)[^\n]*\n(SELECT[^\n]+)", trace)
    return hits[-1] if hits else ""


def slots(trace):
    return sorted(set(re.findall(r"enforce 슬롯 (\w+)", trace or "")))


def ran(trace):
    m = re.search(r"\[Execute\] (\d+)행", trace or "")
    return m.group(1) if m else None


def main():
    final = "--final" in sys.argv
    probe = {r["qid"]: r for r in json.load(io.open(PROBE, encoding="utf-8"))}
    verdicts = json.load(io.open(VFILE, encoding="utf-8")) if os.path.exists(VFILE) else {}

    tally = {"O": 0, "△": 0, "X": 0, "?": 0}
    body, summary = [], []

    for title, qids in blocks():
        rows = []
        for q in qids:
            v = verdicts.get(q, ["?", ""])[0]
            tally[v] = tally.get(v, 0) + 1
            rows.append((q, v))
        summary.append((title, rows))

        body.append(f"\n## {title}\n")
        for q, v in rows:
            axis, exp, crit, _ = EXPECTED[q]
            r = probe.get(q, {})
            ans = (r.get("answer") or "(응답 없음)").strip()
            tr = r.get("think_trace") or ""
            note = verdicts.get(q, ["?", ""])[1]
            body.append(f"### {MARK[v]} `{q}` — {axis}\n")
            body.append(f"> {r.get('question','')}\n")
            body.append(f"**예상** — {exp}\n")
            body.append(f"**통과 조건** — {crit}\n")
            body.append("**실제 답변**\n")
            body.append("```\n" + ans[:1400] + ("\n…(생략)" if len(ans) > 1400 else "") + "\n```\n")
            meta = []
            if ran(tr):
                meta.append(f"`[Execute] {ran(tr)}행`")
            else:
                meta.append("**미실행**")
            if slots(tr):
                meta.append("슬롯 " + "·".join(slots(tr)))
            if "값 검사 실패" in tr:
                meta.append("⚠ 값 검사 실패")
            if "재생성" in tr:
                meta.append("⚠ 재생성")
            if r.get("elapsed_s"):
                meta.append(f"{r['elapsed_s']}s")
            body.append("· ".join(meta) + "\n")
            s = sql_of(tr, ans)
            if s:
                body.append(f"<details><summary>SQL</summary>\n\n```sql\n{s[:900]}\n```\n</details>\n")
            if note:
                body.append(f"**판정** — {note}\n")

    n = sum(tally.values())
    head = [
        "# 공모펀드 78문항 테스트 결과 — 2026-09-04",
        "",
        f"> 문항 `eval/probe_funds_2026-09-04_core.txt` · 실측 `eval/probe_funds_2026-09-04_core.json`",
        f"> 예상 답변 `eval/expected_funds_2026_09_04.py` (전부 `data/financial_products.db` 실측)",
        f"> 모수: 판매중·공모 = 클래스 8,969 · 펀드 3,040 · 기준일 2026-08-21",
        "",
        f"## 총평 — {MARK['O']} {tally['O']} · {MARK['△']} {tally['△']} · {MARK['X']} {tally['X']}"
        + (f" · {MARK['?']} {tally['?']}" if tally.get("?") else "")
        + f"  (총 {n})",
        "",
    ]

    head.append("| 블록 | ✅ | 🟡 | ❌ | 실패·부분 문항 |")
    head.append("| :-- | --: | --: | --: | :-- |")
    for title, rows in summary:
        o = sum(1 for _, v in rows if v == "O")
        m = sum(1 for _, v in rows if v == "△")
        x = sum(1 for _, v in rows if v == "X")
        bad = " ".join(f"`{q}`{MARK[v]}" for q, v in rows if v in ("X", "△"))
        head.append(f"| {title} | {o} | {m} | {x} | {bad} |")
    head.append("")

    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(head) + "\n".join(body))
    print("wrote", OUT, "·", n, "문항 ·", tally)


if __name__ == "__main__":
    main()
