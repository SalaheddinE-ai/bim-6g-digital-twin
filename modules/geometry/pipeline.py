"""M02 pipeline: Building Data Model (M01) + original IFC -> validated meshes + manifest.

Storage (under ``storage_dir``)::

    geometry/<building_id>/geometry.json           GeometryModel (manifest, validation, materials)
    geometry/<building_id>/meshes/<key>.ply        one binary PLY per element (mesh frame, metres)
    geometry/<building_id>/validation_report.md    human-readable report
"""

from __future__ import annotations

import logging
import shutil
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from backend.config import PROJECT_ROOT, GeometrySettings
from modules.bim.parser import load_ifc
from modules.bim.schemas import BimElement, BuildingModel

from . import meshops
from .materials import MaterialMapper
from .schemas import (
    CoordinateSystem,
    GeometryIssue,
    GeometryModel,
    GeometryProvenance,
    GeometryValidation,
    MeshRecord,
)
from .tessellate import RawMesh, tessellate_with_ifcopenshell

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "M02-1.0"
GEOMETRY_CATEGORIES = ("wall", "curtain_wall", "door", "window", "slab", "column", "space")
# The BIM placement origin only lies on/near the element for these categories. Revit exports put
# slabs, columns and spaces on a shared anchor and carry the real position in the representation
# (verified on the real file: 0 mismatches for these, 250 false alarms for the others).
PLACEMENT_CHECK_CATEGORIES = ("wall", "door", "window")
Tessellator = Callable[..., tuple[dict[int, RawMesh], dict[int, str]]]


@dataclass
class GeometryResult:
    model: GeometryModel
    meshes: dict[str, tuple[np.ndarray, np.ndarray]]  # record key -> (vertices, faces), mesh frame
    geometry_dir: Path | None = None
    geometry_path: Path | None = None
    report_path: Path | None = None


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _record_keys(elements: list[BimElement]) -> list[str]:
    counts = Counter(e.global_id for e in elements if e.global_id)
    keys = []
    for e in elements:
        if e.global_id and counts[e.global_id] == 1:
            keys.append(e.global_id)
        else:
            keys.append(f"{e.global_id or 'noid'}__{e.ifc_step_id}")
    return keys


def _issue(sev, code, msg, rec: MeshRecord) -> GeometryIssue:
    return GeometryIssue(
        severity=sev, code=code, message=msg, global_id=rec.global_id, key=rec.key,
        ifc_class=rec.ifc_class,
    )  # fmt: skip


def _choose_offset(
    meshes: dict[str, tuple[np.ndarray, np.ndarray]], settings: GeometrySettings
) -> tuple[float, float, float]:
    if not meshes or settings.recenter == "none":
        return (0.0, 0.0, 0.0)
    lo = np.min([v.min(axis=0) for v, _ in meshes.values()], axis=0)
    hi = np.max([v.max(axis=0) for v, _ in meshes.values()], axis=0)
    if settings.recenter == "bbox_min":
        return tuple(float(x) for x in lo)  # type: ignore[return-value]
    if max(np.abs(lo).max(), np.abs(hi).max()) > settings.recenter_threshold_m:  # auto
        return tuple(float(x) for x in np.round((lo + hi) / 2.0))  # type: ignore[return-value]
    return (0.0, 0.0, 0.0)


