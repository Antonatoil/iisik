"""Domain events created in the owning service's DB transaction.

Envelope and payload follow Lab 2 contracts/events.schema.json exactly.
The outbox rows are committed together with the domain updates; publishing
is asynchronous and resilient to Kafka being temporarily unavailable.
"""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json

from sqlalchemy import text
from jsonschema import Draft202012Validator, FormatChecker

_SCHEMA = json.loads((Path(__file__).resolve().parents[2] / 'contracts' / 'events.schema.json').read_text(encoding='utf-8'))
_VALIDATOR = Draft202012Validator(_SCHEMA, format_checker=FormatChecker())
_TOPIC = 'tutor.events.v1'


def iso(dt):
    if dt is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def build(event_type, producer, aggregate_id, version, correlation_id, payload):
    evt = {'event_id': str(uuid4()), 'event_type': event_type, 'schema_version': 1,
           'occurred_at': iso(None), 'producer': producer,
           'aggregate_id': str(aggregate_id), 'aggregate_version': max(1, int(version)),
           'correlation_id': str(correlation_id), 'payload': payload}
    errors = list(_VALIDATOR.iter_errors(evt))
    if errors:
        raise ValueError('Lab 2 event contract violation: ' + errors[0].message)
    return evt


def stage(conn, event):
    conn.execute(text("""INSERT INTO event_outbox(event_id, topic, partition_key, envelope, created_at)
        VALUES(CAST(:id AS uuid), :topic, :key, CAST(:data AS jsonb), now())
        ON CONFLICT (event_id) DO NOTHING"""),
        {'id': event['event_id'], 'topic': _TOPIC, 'key': event['aggregate_id'],
         'data': json.dumps(event, ensure_ascii=False, separators=(',', ':'))})


def _lesson_snapshot(conn, lid):
    row = conn.execute(text("""SELECT l.id::text AS lesson_id, l.subject_id::text AS subject_id,
        l.status, l.completed_at, l.goal_achieved, l.version,
        b.id::text AS booking_id,b.student_id::text AS student_id,b.price,b.currency,
        b.created_at AS booked_at,s.id::text AS slot_id,s.teacher_id::text AS teacher_id,
        s.starts_at,s.ends_at
        FROM lessons l JOIN bookings b ON b.lesson_id=l.id JOIN slots s ON l.slot_id=s.id
        WHERE l.id=CAST(:id AS uuid)"""), {'id': lid}).mappings().first()
    return dict(row) if row else None


def lesson_payload(s):
    return {'booking_id':s['booking_id'], 'lesson_id':s['lesson_id'],
            'student_id':s['student_id'], 'teacher_id':s['teacher_id'],
            'subject_id':s['subject_id'], 'slot_id':s['slot_id'],
            'starts_at':iso(s['starts_at']), 'ends_at':iso(s['ends_at']),
            'booked_at':iso(s['booked_at']), 'price':str(s['price']),
            'currency':s['currency'],
            'recipient_user_ids':[s['student_id'],s['teacher_id']],
            'status':s['status']}


def on_receipt(conn, op_id, actor_id, command, payload, result):
    owner = None
    if command in ('bookLesson','rescheduleLesson','cancelLesson','completeLesson','setAvailability'):
        owner = 'l'
    if command == 'addReview':
        owner = 'r'
    if owner == 'l':
        if command == 'setAvailability':
            ids = [s['id'] for s in result.get('slots', [])] + list(payload.get('removeIds', []))
            for slot_id in dict.fromkeys(ids):
                row = conn.execute(text("""SELECT id::text,teacher_id::text,starts_at,ends_at,status,version
                    FROM slots WHERE id=CAST(:id AS uuid)"""), {'id':slot_id}).mappings().first()
                if not row:
                    continue
                q=dict(row)
                p={'slot_id':q['id'],'teacher_id':q['teacher_id'],
                   'starts_at':iso(q['starts_at']),'ends_at':iso(q['ends_at']),
                   'status':q['status'],'cause':'DIRECT','related_event_id':None,
                   'recipient_user_ids':[q['teacher_id']]}
                stage(conn,build('ScheduleChanged','L',q['id'],q['version'],op_id,p))
            return
        lesson_id = result['lesson_id'] if command == 'bookLesson' else payload['lessonId']
        s = _lesson_snapshot(conn,lesson_id)
        if not s:
            raise RuntimeError('Missing lesson snapshot for transactional outbox')
        p = lesson_payload(s)
        names={'bookLesson':'LessonBooked', 'cancelLesson':'LessonCancelled',
               'rescheduleLesson':'LessonRescheduled', 'completeLesson':'LessonCompleted'}
        if command=='cancelLesson':
            p['cancelled_at'] = iso(None)
        if command=='completeLesson':
            p['completed_at'] = iso(s['completed_at'])
            p['goal_achieved'] = s['goal_achieved']
        if command=='rescheduleLesson':
            old=conn.execute(text("""SELECT old_slot_id::text,old_starts_at,old_ends_at FROM lesson_moves
                   WHERE lesson_id=CAST(:id AS uuid) ORDER BY changed_at DESC LIMIT 1"""),
                   {'id':lesson_id}).mappings().one()
            p.update(old_slot_id=old['old_slot_id'],old_starts_at=iso(old['old_starts_at']),
                     old_ends_at=iso(old['old_ends_at']))
        stage(conn,build(names[command],'L',lesson_id,s['version'],op_id,p))
    elif owner=='r':
        rating=conn.execute(text("""SELECT teacher_id::text,average,review_count,version,updated_at
             FROM ratings WHERE teacher_id=CAST(:id AS uuid)"""),
             {'id':result['teacherId']}).mappings().one()
        p={'review_id':result['id'],'booking_id':payload['bookingId'],
           'teacher_id':result['teacherId'],'score':int(result['score']),
           'created_at':iso(result['createdAt'])}
        stage(conn,build('ReviewCreated','R',result['id'],1,op_id,p))
        p2={'teacher_id':result['teacherId'],'average':str(rating['average']),
            'review_count':int(rating['review_count']),'updated_at':iso(rating['updated_at'])}
        stage(conn,build('RatingUpdated','R',result['teacherId'],rating['version'],op_id,p2))


def on_payment(conn, actor, arg, booking, result):
    if result['status'] not in ('COMPLETED','FAILED'):
        return
    p={'payment_id':result['id'],'booking_id':arg['bookingId'],'operation_id':arg['operationId'],
       'lesson_id':booking['lesson_id'],'student_id':actor['id'],'teacher_id':booking['teacher_id'],
       'amount':str(booking['price']),'currency':booking['currency'],
       'settled_at':iso(result['settledAt']),'recipient_user_ids':[actor['id']],
       'status':result['status']}
    typ='PaymentCompleted' if result['status']=='COMPLETED' else 'PaymentFailed'
    if typ=='PaymentFailed':p['failure_code']=result['failureCode'] or 'DECLINED'
    stage(conn,build(typ,'P',result['id'],1,arg['operationId'],p))
