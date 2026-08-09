"""
미래에셋 금융상품 마스터 데이터 컬럼 프로파일 자동 생성 스크립트

EDA 1단계 도구입니다. 사람이 손으로 뽑으면 느리고 오타가 나는 "기계적 사실"만 뽑습니다.
해석과 판단은 담당자가 `docs/eda/<domain>_notes.md`에 씁니다.

사용법:
    python scripts/profile_table.py                   # 4개 테이블 전체 (약 40초)
    python scripts/profile_table.py domestic_etfs     # 특정 테이블만
    python scripts/profile_table.py --report          # 재실행 없이 중요 발견만 요약
    python scripts/profile_table.py --report public_funds

출력:
    ontology/enums/<domain>.auto.yaml               컬럼 프로파일 (매번 통째로 덮어씀)
    ontology/enums/<domain>.<column>.values.txt     distinct 200종 초과 컬럼의 값 목록

⚠️ 이 스크립트는 DB를 **읽기 전용(mode=ro)** 으로 엽니다.
   실수로 쓰기 코드가 들어가도 커넥션이 거부하므로 원본이 훼손되지 않습니다.
   원본 엑셀 파일은 열지도 않습니다.

━━━ 탐지기(Detector) 추가 방법 ━━━
새로운 데이터 함정 패턴을 발견하면 함수 하나를 쓰고 DETECTORS 리스트에 등록하세요.
4개 테이블 전체에 자동으로 적용됩니다. 한 사람의 발견이 전원에게 전파됩니다.

    def detect_my_pattern(ctx):
        n = ctx.scalar('SELECT COUNT(*) FROM {t} WHERE ...')
        if not n:
            return []
        return [Finding("my_pattern", "medium", f"설명 {n:,}건", n, ctx.sql('...'))]

    DETECTORS = [..., detect_my_pattern]
"""

import os
import re
import sys
import sqlite3
import argparse
from pathlib import Path
from dataclasses import dataclass, field

import yaml

# UTF-8 출력 설정 (Windows 한국어 로케일에서 cp949 인코딩 오류 방지)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "financial_products.db"
OUT_DIR = PROJECT_ROOT / "ontology" / "enums"

DOMAINS = ["domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"]

# distinct 값이 이 개수를 넘으면 yaml에 인라인하지 않고 별도 .txt로 분리
DISTINCT_INLINE_LIMIT = 200
# 수치형 이상치 판정: max가 p99의 이 배수를 넘으면 플래그
OUTLIER_RATIO = 5.0
# 분포 폭 판정: p99가 p50의 이 배수를 넘으면 플래그
WIDE_RANGE_RATIO = 10.0

# "값이 있는 척하는 결측" 문자열 패턴 (§8-② 위장 결측)
SENTINEL_PATTERNS = [
    "not provided", "not available", "no data", "n/a", "na.",
    "unknown", "미제공", "해당없음", "해당 없음", "확인불가",
]

# 식별자(키) 후보로 볼 컬럼명 패턴
ID_COLUMN_RE = re.compile(r"(^|_)(no|cd|id|code|isin)$|itm_no|isin", re.IGNORECASE)

# 플래그·날짜·코드 컬럼 — 수치처럼 저장돼 있지만 연속량이 아니므로 분포 탐지에서 제외
NON_CONTINUOUS_RE = re.compile(r"_(yn|dt|cd|gcd|pcd|tcd|ccd|id)$", re.IGNORECASE)

# 비율·수익률 컬럼 — 값의 범위가 상식적으로 제한되는 양.
# 분포 폭 이상은 이런 컬럼에서만 의미가 있습니다 (AUM·거래대금은 원래 분포가 넓음).
RATE_COLUMN_RE = re.compile(r"_rt$|_er_|ern_r$|_r$|yield|irt|rate", re.IGNORECASE)
RATE_KOREAN_RE = re.compile(r"[율률]")


# ────────────────────────────────────────────────────────────────
# 자료 구조
# ────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """탐지기가 발견한 사실 하나. 해석이 아니라 사실만 담습니다."""
    detector: str
    severity: str          # high | medium | info
    message: str
    count: int = 0
    repro_sql: str = ""


