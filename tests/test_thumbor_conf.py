"""The shipped thumbor.conf: settings that are configurable from the environment."""

from pathlib import Path

import pytest
import runpy


CONF = Path(__file__).parent.parent / "thumbor.conf"


def load_conf(monkeypatch, **env):
    for name in (
        "THUMBOR_STORAGE",
        "THUMBOR_RESULT_STORAGE",
        "THUMBOR_USE_GIFSICLE_ENGINE",
    ):
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


def test_gifsicle_engine_is_on_by_default(monkeypatch):
    # Pillow decodes every frame of an animated GIF: a 188 KB GIF with 408
    # frames at 1920x1080 took thumbor to 3.6 GB (thumbor/thumbor#1935).
    assert load_conf(monkeypatch)["USE_GIFSICLE_ENGINE"] is True


@pytest.mark.parametrize(("value", "expected"), [("false", False), ("1", True)])
def test_gifsicle_engine_from_environment(monkeypatch, value, expected):
    conf = load_conf(monkeypatch, THUMBOR_USE_GIFSICLE_ENGINE=value)
    assert conf["USE_GIFSICLE_ENGINE"] is expected
