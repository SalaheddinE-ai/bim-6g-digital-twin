"""Attribute, property-set, material, placement and geometry-reference extraction.

Every function is defensive: a failure on one element yields an empty value (and a log line),
never an exception that aborts the whole file. Needs IfcOpenShell.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from .schemas import GeometryRef, MaterialRef, Placement

logger = logging.getLogger(__name__)

_SKIP_ATTRS = {"id", "type", "GlobalId"}
# Length-valued attributes (project units) exposed in metres as ``dimensions_m``.
LENGTH_ATTRS = ("OverallHeight", "OverallWidth")


def jsonable(value: Any) -> Any:
    """Convert IfcOpenShell values to JSON-safe Python values."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if hasattr(value, "is_a") and hasattr(value, "id"):  # entity_instance
        return f"{value.is_a()}#{value.id()}"
    return str(value)


def global_id(entity: Any) -> str | None:
    gid = getattr(entity, "GlobalId", None)
    return str(gid) if gid else None


def scalar_attributes(el: Any) -> dict[str, Any]:
    """Scalar (str/int/float/bool) IFC attributes of the entity, raw project units."""
    try:
        info = el.get_info()
    except Exception as exc:
        logger.warning("get_info failed for #%s: %s", el.id(), exc)
        return {}
    return {
        k: jsonable(v)
        for k, v in info.items()
        if k not in _SKIP_ATTRS and isinstance(v, (str, int, float, bool))
    }


def dimensions_m(el: Any, scale: float) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in LENGTH_ATTRS:
        val = getattr(el, name, None)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out[name] = float(val) * scale
    return out


def _clean_sets(sets: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(name): {str(k): jsonable(v) for k, v in props.items() if k != "id"}
        for name, props in sets.items()
    }


def property_sets(el: Any) -> dict[str, dict[str, Any]]:
    """Property sets (type-level sets are inherited by IfcOpenShell). Excludes quantities."""
    import ifcopenshell.util.element as ue

    try:
        return _clean_sets(ue.get_psets(el, psets_only=True))
    except Exception as exc:
        logger.warning("get_psets failed for #%s: %s", el.id(), exc)
        return {}


def quantity_sets(el: Any) -> dict[str, dict[str, Any]]:
    """Element quantity sets (Qto_*), raw IFC values in project units."""
    import ifcopenshell.util.element as ue

    try:
        return _clean_sets(ue.get_psets(el, qtos_only=True))
    except Exception as exc:
        logger.warning("get_psets(qtos) failed for #%s: %s", el.id(), exc)
        return {}


def materials(el: Any) -> list[MaterialRef]:
    import ifcopenshell.util.element as ue

    try:
        mats = ue.get_materials(el)
    except Exception as exc:
        logger.warning("get_materials failed for #%s: %s", el.id(), exc)
        return []
    out: list[MaterialRef] = []
    for m in mats or []:
        if not m.is_a("IfcMaterial"):
            continue
        cat = getattr(m, "Category", None)
        out.append(MaterialRef(name=m.Name, category=str(cat) if cat else None))
    return out


def type_info(el: Any) -> tuple[str | None, str | None]:
    import ifcopenshell.util.element as ue

    try:
        t = ue.get_type(el)
    except Exception:
        return None, None
    if t is None:
        return None, None
    return getattr(t, "Name", None), global_id(t)


def placement(el: Any, scale: float) -> Placement | None:
    """Absolute placement (PlacementRelTo chain resolved), translation in metres."""
    pl = getattr(el, "ObjectPlacement", None)
    if pl is None:
        return None
    try:
        import ifcopenshell.util.placement as up
        import numpy as np

        m = np.array(up.get_local_placement(pl), dtype=float)
        m[:3, 3] *= scale
        return Placement(
            origin_m=(float(m[0, 3]), float(m[1, 3]), float(m[2, 3])),
            matrix_m=m.tolist(),
            rotation_z_deg=float(math.degrees(math.atan2(m[1, 0], m[0, 0]))),
        )
    except Exception as exc:
        logger.warning("placement failed for #%s: %s", el.id(), exc)
        return None


def geometry_ref(el: Any) -> GeometryRef:
    """Describe where the geometry is, without tessellating it."""
    import ifcopenshell.util.element as ue

    def _reps(rep_container: Any) -> tuple[list[str], list[str]]:
        ids: list[str] = []
        types: list[str] = []
        for rep in getattr(rep_container, "Representations", None) or ():
            if getattr(rep, "RepresentationIdentifier", None):
                ids.append(str(rep.RepresentationIdentifier))
            if getattr(rep, "RepresentationType", None):
                types.append(str(rep.RepresentationType))
        return ids, types

    gid = global_id(el)
    rep = getattr(el, "Representation", None)
    if rep is not None:
        ids, types = _reps(rep)
        return GeometryRef(
            ref_id=gid, has_representation=True, source="occurrence",
            representation_identifiers=ids, representation_types=types,
        )  # fmt: skip
    try:
        t = ue.get_type(el)
    except Exception:
        t = None
    maps = getattr(t, "RepresentationMaps", None) if t is not None else None
    if maps:
        ids, types = [], []
        for m in maps:
            r = getattr(m, "MappedRepresentation", None)
            if r is not None:
                if getattr(r, "RepresentationIdentifier", None):
                    ids.append(str(r.RepresentationIdentifier))
                if getattr(r, "RepresentationType", None):
                    types.append(str(r.RepresentationType))
        return GeometryRef(
            ref_id=gid, has_representation=True, source="type",
            representation_identifiers=ids, representation_types=types,
        )  # fmt: skip
    return GeometryRef(ref_id=gid, has_representation=False)
