"""Real write-side tests against the seeded Docker PostgreSQL databases.
All identities and operation IDs are fresh, so repeated runs do not conflict.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from tests.demo_auth import demo_token
from app.core.db import engine
from sqlalchemy import text

ADMIN='demo-admin-token'
PAGE='{limit:50,offset:0}'

def gql(client, query, token=None, variables=None):
    h={'Authorization':'Bearer '+demo_token(token)} if token else {}
    response=client.post('/graphql/',json={'query':query,'variables':variables or {}},headers=h)
    assert response.status_code==200,response.text
    return response.json()

def op():return str(uuid4())

def require_ok(value):
    assert 'errors' not in value,value
    return value['data']

def test_lab4_mutation_flow():
    with TestClient(app) as client:
        teacher_email=f'teacher{uuid4().hex[:12]}@example.test'
        student_email=f'student{uuid4().hex[:12]}@example.test'
        teacher_id=require_ok(gql(client,'''mutation($a:RegisterInput!){register(input:$a){id role}}''',variables={
          'a':{'operationId':op(),'email':teacher_email,'password':'TeacherPass_123','name':'Преподаватель теста','role':'TEACHER'}}))['register']['id']
        student_op=op()
        student_data={'operationId':student_op,'email':student_email,'password':'StudentPass_123','name':'Тестовый ученик','role':'STUDENT','learningGoal':'Учиться'}
        reg=require_ok(gql(client,'''mutation($a:RegisterInput!){register(input:$a){id role}}''',variables={'a':student_data}))['register']
        assert reg['role']=='STUDENT' and reg['id']
        repeated=require_ok(gql(client,'''mutation($a:RegisterInput!){register(input:$a){id role}}''',variables={'a':student_data}))['register']
        assert repeated['id']==reg['id']
        conflict={**student_data,'email':'different'+student_email}
        err=gql(client,'''mutation($a:RegisterInput!){register(input:$a){id}}''',variables={'a':conflict})
        assert err['errors'][0]['extensions']['code']=='IDEMPOTENCY_CONFLICT'
        ttoken=require_ok(gql(client,'mutation($a:LoginInput!){login(input:$a){token user{role}}}',variables={'a':{'email':teacher_email,'password':'TeacherPass_123'}}))['login']['token']
        stoken=require_ok(gql(client,'mutation($a:LoginInput!){login(input:$a){token}}',variables={'a':{'email':student_email,'password':'StudentPass_123'}}))['login']['token']
        # Administrator creates a subject; the teacher updates a profile with it.
        sub=require_ok(gql(client,'''mutation($a:SubjectInput!){manageSubject(input:$a){id active}}''',ADMIN,
          {'a':{'operationId':op(),'action':'CREATE','name':'Предмет '+uuid4().hex[:12], 'description':'Тест','active':True}}))['manageSubject']['id']
        profile=require_ok(gql(client,'''mutation($a:TeacherProfileInput!){updateTeacherProfile(input:$a){id subjects{name} price{amount}}}''',ttoken,
          {'a':{'operationId':op(),'displayName':'Тестовый преподаватель','bio':'Работа с математикой','price':'55','currency':'BYN','subjectIds':[sub]}}))['updateTeacherProfile']
        assert profile['id']==teacher_id
        # The teacher creates future slots, student books, pays, then moves to another slot.
        start=datetime.now(timezone.utc)+timedelta(days=3)
        def utc(d):return d.isoformat()
        available=require_ok(gql(client,'''mutation($a:AvailabilityInput!){setAvailability(input:$a){slots{id status version}}}''',ttoken,
          {'a':{'operationId':op(),'subjectId':sub,'upsert':[
             {'startsAt':utc(start),'endsAt':utc(start+timedelta(hours=1))},
             {'startsAt':utc(start+timedelta(days=1)),'endsAt':utc(start+timedelta(days=1,hours=1))},
             {'startsAt':utc(start+timedelta(days=2)),'endsAt':utc(start+timedelta(days=2,hours=1))}], 'removeIds':[]}}))['setAvailability']['slots']
        assert len(available)==3
        booking_data={'operationId':op(),'teacherId':teacher_id,'subjectId':sub,'slotId':available[0]['id'],'topic':'Новая тема'}
        booking=require_ok(gql(client,'''mutation($a:BookLessonInput!){bookLesson(input:$a){id paymentState price{amount} lesson{id version slot{id}}}}''',stoken,{'a':booking_data}))['bookLesson']
        assert booking['paymentState']=='UNPAID'
        replay=require_ok(gql(client,'''mutation($a:BookLessonInput!){bookLesson(input:$a){id}}''',stoken,{'a':booking_data}))['bookLesson']
        assert replay['id']==booking['id']
        duplicate=gql(client,'''mutation($a:BookLessonInput!){bookLesson(input:$a){id}}''',stoken,{'a':{**booking_data,'operationId':op()}})
        assert duplicate['errors'][0]['extensions']['code']=='SLOT_UNAVAILABLE'
        payment_key=op()
        payment=require_ok(gql(client,'''mutation($a:PaymentInput!){registerPayment(input:$a){status money{amount}}}''',stoken,
          {'a':{'operationId':payment_key,'bookingId':booking['id']}}))['registerPayment']
        assert payment['status']=='COMPLETED'
        payment_replay=require_ok(gql(client,'''mutation($a:PaymentInput!){registerPayment(input:$a){status}}''',stoken,
          {'a':{'operationId':payment_key,'bookingId':booking['id']}}))['registerPayment']
        assert payment_replay['status']=='COMPLETED'
        new_booking=require_ok(gql(client,'''mutation($a:RescheduleInput!){rescheduleLesson(input:$a){id price{amount} lesson{id version slot{id}}}}''',stoken,
          {'a':{'operationId':op(),'lessonId':booking['lesson']['id'],'newSlotId':available[1]['id'],'expectedVersion':1}}))['rescheduleLesson']
        assert new_booking['id']==booking['id'] and new_booking['price']==booking['price']
        denied=gql(client,'''mutation($a:LessonCommandInput!){cancelLesson(input:$a){id}}''',stoken,
          {'a':{'operationId':op(),'lessonId':booking['lesson']['id'],'expectedVersion':1}})
        assert denied['errors'][0]['extensions']['code']=='VERSION_CONFLICT'
        cancelled=require_ok(gql(client,'''mutation($a:LessonCommandInput!){cancelLesson(input:$a){status paymentState}}''',stoken,
          {'a':{'operationId':op(),'lessonId':booking['lesson']['id'],'expectedVersion':2}}))['cancelLesson']
        assert cancelled['status']=='CANCELLED' and cancelled['paymentState']=='PAID'
        # A second lesson exercises transition PLANNED -> IN_PROGRESS -> COMPLETED.
        second=require_ok(gql(client,'''mutation($a:BookLessonInput!){bookLesson(input:$a){id lesson{id}}}''',stoken,
          {'a':{'operationId':op(),'teacherId':teacher_id,'subjectId':sub,'slotId':available[2]['id'],'topic':'Вторая тема'}}))['bookLesson']
        require_ok(gql(client,'''mutation($a:PaymentInput!){registerPayment(input:$a){status}}''',stoken,
          {'a':{'operationId':op(),'bookingId':second['id']}}))
        # Isolated test fixture: shift this newly created future slot into today's active interval.
        # Production application never overrides schedule in this manner.
        with engine('l').begin() as conn:
            conn.execute(text("UPDATE slots SET starts_at=now()-interval '5 minutes', ends_at=now()+interval '55 minutes' WHERE id=CAST(:id AS uuid)"),{'id':available[2]['id']})
        start_result=require_ok(gql(client,'''mutation($a:LessonCommandInput!){startLesson(input:$a){status version}}''',ttoken,
          {'a':{'operationId':op(),'lessonId':second['lesson']['id'],'expectedVersion':1}}))['startLesson']
        assert start_result['status']=='IN_PROGRESS' and start_result['version']==2
        complete_operation=op()
        completed=require_ok(gql(client,'''mutation($a:CompleteLessonInput!){completeLesson(input:$a){status goalOutcome version}}''',ttoken,
          {'a':{'operationId':complete_operation,'lessonId':second['lesson']['id'],'expectedVersion':2,'resultText':'Цель достигнута','goalOutcome':'ACHIEVED'}}))['completeLesson']
        assert completed['status']=='COMPLETED'
        # Replaying the same completion must NOT bump the popularity projection version.
        with engine('x').connect() as conn:
            p_before=conn.execute(text('SELECT version FROM teacher_popularity WHERE teacher_id=CAST(:id AS uuid)'), {'id':teacher_id}).scalar_one()
        same=require_ok(gql(client,'''mutation($a:CompleteLessonInput!){completeLesson(input:$a){status version}}''',ttoken,
          {'a':{'operationId':complete_operation,'lessonId':second['lesson']['id'],'expectedVersion':2,
                'resultText':'Цель достигнута','goalOutcome':'ACHIEVED'}}))['completeLesson']
        assert same['status']=='COMPLETED'
        with engine('x').connect() as conn:
            p_after=conn.execute(text('SELECT version FROM teacher_popularity WHERE teacher_id=CAST(:id AS uuid)'), {'id':teacher_id}).scalar_one()
        assert p_after == p_before
        review=require_ok(gql(client,'''mutation($a:ReviewInput!){addReview(input:$a){id score}}''',stoken,
          {'a':{'operationId':op(),'bookingId':second['id'],'score':5,'text':'Всё понятно'}}))['addReview']
        assert review['score']==5
        n=require_ok(gql(client,'''{notifications(page:{limit:30,offset:0}){items{id readAt}}}''',stoken))['notifications']['items']
        unread=next(x for x in n if x['readAt'] is None)
        nr=require_ok(gql(client,'''mutation($a:ReadNotificationInput!){markNotificationRead(input:$a){id readAt}}''',stoken,
          {'a':{'operationId':op(),'notificationId':unread['id']}}))['markNotificationRead']
        assert nr['readAt']
        analytics=require_ok(gql(client,'''query($a:AnalyticsInput!){platformAnalytics(input:$a){lessonsCompleted successfulPayments revenue{amount}}}''',ADMIN,
          {'a':{'from':'2020-01-01T00:00:00Z','to':'2035-01-01T00:00:00Z','page':{'limit':20,'offset':0}}}))['platformAnalytics']
        assert analytics['lessonsCompleted']>=2 and analytics['successfulPayments']>=3
        require_ok(gql(client,'''mutation($a:UserStatusInput!){setUserStatus(input:$a){status}}''',ADMIN,
          {'a':{'operationId':op(),'userId':reg['id'],'status':'BLOCKED'}}))
        denied=gql(client,'{me{id}}',stoken)
        assert denied['errors'][0]['extensions']['code']=='UNAUTHENTICATED'
