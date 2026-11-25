# Мониторинг Поровну

Профиль Compose `observability` запускает Grafana Alloy. Он собирает метрики сайта и MCP из внутренних `/metrics` каждые 30 секунд, метрики CPU, памяти, файловых систем и ввода-вывода хоста, а также логи контейнеров web, mcp и caddy. Дашборд показывает CPU и RSS процессов web/mcp и свободное место на файловой системе базы SQLite. Caddy закрывает внешний доступ к `/metrics`.

## Подключение Grafana Cloud Free

1. Создайте стек на тарифе Free. В Cloud Portal найдите URL записи и ID экземпляров для Prometheus и Loki. Создайте Cloud Access Policy для этого стека с областями `metrics:write` и `logs:write` и выпустите по ней токен. [Управление доступом Grafana Cloud](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/security-and-access/authentication-and-permissions/access-policies/)
2. Внесите значения в `secrets.enc.yaml` через SOPS. Используйте полный URL Prometheus remote write и полный URL Loki push, указанные в стеке. Значения USER — ID экземпляров соответствующих хранилищ.

   ```yaml
   GRAFANA_METRICS_URL: https://<metrics-host>/api/prom/push
   GRAFANA_METRICS_USER: "<metrics-instance-id>"
   GRAFANA_LOGS_URL: https://<logs-host>/loki/api/v1/push
   GRAFANA_LOGS_USER: "<logs-instance-id>"
   GRAFANA_CLOUD_TOKEN: "<access-policy-token>"
   ```

3. В `.env` на сервере добавьте `observability` к `COMPOSE_PROFILES` и запустите штатный деплой. Alloy не публикует портов. Он читает файлы хоста и обращается к локальному Docker API для сбора логов. Монтирование сокета с `:ro` само по себе не ограничивает команды Docker API, поэтому доступ к контейнеру Alloy должен оставаться у доверенного оператора.
4. В Grafana импортируйте [dashboard.json](../observability/dashboard.json) и выберите встроенные источники Prometheus и Loki. Проверьте в Explore запросы `up{job=~"porovnu|porovnu-host"}` и `{job="porovnu"}`. Успешный результат — три цели со значением 1 и логи всех трёх контейнеров по мере появления записей. Из HTTP-заголовка `X-Request-ID` идентификатор можно подставить в запрос `{job="porovnu"} | json | request_id="<id>"`.

## Внешние проверки и алерты

В Grafana Cloud → Synthetics создайте проверки с интервалом 5 минут из двух публичных локаций. Уведомления встроенных проверок можно оставить выключенными, если используются правила ниже.

| Имя | Проверка |
| --- | --- |
| `porovnu-health` | GET `https://porovnu.su/healthz`, статус 200 |
| `porovnu-home` | GET `https://porovnu.su/`, статус 200 |
| `porovnu-mcp` | POST `https://porovnu.su/mcp`, метод JSON-RPC `initialize`, в ответе есть `protocolVersion` |

Для MCP укажите `Content-Type: application/json` и `Accept: application/json, text/event-stream`. Подойдёт HTTP-проверка с таким телом и проверкой ответа на строку `protocolVersion`.

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"porovnu-monitor","version":"1.0"}}}
```

В Alerting импортируйте [alerts.yml](../observability/alerts.yml) как Prometheus YAML в Grafana-managed alerts, выбрав источником Prometheus из Cloud. Если импорт недоступен, создайте правила вручную из выражений и интервалов в файле. Направьте уведомления группы `porovnu` в выбранный Contact point и отправьте тестовое уведомление. Во внешнем алерте проверяется `porovnu-health`; остальные синтетические проверки видны отдельно.

[HTTP-проверки Grafana](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/synthetic-monitoring/create-checks/checks/http/) · [Импорт правил алертов](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/alerting-migration/)
