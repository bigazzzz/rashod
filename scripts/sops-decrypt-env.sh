#!/usr/bin/env bash
# Decrypt secrets.enc.yaml → .env.secrets (dotenv) for docker compose.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

KEY_FILE="${SOPS_AGE_KEY_FILE:-$ROOT/keys/age.key}"
ENC_FILE="${SOPS_SECRETS_FILE:-$ROOT/secrets.enc.yaml}"
OUT_FILE="${SOPS_DOTENV_OUT:-$ROOT/.env.secrets}"

if ! command -v sops >/dev/null 2>&1; then
  echo "error: sops not found in PATH (install Mozilla SOPS)" >&2
  exit 1
fi

if [[ ! -f "$KEY_FILE" ]]; then
  echo "error: age private key missing: $KEY_FILE" >&2
  echo "Copy keys/age.key to the server (chmod 600) or set SOPS_AGE_KEY_FILE." >&2
  exit 1
fi

if [[ ! -f "$ENC_FILE" ]]; then
  echo "error: encrypted secrets file missing: $ENC_FILE" >&2
  exit 1
fi

export SOPS_AGE_KEY_FILE="$KEY_FILE"
umask 077
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
sops -d --output-type dotenv "$ENC_FILE" >"$tmp"
mv "$tmp" "$OUT_FILE"
chmod 600 "$OUT_FILE"
trap - EXIT
echo "Wrote $OUT_FILE"
