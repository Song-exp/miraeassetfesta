# -*- coding: utf-8 -*-
"""온톨로지 규칙북 HTML 생성기 — 피쳐(컬럼)별 구조/의미/규칙 정리.

ontology/enums/<도메인>.yaml 4개 + shared/*.yaml 을 읽어 두 파일을 만든다:
  - build/ontology_rules.html          로컬 열람용 (완전한 HTML 문서)
  - build/ontology_rules.artifact.html Artifact 배포용 (doctype/head/body 래퍼 없음)

구성 (2026-08-31 개편): 탭 = 공통 + 도메인 4.
도메인 탭은 ① 테이블 구조(row_grain) ② 피쳐 카드(컬럼별 구조/의미/규칙)
③ 도메인 규칙(query_rules 등 컬럼 하나에 안 묶이는 규칙) 순.
evidence·evidence_grade 같은 근거 필드는 렌더하지 않는다.

재생성: python scripts/gen_rules_html.py
"""

import html
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENUMS = ROOT / "ontology" / "enums"
SHARED = ROOT / "ontology" / "shared"
OUT = ROOT / "build" / "ontology_rules.html"
OUT_ARTIFACT = ROOT / "build" / "ontology_rules.artifact.html"

DOMAINS = [
    ("domestic_bonds", "채권", "국내 채권 — domestic_bonds"),
    ("domestic_etfs", "국내ETF", "국내 ETF·ETN — domestic_etfs"),
    ("overseas_etfs", "해외ETF", "해외 ETF — overseas_etfs"),
    ("public_funds", "펀드", "공모 펀드 — public_funds"),
]

# 컬럼 항목 필드 → 3분류. 여기 없는 키는 '구조' 로 흘려보낸다.
FEAT_STRUCT = ["unit", "missing_reason", "answerable_n", "answerable_n_by_column",
               "missing_semantics", "zero_is_value", "layer", "applies_to",
               "kg_entity", "구조", "결측의_축", "cross_use"]
FEAT_MEANING = ["note", "value_semantics", "value_semantics_요약"]
FEAT_RULE = ["answer_policy", "trap"]
DROP_KEYS = {"evidence", "evidence_grade", "unit_근거", "sql_영문실재", "ev", "근거"}

FIELD_KO = {
    "unit": "단위", "missing_reason": "결측", "answerable_n": "답변가능 행",
    "answerable_n_by_column": "컬럼별 답변가능", "missing_semantics": "위장결측·센티넬",
    "zero_is_value": "0도 값", "layer": "레이어", "applies_to": "적용 대상",
    "kg_entity": "KG 개체", "구조": "구조", "결측의_축": "결측의 축", "cross_use": "교차 사용",
    "note": "설명", "value_semantics": "값 의미", "value_semantics_요약": "값 의미 요약",
    "answer_policy": "답변 정책", "trap": "함정 ⚠️",
}
MISSING_KO = {
    "none": "결측 없음", "missing": "결측 있음(값 미상)", "not_applicable": "해당사항 없음(의도된 공란)",
    "mixed": "혼합(원인 분해 필요)", "present": "값 있음", "unresolved": "미분류",
}

