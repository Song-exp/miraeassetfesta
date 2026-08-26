#!/usr/bin/env bash
# NCP 배포 — 코드 갱신 + DB 반입 + 기동 확인.
#
#   bash deploy/deploy.sh              # 전체 (코드 + DB + 기동)
#   bash deploy/deploy.sh --code-only  # 코드만 (DB 그대로)
#   bash deploy/deploy.sh --db-only    # DB만 반입 후 restart
#   bash deploy/deploy.sh --yaml-only  # 🚀 온톨로지 규칙만 반영 (git pull + restart, 약 5초)
#
# --yaml-only 는 실험 루프용입니다. compose 가 ./ontology 를 마운트하므로 enums/*.yaml 의
# query_rules 를 고친 경우 재빌드도 DB 재전송도 필요 없습니다.
#   ⚠️ shared/*.yaml(개체·alias)을 고쳤다면 kg_* 를 다시 만들어야 하므로 --db-only 가 필요합니다
#      (로컬에서 build_ontology.py 를 먼저 돌린 뒤).
#
# 🔴 이 스크립트는 **로컬에서** 실행합니다. 22번 포트는 ACG 로 특정 IP 에만 열려 있으므로
#    허용된 자리에서 돌려야 합니다.
#
# 전제
#   · 서버에 /opt/mirae 가 git clone 되어 있고 origin 을 pull 할 수 있다 (DEPLOY.md §4)
#   · secrets/mirae-api-key.pem 이 있다
#   · 서버 .env 에 HYPERCLOVA_API_KEY · SITE_ADDRESS 가 들어 있다
set -euo pipefail

IP="${MIRAE_IP:-49.50.134.229}"
KEY="${MIRAE_KEY:-secrets/mirae-api-key.pem}"
USER="${MIRAE_USER:-root}"
REMOTE="/opt/mirae"
DB="data/financial_products.db"
MODE="${1:-all}"

# 오타가 전체 배포로 떨어지지 않게 막는다 — 모르는 인자는 실행하지 않는다
case "$MODE" in
  all|--code-only|--db-only|--yaml-only) ;;
  -h|--help)
    sed -n '2,12p' "$0" | sed 's/^# \?//'
    exit 0 ;;
  *)
    echo "알 수 없는 인자: $MODE"
    echo "사용법: bash deploy/deploy.sh [--code-only | --db-only | --yaml-only]"
    exit 2 ;;
esac

