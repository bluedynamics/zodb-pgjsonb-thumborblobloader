# Changelog

## 0.3.0 (2026-03-07)

- Add configurable Cache-Control headers for authenticated vs public images.
  Authenticated requests default to `private, max-age=86400` (browser-only,
  no proxy caching). Configurable via `PGTHUMBOR_CACHE_CONTROL_AUTHENTICATED`
  and `PGTHUMBOR_CACHE_CONTROL_PUBLIC` environment variables.

## 0.2.0

- Add `AuthImagingHandler` for Plone access control via `@thumbor-auth`
  REST service. 3-segment URLs (`blob_zoid/tid/content_zoid`) verify
  access before delivery; 2-segment URLs are served directly.
- Extend `_parse_path` to accept 3-segment authenticated URL format.

## 0.1.0

- Initial release: Thumbor loader for zodb-pgjsonb blob_state.
