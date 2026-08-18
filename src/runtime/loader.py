"""판단 원천 로더 — enums/shared yaml + kg_* 테이블을 한 번 읽어 캐시한다.

🔴 여기서 읽기만 하고 해석하지 않는다. 해석(기각·주입)은 gate/pipeline 몫.
DB 는 read-only URI 로 연다 — 런타임이 데이터를 바꿀 수 있는 경로 자체를 없앤다.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENUMS_DIR = PROJECT_ROOT / "ontology" / "enums"
SHARED_DIR = PROJECT_ROOT / "ontology" / "shared"

# 주최 측 마스터 4테이블 — SQL guard 의 화이트리스트이기도 하다
TABLES = ("domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds")


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH") or PROJECT_ROOT / "data" / "financial_products.db")


def connect_readonly() -> sqlite3.Connection:
    return sqlite3.connect(f"{db_path().resolve().as_uri()}?mode=ro", uri=True)


@dataclass
class KGNode:
    node_id: str
    node_type: str
    label_ko: str | None
    label_en: str | None

    @property
    def labels(self) -> list[str]:
        return [x for x in (self.label_ko, self.label_en) if x]


@dataclass
class RuntimeContext:
    """파이프라인이 매 질의마다 참조하는 불변 지식. 프로세스당 1회 로드."""

    enums: dict = field(default_factory=dict)          # domain -> yaml dict
    absent: dict = field(default_factory=dict)         # (entity, table) -> 사유 문자열
    entity_property: dict = field(default_factory=dict)  # entity -> .ttl property 이름
    kg_nodes: list[KGNode] = field(default_factory=list)
    kg_aliases: dict = field(default_factory=dict)     # node_id -> [(table, column, raw)]
    crd_grades: set = field(default_factory=set)       # 채권 신용등급 enum 화이트리스트


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def load_context() -> RuntimeContext:
    ctx = RuntimeContext()

    for p in sorted(ENUMS_DIR.glob("*.yaml")):
        doc = _load_yaml(p)
        if doc.get("domain"):
            ctx.enums[doc["domain"]] = doc

    for p in sorted(SHARED_DIR.glob("*.yaml")):
        doc = _load_yaml(p)
        entity = doc.get("entity")
        if not entity:
            continue
        ctx.entity_property[entity] = doc.get("property") or entity
        for table, why in (doc.get("absent_in") or {}).items():
            ctx.absent[(entity, table)] = why

    # 신용등급 화이트리스트 — 채권 yaml value_semantics 가 원천 (CRD_GRD 20종 + EVCO 무접미 표기)
    bonds = ctx.enums.get("domestic_bonds", {})
    crd = ((bonds.get("columns") or {}).get("CRD_GRD") or {}).get("value_semantics") or {}
    ctx.crd_grades = set(crd)
    ctx.crd_grades |= {g.rstrip("0") for g in crd if g.endswith("0")}  # 'AA0' 의 EVCO 표기 'AA'

    with connect_readonly() as con:
        for nid, ntype, lko, len_ in con.execute(
            "select node_id, node_type, label_ko, label_en from kg_node"
        ):
            ctx.kg_nodes.append(KGNode(nid, ntype, lko, len_))
        for nid, t, c, raw in con.execute(
            "select node_id, table_name, column_name, raw_value from kg_alias"
        ):
            ctx.kg_aliases.setdefault(nid, []).append((t, c, raw))
    return ctx
