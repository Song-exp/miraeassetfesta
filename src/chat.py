# -*- coding: utf-8 -*-
"""실험용 챗봇 CLI — 질의 → 답변 + 근거를 눈으로 보고, 그대로 로그에 남긴다.

    python -m src.chat                      대화형
    python -m src.chat -q "질문"            한 건만
    python -m src.chat -f questions.txt     파일의 각 줄을 순서대로

루프에서의 위치 (yaml 이 진실의 원천):

    ontology/*.yaml  ──build_ontology.py──▶  kg_* + ttl
           ▲                                    │
           │                              load_context()
      판정을 여기 적는다                          ▼
           └──────  이 CLI 로 관찰한 오답  ◀──  답변

🔴 로그가 산출물이다. 틀린 질의는 logs/chat-*.jsonl 에서 골라 eval/questions_*.jsonl 로
   승격하고 run_gold_check.py 로 회귀를 고정한다 — 안 그러면 같은 오답이 또 나온다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from src.runtime.loader import load_context
from src.runtime.pipeline import answer_question
from src.runtime.qa_log import build_record

# CLI 진입점에서만 .env 를 읽는다 (서버는 compose 의 env_file 로 주입받는다).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

LOG_DIR = Path(os.environ.get("CHAT_LOG_DIR") or Path(__file__).resolve().parents[1] / "logs")


def _log(rec: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    day = time.strftime("%Y%m%d", time.localtime())
    with open(LOG_DIR / f"chat-{day}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ask(question: str, planner, ctx, qid: str = "CHAT") -> None:
    t0 = time.perf_counter()
    r = answer_question(qid, question, planner=planner, ctx=ctx)
    dt = time.perf_counter() - t0

    print(f"\n\033[1m답변\033[0m  ({dt:.1f}s)\n{r.answer}\n")
    if r.sql:
        print(f"\033[2m--- 실행 SQL ---\n{r.sql}\033[0m\n")
    if r.retrieved_context:
        print(f"\033[2m--- retrieved_context ---\n{r.retrieved_context}\033[0m\n")
    print(f"\033[2m--- think_trace ---\n{r.think_trace}\033[0m\n")

    # 🔴 CLI 실험 로그에는 근거문서까지 남긴다 — "KG·yaml 이 실제로 프롬프트에 실렸는가" 는
    #    이 원문 없이는 확인할 방법이 없다. 평가 서버 쪽은 LOG_GROUNDING 으로 끈다.
    _log(build_record(r, dt, with_grounding=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="실험용 챗봇 CLI")
    ap.add_argument("-q", "--question", help="한 건만 묻고 종료")
    ap.add_argument("-f", "--file", help="줄 단위 질의 파일")
    ap.add_argument("--no-hcx", action="store_true", help="플래너 없이 Ground·Gate 만 (HCX 호출 0회)")
    args = ap.parse_args()

    planner = None
    if not args.no_hcx:
        from src.hcx.planner import build_planner

        planner = build_planner()
        if planner is None:
            print("⚠️  HYPERCLOVA_API_KEY 가 없습니다 — Ground·Gate 만 돕니다 (--no-hcx 와 동일)")

    t0 = time.perf_counter()
    ctx = load_context()
    print(f"📥 컨텍스트 로드 {time.perf_counter() - t0:.1f}s — "
          f"KG 노드 {len(ctx.kg_nodes):,} · alias {len(ctx.kg_aliases):,} · enums {len(ctx.enums)}")

    if args.question:
        ask(args.question, planner, ctx)
        return 0
    if args.file:
        for i, line in enumerate(Path(args.file).read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                print(f"\n\033[1m[{i}] {line.strip()}\033[0m")
                ask(line.strip(), planner, ctx, qid=f"CHAT-{i:03d}")
        return 0

    print("질문을 입력하세요. 종료는 빈 줄 또는 Ctrl-C.\n")
    while True:
        try:
            q = input("\033[1m> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            return 0
        ask(q, planner, ctx)


if __name__ == "__main__":
    sys.exit(main())