@dataclass
class ColumnContext:
    """탐지기에 넘어가는 컬럼 컨텍스트."""
    conn: sqlite3.Connection
    table: str
    column: str
    korean_name: str
    kind: str                                  # numeric | text | empty
    total: int
    n_null: int
    n_blank: int
    n_padded: int
    n_distinct: int
    values: list = field(default_factory=list)  # [(값, 건수)] — text 계열만
    numeric: dict = field(default_factory=dict)  # min/p01/p50/p99/max/mean

    # ── 탐지기가 쓰는 헬퍼 ──
    def sql(self, template: str) -> str:
        """{t}=테이블, {c}=따옴표 처리된 컬럼명 치환."""
        return template.format(t=self.table, c=f'"{self.column}"')

    def scalar(self, template: str):
        return self.conn.execute(self.sql(template)).fetchone()[0]

    @property
    def text_values(self) -> list:
        return [v for v, _ in self.values if isinstance(v, str)]

    @property
    def is_continuous(self) -> bool:
        """수치처럼 저장돼 있어도 플래그·날짜·코드·저카디널리티 범주는 연속량이 아니다."""
        return (self.kind == "numeric"
                and not NON_CONTINUOUS_RE.search(self.column)
                and self.n_distinct >= 50)

    @property
    def is_rate_like(self) -> bool:
        """값의 범위가 상식적으로 제한되는 비율·수익률 컬럼인가."""
        return bool(RATE_COLUMN_RE.search(self.column)
                    or RATE_KOREAN_RE.search(self.korean_name or ""))


@dataclass
class TableContext:
    """테이블 단위 탐지기에 넘어가는 컨텍스트."""
    conn: sqlite3.Connection
    table: str
    total: int
    columns: dict                              # {컬럼명: ColumnContext}

    def scalar(self, sql: str):
        return self.conn.execute(sql).fetchone()[0]


# ────────────────────────────────────────────────────────────────
# 컬럼 단위 탐지기
# ────────────────────────────────────────────────────────────────

def detect_padding(ctx):
    """§8-① 고정폭 공백 패딩. TRIM 없이 정확일치하면 조용히 0건이 나옵니다."""
    if ctx.kind != "text" or not ctx.n_padded:
        return []
    pct = ctx.n_padded / ctx.total * 100
    return [Finding(
        "padding", "high",
        f"앞뒤 공백 패딩 {ctx.n_padded:,}건 ({pct:.1f}%) — 정확일치 비교 시 TRIM() 필수",
        ctx.n_padded,
        ctx.sql('SELECT COUNT(*) FROM {t} WHERE {c} <> TRIM({c})'),
    )]


def detect_blank_string(ctx):
    """§8-② 공백 문자열 결측. IS NULL 로는 안 잡힙니다."""
    if not ctx.n_blank:
        return []
    pct = ctx.n_blank / ctx.total * 100
    return [Finding(
        "blank_string", "high",
        f"공백만 든 문자열 {ctx.n_blank:,}건 ({pct:.1f}%) — NULL이 아니지만 결측",
        ctx.n_blank,
        ctx.sql("SELECT COUNT(*) FROM {t} WHERE {c} IS NOT NULL AND TRIM(CAST({c} AS TEXT))=''"),
    )]


def detect_sentinel(ctx):
    """§8-② 센티넬 문자열 결측. 'Index is not provided by ...' 같은 문장형 결측."""
    out = []
    for value, cnt in ctx.values:
        if not isinstance(value, str):
            continue
        low = value.lower()
        if any(p in low for p in SENTINEL_PATTERNS):
            escaped = value.replace("'", "''")
            out.append(Finding(
                "sentinel", "high",
                f"센티넬(위장 결측) 값 {cnt:,}건: {value!r}",
                cnt,
                f"SELECT COUNT(*) FROM {ctx.table} WHERE TRIM(\"{ctx.column}\")='{escaped}'",
            ))
    return out


def detect_multivalue(ctx):
    """한 칸에 여러 값이 콤마로 묶인 컬럼. 파싱 없이는 필터링 불가."""
    if ctx.kind != "text" or not ctx.values:
        return []
    vals = ctx.text_values
    if not vals:
        return []
    hits = sum(1 for v in vals if "," in v)
    if hits / len(vals) < 0.2:
        return []
    sample = next(v for v in vals if "," in v)
    return [Finding(
        "multivalue", "medium",
        f"distinct 값의 {hits / len(vals) * 100:.0f}%가 콤마 결합 다중값 (예: {sample!r}) — 파싱 필요",
        hits,
        ctx.sql("SELECT DISTINCT {c} FROM {t} WHERE {c} LIKE '%,%' LIMIT 10"),
    )]


