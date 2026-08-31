# -*- coding: utf-8 -*-
"""eval/questions_domestic_bonds.jsonl 생성 — gold SQL 은 yaml query_rules 의 조건식을 그대로 쓰고 DB 로 실측해 채운다."""
import sys, os, re, json, sqlite3
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(r"C:\Users\bella\Desktop\대학\공모전\트리플에이치\미래에셋")
sys.path.insert(0, ".")
import yaml
from src.runtime.pipeline import validate_sql, answer_question
from src.runtime.loader import load_context

D = yaml.safe_load(open("ontology/enums/domestic_bonds.yaml", encoding="utf-8"))["query_rules"]
def case_expr(rule, alias):
    m = re.search(r"(CASE WHEN .*? END AS " + alias + ")", D[rule], re.S)
    assert m, rule
    return re.sub(r"\s+", " ", m.group(1))
STRUCT = case_expr("구조표시", "구조")
BACK = case_expr("신용보강", "보강")
BUY = "curr_cd='KRW' AND mat_dt >= 20260822"
SAFE = "pd_risk_gcd <> '11' AND COALESCE(TRIM(crd_grd), '') <> 'C0' AND bd_ofr_tcd <> '사모'"   # 고위험제외 (NULL-안전)
WARN = "'수익률이 높은 채권은 원금을 돌려받지 못할 위험도 높을 수 있습니다'"

Q = []
def add(qid, difficulty, qtype, beh, question, sql, inc, exc, cols, note, reason):
    Q.append(dict(qid=qid, difficulty=difficulty, qtype=qtype, expected_behavior=beh, question=question, gold_sql=sql,
                  must_include=inc, must_not_include=exc, source_columns=cols, note=note, gold_reason=reason))

add("BND-D-001", "하", "조건검색", "answer", "신용등급 AA- 이상 채권 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(crd_grd) AS crd_grd, mat_dt, applied_yield FROM domestic_bonds WHERE {BUY} AND TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-') GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 30",
    ["종목명", "신용등급"], ["국공채는 등급이 낮", "수익률 전망"], ["crd_grd", "mat_dt", "curr_cd"],
    "등급서열: 'AA- 이상' = IN 4종. 무등급 4,020행(국공채 2,840)은 모수 밖 — '등급 미부여' 로 말하고 '낮은 등급' 으로 읽지 않는다. OFFICIAL-001 과 같은 집합(15,806종목).", "규칙 등급서열·구매가능·대표행")
add("BND-D-002", "중", "랭킹(추천)", "answer", "수익률 높은 채권 추천해줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, applied_yield, TRIM(crd_grd) AS crd_grd, pd_risk_nm, bd_ofr_tcd, {STRUCT} FROM domestic_bonds WHERE {BUY} AND {SAFE} AND applied_yield > 0 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 10",
    ["제외했습니다", "위험등급"], ["728", "C0"], ["applied_yield", "pd_risk_gcd", "crd_grd", "bd_ofr_tcd"],
    "고위험제외(NULL-안전 조건식). ❌ NOT(a OR b) 는 국공채 2,840 증발. 1위 9.82%(중진공 유동화 2-3, BBB-, 2등급) → 6% 초과라 주의 문구 필수. 728% 부실채권(C0·1등급)은 추천에서 빠진다.", "규칙 고위험제외·영값배제·구조표시·답변 규칙(주의 문구)")
add("BND-D-003", "하", "조건검색", "answer", "위험이 가장 낮은 등급의 채권 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, pd_risk_nm, TRIM(std_pd_mcls_nm) AS mcls, applied_yield FROM domestic_bonds WHERE {BUY} AND pd_risk_gcd = '16' GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 30",
    ["6등급", "매우낮은위험"], ["1등급", "매우높은위험"], ["pd_risk_gcd", "pd_risk_nm"],
    "위험등급방향: 숫자 클수록 안전 — '가장 안전' = '16'(6등급). '11' 로 짜면 정반대(최위험). 국공채 2,839/2,840 이 '16'.", "규칙 위험등급방향")
add("BND-D-004", "중", "조건검색(만기)", "answer", "2027년에 만기되는 채권 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, mat_dt, remaining_days, TRIM(crd_grd) AS crd_grd, applied_yield FROM domestic_bonds WHERE curr_cd='KRW' AND mat_dt BETWEEN 20270101 AND 20271231 GROUP BY pd_no ORDER BY mat_dt LIMIT 30",
    ["만기", "2027"], ["확인할 수 없", "전망"], ["mat_dt"],
    "B: 연도가 mat_dt 조건에 쓰였으므로 통과(gate.sql_uses_as_maturity). 종전 게이트는 '2027' 만 보고 기각했다. 모수 5,982종목.", "규칙 구매가능 예외 — 만기 조건 질의는 기준일 이후 연도 허용")
