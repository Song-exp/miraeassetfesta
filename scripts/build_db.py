"""
미래에셋 금융상품 마스터 데이터(Excel) -> SQLite DB 변환 및 인덱스 구축 스크립트

사용법:
    python scripts/build_db.py
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


def find_data_directory():
    """금융상품 데이터 디렉터리 경로 탐색 (NFD/NFC 인코딩 유연 대응)"""
    for item in os.listdir(PROJECT_ROOT):
        normalized = unicodedata.normalize("NFC", item)
        if os.path.isdir(os.path.join(PROJECT_ROOT, item)) and "금융상품" in normalized:
            return os.path.join(PROJECT_ROOT, item)
    raise FileNotFoundError("금융상품 데이터 디렉터리를 찾을 수 없습니다.")


def load_schema_mapping(schema_file_path):
    """schema.xlsx 파일에서 영문 컬럼명 -> 한글 컬럼명 및 설명 맵핑 추출"""
    if not os.path.exists(schema_file_path):
        return {}

    try:
        df = pd.read_excel(schema_file_path, header=1)
        # 컬럼명 통일: 컬럼명(0), 컬럼한글명(3)
        cols = df.columns.tolist()
        col_name_key = [c for c in cols if "컬럼명" in str(c)][0]
        col_kor_key = [c for c in cols if "한글" in str(c)][0]

        mapping = {}
        for _, row in df.iterrows():
            eng = str(row[col_name_key]).strip()
            kor = str(row[col_kor_key]).strip() if pd.notna(row[col_kor_key]) else ""
            if eng and eng != "nan":
                mapping[eng] = kor
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
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 스키마 메타데이터 테이블 준비
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_metadata (
            table_name TEXT,
            column_name TEXT,
            korean_name TEXT,
            PRIMARY KEY (table_name, column_name)
        )
    """)

    tables_config = [
        {
            "data_keyword": "국내채권마스터",
            "schema_keyword": "국내채권마스터_schema",
            "table_name": "domestic_bonds",
            "indexes": ["PD_NO", "PD_NM", "PD_RISK_GCD", "MAT_DT", "AFTER_TAX_YIELD"]
        },
        {
            "data_keyword": "국내ETF마스터",
            "schema_keyword": "국내ETF마스터_schema",
            "table_name": "domestic_etfs",
            "indexes": ["pd_itm_no", "pd_nm", "cu_fund_mgmt_co", "pd_risk_cd", "du_er_1y", "du_last_aum"]
        },
        {
            "data_keyword": "해외ETF마스터",
            "schema_keyword": "해외ETF마스터_schema",
            "table_name": "overseas_etfs",
            "indexes": ["pd_itm_no", "pd_nm", "cu_fund_mgmt_co", "du_er_1d", "du_last_aum"]
        },
        {
            "data_keyword": "공모펀드마스터",
            "schema_keyword": "공모펀드마스터_schema",
            "table_name": "public_funds",
            "indexes": ["std_itm_no", "itm_nm", "fd_yr1_ern_r", "zrin_fd_ivst_risk_gcd"]
        }
    ]

    dir_files = os.listdir(source_dir)

    for config in tables_config:
        tbl_name = config["table_name"]

        # 데이터 파일 찾기
        data_file = None
        schema_file = None

        for f in dir_files:
            norm_f = unicodedata.normalize("NFC", f)
            if config["data_keyword"] in norm_f and f.endswith("datarows.xlsx"):
                data_file = os.path.join(source_dir, f)
            elif config["schema_keyword"] in norm_f and f.endswith(".xlsx"):
                schema_file = os.path.join(source_dir, f)

        if not data_file:
            print(f"❌ 데이터 파일 미발견: {config['data_keyword']}")
            continue

        print(f"\n📥 [{tbl_name}] 데이터 변환 중... ({os.path.basename(data_file)})")
        df = pd.read_excel(data_file)

        # SQLite 테이블 저장
        df.to_sql(tbl_name, conn, if_exists="replace", index=False)
        print(f"  ✅ [{tbl_name}] {len(df):,} 개 레코드 저장 완료")

        # 스키마 맵핑 및 메타데이터 저장
        if schema_file:
            mapping = load_schema_mapping(schema_file)
            meta_rows = []
            for col in df.columns:
                kor_name = mapping.get(col, "")
                meta_rows.append((tbl_name, col, kor_name))

            cursor.executemany(
                "INSERT OR REPLACE INTO schema_metadata VALUES (?, ?, ?)",
                meta_rows
            )
            print(f"  📋 [{tbl_name}] 한글 컬럼 메타데이터 {len(meta_rows)}개 등록")

        # 인덱스 생성
        for idx_col in config["indexes"]:
            if idx_col in df.columns:
                idx_name = f"idx_{tbl_name}_{idx_col}"
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl_name}({idx_col});")

    conn.commit()

    # 구축 결과 요약 검증
    print("\n" + "=" * 60)
    print("🎉 DB 구축 결과 검증 요약")
    print("=" * 60)

    tables = ["domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds", "schema_metadata"]
    for t in tables:
        try:
            count = cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  • 테이블 {t:<18}: {count:>8,} 건")
        except Exception as e:
            print(f"  • 테이블 {t:<18}: 생성 안됨 ({e})")

    conn.close()
    print("\n✨ DB 구축이 성공적으로 완료되었습니다! 파일: " + DB_PATH)


if __name__ == "__main__":
    build_database()
