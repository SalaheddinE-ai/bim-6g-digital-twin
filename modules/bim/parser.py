"""IFC loading with early, explicit rejection of invalid input. Needs IfcOpenShell."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from .schemas import SourceInfo

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = {".ifc", ".ifczip"}
SUPPORTED_SCHEMA_PREFIXES = ("IFC2X3", "IFC4")  # IFC4, IFC4X3...
_STEP_MAGIC = b"ISO-10303-21"


class IfcLoadError(Exception):
    """The file is missing, not an IFC, unsupported, or could not be parsed."""


def _require_ifcopenshell() -> Any:
    try:
        import ifcopenshell
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise IfcLoadError(
            "IfcOpenShell is not installed (pip install -e '.[bim]' / ifcopenshell==0.9.0.post1)"
        ) from exc
    return ifcopenshell


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def building_id_from_sha256(sha256: str) -> str:
    """Stable building ID: same file content -> same ID."""
    return f"bld_{sha256[:12]}"


def load_ifc(path: Path | str, *, max_size_mb: float | None = 500.0) -> Any:
    """Open an IFC file and return the ``ifcopenshell.file``. Raises :class:`IfcLoadError`."""
    p = Path(path)
    if not p.is_file():
        raise IfcLoadError(f"File not found: {p}")
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        raise IfcLoadError(
            f"Unsupported extension '{p.suffix}' (allowed: {sorted(ALLOWED_SUFFIXES)})"
        )
    if max_size_mb is not None and p.stat().st_size > max_size_mb * 1024 * 1024:
        raise IfcLoadError(f"File larger than {max_size_mb} MB: {p.stat().st_size} bytes")
    if p.stat().st_size == 0:
        raise IfcLoadError(f"File is empty: {p}")
    if p.suffix.lower() == ".ifc":
        with p.open("rb") as fh:
            head = fh.read(256).lstrip(b"\xef\xbb\xbf \t\r\n")
        if not head.startswith(_STEP_MAGIC):
            raise IfcLoadError(f"Not an IFC/STEP file (missing ISO-10303-21 header): {p.name}")

    ifcopenshell = _require_ifcopenshell()
    try:
        model = ifcopenshell.open(str(p))
    except Exception as exc:
        raise IfcLoadError(f"IfcOpenShell could not parse {p.name}: {exc}") from exc
    if model is None:
        raise IfcLoadError(f"IfcOpenShell returned no model for {p.name}")
    try:
        schema = model.schema
    except Exception as exc:
        raise IfcLoadError(f"Could not determine IFC schema of {p.name}: {exc}") from exc
    if not schema or not str(schema).upper().startswith(SUPPORTED_SCHEMA_PREFIXES):
        raise IfcLoadError(f"Unsupported or missing IFC schema: {schema!r}")
    logger.info("Loaded %s (%s)", p.name, schema)
    return model


def describe_source(path: Path | str, model: Any) -> SourceInfo:
    p = Path(path)
    ident = getattr(model, "schema_identifier", None)
    app = None
    try:
        names = model.wrapped_data.header.file_name.originating_system
        app = str(names) if names else None
    except Exception:  # header access differs between versions; purely informative
        app = None
    return SourceInfo(
        file_name=p.name,
        sha256=sha256_file(p),
        size_bytes=p.stat().st_size,
        ifc_schema=str(model.schema),
        ifc_schema_identifier=str(ident) if ident else None,
        application=app,
    )
