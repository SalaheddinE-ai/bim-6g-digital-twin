"""IfcOpenShell file -> normalized :class:`BuildingModel`. Needs IfcOpenShell."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from . import properties as props
from . import relationships as rels
from .schemas import (
    BimElement,
    BuildingModel,
    Provenance,
    Relationship,
    SourceInfo,
    SpatialContext,
    SpatialNode,
)
from .validator import audit_global_ids

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "1.0.0"

# category -> IFC classes (subtypes are included by IfcOpenShell's by_type, e.g.
# IfcWallStandardCase is returned for "IfcWall").
CATEGORY_CLASSES: dict[str, tuple[str, ...]] = {
    "project": ("IfcProject",),
    "site": ("IfcSite",),
    "building": ("IfcBuilding",),
    "storey": ("IfcBuildingStorey",),
    "space": ("IfcSpace",),
    "wall": ("IfcWall",),
    "curtain_wall": ("IfcCurtainWall",),
    "door": ("IfcDoor",),
    "window": ("IfcWindow",),
    "slab": ("IfcSlab",),
    "column": ("IfcColumn",),
}


def _unit_scale(ifc: Any, warnings: list[str]) -> float:
    """Metres per IFC length unit."""
    if not ifc.by_type("IfcUnitAssignment"):
        warnings.append("No IfcUnitAssignment: length unit assumed to be metres.")
        return 1.0
    try:
        import ifcopenshell.util.unit as uu

        return float(uu.calculate_unit_scale(ifc))
    except Exception as exc:
        warnings.append(f"Unit scale could not be determined ({exc}); assumed metres.")
        return 1.0


def _safe_by_type(ifc: Any, cls: str) -> list[Any]:
    try:
        return list(ifc.by_type(cls))
    except Exception:  # class not defined in this IFC schema
        return []


def _spatial_context(el: Any, chain: list[Any], scale: float) -> SpatialContext:
    ctx = SpatialContext()
    if chain:
        c = chain[0]
        ctx.container_global_id = props.global_id(c)
        ctx.container_class = c.is_a()
        ctx.container_name = getattr(c, "Name", None)
    for anc in [el, *chain]:
        cls = anc.is_a()
        if cls == "IfcBuildingStorey" and ctx.storey_global_id is None:
            ctx.storey_global_id = props.global_id(anc)
            ctx.storey_name = getattr(anc, "Name", None)
            elev = getattr(anc, "Elevation", None)
            ctx.storey_elevation_m = float(elev) * scale if isinstance(elev, (int, float)) else None
        elif cls == "IfcBuilding" and ctx.building_global_id is None:
            ctx.building_global_id = props.global_id(anc)
        elif cls == "IfcSite" and ctx.site_global_id is None:
            ctx.site_global_id = props.global_id(anc)
    return ctx


def _build_spatial_tree(project: Any, extracted: dict[int, str | None]) -> SpatialNode:
    visited: set[int] = set()

    def node(obj: Any) -> SpatialNode:
        visited.add(obj.id())
        children = [
            node(c) for c in rels.children_of(obj) if c.id() in extracted and c.id() not in visited
        ]
        contained = [
            extracted[e.id()]
            for e in rels.contained_elements(obj)
            if e.id() in extracted and extracted[e.id()]
        ]
        return SpatialNode(
            global_id=props.global_id(obj),
            ifc_class=obj.is_a(),
            name=getattr(obj, "Name", None),
            children=children,
            element_global_ids=[g for g in contained if g],
        )

    return node(project)


def extract_building(ifc: Any, source: SourceInfo, building_id: str) -> BuildingModel:
    """Convert an opened IFC file into a Building Data Model (without validation)."""
    t0 = perf_counter()
    warnings: list[str] = []
    scale = _unit_scale(ifc, warnings)
    schema = source.ifc_schema

    # 1. collect entities once (by STEP id), in category order
    selected: list[tuple[Any, str]] = []
    seen: set[int] = set()
    for category, classes in CATEGORY_CLASSES.items():
        for cls in classes:
            for ent in _safe_by_type(ifc, cls):
                if ent.id() not in seen:
                    seen.add(ent.id())
                    selected.append((ent, category))
    extracted_gid: dict[int, str | None] = {e.id(): props.global_id(e) for e, _ in selected}

    # 2. elements + relationships
    elements: list[BimElement] = []
    relationships: list[Relationship] = []
    rel_seen: set[tuple[str, str | None, str | None]] = set()

    def add_rel(kind: str, src: str | None, dst: str | None, **attrs: Any) -> None:
        key = (kind, src, dst)
        if key in rel_seen:
            return
        rel_seen.add(key)
        relationships.append(
            Relationship(kind=kind, source_global_id=src, target_global_id=dst, attributes=attrs)
        )  # type: ignore[arg-type]

    for ent, category in selected:
        gid = props.global_id(ent)
        chain = rels.spatial_chain(ent)
        spatial = _spatial_context(ent, chain, scale)

        parent = rels.spatial_parent(ent)
        if parent is not None:
            add_rel(parent[1], props.global_id(parent[0]), gid)

        boundaries = rels.space_boundaries(ent)
        space_ids = [spatial.container_global_id] if (
            chain and chain[0].is_a("IfcSpace") and spatial.container_global_id
        ) else []  # fmt: skip
        for space, attrs in boundaries:
            sgid = props.global_id(space)
            add_rel("bounds_space", gid, sgid, **attrs)
            if sgid and sgid not in space_ids:
                space_ids.append(sgid)
        spatial.space_global_ids = space_ids

        for host, opening in rels.host_elements(ent):
            add_rel(
                "hosted_in", gid, props.global_id(host),
                host_kind="opening",
                opening_global_id=props.global_id(opening),
                opening_name=getattr(opening, "Name", None),
            )  # fmt: skip
        if category in ("door", "window"):  # e.g. curtain-wall panels modelled as doors
            for host in rels.aggregate_hosts(ent):
                add_rel("hosted_in", gid, props.global_id(host), host_kind="aggregate")
        for other, attrs in rels.path_connections(ent):
            add_rel("connects_to", gid, props.global_id(other), **attrs)

        type_name, type_gid = props.type_info(ent)
        elements.append(
            BimElement(
                global_id=gid,
                ifc_class=ent.is_a(),
                category=category,  # type: ignore[arg-type]
                ifc_step_id=ent.id(),
                name=getattr(ent, "Name", None),
                object_type=getattr(ent, "ObjectType", None),
                predefined_type=_str_or_none(getattr(ent, "PredefinedType", None)),
                description=getattr(ent, "Description", None),
                tag=getattr(ent, "Tag", None),
                long_name=getattr(ent, "LongName", None),
                type_name=type_name,
                type_global_id=type_gid,
                attributes=props.scalar_attributes(ent),
                dimensions_m=props.dimensions_m(ent, scale),
                properties=props.property_sets(ent),
                quantities=props.quantity_sets(ent),
                materials=props.materials(ent),
                spatial=spatial,
                placement=props.placement(ent, scale),
                geometry=props.geometry_ref(ent),
                source_ifc_schema=schema,
            )
        )

    # 3. spatial tree
    projects = [e for e, c in selected if c == "project"]
    tree = None
    if projects:
        if len(projects) > 1:
            warnings.append(f"{len(projects)} IfcProject found; spatial tree uses the first.")
        tree = _build_spatial_tree(projects[0], extracted_gid)

    # 4. audit of ALL rooted entities (duplicates are only visible here)
    audit = audit_global_ids([props.global_id(e) for e in _safe_by_type(ifc, "IfcRoot")])

    counts = Counter(e.category for e in elements)
    model = BuildingModel(
        building_id=building_id,
        source=source,
        project_name=getattr(projects[0], "Name", None) if projects else None,
        length_unit_scale_m=scale,
        elements=elements,
        relationships=relationships,
        spatial_tree=tree,
        counts={c: counts.get(c, 0) for c in CATEGORY_CLASSES},
        ifc_class_counts=dict(sorted(Counter(e.ifc_class for e in elements).items())),
        global_id_audit=audit,
        warnings=warnings,
        provenance=Provenance(
            extractor_version=EXTRACTOR_VERSION,
            ifcopenshell_version=_ifcopenshell_version(),
            extracted_at=datetime.now(UTC).isoformat(timespec="seconds"),
            duration_s=perf_counter() - t0,
        ),
    )
    logger.info("Extracted %d elements, %d relationships", len(elements), len(relationships))
    return model


def _str_or_none(v: Any) -> str | None:
    return str(v) if v is not None else None


def _ifcopenshell_version() -> str | None:
    try:
        import ifcopenshell

        return str(ifcopenshell.version)
    except Exception:
        return None
