"""Prometheus metrics: the exporter and the counters the routes update."""

import os

from prometheus_client import Counter
from prometheus_flask_exporter import PrometheusMetrics

# Created without an app so routes can use it; main.py attaches it with init_app()
metrics = PrometheusMetrics.for_app_factory()
metrics.info(
    "weatherapp_info",
    "WeatherApp Info",
    version=os.getenv("APP_VERSION", "1.0.0"),
)

CITY_LOOKUPS = Counter(
    "weather_city_lookups_total",
    "Successful weather lookups per city",
    ["city"],
)
CACHE_HITS = Counter(
    "weather_cache_hits_total",
    "Weather lookups served from Redis",
)
CACHE_MISSES = Counter(
    "weather_cache_misses_total", "Weather lookups that needed Open-Meteo"
)
