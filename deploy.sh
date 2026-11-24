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
COMPOSE_ENV+=(--env-file .env.secrets)

docker compose "${COMPOSE_ENV[@]}" pull || true
docker compose "${COMPOSE_ENV[@]}" up -d --force-recreate --build --pull never --remove-orphans
docker image prune -f
