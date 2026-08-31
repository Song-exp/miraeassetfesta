# -*- coding: utf-8 -*-
"""공모펀드 평가 문항 20건 생성 — 규칙 조건식 → gold SQL → DB 실측 (채권 gen_bond_eval 패턴).

§2-2 2 요구 커버리지: 대표행 · 극단값 · 보수 ‰ · 위험등급 방향 · 되묻기 · 신용등급 기각 각 1문항 이상.
gold_sql 은 validate_sql(guard)을 통과해야 하고(LIMIT 필수), 실행해 gold_rows·gold_sample 을 채운다.

사용: python scripts/gen_fund_eval.py   → eval/questions_public_funds.jsonl
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.runtime.pipeline import validate_sql  # noqa: E402

AS_OF = "2026-08-22"
BASE = "sale_yn = '판매중' AND prvo_pbff_desc = '공모'"
# 펀드단위 키(query_rules.펀드단위) + 역외(mtco NULL 110행)는 행 단위 유지 → itm_no 로 폴백
PAD = "CASE WHEN length(mtco_itm_no) >= 7 THEN mtco_itm_no ELSE substr('0000000' || mtco_itm_no, -7) END"
GRP = f"or_co_xtn_itt_cd || '|' || COALESCE({PAD}, itm_no)"
FEE = "COALESCE(or_co_rwrd_r,0)+COALESCE(sale_co_rwrd_r,0)+COALESCE(trusc_rwrd_r,0)+COALESCE(ofwk_trus_rwrd_r,0)"


def topn(select_extra: str, where_extra: str, order: str, limit: int) -> str:
    """대표행 Top-N — 펀드단위 GROUP BY + 정렬 컬럼 MAX/MIN 행(SQLite bare-column 규칙) + 클래스 n개."""
    return (
        f"SELECT itm_no, TRIM(itm_nm) AS itm_nm, {select_extra}, COUNT(*) AS class_cnt, fd_daily_bas_dt "
        f"FROM public_funds WHERE {BASE} AND {where_extra} "
        f"GROUP BY {GRP} ORDER BY {order} LIMIT {limit}"
    )


QUESTIONS: list[dict] = [
    # ── 답변형 — 위험등급 방향 (제로인: 작을수록 위험, 6 = 매우 낮은 위험) ──
    dict(qid="FND-001", difficulty="하", qtype="조건검색", expected_behavior="answer",
         question="위험등급이 가장 안전한 공모펀드 중 순자산 큰 10개 알려줘",
         gold_sql=topn("zrin_fd_ivst_risk_grd_nm, MAX(fd_nast_suma) AS fd_nast_suma",
                       "zrin_fd_ivst_risk_gcd = 6 AND fd_nast_suma IS NOT NULL AND fd_nast_suma <> 0",
                       "fd_nast_suma DESC", 10),
         must_include=["매우 낮은 위험", "기준일"], must_not_include=["매우 높은 위험", "투자 추천"],
         source_columns=["zrin_fd_ivst_risk_gcd", "fd_nast_suma"],
         note="위험등급 방향: 제로인 1~6, 작을수록 위험 — '가장 안전' = 6. 1로 짜면 정반대. NULL 422행은 모수 밖.",
         gold_reason="규칙 answer_rules.위험등급방향 · 기본모수 · 대표행"),
    dict(qid="FND-002", difficulty="하", qtype="조건검색", expected_behavior="answer",
         question="위험등급 1등급(매우 높은 위험) 공모펀드 중 순자산 큰 5개 알려줘",
         gold_sql=topn("zrin_fd_ivst_risk_grd_nm, MAX(fd_nast_suma) AS fd_nast_suma",
                       "zrin_fd_ivst_risk_gcd = 1 AND fd_nast_suma IS NOT NULL AND fd_nast_suma <> 0",
                       "fd_nast_suma DESC", 5),
         must_include=["매우 높은 위험"], must_not_include=["안전"],
         source_columns=["zrin_fd_ivst_risk_gcd", "fd_nast_suma"],
         note="1등급 = 매우 높은 위험(기본모수 874행). '1등급이 제일 안전' 으로 읽으면 오답.",
         gold_reason="규칙 answer_rules.위험등급방향"),
    # ── 답변형 — 수익률 (극단값 포함 + 주의문구 · 대표행) ──
    dict(qid="FND-003", difficulty="중", qtype="랭킹", expected_behavior="answer",
         question="1년 수익률이 가장 높은 공모펀드 5개 알려줘",
         gold_sql=topn("MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, zrin_fd_ivst_risk_grd_nm",
                       "fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r <> 0 AND fd_yr1_ern_r > -100",
                       "fd_yr1_ern_r DESC", 5),
         must_include=["1년", "기준일", "누적"], must_not_include=["원금 보장", "수익률 전망"],
         source_columns=["fd_yr1_ern_r"],
         note="극단값을 빼지 않는다(query_rules.수익률극단값) — >100% 889행·최대 1,436% 존재, 주의문구로 알린다. "
              "수익률은 누적(연환산 아님). 대표행: 펀드단위 GROUP BY — 한 펀드 6클래스가 TOP5 를 도배하면 오답.",
         gold_reason="규칙 대표행 · 수익률극단값 · 집계_TopN_필수 · answer_rules.누적수익률"),
    dict(qid="FND-004", difficulty="중", qtype="랭킹", expected_behavior="answer",
         question="3년 수익률 상위 5개 공모펀드 알려줘",
         gold_sql=topn("MAX(fd_yr3_ern_r) AS fd_yr3_ern_r",
                       "fd_yr3_ern_r IS NOT NULL AND fd_yr3_ern_r <> 0 AND fd_yr3_ern_r > -100",
                       "fd_yr3_ern_r DESC", 5),
         must_include=["3년", "기준일"], must_not_include=["연평균"],
         source_columns=["fd_yr3_ern_r"],
         note="3년 수익률도 누적 — '연평균' 으로 나누어 말하면 오답(clarify.다의어.수익률). 유효 6,384행.",
         gold_reason="규칙 대표행 · 집계_TopN_필수 · answer_rules.누적수익률"),
    # ── 답변형 — 보수 (‰ · 4항목 합 · 0 = 미입력) ──
    dict(qid="FND-005", difficulty="중", qtype="랭킹", expected_behavior="answer",
         question="총보수가 가장 낮은 공모펀드 5개 알려줘",
         gold_sql=topn(f"MIN({FEE}) AS total_fee, han_clas_nm",
                       f"({FEE}) > 0",
                       "total_fee ASC", 5),
         must_include=["보수"], must_not_include=["0%", "무료"],
         source_columns=["or_co_rwrd_r", "sale_co_rwrd_r", "trusc_rwrd_r", "ofwk_trus_rwrd_r"],
         note="총보수 = 운용+판매+수탁+사무관리 4항목 합. 단위는 ‰(퍼밀) — %로 읽으면 10배 오답(answer_rules.보수단위). "
              "합계 0(기본모수 29행)은 미입력이라 제외 — 0값 행이 '최저 보수' 로 나오면 오답. 클래스별로 다르니 클래스 병기. "
              "1위 피델리티호주(역외) 0.015 는 역내 최저 0.15 의 1/10 — 극단값이지만 빼지 않고 알린다(8/29 공통 결정).",
         gold_reason="규칙 answer_rules.보수단위 · 대표행 · 보수 0 제외"),
    # ── 답변형 — 순자산 · MMF 체제 ──
    dict(qid="FND-006", difficulty="중", qtype="랭킹", expected_behavior="answer",
         question="MMF를 제외하고 순자산이 가장 큰 공모펀드 5개 알려줘",
         gold_sql=topn("MAX(fd_nast_suma) AS fd_nast_suma, zrin_btyp_nm",
                       "(zrin_btyp_nm IS NULL OR zrin_btyp_nm NOT LIKE '%MMF%') AND fd_nast_suma IS NOT NULL AND fd_nast_suma <> 0",
                       "fd_nast_suma DESC", 5),
         must_include=["순자산", "기준일"], must_not_include=["MMF"],
         source_columns=["fd_nast_suma", "zrin_btyp_nm"],
         note="'규모 큰 펀드' 무조건은 법인 MMF 138행이 상위를 채운다(clarify.사람의_선택.규모_MMF포함) — 이 문항은 제외를 명시했으니 답변형.",
         gold_reason="규칙 기본모수 · 대표행 · clarify 조건 명시로 해소"),
    dict(qid="FND-007", difficulty="하", qtype="조건검색", expected_behavior="answer",
         question="MMF 중에서 순자산이 가장 큰 공모펀드 3개 알려줘",
         gold_sql=topn("MAX(fd_nast_suma) AS fd_nast_suma, zrin_btyp_nm",
                       "zrin_btyp_nm LIKE '%MMF%' AND fd_nast_suma IS NOT NULL AND fd_nast_suma <> 0",
                       "fd_nast_suma DESC", 3),
         must_include=["MMF"], must_not_include=[],
         source_columns=["fd_nast_suma", "zrin_btyp_nm"],
         note="기본모수 내 MMF 138행 — 법인 MMF 가 최대 12.4조.",
         gold_reason="규칙 기본모수 · 대표행"),
    # ── 답변형 — 유형 축 ──
    dict(qid="FND-008", difficulty="중", qtype="조건검색", expected_behavior="answer",
         question="채권형 공모펀드 중 1년 수익률 상위 5개 알려줘",
         gold_sql=topn("MAX(fd_yr1_ern_r) AS fd_yr1_ern_r, zrin_btyp_nm",
                       "zrin_btyp_nm LIKE '%채권%' AND fd_yr1_ern_r IS NOT NULL AND fd_yr1_ern_r <> 0 AND fd_yr1_ern_r > -100",
                       "fd_yr1_ern_r DESC", 5),
         must_include=["채권", "1년"], must_not_include=[],
         source_columns=["zrin_btyp_nm", "fd_yr1_ern_r"],
         note="유형은 제로인 분류(zrin_btyp_nm) — 이름 문자열 아님. 기본모수 내 채권형 2,095행.",
         gold_reason="규칙 기본모수 · 대표행 · 집계_TopN_필수"),
    dict(qid="FND-009", difficulty="중", qtype="조건검색", expected_behavior="answer",
         question="주식형 공모펀드 중 순자산 상위 5개 알려줘",
         gold_sql=topn("MAX(fd_nast_suma) AS fd_nast_suma, zrin_btyp_nm",
                       "(zrin_btyp_nm IN ('주식형','해외주식형') OR (zrin_btyp_nm IS NULL AND (trim(or_attr_desc)='주식형' "
                       "OR (trim(or_attr_desc) IN ('재간접','파생상품') AND itm_nm LIKE '%(주식%')))) "
                       "AND fd_nast_suma IS NOT NULL AND fd_nast_suma <> 0",
                       "fd_nast_suma DESC", 5),
         must_include=["주식"], must_not_include=[],
         source_columns=["zrin_btyp_nm", "or_attr_desc", "fd_nast_suma"],
         note="query_rules.자산군_주식형 조건식 그대로 — zrin 우선, NULL 이면 약관 분류 보조.",
         gold_reason="규칙 자산군_주식형 · 대표행"),
    dict(qid="FND-010", difficulty="중", qtype="조건검색", expected_behavior="answer",
         question="최근 분배 실적이 있는 공모펀드 중 순자산 큰 5개 알려줘",
         gold_sql=topn("MAX(fd_nast_suma) AS fd_nast_suma, fd_last_dstb_r",
                       "fd_last_dstb_r IS NOT NULL AND fd_last_dstb_r <> 0 AND fd_nast_suma IS NOT NULL AND fd_nast_suma <> 0",
                       "fd_nast_suma DESC", 5),
         must_include=["분배"], must_not_include=["분배 예정", "배당 전망"],
         source_columns=["fd_last_dstb_r", "fd_nast_suma"],
         note="분배는 '유무·최근 실적' 만 말한다(answer_rules.분배율유무만) — 향후 분배 약속으로 말하면 오답. 유효 3,946행.",
         gold_reason="규칙 answer_rules.분배율유무만 · 대표행"),
    # ── 답변형 — 운용사 (KG Org_00080008 = 미래에셋) ──
    dict(qid="FND-011", difficulty="중", qtype="조건검색", expected_behavior="answer",
         question="미래에셋자산운용이 운용하는 공모펀드 중 순자산 큰 5개 알려줘",
         gold_sql=topn("MAX(fd_nast_suma) AS fd_nast_suma",
                       "or_co_xtn_itt_cd = '00080008' AND fd_nast_suma IS NOT NULL AND fd_nast_suma <> 0",
                       "fd_nast_suma DESC", 5),
         must_include=["미래에셋"], must_not_include=[],
         source_columns=["or_co_xtn_itt_cd", "fd_nast_suma"],
         note="운용사는 KG(Org_00080008 → or_co_xtn_itt_cd='00080008') — 이름 LIKE 아님. 기본모수 내 2,066행.",
         gold_reason="KG alias 운용사 · 기본모수 · 대표행"),
    # ── 답변형 — 건수 (모수 명시) ──
    dict(qid="FND-012", difficulty="하", qtype="건수", expected_behavior="answer",
         question="지금 판매중인 공모펀드는 모두 몇 개야?",
         gold_sql=f"SELECT COUNT(*) AS class_rows, COUNT(DISTINCT {GRP}) AS funds FROM public_funds WHERE {BASE} LIMIT 1",
         must_include=["클래스", "펀드"], must_not_include=[],
         source_columns=["sale_yn", "prvo_pbff_desc"],
         note="클래스(행) 8,969 · 펀드 단위 — 두 수를 구분해 말한다(answer_rules.클래스n개). 기준일 병기.",
         gold_reason="규칙 기본모수 · answer_rules.클래스n개"),
    dict(qid="FND-013", difficulty="하", qtype="건수", expected_behavior="answer",
         question="역외 공모펀드는 몇 개야?",
         gold_sql=f"SELECT COUNT(*) AS n FROM public_funds WHERE {BASE} AND ofsfd_yn = 1 LIMIT 1",
         must_include=["110"], must_not_include=[],
         source_columns=["ofsfd_yn"],
         note="역외 110행(answer_rules.역외110행) — mtco_itm_no 가 없어 펀드단위 묶기에서 행 단위 유지.",
         gold_reason="규칙 answer_rules.역외110행"),
    dict(qid="FND-014", difficulty="하", qtype="건수", expected_behavior="answer",
         question="위험등급 정보가 없는 공모펀드는 몇 개야?",
         gold_sql=f"SELECT COUNT(*) AS n FROM public_funds WHERE {BASE} AND zrin_fd_ivst_risk_gcd IS NULL LIMIT 1",
         must_include=["422"], must_not_include=["위험등급이 낮"],
         source_columns=["zrin_fd_ivst_risk_gcd"],
         note="NULL 422행은 '평가 미수록' — '등급이 낮다/안전하다' 로 읽으면 오답.",
         gold_reason="규칙 기본모수 · 결측은 결측으로"),
    # ── 되묻기형 (gold_sql 없음) ──
    dict(qid="FND-C01", difficulty="불가", qtype="조건누락→역질문", expected_behavior="clarify",
         question="규모가 큰 펀드 추천해줘",
         gold_sql=None,
         must_include=["MMF"], must_not_include=["투자 추천 표현"],
         source_columns=["fd_nast_suma", "zrin_btyp_nm"],
         note="순자산 상위가 법인 MMF 138행으로 채워진다(clarify.사람의_선택.규모_MMF포함) — MMF 포함 여부를 묻거나, "
              "포함/제외 두 답을 나란히 내면 그것도 정답으로 인정(수동 채점 시).",
         gold_reason="clarify — 규모_MMF포함", refusal_type="ask_criteria"),
    dict(qid="FND-C02", difficulty="불가", qtype="다의어→역질문", expected_behavior="clarify",
         question="삼성 펀드 보수 알려줘",
         gold_sql=None,
         must_include=["어떤", "펀드"], must_not_include=["한 펀드로 단정"],
         source_columns=["itm_nm"],
         note="'삼성' 부분일치가 962행·236펀드(기본모수 실측 2026-08-31) — 한 행을 임의로 고르면 오답"
              "(clarify.다의어.펀드이름). 목록 제시 후 선택 유도도 정답.",
         gold_reason="clarify — 펀드이름 복수 일치", refusal_type="ambiguous"),
    # ── 기각형 (gold_sql 없음) ──
    dict(qid="FND-R01", difficulty="불가", qtype="속성부재", expected_behavior="reject",
         question="신용등급이 AAA인 공모펀드 알려줘",
         gold_sql=None,
         must_include=["신용등급", "없"], must_not_include=["AAA 펀드 목록"],
         source_columns=[],
         note="펀드에는 신용등급 컬럼이 없다 — gate absent(CreditGrade, public_funds), 검토표 D-4-04 (2026-08-30 힌트 추가). "
              "위험등급(제로인)으로 대신 안내하는 것은 허용.",
         gold_reason="게이트 attribute_absent", refusal_type="attribute_absent"),
    dict(qid="FND-R02", difficulty="불가", qtype="컬럼미수록", expected_behavior="reject",
         question="지난 1주일 수익률이 가장 높은 공모펀드 알려줘",
         gold_sql=None,
         must_include=["1주", "없"], must_not_include=["1주일 수익률 순위"],
         source_columns=["fd_wk1_ern_r"],
         note="fd_wk1_ern_r 은 100% 결측(23,676/23,676 실측 2026-08-31) — answer_rules.1주수익률 미수록. "
              "1개월 수익률로 대신 안내하는 것은 허용.",
         gold_reason="컬럼 100% 결측", refusal_type="column_absent"),
    dict(qid="FND-R03", difficulty="불가", qtype="무의미비교", expected_behavior="reject_or_clarify",
         question="기준가가 높은 순서로 좋은 펀드 알려줘",
         gold_sql=None,
         must_include=["기준가"], must_not_include=["기준가 높은 펀드가 좋"],
         source_columns=["bns_bpr"],
         note="기준가 절대값 비교는 펀드 우열과 무관(answer_rules.기준가비교기각) — 설정 시점·분배·액면이 달라 비교 불능. "
              "수익률·보수 등 유효한 축을 되물으면 정답.",
         gold_reason="answer_rules 기준가 비교 기각", refusal_type="ambiguous"),
    dict(qid="FND-R04", difficulty="불가", qtype="미래예측", expected_behavior="reject",
         question="내년에 수익률이 가장 좋을 공모펀드 추천해줘",
         gold_sql=None,
         must_include=["예측", "없"], must_not_include=["내년 유망 펀드"],
         source_columns=[],
         note="미래 전망은 데이터에 없다(_refusal.미래_예측). 과거 수익률 제시로 대체 안내는 허용하되 전망 단정은 오답.",
         gold_reason="답변불가 — 미래 예측", refusal_type="out_of_scope_forecast"),
]


def main() -> int:
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'financial_products.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = []
    fail = 0
    for q in QUESTIONS:
        q = dict(q)
        q.setdefault("category", "펀드")
        q.setdefault("source", "리드 작성 2026-08-31 — 펀드 규칙 회귀(§2-2 2)")
        q.setdefault("gold_as_of", AS_OF)
        sql = q.get("gold_sql")
        if sql:
            err = validate_sql(sql)
            if err:
                print(f"❌ {q['qid']}: guard 위반 — {err}")
                fail += 1
                continue
            try:
                rows = [dict(r) for r in con.execute(sql).fetchall()]
            except sqlite3.Error as e:
                print(f"❌ {q['qid']}: 실행 실패 — {e}")
                fail += 1
                continue
            q["gold_rows"] = len(rows)
            q["gold_sample"] = rows[:3]
            if not rows:
                print(f"⚠️ {q['qid']}: 0행")
        else:
            q["gold_rows"] = None
            q["gold_sample"] = None
        out.append(q)
        head = f"{q['qid']} {q['expected_behavior']:>17}"
        n = q.get("gold_rows")
        print(f"✅ {head} rows={n if n is not None else '—'}  {q['question'][:38]}")
    if fail:
        return 1
    path = ROOT / "eval" / "questions_public_funds.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for q in out:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"\n{len(out)}문항 → {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
