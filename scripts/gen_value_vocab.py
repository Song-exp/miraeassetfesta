# -*- coding: utf-8 -*-
"""범주값 어휘 생성 — ontology/enums/<domain>.vocab.yaml (2026-08-30 개선 R-1).

무엇: KG alias 가 없는 **저카디널리티 텍스트 컬럼**(고유값 2~MAX)의 실제 값 목록. 플래너는 컬럼 이름·한글명만 받고
값 어휘는 못 받았다 — '변동금리'·'이표채'·'실물복제'·'수수료선취' 를 HCX 가 추측하던 자리다 (개정안 R-1, 37컬럼).
쓰임: ① loader.planner_context 가 프롬프트에 싣는다 ② guard.check_values 가 WHERE 리터럴을 이 값과 대조한다.
원천: DB distinct 값 그대로(trim). 사람이 판정한 것은 <domain>.yaml `value_vocab_notes` 로 따로 둔다 — 이 파일은 재생성된다.

사용: python scripts/gen_value_vocab.py            # 4도메인 전부
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.runtime.loader import TABLES  # noqa: E402

DB = ROOT / "data" / "financial_products.db"
OUT = ROOT / "ontology" / "enums"
MAX_DISTINCT = 40
SKIP_SUFFIX = ("_no", "_cd_desc",)      # 식별자는 제외 (값 목록이 의미 없음)
SKIP_COLS = {"pd_isin_cd", "pd_itm_no", "pd_itm_no_ma", "pd_grp_no_ma"}


def main() -> None:
    con = sqlite3.connect(f"{DB.resolve().as_uri()}?mode=ro", uri=True)
    aliased = {(t, c) for t, c in con.execute("select distinct table_name, column_name from kg_alias")}
    meta = {(t, c): ko for t, c, ko in con.execute("select table_name, column_name, korean_name from schema_metadata")}
    for t in TABLES:
        vocab: dict[str, dict] = {}
        for _, col, typ, *_ in con.execute(f"pragma table_info({t})"):
            if "text" not in (typ or "").lower() or (t, col) in aliased or col in SKIP_COLS or col.endswith("_no"):
                continue
            rows = con.execute(
                f"select trim({col}), count(*) from {t} where {col} is not null and trim({col})<>'' group by 1 order by 2 desc"
            ).fetchall()
            if not 2 <= len(rows) <= MAX_DISTINCT:
                continue
            vocab[col] = {
                "korean_name": meta.get((t, col), ""),
                "values": [v for v, _ in rows],
                "counts": {v: n for v, n in rows},
            }
        doc = {
            "domain": t,
            "generated": True,
            "source": "scripts/gen_value_vocab.py — DB distinct (trim) · 기준일 2026-08-22 · 직접 편집 금지",
            "_note": "범주형 컬럼의 실제 값 목록. 플래너 프롬프트에 실리고(loader.planner_context) WHERE 리터럴 검사(guard.check_values)에 쓰인다. "
                     "코드값('10','20' 등)의 뜻은 <domain>.yaml columns.*.note 가 원천.",
            "value_vocab": vocab,
        }
        path = OUT / f"{t}.vocab.yaml"
        path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
        print(f"✅ {path.name}: {len(vocab)}컬럼 · {sum(len(v['values']) for v in vocab.values())}값")


if __name__ == "__main__":
    main()
