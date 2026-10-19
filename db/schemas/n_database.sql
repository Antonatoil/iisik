-- DB-N: Уведомления. Run in a separate database owned only by N.

BEGIN;

-- Сообщения внутри приложения

CREATE TABLE notifications (
  id uuid NOT NULL PRIMARY KEY,
  user_id uuid NOT NULL,
  event_id uuid NOT NULL,
  kind varchar(40) NOT NULL,
  text text NOT NULL,
  object_id uuid NOT NULL,
  created_at timestamptz NOT NULL,
  read_at timestamptz,
  UNIQUE (event_id, user_id)
);

-- Дедупликация обработанных сообщений

CREATE TABLE inbox (
  event_id uuid NOT NULL PRIMARY KEY,
  event_type varchar(40) NOT NULL,
  processed_at timestamptz NOT NULL
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

COMMIT;

-- Remaining cross-row business rules are enforced by the transactions described in the report.