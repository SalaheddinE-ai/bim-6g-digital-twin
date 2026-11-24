"""JSON export and human-readable extraction report. Pure Python."""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import BuildingModel


def export_json(model: BuildingModel, path: Path | str) -> Path:
    """Write the full Building Data Model (incl. validation) as UTF-8 JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return out


def load_json(path: Path | str) -> BuildingModel:
    return BuildingModel.model_validate_json(Path(path).read_text(encoding="utf-8"))


def build_extraction_report(model: BuildingModel) -> str:
    """Markdown report: source, element counts, validation summary, completeness, issues."""
    v = model.validation
    lines: list[str] = []
    a = lines.append
    a(f"# IFC extraction report - {model.source.file_name}")
    a("")
    a(f"- Building ID: `{model.building_id}`")
    a(f"- IFC schema: {model.source.ifc_schema}  (file SHA-256: `{model.source.sha256[:16]}...`)")
    a(f"- Project: {model.project_name or '<unnamed>'}")
    a(f"- Length unit scale: {model.length_unit_scale_m} m per IFC unit")
    if model.provenance:
        p = model.provenance
        a(
            f"- Extracted by extractor {p.extractor_version}, IfcOpenShell "
            f"{p.ifcopenshell_version}, in {p.duration_s:.2f} s ({p.extracted_at})"
        )
    a(
        f"- Validation: **{'VALID' if v and v.is_valid else 'INVALID'}**"
        if v
        else "- Validation: n/a"
    )
    a("")
    a("## Element counts")
    a("")
    a("| Category | Count |")
    a("|---|---:|")
    for cat, n in model.counts.items():
        a(f"| {cat} | {n} |")
    a("")
    if model.ifc_class_counts:
        a("Exact IFC classes: " + ", ".join(f"{k}={n}" for k, n in model.ifc_class_counts.items()))
        a("")
    if v:
        a("## Validation summary")
        a("")
        for sev in ("error", "warning", "info"):
            a(f"- {sev}: {v.counts_by_severity.get(sev, 0)}")
        a("")
        if v.counts_by_code:
            a("| Issue code | Count |")
            a("|---|---:|")
            for code, n in v.counts_by_code.items():
                a(f"| {code} | {n} |")
            a("")
        a("## Attribute completeness (share of elements that have the attribute)")
        a("")
        cols = ["name", "object_type", "properties", "materials", "placement", "geometry",
                "spatial_container"]  # fmt: skip
        a("| Category | " + " | ".join(cols) + " |")
        a("|---|" + "---:|" * len(cols))
        for cat, row in v.completeness.items():
            a(f"| {cat} | " + " | ".join(f"{row.get(c, 0):.0%}" for c in cols) + " |")
        a("")
        errs = [i for i in v.issues if i.severity == "error"]
        if errs:
            a("## Errors")
            a("")
            for i in errs[:50]:
                a(f"- `{i.code}` {i.message}")
            a("")
    if model.warnings:
        a("## Extraction warnings")
        a("")
        for w in model.warnings:
            a(f"- {w}")
        a("")
    a("_Values come from the IFC file only. Nothing was inferred or invented; missing data is_")
    a("_reported above. Geometry is referenced, not tessellated (that is M02)._")
    return "\n".join(lines) + "\n"
