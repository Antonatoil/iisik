# Лабораторная работа №6. Вариант 27 — Онлайн-репетиторство

## 1. Что реально реализовано

- В Docker запускаются **семь независимых сервисов** Accounts, Catalog, Learning, Payments, Reputation, Notifications, Analytics; у каждого собственный процесс gRPC-сервера `:50051` и собственная PostgreSQL-база. HTTP `:8100` оставлен **только для** `/health` и `/ready`.
- Внешний GraphQL Gateway не имеет доступа к базам и вызывает внутренние сервисы по **реальным gRPC/HTTP2** каналам.
- Сохранён исходный `contracts/tutoring.proto` ЛР2. Его типизированные `Catalog.GetTeachingOffer` и `Reputation.GetRating` вызываются в рабочих бизнес-сценариях. Для 43 внутренних операций ЛР4 добавлен документированный, явно именованный protobuf-контракт `contracts/integration.proto`; каждый метод имеет собственное объявление RPC и пакетное сериализованное тело. Все методы привязаны к одному владельцу.
- Аккаунты и роли по-прежнему принадлежат Accounts; отдельный Auth Service ЛР5 получает данные и хеш пароля исключительно через защищённый gRPC-метод Accounts, затем выдаёт JWT и создаёт активную Redis-сессию.
- Kafka (`apache/kafka:3.9.1`, KRaft, один учебный broker) служит реальным асинхронным транспортом событий, а не демонстрацией вне бизнес-операций.
- В `tutor.events.v1` реально поступают события из локальных **transactional outbox** таблиц. Consumers выполняют бизнес-обработку в Analytics, Notifications, Catalog и Learning с **transactional inbox**, а не просто печатают сообщения.
- Неизвестные/повреждённые сообщения пересылаются в `tutor.events.dlq.v1` (либо удерживаются для повтора, если DLQ недоступна).
- Старые HTTP `/mock/{method}` полностью удалены из служебного приложения и старый клиент `app/transport/mock_ports.py` удалён.

**Ограничения учебной среды:** Kafka single broker (RF=1); внутренний gRPC по приватной Docker-сети без TLS, с shared-key metadata; реальные платежи не проводятся. Для production нужны mTLS, отдельные роли и ACL Kafka, репликация брокеров, ротация секретов, мониторинг consumer lag.

## 2. Сценарии

### `bookLesson`

1. Студент входит в GraphQL API с JWT; Gateway валидирует токен и Redis-сессию через Auth Service.
2. Gateway по **типизированному gRPC** вызывает `Catalog.GetTeachingOffer` для активного предложения преподавателя.
3. Gateway по gRPC вызывает `Learning.BookLessonLocal`.
4. Learning фиксирует занятие, бронь и `LessonBooked` в **одной транзакции DB-L**. Повторный `operationId` не создаёт вторую бронь и второе событие.
5. Publisher Learning отправляет outbox в Kafka; только после подтверждения записи помечает событие опубликованным.
6. Consumer Analytics добавляет/обновляет `lesson_facts` и consumer Notifications создаёт уведомления ученику и преподавателю. Обработка с дедупликацией `event_inbox`.

### `registerPayment`

1. Gateway по gRPC запрашивает актуальную бронь у Learning и проверяет права ученика.
2. Payments по gRPC фиксирует демонстрационную оплату и `PaymentCompleted` в DB-P + outbox.
3. Gateway выполняет синхронное idempotent-подтверждение в Learning (чтобы следующий `startLesson` видел `PAID`), Kafka-consumer Learning также применяет то же событие для восстановления после сетевых сбоев.
4. Kafka-consumers Analytics и Notifications фиксируют факт оплаты и уведомление независимо от доступности Gateway.

### `completeLesson` и `addReview`

- Learning публикует `LessonCompleted`. Consumer Analytics обновляет факт занятия и абсолютный счётчик выполненных занятий, затем пишет `PopularityUpdated` в **свой** outbox DB-X. Consumer Catalog обновляет сортировочную проекцию популярности.
- Reputation локально добавляет отзыв и пересчитывает рейтинг, в той же транзакции сохраняет `ReviewCreated` и `RatingUpdated`. Notifications, Analytics, Catalog потребляют события, каждый в собственной DB-N/DB-X/DB-T.

