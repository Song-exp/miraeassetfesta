# -*- coding: utf-8 -*-
"""온톨로지 yaml 중복 키 검사.

`yaml.safe_load` 는 같은 키가 두 번 나오면 **조용히 뒤엣것만 남긴다**.
판정 문서에서는 이게 치명적이다 — 검수로 확정한 지침이 옛 지침에 덮여 사라져도
빌드는 통과하고 테스트도 통과한다. 실제로 2026-08-26 에
`public_funds.yaml` 의 `fd_last_dstb_r.answer_policy` 가 두 번 선언돼
"단위 미확정 → 수치 인용 금지" 결론이 사라지고, 플래너에게 순위 산출을
지시하는 옛 지침만 남아 있었다.

사용법:
    python scripts/check_yaml_dupkeys.py            # ontology/ 전체
    python scripts/check_yaml_dupkeys.py <경로>...  # 특정 파일·디렉터리

종료 코드: 중복이 하나라도 있으면 1 (CI 에 걸 수 있게).
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.constructor import DuplicateKeyError
except ImportError:  # pragma: no cover
    sys.exit("ruamel.yaml 이 필요합니다:  pip install ruamel.yaml")


def iter_yaml(targets: list[str]) -> list[Path]:
    paths: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            paths.extend(sorted(p.rglob("*.yaml")))
        elif p.is_file():
            paths.append(p)
    return paths


def main() -> int:
    # Windows 콘솔 기본 cp949 에서 ❌ 같은 문자가 깨지지 않게
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    targets = sys.argv[1:] or ["ontology"]
    files = iter_yaml(targets)
    if not files:
        print("검사할 yaml 이 없습니다.")
        return 0

    yaml = YAML()
    yaml.allow_duplicate_keys = False  # 중복을 예외로 승격

    bad = 0
    for p in files:
        try:
            yaml.load(p.read_text(encoding="utf-8"))
        except DuplicateKeyError as e:
            bad += 1
            first = str(e).strip().splitlines()[0]
            print(f"❌ {p}\n   {first}")
            for line in str(e).splitlines():
                if 'line' in line and 'column' in line:
                    print(f"   {line.strip()}")
        except Exception as e:  # 파싱 자체 실패도 알린다
            bad += 1
            print(f"❌ {p} — 파싱 실패: {type(e).__name__}: {str(e).splitlines()[0]}")

    print(f"\n검사 {len(files)}개 · 문제 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
