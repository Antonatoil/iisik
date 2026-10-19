-- LAB3 VARIANT 27: one PostgreSQL server, seven isolated DATABASES/ROLES.
-- Each service role can connect only to its own database.
CREATE ROLE svc_a LOGIN PASSWORD 'service_demo_only';
CREATE ROLE svc_t LOGIN PASSWORD 'service_demo_only';
CREATE ROLE svc_l LOGIN PASSWORD 'service_demo_only';
CREATE ROLE svc_p LOGIN PASSWORD 'service_demo_only';
CREATE ROLE svc_r LOGIN PASSWORD 'service_demo_only';
CREATE ROLE svc_n LOGIN PASSWORD 'service_demo_only';
CREATE ROLE svc_x LOGIN PASSWORD 'service_demo_only';
CREATE DATABASE tutor_a OWNER svc_a;
REVOKE CONNECT ON DATABASE tutor_a FROM PUBLIC;
CREATE DATABASE tutor_t OWNER svc_t;
REVOKE CONNECT ON DATABASE tutor_t FROM PUBLIC;
CREATE DATABASE tutor_l OWNER svc_l;
REVOKE CONNECT ON DATABASE tutor_l FROM PUBLIC;
CREATE DATABASE tutor_p OWNER svc_p;
REVOKE CONNECT ON DATABASE tutor_p FROM PUBLIC;
CREATE DATABASE tutor_r OWNER svc_r;
REVOKE CONNECT ON DATABASE tutor_r FROM PUBLIC;
CREATE DATABASE tutor_n OWNER svc_n;
REVOKE CONNECT ON DATABASE tutor_n FROM PUBLIC;
CREATE DATABASE tutor_x OWNER svc_x;
REVOKE CONNECT ON DATABASE tutor_x FROM PUBLIC;
\connect tutor_a
SET ROLE svc_a;
-- Original Lab2 SQL: a_database.sql
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
-- Demonstration data for DB-a

-- Seed accounts, roles are created by original Lab 2 DDL.
INSERT INTO users(id,role_code,email,password_hash,name,status,created_at) VALUES
('00000000-0000-4000-8000-000000000101','STUDENT','student@example.test','ceff7ffd7dc925f1f55dc4d74882e3774559b9227c28fba1c05347b8df231ded','Анна Ученица','ACTIVE',now()-interval '30 day'),
('00000000-0000-4000-8000-000000000102','STUDENT','student2@example.test','82501600c50c7e857c50c866529502f6807fc9725b641ef210c1b84839c9044b','Алексей Ученик','ACTIVE',now()-interval '29 day'),
('00000000-0000-4000-8000-000000000201','TEACHER','math@example.test','0d8e582d42094b954a011b8b156d623b06e3026933c5dec8e32723681af8e174','Мария Петрова','ACTIVE',now()-interval '60 day'),
('00000000-0000-4000-8000-000000000202','TEACHER','english@example.test','22e7d76271dd58cad849abc6dfa2ab7742fd3922b645f3a4122ac088df64d294','Игорь Соколов','ACTIVE',now()-interval '50 day'),
('00000000-0000-4000-8000-000000000301','ADMIN','admin@example.test','85205126422ac0e1b945b071dfe5e18c146b8266592e0c502fa0715e749d2605','Администратор','ACTIVE',now()-interval '90 day');
INSERT INTO students(id,learning_goal) VALUES
('00000000-0000-4000-8000-000000000101','Подготовиться к экзамену по математике'),
('00000000-0000-4000-8000-000000000102','Улучшить знания по физике');
INSERT INTO sessions(id, token_hash, user_id, expires_at) VALUES
('00000000-0000-4000-8000-000000001301','a094893e99b128f729235f38798b866cce7c26c48907527b0e41715a4d4c9fee','00000000-0000-4000-8000-000000000101',now()+interval '365 days'),
('00000000-0000-4000-8000-000000001302','f39c6ada641558f48949dfa4fb8a05d8ae86d1016d6bc2526126051c5ada883e','00000000-0000-4000-8000-000000000201',now()+interval '365 days'),
('00000000-0000-4000-8000-000000001201','91c16f0d6cc1bec3c3603972182a07c66ff4fa71618a975e963d6dbe42b6dd37','00000000-0000-4000-8000-000000000301',now()+interval '365 days'),
('00000000-0000-4000-8000-000000001202','5f9bdc318f71d1ca0d8e6ea782993f4ae16a56505058b9e9039514d1a98a2cf4','00000000-0000-4000-8000-000000000102',now()+interval '365 days');

