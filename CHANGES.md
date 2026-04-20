# Changelog

## 0.4.3 (unreleased)

- Fix: `AuthImagingHandler.finish()` no longer applies the long-TTL
  `Cache-Control` override to error responses (4xx/5xx).  Previously a
  transient Thumbor 400 (e.g. a PIL decompression-bomb rejection) would
  inherit `public, max-age=31536000, immutable` and get pinned in
  downstream HTTP caches (Varnish, CDN) for a year — a single bad fetch
  persistently hid the image on every shard that cached it.
  Errors now get a short microcache (`PGTHUMBOR_CACHE_CONTROL_ERROR`,
  default `public, max-age=10`) instead: decouples transient errors
  from long-term cache poisoning AND lets downstream caches absorb
  request floods for broken URLs (cheap DoS amplification defense —
  a single bad URL won't fan out to one Thumbor hit per request).
  3xx responses are left untouched (Thumbor default).
  Fixes [#5](https://github.com/bluedynamics/zodb-pgjsonb-thumborblobloader/issues/5).

- Fix: boto3 S3 client is now created with an explicit
  `max_pool_connections` via `botocore.Config` (default 50, overridable
  via `PGTHUMBOR_S3_MAX_POOL_CONNECTIONS`).  The boto3 default of 10
  caused urllib3 pool-full warnings and connection churn under normal
  Thumbor load (30 thumbnails per listing page times active visitors),
  which in turn correlated with intermittent Thumbor 400s on aaf-6
  prod.  50 covers `asyncio.to_thread`'s default executor
  (`min(32, cpu+4)`) plus headroom.
  Fixes [#6](https://github.com/bluedynamics/zodb-pgjsonb-thumborblobloader/issues/6).

## 0.4.2 (2026-04-02)

- Fix: S3 loader now reads `PGTHUMBOR_S3_ACCESS_KEY` and `PGTHUMBOR_S3_SECRET_KEY`
  env vars and passes them to boto3. Previously credentials were only picked up
  via boto3's default chain (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`).
  Fixes [#2](https://github.com/bluedynamics/zodb-pgjsonb-thumborblobloader/issues/2).

## 0.4.1 (2026-04-02)

- Fix: Docker image missing `boto3` — S3 blob loading failed with
  `ModuleNotFoundError: No module named 'botocore'`.
  Install package with `[s3]` extra in Dockerfile.
  Fixes [#1](https://github.com/bluedynamics/zodb-pgjsonb-thumborblobloader/issues/1).

## 0.4.0 (2026-03-10)

- Add smart cropping support via Thumbor's built-in detector system.
  Set `THUMBOR_DETECTORS` environment variable to enable face/feature detection
  for `/smart/` URLs. Docker image now includes `opencv-python-headless`.

## 0.3.2 (2026-03-10)

- Enable AUTO_WEBP by default for automatic WebP conversion when browser
  supports it. AUTO_AVIF available as opt-in. Both configurable via
  `THUMBOR_AUTO_WEBP` and `THUMBOR_AUTO_AVIF` environment variables.

## 0.3.1 (2026-03-09)

- Fix ruff lint/format errors that blocked CI.
- Docker image now built after PyPI release with pinned package version.

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
