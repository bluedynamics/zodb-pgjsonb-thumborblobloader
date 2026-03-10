# zodb-pgjsonb-thumborblobloader

Thumbor 7.x image loader that reads blob data directly from the [zodb-pgjsonb](https://github.com/bluedynamics/zodb-pgjsonb) `blob_state` PostgreSQL table.

## Overview

This loader enables [Thumbor](https://www.thumbor.org/) to serve images stored as ZODB blobs in a `zodb-pgjsonb` PostgreSQL database -- without requiring a running ZODB/Zope instance. It supports:

- **Two-tier storage**: PostgreSQL bytea (preferred) with optional S3 fallback
- **Async connection pool**: psycopg3 `AsyncConnectionPool` for high concurrency
- **Disk cache**: LRU-evicted local cache with deterministic filenames
- **URL-based lookup**: `<zoid_hex>/<tid_hex>` addressing for exact blob versions

## Installation

```bash
pip install zodb-pgjsonb-thumborblobloader

# With S3 fallback support
pip install zodb-pgjsonb-thumborblobloader[s3]
```

## Configuration

In your `thumbor.conf`:

```python
LOADER = 'zodb_pgjsonb_thumborblobloader.loader'

# Required
PGTHUMBOR_DSN = 'dbname=zodb user=zodb password=zodb host=localhost port=5432'

# Connection pool (optional)
PGTHUMBOR_POOL_MIN_SIZE = 1
PGTHUMBOR_POOL_MAX_SIZE = 10

# Disk cache (optional)
PGTHUMBOR_CACHE_DIR = '/var/cache/thumbor/blobs'
PGTHUMBOR_CACHE_MAX_SIZE = 1073741824  # 1 GB

# S3 fallback (optional, requires [s3] extra)
PGTHUMBOR_S3_BUCKET = 'my-blob-bucket'
PGTHUMBOR_S3_REGION = 'eu-central-1'
PGTHUMBOR_S3_ENDPOINT = 'https://s3.example.com'  # for MinIO/Ceph
```

## URL Scheme

```
http://thumbor:8888/<signing>/<transforms>/<zoid_hex>/<tid_hex>
```

Both `zoid_hex` and `tid_hex` are required. The loader fetches the exact blob version identified by the OID/TID pair.

## How It Works

```
Thumbor request
  └-> loader.load(context, path)
       ├-> disk cache hit?  → return cached bytes
       ├-> PostgreSQL query → blob_state.data (bytea)
       ├-> S3 fallback      → blob_state.s3_key → boto3 download
       └-> cache on disk    → LRU eviction by atime
```

The `blob_state` table is owned and managed by [zodb-pgjsonb](https://github.com/bluedynamics/zodb-pgjsonb) -- this loader only reads from it.

## Docker Image

A pre-built OCI image is available on GHCR:

```bash
docker pull ghcr.io/bluedynamics/zodb-pgjsonb-thumborblobloader:latest
```

Platforms: `linux/amd64`, `linux/arm64`

### Image tags

- `thumbor-<THUMBOR_VERSION>_loader-<LOADER_VERSION>` -- versioned (e.g. `thumbor-7.7.7_loader-0.3.0`)
- `latest` -- always the newest build

The image is automatically rebuilt weekly when a new Thumbor version appears on PyPI.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PGTHUMBOR_DSN` | `""` | PostgreSQL connection string (required) |
| `THUMBOR_SECURITY_KEY` | `"CHANGE-ME"` | Thumbor HMAC security key |
| `ALLOW_UNSAFE_URL` | `"False"` | Allow unsigned URLs |
| `RESULT_STORAGE_PATH` | `/tmp/thumbor/result_storage` | Result cache directory |
| `PGTHUMBOR_POOL_MIN_SIZE` | `1` | Min DB pool connections |
| `PGTHUMBOR_POOL_MAX_SIZE` | `4` | Max DB pool connections |
| `PGTHUMBOR_CACHE_DIR` | `""` | Local blob cache directory (empty = disabled) |
| `PGTHUMBOR_CACHE_MAX_SIZE` | `0` | Max cache size in bytes (0 = disabled) |
| `PGTHUMBOR_S3_BUCKET` | `""` | S3 bucket for blob fallback (empty = disabled) |
| `PGTHUMBOR_S3_REGION` | `us-east-1` | S3 region |
| `PGTHUMBOR_S3_ENDPOINT` | `""` | S3 endpoint for MinIO/Ceph (empty = AWS) |
| `THUMBOR_AUTO_WEBP` | `"true"` | Auto-convert to WebP when browser supports it |
| `THUMBOR_AUTO_AVIF` | `"false"` | Auto-convert to AVIF when browser supports it |
| `THUMBOR_DETECTORS` | `""` | Comma-separated Thumbor detector modules for `/smart/` URLs (empty = disabled) |
| `PGTHUMBOR_PLONE_AUTH_URL` | `""` | Plone internal URL for auth (empty = disabled) |
| `PGTHUMBOR_AUTH_CACHE_TTL` | `60` | Auth cache TTL in seconds |
| `PGTHUMBOR_CACHE_CONTROL_AUTHENTICATED` | `private, max-age=86400` | Cache-Control for authenticated images (browser-only, no proxy caching) |
| `PGTHUMBOR_CACHE_CONTROL_PUBLIC` | `""` | Cache-Control for public images (empty = Thumbor default) |

The Plone auth handler (and Cache-Control overrides) is only loaded when `PGTHUMBOR_PLONE_AUTH_URL` is set.

### Quick start

```bash
docker run --rm -p 8888:8888 \
  -e PGTHUMBOR_DSN="dbname=zodb user=zodb password=zodb host=localhost" \
  -e THUMBOR_SECURITY_KEY="my-secret" \
  ghcr.io/bluedynamics/zodb-pgjsonb-thumborblobloader:latest

# Healthcheck
curl http://localhost:8888/healthcheck
```

### Smart cropping

Enable content-aware cropping by setting the `THUMBOR_DETECTORS` environment variable:

```bash
docker run --rm -p 8888:8888 \
  -e PGTHUMBOR_DSN="dbname=zodb user=zodb password=zodb host=localhost" \
  -e THUMBOR_SECURITY_KEY="my-secret" \
  -e THUMBOR_DETECTORS="thumbor.detectors.face_detector,thumbor.detectors.feature_detector" \
  ghcr.io/bluedynamics/zodb-pgjsonb-thumborblobloader:latest
```

When detectors are configured, adding `/smart/` to Thumbor URLs activates
face/feature detection for intelligent cropping. Face detection is tried first;
if no faces are found, feature detection (corners/edges) is used as fallback.
Results are cached by Thumbor's result storage, so detection runs only once per
unique URL.

Available detectors:
- `thumbor.detectors.face_detector` -- frontal face detection (OpenCV Haar cascade)
- `thumbor.detectors.feature_detector` -- corner/edge detection (OpenCV good-features-to-track)
- `thumbor.detectors.profile_detector` -- side profile face detection
- `thumbor.detectors.glasses_detector` -- glasses detection (supplements face detector)

## Development

```bash
cd sources/zodb-pgjsonb-thumborblobloader
uv pip install -e ".[test,s3]"

# Run tests (requires PostgreSQL on localhost:5433)
pytest
```

## Documentation

This package is documented together with [plone-pgthumbor](https://github.com/bluedynamics/plone-pgthumbor):
**https://bluedynamics.github.io/plone-pgthumbor/**

- [Architecture](https://github.com/bluedynamics/plone-pgthumbor/blob/main/docs/sources/explanation/architecture.md) -- request flow, loader integration
- [Configuration Reference](https://github.com/bluedynamics/plone-pgthumbor/blob/main/docs/sources/reference/configuration.md) -- all thumbor.conf settings

## Source Code and Contributions

The source code is managed in a Git repository, with its main branches hosted on GitHub.
Issues can be reported there too.

We'd be happy to see many forks and pull requests to make this package even better.
We welcome AI-assisted contributions, but expect every contributor to fully understand and be able to explain the code they submit.
Please don't send bulk auto-generated pull requests.

Maintainers are Jens Klein and the BlueDynamics Alliance developer team.
We appreciate any contribution and if a release on PyPI is needed, please just contact one of us.
We also offer commercial support if any training, coaching, integration or adaptations are needed.

## License

ZPL-2.1 (Zope Public License)
