"""Real Kafka consumers: DB-X facts, DB-N notifications, DB-T projections.

Each event is validated against original Lab-2 JSON schema. Its business effect
and inbox marker commit in one local DB transaction. Kafka offsets are committed
AFTER the transaction, yielding at-least-once delivery with idempotent effects.
"""
import json
import logging
import os
import time
from threading import Event

from confluent_kafka import Consumer, TopicPartition
from sqlalchemy import text
from app.core.db import engine
from app.events.domain import _VALIDATOR, stage, build, iso
from app.events.publisher import producer

LOG = logging.getLogger(__name__)
CONSUMERS = {
    't': {'RatingUpdated', 'PopularityUpdated'},
    'n': {'LessonBooked', 'LessonCancelled','LessonRescheduled','LessonCompleted',
          'PaymentCompleted','PaymentFailed','ReviewCreated'},
    'x': {'UserAuthenticated','LessonBooked','LessonCancelled','LessonRescheduled',
          'LessonCompleted','PaymentCompleted','PaymentFailed','ReviewCreated','RatingUpdated'},
    'l': {'PaymentCompleted'},
}


def _notifications(conn, evt):
    typ, p = evt['event_type'], evt['payload']
    labels={
        'LessonBooked':'Вы записаны на занятие',
        'LessonCancelled':'Занятие отменено',
        'LessonRescheduled':'Занятие перенесено',
        'LessonCompleted':'Занятие завершено',
        'PaymentCompleted':'Оплата занятия подтверждена (демо)',
        'PaymentFailed':'Оплата не выполнена (демо)',
        'ReviewCreated':'Оставлен новый отзыв',
    }
    recipients = p.get('recipient_user_ids') or ([p['teacher_id']] if typ == 'ReviewCreated' else [])
    subject = p.get('lesson_id') or p.get('booking_id') or p.get('review_id')
    for uid in recipients:
        conn.execute(text("""INSERT INTO notifications(id,user_id,event_id,kind,text,object_id,created_at)
            VALUES(gen_random_uuid(),CAST(:user AS uuid),CAST(:event AS uuid),:kind,:body,
                CAST(:obj AS uuid),now()) ON CONFLICT(event_id,user_id) DO NOTHING"""),
            {'user':uid,'event':evt['event_id'],'kind':typ,'body':labels[typ], 'obj':subject})


def _catalog(conn, evt):
    typ,p=evt['event_type'],evt['payload']
    if typ=='RatingUpdated':
        conn.execute(text("""INSERT INTO teacher_metrics(teacher_id,average,review_count,rating_version,
              completed_count,popularity_version,last_review_at,updated_at)
           VALUES(CAST(:teacher AS uuid),:avg,:count,:version,0,0,:at,now())
           ON CONFLICT(teacher_id) DO UPDATE SET average=EXCLUDED.average,
             review_count=EXCLUDED.review_count,rating_version=EXCLUDED.rating_version,
             last_review_at=EXCLUDED.last_review_at,updated_at=now()
           WHERE teacher_metrics.rating_version<EXCLUDED.rating_version"""),
           {'teacher':p['teacher_id'],'avg':p['average'],'count':p['review_count'],
            'version':evt['aggregate_version'],'at':p['updated_at']})
    elif typ=='PopularityUpdated':
        conn.execute(text("""UPDATE teacher_metrics SET completed_count=:n,
              popularity_version=:version, updated_at=now()
              WHERE teacher_id=CAST(:teacher AS uuid) AND popularity_version<:version"""),
              {'teacher':p['teacher_id'],'n':p['completed_count'],
               'version':evt['aggregate_version']})


