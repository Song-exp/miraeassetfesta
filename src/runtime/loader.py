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
# 외부 수집 보조 테이블 — 교차질의(구성종목·설명서) 조인용. 마스터와 함께 쓸 때만 허용 (validate_sql).
# 출처·기준일이 마스터와 다르므로 답변에 병기한다 (PROJECT.md §2 주최 Q&A: 상충 시 마스터 우선).
EXT_TABLES = ("ext_etf_holdings", "ext_ovs_etf_holdings", "ext_fund_holdings", "ext_fund_page")


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

    def planner_context(self, tables: list[str] | tuple[str, ...] = ()) -> str:
        """플래너(HCX SQL 생성)에 넘길 도메인 규칙 텍스트 — yaml 의 query_rules·normalization 을
        테이블별로 평문화한다. 교차질의면 여러 테이블을 넘겨 한 프롬프트에 합친다.
        (해석하지 않고 yaml 문자열을 그대로 싣는다 — 규칙의 원천은 yaml.)"""
        out: list[str] = []
        for t in tables or TABLES:
            doc = self.enums.get(t) or {}
            rules = doc.get("query_rules") or {}
            norm = doc.get("normalization") or {}
            if not rules and not norm:
                continue
            out.append(f"## {t}")
            for name, rule in rules.items():
                if str(name).startswith("_"):
                    continue
                body = rule if isinstance(rule, str) else yaml.safe_dump(rule, allow_unicode=True, sort_keys=False).strip()
                out.append(f"- {name}: {body}")
            if norm:
                out.append("- normalization: " + yaml.safe_dump(norm, allow_unicode=True, sort_keys=False).strip())
        return "\n".join(out)


_BIG_YAML_BYTES = 1_000_000


def _load_yaml(path: Path, header_only_if_big: bool = False) -> dict:
    """yaml 로드. 생성물(수 MB, nodes 수만 개)은 런타임에 nodes 가 필요 없다 —
    노드·alias 는 build_ontology 가 kg_* 테이블로 이미 풀어놓았다. `nodes:` 앞의 헤더(entity·property·absent_in)만 파싱해
    load_context 를 24s → 1s 로 줄인다 (2026-08-25, security_auto.yaml 9.8MB 도입 후)."""
    if header_only_if_big and path.stat().st_size > _BIG_YAML_BYTES:
        with open(path, encoding="utf-8") as f:
            head = []
            for line in f:
                if line.startswith(("nodes:", "alias_extensions:", "edges:")):
                    break
                head.append(line)
        doc = yaml.safe_load("".join(head)) or {}
        doc.setdefault("nodes", {})
        return doc
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
        doc = _load_yaml(p, header_only_if_big=True)
        entity = doc.get("entity")
        if not entity:
            continue
        ctx.entity_property[entity] = doc.get("property") or entity
        for table, why in (doc.get("absent_in") or {}).items():
            ctx.absent[(entity, table)] = why

    # 신용등급 화이트리스트 — 채권 yaml value_semantics 가 원천 (2차 데이터 15종 + 무접미 표기 'AA' 등)
    # 컬럼 키는 대문자(1차)·소문자(2차) 어느 쪽이든 받는다.
    bonds = ctx.enums.get("domestic_bonds", {})
    bcols = {str(k).lower(): v for k, v in (bonds.get("columns") or {}).items()}
    crd = (bcols.get("crd_grd") or {}).get("value_semantics") or {}
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
