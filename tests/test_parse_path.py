"""Tests for path parsing: extracting (zoid, tid) from hex URL path."""

import pytest


class TestParsePath:
    """Test _parse_path(path) -> (zoid: int, tid: int)."""

    def test_valid_path_basic(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid = _parse_path("42/ff")
        assert zoid == 0x42
        assert tid == 0xFF

    def test_valid_path_zeros(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid = _parse_path("0000000000000000/0000000000000001")
        assert zoid == 0
        assert tid == 1

    def test_valid_path_max_values(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid = _parse_path("ffffffffffffffff/ffffffffffffffff")
        assert zoid == 0xFFFFFFFFFFFFFFFF
        assert tid == 0xFFFFFFFFFFFFFFFF

    def test_valid_path_mixed_case(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid = _parse_path("000000000000002A/000000000000002a")
        assert zoid == 0x2A
        assert tid == 0x2A

    def test_valid_path_short_hex(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid = _parse_path("42/ff")
        assert zoid == 0x42
        assert tid == 0xFF

    def test_valid_path_full_padding(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid = _parse_path("0000000000000042/00000000000000ff")
        assert zoid == 0x42
        assert tid == 0xFF

    def test_valid_path_leading_trailing_slash(self):
        """Thumbor may pass paths with leading slash."""
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        zoid, tid = _parse_path("/42/ff/")
        assert zoid == 0x42
        assert tid == 0xFF

    def test_invalid_no_slash(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("0000000000000042")

    def test_invalid_empty(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("")

    def test_invalid_too_many_segments(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("aa/bb/cc")

    def test_invalid_non_hex_zoid(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("xyz/0000000000000001")

    def test_invalid_non_hex_tid(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("0000000000000001/ghij")

    def test_invalid_slash_only(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("/")

    def test_invalid_empty_segment(self):
        from zodb_pgjsonb_thumborblobloader.loader import _parse_path

        with pytest.raises(ValueError, match="Invalid blob path"):
            _parse_path("/ff")