def build_geometry(
    model: BuildingModel,
    ifc_path: Path | str,
    *,
    storage_dir: Path | str | None = None,
    settings: GeometrySettings | None = None,
    mapper: MaterialMapper | None = None,
    tessellator: Tessellator | None = None,
    ifc: Any = None,
) -> GeometryResult:
    t0 = time.perf_counter()
    settings = settings or GeometrySettings()
    mapper = mapper or MaterialMapper.from_file(_resolve(settings.materials_file))
    tessellate = tessellator or tessellate_with_ifcopenshell
    ifc = ifc if ifc is not None else load_ifc(ifc_path)

    elements = [e for e in model.elements if e.category in GEOMETRY_CATEGORIES]
    keys = _record_keys(elements)
    wanted = [e.ifc_step_id for e in elements if e.geometry.has_representation and e.ifc_step_id]
    raw, failures = tessellate(ifc, wanted, settings.num_threads)

    records: list[MeshRecord] = []
    meshes: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for e, key in zip(elements, keys, strict=True):
        rec = MeshRecord(
            key=key, global_id=e.global_id, ifc_step_id=e.ifc_step_id, ifc_class=e.ifc_class,
            category=e.category, role="volume" if e.category == "space" else "solid",
            status="missing",
        )  # fmt: skip
        records.append(rec)
        if not e.geometry.has_representation:
            if e.category == "curtain_wall":
                rec.issues.append(
                    _issue("info", "NO_OWN_GEOMETRY", "curtain wall without own geometry", rec)
                )
            else:
                rec.issues.append(_issue("warning", "MISSING_GEOMETRY", "no representation", rec))
            continue
        if e.ifc_step_id not in raw:
            rec.status = "failed"
            why = failures.get(e.ifc_step_id or -1, "no mesh produced")
            rec.issues.append(_issue("error", "TESSELLATION_FAILED", why, rec))
            continue
        try:
            v, f = meshops.as_mesh(raw[e.ifc_step_id].vertices, raw[e.ifc_step_id].faces)
            problems = meshops.validate_raw(v, f)
        except meshops.MeshError as exc:
            problems = [("error", "MALFORMED_MESH", str(exc))]
        if problems:
            rec.status = "invalid"
            rec.issues += [_issue(s, c, m, rec) for s, c, m in problems]
            continue
        clean = meshops.clean_mesh(
            v, f, weld_tol=settings.weld_tolerance_m, min_face_area=settings.min_face_area_m2
        )
        rec.issues += [_issue(s, c, m, rec) for s, c, m in clean.issues]
        if any(s == "error" for s, _, _ in clean.issues):
            rec.status = "invalid"
            continue
        rec.status = "repaired" if clean.repairs else "ok"
        rec.repairs, rec.watertight = clean.repairs, clean.watertight
        rec.volume_m3, rec.area_m2 = clean.volume_m3, clean.area_m2
        meshes[key] = (clean.vertices, clean.faces)
        if e.placement is not None and e.category in PLACEMENT_CHECK_CATEGORIES:
            # consistency of M01 placement (metres) with the mesh (metres)
            dist = meshops.point_to_aabb_distance(
                e.placement.origin_m, clean.vertices.min(axis=0), clean.vertices.max(axis=0)
            )
            if dist > settings.placement_tolerance_m:
                rec.issues.append(
                    _issue("warning", "PLACEMENT_MISMATCH",
                           f"BIM placement is {dist:.2f} m away from the mesh bounding box", rec)
                )  # fmt: skip

    # ---- coordinate normalisation (units are already metres; optional recentring) -------------
    offset = _choose_offset(meshes, settings)
    if any(offset):
        shift = np.asarray(offset)
        meshes = {k: (v - shift, f) for k, (v, f) in meshes.items()}
    by_key = {r.key: r for r in records}
    for key, (v, f) in meshes.items():
        rec = by_key[key]
        rec.n_vertices, rec.n_faces = len(v), len(f)
        rec.bbox_min_m = tuple(float(x) for x in v.min(axis=0))  # type: ignore[assignment]
        rec.bbox_max_m = tuple(float(x) for x in v.max(axis=0))  # type: ignore[assignment]

    # ---- coincident duplicate solids (would double-count attenuation) --------------------------
    seen: dict[str, str] = {}
    for rec in records:
        if rec.role != "solid" or rec.key not in meshes:
            continue
        fp = meshops.mesh_fingerprint(*meshes[rec.key])
        if fp in seen:
            first = seen[fp]
            rec.issues.append(
                _issue("warning", "DUPLICATE_GEOMETRY", f"coincident with {first}", rec)
            )
            if settings.duplicate_policy == "exclude":
                rec.excluded_reason = f"duplicate of {first}"
        else:
            seen[fp] = rec.key

    # ---- materials (assumptions) and radio-scene membership -----------------------------------
    el_by_key = dict(zip(keys, elements, strict=True))
    for rec in records:
        if rec.key not in meshes:
            continue
        if rec.role == "volume":
            rec.excluded_reason = "volume (space), not an obstacle"
            continue
        names = [m.name for m in el_by_key[rec.key].materials if m.name]
        rec.material = mapper.assign(rec.category, names, rec.global_id)
        if rec.material.status == "unmapped":
            rec.issues.append(_issue("warning", "UNMAPPED_MATERIAL", "no radio material", rec))
        elif rec.material.composite:
            rec.issues.append(
                _issue("info", "COMPOSITE_MATERIAL", f"candidates: {rec.material.candidates}", rec)
            )
        rec.include_in_radio_scene = rec.excluded_reason is None

    all_issues = [i for r in records for i in r.issues]
    by_sev = Counter(i.severity for i in all_issues)
    gm = GeometryModel(
        building_id=model.building_id,
        source_sha256=model.source.sha256,
        coordinate_system=CoordinateSystem(
            origin_offset_m=offset,
            recenter_mode=settings.recenter,
            source_length_unit_scale_m=model.length_unit_scale_m,
        ),  # fmt: skip
        meshes=records,
        issues=all_issues,
        validation=GeometryValidation(
            is_valid=by_sev.get("error", 0) == 0,
            counts_by_severity=dict(by_sev),
            counts_by_code=dict(Counter(i.code for i in all_issues)),
        ),
        counts={
            "status": dict(Counter(r.status for r in records)),
            "category": dict(Counter(r.category for r in records)),
            "radio_scene": {
                "included": sum(r.include_in_radio_scene for r in records),
                "excluded": sum(
                    1 for r in records if r.key in meshes and not r.include_in_radio_scene
                ),
            },
            "material_status": dict(Counter(r.material.status for r in records if r.material)),
            "em_material": dict(Counter(r.material.em_material for r in records if r.material)),
        },
        provenance=GeometryProvenance(
            pipeline_version=PIPELINE_VERSION,
            ifcopenshell_version=_ifcopenshell_version(),
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            duration_s=round(time.perf_counter() - t0, 3),
            settings=settings.model_dump(mode="json"),
        ),
    )
    logger.info("geometry %s: status=%s", model.building_id, gm.counts["status"])
    result = GeometryResult(gm, meshes)
    if storage_dir is not None:
        _persist(result, Path(storage_dir))
    return result


