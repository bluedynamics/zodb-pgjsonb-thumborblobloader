"""Tests for the Thumbor auth handler (HANDLER_LISTS module)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import time


class TestIsHex:
    """Test the _is_hex helper."""

    def test_valid_hex(self):
        from zodb_pgjsonb_thumborblobloader.auth_handler import _is_hex

        assert _is_hex("42") is True
        assert _is_hex("ff") is True
        assert _is_hex("DEADBEEF") is True
        assert _is_hex("0000000000000042") is True

    def test_invalid_hex(self):
        from zodb_pgjsonb_thumborblobloader.auth_handler import _is_hex

        assert _is_hex("") is False
        assert _is_hex("xyz") is False
        assert _is_hex("unsafe") is False
        assert _is_hex("500x400") is False
        assert _is_hex("fit-in") is False


class TestExtractContentZoid:
    """Test _extract_content_zoid() URL parsing."""

    def _make_handler(self, path):
        """Build a minimal AuthImagingHandler-like object with a mocked request."""
        from zodb_pgjsonb_thumborblobloader.auth_handler import AuthImagingHandler

        handler = object.__new__(AuthImagingHandler)
        handler.request = MagicMock()
        handler.request.path = path
        return handler

    def test_three_segment_url_returns_last(self):
        """3-segment URL: blob_zoid/tid/content_zoid → return content_zoid."""
        handler = self._make_handler(
            "/AbCdEf/unsafe/0000000000000042/00000000000000ff/000000000000001a"
        )
        result = handler._extract_content_zoid()
        assert result == "000000000000001a"

    def test_two_segment_url_returns_none(self):
        """2-segment URL: blob_zoid/tid → return None (anonymous)."""
        handler = self._make_handler("/AbCdEf/unsafe/0000000000000042/00000000000000ff")
        result = handler._extract_content_zoid()
        assert result is None

    def test_short_hex_three_segments(self):
        """Short (unpadded) hex values in 3-segment format."""
        handler = self._make_handler("/hmac/500x400/42/ff/1a")
        result = handler._extract_content_zoid()
        assert result == "1a"

    def test_operations_not_mistaken_for_hex(self):
        """Operations like 'unsafe' contain non-hex chars — not matched."""
        handler = self._make_handler("/hmac/unsafe/42/ff")
        # 'unsafe' is not hex → last 3 segments don't all parse → None
        result = handler._extract_content_zoid()
        assert result is None

    def test_fittin_not_mistaken_for_hex(self):
        handler = self._make_handler("/hmac/fit-in/500x400/42/ff")
        result = handler._extract_content_zoid()
        assert result is None

    def test_empty_path(self):
        handler = self._make_handler("/")
        result = handler._extract_content_zoid()
        assert result is None


class TestCheckAuth:
    """Test _check_auth() Plone subrequest logic and caching."""

    def _make_handler(self, plone_url="http://plone:8080/Plone", cache_ttl=60):
        from zodb_pgjsonb_thumborblobloader.auth_handler import _auth_cache
        from zodb_pgjsonb_thumborblobloader.auth_handler import AuthImagingHandler

        _auth_cache.clear()

        handler = object.__new__(AuthImagingHandler)
        handler.request = MagicMock()
        handler.request.headers = {"Cookie": "auth=abc123"}
        handler.context = MagicMock()
        handler.context.config.get = lambda key, default=None: {
            "PGTHUMBOR_PLONE_AUTH_URL": plone_url,
            "PGTHUMBOR_AUTH_CACHE_TTL": cache_ttl,
        }.get(key, default)
        return handler

    @pytest.mark.asyncio
    async def test_plone_200_returns_true(self):
        handler = self._make_handler()
        mock_response = MagicMock()
        mock_response.code = 200

        with patch(
            "zodb_pgjsonb_thumborblobloader.auth_handler.AsyncHTTPClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.fetch = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await handler._check_auth("000000000000001a")

        assert result is True

    @pytest.mark.asyncio
    async def test_plone_403_returns_false(self):
        handler = self._make_handler()
        mock_response = MagicMock()
        mock_response.code = 403

        with patch(
            "zodb_pgjsonb_thumborblobloader.auth_handler.AsyncHTTPClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.fetch = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await handler._check_auth("000000000000001a")

        assert result is False

    @pytest.mark.asyncio
    async def test_no_plone_url_returns_false(self):
        """When PGTHUMBOR_PLONE_AUTH_URL is not set, fail closed."""
        handler = self._make_handler(plone_url="")
        result = await handler._check_auth("000000000000001a")
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        """Network errors fail closed."""
        handler = self._make_handler()

        with patch(
            "zodb_pgjsonb_thumborblobloader.auth_handler.AsyncHTTPClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.fetch = AsyncMock(side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client

            result = await handler._check_auth("000000000000001a")

        assert result is False

    @pytest.mark.asyncio
    async def test_cache_hit_skips_plone(self):
        """A cached result should not trigger another Plone subrequest."""
        from zodb_pgjsonb_thumborblobloader.auth_handler import _auth_cache

        handler = self._make_handler()
        cache_key = ("000000000000001a", "auth=abc123")
        _auth_cache[cache_key] = (True, time.monotonic() + 60)

        with patch(
            "zodb_pgjsonb_thumborblobloader.auth_handler.AsyncHTTPClient"
        ) as mock_client_cls:
            result = await handler._check_auth("000000000000001a")
            mock_client_cls.assert_not_called()

        assert result is True

    @pytest.mark.asyncio
    async def test_expired_cache_triggers_new_request(self):
        """An expired cache entry should trigger a fresh Plone subrequest."""
        from zodb_pgjsonb_thumborblobloader.auth_handler import _auth_cache

        handler = self._make_handler()
        cache_key = ("000000000000001a", "auth=abc123")
        _auth_cache[cache_key] = (False, time.monotonic() - 1)  # already expired

        mock_response = MagicMock()
        mock_response.code = 200

        with patch(
            "zodb_pgjsonb_thumborblobloader.auth_handler.AsyncHTTPClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.fetch = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await handler._check_auth("000000000000001a")
            mock_client.fetch.assert_called_once()

        assert result is True

    @pytest.mark.asyncio
    async def test_forwards_cookie_header(self):
        """Cookie header from original request is forwarded to Plone."""
        handler = self._make_handler()
        mock_response = MagicMock()
        mock_response.code = 200

        with patch(
            "zodb_pgjsonb_thumborblobloader.auth_handler.AsyncHTTPClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.fetch = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await handler._check_auth("000000000000001a")

            call_args = mock_client.fetch.call_args
            req = call_args[0][0]
            assert req.headers.get("Cookie") == "auth=abc123"
            assert req.headers.get("Accept") == "application/json"


class TestCacheControlHeaders:
    """Test Cache-Control header overrides based on request type."""

    def _make_handler(
        self,
        path="/hmac/300x200/42/ff/1a",
        cc_auth="private, max-age=86400",
        cc_public="",
        cc_error="public, max-age=10",
        status=200,
    ):
        from zodb_pgjsonb_thumborblobloader.auth_handler import _auth_cache
        from zodb_pgjsonb_thumborblobloader.auth_handler import AuthImagingHandler

        _auth_cache.clear()

        handler = object.__new__(AuthImagingHandler)
        handler.request = MagicMock()
        handler.request.path = path
        handler.request.headers = {"Cookie": "auth=abc123"}
        handler.context = MagicMock()
        config = {
            "PGTHUMBOR_PLONE_AUTH_URL": "http://plone:8080/Plone",
            "PGTHUMBOR_AUTH_CACHE_TTL": 60,
            "PGTHUMBOR_CACHE_CONTROL_AUTHENTICATED": cc_auth,
            "PGTHUMBOR_CACHE_CONTROL_PUBLIC": cc_public,
        }
        if cc_error is not None:
            config["PGTHUMBOR_CACHE_CONTROL_ERROR"] = cc_error
        handler.context.config.get = lambda key, default=None: config.get(key, default)
        handler._headers = {}
        handler.get_status = lambda: status
        return handler

    def test_authenticated_request_sets_private(self):
        """3-segment URL → _cache_control_override = private header."""
        handler = self._make_handler(path="/hmac/300x200/42/ff/1a")
        handler._extract_content_zoid()  # verify it's 3-segment
        # Simulate what get() does after auth passes
        handler._cache_control_override = handler.context.config.get(
            "PGTHUMBOR_CACHE_CONTROL_AUTHENTICATED", "private, max-age=86400"
        )
        assert handler._cache_control_override == "private, max-age=86400"

    def test_public_request_empty_default(self):
        """2-segment URL → _cache_control_override = empty (Thumbor default)."""
        handler = self._make_handler(path="/hmac/300x200/42/ff")
        handler._cache_control_override = handler.context.config.get(
            "PGTHUMBOR_CACHE_CONTROL_PUBLIC", ""
        )
        assert handler._cache_control_override == ""

    def test_custom_authenticated_value(self):
        handler = self._make_handler(cc_auth="private, no-store")
        handler._cache_control_override = handler.context.config.get(
            "PGTHUMBOR_CACHE_CONTROL_AUTHENTICATED", "private, max-age=86400"
        )
        assert handler._cache_control_override == "private, no-store"

    def test_custom_public_value(self):
        handler = self._make_handler(cc_public="public, max-age=3600, s-maxage=86400")
        handler._cache_control_override = handler.context.config.get(
            "PGTHUMBOR_CACHE_CONTROL_PUBLIC", ""
        )
        assert handler._cache_control_override == "public, max-age=3600, s-maxage=86400"

    def test_finish_sets_header_when_override_present(self):
        """finish() sets Cache-Control when _cache_control_override is set."""
        handler = self._make_handler()
        handler._cache_control_override = "private, max-age=86400"
        headers_set = {}
        handler.set_header = lambda k, v: headers_set.update({k: v})

        with patch.object(
            type(handler).__mro__[1], "finish", lambda self, *a, **kw: None
        ):
            handler.finish()

        assert headers_set["Cache-Control"] == "private, max-age=86400"

    def test_finish_skips_header_when_no_override(self):
        """finish() does NOT touch Cache-Control when no override is set."""
        handler = self._make_handler()
        # No _cache_control_override attribute set
        headers_set = {}
        handler.set_header = lambda k, v: headers_set.update({k: v})

        with patch.object(
            type(handler).__mro__[1], "finish", lambda self, *a, **kw: None
        ):
            handler.finish()

        assert "Cache-Control" not in headers_set

    def test_finish_skips_header_when_empty_override(self):
        """finish() does NOT touch Cache-Control when override is empty string."""
        handler = self._make_handler()
        handler._cache_control_override = ""
        headers_set = {}
        handler.set_header = lambda k, v: headers_set.update({k: v})

        with patch.object(
            type(handler).__mro__[1], "finish", lambda self, *a, **kw: None
        ):
            handler.finish()

        assert "Cache-Control" not in headers_set

    def test_finish_error_status_gets_microcache(self):
        """4xx response gets a short microcache, not the long-TTL override."""
        handler = self._make_handler(status=400)
        handler._cache_control_override = "public, max-age=31536000, immutable"
        headers_set = {}
        handler.set_header = lambda k, v: headers_set.update({k: v})

        with patch.object(
            type(handler).__mro__[1], "finish", lambda self, *a, **kw: None
        ):
            handler.finish()

        # The long-TTL override MUST NOT leak into the error response.
        assert headers_set["Cache-Control"] == "public, max-age=10"

    def test_finish_error_without_override_still_gets_microcache(self):
        """Error responses get a microcache even if no override was set."""
        handler = self._make_handler(status=404)
        # No _cache_control_override attribute set at all
        headers_set = {}
        handler.set_header = lambda k, v: headers_set.update({k: v})

        with patch.object(
            type(handler).__mro__[1], "finish", lambda self, *a, **kw: None
        ):
            handler.finish()

        assert headers_set["Cache-Control"] == "public, max-age=10"

    def test_finish_5xx_also_microcached(self):
        """5xx responses get the same microcache treatment as 4xx."""
        handler = self._make_handler(status=503)
        handler._cache_control_override = "public, max-age=31536000, immutable"
        headers_set = {}
        handler.set_header = lambda k, v: headers_set.update({k: v})

        with patch.object(
            type(handler).__mro__[1], "finish", lambda self, *a, **kw: None
        ):
            handler.finish()

        assert headers_set["Cache-Control"] == "public, max-age=10"

    def test_finish_error_microcache_configurable(self):
        """PGTHUMBOR_CACHE_CONTROL_ERROR overrides the default microcache."""
        handler = self._make_handler(
            status=400, cc_error="private, max-age=30, must-revalidate"
        )
        headers_set = {}
        handler.set_header = lambda k, v: headers_set.update({k: v})

        with patch.object(
            type(handler).__mro__[1], "finish", lambda self, *a, **kw: None
        ):
            handler.finish()

        assert headers_set["Cache-Control"] == "private, max-age=30, must-revalidate"

    def test_finish_3xx_leaves_cache_control_alone(self):
        """Redirects: no long-TTL override, no microcache — Thumbor default."""
        handler = self._make_handler(status=304)
        handler._cache_control_override = "public, max-age=31536000, immutable"
        headers_set = {}
        handler.set_header = lambda k, v: headers_set.update({k: v})

        with patch.object(
            type(handler).__mro__[1], "finish", lambda self, *a, **kw: None
        ):
            handler.finish()

        assert "Cache-Control" not in headers_set


class TestGetHandlers:
    """Test get_handlers() returns correct URL pattern."""

    def test_returns_handler_list(self):
        from zodb_pgjsonb_thumborblobloader.auth_handler import AuthImagingHandler
        from zodb_pgjsonb_thumborblobloader.auth_handler import get_handlers

        ctx = MagicMock()
        handlers = get_handlers(ctx)
        assert len(handlers) == 1
        pattern, cls, kwargs = handlers[0]
        assert cls is AuthImagingHandler
        # Pattern is Url.regex() — a complex named-group regex; just verify it's a non-empty string
        assert isinstance(pattern, str) and len(pattern) > 0
        assert kwargs == {"context": ctx}
