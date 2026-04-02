# Changelog

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
