# -*- coding: utf-8 -*-
"""공모펀드 78문항 결과 보고서 생성 — 예상 답변 · 회차별 실제 답변 · 판정을 md 하나로.

    python eval/render_funds_report.py            # 판정 없이 검토용 덤프
    python eval/render_funds_report.py --final    # verdicts.json 을 읽어 최종 md

문항마다 **회차를 쌓아** 변천사를 보여준다(ROUNDS). 각 회차는 (라벨, 프로브 json, 판정 json).
새 회차는 ROUNDS 에 한 줄 추가하면 된다 — 이전 회차 답변은 그대로 남는다.

판정은 eval/verdicts_funds_2026-09-04*.json 에 {qid: [판정, 사유]} 로 둔다.
판정값: O(통과) · △(부분) · X(실패) · ?(미채점)

🔴 손으로 쓴 두 절(결함 분류 · 수리 기록)은 별도 파일에 있고 여기서 끼워 넣는다 —
   렌더러를 다시 돌려도 손 편집이 날아가지 않게 하기 위해서다(2026-09-04).
"""
import io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from expected_funds_2026_09_04 import EXPECTED

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QFILE = os.path.join(ROOT, "eval", "probe_funds_2026-09-04_core.txt")
OUT = os.path.join(ROOT, "docs", "funds_test_result_2026-09-04.md")

# (라벨, 프로브 json, 판정 json) — 시간순. 마지막이 최신 회차이고 총평·요약표의 기준이다.
ROUNDS = [
    ("1차 · 09-04 16:00", "probe_funds_2026-09-04_core.json", "verdicts_funds_2026-09-04.json"),
    ("2차 · 09-04 20:5x", "probe_funds_2026-09-04_r2.json", "verdicts_funds_2026-09-04_r2.json"),
    ("3차 · 09-05 02:5x", "probe_funds_2026-09-05_r3.json", "verdicts_funds_2026-09-05_r3.json"),
]
# 본문에 끼워 넣는 손 편집 절 — (앵커, 파일). 앵커 앞에 삽입한다.
INCLUDES = [("BEFORE_BLOCKS", "funds_defects_2026-09-04.md"), ("AFTER_BLOCKS", "funds_repairs_2026-09-04.md")]

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


def _load_round(probe_name, verdict_name):
    pf = os.path.join(ROOT, "eval", probe_name)
    vf = os.path.join(ROOT, "eval", verdict_name)
    probe = {r["qid"]: r for r in json.load(io.open(pf, encoding="utf-8"))} if os.path.exists(pf) else {}
    verd = json.load(io.open(vf, encoding="utf-8")) if os.path.exists(vf) else {}
    return probe, verd


def _include(name):
    """손으로 쓴 절을 그대로 끼워 넣는다 — 렌더러 재실행이 손 편집을 덮지 않게."""
    f = os.path.join(ROOT, "docs", name)
    if not os.path.exists(f):
        return ""
    body = io.open(f, encoding="utf-8").read()
    return re.sub(r"^<!--.*?-->\n+", "", body, count=1, flags=re.S).rstrip() + "\n"


def _round_body(label, r, v, out):
    """한 회차의 답변·메타·판정을 붙인다."""
    ans = (r.get("answer") or "(응답 없음)").strip()
    tr = r.get("think_trace") or ""
    out.append(f"**{label}** {MARK[v[0]]}\n")
    out.append("```\n" + ans[:1400] + ("\n…(생략)" if len(ans) > 1400 else "") + "\n```\n")
    meta = [f"`[Execute] {ran(tr)}행`" if ran(tr) else "**미실행**"]
    if slots(tr):
        meta.append("슬롯 " + "·".join(slots(tr)))
    if "기계 조립" in tr:
        meta.append("기계 조립(HCX 0회)")
    if "값 검사 실패" in tr:
        meta.append("⚠ 값 검사 실패")
    if "재생성" in tr:
        meta.append("⚠ 재생성")
    if r.get("elapsed_s"):
        meta.append(f"{r['elapsed_s']}s")
    out.append("· ".join(meta) + "\n")
    sq = sql_of(tr, ans)
    if sq:
        out.append(f"<details><summary>SQL</summary>\n\n```sql\n{sq[:900]}\n```\n</details>\n")
    if v[1]:
        out.append(f"**판정** — {v[1]}\n")


