"""S3 download support for the Thumbor blob loader.

Uses boto3 synchronously, wrapped in asyncio.to_thread for async context,
since boto3 does not natively support async.
"""

from __future__ import annotations

from botocore.exceptions import ClientError

import asyncio
import logging
import os


logger = logging.getLogger(__name__)

_s3_client = None
_s3_config: tuple[str, str, str] | None = None


def _get_s3_client(bucket: str, region: str, endpoint: str = ""):
    """Get or create a module-level boto3 S3 client."""
    global _s3_client, _s3_config
    key = (bucket, region, endpoint)
    if _s3_client is not None and _s3_config == key:
        return _s3_client

    import boto3

    kwargs: dict = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    access_key = os.environ.get("PGTHUMBOR_S3_ACCESS_KEY", "")
    secret_key = os.environ.get("PGTHUMBOR_S3_SECRET_KEY", "")
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    _s3_client = boto3.client("s3", **kwargs)
    _s3_config = key
    return _s3_client


def _download_sync(
    bucket: str, region: str, s3_key: str, endpoint: str = ""
) -> bytes | None:
    """Download S3 object synchronously.  Returns bytes or None on error."""
    client = _get_s3_client(bucket, region, endpoint)
    try:
        response = client.get_object(Bucket=bucket, Key=s3_key)
        return response["Body"].read()
    except ClientError as exc:
        code = exc.response["Error"].get("Code", "")
        logger.error("S3 download failed for key=%s: %s", s3_key, code)
        return None


async def download_blob(
    bucket: str, region: str, s3_key: str, endpoint: str = ""
) -> bytes | None:
    """Download S3 object asynchronously (runs boto3 in thread executor)."""
    return await asyncio.to_thread(_download_sync, bucket, region, s3_key, endpoint)