RESET ROLE;
\connect tutor_t
SET ROLE svc_t;
-- Original Lab2 SQL: t_database.sql
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
-- Demonstration data for DB-t

INSERT INTO subjects(id,name,description,active) VALUES
('00000000-0000-4000-8000-000000000501','Математика','Алгебра и геометрия',true),
('00000000-0000-4000-8000-000000000502','Физика','Основы физики и задачи',true),
('00000000-0000-4000-8000-000000000503','Английский язык','Разговорная практика',true);
INSERT INTO teachers(id,display_name,bio,price,currency,updated_at) VALUES
('00000000-0000-4000-8000-000000000201','Мария Петрова','Преподаватель математики, 8 лет опыта',60.00,'BYN',now()),
('00000000-0000-4000-8000-000000000202','Игорь Соколов','Преподаватель английского, 5 лет опыта',45.00,'BYN',now());
INSERT INTO teacher_subjects VALUES
('00000000-0000-4000-8000-000000000201','00000000-0000-4000-8000-000000000501'),('00000000-0000-4000-8000-000000000201','00000000-0000-4000-8000-000000000502'),('00000000-0000-4000-8000-000000000202','00000000-0000-4000-8000-000000000503');
INSERT INTO teacher_metrics(teacher_id,average,review_count,rating_version,completed_count,popularity_version,last_review_at,updated_at) VALUES
('00000000-0000-4000-8000-000000000201',5.000,1,1,1,1,now()-interval '1 day',now()),
('00000000-0000-4000-8000-000000000202',null,0,0,0,0,null,now());

RESET ROLE;
\connect tutor_l
SET ROLE svc_l;
-- Original Lab2 SQL: l_database.sql
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
-- Demonstration data for DB-l

INSERT INTO slots(id,teacher_id,starts_at,ends_at,status,version) VALUES
('00000000-0000-4000-8000-000000000601','00000000-0000-4000-8000-000000000201',now()+interval '2 days',now()+interval '2 days 1 hour','AVAILABLE',1),
('00000000-0000-4000-8000-000000000602','00000000-0000-4000-8000-000000000201',now()+interval '4 days',now()+interval '4 days 1 hour','BOOKED',2),
('00000000-0000-4000-8000-000000000603','00000000-0000-4000-8000-000000000202',now()+interval '3 days',now()+interval '3 days 1 hour','AVAILABLE',1),
('00000000-0000-4000-8000-000000000604','00000000-0000-4000-8000-000000000201',now()-interval '2 days',now()-interval '2 days'+interval '1 hour','CLOSED',2);
INSERT INTO lessons(id,slot_id,subject_id,topic,status,result_text,goal_achieved,started_at,completed_at,version) VALUES
('00000000-0000-4000-8000-000000000701','00000000-0000-4000-8000-000000000604','00000000-0000-4000-8000-000000000501','Квадратные уравнения','COMPLETED','Ученик освоил материал',true,now()-interval '2 days',now()-interval '2 days'+interval '1 hour',2),
('00000000-0000-4000-8000-000000000702','00000000-0000-4000-8000-000000000602','00000000-0000-4000-8000-000000000501','Тригонометрия','PLANNED',null,null,null,null,1);
INSERT INTO bookings(id,lesson_id,student_id,status,price,currency,payment_state,created_at) VALUES
('00000000-0000-4000-8000-000000000801','00000000-0000-4000-8000-000000000701','00000000-0000-4000-8000-000000000101','COMPLETED',60.00,'BYN','PAID',now()-interval '4 days'),
('00000000-0000-4000-8000-000000000802','00000000-0000-4000-8000-000000000702','00000000-0000-4000-8000-000000000102','ACTIVE',60.00,'BYN','UNPAID',now()-interval '1 day');

RESET ROLE;
\connect tutor_p
SET ROLE svc_p;
-- Original Lab2 SQL: p_database.sql
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
-- Demonstration data for DB-p