### `UserAuthenticated`

Auth Service публикует необязательное аналитическое событие `UserAuthenticated` в Kafka. Ошибка доставки не отменяет успешную авторизацию: JWT и Redis-сессия остаются источником истины. Это осознанный компромисс для метрики входов, которая не является финансово значимой операцией.

## 3. Сохранение совместимости

- Данные, схемы и JWT ЛР5 **не очищаются**.
- Существующие тома Docker (`tutor_db_data`, `tutor_redis_data`) не изменяют имя. Добавляется только новый `tutor_kafka_data`.
- Одноразовый сервис `migrate` применяет `db/migrations/006_event_outbox.sql` ко всем семи базам: `CREATE ... IF NOT EXISTS`, плюс минимальные права сервиса-владельца на его новые таблицы. Нет `DROP TABLE` и нет `docker compose down -v`.
- Контейнеры `kafka-init`, `migrate` являются **одноразовыми**, это не два постоянно работающих приложения.
- Впервые после обновления нужно собрать **все** образы (Gateway, Auth, 7 сервисов, tests), поскольку обновились зависимости и скомпилированные protobuf.

## 4. Запуск и полная проверка (PowerShell)

```powershell
cd 'D:\бгуир\Иисик\lab3-7'
docker compose config -q
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/ready
docker compose build tests
docker compose run --rm tests python -m pytest --collect-only -q
docker compose run --rm tests
```

`/ready` должен включать `kafka: ok`, `transport: grpc`, `auth: ok`, `redis: ok` и семь успешных сервисов. `test_lab6.py` создаёт **настоящие** бронирование и оплату через GraphQL, проверяет запись `LessonBooked` в outbox DB-L, факт публикации, асинхронные проекции и дедупликацию Kafka consumer.

Показать топики:

```powershell
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list
```

Показать Kafka-события (останавливать Ctrl+C):

```powershell
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:9092 --topic tutor.events.v1 --from-beginning
```

Показать логи сервисов и реального consumer:

```powershell
docker compose logs --tail=100 learning analytics notifications catalog kafka
```

Внутренний gRPC можно проверить через тесты. Доступ без `x-rpc-secret` отклоняется `UNAUTHENTICATED`, метод чужого сервиса — `NOT_FOUND`, обращение к хешам пользователя без `x-auth-repository-key` — `PERMISSION_DENIED`.

## 5. Проверка надежности перед защитой

- **Сетевая недоступность:** gRPC ограничен timeout (8–12 секунд), ошибки преобразуются в GraphQL `SERVICE_UNAVAILABLE`/`SERVICE_TIMEOUT`. Производители событий пишут outbox, поэтому кратковременная остановка Kafka не стирает локальную транзакцию.
- **Повторная доставка:** Kafka at-least-once; отдельный `event_inbox` и SQL `ON CONFLICT` не допускают дубликатов. При отказе consumer offset не подтверждается.
- **Контракты:** события валидируются по исходному `contracts/events.schema.json` ЛР2, включая `event_id`, `event_type`, `producer`, `aggregate_version`, UUID и payload.
- **Согласованность:** аналитика/каталог/уведомления обновляются асинхронно. Защита должна объяснять *eventual consistency* и разницу с синхронным gRPC.
- **Разделение:** gRPC/Kafka отвечают за транспорт; SQL и бизнес-правила остаются внутри соответствующих сервисов.

## 6. Поток данных

```text
Client (JWT)
    |
    v
GraphQL Gateway --HTTP--> Auth Service --Redis sessions
    |
    +-- gRPC protobuf --> Catalog (DB-T)
    +-- gRPC protobuf --> Learning (DB-L + transactional outbox)
    +-- gRPC protobuf --> Payments (DB-P + transactional outbox)
    +-- gRPC protobuf --> Reputation (DB-R + transactional outbox)
    |
Kafka (tutor.events.v1, six partitions)
    +--> Notifications consumer --> DB-N notifications + inbox
    +--> Analytics consumer --> DB-X projections + inbox / outbox
    |                              |
    |                              +--> Kafka PopularityUpdated
    +--> Catalog consumer -------> DB-T projections + inbox
    +--> Learning consumer ------> DB-L payment-state reconciliation + inbox
```
