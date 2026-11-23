import logging

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """Isolate every test from the developer's BIM6G_* variables AND their real .env file."""
    import os

    import backend.config

    for key in list(os.environ):
        if key.startswith("BIM6G_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(backend.config, "DEFAULT_ENV_FILE", tmp_path / "no-such.env")


@pytest.fixture
def clean_logging():
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_bim6g", False):
            root.removeHandler(handler)
            handler.close()