ssh_() { ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER@$IP" "$@"; }
say()  { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }

# ── 0. 로컬 점검 — 깨진 것을 올리지 않는다 ──────────────────────────────
say "0. 로컬 점검"
[ -f "$KEY" ] || { echo "❌ 키 없음: $KEY"; exit 1; }
[ -f "$DB" ]  || { echo "❌ DB 없음: $DB — build_db.py → load_external_* → build_ontology.py 순서로 만드세요"; exit 1; }

python -m pytest tests -q || { echo "❌ 테스트 실패 — 배포 중단"; exit 1; }
python eval/run_gold_check.py | tail -1

# DB 가 v2 이고 KG 까지 들어있는지 — 스텁 시절 DB 를 올리는 사고를 막는다
python - <<'PY'
import sqlite3, sys
c = sqlite3.connect("file:data/financial_products.db?mode=ro", uri=True)
have = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
need = {"domestic_bonds","domestic_etfs","overseas_etfs","public_funds",
        "ext_etf_holdings","ext_ovs_etf_holdings","ext_fund_holdings","ext_fund_page",
        "kg_node","kg_alias","kg_edge","kg_closure"}
missing = need - have
if missing:
    sys.exit(f"❌ DB 에 테이블 누락: {sorted(missing)} — 외부 데이터·KG 까지 만든 DB 여야 합니다")
ver = c.execute("select distinct data_version, as_of from build_info").fetchall()
print(f"   DB 확인 — 14테이블 · build_info {ver}")
PY

LOCAL_MD5=$(python -c "import hashlib;print(hashlib.md5(open('$DB','rb').read()).hexdigest())")
echo "   로컬 md5 $LOCAL_MD5"

# ── 1-Fast. 온톨로지 규칙만 반영 ────────────────────────────────────────
if [ "$MODE" = "--yaml-only" ]; then
  say "1-Fast. 온톨로지 규칙 반영 (git pull + restart)"
  ssh_ "cd $REMOTE && git pull --ff-only && git log --oneline -1 && docker compose restart api"
  sleep 5
  curl -s -m 20 "https://$IP.nip.io/health"; echo
  echo "✅ 반영 완료. shared/*.yaml 을 고쳤다면 이걸로는 부족합니다 — --db-only 로 kg_* 도 보내세요."
  exit 0
fi

# ── 1. 코드 ─────────────────────────────────────────────────────────────
if [ "$MODE" != "--db-only" ]; then
  say "1. 코드 갱신 (git pull)"
  ssh_ "cd $REMOTE && git pull --ff-only && git log --oneline -1"

  say "1-B. 서버 .env 점검"
  ssh_ "cd $REMOTE && for k in HYPERCLOVA_API_KEY SITE_ADDRESS AGENT_READY RELOAD_TOKEN CHAT_TOKEN; do
          if grep -q \"^\$k=.\" .env 2>/dev/null; then echo \"   ✅ \$k 설정됨\"; else echo \"   ⚠️  \$k 비어있음/없음\"; fi
        done"
  echo "   ⚠️  AGENT_READY=1 이 아니면 에이전트가 '구축 중' 으로 답합니다."
  echo "      서버에서: cd $REMOTE && nano .env   (AGENT_READY=1 · RELOAD_TOKEN · CHAT_TOKEN)"
fi

# ── 2. DB 반입 ──────────────────────────────────────────────────────────
if [ "$MODE" != "--code-only" ]; then
  say "2. DB 반입 (263MB — 압축 전송)"
  gzip -c "$DB" > /tmp/fp.db.gz
  echo "   압축 $(du -h /tmp/fp.db.gz | cut -f1)"
  ssh_ "mkdir -p $REMOTE/data $REMOTE/logs"
  scp -i "$KEY" /tmp/fp.db.gz "$USER@$IP:$REMOTE/data/"
  ssh_ "cd $REMOTE/data && gunzip -f -c fp.db.gz > financial_products.db && rm fp.db.gz && md5sum financial_products.db"
  echo "   🔴 위 md5 가 로컬($LOCAL_MD5)과 같은지 확인하세요."
fi

# ── 3. 기동 ─────────────────────────────────────────────────────────────
say "3. 컨테이너 기동"
if [ "$MODE" = "--db-only" ]; then
  # DB 파일만 갈았을 때도 restart 는 필수 — 컨테이너가 잡은 fd 는 옛 inode 를 가리킨다
  ssh_ "cd $REMOTE && docker compose restart api && docker compose ps"
else
  ssh_ "cd $REMOTE && docker compose up -d --build && docker compose ps"
fi

# ── 4. 확인 ─────────────────────────────────────────────────────────────
say "4. 밖에서 확인"
sleep 5
echo "-- /health"
curl -s -m 20 "https://$IP.nip.io/health"; echo
echo "-- /answer (게이트 기각 경로 — HCX 호출 0회)"
curl -sG -m 30 "https://$IP.nip.io/answer" \
  --data-urlencode "question_id=DEPLOY-001" \
  --data-urlencode "question=신용등급 AAAA인 채권 알려줘" | python -m json.tool
echo
echo "✅ 배포 절차 종료. agent_ready 가 false 면 서버 .env 의 AGENT_READY=1 을 확인하세요."
echo "   팀 실험 UI:  https://$IP.nip.io/chat?t=<CHAT_TOKEN>"
