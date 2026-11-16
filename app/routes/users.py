"""Light users (just a name, no password) and their favourite cities."""

import re

from flask import Blueprint, jsonify, request

from app import db

bp = Blueprint("users", __name__)

NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")


def _clean_city(raw):
    city = raw.strip().title()
    return city if 0 < len(city) <= 80 else None


@bp.route("/api/users", methods=["POST"])
def create_user():
    body = request.get_json(silent=True)
    name = body.get("name") if isinstance(body, dict) else None
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        return jsonify({"error": "name must be 1 to 40 letters, digits, - or _"}), 400
    try:
        user = db.get_or_create_user(name)
    except db.DatabaseUnavailable:
        return jsonify({"error": "users are unavailable"}), 503
    return jsonify({"name": user["name"]}), (201 if user["created"] else 200)


@bp.route("/api/users/<name>/favourites", methods=["GET"])
def get_favourites(name):
    if not NAME_RE.fullmatch(name):
        return jsonify({"error": "invalid name"}), 400
    try:
        cities = db.list_favourites(name)
    except db.DatabaseUnavailable:
        return jsonify({"error": "favourites are unavailable"}), 503
    if cities is None:
        return jsonify({"error": f"no such user '{name}'"}), 404
    return jsonify({"name": name, "favourites": cities}), 200


@bp.route("/api/users/<name>/favourites/<city>", methods=["PUT", "DELETE"])
def change_favourite(name, city):
    clean = _clean_city(city)
    if not NAME_RE.fullmatch(name) or clean is None:
        return jsonify({"error": "invalid name or city"}), 400
    action = db.add_favourite if request.method == "PUT" else db.remove_favourite
    try:
        result = action(name, clean)
    except db.DatabaseUnavailable:
        return jsonify({"error": "favourites are unavailable"}), 503
    if result is None:
        return jsonify({"error": f"no such user '{name}'"}), 404
    return jsonify({"name": name, "city": clean}), 200
