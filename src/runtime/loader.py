"""판단 원천 로더 — enums/shared yaml + kg_* 테이블을 한 번 읽어 캐시한다.

🔴 여기서 읽기만 하고 해석하지 않는다. 해석(기각·주입)은 gate/pipeline 몫.
DB 는 read-only URI 로 연다 — 런타임이 데이터를 바꿀 수 있는 경로 자체를 없앤다.
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENUMS_DIR = PROJECT_ROOT / "ontology" / "enums"
SHARED_DIR = PROJECT_ROOT / "ontology" / "shared"
# 신용등급 표준표 (한국기업평가 등급정의) — 게이트가 "등급인가 / 존재하는 등급인가" 를 목록이 아니라 이 표로 판정한다
GRADE_SCALE_CSV = PROJECT_ROOT / "data" / "external" / "lookups" / "credit_grade_scale.csv"
# 라우팅 어휘로 삼을 범주형 컬럼의 고유값 상한 — 이보다 많으면 범주가 아니라 자유 텍스트(이름 등)다
ROUTE_CATEGORICAL_MAX = 60

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
    # 계층 — 조상 -> 후손 목록 (kg_closure, 이미 이행적). 정본 노드(Sec_m_*·CG_*·Idx_a_*)는 alias 가 0개고
    # 실물 노드가 여기 매달려 있다. 런타임이 이걸 안 읽으면 정본에 매칭돼도 SQL 에 넣을 값이 없다 (2026-08-30 ㉡).
    kg_closure: dict = field(default_factory=dict)     # ancestor_id -> [descendant_id]
    # 관계 — 모회사 -> 자회사 목록 (kg_edge subsidiaryOf 의 역방향). "○○의 자회사" 질의에서만 쓴다.
    kg_subsidiaries: dict = field(default_factory=dict)  # parent_id -> [child_id]
    crd_grades: set = field(default_factory=set)       # 채권 신용등급 — 2차 데이터에 실제로 있는 값 (value_semantics)
    std_grades: set = field(default_factory=set)       # 신용등급 표준표 (credit_grade_scale.csv, DB 표기+표준 표기)
    route_vocab: dict = field(default_factory=dict)    # table -> {term: weight} — 라우팅 ② 겹 어휘. DB·yaml synonyms 에서 자동 생성
    schema: dict = field(default_factory=dict)         # table -> [(column, korean_name, data_type)]

    def schema_text(self, tables: list[str] | tuple[str, ...] = ()) -> str:
        """플래너에 넘길 스키마 — "여기 없는 컬럼은 존재하지 않는다" 의 근거.

        컬럼당 한 줄이 아니라 한 줄에 몰아 씁니다. 4테이블 280컬럼을 다 실으면 프롬프트가
        커지고, 병목이 rate limit(분당 3.6질의)이라 토큰이 곧 처리량입니다 —
        그래서 호출부가 **탐지된 테이블만** 넘깁니다.
        """
        out: list[str] = []
        for t in tables or TABLES:
            cols = self.schema.get(t) or []
            if not cols:
                continue
            out.append(f"## {t}")
            out.append(", ".join(f"{c}({ko})" if ko else c for c, ko, _ in cols))
        return "\n".join(out)

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
            syn = doc.get("synonyms") or {}
            if syn:
                # 사용자 통칭 → DB 표기. 라우팅 ② 겹과 같은 원천이라 플래너도 같은 어휘로 LIKE 를 쓴다
                out.append("- 동의어(사용자 표기 → DB 표기): " + " · ".join(f"{k}→{v}" for k, v in syn.items()))
        return "\n".join(out)

    def answer_context(self, tables: list[str] | tuple[str, ...] = ()) -> str:
        """답변 생성기(compose_answer)에 넘길 규약 — yaml `answer_rules` (조회 결과를 **어떻게 말할지**).

        query_rules 는 SQL 생성기만 본다. 국공채는 등급이 없다 · 6% 초과면 주의 문구 같은 말하기 규칙은
        여기서 따로 꺼내 답변 단계에 싣는다 (2026-08-30 전수조사 §3-H)."""
        out: list[str] = []
        for t in tables or TABLES:
            rules = (self.enums.get(t) or {}).get("answer_rules") or []
            if not rules:
                continue
            out.append(f"## {t}")
            out.extend(f"- {r}" for r in (rules if isinstance(rules, list) else [rules]))
        return "\n".join(out)

    def clarify_context(self, tables: list[str] | tuple[str, ...] = ()) -> str:
        """되묻기 규칙 — yaml `clarify` 의 다의어·사람의_선택. SQL 생성기가 '어느 뜻인지 단서가 없으면
        CLARIFY: 로 되묻는' 근거다 (전수조사 §3-G). 해석하지 않고 yaml 문자열을 그대로 싣는다."""
        out: list[str] = []
        for t in tables or TABLES:
            cl = (self.enums.get(t) or {}).get("clarify") or {}
            if not cl:
                continue
            out.append(f"## {t}")
            for group in ("다의어", "사람의_선택"):
                for term, why in (cl.get(group) or {}).items():
                    out.append(f"- {term}: {str(why).strip()}")
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
    ctx.std_grades = _load_std_grades()

    with connect_readonly() as con:
        for nid, ntype, lko, len_ in con.execute(
            "select node_id, node_type, label_ko, label_en from kg_node"
        ):
            ctx.kg_nodes.append(KGNode(nid, ntype, lko, len_))
        for nid, t, c, raw in con.execute(
            "select node_id, table_name, column_name, raw_value from kg_alias"
        ):
            ctx.kg_aliases.setdefault(nid, []).append((t, c, raw))
        for anc, desc in con.execute("select ancestor_id, descendant_id from kg_closure"):
            ctx.kg_closure.setdefault(anc, []).append(desc)
        for child, parent in con.execute(
            "select src_id, dst_id from kg_edge where predicate = 'subsidiaryOf'"
        ):
            ctx.kg_subsidiaries.setdefault(parent, []).append(child)

        # 마스터 4테이블 — 한글 컬럼명은 schema_metadata 가 원천 (build_db.py 가 원본 헤더에서 만듦)
        for t, c, ko, dt in con.execute(
            "select table_name, column_name, korean_name, data_type from schema_metadata"
        ):
            ctx.schema.setdefault(t, []).append((c, ko, dt))
        # 외부 수집 테이블 — schema_metadata 대상이 아니므로(마스터가 아님) PRAGMA 로 읽는다.
        # 교차질의에서 조인 대상이 되므로 컬럼명은 플래너가 알아야 한다.
        for t in EXT_TABLES:
            cols = [(r[1], "", r[2]) for r in con.execute(f"pragma table_info({t})")]
            if cols:
                ctx.schema[t] = cols
        ctx.route_vocab = _build_route_vocab(con, ctx)
    return ctx


