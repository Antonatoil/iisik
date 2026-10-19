"""GraphQL read resolvers stay thin. All domain access goes through mock ports."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from ariadne import QueryType, MutationType, ObjectType, ScalarType, gql, make_executable_schema
from app.core.errors import fail, require_role
from app.core.validation import valid_id, valid_page, valid_range
from app.transport.mock_ports import ports

query = QueryType()
mutation = MutationType()
user_type = ObjectType("User")
teacher_type = ObjectType("Teacher")
lesson_type = ObjectType("Lesson")
booking_type = ObjectType("Booking")
datetime_type = ScalarType("DateTime")
decimal_type = ScalarType("Decimal")
long_type = ScalarType("Long")


@datetime_type.serializer
def serialize_datetime(value):
    return value.isoformat() if isinstance(value, datetime) else value


@datetime_type.value_parser
def parse_datetime(value):
    if not isinstance(value, str):
        raise ValueError("DateTime requires an RFC3339 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Timezone offset required")
        return dt
    except ValueError as exc:
        raise ValueError("DateTime requires RFC3339 and timezone offset") from exc


@decimal_type.serializer
def serialize_decimal(value):
    return str(value) if value is not None else None


@decimal_type.value_parser
def parse_decimal(value):
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError("Invalid decimal") from exc


@long_type.serializer
def serialize_long(value):
    return int(value) if value is not None else None


def actor_of(info, *roles):
    actor = info.context["actor"]
    require_role(actor, *roles)
    return actor


@query.field("me")
def me(_, info):
    actor = actor_of(info)
    return ports.GetMe(actor["id"])


@query.field("users")
def users(_, info, page):
    actor_of(info, "ADMIN")
    return ports.ListUsers(valid_page(page))


@query.field("teachers")
def teachers(_, info, filter, page):
    actor_of(info)
    return ports.SearchTeachers(filter, valid_page(page))


@query.field("teacher")
def teacher(_, info, id):
    actor_of(info)
    return ports.GetTeacher(valid_id(id))


@query.field("subjects")
def subjects(_, info, page, includeInactive=False):
    actor = actor_of(info)
    if includeInactive and actor["role"] != "ADMIN":
        fail("FORBIDDEN", "Inactive subjects are visible only to ADMIN")
    return ports.ListSubjects(valid_page(page), includeInactive)


@query.field("availableSlots")
def available_slots(_, info, teacherId, page, **kw):
    actor_of(info)
    start, end = valid_range(kw["from"], kw["to"])
    return ports.ListAvailableSlots(valid_id(teacherId), start, end, valid_page(page))


@query.field("mySchedule")
def my_schedule(_, info, page, **kw):
    actor = actor_of(info, "TEACHER")
    start, end = valid_range(kw["from"], kw["to"])
    return ports.GetMySchedule(actor["id"], start, end, valid_page(page))


@query.field("lessons")
def lessons(_, info, filter, page):
    actor = actor_of(info, "STUDENT", "TEACHER")
    valid_range(filter["from"], filter["to"])
    return ports.ListLessons(actor, filter, valid_page(page))


@query.field("myBookings")
def my_bookings(_, info, page):
    actor = actor_of(info, "STUDENT")
    return ports.ListMyBookings(actor["id"], valid_page(page))


@query.field("myPayments")
def my_payments(_, info, page):
    actor = actor_of(info, "STUDENT")
    return ports.ListMyPayments(actor["id"], valid_page(page))


@query.field("reviews")
def reviews(_, info, teacherId, page):
    actor_of(info)
    return ports.ListReviews(valid_id(teacherId), valid_page(page))


@query.field("rating")
def rating(_, info, teacherId):
    actor_of(info)
    return ports.GetRating(valid_id(teacherId))


@query.field("notifications")
def notifications(_, info, page, unreadOnly=False):
    actor = actor_of(info)
    return ports.ListNotifications(actor["id"], unreadOnly, valid_page(page))


@query.field("platformAnalytics")
def platform_analytics(_, info, input):
    actor_of(info, "ADMIN")
    valid_range(input["from"], input["to"])
    return ports.GetPlatformAnalytics(input)


@user_type.field("student")
def user_student(parent, info):
    if parent["role"] != "STUDENT":
        return None
    actor = actor_of(info)
    if actor["role"] != "ADMIN" and actor["id"] != parent["id"]:
        return None
    return ports.GetStudent(parent["id"])


@teacher_type.field("subjects")
def teacher_subjects(parent, info):
    actor_of(info)
    return ports.GetTeacherSubjects(parent["id"])


@teacher_type.field("metrics")
def teacher_metrics(parent, info):
    actor_of(info)
    return ports.GetTeacherMetrics(parent["id"])


@teacher_type.field("rating")
def teacher_rating(parent, info):
    actor_of(info)
    return ports.GetRating(parent["id"])


@teacher_type.field("reviews")
def teacher_reviews(parent, info, page):
    actor_of(info)
    return ports.ListReviews(parent["id"], valid_page(page))["items"]


@teacher_type.field("slots")
def teacher_slots(parent, info, page, **kw):
    actor_of(info)
    start, end = valid_range(kw["from"], kw["to"])
    return ports.ListAvailableSlots(parent["id"], start, end, valid_page(page))["items"]


@lesson_type.field("slot")
def lesson_slot(parent, info):
    actor_of(info)
    return ports.GetSlot(parent["slot_id"])


@booking_type.field("lesson")
def booking_lesson(parent, info):
    actor_of(info, "STUDENT")
    return ports.GetLesson(parent["lesson_id"])


# The full Lab 2 mutation contract remains unchanged, but its implementation
# is deliberately postponed: Lab 3 requires GraphQL Query, not write workflows.
MUTATIONS = (
    "register", "login", "updateTeacherProfile", "setAvailability",
    "bookLesson", "cancelLesson", "rescheduleLesson", "registerPayment",
    "startLesson", "completeLesson", "addReview", "markNotificationRead",
    "setUserStatus", "manageSubject",
)


def unavailable_mutation(_, info, **kwargs):
    fail("NOT_IMPLEMENTED_IN_LAB3", "Mutation is reserved for the next laboratory works")


for mutation_name in MUTATIONS:
    mutation.set_field(mutation_name, unavailable_mutation)

schema_path = Path(__file__).resolve().parents[2] / "contracts" / "schema.graphql"
schema = make_executable_schema(gql(schema_path.read_text(encoding="utf-8")), [
    query, mutation, user_type, teacher_type, lesson_type, booking_type,
    datetime_type, decimal_type, long_type,
])
