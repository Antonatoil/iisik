"""Local DB-X projection functions (Lab 6 Kafka consumers own normal delivery)."""
from app.core.db import engine
from app.core.commands import execute, fetch, now


def project_lesson(s):
    """Project each lesson version once, together with teacher popularity.

    Single DB-X transaction prevents half-applied fact/popularity projections.
    Repeating completion with the same version MUST NOT increment popularity.
    """
    if not s:
        return None
    with engine('x').begin() as conn:
        updated = execute(conn,"""INSERT INTO lesson_facts(lesson_id,booking_id,teacher_id,student_id,subject_id,starts_at,ends_at,
           status,booked_at,cancelled_at,completed_at,goal_achieved,version)
           VALUES(CAST(:lesson AS uuid),CAST(:booking AS uuid),CAST(:teacher AS uuid),CAST(:student AS uuid),
           CAST(:subject AS uuid),:starts,:ends,:status,now(),:cancelled,:completed,:goal,:version)
           ON CONFLICT(lesson_id) DO UPDATE SET starts_at=excluded.starts_at,ends_at=excluded.ends_at,
           status=excluded.status,cancelled_at=excluded.cancelled_at,completed_at=excluded.completed_at,
           goal_achieved=excluded.goal_achieved,version=excluded.version
           WHERE lesson_facts.version<excluded.version""",
           lesson=s['id'],booking=s['booking_id'],teacher=s['teacher_id'],student=s['student_id'],subject=s['subject_id'],
           starts=s['starts_at'],ends=s['ends_at'],status=s['status'],cancelled=None if s['status']!='CANCELLED' else now(),
           completed=s['completed_at'],goal=s['goal_achieved'],version=s['version'])
        if s['status'] == 'COMPLETED':
            if updated.rowcount:
                record = fetch(conn,"""SELECT count(*) AS n FROM lesson_facts
                    WHERE teacher_id=CAST(:t AS uuid) AND status='COMPLETED'""",t=s['teacher_id'])
                execute(conn,"""INSERT INTO teacher_popularity(teacher_id,completed_count,version,updated_at)
                    VALUES(CAST(:teacher AS uuid),:n,1,now()) ON CONFLICT(teacher_id) DO UPDATE
                    SET completed_count=excluded.completed_count,
                    version=teacher_popularity.version+1,updated_at=now()""",
                    teacher=s['teacher_id'],n=record['n'])
            return fetch(conn,'SELECT completed_count,version FROM teacher_popularity WHERE teacher_id=CAST(:t AS uuid)',t=s['teacher_id'])
    return None


def project_payment(payment,booking):
    with engine('x').begin() as conn:
        execute(conn,"""INSERT INTO payment_facts(payment_id,booking_id,teacher_id,amount,currency,status,settled_at,version)
         VALUES(CAST(:id AS uuid),CAST(:booking AS uuid),CAST(:teacher AS uuid),:amount,:currency,:status,:settled,1)
         ON CONFLICT(payment_id) DO NOTHING""",
         id=payment['id'],booking=booking['booking_id'],teacher=booking['teacher_id'],amount=booking['price'],
         currency=booking['currency'],status=payment['status'],settled=payment['settledAt'])


def project_review(review, teacher_id, rating):
    with engine('x').begin() as conn:
        execute(conn,"""INSERT INTO review_facts(review_id,teacher_id,score,created_at)
           VALUES(CAST(:id AS uuid),CAST(:teacher AS uuid),:score,:created) ON CONFLICT DO NOTHING""",
           id=review['id'],teacher=teacher_id,score=review['score'],created=review['createdAt'])
        execute(conn,"""INSERT INTO rating_projection(teacher_id,average,review_count,version,updated_at)
          VALUES(CAST(:teacher AS uuid),:avg,:count,:version,:at)
          ON CONFLICT(teacher_id) DO UPDATE SET average=excluded.average,review_count=excluded.review_count,
          version=excluded.version,updated_at=excluded.updated_at
          WHERE rating_projection.version<excluded.version""",teacher=teacher_id,avg=rating['average'],count=rating['reviewCount'],version=rating['version'],at=rating['updatedAt'])


def project_auth(user):
    from app.core.commands import new_id
    with engine('x').begin() as conn:
        execute(conn,"""INSERT INTO auth_facts(event_id,user_id,role_code,authenticated_at)
           VALUES(CAST(:id AS uuid),CAST(:user AS uuid),:role,now())""",id=new_id(),user=user['id'],role=user['role'])
