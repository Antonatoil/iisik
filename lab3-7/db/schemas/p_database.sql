-- DB-P: Платежи. Run in a separate database owned only by P.

BEGIN;

-- Попытка оплаты и восстановление после сбоя

CREATE TABLE payments (
  id uuid NOT NULL PRIMARY KEY,
  operation_id uuid NOT NULL UNIQUE,
  booking_id uuid NOT NULL,
  student_id uuid NOT NULL,
  teacher_id uuid,
  lesson_id uuid,
  amount numeric(12,2),
  currency char(3),
  status varchar(16) NOT NULL,
  failure_code varchar(40),
  created_at timestamptz NOT NULL,
  settled_at timestamptz,
  version bigint NOT NULL,
  CHECK (status IN ('CREATED','PROCESSING','COMPLETED','FAILED','REJECTED')),
  CHECK (status NOT IN ('PROCESSING','COMPLETED','FAILED') OR (teacher_id IS NOT NULL AND lesson_id IS NOT NULL AND amount IS NOT NULL AND amount > 0 AND currency IS NOT NULL))
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

CREATE UNIQUE INDEX one_successful_payment ON payments(booking_id) WHERE status = 'COMPLETED';

COMMIT;

-- Remaining cross-row business rules are enforced by the transactions described in the report.