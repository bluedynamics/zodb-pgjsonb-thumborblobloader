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
LOADER = "zodb_pgjsonb_thumborblobloader.loader"

# Required
PGTHUMBOR_DSN = "dbname=zodb user=zodb password=zodb host=localhost port=5432"

# Connection pool (optional)
PGTHUMBOR_POOL_MIN_SIZE = 1
PGTHUMBOR_POOL_MAX_SIZE = 10

# Disk cache (optional)
PGTHUMBOR_CACHE_DIR = "/var/cache/thumbor/blobs"
PGTHUMBOR_CACHE_MAX_SIZE = 1073741824  # 1 GB

# S3 fallback (optional, requires [s3] extra)
PGTHUMBOR_S3_BUCKET = "my-blob-bucket"
PGTHUMBOR_S3_REGION = "eu-central-1"
PGTHUMBOR_S3_ENDPOINT = "https://s3.example.com"  # for MinIO/Ceph
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
| `THUMBOR_STORAGE` | `thumbor.storages.file_storage` | Thumbor storage for source images; `thumbor.storages.no_storage` disables it |
| `THUMBOR_RESULT_STORAGE` | `thumbor.result_storages.file_storage` | Thumbor result storage; `thumbor.result_storages.no_storage` disables it |
| `RESULT_STORAGE_PATH` | `/tmp/thumbor/result_storage` | Result cache directory |
| `PGTHUMBOR_POOL_MIN_SIZE` | `1` | Min DB pool connections |
| `PGTHUMBOR_POOL_MAX_SIZE` | `4` | Max DB pool connections |
| `PGTHUMBOR_CACHE_DIR` | `""` | Local blob cache directory (empty = disabled) |
| `PGTHUMBOR_CACHE_MAX_SIZE` | `0` | Max cache size in bytes (0 = disabled) |
| `PGTHUMBOR_S3_BUCKET` | `""` | S3 bucket for blob fallback (empty = disabled) |
| `PGTHUMBOR_S3_REGION` | `us-east-1` | S3 region |
| `PGTHUMBOR_S3_ENDPOINT` | `""` | S3 endpoint for MinIO/Ceph (empty = AWS) |
| `PGTHUMBOR_S3_ACCESS_KEY` | `""` | S3 access key (empty = boto3 default chain) |
| `PGTHUMBOR_S3_SECRET_KEY` | `""` | S3 secret key (empty = boto3 default chain) |
| `PGTHUMBOR_S3_MAX_WORKERS` | `8` | Threads for concurrent S3 downloads |
| `PGTHUMBOR_S3_MAX_POOL_CONNECTIONS` | `50` | HTTP connections in the boto3 pool |
| `THUMBOR_AUTO_WEBP` | `"true"` | Auto-convert to WebP when browser supports it |
| `THUMBOR_AUTO_AVIF` | `"false"` | Auto-convert to AVIF when browser supports it |
| `THUMBOR_USE_GIFSICLE_ENGINE` | `"true"` | Process GIFs with gifsicle instead of Pillow; see "Bounding memory" |
| `THUMBOR_DETECTORS` | `""` | Comma-separated Thumbor detector modules for `/smart/` URLs (empty = disabled) |
| `PGTHUMBOR_PLONE_AUTH_URL` | `""` | Plone internal URL for auth (empty = disabled) |
| `PGTHUMBOR_AUTH_CACHE_TTL` | `60` | Auth cache TTL in seconds |
| `PGTHUMBOR_CACHE_CONTROL_AUTHENTICATED` | `private, max-age=86400` | Cache-Control for authenticated images (browser-only, no proxy caching) |
| `PGTHUMBOR_CACHE_CONTROL_PUBLIC` | `""` | Cache-Control for public images (empty = Thumbor default) |
| `PGTHUMBOR_CACHE_CONTROL_ERROR` | `public, max-age=10` | Cache-Control for 4xx/5xx responses — microcache decouples transient errors from long-term cache poisoning and absorbs request floods for broken URLs |

The Plone auth handler (and Cache-Control overrides) is only loaded when `PGTHUMBOR_PLONE_AUTH_URL` is set.

### Bounding disk usage

Thumbor's file storages keep every source image and every rendered result and never delete anything.
In a container they grow until the disk or the ephemeral-storage limit is full.
In production, run behind an HTTP cache (Varnish, a CDN) that caches the rendered results, and:

- set `THUMBOR_STORAGE=thumbor.storages.no_storage` and `THUMBOR_RESULT_STORAGE=thumbor.result_storages.no_storage`,
- enable the blob cache with `PGTHUMBOR_CACHE_DIR` and `PGTHUMBOR_CACHE_MAX_SIZE`, which evicts least recently used blobs,
- put `PGTHUMBOR_CACHE_DIR` on a volume of its own (in Kubernetes, a generic ephemeral volume per pod), sized above `PGTHUMBOR_CACHE_MAX_SIZE`.

### Bounding memory

Thumbor decodes every source image completely, so one large original takes several hundred MiB for a moment.
glibc keeps memory that a thread frees in that thread's own malloc arena and rarely returns it to the system.
With many threads the process grows to well over a GiB without holding any data.

- The Docker image sets `MALLOC_ARENA_MAX=2`. Set it yourself if you build your own image.
- S3 downloads use `PGTHUMBOR_S3_MAX_WORKERS` threads (default 8), independent of the number of cores on the host.
- GIFs go through gifsicle (`THUMBOR_USE_GIFSICLE_ENGINE`, on by default; the Docker image ships gifsicle). Pillow decodes every frame of an animated GIF and converts each to RGB(A): a 188 KB GIF with 408 frames at 1920x1080 took Thumbor to 3.6 GB ([thumbor/thumbor#1935](https://github.com/thumbor/thumbor/issues/1935)); gifsicle needs about 100 MB for it and keeps the animation. With gifsicle, GIFs are not smart-cropped, filters do not apply to them, and static GIFs stay GIF instead of being converted to WebP.
- Size the memory limit for the largest source image you expect. `MAX_PIXELS` in `thumbor.conf` (Thumbor's default: 75 million pixels) rejects larger ones with a 400.

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

GIFs are not smart-cropped while `THUMBOR_USE_GIFSICLE_ENGINE` is on (the default).

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
