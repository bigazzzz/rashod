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

Публичные `DOMAIN`, `PUBLIC_BASE_URL`, … — в обычном `.env` (не в git).

## Редактирование (локально)

```bash
export SOPS_AGE_KEY_FILE=$PWD/keys/age-dev.key
sops secrets.enc.yaml
```

Закоммитьте обновлённый `secrets.enc.yaml`.

## Деплой

CI (secret `AGE_DEPLOY_KEY_B64`) расшифровывает `secrets.enc.yaml` на runner’е и копирует
`.env.secrets` на сервер по SCP, затем по SSH запускает `deploy.sh`.

На сервере нужен `.env` с публичными переменными (`DOMAIN`, `PUBLIC_BASE_URL`, …).

Задать secret один раз (локально):

```bash
base64 -w0 < keys/age-deploy.key | gh secret set AGE_DEPLOY_KEY_B64
```

## Ротация deploy-ключа

```bash
age-keygen -o keys/age-deploy.key
# обновить recipient deploy в .sops.yaml
SOPS_AGE_KEY_FILE=keys/age-dev.key sops updatekeys secrets.enc.yaml
# скопировать новый age-deploy.key на сервер / обновить AGE_DEPLOY_KEY_B64, удалить старый
```
