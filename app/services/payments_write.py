"""Deterministic simulated payment in DB-P: no real money or payment provider."""
from app.core.db import engine
from app.core.commands import new_id, fetch, execute, business_condition
from app.core.validation import valid_id


def register_payment(actor,arg,booking):
    op=valid_id(arg['operationId'])
    with engine('p').begin() as conn:
        # Serialize concurrent payments for one booking and repeated operation IDs.
        execute(conn, 'SELECT pg_advisory_xact_lock(hashtext(:key))', key='payment:'+arg['bookingId'])
        execute(conn, 'SELECT pg_advisory_xact_lock(hashtext(:key))', key='operation:'+op)
        old=fetch(conn,"""SELECT id::text,operation_id::text,booking_id::text,student_id::text,status,amount,currency,
          failure_code,created_at,settled_at FROM payments WHERE operation_id=CAST(:id AS uuid)""",id=op)
        if old:
            business_condition(old['student_id']==actor['id'] and old['booking_id']==arg['bookingId'],
                'IDEMPOTENCY_CONFLICT','Payment operation key already used')
            return _map(old)
        business_condition(fetch(conn,"SELECT id FROM payments WHERE booking_id=CAST(:booking AS uuid) AND status='COMPLETED'",booking=arg['bookingId']) is None,
            'ALREADY_PAID','Booking already has a confirmed payment')
        pid=new_id()
        execute(conn,"""INSERT INTO payments(id,operation_id,booking_id,student_id,teacher_id,lesson_id,amount,currency,
            status,failure_code,created_at,settled_at,version)
            VALUES(CAST(:id AS uuid),CAST(:op AS uuid),CAST(:booking AS uuid),CAST(:student AS uuid),CAST(:teacher AS uuid),
            CAST(:lesson AS uuid),:amount,:currency,'COMPLETED',NULL,now(),now(),1)""",
            id=pid,op=op,booking=arg['bookingId'],student=actor['id'],teacher=booking['teacher_id'],lesson=booking['lesson_id'],
            amount=booking['price'],currency=booking['currency'])
        result=_map(fetch(conn,"""SELECT id::text,operation_id::text,booking_id::text,status,amount,currency,failure_code,created_at,settled_at
           FROM payments WHERE id=CAST(:id AS uuid)""",id=pid))
        from app.events.domain import on_payment
        on_payment(conn,actor,arg,booking,result)
        return result


def _map(r):
    return {'id':r['id'],'operationId':r['operation_id'],'bookingId':r['booking_id'],'status':r['status'],
      'money':({'amount':r['amount'],'currency':r['currency']} if r['amount'] is not None else None),
      'failureCode':r['failure_code'],'createdAt':r['created_at'],'settledAt':r['settled_at']}
