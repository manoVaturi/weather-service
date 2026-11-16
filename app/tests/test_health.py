"""The health check."""

from app.main import app


def test_healthz_reports_the_version_it_runs(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.2.0")

    response = app.test_client().get("/healthz")

    assert response.json["version"] == "1.2.0"


def test_healthz_without_a_version_says_unknown(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)

    assert app.test_client().get("/healthz").json["version"] == "unknown"


def test_healthz():
    client = app.test_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"
    assert "mongo_configured" in response.json
