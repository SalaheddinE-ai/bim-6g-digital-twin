"""Geometry model produced by M02 (pure pydantic, JSON-serialisable). Meshes live in PLY files."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .materials import MaterialAssignment

GEOMETRY_SCHEMA_VERSION = "1.0"

Role = Literal["solid", "volume"]  # solids obstruct radio waves; volumes (IfcSpace) do not
MeshStatus = Literal["ok", "repaired", "invalid", "missing", "failed"]
Severity = Literal["error", "warning", "info"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoordinateSystem(_M):
    units: Literal["m"] = "m"
    up_axis: Literal["Z"] = "Z"
    handedness: Literal["right"] = "right"
    origin_offset_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    recenter_mode: str = "none"
    source_length_unit_scale_m: float = 1.0  # metres per IFC length unit of the source file
    description: str = (
        "IFC world coordinates (all placements applied, no map conversion). "
        "world_m = mesh_m + origin_offset_m"
    )


class GeometryIssue(_M):
    severity: Severity
    code: str
    message: str
    global_id: str | None = None
    key: str | None = None
    ifc_class: str | None = None


class MeshRecord(_M):
    key: str  # unique file stem: GlobalId (suffixed with the STEP id if the GlobalId repeats)
    global_id: str | None
    ifc_step_id: int | None = None
    ifc_class: str
    category: str
    role: Role
    status: MeshStatus
    mesh_file: str | None = None  # relative to the geometry directory
    n_vertices: int = 0
    n_faces: int = 0
    bbox_min_m: tuple[float, float, float] | None = None  # in the (offset) mesh frame
    bbox_max_m: tuple[float, float, float] | None = None
    area_m2: float | None = None
    volume_m3: float | None = None  # only for closed, consistently oriented meshes
    watertight: bool | None = None
    repairs: list[str] = Field(default_factory=list)
    material: MaterialAssignment | None = None
    include_in_radio_scene: bool = False
    excluded_reason: str | None = None
    issues: list[GeometryIssue] = Field(default_factory=list)


class GeometryValidation(_M):
    is_valid: bool  # True iff there is no error-level issue
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
    counts_by_code: dict[str, int] = Field(default_factory=dict)


class GeometryProvenance(_M):
    pipeline_version: str
    ifcopenshell_version: str | None = None
    created_at: str
    duration_s: float
    settings: dict = Field(default_factory=dict)


class GeometryModel(_M):
    schema_version: str = GEOMETRY_SCHEMA_VERSION
    building_id: str
    source_sha256: str
    coordinate_system: CoordinateSystem
    meshes: list[MeshRecord] = Field(default_factory=list)
    issues: list[GeometryIssue] = Field(default_factory=list)
    validation: GeometryValidation | None = None
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    provenance: GeometryProvenance | None = None

    def get(self, global_id: str) -> MeshRecord | None:
        return next((m for m in self.meshes if m.global_id == global_id), None)

    def radio_scene(self) -> list[MeshRecord]:
        return [m for m in self.meshes if m.include_in_radio_scene]
