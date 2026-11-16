"""The weather lookup with its cache, and the search history."""

import psycopg
import requests
from pymongo.errors import ServerSelectionTimeoutError

from app import cache, db, snapshots
from app.main import app
from app.routes import weather
from app.tests.fakes import (
    BrokenRedis,
    FakeRedis,
    FakeResponse,
    fake_open_meteo,
)


def test_second_lookup_comes_from_the_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(cache, "_client", FakeRedis())
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo(calls))
    client = app.test_client()

    first = client.get("/api/weather", query_string={"city": "Paris"})
    second = client.get("/api/weather", query_string={"city": " paris "})

    assert first.status_code == second.status_code == 200
    assert first.json == second.json
    assert len(calls) == 2  # geocoding + forecast, once only


def test_unknown_city_is_not_cached(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "_client", fake)
    monkeypatch.setattr(weather.requests, "get", lambda url, timeout: FakeResponse({}))

    response = app.test_client().get("/api/weather", query_string={"city": "Nowhere"})

    assert response.status_code == 404
    assert fake.data == {}


def test_broken_redis_does_not_break_the_app(monkeypatch):
    calls = []
    monkeypatch.setattr(cache, "_client", BrokenRedis())
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo(calls))

    response = app.test_client().get("/api/weather", query_string={"city": "Paris"})

    assert response.status_code == 200
    assert response.json["location"] == "Paris, France"


def test_no_redis_configured_means_no_caching(monkeypatch):
    calls = []
    monkeypatch.setattr(cache, "_client", None)
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo(calls))
    client = app.test_client()

    client.get("/api/weather", query_string={"city": "Paris"})
    client.get("/api/weather", query_string={"city": "Paris"})

    assert len(calls) == 4  # nothing was cached


def test_every_lookup_is_recorded_in_the_history(monkeypatch):
    recorded = []
    monkeypatch.setattr(cache, "_client", FakeRedis())
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo([]))
    monkeypatch.setattr(db, "record_search", recorded.append)
    client = app.test_client()

    client.get("/api/weather", query_string={"city": "paris"})  # a miss
    client.get("/api/weather", query_string={"city": "paris"})  # a cache hit

    assert recorded == ["Paris", "Paris"]  # the geocoder's name, in both paths


def test_history_endpoint_returns_the_rows(monkeypatch):
    rows = [
        {
            "city": "Paris",
            "lookups": 2,
            "last_searched": "2026-10-21T10:00:00+00:00",
        }
    ]
    monkeypatch.setattr(db, "recent_searches", lambda: rows)

    response = app.test_client().get("/api/history")

    assert response.status_code == 200
    assert response.json == {"searches": rows}


def test_history_says_503_when_the_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(db, "recent_searches", lambda: None)

    response = app.test_client().get("/api/history")

    assert response.status_code == 503
    assert "error" in response.json


def test_a_dead_database_does_not_break_a_lookup(monkeypatch):
    def refuse():
        raise psycopg.OperationalError("database is down")

    monkeypatch.setattr(cache, "_client", None)
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo([]))
    monkeypatch.setattr(db, "DB_HOST", "postgres.invalid")
    monkeypatch.setattr(db, "_connect", refuse)
    monkeypatch.setitem(db._state, "ready", True)

    response = app.test_client().get("/api/weather", query_string={"city": "Paris"})

    assert response.status_code == 200
    assert db._state["ready"] is False  # so the table is recreated next time


def test_only_a_real_fetch_makes_a_snapshot(monkeypatch):
    stored = []
    monkeypatch.setattr(cache, "_client", FakeRedis())
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo([]))
    monkeypatch.setattr(
        snapshots, "record", lambda city, key, body: stored.append((city, key))
    )
    client = app.test_client()

    client.get("/api/weather", query_string={"city": " Paris "})  # a miss
    client.get("/api/weather", query_string={"city": "paris"})  # a cache hit

    assert stored == [("Paris", "paris")]  # one snapshot, keyed by the geocoder's name


def test_a_dead_mongo_does_not_break_a_lookup(monkeypatch):
    def refuse():
        raise ServerSelectionTimeoutError("mongo is down")

    monkeypatch.setattr(cache, "_client", None)
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo([]))
    monkeypatch.setattr(snapshots, "MONGO_HOST", "mongo.invalid")
    monkeypatch.setattr(snapshots, "_collection", refuse)

    response = app.test_client().get("/api/weather", query_string={"city": "Paris"})

    assert response.status_code == 200


def test_a_snapshot_is_filed_under_the_name_the_geocoder_returned(monkeypatch):
    stored = []
    monkeypatch.setattr(cache, "_client", None)
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo([]))
    monkeypatch.setattr(
        snapshots, "record", lambda city, key, body: stored.append((city, key))
    )

    app.test_client().get("/api/weather", query_string={"city": "pari"})

    assert stored == [("Paris", "paris")]  # not "pari": one history per place


def test_the_city_is_url_encoded_in_the_geocoding_request(monkeypatch):
    calls = []
    monkeypatch.setattr(cache, "_client", None)
    monkeypatch.setattr(weather.requests, "get", fake_open_meteo(calls))

    app.test_client().get("/api/weather", query_string={"city": "Rio & Co/é"})

    assert "name=Rio%20%26%20Co%2F%C3%A9&" in calls[0]


def test_geocoding_down_gives_503_and_caches_nothing(monkeypatch):
    fake = FakeRedis()

    def down(url, timeout):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(cache, "_client", fake)
    monkeypatch.setattr(weather.requests, "get", down)

    response = app.test_client().get("/api/weather", query_string={"city": "Paris"})

    assert response.status_code == 503
    assert fake.data == {}


def test_forecast_down_gives_503_and_records_no_search(monkeypatch):
    fake = FakeRedis()
    searches = []

    def geocoding_only(url, timeout):
        if "geocoding" in url:
            return FakeResponse(
                {"results": [{"name": "Paris", "latitude": 1, "longitude": 2}]}
            )
        raise requests.Timeout("too slow")

    monkeypatch.setattr(cache, "_client", fake)
    monkeypatch.setattr(weather.requests, "get", geocoding_only)
    monkeypatch.setattr(db, "record_search", searches.append)

    response = app.test_client().get("/api/weather", query_string={"city": "Paris"})

    assert response.status_code == 503
    assert fake.data == {}
    assert searches == []  # a failed lookup is not a search
