# -*- coding: utf-8 -*-
"""서버 /answer 직접 실측 — 문항 목록을 순차 질의해 5필드 원본을 JSON 으로 저장한다.

    python eval/probe_server.py eval/probe_recheck_2026-09-02.txt -o eval/probe_recheck_2026-09-02.json

입력: 한 줄에 한 질문 (빈 줄·# 주석 무시). 앞에 `ID<TAB>` 를 붙이면 question_id 로 쓴다.
출력: [{qid, question, elapsed_s, http_status, answer, think_trace, retrieved_context}]
주최 호출 방식(순차 1건씩·GET·쿼리스트링)을 그대로 따른다. 재시도 없음 — 실패도 그대로 기록.
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_BASE = "https://49.50.134.229.nip.io"


def ask(base: str, qid: str, question: str, timeout: int = 300) -> dict:
    url = f"{base}/answer?" + urllib.parse.urlencode({"question_id": qid, "question": question})
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            status = r.status
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        status = e.code
        body = {"error": e.read().decode("utf-8", "replace")}
    except Exception as e:  # noqa: BLE001
        status = -1
        body = {"error": repr(e)}
    return {"qid": qid, "question": question, "elapsed_s": round(time.time() - t0, 1),
            "http_status": status, **{k: body.get(k) for k in ("answer", "think_trace", "retrieved_context")},
            **({"error": body["error"]} if "error" in body else {})}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("questions")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--resume", action="store_true",
                    help="출력 파일에 이미 있는 qid 는 건너뛴다 (10분 제한 등으로 끊긴 실측을 이어 돌릴 때)")
    a = ap.parse_args()

    results: list[dict] = []
    if a.resume:
        try:
            results = json.load(open(a.out, encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            results = []
    done = {r["qid"] for r in results}

    items = []
    for i, line in enumerate(open(a.questions, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        if "\t" in line:
            # ID<TAB>질문<TAB>주석… — 세 번째 칸부터는 설계 메모라 서버에 보내지 않는다
            #   (2026-09-02 5R 사고: B 보고서 §⑤ 줄을 그대로 붙여 X1~X25 가 주석까지 질의됨)
            qid, q = line.split("\t")[:2]
        else:
            qid, q = f"P{i:03d}", line
        items.append((qid.strip(), q.strip()))

    if done:
        skipped = [qid for qid, _ in items if qid in done]
        items = [(qid, q) for qid, q in items if qid not in done]
        print(f"resume: {len(skipped)} 건 건너뜀, {len(items)} 건 남음", flush=True)
    for qid, q in items:
        print(f"[{qid}] {q}", flush=True)
        r = ask(a.base, qid, q)
        results.append(r)
        print(f"  -> {r['http_status']} {r['elapsed_s']}s | {(r.get('answer') or r.get('error') or '')[:120]!r}", flush=True)
        json.dump(results, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"saved {len(results)} -> {a.out}")


if __name__ == "__main__":
    main()
