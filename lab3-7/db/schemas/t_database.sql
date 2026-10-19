-- DB-T: Каталог преподавателей. Run in a separate database owned only by T.

BEGIN;

-- Профиль и текущее предложение

CREATE TABLE teachers (
  id uuid NOT NULL PRIMARY KEY,
  display_name varchar(100) NOT NULL,
  bio text NOT NULL,
  price numeric(12,2) NOT NULL,
  currency char(3) NOT NULL,
  updated_at timestamptz NOT NULL,
  CHECK (price > 0)
);

-- Справочник предметов

CREATE TABLE subjects (
  id uuid NOT NULL PRIMARY KEY,
  name varchar(120) NOT NULL UNIQUE,
  description text NOT NULL,
  active boolean NOT NULL
);

-- Связь преподавателей и предметов M N

CREATE TABLE teacher_subjects (
  teacher_id uuid NOT NULL REFERENCES teachers(id),
  subject_id uuid NOT NULL REFERENCES subjects(id),
  PRIMARY KEY (teacher_id, subject_id)
);

-- Проекция для фильтрации и сортировки каталога

CREATE TABLE teacher_metrics (
  teacher_id uuid NOT NULL PRIMARY KEY REFERENCES teachers(id),
  average numeric(4,3),
  review_count bigint NOT NULL,
  rating_version bigint NOT NULL,
  completed_count bigint NOT NULL,
  popularity_version bigint NOT NULL,
  last_review_at timestamptz,
  updated_at timestamptz NOT NULL
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