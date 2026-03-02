"""Tests for path parsing: extracting (zoid, tid, content_zoid) from hex URL path."""

import pytest


class TestParsePath:
    """Test _parse_path(path) -> (zoid: int, tid: int, content_zoid: int | None)."""

    def test_valid_path_basic(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("42/ff")
        assert zoid == 0x42
        assert tid == 0xFF
        assert content_zoid is None

    def test_valid_path_zeros(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("0000000000000000/0000000000000001")
        assert zoid == 0
        assert tid == 1
        assert content_zoid is None

    def test_valid_path_max_values(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("ffffffffffffffff/ffffffffffffffff")
        assert zoid == 0xFFFFFFFFFFFFFFFF
        assert tid == 0xFFFFFFFFFFFFFFFF
        assert content_zoid is None

    def test_valid_path_mixed_case(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("000000000000002A/000000000000002a")
        assert zoid == 0x2A
        assert tid == 0x2A
        assert content_zoid is None

    def test_valid_path_short_hex(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("42/ff")
        assert zoid == 0x42
        assert tid == 0xFF
        assert content_zoid is None

    def test_valid_path_full_padding(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("0000000000000042/00000000000000ff")
        assert zoid == 0x42
        assert tid == 0xFF
        assert content_zoid is None

    def test_valid_path_leading_trailing_slash(self):
        """Thumbor may pass paths with leading slash."""
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("/42/ff/")
        assert zoid == 0x42
        assert tid == 0xFF
        assert content_zoid is None

    def test_valid_path_three_segments(self):
        """3-segment authenticated format: blob_zoid/tid/content_zoid."""
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("42/ff/1a")
        assert zoid == 0x42
        assert tid == 0xFF
        assert content_zoid == 0x1A

    def test_valid_path_three_segments_full_padding(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path(
            "0000000000000042/00000000000000ff/000000000000001a"
        )
        assert zoid == 0x42
        assert tid == 0xFF
        assert content_zoid == 0x1A

    def test_valid_path_three_segments_leading_slash(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid, content_zoid = _parse_path("/42/ff/1a/")
        assert zoid == 0x42
        assert tid == 0xFF
        assert content_zoid == 0x1A

    def test_invalid_no_slash(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("0000000000000042")

    def test_invalid_empty(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("")

    def test_invalid_four_segments(self):
        """4 segments is not valid — only 2 or 3 are accepted."""
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("aa/bb/cc/dd")

    def test_invalid_non_hex_zoid(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("xyz/0000000000000001")

    def test_invalid_non_hex_tid(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("0000000000000001/ghij")

    def test_invalid_non_hex_content_zoid(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("42/ff/xyz")

    def test_invalid_slash_only(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("/")

    def test_invalid_empty_segment(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("/ff")
