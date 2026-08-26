"""
미래에셋 금융상품 마스터 데이터(Excel) -> SQLite DB 변환 및 인덱스 구축 스크립트

사용법:
    python scripts/build_db.py

데이터 버전 (2026-08-25 갱신):
    2차 배포본 (2026-08-24 배포 · 기준일 2026-08-22, 해외 8/23 KST) 을 기본으로 읽는다.
    파일명: {prefix}_data.xlsx / {prefix}_schema.xlsx  (prefix = prbd01n001 등)
    1차 배포본(7/11, *_datarows.xlsx) 은 `1.금융상품/_v1_20260711/` 에 보관 — 자동 탐색 대상 아님.
    두 배포본은 컬럼 구성이 다르므로(채권 40→58, ETF 73→98, 펀드 45→75) 섞어 쓰지 않는다.

주의:
    - 기존 DB 의 ext_* / kg_* 테이블은 건드리지 않는다 (마스터 4테이블만 replace).
    - 컬럼명은 원본 그대로(2차는 전부 소문자) 저장한다. SQLite 는 컬럼명 대소문자를 구분하지 않는다.
"""

import os
import sys
import sqlite3
import unicodedata
import pandas as pd

# UTF-8 출력 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "financial_products.db")

DATA_VERSION = "v2_20260824"
DATA_AS_OF = "2026-08-22"          # 국내 영업일 기준 · 해외는 2026-08-23 KST

# 🔴 선행 0 보존 대상 — 엑셀 원본이 0패딩 코드인데 숫자로 추론되어 손실되는 컬럼.
#
#   or_co_xtn_itt_cd   00040010  →  40010.0   앞 4자리(기관 종별)가 통째로 소실
#   exrt_grte_ern_r_tcd  02      →  2         만기보장수익률구분코드
#   pd_ticker          069500    →  69500     국내ETF 6자리 티커 (외부 Holdings 조인 키)
#
# 🔴 dtype=str 을 테이블 전체에 걸면 안 된다. 수익률·AUM·만기일까지 문자열이 되어
#    모든 수치 비교·정렬이 깨진다. 반드시 컬럼을 지정한다.
#
# 근거: 2차 원본 전수 스캔 (4개 테이블 × 전 컬럼, dtype=str 로 읽어 `^0\d+$` 매치 집계, 2026-08-25).
#       날짜 컬럼의 '00000000' (채권 isu_dt 25·mat_dt 4, 해외ETF pd_lstg_dt 11) 은
#       선행 0 손실이 아니라 날짜 위장결측(=0)이므로 숫자형을 유지하고 yaml 에 기록한다.
CODE_COLUMNS = {
    "domestic_bonds": [
        "exrt_grte_ern_r_tcd",  # 만기보장수익률구분코드      544 / 21,882 (0패딩)
        "pd_risk_gcd",          # 상품위험등급 원문 코드     '00'=해당없음 19건
    ],
    "domestic_etfs": [
        "pd_ticker",            # 6자리 티커 (숫자만인 경우 int 추론)
    ],
    "overseas_etfs": [],
    "public_funds": [
        "or_co_xtn_itt_cd",     # 운용사 대외기관코드   23,647 / 23,676
        "trusc_xtn_itt_cd",     # 수탁사 대외기관코드   22,834
        "pfiv_sale_cntl_tcd",   # 판매통제구분코드      23,676
        "fd_estb_ctry_cd",      # 펀드설정국가코드      23,055
        "fd_set_pcd",           # 펀드설정P코드          1,967
        "fss_itm_no",           # 금감원 종목번호       11,613
        "kofia_fd_ccd",         # 금투협 분류코드       11,433
        "mtco_itm_no",          # 운용사 종목번호       11,100
        "rptt_ksd_itm_no",      # 대표 예탁원 종목번호  12,921
        "ksd_itm_no",           # 예탁원 종목번호            5
        "std_itm_no",           # 표준 종목번호             21
        "itm_no",               # PK — 안전을 위해 문자열 고정
    ],
}

