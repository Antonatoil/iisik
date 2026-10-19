"""T: teacher catalogue, subject dictionary and local search projection."""
from app.core.db import one, rows
from app.core.validation import page_result, decimal_or_none, valid_id
from app.core.errors import fail

ORDER_BY = {
    "RATING_DESC": "m.average DESC NULLS LAST, t.id",
    "PRICE_ASC": "t.price ASC, t.id",
    "PRICE_DESC": "t.price DESC, t.id",
    "POPULARITY_DESC": "m.completed_count DESC, t.id",
}


def _teacher(item: dict) -> dict:
    return {
        "id": item["id"], "displayName": item["display_name"],
        "bio": item["bio"], "price": {"amount": item["price"], "currency": item["currency"]},
    }


def search_teachers(filters: dict, page: dict) -> dict:
    f = filters or {}
    order = ORDER_BY.get(f.get("sort") or "RATING_DESC")
    if order is None:
        fail("BAD_USER_INPUT", "Unknown sort")
    clauses = ["TRUE"]
    params = {"offset": page["offset"], "fetch": page["limit"] + 1}
    if f.get("subjectId") is not None:
        clauses.append("EXISTS (SELECT 1 FROM teacher_subjects x JOIN subjects s ON x.subject_id=s.id WHERE x.teacher_id=t.id AND x.subject_id=CAST(:subject_id AS uuid) AND s.active)")
        params["subject_id"] = valid_id(f["subjectId"])
    for key, sql_key, operator in (("minRating", "m.average", ">="), ("minPrice", "t.price", ">="), ("maxPrice", "t.price", "<=")):
        if f.get(key) is not None:
            value = decimal_or_none(f[key])
            if value < 0 or (key == "minRating" and value > 5):
                fail("BAD_USER_INPUT", "Invalid filter range")
            params[key] = value
            clauses.append(f"{sql_key} {operator} :{key}")
    if f.get("currency"):
        params["currency"] = f["currency"].upper()
        if len(params["currency"]) != 3:
            fail("BAD_USER_INPUT", "currency must be ISO 4217")
        clauses.append("t.currency=:currency")
    statement = f"""
       SELECT t.id::text, t.display_name, t.bio, t.price, t.currency
       FROM teachers t JOIN teacher_metrics m ON m.teacher_id=t.id
       WHERE {' AND '.join(clauses)} ORDER BY {order}
       OFFSET :offset LIMIT :fetch
    """
    return page_result([_teacher(row) for row in rows("t", statement, params)], page)


def get_teacher(uid: str) -> dict | None:
    result = one("t", "SELECT id::text, display_name, bio, price, currency FROM teachers WHERE id=CAST(:id AS uuid)", {"id": uid})
    return _teacher(result) if result else None


def list_subjects(page: dict, include_inactive: bool) -> dict:
    data = rows("t", """
       SELECT id::text, name, description, active FROM subjects
       WHERE active OR :include_inactive ORDER BY name, id OFFSET :offset LIMIT :fetch
    """, {"include_inactive": include_inactive, "offset": page["offset"], "fetch": page["limit"] + 1})
    return page_result(data, page)


def teacher_subjects(teacher_id: str) -> list[dict]:
    return rows("t", """
       SELECT s.id::text, s.name, s.description, s.active FROM subjects s
       JOIN teacher_subjects ts ON ts.subject_id=s.id
       WHERE ts.teacher_id=CAST(:id AS uuid) ORDER BY s.name
    """, {"id": teacher_id})


def metrics(teacher_id: str) -> dict:
    r = one("t", """
       SELECT average, review_count AS \"reviewCount\",
              completed_count AS \"completedCount\",
              last_review_at AS \"lastReviewAt\", updated_at AS \"updatedAt\"
       FROM teacher_metrics WHERE teacher_id=CAST(:id AS uuid)
    """, {"id": teacher_id})
    return r or {"average": None, "reviewCount": 0, "completedCount": 0, "lastReviewAt": None, "updatedAt": None}
