# -*- coding: utf-8 -*-
"""ETF·채권 오답 재생 세트 — 펀드 결정층 기법 이식 실험 (2026-09-06).

서버를 부르지 않는다. 오답 기록에 남은 HCX 원문 모양을 가짜 플래너로 넣고, 가드 체인을 지난 SQL·행·답변을
검사한다. 케이스마다 검사 여러 개 — 하나라도 FAIL 이면 그 케이스는 미해결.

    DB_PATH=<db> python eval/exp_port_guards.py            # 전체
    DB_PATH=<db> python eval/exp_port_guards.py B84 E25    # 접두 필터
"""
import re
import sys

from src.runtime.loader import connect_readonly, load_context
from src.runtime.pipeline import answer_question

I = re.I


def _order_by(sql):
    m = re.search(r"\border\s+by\s+(.*?)(?:\s+limit\b|$)", sql, I | re.S)
    return m.group(1) if m else ""


def no_ordinal(r, rows):
    return not re.search(r"\border\s+by\s+\d|,\s*\d+\s*(?:asc|desc)?\s*(?:,|$|\s+limit)", r.sql, I)


CASES = [
    # ── 채권 #84 하이일드 — 서수 ORDER BY 가 대표행·2차키·근거컬럼·머리줄 가드 넷을 우회 (P1) ──
    dict(qid="B84-ord3", question="하이일드 채권 수익률 높은 순으로 5개 알려줘",
         raw="SELECT TRIM(pd_nm), crd_grd, applied_yield FROM domestic_bonds WHERE curr_cd = 'KRW' "
             "AND mat_dt >= 20260824 GROUP BY pd_no ORDER BY 3 DESC LIMIT 5",
         checks={"서수 없음": no_ordinal,
                 "정렬축 이름": lambda r, rows: "applied_yield" in _order_by(r.sql),
                 "투기등급 필터(P2·yaml 슬롯, 리드 결정 대기)": lambda r, rows: re.search(
                     r"\bwhere\b.*?crd_grd[^,]*?IN\s*\([^)]*'BB", r.sql.split("ORDER BY")[0], I | re.S) is not None}),
    dict(qid="B84-ord31", question="하이일드 채권 수익률 높은 순으로 5개 알려줘",
         raw="SELECT TRIM(pd_nm), crd_grd, applied_yield FROM domestic_bonds WHERE curr_cd = 'KRW' "
             "AND mat_dt >= 20260824 GROUP BY pd_no ORDER BY 3 DESC, 1 LIMIT 5",
         checks={"서수 없음": no_ordinal,
                 "정렬축 이름": lambda r, rows: "applied_yield" in _order_by(r.sql)}),
    dict(qid="B59-ord2", question="A등급 이상 회사채 중 표면금리 높은 순으로 5개 알려줘",
         raw="SELECT TRIM(pd_nm), srfc_irt FROM domestic_bonds WHERE crd_grd IN ('A0','A+','A-','AA-','AA0','AA+','AAA') "
             "AND mat_dt >= 20260824 GROUP BY pd_no ORDER BY 2 DESC LIMIT 5",
         checks={"서수 없음": no_ordinal,
                 "정렬축 이름": lambda r, rows: "srfc_irt" in _order_by(r.sql),
                 "동률 2차키": lambda r, rows: "," in _order_by(r.sql)}),
    # ── ETF #25 부정조건 — '빼고' 가 SQL 에 없어 인버스가 답에 그대로 (규칙만 있고 코드 없음) ──
    dict(qid="E25-list", question="레버리지 ETF 중에서 인버스는 빼고 알려줘",
         raw="SELECT pd_abrv_nm, cu_lev_fector FROM domestic_etfs WHERE cu_lev_fector > 1 LIMIT 30",
         checks={"부정조건 SQL": lambda r, rows: re.search(r"NOT\s+LIKE\s+'%인버스%'|NOT\s*\(", r.sql, I) is not None,
                 "행에 인버스 없음": lambda r, rows: rows is not None and all("인버스" not in str(x[0]) for x in rows)}),
    dict(qid="E25-count", question="레버리지 ETF 중에서 인버스는 빼고 몇 개야?",
         raw="SELECT COUNT(*) FROM domestic_etfs WHERE cu_lev_fector > 1 LIMIT 30",
         checks={"정답 62": lambda r, rows: rows == [(62,)]}),
    # ── ETF #5 환각 — 배수 조건이 SQL 에 없는데 '3배' 라 단정 ──
    dict(qid="E5-3x", question="미국 3배 레버리지 ETF 뭐 있어?",
         raw="SELECT pd_nm, pd_abrv_nm FROM overseas_etfs WHERE wu_inv_rgn = 'United States of America' LIMIT 30",
         checks={"배수 조건": lambda r, rows: re.search(r"cu_lev_fector\)?\s*(?:=|IN)\s*\(?\s*-?3", r.sql, I) is not None
                                              or re.search(r"ABS\(\s*cu_lev_fector\s*\)\s*=\s*3", r.sql, I) is not None}),
    # ── ETF #7 조건누락 — 추적오차 0 은 미입력인데 1위로 나옴 ──
    dict(qid="E7-te", question="추적오차 작은 ETF 알려줘",
         raw="SELECT pd_abrv_nm, du_chas_errt FROM domestic_etfs WHERE pd_grp_no = 'ETF' ORDER BY du_chas_errt ASC LIMIT 30",
         checks={"0 제외": lambda r, rows: re.search(r"du_chas_errt\s*>\s*0", r.sql, I) is not None,
                 "1위 양수": lambda r, rows: bool(rows) and rows[0][1] is not None and rows[0][1] > 0}),
    # ── ETF #12·#14 모수 미고지 (기계 고지 있는지) ──
    dict(qid="E12-scope", question="국내 상장 ETF 총 몇 개야?",
         raw="SELECT COUNT(*) FROM domestic_etfs WHERE pd_sale_yn = 1 LIMIT 30",
         checks={"모수 고지": lambda r, rows: "기준" in (r.answer or "").split("\n", 1)[0]}),
    # ── ETF #13 축뒤집기 — 괴리율 부호의 뜻 미고지 (조립 층) ──
    dict(qid="E13-sign", question="괴리율 가장 큰 ETF는?",
         raw="SELECT pd_abrv_nm, du_diff_rt FROM domestic_etfs WHERE pd_grp_no = 'ETF' ORDER BY ABS(du_diff_rt) DESC LIMIT 1",
         checks={"부호 뜻 고지": lambda r, rows: re.search(r"고평가|저평가", r.answer or "") is not None}),
]


