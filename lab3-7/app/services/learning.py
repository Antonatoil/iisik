"""L: schedule slots, lessons and booking ownership, exclusively DB-L."""
from app.core.db import one, rows
from app.core.validation import page_result


def slot_map(s: dict) -> dict:
    return {"id": s["id"], "teacherId": s["teacher_id"], "startsAt": s["starts_at"], "endsAt": s["ends_at"], "status": s["status"], "version": s["version"]}


def lesson_map(s: dict) -> dict:
    return {"id": s["id"], "slot_id": s["slot_id"], "subjectId": s["subject_id"], "topic": s["topic"], "status": s["status"], "resultText": s["result_text"], "goalOutcome": "NOT_ASSESSED" if s["goal_achieved"] is None else ("ACHIEVED" if s["goal_achieved"] else "NOT_ACHIEVED"), "startedAt": s["started_at"], "completedAt": s["completed_at"], "version": s["version"]}


def booking_map(s: dict) -> dict:
    return {"id": s["id"], "studentId": s["student_id"], "lesson_id": s["lesson_id"], "status": s["status"], "price": {"amount": s["price"], "currency": s["currency"]}, "paymentState": s["payment_state"], "createdAt": s["created_at"]}


def get_slot(uid: str) -> dict | None:
    s = one("l", "SELECT id::text, teacher_id::text, starts_at, ends_at, status, version FROM slots WHERE id=CAST(:id AS uuid)", {"id": uid})
    return slot_map(s) if s else None


def get_lesson(uid: str) -> dict | None:
    s = one("l", "SELECT id::text, slot_id::text, subject_id::text, topic, status, result_text, goal_achieved, started_at, completed_at, version FROM lessons WHERE id=CAST(:id AS uuid)", {"id": uid})
    return lesson_map(s) if s else None


def available_slots(teacher_id: str, start, end, page: dict) -> dict:
    records = rows("l", """
        SELECT s.id::text, s.teacher_id::text, s.starts_at, s.ends_at, s.status, s.version
        FROM slots s WHERE s.teacher_id=CAST(:teacher AS uuid)
        AND s.starts_at>=:start AND s.starts_at<:end AND s.status='AVAILABLE'
        ORDER BY s.starts_at, s.id OFFSET :offset LIMIT :fetch
    """, {"teacher": teacher_id, "start": start, "end": end, "offset": page["offset"], "fetch": page["limit"] + 1})
    return page_result([slot_map(r) for r in records], page)


def my_schedule(teacher_id: str, start, end, page: dict) -> dict:
    records = rows("l", """
        SELECT id::text, teacher_id::text, starts_at, ends_at, status, version
        FROM slots WHERE teacher_id=CAST(:teacher AS uuid)
        AND starts_at<:end AND ends_at>:start ORDER BY starts_at, id
        OFFSET :offset LIMIT :fetch
    """, {"teacher": teacher_id, "start": start, "end": end, "offset": page["offset"], "fetch": page["limit"] + 1})
    return page_result([slot_map(r) for r in records], page)


def lessons_for_actor(actor: dict, filters: dict, page: dict) -> dict:
    if actor["role"] == "STUDENT":
        join_sql = "JOIN bookings b ON b.lesson_id=le.id"
        own_sql = "b.student_id=CAST(:actor AS uuid)"
    else:
        join_sql = ""
        own_sql = "s.teacher_id=CAST(:actor AS uuid)"
    params = {"actor": actor["id"], "start": filters["from"], "end": filters["to"], "offset": page["offset"], "fetch": page["limit"] + 1}
    status = ""
    if filters.get("status"):
        params["status"] = filters["status"]
        status = "AND le.status=:status"
    data = rows("l", f"""
        SELECT le.id::text, le.slot_id::text, le.subject_id::text, le.topic,
               le.status, le.result_text, le.goal_achieved, le.started_at,
               le.completed_at, le.version
        FROM lessons le JOIN slots s ON s.id=le.slot_id {join_sql}
        WHERE {own_sql} AND s.starts_at<:end AND s.ends_at>:start {status}
        ORDER BY s.starts_at, le.id OFFSET :offset LIMIT :fetch
    """, params)
    return page_result([lesson_map(r) for r in data], page)


def my_bookings(student_id: str, page: dict) -> dict:
    data = rows("l", """
        SELECT id::text, lesson_id::text, student_id::text, status,
               price, currency, payment_state, created_at
        FROM bookings WHERE student_id=CAST(:user AS uuid)
        ORDER BY created_at DESC, id OFFSET :offset LIMIT :fetch
    """, {"user": student_id, "offset": page["offset"], "fetch": page["limit"] + 1})
    return page_result([booking_map(r) for r in data], page)
