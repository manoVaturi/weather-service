"""Looking up the weather (with the Redis cache) and the search history."""

from urllib.parse import quote

import requests
from flask import Blueprint, jsonify, request

from app import cache, db, snapshots
from app.monitoring import CACHE_HITS, CACHE_MISSES, CITY_LOOKUPS

bp = Blueprint("weather", __name__)

UPSTREAM_DOWN = "the weather service is unavailable, try again later"


def fetch_json(url):
    """The JSON answer of Open-Meteo, or None when it cannot be reached or answers nonsense."""
    try:
        return requests.get(url, timeout=5).json()
    except (requests.RequestException, ValueError):
        return None


@bp.route("/api/weather", methods=["GET"])
def get_weather():
    city = request.args.get("city", "London")

    key = "weather:" + city.strip().lower()

    cached = cache.get(key)
    if cached:
        CACHE_HITS.inc()
        CITY_LOOKUPS.labels(city=cached["city"]).inc()
        db.record_search(cached["city"])
        return jsonify(cached["body"]), 200

    CACHE_MISSES.inc()

    # 1. Geocoding API to get latitude, longitude, and country info
    geo_url = (
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={quote(city, safe='')}&count=5&language=en&format=json"
    )
    geo_res = fetch_json(geo_url)
    if geo_res is None:
        return jsonify({"error": UPSTREAM_DOWN}), 503

    if not geo_res.get("results"):
        return jsonify({"error": f"City '{city}' not found"}), 404

    location = geo_res["results"][0]

    lat = location["latitude"]
    lon = location["longitude"]
    loc_name = f"{location.get('name')}, {location.get('country', '')}"

    # 2. Weather Forecast API (Current conditions + 7-day daily forecast)
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min"
        f"&timezone=auto"
    )
    weather_res = fetch_json(weather_url)
    if weather_res is None:
        return jsonify({"error": UPSTREAM_DOWN}), 503

    CITY_LOOKUPS.labels(city=location.get("name", "unknown")).inc()
    db.record_search(location.get("name", "unknown"))

    body = {
        "location": loc_name,
        "current": weather_res.get("current"),
        "daily": weather_res.get("daily"),
        "db_backend": db.DB_HOST or "not-configured",
    }
    cache.put(key, {"city": location.get("name", "unknown"), "body": body})
    # Only a real fetch makes a snapshot, filed under the geocoder's name
    name = location.get("name", "unknown")
    snapshots.record(name, name.strip().lower(), body)
    return jsonify(body), 200


@bp.route("/api/history", methods=["GET"])
def history():
    searches = db.recent_searches()
    if searches is None:
        return jsonify({"error": "history is unavailable"}), 503
    return jsonify({"searches": searches}), 200
