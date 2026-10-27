# Секреты через Mozilla SOPS (age)

Чувствительные переменные хранятся в git **только** в зашифрованном виде: [`secrets.enc.yaml`](../secrets.enc.yaml).

## Что шифруем

| Переменная | Назначение |
|------------|------------|
| `POLLINATIONS_API_KEY` | опциональный ключ Pollinations |
| `OPS_TOKEN` | доступ к `/internal/ops/*` |
| `MCP_TOKEN` | Bearer для `https://…/mcp` |

Публичные настройки (`DOMAIN`, `PUBLIC_BASE_URL`, `EVENT_RETENTION_DAYS`) остаются в обычном `.env` (не в git).

## Файлы

- [`.sops.yaml`](../.sops.yaml) — правило шифрования (публичный age-ключ)
- `secrets.enc.yaml` — зашифрованные значения (в git)
- `keys/age.key` — **приватный** age-ключ (**не** в git), `chmod 600`
- `.env.secrets` — расшифрованный dotenv на машине (**не** в git)

## Редактирование секретов

На машине с приватным ключом:

```bash
export SOPS_AGE_KEY_FILE=$PWD/keys/age.key
sops secrets.enc.yaml
```

Сохранить и закоммитить обновлённый `secrets.enc.yaml`.

## Деплой

[`deploy.sh`](../deploy.sh) вызывает [`scripts/sops-decrypt-env.sh`](../scripts/sops-decrypt-env.sh), затем:

```bash
docker compose --env-file .env --env-file .env.secrets up -d …
```

На сервере должны быть:

1. `sops` и `age` в `PATH`
2. `keys/age.key` (или `SOPS_AGE_KEY_FILE=…`)
3. `.env` с публичными переменными

## Новый ключ / ротация

```bash
age-keygen -o keys/age.key
# обновить recipient в .sops.yaml публичным ключом из комментария в age.key
SOPS_AGE_KEY_FILE=keys/age.key sops updatekeys secrets.enc.yaml
```

Скопируйте новый `keys/age.key` на сервер по безопасному каналу и удалите старый.

## Локальный compose

```bash
./scripts/sops-decrypt-env.sh
docker compose --env-file .env --env-file .env.secrets up -d --build
```