# 도메인 규칙 섹션 — 컬럼 하나에 안 묶이는 규칙들 (yaml 등장 순서와 무관하게 이 순서로)
DOMAIN_RULE_KEYS = [
    ("row_grain", "테이블 구조 (행 단위)", "한 행이 무엇 하나인지 — COUNT(*) 가 종목 수가 아닌 이유"),
    ("product_group", "상품군", "테이블 안에 섞인 상품 구분"),
    ("name_encoding", "이름 인코딩", "종목명 문자열에 실린 구조·라벨 판정 규칙"),
    ("normalization", "정규화", "비교 전 TRIM·접미사·0/결측 처리"),
    ("constant_columns", "상수 컬럼", "전 행 동일값 — 정보량 0"),
    ("gate_constants", "게이트 상수", "게이트가 HCX 호출 없이 즉답/기각하는 근거"),
    ("schema_exclude", "스키마 제외", "플래너 스키마에서 뺀 컬럼 — 전건 결측·답변금지"),
    ("query_rules", "쿼리 가드레일", "SQL 생성이 지켜야 하는 조건식·금지 규칙"),
    ("domestic_asymmetry", "국내와의 비대칭", "국내ETF 에는 있는데 해외에는 없는 것"),
    ("derivation_rules", "파생 규칙", "없는 축을 다른 컬럼에서 유도"),
    ("axis_derivation", "축 유도", "confirmed = 확정 / pending_workshop = 미확정"),
    ("external_join", "외부 데이터 조인", "ext_* 테이블과의 조인 키·커버리지·기준일"),
    ("missing_profile", "결측 프로파일", "비어 있음의 뜻 분류"),
    ("answer_rules", "답변 규칙", "조회 결과를 어떻게 말할지"),
    ("clarify", "역질문 분기", "되묻기가 정답인 모호 질의"),
    ("synonyms", "동의어", "사용자 통칭 → DB 표기"),
    ("entities", "개체 연결", "이 도메인이 참조하는 KG 개체"),
    ("class_hierarchy", "클래스 계층", "온톨로지 클래스 구조"),
    ("axis_mapping", "축 매핑", "사용자 어휘 축 → 컬럼"),
    ("attributes", "속성 선언", "온톨로지 속성 정의"),
    ("cross_domain", "교차 도메인", "다른 도메인과 잇는 규칙"),
    ("external_facts", "외부 사실", "외부 수집으로 보강된 사실"),
]

INLINE_CODE = re.compile(r"`([^`]+)`")
INLINE_BOLD = re.compile(r"\*\*([^*]+)\*\*")

CUR_COLS = {}
CUR_COLRE = None


def set_domain_cols(colmap):
    global CUR_COLS, CUR_COLRE
    CUR_COLS = colmap
    if colmap:
        names = sorted(colmap, key=len, reverse=True)
        CUR_COLRE = re.compile(
            r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9_])"
        )
    else:
        CUR_COLRE = None


def _code_sub(m):
    inner = m.group(1)
    ko = CUR_COLS.get(inner)
    if ko:
        return f"<code>{inner}</code><span class='ko'>{html.escape(str(ko), quote=False)}</span>"
    return f"<code>{inner}</code>"


def md(text):
    """이스케이프 후 `code`·**bold** 만 살린다. 백틱 컬럼명엔 한글명 병기."""
    s = html.escape(str(text), quote=False)
    s = INLINE_CODE.sub(_code_sub, s)
    s = INLINE_BOLD.sub(r"<strong>\1</strong>", s)
    return s


def col_chips(raw):
    """문장에 백틱 없이 등장한 컬럼들의 한글명 칩."""
    if not CUR_COLRE:
        return ""
    raw = str(raw)
    seen, order = set(), []
    for c in CUR_COLRE.findall(raw):
        if c not in seen:
            seen.add(c)
            order.append(c)
    already = set(re.findall(r"`([A-Za-z0-9_]+)`", raw))
    order = [c for c in order if c not in already]
    if not order:
        return ""
    chips = " · ".join(
        f"<code>{c}</code><span class='ko'>{html.escape(str(CUR_COLS[c]), quote=False)}</span>"
        for c in order
    )
    return f"<div class='cols'>{chips}</div>"


def leaf(text):
    return md(text) + col_chips(text)


def render_value(v, depth=0):
    """yaml 값 재귀 렌더 — DROP_KEYS 는 뺀다."""
    if isinstance(v, dict):
        parts = ["<div class='sub'>"]
        for k, val in v.items():
            if k in DROP_KEYS or val is None:
                continue
            if isinstance(val, (dict, list)):
                parts.append(
                    f"<div class='kv nested'><div class='k'>{md(k)}</div>"
                    f"<div class='v'>{render_value(val, depth + 1)}</div></div>"
                )
            else:
                parts.append(
                    f"<div class='kv'><div class='k'>{md(k)}</div>"
                    f"<div class='v'>{leaf(val)}</div></div>"
                )
        parts.append("</div>")
        return "".join(parts)
    if isinstance(v, list):
        if all(not isinstance(x, (dict, list)) for x in v):
            items = "".join(f"<li>{leaf(x)}</li>" for x in v)
            return f"<ul>{items}</ul>"
        items = "".join(f"<li>{render_value(x, depth + 1)}</li>" for x in v)
        return f"<ul class='blocks'>{items}</ul>"
    return f"<p>{md(v)}</p>" + col_chips(v)