TABLES = [
    {
        "prefix": "prbd01n001",
        "table_name": "domestic_bonds",
        "label": "국내채권마스터",
        "indexes": ["pd_no", "pd_nm", "pd_risk_gcd", "mat_dt", "after_tax_yield", "crd_grd", "bd_intp_tcd", "pd_exg_mkt"],
    },
    {
        "prefix": "pref01n001",
        "table_name": "domestic_etfs",
        "label": "국내ETF마스터",
        "indexes": ["pd_itm_no", "pd_nm", "cu_fund_mgmt_co", "pd_risk_cd", "du_er_1y", "du_last_aum", "pd_grp_no", "pd_ticker", "ref_base_index"],
    },
    {
        "prefix": "pref02n001",
        "table_name": "overseas_etfs",
        "label": "해외ETF마스터",
        "indexes": ["pd_itm_no", "pd_nm", "cu_fund_mgmt_co", "du_er_1d", "du_last_aum", "pd_isin_cd", "pd_abrv_nm"],
    },
    {
        "prefix": "prfd01n001",
        "table_name": "public_funds",
        "label": "공모펀드마스터",
        "indexes": ["itm_no", "std_itm_no", "itm_nm", "fd_yr1_ern_r", "zrin_fd_ivst_risk_gcd", "sale_yn", "or_co_xtn_itt_cd", "zrin_btyp_nm"],
    },
]


def find_data_directory():
    """금융상품 데이터 디렉터리 경로 탐색 (NFD/NFC 인코딩 유연 대응)"""
    for item in os.listdir(PROJECT_ROOT):
        normalized = unicodedata.normalize("NFC", item)
        if os.path.isdir(os.path.join(PROJECT_ROOT, item)) and "금융상품" in normalized:
            return os.path.join(PROJECT_ROOT, item)
    raise FileNotFoundError("금융상품 데이터 디렉터리를 찾을 수 없습니다.")


def load_schema_mapping(schema_file_path):
    """schema.xlsx -> {컬럼명: (한글명/코멘트, 데이터타입, nullable)}

    2차 형식: 1행 헤더 = 순번 / 컬럼명 / 데이터타입 / Nullable / 컬럼코멘트
    1차 형식: 0행 '[ 데이터 최종 추출일자 ]', 1행 헤더 = 컬럼명 / PK/FK / 컬럼타입 / 컬럼한글명 / 컬럼값 예시
    두 형식 모두 지원한다.
    """
    if not os.path.exists(schema_file_path):
        return {}
    try:
        df = None
        for header_row in (0, 1):
            cand = pd.read_excel(schema_file_path, header=header_row)
            cols = [str(c) for c in cand.columns]
            if any("컬럼명" in c for c in cols):
                df = cand
                break
        if df is None:
            return {}
        cols = df.columns.tolist()
        pick = lambda kws: next((c for c in cols if any(k in str(c) for k in kws)), None)
        col_name = pick(["컬럼명"])
        col_kor = pick(["코멘트", "한글"])
        col_type = pick(["데이터타입", "컬럼타입"])
        col_null = pick(["Nullable"])

        mapping = {}
        for _, row in df.iterrows():
            eng = str(row[col_name]).strip()
            if not eng or eng == "nan":
                continue
            kor = str(row[col_kor]).strip() if col_kor and pd.notna(row[col_kor]) else ""
            typ = str(row[col_type]).strip() if col_type and pd.notna(row[col_type]) else ""
            nul = str(row[col_null]).strip() if col_null and pd.notna(row[col_null]) else ""
            mapping[eng.lower()] = (kor, typ, nul)
        return mapping
    except Exception as e:
        print(f"⚠️ 스키마 맵핑 파일 읽기 경고 ({os.path.basename(schema_file_path)}): {e}")
        return {}


