"""End-to-end integration tests for the Thumbor loader."""

from __future__ import annotations

from moto import mock_aws
from tests.conftest import DSN
from tests.conftest import insert_pg_blob
from tests.conftest import insert_s3_blob
from tests.conftest import make_context

import boto3
import pytest


S3_BUCKET = "test-thumbor-blobs"
S3_REGION = "us-east-1"

pytestmark = pytest.mark.skipif(not DSN, reason="ZODB_TEST_DSN not set")


@pytest.fixture(autouse=True)
def _reset_s3_client():
    """Reset module-level S3 client between tests."""
    yield
    from zodb_pgjsonb_thumborblobloader import s3 as s3_mod

    s3_mod._s3_client = None
    s3_mod._s3_config = None


class TestEndToEnd:
    """Full pipeline: insert blob -> load via Thumbor loader -> verify."""

    async def test_pg_blob_end_to_end(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        blob_data = b"PNG\x89\x50\x4e\x47\x0d\x0a\x1a\x0a" + b"\x00" * 100
        insert_pg_blob(pg_conn, zoid=0xDEAD, tid=0xBEEF, data=blob_data)

        result = await load(make_context(), "dead/beef")

        assert result.successful is True
        assert result.buffer == blob_data
        assert result.error is None

    async def test_s3_blob_end_to_end(self, pg_conn, tmp_path):
        from zodb_pgjsonb_thumborblobloader.loader import load

        with mock_aws():
            client = boto3.client("s3", region_name=S3_REGION)
            client.create_bucket(Bucket=S3_BUCKET)

            blob_data = b"JPEG\xff\xd8\xff\xe0" + b"\xff" * 200
            s3_key = "blobs/000000000000dead/000000000000beef.blob"
            client.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=blob_data)

            insert_s3_blob(
                pg_conn,
                zoid=0xDEAD,
                tid=0xBEEF,
                s3_key=s3_key,
                blob_size=len(blob_data),
            )

            cache_dir = str(tmp_path / "cache")
            ctx = make_context(
                PGTHUMBOR_S3_BUCKET=S3_BUCKET,
                PGTHUMBOR_S3_REGION=S3_REGION,
                PGTHUMBOR_CACHE_DIR=cache_dir,
                PGTHUMBOR_CACHE_MAX_SIZE=1024 * 1024,
            )
            result = await load(ctx, "dead/beef")

            assert result.successful is True
            assert result.buffer == blob_data

            # Second load should come from cache
            result2 = await load(ctx, "dead/beef")
            assert result2.successful is True
            assert result2.buffer == blob_data

    async def test_not_found_end_to_end(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        result = await load(make_context(), "ffff/ffff")

        assert result.successful is False
        assert result.error == "not_found"
        assert result.buffer is None

    async def test_bad_request_end_to_end(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        result = await load(make_context(), "../../etc/passwd")

        assert result.successful is False
        assert result.error == "bad_request"

    async def test_multiple_blobs_same_session(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        for i in range(5):
            insert_pg_blob(
                pg_conn, zoid=i + 1, tid=i + 100, data=f"blob number {i}".encode()
            )

        ctx = make_context()
        for i in range(5):
            zoid_hex = format(i + 1, "x")
            tid_hex = format(i + 100, "x")
            result = await load(ctx, f"{zoid_hex}/{tid_hex}")
            assert result.successful is True
            assert result.buffer == f"blob number {i}".encode()


class TestValidateIntegration:
    """Test validate function behavior."""

    def test_validate_accepts_real_path(self):
        from zodb_pgjsonb_thumborblobloader.loader import validate

        assert validate(None, "dead/beef") is True

    def test_validate_rejects_traversal(self):
        from zodb_pgjsonb_thumborblobloader.loader import validate

        assert validate(None, "../../etc/passwd") is False

    def test_validate_rejects_url(self):
        from zodb_pgjsonb_thumborblobloader.loader import validate

        assert validate(None, "https://example.com/image.jpg") is False
