import os

import psycopg

DB_HOST = os.getenv("DB_HOST")  # not set -> the history feature is off
DB_NAME = os.getenv("DB_NAME", "weatherapp")
DB_USER = os.getenv("DB_USER", "weatherapp")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id          BIGSERIAL PRIMARY KEY,
    city        TEXT NOT NULL,
    searched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS searches_city_idx ON searches (city);

CREATE TABLE IF NOT EXISTS users (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE CHECK (name ~ '^[A-Za-z0-9_-]{1,40}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS favourites (
    user_id  BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    city     TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, city)
);
"""


_state = {"ready": False}


def _connect():
    return psycopg.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=1,
    )


def _prepare(conn):
    """Create the table on first use. The database is rebuilt every night,
    so the app has to be able to rebuild its own schema."""
    if not _state["ready"]:
        conn.execute(SCHEMA)
        _state["ready"] = True


def record_search(city):
    """Write one row per lookup. A database problem never breaks a lookup."""
    if not DB_HOST:
        return
    try:
        with _connect() as conn:
            _prepare(conn)
            conn.execute("INSERT INTO searches (city) VALUES (%s)", (city,))
    except psycopg.Error:
        _state["ready"] = (
            False  # the database may have been rebuilt: recreate the table next time
        )


def recent_searches(limit=10):
    """One row per city, most recent first. None means 'database unavailable'."""
    if not DB_HOST:
        return None
    try:
        with _connect() as conn:
            _prepare(conn)
            rows = conn.execute(
                "SELECT city, count(*), max(searched_at) FROM searches "
                "GROUP BY city ORDER BY max(searched_at) DESC LIMIT %s",
                (limit,),
            ).fetchall()
    except psycopg.Error:
        _state["ready"] = False
        return None
    return [
        {"city": c, "lookups": n, "last_searched": t.isoformat()} for c, n, t in rows
    ]


class DatabaseUnavailable(Exception):
    """The database is not configured or cannot be reached."""


def _query(work):
    """Run work(conn) in one transaction and return what it returns."""
    if not DB_HOST:
        raise DatabaseUnavailable("not configured")
    try:
        with _connect() as conn:
            _prepare(conn)
            return work(conn)
    except psycopg.Error as err:
        _state["ready"] = (
            False  # the database may have been rebuilt: recreate the tables next time
        )
        raise DatabaseUnavailable(str(err)) from err


def get_or_create_user(name):
    """Return {'name', 'created'}; created is False when the user already existed."""

    def work(conn):
        row = conn.execute(
            "INSERT INTO users (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING id",
            (name,),
        ).fetchone()
        return {"name": name, "created": row is not None}

    return _query(work)


def list_favourites(name):
    """The user's cities, newest first. None means there is no such user."""

    def work(conn):
        rows = conn.execute(
            "SELECT f.city FROM users u LEFT JOIN favourites f ON f.user_id = u.id "
            "WHERE u.name = %s ORDER BY f.added_at DESC",
            (name,),
        ).fetchall()
        if not rows:
            return None
        return [city for (city,) in rows if city is not None]

    return _query(work)


def add_favourite(name, city):
    """True when stored (or already there), None when there is no such user."""

    def work(conn):
        user = conn.execute("SELECT id FROM users WHERE name = %s", (name,)).fetchone()
        if user is None:
            return None
        conn.execute(
            "INSERT INTO favourites (user_id, city) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user[0], city),
        )
        return True

    return _query(work)


def remove_favourite(name, city):
    """True when the user exists (the favourite is gone either way), None when there is no such user."""

    def work(conn):
        user = conn.execute("SELECT id FROM users WHERE name = %s", (name,)).fetchone()
        if user is None:
            return None
        conn.execute(
            "DELETE FROM favourites WHERE user_id = %s AND city = %s",
            (user[0], city),
        )
        return True

    return _query(work)
