"""HCX p95 레이턴시 벤치마크 — 지시서 §4.3 ① (워크샵 제출물).

측정하는 것
  ① 모델별 p50/p95/max 레이턴시      → 아키텍처 분기 (2초 / 5초 / 8초)
  ② 입력 토큰 길이별 변화             → retrieved_context 상한
  ③ 동시 호출 rate limit             → 주최측 오토배치 30문항 대응 가능 여부

사용법
  python scripts/bench_hcx.py                      # 기본 (설정 3종 × 크기 3종 × 10회)
  python scripts/bench_hcx.py --n 20
  python scripts/bench_hcx.py --configs 005,007-none --sizes small,large
  python scripts/bench_hcx.py --skip-latency --concurrency 8
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.hcx import HCXClient, HCXConfig, HCXError  # noqa: E402

OUT_DIR = ROOT / "docs" / "bench"

CONFIGS: dict[str, HCXConfig] = {
    "005": HCXConfig(model="HCX-005"),
    "007-none": HCXConfig(model="HCX-007", thinking_effort="none"),
    "007-low": HCXConfig(model="HCX-007", thinking_effort="low"),
}

SYSTEM = (
    "너는 금융상품 데이터 질의를 SQLite SQL로 변환하는 도구다. "
    "설명 없이 SQL 한 문장만 출력한다."
)
QUESTION = "국내 상장 ETF 중 최근 1년 수익률이 가장 높은 채권형 ETF 3개를 알려줘."


def _yaml_context(name: str) -> str:
    """실제 yaml 을 프롬프트 컨텍스트로 씁니다 (합성 패딩보다 측정 타당성이 높음)."""
    p = ROOT / "ontology" / "enums" / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def build_sizes() -> dict[str, str]:
    """small→large 로 갈수록 retrieved_context 가 커지는 상황을 모사."""
    etf = _yaml_context("domestic_etfs.yaml")
    funds = _yaml_context("public_funds.yaml")
    return {
        "small": QUESTION,
        "medium": f"[스키마·품질 규칙]\n{etf}\n\n[질의]\n{QUESTION}",
        "large": f"[스키마·품질 규칙]\n{etf}\n{funds}\n\n[질의]\n{QUESTION}",
    }


@dataclass
class Sample:
    config: str
    size: str
    ok: bool
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    finish_reason: str = ""
    retries: int = 0
    remaining_tokens: int | None = None
    error: str = ""


def pct(values: list[float], q: float) -> float:
    """선형 보간 분위수. n<2 면 그대로 반환."""
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    s = sorted(values)
    idx = q * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _pace(client: HCXClient, est_cost: int) -> float:
    """토큰 예산이 다음 호출을 못 감당하면 reset 창만큼 쉽니다.

    🔴 테스트 키는 60,000 tokens/60s 라 컨텍스트가 크면 요청 수가 아니라
    토큰 한도에 먼저 걸립니다. 페이싱 없이 재면 429 가 레이턴시 표본을 통째로 날립니다.
    """
    rl = client.last_rate_limit
    if rl.remaining_tokens is None or est_cost <= 0:
        return 0.0
    if rl.remaining_tokens >= est_cost * 2:
        return 0.0
    wait = (rl.reset_tokens_s or 60.0) + 1.0
    time.sleep(wait)
    return wait


def run_latency(cfg_names: list[str], size_names: list[str], n: int) -> list[Sample]:
    sizes = build_sizes()
    samples: list[Sample] = []
    for cname in cfg_names:
        cfg = CONFIGS[cname]
        with HCXClient(cfg) as client:
            for sname in size_names:
                user = sizes[sname]
                print(f"  {cname:9s} / {sname:6s} ", end="", flush=True)
                est = 0
                for _ in range(n):
                    if _pace(client, est):
                        print("~", end="", flush=True)  # 예산 대기
                    try:
                        r = client.complete(SYSTEM, user)
                        est = r.prompt_tokens + r.completion_tokens
                        samples.append(
                            Sample(
                                cname, sname, True, r.latency_s,
                                r.prompt_tokens, r.completion_tokens,
                                r.thinking_tokens, r.finish_reason,
                                r.retries, r.rate_limit.remaining_tokens,
                            )
                        )
                        print("." if not r.retries else "R", end="", flush=True)
                    except HCXError as e:
                        samples.append(Sample(cname, sname, False, 0.0, error=str(e)))
                        print("x", end="", flush=True)
                    time.sleep(0.2)  # 레이턴시 측정에 동시성은 넣지 않습니다
                print()
    return samples


def run_concurrency(cfg_name: str, k: int) -> dict:
    """동시 K개 발사 후 성공/429 집계. 오토배치가 몰아칠 때를 모사합니다."""
    cfg = CONFIGS[cfg_name]
    sizes = build_sizes()
    user = sizes["medium"]

    def one(_i: int) -> tuple[bool, float, str]:
        # 커넥션 공유로 인한 직렬화를 피하려 요청마다 클라이언트를 따로 씁니다.
        with HCXClient(cfg) as c:
            try:
                r = c.complete(SYSTEM, user)
                return True, r.latency_s, ""
            except HCXError as e:
                return False, 0.0, f"{e.status_code}: {e}"

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=k) as pool:
        results = list(pool.map(one, range(k)))
    wall = time.perf_counter() - t0

    ok = [r for r in results if r[0]]
    errs = [r[2] for r in results if not r[0]]
    return {
        "config": cfg_name,
        "concurrent": k,
        "succeeded": len(ok),
        "failed": len(errs),
        "wall_s": round(wall, 2),
        "max_latency_s": round(max((r[1] for r in ok), default=0.0), 2),
        "errors": errs[:5],
    }


def summarize(samples: list[Sample]) -> list[dict]:
    rows = []
    keys = sorted({(s.config, s.size) for s in samples})
    for cname, sname in keys:
        grp = [s for s in samples if s.config == cname and s.size == sname]
        ok = [s for s in grp if s.ok]
        lat = [s.latency_s for s in ok]
        rows.append(
            {
                "config": cname,
                "size": sname,
                "n": len(grp),
                "ok": len(ok),
                "p50": round(pct(lat, 0.50), 2) if lat else None,
                "p95": round(pct(lat, 0.95), 2) if lat else None,
                "max": round(max(lat), 2) if lat else None,
                "prompt_tokens": ok[0].prompt_tokens if ok else 0,
                "completion_avg": round(statistics.mean([s.completion_tokens for s in ok]), 1) if ok else 0,
                "thinking_avg": round(statistics.mean([s.thinking_tokens for s in ok]), 1) if ok else 0,
                "truncated": sum(1 for s in ok if s.finish_reason == "length"),
                "retried": sum(s.retries for s in ok),
                "calls_per_min": (
                    round(60000 / (ok[0].prompt_tokens + statistics.mean([s.completion_tokens for s in ok])))
                    if ok else None
                ),
            }
        )
    return rows


def render_markdown(rows: list[dict], conc: list[dict], n: int) -> str:
    lines = [
        "# HCX p95 레이턴시 실측 — 지시서 §4.3 ①",
        "",
        f"> 반복 {n}회/조합 · 순차 호출 · temperature=0 · 테스트 API 키",
        "> p95 는 표본 수가 작으면 max 에 가까워집니다. 표본 수를 함께 보세요.",
        "",
        "## 1. 모델 × 입력 크기별 레이턴시",
        "",
        "| 설정 | 입력 | 입력토큰 | n | 성공 | p50 | **p95** | max | 생성토큰 | 사고토큰 | 잘림 | 429재시도 | 분당가능 |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        lines.append(
            f"| `{r['config']}` | {r['size']} | {r['prompt_tokens']:,} | {r['n']} | {r['ok']} | "
            f"{r['p50']} | **{r['p95']}** | {r['max']} | {r['completion_avg']} | "
            f"{r['thinking_avg']} | {r['truncated']} | {r['retried']} | {r['calls_per_min']} |"
        )
    lines += [
        "",
        "> `분당가능` = 60,000 tokens/min ÷ (입력+생성 토큰). 테스트 키 토큰 한도 기준 이론 상한입니다.",
        "> 경로당 2회 호출이므로 **질의 처리량은 이 값의 절반**입니다.",
    ]

    lines += ["", "## 2. 동시 호출 (rate limit)", ""]
    if conc:
        lines += [
            "| 설정 | 동시 | 성공 | 실패 | 총 소요 | 최대 지연 |",
            "| :--- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for c in conc:
            lines.append(
                f"| `{c['config']}` | {c['concurrent']} | {c['succeeded']} | {c['failed']} | "
                f"{c['wall_s']}s | {c['max_latency_s']}s |"
            )
        errs = [e for c in conc for e in c["errors"]]
        if errs:
            lines += ["", "실패 샘플:", "", "```"] + errs + ["```"]
    else:
        lines.append("_측정 안 함 (`--concurrency N` 으로 실행)_")

    lines += [
        "",
        "## 3. 테스트 API 키 한도 (응답 헤더 실측)",
        "",
        "```",
        "x-ratelimit-limit-requests:     60  / 60s",
        "x-ratelimit-limit-tokens:   60,000  / 60s   🔴 이쪽이 먼저 걸립니다",
        "```",
        "",
        "컨텍스트가 커질수록 요청 수가 아니라 **토큰 한도**가 상한을 정합니다.",
        "`retrieved_context` 크기를 줄이는 것이 처리량을 늘리는 유일한 수단입니다.",
        "",
        "## 4. 판정",
        "",
        "경로당 HCX 2회(PlanSQL + Answer) 기준, 주최측 권장 응답 15초.",
        "",
        "```",
        "p95 ~2초   호출 2회 + 재시도 여유",
        "p95 ~5초   호출 2회가 상한. 재시도는 SQL 단계에만",
        "p95 8초+   🔴 호출 1회 구조로 재설계 — PlanSQL 을 룰 기반으로",
        "```",
        "",
        "> 🔴 `thinkingContent` 는 클라이언트가 버립니다. `think_trace` 는 노드 로그로만 만듭니다.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="조합당 반복 횟수")
    ap.add_argument("--configs", default="005,007-none,007-low")
    ap.add_argument("--sizes", default="small,medium,large")
    ap.add_argument("--concurrency", type=int, default=0, help="동시 호출 K (0=생략)")
    ap.add_argument("--conc-config", default="005")
    ap.add_argument("--skip-latency", action="store_true")
    ap.add_argument(
        "--tag",
        default="",
        help="산출물 파일명 접미사. 부분 측정이 전체 측정 결과를 덮어쓰는 것을 막습니다.",
    )
    args = ap.parse_args()

    cfg_names = [c.strip() for c in args.configs.split(",") if c.strip()]
    size_names = [s.strip() for s in args.sizes.split(",") if s.strip()]
    for c in cfg_names:
        if c not in CONFIGS:
            print(f"알 수 없는 설정: {c} (가능: {list(CONFIGS)})")
            return 2

    samples: list[Sample] = []
    if not args.skip_latency:
        total = len(cfg_names) * len(size_names) * args.n
        print(f"레이턴시 측정: {total}회 호출\n")
        samples = run_latency(cfg_names, size_names, args.n)

    conc: list[dict] = []
    if args.concurrency > 0:
        print(f"\n동시 호출 측정: {args.conc_config} × {args.concurrency}")
        conc.append(run_concurrency(args.conc_config, args.concurrency))

    rows = summarize(samples)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.tag}" if args.tag else ""
    (OUT_DIR / f"hcx_latency{suffix}.json").write_text(
        json.dumps(
            {"n": args.n, "summary": rows, "concurrency": conc,
             "samples": [asdict(s) for s in samples]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    md = render_markdown(rows, conc, args.n)
    (OUT_DIR / f"hcx_latency{suffix}.md").write_text(md, encoding="utf-8")

    print("\n" + md)
    print(f"\n저장: {OUT_DIR / f'hcx_latency{suffix}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
