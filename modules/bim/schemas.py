"""Normalized Building Data Model (BDM) produced by the M01 ingestion engine.

Pure pydantic: importing this module does NOT require IfcOpenShell, so the data model and the
validator can be used (and tested) anywhere. All lengths are in metres unless a field name says
otherwise. Missing information is kept as ``None`` / empty and reported by the validator; it is
never invented.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BDM_SCHEMA_VERSION = "1.0"

Category = Literal[
    "project", "site", "building", "storey", "space",
    "wall", "curtain_wall", "door", "window", "slab", "column",
]  # fmt: skip
RelationKind = Literal[
    "aggregates",    # parent -> child in the spatial decomposition (IfcRelAggregates)
    "contains",      # spatial container -> element (IfcRelContainedInSpatialStructure)
    "hosted_in",     # door/window -> host element, through an opening (Voids + Fills)
    "bounds_space",  # element -> space it bounds (IfcRelSpaceBoundary)
    "connects_to",   # element -> element (IfcRelConnectsPathElements)
]  # fmt: skip
Severity = Literal["error", "warning", "info"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Placement(_M):
    """Absolute (world) placement, translation converted to metres."""

    origin_m: tuple[float, float, float]
    matrix_m: list[list[float]]  # 4x4 row-major, translation in metres
    rotation_z_deg: float  # heading of the local X axis around world Z


class GeometryRef(_M):
    """Pointer to the geometry. M01 does not tessellate; M02 will key meshes by ``ref_id``."""

    ref_id: str | None  # = GlobalId (stable key for M02 meshes)
    has_representation: bool
    source: Literal["occurrence", "type"] | None = None
    representation_identifiers: list[str] = Field(default_factory=list)
    representation_types: list[str] = Field(default_factory=list)


class MaterialRef(_M):
    name: str | None
    category: str | None = None


class SpatialContext(_M):
    container_global_id: str | None = None
    container_class: str | None = None
    container_name: str | None = None
    storey_global_id: str | None = None
    storey_name: str | None = None
    storey_elevation_m: float | None = None
    building_global_id: str | None = None
    site_global_id: str | None = None
    # spaces the element is located in or bounds (containment or IfcRelSpaceBoundary)
    space_global_ids: list[str] = Field(default_factory=list)


class BimElement(_M):
    global_id: str | None
    ifc_class: str
    category: Category
    ifc_step_id: int | None = None  # local to the file, NOT stable across exports
    name: str | None = None
    object_type: str | None = None
    predefined_type: str | None = None
    description: str | None = None
    tag: str | None = None
    long_name: str | None = None
    type_name: str | None = None
    type_global_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)  # raw scalar IFC attributes
    dimensions_m: dict[str, float] = Field(default_factory=dict)  # e.g. OverallWidth
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)  # property sets
    quantities: dict[str, dict[str, Any]] = Field(default_factory=dict)  # Qto_*, raw IFC units
    materials: list[MaterialRef] = Field(default_factory=list)
    spatial: SpatialContext = Field(default_factory=SpatialContext)
    placement: Placement | None = None
    geometry: GeometryRef
    source_ifc_schema: str


class Relationship(_M):
    kind: RelationKind
    source_global_id: str | None
    target_global_id: str | None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpatialNode(_M):
    global_id: str | None
    ifc_class: str
    name: str | None = None
    children: list[SpatialNode] = Field(default_factory=list)
    element_global_ids: list[str] = Field(default_factory=list)  # contained, extracted elements


class SourceInfo(_M):
    file_name: str
    sha256: str
    size_bytes: int
    ifc_schema: str  # e.g. IFC2X3, IFC4
    ifc_schema_identifier: str | None = None  # e.g. IFC4X3_ADD2 when available
    application: str | None = None  # authoring application from the file header, if any


class GlobalIdAudit(_M):
    """GlobalId audit over ALL rooted entities of the file (not only extracted elements)."""

    total_rooted: int = 0
    duplicates: dict[str, int] = Field(default_factory=dict)  # global_id -> occurrences (>1)
    malformed: list[str] = Field(default_factory=list)
    missing: int = 0


class Provenance(_M):
    extractor_version: str
    ifcopenshell_version: str | None = None
    extracted_at: str  # ISO-8601 UTC
    duration_s: float


class ValidationIssue(_M):
    severity: Severity
    code: str
    message: str
    global_id: str | None = None
    ifc_class: str | None = None
    category: str | None = None


class ValidationReport(_M):
    is_valid: bool  # True iff there is no error-level issue
    issues: list[ValidationIssue] = Field(default_factory=list)
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
    counts_by_code: dict[str, int] = Field(default_factory=dict)
    # category -> {attribute -> fraction of elements of that category that have it (0..1)}
    completeness: dict[str, dict[str, float]] = Field(default_factory=dict)


class BuildingModel(_M):
    schema_version: str = BDM_SCHEMA_VERSION
    building_id: str
    source: SourceInfo
    project_name: str | None = None
    length_unit_scale_m: float = 1.0  # metres per IFC length unit of the source file
    elements: list[BimElement] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    spatial_tree: SpatialNode | None = None
    counts: dict[str, int] = Field(default_factory=dict)  # per category
    ifc_class_counts: dict[str, int] = Field(default_factory=dict)  # per exact IFC class
    global_id_audit: GlobalIdAudit | None = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Provenance | None = None
    validation: ValidationReport | None = None

    # ---- convenience accessors (read-only) -------------------------------------------------
    def by_category(self, category: str) -> list[BimElement]:
        return [e for e in self.elements if e.category == category]

    def get(self, global_id: str) -> BimElement | None:
        return next((e for e in self.elements if e.global_id == global_id), None)

    def find_by_name(self, name: str) -> list[BimElement]:
        return [e for e in self.elements if e.name == name]


SpatialNode.model_rebuild()