def build_database():
    os.makedirs(DATA_DIR, exist_ok=True)
    source_dir = find_data_directory()

    print("=" * 60)
    print(f"🚀 SQLite DB 구축 시작: {DB_PATH}")
    print(f"📁 소스 데이터 경로: {source_dir}")
    print(f"📅 데이터 버전 {DATA_VERSION} · 기준일 {DATA_AS_OF}")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 스키마 메타데이터 테이블 — 기존 3컬럼 구조 유지 + 타입/nullable 추가
    cursor.execute("DROP TABLE IF EXISTS schema_metadata")
    cursor.execute("""
        CREATE TABLE schema_metadata (
            table_name  TEXT,
            column_name TEXT,
            korean_name TEXT,
            data_type   TEXT,
            nullable    TEXT,
            PRIMARY KEY (table_name, column_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS build_info (
            table_name   TEXT PRIMARY KEY,
            source_file  TEXT,
            row_count    INTEGER,
            col_count    INTEGER,
            data_version TEXT,
            as_of        TEXT
        )
    """)

    dir_files = {unicodedata.normalize("NFC", f): f for f in os.listdir(source_dir)}

    for config in TABLES:
        tbl_name = config["table_name"]
        prefix = config["prefix"]
        data_file = dir_files.get(f"{prefix}_data.xlsx")
        schema_file = dir_files.get(f"{prefix}_schema.xlsx")

        if not data_file:
            print(f"❌ 데이터 파일 미발견: {prefix}_data.xlsx ({config['label']}) — 1차본(*_datarows.xlsx)은 자동 탐색하지 않습니다")
            continue
        data_file = os.path.join(source_dir, data_file)
        schema_file = os.path.join(source_dir, schema_file) if schema_file else None

        print(f"\n📥 [{tbl_name}] {config['label']} 변환 중... ({os.path.basename(data_file)})")

        # 지정 컬럼만 문자열로 고정해 선행 0 을 보존한다 (CODE_COLUMNS 주석 참조).
        str_cols = {c: str for c in CODE_COLUMNS.get(tbl_name, [])}
        df = pd.read_excel(data_file, dtype=str_cols) if str_cols else pd.read_excel(data_file)
        df.columns = [str(c).strip() for c in df.columns]

        # 지정한 컬럼이 실제로 존재했는지, 선행 0 이 살아남았는지 즉시 확인한다.
        for col in CODE_COLUMNS.get(tbl_name, []):
            if col not in df.columns:
                print(f"  ⚠️ 선행0 대상 컬럼 없음: {col} — CODE_COLUMNS 갱신 필요")
                continue
            sample = df[col].dropna().astype(str)
            padded = sample[sample.str.match(r"^0\d")]
            print(f"  🔑 {col:<20} 0패딩 {len(padded):>6,}건 보존  예) {padded.iloc[0] if len(padded) else '—'}")

        df.to_sql(tbl_name, conn, if_exists="replace", index=False)
        print(f"  ✅ [{tbl_name}] {len(df):,} 행 × {len(df.columns)} 열 저장 완료")

        mapping = load_schema_mapping(schema_file) if schema_file else {}
        meta_rows = []
        for col in df.columns:
            kor, typ, nul = mapping.get(col.lower(), ("", "", ""))
            meta_rows.append((tbl_name, col, kor, typ, nul))
        cursor.executemany("INSERT OR REPLACE INTO schema_metadata VALUES (?, ?, ?, ?, ?)", meta_rows)
        missing_meta = sum(1 for r in meta_rows if not r[2])
        print(f"  📋 [{tbl_name}] 스키마 메타 {len(meta_rows)}개 등록 (설명 없음 {missing_meta})")

        cursor.execute(
            "INSERT OR REPLACE INTO build_info VALUES (?, ?, ?, ?, ?, ?)",
            (tbl_name, os.path.basename(data_file), len(df), len(df.columns), DATA_VERSION, DATA_AS_OF),
        )

        for idx_col in config["indexes"]:
            if idx_col in df.columns:
                cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{tbl_name}_{idx_col} ON {tbl_name}("{idx_col}");')
            else:
                print(f"  ⚠️ 인덱스 대상 컬럼 없음: {idx_col}")

    conn.commit()

    print("\n" + "=" * 60)
    print("🎉 DB 구축 결과 검증 요약")
    print("=" * 60)
    for t in [c["table_name"] for c in TABLES] + ["schema_metadata", "build_info"]:
        try:
            count = cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  • 테이블 {t:<18}: {count:>8,} 건")
        except Exception as e:
            print(f"  • 테이블 {t:<18}: 생성 안됨 ({e})")
    others = [r[0] for r in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN "
        "('domestic_bonds','domestic_etfs','overseas_etfs','public_funds','schema_metadata','build_info')")]
    if others:
        print(f"  • 보존된 기타 테이블: {', '.join(others)}")

    conn.close()
    print("\n✨ DB 구축이 성공적으로 완료되었습니다! 파일: " + DB_PATH)


if __name__ == "__main__":
    build_database()
