#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${SKIP_GIT_PULL:-}" != "1" ]]; then
  ok=0
  for i in 1 2 3 4 5; do
    if git pull --ff-only; then
      ok=1
      break
    fi
    echo "git pull failed (attempt $i); retrying…" >&2
    sleep $((i * 5))
  done
  if [[ "$ok" != 1 ]]; then
    echo "error: git pull failed after retries" >&2
    exit 1
  fi
fi

if [[ ! -f .env ]]; then
  echo "error: .env missing (non-secret config: DOMAIN, PUBLIC_BASE_URL, …)" >&2
  echo "Copy from .env.example and fill public values." >&2
  exit 1
fi

COMPOSE_ENV=(--env-file .env)

if [[ "${SKIP_SOPS_DECRYPT:-}" == "1" ]] && [[ -f .env.secrets ]]; then
  echo "Using pre-written .env.secrets (CI)"
  COMPOSE_ENV+=(--env-file .env.secrets)
else
  # Optional local/server path: age-deploy key → sops decrypt
  if [[ -n "${AGE_DEPLOY_KEY_B64:-}" ]]; then
    mkdir -p keys
    umask 077
    echo "$AGE_DEPLOY_KEY_B64" | base64 -d > keys/age-deploy.key
    chmod 600 keys/age-deploy.key
  fi

  ensure_sops() {
    if command -v sops >/dev/null 2>&1; then
      return 0
    fi
    local bindir="${HOME}/.local/bin"
    mkdir -p "$bindir"
    local dest="${bindir}/sops"
    echo "sops not found; installing to ${dest}"
    curl -fsSL -o "$dest" \
      "https://github.com/getsops/sops/releases/download/v3.9.0/sops-v3.9.0.linux.amd64"
    chmod 755 "$dest"
    export PATH="${bindir}:${PATH}"
    command -v sops >/dev/null
  }

  KEY_FILE="${SOPS_AGE_KEY_FILE:-$PWD/keys/age-deploy.key}"
  if [[ -f "$KEY_FILE" ]] && [[ -s "$KEY_FILE" ]]; then
    ensure_sops
    SOPS_AGE_KEY_FILE="$KEY_FILE" ./scripts/sops-decrypt-env.sh
    COMPOSE_ENV+=(--env-file .env.secrets)
  elif [[ -f .env.secrets ]]; then
    echo "warn: age key missing; reusing existing .env.secrets" >&2
    COMPOSE_ENV+=(--env-file .env.secrets)
  else
    echo "error: no .env.secrets and no age-deploy key" >&2
    echo "CI should decrypt SOPS and pass OPS_TOKEN/MCP_TOKEN. See docs/sops.md" >&2
    exit 1
  fi
fi

docker compose "${COMPOSE_ENV[@]}" pull || true
docker compose "${COMPOSE_ENV[@]}" up -d --force-recreate --build --pull never --remove-orphans
docker image prune -f
