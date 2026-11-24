"""M01 parser: load valid / reject invalid. Needs IfcOpenShell."""

import pytest

pytest.importorskip("ifcopenshell")
pytestmark = pytest.mark.ifc

from modules.bim.parser import (  # noqa: E402
    IfcLoadError,
    building_id_from_sha256,
    describe_source,
    load_ifc,
)


def test_load_valid_ifc(small_ifc):
    model = load_ifc(small_ifc)
    assert model.schema == "IFC4"
    assert len(model.by_type("IfcWall")) == 5  # includes IfcWallStandardCase


def test_describe_source_and_stable_building_id(small_ifc):
    model = load_ifc(small_ifc)
    src = describe_source(small_ifc, model)
    assert src.ifc_schema == "IFC4" and src.size_bytes == small_ifc.stat().st_size
    assert len(src.sha256) == 64
    assert building_id_from_sha256(src.sha256) == building_id_from_sha256(src.sha256)


def test_reject_garbage_file(tmp_path):
    p = tmp_path / "garbage.ifc"
    p.write_text("this is definitely not an IFC file\n")
    with pytest.raises(IfcLoadError, match="Not an IFC"):
        load_ifc(p)


def test_reject_step_header_with_broken_body(tmp_path):
    p = tmp_path / "broken.ifc"
    p.write_text("ISO-10303-21;\nHEADER;\nthis is not valid\n")
    with pytest.raises(IfcLoadError):
        load_ifc(p)


def test_reject_missing_empty_wrong_extension_and_oversize(tmp_path, small_ifc):
    with pytest.raises(IfcLoadError, match="not found"):
        load_ifc(tmp_path / "nope.ifc")
    empty = tmp_path / "empty.ifc"
    empty.write_bytes(b"")
    with pytest.raises(IfcLoadError, match="empty"):
        load_ifc(empty)
    txt = tmp_path / "model.txt"
    txt.write_text(small_ifc.read_text())
    with pytest.raises(IfcLoadError, match="extension"):
        load_ifc(txt)
    with pytest.raises(IfcLoadError, match="larger"):
        load_ifc(small_ifc, max_size_mb=0.0001)


def test_empty_model_loads(empty_ifc):
    model = load_ifc(empty_ifc)
    assert len(model.by_type("IfcWall")) == 0
