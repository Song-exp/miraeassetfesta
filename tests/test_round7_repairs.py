# -*- coding: utf-8 -*-
"""7R 수리 회귀 — 재검 §③(M′·R′·S′·P′·B-4′) + KG §③(G1~G7). 간섭 지도: docs/recheck_2026-09-02_round7_plan.md

SQL 은 전부 6R 실측 원문(eval/probe_recheck_2026-09-02_r6*.json)이다 — 문항별 예외가 아니라
"HCX 가 그 모양을 냈을 때 결정층이 무엇을 하는가" 를 고정한다.
"""
import re

import pytest

from src.runtime.loader import db_path, load_context

pytestmark = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return load_context()


# ── 뿌리③+④ — 답변 표면 규약 (S′ 뒤 · G4 · B-4′ · B-5) ──

def test_answer_surface_rules(ctx):
    from src.runtime import pipeline as P

    # ① B-4′ — 대체 표시 열이 없으면 원 단위 금액을 숨기지 않는다 (6R Y16: overseas_etfs 는 억원 병기 대상 밖)
    y16_sql = ("SELECT TRIM(cu_fund_mgmt_co) AS 운용사, SUM(du_last_aum) AS 총순자산USD FROM overseas_etfs "
               "WHERE pd_grp_no = 'ETF' AND pd_sale_yn = 1 GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    rows = "운용사 | 총순자산USD\nBlackRock Fund Advisors | 4378085220000.0"
    kept, hidden = P._hide_answer_columns(rows, y16_sql)
    assert not hidden and "4378085220000" in kept, "대체 열이 없는데 값을 숨겼다"

    # ② 억원 열이 있으면 종전대로 원값만 숨긴다 (V7·W10 불변)
    v7_sql = ("SELECT cu_fund_mgmt_co, SUM(du_last_aum) AS total_aum, "
              "CAST(SUM(du_last_aum)/100000000 AS INTEGER) || '억원' AS \"total_aum_억원\" FROM domestic_etfs GROUP BY 1")
    kept2, hidden2 = P._hide_answer_columns("cu_fund_mgmt_co | total_aum | total_aum_억원\n삼성 | 164377105967341 | 1643771억원", v7_sql)
    assert hidden2 == ["total_aum"] and "1643771억원" in kept2

    # ③ 내부 태그 코드는 대체 열과 무관하게 종전대로 숨긴다 (R3 불변)
    _, hidden3 = P._hide_answer_columns("itm_nm | prfd_attr_cds\n펀드 | C101,M109", "SELECT itm_nm, prfd_attr_cds FROM public_funds")
    assert hidden3 == ["prfd_attr_cds"]

    # ④ G4 — 코드 컬럼은 **별칭과 무관하게** 원 컬럼으로 판정하고 이름·기계 표기로 굽는다 (KG-008 날조 차단)
    kg8_sql = ("SELECT trim(trusc_xtn_itt_cd) as 수탁회사명, COUNT(*) as 펀드수 FROM public_funds GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    out, labeled = P.label_code_columns("수탁회사명 | 펀드수\n00050004 | 257\n00020004 | 1656", kg8_sql)
    assert labeled == ["수탁회사명"], labeled
    for ln in out.splitlines()[1:]:
        v = ln.split(" | ")[0]
        assert re.fullmatch(r"(?:코드 \d+\(기관명 미수록\)|.+\(\d+\))", v), v

    # ⑤ G4 — 값이 있는 코드를 숨겨 '부재' 로 서술하게 두지 않는다 (Z23: trusc 코드 00020088 → '수록 안 됨')
    z23_sql = ("SELECT MIN(itm_no) AS 대표_itm_no, MAX(trusc_xtn_itt_cd) AS trusc_xtn_itt_cd FROM public_funds GROUP BY 1")
    out5, labeled5 = P.label_code_columns("대표_itm_no | trusc_xtn_itt_cd\nKR5153450780 | 00020088", z23_sql)
    # 수탁 코드도 kg_alias 에 실재한다(00020088 → 신한은행) — 매핑이 있으면 정본 이름, 없으면 '코드 X(기관명 미수록)'
    assert labeled5 == ["trusc_xtn_itt_cd"] and "00020088" in out5
    assert re.search(r"\S+\(00020088\)|코드 00020088\(기관명 미수록\)", out5), out5

    # ⑥ 이름 컬럼·종목번호는 건드리지 않는다 (과잉 개입 방지)
    _, none = P.label_code_columns("itm_nm | 클래스수\n미래에셋코어테크 | 10", "SELECT itm_nm, COUNT(*) AS 클래스수 FROM public_funds GROUP BY 1")
    assert none == []

    # ⑦ B-5 — 부사가 낀 면책("금융 기관에 **직접** 문의")과 투자권유형 문장을 걷어낸다 (Z21·Z23·Y16)
    z21 = ("죄송합니다. 제공된 데이터에는 정보가 포함되어 있지 않습니다. 해당 정보를 찾기 위해서는 금융 기관에 "
           "직접 문의하시거나, 공식 웹사이트를 참고하시는 것을 추천드립니다.")
    out7, hit7 = P.strip_disclaimer(z21)
    assert hit7 and "문의" not in out7, out7
    y16 = "이들은 대형 자산운용사입니다. 따라서 투자자들은 이러한 운용사의 ETF들을 긍정적으로 검토해볼 수 있을 것입니다."
    out8, hit8 = P.strip_disclaimer(y16)
    assert hit8 and "긍정적으로 검토" not in out8, out8
    # 정상 문장은 살아남는다
    assert P.strip_disclaimer("순자산 상위 3개 운용사입니다.")[1] is False


def test_zero_row_reason_never_leaks_sql(ctx):
    """S′ 뒤 — 0행 문구에 SQL 절 원문(`itm_no IN (…)`·`REPLACE(`·`LIKE '%`)이 절대 실리지 않는다 (6R W11)."""
    from src.runtime.pipeline import _zero_row_reason

    for sql in (
        "SELECT itm_no FROM public_funds WHERE itm_no IN ('030230002D36') AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30",
        "SELECT itm_no FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%존재하지않는펀드명%' AND sale_yn = '판매중' LIMIT 30",
    ):
        txt = _zero_row_reason(sql)
        assert txt
        for tok in ("itm_no", "REPLACE(", "LIKE '%", "IN (", "sale_yn", "SELECT"):
            assert tok not in txt, (tok, txt)
