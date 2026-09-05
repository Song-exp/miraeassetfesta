"""판단 원천 로더 — enums/shared yaml + kg_* 테이블을 한 번 읽어 캐시한다.

🔴 여기서 읽기만 하고 해석하지 않는다. 해석(기각·주입)은 gate/pipeline 몫.
DB 는 read-only URI 로 연다 — 런타임이 데이터를 바꿀 수 있는 경로 자체를 없앤다.
"""

from __future__ import annotations

import csv
import os
import re
import json
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
    # KG 1R S1 — 라벨 슬롯 체계: 정식명(코드북)·구상호·후계 노드·출처(curated/auto/derived). derived(종목명 접두 최빈값)는 매칭 키에서 제외
    label_official: str | None = None
    former_names: list = field(default_factory=list)
    successor: str | None = None
    provenance: str = "curated"

    @property
    def labels(self) -> list[str]:
        out = []
        for x in (self.label_ko, self.label_official, self.label_en):
            if x and x not in out:
                out.append(x)
        return out


@dataclass
class RuntimeContext:
    """파이프라인이 매 질의마다 참조하는 불변 지식. 프로세스당 1회 로드."""

    enums: dict = field(default_factory=dict)          # domain -> yaml dict
    absent: dict = field(default_factory=dict)         # (entity, table) -> 사유 문자열
    entity_property: dict = field(default_factory=dict)  # entity -> .ttl property 이름
    kg_nodes: list[KGNode] = field(default_factory=list)
    kg_aliases: dict = field(default_factory=dict)     # node_id -> [(table, column, raw)]
    kg_node_by_id: dict = field(default_factory=dict)  # node_id -> KGNode (S1 후계 노드 조회)
    kg_alias_kind: dict = field(default_factory=dict)  # (node_id, table, column, raw) -> match_kind ('token' 등, 'eq' 는 생략) — S3 token alias
    # 계층 — 조상 -> 후손 목록 (kg_closure, 이미 이행적). 정본 노드(Sec_m_*·CG_*·Idx_a_*)는 alias 가 0개고
    # 실물 노드가 여기 매달려 있다. 런타임이 이걸 안 읽으면 정본에 매칭돼도 SQL 에 넣을 값이 없다 (2026-08-30 ㉡).
    kg_closure: dict = field(default_factory=dict)     # ancestor_id -> [descendant_id]
    # 관계 — 모회사 -> 자회사 목록 (kg_edge subsidiaryOf 의 역방향). "○○의 자회사" 질의에서만 쓴다.
    kg_subsidiaries: dict = field(default_factory=dict)  # parent_id -> [child_id]
    crd_grades: set = field(default_factory=set)       # 채권 신용등급 — 2차 데이터에 실제로 있는 값 (value_semantics)
    std_grades: set = field(default_factory=set)       # 신용등급 표준표 (credit_grade_scale.csv, DB 표기+표준 표기)
    route_vocab: dict = field(default_factory=dict)    # table -> {term: weight} — 라우팅 ② 겹 어휘. DB·yaml synonyms 에서 자동 생성
    route_products: dict = field(default_factory=dict) # table -> {상품명 term} — 이 매치가 있는 테이블은 라우팅 점수컷 면제
    schema: dict = field(default_factory=dict)         # table -> [(column, korean_name, data_type)]
    # ── 2026-08-30 개선 (docs/research/온톨로지_개정안_2026-08-30.md) ──
    refusal_rules: dict = field(default_factory=dict)  # R-5 ② 층 — enums/_refusal.yaml (사유명 -> 규칙 문장). 플래너가 REFUSE: 를 내는 근거
    value_vocab: dict = field(default_factory=dict)    # R-1 — (table, column) -> [값…]  범주형 컬럼의 실제 값 목록 (enums/<domain>.vocab.yaml, 생성물)
    value_index: dict = field(default_factory=dict)    # R-4 — (table, column) -> {정규화 값}  WHERE 리터럴 검사용. **전 값을 아는 컬럼만** 들어간다
    gate_constants: dict = field(default_factory=dict) # R-5 ① 층 — table -> [{column, value, triggers[], answer}] 상수 컬럼 위반 (enums yaml gate_constants)
    grade_ranges: dict = field(default_factory=dict)   # KG 1R S6 — table -> {min,max,label_min,label_max,note} (shared/risk_grade.yaml range_by_table)
    absent_props: dict = field(default_factory=dict)   # KG 1R S5 — table -> [{property, why, vocab[], substitute}] 부재 속성 선언 (enums yaml absent_properties → ttl ABSENT + 게이트 어휘)
    similarity_axes: dict = field(default_factory=dict) # 2026-09-05 #73 — table -> {default[], axes{col: {vocab, kind, …}}, same_kind[], buckets, exclude_issuer_vocab} '비슷한 상품' 확정식의 축 표 (enums yaml similarity_axes)

    # 2026-09-05 #78 — table -> {column: 재생성 사유}. 컬럼 정책이 "사용 금지" 로 못 박은 컬럼을 쓴 SQL 은
    # 기각해 재생성 사유로 돌려준다(pipeline.forbidden_column_use). 🔴 반드시 **테이블 단위**다 — 같은
    # 컬럼명이 다른 도메인에서 정반대 사실을 가질 수 있다(2026-09-04 DOM-03: 채권용 curr_cd 규칙이 펀드를 기각).
    forbidden_cols: dict = field(default_factory=dict)

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

    def planner_context(self, tables: list[str] | tuple[str, ...] = (), question: str | None = None) -> str:
        """플래너(HCX SQL 생성)에 넘길 도메인 규칙 텍스트 — yaml 의 query_rules·normalization 을
        테이블별로 평문화한다. 교차질의면 여러 테이블을 넘겨 한 프롬프트에 합친다.
        (해석하지 않고 yaml 문자열을 그대로 싣는다 — 규칙의 원천은 yaml.)

        2026-08-30 R-2 — 규칙 2층: 값이 `{text:, triggers:[…]}` 꼴이면 **triggered** 규칙이다. `question` 이 주어졌을 때
        triggers 낱말이 하나라도 질문에 있어야 싣는다(없으면 뺀다). 문자열 규칙은 종전대로 always_on.
        question 을 안 주면 전부 싣는다(호환 — 테스트·문서 생성기). 근거: 규칙 전부 주입 < 선별 주입 (DK-1 Table VI).
        2026-08-30 R-1 — value_vocab(범주형 컬럼의 실제 값)을 같이 싣는다. 값을 모르면 HCX 가 리터럴을 추측한다."""
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
                if isinstance(rule, dict) and "triggers" in rule:
                    # 🔴 대소문자 무시 — 사람은 'kodex'·'ai' 라고도 쓴다. 트리거가 대문자(KODEX·AI)로만
                    #    등록돼 있으면 소문자 질의에서 규칙이 통째로 빠진다 (2026-09-01, ETF triggers 도입 시 실측).
                    #    트리거 누락은 규칙 미주입 = 오답이고, 과잉 주입은 무해하므로 casefold 로 넓게 맞춘다.
                    if question is not None:
                        q_cf = question.casefold()
                        if not any(str(w).casefold() in q_cf for w in rule.get("triggers") or []):
                            continue
                if isinstance(rule, dict) and "text" in rule:
                    # 🔴 2026-09-03 — dict 규칙은 **text 만** 싣는다. 종전엔 triggers 가 있는 dict 만
                    #    text 를 꺼내고 나머지 dict 는 통째로 safe_dump 했다. `enforce`(가드 슬롯,
                    #    docs/guard_to_yaml_migration_2026-09-03.md)를 붙이면 when·action·sql·mark 가
                    #    전부 프롬프트로 새어 나간다 — 적용기만 읽어야 하는 값이다. 실측으로 확인했다.
                    rule = rule.get("text", "")
                body = rule if isinstance(rule, str) else yaml.safe_dump(rule, allow_unicode=True, sort_keys=False).strip()
                out.append(f"- {name}: {body}")
            if norm:
                # 2026-08-31 압축 — 사람용 주석 키(_·🔴·실측·주의…)는 프롬프트에서 뺀다.
                # 실측: 펀드 planner_context 11,599자 중 normalization 덤프가 6,287자(54%)였고 대부분이
                # 경고·이력 주석이었다. 규칙의 원천(yaml)은 그대로 — 싣는 요약만 조작 가능한 키로 한정.
                out.append("- normalization: "
                           + yaml.safe_dump(_strip_annotations(norm), allow_unicode=True, sort_keys=False).strip())
            syn = doc.get("synonyms") or {}
            if syn:
                # 사용자 통칭 → DB 표기. 라우팅 ② 겹과 같은 원천이라 플래너도 같은 어휘로 LIKE 를 쓴다
                out.append("- 동의어(사용자 표기 → DB 표기): " + " · ".join(f"{k}→{v}" for k, v in syn.items()))
            vocab = [(c, v) for (tt, c), v in self.value_vocab.items() if tt == t]
            if vocab:
                out.append("- 범주형 컬럼의 실제 값 (이 값 그대로 = 로 쓴다. 목록 밖 값을 만들지 않는다): "
                           + " · ".join(f"{c}∈{{{', '.join(v)}}}" for c, v in vocab))
        return "\n".join(out)

    def refusal_context(self) -> str:
        """R-5 ② 층 — enums/_refusal.yaml 의 답변불가 사유. 플래너가 SQL 대신 'REFUSE: <사유>' 를 내는 근거."""
        if not self.refusal_rules:
            return ""
        return "\n".join(f"- {k}: {str(v).strip()}" for k, v in self.refusal_rules.items() if not str(k).startswith("_"))

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


