# -*- coding: utf-8 -*-
"""I — 채권 query_rules 압축: 조건식 + 한 줄 이유만 남기고, 이력·근거·검증 수치는 문서로 옮긴다.
CASE 식·조건식은 원문에서 그대로 추출해 글자 하나 안 바뀐다(검증)."""
import sys, os, re, json
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(r"C:\Users\bella\Desktop\대학\공모전\트리플에이치\미래에셋"); sys.path.insert(0, ".")
import yaml

P = "ontology/enums/domestic_bonds.yaml"
raw = open(P, encoding="utf-8").read()
D = yaml.safe_load(raw)
OLD = D["query_rules"]
assert all(isinstance(v, str) for v in OLD.values())

def grab(rule, pat):
    m = re.search(pat, OLD[rule], re.S); assert m, (rule, pat[:30]); return re.sub(r"\s+", " ", m.group(1)).strip()
STRUCT = grab("구조표시", r"(CASE WHEN .*? END AS 구조)")
BACK = grab("신용보강", r"(CASE WHEN .*? END AS 보강)")
SEC = grab("유동화위험금지", r"조건식: (TRIM\(bd_knd\) IN .*?pd_nm LIKE '%유동화%')")

# ── 1. 원문 보존 문서 ──
hist = ["# 채권 query_rules 원문(압축 전) — 2026-08-30 밤 I 작업",
        "",
        "> `ontology/enums/domestic_bonds.yaml` 의 `query_rules` 26개를 SQL 생성기용으로 압축하면서(9,105자 → 아래 표 참조) 뺀 **이력·근거·검증 수치**를 여기 보존한다. 규칙의 조건식은 압축본과 동일하다(스크립트가 CASE 식 동일성을 검증). 근거 SQL 은 `채권_검토기록_2026-08-27.md` · `채권_전수조사_2026-08-30.md`.",
        ""]
for k, v in OLD.items():
    hist += [f"## {k} ({len(v)}자)", "", v.strip(), ""]
open("docs/review_2026-08-26/채권_규칙_원문_2026-08-30.md", "w", encoding="utf-8").write("\n".join(hist))

