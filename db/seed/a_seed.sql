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
