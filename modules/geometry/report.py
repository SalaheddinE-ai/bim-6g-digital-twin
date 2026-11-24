"""Markdown validation report for a GeometryModel (pure)."""

from __future__ import annotations

from .schemas import GeometryModel


def build_geometry_report(gm: GeometryModel) -> str:
    cs, val = gm.coordinate_system, gm.validation
    lines = [
        f"# Geometry validation report - {gm.building_id}",
        "",
        f"- Source IFC SHA-256: `{gm.source_sha256}`",
        f"- Pipeline: {gm.provenance.pipeline_version if gm.provenance else '?'}",
        f"- Coordinates: {cs.units}, {cs.up_axis}-up, {cs.handedness}-handed; "
        f"origin offset {cs.origin_offset_m} (mode `{cs.recenter_mode}`)",
        f"- Valid (no error-level issue): **{val.is_valid if val else '?'}**",
        "",
        "> Material classes below are ASSUMPTIONS (IFC names / categories), never measurements.",
        "",
        "## Mesh status",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in sorted(gm.counts.get("status", {}).items())]
    lines += ["", "## By category", "", "| Category | Count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(gm.counts.get("category", {}).items())]
    rs = gm.counts.get("radio_scene", {})
    lines += [
        "",
        "## Radio scene membership",
        "",
        f"- included: {rs.get('included', 0)}, "
        f"excluded (duplicates, volumes): {rs.get('excluded', 0)}",
        "",
        "## Material assignment (assumptions)",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in sorted(gm.counts.get("material_status", {}).items())]
    lines += ["", "| Radio class | Elements |", "|---|---|"]
    lines += [
        f"| {k} | {v} |" for k, v in sorted(gm.counts.get("em_material", {}).items(), key=str)
    ]
    lines += ["", "## Issues by code", "", "| Code | Count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted((val.counts_by_code if val else {}).items())]
    errors = [i for i in gm.issues if i.severity == "error"]
    if errors:
        lines += ["", "## Errors", ""]
        lines += [f"- `{i.code}` {i.global_id} ({i.ifc_class}): {i.message}" for i in errors[:50]]
    dups = [m for m in gm.meshes if m.excluded_reason and m.role == "solid"]
    if dups:
        lines += ["", "## Excluded solids", ""]
        lines += [f"- {m.global_id} ({m.ifc_class}): {m.excluded_reason}" for m in dups[:50]]
    return "\n".join(lines) + "\n"
