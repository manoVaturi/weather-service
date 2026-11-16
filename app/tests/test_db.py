"""The database layer: parameters, error handling and the schema flag."""

import psycopg
import pytest

from app import db
from app.tests.fakes import FakeConnection


def test_the_city_is_sent_as_a_parameter_never_inside_the_sql(monkeypatch):
    connection = FakeConnection()
    nasty = "x'); DROP TABLE searches;--"
    monkeypatch.setattr(db, "DB_HOST", "postgres.invalid")
    monkeypatch.setattr(db, "_connect", lambda: connection)
    monkeypatch.setitem(db._state, "ready", False)

    db.record_search(nasty)

    assert connection.calls[0][0] == db.SCHEMA  # the table is created first
    sql, params = connection.calls[1]
    assert sql == "INSERT INTO searches (city) VALUES (%s)"
    assert params == (nasty,)
    assert "DROP TABLE" not in sql


def test_user_functions_refuse_when_the_database_is_not_configured(monkeypatch):
    monkeypatch.setattr(db, "DB_HOST", None)

    with pytest.raises(db.DatabaseUnavailable):
        db.get_or_create_user("mano")


def test_a_database_error_becomes_unavailable_and_resets_the_schema_flag(
    monkeypatch,
):
    def refuse():
        raise psycopg.OperationalError("database is down")

    monkeypatch.setattr(db, "DB_HOST", "postgres.invalid")
    monkeypatch.setattr(db, "_connect", refuse)
    monkeypatch.setitem(db._state, "ready", True)

    with pytest.raises(db.DatabaseUnavailable):
        db.list_favourites("mano")

    assert db._state["ready"] is False


def test_creating_a_user_says_whether_it_was_new(monkeypatch):
    monkeypatch.setattr(db, "DB_HOST", "postgres.invalid")
    monkeypatch.setitem(db._state, "ready", True)

    monkeypatch.setattr(
        db, "_connect", lambda: FakeConnection(rows=[(7,)])
    )  # the INSERT returned an id
    assert db.get_or_create_user("mano") == {"name": "mano", "created": True}

    monkeypatch.setattr(
        db, "_connect", lambda: FakeConnection(rows=[])
    )  # conflict: no row came back
    assert db.get_or_create_user("mano") == {"name": "mano", "created": False}
