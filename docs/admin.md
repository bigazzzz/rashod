# Админка Поровну

Браузерный UI на `https://porovnu.su/admin` (см. [PLAN.md](../PLAN.md)).

## Секреты

В `secrets.enc.yaml` (через sops) задайте оба значения — иначе `/admin` отвечает **404**:

```bash
export SOPS_AGE_KEY_FILE=$PWD/keys/age-dev.key
sops secrets.enc.yaml
# ADMIN_PASSWORD: "…"
# ADMIN_SESSION_SECRET: "…"   # например: openssl rand -hex 32
```

После деплоя / `sops-decrypt-env.sh` переменные попадают в `.env.secrets` и в контейнер `web`.

`OPS_TOKEN` / `MCP_TOKEN` к админке не относятся.

## Возможности

- Дашборд: health, счётчики, топ-20 событий, топ-20 назначений, график созданий (7/30/90/365 дн.)
- Список и карточка события (без сумм и имён плательщиков)
- Удаление события (+ OG), ручной cleanup, smoke-checks

## Локально

```bash
ADMIN_PASSWORD=dev ADMIN_SESSION_SECRET=dev-session-secret \
  ADMIN_COOKIE_SECURE=0 uvicorn app.main:app --reload
```
