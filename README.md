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

## Development

```bash
cd sources/zodb-pgjsonb-thumborblobloader
uv pip install -e ".[test,s3]"

# Run tests (requires PostgreSQL on localhost:5433)
pytest
```

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
