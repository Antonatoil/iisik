"""Lab 6 end-to-end proof: protobuf gRPC, transactional Kafka outbox/inbox,
real business flow and event-driven projections. Requires Docker Compose.
"""
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import grpc
import httpx
from confluent_kafka.admin import AdminClient
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.core.db import engine
from app.events.domain import _VALIDATOR, build
from app.transport.grpc_ports import ports, channel_for
from app.transport.rpc_registry import SERVICE_NAMES
from contracts import integration_pb2, integration_pb2_grpc, tutoring_pb2, tutoring_pb2_grpc
from tests.demo_auth import demo_token


def eventually(fn, timeout=35):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value=fn()
        if value:return value
        time.sleep(.3)
    raise AssertionError('Kafka delivery/DB projection did not converge within 35s')


def graphql(client, query, variables=None, token=None):
    headers={'Authorization':'Bearer '+token} if token else {}
    response=client.post('/graphql/',json={'query':query,'variables':variables or {}},headers=headers)
    assert response.status_code==200,response.text
    body=response.json()
    assert 'errors' not in body,body
    return body['data']


def new_user(client, role):
    email='lab6-'+uuid4().hex[:14]+'@example.test'
    password='Lab6StrongPass_12345!'
    uid=graphql(client,'mutation($a:RegisterInput!){register(input:$a){id}}',{
       'a':{'operationId':str(uuid4()),'email':email,'password':password,
            'name':'Lab 6', 'role':role}})['register']['id']
    token=graphql(client,'mutation($a:LoginInput!){login(input:$a){token}}',{
       'a':{'email':email,'password':password}})['login']['token']
    return uid, token


def lookup(owner,statement,**params):
    with engine(owner).connect() as conn:
        return conn.execute(text(statement),params).mappings().first()


def test_real_protobuf_grpc_runs_in_seven_separate_services():
    for owner,name in SERVICE_NAMES.items():
        stub=integration_pb2_grpc.InternalOperationsStub(channel_for(owner))
        answer=stub.Check(integration_pb2.HealthRequest(),
             metadata=(('x-rpc-secret',os.environ['RPC_SHARED_KEY']),),timeout=5)
        assert answer.service==name and answer.ready
    # The Lab 2 typed interface must be deployed, not just stored as a text file.
    resp=tutoring_pb2_grpc.CatalogStub(channel_for('t')).GetTeachingOffer(
        tutoring_pb2.GetTeachingOfferRequest(
           teacher_id='00000000-0000-4000-8000-000000000201',
           subject_id='00000000-0000-4000-8000-000000000501'),
        metadata=(('x-rpc-secret',os.environ['RPC_SHARED_KEY']),),timeout=5)
    assert resp.teacher_id and Decimal(resp.price.amount)>0


def test_real_kafka_topics_and_private_internal_transport():
    md=AdminClient({'bootstrap.servers':os.environ.get('KAFKA_BOOTSTRAP','kafka:9092')}).list_topics(timeout=5)
    assert 'tutor.events.v1' in md.topics and 'tutor.events.dlq.v1' in md.topics
    assert len(md.topics['tutor.events.v1'].partitions)>=3
    with httpx.Client(trust_env=False,timeout=4) as client:
        for name in SERVICE_NAMES.values():
            # Lab4 HTTP mock endpoints were removed, not left alongside gRPC.
            resp=client.post(f'http://{name}:8100/mock/GetMe',json={})
            assert resp.status_code==404
    assert not (Path(__file__).parents[1]/'app/transport/mock_ports.py').exists()


def test_lab2_event_contract_is_enforced():
    assert _VALIDATOR.is_valid(build('UserAuthenticated','A',
        '00000000-0000-4000-8000-000000000002',1,
        '00000000-0000-4000-8000-000000000002',{
         'user_id':'00000000-0000-4000-8000-000000000002',
         'role':'STUDENT','authenticated_at':datetime.now(timezone.utc).isoformat()}))
    try:
        build('UserAuthenticated','A','00000000-0000-4000-8000-000000000002',1,
              '00000000-0000-4000-8000-000000000002',{'user_id':'not a UUID'})
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid Lab2 Kafka event was accepted')


