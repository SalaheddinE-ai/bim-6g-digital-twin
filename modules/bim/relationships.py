"""IFC relationship traversal helpers (raw IfcOpenShell entities in, plain data out).

Uses the standard IFC inverse attributes (Decomposes, ContainedInStructure, FillsVoids,
VoidsElements, ProvidesBoundaries, ConnectedTo, IsDecomposedBy, ContainsElements). ``getattr``
defaults make the helpers tolerant of schema differences (IFC2X3 / IFC4 / IFC4X3).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .properties import global_id


def spatial_parent(obj: Any) -> tuple[Any, str] | None:
    """Next entity up the spatial structure and the relationship kind.

    Returns (parent, "contains") for IfcRelContainedInSpatialStructure or (parent, "aggregates")
    for IfcRelAggregates, or None.
    """
    for rel in getattr(obj, "ContainedInStructure", None) or ():
        if rel.RelatingStructure is not None:
            return rel.RelatingStructure, "contains"
    for rel in getattr(obj, "Decomposes", None) or ():
        if rel.RelatingObject is not None:
            return rel.RelatingObject, "aggregates"
    return None


def spatial_chain(obj: Any) -> list[Any]:
    """Ancestors from the nearest container up to the project (cycle-safe)."""
    chain: list[Any] = []
    seen = {obj.id()}
    cur = obj
    while True:
        nxt = spatial_parent(cur)
        if nxt is None or nxt[0].id() in seen:
            break
        cur = nxt[0]
        seen.add(cur.id())
        chain.append(cur)
    return chain


def children_of(obj: Any) -> Iterator[Any]:
    """Aggregated children (IsDecomposedBy)."""
    for rel in getattr(obj, "IsDecomposedBy", None) or ():
        yield from rel.RelatedObjects or ()


def contained_elements(obj: Any) -> Iterator[Any]:
    """Elements contained in a spatial structure element (ContainsElements)."""
    for rel in getattr(obj, "ContainsElements", None) or ():
        yield from rel.RelatedElements or ()


def host_elements(el: Any) -> list[tuple[Any, Any]]:
    """(host element, opening) pairs for a door/window: FillsVoids -> opening -> VoidsElements."""
    out: list[tuple[Any, Any]] = []
    for fill in getattr(el, "FillsVoids", None) or ():
        opening = fill.RelatingOpeningElement
        for void in getattr(opening, "VoidsElements", None) or ():
            if void.RelatingBuildingElement is not None:
                out.append((void.RelatingBuildingElement, opening))
    return out


def aggregate_hosts(el: Any) -> list[Any]:
    """Building elements (not spatial structure) that aggregate ``el``, e.g. an IfcCurtainWall
    whose panels are IfcDoor/IfcWindow. These are not linked by an opening (Voids/Fills)."""
    out: list[Any] = []
    for rel in getattr(el, "Decomposes", None) or ():
        parent = getattr(rel, "RelatingObject", None)
        if parent is not None and parent.is_a("IfcElement"):
            out.append(parent)
    return out


def space_boundaries(el: Any) -> list[tuple[Any, dict[str, Any]]]:
    """(space, attributes) for every IfcRelSpaceBoundary the element provides."""
    out: list[tuple[Any, dict[str, Any]]] = []
    for rel in getattr(el, "ProvidesBoundaries", None) or ():
        space = getattr(rel, "RelatingSpace", None)
        if space is None:
            continue
        attrs = {
            "physical_or_virtual": getattr(rel, "PhysicalOrVirtualBoundary", None),
            "internal_or_external": getattr(rel, "InternalOrExternalBoundary", None),
        }
        out.append((space, {k: str(v) for k, v in attrs.items() if v is not None}))
    return out


def path_connections(el: Any) -> list[tuple[Any, dict[str, Any]]]:
    """Outgoing IfcRelConnectsPathElements (wall-to-wall connections)."""
    out: list[tuple[Any, dict[str, Any]]] = []
    for rel in getattr(el, "ConnectedTo", None) or ():
        other = getattr(rel, "RelatedElement", None)
        if other is None:
            continue
        attrs = {
            "relating_connection_type": getattr(rel, "RelatingConnectionType", None),
            "related_connection_type": getattr(rel, "RelatedConnectionType", None),
        }
        out.append((other, {k: str(v) for k, v in attrs.items() if v is not None}))
    return out


__all__ = [
    "aggregate_hosts", "children_of", "contained_elements", "global_id", "host_elements",
    "path_connections", "space_boundaries", "spatial_chain", "spatial_parent",
]  # fmt: skip