def count_rules(v):
    if isinstance(v, dict):
        return sum(count_rules(x) for x in v.items() if x[0] not in DROP_KEYS for x in [x[1]])
    if isinstance(v, list):
        return sum(count_rules(x) for x in v)
    return 1


def load_domain(name):
    with open(ENUMS / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def domain_colmap(data):
    m = {}
    for k, v in (data.get("column_korean_names") or {}).items():
        if v:
            m[k] = v
    for k, v in (data.get("columns") or {}).items():
        if isinstance(v, dict) and v.get("korean_name"):
            m[k] = v["korean_name"]
    return m


# ── 피쳐 카드 ────────────────────────────────────────────────────────

def _bucket_html(entry, keys):
    """컬럼 항목에서 keys 순서로 뽑아 라벨:값 목록으로."""
    rows = []
    for k in keys:
        if k not in entry or entry[k] is None:
            continue
        v = entry[k]
        label = FIELD_KO.get(k, k)
        if k == "missing_reason":
            v = f"{v} — {MISSING_KO.get(str(v), '')}".rstrip(" —")
        if isinstance(v, (dict, list)):
            rows.append(f"<div class='fitem'><b>{label}</b>{render_value(v)}</div>")
        else:
            rows.append(f"<div class='fitem'><b>{label}</b> {md(v)}</div>")
    return "".join(rows)


def render_feature(dom_id, col, entry, related_rules):
    if not isinstance(entry, dict):
        entry = {"note": entry}
    ko = entry.get("korean_name", "")

    # 헤더 배지: 단위 · 결측 분류
    badges = []
    if entry.get("unit"):
        badges.append(f"<span class='fb'>단위 {md(entry['unit'])}</span>")
    mr = entry.get("missing_reason")
    if mr:
        badges.append(f"<span class='fb mr-{html.escape(str(mr))}'>{MISSING_KO.get(str(mr), md(mr))}</span>")

    struct = _bucket_html(entry, [k for k in FEAT_STRUCT if k not in ("unit", "missing_reason")])
    # 분류 밖 미지의 키도 구조로
    known = set(FEAT_STRUCT) | set(FEAT_MEANING) | set(FEAT_RULE) | DROP_KEYS | {"korean_name"}
    struct += _bucket_html(entry, [k for k in entry if k not in known])
    meaning = _bucket_html(entry, FEAT_MEANING)
    rule = _bucket_html(entry, FEAT_RULE)
    if related_rules:
        chips = " ".join(
            f"<a class='rchip' href='#{dom_id}--query_rules'>{md(r)}</a>" for r in related_rules
        )
        rule += f"<div class='fitem'><b>관련 가드레일</b> {chips}</div>"

    rows = []
    for label, content in (("구조", struct), ("의미", meaning), ("규칙", rule)):
        if content:
            rows.append(f"<div class='frow'><div class='fl'>{label}</div><div class='fv'>{content}</div></div>")
    return (
        f"<article class='feat' id='{dom_id}--f-{col}'>"
        f"<h4><code>{md(col)}</code> <span class='fko'>{md(ko)}</span> {' '.join(badges)}</h4>"
        f"{''.join(rows)}</article>"
    )


def rules_by_column(data, colmap):
    """query_rules 각 항목이 언급하는 컬럼 → 규칙 이름 목록."""
    out = {}
    qr = data.get("query_rules") or {}
    if not colmap or not isinstance(qr, dict):
        return out
    names = sorted(colmap, key=len, reverse=True)
    colre = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9_])")
    for rname, rtext in qr.items():
        for c in set(colre.findall(str(rtext))):
            out.setdefault(c, []).append(rname)
    return out


# ── shared 탭 (개체·계층 — 기존 유지) ───────────────────────────────

def count_auto_nodes(path):
    n, in_nodes = 0, False
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("nodes:"):
                in_nodes = True
                continue
            if in_nodes:
                if line[:1] not in (" ", "\n", "#") and line.strip():
                    in_nodes = False
                elif re.match(r"^  \S[^:]*:", line):
                    n += 1
    return n


