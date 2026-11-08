"""Auth-service-only call into the existing allowlisted internal Mock RPC transport."""
import os
import httpx
from app.transport.rpc_codec import to_wire, from_wire
from app.transport.rpc_registry import RPC_METHODS, SERVICE_NAMES


def internal_rpc(owner: str, method: str, *args):
    if RPC_METHODS.get(method, (None,))[0] != owner:
        raise RuntimeError('Cross-owner RPC method is not allowed')
    with httpx.Client(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False) as client:
        response = client.post('http://' + SERVICE_NAMES[owner] + ':8100/mock/' + method,
                               json={'args': to_wire(list(args)), 'kwargs': {}},
                               headers={'X-Mock-Token': os.environ['RPC_SHARED_KEY']})
    response.raise_for_status()
    payload = response.json()
    if payload.get('ok') is not True:
        raise RuntimeError('Auth metric / repository call rejected')
    return from_wire(payload['result'])
