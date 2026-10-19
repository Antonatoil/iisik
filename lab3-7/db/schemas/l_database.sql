-- DB-L: Занятия и расписание. Run in a separate database owned only by L.

BEGIN;

-- Интервал расписания преподавателя

CREATE TABLE slots (
  id uuid NOT NULL PRIMARY KEY,
  teacher_id uuid NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  status varchar(16) NOT NULL,
  version bigint NOT NULL,
  CHECK (ends_at > starts_at),
  CHECK (status IN ('AVAILABLE','BOOKED','CLOSED','REMOVED'))
);

-- Занятие и результат проведения

CREATE TABLE lessons (
  id uuid NOT NULL PRIMARY KEY,
  slot_id uuid NOT NULL REFERENCES slots(id),
  subject_id uuid NOT NULL,
  topic varchar(200) NOT NULL,
  status varchar(16) NOT NULL,
  result_text text,
  goal_achieved boolean,
  started_at timestamptz,
  completed_at timestamptz,
  version bigint NOT NULL,
  CHECK (status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED'))
);

-- Единственное участие ученика в занятии

CREATE TABLE bookings (
  id uuid NOT NULL PRIMARY KEY,
  lesson_id uuid NOT NULL UNIQUE REFERENCES lessons(id),
  student_id uuid NOT NULL,
  status varchar(16) NOT NULL,
  price numeric(12,2) NOT NULL,
  currency char(3) NOT NULL,
  payment_state varchar(16) NOT NULL,
  payment_operation_id uuid,
  created_at timestamptz NOT NULL,
  CHECK (price > 0),
  CHECK (status IN ('ACTIVE','COMPLETED','CANCELLED')),
  CHECK (payment_state IN ('UNPAID','PROCESSING','PAID'))
);

-- История переносов без изменения идентичности занятия

CREATE TABLE lesson_moves (
  id uuid NOT NULL PRIMARY KEY,
  lesson_id uuid NOT NULL REFERENCES lessons(id),
  old_slot_id uuid NOT NULL REFERENCES slots(id),
  new_slot_id uuid NOT NULL REFERENCES slots(id),
  old_starts_at timestamptz NOT NULL,
  old_ends_at timestamptz NOT NULL,
  new_starts_at timestamptz NOT NULL,
  new_ends_at timestamptz NOT NULL,
  actor_user_id uuid NOT NULL,
  changed_at timestamptz NOT NULL
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

CREATE UNIQUE INDEX one_active_lesson_per_slot ON lessons(slot_id) WHERE status IN ('PLANNED','IN_PROGRESS');

COMMIT;

-- Remaining cross-row business rules are enforced by the transactions described in the report.