def detect_mixed_type_categorical(ctx):
    """설명값과 미해독 코드값이 섞인 범주형. 예: '주식형' 사이에 '06'이 섞여 있음."""
    if ctx.kind != "text" or not (2 <= ctx.n_distinct <= DISTINCT_INLINE_LIMIT):
        return []
    numeric_like = [(v, c) for v, c in ctx.values if isinstance(v, str) and v.strip().isdigit()]
    worded = [v for v, _ in ctx.values if isinstance(v, str) and not v.strip().isdigit() and v.strip()]
    if not numeric_like or not worded:
        return []
    total_hits = sum(c for _, c in numeric_like)
    codes = ", ".join(repr(v) for v, _ in numeric_like[:5])
    return [Finding(
        "mixed_type_categorical", "medium",
        f"설명값 사이에 숫자 코드가 섞임 ({codes}) — 디코딩 안 된 값으로 추정, {total_hits:,}건",
        total_hits,
        ctx.sql("SELECT {c}, COUNT(*) FROM {t} GROUP BY 1 ORDER BY 2 DESC"),
    )]


def detect_outlier(ctx):
    """§8-⑧ 수치 이상치. Top-N 질의에서 1위로 올라옵니다."""
    n = ctx.numeric
    if not n:
        return []
    out = []
    p50, p99, mx = n["p50"], n["p99"], n["max"]
    if p99 and mx > abs(p99) * OUTLIER_RATIO:
        out.append(Finding(
            "outlier_high", "medium",
            f"최대값 {mx:,.2f} 이 p99({p99:,.2f})의 {mx / abs(p99):.1f}배 "
            f"— 단위 정의 오류 가능성. 원본 schema 대조 필요",
            0,
            ctx.sql("SELECT * FROM {t} ORDER BY {c} DESC LIMIT 5"),
        ))
    # 소수의 이상치가 아니라 분포 자체가 넓은 경우 (p99가 이미 부풀어 있어 위 규칙에 안 걸림).
    # AUM·거래대금·주가는 원래 분포가 넓으므로, 값의 범위가 상식적으로 제한되는
    # 비율·수익률 컬럼에서만 판정합니다.
    if p50 and ctx.is_rate_like and abs(p99 / p50) > WIDE_RANGE_RATIO:
        out.append(Finding(
            "wide_range", "medium",
            f"비율 컬럼인데 분포가 극단적으로 넓음 — p50 {p50:,.2f} / p99 {p99:,.2f} / max {mx:,.2f} "
            f"(p99가 p50의 {abs(p99 / p50):.0f}배). 단위·정의(누적/연환산) 확인 필요",
            0,
            ctx.sql("SELECT * FROM {t} ORDER BY {c} DESC LIMIT 10"),
        ))
    return out


def detect_zero_heavy(ctx):
    """
    non-null 값의 상당수가 0인 수치 컬럼.
    "값이 있다"와 "값이 0이다"는 다릅니다 — 미입력을 0으로 채운 것일 수 있고,
    그렇다면 실질 답변 가능 모수가 크게 줄어듭니다.

    플래그(`_yn`)·코드(`_cd`) 컬럼은 0이 정상 값이므로 제외합니다.
    """
    n = ctx.numeric
    if not n or not n.get("n_nonnull") or NON_CONTINUOUS_RE.search(ctx.column):
        return []
    n_zero = n["n_zero"]
    if not n_zero or n_zero / n["n_nonnull"] < 0.3 or n["max"] <= 0:
        return []
    nonzero = n["n_nonnull"] - n_zero
    return [Finding(
        "zero_heavy", "high",
        f"non-null {n['n_nonnull']:,}건 중 {n_zero:,}건({n_zero / n['n_nonnull']:.0%})이 0 "
        f"— 실제 0인지 미입력인지 확인 필요. 0을 제외하면 실질 모수는 {nonzero:,}건",
        n_zero,
        ctx.sql("SELECT COUNT(*) FROM {t} WHERE {c} = 0"),
    )]


