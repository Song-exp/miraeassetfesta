# -*- coding: utf-8 -*-
"""제출 패키지 추출 — 우리 저장소에서 **주최 저장소에 올릴 것만** 골라 복사한다.

왜: 작업 저장소에는 오답기록·라운드 로그·EDA 노트가 함께 산다(528파일 41.8MB).
    그중 심사 대상은 소스코드·제안서·API 명세 셋이고, 나머지는 그것을 만든 재료다.
    마감 직전에 손으로 고르면 반드시 빠뜨린다 — 목록을 코드로 고정한다.

사용:
    python scripts/make_submission.py                 # build/submission/ 에 복사
    python scripts/make_submission.py --out ../submit # 다른 곳에
    python scripts/make_submission.py --list          # 복사 없이 목록만

🔴 이 스크립트는 **아무것도 지우지 않는다.** 원본은 그대로 두고 대상 디렉터리에 복사만 한다.
🔴 제안서 PDF·워드와 API 명세서는 저장소 밖 산출물이라 여기서 다루지 않는다 — §수동 항목 참조.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# ── 포함 ─────────────────────────────────────────────────────────────
# 디렉터리 통째로. 런타임이 읽거나(src·ontology), 재현에 필요하거나(scripts·Dockerfile),
# 완성도의 증거인 것(tests).
INCLUDE_DIRS = (
    "src/",        # 구현체 — Dockerfile 의 COPY 대상
    "ontology/",   # yaml 단일 원천 + 생성된 ttl 5분할. 주최가 ttl 제출을 요구한다
    "scripts/",    # 빌드·수집 재현 (build_ontology · build_db · fetch_*)
    "tests/",      # 회귀 담장 — "기술완성도" 의 증거
    "deploy/",     # 배포 스크립트
    "data/",       # 코드북 csv + 외부수집 출처 기록 (원본 엑셀·DB 는 추적 대상이 아니다)
)
INCLUDE_FILES = {
    "Dockerfile", "requirements.txt", "requirements-dev.txt", "docker-compose.yml",
    ".dockerignore", ".env.example", ".gitignore", ".gitattributes",
    "README.md",        # 🔴 제출 필수 (환경 구성·실행 명령어). 아직 없으면 경고만 내고 넘어간다
    "docs/API_SPEC.md", # 🔴 제출 항목 3 그 자체. docs/ 밑이라 디렉터리 규칙으로는 안 잡힌다
}

# ── 제외 ─────────────────────────────────────────────────────────────
# eval/ 은 통째로 넣지 않는다 — 평가셋(jsonl)과 실행기(py)만 넣고
# probe_*.json 같은 라운드 실행 로그 13.6MB 는 뺀다. 재현 절차에 필요한 것은 앞의 둘이다.
def _keep_eval(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.endswith(".jsonl") or name.endswith(".py")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    return out.splitlines()


def keep(rel: str) -> bool:
    if rel in INCLUDE_FILES:
        return True
    if rel.startswith("eval/"):
        return _keep_eval(rel)
    return rel.startswith(INCLUDE_DIRS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/submission", help="복사할 곳 (기본 build/submission)")
    ap.add_argument("--list", action="store_true", help="복사하지 않고 목록만 출력")
    a = ap.parse_args()

    files = tracked()
    inc = sorted(f for f in files if keep(f))
    exc = sorted(f for f in files if not keep(f))

    def total(fs: list[str]) -> int:
        return sum((ROOT / f).stat().st_size for f in fs if (ROOT / f).exists())

    print(f"포함 {len(inc):4}개 {total(inc)/1048576:6.1f}MB")
    print(f"제외 {len(exc):4}개 {total(exc)/1048576:6.1f}MB")

    if a.list:
        for f in inc:
            print("  ", f)
        return 0

    dst = (ROOT / a.out).resolve() if not pathlib.Path(a.out).is_absolute() else pathlib.Path(a.out)
    if dst.exists():
        print(f"\n🔴 이미 있습니다: {dst}\n   지우고 다시 돌리세요 — 이 스크립트는 지우지 않습니다.")
        return 1
    for rel in inc:
        src = ROOT / rel
        if not src.exists():
            continue
        tgt = dst / rel
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, tgt)
    print(f"\n복사 완료 → {dst}")

    # ── 제출 전 확인 ──────────────────────────────────────────────
    missing = []
    if not (ROOT / "README.md").exists():
        missing.append("README.md — 환경 구성·실행 명령어 (제출 항목 1 필수)")
    if not (ROOT / "docs/API_SPEC.md").exists():
        missing.append("docs/API_SPEC.md — End-point URL + 요청/응답 스키마 (제출 항목 3 필수)")
    print("\n" + "─" * 62)
    print("수동으로 더 넣어야 하는 것 (저장소 밖 산출물)")
    print("  1. 기술 제안서 — PDF **와 워드 둘 다** (설명회 명시)")
    print("     원본 원고: docs/기술제안서/27_기술제안서_ETF판_전체원고.md")
    if missing:
        print("\n🔴 빠진 필수 파일")
        for m in missing:
            print("  -", m)
    print("─" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
