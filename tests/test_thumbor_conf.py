"""The shipped thumbor.conf: storages are configurable from the environment."""

from pathlib import Path

import pytest
import runpy


CONF = Path(__file__).parent.parent / "thumbor.conf"


def load_conf(monkeypatch, **env):
    for name in ("THUMBOR_STORAGE", "THUMBOR_RESULT_STORAGE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return runpy.run_path(str(CONF))


def test_defaults_keep_file_storages(monkeypatch):
    conf = load_conf(monkeypatch)
    assert conf["STORAGE"] == "thumbor.storages.file_storage"
    assert conf["RESULT_STORAGE"] == "thumbor.result_storages.file_storage"


@pytest.mark.parametrize(
    ("env", "key", "expected"),
    [
        ("THUMBOR_STORAGE", "STORAGE", "thumbor.storages.no_storage"),
        (
            "THUMBOR_RESULT_STORAGE",
            "RESULT_STORAGE",
            "thumbor.result_storages.no_storage",
        ),
    ],
)
def test_storages_from_environment(monkeypatch, env, key, expected):
    conf = load_conf(monkeypatch, **{env: expected})
    assert conf[key] == expected