def _ifcopenshell_version() -> str | None:
    try:
        import ifcopenshell

        return ifcopenshell.version
    except Exception:  # noqa: BLE001
        return None


def _persist(result: GeometryResult, storage_dir: Path) -> None:
    from .report import build_geometry_report

    gm = result.model
    gdir = storage_dir / "geometry" / gm.building_id
    mesh_dir = gdir / "meshes"
    if mesh_dir.exists():
        shutil.rmtree(mesh_dir)  # derived data only: regenerated, never the original IFC
    mesh_dir.mkdir(parents=True)
    for rec in gm.meshes:
        if rec.key in result.meshes:
            rec.mesh_file = f"meshes/{rec.key}.ply"
            meshops.write_ply(gdir / rec.mesh_file, *result.meshes[rec.key])
    result.geometry_dir = gdir
    result.geometry_path = gdir / "geometry.json"
    result.geometry_path.write_text(gm.model_dump_json(indent=2), encoding="utf-8")
    result.report_path = gdir / "validation_report.md"
    result.report_path.write_text(build_geometry_report(gm), encoding="utf-8")


def load_geometry(geometry_dir: Path | str) -> GeometryModel:
    return GeometryModel.model_validate_json(
        (Path(geometry_dir) / "geometry.json").read_text(encoding="utf-8")
    )


def load_record_mesh(geometry_dir: Path | str, record: MeshRecord):
    if not record.mesh_file:
        raise FileNotFoundError(f"record {record.key} has no mesh file (status={record.status})")
    return meshops.read_ply(Path(geometry_dir) / record.mesh_file)
