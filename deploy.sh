#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
git pull
docker compose pull
# Recreate so volume-mounted Caddyfile and new services (mcp) always apply.
docker compose up -d --force-recreate --remove-orphans
docker image prune -f
