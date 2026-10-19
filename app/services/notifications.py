"""N: in-app notifications, exclusively DB-N."""
from app.core.db import rows
from app.core.validation import page_result


def list_notifications(user_id: str, unread_only: bool, page: dict) -> dict:
    raw = rows("n", """
       SELECT id::text, kind, text, object_id::text, created_at, read_at
       FROM notifications WHERE user_id=CAST(:user AS uuid)
       AND (NOT :unread OR read_at IS NULL)
       ORDER BY created_at DESC, id OFFSET :offset LIMIT :fetch
    """, {"user": user_id, "unread": unread_only, "offset": page["offset"], "fetch": page["limit"] + 1})
    return page_result([{"id": r["id"], "kind": r["kind"], "text": r["text"], "objectId": r["object_id"], "createdAt": r["created_at"], "readAt": r["read_at"]} for r in raw], page)
