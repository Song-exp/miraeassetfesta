# -*- coding: utf-8 -*-
"""도메인별 데이터 사전 생성 — 마스터 + 외부(`ext_*`) 전 컬럼의 의미·결측 판정·근거.

손으로 쓰지 않는 이유: 컬럼이 330개고, 배포본이 바뀌면 수치가 통째로 낡는다.
권위 있는 출처 넷을 결합해 매번 새로 만든다.

  1. `schema_metadata`            주최가 준 컬럼 한글명·타입·Nullable (원본 schema.xlsx)
  2. 라이브 DB                     결측·0값·distinct·범위·값 분포 — **실측** (auto.yaml 은 1차 잔재라 쓰지 않는다)
  3. `ontology/enums/<dom>.yaml`  사람의 판정 — 결측 사유·값 의미·단위·답변 정책·함정·근거
  4. `EXT_DICT` (이 파일 하단)     외부 테이블 컬럼 의미 — 주최 스키마가 없으므로 적재 스크립트에서 확정

출력: docs/data_dictionary/{bonds,etf,funds}.md

사용:
    python scripts/gen_data_dictionary.py            # 3개 전부
    python scripts/gen_data_dictionary.py funds      # 하나만

⚠️ DB 를 읽기 전용(mode=ro)으로 연다. 원본은 절대 건드리지 않는다.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "financial_products.db"
OUT = ROOT / "docs" / "data_dictionary"

# ── 문서 구성: 파일 → (제목, 마스터 테이블들, 외부 테이블들) ────────────────
DOCS = {
    "bonds": ("국내채권", ["domestic_bonds"], []),
    "etf": ("ETF (국내·해외)", ["domestic_etfs", "overseas_etfs"],
            ["ext_etf_holdings", "ext_ovs_etf_holdings"]),
    "funds": ("공모펀드", ["public_funds"],
              ["ext_fund_holdings", "ext_fund_page"]),
}

MISSING_REASON_KO = {
    "not_applicable": "**해당 없음** — 그 상품엔 개념 자체가 없다. 답변은 “해당 사항이 없습니다”, ❌ “모릅니다” 아님",
    "missing": "**미수록** — 있어야 하는데 안 왔다. 답변은 “데이터가 제공되지 않았습니다”",
    "present": "**결측 없음** — 그대로 답변 가능",
    "mixed": "**행마다 이유가 다름** — 아래 `값별 의미` 로 분해해서 판단",
    "none": "**결측 없음**",
}

# 값별 의미 안에서 짧게 쓸 때
REASON_SHORT = {
    "not_applicable": "해당 없음(개념 자체가 없음)",
    "missing": "미수록(있어야 하는데 안 옴)",
    "present": "정상값",
    "none": "정상값",
    "mixed": "행마다 다름 — 단일 해석 금지",
}


def semantic(v) -> str:
    """missing_semantics/value_semantics 의 값을 사람 말로."""
    return REASON_SHORT.get(str(v), clean(v))


def check_consistency(col: str, judged: dict, st: dict) -> list[str]:
    """yaml 판정과 라이브 실측이 어긋나는 곳을 잡는다.

    사전이 곧 검사기가 되게 하려는 것 — 판정은 사람이 쓰고 수치는 배포본마다 바뀌므로
    둘은 조용히 어긋난다. 어긋난 채로 플래너에 들어가면 답변 모수가 틀린다.
    """
    out = []
    mr = str(judged.get("missing_reason"))
    if mr in ("none", "present") and st["missing"] > 0:
        out.append(f"판정은 `{mr}`(결측 없음)인데 **실측 결측 {st['missing']:,}행** — 판정을 고치거나 사유를 적어야 한다")
    an = judged.get("answerable_n")
    if isinstance(an, int):
        live = st["total"] - st["missing"]
        if abs(live - an) > max(5, an * 0.01):
            out.append(f"`answerable_n` 기재 **{an:,}** vs 실측 non-null **{live:,}** — "
                       f"판정 모수(도메인 조건 포함)라면 그 조건을 적고, 단순 non-null 이면 값을 갱신할 것")
    return out


# ── 실측 ────────────────────────────────────────────────────────────────
def col_stats(con: sqlite3.Connection, table: str, col: str, numeric: bool) -> dict:
    q = f'''select count(*),
                   sum(case when "{col}" is null then 1 else 0 end),
                   sum(case when "{col}" is not null and trim(cast("{col}" as text))='' then 1 else 0 end),
                   count(distinct "{col}")
            from "{table}"'''
    total, nulls, blanks, distinct = con.execute(q).fetchone()
    s = {"total": total, "null": nulls or 0, "blank": blanks or 0, "distinct": distinct}
    s["missing"] = s["null"] + s["blank"]

    if numeric:
        r = con.execute(
            f'''select sum(case when "{col}"=0 then 1 else 0 end), min("{col}"), max("{col}")
                from "{table}" where "{col}" is not null'''
        ).fetchone()
        s["zero"], s["min"], s["max"] = (r[0] or 0), r[1], r[2]
    else:
        s["zero"] = con.execute(
            f'''select count(*) from "{table}" where trim(cast("{col}" as text))='0' '''
        ).fetchone()[0]
        s["min"] = s["max"] = None

    # 값 분포 — distinct 가 적을 때만 (많으면 상위 5개)
    s["top"] = con.execute(
        f'''select cast("{col}" as text), count(*) from "{table}"
            where "{col}" is not null and trim(cast("{col}" as text))<>''
            group by 1 order by 2 desc limit 5'''
    ).fetchall()
    return s


def pct(n: int, total: int) -> str:
    return f"{n:,} ({n / total * 100:.1f}%)" if total else f"{n:,}"


def fmt_num(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.4g}"
    return f"{v:,}"


def clean(v) -> str:
    """마크다운 표 안에서 깨지지 않게."""
    s = str(v).replace("|", "\\|").replace("\n", " ").strip()
    return s


# ── 컬럼 한 개 렌더 ──────────────────────────────────────────────────────
def render_column(col: str, meta: dict, judged: dict | None, st: dict) -> list[str]:
    L = []
    kname = (judged or {}).get("korean_name") or meta.get("korean_name") or ""
    flag = "" if judged else "  🔲 **미판정**"
    L.append(f"#### `{col}`{' · ' + clean(kname) if kname else ''}{flag}")
    L.append("")

    # 실측 한 줄
    bits = [f"`{meta.get('data_type', '?')}`", f"Nullable {meta.get('nullable', '?')}"]
    m = st["missing"]
    bits.append(("**결측 " if m else "결측 ") + pct(m, st["total"]) + ("**" if m else ""))
    if st["zero"]:
        bits.append("0값 " + pct(st["zero"], st["total"]))
    bits.append(f"distinct {st['distinct']:,}")
    if st["min"] is not None:
        bits.append(f"범위 {fmt_num(st['min'])} ~ {fmt_num(st['max'])}")
    L.append(" · ".join(bits))
    L.append("")

    # 값 분포
    if st["top"] and st["distinct"] <= 30:
        vals = " · ".join(f"`{clean(v)[:28]}` {c:,}" for v, c in st["top"])
        L.append(f"값: {vals}" + (" …" if st["distinct"] > 5 else ""))
        L.append("")
    elif st["top"]:
        vals = " · ".join(f"`{clean(v)[:24]}`" for v, _ in st["top"][:3])
        L.append(f"값 예시: {vals}")
        L.append("")

    if not judged:
        L.append("> 🔲 `ontology/enums/` 에 판정이 없다. 주최 한글명과 실측만 있는 상태 — **결측 사유·답변 정책 미정**.")
        L.append("")
        return L

    # 판정 표
    rows = []
    mr = judged.get("missing_reason")
    if mr:
        rows.append(("결측 사유", f"`{mr}` — {MISSING_REASON_KO.get(str(mr), '')}"))
    ms = judged.get("missing_semantics")
    if ms:
        if isinstance(ms, dict):
            rows.append(("값별 의미", " · ".join(f"값 `{k}` → {semantic(v)}" for k, v in ms.items())))
        else:
            rows.append(("값별 의미", semantic(ms)))
    vs = judged.get("value_semantics")
    if vs:
        if isinstance(vs, dict):
            rows.append(("값 의미", " · ".join(f"`{k}` = {clean(v)}" for k, v in vs.items())))
        else:
            rows.append(("값 의미", clean(vs)))
    if judged.get("unit"):
        rows.append(("단위", f"**{clean(judged['unit'])}**"))
    if judged.get("zero_is_value"):
        rows.append(("0 처리", "**예외 — 0 이 실제값**이라 정렬·필터에서 배제하지 않는다"))
    if judged.get("answerable_n") is not None:
        rows.append(("답변 가능 모수", f"{judged['answerable_n']:,}행"))
    if judged.get("evidence_grade"):
        rows.append(("근거 등급", f"`{judged['evidence_grade']}`"))
    if judged.get("kg_entity"):
        rows.append(("KG 개체", f"`{judged['kg_entity']}` — `kg_alias` 로 노드 연결"))
    if judged.get("layer"):
        rows.append(("계층", clean(judged["layer"])))
    if judged.get("_inherited_from"):
        rows.append(("판정 출처", f"`{judged['_inherited_from']}` 의 `applies_to` 로 **공통 판정을 물려받음** "
                                  f"— 같은 성격의 컬럼 묶음이다. 실측 수치는 이 컬럼의 것"))

    if rows:
        L.append("| 판정 | 내용 |")
        L.append("| :-- | :-- |")
        for k, v in rows:
            L.append(f"| {k} | {v} |")
        L.append("")

    for key, label in (("answer_policy", "**답변 정책**"),
                       ("trap", "🔴 **함정**"),
                       ("note", "**근거·메모**")):
        if judged.get(key):
            L.append(f"{label} — {clean(judged[key])}")
            L.append("")

    for w in check_consistency(col, judged, st):
        L.append(f"> ⚠️ **판정 ↔ 실측 불일치** — {w}")
        L.append("")
    return L


# ── 테이블 하나 렌더 ─────────────────────────────────────────────────────
def render_master(con, table: str, dom_yaml: dict, meta_by_col: dict) -> list[str]:
    cols = [r[1] for r in con.execute(f"pragma table_info({table})")]
    judged_all = dict(dom_yaml.get("columns") or {})
    n = con.execute(f"select count(*) from {table}").fetchone()[0]

    # `applies_to` — 한 항목이 여러 컬럼을 한꺼번에 판정하는 형태. 대상 컬럼에 그 판정을 물려준다.
    # (물려받은 것은 실측이 다르므로 answerable_n 은 떼고, 출처를 밝힌다)
    for src, v in list(judged_all.items()):
        if not isinstance(v, dict):
            continue
        for tgt in (v.get("applies_to") or []):
            if tgt != src and tgt in cols and tgt not in judged_all:
                inherited = {k: val for k, val in v.items()
                             if k not in ("applies_to", "answerable_n", "korean_name")}
                inherited["_inherited_from"] = src
                judged_all[tgt] = inherited

    L = [f"## 📋 `{table}` — 마스터 (L0)", ""]
    L.append(f"**{n:,}행 × {len(cols)}컬럼** · 주최 원본 그대로 · 기준일 2026-08-22")
    L.append("")
    if dom_yaml.get("row_grain"):
        L.append(f"**행 단위**: {clean(dom_yaml['row_grain'])}")
        L.append("")

    qr = dom_yaml.get("query_rules")
    if qr:
        L += ["### 이 도메인 질의 규칙 (`query_rules`)", "",
              "> 질의를 만들 때 **반드시** 걸어야 하는 조건들이다. 플래너 프롬프트로도 전달된다.", "",
              "| 규칙 | 내용 |", "| :-- | :-- |"]
        for k, v in qr.items():
            L.append(f"| `{k}` | {clean(v)[:400]} |")
        L.append("")

    # 컬럼별 실측을 한 번에 — 요약과 본문이 같은 수치를 쓰게
    stats, warns = {}, []
    for c in cols:
        meta = meta_by_col.get(c, {})
        numeric = any(k in str(meta.get("data_type", "")).lower()
                      for k in ("int", "double", "numeric", "real", "decimal", "float"))
        stats[c] = col_stats(con, table, c, numeric)
        if c in judged_all:
            for w in check_consistency(c, judged_all[c], stats[c]):
                warns.append((c, w))

    # 결측 상위 — 어디가 비어 있는지 한눈에
    ranked = sorted(((c, stats[c]["missing"]) for c in cols), key=lambda x: -x[1])
    top_missing = [(c, m) for c, m in ranked if m > 0][:15]
    if top_missing:
        L += ["### 결측이 많은 컬럼 (상위 15)", "",
              "| 컬럼 | 한글명 | 결측 | 판정 |", "| :-- | :-- | --: | :-- |"]
        for c, m in top_missing:
            j = judged_all.get(c) or {}
            ko = j.get("korean_name") or meta_by_col.get(c, {}).get("korean_name") or ""
            mr = f"`{j.get('missing_reason')}`" if j.get("missing_reason") else "🔲 미판정"
            L.append(f"| `{c}` | {clean(ko)} | {pct(m, n)} | {mr} |")
        L.append("")

    if warns:
        L += [f"### ⚠️ 판정 ↔ 실측 불일치 {len(warns)}건", "",
              "yaml 판정은 사람이 쓰고 수치는 배포본마다 바뀌므로 둘은 조용히 어긋난다. "
              "어긋난 채로 플래너에 들어가면 **답변 모수가 틀린다.** 아래는 고쳐야 할 목록이다.", "",
              "| 컬럼 | 내용 |", "| :-- | :-- |"]
        for c, w in warns:
            L.append(f"| `{c}` | {w} |")
        L.append("")

    judged_n = sum(1 for c in cols if c in judged_all)
    L += ["### 컬럼 사전", "",
          f"판정 완료 **{judged_n}/{len(cols)}** 컬럼. 🔲 표시는 주최 한글명만 있고 우리 판정이 없는 것.", ""]

    for c in cols:
        L += render_column(c, meta_by_col.get(c, {}), judged_all.get(c), stats[c])

    missing = [c for c in cols if c not in judged_all]
    if missing:
        L += ["", f"### 🔲 미판정 컬럼 {len(missing)}개", "",
              "결측 사유·답변 정책이 없어 **질의에 쓰면 안 되는** 상태다. 채우는 것이 이 도메인의 남은 작업.", "",
              "```", ", ".join(missing), "```", ""]
    return L


def render_ext(con, table: str) -> list[str]:
    info = EXT_DICT[table]
    cols = [r[1] for r in con.execute(f"pragma table_info({table})")]
    n = con.execute(f"select count(*) from {table}").fetchone()[0]

    L = [f"## 🌐 `{table}` — 외부 보강 (L2)", ""]
    L += [f"**{n:,}행 × {len(cols)}컬럼**", "",
          "| 항목 | 내용 |", "| :-- | :-- |",
          f"| 원천 | {info['source']} |",
          f"| 조인 키 | {info['join']} |",
          f"| 기준일 | {info['as_of']} |",
          f"| 적재 | `{info['loader']}` |", ""]
    L.append(f"> {info['caveat']}")
    L.append("")
    L += ["### 컬럼 사전", "",
          "> 🔴 주최 `schema_metadata` 에 없는 테이블이라 **한글명·타입 정의가 없다.** "
          "아래 의미는 적재 스크립트와 수집 원천에서 확정한 것이다.", ""]

    for c in cols:
        d = info["cols"].get(c)
        st = col_stats(con, table, c, d and d.get("numeric", False))
        L.append(f"#### `{c}`{' · ' + d['ko'] if d else '  🔲 **의미 미확정**'}")
        L.append("")
        bits = []
        m = st["missing"]
        bits.append(("**결측 " if m else "결측 ") + pct(m, st["total"]) + ("**" if m else ""))
        if st["zero"]:
            bits.append("0값 " + pct(st["zero"], st["total"]))
        bits.append(f"distinct {st['distinct']:,}")
        if st["min"] is not None:
            bits.append(f"범위 {fmt_num(st['min'])} ~ {fmt_num(st['max'])}")
        L.append(" · ".join(bits))
        L.append("")
        if st["top"]:
            if st["distinct"] <= 30:
                L.append("값: " + " · ".join(f"`{clean(v)[:28]}` {c2:,}" for v, c2 in st["top"]))
            else:
                L.append("값 예시: " + " · ".join(f"`{clean(v)[:24]}`" for v, _ in st["top"][:3]))
            L.append("")
        if d:
            L.append(d["desc"])
            L.append("")
            if d.get("trap"):
                L.append(f"🔴 **함정** — {d['trap']}")
                L.append("")
        else:
            L.append("> 🔲 의미 미확정 — 적재 스크립트에도 설명이 없다.")
            L.append("")
    return L


# ── 외부 테이블 사전 (주최 스키마 없음 → 적재 스크립트·수집 원천에서 확정) ──
EXT_DICT = {
    "ext_etf_holdings": {
        "source": "FunETF 경유 KRX/코스콤 — 국내 ETF 구성종목",
        "join": "`etf_code` = `domestic_etfs.pd_itm_no`",
        "as_of": "**2026-08-21 스냅샷** (마스터 8/22 와 다름 — 답변에 병기 필수)",
        "loader": "scripts/load_external_holdings.py",
        "caveat": "커버리지 ETF 1,160/1,235 (93.9%). **ETN 545건은 전건 미제공** — 구조상 구성종목이 없는 것이라 "
                  "‘데이터 없음’ 이 아니라 ‘해당 없음’ 으로 답한다 (`fetch_log_20260821.csv` 가 근거).",
        "cols": {
            "etf_code": {"ko": "ETF 종목코드", "desc": "마스터 `domestic_etfs.pd_itm_no` 와 같은 6자리 코드. **조인 키**.",
                         "trap": "선행 0 이 있는 문자열이다. 숫자로 비교하지 말 것."},
            "etf_name": {"ko": "ETF 명칭 (수집 시점)", "desc": "수집원이 표기한 이름. 마스터의 `pd_abrv_nm` 과 다를 수 있다 — **표시는 마스터 이름을 쓴다.**"},
            "rank": {"ko": "편입 순위", "numeric": True,
                     "desc": "비중 내림차순 순위. 수집원이 **상위 종목만** 제공하므로 하위 종목은 아예 행이 없다.",
                     "trap": "`rank` 최댓값이 그 ETF 의 실제 보유 종목 수가 아니다. ‘몇 종목 보유’ 질의에 쓰지 말 것."},
            "ticker": {"ko": "구성종목 티커", "desc": "국내 종목코드 6자리. `kg_alias` 의 Security 노드와 잇는 키."},
            "constituent": {"ko": "구성종목명", "desc": "한글 종목명. 교차질의(‘삼성전자를 보유한 ETF’)의 매칭 대상.",
                            "trap": "이름 `LIKE` 로 풀면 오탐이 난다. `kg_alias` 로 종목 노드를 찾아 `ticker` 로 조인할 것."},
            "weight_pct": {"ko": "편입 비중 (%)", "numeric": True, "desc": "해당 ETF 내 비중. 단위 **%**."},
            "quantity": {"ko": "보유 수량 (주)", "numeric": True, "desc": "CU 당 보유 주식 수. 금액이 아니다."},
            "as_of": {"ko": "구성종목 기준일", "desc": "**2026-08-21**. 마스터(8/22)와 다르므로 답변에 반드시 병기한다."},
        },
    },
    "ext_ovs_etf_holdings": {
        "source": "SEC EDGAR **NPORT-P** 공시 — 해외 ETF 구성종목",
        "join": "`isin` = `overseas_etfs.pd_isin_cd` (티커→ISIN 매핑 90.9%)",
        "as_of": "**ETF 별 `report_date` 3/31~6/30** — 상품마다 다르다",
        "loader": "scripts/load_external_holdings.py",
        "caveat": "1,356 ETF · 종목수 커버리지 22.7% 이지만 **AUM 가중 88.6%**. 커버리지를 말할 땐 반드시 AUM 가중으로. "
                  "보고기준일이 상품마다 달라 **ETF 간 비중 비교 시 시점이 어긋난다** — 답변에 `report_date` 병기.",
        "cols": {
            "etf_ticker": {"ko": "ETF 티커", "desc": "미국 상장 티커. 수집 단위 키."},
            "seriesId": {"ko": "SEC 시리즈 ID", "desc": "EDGAR 가 부여한 펀드 시리즈 식별자(`S000…`). 티커↔ISIN 매핑의 중간 키."},
            "report_date": {"ko": "보고 기준일", "desc": "NPORT-P 보고 시점. 분포 4/30 443 · 5/31 389 · 3/31 352 · 6/30 94.",
                            "trap": "6/30 분이 적은 건 제출기한(8/29)이 아직 안 지나서다 — **결측이 아니라 정상**."},
            "rank": {"ko": "편입 순위", "numeric": True, "desc": "비중 내림차순."},
            "holding_name": {"ko": "구성종목명 (영문)", "desc": "공시 원문 표기.",
                             "trap": "`LIKE '%Samsung Elec%'` 가 **삼성전기**(SAMSUNG ELECTRO-MECHANICS)까지 잡는다. "
                                     "GDR·우선주 표기도 섞인다 — `kg_alias`/`cusip`/`lei` 로 풀 것."},
            "cusip": {"ko": "CUSIP", "desc": "북미 증권 식별번호 9자리. 종목 동일성 판정의 1순위 키."},
            "lei": {"ko": "LEI", "desc": "발행 법인 식별자 20자리. 같은 법인의 여러 종목을 묶을 때 쓴다."},
            "pct_val": {"ko": "편입 비중 (%)", "numeric": True,
                        "desc": "순자산 대비 비중. 국내의 `weight_pct` 와 **같은 단위(%)** 지만 컬럼명이 다르다."},
            "balance": {"ko": "보유 수량", "numeric": True,
                        "desc": "보유 주식/계약 수. 국내 `quantity` 에 대응.",
                        "trap": "자산 유형에 따라 단위가 주식 수일 수도 액면가일 수도 있다 — **절대량 비교 금지**."},
            "accession": {"ko": "EDGAR 접수번호", "desc": "원문 공시 문서 식별자. 출처 추적·재현용."},
            "isin": {"ko": "ETF 의 ISIN", "desc": "마스터 조인 키. **구성종목이 아니라 ETF 자신의 ISIN** 이다.",
                     "trap": "티커→ISIN 매핑이 90.9% 라 **9.1% 는 NULL** — 마스터와 조인되지 않는다."},
        },
    },
    "ext_fund_holdings": {
        "source": "미래에셋증권 웹 — 공모펀드 구성종목",
        "join": "`grp` = `public_funds.mtco_itm_no` (펀드묶음 단위)",
        "as_of": "**행별 `bas_dt`** — 전 행 ≤ 7/11 검증 완료",
        "loader": "scripts/load_external_web.py",
        "caveat": "클래스(`itm_no`)가 아니라 **펀드묶음(`grp`)** 단위다. 같은 펀드의 A/C 클래스는 포트폴리오가 같으므로 "
                  "클래스별로 세면 중복된다.",
        "cols": {
            "grp": {"ko": "펀드묶음 코드", "desc": "`public_funds.mtco_itm_no` 와 잇는 **조인 키**. 클래스를 묶는 단위.",
                    "trap": "선행 0 손실로 길이가 1~7 로 섞인다. 7자리 zero-pad 후 비교할 것."},
            "itm_no": {"ko": "대표 클래스 코드", "desc": "묶음을 대표하는 클래스. 수집 시 진입점이었을 뿐 의미는 `grp` 에 있다."},
            "bas_dt": {"ko": "구성종목 기준일", "desc": "행마다 다르다. 답변에 병기."},
            "isin": {"ko": "구성종목 ISIN", "desc": "종목 식별자. 이름보다 이것으로 조인하는 편이 안전하다."},
            "holding_nm": {"ko": "구성종목명", "desc": "한글/영문 혼재.",
                           "trap": "‘KODEX 삼성전자단일종목레버리지’, ‘2026-06 삼성전자개별선물’ 처럼 **ETF·선물이 종목명으로 섞인다.** "
                                   "`asset_type` 으로 먼저 걸러야 한다."},
            "weight_pct": {"ko": "편입 비중 (%)", "numeric": True, "desc": "펀드 내 비중."},
            "asset_type": {"ko": "자산 유형", "desc": "주식·채권·수익증권·파생 등. **종목명 오탐을 거르는 1차 필터**."},
            "market": {"ko": "시장 구분", "desc": "상장 시장."},
            "as_of_ok": {"ko": "기준일 유효 플래그", "desc": "수집 시점 유출 가드 통과 여부. 적재된 행은 전부 통과분이다.",
                         "trap": "품질 플래그가 아니라 **날짜 규정 준수 플래그**다. 값 해석에 쓰지 말 것."},
            "retrieved_at": {"ko": "수집 일시", "desc": "크롤 시각. 출처 기재용."},
            "source": {"ko": "출처", "desc": "수집 원천 표기. 답변의 근거 문구에 쓴다."},
        },
    },
    "ext_fund_page": {
        "source": "미래에셋증권 웹 펀드 상세 페이지 + 간이투자설명서",
        "join": "`itm_no` = `public_funds.itm_no` (클래스 단위, unique)",
        "as_of": "**2026-08-18 관측**",
        "loader": "scripts/load_external_web.py",
        "caveat": "🔴 **시계열 값(순자산·수익률)은 일부러 적재하지 않았다** — 8/18 관측치라 답변 근거로 쓰면 기준일이 어긋난다. "
                  "여기 있는 건 설정일·보수·환매 규칙처럼 **불변 또는 준정적인 사실**뿐이다. "
                  "이 테이블이 마스터 펀드 보수의 **단위 ‰ 를 확정한 근거**다(마스터 = 이 값 × 10).",
        "cols": {
            "itm_no": {"ko": "클래스 코드", "desc": "마스터 조인 키. unique 인덱스."},
            "estb_dt": {"ko": "설정일 (YYYYMMDD)", "desc": "펀드 설정일. **불변 사실** — 마스터에 없어 이 테이블이 유일 출처."},
            "mgmt_co_nm": {"ko": "운용사 법인명", "desc": "웹 관측 법인명. 코드북 `asset_manager.csv` 의 근거."},
            "total_fee_pct": {"ko": "총보수 (%)", "numeric": True,
                              "desc": "설명서 기재 총보수. **단위 %**.",
                              "trap": "마스터의 보수 컬럼은 **‰** 라 이 값의 10배다. 섞어 쓰면 자릿수가 틀린다."},
            "sale_fee_pct": {"ko": "판매보수 (%)", "numeric": True, "desc": "총보수의 구성 항목."},
            "mgmt_fee_pct": {"ko": "운용보수 (%)", "numeric": True, "desc": "총보수의 구성 항목."},
            "trust_fee_pct": {"ko": "수탁보수 (%)", "numeric": True, "desc": "총보수의 구성 항목."},
            "admin_fee_pct": {"ko": "사무관리보수 (%)", "numeric": True,
                              "desc": "총보수의 구성 항목. 마스터 `ofwk_trus_rwrd_r` 대응.",
                              "trap": "0 이 정상값이다 — 사무관리회사를 두지 않는 펀드가 있다. **합산 성분이므로 0 을 배제하지 않는다.**"},
            "redemption_prohibited": {"ko": "환매금지 여부", "desc": "`1` = 환매금지형(폐쇄형)."},
            "redemption_fee_desc": {"ko": "환매수수료 설명", "desc": "원문 텍스트. 정규화 전."},
            "redemption_pay_rule": {"ko": "환매대금 지급 규칙", "desc": "‘제N영업일’ 형태 원문."},
            "mirae_pd_clss": {"ko": "사내 분류코드", "desc": "미래에셋 내부 코드. **해독 미완 — 답변에 노출 금지.**"},
            "mirae_pd_typ_cd": {"ko": "사내 유형코드", "desc": "마스터 `or_attr_desc` 와 같은 체계로 관측됨."},
            "mirae_fd_stc_cd": {"ko": "사내 펀드구조 코드", "desc": "내부 코드. 해독 미완."},
            "mirae_spc_dv_cd": {"ko": "사내 특수구분 코드", "desc": "내부 코드. 해독 미완."},
            "class_desc_ko": {"ko": "클래스 한글 설명", "desc": "수수료 구조·판매 채널·가입 자격 서술. 클래스 질의의 좋은 근거."},
            "mother_fund_names_raw": {"ko": "모펀드명 (원문)", "desc": "투자개요 텍스트에서 추출. **정규화 전** 이라 표기가 흔들린다.",
                                      "trap": "모자형 판정의 보조 근거일 뿐, 이 값으로 모펀드 개체를 만들지 말 것."},
            "prospectus_url": {"ko": "간이투자설명서 URL", "desc": "원문 링크. 출처 기재·재현용."},
            "retrieved_at": {"ko": "수집 일시", "desc": "2026-08-18 관측."},
            "source": {"ko": "출처", "desc": "수집 원천 표기."},
        },
    },
}

HEADER_NOTE = """> **이 문서가 답하는 것**: 이 도메인의 DB 에 무엇이 들어 있고, 각 컬럼이 무슨 뜻이며,
> 비어 있는 칸을 우리가 어떻게 판정했고 그 근거가 무엇인가.
>
> 🔴 **손으로 고치지 마세요.** `python scripts/gen_data_dictionary.py` 로 재생성됩니다.
> 내용을 바꾸려면 판정의 원본인 `ontology/enums/<도메인>.yaml`(마스터) 또는
> `scripts/gen_data_dictionary.py` 의 `EXT_DICT`(외부)를 고칩니다.

