"""A: accounts, roles, students and sessions. Reads DB-A only."""
from hashlib import sha256
from app.core.db import one, rows
from app.core.validation import page_result


def validate_session(token: str) -> dict | None:
    if not token:
        return None
    record = one("a", """
        SELECT u.id::text AS id, u.role_code AS role, u.name, u.email,
               u.status, s.id::text AS session_id
        FROM sessions s JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=:hash AND s.revoked_at IS NULL
          AND s.expires_at>now() AND u.status='ACTIVE'
    """, {"hash": sha256(token.encode("utf-8")).hexdigest()})
    return record


def get_user(user_id: str) -> dict | None:
    return one("a", """
        SELECT id::text AS id, role_code AS role, name, email, status
        FROM users WHERE id=CAST(:id AS uuid)
    """, {"id": user_id})


def list_users(page: dict) -> dict:
    records = rows("a", """
        SELECT id::text AS id, role_code AS role, name, email, status
        FROM users ORDER BY name, id OFFSET :offset LIMIT :fetch
    """, {"offset": page["offset"], "fetch": page["limit"] + 1})
    return page_result(records, page)


def get_student(user_id: str) -> dict | None:
    item = one("a", "SELECT id::text, learning_goal AS \"learningGoal\" FROM students WHERE id=CAST(:id AS uuid)", {"id": user_id})
    return item
