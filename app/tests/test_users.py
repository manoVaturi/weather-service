"""The users and favourites endpoints."""

import pytest

from app import db
from app.main import app
from app.tests.fakes import unavailable


def test_creating_a_user_returns_201_then_200(monkeypatch):
    results = iter(
        [{"name": "mano", "created": True}, {"name": "mano", "created": False}]
    )
    monkeypatch.setattr(db, "get_or_create_user", lambda name: next(results))
    client = app.test_client()

    first = client.post("/api/users", json={"name": "mano"})
    second = client.post("/api/users", json={"name": "mano"})

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json == {"name": "mano"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "has space"},
        {"name": "a" * 41},
        {"name": "semi;colon"},
        {"name": "mano\n"},
        {"name": 5},
    ],
)
def test_bad_user_names_are_refused_before_the_database_is_asked(monkeypatch, payload):
    monkeypatch.setattr(
        db, "get_or_create_user", unavailable
    )  # reaching it would give 503, not 400

    response = app.test_client().post("/api/users", json=payload)

    assert response.status_code == 400


def test_a_body_that_is_not_json_is_a_400_not_a_crash():
    response = app.test_client().post(
        "/api/users", data="not json", content_type="text/plain"
    )

    assert response.status_code == 400


def test_user_endpoints_say_503_when_the_database_is_down(monkeypatch):
    monkeypatch.setattr(db, "get_or_create_user", unavailable)
    monkeypatch.setattr(db, "list_favourites", unavailable)
    monkeypatch.setattr(db, "add_favourite", unavailable)
    client = app.test_client()

    assert client.post("/api/users", json={"name": "mano"}).status_code == 503
    assert client.get("/api/users/mano/favourites").status_code == 503
    assert client.put("/api/users/mano/favourites/Paris").status_code == 503


def test_listing_favourites(monkeypatch):
    monkeypatch.setattr(
        db,
        "list_favourites",
        lambda name: ["Tokyo", "Paris"] if name == "mano" else None,
    )
    client = app.test_client()

    found = client.get("/api/users/mano/favourites")
    missing = client.get("/api/users/nobody/favourites")

    assert found.status_code == 200
    assert found.json == {"name": "mano", "favourites": ["Tokyo", "Paris"]}
    assert missing.status_code == 404


def test_a_favourite_is_cleaned_up_before_it_is_stored(monkeypatch):
    stored = []
    monkeypatch.setattr(
        db,
        "add_favourite",
        lambda name, city: stored.append((name, city)) or True,
    )

    response = app.test_client().put("/api/users/mano/favourites/%20new%20york%20")

    assert response.status_code == 200
    assert stored == [("mano", "New York")]
    assert response.json == {"name": "mano", "city": "New York"}


def test_changing_the_favourites_of_an_unknown_user_is_a_404(monkeypatch):
    monkeypatch.setattr(db, "add_favourite", lambda name, city: None)
    monkeypatch.setattr(db, "remove_favourite", lambda name, city: None)
    client = app.test_client()

    assert client.put("/api/users/ghost/favourites/Paris").status_code == 404
    assert client.delete("/api/users/ghost/favourites/Paris").status_code == 404


def test_an_absurdly_long_city_is_refused(monkeypatch):
    monkeypatch.setattr(db, "add_favourite", unavailable)  # must not be reached

    response = app.test_client().put("/api/users/mano/favourites/" + "x" * 81)

    assert response.status_code == 400
