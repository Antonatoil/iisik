"""Run INSIDE the running gateway container with seven seeded DBs available."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

STUDENT = "demo-student-token"
TEACHER = "demo-teacher-token"
ADMIN = "demo-admin-token"
TID = "00000000-0000-4000-8000-000000000201"
PAGE = "{limit: 20, offset: 0}"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as instance:
        yield instance


def run(client, query, token=STUDENT, variables=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post("/graphql/", json={"query": query, "variables": variables or {}}, headers=h)
    assert response.status_code == 200, response.text
    return response.json()


def test_ready_and_seven_databases(client):
    r = client.get("/ready")
    assert r.status_code == 200, r.text
    assert set(r.json()["databases"]) == set("atlprnx")


def test_student_can_read_me_and_nested_student(client):
    response = run(client, "{me{id role name student{learningGoal}}}")
    assert "errors" not in response, response
    assert response["data"]["me"]["role"] == "STUDENT"
    assert response["data"]["me"]["student"]["learningGoal"]


def test_teacher_catalogue_and_related_fields(client):
    response = run(client, f"""{{ teachers(filter:{{sort:RATING_DESC}},page:{PAGE}) {{
        items {{ id displayName subjects{{name}} price{{amount currency}}
                metrics{{average completedCount}} rating{{average reviewCount}}
                reviews(page:{PAGE}){{score text}} }} nextOffset }} }}""")
    assert "errors" not in response, response
    assert len(response["data"]["teachers"]["items"]) == 2
    assert response["data"]["teachers"]["items"][0]["rating"]["average"] == "5.000"


def test_available_slots_and_missing_teacher(client):
    r = run(client, f"""{{ availableSlots(teacherId:\"{TID}\",from:\"2020-01-01T00:00:00Z\",to:\"2035-01-01T00:00:00Z\",page:{PAGE}){{ items{{id status}} }} }}""")
    assert "errors" not in r, r
    assert len(r["data"]["availableSlots"]["items"]) == 1
    r = run(client, "{teacher(id:\"00000000-0000-4000-8000-000000009999\"){id}}")
    assert r["data"]["teacher"] is None


def test_bookings_payments_notifications_and_lesson_links(client):
    r = run(client, f"""{{ myBookings(page:{PAGE}){{items{{id lesson{{topic slot{{startsAt status}}}}}}}}
    myPayments(page:{PAGE}){{items{{status money{{amount currency}}}}}}
    notifications(page:{PAGE}){{items{{kind text}}}} }}""")
    assert "errors" not in r, r
    assert r["data"]["myBookings"]["items"][0]["lesson"]["topic"]
    assert r["data"]["myPayments"]["items"][0]["status"] == "COMPLETED"
    assert r["data"]["notifications"]["items"]


def test_role_isolation_and_no_bearer(client):
    r = run(client, f"{{users(page:{PAGE}){{items{{id}}}}}}")
    assert r["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    r = run(client, "{me{id}}", token=None)
    assert r["errors"][0]["extensions"]["code"] == "UNAUTHENTICATED"
    r = run(client, f"{{mySchedule(from:\"2020-01-01T00:00:00Z\",to:\"2035-01-01T00:00:00Z\",page:{PAGE}){{items{{id}}}}}}")
    assert r["errors"][0]["extensions"]["code"] == "FORBIDDEN"


def test_teacher_schedule_and_student_lessons(client):
    r = run(client, f"{{mySchedule(from:\"2020-01-01T00:00:00Z\",to:\"2035-01-01T00:00:00Z\",page:{PAGE}){{items{{status}}}}}}", token=TEACHER)
    assert "errors" not in r, r
    assert len(r["data"]["mySchedule"]["items"]) == 3
    r = run(client, f"{{lessons(filter:{{from:\"2020-01-01T00:00:00Z\",to:\"2035-01-01T00:00:00Z\"}},page:{PAGE}){{items{{status}}}}}}")
    assert "errors" not in r, r
    assert len(r["data"]["lessons"]["items"]) == 1


def test_admin_analytics_and_all_users(client):
    r = run(client, f"""{{users(page:{PAGE}){{items{{name role}}}}
        platformAnalytics(input:{{from:\"2020-01-01T00:00:00Z\",to:\"2035-01-01T00:00:00Z\",page:{PAGE}}}){{
            lessonsCompleted successfulPayments revenue{{amount currency}} teachers{{teacherId currentRating}}
        }} }}""", token=ADMIN)
    assert "errors" not in r, r
    assert len(r["data"]["users"]["items"]) == 5
    assert r["data"]["platformAnalytics"]["lessonsCompleted"] == 1
    assert r["data"]["platformAnalytics"]["successfulPayments"] == 1


def test_mutations_are_explicitly_deferred(client):
    r = run(client, "mutation {login(input:{email:\"x\",password:\"y\"}){token}}", token=None)
    assert r["errors"][0]["extensions"]["code"] == "NOT_IMPLEMENTED_IN_LAB3"


def test_invalid_date_and_page_are_rejected(client):
    r = run(client, f"{{availableSlots(teacherId:\"{TID}\",from:\"2030-01-01T00:00:00Z\",to:\"2020-01-01T00:00:00Z\",page:{PAGE}){{items{{id}}}}}}")
    assert r["errors"][0]["extensions"]["code"] == "BAD_USER_INPUT"
    r = run(client, "{teachers(filter:{},page:{limit:0,offset:0}){items{id}}}")
    assert r["errors"][0]["extensions"]["code"] == "BAD_USER_INPUT"
