# Лабораторная работа № 5 — безопасность GraphQL API, вариант 27

## Что добавлено

В новом коммите поверх ЛР4 создан независимый Auth Service (`app/auth_service.py`)
и Redis. Существующие семь бизнес-сервисов сохраняют свои границы и БД.
Auth Service реализует получение логина/пароля через защищённый Accounts Mock RPC,
проверяет пароль в собственном процессе, выпускает JWT HS256 и хранит сессии с TTL
3600 секунд в Redis. JWT_SECRET известен только Auth Service.

Основной путь запроса:

1. `login` из GraphQL Gateway передаёт данные в Auth Service по HTTP.
2. Auth Service считывает hash-пароля у Accounts через `ReadCredentialForAuth`.
3. При верном пароле выдаёт подписанный JWT и сохраняет `lab5:session:<jti>` с TTL.
4. Клиент отправляет `Authorization: Bearer <JWT>` в Gateway.
5. Gateway спрашивает Auth Service: валиден ли JWT, существует ли сессия в Redis,
   является ли пользователь активным и соответствует ли роль текущим данным.
6. Затем GraphQL Resolver проверяет роль и вызывает бизнес-сервис через Mock RPC.
7. `logout` удаляет ключ сессии из Redis. При `setUserStatus(BLOCKED)` сессии
   пользователя отзываются, а дополнительная проверка `status` блокирует доступ
   даже если удаление ключа не удалось.

**Важно:** JWT и его подпись сами по себе не являются активной сессией.
Без Redis-сессии запрос отклоняется. Старые bearer-токены ЛР3/4 не принимаются.

## Запуск

```powershell
cd 'D:\бгуир\Иисик\lab3-7'
docker compose config
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/ready
docker compose run --rm tests
```

Ожидается 11 постоянно работающих контейнеров: Gateway, Auth, Accounts,
Catalog, Learning, Payments, Reputation, Notifications, Analytics, PostgreSQL,
Redis. Тестовый контейнер запускается отдельно и удаляется после проверки.

## Демонстрация

Демонстрационные учетные записи после однократной миграции паролей:
`student@example.test`, `math@example.test`, `admin@example.test`.
Пароль из **локального** `.env` (`LAB5_DEMO_PASSWORD`); этот файл не коммитить.

- Без токена `{me{id}}` -> `UNAUTHENTICATED`.
- Неподписанный или изменённый JWT -> `UNAUTHENTICATED`.
- Верный JWT ученика -> `me`, `teachers` работают; `users` -> `FORBIDDEN`.
- JWT администратора -> `users`, `platformAnalytics` работают.
- `logout` -> `true`, повторный запрос с тем же JWT -> `UNAUTHENTICATED`.
- Удалить `lab5:session:<jti>` в Redis -> токен отклоняется.
- Заблокировать пользователя через `setUserStatus` -> его токен отзывается.
- `docker compose restart auth` -> Gateway не пересоздаётся.

## Файлы и архитектура

- `app/auth_service.py`: JWT HS256, login, register, validate, logout, revoke-user,
  Redis TTL, защита от повторных неудачных входов.
- `app/transport/auth_client.py`: HTTP-адаптер Gateway к Auth Service.
- `app/transport/auth_rpc.py`: защищённый вызов Accounts/Analytics из Auth.
- `app/services/accounts.py`: доступ к учётным данным принадлежит DB-A;
  никаких SQL из Gateway или Auth Service.
- `app/main.py`: Gateway проверяет JWT + Redis-сессию через Auth Service.
- `app/gateway/schema.py`: существующие проверки ролей и добавленный logout.
- `Dockerfile.auth`: отдельный образ Auth без кода сервисов и SQL-доступа.
- `compose.yaml`: отдельные auth и redis, healthcheck, неизменённый PostgreSQL volume.
- `scripts/seed_lab5_demo.py`: однократная безопасная миграция паролей
  только исходных демонстрационных пользователей.
- `tests/test_auth_security.py`: JWT, Redis, RBAC, logout, отзыв и изоляция.

## Ограничения

Взаимодействие между Auth/Accounts/Gateway выполнено поверх сохранённых Mock
HTTP интерфейсов, а не настоящего gRPC; Kafka не используется. Auth Service
не владеет таблицами Accounts, а обращается к владельцу данных через защищённый
внутренний RPC. В ЛР5 не реализованы OAuth2 Authorization Code, MFA и реальный
платёжный провайдер.
