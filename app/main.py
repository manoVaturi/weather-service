import os

import requests
from flask import Flask, jsonify, render_template, request
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__, static_folder="static", template_folder="templates")

# Automatically exposes /metrics for Prometheus
metrics = PrometheusMetrics(app)
metrics.info(
    "weatherapp_info",
    "WeatherApp Info",
    version=os.getenv("APP_VERSION", "1.0.0"),
)

DB_HOST = os.getenv("DB_HOST", "not-configured")


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/healthz", methods=["GET"])
@metrics.do_not_track()
def healthz():
    return jsonify(
        {"status": "healthy", "db_configured": DB_HOST != "not-configured"}
    ), 200


@app.route("/api/weather", methods=["GET"])
def get_weather():
    city = request.args.get("city", "London")

    # 1. Geocoding API to get latitude, longitude, and country info
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=5&language=en&format=json"
    geo_res = requests.get(geo_url, timeout=5).json()

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
    weather_res = requests.get(weather_url, timeout=5).json()

    return jsonify(
        {
            "location": loc_name,
            "current": weather_res.get("current"),
            "daily": weather_res.get("daily"),
            "db_backend": DB_HOST,
        }
    ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
