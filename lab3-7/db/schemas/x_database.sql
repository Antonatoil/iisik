-- DB-X: Аналитика. Run in a separate database owned only by X.

BEGIN;

-- Факты входа для числа активных пользователей

CREATE TABLE auth_facts (
  event_id uuid NOT NULL PRIMARY KEY,
  user_id uuid NOT NULL,
  role_code varchar(16) NOT NULL,
  authenticated_at timestamptz NOT NULL
);

-- Проекция занятий и результатов

CREATE TABLE lesson_facts (
  lesson_id uuid NOT NULL PRIMARY KEY,
  booking_id uuid NOT NULL UNIQUE,
  teacher_id uuid NOT NULL,
  student_id uuid NOT NULL,
  subject_id uuid NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  status varchar(16) NOT NULL,
  booked_at timestamptz NOT NULL,
  cancelled_at timestamptz,
  completed_at timestamptz,
  goal_achieved boolean,
  version bigint NOT NULL
);

-- Финансовые факты без чужой БД

CREATE TABLE payment_facts (
  payment_id uuid NOT NULL PRIMARY KEY,
  booking_id uuid NOT NULL,
  teacher_id uuid NOT NULL,
  amount numeric(12,2) NOT NULL,
  currency char(3) NOT NULL,
  status varchar(16) NOT NULL,
  settled_at timestamptz NOT NULL,
  version bigint NOT NULL
);

-- Оценки за выбранный период

CREATE TABLE review_facts (
  review_id uuid NOT NULL PRIMARY KEY,
  teacher_id uuid NOT NULL,
  score smallint NOT NULL,
  created_at timestamptz NOT NULL
);

-- Текущие рейтинги, отдельно от оценок за период

CREATE TABLE rating_projection (
  teacher_id uuid NOT NULL PRIMARY KEY,
  average numeric(4,3) NOT NULL,
  review_count bigint NOT NULL,
  version bigint NOT NULL,
  updated_at timestamptz NOT NULL
);

-- Абсолютный счётчик для каталога

CREATE TABLE teacher_popularity (
  teacher_id uuid NOT NULL PRIMARY KEY,
  completed_count bigint NOT NULL,
  version bigint NOT NULL,
  updated_at timestamptz NOT NULL
);

-- Дедупликация обработанных сообщений

CREATE TABLE inbox (
  event_id uuid NOT NULL PRIMARY KEY,
  event_type varchar(40) NOT NULL,
  processed_at timestamptz NOT NULL
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

COMMIT;

-- Remaining cross-row business rules are enforced by the transactions described in the report.