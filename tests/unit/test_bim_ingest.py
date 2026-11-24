"""M01 ingest pipeline: storage, JSON export, report, rejection. Needs IfcOpenShell."""

import hashlib

import pytest

pytest.importorskip("ifcopenshell")
pytestmark = pytest.mark.ifc

from modules.bim.ingest import IfcLoadError, ingest_ifc  # noqa: E402
from modules.bim.report import load_json  # noqa: E402


def test_ingest_stores_original_json_and_report(small_ifc, tmp_path):
    res = ingest_ifc(small_ifc, tmp_path / "storage")
    assert res.model.building_id.startswith("bld_")
    assert res.ifc_path.name == "original.ifc"
    assert hashlib.sha256(res.ifc_path.read_bytes()).hexdigest() == res.model.source.sha256
    assert load_json(res.json_path) == res.model  # lossless JSON round trip
    report = res.report_path.read_text()
    assert "| wall | 5 |" in report and "| door | 3 |" in report


def test_ingest_is_idempotent_and_never_overwrites_original(small_ifc, tmp_path):
    a = ingest_ifc(small_ifc, tmp_path)
    before = a.ifc_path.stat().st_mtime_ns
    b = ingest_ifc(small_ifc, tmp_path)
    assert a.model.building_id == b.model.building_id
    assert b.ifc_path.stat().st_mtime_ns == before


def test_invalid_file_rejected_and_nothing_stored(tmp_path):
    bad = tmp_path / "bad.ifc"
    bad.write_text("nope")
    with pytest.raises(IfcLoadError):
        ingest_ifc(bad, tmp_path / "storage")
    assert not (tmp_path / "storage").exists()


def test_extraction_is_deterministic(small_ifc):
    a = ingest_ifc(small_ifc).model.model_dump(exclude={"provenance"})
    b = ingest_ifc(small_ifc).model.model_dump(exclude={"provenance"})
    assert a == b
