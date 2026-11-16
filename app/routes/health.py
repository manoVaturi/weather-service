"""The health check used by the Kubernetes probes and the load balancer."""

import os

from flask import Blueprint, jsonify

from app import db, snapshots
from app.monitoring import metrics

bp = Blueprint("health", __name__)


@bp.route("/healthz", methods=["GET"])
@metrics.do_not_track()
def healthz():
    return jsonify(
        {
            "status": "healthy",
            # the git SHA on dev, the release version on production
            "version": os.getenv("APP_VERSION", "unknown"),
            "db_configured": bool(db.DB_HOST),
            "mongo_configured": bool(snapshots.MONGO_HOST),
        }
    ), 200
