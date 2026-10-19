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