INSERT INTO payments(id,operation_id,booking_id,student_id,teacher_id,lesson_id,amount,currency,status,created_at,settled_at,version) VALUES
('00000000-0000-4000-8000-000000000901','00000000-0000-4000-8000-000000001001','00000000-0000-4000-8000-000000000801','00000000-0000-4000-8000-000000000101','00000000-0000-4000-8000-000000000201','00000000-0000-4000-8000-000000000701',60.00,'BYN','COMPLETED',now()-interval '3 days',now()-interval '3 days',1);

RESET ROLE;
\connect tutor_r
SET ROLE svc_r;
-- Original Lab2 SQL: r_database.sql
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
-- Demonstration data for DB-r

INSERT INTO reviews(id,booking_id,student_id,teacher_id,score,text,created_at) VALUES
('00000000-0000-4000-8000-000000001101','00000000-0000-4000-8000-000000000801','00000000-0000-4000-8000-000000000101','00000000-0000-4000-8000-000000000201',5,'Преподаватель объясняет понятно',now()-interval '1 day');
INSERT INTO ratings(teacher_id,score_sum,review_count,average,version,updated_at) VALUES
('00000000-0000-4000-8000-000000000201',5,1,5.000,1,now()-interval '1 day');

RESET ROLE;
\connect tutor_n
SET ROLE svc_n;
-- Original Lab2 SQL: n_database.sql
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
-- Demonstration data for DB-n

INSERT INTO notifications(id,user_id,event_id,kind,text,object_id,created_at,read_at) VALUES
('00000000-0000-4000-8000-000000001101','00000000-0000-4000-8000-000000000101','00000000-0000-4000-8000-000000000901','LessonCompleted','Занятие завершено','00000000-0000-4000-8000-000000000701',now()-interval '2 days',now()-interval '1 day'),
('00000000-0000-4000-8000-000000001102','00000000-0000-4000-8000-000000000102','00000000-0000-4000-8000-000000000702','LessonBooked','Вы записаны на занятие','00000000-0000-4000-8000-000000000702',now()-interval '1 day',null);

RESET ROLE;
\connect tutor_x
SET ROLE svc_x;
-- Original Lab2 SQL: x_database.sql
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
-- Demonstration data for DB-x

INSERT INTO auth_facts(event_id,user_id,role_code,authenticated_at) VALUES
('00000000-0000-4000-8000-000000001101','00000000-0000-4000-8000-000000000101','STUDENT',now()-interval '2 days'),
('00000000-0000-4000-8000-000000001102','00000000-0000-4000-8000-000000000201','TEACHER',now()-interval '2 days');
INSERT INTO lesson_facts(lesson_id,booking_id,teacher_id,student_id,subject_id,starts_at,ends_at,status,booked_at,cancelled_at,completed_at,goal_achieved,version) VALUES
('00000000-0000-4000-8000-000000000701','00000000-0000-4000-8000-000000000801','00000000-0000-4000-8000-000000000201','00000000-0000-4000-8000-000000000101','00000000-0000-4000-8000-000000000501',now()-interval '2 days',now()-interval '2 days'+interval '1 hour','COMPLETED',now()-interval '4 days',null,now()-interval '2 days'+interval '1 hour',true,2),
('00000000-0000-4000-8000-000000000702','00000000-0000-4000-8000-000000000802','00000000-0000-4000-8000-000000000201','00000000-0000-4000-8000-000000000102','00000000-0000-4000-8000-000000000501',now()+interval '4 days',now()+interval '4 days 1 hour','PLANNED',now()-interval '1 day',null,null,null,1);
INSERT INTO payment_facts(payment_id,booking_id,teacher_id,amount,currency,status,settled_at,version) VALUES
('00000000-0000-4000-8000-000000000901','00000000-0000-4000-8000-000000000801','00000000-0000-4000-8000-000000000201',60.00,'BYN','COMPLETED',now()-interval '3 days',1);
INSERT INTO review_facts(review_id,teacher_id,score,created_at) VALUES
('00000000-0000-4000-8000-000000001101','00000000-0000-4000-8000-000000000201',5,now()-interval '1 day');
INSERT INTO rating_projection(teacher_id,average,review_count,version,updated_at) VALUES
('00000000-0000-4000-8000-000000000201',5.000,1,1,now()-interval '1 day');
INSERT INTO teacher_popularity(teacher_id,completed_count,version,updated_at) VALUES
('00000000-0000-4000-8000-000000000201',1,1,now()),('00000000-0000-4000-8000-000000000202',0,0,now());

RESET ROLE;
