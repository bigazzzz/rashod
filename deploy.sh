#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
git pull
# Prefer registry images; on ghcr TLS blips fall back to local build.
docker compose pull || true
# Recreate so volume-mounted Caddyfile and new services (mcp) always apply.
docker compose up -d --force-recreate --build --remove-orphans
docker image prune -f
