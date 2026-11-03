"""Separate FastAPI entry point for ONE internal service per process/container."""
import os
import hmac
import logging
from importlib import import_module
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from graphql import GraphQLError
from app.transport.rpc_registry import RPC_METHODS, SERVICE_NAMES
from app.transport.rpc_codec import to_wire, from_wire
from app.core.db import engine

logger = logging.getLogger(__name__)
owner = os.getenv('SERVICE_OWNER', '')
if owner not in SERVICE_NAMES:
    raise RuntimeError('Set SERVICE_OWNER to one of: ' + ','.join(SERVICE_NAMES))
if not os.getenv('RPC_SHARED_KEY'):
    raise RuntimeError('RPC_SHARED_KEY is required for internal service')

app = FastAPI(title='Tutoring mock service: ' + SERVICE_NAMES[owner], docs_url=None, redoc_url=None)

# Explicit allowlist; no arbitrary module name or function may come from an HTTP request.
handlers = {}
for rpc_method, (rpc_owner, target) in RPC_METHODS.items():
    if rpc_owner != owner:
        continue
    module_name, func_name = target.rsplit('.', 1)
    module = import_module('app.services.' + module_name)
    handlers[rpc_method] = getattr(module, func_name)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': SERVICE_NAMES[owner], 'owner': owner}


@app.get('/ready')
def ready():
    try:
        with engine(owner).connect() as conn:
            conn.execute(text('SELECT 1'))
        return {'status': 'ready', 'service': SERVICE_NAMES[owner], 'database': 'tutor_' + owner}
    except Exception:
        raise HTTPException(status_code=503, detail='Service database unavailable')


@app.post('/mock/{method}')
async def mock_call(method: str, request: Request):
    expected = os.environ['RPC_SHARED_KEY']
    provided = request.headers.get('X-Mock-Token', '')
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail='Unauthorized internal call')
    if method not in handlers:
        raise HTTPException(status_code=404, detail='Unknown service method')
    try:
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get('args'), list) or not isinstance(payload.get('kwargs'), dict):
            raise ValueError('args must be array and kwargs object')
        args = from_wire(payload['args'])
        kwargs = from_wire(payload['kwargs'])
    except (ValueError, TypeError, KeyError):
        return JSONResponse(status_code=400, content={'ok': False, 'error': {'code': 'BAD_USER_INPUT', 'message': 'Malformed RPC payload'}})
    try:
        from starlette.concurrency import run_in_threadpool
        result = await run_in_threadpool(handlers[method], *args, **kwargs)
        return {'ok': True, 'result': to_wire(result)}
    except GraphQLError as exc:
        code = (exc.extensions or {}).get('code', 'BUSINESS_ERROR')
        return JSONResponse(status_code=422, content={'ok': False, 'error': {'code': code, 'message': exc.message}})
    except Exception:
        logger.exception('Unhandled mock RPC %s in %s', method, SERVICE_NAMES[owner])
        return JSONResponse(status_code=500, content={'ok': False, 'error': {'code': 'INTERNAL_ERROR', 'message': 'Internal service error'}})
