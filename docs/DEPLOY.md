# 🚀 배포 절차 — NCP + Docker + Caddy(HTTPS)

> **목표: 8/19 HTTPS 엔드포인트 생존** (지시서 §4.3 ②)
> 내용은 더미여도 됩니다. **살아 있는 것 자체가 API 40점의 전제**입니다.
>
> 구성: `Caddy(80/443, TLS 자동) → api(FastAPI:8000)` · 도메인 없이 `nip.io` 사용

---

## 0. 전체 그림

```
    주최측 오토배치
          │  HTTPS GET /answer?question_id=&question=
          ▼
  ┌───────────────────────────────────────────┐
  │  NCP Server (Ubuntu 22.04, 2vCPU/4GB)     │
  │                                            │
  │   [Caddy]  :80 :443  ← 외부 노출은 여기뿐  │
  │      │  Let's Encrypt 자동 발급·갱신       │
  │      ▼  reverse_proxy                      │
  │   [api]    :8000     ← 호스트 미노출        │
  └───────────────────────────────────────────┘
          ▲
   ACG 인바운드: 22(내 IP만) · 80 · 443
```

> 📌 **8000 포트는 열지 않습니다.** 지시서엔 *"API 포트 인바운드"* 라고 되어 있지만,
> Caddy가 컨테이너 네트워크 안에서 프록시하므로 외부 노출이 불필요합니다. 열면 HTTP 평문 우회 경로가 생깁니다.

---

## 1. NCP 콘솔 — 서버 개설

| 항목 | 값 | 비고 |
| :--- | :--- | :--- |
| 플랫폼 | **VPC** | Classic 말고 VPC |
| 이미지 | Ubuntu Server 22.04 LTS | |
| 서버 타입 | **2vCPU / 4GB** | PROJECT.md §6-2 명시 사양 |
| 스토리지 | 기본 50GB | Docker 이미지 여유 |
| 인증키 | 신규 생성 → **`.pem` 다운로드** | 🔴 재발급 불가. 잃으면 서버 재생성 |
| 공인 IP | **할당** | 이게 있어야 `nip.io` 가 성립 |

순서: `VPC 생성` → `Subnet 생성(Public)` → `Server 생성` → `공인 IP 할당`

### ACG 인바운드 규칙

| 프로토콜 | 접근 소스 | 포트 | 용도 |
| :--- | :--- | :--- | :--- |
| TCP | **내 IP/32** | 22 | SSH. `0.0.0.0/0` 로 열지 마세요 |
| TCP | `0.0.0.0/0` | 80 | Let's Encrypt HTTP-01 챌린지 · HTTPS 리다이렉트 |
| TCP | `0.0.0.0/0` | 443 | 실제 평가 트래픽 |

> 🔴 **80을 막으면 인증서 발급이 실패합니다.** Caddy가 HTTP-01 챌린지를 씁니다.

### 접속

NCP 콘솔 → 서버 → `관리자 비밀번호 확인` 에 `.pem` 을 올려 root 비밀번호를 받습니다.

```bash
ssh root@<공인IP>
```

---

## 2. 서버 준비

```bash
# Docker + Compose 플러그인
curl -fsSL https://get.docker.com | sh
docker compose version        # v2 확인

# 코드
apt-get update && apt-get install -y git
git clone <레포 URL> /opt/mirae && cd /opt/mirae
```

---

## 3. `.env` 생성 — 🔴 서버에서 직접 만듭니다

**커밋된 적 없고, 커밋해서도 안 됩니다.** `scp` 로 올리거나 아래처럼 직접 작성하세요.

```bash
cd /opt/mirae
cat > .env <<'EOF'
HYPERCLOVA_API_KEY=nv-xxxxxxxxxxxxxxxxxxxx
HYPERCLOVA_BASE_URL=https://clovastudio.stream.ntruss.com
PORT=8000
HOST=0.0.0.0
AGENT_READY=0
SITE_ADDRESS=<공인IP>.nip.io
EOF
chmod 600 .env
```

`SITE_ADDRESS` 예시 — 공인 IP가 `223.130.145.7` 이면:

```
SITE_ADDRESS=223.130.145.7.nip.io
```

---

## 4. 기동

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f caddy      # 인증서 발급 로그 확인
```

Caddy 로그에 `certificate obtained successfully` 가 뜨면 성공입니다.

### 확인

```bash
# 서버 안에서
curl -s localhost/health

# 밖에서 — 이게 평가 경로입니다
curl -s https://<공인IP>.nip.io/health

curl -sG "https://<공인IP>.nip.io/answer" \
  --data-urlencode "question_id=Q-001" \
  --data-urlencode "question=국내 상장 ETF 중 최근 1년 수익률이 가장 높은 채권형 ETF 3개를 알려줘."
```

기대 응답 — **5필드가 전부 있어야 합니다**:

```json
{
  "question_id": "Q-001",
  "question": "...",
  "retrieved_context": "",
  "think_trace": "1. [Normalize] ...",
  "answer": "현재 시스템 구축 중으로 답변을 제공할 수 없습니다."
}
```

---

## 5. 🔴 자주 막히는 지점

| 증상 | 원인 | 조치 |
| :--- | :--- | :--- |
| 인증서 발급 실패 | ACG 80 미개방 | 80 인바운드 추가 |
| 인증서 발급 실패 | 공인 IP 미할당 | `nip.io` 가 해석할 IP가 없음 |
| `too many certificates` | 재배포 반복 | 🔴 **주간 5회 한도.** `caddy_data` 볼륨을 지우지 마세요 |
| 502 Bad Gateway | api 컨테이너 미기동 | `docker compose logs api` |
| 컨테이너는 사는데 응답 없음 | 이미지에 `.env` 없음 | `--env-file` / `env_file` 확인 |
| 빌드 실패 | Windows 로컬 미검증 | 🔴 아래 참조 |

> ⚠️ **Dockerfile 은 로컬에서 검증되지 않았습니다** (개발 PC에 Docker 미설치).
> 서버에서 첫 빌드가 곧 첫 검증입니다. 8/19 당일에 하지 말고 **미리 한 번 돌려 보세요.**

### 재배포

```bash
cd /opt/mirae && git pull && docker compose up -d --build
```

`caddy_data` 는 볼륨이라 재빌드에도 보존됩니다. **`docker compose down -v` 는 쓰지 마세요** — `-v` 가 볼륨을 지웁니다.

---

## 6. 이후 할 일

- [ ] `AGENT_READY=1` — 에이전트 연결 후
- [ ] `answer_question()` 교체 (`src/api/main.py`) — 이 함수 하나만 바꾸면 됩니다
- [ ] 서비스 API 키 한도 확인 → 테스트 키로 30문항을 버티는지 (`docs/bench/hcx_latency.md` §4)
- [ ] 응답 시간 감시 — 주최측 권장 15초
- [ ] ⚠️ **NCP 크레딧 유효기간 9/30.** 서버는 24시간 과금됩니다
