# -*- coding: utf-8 -*-
"""외부 수집 ETF 구성종목(Holdings) → SQLite ext_* 테이블 적재 (교차질의 재료)

입력 (data/external/, git 제외 — 드라이브 배포본):
  holdings/domestic_holdings_20260710.csv          국내 ETF 구성종목 (FunETF 경유 KRX/코스콤, 기준일 2026-07-10)
  holdings_overseas/overseas_holdings.csv          해외 ETF 구성종목 (SEC EDGAR NPORT-P, ETF별 report_date 3/31~5/31)
  holdings_overseas/ticker_series_map.csv          해외 티커 ↔ ISIN(마스터 pd_isin_cd 조인 키)

출력:
  ext_etf_holdings      국내 — etf_code(=domestic_etfs.pd_itm_no) · constituent · ticker · weight_pct · as_of
  ext_ovs_etf_holdings  해외 — etf_ticker · isin(=overseas_etfs.pd_isin_cd) · holding_name · pct_val · report_date

🔴 유출 가드: 외부 자료는 발행일 ≤ 2026-08-24 (8/24 공지). 두 파일 모두 7/10·≤5/31 로 통과.
   교차질의 예시 "삼성전자를 보유한 국내/해외ETF·공모펀드" 는
   ext_etf_holdings.constituent / ext_ovs_etf_holdings.holding_name / ext_fund_holdings.holding_nm 세 곳을 함께 본다.
   답변 시 as_of / report_date 를 반드시 병기한다 (마스터 기준일 8/22 와 다르다).

사용: python scripts/load_external_holdings.py
"""
import os, sys, glob, sqlite3
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "financial_products.db")
EXT = os.path.join(ROOT, "data", "external")
AS_OF_LIMIT = "2026-08-24"

def main():
    con = sqlite3.connect(DB)
    # 국내
    # 최신 스냅샷 우선 (8/21 재수집본 → 없으면 7/10). 파일명의 날짜가 as_of.
    cands = sorted(glob.glob(os.path.join(EXT, "holdings", "domestic_holdings_*.csv")))
    p = cands[-1]
    print(f"국내 원천: {os.path.basename(p)}")
    d = pd.read_csv(p, dtype={"ticker": str, "etf_code": str}, encoding="utf-8-sig")
    assert (d["as_of"].astype(str) <= AS_OF_LIMIT).all(), "국내 holdings 기준일이 허용 범위를 넘음"
    con.execute("drop table if exists ext_etf_holdings")
    d.to_sql("ext_etf_holdings", con, index=False)
    con.execute("create index idx_ext_etfh_code on ext_etf_holdings(etf_code)")
    con.execute("create index idx_ext_etfh_const on ext_etf_holdings(constituent)")
    con.execute("create index idx_ext_etfh_ticker on ext_etf_holdings(ticker)")
    n_etf = d["etf_code"].nunique()
    print(f"ext_etf_holdings      {len(d):>8,}행 · ETF {n_etf:,} · as_of {d['as_of'].min()}~{d['as_of'].max()}")
    # 해외
    # 확장 재수집 폴더(holdings_overseas_YYYYMMDD) 가 있으면 그것을 쓰고, 거기 없는 티커는 기존 186종본으로 보충
    dirs = sorted(glob.glob(os.path.join(EXT, "holdings_overseas_*"))) or []
    base = os.path.join(EXT, "holdings_overseas")
    frames, maps = [], []
    for dd in ([dirs[-1]] if dirs else []) + [base]:
        hp = os.path.join(dd, "overseas_holdings.csv")
        if not os.path.exists(hp):
            continue
        f = pd.read_csv(hp, dtype={"cusip": str}, encoding="utf-8-sig")
        mm = pd.read_csv(os.path.join(dd, "ticker_series_map.csv"), encoding="utf-8-sig")
        if frames:
            f = f[~f["etf_ticker"].isin(set(pd.concat(frames)["etf_ticker"]))]
        print(f"해외 원천: {os.path.basename(dd)} — ETF {f['etf_ticker'].nunique():,} (신규분만)")
        frames.append(f); maps.append(mm)
    o = pd.concat(frames, ignore_index=True)
    m = pd.concat(maps, ignore_index=True).drop_duplicates("ticker")
    o = o.merge(m[["ticker", "isin"]].rename(columns={"ticker": "etf_ticker"}), on="etf_ticker", how="left")
    assert (o["report_date"].astype(str) <= AS_OF_LIMIT).all(), "해외 holdings 보고기준일이 허용 범위를 넘음"
    con.execute("drop table if exists ext_ovs_etf_holdings")
    o.to_sql("ext_ovs_etf_holdings", con, index=False)
    con.execute("create index idx_ext_ovsh_isin on ext_ovs_etf_holdings(isin)")
    con.execute("create index idx_ext_ovsh_ticker on ext_ovs_etf_holdings(etf_ticker)")
    con.execute("create index idx_ext_ovsh_name on ext_ovs_etf_holdings(holding_name)")
    print(f"ext_ovs_etf_holdings  {len(o):>8,}행 · ETF {o['etf_ticker'].nunique():,} · ISIN 매칭 {o['isin'].notna().mean():.1%} · report_date {o['report_date'].min()}~{o['report_date'].max()}")
    con.commit()
    # 마스터 조인 커버리지
    cov = con.execute("select count(distinct h.etf_code) from ext_etf_holdings h join domestic_etfs e on e.pd_itm_no=h.etf_code").fetchone()[0]
    tot = con.execute("select count(*) from domestic_etfs where pd_grp_no='ETF'").fetchone()[0]
    cov2 = con.execute("select count(distinct h.isin) from ext_ovs_etf_holdings h join overseas_etfs e on e.pd_isin_cd=h.isin").fetchone()[0]
    tot2 = con.execute("select count(*) from overseas_etfs where pd_grp_no='ETF'").fetchone()[0]
    print(f"마스터 조인 커버리지 — 국내 ETF {cov}/{tot} ({cov/tot:.1%}) · 해외 ETF {cov2}/{tot2} ({cov2/tot2:.1%})")
    s = con.execute("select count(distinct etf_code) from ext_etf_holdings where constituent like '%삼성전자%'").fetchone()[0]
    s2 = con.execute("select count(distinct etf_ticker) from ext_ovs_etf_holdings where holding_name like '%Samsung Electronics%'").fetchone()[0]
    s3 = con.execute("select count(distinct grp) from ext_fund_holdings where holding_nm like '%삼성전자%'").fetchone()[0]
    print(f"교차 예시 '삼성전자 보유' — 국내ETF {s} · 해외ETF {s2} · 펀드그룹 {s3}")
    con.close()

if __name__ == "__main__":
    main()
