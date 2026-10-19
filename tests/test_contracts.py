"""Pure contract tests: no network and no database required."""
from pathlib import Path
from graphql import validate_schema, parse
from app.gateway.schema import schema
from app.transport.mock_ports import ports

ROOT = Path(__file__).resolve().parents[1]


def test_original_lab2_graphql_contract_is_executable():
    assert not validate_schema(schema)
    assert len(schema.query_type.fields) == 14
    assert len(schema.mutation_type.fields) == 14
    assert schema.get_type("Teacher") is not None


def test_original_proto_has_all_seven_rpc_services():
    proto = (ROOT / "contracts" / "tutoring.proto").read_text(encoding="utf-8")
    for service in ("Accounts", "Catalog", "Learning", "Payments", "Reputation", "Notifications", "AnalyticsService"):
        assert f"service {service} {{" in proto


def test_each_database_has_own_schema():
    for name in "atlprnx":
        ddl = (ROOT / "db" / "schemas" / f"{name}_database.sql").read_text(encoding="utf-8")
        assert "CREATE TABLE" in ddl
        assert "BEGIN;" in ddl and "COMMIT;" in ddl
    # Seven different physical DBs; contract must not create one shared DB.
    init = (ROOT / "db" / "init_all.sql").read_text(encoding="utf-8")
    assert sum(init.count(f"CREATE DATABASE tutor_{owner}") for owner in "atlprnx") == 7


def test_mock_adapters_expose_expected_read_rpc_methods():
    for method in ("ValidateSession", "SearchTeachers", "ListAvailableSlots", "ListLessons", "ListMyBookings", "ListMyPayments", "ListReviews", "GetRating", "ListNotifications", "GetPlatformAnalytics"):
        assert callable(getattr(ports, method))
