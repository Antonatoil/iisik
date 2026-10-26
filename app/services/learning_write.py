"""Business write-side for lessons/availability; DB-L ONLY.
Local transactions, teacher advisory locks, optimistic versions and owner checks.
"""
from app.core.db import engine
from app.core.commands import new_id, fetch, execute, check_receipt, save_receipt, business_condition, now
from app.core.validation import valid_id
from app.core.errors import fail
from app.services.learning import slot_map, lesson_map, booking_map

SLOT_SELECT='SELECT id::text,teacher_id::text,starts_at,ends_at,status,version FROM slots WHERE id=CAST(:id AS uuid) FOR UPDATE'
LESSON_JOIN="""SELECT l.id::text,l.slot_id::text,l.subject_id::text,l.topic,l.status,l.result_text,l.goal_achieved,
 l.started_at,l.completed_at,l.version,b.id::text AS booking_id,b.student_id::text,b.status AS booking_status,
 b.payment_state,b.payment_operation_id::text,s.teacher_id::text,s.starts_at,s.ends_at,s.status AS slot_status
 FROM lessons l JOIN bookings b ON b.lesson_id=l.id JOIN slots s ON s.id=l.slot_id
 WHERE l.id=CAST(:id AS uuid) FOR UPDATE OF l,b,s"""


def _teacher_lock(conn, teacher_id):
    execute(conn,'SELECT pg_advisory_xact_lock(hashtext(:id))',id=teacher_id)


def set_availability(actor,arg):
    business_condition(arg['upsert'] or arg['removeIds'],'BAD_USER_INPUT','Provide upsert or removeIds')
    with engine('l').begin() as conn:
        _teacher_lock(conn,actor['id'])
        cached=check_receipt(conn,arg['operationId'],actor['id'],'setAvailability',arg)
        if cached:return cached
        removals=[valid_id(i) for i in arg['removeIds']]
        business_condition(len(set(removals))==len(removals),'BAD_USER_INPUT','Duplicate removeIds')
        for sid in removals:
            s=fetch(conn,SLOT_SELECT,id=sid)
            business_condition(s is not None and s['teacher_id']==actor['id'],'NOT_FOUND','Slot not found')
            business_condition(s['status'] in ('AVAILABLE','CLOSED'),'INVALID_STATE','Cannot remove booked slot')
            execute(conn,"UPDATE slots SET status='REMOVED',version=version+1 WHERE id=CAST(:id AS uuid)",id=sid)
        output=[]
        for entry in arg['upsert']:
            start,end=entry['startsAt'],entry['endsAt']
            business_condition(start<end and start>now(),'BAD_USER_INPUT','Slot must start in future and end after start')
            sid=valid_id(entry['id']) if entry.get('id') else new_id()
            existing=fetch(conn,SLOT_SELECT,id=sid)
            if existing:
                business_condition(existing['teacher_id']==actor['id'],'FORBIDDEN','Cannot edit another teacher slot')
                business_condition(existing['status']=='AVAILABLE','INVALID_STATE','Only an available slot can be changed')
            business_condition(fetch(conn,"""SELECT id FROM slots WHERE teacher_id=CAST(:teacher AS uuid)
                AND status IN ('AVAILABLE','BOOKED') AND id<>CAST(:id AS uuid)
                AND starts_at<:end AND ends_at>:start LIMIT 1""",teacher=actor['id'],id=sid,start=start,end=end) is None,
                'SLOT_CONFLICT','Teacher already has an overlapping slot')
            if existing:
                execute(conn,"""UPDATE slots SET starts_at=:start,ends_at=:end,status='AVAILABLE',version=version+1 WHERE id=CAST(:id AS uuid)""",id=sid,start=start,end=end)
            else:
                execute(conn,"""INSERT INTO slots(id,teacher_id,starts_at,ends_at,status,version)
                 VALUES(CAST(:id AS uuid),CAST(:teacher AS uuid),:start,:end,'AVAILABLE',1)""",id=sid,teacher=actor['id'],start=start,end=end)
            output.append(slot_map(fetch(conn,SLOT_SELECT,id=sid)))
        return save_receipt(conn,arg['operationId'],actor['id'],'setAvailability',arg,{'slots':output})