def detect_repeated_extreme(ctx):
    """
    최소값 또는 최대값이 여러 건 정확히 반복되는 **연속량** 컬럼.
    자연 데이터라면 극단값이 딱 떨어지게 반복되지 않습니다 — 수치형 센티넬(-100, -999 등) 의심.

    오탐을 막기 위해 제외하는 것:
      · 플래그·날짜·코드 컬럼 (0/1, 갱신일자, 분류코드는 값이 반복되는 게 정상)
      · distinct가 작은 범주형
      · 반복값이 0인 경우 (detect_zero_heavy 가 이미 다룸)
    """
    n = ctx.numeric
    if not n or not n.get("n_nonnull") or not ctx.is_continuous:
        return []
    out = []
    for label, value, cnt in (("최소", n["min"], n["n_min_repeat"]),
                              ("최대", n["max"], n["n_max_repeat"])):
        if value == 0:
            continue
        if cnt >= 10 and cnt / n["n_nonnull"] >= 0.01:
            out.append(Finding(
                "repeated_extreme", "medium",
                f"{label}값 {value:,.2f} 이 정확히 {cnt:,}건 반복 "
                f"— 수치형 센티넬(미상장·데이터없음 표기) 가능성",
                cnt,
                ctx.sql(f"SELECT COUNT(*) FROM {{t}} WHERE {{c}} = {value}"),
            ))
    return out


def detect_empty_or_constant(ctx):
    """전 레코드 결측이거나 값이 한 종류뿐인 컬럼. 질의 대상이 될 수 없습니다."""
    if ctx.n_distinct == 0:
        return [Finding("empty_column", "high",
                        "전 레코드 결측 — 이 컬럼으로는 답변 불가 ('데이터 미제공' 대상)", ctx.total)]
    if ctx.n_distinct == 1:
        only = ctx.values[0][0] if ctx.values else None
        return [Finding("constant_column", "info",
                        f"값이 한 종류뿐 ({only!r}) — 필터 조건으로 의미 없음", ctx.total)]
    return []


def detect_boolean_variant(ctx):
    """Y/N 계열 플래그의 표현 방식. §8-⑨ 테이블마다 표현이 다릅니다."""
    if not ctx.column.lower().endswith("_yn") or ctx.n_distinct > 4:
        return []
    shown = ", ".join(f"{v!r}({c:,})" for v, c in ctx.values[:4])
    return [Finding("boolean_variant", "info",
                    f"플래그 컬럼 표현: {shown} — 다른 테이블과 표기가 다를 수 있음", 0)]


DETECTORS = [
    detect_padding,
    detect_blank_string,
    detect_sentinel,
    detect_multivalue,
    detect_mixed_type_categorical,
    detect_outlier,
    detect_zero_heavy,
    detect_repeated_extreme,
    detect_empty_or_constant,
    detect_boolean_variant,
    # ← 새 패턴을 발견하면 여기에 함수를 추가하세요 (파일 상단 주석 참조)
]


# ────────────────────────────────────────────────────────────────
# 테이블 단위 탐지기
# ────────────────────────────────────────────────────────────────

def detect_duplicate_rows(tctx):
    """전 컬럼이 완전히 동일한 중복 행."""
    uniq = tctx.scalar(f"SELECT COUNT(*) FROM (SELECT DISTINCT * FROM {tctx.table})")
    if uniq == tctx.total:
        return []
    dup = tctx.total - uniq
    return [Finding("duplicate_rows", "high",
                    f"전 컬럼 동일한 중복 행 {dup:,}건 (총 {tctx.total:,} → 고유 {uniq:,})",
                    dup, f"SELECT COUNT(*) FROM (SELECT DISTINCT * FROM {tctx.table})")]