add("BND-R-005", "중", "네거티브(시점)", "reject", "2027년 채권 시장 전망 알려줘", None,
    ["2026-08-22", "확인할 수 없"], ["종목명", "2027년에는"], ["mat_dt"],
    "B 사후 검사: HCX SQL 에 2027 이 mat_dt 조건으로 안 쓰이면 시점·전망 질의 → 기준일 안내. HCX 가 만기로 오해석하면 만기 목록이 나갈 수 있음(실측 확인 항목).", "DB 에 미래 시점 값 없음(미래 날짜는 mat_dt 뿐) — pipeline 사후 검사 기각")
add("BND-D-006", "하", "조건검색(발행사)", "answer", "한국전력 채권 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(pd_pbcm) AS pd_pbcm, mat_dt, TRIM(crd_grd) AS crd_grd, applied_yield, {BACK} FROM domestic_bonds WHERE {BUY} AND pd_pbcm LIKE '%한국전력%' GROUP BY pd_no ORDER BY mat_dt LIMIT 30",
    ["한국전력공사", "정부 보증 표기 없음"], ["ETF", "정부가 보증"], ["pd_pbcm", "std_pd_mcls_nm"],
    "E: KG 에 '한국전력' 짧은 라벨 노드가 채권 쪽엔 없다 → 발행사조회 규칙(LIKE). 주식 '한국전력' 노드로 fallback 금지. 보강 층 D(특별법 공공기관) — '정부 보증' 이라 말하지 않는다.", "규칙 발행사조회·신용보강 D")
add("BND-D-007", "하", "조건검색(종류)", "answer", "국고채 중 잔존만기 1년 이내인 것 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, mat_dt, remaining_days, srfc_irt, applied_yield FROM domestic_bonds WHERE {BUY} AND TRIM(std_pd_scls_nm) = '국고채' AND remaining_days BETWEEN 1 AND 365 GROUP BY pd_no ORDER BY remaining_days LIMIT 30",
    ["국고채", "잔존"], ["신용등급이 없어 위험", "AAA"], ["std_pd_scls_nm", "remaining_days"],
    "F: '채권' 글자 없이 '국고채' 만으로 채권 라우팅(소분류 값). 국고채는 신용등급 미부여 — 빈 칸을 위험 신호로 말하지 않는다.", "규칙 대표행·답변 규칙(국공채 등급 미부여)")
add("BND-A-008", "하", "집계", "answer", "통안채 몇 개 있어?",
    "SELECT COUNT(DISTINCT pd_no) AS n, COUNT(*) AS rows_ FROM domestic_bonds WHERE TRIM(bd_knd) = '통화안정채권' LIMIT 1",
    ["종목"], ["확인할 수 없"], ["bd_knd"],
    "F ③ 동의어: 통안채→통화안정채권(yaml synonyms). 데이터 분류는 특수채(한국은행). 집계는 종목 수(DISTINCT pd_no)로.", "규칙 대표행·동의어")
add("BND-D-009", "중", "조건검색(구조)", "answer", "영구채 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, mat_dt, TRIM(crd_grd) AS crd_grd, pd_risk_nm, applied_yield, {STRUCT} FROM domestic_bonds WHERE {BUY} AND (pd_nm LIKE '%신종%' OR pd_nm LIKE '%영구%') GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 30",
    ["콜"], ["만기일에 원금 상환"], ["pd_nm", "mat_dt"],
    "구조표시: 영구채는 mat_dt 가 만기일이 아니라 콜 개시일 — 답변에 '만기일 = 콜 개시일' 명시. 266행 중 콜 265.", "규칙 구조표시·답변 규칙")
add("BND-D-010", "상", "조건검색(구조)", "answer", "코코본드 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(bd_knd) AS bd_knd, pd_risk_nm, TRIM(crd_grd) AS crd_grd, applied_yield, {STRUCT} FROM domestic_bonds WHERE {BUY} AND ({STRUCT.replace(' AS 구조', '')}) = '은행 자본성증권(후순위·조건부자본·영구)' GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 30",
    ["원금 상각", "위험등급"], ["전부 AA급", "안전한"], ["bd_knd", "pd_risk_gcd", "pd_nm"],
    "단어(코코/조건상각/(상)) 가 아니라 컬럼 신호(은행 종류 + 위험등급 1~3)로 판정 = 278행. 코코 '전부 AA급' 아님(A+ 7·무등급 1). 답변에 '원금 상각·이자 미지급 조건 가능'.", "규칙 구조표시(첫 WHEN)·동의어 코코본드→조건부자본")
