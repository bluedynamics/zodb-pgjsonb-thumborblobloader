"""Tests for the Thumbor loader — PG bytea path."""

from __future__ import annotations

from tests.conftest import DSN
from tests.conftest import insert_pg_blob
from tests.conftest import make_context

import psycopg
import pytest


pytestmark = pytest.mark.skipif(not DSN, reason="ZODB_TEST_DSN not set")


class TestLoadPGBlob:
    """Test loading blobs from PG bytea column."""

    async def test_load_existing_blob(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        blob_data = b"Hello, thumbor!"
        insert_pg_blob(pg_conn, zoid=0x42, tid=0xFF, data=blob_data)

        result = await load(make_context(), "42/ff")

        assert result.successful is True
        assert result.buffer == blob_data
        assert result.error is None

    async def test_load_nonexistent_blob(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        result = await load(make_context(), "9999/9999")

        assert result.successful is False
        assert result.error == "not_found"
        assert result.buffer is None

    async def test_load_invalid_path(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        result = await load(make_context(), "invalid-path")

        assert result.successful is False
        assert result.error == "bad_request"

    async def test_load_large_blob(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        blob_data = b"X" * (1024 * 1024 + 1)
        insert_pg_blob(pg_conn, zoid=0x100, tid=0x200, data=blob_data)

        result = await load(make_context(), "100/200")

        assert result.successful is True
        assert result.buffer == blob_data

    async def test_load_metadata_includes_size(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        blob_data = b"metadata test"
        insert_pg_blob(pg_conn, zoid=0x50, tid=0x60, data=blob_data)

        result = await load(make_context(), "50/60")

        assert result.metadata["size"] == len(blob_data)

    async def test_load_with_full_hex_padding(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        blob_data = b"padded hex"
        insert_pg_blob(pg_conn, zoid=0x42, tid=0xFF, data=blob_data)

        result = await load(make_context(), "0000000000000042/00000000000000ff")

        assert result.successful is True
        assert result.buffer == blob_data

    async def test_load_missing_table(self):
        """When blob_state table doesn't exist, return clear error."""
        from zodb_pgjsonb_thumborblobloader.loader import load

        # Drop the table
        conn = psycopg.connect(DSN)
        conn.execute("DROP TABLE IF EXISTS blob_state CASCADE")
        conn.commit()
        conn.close()

        result = await load(make_context(), "42/ff")

        assert result.successful is False
        assert result.error == "upstream"
        assert "blob_state" in result.extras.get("detail", "")


class TestLoaderEdgeCases:
    """Test error-handling paths in the loader."""

    async def test_load_dsn_not_configured(self):
        from zodb_pgjsonb_thumborblobloader.loader import load

        ctx = make_context(PGTHUMBOR_DSN="")
        result = await load(ctx, "42/ff")

        assert result.successful is False
        assert result.error == "upstream"
        assert "DSN" in result.extras.get("detail", "")

    async def test_load_no_data_no_s3_key(self, pg_conn):
        """Row exists but has neither data nor s3_key."""
        from zodb_pgjsonb_thumborblobloader.loader import load

        with pg_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO blob_state (zoid, tid, blob_size) VALUES (%s, %s, %s)",
                (0x77, 0x88, 0),
            )
        pg_conn.commit()

        result = await load(make_context(), "77/88")

        assert result.successful is False
        assert result.error == "upstream"


class TestPoolLifecycle:
    """Test pool management functions."""

    async def test_close_pool(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.pool import close_pool
        from zodb_pgjsonb_thumborblobloader.pool import get_pool

        pool = await get_pool(DSN, min_size=1, max_size=2)
        assert pool is not None
        await close_pool()

        from zodb_pgjsonb_thumborblobloader import pool as pool_mod

        assert pool_mod._pool is None

    async def test_pool_dsn_change(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.pool import get_pool

        pool1 = await get_pool(DSN, min_size=1, max_size=2)
        # Same DSN returns same pool
        pool2 = await get_pool(DSN, min_size=1, max_size=2)
        assert pool2 is pool1


class TestValidate:
    """Test the optional validate function."""

    def test_validate_valid_path(self):
        from zodb_pgjsonb_thumborblobloader.loader import validate

        assert validate(None, "42/ff") is True

    def test_validate_invalid_path(self):
        from zodb_pgjsonb_thumborblobloader.loader import validate

        assert validate(None, "not-a-path") is False

    def test_validate_empty(self):
        from zodb_pgjsonb_thumborblobloader.loader import validate

        assert validate(None, "") is False
