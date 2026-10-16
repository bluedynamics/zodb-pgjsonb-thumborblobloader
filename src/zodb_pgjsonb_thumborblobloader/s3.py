"""S3 download support for the Thumbor blob loader.

Uses boto3 synchronously in a small thread pool of its own, since boto3 does
not natively support async.
"""

from __future__ import annotations

from botocore.config import Config
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor

import asyncio
import logging
import os


logger = logging.getLogger(__name__)

# boto3's default urllib3 max_pool_connections is 10 — too low for
# concurrent Thumbor image loads (30 thumbnails per listing page times
# active visitors easily exceeds it, causing connection discard/reopen
# churn and handshake-failure-induced 400s).  50 covers the download
# threads plus headroom.
DEFAULT_MAX_POOL_CONNECTIONS = 50

# asyncio.to_thread's default executor sizes itself from the host's cores and
# ignores a container CPU limit: 24 threads on a 20-core node.  glibc gives
# each thread its own malloc arena, and the freed download buffers stayed
# behind as over a GiB of fragmented memory.
DEFAULT_MAX_WORKERS = 8

_s3_client = None
_s3_config: tuple[str, str, str] | None = None
_executor: ThreadPoolExecutor | None = None


def _get_s3_client(bucket: str, region: str, endpoint: str = ""):
    """Get or create a module-level boto3 S3 client."""
    global _s3_client, _s3_config
    key = (bucket, region, endpoint)
    if _s3_client is not None and _s3_config == key:
        return _s3_client

    import boto3

    max_pool = int(
        os.environ.get(
            "PGTHUMBOR_S3_MAX_POOL_CONNECTIONS", str(DEFAULT_MAX_POOL_CONNECTIONS)
        )
    )
    kwargs: dict = {
        "region_name": region,
        "config": Config(max_pool_connections=max_pool),
    }
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


def _get_executor() -> ThreadPoolExecutor:
    """Get or create the module-level thread pool for S3 downloads."""
    global _executor
    if _executor is None:
        max_workers = int(
            os.environ.get("PGTHUMBOR_S3_MAX_WORKERS", str(DEFAULT_MAX_WORKERS))
        )
        _executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="pgthumbor-s3"
        )
    return _executor


async def download_blob(
    bucket: str, region: str, s3_key: str, endpoint: str = ""
) -> bytes | None:
    """Download S3 object asynchronously (runs boto3 in the S3 thread pool)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _get_executor(), _download_sync, bucket, region, s3_key, endpoint
    )
