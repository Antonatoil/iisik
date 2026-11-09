# ЛР7. Надёжность и оптимизация распределённой платформы (вариант 27)

**Базовая версия:** ЛР6, Git commit `4572eab`. Вся архитектура ЛР6 сохранена:
GraphQL Gateway + отдельный Auth + 7 gRPC-сервисов (по одному владельцу БД A/T/L/P/R/N/X),
Kafka/KRaft, PostgreSQL, Redis. Продуктовые данные не мигрируются и не сбрасываются.

## 1. Выполненные требования

| Требование | Реализация | Где проверить |
| --- | --- | --- |
| Deadline gRPC | Общий бюджет 9 с для чтения / 12 с для записи; отдельная попытка до 3.5 с для чтения | `app/resilience/grpc_policy.py` |
| Retry | До 3 попыток только для идемпотентных RPC чтения; задержка 0.15/0.30 с + jitter | `grpc_policy.py`, `tests/test_lab7.py` |
| Ошибки gRPC | UNAVAILABLE/DEADLINE_EXCEEDED -> GraphQL SERVICE_UNAVAILABLE/SERVICE_TIMEOUT; бизнес-ошибки не ретраятся | `app/transport/grpc_ports.py` |
| Ошибки Kafka | Outbox не удаляет событие до ack; consumer сохраняет inbox и commit offset после транзакции; после 5 неудач - DLQ | `app/events/{publisher,consumer}.py` |
| Redis-кеш | Read-through каталогов: subjects, teachers, related metrics; TTL 45 с; DB 1 отдельно от JWT DB 0 | `app/resilience/catalog_cache.py` |
| Инвалидация | Версия пространства ключей увеличивается после изменений Catalog и Kafka RatingUpdated/PopularityUpdated | `app/grpc/server.py`, `app/events/consumer.py` |
| Логирование | JSON-поля event, correlation_id, service, method, attempt, result, elapsed_ms; без JWT/паролей | `app/resilience/telemetry.py` |
| Бизнес-сценарии | bookLesson не дублируется retry; payment commit в DB-P не откатывается из-за временного сбоя Learning: Kafka PaymentCompleted завершает синхронизацию | `app/transport/workflows.py` |

## 2. Почему retry НЕ включен для каждой Mutation

Получив `DEADLINE_EXCEEDED`, клиент **не знает**, была ли запись уже закоммичена.
Повторение `bookLesson` без контроля может породить дубль. Поэтому:
- автоматический повтор производится только у read-only методов из явного allowlist;
- write-RPC выполняется **один раз** с timeout 12 с;
- предусмотренные с ЛР4 `operationId` и `command_receipts` позволяют клиенту безопасно **повторить команду с тем же operationId**;
- бизнес-отказы `FORBIDDEN`, `BAD_USER_INPUT`, `INVALID_STATE` не ретраятся.

`registerPayment` сначала фиксирует оплату и событие PaymentCompleted в DB-P.
Если следующая синхронная попытка `ApplyPaymentToBooking` завершается `SERVICE_UNAVAILABLE`/`SERVICE_TIMEOUT`,
GraphQL возвращает подтверждённый платёж, а Learning consumer применяет событие из Kafka позднее.
Это **eventual consistency**, а не одна распределённая транзакция. Если Kafka недоступна,
событие остается в outbox до возобновления работы брокера.

## 3. Кеш и корректность

Кешируются **только каталожные чтения** `SearchTeachers`, `GetTeacher`, `ListSubjects`,
`GetTeacherSubjects`, `GetTeacherMetrics`. `GetTeachingOffer`, свободные слоты и операции
бронирования **не кешируются**: их данные должны проверяться актуально.

Redis DB 0 хранит JWT-сессии, Redis DB 1 - кеш. Отказ кеша не должен прекращать
каталожное чтение: происходит прямой вызов SQL. Однако при отказе Redis DB 0
Auth Service не должен пропускать запросы с неподтвержденной сессией (fail-closed).

Ключи `lab7:catalog:v1:<generation>:<sha256(normalized_args)>`.
После изменения данных `INCR lab7:catalog:v1:generation` делает старые записи недоступными,
а TTL автоматически удаляет их. При недоступности Redis после коммита инвалидация
может не состояться; TTL 45 с ограничивает период устаревания. Это учебный
read-through кеш, а не сильная согласованность или распределенная блокировка.