## 0. 결측을 다루는 원칙

주최 공지: **0 과 결측은 의도된 값이다.** 채우지 말고, 조회 시 빼거나 "없다"고 답한다.
2026-08-26 추가 답변으로 더 좁혀졌다 — *"수익률·총보수 같은 컬럼을 질의했을 때 그 컬럼의 값이
0 인 행들은 아예 포함하지 않는 게 맞다 (값이 0 이니 당연히 기준이 없음)"*.

그래서 우리는 값을 **고치지 않고 판정으로 선언**한다. 네 가지로 나눈다.

| `missing_reason` | 뜻 | 답변 문장 |
| :-- | :-- | :-- |
| `not_applicable` | 그 상품엔 개념 자체가 없음 | "해당 사항이 없습니다" (❌ "모릅니다") |
| `missing` | 있어야 하는데 미수록 | "데이터가 제공되지 않았습니다" |
| `present` / `none` | 결측 없음 | 그대로 답변 |
| `mixed` | 행마다 이유가 다름 | `값별 의미` 로 분해해 판단 |

**결측이 아닌데 비어 보이는 것** 세 가지를 따로 구분한다.

- **위장결측** — 값은 있는데 의미가 없다. 날짜 `0`/`00000000`, 더미 코드 `000000000000`, 채권 `dur = 99`
- **센티넬** — 부재를 나타내는 특정 값. 수익률 `-100`, 해외 기초지수 `'Index is not provided by...'`
- **0** — 위 주최 규칙 적용. 예외는 0 이 랭킹 축이 아니라 분류 정보이거나 합산 성분인 컬럼뿐이며,
  그런 컬럼에는 아래 사전에 `0 처리` 행이 붙어 있다.

