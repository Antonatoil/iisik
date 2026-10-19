"""R: authoritative reviews and teacher rating, exclusively DB-R."""
from app.core.db import one, rows
from app.core.validation import page_result


def list_reviews(teacher_id: str, page: dict) -> dict:
    raw = rows("r", """
       SELECT id::text, teacher_id::text, score, text, created_at
       FROM reviews WHERE teacher_id=CAST(:teacher AS uuid)
       ORDER BY created_at DESC, id OFFSET :offset LIMIT :fetch
    """, {"teacher": teacher_id, "offset": page["offset"], "fetch": page["limit"] + 1})
    return page_result([{"id": r["id"], "teacherId": r["teacher_id"], "score": r["score"], "text": r["text"], "createdAt": r["created_at"]} for r in raw], page)


def get_rating(teacher_id: str) -> dict | None:
    return one("r", """
       SELECT teacher_id::text AS \"teacherId\", average, review_count AS \"reviewCount\",
              version, updated_at AS \"updatedAt\" FROM ratings
       WHERE teacher_id=CAST(:teacher AS uuid)
    """, {"teacher": teacher_id})
