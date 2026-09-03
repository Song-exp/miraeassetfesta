# -*- coding: utf-8 -*-
"""심사관 3인의 verdicts 를 라운드 키 정규화해서 하나로 합친다.

    python eval/merge_verdicts.py -o eval/verdicts_merged.json

심사관마다 키가 다르다: `13라운드(수리 후)` / `13라운드(c1ec397)` / `13R(c1ec397)`.
앞의 라운드 번호만 뽑아 `NNR` 로 통일한다(G1 은 7R 시점 gold 초회라 `7R-gold` 로).
render_probe_md.py --verdict 에 그대로 넣는다.
"""
import argparse, json, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SRC = ["eval/verdicts_2026-09-02.json", "eval/verdicts_kg_2026-09-02.json",
       "eval/verdicts_gold_2026-09-03.json"]


def norm(k: str) -> str:
    if k.startswith("G1"):
        return "7R-gold"
    if "기준선" in k:
        return "0R"                      # KG 기준선 = 재검 2R 배포 시점
    m = re.match(r"\s*(\d+)", k)
    return f"{m.group(1)}R" if m else k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    merged, clash = {}, 0
    for f in SRC:
        p = Path(f)
        if not p.exists():
            print(f"  건너뜀(없음) {f}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for qid, v in d.items():
            if not isinstance(v, dict):
                continue
            slot = merged.setdefault(qid, {})
            for k, txt in v.items():
                nk = norm(k)
                if nk in slot and slot[nk] != txt:
                    clash += 1          # 같은 문항·같은 라운드를 두 심사관이 채점 — 있으면 안 된다
                slot[nk] = txt
        print(f"  {p.name}: {len(d)}문항")
    Path(a.out).write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    rounds = sorted({k for v in merged.values() for k in v}, key=lambda x: float(re.match(r"(\d+)", x).group(1)))
    print(f"\n합계 {len(merged)}문항 · 라운드 {rounds}")
    print(f"키 충돌 {clash}건" + ("  🔴 같은 문항을 두 심사관이 채점했다" if clash else " ✅"))


if __name__ == "__main__":
    main()