계층은 셋이고, 충돌하면 **마스터(L0)가 항상 이긴다**. `ext_*`(L2)는 마스터가 비어 있을 때만 쓰고
기준일이 다르므로 답변에 병기한다.
"""


def build(name: str, con: sqlite3.Connection, meta: dict) -> Path:
    title, masters, exts = DOCS[name]
    L = [f"# 📖 데이터 사전 — {title}", ""]
    L.append(f"> 대상 테이블: {' · '.join('`' + t + '`' for t in masters + exts)}")
    L.append("> 생성: `scripts/gen_data_dictionary.py` · 출처 = `schema_metadata` + 라이브 DB 실측 "
             "+ `ontology/enums/*.yaml` + 적재 스크립트")
    L.append("")
    L.append(HEADER_NOTE)
    L.append("")
    L.append("---")
    L.append("")

    for t in masters:
        dom_yaml = yaml.safe_load((ROOT / "ontology" / "enums" / f"{t}.yaml").read_text(encoding="utf-8"))
        L += render_master(con, t, dom_yaml, meta.get(t, {}))
        L += ["", "---", ""]

    if exts:
        for t in exts:
            L += render_ext(con, t)
            L += ["", "---", ""]
    else:
        L += ["## 🌐 외부 보강 데이터", "",
              "이 도메인에는 `ext_*` 테이블이 **없습니다.** 채권 구성종목·발행사 재무 같은 외부 사실은 "
              "아직 수집되지 않았고, 코드북(`data/external/lookups/`)의 담보구분·발행사 업종 매핑이 "
              "edge 후보로 남아 있습니다 (`docs/graph_sources_review_2026-08-25.md` §1).", "", "---", ""]

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def main() -> None:
    if not DB.exists():
        sys.exit(f"DB 없음: {DB}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    meta: dict = {}
    for t, c, ko, dt, nu in con.execute("select table_name,column_name,korean_name,data_type,nullable from schema_metadata"):
        meta.setdefault(t, {})[c] = {"korean_name": ko, "data_type": dt, "nullable": nu}

    targets = sys.argv[1:] or list(DOCS)
    for name in targets:
        if name not in DOCS:
            sys.exit(f"알 수 없는 대상: {name} (가능: {', '.join(DOCS)})")
        p = build(name, con, meta)
        lines = len(p.read_text(encoding="utf-8").splitlines())
        print(f"✅ {p.relative_to(ROOT)}  ({lines:,}줄)")
    con.close()


if __name__ == "__main__":
    main()