def _strip_annotations(obj):
    """normalization 을 프롬프트에 실을 때 사람용 주석 키를 걷어낸다 — 조작 가능한 것(컬럼 목록·패턴·sql)만 남긴다."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            ks = str(k)
            if ks.startswith("_") or ks.startswith("🔴") or any(
                    w in ks for w in ("실측", "주의", "근거", "한계", "기각", "화이트리스트", "note")):
                continue
            out[k] = _strip_annotations(v)
        return out
    if isinstance(obj, list):
        return [_strip_annotations(v) for v in obj]
    return obj


@lru_cache(maxsize=1)
def load_context() -> RuntimeContext:
    ctx = RuntimeContext()

    for p in sorted(ENUMS_DIR.glob("*.yaml")):
        doc = _load_yaml(p)
        if p.name.endswith(".vocab.yaml"):
            # R-1 — 생성물(scripts/gen_value_vocab.py). 도메인 yaml 을 덮지 않고 별도 사전으로 둔다
            for col, spec in (doc.get("value_vocab") or {}).items():
                ctx.value_vocab[(doc["domain"], col)] = list(spec.get("values") or [])
            continue
        if p.name == "_refusal.yaml":
            ctx.refusal_rules = doc.get("refusal_rules") or {}
            if doc.get("출력_형식"):
                ctx.refusal_rules["_출력_형식"] = doc["출력_형식"]
            continue
        if doc.get("domain"):
            ctx.enums[doc["domain"]] = doc
            for item in doc.get("gate_constants") or []:
                # 🔴 상수인지 아닌지는 **스코프 선언**이 정한다 (2026-09-04). `scope_key` 가 달린 항목은
                #    enums `scope` 의 값이 하나일 때만 상수 게이트로 산다 — 값이 둘 이상이면(외화채가 적재되면)
                #    더 이상 상수가 아니므로 게이트에서 뺀다. 1차엔 USD·JPY·EUR 가 있었다: 한 번 변한 축이다.
                key = item.get("scope_key")
                if key:
                    vals = scope_values(doc["domain"], key)
                    if len(vals) != 1:
                        continue
                    item = dict(item, value=vals[0])
                ctx.gate_constants.setdefault(doc["domain"], []).append(item)
            for item in doc.get("absent_properties") or []:
                ctx.absent_props.setdefault(doc["domain"], []).append(item)
            if doc.get("similarity_axes"):
                ctx.similarity_axes[doc["domain"]] = doc["similarity_axes"]
            if doc.get("forbidden_columns"):
                ctx.forbidden_cols[doc["domain"]] = {
                    str(c): " ".join(str(why).split()) for c, why in doc["forbidden_columns"].items()}

    for p in sorted(SHARED_DIR.glob("*.yaml")):
        doc = _load_yaml(p, header_only_if_big=True)
        entity = doc.get("entity")
        if not entity:
            continue
        ctx.entity_property[entity] = doc.get("property") or entity
        for table, why in (doc.get("absent_in") or {}).items():
            ctx.absent[(entity, table)] = why
        for table, spec in (doc.get("range_by_table") or {}).items():
            ctx.grade_ranges[table] = dict(spec, entity=entity)

    # 신용등급 화이트리스트 — 채권 yaml value_semantics 가 원천 (2차 데이터 15종 + 무접미 표기 'AA' 등)
    # 컬럼 키는 대문자(1차)·소문자(2차) 어느 쪽이든 받는다.
    bonds = ctx.enums.get("domestic_bonds", {})
    bcols = {str(k).lower(): v for k, v in (bonds.get("columns") or {}).items()}
    crd = (bcols.get("crd_grd") or {}).get("value_semantics") or {}
    ctx.crd_grades = set(crd)
    ctx.crd_grades |= {g.rstrip("0") for g in crd if g.endswith("0")}  # 'AA0' 의 EVCO 표기 'AA'
    ctx.std_grades = _load_std_grades()

    with connect_readonly() as con:
        node_cols = {r[1] for r in con.execute("pragma table_info(kg_node)")}
        extra = "label_official, former_names, successor, provenance" if "provenance" in node_cols else "NULL, NULL, NULL, 'curated'"
        for nid, ntype, lko, len_, lof, former, succ, prov in con.execute(
            f"select node_id, node_type, label_ko, label_en, {extra} from kg_node"
        ):
            node = KGNode(nid, ntype, lko, len_, lof, json.loads(former) if former else [], succ, prov or "curated")
            ctx.kg_nodes.append(node)
            ctx.kg_node_by_id[nid] = node
        alias_cols = {r[1] for r in con.execute("pragma table_info(kg_alias)")}
        kind_col = "match_kind" if "match_kind" in alias_cols else "'eq'"
        for nid, t, c, raw, kind in con.execute(
            f"select node_id, table_name, column_name, raw_value, {kind_col} from kg_alias"
        ):
            ctx.kg_aliases.setdefault(nid, []).append((t, c, raw))
            if kind and kind != "eq":
                ctx.kg_alias_kind[(nid, t, c, raw)] = kind
        for anc, desc in con.execute("select ancestor_id, descendant_id from kg_closure"):
            ctx.kg_closure.setdefault(anc, []).append(desc)
        for child, parent in con.execute(
            "select src_id, dst_id from kg_edge where predicate = 'subsidiaryOf'"
        ):
            ctx.kg_subsidiaries.setdefault(parent, []).append(child)

        # 마스터 4테이블 — 한글 컬럼명은 schema_metadata 가 원천 (build_db.py 가 원본 헤더에서 만듦)
        # 2026-08-31 — yaml `schema_exclude` 컬럼은 스키마 프롬프트에서 뺀다(전건 결측·답변금지).
        # 스키마 서두가 "여기 없는 컬럼은 존재하지 않는다" 라서, 빼면 플래너가 참조 자체를 못 한다.
        excluded = {(t, c) for t, doc in ctx.enums.items() for c in (doc.get("schema_exclude") or [])}
        for t, c, ko, dt in con.execute(
            "select table_name, column_name, korean_name, data_type from schema_metadata"
        ):
            if (t, c) in excluded:
                continue
            ctx.schema.setdefault(t, []).append((c, ko, dt))
        # 외부 수집 테이블 — schema_metadata 대상이 아니므로(마스터가 아님) PRAGMA 로 읽는다.
        # 교차질의에서 조인 대상이 되므로 컬럼명은 플래너가 알아야 한다.
        for t in EXT_TABLES:
            cols = [(r[1], "", r[2]) for r in con.execute(f"pragma table_info({t})")]
            if cols:
                ctx.schema[t] = cols
        ctx.route_vocab, ctx.route_products = _build_route_vocab(con, ctx)
        ctx.value_index = _build_value_index(con, ctx)
    # validate_sql 이 `테이블.컬럼` 수식자의 소속을 검사할 수 있게 색인을 넘긴다
    # (ctx 를 못 받는 순수 함수라 모듈 캐시로 준다 — 2026-08-31 'domestic_etfs.weight_pct' 실측)
    from .pipeline import set_column_index
    set_column_index(ctx.schema)
    validate_enforce(ctx)
    return ctx


# ── enforce 슬롯 검증 (V8 성격) — docs/guard_to_yaml_migration_2026-09-03.md §2-2 ──
# 빌드 게이트 V1~V7 과 같은 태도로 **로드를 거부**한다. 슬롯은 SQL 을 고치므로,
# 오타 하나가 조용히 "발동 안 함" 으로 끝나면 가드를 뗀 뒤에 오답으로 나타난다.
_WHEN_AXES = {"tables", "question", "grounded", "sql"}
_SQL_AXES = {"has", "lacks", "any_of_has"}
_QUESTION_AXES = {"any", "not_any"}
_PLACEHOLDER = re.compile(r"\{(\w+)(?::nospace)?\}")
_KNOWN_PLACEHOLDERS = {"fund_key", "code", "key", "col", "type", "brand", "token"}


def validate_enforce(ctx: "RuntimeContext") -> None:
    from .guard import ENFORCE_ACTIONS

    marks: dict[str, str] = {}
    errs: list[str] = []
    for t in TABLES:
        cols = {c for c, _ko, _ty in (ctx.schema.get(t) or [])}
        for name, rule in ((ctx.enums.get(t) or {}).get("query_rules") or {}).items():
            enf = rule.get("enforce") if isinstance(rule, dict) else None
            if not isinstance(enf, dict) or enf.get("enabled", True) is False:
                continue
            where = f"{t}.query_rules.{name}.enforce"
            action = enf.get("action")
            if action not in ENFORCE_ACTIONS:
                errs.append(f"{where}: action '{action}' 은 지원 목록 {ENFORCE_ACTIONS} 밖")
            if action == "replace_expr" and not (enf.get("from") or enf.get("from_pattern")):
                errs.append(f"{where}: replace_expr 은 from(리터럴) 또는 from_pattern(정규식)이 필요하다")
            if action == "replace_predicate" and not enf.get("from_pattern"):
                errs.append(f"{where}: replace_predicate 은 from_pattern 이 필요하다")
            if enf.get("from") and action != "replace_expr":
                errs.append(f"{where}: from 은 replace_expr 에서만 쓴다")
            if enf.get("from") and enf.get("from_pattern"):
                errs.append(f"{where}: from 과 from_pattern 을 함께 쓰지 않는다")
            mark = str(enf.get("mark") or "")
            if not mark:
                errs.append(f"{where}: mark 가 없다")
            elif mark in marks:
                errs.append(f"{where}: mark '{mark}' 가 {marks[mark]} 와 중복")
            else:
                marks[mark] = where
            when = enf.get("when") or {}
            if set(when) - _WHEN_AXES:
                errs.append(f"{where}.when: 다섯 축 밖의 키 {sorted(set(when) - _WHEN_AXES)}")
            if set(when.get("sql") or {}) - _SQL_AXES:
                errs.append(f"{where}.when.sql: 허용 밖 {sorted(set(when['sql']) - _SQL_AXES)}")
            if set(when.get("question") or {}) - _QUESTION_AXES:
                errs.append(f"{where}.when.question: 허용 밖 {sorted(set(when['question']) - _QUESTION_AXES)}")
            for tb in when.get("tables") or []:
                if tb not in TABLES:
                    errs.append(f"{where}.when.tables: '{tb}' 는 마스터 테이블이 아니다")
            # 확정식의 컬럼이 그 테이블에 실재하는가 — 자리표시자는 검사 대상 밖
            body = _PLACEHOLDER.sub("", str(enf.get("sql") or "") + " " + str(enf.get("sql_union") or ""))
            for ident in set(re.findall(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", body)):
                if ident not in cols and ident not in ctx.schema:
                    errs.append(f"{where}.sql: '{ident}' 는 {t} 의 컬럼이 아니다")
            for ph in set(_PLACEHOLDER.findall(str(enf.get("sql") or "") + str(enf.get("sql_union") or ""))):
                if ph not in _KNOWN_PLACEHOLDERS and not ph.isdigit():
                    errs.append(f"{where}.sql: 모르는 자리표시자 {{{ph}}}")
    if errs:
        raise ValueError("enforce 슬롯 검증 실패 (로드 거부):\n  - " + "\n  - ".join(errs))


def _build_value_index(con: sqlite3.Connection, ctx: RuntimeContext) -> dict:
    """R-4 — WHERE 리터럴 검사용 값 집합. **전 값을 아는 컬럼만**: ① kg_alias 가 그 컬럼의 distinct 를 사실상 다 덮는
    컬럼(≥ 98%) ② value_vocab 컬럼. 부분 사전(이름·자유 텍스트)은 넣지 않는다 — 정상 값을 기각하면 안 된다.
    키 ('_raw', table, col) 에는 힌트용 원값 몇 개를 둔다."""
    index: dict = {}
    by_col: dict[tuple[str, str], set] = {}
    raw_by_col: dict[tuple[str, str], set] = {}
    for t, c, raw in con.execute("select table_name, column_name, raw_value from kg_alias"):
        by_col.setdefault((t, c), set()).add(str(raw).strip().casefold())
        raw_by_col.setdefault((t, c), set()).add(str(raw).strip())
    for (t, c), vals in by_col.items():
        if t not in TABLES:
            continue
        try:
            n = con.execute(f"select count(distinct trim({c})) from {t} where {c} is not null").fetchone()[0]
        except sqlite3.Error:
            continue
        if n and len(vals) >= 0.98 * n:
            index[(t, c)] = vals
            # 🔴 원값은 **전부** 둔다 — 2026-09-02 실측: 12개 표본만 두면 pd_pbcm(1,818값)의 힌트·근사치환이
            #    사전순 앞 12개('(주)BNK금융지주'…)에 갇혀 '한국전력공사' → '한국전력공사(주)' 를 찾지 못한다.
            #    힌트는 guard._value_hints 가 어간 포함 순으로 4개만 추리고, 근사치환은 유일 후보일 때만 한다.
            index[("_raw", t, c)] = sorted(raw_by_col[(t, c)])
    for (t, c), values in ctx.value_vocab.items():
        index[(t, c)] = {str(v).strip().casefold() for v in values}
        index[("_raw", t, c)] = list(values)
    return index


@lru_cache(maxsize=1)
def dataset_scope() -> dict:
    """이 적재분의 범위·기준일 선언 — shared/dataset.yaml. 없으면 빈 dict(호출자가 종전 상수로 물러선다).

    날짜를 코드 상수로 두면 서비스로 옮길 때(‘오늘’ 이 매일 바뀔 때) 코드를 고쳐야 한다.
    선언에서 읽으면 배포 설정만 바뀐다 (2026-09-04)."""
    p = SHARED_DIR / "dataset.yaml"
    return _load_yaml(p) if p.exists() else {}


@lru_cache(maxsize=4)
def kind_filter_decl(table: str, particle: str) -> tuple[tuple, tuple]:
    """상품 종류 확정식 선언 — enums/<table>.yaml `kind_filters`.

    반환: (낱말 목록[(token, sql), …], 서술형 목록[(compiled_pattern, sql), …]).
    낱말 항목의 `regex` 는 별칭 정규식('국채' 처럼 합성어를 걸러야 하는 통칭)이고, 서술형의 `{P}` 는
    호출자가 넘긴 조사+'발행' 정규식으로 채운다. 종류를 늘리는 일이 코드 수정이 아니라 선언 한 줄이 되게 한다."""
    p = ENUMS_DIR / f"{table}.yaml"
    decl = (_load_yaml(p) if p.exists() else {}).get("kind_filters") or {}
    toks, alias = [], []
    for item in decl.get("tokens") or []:
        tok, sql = item.get("token"), item.get("sql")
        if not tok or not sql:
            continue
        toks.append((tok, sql))
        if item.get("regex"):
            alias.append((re.compile(item["regex"]), sql))
    paras = [(re.compile(str(i["pattern"]).replace("{P}", particle)), i["sql"])
             for i in (decl.get("paraphrases") or []) if i.get("pattern") and i.get("sql")]
    return tuple(toks), tuple(alias + paras)


def scope_values(table: str, key: str) -> list:
    """테이블 스코프의 한 축(통화·발행국 …)에 담긴 값 목록 — enums/<table>.yaml `scope`.

    값이 하나면 '이 적재분에서는 상수', 여럿이면 더 이상 상수가 아니다. 게이트 상수(gate_constants)가
    이 판정을 참조하므로, 데이터 범위가 넓어지면 게이트가 자동으로 막지 않는다."""
    p = ENUMS_DIR / f"{table}.yaml"
    doc = _load_yaml(p) if p.exists() else {}
    v = ((doc.get("scope") or {}).get(key) or {})
    vals = v.get("values") if isinstance(v, dict) else v
    return list(vals or [])


@lru_cache(maxsize=4)
def grade_scale(table: str = "domestic_bonds", column: str = "crd_grd") -> tuple[str, ...]:
    """신용등급 서열 — 표준표(rank 순)에 **이 데이터에 실재하는 표기만** 남긴 DB 표기 목록(우량→하위).

    두 원천을 각자의 자리에서 읽는다 — 코드에 등급 목록을 적지 않는다.
      · 순서·경계(무엇이 무엇보다 위인가) = 표준표 코드북 credit_grade_scale.csv (= shared/credit_grade.yaml 노드의 원천)
      · 실재 여부(무엇이 이 적재분에 있는가) = 값 사전 enums/<table>.yaml columns.<column>.value_semantics
    새 데이터에 CCC·D 가 들어오면 값 사전만 갱신되고 서열 확장은 코드 수정 없이 따라온다.
    반대로 표준표에 없는 표기는 서열에 못 들어온다(등급 아닌 문자열이 IN 목록에 섞이는 것을 막는다).
    표준표가 없으면 값 사전 순서를 그대로, 값 사전이 없으면 표준표 전체를 돌려준다."""
    ranked: list[tuple[int, str]] = []
    if GRADE_SCALE_CSV.exists():
        with open(GRADE_SCALE_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(line for line in f if not line.startswith("#")):
                tok, rank = (r.get("grade_db") or "").strip(), (r.get("rank") or "").strip()
                if tok and rank.isdigit():
                    ranked.append((int(rank), tok))
    std = [tok for _, tok in sorted(ranked)]
    doc = _load_yaml(ENUMS_DIR / f"{table}.yaml") if (ENUMS_DIR / f"{table}.yaml").exists() else {}
    cols = {str(k).lower(): v for k, v in (doc.get("columns") or {}).items()}
    observed = list((cols.get(column) or {}).get("value_semantics") or {})
    if not std:
        return tuple(observed)
    if not observed:
        return tuple(std)
    seen = {o.strip() for o in observed}
    return tuple(tok for tok in std if tok in seen)


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
    # 상품명(약어명·티커)은 별도 집합에도 담는다 — "TIGER 미국S&P500 이랑 VOO 중 뭐가 나아" 에서
    # 긴 국내 상품명이 점수를 부풀려 해외(VOO 직격 매치)가 70% 컷에 잘렸다(2026-09-01 로컬 점검).
    # 상품명이 직접 나온 테이블은 상대 점수와 무관하게 라우팅에서 탈락하면 안 된다.
    products: dict[str, set] = {t: set() for t in TABLES}
    for t in ("domestic_etfs", "overseas_etfs"):
        for (v,) in con.execute(f"select distinct trim(pd_abrv_nm) from {t} where pd_abrv_nm is not null"):
            add(t, v, 3)
            term = _VOCAB_STRIP.sub("", str(v or "")).strip()
            if term in vocab[t]:
                products[t].add(term)
    for t in TABLES:
        cols = {r[1].lower() for r in con.execute(f"pragma table_info({t})")}
        for term, canon in (((ctx.enums.get(t) or {}).get("synonyms") or {}).items()):
            # 3R B-1 — 값이 **컬럼명**인 동의어('순자산 → du_last_aum')는 측정축 낱말이지 그 테이블의 값이 아니다.
            #    T2 "순자산 합계가 가장 큰 자산운용사" 가 값 ['순자산'] 로 ETF 단독 라우팅된 직접 원인. 값 동의어(통안채→통화안정채권)만.
            if isinstance(canon, str) and canon.strip().lower() in cols:
                continue
            add(t, term, 2, min_len=2)          # '국채'·'만기' 같은 2자 통칭 — yaml 이 고른 것만
    # 다의어 상품명은 면제 자격 박탈 — 'AAA' 는 해외 ETF 티커이자 채권 신용등급이라
    # "은행채 중 AAA" 를 해외로 끌고 갔다(2026-09-01). 그 테이블에만 있는 상품명만 남긴다.
    for t in products:
        products[t] = {p for p in products[t]
                       if not any(p in vocab[u] for u in TABLES if u != t)}
    return vocab, products
