"""Independent-process deployment and mock transport regression checks.
Run with `docker compose run --rm tests` after the eight application containers start.
"""
import os
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.demo_auth import demo_token
from app.transport.grpc_ports import ports
from app.transport.rpc_registry import RPC_METHODS, SERVICE_NAMES
from app.transport.rpc_codec import to_wire, from_wire
from datetime import datetime, timezone
from decimal import Decimal


def test_wire_codec_preserves_time_and_money():
    item = {'time': datetime(2026, 1, 1, 12, tzinfo=timezone.utc), 'price': Decimal('55.20'), 'list': [True, None]}
    assert from_wire(to_wire(item)) == item


def test_seven_separate_service_applications_and_db_ownership():
    with httpx.Client(trust_env=False, timeout=4) as client:
        for owner, name in SERVICE_NAMES.items():
            health = client.get(f'http://{name}:8100/health')
            assert health.status_code == 200, (name, health.text)
            assert health.json()['owner'] == owner
            ready = client.get(f'http://{name}:8100/ready')
            assert ready.status_code == 200, (name, ready.text)
            assert ready.json()['database'] == 'tutor_' + owner


def test_internal_services_reject_untrusted_or_foreign_calls():
    import grpc
    from contracts import integration_pb2, integration_pb2_grpc
    from app.transport.grpc_ports import channel_for
    stub = integration_pb2_grpc.InternalOperationsStub(channel_for('l'))
    with pytest.raises(grpc.RpcError) as denied:
        stub.Check(integration_pb2.HealthRequest(), timeout=4)
    assert denied.value.code() == grpc.StatusCode.UNAUTHENTICATED
    stub_a=integration_pb2_grpc.InternalOperationsStub(channel_for('a'))
    payload=integration_pb2.InvokeRequest(args_json=b'[]',kwargs_json=b'{}')
    with pytest.raises(grpc.RpcError) as forbidden:
        stub_a.GetSlot(payload,metadata=(('x-rpc-secret',os.environ['RPC_SHARED_KEY']),),timeout=4)
    assert forbidden.value.code() == grpc.StatusCode.NOT_FOUND


def test_gateway_is_only_public_graphql_and_real_grpc_keeps_interface():
    main = (Path(__file__).parents[1] / 'app' / 'main.py').read_text('utf-8')
    adapter = (Path(__file__).parents[1] / 'app' / 'transport' / 'grpc_ports.py').read_text('utf-8')
    gateway_dockerfile = (Path(__file__).parents[1] / 'Dockerfile.gateway').read_text('utf-8')
    assert 'COPY app/services/' not in gateway_dockerfile
    assert 'COPY app/core/db.py' not in gateway_dockerfile
    assert 'from app.core.db import' not in main + adapter
    assert not (Path(__file__).parents[1] / 'app/transport/mock_ports.py').exists()
    for method in ('ValidateSession','SearchTeachers','ListAvailableSlots','RegisterPaymentLocal'):
        assert callable(getattr(ports,method)) and method in RPC_METHODS
    with TestClient(app) as client:
        ready=client.get('/ready')
        assert ready.status_code==200,ready.text
        assert len(ready.json()['services'])==7


def test_grpc_transport_reports_upstream_outage_as_business_error(monkeypatch):
    import grpc
    from app.transport import grpc_ports
    class Unavailable(grpc.RpcError):
        def code(self):return grpc.StatusCode.UNAVAILABLE
    def broken(*args,**kwargs):raise Unavailable()
    class DeadStub:
        def __init__(self, channel):pass
        def GetMe(self, *args, **kwargs):raise Unavailable()
    monkeypatch.setattr(grpc_ports.integration_pb2_grpc,'InternalOperationsStub',DeadStub)
    from graphql import GraphQLError
    with pytest.raises(GraphQLError) as error:
        ports.GetMe('00000000-0000-4000-8000-000000000001')
    assert error.value.extensions['code']=='SERVICE_UNAVAILABLE'


def test_query_filter_sort_and_aggregate_remain_available():
    with TestClient(app) as client:
        headers = {'Authorization': 'Bearer ' + demo_token('demo-student-token')}
        response = client.post('/graphql/', json={'query': '''query {
          teachers(filter:{sort:PRICE_ASC,minPrice:"0"},page:{limit:100,offset:0}){
            items{id price{amount currency}}
          }
        }'''}, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert 'errors' not in data, data
        prices = [Decimal(item['price']['amount']) for item in data['data']['teachers']['items']]
        assert prices == sorted(prices)
        assert prices
        admin = client.post('/graphql/', headers={'Authorization': 'Bearer ' + demo_token('demo-admin-token')},
                            json={'query': '''query { platformAnalytics(input:{
                              from:"2020-01-01T00:00:00Z",
                              to:"2035-01-01T00:00:00Z",
                              page:{limit:10,offset:0}
                            }) { lessonsCompleted successfulPayments } }'''})
        assert admin.status_code == 200, admin.text
        assert 'errors' not in admin.json(), admin.json()