def detect_composite_key(tctx):
    """
    §8-⑦ 식별자로 보이는 컬럼이 실제로는 유일하지 않은 경우를 찾고,
    무엇이 행을 가르는지(복합키의 나머지 축)까지 자동으로 짚어줍니다.
    """
    candidates = [c for c in tctx.columns.values()
                  if ID_COLUMN_RE.search(c.column) and c.n_distinct > 100]
    if not candidates:
        return []
    best = max(candidates, key=lambda c: c.n_distinct)
    if best.n_distinct >= tctx.total:
        return [Finding("primary_key", "info",
                        f"'{best.column}' 이 행 단위 유일 — PK로 사용 가능", 0)]

    ratio = tctx.total / best.n_distinct
    findings = [Finding(
        "not_unique_key", "high",
        f"'{best.column}' 는 유일하지 않음 — {tctx.total:,}행 / 고유 {best.n_distinct:,}개 "
        f"(평균 {ratio:.1f}배 중복). Top-N·집계 질의 시 GROUP BY 필요",
        tctx.total - best.n_distinct,
        f'SELECT COUNT(*), COUNT(DISTINCT "{best.column}") FROM {tctx.table}',
    )]

    # 중복이 가장 심한 값 하나를 뽑아, 어떤 컬럼이 행을 가르는지 확인
    row = tctx.conn.execute(
        f'SELECT "{best.column}" FROM {tctx.table} WHERE "{best.column}" IS NOT NULL '
        f'GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1'
    ).fetchone()
    if row:
        key_value = row[0]
        rows = tctx.conn.execute(
            f'SELECT * FROM {tctx.table} WHERE "{best.column}" = ?', (key_value,)
        ).fetchall()
        names = [d[0] for d in tctx.conn.execute(
            f'SELECT * FROM {tctx.table} LIMIT 0').description]
        varying = [names[i] for i in range(len(names)) if len({r[i] for r in rows}) > 1]
        if varying:
            findings.append(Finding(
                "composite_key_hint", "high",
                f"'{best.column}'={key_value!r} 인 {len(rows)}개 행에서 값이 달라지는 컬럼은 "
                f"{varying} 뿐 — 실질 복합키는 ('{best.column}', {varying[0]!r}) 로 추정",
                len(rows),
                f'SELECT * FROM {tctx.table} WHERE "{best.column}" = {key_value!r}',
            ))
    return findings


TABLE_DETECTORS = [
    detect_duplicate_rows,
    detect_composite_key,
    # ← 테이블 단위 패턴은 여기에 추가
]


# ────────────────────────────────────────────────────────────────
# 프로파일링 본체
# ────────────────────────────────────────────────────────────────

