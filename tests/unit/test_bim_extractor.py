"""M01 extraction on the small IFC4 fixture. Needs IfcOpenShell."""

import pytest

pytest.importorskip("ifcopenshell")
pytestmark = pytest.mark.ifc

from modules.bim.ingest import ingest_ifc  # noqa: E402
from tests.fixtures.small_building import EXPECTED, GUIDS  # noqa: E402


def test_element_counts(small_model):
    assert small_model.counts == EXPECTED["counts"]
    assert small_model.ifc_class_counts["IfcWallStandardCase"] == 1
    assert small_model.ifc_class_counts["IfcWall"] == 4
    assert small_model.source.ifc_schema == "IFC4"


def test_walls(small_model):
    walls = {w.name: w for w in small_model.by_category("wall")}
    assert set(walls) == {"W_South", "W_North", "W_West", "W_East", "W_Part"}
    assert walls["W_South"].properties["Pset_WallCommon"]["IsExternal"] is True
    assert walls["W_South"].properties["Pset_WallCommon"]["FireRating"] == "1HR"
    assert walls["W_Part"].properties["Pset_WallCommon"]["IsExternal"] is False
    assert walls["W_Part"].attributes["Tag"] == "W-005"
    assert walls["W_Part"].object_type == "Basic Wall:Generic 200"
    assert all(w.geometry.has_representation for w in walls.values())
    assert walls["W_South"].geometry.representation_types == ["SweptSolid"]
    assert walls["W_South"].geometry.ref_id == GUIDS["W_South"]
    assert [m.name for m in walls["W_South"].materials] == ["Concrete"]


def test_doors(small_model):
    doors = {d.name: d for d in small_model.by_category("door")}
    assert set(doors) == {"D01", "D02", "D03"}
    d01 = doors["D01"]
    assert d01.dimensions_m == pytest.approx({"OverallHeight": 2.1, "OverallWidth": 0.9})
    assert d01.properties["Pset_DoorCommon"]["FireRating"] == "30min"
    assert [m.name for m in d01.materials] == ["Wood"]
    # unit conversion: project unit is mm -> placement in metres, heading 90 deg (ref dir = +Y)
    assert d01.placement.origin_m == pytest.approx((5.0, 2.5, 0.0))
    assert d01.placement.rotation_z_deg == pytest.approx(90.0)
    assert small_model.length_unit_scale_m == pytest.approx(0.001)
    assert not d01.geometry.has_representation  # fixture has no door geometry: reported, not faked


def test_door_host_and_space_relationships(small_model):
    hosted = {
        (r.source_global_id, r.target_global_id): r
        for r in small_model.relationships
        if r.kind == "hosted_in"
    }
    assert (GUIDS["D01"], GUIDS["W_Part"]) in hosted
    assert (
        hosted[(GUIDS["D01"], GUIDS["W_Part"])].attributes["opening_global_id"] == GUIDS["OpenD01"]
    )
    assert (GUIDS["D02"], GUIDS["W_South"]) in hosted
    assert (GUIDS["W01"], GUIDS["W_North"]) in hosted
    d01 = small_model.get(GUIDS["D01"])
    assert set(d01.spatial.space_global_ids) == {GUIDS["RoomA"], GUIDS["RoomB"]}  # between rooms
    d02 = small_model.get(GUIDS["D02"])
    assert d02.spatial.space_global_ids == [GUIDS["RoomA"]]


def test_curtain_wall_panel_door_is_hosted_via_aggregation(small_model):
    (cw,) = small_model.by_category("curtain_wall")
    assert cw.ifc_class == "IfcCurtainWall" and cw.name == "CW01"
    d03 = small_model.get(GUIDS["D03"])
    rel = next(r for r in small_model.relationships
               if r.kind == "hosted_in" and r.source_global_id == GUIDS["D03"])  # fmt: skip
    assert rel.target_global_id == GUIDS["CurtainWall"]
    assert rel.attributes["host_kind"] == "aggregate"
    # no direct containment: storey context is resolved through the curtain wall
    assert d03.spatial.container_global_id == GUIDS["CurtainWall"]
    assert d03.spatial.storey_name == "Ground Floor"
    assert "NO_HOST_ELEMENT" not in small_model.validation.counts_by_code
    assert "DANGLING_RELATIONSHIP" not in small_model.validation.counts_by_code
    opening_rel = next(r for r in small_model.relationships
                       if r.kind == "hosted_in" and r.source_global_id == GUIDS["D01"])  # fmt: skip
    assert opening_rel.attributes["host_kind"] == "opening"


