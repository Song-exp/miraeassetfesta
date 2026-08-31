# -*- coding: utf-8 -*-
"""약한 고리 스트레스 — 예상 질문 107개를 Route→Ground→Gate→안내판 까지 통과시켜 기대와 다른 것만 ❌ 표시 (HCX 0회, 비용 0).

2026-08-30 밤: 처음 11건 불일치 → 라우터(수식어 공집합·접속사·'형'·2자 동의어)·게이트(시점 표기·내년·등급 꼬리)·채권 단독 교차 금지 수정 후 2건
(둘 다 의도: '국고 채' 띄어쓰기 오타 · 'A++' 는 등급 아님). 새 질문은 CASES 에 (질문, 기대 상품군, 기대 게이트, 메모) 로 추가.
실행: python scripts/stress_route_gate.py"""
import sys, os, re
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(r"C:\Users\bella\Desktop\대학\공모전\트리플에이치\미래에셋"); sys.path.insert(0, ".")
from src.runtime.loader import load_context
from src.runtime.pipeline import answer_question, build_grounding, _ground
from src.runtime.router import route
from src.runtime import gate
ctx = load_context()
B, DE, OE, PF = "domestic_bonds", "domestic_etfs", "overseas_etfs", "public_funds"
short = {B: "채권", DE: "국내ETF", OE: "해외ETF", PF: "펀드"}