def book_lesson(actor,arg,offer):
    business_condition(offer is not None,'INVALID_OFFER','Teacher does not teach this active subject')
    slot_id=valid_id(arg['slotId'])
    business_condition(bool(arg['topic'].strip()) and len(arg['topic'])<=200,'BAD_USER_INPUT','Topic is required')
    with engine('l').begin() as conn:
        _teacher_lock(conn,offer['teacher_id'])
        cached=check_receipt(conn,arg['operationId'],actor['id'],'bookLesson',arg)
        if cached:return cached
        s=fetch(conn,SLOT_SELECT,id=slot_id)
        business_condition(s is not None and s['teacher_id']==offer['teacher_id'],'NOT_FOUND','Slot is missing')
        business_condition(s['status']=='AVAILABLE' and s['starts_at']>now(),'SLOT_UNAVAILABLE','Slot is not free or already started')
        execute(conn,"SELECT pg_advisory_xact_lock(hashtext(:student))",student='student:'+actor['id'])
        business_condition(fetch(conn,"""SELECT b.id FROM bookings b JOIN lessons l ON b.lesson_id=l.id JOIN slots s ON l.slot_id=s.id
          WHERE b.student_id=CAST(:student AS uuid) AND b.status='ACTIVE' AND l.status IN ('PLANNED','IN_PROGRESS')
          AND s.starts_at<:end AND s.ends_at>:start LIMIT 1""",student=actor['id'],start=s['starts_at'],end=s['ends_at']) is None,
          'STUDENT_SCHEDULE_CONFLICT','Student already has a lesson at this time')
        lid,bid=new_id(),new_id()
        execute(conn,"""INSERT INTO lessons(id,slot_id,subject_id,topic,status,version)
           VALUES(CAST(:id AS uuid),CAST(:slot AS uuid),CAST(:subject AS uuid),:topic,'PLANNED',1)""",
           id=lid,slot=slot_id,subject=arg['subjectId'],topic=arg['topic'].strip())
        execute(conn,"""INSERT INTO bookings(id,lesson_id,student_id,status,price,currency,payment_state,created_at)
           VALUES(CAST(:id AS uuid),CAST(:lesson AS uuid),CAST(:student AS uuid),'ACTIVE',:price,:currency,'UNPAID',now())""",
           id=bid,lesson=lid,student=actor['id'],price=offer['price'],currency=offer['currency'])
        execute(conn,"UPDATE slots SET status='BOOKED',version=version+1 WHERE id=CAST(:id AS uuid)",id=slot_id)
        b=fetch(conn,"""SELECT id::text,lesson_id::text,student_id::text,status,price,currency,payment_state,created_at FROM bookings WHERE id=CAST(:id AS uuid)""",id=bid)
        return save_receipt(conn,arg['operationId'],actor['id'],'bookLesson',arg,booking_map(b))


def lesson_snapshot(lesson_id):
    from app.core.db import one
    return one('l',LESSON_JOIN.replace('FOR UPDATE OF l,b,s',''),{'id':valid_id(lesson_id)})


def booking_snapshot(booking_id):
    from app.core.db import one
    return one('l',"""SELECT b.id::text AS booking_id,b.student_id::text,b.lesson_id::text,b.status AS booking_status,
      b.price,b.currency,b.payment_state,b.payment_operation_id::text,l.status AS lesson_status,
      l.version,s.teacher_id::text,s.starts_at,s.ends_at,s.id::text AS slot_id
      FROM bookings b JOIN lessons l ON b.lesson_id=l.id JOIN slots s ON l.slot_id=s.id
      WHERE b.id=CAST(:id AS uuid)""",{'id':valid_id(booking_id)})


def _check_owner(actor,s):
    business_condition(actor['id']==(s['student_id'] if actor['role']=='STUDENT' else s['teacher_id']),
        'FORBIDDEN','Lesson does not belong to current user')


