#!/usr/bin/env bash
# Decrypt secrets.enc.yaml → .env.secrets (dotenv) for docker compose.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer the deployed identity on the server. Local runs can use SOPS discovery.
if [[ -z "${SOPS_AGE_KEY_FILE:-}" && -f "$ROOT/keys/age-deploy.key" ]]; then
  export SOPS_AGE_KEY_FILE="$ROOT/keys/age-deploy.key"
fi
ENC_FILE="${SOPS_SECRETS_FILE:-$ROOT/secrets.enc.yaml}"
OUT_FILE="${SOPS_DOTENV_OUT:-$ROOT/.env.secrets}"

if ! command -v sops >/dev/null 2>&1; then
  echo "error: sops not found in PATH (install Mozilla SOPS)" >&2
  exit 1
fi

if [[ ! -f "$ENC_FILE" ]]; then
  echo "error: encrypted secrets file missing: $ENC_FILE" >&2
  exit 1
fi

umask 077
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
sops -d --output-type dotenv "$ENC_FILE" >"$tmp"
mv "$tmp" "$OUT_FILE"
chmod 600 "$OUT_FILE"
trap - EXIT
echo "Wrote $OUT_FILE"
