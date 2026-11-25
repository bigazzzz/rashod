# Мониторинг Поровну

Профиль Compose `observability` запускает Grafana Alloy. Он собирает метрики сайта и MCP из внутренних `/metrics` каждые 30 секунд, метрики CPU, памяти, файловых систем и ввода-вывода хоста, а также логи контейнеров web, mcp и caddy. Дашборд показывает CPU и RSS процессов web/mcp и свободное место на файловой системе базы SQLite. Caddy закрывает внешний доступ к `/metrics`.

## Подключение Grafana Cloud Free

1. Создайте стек на тарифе Free. В Cloud Portal найдите URL записи и ID экземпляров для Prometheus и Loki. Создайте Cloud Access Policy для этого стека с областями `metrics:write` и `logs:write` и выпустите по ней токен. [Управление доступом Grafana Cloud](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/security-and-access/authentication-and-permissions/access-policies/)
2. Внесите значения в `grafana-cloud.enc.yaml` через SOPS. Используйте полный URL Prometheus remote write и полный URL Loki push, указанные в стеке. Значения USER — ID экземпляров соответствующих хранилищ.

   ```yaml
   GRAFANA_METRICS_URL: https://<metrics-host>/api/prom/push
   GRAFANA_METRICS_USER: "<metrics-instance-id>"
   GRAFANA_LOGS_URL: https://<logs-host>/loki/api/v1/push
   GRAFANA_LOGS_USER: "<logs-instance-id>"
   GRAFANA_CLOUD_TOKEN: "<access-policy-token>"
   ```

3. Добавьте зашифрованный файл в Git и запустите штатный деплой. Деплой расшифрует файл во временный dotenv и включит профиль `observability`. В конце выкладки он проверит счётчики отправленных метрик и логов Alloy. Alloy не публикует портов. Он читает файлы хоста и обращается к локальному Docker API для сбора логов. Монтирование сокета с `:ro` само по себе не ограничивает команды Docker API, поэтому доступ к контейнеру Alloy должен оставаться у доверенного оператора.
4. В Grafana импортируйте [дашборд метрик](../observability/dashboard.json) с источником Grafana Cloud Prometheus и [дашборд логов](../observability/loki-dashboard.json) с источником Grafana Cloud Loki. В Explore проверьте `up{job=~"porovnu|porovnu-host"}` в Prometheus и `{job="porovnu"}` в Loki. Успешный результат — три цели со значением 1 и логи всех трёх контейнеров по мере появления записей.

## Поиск по логам

На дашборде «Поровну · Логи Loki» задайте период и выберите один или несколько сервисов. Пустое поле **Фильтр LogQL** показывает все строки выбранных сервисов. Вставьте в него выражение после селектора и нажмите Enter.

| Задача | Фильтр LogQL |
| --- | --- |
| Найти текст | `\|= "timeout"` |
| Найти предупреждения и ошибки | `\| json \| level =~ "(?i)warn(ing)?\|error\|critical"` |
| Найти HTTP-ответы 5xx | `\| json \| status >= 500` |
| Найти запрос по `X-Request-ID` | `\| json \| request_id="<id>"` |

Для полного выражения с собственным селектором откройте **Explore → Loki**. Запрос панели начинается с `{job="porovnu",service=~".+"}` при выборе всех сервисов.

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