class _P:
    def __init__(self, raw):
        self.raw = raw

    def plan_sql(self, q, g):
        return self.raw

    def compose_answer(self, q, rows, answer_rules=""):
        return "HCX-CALLED"


def run(prefixes=()):
    ctx = load_context()
    con = connect_readonly()
    fails = 0
    for c in CASES:
        if prefixes and not any(c["qid"].startswith(p) for p in prefixes):
            continue
        r = answer_question(c["qid"], c["question"], planner=_P(c["raw"]), ctx=ctx)
        rows = None
        try:
            rows = con.execute(r.sql).fetchall() if r.sql and r.sql.lstrip().upper().startswith("SELECT") else None
        except Exception as e:  # noqa: BLE001
            rows = None
        verdicts = {}
        for name, fn in c["checks"].items():
            try:
                verdicts[name] = bool(fn(r, rows))
            except Exception:  # noqa: BLE001
                verdicts[name] = False
        ok = all(verdicts.values())
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'} {c['qid']:10} " + " · ".join(f"{'✅' if v else '❌'}{k}" for k, v in verdicts.items()))
        if not ok:
            print(f"      SQL: {r.sql[:300]}")
            print(f"      ANS: {(r.answer or '')[:160]!r}")
    print(f"\n{len(CASES) - fails if not prefixes else '-'} pass / {fails} fail")
    return fails


if __name__ == "__main__":
    sys.exit(1 if run(tuple(sys.argv[1:])) else 0)
