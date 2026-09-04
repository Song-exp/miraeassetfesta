"""네거티브 게이트 — HCX 호출 **전에** 기각할 질의를 기각한다.

규칙 §3: DB 근거가 없거나 기준일 이후면 HCX 를 건너뛰고 즉시 반환.
기각 사유는 문장으로 만들어 think_trace 에 남긴다 — 근거 제시 배점 (BUILD_PLAN §5⑤).

세 게이트:
  ① absent  — 온톨로지 속성 부재 ("위험등급 낮은 해외ETF")
  ② enum    — 신용등급은 **표준표**(credit_grade_scale.csv)로 판정 ("AAAA" 는 표에 없는 등급 · "BB+" 는 표에 있으나 데이터 0건 · "CB" 는 등급 모양이 아님)
              위험등급은 0~6
  ③ cutoff  — 기준일(2026-08-24, 리드 결정 09-02) 이후 시점 질의.
              🔴 2026-08-30: 여기서 **미리 기각하지 않는다**. "2027년 만기 채권" 은 만기 질문이고 채권에서 가장 흔한데
              연도만 보고 막으면 전부 죽는다(전수조사 §2-B). 미래 날짜를 가진 컬럼은 이 DB 에서 mat_dt 하나뿐이므로,
              HCX 가 쓴 SQL 에서 그 연도가 mat_dt 조건에 쓰였는지를 pipeline 이 **사후 검사**한다
              (future_tokens · sql_uses_as_maturity). 추가 호출 0회, 역질문 없음.

상품군 탐지(종전 _TABLE_HINTS 단어 11개)는 router.route 로 옮겼다 — 단어 목록으로 판정하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .loader import RuntimeContext, dataset_scope

# 🔴 세 날짜의 원천은 선언이다 — ontology/shared/dataset.yaml `dates` (2026-09-04).
#    코드에 박아 두면 서비스로 옮길 때(‘오늘’ 이 매일 바뀔 때) 코드를 고쳐야 한다. 선언이 없거나 깨지면 아래 값으로 물러선다.
_DATES = (dataset_scope().get("dates") or {})

DATA_CUTOFF = _DATES.get("decision") or "2026-08-24"   # 🔄 리드 결정 2026-09-02: 답변 표기·판정 기준일을 8/24 로 통일 (데이터 스냅샷 info_base_dt 8/21 · 주최 공지 as-of 8/22 는 데이터 설명에만)
# 🔴 구매가능(만기 경과) 판정 기준일 — 데이터 as-of(8/22 토, info_base_dt 8/21) 와 다르다. 리드 결정 2026-09-02:
#    평가·서비스 시점은 8/24(월, 2차 배포일) 이므로 mat_dt < 20260824 는 전부 '만기 경과' 로 제외한다.
#    8/22·8/23(주말) 만기 14종목은 as-of 기준으론 살아 있지만 8/24 에는 결제 불가 → 모수 밖. 답변의 '기준일' 표기도 8/24(DATA_CUTOFF) — 두 상수는 같은 값이지만 역할(표기 vs 만기 판정)이 달라 분리 유지.
BUYABLE_CUTOFF = _DATES.get("decision") or "2026-08-24"
# 데이터 스냅샷 종가일 — 전 행 info_base_dt=20260821(금). remaining_days·가격·수익률은 이 날 기준으로 산출돼 있다.
# 답변에서 잔존일수를 보일 때 이 날짜를 병기한다(질문 시점 8/24 와 3일 차이 — 오늘 만기 채권의 잔존일수가 3 으로 적혀 있다).
SNAPSHOT_DATE = _DATES.get("snapshot") or "2026-08-21"

# 교차질의 힌트 — 구성종목 보유 조건은 외부 Holdings 테이블(ext_*)을 함께 본다는 신호.
# 테이블을 "하나 고르기"가 아니라 "해당하는 전부"로 라우팅한다 (주최 8/24: 교차질의는 한 호출에서 복수 상품군).
_CROSS_HINTS = ("보유한", "보유중", "편입", "구성종목", "담고 있는", "포함된", "들어있는",
                # 🔴 2026-08-31 서버 실측 — "Li Auto 담은 국내 ETF" 가 교차로 안 잡혀 종목 노드가
                #    규칙 E(대상 테이블 alias 없음)에 걸려 버려졌다. '담은' 계열 표면형 보강.
                "담은", "담긴", "포함한", "보유하")


def detect_tables(question: str, ctx: RuntimeContext | None = None) -> list[str]:
    """호환용 — router.route 의 결과. 미특정이면 빈 목록(종전 의미 유지)."""
    from .loader import load_context
    from .router import route

    r = route(question, ctx or load_context())
    return r.tables if r.decided else []


def is_cross_query(question: str, tables: list[str], groups: int | None = None) -> bool:
    """`tables` 는 라우터가 **정한** 테이블만 (미특정 4테이블을 넘기면 안 된다).
    `groups` 는 서로 다른 상품군의 수(router.Route.groups) — '채권형 ETF' 가 국내/해외 둘로 남은 것은 교차가 아니다."""
    n = len(tables) if groups is None else groups
    return any(h in question for h in _CROSS_HINTS) or n >= 2


# 질의 문구 → shared 개체 축. absent 검사의 좌변
_ENTITY_HINTS: list[tuple[str, str]] = [
    ("위험등급", "RiskGrade"),
    # 2026-08-30 — 이 항목이 없어 absent(CreditGrade, public_funds/ETF) 선언이 한 번도 발동하지 않았다 (검토표 D-4-04).
    #   채권은 absent 에 없으므로 ① 을 지나 ② enum 검사로 간다.
    ("신용등급", "CreditGrade"),
    ("기초지수", "Index"),
    ("벤치마크", "Index"),
    ("추종", "Index"),
    ("자산군", "AssetClass"),
    ("투자지역", "Region"),
]

# 신용등급 토큰 후보 — 한글 사이의 대문자 시퀀스 (AAAA·AA+·CB 등)
# 🔴 \b 를 쓰면 안 된다. 파이썬 re 에서 한글은 단어 문자라 'AAAA인'·'AAAA등급' 의 A 와 '인' 사이에
#    경계가 서지 않아 토큰을 통째로 놓친다 (2026-08-26 실측: "신용등급 AAAA인 채권" 이 게이트를
#    통과해 HCX 를 호출했다). ASCII 영숫자만 경계로 본다.
_CRD_TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-D]{1,4}[+\-0]?)(?![A-Za-z0-9+\-])")   # 꼬리에 +/- 가 더 붙으면(A++) 토큰이 아니라 오기
# 등급의 '모양' — 표준표(AAA·AA+·BBB-·CCC·C …)의 구조: 같은 글자의 반복 + 선택 접미(+/-/0).
# 목록이 아니라 표의 형태에서 온 규칙이다 — 'CB'(전환사채)·'DC'(퇴직연금형) 는 글자가 섞여 등급이 아니고,
# 'AAAA' 는 모양은 맞지만 표에 없다. loader 가 표준표 전체가 이 모양임을 보장한다.
_GRADE_SHAPE = re.compile(r"^([A-D])\1{0,3}[+\-0]?$")
_TABLE_KO = {"public_funds": "공모펀드", "domestic_etfs": "국내 ETF", "overseas_etfs": "해외 ETF", "domestic_bonds": "국내채권"}
_RISK_GRADE = re.compile(r"(?:위험\s*등급|위험등급)\s*(\d+)\s*등급|(\d+)\s*등급")
# 기준일 2026-08-24 — 2026년 8월은 기준일 포함 월이라 허용, 9월 이후만 미래 (2차 데이터 전환 2026-08-25)
# 연도: '2027년' · '2027.' · '2027-' · '2027/' · '20270101' — 월: '2026년 9월' · '2026-09' · '2026.10'
_FUTURE = re.compile(
    r"(?<!\d)(202[7-9]|20[3-9]\d)(?:\s*년|(?=[.\-/]\d)|(?=\d{4}(?!\d)))"
    r"|(?<!\d)2026(?:\s*년\s*|[.\-/])(?:0?(9)|(1[0-2]))(?:\s*월|(?!\d))"
    # 두 자리 연도 — '28년 12월'·'28년까지'·'28년에 만기' 처럼 연도임이 분명한 꼴만.
    # '잔존만기 28년'·'10년 만기 채권' 의 28년·10년은 기간이라 잡으면 안 된다 (2026-08-31 실측: '28년 12월까지' 를 미탐지 → 연도 오기 20291231 을 못 잡음)
    r"|(?<!\d)(2[7-9]|[3-9]\d)\s*년(?=\s*\d{1,2}\s*월|까지|에\s*만기)"
)
# ── 상대 시점 확정표 — 질문 시점(오늘) D = BUYABLE_CUTOFF(2026-08-24, 월) 고정 ───────────────────
# 🔴 2026-09-03 서버 실측(오답기록 #51): "내년에 만기가 되는 회사채 중 AA 이상" → HCX 가 '내년' 을
#    mat_dt BETWEEN 20280824 AND 20290824(+2~+3년) 로 오계산했고, 사후검사가 "SQL 에 2027 이 없다" 를
#    "만기 질의가 아니다" 로 읽어 오기각. 코드가 아는 상대 시점 낱말이 내년·내후년·후년 셋뿐이었고 그것도
#    미래 감지용이었다 — 오늘·내일·이번 달·올해·N개월 안에·N년 뒤 는 전부 HCX 재량이었다.
#    이 표가 유일한 정의다. 프롬프트(build_grounding)·가드(enforce_relative_window)·테스트가 전부 여기서 읽는다.
#
# 날짜 판단(리드·채권 담당 결정 2026-09-03, 주최 공지 "26.08.24일 기준, 영업일 08.22 까지 / 해외는 한국시간 23일"):
#   · 8/21(금) = 데이터 스냅샷 종가일(info_base_dt) — remaining_days·가격·수익률의 산출 기준. 8/22(토)·8/23(일)은 영업일이 아니다.
#   · 8/24(월) = 주최가 명시한 '기준일' · 배포일 · 첫 결제 가능 영업일 → **질문 시점(오늘)** 은 8/24 로 고정한다.
#   · 상대 시점 창은 mat_dt 로만 만든다 — remaining_days 는 8/21 기준이라 8/24 를 오늘로 두면 3일 어긋난다
#     (mat_dt 20260824 → remaining_days 3). 답변의 잔존일수는 컬럼 원값을 보이되 산출 기준일(8/21)을 병기한다(재계산하지 않는다 —
#     심사 gold 는 제공 데이터의 컬럼값에서 나올 가능성이 높다).
#   · 'N년 뒤' = (D.year+N)년 전체(내년 = 1년 뒤 = 2027년 전체와 같은 읽기). 'N년 안에·이내' = D ~ D+N년(같은 날짜).
import datetime as _dt

_TODAY = _dt.date.fromisoformat(BUYABLE_CUTOFF)


def _ymd(d: _dt.date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def _month_end(y: int, m: int) -> _dt.date:
    return (_dt.date(y + (m == 12), (m % 12) + 1, 1) - _dt.timedelta(days=1))


def _add_months(d: _dt.date, n: int) -> _dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return _dt.date(y, m, min(d.day, _month_end(y, m).day))


def _add_years(d: _dt.date, n: int) -> _dt.date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:                      # 2/29
        return d.replace(year=d.year + n, day=28)


# 낱말 앞에 한글·영숫자가 붙으면 낱말이 아니다 — 'KB내일드림'·'오늘이엔엠'(발행사) 은 상대 시점이 아니다
_W = r"(?<![가-힣A-Za-z0-9])"
_RELATIVE_WINDOW: list[tuple[str, str, Callable[[], tuple[int, int]]]] = [
    # (라벨, 정규식, 창 계산) — 위에서부터 첫 매치가 이긴다(세부 표현 → 일반 표현 순)
    ("내년 상반기", _W + r"내년\s*상반기", lambda: (_ymd(_dt.date(_TODAY.year + 1, 1, 1)), _ymd(_dt.date(_TODAY.year + 1, 6, 30)))),
    ("내년 하반기", _W + r"내년\s*하반기", lambda: (_ymd(_dt.date(_TODAY.year + 1, 7, 1)), _ymd(_dt.date(_TODAY.year + 1, 12, 31)))),
    ("올해 하반기", _W + r"(?:올해|금년|이번\s*해)\s*하반기", lambda: (_ymd(_TODAY), _ymd(_dt.date(_TODAY.year, 12, 31)))),
    ("내후년", _W + r"(?:내후년|후년)", lambda: (_ymd(_dt.date(_TODAY.year + 2, 1, 1)), _ymd(_dt.date(_TODAY.year + 2, 12, 31)))),
    ("내년", _W + r"내년", lambda: (_ymd(_dt.date(_TODAY.year + 1, 1, 1)), _ymd(_dt.date(_TODAY.year + 1, 12, 31)))),
    ("올해", _W + r"(?:올해|금년|연내|올\s*해|이번\s*해|연말\s*까지|올해\s*말)", lambda: (_ymd(_TODAY), _ymd(_dt.date(_TODAY.year, 12, 31)))),
    # 발행사 '(주)오늘이엔엠' · 펀드명 '교보악사 내일환매'·'내일받는'·'내일드림'·'내일출금' 은 상대 시점이 아니다
    ("오늘", _W + r"(?:오늘(?!이엔엠)|금일|당일)", lambda: (_ymd(_TODAY), _ymd(_TODAY))),
    ("내일", _W + r"내일(?!환매|받는|드림|출금)", lambda: (_ymd(_TODAY + _dt.timedelta(days=1)),) * 2),
    ("모레", _W + r"모레", lambda: (_ymd(_TODAY + _dt.timedelta(days=2)),) * 2),
    ("이번 주", _W + r"(?:이번\s*주|금주)", lambda: (_ymd(_TODAY), _ymd(_TODAY + _dt.timedelta(days=6 - _TODAY.weekday())))),
    ("다음 주", _W + r"(?:다음\s*주|차주)", lambda: (_ymd(_TODAY + _dt.timedelta(days=7 - _TODAY.weekday())), _ymd(_TODAY + _dt.timedelta(days=13 - _TODAY.weekday())))),
    ("이번 달", _W + r"(?:이번\s*달|이달|당월)", lambda: (_ymd(_TODAY), _ymd(_month_end(_TODAY.year, _TODAY.month)))),
    ("다음 달", _W + r"(?:다음\s*달|다음달|내달|익월)", lambda: _month_window(_add_months(_TODAY, 1))),
]


def _month_window(d: _dt.date) -> tuple[int, int]:
    return _ymd(d.replace(day=1)), _ymd(_month_end(d.year, d.month))
# 숫자 상대 시점 — 'N년 뒤·후' = 해당 연도 전체 / 'N개월 뒤·후' = 해당 월 전체 / 'N년·N개월 안에·이내' = D ~ D+N
_REL_NUM = re.compile(
    _W + r"(\d{1,2})\s*(년|개월|달)\s*(뒤|후(?!순위)|안에|이내|내에|내로)"
)
_MAT_DT_WINDOW = 60      # SQL 에서 mat_dt 와 연도 사이의 허용 거리(글자) — BETWEEN·SUBSTR·CAST 어느 형태든 이 안에 든다

# ── 과거 방향 창 — '최근 N개월'·'지난 N년' (2026-09-05 #66) ───────────────────────────────
# 🔴 확정표(_RELATIVE_WINDOW·_REL_NUM)에는 과거 방향이 없다. 그래서 "최근 6개월 안에 새로 발행된" 과
#    "6개월 안에 만기되는" 이 **똑같은 창**(20260824~20270224)으로 잡혔다 — 앞의 '최근' 을 아무도 안 봤다.
# 🔴 확정표에 섞지 않고 따로 둔다. 코퍼스 395문항의 '최근/지난' 9건 중 6건이 "최근 1년 수익률"·"지난 1주일
#    수익률" 처럼 **성과 기간(컬럼 선택)** 이지 날짜 창이 아니다. 확정표에 넣으면 그 6건을 오폭한다 —
#    이 함수는 호출부가 발행 시점 질의로 판정했을 때만 부른다.
_PAST_NUM = re.compile(
    r"(?:최근|지난|근래)\s*(\d{1,2})\s*(년|개월|달|주일|주|일)|(?:최근|지난|근래)\s*(반\s*년)"
)


def resolve_past_window(question: str) -> list[tuple[str, int, int]]:
    """'최근 N개월'·'지난 N년' → [(낱말, lo, hi)] (D-N ~ D, 양끝 포함). 질문 시점 D = BUYABLE_CUTOFF.

    달 수는 일수 환산이 아니라 _add_months 로 센다 — 184일 빼기와 6개월 빼기는 사흘 어긋나고,
    그 사흘에 종목이 들고 난다.
    """
    out: list[tuple[str, int, int]] = []
    for m in _PAST_NUM.finditer(question):
        if m.group(3):                                   # '반 년'
            n, unit = 6, "개월"
        else:
            n, unit = int(m.group(1)), m.group(2)
        if n == 0:
            continue
        if unit == "년":
            lo_d = _add_years(_TODAY, -n)
        elif unit in ("개월", "달"):
            lo_d = _add_months(_TODAY, -n)
        elif unit in ("주", "주일"):
            lo_d = _TODAY - _dt.timedelta(weeks=n)
        else:
            lo_d = _TODAY - _dt.timedelta(days=n)
        lo, hi = _ymd(lo_d), _ymd(_TODAY)
        label = re.sub(r"\s+", " ", m.group(0).strip())
        if not any(l == lo and h == hi for _, l, h in out):
            out.append((label, lo, hi))
    return out


def resolve_relative_window(question: str) -> list[tuple[str, int, int]]:
    """질문의 상대 시점 낱말 → [(낱말, lo, hi)] (mat_dt 정수 창, 양끝 포함). 질문 시점은 BUYABLE_CUTOFF 로 고정.

    '10년 만기'·'잔존 3년' 같은 기간 표현은 창이 아니다(숫자형은 뒤·후·안에·이내 가 붙을 때만).
    같은 창이 두 번 나오면 하나로 센다. 서로 다른 창이 여럿이면 호출자가 판단한다(가드는 불개입).
    """
    out: list[tuple[str, int, int]] = []
    for label, pat, fn in _RELATIVE_WINDOW:
        m = re.search(pat, question)
        if m:
            lo, hi = fn()
            if not any(l == lo and h == hi for _, l, h in out):
                out.append((label, lo, hi))
            question = question[:m.start()] + " " * (m.end() - m.start()) + question[m.end():]   # '내년 상반기' 가 '내년' 으로 또 잡히지 않게
    for m in _REL_NUM.finditer(question):
        n, unit, rel = int(m.group(1)), m.group(2), m.group(3)
        if n == 0:
            continue
        if rel in ("뒤", "후"):
            if unit == "년":
                y = _TODAY.year + n
                lo, hi = _ymd(_dt.date(y, 1, 1)), _ymd(_dt.date(y, 12, 31))
            else:
                lo, hi = _month_window(_add_months(_TODAY, n))
        else:
            hi_d = _add_years(_TODAY, n) if unit == "년" else _add_months(_TODAY, n)
            lo, hi = _ymd(_TODAY), _ymd(hi_d)
        label = m.group(0).strip()
        if not any(l == lo and h == hi for _, l, h in out):
            out.append((label, lo, hi))
    return out


def relative_future_years(question: str) -> list[str]:
    """상대 시점 창 가운데 기준일 다음 해 이후로 시작하는 것의 연도('YYYY') — future_tokens 의 재료."""
    ys: list[str] = []
    for _, lo, _hi in resolve_relative_window(question):
        y = str(lo // 10000)
        if lo // 10000 > _TODAY.year and y not in ys:
            ys.append(y)
    return ys


# 호환 — 옛 이름. 값은 확정표에서 파생한다(리터럴 중복 금지)
_RELATIVE_FUTURE = {"내년": str(_TODAY.year + 1), "내후년": str(_TODAY.year + 2), "후년": str(_TODAY.year + 2)}


@dataclass
class GateResult:
    rejected: bool
    reason: str = ""       # think_trace 용 — 기각 근거 문장
    answer: str = ""       # 사용자에게 나갈 답


def detect_entities(question: str) -> list[str]:
    return [e for hint, e in _ENTITY_HINTS if hint in question]


# ── ③ cutoff — 사후 검사용 도구 (pipeline 이 SQL 생성 뒤에 부른다) ─────────────

def future_tokens(question: str) -> list[str]:
    """질문 속 기준일 이후 시점 — 연도는 'YYYY', 2026년 9~12월은 'YYYYMM'."""
    toks: list[str] = []
    for m in _FUTURE.finditer(question):
        if m.group(1):
            toks.append(m.group(1))
        elif m.group(4):                     # 두 자리 연도 '28년' → 2028
            toks.append(f"20{m.group(4)}")
        else:
            toks.append(f"2026{int(m.group(2) or m.group(3)):02d}")
    # 상대 시점('내년'·'3년 뒤' …)은 확정표에서 연도를 받는다 — 표와 다른 값을 여기 따로 적지 않는다
    for year in relative_future_years(question):
        if year not in toks:
            toks.append(year)
    return toks


def sql_uses_as_maturity(sql: str, tokens: list[str]) -> bool:
    """토큰 전부가 SQL 의 mat_dt 조건 근처(±60자)에 쓰였는가 = HCX 가 '만기' 로 해석했는가.

    이 DB 에서 미래 날짜를 가진 컬럼은 mat_dt(만기일, 최대 2083-06-05) 하나뿐이다 — 발행일 최대 2026-09-10,
    등급일·종가일 최대 2026-08-21. 그래서 미래 연도가 정당하게 들어갈 자리는 mat_dt 조건밖에 없다.
    """
    anchors = [m.start() for m in re.finditer(r"mat_dt", sql, re.I)]
    if not anchors:
        return False
    for tok in tokens:
        pat = re.escape(tok) if len(tok) == 4 else rf"{tok[:4]}-?{tok[4:]}"   # 'YYYYMM' 은 'YYYY-MM' 표기도 허용
        hit = any(abs(m.start() - a) <= _MAT_DT_WINDOW for m in re.finditer(pat, sql) for a in anchors)
        if not hit:
            return False
    return True


# ── ② enum — 신용등급 판정 ──────────────────────────────────────────────

def _grade_span(ctx: RuntimeContext) -> str:
    """'AAA~D' — 표준표의 최상·최하 등급으로 만든 유효 범위 문구 (표가 늘면 문구도 따라온다)."""
    from .loader import GRADE_SCALE_CSV, grade_scale

    std = [g for g in ctx.std_grades if g and g[0].isalpha()]
    if not std:
        return "AAA~C"
    scale = grade_scale() if GRADE_SCALE_CSV.exists() else ()
    top = scale[0] if scale else "AAA"
    worst = max(std, key=lambda g: (g[0], len(g)))          # 알파벳이 뒤일수록 하위 등급
    return f"{top.rstrip('0')}~{worst.rstrip('0')}"


def classify_grade_token(tok: str, ctx: RuntimeContext) -> str:
    """'not_grade'(등급 모양 아님 — 무시) · 'unknown'(표준표에 없음 — 존재하지 않는 등급) ·
    'no_data'(표준 등급이나 2차 데이터 0건) · 'ok'."""
    if not _GRADE_SHAPE.match(tok):
        return "not_grade"
    if ctx.std_grades and tok not in ctx.std_grades:
        return "unknown"
    if tok in ctx.crd_grades:
        return "ok"
    return "no_data" if ctx.std_grades else "unknown"    # 표준표가 없으면 종전대로 데이터 값만으로 판정


def check(question: str, ctx: RuntimeContext, tables: list[str]) -> GateResult:
    """`tables` 는 라우터가 정한 테이블(미특정이면 빈 목록)."""
    entities = detect_entities(question)

    # ①-0 absent_properties — 속성 자체가 없는 부류(좌수·운용역·기준가 시계열…): enums yaml 선언(= ttl ABSENT)이 곧
    #    게이트 어휘다. HCX 0회 — 컬럼명 유사어(fd_set_pcd ≈ '설정')로 모델이 대체 계산하는 경로를 먼저 끊는다
    #    (2026-09-02 KG-027: 설정유형코드 '10' 을 "10좌" 로 6펀드 단언). 대체 안내는 선언의 substitute 만.
    if len(tables) == 1:
        for item in ctx.absent_props.get(tables[0], []):
            for pat in item.get("vocab") or []:
                hit = re.search(pat, question)
                if hit:
                    sub = item.get("substitute") or {}
                    note = f" {sub['note']}" if sub.get("note") else ""
                    return GateResult(
                        rejected=True,
                        reason=f"온톨로지 ABSENT — {tables[0]} 에 {item['property']} 속성 없음 · 질문의 '{hit.group(0)}' (enums absent_properties → HCX 0회)",
                        answer=f"{item['why']}{note}",
                    )

    # ① absent — 온톨로지 속성 부재 (질의가 특정 테이블 하나로 좁혀질 때만 기각)
    if len(tables) == 1:
        for entity in entities:
            why = ctx.absent.get((entity, tables[0]))
            if why:
                prop = ctx.entity_property.get(entity, entity)
                return GateResult(
                    rejected=True,
                    reason=f"온톨로지상 {tables[0]} 클래스에 {prop} 속성이 정의되어 있지 않음 — {why}",
                    answer=f"해당 상품군에는 요청하신 속성이 제공되지 않습니다. ({why.split('→')[0].strip()})",
                )

    # ② enum — 신용등급 (채권 문맥 또는 '신용등급' 명시)
    if ctx.crd_grades and ("신용등급" in question or "domestic_bonds" in tables):
        for tok in _CRD_TOKEN.findall(question):
            kind = classify_grade_token(tok, ctx)
            if kind == "unknown":
                return GateResult(
                    rejected=True,
                    reason=f"'{tok}' 는 신용등급 표준표({len(ctx.std_grades) or len(ctx.crd_grades)}종)에 없음 — 존재하지 않는 등급",
                    # 유효 범위 문구도 표준표에서 만든다 — 코드에 'AAA~C' 를 적어 두면 표가 늘어도 문구가 안 따라온다 (2026-09-04, D 등급 노드 추가)
                    answer=f"'{tok}'는 존재하지 않는 신용등급이라 확인할 수 없습니다. 유효 등급은 {_grade_span(ctx)} 체계입니다.",
                )
            if kind == "no_data":
                # 기각이 아니라 DB 근거의 즉답 — 표준 등급이지만 2차 데이터에 해당 채권이 없다 (등급서열 규칙)
                return GateResult(
                    rejected=True,
                    reason=f"'{tok}' 는 표준 등급이나 2차 데이터에 0건 — HCX 없이 즉답 (등급서열 규칙)",
                    answer=f"'{tok}' 등급은 신용등급 체계에 있으나, 기준일 {DATA_CUTOFF} 데이터에 해당 등급의 채권이 없습니다.",
                )

    # ④ constant — 상수 컬럼 위반 (2026-08-30 R-5 ① 층). 그 테이블 하나로 라우팅됐을 때만. 규칙은 yaml gate_constants,
    #    triggers 는 정규식(경계 포함 — '유로스탁스50' 지수명은 '유로 거래' 가 아니다)
    if len(tables) == 1:
        for item in ctx.gate_constants.get(tables[0], []):
            for pat in item.get("triggers") or []:
                hit = re.search(pat, question)
                if hit:
                    return GateResult(
                        rejected=True,
                        # reason 키가 있으면 그대로 쓴다 — '상수 컬럼' 서술이 안 맞는 부재형 항목용 (연평균 등)
                        reason=item.get("reason") or f"{tables[0]}.{item['column']} 은(는) 전건 '{item['value']}' 인 상수 컬럼 — 질문의 '{hit.group(0)}' 조건은 데이터에 존재하지 않음 (yaml gate_constants)",
                        answer=item.get("answer") or f"해당 상품군의 {item['column']} 은(는) 전부 '{item['value']}' 이라 요청하신 조건의 상품은 수록되어 있지 않습니다.",
                    )

    # ② enum — 위험등급 값 범위: **테이블별 선언**(shared/risk_grade.yaml range_by_table)에서 판정한다 — 코드 상수 금지.
    #    2026-09-02 KG-013/014: 공용 상수 0~6 이 펀드 0등급을 정의역으로 허용(NULL 422 ≠ 0)하고 즉답 문구도 "0~6" 이었다.
    #    라우팅 테이블이 하나면 그 범위·문구, 여럿/미특정이면 선언들의 합집합. 선언이 없으면 종전 0~6.
    if "위험등급" in question:
        m = _RISK_GRADE.search(question)
        grade = next((g for g in (m.groups() if m else ()) if g), None)
        if grade is not None:
            g = int(grade)
            specs = {t: ctx.grade_ranges[t] for t in (tables or list(ctx.grade_ranges)) if t in ctx.grade_ranges}
            lo = min((r["min"] for r in specs.values()), default=0)
            hi = max((r["max"] for r in specs.values()), default=6)
            if not lo <= g <= hi:
                if len(tables) == 1 and tables[0] in specs:
                    r, name = specs[tables[0]], _TABLE_KO.get(tables[0], tables[0])
                    answer = (f"{name} 위험등급은 {r['min']}({r.get('label_min', '')})~{r['max']}({r.get('label_max', '')}) "
                              f"범위로 정의되어 있어 {g}등급은 없습니다." + (f" ({r['note']})" if r.get("note") else ""))
                else:
                    answer = f"위험등급은 {lo}~{hi} 범위로 정의되어 있습니다. {g}등급은 존재하지 않습니다."
                return GateResult(
                    rejected=True,
                    reason=f"위험등급 {g} 는 정의 범위({lo}~{hi}, 테이블별 선언 range_by_table)를 벗어남",
                    answer=answer,
                )

    return GateResult(rejected=False)
