"""Ingest IFC files: python scripts/ingest_ifc.py FILE.ifc [FILE2.ifc ...] [--samples-dir DIR]

Stores the original, writes building.json + extraction_report.md under <storage_dir>/bim/<id>/,
prints the report, and optionally copies both to --samples-dir (e.g. docs/samples/<name>/).
Exit code 1 if any file is rejected or fails validation.
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import load_settings  # noqa: E402
from backend.logging_setup import setup_logging  # noqa: E402
from modules.bim.ingest import IfcLoadError, ingest_ifc  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--storage-dir", type=Path, default=None)
    ap.add_argument("--samples-dir", type=Path, default=None)
    args = ap.parse_args()

    settings = load_settings()
    setup_logging(settings.logging.level, None)
    storage = args.storage_dir or settings.resolve_path(settings.paths.storage_dir)

    rc = 0
    for f in args.files:
        try:
            res = ingest_ifc(f, storage)
        except IfcLoadError as exc:
            print(f"REJECTED {f}: {exc}")
            rc = 1
            continue
        print(res.report_path.read_text(encoding="utf-8"))
        print(f"-> {res.json_path}")
        if not res.model.validation.is_valid:
            rc = 1
        if args.samples_dir:
            out = args.samples_dir / f.stem.replace(" ", "_")
            out.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(res.json_path, out / "building.json")
            shutil.copyfile(res.report_path, out / "extraction_report.md")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
