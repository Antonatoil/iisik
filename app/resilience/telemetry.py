"""Structured event logging without passwords, tokens or request payloads.

X-Correlation-ID follows GraphQL -> internal Auth/gRPC. Domain Kafka events
already carry an operation-based correlation_id from the Lab-2 contract.
"""
import contextvars
import json
import logging
import re
import time
from uuid import uuid4

_correlation = contextvars.ContextVar('tutoring_correlation_id', default=None)
_SAFE = re.compile(r'^[a-zA-Z0-9._:-]{1,80}$')
# Ensure INFO business traces reach stdout in both Uvicorn and service worker images.
logging.basicConfig(level=logging.INFO, format='%(message)s')
LOG = logging.getLogger('tutoring.telemetry')
LOG.setLevel(logging.INFO)


def clean_id(value):
    return value if isinstance(value, str) and _SAFE.fullmatch(value) else str(uuid4())


def start_trace(value=None):
    trace = clean_id(value)
    token = _correlation.set(trace)
    return trace, token


def end_trace(token):
    _correlation.reset(token)


def trace_id():
    return _correlation.get() or '-'


def emit(event, *, level='info', **fields):
    # Explicit safe metadata only; never pass bearer tokens, passwords, payloads.
    record = {'event': event, 'correlation_id': trace_id(), **fields}
    text = json.dumps(record, ensure_ascii=False, default=str, separators=(',', ':'))
    getattr(LOG, level)(text)


def elapsed_ms(since):
    return round((time.monotonic() - since) * 1000, 2)
