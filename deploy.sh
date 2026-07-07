#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
git pull
docker compose pull
docker compose up -d
docker image prune -f
