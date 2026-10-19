-- DB-A: Учётные записи. Run in a separate database owned only by A.

BEGIN;

-- Три роли варианта

CREATE TABLE roles (
  code varchar(16) NOT NULL PRIMARY KEY,
  name varchar(40) NOT NULL,
  CHECK (code IN ('STUDENT','TEACHER','ADMIN'))
);

-- Учётная запись и статус доступа

CREATE TABLE users (
  id uuid NOT NULL PRIMARY KEY,
  role_code varchar(16) NOT NULL REFERENCES roles(code),
  email varchar(254) NOT NULL UNIQUE,
  password_hash text NOT NULL,
  name varchar(100) NOT NULL,
  status varchar(16) NOT NULL,
  created_at timestamptz NOT NULL,
  CHECK (status IN ('ACTIVE','BLOCKED'))
);

-- Профиль ученика

CREATE TABLE students (
  id uuid NOT NULL PRIMARY KEY REFERENCES users(id),
  learning_goal text
);

-- Проверка сеанса каждого защищённого запроса

CREATE TABLE sessions (
  id uuid NOT NULL PRIMARY KEY,
  token_hash text NOT NULL UNIQUE,
  user_id uuid NOT NULL REFERENCES users(id),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz
);

-- Событие сохраняется вместе с бизнес-изменением

CREATE TABLE outbox (
  event_id uuid NOT NULL PRIMARY KEY,
  topic text NOT NULL,
  partition_key text NOT NULL,
  envelope jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  published_at timestamptz
);

-- Безопасный повтор пользовательской команды

CREATE TABLE command_receipts (
  operation_id uuid NOT NULL PRIMARY KEY,
  actor_user_id uuid NOT NULL,
  command varchar(40) NOT NULL,
  request_hash text NOT NULL,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL
);

INSERT INTO roles(code,name) VALUES ('STUDENT','Ученик'),('TEACHER','Преподаватель'),('ADMIN','Администратор');

COMMIT;

-- Remaining cross-row business rules are enforced by the transactions described in the report.