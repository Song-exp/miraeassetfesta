# -*- coding: utf-8 -*-
"""미래에셋 웹 수집물 → SQLite 보조 테이블 적재 (멱등: drop & recreate).

입력: data/external/miraeasset_web/fund_pages_full.csv · holdings_full.csv
출력: ext_fund_page      — 클래스(itm_no) 단위 불변·준정적 필드
      ext_fund_holdings  — 펀드묶음(grp=mtco_itm_no) 단위 구성종목

🔴 유출 가드 (PROJECT.md §2-2 데이터 기준일 2026-08-22 · 외부자료 발행일 ≤ 2026-08-24):
  - 페이지의 시계열 값(순자산 NASST_SUM·수익률 M*_BNFR)은 **적재하지 않는다** —
    8/18 관측치라 답변 근거로 쓰면 감점. 결측 검증용은 CSV 에만 남긴다.
  - 적재 대상: 설정일(estd)·운용사명(ADMICN)·보수 분해(투자설명서 기재 사항)·
    환매 규칙·사내 분류코드·모펀드명 — 불변 또는 준정적 사실만.
  - holdings 는 bas_dt(기준일)가 행마다 붙으며 전 행 ≤ 7/11 검증 완료(as_of_ok).

사용: python scripts/load_external_web.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "financial_products.db"
SRC = ROOT / "data" / "external" / "miraeasset_web"

PAGE_COLS = {
    # csv 컬럼 → 테이블 컬럼 (전부 불변·준정적)
    "itm_no": "itm_no",
    "estd": "estb_dt",                # 설정일 YYYYMMDD — 불변
    "ADMICN": "mgmt_co_nm",           # 운용사 법인명 — 관측 사실
    "TFEE": "total_fee_pct",          # 총보수 %
    "SLE_FEE": "sale_fee_pct",        # 판매보수 %
    "ADMI_FEE": "mgmt_fee_pct",       # 운용보수 %
    "TRST_FEE": "trust_fee_pct",      # 수탁보수 %
    "OFW_TRST_FEE": "admin_fee_pct",  # 사무수탁보수 %
    "RPC_PHBT_YN": "redemption_prohibited",  # 환매금지 여부(1=금지)
    "RPC_FEE_EXP": "redemption_fee_desc",
    "RPC_TGM_GIV": "redemption_pay_rule",
    "PD_CLSS": "mirae_pd_clss",       # 사내 분류코드 — 해독 진행 중
    "PD_TYP_CD": "mirae_pd_typ_cd",   # 사내 유형코드 — or_attr_desc 와 동일 체계 관측
    "fdStcCd": "mirae_fd_stc_cd",
    "spcDvCd": "mirae_spc_dv_cd",
    "HAN_CLAS_NM": "class_desc_ko",   # 클래스 한글 설명 (수수료·채널·자격)
    "mo_fund_names": "mother_fund_names_raw",  # 투자개요 텍스트 추출 — 정규화 전
    "prospectus_url": "prospectus_url",
    "retrieved_at": "retrieved_at",
    "source": "source",
}
NUM_COLS = ["total_fee_pct", "sale_fee_pct", "mgmt_fee_pct",
            "trust_fee_pct", "admin_fee_pct"]


def main():
    con = sqlite3.connect(DB)

    df = pd.read_csv(SRC / "fund_pages_full.csv", dtype=str)
    df = df[df.page_ok == "True"][list(PAGE_COLS)].rename(columns=PAGE_COLS)
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    con.execute("drop table if exists ext_fund_page")
    df.to_sql("ext_fund_page", con, index=False)
    con.execute("create unique index idx_ext_page_itm on ext_fund_page(itm_no)")
    print(f"ext_fund_page      {len(df):6d}행")

    h = pd.read_csv(SRC / "holdings_full.csv", dtype=str)
    h["weight_pct"] = pd.to_numeric(h.weight_pct, errors="coerce")
    h = h[["grp", "itm_no", "bas_dt", "isin", "holding_nm", "weight_pct",
           "asset_type", "market", "as_of_ok", "retrieved_at", "source"]]
    con.execute("drop table if exists ext_fund_holdings")
    h.to_sql("ext_fund_holdings", con, index=False)
    # 🔴 2026-08-30 A-3-03 — grp(=mtco_itm_no)는 **운용사 안에서만 유일**하다. grp 단독 조인은
    #    103개 grp 가 복수 운용사에 걸려 (클래스,holding) 쌍 179,333 중 5,099(2.84%)를 오부착시킨다
    #    (최악 grp='00' 은 운용사 34곳·클래스 138개). 그렇다고 itm_no 단독 조인으로 바꾸면
    #    **형제 클래스 비중 확장이 사라져** 쌍이 59,206 으로 줄어든다(정당한 확장 174,234 를 버린다).
    #    → 수집원 클래스의 운용사 코드를 컬럼으로 굳혀 (grp, or_co) 복합키로 조인한다. 확장은 지키고 오부착만 막는다.
    con.execute("alter table ext_fund_holdings add column or_co TEXT")
    con.execute("""update ext_fund_holdings set or_co =
                     (select p.or_co_xtn_itt_cd from public_funds p where p.itm_no = ext_fund_holdings.itm_no)""")
    con.execute("create index idx_ext_hold_grp on ext_fund_holdings(grp)")
    con.execute("create index idx_ext_hold_orco_grp on ext_fund_holdings(or_co, grp)")
    con.execute("create index idx_ext_hold_isin on ext_fund_holdings(isin)")
    con.execute("create index idx_ext_hold_nm on ext_fund_holdings(holding_nm)")
    n_orco = con.execute("select count(*) from ext_fund_holdings where or_co is null").fetchone()[0]
    print(f"ext_fund_holdings  {len(h):6d}행 · 그룹 {h.grp.nunique()} · or_co 미해결 {n_orco}행")

    con.commit()

    # 검증 예시 — "미래에셋자산운용이 운용하는 판매중 펀드 수" (기존 조회 불가 질의)
    q = """select count(distinct p.itm_no) from ext_fund_page e
           join public_funds p on p.itm_no = e.itm_no
           where e.mgmt_co_nm = '미래에셋자산운용' and p.sale_yn = '판매중'"""
    print("검증 질의 — 미래에셋자산운용 판매중 클래스:", con.execute(q).fetchone()[0])
    q2 = """select count(distinct grp) from ext_fund_holdings
            where holding_nm like '%Apple%' or holding_nm like '%애플%'"""
    print("검증 질의 — Apple 편입 펀드묶음:", con.execute(q2).fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
