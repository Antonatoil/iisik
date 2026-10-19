INSERT INTO reviews(id,booking_id,student_id,teacher_id,score,text,created_at) VALUES
('00000000-0000-4000-8000-000000001101','00000000-0000-4000-8000-000000000801','00000000-0000-4000-8000-000000000101','00000000-0000-4000-8000-000000000201',5,'Преподаватель объясняет понятно',now()-interval '1 day');
INSERT INTO ratings(teacher_id,score_sum,review_count,average,version,updated_at) VALUES
('00000000-0000-4000-8000-000000000201',5,1,5.000,1,now()-interval '1 day');
