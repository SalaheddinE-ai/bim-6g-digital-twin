import pytest
from pydantic import ValidationError

from backend.config import load_settings
from modules.geometry.report import build_geometry_report
from modules.geometry.schemas import (
    CoordinateSystem,
    GeometryIssue,
    GeometryModel,
    GeometryValidation,
    MeshRecord,
)


def _model():
    rec = MeshRecord(
        key="GID1", global_id="GID1", ifc_class="IfcWall", category="wall", role="solid",
        status="ok", mesh_file="meshes/GID1.ply", n_vertices=8, n_faces=12,
        bbox_min_m=(0, 0, 0), bbox_max_m=(1, 1, 1), include_in_radio_scene=True,
    )  # fmt: skip
    issue = GeometryIssue(severity="warning", code="X", message="m", global_id="GID1", key="GID1")
    return GeometryModel(
        building_id="bld_x", source_sha256="ab" * 32, coordinate_system=CoordinateSystem(),
        meshes=[rec], issues=[issue],
        validation=GeometryValidation(is_valid=True, counts_by_code={"X": 1}),
        counts={"status": {"ok": 1}, "category": {"wall": 1}},
    )  # fmt: skip


def test_geometry_model_json_round_trip():
    gm = _model()
    again = GeometryModel.model_validate_json(gm.model_dump_json())
    assert again == gm
    assert again.get("GID1").include_in_radio_scene and again.radio_scene()[0].key == "GID1"


def test_schema_rejects_unknown_fields_and_values():
    with pytest.raises(ValidationError):
        MeshRecord(key="k", global_id=None, ifc_class="IfcWall", category="wall", role="solid",
                   status="ok", surprise=1)  # fmt: skip
    with pytest.raises(ValidationError):
        MeshRecord(key="k", global_id=None, ifc_class="IfcWall", category="wall", role="solid",
                   status="great")  # fmt: skip


def test_report_contains_key_sections():
    text = build_geometry_report(_model())
    for needle in (
        "# Geometry validation report",
        "bld_x",
        "ASSUMPTIONS",
        "Mesh status",
        "Issues by code",
    ):
        assert needle in text


def test_geometry_settings_defaults_and_validation(monkeypatch):
    g = load_settings().geometry
    assert g.recenter == "auto" and g.duplicate_policy == "exclude" and g.weld_tolerance_m > 0
    monkeypatch.setenv("BIM6G_GEOMETRY__RECENTER", "none")
    assert load_settings().geometry.recenter == "none"
    for bad in ("BIM6G_GEOMETRY__RECENTER=sideways", "BIM6G_GEOMETRY__NUM_THREADS=0"):
        key, val = bad.split("=")
        monkeypatch.setenv(key, val)
        with pytest.raises(ValidationError):
            load_settings()
        monkeypatch.delenv(key)
