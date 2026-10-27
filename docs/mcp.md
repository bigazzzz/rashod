# MCP ops-сервер Поровну

Удалённый read-only MCP для Cursor: метрики, health, метаданные событий. Без записи данных и без отзывов.

## Токены

В `.env` на сервере (не в git):

```bash
OPS_TOKEN=длинный-секрет
MCP_TOKEN=длинный-секрет   # можно тот же, что OPS_TOKEN
```

- `OPS_TOKEN` — заголовок `X-Ops-Token` на `/internal/ops/*` внутри Docker-сети.
- `MCP_TOKEN` — `Authorization: Bearer …` на `https://porovnu.su/mcp`.

Пустой `OPS_TOKEN` отключает ops API (404). Пустой `MCP_TOKEN` — MCP отвечает 503.

## Cursor (remote MCP)

В конфиге MCP клиента:

```json
{
  "mcpServers": {
    "porovnu-ops": {
      "url": "https://porovnu.su/mcp",
      "headers": {
        "Authorization": "Bearer ВАШ_MCP_TOKEN"
      }
    }
  }
}
```

## Тулзы

| Tool | Что делает |
|------|------------|
| `health` | Версия, БД, OG dir, флаги конфига (без секретов) |
| `site_stats` | Число событий/трат/OG, уникальные имена участников (не аккаунты) + counters |
| `metrics_summary` | Урезанный снимок Prometheus |
| `event_info` | Мета события по slug (без сумм и имён плательщиков) |
| `public_checks` | Статус `/healthz`, `/`, `/og/site.jpg` |

## Smoke

```bash
# Ops API (из контейнера web или с токеном с хоста через внутренний порт — только внутри сети)
curl -sS -H "X-Ops-Token: $OPS_TOKEN" http://127.0.0.1:8000/internal/ops/health

# MCP без токена → 401
curl -sS -o /dev/null -w '%{http_code}\n' https://porovnu.su/mcp

# MCP с токеном (код не 401)
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $MCP_TOKEN" \
  https://porovnu.su/mcp
```
