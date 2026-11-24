"""M01 acceptance on REAL IFC files in tests/fixtures/real_ifc/ (skipped if none present).

Model-agnostic checks: the extraction must agree with what IfcOpenShell itself reports.
"""

from pathlib import Path

import pytest

pytest.importorskip("ifcopenshell")
pytestmark = [pytest.mark.integration, pytest.mark.ifc]

import ifcopenshell  # noqa: E402

from modules.bim.ingest import ingest_ifc  # noqa: E402
from modules.bim.report import load_json  # noqa: E402

REAL = sorted((Path(__file__).parents[1] / "fixtures" / "real_ifc").glob("*.ifc"))


@pytest.fixture(scope="module", params=REAL, ids=lambda p: p.name)
def real(request, tmp_path_factory):
    res = ingest_ifc(request.param, tmp_path_factory.mktemp("storage"))
    return request.param, res


@pytest.mark.skipif(not REAL, reason="no real IFC files in tests/fixtures/real_ifc")
def test_real_ifc_becomes_validated_model(real):
    path, res = real
    m = res.model
    assert m.validation is not None
    assert m.counts["project"] >= 1
    assert sum(m.counts.values()) > 1
    assert not [i for i in m.validation.issues if i.code == "EMPTY_MODEL"]
    assert load_json(res.json_path) == m


@pytest.mark.skipif(not REAL, reason="no real IFC files in tests/fixtures/real_ifc")
def test_real_ifc_counts_and_globalids_match_ifcopenshell(real):
    path, res = real
    raw = ifcopenshell.open(str(path))
    pairs = [
        ("wall", "IfcWall"), ("door", "IfcDoor"), ("window", "IfcWindow"),
        ("curtain_wall", "IfcCurtainWall"), ("slab", "IfcSlab"), ("column", "IfcColumn"),
        ("space", "IfcSpace"), ("storey", "IfcBuildingStorey"),
    ]  # fmt: skip
    for category, cls in pairs:
        raw_ids = sorted(e.GlobalId for e in raw.by_type(cls))
        got_ids = sorted(e.global_id for e in res.model.by_category(category))
        assert got_ids == raw_ids, category


@pytest.mark.skipif(not REAL, reason="no real IFC files in tests/fixtures/real_ifc")
def test_real_ifc_relationships_reference_known_elements_or_are_reported(real):
    _, res = real
    m = res.model
    known = {e.global_id for e in m.elements}
    dangling = [
        r
        for r in m.relationships
        if r.source_global_id not in known or r.target_global_id not in known
    ]
    reported = m.validation.counts_by_code.get("DANGLING_RELATIONSHIP", 0)
    assert reported >= len(dangling)  # every dangling reference is surfaced by the validator


@pytest.mark.skipif(not REAL, reason="no real IFC files in tests/fixtures/real_ifc")
def test_real_ifc_hosts_are_resolved_or_reported(real):
    """Every door/window is either hosted (opening or aggregate) or explicitly reported."""
    _, res = real
    m = res.model
    hosted = {r.source_global_id for r in m.relationships if r.kind == "hosted_in"}
    orphans = [e for e in m.elements if e.category in ("door", "window")
               and e.global_id not in hosted]  # fmt: skip
    assert len(orphans) == m.validation.counts_by_code.get("NO_HOST_ELEMENT", 0)
