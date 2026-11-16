import json
import os

import redis

REDIS_HOST = os.getenv("REDIS_HOST")  # not set -> cache disabled
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))

_client = None
if REDIS_HOST:
    _client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
        decode_responses=True,
    )


def get(key):
    if _client is None:
        return None
    try:
        raw = _client.get(key)
        return json.loads(raw) if raw else None
    except redis.RedisError:
        return None


def put(key, value):
    if _client is None:
        return
    try:
        _client.set(key, json.dumps(value), ex=TTL_SECONDS)
    except redis.RedisError:
        pass
