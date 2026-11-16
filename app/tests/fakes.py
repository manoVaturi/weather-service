"""Stand-ins for the tests: a fake Redis, database connection and Open-Meteo."""

import redis

from app import db


class FakeRedis:
    """Just enough of redis.Redis for cache.py: get and set."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value


class BrokenRedis:
    """A Redis that is down: every call raises, like a dead connection."""

    def get(self, key):
        raise redis.ConnectionError("redis is down")

    def set(self, key, value, ex=None):
        raise redis.ConnectionError("redis is down")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeConnection:
    """A database connection that records what it is asked to run and answers from a script."""

    def __init__(self, rows=()):
        self.calls = []
        self.rows = list(rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return self.rows


class FakeCursor:
    """The chain find().sort().limit() that pymongo returns."""

    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, key, direction):
        self.documents.sort(key=lambda d: d[key], reverse=direction == -1)
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    """Just enough of a pymongo collection: indexes, insert_one and find."""

    def __init__(self):
        self.documents = []
        self.indexes = []

    def create_index(self, keys, **options):
        self.indexes.append((keys, options))

    def insert_one(self, document):
        self.documents.append(dict(document))

    def find(self, query, projection=None):
        matching = [
            dict(d)
            for d in self.documents
            if all(d.get(k) == v for k, v in query.items())
        ]
        return FakeCursor(matching)


def fake_open_meteo(calls):
    """Stands in for requests.get and records every URL the app asks for."""

    def fake_get(url, timeout):
        calls.append(url)
        if "geocoding" in url:
            return FakeResponse(
                {
                    "results": [
                        {
                            "name": "Paris",
                            "country": "France",
                            "latitude": 48.85,
                            "longitude": 2.35,
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "current": {"temperature_2m": 12.3},
                "daily": {"time": ["2026-10-20"]},
            }
        )

    return fake_get


def unavailable(*args, **kwargs):
    raise db.DatabaseUnavailable("database is down")
