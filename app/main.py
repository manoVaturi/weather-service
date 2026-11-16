"""Wires the app together; the features live in app/routes/."""

from flask import Flask

from app.monitoring import metrics
from app.routes import health, pages, snapshots, users, weather

app = Flask(__name__, static_folder="static", template_folder="templates")

metrics.init_app(app)  # also exposes /metrics for Prometheus

for module in (pages, health, weather, users, snapshots):
    app.register_blueprint(module.bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
