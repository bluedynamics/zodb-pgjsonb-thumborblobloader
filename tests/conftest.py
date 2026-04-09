"""Shared test configuration for zodb-pgjsonb-thumborblobloader tests."""

from __future__ import annotations

import os
import psycopg
import pytest


def _get_test_dsn():
    """Resolve PostgreSQL DSN: env var → local Docker → testcontainers."""
    _DEFAULT = "dbname=zodb_test user=zodb password=zodb host=localhost port=5433"
    env_dsn = os.environ.get("ZODB_TEST_DSN")
    if env_dsn:
        return env_dsn
    try:
        conn = psycopg.connect(_DEFAULT, connect_timeout=2)
        conn.close()
        return _DEFAULT
    except Exception:
        pass
    from testcontainers.postgres import PostgresContainer

    import atexit

    container = PostgresContainer(
        image="postgres:17", username="zodb", password="zodb", dbname="zodb_test"
    )
    container.start()
    atexit.register(container.stop)
    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return f"dbname=zodb_test user=zodb password=zodb host={host} port={port}"


DSN = _get_test_dsn()

BLOB_STATE_DDL = """\
CREATE TABLE IF NOT EXISTS blob_state (
    zoid        BIGINT NOT NULL,
    tid         BIGINT NOT NULL,
    blob_size   BIGINT NOT NULL,
    data        BYTEA,
    s3_key      TEXT,
    PRIMARY KEY (zoid, tid)
);
"""


def _ensure_blob_state(conn):
    """Create blob_state table if it doesn't exist (test-only setup)."""
    conn.execute(BLOB_STATE_DDL)
    conn.commit()


def _clean_blob_state(conn):
    """Truncate blob_state for test isolation."""
    conn.execute("TRUNCATE blob_state")
    conn.commit()


@pytest.fixture
def pg_conn():
    """Sync psycopg connection with fresh blob_state table."""
    conn = psycopg.connect(DSN)
    _ensure_blob_state(conn)
    _clean_blob_state(conn)
    yield conn
    conn.close()


def insert_pg_blob(conn, zoid, tid, data):
    """Insert a blob row with inline PG bytea data."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO blob_state (zoid, tid, blob_size, data) VALUES (%s, %s, %s, %s)",
            (zoid, tid, len(data), data),
        )
    conn.commit()


def insert_s3_blob(conn, zoid, tid, s3_key, blob_size):
    """Insert a blob row with S3 reference (no inline data)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO blob_state (zoid, tid, blob_size, s3_key) VALUES (%s, %s, %s, %s)",
            (zoid, tid, blob_size, s3_key),
        )
    conn.commit()


class MockConfig:
    """Minimal mock of Thumbor config."""

    def __init__(self, **kwargs):
        self._values = kwargs

    def get(self, key, default=None):
        return self._values.get(key, default)

    def __getattr__(self, name):
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name) from None


class MockContext:
    """Minimal mock of Thumbor context."""

    def __init__(self, **config_kwargs):
        self.config = MockConfig(**config_kwargs)


def make_context(**overrides):
    """Create a MockContext with sensible test defaults."""
    defaults = {
        "PGTHUMBOR_DSN": DSN,
        "PGTHUMBOR_POOL_MIN_SIZE": 1,
        "PGTHUMBOR_POOL_MAX_SIZE": 2,
        "PGTHUMBOR_CACHE_DIR": "",
        "PGTHUMBOR_CACHE_MAX_SIZE": 0,
        "PGTHUMBOR_S3_BUCKET": "",
        "PGTHUMBOR_S3_REGION": "",
        "PGTHUMBOR_S3_ENDPOINT": "",
    }
    defaults.update(overrides)
    return MockContext(**defaults)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset module-level singletons between tests."""
    yield
    from zodb_pgjsonb_thumborblobloader import pool as pool_mod

    # Sync teardown — just discard refs; pool GC handles close
    if pool_mod._pool is not None:
        import contextlib

        with contextlib.suppress(Exception):
            pool_mod._pool.close(timeout=0)
    pool_mod._pool = None
    pool_mod._pool_dsn = None
    pool_mod._schema_verified = False

    import zodb_pgjsonb_thumborblobloader.loader as loader_mod

    loader_mod._cache_instance = None
