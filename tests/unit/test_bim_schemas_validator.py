"""M01 data model + validator on synthetic models (pure Python, no IfcOpenShell)."""

import pytest
from pydantic import ValidationError

from modules.bim.report import build_extraction_report, export_json, load_json
from modules.bim.schemas import (
    BimElement,
    BuildingModel,
    GeometryRef,
    MaterialRef,
    Placement,
    Relationship,
    SourceInfo,
    SpatialContext,
)
from modules.bim.validator import GLOBAL_ID_RE, audit_global_ids, validate_building

G = [f"{i}" + "A" * 21 for i in range(4)]  # four valid, distinct GlobalIds (first char 0-3)


def element(gid, category="wall", *, name="X", material=True, geometry=True, container="C1",
            props=True, placement=True, dims=None):  # fmt: skip
    return BimElement(
        global_id=gid,
        ifc_class="IfcWall" if category == "wall" else "Ifc" + category.title(),
        category=category,
        name=name,
        properties={"Pset": {"a": 1}} if props else {},
        materials=[MaterialRef(name="Concrete")] if material else [],
        spatial=SpatialContext(container_global_id=container),
        placement=Placement(origin_m=(0, 0, 0), matrix_m=[[1.0] * 4] * 4, rotation_z_deg=0.0)
        if placement else None,
        geometry=GeometryRef(ref_id=gid, has_representation=geometry),
        dimensions_m=dims or {},
        source_ifc_schema="IFC4",
    )  # fmt: skip


def model(elements, relationships=None, **kw):
    return BuildingModel(
        building_id="bld_test",
        source=SourceInfo(file_name="t.ifc", sha256="0" * 64, size_bytes=1, ifc_schema="IFC4"),
        elements=elements,
        relationships=relationships or [],
        **kw,
    )


def codes(report):
    return set(report.counts_by_code)


def test_global_id_regex():
    assert GLOBAL_ID_RE.match("2ud2oj6xHSCff8I8_5tZ3c")
    assert not GLOBAL_ID_RE.match("short")
    assert not GLOBAL_ID_RE.match("9" + "A" * 21)  # first char must be 0-3
    assert not GLOBAL_ID_RE.match("0" + "A" * 20 + "!")


def test_empty_model_is_error():
    rep = validate_building(model([]))
    assert not rep.is_valid and "EMPTY_MODEL" in codes(rep)


def test_complete_model_has_no_errors():
    els = [
        element(G[0], "storey", container=None, material=False, geometry=False),
        element(G[1], "wall"),
    ]
    rep = validate_building(model(els))
    assert rep.is_valid
    assert rep.counts_by_severity.get("error", 0) == 0
    assert rep.completeness["wall"]["materials"] == 1.0


def test_missing_attributes_are_reported_not_invented():
    els = [element(G[1], "wall", name=None, material=False, geometry=False, container=None,
                   props=False, placement=False)]  # fmt: skip
    rep = validate_building(model(els))
    assert {"MISSING_NAME", "MISSING_MATERIAL", "MISSING_GEOMETRY", "NO_SPATIAL_CONTAINER",
            "MISSING_PLACEMENT", "MISSING_PROPERTIES"} <= codes(rep)  # fmt: skip
    assert rep.is_valid  # warnings/info only
    assert rep.completeness["wall"]["name"] == 0.0


def test_duplicate_and_malformed_ids_are_errors():
    els = [element(G[1]), element(G[1]), element("bad-id")]
    rep = validate_building(model(els))
    assert not rep.is_valid
    assert {"DUPLICATE_GLOBAL_ID", "MALFORMED_GLOBAL_ID"} <= codes(rep)


def test_missing_global_id_is_error():
    rep = validate_building(model([element(None)]))
    assert not rep.is_valid and "MISSING_GLOBAL_ID" in codes(rep)


def test_audit_global_ids():
    a = audit_global_ids([G[0], G[0], "oops", None])
    assert a.total_rooted == 4 and a.duplicates == {G[0]: 2}
    assert a.malformed == ["oops"] and a.missing == 1


def test_door_needs_host_and_dimensions_and_dangling_relationship():
    door = element(G[2], "door")
    rep = validate_building(model([door, element(G[1], "wall")]))
    assert {"NO_HOST_ELEMENT", "MISSING_DIMENSIONS"} <= codes(rep)

    ok = element(G[2], "door", dims={"OverallWidth": 0.9, "OverallHeight": 2.1})
    rel = Relationship(kind="hosted_in", source_global_id=G[2], target_global_id=G[1])
    rep = validate_building(model([ok, element(G[1], "wall")], [rel]))
    assert "NO_HOST_ELEMENT" not in codes(rep) and "DANGLING_RELATIONSHIP" not in codes(rep)

    bad = Relationship(kind="hosted_in", source_global_id=G[2], target_global_id=G[3])
    rep = validate_building(model([ok], [bad]))
    assert "DANGLING_RELATIONSHIP" in codes(rep)


def test_schema_forbids_unknown_fields_and_bad_category():
    with pytest.raises(ValidationError):
        BimElement(global_id=G[0], ifc_class="IfcWall", category="spaceship",
                   geometry=GeometryRef(ref_id=None, has_representation=False),
                   source_ifc_schema="IFC4")  # fmt: skip
    with pytest.raises(ValidationError):
        Relationship(kind="contains", source_global_id=None, target_global_id=None, bogus=1)


def test_json_roundtrip_and_report(tmp_path):
    m = model([element(G[1])], counts={"wall": 1})
    m.validation = validate_building(m)
    path = export_json(m, tmp_path / "sub" / "building.json")
    assert load_json(path) == m
    text = build_extraction_report(m)
    assert "| wall | 1 |" in text and "Validation" in text


def test_curtain_wall_aggregate_needs_no_own_geometry_or_material():
    cw = element(G[1], "curtain_wall", material=False, geometry=False, props=False)
    rep = validate_building(model([cw]))
    assert not {"MISSING_GEOMETRY", "MISSING_MATERIAL"} & codes(rep)
