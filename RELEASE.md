# Release Process

This project publishes two artifacts:

1. **Python package** on PyPI (`zodb-pgjsonb-thumborblobloader`)
2. **OCI image** on GHCR (`ghcr.io/bluedynamics/zodb-pgjsonb-thumborblobloader`)

## Python Package Release

Version is determined automatically from git tags via `hatch-vcs`.

### Steps

1. Update `CHANGES.md` — set the version and date:

   ```markdown
   ## 0.3.0 (2026-04-01)
   ```

2. Commit and push to `main`:

   ```bash
   git add CHANGES.md
   git commit -m "Release 0.3.0"
   git push
   ```

3. Create a GitHub release with a `v`-prefixed tag:

   ```bash
   gh release create v0.3.0 --title "0.3.0" --notes "See CHANGES.md"
   ```

4. The `release.yaml` workflow runs automatically:
   - QA (ruff) and tests must pass
   - Package is built via `hynek/build-and-inspect-python-package`
   - Published to PyPI via trusted publishing (OIDC)

5. Verify on PyPI: https://pypi.org/project/zodb-pgjsonb-thumborblobloader/

### Dev builds

Every push to `main` also publishes a dev build to
[Test PyPI](https://test.pypi.org/project/zodb-pgjsonb-thumborblobloader/).

## OCI Image Release

The Docker image is built and pushed to GHCR automatically.

### Image tags

- `thumbor-<THUMBOR_VERSION>_loader-<LOADER_VERSION>` — versioned tag
- `latest` — always points to the newest build

On tagged releases the loader version is clean (e.g. `0.3.0`).
On `main` pushes it includes the git describe suffix (e.g. `0.3.0-2-gabcdef0`).

### Automatic triggers

| Trigger | When |
|---------|------|
| Push to `main` | Every merge/push to main |
| GitHub Release published | When a `v*` tag is created |
| Manual dispatch | Via Actions UI or `gh workflow run docker.yaml` |
| Weekly Thumbor check | Mondays 06:00 UTC — rebuilds if a new Thumbor version is on PyPI |

### Manual rebuild

```bash
gh workflow run docker.yaml
```

### Platforms

Images are built for `linux/amd64` and `linux/arm64`.

See `README.md` for the full list of environment variables.

## Full Release Checklist

1. Update `CHANGES.md` with version and date
2. Commit: `git commit -am "Release X.Y.Z"`
3. Push: `git push`
4. Create release: `gh release create vX.Y.Z --title "X.Y.Z" --notes "See CHANGES.md"`
5. Verify:
   - PyPI package: https://pypi.org/project/zodb-pgjsonb-thumborblobloader/
   - GHCR image: `docker pull ghcr.io/bluedynamics/zodb-pgjsonb-thumborblobloader:latest`
   - Healthcheck: `docker run --rm -p 8888:8888 -e THUMBOR_SECURITY_KEY=test ghcr.io/bluedynamics/zodb-pgjsonb-thumborblobloader:latest` then `curl http://localhost:8888/healthcheck`
