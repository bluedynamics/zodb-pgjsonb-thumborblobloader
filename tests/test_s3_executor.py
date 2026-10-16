"""Tests for the thread pool that runs S3 downloads."""

from __future__ import annotations

from zodb_pgjsonb_thumborblobloader import s3 as s3_mod

import pytest
import threading


@pytest.fixture(autouse=True)
def _reset_executor():
    yield
    if s3_mod._executor is not None:
        s3_mod._executor.shutdown(wait=True)
    s3_mod._executor = None


def test_default_max_workers(monkeypatch):
    monkeypatch.delenv("PGTHUMBOR_S3_MAX_WORKERS", raising=False)
    assert s3_mod._get_executor()._max_workers == 8


def test_env_override_max_workers(monkeypatch):
    monkeypatch.setenv("PGTHUMBOR_S3_MAX_WORKERS", "3")
    assert s3_mod._get_executor()._max_workers == 3


async def test_download_runs_in_own_executor(monkeypatch):
    def fake_download(bucket, region, s3_key, endpoint=""):
        return threading.current_thread().name.encode()

    monkeypatch.setattr(s3_mod, "_download_sync", fake_download)

    thread_name = await s3_mod.download_blob("bucket", "us-east-1", "key")

    assert thread_name.startswith(b"pgthumbor-s3")