# ── 2. 압축본 ──
NEW = {
"대표행": "종목 수 집계는 COUNT(DISTINCT pd_no) 또는 GROUP BY pd_no — 1,078종목이 장내·장외 2~4행. 속성 답변에서 '장내행 우선' 으로 한 줄만 고르지 말 것: 장외행은 종류·등급·발행사·위험등급·듀레이션이 NULL 일 수 있다. 값이 다르면 두 줄을 병기(같으면 한 번), 장외 가격엔 '액면가 수준' 단서. 결측을 옆 줄 값으로 채우지 않는다.",
"판매행": OLD["판매행"].strip(),
"구매가능": "buyable_quantity 는 무효(사용 금지). '살 수 있나' = curr_cd='KRW' AND mat_dt >= 20260822 (21,828행) 면 구매가능. 판매 조건(수익률·단가)이 수록된 것은 그중 634행(판매행) — 나머지는 '구매 가능하나 당사 판매 조건은 미수록'.",
"문자열비교": OLD["문자열비교"].strip(),
"위험등급방향": "pd_risk_gcd 는 문자열 '11'~'16'·'00'. 뒷자리가 등급이며 숫자가 클수록 안전: 11=매우높은위험(1등급) · 12=높은위험 · 13=다소높은위험 · 14=보통위험 · 15=낮은위험 · 16=매우낮은위험(6등급) · 00=해당없음. '위험 낮은·안전한' = pd_risk_gcd='16'(넓게 IN ('15','16')) · '위험 높은' = '11'(넓게 IN ('11','12','13')). '1등급' 은 최위험이지 최우량이 아니다. 답변엔 pd_risk_nm 문구를 그대로 인용. 신용등급(crd_grd)과 별개 축 — '등급' 만 있으면 어느 쪽인지 밝힌다. 국공채는 거의 전부 '16'.",
"등급서열": "crd_grd 서열(높→낮): AAA > AA+ > AA0 > AA- > A+ > A0 > A- > BBB+ > BBB0 > BBB- > BB0 > BB- > B+ > B- > C0 (데이터 15종). 'AA- 이상' = TRIM(crd_grd) IN ('AAA','AA+','AA0','AA-') · 'A 이상' = 앞 7종 · '투자등급(BBB- 이상)' = 앞 10종 · '투기등급' = BB0 이하 5종. 사용자 표기 AA·A·BBB·BB·B 는 DB 의 AA0·A0·BBB0·BB0·B0. 표준 등급 중 BB+·B0·CCC·CC·D 는 데이터 0건 — '존재하지 않는 등급' 이 아니라 '해당 채권 없음'. 무등급(NULL) 4,020행(국공채 2,840 전부 + 특수채 254 + 회사채 926)은 등급 조건에서 빠진다 — 국공채는 '신용등급 미부여' 로 답하고 결측을 '낮은 등급' 으로 취급하지 않는다.",
"등급정규화": OLD["등급정규화"].strip(),
"영값배제": OLD["영값배제"].strip(),
"수익률정상": OLD["수익률정상"].strip(),
"듀레이션정상": "dur IS NOT NULL AND dur != 99 AND dur != 0 AND remaining_days > 0 (99·0 은 결측 표기 · 만기 경과 행 제외). 익일 질의의 ndy_dur 도 같은 조건.",
"익일값": "ndy_* 컬럼은 '익일' 질의에만. 일반 질의는 당일 컬럼.",
"과세수익률금지": OLD["과세수익률금지"].strip(),
"더티금지": OLD["더티금지"].strip(),
"등급일사용금지": OLD["등급일사용금지"].strip(),
"이자유형분리": OLD["이자유형분리"].strip(),
"장내종가": OLD["장내종가"].strip(),
"구조표시": ("추천·랭킹에서 특수구조(콜·풋·후순위·전환·영구·코코·분리채권·물가채)를 제외하지 않는다 — 빼는 것은 고위험제외 규칙뿐(분리채권 209 는 전부 국고채 6등급). "
            "대신 채권 목록 SELECT 에 아래 식을 '구조' 열로 그대로 붙인다(LIKE 만 사용 · 우선순위 순): " + STRUCT + " "
            "첫 줄(은행 자본성증권)은 이름이 아니라 컬럼 두 개(발행 종류 + 위험등급 1~3)로 판정한다 — 이름의 코코/조건상각/(상) 은 판정에 쓰지 않는다. "
            "콜은 '콜' 앞뒤에 한글이 없을 때만(한국콜마 제외). 답변에서 이 열의 값을 종목 옆에 한 단어로 붙이고, 영구채는 '만기일 = 콜 개시일', 은행 자본성증권은 '원금 상각·이자 미지급 조건 가능' 을 덧붙인다. "
            "ESG 라벨 (녹)/(사)/(지) 는 name_encoding.esg_labels. 조회·사실확인 질의는 아무것도 빼지 않는다."),
"고위험제외": ("추천·랭킹 질의는 WHERE 에 pd_risk_gcd <> '11' AND COALESCE(TRIM(crd_grd), '') <> 'C0' AND bd_ofr_tcd <> '사모' 를 넣는다. "
             "❌ NOT (pd_risk_gcd='11' OR crd_grd='C0') 금지 — crd_grd 가 NULL 인 4,020행(국공채 전부)이 통째로 빠진다. "
             "이유: 수익률 50% 초과 96행(최고 728.5%)은 전부 C0·1등급 부실채(평가가가 액면의 27~45%)이고, 사모는 일반 투자자가 살 수 없다. "
             "제외 사실을 답변에 밝힌다: '위험등급이 매우 높은(1등급) 채권과 사모 채권은 제외했습니다.' "
             "조회·사실확인 질의에서는 제외하지 않는다(728.5% 는 사실) — 신용등급·위험등급을 함께 답한다. "
             "주의 문구: 답변에 실린 종목 중 applied_yield > 6% 또는 pd_risk_gcd IN ('12','13') 이 있으면 '수익률이 높은 채권은 원금을 돌려받지 못할 위험도 높을 수 있습니다. 신용등급·위험등급을 함께 확인하세요.' 를 붙인다(조회 답변도). "
             "추천 모수 약 19,400행 · 최고 9.82% · 국공채 최고 4.89%. ❌ 가격 기준 필터 금지 · ❌ 유동화 전체 제외 금지."),
"신용보강": ("'정부가 보증하는/안전한 공공 채권' 류 질의는 아래 식을 '보강' 열로 붙여 층을 함께 답한다(컬럼 3개만 · 단어 필터 없음): " + BACK + " "
            "분포: A 2,873 · B 7 · C 2,968 · D 3,171 · E 2,648 · F 10,215. A = 국공채 + 한국은행 통안채. C = 법정 손실보전이 확인된 4곳(주금공 MBS 포함). D = 특수채 발행 공공기관(한전·도로공사·수출입은행 등) — 손실보전 조항 미확인. "
            "답변 규약: ① D 에 '정부 보증' 이라 말하지 않는다('특별법 공공기관 발행, 정부 보증 표기 없음') ② 구조 열이 은행 자본성증권·후순위·영구채면 A·B·C 라도 '손실보전 대상 아님' 병기 ③ 발행사 칸이 빈 행은 '발행사 미수록' 병기 ④ E 는 정부와 무관(담보는 기초자산)."),
"시장집계금지": OLD["시장집계금지"].strip(),
"장외등급해석": OLD["장외등급해석"].strip(),
"유동화위험금지": "유동화 = " + SEC + " (4,045행). 발행자가 SPC 라 발행사명으로 위험·원회사를 판단하지 않는다.",
"외화채없음": "모든 채권 질의에 curr_cd='KRW' 를 기본 조건으로 건다(원화채 21,881행이 모수). curr_cd='000' 외국발행채 1행은 정보 미비로 사용 불가. '외화채권·해외채권' 질의는 '수록 없음' 으로 답한다(해외ETF 로 유도 금지).",
"기준일": OLD["기준일"].strip(),
"발행사조회": "발행사 질의는 KG 매핑값이 있으면 TRIM(pd_pbcm) 정확 일치, 없으면 pd_pbcm LIKE '%이름%' ('(주)' 위치·꼬리 공백이 제각각: 한국전력 → '한국전력공사(주)' · 산업은행 → '한국산업은행' · 기업은행 → '(주)중소기업은행'). 약칭(한전·LH·산은·기은·주금공)은 동의어 표. MBS·유동화는 발행자가 SPC 라 원회사 이름으로 검색되지 않는다. 발행사 빈 행은 '발행사 미수록'. 다른 상품군의 같은 이름 값을 끌어오지 않는다.",
"공모사모판정": "공모/사모는 bd_ofr_tcd 로만(공모 19,875 · 사모 2,007). 종목명으로 추론 금지 — 이름의 '(사)' 는 사모가 아니라 사회적채권 라벨(99.8% 가 공모).",
}
assert list(NEW) == list(OLD), "키 순서"

