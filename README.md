# zodb-pgjsonb-thumborblobloader

Thumbor 7.x image loader that reads blob data directly from the
zodb-pgjsonb `blob_state` PostgreSQL table.

## Configuration

In your `thumbor.conf`:

```python
LOADER = 'zodb_pgjsonb_thumborblobloader.loader'

PGTHUMBOR_DSN = 'dbname=zodb user=zodb password=zodb host=localhost port=5433'
```

## URL scheme

```
http://thumbor:8888/<signing>/<transforms>/<zoid_hex>/<tid_hex>
```