## 4. Kafka, DLQ, восстановление

`Kafka producer -> tutor.events.v1 -> consumers T/N/X/L`.
Временные ошибки БД или обработки: до 5 попыток с экспоненциальным backoff;
после них сообщение с контекстом ошибки поступает в `tutor.events.dlq.v1`.
Исходный offset подтверждается **только после ack от DLQ**. Если DLQ недоступен,
offset не коммитится и событие остается для последующего повтора.

Семантика — **at-least-once**, а не exactly-once end-to-end. Таблица `event_inbox`
предотвращает повторный бизнес-эффект при редоставке. Факт ошибки из DLQ
требует анализа и ручного повторного воспроизведения после устранения причины;
перевод в DLQ не означает, что бизнес-событие успешно применено.

## 5. Запуск и регрессии

```powershell
cd 'D:\бгуир\Иисик\lab3-7'
docker compose config -q
docker compose up -d --build
docker compose ps
docker compose build tests
docker compose run --rm tests
Invoke-RestMethod http://localhost:8000/ready
```

**Критерий:** все старые тесты ЛР3–ЛР6 (33) и новые ЛР7 должны завершиться без fail.
До первого фактического прогона в Docker количество успешных тестов не заявляется.

### Демонстрация Redis HIT/MISS

С помощью `scripts/demo_lab7.ps1` дважды вызовите защищённую GraphQL Query `subjects`.
В логах Catalog ищите JSON-события `catalog_cache` с `result=miss` и `result=hit`.
Подходящий список ключей (без вывода пароля):

```powershell
docker compose exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" -n 1 --scan --pattern "lab7:catalog:v1:*" 2>/dev/null'
docker compose logs --tail=100 catalog
```

Запросы `bookLesson` и `GetTeachingOffer` не используют этот кеш.

### Демонстрация временной ошибки gRPC (осторожно, временно влияет на Catalog)

Сначала получить JWT через `demo_lab7.ps1`, затем:

```powershell
docker compose stop catalog
# Пока сервис выключен, повторить Query subjects с действующим JWT;
# получить SERVICE_UNAVAILABLE, увидеть <= 3 grpc_client attempt в логах gateway.
docker compose start catalog
docker compose ps
```

При недоступности Catalog остальные сервисы продолжают работать. `/ready`
по контракту может возвращать HTTP 503 в период частичного отказа — это **правильный** сигнал готовности.

### Демонстрация DLQ

В тестовом окружении можно подать некорректный JSON в `tutor.events.v1`.
Consumer отклонит его, запишет причину и исходные координаты в DLQ,
не зависнет на нём. Не выполняйте такую инъекцию в рабочей системе.

### Сквозные логи

```powershell
docker compose logs --tail=120 gateway auth catalog learning payments analytics notifications
```

`X-Correlation-ID` принимается от клиента (валидация длины и символов) или генерируется Gateway;
затем передается в gRPC metadata `x-correlation-id`. В событиях Kafka используется
`correlation_id`, заданный бизнес-командой (`operationId`). В случае связи между
GraphQL-запросом и Kafka-событием можно искать и request correlation ID,
и `operationId` из соответствующего бизнес-сценария.

## 6. Архитектурные ограничения, которые важно проговорить на защите

- Одноузловая Kafka/KRaft и общий RPC-секрет достаточны для учебного стенда, **не** HA/production.
- Логи JSON-структурированы, но в стенде нет отдельной системы централизованного сбора логов.
- Outbox дает надежную публикацию **после локального коммита**, но не мгновенную синхронизацию.
- Тесты fault injection проверяют retry, DLQ, ошибки Redis и deferred payment; время реального
  падения Kafka и Redis тоже стоит показать вручную, не удаляя volumes.
- Отзыв JWT-сессии никогда не зависит от каталожного кеша.
- Для настоящего production понадобятся ACL/TLS/mTLS, мониторинг DLQ, алерты и реплей из DLQ.

## 7. Git

Исправление ЛР7 сохраняет коммит ЛР6 `4572eab`, историю и `.env`.
Создавать коммит и отправлять `git push` следует **только после успешных тестов**.
Никогда не используйте `docker compose down -v`: это удаляет данные PostgreSQL, Redis и Kafka.
