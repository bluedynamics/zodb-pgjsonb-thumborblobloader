"""Thumbor HANDLER_LISTS module for Plone access control.

Intercepts image requests with a 3-segment URL path
(blob_zoid/tid/content_zoid) and verifies access with Plone before delivery.
2-segment URLs (blob_zoid/tid) are served directly without any auth check.

Configuration (thumbor.conf):
    HANDLER_LISTS = ['zodb_pgjsonb_thumborblobloader.auth_handler']
    PGTHUMBOR_PLONE_AUTH_URL = 'http://plone-internal:8080/Plone'
    PGTHUMBOR_AUTH_CACHE_TTL = 60
"""

from __future__ import annotations

from thumbor.handlers.imaging import ImagingHandler
from thumbor.url import Url
from tornado.httpclient import AsyncHTTPClient
from tornado.httpclient import HTTPRequest

import logging
import time


logger = logging.getLogger(__name__)

# (content_zoid_hex, cookie_header) -> (allowed: bool, expiry: float)
_auth_cache: dict[tuple[str, str], tuple[bool, float]] = {}

HEADERS_TO_FORWARD = ("Cookie", "Authorization")


def _is_hex(s: str) -> bool:
    """Return True if s is a non-empty valid hexadecimal string."""
    if not s:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


class AuthImagingHandler(ImagingHandler):
    """ImagingHandler subclass that enforces Plone access control.

    For 3-segment URLs (blob_zoid/tid/content_zoid), the content_zoid is
    verified against Plone's @thumbor-auth REST service before delivery.
    Browser cookies/auth headers are forwarded so Plone can authenticate
    the user from the shared reverse-proxy session.

    For 2-segment URLs (blob_zoid/tid), no auth check is performed.
    """

    async def get(self, **kwargs):
        content_zoid_hex = self._extract_content_zoid()
        if content_zoid_hex is not None:
            if not await self._check_auth(content_zoid_hex):
                self.set_status(403)
                self.finish()
                return
            self._cache_control_override = self.context.config.get(
                "PGTHUMBOR_CACHE_CONTROL_AUTHENTICATED",
                "private, max-age=86400",
            )
        else:
            self._cache_control_override = self.context.config.get(
                "PGTHUMBOR_CACHE_CONTROL_PUBLIC",
                "",
            )
        await super().get(**kwargs)

    def finish(self, *args, **kwargs):
        # Only apply the long-TTL Cache-Control override on success.
        # Otherwise a transient 4xx/5xx from Thumbor (e.g. a PIL
        # decompression-bomb 400) would get pinned in downstream HTTP
        # caches for the full max-age window, hiding the image for a year.
        #
        # Errors get a short "microcache" TTL instead of no-store: it
        # decouples transient errors from long-term cache poisoning,
        # *and* it absorbs request floods for the same broken URL —
        # downstream caches serve the error themselves for the next
        # few seconds instead of each request hitting Thumbor. Cheap
        # DoS amplification defense on top of the primary fix.
        status = self.get_status()
        cc = getattr(self, "_cache_control_override", "")
        if 200 <= status < 300:
            if cc:
                self.set_header("Cache-Control", cc)
        elif status >= 400:
            error_cc = self.context.config.get(
                "PGTHUMBOR_CACHE_CONTROL_ERROR",
                "public, max-age=10",
            )
            self.set_header("Cache-Control", error_cc)
        super().finish(*args, **kwargs)

    def _extract_content_zoid(self) -> str | None:
        """Return the content_zoid hex string if this is a 3-segment URL, else None.

        Thumbor URL structure:
            /{hmac}/{ops}/{blob_zoid}/{tid}                   ← 2-segment (anonymous)
            /{hmac}/{ops}/{blob_zoid}/{tid}/{content_zoid}    ← 3-segment (authenticated)

        We check if the last 3 path segments are all valid hex. If yes,
        it's a 3-segment authenticated URL and we return the last segment.
        If only the last 2 are valid hex, it's anonymous — return None.

        Both formats may optionally include a file extension on the last segment.
        """
        parts = [p for p in self.request.path.split("/") if p]
        if len(parts) < 2:
            return None

        # Work on a copy of the last segments to strip extensions for validation
        segments = list(parts[-3:])
        if "." in segments[-1]:
            segments[-1] = segments[-1].split(".", 1)[0]

        if (
            len(segments) >= 3
            and _is_hex(segments[-1])
            and _is_hex(segments[-2])
            and _is_hex(segments[-3])
        ):
            return segments[-1]
        return None

    async def _check_auth(self, content_zoid_hex: str) -> bool:
        """Check with Plone whether the current user may view this content.

        Forwards browser Cookie and Authorization headers so Plone can
        authenticate the user from the shared reverse-proxy session.
        Results are cached per (content_zoid, cookie) for PGTHUMBOR_AUTH_CACHE_TTL
        seconds to avoid a Plone round-trip on every image request.
        """
        cookie = self.request.headers.get("Cookie", "")
        cache_key = (content_zoid_hex, cookie)
        now = time.monotonic()

        cached = _auth_cache.get(cache_key)
        if cached is not None:
            result, expiry = cached
            if now < expiry:
                return result
            del _auth_cache[cache_key]

        plone_url = self.context.config.get("PGTHUMBOR_PLONE_AUTH_URL", "")
        if not plone_url:
            logger.warning(
                "PGTHUMBOR_PLONE_AUTH_URL not configured — denying request for zoid=%s",
                content_zoid_hex,
            )
            return False

        ttl = int(self.context.config.get("PGTHUMBOR_AUTH_CACHE_TTL", 60))
        url = f"{plone_url.rstrip('/')}/@thumbor-auth?zoid={content_zoid_hex}"

        headers = {"Accept": "application/json"}
        for h in HEADERS_TO_FORWARD:
            val = self.request.headers.get(h)
            if val:
                headers[h] = val

        try:
            client = AsyncHTTPClient()
            req = HTTPRequest(url, headers=headers, request_timeout=5.0)
            resp = await client.fetch(req, raise_error=False)
            result = resp.code == 200
        except Exception as exc:
            logger.error("Auth check failed for zoid=%s: %s", content_zoid_hex, exc)
            result = False

        _auth_cache[cache_key] = (result, now + ttl)
        return result


def get_handlers(context):
    """Return handler list for Thumbor's HANDLER_LISTS configuration."""
    return [(Url.regex(), AuthImagingHandler, {"context": context})]
