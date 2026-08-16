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
  │  NCP Server (Ubuntu 24.04, 2vCPU/4GB)     │
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

> 📖 **화면별 클릭 순서와 입력값은 `docs/NCP_CONSOLE.md` 에 있습니다.** 아래는 요약입니다.

| 항목 | 값 | 비고 |
| :--- | :--- | :--- |
| 플랫폼 | **VPC** | Classic 말고 VPC |
| 이미지 | Ubuntu Server **24.04 LTS** | 22.04 도 무방. 앱이 컨테이너 안이라 호스트 버전 무관 |
| 서버 타입 | **2vCPU / 4GB** | PROJECT.md §6-2 명시 사양 |
| 요금제 | **시간 요금제** | 정지 기간 제한·중도 해지 제약을 피하려고 |
| 스토리지 | **50GB** | 주최측 권장 20GB 상향. 9/7~9/20 은 정지 불가 = 증설 창구 없음 |
| 인증키 | 신규 생성 → **`.pem` 다운로드** | 🔴 재발급 불가. 잃으면 서버 재생성 |
| 공인 IP | **할당** | 이게 있어야 `nip.io` 가 성립 |

순서: `VPC 생성` → `Subnet 생성(Public)` → `ACG 규칙` → `Server 생성` → `공인 IP 할당`

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

### 🔴 DB 반입 — 지금은 서버에 DB가 없습니다

스텁은 DB를 안 읽어서 이 상태로도 뜹니다. **에이전트를 붙이는 순간 걸립니다.**

```
data/financial_products.db   95MB
  ├ .gitignore:60    data/       → git clone 해도 안 따라옴
  ├ .dockerignore    *.db, data/ → 이미지에도 안 들어감
  └ docker-compose.yml api:      → ✅ volumes 반영 완료 (아래 참조)
```

원본 엑셀도 git에 없으므로 **서버에서 재생성도 불가능**합니다. 반입해야 합니다.

#### ① 보낼 파일을 확인합니다 — 로컬에 DB가 **2개** 있습니다

```
data/financial_products.db             ← 🔴 이것을 보냅니다 (선행 0 수정본, dd9b482)
data/financial_products.pre_dtype.db   ← 수정 전 백업. 보내면 안 됩니다
```

이름이 비슷해서 탭 완성으로 잘못 잡기 쉽습니다. **보내기 전에 한 줄로 판별하세요.**

```bash
python -c "import sqlite3;print(sqlite3.connect('data/financial_products.db').execute(\"select typeof(or_co_xtn_itt_cd), or_co_xtn_itt_cd from public_funds limit 1\").fetchone())"
```

| 출력 | 판정 |
| :--- | :--- |
| `('text', '00040010')` | ✅ 수정본. 이걸 보냅니다 |
| `('real', 40010.0)` | 🔴 수정 전. 보내면 **코드북 조인이 전부 0건**이 됩니다 |

#### ② 🔴 서버에 디렉터리를 먼저 만듭니다

`data/` 는 `.gitignore` 로 막혀 있어 **`git clone` 후 서버에 존재하지 않습니다.**
바로 `scp` 하면 `No such file or directory` 로 실패합니다.

```bash
# 서버에서
mkdir -p /opt/mirae/data
```

#### ③ 전송

```bash
# 로컬에서 — 95MB, 회선에 따라 1~5분
scp -i <키>.pem data/financial_products.db root@<공인IP>:/opt/mirae/data/

# 서버에서 검증 — 크기가 로컬과 같은지
ls -l /opt/mirae/data/financial_products.db
```

#### ④ 마운트 — **이미 반영되어 있습니다**

`docker-compose.yml` 의 `api` 서비스에 아래가 들어가 있습니다. 서버에서 편집할 필요 없습니다.

```yaml
  api:
    volumes:
      - ./data:/app/data:ro      # 🔴 읽기 전용
```

> 📌 `:ro` 를 붙이는 이유 — 에이전트는 조회만 합니다. 쓰기 권한을 주면 컨테이너가
> DB를 건드릴 여지가 생깁니다.
>
> 📌 **읽기 전용인데 SELECT가 되는 이유** — 이 DB는 `journal_mode=delete` 입니다.
> WAL 모드였다면 `-wal`·`-shm` 파일을 만들지 못해 **조회 자체가 막힙니다.**
> `build_db.py` 를 고칠 때 journal_mode를 바꾸지 마세요.
>
> 📌 바인드 마운트라 **재빌드해도 유지됩니다.** DB는 한 번만 보내면 됩니다.
> (`caddy_data` 와 달리 named volume이 아니라 호스트 디렉터리를 직접 봅니다)

### 나머지

- [ ] `AGENT_READY=1` — 에이전트 연결 후
- [ ] `answer_question()` 교체 (`src/api/main.py`) — 이 함수 하나만 바꾸면 됩니다
- [ ] 서비스 API 키 한도 확인 → 테스트 키로 30문항을 버티는지 (`docs/bench/hcx_latency.md` §4)
- [ ] 응답 시간 감시 — 주최측 권장 15초
- [ ] ⚠️ **NCP 크레딧 유효기간 9/30.** 서버는 24시간 과금됩니다
