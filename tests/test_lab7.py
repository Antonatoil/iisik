"""Lab 7: deterministic failure injection + real GraphQL/Redis cache smoke.

These tests require the normal Lab 6 Docker Compose environment. They do
not stop shared Kafka/Postgres/Redis or delete any user data.
"""
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import grpc
import pytest
import redis
from graphql import GraphQLError

from app.resilience import grpc_policy, catalog_cache, telemetry
from app.transport import workflows


class RpcFailure(grpc.RpcError):
    def __init__(self, code):
        self._code=code
    def code(self):return self._code


def test_read_only_grpc_retries_transient_and_succeeds():
    attempts=[]; pauses=[]
    def call(timeout):
        attempts.append(timeout)
        if len(attempts)<3:raise RpcFailure(grpc.StatusCode.UNAVAILABLE)
        return 'OK'
    assert grpc_policy.call_with_policy(call,service='catalog',method='ListSubjects',
       pause=pauses.append,jitter=lambda low,high:0)=='OK'
    assert len(attempts)==3 and pauses==[pytest.approx(.15),pytest.approx(.3)]
    assert all(0 < t <= 3.5 for t in attempts)


def test_mutations_never_retry_after_timeout():
    attempts=[]
    def call(timeout):
        attempts.append(timeout)
        raise RpcFailure(grpc.StatusCode.DEADLINE_EXCEEDED)
    with pytest.raises(grpc.RpcError):
        grpc_policy.call_with_policy(call,service='learning',method='BookLessonLocal',
                                      pause=lambda _:None)
    assert len(attempts)==1


def test_permanent_grpc_errors_not_retried():
    calls=[]
    def call(timeout):
        calls.append(timeout)
        raise RpcFailure(grpc.StatusCode.PERMISSION_DENIED)
    with pytest.raises(grpc.RpcError):
        grpc_policy.call_with_policy(call,service='catalog',method='ListSubjects')
    assert len(calls)==1


def test_read_retry_has_a_hard_cap():
    calls=[]
    def call(timeout):
        calls.append(timeout)
        raise RpcFailure(grpc.StatusCode.UNAVAILABLE)
    with pytest.raises(grpc.RpcError):
        grpc_policy.call_with_policy(call,service='catalog',method='GetTeacher',
                                      pause=lambda _:None,jitter=lambda low,high:0)
    assert len(calls)==3


class MemoryRedis:
    def __init__(self):
        self.data={}
    def get(self,key):return self.data.get(key)
    def setex(self,key,ttl,val):
        assert ttl==45
        self.data[key]=val
    def incr(self,key):
        self.data[key]=str(int(self.data.get(key,'0'))+1)
        return int(self.data[key])


def test_redis_cache_hit_miss_and_invalidation(monkeypatch):
    store=MemoryRedis()
    monkeypatch.setattr(catalog_cache,'client',lambda:store)
    calls=[]
    def db():
        calls.append(1)
        return {'price':Decimal('12.35'),'time':datetime(2026,1,1,tzinfo=timezone.utc)}
    a=catalog_cache.read_through('ListSubjects',[{'limit':5}],{},db)
    b=catalog_cache.read_through('ListSubjects',[{'limit':5}],{},db)
    assert a==b and len(calls)==1
    catalog_cache.invalidate('ManageSubjectLocal')
    c=catalog_cache.read_through('ListSubjects',[{'limit':5}],{},db)
    assert c==a and len(calls)==2


def test_cache_key_includes_filters_and_does_not_cache_critical_offers(monkeypatch):
    store=MemoryRedis(); monkeypatch.setattr(catalog_cache,'client',lambda:store)
    calls=[]
    def db():
        calls.append(1);return {'ok':len(calls)}
    a=catalog_cache.read_through('SearchTeachers',[{'subjectId':'a'}],{},db)
    b=catalog_cache.read_through('SearchTeachers',[{'subjectId':'b'}],{},db)
    assert a!=b and len(calls)==2
    assert catalog_cache.read_through('GetTeachingOffer',['t','s'],{},db)!=catalog_cache.read_through('GetTeachingOffer',['t','s'],{},db)


def test_catalog_cache_fails_open_when_redis_unavailable(monkeypatch):
    class Down:
        def get(self,key):raise redis.ConnectionError('connection refused')
        def incr(self,key):raise redis.ConnectionError('connection refused')
    monkeypatch.setattr(catalog_cache,'client',lambda:Down())
    assert catalog_cache.read_through('ListSubjects',[],{},lambda:{'items':[]})=={'items':[]}
    catalog_cache.invalidate('Kafka:RatingUpdated') # No business error.


def test_telemetry_emits_correlation_without_sensitive_values(caplog):
    cid,token=telemetry.start_trace('lab7-test-flow')
    try:
        with caplog.at_level(logging.INFO,logger='tutoring.telemetry'):
            telemetry.emit('grpc_client',service='catalog',method='ListSubjects',result='ok')
        payload=json.loads(caplog.records[-1].message)
        assert payload['correlation_id']=='lab7-test-flow'
        assert payload['event']=='grpc_client' and 'token' not in payload
    finally:
        telemetry.end_trace(token)


def test_malformed_trace_ids_not_reflected():
    assert '\n' not in telemetry.clean_id('unsafe\ninjected')
    assert len(telemetry.clean_id('a'*200))==36


