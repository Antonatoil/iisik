"""Lab 5: independently deployed Authentication Service.

JWT minting/verification and Redis session lifecycle ONLY happen here.
Accounts remains the sole owner of DB-A; Auth obtains credentials/identity
through the existing protected Mock RPC boundary rather than opening DB-A.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import jwt
import redis
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.transport.rpc_codec import from_wire, to_wire

logger = logging.getLogger(__name__)
ISSUER = 'tutoring-v27-auth'
AUDIENCE = 'tutoring-v27-graphql'
TTL = 3600
MAX_TOKEN_LENGTH = 8192

for key in ('JWT_SECRET', 'AUTH_INTERNAL_KEY', 'RPC_SHARED_KEY', 'REDIS_URL', 'AUTH_REPOSITORY_KEY'):
    if not os.environ.get(key):
        raise RuntimeError(key + ' environment variable is required')
if len(os.environ['JWT_SECRET']) < 48:
    raise RuntimeError('JWT_SECRET should contain at least 48 characters')

redis_client = redis.Redis.from_url(os.environ['REDIS_URL'], decode_responses=True,
                                  socket_connect_timeout=2, socket_timeout=3,
                                  health_check_interval=30)
app = FastAPI(title='Auth Service - Lab 5 Variant 27', version='5.0',
              docs_url=None, redoc_url=None, openapi_url=None)


class Envelope(BaseModel):
    data: dict = Field(default_factory=dict)


class TokenEnvelope(BaseModel):
    token: str


class UserEnvelope(BaseModel):
    userId: str


def _internal_guard(request: Request) -> None:
    provided = request.headers.get('X-Auth-Internal-Key', '')
    if not hmac.compare_digest(provided, os.environ['AUTH_INTERNAL_KEY']):
        raise HTTPException(401, 'Unauthorized internal authentication call')


def _account_rpc(method: str, *args):
    url = 'http://accounts:8100/mock/' + method
    try:
        headers = {'X-Mock-Token': os.environ['RPC_SHARED_KEY']}
        if method == 'ReadCredentialForAuth':
            headers['X-Auth-Repository-Key'] = os.environ['AUTH_REPOSITORY_KEY']
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=2.0), trust_env=False) as client:
            response = client.post(url,
                                   json={'args': to_wire(list(args)), 'kwargs': {}},
                                   headers=headers)
        payload = response.json()
        if response.status_code >= 500:
            raise HTTPException(503, 'Account service unavailable')
        if response.status_code == 422 or not payload.get('ok'):
            err = payload.get('error') or {}
            code = err.get('code', 'AUTH_BACKEND_ERROR')
            # Protect credential checks from account enumeration.
            if method == 'ReadCredentialForAuth':
                return None
            raise HTTPException(400 if code == 'BAD_USER_INPUT' else 409,
                                detail={'code': code, 'message': err.get('message', 'Operation rejected')})
        return from_wire(payload['result'])
    except HTTPException:
        raise
    except (httpx.RequestError, httpx.TimeoutException, ValueError, KeyError) as exc:
        logger.warning('Account service unavailable: %s', type(exc).__name__)
        raise HTTPException(503, 'Account service unavailable') from exc


def _verify_password(password: str, stored: str) -> bool:
    if not isinstance(stored, str):
        return False
    if stored.startswith('pbkdf2_sha256$'):
        try:
            _, raw_iters, raw_salt, raw_hash = stored.split('$')
            iters = int(raw_iters)
            if not 100000 <= iters <= 2000000:
                return False
            got = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(raw_salt), iters)
            return hmac.compare_digest(got, bytes.fromhex(raw_hash))
        except (ValueError, TypeError):
            return False
    # Migration compatibility for demonstration users created in Lab 3.
    if len(stored) == 64:
        return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)
    return False


def _rate_limit(email: str):
    # Fixed-window limit against repeated login attempts for a single email.
    key = 'auth:attempts:' + hashlib.sha256(email.encode()).hexdigest()
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, 300)
        if count > 15:
            raise HTTPException(429, 'Too many login attempts; retry later')
    except redis.RedisError as exc:
        raise HTTPException(503, 'Authentication session store unavailable') from exc


def _session_key(jti: str) -> str:
    return 'lab5:session:' + jti


def _user_set_key(user_id: str) -> str:
    return 'lab5:user_sessions:' + user_id


def _issue_token(user: dict) -> dict:
    now = int(time.time())
    jti = str(uuid4())
    exp = now + TTL
    claims = {
        'iss': ISSUER, 'aud': AUDIENCE, 'typ': 'access',
        'sub': user['id'], 'role': user['role'], 'jti': jti,
        'iat': now, 'nbf': now, 'exp': exp,
    }
    access_token = jwt.encode(claims, os.environ['JWT_SECRET'], algorithm='HS256')
    state = {'user_id': user['id'], 'role': user['role'], 'expires_at': exp}
    try:
        pipe = redis_client.pipeline(transaction=True)
        pipe.set(_session_key(jti), json.dumps(state), ex=TTL)
        pipe.sadd(_user_set_key(user['id']), jti)
        pipe.expire(_user_set_key(user['id']), TTL + 120)
        pipe.execute()
    except redis.RedisError as exc:
        raise HTTPException(503, 'Authentication session store unavailable') from exc
    return {'token': access_token, 'expiresAt': datetime.fromtimestamp(exp, tz=timezone.utc).isoformat(), 'user': user}


def _validate_token(token: str) -> tuple[dict, str]:
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise HTTPException(401, 'Invalid JWT')
    try:
        claims = jwt.decode(token, os.environ['JWT_SECRET'], algorithms=['HS256'],
                            audience=AUDIENCE, issuer=ISSUER,
                            options={'require': ['sub', 'jti', 'iss', 'aud', 'exp', 'iat', 'nbf', 'role']})
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(401, 'Invalid or expired JWT') from exc
    if claims.get('typ') != 'access' or not isinstance(claims.get('sub'), str) or not isinstance(claims.get('jti'), str):
        raise HTTPException(401, 'Invalid JWT claims')
    try:
        raw = redis_client.get(_session_key(claims['jti']))
    except redis.RedisError as exc:
        raise HTTPException(503, 'Authentication session store unavailable') from exc
    if raw is None:
        raise HTTPException(401, 'Active Redis session is missing')
    try:
        session = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(401, 'Invalid session record')
    if (session.get('user_id') != claims['sub'] or session.get('role') != claims.get('role')
            or session.get('expires_at', 0) <= time.time()):
        raise HTTPException(401, 'Invalid session state')
    # Re-read the current status/role to revoke blocked accounts immediately.
    user = _account_rpc('GetMe', claims['sub'])
    if not user or user.get('status') != 'ACTIVE' or user.get('role') != claims.get('role'):
        raise HTTPException(401, 'User is blocked, missing, or their role has changed')
    return user, claims['jti']


def _revoke_session(user_id: str, jti: str):
    try:
        pipe = redis_client.pipeline(transaction=True)
        pipe.delete(_session_key(jti))
        pipe.srem(_user_set_key(user_id), jti)
        pipe.execute()
    except redis.RedisError as exc:
        raise HTTPException(503, 'Authentication session store unavailable') from exc


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'auth', 'laboratory': 5}


@app.get('/ready')
def ready():
    try:
        redis_client.ping()
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            resp = client.get('http://accounts:8100/ready')
        if resp.status_code != 200 or resp.json().get('status') != 'ready':
            raise HTTPException(503, 'Accounts service unavailable')
        return {'status': 'ready', 'service': 'auth', 'redis': 'ok', 'accounts': 'ok'}
    except (redis.RedisError, httpx.RequestError, ValueError) as exc:
        raise HTTPException(503, 'Auth dependencies unavailable') from exc


@app.post('/internal/register')
def register(payload: Envelope, request: Request):
    _internal_guard(request)
    # Accounts keeps ownership of DB-A and its registration transaction.
    # This endpoint is the only GraphQL-facing route for registration.
    result = _account_rpc('RegisterUserLocal', payload.data)
    return {'result': to_wire(result)}


@app.post('/internal/login')
def login(payload: Envelope, request: Request):
    _internal_guard(request)
    email = str(payload.data.get('email', '')).strip().lower()
    password = payload.data.get('password')
    if not isinstance(password, str) or len(password) > 256 or not email or len(email) > 254:
        raise HTTPException(401, 'Invalid credentials')
    _rate_limit(email)
    account = _account_rpc('ReadCredentialForAuth', email)
    if not account or account.get('status') != 'ACTIVE' or not _verify_password(password, account.get('password_hash', '')):
        raise HTTPException(401, 'Invalid credentials')
    user = {k: account[k] for k in ('id', 'name', 'role', 'email', 'status')}
    result = _issue_token(user)
    # Authentication is complete regardless of an analytics outage.
    try:
        from app.transport.auth_rpc import internal_rpc
        internal_rpc('x', 'RecordAuthentication', user)
    except Exception:
        logger.warning('Could not deliver optional auth metric')
    return {'result': result}


@app.post('/internal/validate')
def validate(payload: TokenEnvelope, request: Request):
    _internal_guard(request)
    user, _ = _validate_token(payload.token)
    return {'actor': user}


@app.post('/internal/logout')
def logout(payload: TokenEnvelope, request: Request):
    _internal_guard(request)
    user, jti = _validate_token(payload.token)
    _revoke_session(user['id'], jti)
    return {'ok': True}


@app.post('/internal/revoke-user')
def revoke_user(payload: UserEnvelope, request: Request):
    _internal_guard(request)
    uid = payload.userId
    try:
        ids = redis_client.smembers(_user_set_key(uid))
        pipe = redis_client.pipeline(transaction=True)
        for jti in ids:
            pipe.delete(_session_key(jti))
        pipe.delete(_user_set_key(uid))
        pipe.execute()
        return {'ok': True, 'revoked_count': len(ids)}
    except redis.RedisError as exc:
        raise HTTPException(503, 'Authentication session store unavailable') from exc
