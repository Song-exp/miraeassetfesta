# -*- coding: utf-8 -*-
"""평가셋 gold_sql 검증 — 모든 jsonl 을 읽어 (1) validate_sql 통과 (2) 읽기 전용 DB 실행 성공 (3) 행수 = gold_rows 확인.
사용: python eval/run_gold_check.py   (실패 시 exit 1)
"""
import glob, json, os, sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.runtime.pipeline import validate_sql  # noqa: E402


def _first_row_matches(gold_row: dict, actual: tuple) -> bool:
    """gold_sample[0] 의 각 값이 실제 1행 어딘가에 있으면 통과 — 컬럼 순서·별칭 차이는 무시한다."""
    actual_vals = list(actual)

    def has(g):
        for a in actual_vals:
            if g is None and a is None:
                return True
            try:
                if abs(float(g) - float(a)) < 1e-6:
                    return True
            except (TypeError, ValueError):
                pass
            if str(g).strip() == str(a).strip():
                return True
        return False

    return all(has(g) for g in gold_row.values())


def main():
    con = sqlite3.connect(f"file:{os.path.join(ROOT,'data','financial_products.db')}?mode=ro", uri=True)
    n = ok = with_sql = fail = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "eval", "questions_*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            q = json.loads(line); n += 1
            sql = q.get("gold_sql")
            if not sql:
                if q.get("gold_reason"):
                    ok += 1
                else:
                    fail += 1; print(f"❌ {q['qid']}: gold_sql 도 gold_reason 도 없음")
                continue
            with_sql += 1
            err = validate_sql(sql)
            if err:
                fail += 1; print(f"❌ {q['qid']}: guard 위반 — {err}"); continue
            try:
                rows = con.execute(sql).fetchall()
            except sqlite3.Error as e:
                fail += 1; print(f"❌ {q['qid']}: 실행 실패 — {e}"); continue
            if len(rows) != q.get("gold_rows"):
                fail += 1; print(f"❌ {q['qid']}: 행수 불일치 gold_rows={q.get('gold_rows')} 실제={len(rows)}"); continue
            # 🆕 2026-09-01 — 1위 행 내용 대조. 행수만 보면 ORDER BY 가 바뀌어 Top-N 내용이
            #    통째로 달라져도 통과한다(자체 점검 §3). gold_sample[0] 의 값이 실제 1행에
            #    전부 있어야 한다(숫자는 오차 허용·문자열은 trim 비교 — 컬럼 순서 무관).
            sample = q.get("gold_sample") or []
            if rows and sample and isinstance(sample[0], dict):
                if not _first_row_matches(sample[0], rows[0]):
                    fail += 1
                    print(f"❌ {q['qid']}: 1위 행 불일치 — gold={list(sample[0].values())[:3]}… 실제={list(rows[0])[:3]}…")
                    continue
            if len(rows) == 0 and q.get("expected_behavior") in ("answer",):
                print(f"⚠️ {q['qid']}: expected answer 인데 0행")
            ok += 1
    print(f"문항 {n} · gold_sql {with_sql} · 통과 {ok} · 실패 {fail}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
