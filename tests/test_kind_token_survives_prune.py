# -*- coding: utf-8 -*-
"""2026-09-06 — 종류 통칭이 IN 목록 정리에 걷혀 뒤 가드의 근거가 사라지던 자리.

'산금채는 몇 종목이야?' → `bd_knd IN ('산금채','특수은행채')`. '산금채' 는 컬럼 값이 아니라
죽은 값으로 보이지만, 걷어내면 남은 `IN ('특수은행채')` 이 정상으로 보여 restore_kind_breadth 가
확정식(특수은행채 AND 한국산업은행)과의 불일치를 못 본다 — 503 이 1,299 로 나갔다.
"""
from src.runtime import guard
from src.runtime.loader import load_context
from src.runtime.pipeline import _kind_filters, restore_kind_breadth

Q = "산금채는 몇 종목이야?"
SQL = ("SELECT COUNT(DISTINCT pd_no) FROM domestic_bonds "
       "WHERE curr_cd = 'KRW' AND mat_dt >= 20260824 "
       "AND bd_knd IN ('산금채', '특수은행채') LIMIT 30")


def test_kind_token_survives_prune_and_breadth_fires():
    ctx = load_context()
    protect = frozenset(tok for tok, _f in _kind_filters()[0] if tok in Q)
    assert "산금채" in protect

    pruned, dead = guard.prune_dead_in_literals(SQL, ctx, protect=protect)
    assert "산금채" in pruned and "산금채" not in dead

    fixed, why = restore_kind_breadth(pruned, Q)
    assert why is not None
    assert "한국산업은행" in fixed

    # 보호가 없으면 신호가 사라져 뒤 가드가 침묵한다 — 이것이 회귀시키면 안 되는 그 실패다.
    bare, _ = guard.prune_dead_in_literals(SQL, ctx)
    assert "산금채" not in bare
    assert restore_kind_breadth(bare, Q)[1] is None


if __name__ == "__main__":
    test_kind_token_survives_prune_and_breadth_fires()
    print("ok")
