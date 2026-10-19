from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID
from app.core.errors import fail


def valid_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        fail("BAD_USER_INPUT", "Invalid UUID")


def valid_page(page: dict) -> dict:
    limit, offset = page.get("limit", 20), page.get("offset", 0)
    if type(limit) is not int or type(offset) is not int or not (1 <= limit <= 100) or offset < 0:
        fail("BAD_USER_INPUT", "Page must have limit 1..100 and offset >= 0")
    return {"limit": limit, "offset": offset}


def valid_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start >= end:
        fail("BAD_USER_INPUT", "from must precede to")
    return start, end


def decimal_or_none(v):
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        fail("BAD_USER_INPUT", "Invalid decimal")


def page_result(values: list, page: dict) -> dict:
    return {
        "items": values[:page["limit"]],
        "nextOffset": page["offset"] + page["limit"] if len(values) > page["limit"] else None,
    }
