"""Thumbor image loader for zodb-pgjsonb blob_state table.

Config keys (set in thumbor.conf):
    PGTHUMBOR_DSN           -- PostgreSQL connection string (required)
    PGTHUMBOR_POOL_MIN_SIZE -- Min pool connections (default: 1)
    PGTHUMBOR_POOL_MAX_SIZE -- Max pool connections (default: 4)
    PGTHUMBOR_CACHE_DIR     -- Disk cache directory (empty = disabled)
    PGTHUMBOR_CACHE_MAX_SIZE -- Max cache size in bytes (0 = disabled)
    PGTHUMBOR_S3_BUCKET     -- S3 bucket for large blobs (empty = disabled)
    PGTHUMBOR_S3_REGION     -- S3 region (default: us-east-1)
    PGTHUMBOR_S3_ENDPOINT   -- S3 endpoint for MinIO (empty = AWS)

Usage in thumbor.conf:
    LOADER = 'zodb_pgjsonb_thumborblobloader.loader'
"""

from __future__ import annotations

from thumbor.loaders import LoaderResult
from zodb_pgjsonb_thumborblobloader.pool import get_pool
from zodb_pgjsonb_thumborblobloader.pool import SchemaError

import logging


logger = logging.getLogger(__name__)

_cache_instance = None


def _parse_path(path: str) -> tuple[int, int, int | None]:
    """Parse blob path into (zoid, tid, content_zoid) integers.

    Accepts two formats:
    - '<zoid_hex>/<tid_hex>'                        → (zoid, tid, None)
    - '<zoid_hex>/<tid_hex>/<content_zoid_hex>'     → (zoid, tid, content_zoid)

    The 3-segment format is used for authenticated content where the Thumbor
    handler must verify Plone access before delivering the image.

    Args:
        path: URL path segment, e.g. '0000000000000042/00000000000000ff'
              or '0000000000000042/00000000000000ff/000000000000001a'

    Returns:
        Tuple of (zoid, tid, content_zoid) as Python ints.
        content_zoid is None for the 2-segment anonymous format.

    Raises:
        ValueError: If path cannot be parsed as two or three hex segments.
    """
    stripped = path.strip("/")
    if not stripped:
        raise ValueError(f"Invalid blob path: {path!r} (empty)")
    parts = stripped.split("/")
    if len(parts) not in (2, 3):
        raise ValueError(
            f"Invalid blob path: {path!r} "
            f"(expected '<zoid_hex>/<tid_hex>[/<content_zoid_hex>]')"
        )
    if any(not p for p in parts):
        raise ValueError(f"Invalid blob path: {path!r} (empty segment)")
    try:
        parts_list = list(parts)
        # Strip optional extension from the last segment (tid or content_zoid)
        if "." in parts_list[-1]:
            parts_list[-1] = parts_list[-1].split(".", 1)[0]

        zoid = int(parts_list[0], 16)
        tid = int(parts_list[1], 16)
        content_zoid = int(parts_list[2], 16) if len(parts_list) == 3 else None
    except ValueError:
        raise ValueError(f"Invalid blob path: {path!r} (not valid hex)") from None
    return zoid, tid, content_zoid


def validate(context, url: str) -> bool:
    """Validate whether the URL is a valid blob path."""
    try:
        _parse_path(url)
        return True
    except ValueError:
        return False


