"""HyperCLOVA X 클라이언트.

노드(PlanSQL·Answer)는 어떤 모델을 쓰는지 몰라야 합니다. 모델 선택은 설정이고,
`HCXConfig` 하나만 갈아끼우면 노드 코드는 그대로입니다.

인증 스킴: 신규(2025-01 이후) `Authorization: Bearer nv-****`.
  구버전 `X-NCP-CLOVASTUDIO-API-KEY` + APIGW 게이트웨이 키 2-키 방식은 지원 중단 예정입니다.
  확인: https://api.ncloud-docs.com/docs/ai-naver-clovastudio-summary (2026-08-14)

🔴 thinkingContent 는 의도적으로 버립니다.
  HCX-007 의 사고과정은 '모델이 생성한 문장'이라 근거가 아닙니다.
  우리 `think_trace` 는 각 노드가 실제로 한 일의 로그로만 만듭니다 — 지어낼 수 없는 근거여야 합니다.
  토큰 수(`thinking_tokens`)만 레이턴시·비용 회계용으로 남깁니다.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_BASE_URL = "https://clovastudio.stream.ntruss.com"

# HCX-007 thinking.effort 별 maxCompletionTokens 기본값 (공급자 문서 기준)
_EFFORT_DEFAULT_TOKENS = {"none": 512, "low": 5120, "medium": 10240, "high": 20480}
_VALID_EFFORTS = frozenset(_EFFORT_DEFAULT_TOKENS)


class HCXError(RuntimeError):
    """HCX 호출 실패. status_code 는 HTTP 응답이 없으면 None."""

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body

    @property
    def is_rate_limited(self) -> bool:
        return self.status_code == 429


@dataclass(frozen=True)
class RateLimit:
    """응답 헤더 x-ratelimit-* 파싱 결과.

    🔴 테스트 키 실측(2026-08-14): 60 requests/60s · 60,000 tokens/60s.
    토큰 한도가 먼저 걸립니다 — 컨텍스트 8,159토큰이면 분당 7회가 상한입니다.
    """

    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests_s: float | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens_s: float | None = None

    @classmethod
    def from_headers(cls, h) -> RateLimit:
        def num(key: str) -> int | None:
            v = h.get(key)
            if v is None:
                return None
            m = re.search(r"\d+", v)
            return int(m.group()) if m else None

        def secs(key: str) -> float | None:
            v = h.get(key)
            if v is None:
                return None
            m = re.search(r"([\d.]+)\s*(ms|s|m)?", v)
            if not m:
                return None
            n = float(m.group(1))
            return {"ms": n / 1000, "m": n * 60}.get(m.group(2) or "s", n)

        return cls(
            limit_requests=num("x-ratelimit-limit-requests"),
            remaining_requests=num("x-ratelimit-remaining-requests"),
            reset_requests_s=secs("x-ratelimit-reset-requests"),
            limit_tokens=num("x-ratelimit-limit-tokens"),
            remaining_tokens=num("x-ratelimit-remaining-tokens"),
            reset_tokens_s=secs("x-ratelimit-reset-tokens"),
        )


@dataclass(frozen=True)
class HCXConfig:
    """노드별로 따로 갖는 설정. 모델 교체는 여기만 바꿉니다."""

    model: str = "HCX-005"
    thinking_effort: str | None = None  # HCX-007 전용. None 이면 추론 파라미터를 안 보냄
    max_tokens: int = 1024
    temperature: float = 0.0
    top_p: float = 0.8
    repeat_penalty: float = 1.1
    timeout_s: float = 60.0
    max_retries: int = 3  # 429 전용. 다른 오류는 재시도하지 않습니다
    retry_wait_s: float = 20.0  # 헤더에 reset 값이 없을 때의 대기

    def __post_init__(self) -> None:
        if self.thinking_effort is not None and self.thinking_effort not in _VALID_EFFORTS:
            raise ValueError(
                f"thinking_effort 는 {sorted(_VALID_EFFORTS)} 중 하나여야 합니다: {self.thinking_effort!r}"
            )

    @property
    def label(self) -> str:
        return self.model if self.thinking_effort is None else f"{self.model}({self.thinking_effort})"


@dataclass
class HCXResult:
    text: str
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    thinking_tokens: int
    finish_reason: str
    rate_limit: RateLimit = field(default_factory=RateLimit)
    retries: int = 0  # 429 로 재시도한 횟수
    wait_s: float = 0.0  # 429 로 잠든 시간 합 (2026-09-06 QA r1 BP④ — 기록만, 정책은 그대로)
    raw: dict = field(repr=False, default_factory=dict)

    @property
    def truncated(self) -> bool:
        """length 로 끊긴 응답. 추론 모델에서 사고가 예산을 먹으면 발생합니다."""
        return self.finish_reason == "length"


class HCXClient:
    def __init__(
        self,
        config: HCXConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
    ):
        self.config = config or HCXConfig()
        key = api_key or os.environ.get("HYPERCLOVA_API_KEY")
        if not key:
            raise HCXError("HYPERCLOVA_API_KEY 가 없습니다. .env 를 확인하세요.")
        self._key = key
        self._base_url = (base_url or os.environ.get("HYPERCLOVA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._client = client or httpx.Client(timeout=self.config.timeout_s)
        self._owns_client = client is None
        self.last_rate_limit = RateLimit()  # 호출자가 페이싱에 씁니다
        # 🆕 2026-09-06 QA r1 BP④ — 마지막 호출의 429 재시도·대기·응답 시간. **기록만** 한다(재시도 정책은 리드 결정 영역).
        #    trace 에 이 수치가 없어서 "60초 문항의 시간이 어디서 갔는지" 를 서버 로그로 확정할 수 없었다.
        self.last_retries = 0
        self.last_wait_s = 0.0
        self.last_latency_s = 0.0

    # -- 내부 ------------------------------------------------------------
    def _payload(self, messages: list[dict]) -> dict:
        cfg = self.config
        payload: dict = {
            "messages": messages,
            "temperature": cfg.temperature,
            "topP": cfg.top_p,
            "repeatPenalty": cfg.repeat_penalty,
        }
        if cfg.thinking_effort is None:
            payload["maxTokens"] = cfg.max_tokens
        else:
            # 추론 모델은 maxTokens 가 아니라 maxCompletionTokens 를 씁니다.
            # 사고 토큰이 예산을 먹으므로 effort 기본값보다 작게 주면 답변이 잘립니다.
            payload["thinking"] = {"effort": cfg.thinking_effort}
            payload["maxCompletionTokens"] = max(
                cfg.max_tokens, _EFFORT_DEFAULT_TOKENS[cfg.thinking_effort]
            )
        return payload

    # -- 공개 ------------------------------------------------------------
    def complete(self, system: str, user: str) -> HCXResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        url = f"{self._base_url}/v3/chat-completions/{self.config.model}"
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = self._payload(messages)
        retries = 0
        waited = 0.0
        self.last_retries, self.last_wait_s, self.last_latency_s = 0, 0.0, 0.0
        while True:
            t0 = time.perf_counter()
            try:
                resp = self._client.post(
                    url, headers=headers, json=payload, timeout=self.config.timeout_s
                )
            except httpx.HTTPError as e:
                raise HCXError(f"{self.config.label} 요청 실패: {type(e).__name__}: {e}") from e
            latency = time.perf_counter() - t0
            rl = RateLimit.from_headers(resp.headers)

            if resp.status_code == 429 and retries < self.config.max_retries:
                # 토큰 한도가 먼저 걸리므로 reset 창만큼 통째로 기다립니다.
                wait = max(
                    rl.reset_tokens_s or 0.0,
                    rl.reset_requests_s or 0.0,
                    self.config.retry_wait_s,
                )
                self.last_rate_limit = rl
                time.sleep(wait)
                waited += wait
                retries += 1
                self.last_retries, self.last_wait_s = retries, waited
                continue

            if resp.status_code != 200:
                self.last_retries, self.last_wait_s, self.last_latency_s = retries, waited, latency
                raise HCXError(
                    f"{self.config.label} HTTP {resp.status_code}"
                    + (f" (재시도 {retries}회 후)" if retries else "")
                    + f" body={resp.text[:300]}",
                    status_code=resp.status_code,
                    body=resp.text[:1000],
                )
            break

        body = resp.json()
        # CLOVA 는 HTTP 200 이어도 status.code 로 에러를 싣습니다.
        code = (body.get("status") or {}).get("code")
        if code and code != "20000":
            raise HCXError(
                f"{self.config.label} status={code} {(body.get('status') or {}).get('message')}",
                status_code=resp.status_code,
                body=resp.text[:1000],
            )

        result = body.get("result") or {}
        message = result.get("message") or {}
        usage = result.get("usage") or {}
        details = usage.get("completionTokensDetails") or {}

        self.last_rate_limit = rl
        self.last_retries, self.last_wait_s, self.last_latency_s = retries, waited, latency
        return HCXResult(
            text=(message.get("content") or "").strip(),
            latency_s=latency,
            prompt_tokens=usage.get("promptTokens", 0),
            completion_tokens=usage.get("completionTokens", 0),
            thinking_tokens=details.get("thinkingTokens", 0),  # 🔴 개수만. 내용은 버립니다
            finish_reason=result.get("finishReason", ""),
            rate_limit=rl,
            retries=retries,
            wait_s=waited,
            raw=body,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> HCXClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
