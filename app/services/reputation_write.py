"""Review submission, unique booking + local atomic rating in DB-R."""
from app.core.db import engine
from app.core.commands import new_id, fetch, execute, check_receipt, save_receipt, business_condition
from app.core.validation import valid_id
from app.services.reputation import get_rating


def add_review(actor,arg,booking):
    business_condition(1<=arg['score']<=5,'BAD_USER_INPUT','Rating must be 1..5')
    business_condition(bool(arg['text'].strip()),'BAD_USER_INPUT','Review text is required')
    business_condition(booking is not None and booking['student_id']==actor['id'] and
                       booking['booking_status']=='COMPLETED' and booking['lesson_status']=='COMPLETED',
                       'INVALID_STATE','Only completed own booking can be reviewed')
    with engine('r').begin() as conn:
        cached=check_receipt(conn,arg['operationId'],actor['id'],'addReview',arg)
        if cached:return cached
        business_condition(fetch(conn,'SELECT id FROM reviews WHERE booking_id=CAST(:id AS uuid)',id=arg['bookingId']) is None,
            'ALREADY_REVIEWED','One review allowed per booking')
        rid=new_id()
        execute(conn,"""INSERT INTO reviews(id,booking_id,student_id,teacher_id,score,text,created_at)
          VALUES(CAST(:id AS uuid),CAST(:booking AS uuid),CAST(:student AS uuid),CAST(:teacher AS uuid),:score,:body,now())""",
          id=rid,booking=arg['bookingId'],student=actor['id'],teacher=booking['teacher_id'],score=arg['score'],body=arg['text'].strip())
        execute(conn,"""INSERT INTO ratings(teacher_id,score_sum,review_count,average,version,updated_at)
         VALUES(CAST(:teacher AS uuid),:score,1,:score,1,now())
         ON CONFLICT (teacher_id) DO UPDATE SET score_sum=ratings.score_sum+excluded.score_sum,
          review_count=ratings.review_count+1,
          average=round((ratings.score_sum+excluded.score_sum)::numeric/(ratings.review_count+1),3),
          version=ratings.version+1,updated_at=now()""",teacher=booking['teacher_id'],score=arg['score'])
        result=fetch(conn,"SELECT id::text,teacher_id::text AS \"teacherId\",score,text,created_at AS \"createdAt\" FROM reviews WHERE id=CAST(:id AS uuid)",id=rid)
        return save_receipt(conn,arg['operationId'],actor['id'],'addReview',arg,result)