def render_tree(nodes):
    children, roots = {}, []
    for nid, nd in nodes.items():
        p = (nd or {}).get("parent")
        if p and p in nodes:
            children.setdefault(p, []).append(nid)
        else:
            roots.append(nid)

    def li(nid):
        nd = nodes[nid] or {}
        label = nd.get("label_ko") or nd.get("label_en") or nid
        extra = []
        if nd.get("rank") is not None:
            extra.append(f"rank {nd['rank']}")
        na = len(nd.get("aliases") or [])
        if na:
            extra.append(f"alias {na}")
        if nd.get("note"):
            extra.append(str(nd["note"]))
        ex = f" <span class='muted'>({md(' · '.join(extra))})</span>" if extra else ""
        kids = children.get(nid, [])
        sub = f"<ul>{''.join(li(k) for k in kids)}</ul>" if kids else ""
        return f"<li><code>{md(nid)}</code> {md(label)}{ex}{sub}</li>"

    return f"<ul class='tree'>{''.join(li(r) for r in roots)}</ul>"


def render_shared():
    manual = ["asset_class", "credit_grade", "currency", "index",
              "organization", "region", "risk_grade"]
    autos = [
        ("security_auto", "종목 (Security)"),
        ("index_auto", "지수 (Index)"),
        ("organization_issuer_auto", "발행사 (Organization)"),
        ("organization_manager_auto", "운용사 (Organization)"),
        ("fund_structure_auto", "펀드 구조 (FundStructure)"),
    ]
    out = []
    rows = "".join(
        f"<tr><td><code>shared/{n}.yaml</code></td><td>{d}</td>"
        f"<td class='num'>{count_auto_nodes(SHARED / (n + '.yaml')):,}</td></tr>"
        for n, d in autos
    )
    out.append(
        "<section class='rulesec' id='shared--auto'>"
        "<h3>자동 생성 개체 <span class='blurb'>gen_*_auto 스크립트 산출 — 노드 수만 표시</span></h3>"
        f"<div class='tblwrap'><table><tr><th>파일</th><th>개체</th><th>노드</th></tr>{rows}</table></div></section>"
    )
    for name in manual:
        with open(SHARED / f"{name}.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        nodes = data.get("nodes") or {}
        head = []
        for k in ("entity", "description", "property", "scale", "direction"):
            if data.get(k):
                head.append(
                    f"<div class='kv'><div class='k'>{k}</div><div class='v'>{md(data[k])}</div></div>"
                )
        n_parent = sum(1 for nd in nodes.values() if (nd or {}).get("parent"))
        out.append(
            f"<section class='rulesec' id='shared--{name}'>"
            f"<h3>{md(data.get('entity', name))} <span class='badge'>{len(nodes)}</span> "
            f"<span class='blurb'>계층 있는 노드 {n_parent}개 — <code>shared/{name}.yaml</code></span></h3>"
            f"<div class='sub'>{''.join(head)}</div>"
            f"<details><summary>노드 트리 펼치기</summary>{render_tree(nodes)}</details>"
            "</section>"
        )
    return "".join(out)


# ── 조립 ────────────────────────────────────────────────────────────

def main():
    tabs = []
    for name, label, subtitle in DOMAINS:
        data = load_domain(name)
        colmap = domain_colmap(data)
        set_domain_cols(colmap)
        related = rules_by_column(data, colmap)
        secs, body = [], []

        # ① 피쳐 카드
        cols = data.get("columns") or {}
        feats = "".join(
            render_feature(name, c, e, related.get(c, [])) for c, e in cols.items()
        )
        # column_korean_names 에만 있고 columns 엔 없는 컬럼(해외ETF)도 이름만이라도 싣는다
        only_named = [c for c in (data.get("column_korean_names") or {}) if c not in cols]
        if only_named:
            feats += "".join(
                render_feature(name, c, {"korean_name": (data["column_korean_names"][c])}, related.get(c, []))
                for c in only_named
            )
        n_feat = len(cols) + len(only_named)
        secs.append((f"{name}--features", f"피쳐 {n_feat}개", 0))
        body.append(
            f"<section class='featwrap' id='{name}--features'>"
            f"<h3 class='feathead'>피쳐별 구조 · 의미 · 규칙 <span class='badge'>{n_feat}</span></h3>{feats}</section>"
        )

        # ② 도메인 규칙 (컬럼 하나에 안 묶이는 것)
        for key, title, blurb in DOMAIN_RULE_KEYS:
            val = data.get(key)
            if val is None:
                continue
            secs.append((f"{name}--{key}", title, count_rules(val)))
            body.append(
                f"<section class='rulesec' id='{name}--{key}'>"
                f"<h3>{md(title)} <span class='badge'>{count_rules(val)}</span> "
                f"<span class='blurb'>{md(blurb)}</span></h3>{render_value(val)}</section>"
            )
        tabs.append((name, label, subtitle, "".join(body), secs))

    set_domain_cols({})
    shared_html = render_shared()
    shared_secs = [("shared--auto", "자동 생성 개체", 5)] + [
        (f"shared--{n}", n, 0)
        for n in ["asset_class", "credit_grade", "currency", "index", "organization", "region", "risk_grade"]
    ]
    tabs.insert(0, ("shared", "공통", "횡단 개체·계층 — ontology/shared/", shared_html, shared_secs))

    nav_btns, panels, toc_blocks = [], [], []
    for tab_id, label, subtitle, body, secs in tabs:
        nav_btns.append(
            f"<button class='tabbtn ch-{tab_id}' data-tab='{tab_id}'>{label}</button>"
        )
        toc = "".join(
            f"<a href='#{sid}' data-tab='{tab_id}'>{html.escape(t)}"
            + (f" <span class='badge sm'>{n}</span>" if n else "")
            + "</a>"
            for sid, t, n in secs
        )
        toc_blocks.append(f"<nav class='toc' data-tab='{tab_id}'>{toc}</nav>")
        panels.append(
            f"<div class='panel ch-{tab_id}' data-tab='{tab_id}'>"
            f"<h2>{label} <span class='subtitle'>{html.escape(subtitle)}</span></h2>{body}</div>"
        )

    inner = INNER.replace("{{NAV}}", "".join(nav_btns))
    inner = inner.replace("{{TOC}}", "".join(toc_blocks))
    inner = inner.replace("{{PANELS}}", "".join(panels))

    OUT.parent.mkdir(exist_ok=True)
    standalone = (
        "<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "</head>\n<body>\n" + inner + "\n</body>\n</html>\n"
    )
    OUT.write_text(standalone, encoding="utf-8")
    OUT_ARTIFACT.write_text(inner, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    print(f"wrote {OUT_ARTIFACT} ({OUT_ARTIFACT.stat().st_size:,} bytes)")


INNER = """<title>온톨로지 규칙북</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
:root {
  --bg:#f7f8fa; --card:#ffffff; --ink:#1d2433; --mut:#667085; --line:#e4e7ee;
  --chip:#eef1f6; --soft:#f1f3f7; --dash:#f1f3f7; --hit:#fff3bf; --hit-ink:#1d2433;
  --badge-sm-bg:#cbd5e1; --badge-sm-fg:#334155; --badge-fg:#ffffff;
  --ch-shared:#7c3aed; --ch-domestic_bonds:#2563eb; --ch-domestic_etfs:#059669;
  --ch-overseas_etfs:#0d9488; --ch-public_funds:#d97706;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:#14161d; --card:#1c1f28; --ink:#e5e8f0; --mut:#8b93a5; --line:#2b2f3b;
    --chip:#262a36; --soft:#232733; --dash:#262a36; --hit:#4d431a; --hit-ink:#f3ecd0;
    --badge-sm-bg:#3a4152; --badge-sm-fg:#c3cad9; --badge-fg:#12141a;
    --ch-shared:#a78bfa; --ch-domestic_bonds:#60a5fa; --ch-domestic_etfs:#34d399;
    --ch-overseas_etfs:#2dd4bf; --ch-public_funds:#fbbf24;
  }
}
:root[data-theme="dark"] {
  --bg:#14161d; --card:#1c1f28; --ink:#e5e8f0; --mut:#8b93a5; --line:#2b2f3b;
  --chip:#262a36; --soft:#232733; --dash:#262a36; --hit:#4d431a; --hit-ink:#f3ecd0;
  --badge-sm-bg:#3a4152; --badge-sm-fg:#c3cad9; --badge-fg:#12141a;
  --ch-shared:#a78bfa; --ch-domestic_bonds:#60a5fa; --ch-domestic_etfs:#34d399;
  --ch-overseas_etfs:#2dd4bf; --ch-public_funds:#fbbf24;
}
.ch-shared { --c:var(--ch-shared); }
.ch-domestic_bonds { --c:var(--ch-domestic_bonds); }
.ch-domestic_etfs { --c:var(--ch-domestic_etfs); }
.ch-overseas_etfs { --c:var(--ch-overseas_etfs); }
.ch-public_funds { --c:var(--ch-public_funds); }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:14px/1.65 "IBM Plex Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif; }
code { background:var(--chip); border:1px solid var(--line); border-radius:4px;
  padding:0 4px; font:12px/1.5 "IBM Plex Mono",Consolas,"D2Coding",monospace; word-break:break-all; }
header { position:sticky; top:0; z-index:10; background:var(--card); border-bottom:1px solid var(--line);
  display:flex; gap:10px; align-items:center; padding:10px 20px; flex-wrap:wrap; }
header h1 { font-size:16px; font-weight:700; margin:0 12px 0 0; letter-spacing:-0.01em; }
.tabbtn { border:1px solid var(--line); background:var(--card); border-radius:20px;
  padding:5px 14px; cursor:pointer; font:inherit; font-weight:600; color:var(--mut); }
.tabbtn:focus-visible, #q:focus-visible, .toc a:focus-visible { outline:2px solid var(--c,var(--ink)); outline-offset:2px; }
.tabbtn.on { background:var(--c); border-color:var(--c); color:var(--badge-fg); }
#q { margin-left:auto; border:1px solid var(--line); border-radius:8px; background:var(--card);
  color:var(--ink); padding:6px 10px; width:260px; font:inherit; }
.layout { display:flex; gap:0; align-items:flex-start; }
.side { position:sticky; top:56px; width:230px; flex:none; padding:16px 8px 16px 16px;
  max-height:calc(100vh - 56px); overflow:auto; }
.toc { display:none; flex-direction:column; gap:2px; }
.toc.on { display:flex; }
.toc a { color:var(--mut); text-decoration:none; padding:4px 8px; border-radius:6px; font-size:13px; }
.toc a:hover { background:var(--soft); color:var(--ink); }
main { flex:1; min-width:0; padding:16px 24px 60px 12px; }
@media (max-width: 760px) { .side { display:none; } main { padding-left:20px; } }
.panel { display:none; }
.panel.on { display:block; }
.panel h2 { border-left:5px solid var(--c); padding-left:10px; margin:8px 0 16px; text-wrap:balance; }
.subtitle { font-size:13px; color:var(--mut); font-weight:400; }
.rulesec, .featwrap { background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:14px 18px; margin-bottom:14px; overflow-x:auto; }
.rulesec h3, .feathead { margin:0 0 10px; font-size:15px; }
.blurb { font-size:12px; color:var(--mut); font-weight:400; }
.badge { background:var(--c,var(--mut)); color:var(--badge-fg); border-radius:10px;
  font-size:11px; padding:1px 7px; vertical-align:2px; }
.badge.sm { background:var(--badge-sm-bg); color:var(--badge-sm-fg); padding:0 5px; }
.feat { border-top:1px solid var(--line); padding:10px 0; }
.feat h4 { margin:0 0 6px; font-size:13.5px; }
.feat h4 code { font-size:13px; font-weight:600; }
.fko { font-weight:700; }
.fb { font-size:11px; color:var(--mut); border:1px solid var(--line); border-radius:10px;
  padding:0 7px; margin-left:4px; white-space:nowrap; }
.fb.mr-none { color:var(--ch-domestic_etfs); border-color:var(--ch-domestic_etfs); }
.frow { display:flex; gap:10px; padding:3px 0; }
.fl { flex:none; width:36px; font-size:12px; font-weight:700; color:var(--c,var(--ink)); }
.fv { min-width:0; flex:1; }
.fitem { margin-bottom:3px; }
.fitem > b { font-weight:600; color:var(--mut); font-size:12px; margin-right:4px; }
.rchip { display:inline-block; font-size:12px; color:var(--c,var(--ink)); text-decoration:none;
  border:1px solid var(--line); border-radius:10px; padding:0 8px; margin:1px 2px 1px 0; }
.rchip:hover { background:var(--soft); }
.kv { display:flex; gap:10px; padding:7px 0; border-top:1px solid var(--dash); }
.kv:first-child { border-top:0; }
.k { flex:none; width:150px; font-weight:700; color:var(--c,var(--ink)); word-break:keep-all; }
.kv.nested .k { color:var(--ink); }
.v { min-width:0; flex:1; }
.v p { margin:0 0 4px; }
.sub .sub .kv { border-top:1px dashed var(--dash); }
ul { margin:4px 0; padding-left:20px; }
ul.blocks > li { margin-bottom:8px; }
.tblwrap { overflow-x:auto; }
table { border-collapse:collapse; width:100%; }
th, td { border:1px solid var(--line); padding:5px 10px; text-align:left; }
th { background:var(--soft); }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.muted { color:var(--mut); font-size:12px; }
.ko { color:var(--mut); font-size:11.5px; margin-left:3px; white-space:nowrap; }
.ko::before { content:"("; } .ko::after { content:")"; }
.cols { margin-top:5px; padding-top:4px; border-top:1px dashed var(--dash);
  font-size:12px; color:var(--mut); line-height:2; }
.tree, .tree ul { list-style:none; padding-left:18px; }
.tree > li { margin:2px 0; }
details summary { cursor:pointer; color:var(--mut); margin:6px 0; }
.hit { background:var(--hit); color:var(--hit-ink); }
.hidden { display:none !important; }
#count { font-size:12px; color:var(--mut); }
</style>
<header>
  <h1>온톨로지 규칙북</h1>
  {{NAV}}
  <input id="q" type="search" placeholder="피쳐·규칙 검색 (한글명 가능)…">
  <span id="count"></span>
</header>
<div class="layout">
  <aside class="side">{{TOC}}</aside>
  <main>{{PANELS}}</main>
</div>
<script>
const btns = [...document.querySelectorAll('.tabbtn')];
const panels = [...document.querySelectorAll('.panel')];
const tocs = [...document.querySelectorAll('.toc')];
function show(id) {
  btns.forEach(b => b.classList.toggle('on', b.dataset.tab === id));
  panels.forEach(p => p.classList.toggle('on', p.dataset.tab === id));
  tocs.forEach(t => t.classList.toggle('on', t.dataset.tab === id));
  try { localStorage.setItem('rules-tab', id); } catch (e) {}
}
btns.forEach(b => b.onclick = () => show(b.dataset.tab));
let init = 'shared';
try { init = localStorage.getItem('rules-tab') || init; } catch (e) {}
if (!btns.some(b => b.dataset.tab === init)) init = 'shared';
show(init);
document.querySelectorAll('.toc a').forEach(a => a.onclick = () => show(a.dataset.tab));

const q = document.getElementById('q');
const count = document.getElementById('count');
const units = [...document.querySelectorAll('.feat, .kv, ul.blocks > li, .rulesec > ul > li')];
q.addEventListener('input', () => {
  const t = q.value.trim().toLowerCase();
  document.querySelectorAll('.hit').forEach(e => e.classList.remove('hit'));
  if (!t) {
    units.forEach(u => u.classList.remove('hidden'));
    document.querySelectorAll('.rulesec, .featwrap').forEach(s => s.classList.remove('hidden'));
    count.textContent = '';
    btns.forEach(b => b.style.opacity = 1);
    return;
  }
  let n = 0;
  units.forEach(u => {
    const hit = u.textContent.toLowerCase().includes(t);
    u.classList.toggle('hidden', !hit);
    if (hit) { n++; if (!u.classList.contains('feat')) u.classList.add('hit'); }
  });
  document.querySelectorAll('.rulesec, .featwrap').forEach(s => {
    s.classList.toggle('hidden', !s.textContent.toLowerCase().includes(t));
    const d = s.querySelector('details'); if (d && t) d.open = true;
  });
  const tabHits = {};
  panels.forEach(p => { tabHits[p.dataset.tab] = p.textContent.toLowerCase().includes(t); });
  btns.forEach(b => b.style.opacity = tabHits[b.dataset.tab] ? 1 : 0.35);
  count.textContent = n + '건 일치';
});
</script>
"""

if __name__ == "__main__":
    sys.exit(main())