# (질문, 기대 상품군 집합 or None(미특정 허용), 기대 게이트 'pass'/'reject'/'nodata', 메모)
CASES = [
 # ── A. 라우팅: '채권' 글자 없는 통칭·변종 ──
 ("국채 알려줘", {B}, "pass", "국채 — 소분류 값?"),
 ("공사채 알려줘", {B}, "pass", "공사채"),
 ("회사채 수익률 높은 순", {B}, "pass", ""),
 ("특수채 뭐 있어?", {B}, "pass", ""),
 ("물가연동국채 알려줘", {B}, "pass", "물가채"),
 ("국민주택채권 알려줘", {B}, "pass", "bd_knd 값?"),
 ("도시철도채권 알려줘", {B}, "pass", ""),
 ("신종자본증권 알려줘", {B}, "pass", "영구채 다른 이름"),
 ("후순위채 알려줘", {B}, "pass", ""),
 ("전단채 알려줘", None, "pass", "데이터 없음 → 미특정 허용"),
 ("국고 채 알려줘", {B}, "pass", "띄어쓰기"),
 ("KTB 알려줘", None, "pass", "영문 약어"),
 ("해외 채권 알려줘", {B}, "pass", "외화채없음 규칙이 답해야 → 채권으로"),
 ("달러 채권 있어?", {B}, "pass", "curr_cd USD?"),
 ("채권형 펀드 추천", {PF}, "pass", ""),
 ("채권형 상품 추천해줘", None, "pass", "채권형 = 펀드/ETF 모두 가능"),
 ("채권 ETN 알려줘", {DE, OE}, "pass", ""),
 ("채권이랑 펀드 중 뭐가 나아?", {B, PF}, "pass", "접속사 이랑"),
 ("채권 또는 ETF", {B, DE, OE}, "pass", "접속사 또는 — 목록에 없음"),
 ("펀드 말고 채권으로 추천", {B}, "pass", "'말고' — 마지막 명사 채권"),
 ("채권보다 ETF 가 나아?", {DE, OE}, "pass", "'보다' 비교"),
 ("리츠 알려줘", None, "pass", "리츠 — 데이터 밖"),
 ("ELS 있어?", None, "pass", "ELS 는 상품군 밖 → 미특정"),
 ("한국투자증권 채권 있어?", {B}, "pass", "회사명 안에 '증권'"),
 ("채권자 보호 조항 있는 채권", {B}, "pass", "'채권자' 안의 채권"),
 ("삼성 채권", {B}, "pass", "짧은 발행사"),
 # ── B. 매핑: 발행사 표기 ──
 ("한국전력공사 채권 알려줘", {B}, "pass", "정확 매핑"),
 ("한전 채권 알려줘", {B}, "pass", "동의어 한전"),
 ("LH 채권 알려줘", {B}, "pass", ""),
 ("주택금융공사 채권", {B}, "pass", ""),
 ("KB국민은행 채권", {B}, "pass", "은행명 변종"),
 ("신한은행 채권 수익률", {B}, "pass", ""),
 ("현대차 채권 알려줘", {B}, "pass", "현대자동차"),
 ("SK하이닉스 채권", {B}, "pass", ""),
 ("삼성전자 채권 있어?", {B}, "pass", "삼성전자 채권 0건 — 주식 노드 금지"),
 ("미래에셋 채권 알려줘", {B}, "pass", "미래에셋증권 발행?"),
 ("포스코 채권", {B}, "pass", ""),
 ("한국은행 통안채", {B}, "pass", ""),
 ("한국도로공사 채권", {B}, "pass", ""),
 ("기업은행 채권", {B}, "pass", "(주)중소기업은행"),
 # ── C. 문지기: 등급 토큰 ──
 ("A등급 채권 알려줘", {B}, "pass", "A = A0"),
 ("AA등급 채권", {B}, "pass", ""),
 ("BBB 이상 채권", {B}, "pass", ""),
 ("AA+ 이상 채권", {B}, "pass", ""),
 ("C등급 채권", {B}, "pass", "C = C0 있음"),
 ("D등급 채권 있어?", {B}, "nodata", "D 표준 있음·데이터 0"),
 ("B등급 채권", {B}, "nodata", "B0 데이터 0 — 'B' 는?"),
 ("CC 등급 채권", {B}, "nodata", ""),
 ("AA0 채권", {B}, "pass", "DB 표기"),
 ("투자등급 채권 알려줘", {B}, "pass", "closure 확장"),
 ("투기등급 채권", {B}, "pass", ""),
 ("ABS 채권 알려줘", {B}, "pass", "ABS 는 등급 모양 아님"),
 ("ABCP 있어?", None, "pass", ""),
 ("CP 금리 알려줘", None, "pass", "CP"),
 ("CD금리 연동 채권", {B}, "pass", "CD"),
 ("BW 알려줘", None, "pass", "신주인수권부"),
 ("EB 있어?", None, "pass", "교환사채"),
 ("IRP 에 담을 채권", {B}, "pass", "IRP"),
 ("DB형 퇴직연금 채권", {B}, "pass", "DB"),
 ("AAAA 채권", {B}, "reject", ""),
 ("AAA+ 채권", {B}, "reject", "표준표 없음"),
 ("A++ 채권", {B}, "reject", "모양: A++ — 토큰 정규식이 잡나?"),
 ("신용등급 상위 채권", {B}, "pass", ""),
 ("위험등급 7등급 채권", {B}, "reject", ""),
 ("위험등급 0등급 채권", {B}, "pass", "0 허용"),
 ("6등급 채권", {B}, "pass", ""),
 ("1등급 채권 알려줘", {B}, "pass", "1등급 = 최위험 — 안내판에 방향 규칙"),
 # ── D. 시점 ──
 ("2026년 12월 만기 채권", {B}, "pass", "월 토큰"),
 ("2030년까지 보유할 채권", {B}, "pass", ""),
 ("내년 만기 채권", {B}, "pass", "'내년' — 토큰 없음 → HCX 가 2027 로 써야"),
 ("2027년 발행 예정 채권", {B}, "pass", "사후검사에서 기각돼야"),
 ("2027년 1월 1일 이후 만기", {B}, "pass", ""),
 ("27년 만기 채권", {B}, "pass", "두 자리 연도"),
 ("만기 2030-12-31", {B}, "pass", "ISO 표기 — 토큰 안 잡힘"),
 ("2025년에 발행된 채권", {B}, "pass", "과거 연도"),
 ("2026년 8월 이후 만기", {B}, "pass", "8월 허용"),
 ("2026년 9월 만기", {B}, "pass", "9월 토큰"),
 # ── E. 되묻기·다의어 ──
 ("등급 높은 채권", {B}, "pass", "clarify 등급"),
 ("수익률 좋은 채권", {B}, "pass", "수익률 다의어(기본값 있음)"),
 ("가격 낮은 채권", {B}, "pass", "가격 다의어"),
 ("위험한 채권", {B}, "pass", "위험 다의어"),
 ("만기 짧은 채권", {B}, "pass", "만기 다의어"),
 ("안전한 채권 추천", {B}, "pass", "안전의_정의"),
 ("안전하고 수익률 7% 이상인 채권 추천해줘", {B}, "pass", "08-29 오류 건"),
 # ── F. 속성 부재·범위 밖 ──
 ("채권 총보수 알려줘", {B}, "pass", "총보수는 ETF 속성 — absent 없음?"),
 ("채권 기초지수", {B}, "reject", "absent"),
 ("채권 순자산 큰 순", {B}, "pass", "순자산 없음"),
 ("채권 배당 많은 것", {B}, "pass", ""),
 ("채권 가격 전망", {B}, "pass", "전망 — 시점 토큰 없음"),
 ("채권 투자지역 미국", {B}, "reject", "absent Region?"),
 ("채권 자산군", {B}, "reject", "absent AssetClass?"),
 # ── G. 숫자·단위 ──
 ("수익률 5% 이상 채권", {B}, "pass", ""),
 ("표면금리 3퍼센트 넘는 채권", {B}, "pass", ""),
 ("잔존만기 6개월 이내", {B}, "pass", ""),
 ("만기 3년 이내 채권", {B}, "pass", ""),
 ("1억 투자 가능한 채권", {B}, "pass", ""),
 ("최소 투자금액 낮은 채권", {B}, "pass", ""),
 # ── H. 교차·기타 ──
 ("삼성전자를 보유한 채권", {B}, "pass", "채권엔 구성종목 없음"),
 ("채권 ETF 와 채권 직접투자 비교", {B, DE, OE}, "pass", "접속사 와"),
 ("녹색채권 ETF", {DE, OE}, "pass", "ESG 라벨 + ETF"),
 ("사회적채권 알려줘", {B}, "pass", "(사) 라벨 — 동의어 없음"),
 ("사모 채권 알려줘", {B}, "pass", ""),
 ("공모 채권만", {B}, "pass", ""),
 ("장내 채권 종가", {B}, "pass", ""),
 ("변동금리 채권", {B}, "pass", ""),
 ("할인채 알려줘", {B}, "pass", "bd_intp_tcd 값"),
 ("이표채 중 이자 자주 주는 것", {B}, "pass", ""),
]