def main():
    rounds = [(lbl,) + _load_round(pj, vj) for lbl, pj, vj in ROUNDS]
    last = len(rounds) - 1
    tally = [{"O": 0, "△": 0, "X": 0, "?": 0} for _ in rounds]
    body, summary = [], []

    for title, qids in blocks():
        rows = []
        for q in qids:
            vs = [rd[2].get(q, ["?", ""]) for rd in rounds]
            for t, v in zip(tally, vs):
                t[v[0]] = t.get(v[0], 0) + 1
            rows.append((q, vs))
        summary.append((title, rows))

        body.append(f"\n## {title}\n")
        for q, vs in rows:
            axis, exp, crit, _ = EXPECTED[q]
            # 제목에 변천을 박는다 — 회차 사이에 판정이 바뀌었으면 화살표로 (❌→✅)
            seen = [v[0] for v in vs if v[0] != "?"]
            trail = "→".join(MARK[x] for i, x in enumerate(seen) if i == 0 or x != seen[i - 1]) or MARK["?"]
            body.append(f"### {trail} `{q}` — {axis}\n")
            body.append(f"> {rounds[last][1].get(q, {}).get('question') or rounds[0][1].get(q, {}).get('question', '')}\n")
            body.append(f"**예상** — {exp}\n")
            body.append(f"**통과 조건** — {crit}\n")
            for (lbl, probe, _v), v in zip(rounds, vs):
                if q in probe:
                    _round_body(lbl, probe[q], v, body)

    n = sum(tally[last].values())
    t0, tl = tally[0], tally[last]
    head = [
        "# 공모펀드 78문항 테스트 결과 — 2026-09-04",
        "",
        "> 문항 `eval/probe_funds_2026-09-04_core.txt` · 예상 답변 `eval/expected_funds_2026_09_04.py` (전부 DB 실측)",
        "> 회차: " + " · ".join(f"**{lbl}** `eval/{pj}`" for lbl, pj, _ in ROUNDS),
        "> 모수: 판매중·공모 = 클래스 8,969 · 펀드 3,040 · 기준일 2026-08-24",
        "",
        f"## 총평 — {MARK['O']} {tl['O']} · {MARK['△']} {tl['△']} · {MARK['X']} {tl['X']}"
        + (f" · {MARK['?']} {tl['?']}" if tl.get("?") else "") + f"  (총 {n})",
        "",
    ]
    if len(rounds) > 1 and sum(t0.values()) and any(t0[k] != tl[k] for k in ("O", "△", "X")):
        head += ["| 회차 | ✅ | 🟡 | ❌ | 변동 |", "| :-- | --: | --: | --: | :-- |"]
        prev = None
        for (lbl, _p, _v), t in zip(rounds, tally):
            d = "" if prev is None else f"✅ {t['O'] - prev['O']:+d} · ❌ {t['X'] - prev['X']:+d}"
            head.append(f"| {lbl} | {t['O']} | {t['△']} | {t['X']} | {d} |")
            prev = t
        head += [""]

    head.append("| 블록 | ✅ | 🟡 | ❌ | 실패·부분 문항 (최신 회차) |")
    head.append("| :-- | --: | --: | --: | :-- |")
    for title, rows in summary:
        o = sum(1 for _, vs in rows if vs[last][0] == "O")
        m = sum(1 for _, vs in rows if vs[last][0] == "△")
        x = sum(1 for _, vs in rows if vs[last][0] == "X")
        bad = " ".join(f"`{q}`{MARK[vs[last][0]]}" for q, vs in rows if vs[last][0] in ("X", "△"))
        head.append(f"| {title} | {o} | {m} | {x} | {bad} |")
    head.append("")

    pre = "".join(_include(f) for a, f in INCLUDES if a == "BEFORE_BLOCKS")
    post = "".join(_include(f) for a, f in INCLUDES if a == "AFTER_BLOCKS")
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        "\n".join(head) + ("\n---\n\n" + pre + "\n---\n" if pre else "")
        + "\n".join(body) + ("\n\n---\n\n" + post if post else ""))
    print("wrote", OUT, "·", n, "문항")
    for (lbl, _p, _v), t in zip(rounds, tally):
        print(f"   {lbl}: {t}")


if __name__ == "__main__":
    main()