add("BND-D-011", "중", "랭킹(추천)", "answer", "듀레이션 짧은 채권 추천해줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, dur, remaining_days, applied_yield, TRIM(crd_grd) AS crd_grd FROM domestic_bonds WHERE {BUY} AND {SAFE} AND dur IS NOT NULL AND dur <> 99 AND dur > 0 AND remaining_days > 0 GROUP BY pd_no ORDER BY dur ASC LIMIT 10",
    ["듀레이션", "제외했습니다"], ["99"], ["dur", "remaining_days"],
    "듀레이션정상: 99·0 은 결측 표기. J 결정(08-30 현상 유지): 잔존 1일 종목이 상단에 와도 하한을 두지 않는다 — 답변에 잔존일수를 함께 보여 준다.", "규칙 듀레이션정상·고위험제외")
add("BND-D-012", "중", "랭킹(추천)", "answer", "표면금리 높은 채권 추천해줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, srfc_irt, bd_intp_tcd, bd_inrt_tcd, TRIM(crd_grd) AS crd_grd, pd_risk_nm, applied_yield FROM domestic_bonds WHERE {BUY} AND {SAFE} AND bd_inrt_tcd = '고정금리' AND bd_intp_tcd = '이표채' AND srfc_irt > 0 GROUP BY pd_no ORDER BY srfc_irt DESC LIMIT 10",
    ["표면금리", "고정금리"], ["할인채", "변동금리"], ["srfc_irt", "bd_intp_tcd", "bd_inrt_tcd"],
    "이자유형분리: 표면금리 비교는 고정금리·이표채 안에서만(할인채·변동금리 섞으면 비교 불가). 표면금리 ≠ 수익률.", "규칙 이자유형분리·고위험제외")
add("BND-D-013", "하", "조건검색(ESG)", "answer", "녹색채권 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(pd_pbcm) AS pd_pbcm, mat_dt, TRIM(crd_grd) AS crd_grd, applied_yield FROM domestic_bonds WHERE {BUY} AND (pd_nm LIKE '%(녹)%' OR pd_nm LIKE '%(녹/%' OR pd_nm LIKE '%/녹)%' OR pd_nm LIKE '%/녹/%') GROUP BY pd_no ORDER BY mat_dt LIMIT 30",
    ["녹색채권", "종목명 표기 기준"], ["사모"], ["pd_nm"],
    "규칙 ESG라벨(LIKE 4형): (녹)=녹색 356 · (사)=사회적 1,984 · (지)=지속가능 159. 주최 확인 대기 — '종목명 표기 기준' 병기. (사)를 사모로 읽지 않는다.", "규칙 ESG라벨 · name_encoding.esg_labels")
add("BND-D-014", "상", "조건검색(신용보강)", "answer", "정부가 보증하는 채권 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, TRIM(pd_pbcm) AS pd_pbcm, TRIM(std_pd_mcls_nm) AS mcls, applied_yield, {BACK} FROM domestic_bonds WHERE {BUY} AND ({BACK.replace(' AS 보강', '')}) IN ('A 정부·지자체·한은 직접 발행', 'B 정부보증 명시', 'C 법정 손실보전 기관') GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 30",
    ["정부보증", "손실보전"], ["한국전력공사 정부 보증", "특수채는 모두 정부 보증"], ["std_pd_mcls_nm", "pd_pbcm", "pd_nm"],
    "신용보강 6층: 명시적 (정부보증) 은 7건뿐 — A 직접발행·C 법정 손실보전까지 층을 같이 답한다. D(특별법 공공기관)를 '정부 보증' 이라 말하지 않는다. C 라도 후순위·자본성증권은 '손실보전 대상 아님'.", "규칙 신용보강 A·B·C")
add("BND-A-015", "하", "집계", "answer", "채권 종류별로 몇 개씩 있어?",
    "SELECT TRIM(bd_knd) AS bd_knd, COUNT(DISTINCT pd_no) AS n FROM domestic_bonds WHERE TRIM(bd_knd) <> '' GROUP BY TRIM(bd_knd) ORDER BY n DESC LIMIT 30",
    ["종류", "개"], ["확인할 수 없"], ["bd_knd"],
    "bd_knd 32종. 종목 수(DISTINCT pd_no)로 센다 — 행 수로 세면 장내/장외 중복. LIMIT 30 이라 하위 2종은 잘린다(답변에 '상위 30종' 명시).", "규칙 대표행")
