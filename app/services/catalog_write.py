"""Write operations for teacher catalog and subjects (DB-T only)."""
from decimal import Decimal
from app.core.db import engine
from app.core.commands import new_id, fetch, execute, check_receipt, save_receipt, business_condition
from app.core.validation import valid_id, decimal_or_none
from app.services.catalog import get_teacher


def teaching_offer(teacher_id,subject_id):
    from app.core.db import one
    return one('t',"""SELECT t.id::text AS teacher_id,t.price,t.currency,s.id::text AS subject_id
      FROM teachers t JOIN teacher_subjects ts ON ts.teacher_id=t.id JOIN subjects s ON s.id=ts.subject_id
      WHERE t.id=CAST(:t AS uuid) AND s.id=CAST(:s AS uuid) AND s.active""",{'t':valid_id(teacher_id),'s':valid_id(subject_id)})


def update_teacher_profile(actor,arg):
    price=decimal_or_none(arg['price'])
    business_condition(price is not None and price>0,'BAD_USER_INPUT','Price must be positive')
    currency=arg['currency'].strip().upper()
    business_condition(len(currency)==3 and currency.isalpha(),'BAD_USER_INPUT','Currency must contain three letters')
    ids=[valid_id(i) for i in arg['subjectIds']]
    business_condition(bool(ids) and len(set(ids))==len(ids),'BAD_USER_INPUT','Select nonduplicated subjects')
    business_condition(bool(arg['displayName'].strip()) and bool(arg['bio'].strip()),'BAD_USER_INPUT','Display name and biography are required')
    payload={**arg,'price':str(price),'currency':currency}
    with engine('t').begin() as conn:
        cached=check_receipt(conn,arg['operationId'],actor['id'],'updateTeacherProfile',payload)
        if cached:return cached
        existing=fetch(conn,'SELECT id FROM teachers WHERE id=CAST(:id AS uuid) FOR UPDATE',id=actor['id'])
        for sid in ids:
            business_condition(fetch(conn,'SELECT id FROM subjects WHERE id=CAST(:id AS uuid) AND active',id=sid) is not None,'BAD_USER_INPUT','Subject is absent or inactive')
        if existing:
            execute(conn,"""UPDATE teachers SET display_name=:name,bio=:bio,price=:price,currency=:currency,updated_at=now() WHERE id=CAST(:id AS uuid)""",id=actor['id'],name=arg['displayName'],bio=arg['bio'],price=price,currency=currency)
            execute(conn,'DELETE FROM teacher_subjects WHERE teacher_id=CAST(:id AS uuid)',id=actor['id'])
        else:
            execute(conn,"""INSERT INTO teachers(id,display_name,bio,price,currency,updated_at)
              VALUES(CAST(:id AS uuid),:name,:bio,:price,:currency,now())""",id=actor['id'],name=arg['displayName'],bio=arg['bio'],price=price,currency=currency)
            execute(conn,"""INSERT INTO teacher_metrics(teacher_id,average,review_count,rating_version,completed_count,popularity_version,updated_at)
              VALUES(CAST(:id AS uuid),NULL,0,0,0,0,now())""",id=actor['id'])
        for sid in ids:
            execute(conn,'INSERT INTO teacher_subjects(teacher_id,subject_id) VALUES(CAST(:t AS uuid),CAST(:s AS uuid))',t=actor['id'],s=sid)
        result={'id':actor['id'],'displayName':arg['displayName'],'bio':arg['bio'],'price':{'amount':str(price),'currency':currency}}
        return save_receipt(conn,arg['operationId'],actor['id'],'updateTeacherProfile',payload,result)


def manage_subject(actor,arg):
    with engine('t').begin() as conn:
        cached=check_receipt(conn,arg['operationId'],actor['id'],'manageSubject',arg)
        if cached:return cached
        name=arg['name'].strip()
        business_condition(name and len(name)<=120,'BAD_USER_INPUT','Subject name is required')
        if arg['action']=='CREATE':
            business_condition(arg.get('id') is None,'BAD_USER_INPUT','Do not provide id for CREATE')
            sid=new_id()
            business_condition(fetch(conn,'SELECT id FROM subjects WHERE lower(name)=lower(:name)',name=name) is None,'CONFLICT','Subject with that name already exists')
            execute(conn,'INSERT INTO subjects(id,name,description,active) VALUES(CAST(:id AS uuid),:name,:description,:active)',id=sid,name=name,description=arg['description'],active=arg['active'])
        else:
            business_condition(arg.get('id') is not None,'BAD_USER_INPUT','Subject id required for UPDATE')
            sid=valid_id(arg['id'])
            business_condition(fetch(conn,'SELECT id FROM subjects WHERE id=CAST(:id AS uuid) FOR UPDATE',id=sid) is not None,'NOT_FOUND','Subject not found')
            execute(conn,'UPDATE subjects SET name=:name,description=:description,active=:active WHERE id=CAST(:id AS uuid)',id=sid,name=name,description=arg['description'],active=arg['active'])
        result={'id':sid,'name':name,'description':arg['description'],'active':arg['active']}
        return save_receipt(conn,arg['operationId'],actor['id'],'manageSubject',arg,result)


def update_rating_projection(teacher_id, avg, count, version, updated):
    with engine('t').begin() as conn:
        execute(conn,"""INSERT INTO teacher_metrics(teacher_id,average,review_count,rating_version,completed_count,popularity_version,last_review_at,updated_at)
         VALUES(CAST(:t AS uuid),:avg,:count,:v,0,0,:at,now())
         ON CONFLICT(teacher_id) DO UPDATE SET average=excluded.average,review_count=excluded.review_count,
           rating_version=excluded.rating_version,last_review_at=excluded.last_review_at,updated_at=now()
           WHERE teacher_metrics.rating_version<excluded.rating_version""",t=teacher_id,avg=avg,count=count,v=version,at=updated)


def update_popularity_projection(teacher_id,count,version):
    with engine('t').begin() as conn:
        execute(conn,"""UPDATE teacher_metrics SET completed_count=:n,popularity_version=:v,updated_at=now()
          WHERE teacher_id=CAST(:t AS uuid) AND popularity_version<:v""",t=teacher_id,n=count,v=version)