def test_dead_letter_ack_required_before_offset_commit(monkeypatch):
    from app.events import consumer
    class Message:
        def topic(self):return 'tutor.events.v1'
        def partition(self):return 2
        def offset(self):return 91
        def value(self):return b'{broken-payload}'
    recorded=[]
    class FakeProducer:
        def produce(self,topic,value,key,on_delivery):
            recorded.append((topic,json.loads(value),key))
            on_delivery(None,None)
        def flush(self,timeout):return 0
    monkeypatch.setattr(consumer,'producer',lambda:FakeProducer())
    consumer.dead_letter(Message(),'x',ValueError('broken'),5,'processing_failed')
    assert recorded[0][0]=='tutor.events.dlq.v1'
    assert recorded[0][1]['owner']=='x' and recorded[0][1]['attempts']==5


def test_failed_dead_letter_does_not_ack(monkeypatch):
    from app.events import consumer
    class Msg:
        def topic(self):return 'x'
        def partition(self):return 0
        def offset(self):return 1
        def value(self):return b'x'
    class Broken:
        def produce(self,*args,**kwargs):pass
        def flush(self,timeout):return 1
    monkeypatch.setattr(consumer,'producer',lambda:Broken())
    with pytest.raises(RuntimeError,match='not acknowledged'):
        consumer.dead_letter(Msg(),'x','db down',5,'processing_failed')


def test_payment_committed_can_complete_via_kafka_when_learning_unavailable(monkeypatch):
    operation=str(uuid4());booking=str(uuid4());student=str(uuid4())
    class Ports:
        def GetBookingSnapshot(self,id):
            return {'student_id':student,'booking_status':'ACTIVE','payment_state':'PENDING',
                    'payment_operation_id':None}
        def RegisterPaymentLocal(self,actor,arg,snapshot):
            return {'id':str(uuid4()),'status':'COMPLETED'}
        def ApplyPaymentToBooking(self,*args):
            raise GraphQLError('Learning down',extensions={'code':'SERVICE_UNAVAILABLE'})
    monkeypatch.setattr(workflows,'_ports',lambda:Ports())
    result=workflows.register_payment({'id':student,'role':'STUDENT'},
                       {'bookingId':booking,'operationId':operation})
    assert result['status']=='COMPLETED'  # DB-P already committed; Kafka will reconcile.


def test_payment_business_error_is_not_silenced(monkeypatch):
    operation=str(uuid4());booking=str(uuid4());student=str(uuid4())
    class Ports:
        def GetBookingSnapshot(self,id):
            return {'student_id':student,'booking_status':'ACTIVE','payment_state':'PENDING',
                    'payment_operation_id':None}
        def RegisterPaymentLocal(self,actor,arg,snapshot):return {'status':'COMPLETED'}
        def ApplyPaymentToBooking(self,*args):
            raise GraphQLError('Invalid booking',extensions={'code':'INVALID_STATE'})
    monkeypatch.setattr(workflows,'_ports',lambda:Ports())
    with pytest.raises(GraphQLError):
        workflows.register_payment({'id':student,'role':'STUDENT'},
                       {'bookingId':booking,'operationId':operation})


def test_redis_cache_is_separate_from_jwt_session_storage():
    text=(Path(__file__).resolve().parents[1]/'compose.yaml').read_text('utf-8')
    assert 'CATALOG_CACHE_URL:' in text
    assert '@redis:6379/1' in text and '@redis:6379/0' in text


def test_actual_graphql_query_populates_catalog_cache():
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.demo_auth import demo_token
    import os
    r=redis.Redis.from_url(os.environ['CATALOG_CACHE_URL'],decode_responses=True)
    with TestClient(app) as client:
        auth={'Authorization':'Bearer '+demo_token('demo-student-token')}
        query={'query':'query { subjects(page:{limit:20,offset:0}) { items { id name } } }'}
        first=client.post('/graphql/',json=query,headers=auth)
        second=client.post('/graphql/',json=query,headers=auth)
        assert first.status_code==second.status_code==200
        assert 'errors' not in first.json() and first.json()==second.json()
        assert first.json()['data']['subjects']['items']
    assert any('lab7:catalog:v1:' in key and 'generation' not in key
               for key in r.scan_iter(match='lab7:catalog:v1:*',count=100))


def test_poison_kafka_event_moves_to_dlq_after_five_attempts(monkeypatch):
    """Inject a DB failure and verify bounded retries + DLQ + offset commit."""
    from app.events import consumer as module
    from app.events.domain import build
    valid_event=build('RatingUpdated','R',str(uuid4()),1,str(uuid4()),{
        'teacher_id':str(uuid4()),'average':'4.0', 'review_count':3,
        'updated_at':datetime.now(timezone.utc).isoformat()})
    class FakeMsg:
        def error(self):return None
        def topic(self):return 'tutor.events.v1'
        def partition(self):return 0
        def offset(self):return 33
        def value(self):return json.dumps(valid_event).encode()
    class Stop:
        ended=False
        def is_set(self):return self.ended
        def wait(self,secs):pass
    stop=Stop()
    class FakeConsumer:
        def __init__(self,*args,**kwargs):self.commits=0;self.seeks=0;self.closed=False
        def subscribe(self,topics):pass
        def poll(self,timeout):return FakeMsg()
        def commit(self,**kwargs):
            self.commits+=1;stop.ended=True
        def seek(self,*args):self.seeks+=1
        def close(self):self.closed=True
    client=FakeConsumer()
    monkeypatch.setattr(module,'Consumer',lambda conf:client)
    attempts=[];dropped=[]
    def broken(owner,evt):
        attempts.append(1);raise RuntimeError('fake DB failure')
    def send_dlq(msg,owner,error,attempts,reason):
        dropped.append((owner,attempts,reason))
    monkeypatch.setattr(module,'process',broken)
    monkeypatch.setattr(module,'dead_letter',send_dlq)
    module.consumer_loop('t',stop)
    assert len(attempts)==5 and client.seeks==4
    assert dropped==[('t',5,'processing_failed')]
    assert client.commits==1 and client.closed
