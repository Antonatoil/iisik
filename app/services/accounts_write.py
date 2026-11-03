"""Write business operations owned by Accounts (DB-A)."""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from sqlalchemy import text
from app.core.db import engine
from app.core.commands import (now, new_id, fetch, execute, check_receipt, save_receipt, business_condition)
from app.core.errors import fail
from app.core.validation import valid_id
from app.services.accounts import get_user


def _hash(password):
    salt = os.urandom(16)
    iters = 260000
    return f"pbkdf2_sha256${iters}${salt.hex()}${hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iters).hex()}"


def _verify(password, stored):
    if stored.startswith('pbkdf2_sha256$'):
        try:
            _, count, salt, digest = stored.split('$')
            actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count))
            return hmac.compare_digest(actual, bytes.fromhex(digest))
        except (ValueError, TypeError):
            return False
    # Lab 3 demo data used historical SHA256 hashes; upgrade on first valid login.
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def register_user(arg):
    business_condition(arg['role'] in ('STUDENT','TEACHER'), 'BAD_USER_INPUT', 'Self registration allows STUDENT or TEACHER')
    email = arg['email'].strip().lower()
    business_condition('@' in email and len(email) <= 254, 'BAD_USER_INPUT', 'Invalid email')
    business_condition(8 <= len(arg['password']) <= 128, 'BAD_USER_INPUT', 'Password must be 8..128 characters')
    name = arg['name'].strip()
    business_condition(1 <= len(name) <= 100, 'BAD_USER_INPUT', 'Name is required')
    # No plaintext password in receipts (only a secret-keyed fingerprint).
    key = os.environ.get('REGISTRATION_HMAC_KEY', 'lab4_local_demo_change_me').encode()
    sig = hmac.new(key, arg['password'].encode(), hashlib.sha256).hexdigest()
    data = {'email':email, 'role':arg['role'], 'name':name, 'goal':arg.get('learningGoal'), 'password_sig':sig}
    uid = new_id()
    with engine('a').begin() as conn:
        execute(conn, 'SELECT pg_advisory_xact_lock(hashtext(:key))', key='operation:'+valid_id(arg['operationId']))
        execute(conn, 'SELECT pg_advisory_xact_lock(hashtext(:key))', key='register:'+email)
        found = fetch(conn, 'SELECT response FROM command_receipts WHERE operation_id=CAST(:op AS uuid)', op=valid_id(arg['operationId']))
        if found:
            record = fetch(conn, "SELECT actor_user_id::text AS actor, command,request_hash,response FROM command_receipts WHERE operation_id=CAST(:op AS uuid)", op=arg['operationId'])
            from app.core.commands import digest
            if record['command']!='register' or record['request_hash'] != digest(data):
                fail('IDEMPOTENCY_CONFLICT','The registration operationId is already used')
            return record['response']
        business_condition(fetch(conn,'SELECT id FROM users WHERE email=:e',e=email) is None,'CONFLICT','Email already registered')
        execute(conn,"""INSERT INTO users(id,role_code,email,password_hash,name,status,created_at)
          VALUES(CAST(:id AS uuid),:role,:email,:pw,:name,'ACTIVE',now())""", id=uid,role=arg['role'],email=email,pw=_hash(arg['password']),name=name)
        if arg['role']=='STUDENT':
            execute(conn,'INSERT INTO students(id,learning_goal) VALUES(CAST(:id AS uuid),:goal)',id=uid,goal=arg.get('learningGoal'))
        result={'id':uid,'role':arg['role'],'name':name,'email':email,'status':'ACTIVE'}
        return save_receipt(conn,arg['operationId'],uid,'register',data,result)


def login_user(arg):
    email=arg['email'].strip().lower()
    with engine('a').begin() as conn:
        u=fetch(conn,'SELECT id::text,password_hash,status FROM users WHERE email=:email FOR UPDATE',email=email)
        business_condition(u is not None and u['status']=='ACTIVE' and _verify(arg['password'],u['password_hash']), 'UNAUTHENTICATED','Invalid credentials')
        if not u['password_hash'].startswith('pbkdf2_sha256$'):
            execute(conn,'UPDATE users SET password_hash=:pw WHERE id=CAST(:id AS uuid)',pw=_hash(arg['password']),id=u['id'])
        token=secrets.token_urlsafe(32)
        expires=now()+timedelta(hours=1)
        execute(conn,"""INSERT INTO sessions(id,token_hash,user_id,expires_at)
         VALUES(CAST(:id AS uuid),:hash,CAST(:user AS uuid),:expiry)""",id=new_id(),hash=hashlib.sha256(token.encode()).hexdigest(),user=u['id'],expiry=expires)
    return {'token':token,'expiresAt':expires,'user':get_user(u['id'])}


def set_user_status(actor,arg):
    uid=valid_id(arg['userId'])
    business_condition(uid != actor['id'],'BAD_USER_INPUT','Administrator cannot block their own account')
    with engine('a').begin() as conn:
        cached=check_receipt(conn,arg['operationId'],actor['id'],'setUserStatus',arg)
        if cached:return cached
        u=fetch(conn,'SELECT id FROM users WHERE id=CAST(:id AS uuid) FOR UPDATE',id=uid)
        business_condition(u is not None,'NOT_FOUND','User not found')
        execute(conn,'UPDATE users SET status=:status WHERE id=CAST(:id AS uuid)',status=arg['status'],id=uid)
        if arg['status']=='BLOCKED':
            execute(conn,'UPDATE sessions SET revoked_at=now() WHERE user_id=CAST(:id AS uuid) AND revoked_at IS NULL',id=uid)
        user=fetch(conn,'SELECT id::text,role_code AS role,name,email,status FROM users WHERE id=CAST(:id AS uuid)',id=uid)
        return save_receipt(conn,arg['operationId'],actor['id'],'setUserStatus',arg,user)
