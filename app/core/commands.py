"""Lab 4 helpers for local ACID transactions and idempotent user commands.
A transaction may touch ONLY the database owned by its service.
"""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.core.db import engine
from app.core.errors import fail
from app.core.validation import valid_id


def now():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def digest(value):
    return hashlib.sha256(canon(value).encode('utf-8')).hexdigest()


def fetch(conn, sql, **params):
    row = conn.execute(text(sql), params).mappings().first()
    return dict(row) if row else None


def execute(conn, sql, **params):
    return conn.execute(text(sql), params)


def check_receipt(conn, op_id, actor_id, command, payload):
    op_id = valid_id(op_id)
    # Lock per operation ID BEFORE checking its receipt: concurrent retries serialize.
    execute(conn, 'SELECT pg_advisory_xact_lock(hashtext(:key))', key='operation:'+op_id)
    found = fetch(conn, "SELECT actor_user_id::text AS actor, command, request_hash, response FROM command_receipts WHERE operation_id=CAST(:id AS uuid)", id=op_id)
    if not found:
        return None
    if found['actor'] != actor_id or found['command'] != command or found['request_hash'] != digest(payload):
        fail('IDEMPOTENCY_CONFLICT', 'operationId was already used with different arguments')
    return found['response']


def save_receipt(conn, op_id, actor_id, command, payload, result):
    safe = json.loads(canon(result))
    execute(conn, """INSERT INTO command_receipts(operation_id,actor_user_id,command,request_hash,response,created_at)
      VALUES (CAST(:op AS uuid),CAST(:actor AS uuid),:command,:hash,CAST(:reply AS jsonb),now())""",
      op=valid_id(op_id), actor=actor_id, command=command, hash=digest(payload), reply=canon(safe))
    # The event is saved in the same local transaction as the command receipt.
    from app.events.domain import on_receipt
    on_receipt(conn, op_id, actor_id, command, payload, result)
    return result


def business_condition(test, code, message):
    if not test:
        fail(code, message)


def conflict_or_raise(exc):
    if isinstance(exc, IntegrityError):
        fail('CONFLICT', 'Database constraint prevents this operation')
    raise exc
