"""Validation of a Building Data Model. Pure Python (no IfcOpenShell).

Reports problems; never repairs or invents data.
"""

from __future__ import annotations

import re
from collections import Counter

from .schemas import (
    BimElement,
    BuildingModel,
    GlobalIdAudit,
    Severity,
    ValidationIssue,
    ValidationReport,
)

# IFC GlobalId: 22 chars, base-64 alphabet of buildingSMART, first char encodes 2 bits (0-3).
GLOBAL_ID_RE = re.compile(r"^[0-3][0-9A-Za-z_$]{21}$")

# Categories that must carry a material / geometry to be useful downstream (M02, M04).
# Curtain walls are aggregates: their geometry/material live in the aggregated parts (plates,
# members, panels), which M01 does not extract. So they are not required to carry their own.
_NEEDS_MATERIAL = {"wall", "door", "window", "slab", "column"}
_NEEDS_GEOMETRY = {"wall", "door", "window", "slab", "column"}
_NON_SPATIAL = {"wall", "curtain_wall", "door", "window", "slab", "column"}
_HOSTED = {"door", "window"}


def audit_global_ids(global_ids: list[str | None]) -> GlobalIdAudit:
    """Audit a list of GlobalIds (None = missing)."""
    present = [g for g in global_ids if g]
    counts = Counter(present)
    return GlobalIdAudit(
        total_rooted=len(global_ids),
        duplicates={g: n for g, n in counts.items() if n > 1},
        malformed=sorted({g for g in counts if not GLOBAL_ID_RE.match(g)}),
        missing=len(global_ids) - len(present),
    )


def _issue(sev: Severity, code: str, msg: str, el: BimElement | None = None) -> ValidationIssue:
    return ValidationIssue(
        severity=sev,
        code=code,
        message=msg,
        global_id=el.global_id if el else None,
        ifc_class=el.ifc_class if el else None,
        category=el.category if el else None,
    )


def _label(el: BimElement) -> str:
    return f"{el.ifc_class} '{el.name or '<unnamed>'}' ({el.global_id})"


def _completeness(model: BuildingModel) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    cats = sorted({e.category for e in model.elements})
    for cat in cats:
        els = model.by_category(cat)
        n = len(els)
        checks = {
            "name": sum(1 for e in els if e.name),
            "object_type": sum(1 for e in els if e.object_type),
            "properties": sum(1 for e in els if e.properties),
            "materials": sum(1 for e in els if e.materials),
            "placement": sum(1 for e in els if e.placement is not None),
            "geometry": sum(1 for e in els if e.geometry.has_representation),
            "spatial_container": sum(1 for e in els if e.spatial.container_global_id),
        }
        out[cat] = {k: round(v / n, 4) for k, v in checks.items()}
    return out


def validate_building(model: BuildingModel) -> ValidationReport:
    issues: list[ValidationIssue] = []

    # ---- empty / structure -------------------------------------------------------------
    if not model.elements:
        issues.append(_issue("error", "EMPTY_MODEL", "No BIM elements could be extracted."))
    else:
        if not model.by_category("storey"):
            issues.append(_issue("warning", "NO_STOREYS", "Model has no IfcBuildingStorey."))
        if not model.by_category("space"):
            issues.append(_issue("info", "NO_SPACES", "Model has no IfcSpace (no rooms)."))
        if model.spatial_tree is None:
            issues.append(_issue("warning", "NO_SPATIAL_STRUCTURE", "No IfcProject hierarchy."))

    # ---- identifiers ---------------------------------------------------------------------
    audit = model.global_id_audit or audit_global_ids([e.global_id for e in model.elements])
    for gid, n in sorted(audit.duplicates.items()):
        issues.append(
            ValidationIssue(
                severity="error",
                code="DUPLICATE_GLOBAL_ID",
                message=f"GlobalId '{gid}' is used by {n} rooted entities.",
                global_id=gid,
            )
        )
    for gid in audit.malformed:
        issues.append(
            ValidationIssue(
                severity="error",
                code="MALFORMED_GLOBAL_ID",
                message=f"GlobalId '{gid}' is not a valid 22-character IFC GUID.",
                global_id=gid,
            )
        )
    if audit.missing:
        issues.append(
            _issue(
                "error", "MISSING_GLOBAL_ID", f"{audit.missing} rooted entities lack a GlobalId."
            )
        )
    for el in model.elements:
        if el.global_id is None:
            issues.append(
                _issue("error", "MISSING_GLOBAL_ID", f"{_label(el)} has no GlobalId.", el)
            )

    # ---- per-element completeness ---------------------------------------------------------
    for el in model.elements:
        if not el.name:
            issues.append(_issue("warning", "MISSING_NAME", f"{_label(el)} has no Name.", el))
        if el.category in _NON_SPATIAL and not el.spatial.container_global_id:
            issues.append(
                _issue("warning", "NO_SPATIAL_CONTAINER", f"{_label(el)} has no container.", el)
            )
        if el.category in _NEEDS_GEOMETRY and not el.geometry.has_representation:
            issues.append(
                _issue("warning", "MISSING_GEOMETRY", f"{_label(el)} has no representation.", el)
            )
        if el.category in _NEEDS_MATERIAL and not el.materials:
            issues.append(
                _issue("warning", "MISSING_MATERIAL", f"{_label(el)} has no material.", el)
            )
        if el.category != "project" and el.placement is None:
            issues.append(
                _issue("warning", "MISSING_PLACEMENT", f"{_label(el)} has no placement.", el)
            )
        if el.category in _NEEDS_MATERIAL and not el.properties:
            issues.append(
                _issue("info", "MISSING_PROPERTIES", f"{_label(el)} has no property sets.", el)
            )
        if el.category in _HOSTED:
            missing = [k for k in ("OverallWidth", "OverallHeight") if k not in el.dimensions_m]
            if missing:
                issues.append(
                    _issue(
                        "warning",
                        "MISSING_DIMENSIONS",
                        f"{_label(el)} lacks {', '.join(missing)}.",
                        el,
                    )
                )

    # ---- relationships ---------------------------------------------------------------------
    known = {e.global_id for e in model.elements if e.global_id}
    hosted_ids = {r.source_global_id for r in model.relationships if r.kind == "hosted_in"}
    for el in model.elements:
        if el.category in _HOSTED and el.global_id not in hosted_ids:
            issues.append(
                _issue(
                    "warning",
                    "NO_HOST_ELEMENT",
                    f"{_label(el)} is not hosted in a wall or curtain wall.",
                    el,
                )
            )
    for rel in model.relationships:
        for end in (rel.source_global_id, rel.target_global_id):
            if end is None or end not in known:
                issues.append(
                    _issue(
                        "warning",
                        "DANGLING_RELATIONSHIP",
                        f"Relationship '{rel.kind}' references {end!r}, which was not extracted.",
                    )
                )

    counts_sev = Counter(i.severity for i in issues)
    counts_code = Counter(i.code for i in issues)
    return ValidationReport(
        is_valid=counts_sev.get("error", 0) == 0,
        issues=issues,
        counts_by_severity=dict(counts_sev),
        counts_by_code=dict(sorted(counts_code.items())),
        completeness=_completeness(model),
    )