add("BND-C-016", "중", "역질문", "clarify", "등급 낮은 채권 알려줘", None,
    ["신용등급", "위험등급"], ["종목명"], ["crd_grd", "pd_risk_nm"],
    "clarify.다의어.등급: 신용등급/위험등급 별개 축 + 위험등급은 숫자 낮을수록 위험 — 단서 없이 하나 찍으면 정반대 답. HCX 가 'CLARIFY:' 로 되물어야 한다(실측 확인 항목).", "yaml clarify 다의어 '등급' — SQL 대신 되묻기")
add("BND-C-017", "중", "역질문", "clarify", "싼 채권 알려줘", None,
    ["가격", "수익률"], ["종목명"], ["eval_price", "applied_yield"],
    "clarify.다의어.싸다: 가격 낮음 / 수익률 높음 — 정반대라 기본값 금지, 반드시 되묻기.", "yaml clarify 다의어 '싸다' — SQL 대신 되묻기")
add("BND-U-018", "하", "네거티브(데이터 없음)", "unanswerable", "신용등급 BB+ 채권 알려줘", None,
    ["해당 등급의 채권이 없습니다", "BB+"], ["존재하지 않는 등급", "AAA"], ["crd_grd"],
    "B: BB+ 는 표준 등급표에 있으나 2차 데이터 0건 → '존재하지 않는 등급' 이 아니라 '데이터에 없음'. 게이트가 HCX 없이 즉답.", "표준표 credit_grade_scale.csv 에 있음 · value_semantics 에 없음 — gate no_data")
add("BND-D-019", "중", "조건검색(구조)", "answer", "전환사채(CB) 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, mat_dt, TRIM(crd_grd) AS crd_grd, pd_risk_nm, applied_yield, {STRUCT} FROM domestic_bonds WHERE {BUY} AND ({STRUCT.replace(' AS 구조', '')}) = '전환사채' GROUP BY pd_no ORDER BY mat_dt LIMIT 30",
    ["전환사채"], ["존재하지 않는 신용등급"], ["pd_nm"],
    "B: 'CB' 는 등급 모양이 아니라 게이트가 무시한다(종전엔 '없는 등급' 으로 기각). 구조표시 CASE 의 '전환사채' 열로 판정.", "규칙 구조표시")
add("BND-D-020", "중", "랭킹(추천)", "answer", "퇴직연금에 담을 수 있는 채권 중 수익률 높은 것 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, applied_yield, TRIM(crd_grd) AS crd_grd, pd_risk_nm, TRIM(std_pd_mcls_nm) AS mcls FROM domestic_bonds WHERE {BUY} AND {SAFE} AND pd_pen_tr_yn = 'Y' AND applied_yield > 0 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 10",
    ["퇴직연금"], ["A- 이상만"], ["pd_pen_tr_yn", "applied_yield"],
    "퇴직연금 편입 가능 = pd_pen_tr_yn='Y'. 'A- 이상만 가능' 이 아니다(BBB+ 15종목 존재 — 08-30 정정).", "규칙 고위험제외 + 컬럼 pd_pen_tr_yn")
add("BND-F-021", "중", "사실확인", "answer", "수익률이 가장 높은 채권은 뭐야?",
    "SELECT pd_no, TRIM(pd_nm) AS pd_nm, applied_yield, TRIM(crd_grd) AS crd_grd, pd_risk_nm, eval_price, bd_ofr_tcd FROM domestic_bonds WHERE curr_cd='KRW' AND mat_dt >= 20260822 AND applied_yield > 0 GROUP BY pd_no ORDER BY applied_yield DESC LIMIT 5",
    ["728", "C0", "원금"], ["추천"], ["applied_yield", "crd_grd", "pd_risk_gcd"],
    "조회·사실확인은 고위험제외 안 함 — 728.5% 는 사실. 단 신용등급(C0)·위험등급(1등급)과 주의 문구를 함께. 평가가 액면의 27~45% = 원금 손실 위험이 가격에 반영된 것.", "규칙 고위험제외(조회 예외)·답변 규칙(주의 문구)")