rows = []
for q, exp_t, exp_g, memo in CASES:
    r = route(q, ctx)
    tables = r.tables if r.decided else []
    cross = gate.is_cross_query(q, tables, r.groups)
    hits, lines = _ground(q, ctx, tables, cross)
    g = gate.check(q, ctx, tables)
    fut = gate.future_tokens(q)
    got_t = set(tables)
    t_ok = (exp_t is None) or (got_t == exp_t) or (exp_t and got_t and got_t <= exp_t and len(exp_t) > 1)
    if g.rejected:
        gs = "nodata" if "0건" in g.reason else "reject"
    else:
        gs = "pass"
    g_ok = gs == exp_g
    hit_s = " / ".join(f"{n.node_id}" for n in hits)[:60]
    flag = "" if (t_ok and g_ok) else "❌"
    rows.append((flag, q, "+".join(short[t] for t in tables) or "미특정", "교차" if cross else "", gs, hit_s, fut, r.why[:45], memo))

bad = [x for x in rows if x[0]]
print(f"총 {len(rows)} · 기대와 다름 {len(bad)}\n")
print(f"{'':2}{'질문':<28} {'상품군':<14} {'교차':<3} {'게이트':<7} {'매핑':<28} {'시점':<10} 근거 | 메모")
for x in rows:
    print(f"{x[0]:<2}{x[1][:27]:<28} {x[2]:<14} {x[3]:<3} {x[4]:<7} {x[5][:27]:<28} {str(x[6]) if x[6] else '':<10} {x[7]} | {x[8]}")

# ── SQL 사후검사: HCX 가 쓸 법한 변형 ──
print("\n### 사후검사 변형")
for sql, toks, exp in [
    ("SELECT pd_nm FROM domestic_bonds WHERE substr(mat_dt,1,4)='2027' LIMIT 30", ["2027"], True),
    ("SELECT pd_nm FROM domestic_bonds WHERE mat_dt LIKE '2027%' LIMIT 30", ["2027"], True),
    ("SELECT pd_nm FROM domestic_bonds WHERE CAST(domestic_bonds.mat_dt AS INTEGER) BETWEEN 20270101 AND 20271231 LIMIT 30", ["2027"], True),
    ("SELECT pd_nm FROM domestic_bonds WHERE strftime('%Y', substr(mat_dt,1,4)||'-'||substr(mat_dt,5,2)||'-'||substr(mat_dt,7,2)) = '2027' LIMIT 30", ["2027"], True),
    ("SELECT pd_nm FROM domestic_bonds WHERE mat_dt >= 20260822 AND crd_grd IN ('AAA') ORDER BY applied_yield DESC LIMIT 30 -- 2027", ["2027"], False),
    ("SELECT pd_nm FROM domestic_bonds WHERE isu_dt BETWEEN 20270101 AND 20271231 AND mat_dt >= 20260822 LIMIT 30", ["2027"], "?"),
    ("SELECT pd_nm FROM domestic_bonds WHERE mat_dt BETWEEN 20261201 AND 20261231 LIMIT 30", ["202612"], True),
    ("SELECT pd_nm FROM domestic_bonds WHERE mat_dt <= 20301231 LIMIT 30", ["2030"], True),
]:
    got = gate.sql_uses_as_maturity(sql, toks)
    print(f"  {'✅' if got == exp or exp == '?' else '❌'} exp={exp!s:<5} got={got!s:<5} {sql[:95]}")

# ── 안내판 크기 (채권 단독 · 미특정 4테이블) ──
g1 = build_grounding(ctx, [], [B], cross=False); g4 = build_grounding(ctx, [], [], cross=False)
print(f"\n안내판: 채권 단독 {len(g1):,}자 · 미특정 4테이블 {len(g4):,}자")