def _lesson_fact(conn, evt):
    p=evt['payload']
    cancelled=p.get('cancelled_at')
    goal=p.get('goal_achieved')
    result=conn.execute(text("""INSERT INTO lesson_facts(lesson_id,booking_id,teacher_id,student_id,
       subject_id,starts_at,ends_at,status,booked_at,cancelled_at,completed_at,goal_achieved,version)
       VALUES(CAST(:lesson AS uuid),CAST(:booking AS uuid),CAST(:teacher AS uuid),
        CAST(:student AS uuid),CAST(:subject AS uuid),:starts,:ends,:status,:booked,
        :cancelled,:completed,:goal,:version)
       ON CONFLICT(lesson_id) DO UPDATE SET starts_at=EXCLUDED.starts_at,
       ends_at=EXCLUDED.ends_at,status=EXCLUDED.status,cancelled_at=EXCLUDED.cancelled_at,
       completed_at=EXCLUDED.completed_at,goal_achieved=EXCLUDED.goal_achieved,
       version=EXCLUDED.version WHERE lesson_facts.version<EXCLUDED.version"""),
       {'lesson':p['lesson_id'],'booking':p['booking_id'],'teacher':p['teacher_id'],
        'student':p['student_id'],'subject':p['subject_id'],'starts':p['starts_at'],
        'ends':p['ends_at'],'status':p['status'],'booked':p['booked_at'],
        'cancelled':cancelled,'completed':p.get('completed_at'),'goal':goal,
        'version':evt['aggregate_version']})
    if evt['event_type']=='LessonCompleted' and result.rowcount:
        # Recompute absolute completed count from facts, never increment blindly.
        count=conn.execute(text("""SELECT count(*) FROM lesson_facts
           WHERE teacher_id=CAST(:t AS uuid) AND status='COMPLETED'"""),
           {'t':p['teacher_id']}).scalar_one()
        conn.execute(text("""INSERT INTO teacher_popularity(teacher_id,completed_count,version,updated_at)
          VALUES(CAST(:t AS uuid),:n,1,now()) ON CONFLICT(teacher_id) DO UPDATE SET
          completed_count=EXCLUDED.completed_count,version=teacher_popularity.version+1,
          updated_at=now()"""), {'t':p['teacher_id'],'n':count})
        state=conn.execute(text("""SELECT version,updated_at FROM teacher_popularity
           WHERE teacher_id=CAST(:t AS uuid)"""),{'t':p['teacher_id']}).mappings().one()
        event=build('PopularityUpdated','X',p['teacher_id'],state['version'],
                    evt['correlation_id'],{'teacher_id':p['teacher_id'],
                    'completed_count':count,'updated_at':iso(state['updated_at'])})
        stage(conn,event)


def _analytics(conn, evt):
    typ,p=evt['event_type'],evt['payload']
    if typ in {'LessonBooked','LessonCancelled','LessonRescheduled','LessonCompleted'}:
        _lesson_fact(conn,evt)
    elif typ=='PaymentCompleted':
        conn.execute(text("""INSERT INTO payment_facts(payment_id,booking_id,teacher_id,amount,currency,
            status,settled_at,version)
            VALUES(CAST(:id AS uuid),CAST(:booking AS uuid),CAST(:teacher AS uuid),
            :amount,:currency,'COMPLETED',:settled,1)
            ON CONFLICT(payment_id) DO NOTHING"""),
            {'id':p['payment_id'],'booking':p['booking_id'],'teacher':p['teacher_id'],
             'amount':p['amount'],'currency':p['currency'],'settled':p['settled_at']})
    elif typ=='ReviewCreated':
        conn.execute(text("""INSERT INTO review_facts(review_id,teacher_id,score,created_at)
          VALUES(CAST(:id AS uuid),CAST(:teacher AS uuid),:score,:created)
          ON CONFLICT(review_id) DO NOTHING"""),
          {'id':p['review_id'],'teacher':p['teacher_id'],'score':p['score'],
           'created':p['created_at']})
    elif typ=='RatingUpdated':
        conn.execute(text("""INSERT INTO rating_projection(teacher_id,average,review_count,version,updated_at)
          VALUES(CAST(:teacher AS uuid),:average,:count,:version,:updated)
          ON CONFLICT(teacher_id) DO UPDATE SET average=EXCLUDED.average,
           review_count=EXCLUDED.review_count, version=EXCLUDED.version,
           updated_at=EXCLUDED.updated_at
          WHERE rating_projection.version<EXCLUDED.version"""),
          {'teacher':p['teacher_id'],'average':p['average'],'count':p['review_count'],
           'version':evt['aggregate_version'],'updated':p['updated_at']})
    elif typ=='UserAuthenticated':
        conn.execute(text("""INSERT INTO auth_facts(event_id,user_id,role_code,authenticated_at)
          VALUES(CAST(:event AS uuid),CAST(:user AS uuid),:role,:at)
          ON CONFLICT(event_id) DO NOTHING"""),
          {'event':evt['event_id'],'user':p['user_id'],'role':p['role'],
           'at':p['authenticated_at']})


