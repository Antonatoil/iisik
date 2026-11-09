"""Service-owned Redis read-through cache for PUBLIC catalogue queries.

Uses Redis DB 1, separate from JWT sessions on DB 0. Business-critical
GetTeachingOffer is deliberately uncached (booking sees current DB state).
Versioned keys ensure invalidation does not race with in-flight cache loads.
Redis failures are fail-open for *catalogue reads only*, never Auth sessions.
"""
import hashlib
import json
import logging
import os
from functools import lru_cache
import redis
from app.transport.rpc_codec import to_wire, from_wire
from app.resilience.telemetry import emit

LOG = logging.getLogger(__name__)
METHODS = frozenset({'SearchTeachers','GetTeacher','ListSubjects',
                     'GetTeacherSubjects','GetTeacherMetrics'})
PREFIX = 'lab7:catalog:v1'
GENERATION = PREFIX + ':generation'
TTL = 45


@lru_cache(maxsize=1)
def client():
    url = os.environ.get('CATALOG_CACHE_URL', '')
    if not url:
        return None
    return redis.Redis.from_url(url,decode_responses=True,
                                socket_connect_timeout=.35,socket_timeout=.5)


def _key(method, args, kwargs, generation):
    payload=json.dumps(to_wire([method,args,kwargs]),ensure_ascii=False,
                       sort_keys=True,separators=(',', ':'))
    return f'{PREFIX}:{generation}:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()


def read_through(method, args, kwargs, load):
    if method not in METHODS:
        return load()
    r=client()
    if r is None:
        return load()
    key=None
    try:
        generation=r.get(GENERATION) or '0'
        key=_key(method,args,kwargs,generation)
        cached=r.get(key)
        if cached is not None:
            value=from_wire(json.loads(cached))
            emit('catalog_cache',service='catalog',method=method,result='hit')
            return value
    except (redis.RedisError,ValueError,TypeError,KeyError) as exc:
        emit('catalog_cache',level='warning',service='catalog',method=method,
             result='unavailable',error_type=type(exc).__name__)
        key=None
    result=load()
    if key is not None:
        try:
            r.setex(key,TTL,json.dumps(to_wire(result),ensure_ascii=False,
                                        sort_keys=True,separators=(',', ':')))
        except (redis.RedisError,ValueError,TypeError) as exc:
            emit('catalog_cache',level='warning',service='catalog',method=method,
                 result='write_failed',error_type=type(exc).__name__)
    emit('catalog_cache',service='catalog',method=method,result='miss')
    return result


def invalidate(reason):
    r=client()
    if r is None:
        return
    try:
        version=r.incr(GENERATION)
        emit('catalog_cache',service='catalog',result='invalidated',reason=reason,
             generation=version)
    except redis.RedisError as exc:
        # Never roll back a committed catalogue business operation due to cache.
        emit('catalog_cache',level='warning',service='catalog',result='invalidate_failed',
             error_type=type(exc).__name__)