def test_booking_payment_use_grpc_then_kafka_consumers_and_inbox():
    with TestClient(app) as client:
        teacher,ttoken=new_user(client,'TEACHER')
        student,stoken=new_user(client,'STUDENT')
        subject=graphql(client,'mutation($a:SubjectInput!){manageSubject(input:$a){id}}',{
          'a':{'operationId':str(uuid4()),'action':'CREATE',
               'name':'Kafka gRPC '+uuid4().hex[:10], 'description':'Lab6','active':True}},
          demo_token('demo-admin-token'))['manageSubject']['id']
        graphql(client,'mutation($a:TeacherProfileInput!){updateTeacherProfile(input:$a){id}}',{
           'a':{'operationId':str(uuid4()),'displayName':'Lab6 Teacher',
                'bio':'Distributed teaching', 'price':'42.50','currency':'BYN','subjectIds':[subject]}},ttoken)
        # This directly invokes original typed Catalog.GetTeachingOffer over gRPC.
        offer=ports.GetTeachingOffer(teacher,subject)
        assert offer and offer['currency']=='BYN' and offer['price']==Decimal('42.50')
        start=datetime.now(timezone.utc)+timedelta(days=3)
        slots=graphql(client,'mutation($a:AvailabilityInput!){setAvailability(input:$a){slots{id}}}',{
          'a':{'operationId':str(uuid4()),'subjectId':subject,
               'upsert':[{'startsAt':start.isoformat(),
                          'endsAt':(start+timedelta(hours=1)).isoformat()}], 'removeIds':[]}},ttoken)['setAvailability']['slots']
        operation=str(uuid4())
        booked=graphql(client,'mutation($a:BookLessonInput!){bookLesson(input:$a){id lesson{id}}}',{
          'a':{'operationId':operation,'teacherId':teacher,'subjectId':subject,
               'slotId':slots[0]['id'],'topic':'Live gRPC Kafka lesson'}},stoken)['bookLesson']
        lid=booked['lesson']['id']
        bid=booked['id']
        # Outbox written in exact same local PostgreSQL DB-L transaction.
        event=eventually(lambda:lookup('l',"""SELECT event_id::text, envelope,published_at
             FROM event_outbox WHERE envelope->>'event_type'='LessonBooked'
             AND envelope->'payload'->>'booking_id'=:booking""",booking=bid))
        assert event and event['envelope']['payload']['lesson_id']==lid
        assert _VALIDATOR.is_valid(event['envelope'])
        eventually(lambda: lookup('l',
            'SELECT published_at FROM event_outbox WHERE event_id=CAST(:id AS uuid) AND published_at IS NOT NULL',
            id=event['event_id']))
        fact=eventually(lambda: lookup('x',
            'SELECT version FROM lesson_facts WHERE lesson_id=CAST(:id AS uuid)',id=lid))
        assert fact['version']>=1
        note=eventually(lambda: lookup('n',"""SELECT kind FROM notifications
           WHERE user_id=CAST(:user AS uuid) AND event_id=CAST(:event AS uuid)""",
           user=student,event=event['event_id']))
        assert note['kind']=='LessonBooked'
        with engine('x').connect() as conn:
            count=conn.execute(text('SELECT COUNT(*) FROM event_inbox WHERE event_id=CAST(:id AS uuid)'),
                  {'id':event['event_id']}).scalar_one()
        assert count==1
        # Processing a replay is a no-op, so duplicates are safe.
        from app.events.consumer import process
        assert process('x',event['envelope']) is False
        payment=graphql(client,'mutation($a:PaymentInput!){registerPayment(input:$a){id status}}',{
          'a':{'operationId':str(uuid4()),'bookingId':bid}},stoken)['registerPayment']
        assert payment['status']=='COMPLETED'
        payment_fact=eventually(lambda:lookup('x',
          'SELECT status FROM payment_facts WHERE payment_id=CAST(:id AS uuid)', id=payment['id']))
        assert payment_fact['status']=='COMPLETED'
        eventual_booking=lookup('l','SELECT payment_state FROM bookings WHERE id=CAST(:id AS uuid)',id=bid)
        assert eventual_booking['payment_state']=='PAID'


def test_existing_seven_databases_and_auth_not_regressed():
    with TestClient(app) as client:
        data=client.get('/ready')
        assert data.status_code==200,data.text
        values=data.json()
        assert values['auth']=='ok' and values['redis']=='ok'
        assert values['kafka']=='ok' and values['transport']=='grpc'
        assert set(values['databases'])==set('atlprnx')


def test_no_outbox_schema_changes_or_dangerous_volume_removal():
    root=Path(__file__).resolve().parents[1]
    migration=(root/'db/migrations/006_event_outbox.sql').read_text()
    assert 'IF NOT EXISTS' in migration and 'DROP TABLE' not in migration
    compose=(root/'compose.yaml').read_text()
    assert 'tutor_db_data:/var/lib/postgresql/data' in compose
    assert 'tutor_redis_data:/data' in compose
    assert 'tutor_kafka_data:/tmp/kraft-combined-logs' in compose
