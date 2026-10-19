# ЛР3. Онлайн-репетиторство, вариант 27

**Тема:** реализация базовой структуры распределённой системы и GraphQL Query.
**Основа:** архитектура ЛР1 и исходные контракты ЛР2.

## Что реализовано

- GraphQL Gateway на FastAPI + Ariadne, SDL `contracts/schema.graphql` без изменения.
- Все 14 Query из ЛР2, вложенные поля и пагинация, фильтры/сортировка преподавателей, агрегированная аналитика.
- 7 внутренних сервисных модулей A/T/L/P/R/N/X со слоями доступа к данным.
- 7 отдельных PostgreSQL DATABASE с различными логинами и запретом CONNECT к чужим БД.
- Репозитории на SQLAlchemy Core с параметризованными SQL, никакого межсервисного JOIN.
- MockRpcPorts как подменяемый in-process адаптер будущих RPC из `tutoring.proto`.
- Проверка сеанса и ролей, запрет чтения чужих бронирований, оплат и уведомлений.
- Демо-данные и автотесты успешных запросов, ошибок и разграничения доступа.

**Не реализовано сознательно:** настоящие gRPC, Kafka, сложная бизнес-логика записи и оплаты,
GraphQL Mutation. 14 Mutation сохранены в SDL, но возвращают `NOT_IMPLEMENTED_IN_LAB3`:
это граница работ по заданию ЛР3. Данные в БД изменяются исключительно исходным SQL при
первой инициализации тома PostgreSQL. Платёж в таблице — демонстрационная тестовая запись,
а не выполненная банковская транзакция. Примерная версия не для production.

## Требования

- Windows 10/11 + Docker Desktop с запущенным Linux engine (WSL2), свободные порты 8000 и 5434.
- PowerShell и VS Code (опционально — расширения Python, Docker, GraphQL).
- Python локально **не требуется**: установка пакетов выполняется внутри Docker.

## Запуск в PowerShell

```powershell
cd 'D:\бгуир\Иисик\lab3-7'
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
не выполняются в ЛР3 (Mutation относится к следующим работам).

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