def open_readonly():
    """DB를 읽기 전용으로 연다. 쓰기 시도는 커넥션 레벨에서 거부된다."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"DB가 없습니다: {DB_PATH}\n먼저 `python scripts/build_db.py` 를 실행하세요."
        )
    return sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)


def load_korean_names(conn, table):
    try:
        rows = conn.execute(
            "SELECT column_name, korean_name FROM schema_metadata WHERE table_name = ?",
            (table,),
        ).fetchall()
        return {c: (k or "") for c, k in rows}
    except sqlite3.Error:
        return {}


def infer_kind(conn, table, column):
    rows = conn.execute(
        f'SELECT typeof("{column}") AS t, COUNT(*) FROM {table} GROUP BY 1'
    ).fetchall()
    counts = {t: n for t, n in rows}
    non_null = {t: n for t, n in counts.items() if t != "null"}
    if not non_null:
        return "empty"
    dominant = max(non_null, key=non_null.get)
    return "numeric" if dominant in ("integer", "real") else "text"


def percentiles(values):
    """정렬된 리스트에서 분위수 및 탐지기가 쓸 보조 통계 추출 (외부 의존 없이)."""
    if not values:
        return {}
    s = sorted(values)
    n = len(s)
    at = lambda q: s[min(n - 1, max(0, int(q * (n - 1))))]
    return {
        "min": float(s[0]),
        "p01": float(at(0.01)),
        "p50": float(at(0.50)),
        "p99": float(at(0.99)),
        "max": float(s[-1]),
        "mean": float(sum(s) / n),
        "n_nonnull": n,
        "n_zero": sum(1 for v in s if v == 0),
        "n_min_repeat": sum(1 for v in s if v == s[0]),
        "n_max_repeat": sum(1 for v in s if v == s[-1]),
    }


def profile_column(conn, table, column, total, korean_name):
    kind = infer_kind(conn, table, column)
    q = f'''
        SELECT
            SUM(CASE WHEN "{column}" IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN "{column}" IS NOT NULL
                      AND TRIM(CAST("{column}" AS TEXT)) = '' THEN 1 ELSE 0 END),
            SUM(CASE WHEN "{column}" IS NOT NULL
                      AND CAST("{column}" AS TEXT) <> TRIM(CAST("{column}" AS TEXT))
                     THEN 1 ELSE 0 END),
            COUNT(DISTINCT TRIM(CAST("{column}" AS TEXT)))
        FROM {table}
    '''
    n_null, n_blank, n_padded, n_distinct_raw = conn.execute(q).fetchone()
    # 공백문자열도 하나의 distinct로 세어지므로 제외
    n_distinct = max(0, n_distinct_raw - (1 if n_blank else 0))

    ctx = ColumnContext(
        conn=conn, table=table, column=column, korean_name=korean_name, kind=kind,
        total=total, n_null=n_null or 0, n_blank=n_blank or 0,
        n_padded=n_padded or 0, n_distinct=n_distinct,
    )

    if kind == "numeric":
        vals = [r[0] for r in conn.execute(
            f'SELECT "{column}" FROM {table} WHERE "{column}" IS NOT NULL')]
        ctx.numeric = percentiles(vals)
    elif kind == "text":
        ctx.values = conn.execute(f'''
            SELECT TRIM(CAST("{column}" AS TEXT)) AS v, COUNT(*) AS n
            FROM {table}
            WHERE "{column}" IS NOT NULL AND TRIM(CAST("{column}" AS TEXT)) <> ''
            GROUP BY 1 ORDER BY n DESC
        ''').fetchall()

    findings = [f for det in DETECTORS for f in det(ctx)]

    # 결측 = NULL + 공백문자열 + 센티넬
    sentinel_n = sum(f.count for f in findings if f.detector == "sentinel")
    missing = ctx.n_null + ctx.n_blank + sentinel_n
    return ctx, findings, missing, sentinel_n


def to_yaml_column(ctx, findings, missing, sentinel_n, values_path):
    entry = {
        "korean_name": ctx.korean_name,
        "kind": ctx.kind,
        "total": ctx.total,
        "missing": missing,
        "missing_rate": round(missing / ctx.total, 4) if ctx.total else 0.0,
        "answerable_n": ctx.total - missing,
        "missing_breakdown": {
            "null": ctx.n_null, "blank_string": ctx.n_blank, "sentinel": sentinel_n,
        },
        "distinct_count": ctx.n_distinct,
    }
    if ctx.numeric:
        entry["numeric"] = {k: round(v, 4) for k, v in ctx.numeric.items()}
    if ctx.kind == "text" and ctx.values:
        if len(ctx.values) <= DISTINCT_INLINE_LIMIT:
            entry["values"] = [{"value": v, "count": n} for v, n in ctx.values]
        else:
            entry["values_file"] = values_path
            entry["values_top"] = [{"value": v, "count": n} for v, n in ctx.values[:20]]
    if findings:
        entry["findings"] = [
            {"detector": f.detector, "severity": f.severity, "message": f.message,
             **({"count": f.count} if f.count else {}),
             **({"repro_sql": f.repro_sql} if f.repro_sql else {})}
            for f in findings
        ]
    return entry


def profile_table(conn, table):
    total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    korean = load_korean_names(conn, table)

    print(f"\n📊 [{table}] {total:,}행 × {len(columns)}컬럼 프로파일링")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    contexts, col_yaml, all_findings = {}, {}, []
    for i, column in enumerate(columns, 1):
        ctx, findings, missing, sentinel_n = profile_column(
            conn, table, column, total, korean.get(column, "")
        )
        contexts[column] = ctx
        all_findings.extend(findings)

        values_path = ""
        if ctx.kind == "text" and len(ctx.values) > DISTINCT_INLINE_LIMIT:
            fname = f"{table}.{column}.values.txt"
            (OUT_DIR / fname).write_text(
                "\n".join(f"{n}\t{v}" for v, n in ctx.values), encoding="utf-8"
            )
            values_path = f"ontology/enums/{fname}"

        col_yaml[column] = to_yaml_column(ctx, findings, missing, sentinel_n, values_path)
        flag = "  ⚠️" if any(f.severity == "high" for f in findings) else ""
        print(f"  [{i:>2}/{len(columns)}] {column:<28} "
              f"결측 {col_yaml[column]['missing_rate']:>6.1%}  "
              f"distinct {ctx.n_distinct:>6,}{flag}")

    tctx = TableContext(conn=conn, table=table, total=total, columns=contexts)
    table_findings = [f for det in TABLE_DETECTORS for f in det(tctx)]
    all_findings.extend(table_findings)

    doc = {
        "meta": {
            "domain": table,
            "table": table,
            "row_count": total,
            "column_count": len(columns),
            "data_asof": "2026-07-11",
            "generator": "scripts/profile_table.py",
            "db_access": "read-only (mode=ro)",
            "note": "자동 생성 파일입니다. 직접 편집하지 마세요 — 언제든 재생성됩니다. "
                    "해석과 판단은 docs/eda/<domain>_notes.md 와 ontology/enums/<domain>.yaml 에 씁니다.",
        },
        "table_findings": [
            {"detector": f.detector, "severity": f.severity, "message": f.message,
             **({"count": f.count} if f.count else {}),
             **({"repro_sql": f.repro_sql} if f.repro_sql else {})}
            for f in table_findings
        ],
        "columns": col_yaml,
    }

    out_path = OUT_DIR / f"{table}.auto.yaml"
    with out_path.open("w", encoding="utf-8") as fp:
        fp.write(f"# 자동 생성 파일 — 직접 편집하지 마세요. (scripts/profile_table.py)\n")
        yaml.safe_dump(doc, fp, allow_unicode=True, sort_keys=False, width=120)

    highs = [f for f in all_findings if f.severity == "high"]
    print(f"  ✅ {out_path.relative_to(PROJECT_ROOT)} 생성 "
          f"(발견 {len(all_findings)}건 / 그중 high {len(highs)}건)")
    for f in table_findings:
        print(f"     🔴 [{f.detector}] {f.message}")
    return all_findings


def print_report(targets):
    """이미 만들어진 .auto.yaml 에서 중요 발견만 다시 요약해 출력 (재프로파일링 없음)."""
    for table in targets:
        path = OUT_DIR / f"{table}.auto.yaml"
        if not path.exists():
            print(f"\n⚠️ {path.name} 없음 — 먼저 `python scripts/profile_table.py {table}` 실행")
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        print(f"\n📊 [{table}] {doc['meta']['row_count']:,}행 × {doc['meta']['column_count']}컬럼")

        for f in doc.get("table_findings", []):
            print(f"  🔴 [테이블] {f['detector']}: {f['message']}")

        rows = [(col, f) for col, e in doc["columns"].items()
                for f in e.get("findings", []) if f["severity"] == "high"]
        for col, f in rows:
            print(f"  ⚠️  {col:<28} [{f['detector']}] {f['message']}")

        thin = sorted(
            ((col, e["answerable_n"], e["total"]) for col, e in doc["columns"].items()
             if e["total"] and e["answerable_n"] / e["total"] < 0.5),
            key=lambda r: r[1],
        )[:8]
        if thin:
            print("  📉 답변 가능 모수가 절반 미만인 컬럼 (답변 정책 필요):")
            for col, n, total in thin:
                print(f"       {col:<28} {n:>7,} / {total:,}")


def main():
    parser = argparse.ArgumentParser(
        description="금융상품 마스터 테이블 컬럼 프로파일 자동 생성 (읽기 전용)"
    )
    parser.add_argument("domain", nargs="?", choices=DOMAINS,
                        help="테이블명. 생략하면 4개 전체")
    parser.add_argument("--report", action="store_true",
                        help="재실행 없이, 이미 생성된 .auto.yaml 의 중요 발견만 요약 출력")
    args = parser.parse_args()
    targets = [args.domain] if args.domain else DOMAINS

    if args.report:
        print("=" * 70)
        print("📋 프로파일 요약 — 테이블 발견 + severity:high + 저모수 컬럼")
        print("=" * 70)
        print_report(targets)
        print("\n" + "=" * 70)
        print("   상세는 ontology/enums/<domain>.auto.yaml 을 직접 여세요.")
        print("   각 발견에 repro_sql 이 붙어 있으니 복사해서 돌려보세요.")
        print("=" * 70)
        return

    print("=" * 70)
    print(f"🔍 컬럼 프로파일 생성 — DB: {DB_PATH.name} (읽기 전용)")
    print("=" * 70)

    conn = open_readonly()
    try:
        total_findings = sum(len(profile_table(conn, t)) for t in targets)
    finally:
        conn.close()

    print("\n" + "=" * 70)
    print(f"✨ 완료 — 총 {total_findings}건 발견. 출력: ontology/enums/*.auto.yaml")
    print("   요약만 다시 보려면: python scripts/profile_table.py --report")
    print("   다음 단계: docs/EDA_GUIDE.md §3 의 질문에 답하며 탐색 노트를 작성하세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()
