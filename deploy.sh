#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${SKIP_GIT_PULL:-}" != "1" ]]; then
  ok=0
  for i in 1 2 3 4 5; do
    if git pull --ff-only; then ok=1; break; fi
    echo "git pull failed (attempt $i); retrying…" >&2
    sleep $((i * 5))
  done
  [[ "$ok" == 1 ]] || { echo "error: git pull failed" >&2; exit 1; }
fi

if [[ ! -f .env ]]; then
  echo "error: .env missing" >&2
  exit 1
fi

COMPOSE_ENV=(--env-file .env)

if [[ -f .env.secrets && -s .env.secrets ]]; then
  echo "Using .env.secrets"
  COMPOSE_ENV+=(--env-file .env.secrets)
elif [[ -f keys/age-deploy.key && -s keys/age-deploy.key ]]; then
  if ! command -v sops >/dev/null 2>&1; then
    mkdir -p "$HOME/.local/bin"
    curl -fsSL -o "$HOME/.local/bin/sops" \
      https://github.com/getsops/sops/releases/download/v3.9.0/sops-v3.9.0.linux.amd64
    chmod 755 "$HOME/.local/bin/sops"
    export PATH="$HOME/.local/bin:$PATH"
  fi
  SOPS_AGE_KEY_FILE="$PWD/keys/age-deploy.key" ./scripts/sops-decrypt-env.sh
  COMPOSE_ENV+=(--env-file .env.secrets)
else
  echo "error: need .env.secrets or keys/age-deploy.key" >&2
  exit 1
fi

docker compose "${COMPOSE_ENV[@]}" pull || true
docker compose "${COMPOSE_ENV[@]}" up -d --force-recreate --build --pull never --remove-orphans
docker image prune -f
