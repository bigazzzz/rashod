#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

# Always re-exec latest logic after pull (bash keeps reading the old inode otherwise).
if [[ "${SKIP_GIT_PULL:-}" != "1" ]]; then
  ok=0
  for i in 1 2 3 4 5; do
    if git pull --ff-only; then ok=1; break; fi
    echo "git pull failed (attempt $i); retrying…" >&2
    sleep $((i * 5))
  done
  [[ "$ok" == 1 ]] || { echo "error: git pull failed" >&2; exit 1; }
  export SKIP_GIT_PULL=1
  exec "$PWD/deploy.sh"
fi

if [[ ! -f .env ]]; then
  echo "error: .env missing" >&2
  exit 1
fi

COMPOSE_ENV=(--env-file .env)

ensure_sops() {
  if command -v sops >/dev/null 2>&1; then
    return 0
  fi
  mkdir -p "$HOME/.local/bin"
  curl -fsSL -o "$HOME/.local/bin/sops" \
    https://github.com/getsops/sops/releases/download/v3.9.0/sops-v3.9.0.linux.amd64
  chmod 755 "$HOME/.local/bin/sops"
  export PATH="$HOME/.local/bin:$PATH"
}

# Always re-decrypt: .env.secrets is derived from secrets.enc.yaml.
# Skipping when the file already exists leaves new keys (e.g. admin) unset.
KEY_FILE="${SOPS_AGE_KEY_FILE:-$PWD/keys/age-deploy.key}"
if [[ ! -s "$KEY_FILE" ]]; then
  echo "error: provision the deploy age key on the server before deploying" >&2
  exit 1
fi
ensure_sops
SOPS_AGE_KEY_FILE="$KEY_FILE" ./scripts/sops-decrypt-env.sh
cloudflare_env=$(mktemp)
grafana_env=
trap 'rm -f -- "$cloudflare_env" ${grafana_env:+"$grafana_env"}' EXIT
SOPS_AGE_KEY_FILE="$KEY_FILE" SOPS_SECRETS_FILE="$PWD/cloudflare.enc.yaml" \
  SOPS_DOTENV_OUT="$cloudflare_env" ./scripts/sops-decrypt-env.sh
# Compose normally gives shell variables precedence over --env-file.
unset CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN
COMPOSE_ENV+=(--env-file .env.secrets --env-file "$cloudflare_env")

if [[ -f grafana-cloud.enc.yaml ]]; then
  grafana_env=$(mktemp)
  SOPS_AGE_KEY_FILE="$KEY_FILE" SOPS_SECRETS_FILE="$PWD/grafana-cloud.enc.yaml" \
    SOPS_DOTENV_OUT="$grafana_env" ./scripts/sops-decrypt-env.sh
  unset GRAFANA_METRICS_URL GRAFANA_METRICS_USER GRAFANA_LOGS_URL GRAFANA_LOGS_USER GRAFANA_CLOUD_TOKEN
  COMPOSE_ENV+=(--env-file "$grafana_env" --profile observability)
fi

docker compose "${COMPOSE_ENV[@]}" pull || true
docker compose "${COMPOSE_ENV[@]}" up -d --force-recreate --build --pull never --remove-orphans

check_alloy_delivery() {
  docker compose "${COMPOSE_ENV[@]}" exec -T alloy timeout 5 bash -s <<'BASH'
set -e
exec 3<>/dev/tcp/127.0.0.1/12345
printf 'GET /metrics HTTP/1.0\r\nHost: localhost\r\n\r\n' >&3
awk '
  /^prometheus_remote_storage_samples_total[{ ]/ && $NF > 0 { metrics = 1 }
  /^loki_write_sent_entries_total[{ ]/ && $NF > 0 { logs = 1 }
  END { exit !(metrics && logs) }
' <&3
BASH
}

if [[ -n "$grafana_env" ]]; then
  alloy_delivery_confirmed=
  for attempt in {1..12}; do
    if check_alloy_delivery 2>/dev/null; then
      echo "Grafana Cloud accepted metrics and logs from Alloy."
      alloy_delivery_confirmed=1
      break
    fi
    if [[ "$attempt" != 12 ]]; then sleep 5; fi
  done
  if [[ -z "$alloy_delivery_confirmed" ]]; then
    echo "warning: Alloy did not confirm delivery of both signals during deployment." >&2
  fi
fi

docker image prune -f
