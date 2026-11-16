"""The stored weather snapshots (MongoDB)."""

from flask import Blueprint, jsonify, request

from app import snapshots

bp = Blueprint("snapshots", __name__)


@bp.route("/api/snapshots", methods=["GET"])
def list_snapshots():
    city_key = request.args.get("city", "").strip().lower() or None
    found = snapshots.recent(city_key)
    if found is None:
        return jsonify({"error": "snapshots are unavailable"}), 503
    return jsonify({"snapshots": found}), 200
