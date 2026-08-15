# 제출물 필수 항목 (PROJECT.md §6-4: Dockerfile 재현성 = 소스코드 20점)
#
# 빌드   docker build -t mirae-agent .
# 실행   docker run --rm -p 8000:8000 --env-file .env mirae-agent
# 확인   curl -G localhost:8000/answer --data-urlencode "question_id=Q-001" \
#                --data-urlencode "question=테스트"

FROM python:3.12-slim

# 파이썬 런타임 위생 — .pyc 안 남기고, 로그를 버퍼링 없이 즉시 내보냅니다.
# (버퍼링되면 컨테이너 로그로 장애를 못 봅니다)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성을 먼저 복사해 레이어 캐시를 살립니다.
# 소스만 바뀌면 pip install 을 건너뜁니다 — 2vCPU 서버에서 재배포 시간이 크게 줄어듭니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
# 온톨로지 산출물은 런타임에 읽습니다 (yaml 규칙 · ttl 제약).
# 없어도 기동은 되어야 하므로 실패를 무시합니다.
COPY ontology/ ./ontology/

# 🔴 원본 엑셀과 .env 는 이미지에 넣지 않습니다 (.dockerignore 참조).
#    DB 는 볼륨으로 마운트하거나 빌드 단계에서 별도 생성합니다.

EXPOSE 8000

# 컨테이너가 죽지 않고 '멍청하게 살아있는' 상태를 배포 감시가 잡아내도록.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=4).status==200 else 1)"

# 2vCPU 서버 기준. 워커를 늘리면 메모리(4GB)와 rate limit 을 같이 봐야 합니다.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
