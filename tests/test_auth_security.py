"""Lab 5: JWT + Redis + RBAC + Auth Service security regression suite."""
import os
import secrets
from uuid import uuid4

import httpx
import jwt
import redis
from fastapi.testclient import TestClient
from app.main import app
from tests.demo_auth import demo_token


def graphql(client, query, token=None, variables=None):
    headers={'Authorization':'Bearer '+token} if token else {}
    response=client.post('/graphql/',json={'query':query,'variables':variables or {}},headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def register_and_login(client, role='STUDENT'):
    email='lab5-'+uuid4().hex[:15]+'@example.test'
    password='StrongSecurityTest_123!'
    data=graphql(client,"mutation($a:RegisterInput!){register(input:$a){id role status}}",variables={
        'a': {'operationId':str(uuid4()),'email':email,'password':password,
              'name':'Lab5 Test User','role':role}})
    assert 'errors' not in data, data
    signed=graphql(client,"mutation($a:LoginInput!){login(input:$a){token user{id role} expiresAt}}",variables={
        'a':{'email':email,'password':password}})
    assert 'errors' not in signed, signed
    return data['data']['register'], signed['data']['login']['token']


def error_code(response):
    assert response.get('errors'), response
    return response['errors'][0].get('extensions',{}).get('code')


def test_auth_service_and_redis_are_independent_and_ready():
    with httpx.Client(trust_env=False, timeout=4.0) as client:
        r=client.get('http://auth:8200/ready')
        assert r.status_code == 200, r.text
        assert r.json()['redis'] == 'ok'
    with TestClient(app) as client:
        r=client.get('/ready')
        assert r.status_code == 200, r.text
        assert r.json()['auth'] == 'ok' and r.json()['redis'] == 'ok'


def test_no_token_legacy_token_tamper_and_role_enforcement():
    with TestClient(app) as client:
        assert error_code(graphql(client,'{me{id}}')) == 'UNAUTHENTICATED'
        assert error_code(graphql(client,'{me{id}}','demo-student-token')) == 'UNAUTHENTICATED'
        user, token=register_and_login(client)
        parts=token.split('.')
        assert len(parts)==3
        unverified=jwt.decode(token,options={'verify_signature':False})
        assert unverified['sub']==user['id'] and unverified['jti']
        assert 'exp' in unverified and 'iss' in unverified and unverified['role']=='STUDENT'
        damaged=token[:-2]+('aa' if token[-2:]!='aa' else 'bb')
        assert error_code(graphql(client,'{me{id}}',damaged)) == 'UNAUTHENTICATED'
        assert graphql(client,'{me{id role}}',token)['data']['me']['id']==user['id']
        assert error_code(graphql(client,'{users(page:{limit:5,offset:0}){items{id}}}',token))=='FORBIDDEN'
        # Untrusted actor data in GraphQL inputs cannot grant the ADMIN role.
        assert error_code(graphql(client,"mutation($a:UserStatusInput!){setUserStatus(input:$a){status}}",token,{
          'a':{'operationId':str(uuid4()),'userId':user['id'],'status':'BLOCKED'}}))=='FORBIDDEN'


def test_valid_jwt_without_redis_session_is_denied_and_logout_revokes():
    rc=redis.Redis.from_url(os.environ['REDIS_URL'],decode_responses=True)
    with TestClient(app) as client:
        _,token=register_and_login(client)
        claims=jwt.decode(token,options={'verify_signature':False})
        key='lab5:session:'+claims['jti']
        assert rc.ttl(key)>0
        rc.delete(key)
        assert error_code(graphql(client,'{me{id}}',token)) == 'UNAUTHENTICATED'
        _, token2=register_and_login(client)
        assert graphql(client,'mutation{logout}',token2)['data']['logout'] is True
        assert error_code(graphql(client,'{me{id}}',token2)) == 'UNAUTHENTICATED'
        assert error_code(graphql(client,'mutation{logout}',token2)) == 'UNAUTHENTICATED'


def test_admin_block_revokes_jwt_and_sends_role_from_database():
    with TestClient(app) as client:
        user,token=register_and_login(client)
        admin=demo_token('demo-admin-token')
        assert graphql(client,'{me{role}}',admin)['data']['me']['role']=='ADMIN'
        blocked=graphql(client,"mutation($a:UserStatusInput!){setUserStatus(input:$a){status}}",admin,{
          'a':{'operationId':str(uuid4()),'userId':user['id'],'status':'BLOCKED'}})
        assert 'errors' not in blocked, blocked
        assert blocked['data']['setUserStatus']['status']=='BLOCKED'
        assert error_code(graphql(client,'{me{id}}',token))=='UNAUTHENTICATED'


def test_wrong_password_rejected_and_internal_auth_requires_shared_key():
    with TestClient(app) as client:
        reg,_=register_and_login(client)
        wrong=graphql(client,"mutation($a:LoginInput!){login(input:$a){token}}",variables={
          'a':{'email':'nonexistent-'+uuid4().hex+'@example.test','password':'WrongPassword123!'}})
        assert error_code(wrong)=='UNAUTHENTICATED'
    with httpx.Client(trust_env=False, timeout=4) as client:
        r=client.post('http://auth:8200/internal/validate',json={'token':'bad'})
        assert r.status_code==401


def test_credentials_rpc_not_available_to_other_service_tokens():
    import grpc
    from contracts import integration_pb2, integration_pb2_grpc
    from app.transport.grpc_ports import channel_for
    stub=integration_pb2_grpc.InternalOperationsStub(channel_for('a'))
    request=integration_pb2.InvokeRequest(args_json=b'["admin@example.test"]',kwargs_json=b'{}')
    with __import__('pytest').raises(grpc.RpcError) as err:
        stub.ReadCredentialForAuth(request,metadata=(('x-rpc-secret',os.environ['RPC_SHARED_KEY']),),timeout=5)
    assert err.value.code()==grpc.StatusCode.PERMISSION_DENIED
