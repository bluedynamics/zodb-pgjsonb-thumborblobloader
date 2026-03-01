"""Disk cache for blob data with LRU eviction.

Caches blob bytes to local disk to avoid repeated PG/S3 fetches.
Deterministic filenames: {cache_dir}/{zoid:016x}-{tid:016x}.blob

Since blobs are addressed by (zoid, tid) — both immutable in ZODB —
there is no cache invalidation concern.  Only LRU eviction for space.
"""

from __future__ import annotations

import contextlib
import logging
import os


logger = logging.getLogger(__name__)


class BlobCache:
    """Local filesystem cache for blob bytes."""

    def __init__(self, cache_dir: str, max_size: int):
        self.cache_dir = cache_dir
        self.max_size = max_size
        self.enabled = bool(cache_dir and max_size > 0)
        self._target_size = int(max_size * 0.9) if max_size > 0 else 0

        if self.enabled:
            os.makedirs(cache_dir, exist_ok=True, mode=0o700)

    def _blob_path(self, zoid: int, tid: int) -> str:
        return os.path.join(self.cache_dir, f"{zoid:016x}-{tid:016x}.blob")

    def get(self, zoid: int, tid: int) -> bytes | None:
        """Read cached blob bytes, or None if not cached."""
        if not self.enabled:
            return None
        path = self._blob_path(zoid, tid)
        try:
            with open(path, "rb") as f:
                data = f.read()
            # Touch atime for LRU
            os.utime(path)
            return data
        except FileNotFoundError:
            return None

    def put(self, zoid: int, tid: int, data: bytes) -> None:
        """Write blob bytes to cache."""
        if not self.enabled:
            return
        path = self._blob_path(zoid, tid)
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "wb") as f:
                f.write(data)
            os.rename(tmp_path, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

    def evict_if_needed(self) -> None:
        """Remove oldest files (by atime) if total size exceeds max_size."""
        if not self.enabled:
            return
        files = []
        for fn in os.listdir(self.cache_dir):
            if fn.endswith(".blob"):
                fp = os.path.join(self.cache_dir, fn)
                with contextlib.suppress(OSError):
                    st = os.stat(fp)
                    files.append((st.st_atime, st.st_size, fp))

        total_size = sum(size for _, size, _ in files)
        if total_size <= self.max_size:
            return

        files.sort(key=lambda x: x[0])  # oldest atime first
        for _atime, size, fp in files:
            if total_size <= self._target_size:
                break
            with contextlib.suppress(OSError):
                os.remove(fp)
                total_size -= size

    def current_size(self) -> int:
        """Return total size of cached files.  For testing."""
        if not self.enabled:
            return 0
        total = 0
        for fn in os.listdir(self.cache_dir):
            if fn.endswith(".blob"):
                with contextlib.suppress(OSError):
                    total += os.path.getsize(os.path.join(self.cache_dir, fn))
        return total
