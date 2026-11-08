"""Health/readiness HTTP only. Actual inter-service operations run on gRPC :50051.
No business endpoints are exposed over HTTP; all internal operations use gRPC.
"""
import os
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from app.core.db import engine
import grpc
from contracts import integration_pb2, integration_pb2_grpc
from app.transport.rpc_registry import SERVICE_NAMES

owner = os.environ.get('SERVICE_OWNER', '')
if owner not in SERVICE_NAMES:
    raise RuntimeError('SERVICE_OWNER must be one of the seven owners')
app = FastAPI(title='Tutoring ' + SERVICE_NAMES[owner] + ' service', docs_url=None,
              redoc_url=None, openapi_url=None)

@app.get('/health')
def health():
    return {'status': 'ok', 'service': SERVICE_NAMES[owner], 'owner': owner, 'transport': 'grpc'}

@app.get('/ready')
def ready():
    try:
        with engine(owner).connect() as conn:
            conn.execute(text('SELECT 1'))
        # A healthy SQL connection alone cannot prove the gRPC server is live.
        with grpc.insecure_channel('127.0.0.1:50051') as channel:
            answer = integration_pb2_grpc.InternalOperationsStub(channel).Check(
                integration_pb2.HealthRequest(),
                metadata=(('x-rpc-secret', os.environ['RPC_SHARED_KEY']),), timeout=1.5)
            if not answer.ready:
                raise RuntimeError('gRPC server not ready')
        return {'status': 'ready', 'service': SERVICE_NAMES[owner],
                'database': 'tutor_' + owner, 'grpc_port': 50051}
    except Exception:
        raise HTTPException(status_code=503, detail='Service database unavailable')
