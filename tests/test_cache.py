"""Tests for the disk cache module."""

from __future__ import annotations

import time


class TestCacheFilename:
    """Test deterministic filename generation."""

    def test_filename_format(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=1024 * 1024)
        path = cache._blob_path(0x42, 0xFF)
        assert path.endswith("0000000000000042-00000000000000ff.blob")

    def test_filename_zero(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=1024 * 1024)
        path = cache._blob_path(0, 0)
        assert path.endswith("0000000000000000-0000000000000000.blob")


class TestCacheGetPut:
    """Test cache get/put operations."""

    def test_get_missing_returns_none(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=1024 * 1024)
        assert cache.get(0x42, 0xFF) is None

    def test_put_and_get_roundtrip(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=1024 * 1024)
        blob_data = b"cached blob data"
        cache.put(0x42, 0xFF, blob_data)
        assert cache.get(0x42, 0xFF) == blob_data

    def test_put_overwrites(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=1024 * 1024)
        cache.put(0x42, 0xFF, b"version 1")
        cache.put(0x42, 0xFF, b"version 2")
        assert cache.get(0x42, 0xFF) == b"version 2"

    def test_different_zoid_tid_pairs(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=1024 * 1024)
        cache.put(1, 1, b"blob_1_1")
        cache.put(1, 2, b"blob_1_2")
        cache.put(2, 1, b"blob_2_1")

        assert cache.get(1, 1) == b"blob_1_1"
        assert cache.get(1, 2) == b"blob_1_2"
        assert cache.get(2, 1) == b"blob_2_1"


class TestCacheDisabled:
    """Test that cache is a no-op when disabled."""

    def test_disabled_when_no_dir(self):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache("", max_size=0)
        assert cache.enabled is False
        assert cache.get(1, 1) is None
        cache.put(1, 1, b"data")  # Should not raise
        assert cache.get(1, 1) is None

    def test_disabled_when_zero_size(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=0)
        assert cache.enabled is False


class TestCacheEviction:
    """Test LRU eviction by atime."""

    def test_eviction_removes_oldest(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        # max_size=500 bytes — each blob is 200 bytes, so 4 blobs exceed it
        cache = BlobCache(str(tmp_path / "cache"), max_size=500)

        for i in range(4):
            cache.put(i, 1, b"X" * 200)
            time.sleep(0.05)  # Ensure distinct atimes

        cache.evict_if_needed()
        total = cache.current_size()
        assert total <= 500

    def test_eviction_keeps_newest(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=500)

        for i in range(4):
            cache.put(i, 1, b"X" * 200)
            time.sleep(0.05)

        cache.evict_if_needed()
        # The newest (last written) should survive
        assert cache.get(3, 1) is not None

    def test_eviction_not_triggered_below_threshold(self, tmp_path):
        from zodb_pgjsonb_thumborblobloader.cache import BlobCache

        cache = BlobCache(str(tmp_path / "cache"), max_size=10000)
        cache.put(1, 1, b"small")
        cache.evict_if_needed()
        assert cache.get(1, 1) == b"small"
