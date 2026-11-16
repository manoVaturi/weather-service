"""MongoDB: a snapshot of every real fetch from Open-Meteo, deleted by Mongo itself when it gets old."""

import os
from datetime import UTC, datetime

import pymongo
from pymongo.errors import PyMongoError

MONGO_HOST = os.getenv("MONGO_HOST")  # not set -> the snapshot feature is off
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "weatherapp")
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
TTL_SECONDS = int(os.getenv("SNAPSHOT_TTL_SECONDS", "86400"))

_state = {"ready": False, "client": None}


def _collection():
    # The client connects lazily, so creating it never blocks the app from starting.
    if _state["client"] is None:
        _state["client"] = pymongo.MongoClient(
            host=MONGO_HOST,
            port=MONGO_PORT,
            username=MONGO_USER,
            password=MONGO_PASSWORD,
            authSource="admin",  # the root user lives in the admin database
            tz_aware=True,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=1000,
        )
    return _state["client"][MONGO_DB]["snapshots"]


def _prepare(collection):
    """Create the indexes on first use. The database is rebuilt every night,
    so the app has to be able to rebuild its own collection."""
    if not _state["ready"]:
        # The TTL index: Mongo deletes a document TTL_SECONDS after its fetched_at.
        collection.create_index("fetched_at", expireAfterSeconds=TTL_SECONDS)
        collection.create_index([("city_key", 1), ("fetched_at", -1)])
        _state["ready"] = True


def record(city, city_key, body):
    """Store one snapshot per real fetch. A Mongo problem never breaks a lookup."""
    if not MONGO_HOST:
        return
    try:
        collection = _collection()
        _prepare(collection)
        collection.insert_one(
            {
                "city": city,
                "city_key": city_key,
                "location": body["location"],
                "current": body["current"],
                "daily": body["daily"],
                "fetched_at": datetime.now(UTC),
            }
        )
    except PyMongoError:
        _state["ready"] = False


def recent(city_key=None, limit=20):
    """Newest snapshots first, optionally for one city. None means Mongo is unavailable."""
    if not MONGO_HOST:
        return None
    try:
        collection = _collection()
        _prepare(collection)
        query = {"city_key": city_key} if city_key else {}
        cursor = (
            collection.find(query, {"_id": 0, "city_key": 0})
            .sort("fetched_at", -1)
            .limit(limit)
        )
        documents = list(cursor)
    except PyMongoError:
        _state["ready"] = False
        return None
    for document in documents:
        document["fetched_at"] = document["fetched_at"].isoformat()
    return documents
