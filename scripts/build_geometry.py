"""Ingest an IFC (M01) then build validated meshes (M02).

python scripts/build_geometry.py tests/fixtures/real_ifc/BuildingBIMModel.ifc
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import load_settings  # noqa: E402
from modules.bim.ingest import ingest_ifc  # noqa: E402
from modules.geometry.pipeline import build_geometry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ifc", type=Path)
    ap.add_argument(
        "--storage", type=Path, default=None, help="default: settings paths.storage_dir"
    )
    args = ap.parse_args()

    settings = load_settings()
    storage = args.storage or settings.resolve_path(settings.paths.storage_dir)
    ing = ingest_ifc(args.ifc, storage)
    res = build_geometry(ing.model, ing.ifc_path or args.ifc, storage_dir=storage,
                         settings=settings.geometry)  # fmt: skip
    gm = res.model
    print(f"building_id : {gm.building_id}")
    print(f"status      : {gm.counts['status']}")
    print(f"radio scene : {gm.counts['radio_scene']}")
    print(f"materials   : {gm.counts['material_status']}")
    print(f"issues      : {gm.validation.counts_by_code}")
    print(f"offset      : {gm.coordinate_system.origin_offset_m}")
    print(f"valid       : {gm.validation.is_valid}  ({gm.provenance.duration_s:.1f}s)")
    print(f"output      : {res.geometry_dir}")
    return 0 if gm.validation.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
