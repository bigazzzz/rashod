#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
git pull

if [[ ! -f .env ]]; then
  echo "error: .env missing (non-secret config: DOMAIN, PUBLIC_BASE_URL, …)" >&2
  echo "Copy from .env.example and fill public values." >&2
  exit 1
fi

# Deploy decrypt uses the dedicated server key only (not a personal age key).
KEY_FILE="${SOPS_AGE_KEY_FILE:-$PWD/keys/age-deploy.key}"
COMPOSE_ENV=(--env-file .env)
if [[ -f "$KEY_FILE" ]]; then
  SOPS_AGE_KEY_FILE="$KEY_FILE" ./scripts/sops-decrypt-env.sh
  COMPOSE_ENV+=(--env-file .env.secrets)
elif [[ -f .env.secrets ]]; then
  echo "warn: $KEY_FILE missing; reusing existing .env.secrets" >&2
  COMPOSE_ENV+=(--env-file .env.secrets)
else
  echo "error: deploy age key missing ($KEY_FILE) and no .env.secrets" >&2
  echo "Copy keys/age-deploy.key to the server (chmod 600). See docs/sops.md" >&2
  exit 1
fi

# Prefer registry images; ignore pull failures (ghcr TLS / auth flakes).
docker compose "${COMPOSE_ENV[@]}" pull || true
# Recreate so Caddyfile/mcp apply. --pull never avoids hard-fail if ghcr is down;
# --build refreshes images from Dockerfiles when needed.
docker compose "${COMPOSE_ENV[@]}" up -d --force-recreate --build --pull never --remove-orphans
docker image prune -f
