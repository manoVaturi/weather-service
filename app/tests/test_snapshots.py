"""MongoDB snapshots: what is stored, the TTL index, ordering and the failure rules."""

from datetime import UTC, datetime

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from app import snapshots
from app.main import app
from app.tests.fakes import FakeCollection

BODY = {
    "location": "Paris, France",
    "current": {"temperature_2m": 12.3},
    "daily": {"time": ["2026-10-21"]},
}


@pytest.fixture
def collection(monkeypatch):
    fake = FakeCollection()
    monkeypatch.setattr(snapshots, "MONGO_HOST", "mongo.invalid")
    monkeypatch.setattr(snapshots, "_collection", lambda: fake)
    monkeypatch.setitem(snapshots._state, "ready", False)
    return fake


def refuse():
    raise ServerSelectionTimeoutError("mongo is down")


def test_a_snapshot_keeps_the_weather_and_a_timestamp(collection):
    snapshots.record("Paris", "paris", BODY)

    stored = collection.documents[0]
    assert stored["city"] == "Paris"
    assert stored["city_key"] == "paris"
    assert stored["current"] == BODY["current"]
    assert stored["daily"] == BODY["daily"]
    assert stored["fetched_at"].tzinfo is not None


def test_the_ttl_index_is_created_once_with_the_configured_lifetime(
    collection, monkeypatch
):
    monkeypatch.setattr(snapshots, "TTL_SECONDS", 3600)

    snapshots.record("Paris", "paris", BODY)
    snapshots.record("Paris", "paris", BODY)

    ttl = [i for i in collection.indexes if "expireAfterSeconds" in i[1]]
    assert ttl == [("fetched_at", {"expireAfterSeconds": 3600})]
    assert len(collection.indexes) == 2  # the TTL index and the lookup index
    assert len(collection.documents) == 2


def test_nothing_happens_when_mongo_is_not_configured(monkeypatch):
    monkeypatch.setattr(snapshots, "MONGO_HOST", None)
    monkeypatch.setattr(snapshots, "_collection", refuse)

    snapshots.record("Paris", "paris", BODY)  # must not even try

    assert snapshots.recent() is None


def test_a_mongo_error_never_escapes_and_resets_the_index_flag(monkeypatch):
    monkeypatch.setattr(snapshots, "MONGO_HOST", "mongo.invalid")
    monkeypatch.setattr(snapshots, "_collection", refuse)
    monkeypatch.setitem(snapshots._state, "ready", True)

    snapshots.record("Paris", "paris", BODY)  # no exception

    assert snapshots._state["ready"] is False  # indexes are recreated next time
    assert snapshots.recent() is None


def test_recent_returns_newest_first_for_one_city(collection):
    def make(city_key, hour):
        return {
            "city": city_key.title(),
            "city_key": city_key,
            "fetched_at": datetime(2026, 10, 21, hour, tzinfo=UTC),
        }

    collection.documents += [make("paris", 9), make("london", 10), make("paris", 11)]

    found = snapshots.recent("paris")

    assert [d["fetched_at"] for d in found] == [
        "2026-10-21T11:00:00+00:00",
        "2026-10-21T09:00:00+00:00",
    ]


def test_the_endpoint_returns_the_snapshots(monkeypatch):
    rows = [{"city": "Paris", "fetched_at": "2026-10-21T11:00:00+00:00"}]
    asked = []
    monkeypatch.setattr(
        snapshots, "recent", lambda city_key=None: asked.append(city_key) or rows
    )

    response = app.test_client().get("/api/snapshots", query_string={"city": " Paris "})

    assert response.status_code == 200
    assert response.json == {"snapshots": rows}
    assert asked == ["paris"]  # trimmed and lower-cased, like the cache key


def test_the_endpoint_says_503_when_mongo_is_unavailable(monkeypatch):
    monkeypatch.setattr(snapshots, "recent", lambda city_key=None: None)

    response = app.test_client().get("/api/snapshots")

    assert response.status_code == 503
    assert "error" in response.json
