# Changelog

## 0.4.4 (unreleased)

- GIFs go through gifsicle instead of Pillow: the Docker image installs gifsicle
  and `thumbor.conf` sets `USE_GIFSICLE_ENGINE` from `THUMBOR_USE_GIFSICLE_ENGINE`,
  on by default. Pillow decodes every frame of an animated GIF up front and
  converts each to RGB(A) for the resize. In production a 1.9 MB GIF with 408
  frames at 1920x1080 OOM-killed the pod on every cache miss; a synthetic 188 KB
  GIF of the same shape takes Thumbor 7.8.0 to 3.6 GB and 123 s
  ([thumbor/thumbor#1935](https://github.com/thumbor/thumbor/issues/1935)).
  gifsicle renders the production GIF in 3 s with about 100 MB and keeps all
  frames. With gifsicle, GIFs are not smart-cropped, filters do not apply to them,
  and static GIFs stay GIF instead of being converted to WebP. Set
  `THUMBOR_USE_GIFSICLE_ENGINE=false` for the previous behaviour.

- The Docker build fails if Debian ships gifsicle 1.98 or later. Thumbor 7.8.0
  passes float sizes such as `--resize 70x70.0`, which gifsicle 1.98 rejects, so
  every animated GIF would fail with a 500
  ([thumbor/thumbor#1933](https://github.com/thumbor/thumbor/pull/1933)).

- S3 downloads run in a thread pool of their own with 8 threads, set by
  `PGTHUMBOR_S3_MAX_WORKERS`. Before, they used `asyncio.to_thread`, whose default
  executor sizes itself from the host's cores and ignores a container CPU limit:
  24 threads on a 20-core node. glibc gives each thread its own malloc arena, and
  the freed download buffers stayed behind. In production 1.2 of 1.3 GiB resident
  memory were fragmented arenas, the Python heap was 61 MiB, and decoding a large
  image then pushed the pod over its 2 GiB memory limit.

- The Docker image sets `MALLOC_ARENA_MAX=2`. Thumbor and the libraries it loads
  start further threads; this bounds their arenas as well.

## 0.4.3 (2026-10-14)

- `THUMBOR_STORAGE` and `THUMBOR_RESULT_STORAGE` select Thumbor's storages from the
  environment. Both default to the file storages as before. The file storages
  never shrink: in a container with an ephemeral-storage limit of 4 Gi they filled
  it within about four hours and got the pod evicted, over and over. The README
  describes how to bound disk usage with the `no_storage` variants and the blob
  cache.

- Lower ruff's C901 max-complexity threshold from 15 to 13 as part of the
  ecosystem-wide complexity ratchet. The code base passes as-is.

- Enable ruff's cyclomatic-complexity check (`C901`, mccabe) with
  `max-complexity = 15`. The code base passes as-is.

- Bump `hynek/build-and-inspect-python-package` from v2 to v3.0.1. Hatchling now
  emits `Metadata-Version: 2.5`, which the Twine bundled in v2 rejects with
  `InvalidDistribution: '2.5' is not a valid metadata version` — the release
  build failed before uploading anything. v3 ships Twine 7, which supports it.

- Add the `LICENSE.txt` file with the full Zope Public License 2.1 text.
  The packaging metadata already declared `ZPL-2.1`, but the license text
  itself was missing from the repository, so GitHub reported "No license" and
  the terms could not be verified from the source tree alone. Fixes #12.

- Reformat the `thumbor.conf` example in the README. `ruff format` 0.16 also
  formats Python code inside markdown fences, so the single-quoted string
  literals in that block failed `qa / Ruff` on every pull request. No content
  change.

## 0.4.2 (2026-04-20)

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

- Fix: S3 loader now reads `PGTHUMBOR_S3_ACCESS_KEY` and
  `PGTHUMBOR_S3_SECRET_KEY` env vars and passes them to boto3.
  Previously credentials were only picked up via boto3's default chain
  (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`).
  Fixes [#2](https://github.com/bluedynamics/zodb-pgjsonb-thumborblobloader/issues/2).

- Test-infra: test suite now falls back to an ephemeral PostgreSQL
  container via `testcontainers` when `ZODB_TEST_DSN` is not set,
  so tests run without any prior local Postgres setup.

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
