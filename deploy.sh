#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
git pull
# Prefer registry images; ignore pull failures (ghcr TLS / auth flakes).
docker compose pull || true
# Recreate so Caddyfile/mcp apply. --pull never avoids hard-fail if ghcr is down;
# --build refreshes images from Dockerfiles when needed.
docker compose up -d --force-recreate --build --pull never --remove-orphans
docker image prune -f
