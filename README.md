# ЛР7 — устойчивость и оптимизация распределённой системы

Актуальная версия: ЛР7 поверх ЛР6 (`4572eab`). Добавлены **bounded retry/timeout** для
read-only gRPC, обработка Kafka с DLQ после ограниченного числа попыток,
**Redis read-through кеш каталога** (отдельный DB 1, TTL 45 с, инвалидация),
структурированные логи с correlation ID и восстановление платежного сценария
после частичного отказа Learning через Kafka.

Запуск: `docker compose up -d --build`.
Проверка: `docker compose build tests; docker compose run --rm tests`.
Демонстрация: `scripts/demo_lab7.ps1`.
Подробности и ограничения: `docs/LAB7_RESILIENCE.md`.
Данные и история ЛР3–ЛР6 сохраняются; не удаляйте Docker volumes.

---

# ЛР5 — безопасность GraphQL API (текущая версия)

Один **GraphQL Gateway**, семь независимых сервисов ЛР4, отдельный
**Auth Service** и **Redis** для JWT-сессий. Всего **11 постоянно запущенных
контейнеров** (8 приложений + Gateway + PostgreSQL + Redis).
Регистрация и вход теперь выполняются через Auth Service; Redis хранит
активную сессию с TTL, а Gateway проверяет JWT + Redis до операций GraphQL.
Для демонстрации выполните `login` с паролем из локальной `.env`.
Старые токены `demo-*-token` отклоняются.

Весь актуальный порядок запуска и сценарии — `docs/LAB5_SECURITY.md`.

---

# Актуальная архитектура ЛР4 после замечания преподавателя

Теперь система имеет **девять постоянно запущенных контейнеров**: отдельный
GraphQL Gateway, **семь самостоятельно запускаемых FastAPI-сервисов**
(Accounts, Catalog, Learning, Payments, Reputation, Notifications, Analytics)
и один PostgreSQL с семью базами. Реального gRPC/Kafka нет: `MockRpcPorts`
сохраняет имена методов, но доставляет запросы сервисам по внутреннему HTTP.
Gateway **не подключается к базам данных**. Сервисы обращаются только к своим БД.

Запуск: `docker compose up -d --build`.
Проверка: `docker compose run --rm tests` (временный test-runner).
Проверка готовности: `http://localhost:8000/ready`.
Полная документация: `docs/LAB4_DEPLOYMENT.md`.
**Ниже сохранены исторические инструкции и описание исходной ЛР3/первой ЛР4.**

---

# ЛР3–ЛР4. Онлайн-репетиторство, вариант 27

**Тема:** базовая структура и GraphQL Query (ЛР3), бизнес-операции GraphQL Mutation (ЛР4).
**Основа:** архитектура ЛР1 и исходные контракты ЛР2 (не переработанные заново).

## Что реализовано

- GraphQL Gateway на FastAPI + Ariadne, SDL `contracts/schema.graphql` без изменения.
- Все 14 Query из ЛР2, вложенные поля и пагинация, фильтры/сортировка преподавателей, агрегированная аналитика.
- 7 внутренних сервисных модулей A/T/L/P/R/N/X со слоями доступа к данным.
- 7 отдельных PostgreSQL DATABASE с различными логинами и запретом CONNECT к чужим БД.
- Репозитории на SQLAlchemy Core с параметризованными SQL, никакого межсервисного JOIN.
- MockRpcPorts как подменяемый in-process адаптер будущих RPC из `tutoring.proto`.
- Проверка сеанса и ролей, запрет чтения чужих бронирований, оплат и уведомлений.
- Демо-данные и автотесты успешных запросов, ошибок и разграничения доступа.

**Границы работ:** в коммите ЛР3 Mutation были не реализованы. В текущем коммите ЛР4
добавлены все 14 Mutation, проверки состояний, изолированные операции записи и тесты.
Полноценные gRPC, Kafka и реальный эквайринг по методичке пока не реализуются.
Оплата — учебная симуляция, а не банковская транзакция. Код не предназначен для production.

## Требования

- Windows 10/11 + Docker Desktop с запущенным Linux engine (WSL2), свободные порты 8000 и 5434.
- PowerShell и VS Code (опционально — расширения Python, Docker, GraphQL).
- Python локально **не требуется**: установка пакетов выполняется внутри Docker.

## Запуск в PowerShell

```powershell
cd 'D:\бгуир\Иисик\iisik-github'  # корень Git-репозитория
docker compose up -d --build
docker compose ps
docker compose logs --tail=80 gateway
```

Открыть `http://localhost:8000/graphql/` (GraphQL Explorer),
`http://localhost:8000/health`, `http://localhost:8000/ready`.

