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
mkdir -p keys
if [[ ! -s keys/age-deploy.key ]]; then
  if [[ -f scripts/age-deploy.key.b64 ]]; then
    # Private-repo bootstrap so server auto-deploy can decrypt without SSH file upload.
    base64 -d < scripts/age-deploy.key.b64 > keys/age-deploy.key
    chmod 600 keys/age-deploy.key
    echo "Restored keys/age-deploy.key from scripts/age-deploy.key.b64"
  elif [[ -n "${AGE_DEPLOY_KEY_B64:-}" ]]; then
    printf '%s' "$AGE_DEPLOY_KEY_B64" | base64 -d > keys/age-deploy.key
    chmod 600 keys/age-deploy.key
  fi
fi
if [[ -s keys/age-deploy.key ]]; then
  ensure_sops
  SOPS_AGE_KEY_FILE="$PWD/keys/age-deploy.key" ./scripts/sops-decrypt-env.sh
fi

if [[ -f .env.secrets && -s .env.secrets ]]; then
  echo "Using .env.secrets"
  COMPOSE_ENV+=(--env-file .env.secrets)
else
  echo "error: need .env.secrets (decrypt secrets.enc.yaml)" >&2
  exit 1
fi

docker compose "${COMPOSE_ENV[@]}" pull || true
docker compose "${COMPOSE_ENV[@]}" up -d --force-recreate --build --pull never --remove-orphans
docker image prune -f
