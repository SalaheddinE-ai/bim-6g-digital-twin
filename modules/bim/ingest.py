"""End-to-end ingestion: IFC file -> stored original + validated Building Data Model + report.

Storage layout (under ``storage_dir``)::

    ifc/<building_id>/original.ifc          read-only copy, never modified
    bim/<building_id>/building.json         Building Data Model incl. validation
    bim/<building_id>/extraction_report.md  human-readable report
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from .extractor import extract_building
from .parser import IfcLoadError, building_id_from_sha256, describe_source, load_ifc
from .report import build_extraction_report, export_json
from .schemas import BuildingModel
from .validator import validate_building

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    model: BuildingModel
    ifc_path: Path | None
    json_path: Path | None
    report_path: Path | None


def ingest_ifc(
    path: Path | str, storage_dir: Path | str | None = None, *, max_size_mb: float | None = 500.0
) -> IngestResult:
    """Load, extract and validate an IFC file; persist results when ``storage_dir`` is given.

    Invalid files raise :class:`IfcLoadError` BEFORE anything is stored. A structurally valid
    IFC that fails *validation* (e.g. duplicate GlobalIds) is still returned, with
    ``model.validation.is_valid == False``, so the caller can decide.
    """
    src = Path(path)
    ifc = load_ifc(src, max_size_mb=max_size_mb)
    source = describe_source(src, ifc)
    building_id = building_id_from_sha256(source.sha256)

    model = extract_building(ifc, source, building_id)
    model.validation = validate_building(model)
    logger.info(
        "Ingested %s as %s: valid=%s counts=%s",
        src.name, building_id, model.validation.is_valid, model.counts,
    )  # fmt: skip

    if storage_dir is None:
        return IngestResult(model, None, None, None)

    root = Path(storage_dir)
    ifc_dir = root / "ifc" / building_id
    bim_dir = root / "bim" / building_id
    ifc_dir.mkdir(parents=True, exist_ok=True)
    stored = ifc_dir / "original.ifc"
    if not stored.exists():  # same hash == same content: never overwrite the original
        shutil.copyfile(src, stored)
        os.chmod(stored, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    json_path = export_json(model, bim_dir / "building.json")
    report_path = bim_dir / "extraction_report.md"
    report_path.write_text(build_extraction_report(model), encoding="utf-8")
    return IngestResult(model, stored, json_path, report_path)


__all__ = ["IfcLoadError", "IngestResult", "ingest_ifc"]
