"""Gateway-only client: forwards auth requests to the independent Auth Service.

No password verification, JWT secret, session database or Redis client lives in Gateway.
"""
import os
import httpx
from app.resilience.telemetry import trace_id
from app.core.errors import fail
from app.transport.rpc_codec import from_wire

URL = 'http://auth:8200/internal/'


def _call(name, payload, *, allow_denied=False):
    secret = os.getenv('AUTH_INTERNAL_KEY')
    if not secret:
        fail('CONFIGURATION_ERROR', 'Auth client secret is missing')
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False) as client:
            response = client.post(URL + name, json=payload,
                                   headers={'X-Auth-Internal-Key': secret,'X-Correlation-ID': trace_id()})
    except httpx.TimeoutException:
        fail('SERVICE_TIMEOUT', 'Authentication service timed out')
    except httpx.RequestError:
        fail('SERVICE_UNAVAILABLE', 'Authentication service is unreachable')
    if allow_denied and response.status_code == 401:
        return None
    if response.status_code >= 500:
        fail('SERVICE_UNAVAILABLE', 'Authentication service is unavailable')
    if response.status_code == 401:
        fail('UNAUTHENTICATED', 'Invalid credentials or session')
    if response.status_code == 429:
        fail('RATE_LIMITED', 'Too many login attempts')
    if response.status_code >= 400:
        try:
            details=response.json().get('detail') or {}
            if isinstance(details, dict):
                fail(details.get('code','BAD_USER_INPUT'), details.get('message','Operation rejected'))
        except ValueError:
            pass
        fail('BAD_USER_INPUT', 'Authentication command rejected')
    try:
        return response.json()
    except ValueError:
        fail('SERVICE_UNAVAILABLE', 'Malformed authentication service reply')


def register(arg):
    return from_wire(_call('register', {'data': arg})['result'])


def login(arg):
    return from_wire(_call('login', {'data': arg})['result'])


def validate(token):
    if not token:
        return None
    data = _call('validate', {'token': token}, allow_denied=True)
    return data['actor'] if data else None


def logout(token):
    return _call('logout', {'token': token})['ok']


def revoke_user(user_id):
    return _call('revoke-user', {'userId': user_id})['ok']
