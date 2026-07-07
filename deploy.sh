#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
git pull
docker compose up --build -d
