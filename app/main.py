"""Public GraphQL Gateway; zero direct SQL or service implementation imports."""
import httpx
from fastapi import FastAPI, HTTPException
from ariadne.asgi import GraphQL
from app.gateway.schema import schema
from app.transport.mock_ports import ports
from app.transport.rpc_registry import SERVICE_NAMES

app = FastAPI(title='Tutoring Platform - Lab 4 / Variant 27', version='4.1')


async def context_value(request, data=None):
    auth = request.headers.get('authorization', '')
    token = auth[7:].strip() if auth.lower().startswith('bearer ') else ''
    return {'actor': ports.ValidateSession(token) if token else None}


@app.get('/health')
def health():
    return {'status': 'ok', 'laboratory': 4, 'variant': 27}


@app.get('/ready')
def ready():
    """Check seven independently deployed services, not their SQL engines."""
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
    if any(status != 'ok' for status in services.values()):
        raise HTTPException(status_code=503, detail={'services': services, 'databases': databases})
    return {'status': 'ready', 'services': services, 'databases': databases}


app.mount('/graphql', GraphQL(schema, debug=False, context_value=context_value))
