"""Public GraphQL Gateway; zero direct SQL or service implementation imports."""
import httpx
import time
from app.resilience.telemetry import start_trace, end_trace, emit, elapsed_ms
from confluent_kafka.admin import AdminClient
from fastapi import FastAPI, HTTPException
from ariadne.asgi import GraphQL
from app.gateway.schema import schema
from app.transport.grpc_ports import ports
from app.transport.rpc_registry import SERVICE_NAMES
from app.transport.auth_client import validate as validate_jwt_session

app = FastAPI(title='Tutoring Platform - Lab 7 / Variant 27', version='7.0')


@app.middleware('http')
async def correlation_middleware(request, call_next):
    trace, token = start_trace(request.headers.get('x-correlation-id'))
    started = time.monotonic()
    try:
        response = await call_next(request)
        response.headers['X-Correlation-ID'] = trace
        emit('http_request',service='gateway',path=request.url.path,
             status=response.status_code,elapsed_ms=elapsed_ms(started))
        return response
    except Exception:
        emit('http_request',level='error',service='gateway',path=request.url.path,
             result='exception',elapsed_ms=elapsed_ms(started))
        raise
    finally:
        end_trace(token)


async def context_value(request, data=None):
    auth = request.headers.get('authorization', '')
    token = auth[7:].strip() if auth.lower().startswith('bearer ') else ''
    # Only Auth Service validates JWT signature + Redis session.
    return {'actor': validate_jwt_session(token) if token else None, 'token': token}


@app.get('/health')
def health():
    return {'status': 'ok', 'laboratory': 7, 'variant': 27}


@app.get('/ready')
def ready():
    """Check all seven independent gRPC-backed service processes."""
    databases, services = {}, {}
    with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.5), trust_env=False) as client:
        for owner, name in SERVICE_NAMES.items():
            try:
                response = client.get(f'http://{name}:8100/ready')
                payload = response.json()
                state = 'ok' if response.status_code == 200 and payload.get('status') == 'ready' and payload.get('database') == 'tutor_' + owner else 'unavailable'
            except (httpx.RequestError, ValueError):
                state = 'unavailable'
            databases[owner] = state
            services[name] = state
    # Auth Service checks Redis and DB-A; Gateway does not access either store.
    try:
        with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.5), trust_env=False) as client:
            reply = client.get('http://auth:8200/ready')
            auth_ready = reply.status_code == 200 and reply.json().get('redis') == 'ok'
    except (httpx.RequestError, ValueError):
        auth_ready = False
    try:
        kafka_md=AdminClient({'bootstrap.servers':'kafka:9092', 'socket.timeout.ms':2500}).list_topics(
            topic='tutor.events.v1',timeout=3)
        kafka_ready = 'tutor.events.v1' in kafka_md.topics and kafka_md.topics['tutor.events.v1'].error is None
    except Exception:
        kafka_ready = False
    if any(status != 'ok' for status in services.values()) or not auth_ready or not kafka_ready:
        raise HTTPException(status_code=503, detail={'services': services, 'databases': databases,
            'auth': 'ok' if auth_ready else 'unavailable',
            'kafka': 'ok' if kafka_ready else 'unavailable'})
    return {'status': 'ready', 'services': services, 'databases': databases,
            'auth': 'ok', 'redis': 'ok', 'kafka': 'ok', 'transport': 'grpc'}


app.mount('/graphql', GraphQL(schema, debug=False, context_value=context_value))
