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
