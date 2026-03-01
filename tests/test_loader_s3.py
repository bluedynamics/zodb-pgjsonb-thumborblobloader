"""Tests for the Thumbor loader — S3 blob path.

Uses moto to mock AWS S3.  Requires PG for blob_state queries.
"""

from __future__ import annotations

from moto import mock_aws
from tests.conftest import DSN
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


class TestLoadS3Blob:
    """Test loading blobs from S3 via s3_key."""

    async def test_load_s3_blob(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        with mock_aws():
            client = boto3.client("s3", region_name=S3_REGION)
            client.create_bucket(Bucket=S3_BUCKET)

            blob_data = b"S3 blob data here"
            s3_key = "blobs/0000000000000042/00000000000000ff.blob"
            client.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=blob_data)

            insert_s3_blob(
                pg_conn, zoid=0x42, tid=0xFF, s3_key=s3_key, blob_size=len(blob_data)
            )

            ctx = make_context(
                PGTHUMBOR_S3_BUCKET=S3_BUCKET, PGTHUMBOR_S3_REGION=S3_REGION
            )
            result = await load(ctx, "42/ff")

            assert result.successful is True
            assert result.buffer == blob_data
            assert result.metadata["size"] == len(blob_data)

    async def test_s3_key_missing_in_bucket(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        with mock_aws():
            client = boto3.client("s3", region_name=S3_REGION)
            client.create_bucket(Bucket=S3_BUCKET)
            # Do NOT upload the object

            insert_s3_blob(
                pg_conn, zoid=0x42, tid=0xFF, s3_key="blobs/missing.blob", blob_size=100
            )

            ctx = make_context(
                PGTHUMBOR_S3_BUCKET=S3_BUCKET, PGTHUMBOR_S3_REGION=S3_REGION
            )
            result = await load(ctx, "42/ff")

            assert result.successful is False
            assert result.error == "upstream"

    async def test_s3_not_configured_but_needed(self, pg_conn):
        from zodb_pgjsonb_thumborblobloader.loader import load

        insert_s3_blob(
            pg_conn, zoid=0x42, tid=0xFF, s3_key="blobs/no-config.blob", blob_size=100
        )

        ctx = make_context(PGTHUMBOR_S3_BUCKET="", PGTHUMBOR_S3_REGION="")
        result = await load(ctx, "42/ff")

        assert result.successful is False
        assert result.error == "upstream"

    async def test_pg_blob_preferred_over_s3(self, pg_conn):
        """If both data and s3_key exist, PG data is used."""
        from zodb_pgjsonb_thumborblobloader.loader import load

        blob_data = b"PG wins"
        with pg_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO blob_state (zoid, tid, blob_size, data, s3_key) VALUES (%s, %s, %s, %s, %s)",
                (0x42, 0xFF, len(blob_data), blob_data, "blobs/unused.blob"),
            )
        pg_conn.commit()

        ctx = make_context(PGTHUMBOR_S3_BUCKET=S3_BUCKET, PGTHUMBOR_S3_REGION=S3_REGION)
        result = await load(ctx, "42/ff")

        assert result.successful is True
        assert result.buffer == blob_data