add("BND-D-022", "중", "랭킹(판매)", "answer", "지금 살 수 있는 채권 중 세후수익률 높은 것 알려줘",
    f"SELECT pd_no, TRIM(pd_nm) AS pd_nm, buy_yield, after_tax_yield, trade_price, TRIM(crd_grd) AS crd_grd, pd_risk_nm, remaining_days FROM domestic_bonds WHERE buy_yield IS NOT NULL AND {SAFE} ORDER BY after_tax_yield DESC LIMIT 10",
    ["세후", "판매"], ["시장 전체"], ["buy_yield", "after_tax_yield"],
    "판매행: 당사 판매 조건이 있는 634 LOT(buy_yield 있음) 안에서. 세후 = 개인 15.4% 기본(과세수익률금지·clarify 수익률 참조). 판매 LOT 은 pd_no 가 여러 행일 수 있어 대표행 GROUP BY 를 쓰지 않는다.", "규칙 판매행·고위험제외")
add("BND-R-023", "하", "네거티브(속성 부재)", "reject", "기초지수를 추종하는 채권 알려줘", None,
    ["제공되지"], ["종목명"], [],
    "absent 게이트: 채권 클래스에 tracksIndex 속성 없음 — HCX 0회.", "shared/index.yaml absent_in domestic_bonds")
add("BND-D-024", "하", "조건검색(등급 없음)", "answer", "신용등급이 없는 채권은 어떤 거야?",
    "SELECT TRIM(std_pd_mcls_nm) AS mcls, COUNT(DISTINCT pd_no) AS n FROM domestic_bonds WHERE COALESCE(TRIM(crd_grd), '') = '' GROUP BY TRIM(std_pd_mcls_nm) ORDER BY n DESC LIMIT 10",
    ["국공채", "미부여"], ["신뢰도가 낮", "위험한"], ["crd_grd", "std_pd_mcls_nm"],
    "무등급 4,020행 = 국공채 2,840(전부) + 특수채 254 + 회사채 926. '등급이 없다 = 위험하다' 가 아니다 — 국공채는 등급 미부여가 정상.", "규칙 등급서열(무등급) · 답변 규칙")

# ── 실측 ──
con = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
ctx = load_context()
out = []
for q in Q:
    q["gold_as_of"] = "2026-08-22"
    if q["gold_sql"]:
        err = validate_sql(q["gold_sql"]); assert not err, (q["qid"], err)
        cur = con.execute(q["gold_sql"]); cols = [c[0] for c in cur.description]; rows = cur.fetchall()
        q["gold_rows"] = len(rows)
        q["gold_sample"] = [dict(zip(cols, r)) for r in rows[:3]]
        vn = f"gold SQL DB 실행 재현 — {len(rows)}행 · 규칙 조건식 그대로"
        assert rows, q["qid"]
    else:
        q["gold_rows"] = None; q["gold_sample"] = []
        r = answer_question(q["qid"], q["question"], ctx=ctx)
        if q["expected_behavior"] in ("reject", "unanswerable"):
            if q["qid"] == "BND-R-005":
                vn = "사후 검사 경로 — planner 없이는 '[Decision] 기준일 이후 시점' 으로 종료 확인. HCX 실측 대기"
                assert "2026-08-22" in r.answer, r.think_trace
            else:
                assert "[Gate] 기각" in r.think_trace, (q["qid"], r.think_trace)
                for m in q["must_include"]:
                    assert m in r.answer or m in r.think_trace, (q["qid"], m, r.answer)
                vn = f"pipeline 오프라인 재현 — [Gate] 기각 · 답변 \"{r.answer[:60]}\""
        else:  # clarify — 안내판에 되묻기 규칙이 실리는지까지만 오프라인 확인
            g = ctx.clarify_context(["domestic_bonds"])
            key = "등급" if "등급" in q["question"] else "싸다"
            assert key in g
            vn = f"오프라인: 안내판 '# 되묻기 규칙' 에 '{key}' 실림 확인. HCX 가 CLARIFY: 를 내는지는 실측 대기"
    q["gold_verified"] = True; q["verified_by"] = "seohyun"; q["verified_at"] = "2026-08-30"; q["verify_note"] = vn
    out.append(q)
    print(f"{q['qid']:<11} {q['expected_behavior']:<12} rows={q['gold_rows']!s:<5} {q['question']}")

with open("eval/questions_domestic_bonds.jsonl", "w", encoding="utf-8") as f:
    for q in out:
        f.write(json.dumps(q, ensure_ascii=False) + "\n")
print("written", len(out))
