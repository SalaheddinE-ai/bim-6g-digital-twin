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


# ---------------------------------------------------------------------------------------------
# M01 fixtures
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def small_ifc(tmp_path_factory):
    """The deterministic small IFC4 building, written to a temp file."""
    from tests.fixtures.small_building import build_small_building_ifc, write

    return write(tmp_path_factory.mktemp("ifc") / "small_building.ifc", build_small_building_ifc())


@pytest.fixture(scope="session")
def empty_ifc(tmp_path_factory):
    from tests.fixtures.small_building import build_empty_ifc, write

    return write(tmp_path_factory.mktemp("ifc_empty") / "empty.ifc", build_empty_ifc())


@pytest.fixture(scope="session")
def small_model(small_ifc):
    """Extracted + validated model of the small building (needs IfcOpenShell)."""
    pytest.importorskip("ifcopenshell")
    from modules.bim.ingest import ingest_ifc

    return ingest_ifc(small_ifc).model


@pytest.fixture(scope="session")
def no_entities_ifc(tmp_path_factory):
    from tests.fixtures.small_building import build_no_entities_ifc, write

    return write(tmp_path_factory.mktemp("ifc_none") / "none.ifc", build_no_entities_ifc())