Если порт занят, изменить левую часть `ports` в `compose.yaml`, например `8001:8000`.

## Демо-сеансы (только для разработки)

В GraphQL Explorer добавьте HTTP-заголовок `Authorization`. Права переключаются сменой токена.

| Роль | Заголовок |
|---|---|
| Ученик | `Authorization: Bearer demo-student-token` |
| Преподаватель | `Authorization: Bearer demo-teacher-token` |
| Администратор | `Authorization: Bearer demo-admin-token` |
| Второй ученик | `Authorization: Bearer demo-student2-token` |

Аутентификация по демонстрационному bearer-токену проверяется по хешу из таблицы
`sessions` БД-A; без токена Query возвращает `UNAUTHENTICATED`. Логин и регистрация
были отложены в ЛР3 и реализованы в текущей ЛР4.

### Запрос 1. Каталог и связи

```graphql
query {
  teachers(filter: {sort: RATING_DESC}, page: {limit: 10, offset: 0}) {
    items {
      id displayName bio
      price { amount currency }
      subjects { name }
      metrics { average completedCount }
      rating { average reviewCount }
    }
  }
}
```

### Запрос 2. Мои занятия и оплаты (ученик)

```graphql
query {
  me { name role student { learningGoal } }
  myBookings(page: {limit: 10, offset: 0}) {
    items {
      id status paymentState
      lesson { id topic status slot { startsAt endsAt } }
    }
  }
  myPayments(page: {limit: 10, offset: 0}) {
    items { id status money { amount currency } }
  }
}
```

### Запрос 3. Аналитика (токен администратора)

```graphql
query {
  platformAnalytics(input: {
    from: "2020-01-01T00:00:00Z", to: "2035-01-01T00:00:00Z",
    page: {limit: 20, offset: 0}
  }) {
    lessonsCompleted successfulPayments averageScore
    revenue { amount currency }
    teachers { teacherId lessonsCompleted currentRating }
  }
}
```

Другие сценарии, в том числе расписание преподавателя и свободные интервалы:
`demo/queries.graphql`.

## Проверка работы / тесты

```powershell
docker compose exec -T gateway pytest -q
```

Тесты включают оригинальную схему ЛР2, 7 физических БД, чтение связанных сущностей,
проверку ролей, ошибки `FORBIDDEN`, `BAD_USER_INPUT`, `UNAUTHENTICATED`, отсутствие
объекта и явную отсрочку Mutation.

Для просмотра содержимого отдельной базы через psql (пример DB-T):

```powershell
docker compose exec -T postgres psql -U lab_admin -d tutor_t -c "SELECT display_name, price FROM teachers;"
docker compose exec -T postgres psql -U lab_admin -d tutor_l -c "SELECT id, status FROM slots;"
```

Проверка запрета подключения чужим пользователем (DB-A пользователь `svc_a`
не может подключиться к `tutor_t`):

```powershell
docker compose exec -T -e PGPASSWORD=service_demo_only postgres psql -h 127.0.0.1 -U svc_a -d tutor_t -c 'SELECT 1;'
```

Последняя команда **должна завершиться ошибкой разрешения** — это ожидаемый тест изоляции.

## Организация исходников

```text
app/main.py                  Внешний API, readiness
app/gateway/schema.py        GraphQL SDL + 14 Query + вложенные резолверы
app/transport/mock_ports.py  Локальный mock вместо будущих gRPC
app/services/accounts.py     DB-A: пользователь, роль и сессия
app/services/catalog.py      DB-T: преподаватели, предметы, метрики
app/services/learning.py     DB-L: расписание, занятия, записи
app/services/payments.py     DB-P: платежи (чтение)
app/services/reputation.py   DB-R: отзывы и рейтинг
app/services/notifications.py DB-N: уведомления
app/services/analytics.py    DB-X: агрегация только проекций
app/core/db.py               Пулы SQLAlchemy, отдельный по владельцу
app/core/validation.py       Общие проверки ввода и пагинации
contracts/                   Исходные GraphQL/protobuf/JSON Schema из ЛР2
db/schemas/                  7 неизменённых DDL-файлов из ЛР2
db/seed/                     Фиксированные демонстрационные данные
db/init_all.sql              Самодостаточная инициализация PostgreSQL
tests/                       Контрактные и интеграционные тесты
```

**Путь запроса:** клиент → `GraphQL` → resolver → `MockRpcPorts` → конкретный
сервис → `db.rows/one` → исключительно своя PostgreSQL DB → ответ по той же цепочке.
Подмена `MockRpcPorts` на настоящие gRPC-клиенты будет следующей итерацией и
не потребует переноса SQL в Gateway.

## Остановка и повторный запуск

