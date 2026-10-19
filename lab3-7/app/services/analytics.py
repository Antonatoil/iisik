"""X: read-only analytics built only from DB-X projections (no cross-db JOIN)."""
from app.core.db import one, rows
from app.core.validation import valid_page, valid_id


def _money_list(data: list[dict]) -> list[dict]:
    return [{"amount": r["amount"], "currency": r["currency"]} for r in data]


def platform_analytics(arg: dict) -> dict:
    start, end = arg["from"], arg["to"]
    page = valid_page(arg["page"])
    tf = arg.get("teacherId")
    if tf:
        tf = valid_id(tf)
    p = {"start": start, "end": end, "teacher": tf}
    teacher_filter = "AND (CAST(:teacher AS uuid) IS NULL OR teacher_id=CAST(:teacher AS uuid))"
    active = one("x", "SELECT count(DISTINCT user_id) AS n FROM auth_facts WHERE authenticated_at>=:start AND authenticated_at<:end", p)["n"]
    lessons = one("x", f"""
       SELECT count(*) FILTER (WHERE status='COMPLETED' AND completed_at>=:start AND completed_at<:end) AS completed,
              count(*) FILTER (WHERE status='CANCELLED' AND cancelled_at>=:start AND cancelled_at<:end) AS cancelled,
              count(*) FILTER (WHERE status='COMPLETED' AND completed_at>=:start AND completed_at<:end AND goal_achieved IS NOT NULL) AS assessed,
              count(*) FILTER (WHERE status='COMPLETED' AND completed_at>=:start AND completed_at<:end AND goal_achieved IS TRUE) AS achieved
       FROM lesson_facts WHERE TRUE {teacher_filter}
    """, p)
    payments = one("x", f"""
       SELECT count(*) FILTER (WHERE status='COMPLETED') AS successful,
              count(*) FILTER (WHERE status='FAILED') AS failed
       FROM payment_facts WHERE settled_at>=:start AND settled_at<:end {teacher_filter}
    """, p)
    revenue = rows("x", f"""
       SELECT currency, sum(amount) AS amount FROM payment_facts
       WHERE status='COMPLETED' AND settled_at>=:start AND settled_at<:end {teacher_filter}
       GROUP BY currency ORDER BY currency
    """, p)
    ratings = one("x", f"""
       SELECT avg(score) AS average FROM review_facts
       WHERE created_at>=:start AND created_at<:end {teacher_filter}
    """, p)
    teachers = rows("x", f"""
       WITH ids AS (
           SELECT teacher_id FROM lesson_facts UNION
           SELECT teacher_id FROM payment_facts UNION
           SELECT teacher_id FROM review_facts UNION
           SELECT teacher_id FROM rating_projection
       )
       SELECT ids.teacher_id::text AS teacher_id FROM ids
       WHERE (CAST(:teacher AS uuid) IS NULL OR ids.teacher_id=CAST(:teacher AS uuid))
       ORDER BY ids.teacher_id OFFSET :offset LIMIT :fetch
    """, {**p, "offset": page["offset"], "fetch": page["limit"] + 1})
    next_offset = page["offset"] + page["limit"] if len(teachers)>page["limit"] else None
    stats = []
    for row in teachers[:page["limit"]]:
        tid = row["teacher_id"]
        q = {"teacher": tid, "start": start, "end": end}
        comp = one("x", "SELECT count(*) AS n FROM lesson_facts WHERE teacher_id=CAST(:teacher AS uuid) AND status='COMPLETED' AND completed_at>=:start AND completed_at<:end", q)["n"]
        rev = rows("x", "SELECT currency, sum(amount) AS amount FROM payment_facts WHERE teacher_id=CAST(:teacher AS uuid) AND status='COMPLETED' AND settled_at>=:start AND settled_at<:end GROUP BY currency ORDER BY currency", q)
        avg = one("x", "SELECT avg(score) AS n FROM review_facts WHERE teacher_id=CAST(:teacher AS uuid) AND created_at>=:start AND created_at<:end", q)["n"]
        current = one("x", "SELECT average FROM rating_projection WHERE teacher_id=CAST(:teacher AS uuid)", {"teacher": tid})
        stats.append({"teacherId": tid, "lessonsCompleted": comp, "revenue": _money_list(rev), "averageScore": avg, "currentRating": current["average"] if current else None})
    completed = int(lessons["completed"])
    assessed = int(lessons["assessed"])
    timestamp = one("x", "SELECT max(processed_at) AS last FROM inbox")
    return {
       "from": start, "to": end, "activeUsers": active,
       "lessonsCompleted": completed, "cancellations": lessons["cancelled"],
       "successfulPayments": payments["successful"], "failedPayments": payments["failed"],
       "revenue": _money_list(revenue), "averageScore": ratings["average"],
       "goalAchievementRate": (assessed and int(lessons["achieved"]) / assessed) if assessed else None,
       "resultCoverage": assessed / completed if completed else None,
       "teachers": stats, "nextOffset": next_offset,
       "lastProcessedAt": timestamp["last"] if timestamp else None,
    }