def change_lesson(actor,arg,action):
    lid=valid_id(arg['lessonId'])
    with engine('l').begin() as conn:
        first=fetch(conn,"""SELECT s.teacher_id::text FROM lessons l JOIN slots s ON s.id=l.slot_id WHERE l.id=CAST(:id AS uuid)""",id=lid)
        business_condition(first is not None,'NOT_FOUND','Lesson not found')
        _teacher_lock(conn,first['teacher_id'])
        cached=check_receipt(conn,arg['operationId'],actor['id'],action,arg)
        if cached:return cached
        s=fetch(conn,LESSON_JOIN,id=lid)
        _check_owner(actor,s)
        business_condition(s['version']==arg['expectedVersion'],'VERSION_CONFLICT','Lesson version has changed')
        if action=='cancelLesson':
            business_condition(s['status']=='PLANNED' and s['starts_at']>now() and s['payment_state']!='PROCESSING',
                'INVALID_STATE','Cancellation prohibited in current state')
            execute(conn,"UPDATE lessons SET status='CANCELLED',version=version+1 WHERE id=CAST(:id AS uuid)",id=lid)
            execute(conn,"UPDATE bookings SET status='CANCELLED' WHERE lesson_id=CAST(:id AS uuid)",id=lid)
            execute(conn,"UPDATE slots SET status='AVAILABLE',version=version+1 WHERE id=CAST(:id AS uuid)",id=s['slot_id'])
        elif action=='rescheduleLesson':
            business_condition(s['status']=='PLANNED' and s['starts_at']>now() and s['payment_state']!='PROCESSING',
                'INVALID_STATE','Rescheduling prohibited in current state')
            new_id_slot=valid_id(arg['newSlotId'])
            target=fetch(conn,SLOT_SELECT,id=new_id_slot)
            business_condition(target is not None and target['teacher_id']==s['teacher_id'] and target['status']=='AVAILABLE' and target['starts_at']>now(),
                'SLOT_UNAVAILABLE','Target slot unavailable')
            execute(conn,"SELECT pg_advisory_xact_lock(hashtext(:student))",student='student:'+s['student_id'])
            business_condition(fetch(conn,"""SELECT b.id FROM bookings b JOIN lessons l ON b.lesson_id=l.id JOIN slots t ON t.id=l.slot_id
              WHERE b.student_id=CAST(:student AS uuid) AND b.status='ACTIVE' AND l.id<>CAST(:lesson AS uuid)
              AND l.status IN ('PLANNED','IN_PROGRESS') AND t.starts_at<:end AND t.ends_at>:start LIMIT 1""",
              student=s['student_id'],lesson=lid,start=target['starts_at'],end=target['ends_at']) is None,
              'STUDENT_SCHEDULE_CONFLICT','New time conflicts with other student booking')
            execute(conn,"UPDATE slots SET status='AVAILABLE',version=version+1 WHERE id=CAST(:id AS uuid)",id=s['slot_id'])
            execute(conn,"UPDATE slots SET status='BOOKED',version=version+1 WHERE id=CAST(:id AS uuid)",id=new_id_slot)
            execute(conn,"UPDATE lessons SET slot_id=CAST(:slot AS uuid),version=version+1 WHERE id=CAST(:id AS uuid)",slot=new_id_slot,id=lid)
            execute(conn,"""INSERT INTO lesson_moves(id,lesson_id,old_slot_id,new_slot_id,old_starts_at,old_ends_at,new_starts_at,new_ends_at,actor_user_id,changed_at)
              VALUES(CAST(:id AS uuid),CAST(:lesson AS uuid),CAST(:old AS uuid),CAST(:new AS uuid),:os,:oe,:ns,:ne,CAST(:actor AS uuid),now())""",
              id=new_id(),lesson=lid,old=s['slot_id'],new=new_id_slot,os=s['starts_at'],oe=s['ends_at'],ns=target['starts_at'],ne=target['ends_at'],actor=actor['id'])
        elif action=='startLesson':
            business_condition(actor['role']=='TEACHER','FORBIDDEN','Only teacher can start lesson')
            business_condition(s['status']=='PLANNED' and s['payment_state']=='PAID' and s['starts_at']<=now()<s['ends_at'],
                 'INVALID_STATE','Lesson requires PAID booking and scheduled start time')
            execute(conn,"UPDATE lessons SET status='IN_PROGRESS',started_at=now(),version=version+1 WHERE id=CAST(:id AS uuid)",id=lid)
        elif action=='completeLesson':
            business_condition(actor['role']=='TEACHER','FORBIDDEN','Only teacher can complete lesson')
            business_condition(s['status']=='IN_PROGRESS','INVALID_STATE','Lesson is not in progress')
            business_condition(bool(arg['resultText'].strip()),'BAD_USER_INPUT','Result description is required')
            goal={'ACHIEVED':True,'NOT_ACHIEVED':False,'NOT_ASSESSED':None}[arg['goalOutcome']]
            execute(conn,"""UPDATE lessons SET status='COMPLETED',result_text=:text,goal_achieved=:goal,
              completed_at=now(),version=version+1 WHERE id=CAST(:id AS uuid)""",id=lid,text=arg['resultText'].strip(),goal=goal)
            execute(conn,"UPDATE bookings SET status='COMPLETED' WHERE lesson_id=CAST(:id AS uuid)",id=lid)
            execute(conn,"UPDATE slots SET status='CLOSED',version=version+1 WHERE id=CAST(:id AS uuid)",id=s['slot_id'])
        else:raise ValueError(action)
        if action in ('cancelLesson','rescheduleLesson'):
            b=fetch(conn,"SELECT id::text,lesson_id::text,student_id::text,status,price,currency,payment_state,created_at FROM bookings WHERE lesson_id=CAST(:id AS uuid)",id=lid)
            return save_receipt(conn,arg['operationId'],actor['id'],action,arg,booking_map(b))
        l=fetch(conn,"SELECT id::text,slot_id::text,subject_id::text,topic,status,result_text,goal_achieved,started_at,completed_at,version FROM lessons WHERE id=CAST(:id AS uuid)",id=lid)
        return save_receipt(conn,arg['operationId'],actor['id'],action,arg,lesson_map(l))


def apply_payment(booking_id, operation_id):
    with engine('l').begin() as conn:
        b=fetch(conn,'SELECT id::text,payment_state,payment_operation_id::text,status FROM bookings WHERE id=CAST(:id AS uuid) FOR UPDATE',id=booking_id)
        business_condition(b is not None and b['status']=='ACTIVE','INVALID_STATE','Booking is not active')
        if b['payment_state']=='PAID':
            business_condition(b['payment_operation_id']==operation_id,'ALREADY_PAID','Booking already paid')
            return
        business_condition(b['payment_state']!='PROCESSING' or b['payment_operation_id']==operation_id,'INVALID_STATE','Payment in progress')
        execute(conn,"UPDATE bookings SET payment_state='PAID',payment_operation_id=CAST(:op AS uuid) WHERE id=CAST(:id AS uuid)",op=operation_id,id=booking_id)
