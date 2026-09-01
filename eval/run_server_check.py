# -*- coding: utf-8 -*-
"""배포 후 서버 재검증 — 회귀·공식 문항을 실서버에 쏘고 gold 기준으로 자동 채점한다.

    python eval/run_server_check.py --base https://<서버> --token <CHAT_TOKEN>
    python eval/run_server_check.py --dry-run                    # 보낼 문항만 출력 (호출 0회)
    python eval/run_server_check.py --base .. --token .. --qids ETF-D-025,OFFICIAL-003

왜 만들었나(2026-09-01 자체 점검) — 서버 재검증을 사람이 챗 UI 에 복붙하고 결과를 눈으로
대조해 왔다. 문항당 왕복이 느리고, 채점이 인상 평가가 된다. 이 스크립트는 /chat/ask 로 쏘고
eval 정답지(must_include / must_not_include / expected_behavior)로 기계 채점한다.

🔴 비용 — 문항당 HCX 2회(Plan·Answer)다. 기본 셋 15문항 ≈ 30콜. --dry-run 이 아니면
   반드시 --token 을 요구하므로 실수로 돌 일은 없다. 토큰은 저장소에 두지 않는다.
판정 —
  PASS  answer 문항: must_include 전부 포함 + must_not_include 전무
  FAIL  위반 1개 이상, 또는 오류·타임아웃
  참고  must 문구는 표현이 달라지면 오탐할 수 있는 근사 채점이다(자체 점검 §7 인정).
        FAIL 이면 sql·trace 를 눈으로 확인하고 판단한다 — 기계 채점은 1차 선별이다.
"""
import argparse
import glob
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 기본 셋 — 서버 실측 오답에서 승격한 회귀 문항 + 공식 예시(ETF 몫)
DEFAULT_QIDS = [
    "ETF-D-024", "ETF-D-025", "ETF-D-026", "ETF-D-027", "ETF-D-028",
    "ETF-D-029", "ETF-D-030", "ETF-D-031",
    "ETF-O-030", "ETF-O-031", "ETF-O-032", "ETF-O-033",
    "OFFICIAL-003", "OFFICIAL-004", "OFFICIAL-005", "OFFICIAL-NA-003",
]


def load_questions(qids):
    got = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "eval", "questions_*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            q = json.loads(line)
            if q.get("qid") in qids:
                got[q["qid"]] = q
    missing = [q for q in qids if q not in got]
    if missing:
        print(f"⚠️ eval 에 없는 qid: {missing}")
    return [got[q] for q in qids if q in got]


def ask(base, token, question, timeout, insecure):
    url = f"{base.rstrip('/')}/chat/ask?" + urllib.parse.urlencode({"question": question, "t": token})
    ctx = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def grade(q, answer):
    """(판정, 위반목록). 근사 채점 — FAIL 은 사람이 재확인한다."""
    bad = []
    for w in q.get("must_include") or []:
        if w not in answer:
            bad.append(f"미포함:{w}")
    for w in q.get("must_not_include") or []:
        if w in answer:
            bad.append(f"금지어:{w}")
    return ("PASS" if not bad else "FAIL"), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="서버 베이스 URL (예: https://49.50.134.229.nip.io)")
    ap.add_argument("--token", help="CHAT_TOKEN — 저장소에 두지 말 것")
    ap.add_argument("--qids", help="쉼표 구분 qid 목록 (기본: 회귀+공식 16문항)")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--insecure", action="store_true", help="TLS 검증 생략")
    ap.add_argument("--dry-run", action="store_true", help="호출 없이 보낼 문항만 출력")
    a = ap.parse_args()

    qids = [s.strip() for s in a.qids.split(",")] if a.qids else DEFAULT_QIDS
    qs = load_questions(qids)
    if a.dry_run:
        print(f"보낼 문항 {len(qs)}건 (HCX 약 {len(qs)*2}콜):")
        for q in qs:
            print(f"  {q['qid']:16s} {q['question'][:60]}")
        return 0
    if not (a.base and a.token):
        ap.error("--base 와 --token 이 필요하다 (--dry-run 은 예외)")

    results, fails = [], 0
    for q in qs:
        t0 = time.time()
        try:
            r = ask(a.base, a.token, q["question"], a.timeout, a.insecure)
            verdict, bad = grade(q, r.get("answer") or "")
        except Exception as e:  # noqa: BLE001 — 네트워크·타임아웃은 전부 FAIL 로 집계
            r, verdict, bad = {}, "FAIL", [f"오류:{type(e).__name__}"]
        dt = time.time() - t0
        fails += verdict == "FAIL"
        results.append((q, r, verdict, bad, dt))
        mark = "✅" if verdict == "PASS" else "🔴"
        print(f"{mark} {q['qid']:16s} {dt:5.1f}s  {'; '.join(bad) or 'OK'}")
        if verdict == "FAIL" and r:
            print(f"     sql: {(r.get('sql') or '')[:110]}")
            print(f"     ans: {(r.get('answer') or '')[:110]}")

    out = os.path.join(ROOT, "eval", "server_check_last.json")
    json.dump([{ "qid": q["qid"], "verdict": v, "bad": b, "elapsed_s": round(dt, 1),
                 "sql": r.get("sql"), "answer": r.get("answer")}
               for q, r, v, b, dt in results],
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{len(results)}문항 · PASS {len(results)-fails} · FAIL {fails} → {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