# ── 3. 원문 블록을 그 자리에서 치환 ──
lines = raw.split("\n")
i0 = next(i for i, l in enumerate(lines) if l.startswith("query_rules:"))
i1 = next(i for i, l in enumerate(lines) if l.startswith("# ── 동의어"))
def q(s): return json.dumps(s, ensure_ascii=False)          # YAML 겹따옴표 문자열 = JSON 문자열
w = max(len(k) for k in NEW) + 1
block = ["query_rules:",
         "  # ── 2026-08-30 밤 압축본 — SQL 생성기용: 조건식 + 한 줄 이유만. 이력·근거·검증 수치는 docs/review_2026-08-26/채권_규칙_원문_2026-08-30.md ──"]
for k, v in NEW.items():
    block.append(f"  {k}:{' ' * (w - len(k))}{q(v)}")
block.append("")
lines[i0:i1] = block
open(P, "w", encoding="utf-8").write("\n".join(lines))

# ── 4. 검증 ──
D2 = yaml.safe_load(open(P, encoding="utf-8"))
Q2 = D2["query_rules"]
assert list(Q2) == list(OLD)
assert grab.__call__  # noqa
assert re.search(r"(CASE WHEN .*? END AS 구조)", Q2["구조표시"], re.S).group(1) == STRUCT
assert re.search(r"(CASE WHEN .*? END AS 보강)", Q2["신용보강"], re.S).group(1) == BACK
for k in ("synonyms", "answer_rules", "clarify", "name_encoding", "normalization", "columns"):
    assert D2.get(k) == D.get(k), k
old_n = sum(len(v) for v in OLD.values()); new_n = sum(len(v) for v in Q2.values())
print(f"query_rules {old_n:,} → {new_n:,}자 ({new_n/old_n:.0%})")
for k in OLD:
    if len(OLD[k]) != len(Q2[k]): print(f"  {k:<8} {len(OLD[k]):>5} → {len(Q2[k]):>5}")
from src.runtime.loader import load_context
ctx = load_context()
from src.runtime.pipeline import build_grounding
print("안내판 채권 단독:", f"{len(build_grounding(ctx, [], ['domestic_bonds'], cross=False)):,}자 · 규칙 {len(ctx.planner_context(['domestic_bonds'])):,}자")