```powershell
docker compose down
```

Данные остаются в Docker volume. Для повторного создания баз и **сброса** данных:

```powershell
docker compose down -v
docker compose up -d --build
```

`down -v` удаляет данные лабораторного проекта без возможности восстановления.
Не выполнять, если в базе есть нужные собственные данные.

## Как защищать работу

1. По схеме объяснить 7 bounded context и почему у каждого есть своя БД.
2. Показать исходный `contracts/schema.graphql` и реализации Query в `schema.py`.
3. Показать путь `teachers` → `MockRpcPorts.SearchTeachers` → `catalog.search_teachers` → DB-T.
4. Показать связанные поля Teacher.subjects/Teacher.rating и Booking.lesson.
5. Переключить токен ученика на токен администратора и показать контроль доступа.
6. Продемонстрировать `pytest -q` и `GET /ready`.
7. Объяснить, почему реальные gRPC/Kafka и Mutation НЕ добавлены в ЛР3.

---

## ЛР4 — реализация GraphQL Mutation (вариант 27)

ЛР4 продолжает ЛР3 **в том же корне репозитория**. Файлы ЛР1/2 и семь баз PostgreSQL остаются прежними. Добавлены `app/services/*_write.py`, `app/transport/workflows.py`, 14 Mutation Resolver, idempotency и тесты. Подробнее: `docs/LAB4_DEFENSE.md` и `demo/lab4.graphql`.

```powershell
docker compose up -d --build
docker compose exec -T gateway python -m pytest -q
```

Не выполняйте `docker compose down -v`: это удалит сохранённые данные PostgreSQL. `db/init_all.sql` предназначен **только для первого создания пустого Docker volume**; новые Mutation работают с уже существующими БД без миграций.

**Отличия:** Mutation отражают бизнес-действия (не CRUD), права и состояния проверяются во внутренних сервисах. Фильтрация/сортировка Query и агрегирование `platformAnalytics` сохранены из ЛР3. Платёж симулирован. Связи между сервисами пока выполнены через синхронные Mock-порты без сетевых gRPC/Kafka; общей распределённой транзакции нет.


## ЛР5: JWT и независимый Auth Service

ЛР5 продолжает коммит `5700de0`. Теперь GraphQL Gateway и семь сервисов
работают с **отдельным Auth Service** и Redis: всего 11 постоянно работающих
контейнеров (Gateway, Auth, 7 бизнес-сервисов, PostgreSQL, Redis).

- Регистрация и вход передаются из GraphQL только в Auth Service.
- Auth Service проверяет пароль по защищённым данным Accounts через Mock RPC,
  выдаёт JWT HS256 (подпись хранится только у Auth) и записывает сессию в Redis
  на 3600 секунд.
- При каждом Query/Mutation (кроме register/login) Gateway проверяет JWT и
  Redis-сессию через Auth Service. Статус пользователя берётся из Accounts.
- `logout` отзывает одну Redis-сессию; блокировка пользователя администратором
  отзывает его сессии и запрещает доступ даже по ранее выданному JWT.
- Существующие Query/Mutation, Workflow, семь БД и HTTP Mock сохраняются.
- Старые `demo-student-token`, `demo-teacher-token`, `demo-admin-token` больше
  **не дают доступ**; для демонстрации нужно сделать `login` и использовать JWT.
- Созданная установщиком `.env` содержит уникальные секреты и демонстрационный
  пароль для первоначальных учебных пользователей. `.env` не попадает в Git.

Запуск и полный сценарий приведены в `docs/LAB5_SECURITY.md`.

```powershell
docker compose up -d --build
docker compose run --rm tests
```

Для остановки без удаления PostgreSQL и Redis volume: `docker compose down`.
**Не использовать `docker compose down -v`.**

---

## ЛР6 — реальные gRPC и Apache Kafka

**Последняя версия:** см. `docs/LAB6_INTEGRATION.md` и `demo/lab6.graphql`.
HTTP `/mock/{method}` больше нет. Gateway и все бизнес-сервисы обмениваются реальными gRPC-вызовами по protobuf (включая типизированные методы исходного контракта ЛР2); Kafka обрабатывает реальные события бронирования, изменения занятий, оплаты и отзывов через transactional outbox/inbox.

Состав: 7 бизнес-сервисов + Gateway + Auth + PostgreSQL + Redis + Kafka = **12 постоянно работающих контейнеров**. Одноразовые `migrate` и `kafka-init` добавляются при развёртывании. Все данные ЛР5 и история Git сохраняются.

```powershell
cd 'D:\бгуир\Иисик\lab3-7'
docker compose up -d --build
docker compose run --rm tests
Invoke-RestMethod http://localhost:8000/ready
```
