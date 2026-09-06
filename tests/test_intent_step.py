# -*- coding: utf-8 -*-
"""질의 의도 분석 단계 (2026-09-06 · 주최 8/31 공지 "Intent 분석은 HCX 필수").

환각 방어는 프롬프트가 아니라 구조다 — parse_intent 가 닫힌 어휘로 접고 질문에 없는 어구를 버리며,
pipeline 은 결과를 trace 와 '규칙·KG 가 둘 다 침묵한 자리의 라우팅' 에만 쓴다. SQL·답변에는 닿지 않는다.
"""
import pytest

from src.hcx.planner import parse_intent
from src.runtime import pipeline as P
from src.runtime.loader import db_path

Q = "미래에셋자산운용이 운영하는 ETF 중 삼성전자 비중이 5% 넘는 것 몇 개야?"


def test_parse_keeps_only_closed_vocab_and_verbatim_spans():
    out = parse_intent('{"domain":"국내ETF","task":"개수","entities":["미래에셋자산운용","삼성전자","엔비디아"],'
                       '"constraints":["5% 넘는","레버리지 제외"]}', Q)
    assert out == {"domain": "국내ETF", "task": "개수", "entities": ["미래에셋자산운용", "삼성전자"], "constraints": ["5% 넘는"]}


def test_parse_folds_unknown_words_to_unknown_and_survives_noise():
    out = parse_intent('분류 결과입니다:\n```json\n{"domain":"주식","task":"예측","entities":"삼성전자"}\n```', Q)
    assert out == {"domain": "불명", "task": "불명", "entities": [], "constraints": []}


def test_parse_rejects_non_json():
    assert parse_intent("SELECT * FROM domestic_etfs", Q) is None
    assert parse_intent("", Q) is None
    assert parse_intent('["국내ETF"]', Q) is None


class _P:
    """가짜 플래너 — 의도 분석은 고정 JSON, SQL 은 원문 그대로, 답변은 표식."""

    def __init__(self, intent_text, raw):
        self.intent_text, self.raw, self.intent_calls = intent_text, raw, 0

    def analyze_intent(self, q):
        self.intent_calls += 1
        return parse_intent(self.intent_text, q)

    def plan_sql(self, q, g):
        return self.raw

    def compose_answer(self, q, rows, answer_rules=""):
        return "HCX"


class _NoIntent:
    def plan_sql(self, q, g):
        return "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' LIMIT 30"

    def compose_answer(self, q, rows, answer_rules=""):
        return "HCX"


needs_db = pytest.mark.skipif(not db_path().exists(), reason="DB 없음")


@pytest.fixture(scope="module")
def ctx():
    return P.load_context()


@needs_db
def test_intent_is_recorded_and_gate_rejection_still_needs_no_more_hcx(ctx):
    p = _P('{"domain":"채권","task":"조회","entities":["AAAA"],"constraints":[]}', "SELECT 1")
    r = P.answer_question("T", "신용등급 AAAA인 채권 알려줘", planner=p, ctx=ctx)
    assert p.intent_calls == 1
    assert "[Intent] HCX-005 질의 의도 분석 — 상품군 채권 · 과제 조회 · 개체 ['AAAA']" in r.think_trace
    assert "[Gate] 기각" in r.think_trace and "AAAA" in r.answer


@needs_db
def test_intent_does_not_override_router_or_kg(ctx):
    # 라우터가 ETF 로 정한 질문에 의도 분석이 '채권' 이라 해도 상품군은 바뀌지 않는다.
    p = _P('{"domain":"채권","task":"개수","entities":[],"constraints":[]}',
           "SELECT COUNT(*) FROM domestic_etfs WHERE pd_grp_no = 'ETF' LIMIT 30")
    r = P.answer_question("T", "국내 ETF 총 몇 개야?", planner=p, ctx=ctx)
    assert "Intent 채택" not in r.think_trace
    assert "domestic_etfs" in r.sql and "domestic_bonds" not in r.sql


@needs_db
def test_intent_fills_only_when_router_and_kg_are_both_silent(ctx):
    q = "수익률 제일 높은 거 5개만 알려줘"          # 상품 명사 없음 → 미특정, KG 매핑 없음
    p = _P('{"domain":"펀드","task":"랭킹","entities":[],"constraints":["5개"]}',
           "SELECT itm_no, TRIM(itm_nm), fd_yr1_ern_r FROM public_funds WHERE sale_yn = '판매중' ORDER BY fd_yr1_ern_r DESC LIMIT 5")
    r = P.answer_question("T", q, planner=p, ctx=ctx)
    assert "[Route] 상품군 — 미특정" in r.think_trace
    assert "Intent 채택" in r.think_trace and "public_funds" in r.think_trace.split("Intent 채택")[1][:80]


@needs_db
def test_planner_without_intent_method_runs_as_before(ctx):
    r = P.answer_question("T", "국내 ETF 총 몇 개야?", planner=_NoIntent(), ctx=ctx)
    assert "[Intent]" not in r.think_trace and r.sql


def test_planner_intent_roundtrip_with_fake_client():
    from src.hcx.planner import HCXPlanner

    class FakeHCX:
        def __init__(self, text):
            self.text, self.calls = text, []

        def complete(self, system, user):
            self.calls.append((system, user))
            return type("R", (), {"text": self.text})()

        def close(self):
            pass

    fake = FakeHCX('{"domain":"국내ETF","task":"개수","entities":["삼성전자"],"constraints":["없는조건"]}')
    p = HCXPlanner(sql_client=FakeHCX("SELECT 1"), answer_client=FakeHCX("x"), intent_client=fake)
    out = p.analyze_intent("삼성전자 담은 ETF 몇 개야?")
    assert out == {"domain": "국내ETF", "task": "개수", "entities": ["삼성전자"], "constraints": []}
    assert "지어내지 않는다" in fake.calls[0][0] and "삼성전자 담은 ETF" in fake.calls[0][1]
    # 2인자 생성(종전 호출 형태)은 의도 클라이언트를 만들지 않는다 — 키 없는 환경에서도 생성이 죽지 않는다
    assert HCXPlanner(sql_client=FakeHCX("SELECT 1"), answer_client=FakeHCX("x"))._intent is None


def test_intent_config_never_waits_on_rate_limit():
    # 서현 응답시간 분석 §2.1 — 보조 호출이 429 대기(20초×3)로 문항을 50초대로 밀면 안 된다
    from src.hcx.planner import INTENT_CONFIG

    assert INTENT_CONFIG.max_retries == 0 and INTENT_CONFIG.timeout_s <= 30