def _get_cache(context):
    """Get or create the disk cache singleton from context config."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance
    from zodb_pgjsonb_thumborblobloader.cache import BlobCache

    cache_dir = context.config.get("PGTHUMBOR_CACHE_DIR", "")
    max_size = context.config.get("PGTHUMBOR_CACHE_MAX_SIZE", 0)
    _cache_instance = BlobCache(cache_dir, max_size)
    return _cache_instance


async def load(context, path: str) -> LoaderResult:
    """Load blob data from the zodb-pgjsonb blob_state table.

    Args:
        context: Thumbor context with config
        path: URL path segment '<zoid_hex>/<tid_hex>'

    Returns:
        LoaderResult with buffer (bytes) on success, or error on failure.
    """
    # Parse path
    try:
        zoid, tid, _ = _parse_path(path)
    except ValueError as exc:
        logger.warning("Bad request: %s", exc)
        return LoaderResult(
            successful=False,
            error=LoaderResult.ERROR_BAD_REQUEST,
            extras={"detail": str(exc)},
        )

    # Check disk cache
    cache = _get_cache(context)
    if cache.enabled:
        cached_data = cache.get(zoid, tid)
        if cached_data is not None:
            return LoaderResult(
                buffer=cached_data,
                successful=True,
                metadata={"size": len(cached_data)},
            )

    # Get pool (triggers schema verification on first call)
    dsn = context.config.get("PGTHUMBOR_DSN", "")
    if not dsn:
        logger.error("PGTHUMBOR_DSN not configured")
        return LoaderResult(
            successful=False,
            error=LoaderResult.ERROR_UPSTREAM,
            extras={"detail": "PGTHUMBOR_DSN not configured"},
        )

    min_size = context.config.get("PGTHUMBOR_POOL_MIN_SIZE", 1)
    max_size = context.config.get("PGTHUMBOR_POOL_MAX_SIZE", 4)

    try:
        pool = await get_pool(dsn, min_size=min_size, max_size=max_size)
    except SchemaError as exc:
        logger.error("Schema error: %s", exc)
        return LoaderResult(
            successful=False,
            error=LoaderResult.ERROR_UPSTREAM,
            extras={"detail": str(exc)},
        )
    except Exception as exc:
        logger.error("Failed to get connection pool: %s", exc)
        return LoaderResult(
            successful=False,
            error=LoaderResult.ERROR_UPSTREAM,
            extras={"detail": f"Pool error: {exc}"},
        )

    # Query blob_state
    try:
        async with pool.connection() as conn:
            result = await conn.execute(
                "SELECT data, s3_key, blob_size FROM blob_state WHERE zoid = %s AND tid = %s",
                (zoid, tid),
            )
            row = await result.fetchone()
    except Exception as exc:
        logger.error("Database query error: %s", exc)
        return LoaderResult(
            successful=False,
            error=LoaderResult.ERROR_UPSTREAM,
            extras={"detail": f"DB error: {exc}"},
        )

    if row is None:
        return LoaderResult(
            successful=False,
            error=LoaderResult.ERROR_NOT_FOUND,
        )

    data, s3_key, blob_size = row

    # PG bytea path — data is directly available
    if data is not None:
        result_bytes = bytes(data)
        if cache.enabled:
            cache.put(zoid, tid, result_bytes)
            cache.evict_if_needed()
        return LoaderResult(
            buffer=result_bytes,
            successful=True,
            metadata={"size": blob_size},
        )

    # S3 path
    if s3_key is not None:
        return await _load_from_s3(context, s3_key, blob_size, zoid, tid, cache)

    # Neither data nor s3_key — should not happen
    logger.error(
        "blob_state row has neither data nor s3_key: zoid=%d tid=%d", zoid, tid
    )
    return LoaderResult(
        successful=False,
        error=LoaderResult.ERROR_UPSTREAM,
        extras={"detail": "Blob row has no data source"},
    )


async def _load_from_s3(
    context, s3_key: str, blob_size: int, zoid: int, tid: int, cache
) -> LoaderResult:
    """Load blob bytes from S3."""
    bucket = context.config.get("PGTHUMBOR_S3_BUCKET", "")
    region = context.config.get("PGTHUMBOR_S3_REGION", "us-east-1")
    endpoint = context.config.get("PGTHUMBOR_S3_ENDPOINT", "")

    if not bucket:
        logger.error("S3 key %s found but PGTHUMBOR_S3_BUCKET not configured", s3_key)
        return LoaderResult(
            successful=False,
            error=LoaderResult.ERROR_UPSTREAM,
            extras={"detail": "S3 not configured"},
        )

    from zodb_pgjsonb_thumborblobloader.s3 import download_blob

    data = await download_blob(bucket, region, s3_key, endpoint=endpoint)
    if data is None:
        return LoaderResult(
            successful=False,
            error=LoaderResult.ERROR_UPSTREAM,
            extras={"detail": f"S3 download failed: {s3_key}"},
        )

    if cache.enabled:
        cache.put(zoid, tid, data)
        cache.evict_if_needed()

    return LoaderResult(
        buffer=data,
        successful=True,
        metadata={"size": blob_size},
    )
