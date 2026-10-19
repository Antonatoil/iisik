-- DB-R: Отзывы и рейтинг. Run in a separate database owned only by R.

BEGIN;

-- Один отзыв по подтверждённому завершённому участию

CREATE TABLE reviews (
  id uuid NOT NULL PRIMARY KEY,
  booking_id uuid NOT NULL UNIQUE,
  student_id uuid NOT NULL,
  teacher_id uuid NOT NULL,
  score smallint NOT NULL,
  text text NOT NULL,
  created_at timestamptz NOT NULL,
  CHECK (score BETWEEN 1 AND 5)
);

-- Авторитетный расчёт рейтинга

CREATE TABLE ratings (
  teacher_id uuid NOT NULL PRIMARY KEY,
  score_sum bigint NOT NULL,
  review_count bigint NOT NULL,
  average numeric(4,3) NOT NULL,
  version bigint NOT NULL,
  updated_at timestamptz NOT NULL,
  CHECK (review_count > 0)
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

COMMIT;

-- Remaining cross-row business rules are enforced by the transactions described in the report.