def test_windows(small_model):
    (w01,) = small_model.by_category("window")
    assert w01.name == "W01"
    assert w01.dimensions_m == pytest.approx({"OverallHeight": 1.2, "OverallWidth": 1.5})
    assert w01.placement.origin_m == pytest.approx((7.5, 6.0, 1.0))
    assert [m.name for m in w01.materials] == ["Glass"]


def test_globalids_preserved(small_model):
    for key in ("W_South", "W_Part", "D01", "D02", "W01", "RoomA", "RoomB", "storey",
                "building", "site", "project", "Slab", "Column"):  # fmt: skip
        assert small_model.get(GUIDS[key]) is not None, key
    assert small_model.get(GUIDS["D01"]).name == "D01"
    assert small_model.global_id_audit.duplicates == {}
    assert small_model.global_id_audit.malformed == []


def test_spatial_hierarchy_and_context(small_model):
    tree = small_model.spatial_tree
    assert (tree.ifc_class, tree.name) == ("IfcProject", "Small Test Project")
    site = tree.children[0]
    building = site.children[0]
    storey = building.children[0]
    assert [n.ifc_class for n in (site, building, storey)] == [
        "IfcSite", "IfcBuilding", "IfcBuildingStorey",
    ]  # fmt: skip
    assert {c.name for c in storey.children} == {"Room A", "Room B"}
    assert GUIDS["D01"] in storey.element_global_ids
    assert (
        len(storey.element_global_ids) == 11
    )  # 5 walls + 2 doors + curtain wall + window + slab + column

    d01 = small_model.get(GUIDS["D01"])
    assert d01.spatial.container_global_id == GUIDS["storey"]
    assert d01.spatial.storey_name == "Ground Floor"
    assert d01.spatial.building_global_id == GUIDS["building"]
    assert d01.spatial.site_global_id == GUIDS["site"]
    room = small_model.get(GUIDS["RoomA"])  # spaces are aggregated, not "contained"
    assert room.spatial.container_global_id == GUIDS["storey"]
    kinds = {r.kind for r in small_model.relationships}
    assert {"aggregates", "contains", "hosted_in", "bounds_space"} <= kinds


def test_missing_properties_are_handled(small_model):
    col = small_model.get(GUIDS["Column"])
    assert col.name is None and col.properties == {} and col.materials == []
    codes = small_model.validation.counts_by_code
    assert {"MISSING_NAME", "MISSING_MATERIAL", "MISSING_GEOMETRY", "MISSING_PROPERTIES"} <= set(
        codes
    )
    assert small_model.validation.is_valid  # only warnings/info
    assert small_model.validation.completeness["door"]["materials"] == 1.0
    assert small_model.validation.completeness["column"]["materials"] == 0.0


def test_empty_model_is_handled(empty_ifc):
    res = ingest_ifc(empty_ifc)
    assert res.model.counts["wall"] == 0 and res.model.counts["project"] == 1
    assert res.model.validation.is_valid  # a project exists...
    assert {"NO_STOREYS", "NO_SPACES"} <= set(res.model.validation.counts_by_code)


def test_file_without_any_entities_is_reported_empty(no_entities_ifc):
    res = ingest_ifc(no_entities_ifc)
    assert sum(res.model.counts.values()) == 0
    assert res.model.spatial_tree is None
    assert not res.model.validation.is_valid
    assert "EMPTY_MODEL" in res.model.validation.counts_by_code


def test_duplicate_global_ids_detected(small_ifc, tmp_path):
    text = small_ifc.read_text().replace(GUIDS["D02"], GUIDS["D01"])
    p = tmp_path / "dup.ifc"
    p.write_text(text)
    res = ingest_ifc(p)
    assert res.model.global_id_audit.duplicates == {GUIDS["D01"]: 2}
    assert not res.model.validation.is_valid
    assert "DUPLICATE_GLOBAL_ID" in res.model.validation.counts_by_code


def test_malformed_global_id_detected(small_ifc, tmp_path):
    p = tmp_path / "bad.ifc"
    p.write_text(small_ifc.read_text().replace(GUIDS["D02"], "NOT-A-GUID"))
    res = ingest_ifc(p)
    assert "NOT-A-GUID" in res.model.global_id_audit.malformed
    assert not res.model.validation.is_valid
    assert "MALFORMED_GLOBAL_ID" in res.model.validation.counts_by_code