def _load_std_grades() -> set:
    """신용등급 표준표 — DB 표기(AA0)와 표준 표기(AA) 둘 다. 파일이 없으면 빈 집합(게이트는 데이터 값만으로 판정)."""
    if not GRADE_SCALE_CSV.exists():
        return set()
    with open(GRADE_SCALE_CSV, encoding="utf-8") as f:
        rows = csv.DictReader(line for line in f if not line.startswith("#"))
        grades = set()
        for r in rows:
            grades.add((r.get("grade_db") or "").strip())
            grades.add((r.get("grade_std") or "").strip())
    grades.discard("")
    return grades


# 라우팅 어휘에서 빼는 것 — 상품 명사는 ① 겹(문장 구조)이 다루고, 회사 표기의 군더더기는 경계 검사를 방해한다
_VOCAB_STRIP = re.compile(r"\(주\)|주식회사|\s+")
_VOCAB_NUMERIC = re.compile(r"[\d.\-/]+")
PRODUCT_NOUNS = ("채권", "ETF", "ETN", "펀드")


def _build_route_vocab(con: sqlite3.Connection, ctx: RuntimeContext) -> dict:
    """라우팅 ② 겹 어휘 — "질문에 어느 테이블의 값이 나오는가" 를 재기 위한 테이블별 {값: 가중치}.

    사람이 쓴 단어 목록이 아니다. 전부 DB 와 yaml 에서 온다:
      · kg_alias 의 raw 값(발행사·운용사·지수·종목) — 3
      · 범주형 텍스트 컬럼(고유값 ≤ ROUTE_CATEGORICAL_MAX)의 값(대분류·소분류·채권종류·자산군 …) — 2
      · ETF 약어명(pd_abrv_nm) — 3 ('KODEX 국고채3년' 이 채권 값 '국고채' 보다 길어 이긴다)
      · yaml `synonyms` 의 사용자 표기(통안채·영구채 …) — 2
    실측 1.7s (2026-08-30). 프로세스당 1회.
    """
    vocab: dict[str, dict[str, int]] = {t: {} for t in TABLES}

    def add(t: str, term, w: int, min_len: int = 3) -> None:
        term = _VOCAB_STRIP.sub("", str(term or "")).strip()
        if len(term) < min_len or _VOCAB_NUMERIC.fullmatch(term) or term in PRODUCT_NOUNS:
            return
        vocab[t][term] = max(vocab[t].get(term, 0), w)

    for t, raw in con.execute("select table_name, raw_value from kg_alias"):
        if t in vocab:
            add(t, raw, 3)
    for t in TABLES:
        for _, col, typ, *_ in con.execute(f"pragma table_info({t})"):
            if "text" not in (typ or "").lower():
                continue
            n = con.execute(f"select count(distinct trim({col})) from {t}").fetchone()[0]
            if 1 < n <= ROUTE_CATEGORICAL_MAX:
                for (v,) in con.execute(f"select distinct trim({col}) from {t} where {col} is not null"):
                    add(t, v, 2)
    for t in ("domestic_etfs", "overseas_etfs"):
        for (v,) in con.execute(f"select distinct trim(pd_abrv_nm) from {t} where pd_abrv_nm is not null"):
            add(t, v, 3)
    for t in TABLES:
        for term in ((ctx.enums.get(t) or {}).get("synonyms") or {}):
            add(t, term, 2, min_len=2)          # '국채'·'만기' 같은 2자 통칭 — yaml 이 고른 것만
    return vocab
