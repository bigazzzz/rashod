# Секреты через Mozilla SOPS (age)

Чувствительные переменные в git только в [`secrets.enc.yaml`](../secrets.enc.yaml).

## Ключи (разделены специально)

| Ключ | Куда | Зачем |
|------|------|--------|
| `keys/age-deploy.key` | **только сервер** | `deploy.sh` расшифровывает секреты |
| `keys/age-dev.key` | машина разработчика | правка `sops secrets.enc.yaml` |

Личный age-ключ для деплоя **не используется**. На сервер копируйте только `age-deploy.key`.

Публичные ключи прописаны в [`.sops.yaml`](../.sops.yaml).

## Что шифруем

| Переменная | Назначение |
|------------|------------|
| `POLLINATIONS_API_KEY` | опциональный ключ Pollinations |
| `OPS_TOKEN` | `/internal/ops/*` |
| `MCP_TOKEN` | Bearer для `/mcp` |
| `ADMIN_PASSWORD` | пароль входа в `/admin` |
| `ADMIN_SESSION_SECRET` | подпись cookie-сессии админки (отдельный random) |

Публичные `DOMAIN`, `PUBLIC_BASE_URL`, … — в обычном `.env` (не в git).

## Редактирование (локально)

```bash
export SOPS_AGE_KEY_FILE=$PWD/keys/age-dev.key
sops secrets.enc.yaml
```

Закоммитьте обновлённый `secrets.enc.yaml`.

## Деплой

SSH на сервер сам делает `git pull` + `deploy.sh`. Скрипт достаёт age-ключ из
`scripts/age-deploy.key.b64` (приватный репозиторий), расшифровывает `secrets.enc.yaml`
→ `.env.secrets` и поднимает compose.

На сервере нужен `.env` с публичными переменными (`DOMAIN`, `PUBLIC_BASE_URL`, …).

Локально для правки секретов:

```bash
export SOPS_AGE_KEY_FILE=$PWD/keys/age-dev.key
sops secrets.enc.yaml
```

## Ротация deploy-ключа

```bash
age-keygen -o keys/age-deploy.key
# обновить recipient deploy в .sops.yaml
SOPS_AGE_KEY_FILE=keys/age-dev.key sops updatekeys secrets.enc.yaml
# скопировать новый age-deploy.key на сервер / обновить AGE_DEPLOY_KEY_B64, удалить старый
```