def _learning(conn, evt):
    p=evt['payload']
    b=conn.execute(text("""SELECT id::text,payment_state,payment_operation_id::text,status
       FROM bookings WHERE id=CAST(:id AS uuid) FOR UPDATE"""),
       {'id':p['booking_id']}).mappings().first()
    if b is None or b['status']!='ACTIVE':
        # Booking may have been cancelled before the event is consumed; avoid resurrection.
        return
    if b['payment_state']=='PAID':
        if b['payment_operation_id']!=p['operation_id']:
            raise RuntimeError('Payment event conflicts with another successful payment')
        return
    conn.execute(text("""UPDATE bookings SET payment_state='PAID',
      payment_operation_id=CAST(:op AS uuid) WHERE id=CAST(:id AS uuid)"""),
      {'id':p['booking_id'],'op':p['operation_id']})


def process(owner, evt):
    typ=evt['event_type']
    if typ not in CONSUMERS.get(owner,set()):
        return False
    with engine(owner).begin() as conn:
        seen=conn.execute(text('SELECT 1 FROM event_inbox WHERE event_id=CAST(:id AS uuid)'),
                          {'id':evt['event_id']}).scalar_one_or_none()
        if seen:
            return False
        if owner=='t':_catalog(conn,evt)
        elif owner=='n':_notifications(conn,evt)
        elif owner=='x':_analytics(conn,evt)
        elif owner=='l':_learning(conn,evt)
        conn.execute(text("""INSERT INTO event_inbox(event_id,event_type,processed_at)
             VALUES(CAST(:id AS uuid),:typ,now()) ON CONFLICT DO NOTHING"""),
             {'id':evt['event_id'],'typ':typ})
    return True


def consumer_loop(owner, stop:Event):
    consumer=Consumer({'bootstrap.servers':os.getenv('KAFKA_BOOTSTRAP','kafka:9092'),
       'group.id':'tutoring-lab6-'+owner+'-v1', 'enable.auto.commit':False,
       'auto.offset.reset':'earliest', 'allow.auto.create.topics':False,
       'client.id':'tutoring-consumer-'+owner})
    consumer.subscribe(['tutor.events.v1'])
    retries={}
    try:
        while not stop.is_set():
            try:
                msg=consumer.poll(1.0)
                if msg is None:continue
                if msg.error():
                    LOG.warning('Kafka error %s: %s',owner,msg.error());continue
                pos=(msg.topic(),msg.partition(),msg.offset())
                try:
                    evt=json.loads(msg.value())
                    errors=list(_VALIDATOR.iter_errors(evt))
                    if errors:
                        raise ValueError(errors[0].message)
                    process(owner,evt)
                    consumer.commit(message=msg,asynchronous=False)
                    retries.pop(pos,None)
                except (json.JSONDecodeError,ValueError,UnicodeDecodeError) as exc:
                    # Invalid contract cannot be fixed by retrying. Keep DLQ evidence.
                    LOG.error('Rejected invalid event: %s',exc)
                    try:
                        payload={'error':str(exc),'source_topic':msg.topic(),
                                 'source_partition':msg.partition(),'source_offset':msg.offset(),
                                 'payload':msg.value().decode('utf-8','replace')}
                        p=producer()
                        ack=[]
                        p.produce('tutor.events.dlq.v1',json.dumps(payload).encode(),
                                  on_delivery=lambda err,record:ack.append(err))
                        assert p.flush(10)==0 and ack==[None]
                        consumer.commit(message=msg,asynchronous=False)
                    except Exception:
                        LOG.exception('DLQ unavailable; will retry original Kafka record')
                        consumer.seek(TopicPartition(msg.topic(),msg.partition(),msg.offset()))
                        stop.wait(2)
                except Exception:
                    retries[pos]=retries.get(pos,0)+1
                    LOG.exception('Event processing failed for %s, attempt %s',owner,retries[pos])
                    consumer.seek(TopicPartition(msg.topic(),msg.partition(),msg.offset()))
                    stop.wait(min(5,retries[pos]))
            except Exception:
                LOG.exception('Kafka consumer %s failure',owner)
                stop.wait(2)
    finally:
        consumer.close()
