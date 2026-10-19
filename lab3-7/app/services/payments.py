"""P: persisted payment attempts, exclusively DB-P."""
from app.core.db import rows
from app.core.validation import page_result


def my_payments(student_id: str, page: dict) -> dict:
    raw = rows("p", """
       SELECT id::text, operation_id::text, booking_id::text, status,
              amount, currency, failure_code, created_at, settled_at
       FROM payments WHERE student_id=CAST(:user AS uuid)
       ORDER BY created_at DESC, id OFFSET :offset LIMIT :fetch
    """, {"user": student_id, "offset": page["offset"], "fetch": page["limit"] + 1})
    data = [{"id": r["id"], "operationId": r["operation_id"], "bookingId": r["booking_id"], "status": r["status"], "money": ({"amount": r["amount"], "currency": r["currency"]} if r["amount"] is not None else None), "failureCode": r["failure_code"], "createdAt": r["created_at"], "settledAt": r["settled_at"]} for r in raw]
    return page_result(data, page)
