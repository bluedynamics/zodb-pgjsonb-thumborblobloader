"""Async connection pool management for the Thumbor blob loader.

Provides a module-level singleton AsyncConnectionPool, lazily initialized
from Thumbor config on first use.  Includes schema verification to ensure
the blob_state table (owned by zodb-pgjsonb) exists.
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

import logging


logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_pool_dsn: str | None = None
_schema_verified: bool = False


class SchemaError(Exception):
    """Raised when the expected database schema is not found."""


async def verify_schema(pool: AsyncConnectionPool) -> None:
    """Verify that blob_state table exists.

    Raises SchemaError if the table is missing.
    """
    global _schema_verified
    if _schema_verified:
        return
    async with pool.connection() as conn:
        result = await conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'blob_state'",
        )
        row = await result.fetchone()
    if row is None:
        raise SchemaError(
            "blob_state table not found — is zodb-pgjsonb schema installed?"
        )
    _schema_verified = True
    logger.info("Schema verified: blob_state table exists")


async def get_pool(dsn: str, min_size: int = 1, max_size: int = 4) -> AsyncConnectionPool:
    """Get or create the module-level async connection pool.

    The pool is created on first call and reused for subsequent calls.
    If the DSN changes, the old pool is closed and a new one is created.
    Schema verification runs once after pool creation.
    """
    global _pool, _pool_dsn, _schema_verified

    if _pool is not None and _pool_dsn == dsn:
        await verify_schema(_pool)
        return _pool

    if _pool is not None:
        await _pool.close()
        _schema_verified = False
        logger.info("Closed old pool (DSN changed)")

    _pool = AsyncConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        open=False,
    )
    await _pool.open()
    _pool_dsn = dsn
    logger.info("Opened async connection pool: min=%d, max=%d", min_size, max_size)

    await verify_schema(_pool)
    return _pool


async def close_pool() -> None:
    """Close the module-level pool.  For shutdown/testing."""
    global _pool, _pool_dsn, _schema_verified
    if _pool is not None:
        await _pool.close()
        _pool = None
        _pool_dsn = None
        _schema_verified = False
