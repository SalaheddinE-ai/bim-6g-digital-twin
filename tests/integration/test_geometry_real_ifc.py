"""M02 acceptance on the REAL building (Revit export, 626 geometry elements).

The numeric expectations below were OBSERVED on this specific sample file during development and
are sanity invariants (accounting, units, levels), not quality targets.
"""

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("ifcopenshell")

from backend.config import GeometrySettings  # noqa: E402
from modules.bim.ingest import ingest_ifc  # noqa: E402
from modules.geometry.pipeline import (  # noqa: E402
    GEOMETRY_CATEGORIES,
    build_geometry,
    load_geometry,
    load_record_mesh,
)

REAL = Path(__file__).resolve().parents[1] / "fixtures" / "real_ifc" / "BuildingBIMModel.ifc"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.ifc,
    pytest.mark.skipif(not REAL.is_file(), reason=f"real IFC fixture missing: {REAL}"),
]


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    store = tmp_path_factory.mktemp("store")
    ing = ingest_ifc(REAL, store)
    res = build_geometry(
        ing.model, ing.ifc_path, storage_dir=store, settings=GeometrySettings(num_threads=2)
    )
    return ing, res


def test_accounting_every_geometry_element_gets_exactly_one_record(real):
    ing, res = real
    expected = [e for e in ing.model.elements if e.category in GEOMETRY_CATEGORIES]
    gm = res.model
    assert len(gm.meshes) == len(expected) == sum(gm.counts["status"].values())
    assert {r.global_id for r in gm.meshes} == {e.global_id for e in expected}


def test_only_curtain_walls_lack_geometry_and_nothing_failed(real):
    gm = real[1].model
    assert gm.validation.is_valid, gm.validation.counts_by_code
    assert gm.counts["status"].get("failed", 0) == 0 and gm.counts["status"].get("invalid", 0) == 0
    assert {r.category for r in gm.meshes if r.status == "missing"} == {"curtain_wall"}


def test_all_meshes_are_finite_and_indices_valid(real):
    for key, (v, f) in real[1].meshes.items():
        assert np.isfinite(v).all(), key
        assert f.min() >= 0 and f.max() < len(v), key


def test_units_and_extent_are_plausible_metres(real):
    gm = real[1].model
    assert gm.coordinate_system.source_length_unit_scale_m == pytest.approx(0.001)  # file is in mm
    boxes = [(r.bbox_min_m, r.bbox_max_m) for r in gm.meshes if r.bbox_min_m]
    lo, hi = np.min([b[0] for b in boxes], axis=0), np.max([b[1] for b in boxes], axis=0)
    ext = hi - lo
    assert 5 < ext[0] < 1000 and 5 < ext[1] < 1000 and 2 < ext[2] < 200, ext
    doors = [r for r in gm.meshes if r.category == "door" and r.bbox_min_m]
    heights = [r.bbox_max_m[2] - r.bbox_min_m[2] for r in doors]
    assert 1.8 < np.median(heights) < 2.6  # a door is about 2 m tall: independent unit check


def test_levels_agree_with_storey_elevations(real):
    """Independent of M02's own transform: mesh heights vs the BIM storey elevations (metres)."""
    ing, res = real
    for category in ("space", "door", "wall"):
        d = []
        for r in res.model.meshes:
            el = ing.model.get(r.global_id)
            if (
                r.category == category
                and r.bbox_min_m
                and el.spatial.storey_elevation_m is not None
            ):
                d.append(r.bbox_min_m[2] - el.spatial.storey_elevation_m)
        assert len(d) > 20
        assert np.mean(np.abs(d) < 0.1) >= 0.99, (category, np.round(d[:10], 2))


def test_bim_placement_is_consistent_with_meshes_for_walls_doors_windows(real):
    codes = Counter(i.code for i in real[1].model.issues)
    assert codes.get("PLACEMENT_MISMATCH", 0) == 0


def test_spaces_are_volumes_and_solids_form_the_radio_scene(real):
    gm = real[1].model
    spaces = [r for r in gm.meshes if r.category == "space"]
    assert spaces and all(r.role == "volume" and not r.include_in_radio_scene for r in spaces)
    scene = gm.radio_scene()
    assert scene and all(r.role == "solid" and r.material is not None for r in scene)
    assert all(
        r.material.status.startswith("assumed") or r.material.status == "unmapped" for r in scene
    )
    valid = sum(1 for r in gm.meshes if r.status in ("ok", "repaired"))
    assert gm.counts["radio_scene"]["included"] + gm.counts["radio_scene"]["excluded"] == valid


def test_exported_files_match_the_manifest(real):
    ing, res = real
    gm = load_geometry(res.geometry_dir)
    assert gm == res.model
    with_mesh = [r for r in gm.meshes if r.mesh_file]
    assert (
        len(list((res.geometry_dir / "meshes").glob("*.ply"))) == len(with_mesh) == len(res.meshes)
    )
    r = with_mesh[0]
    v, f = load_record_mesh(res.geometry_dir, r)
    np.testing.assert_allclose(v, res.meshes[r.key][0], atol=1e-4)
    assert Path(ing.ifc_path).is_file()  # the stored original is untouched and still there
