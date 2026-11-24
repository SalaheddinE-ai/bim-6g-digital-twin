"""M02 pipeline on synthetic IFC files with exact, known geometry (real IfcOpenShell, no mocks,
except the explicit stub tessellator used ONLY to inject invalid meshes)."""

import hashlib

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
from modules.geometry.tessellate import RawMesh  # noqa: E402
from tests.fixtures.geometry_ifc import SCENE, Spec, build_ifc, expected_bbox  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.ifc]

TOL = 1e-6


def run(path, storage=None, **settings):
    ing = ingest_ifc(path, storage)
    settings = {"num_threads": 1, **settings}
    res = build_geometry(
        ing.model, ing.ifc_path or path, storage_dir=storage, settings=GeometrySettings(**settings)
    )
    return ing, res


def rec_by_name(ing, res, name):
    el = next(e for e in ing.model.elements if e.name == name)
    return next(r for r in res.model.meshes if r.global_id == el.global_id)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    path = build_ifc(tmp_path_factory.mktemp("scene") / "scene.ifc")
    ing, res = run(path)
    return path, ing, res


# ---- mesh extraction, validation, missing geometry ---------------------------------------------
def test_mesh_extraction_matches_exact_boxes(built):
    _, ing, res = built
    for spec in SCENE:
        rec = rec_by_name(ing, res, spec.name)
        if spec.size is None:
            continue
        assert rec.status == "ok", (spec.name, rec.status, rec.issues)
        lo, hi = expected_bbox(spec)
        np.testing.assert_allclose(rec.bbox_min_m, lo, atol=TOL, err_msg=spec.name)
        np.testing.assert_allclose(rec.bbox_max_m, hi, atol=TOL, err_msg=spec.name)
        assert rec.watertight and rec.n_vertices == 8 and rec.n_faces == 12


def test_volumes_and_areas(built):
    _, ing, res = built
    w1 = rec_by_name(ing, res, "W1")  # 5 x 0.2 x 3
    assert w1.volume_m3 == pytest.approx(3.0) and w1.area_m2 == pytest.approx(2 * (1 + 15 + 0.6))


def test_missing_geometry_is_reported_not_invented(built):
    _, ing, res = built
    rec = rec_by_name(ing, res, "W3_nogeom")
    assert rec.status == "missing" and rec.mesh_file is None and not rec.include_in_radio_scene
    assert [i.code for i in rec.issues] == ["MISSING_GEOMETRY"]
    assert rec.key not in res.meshes
    assert res.model.validation.is_valid  # a warning, not an error


def test_curtain_wall_without_geometry_is_only_informational(tmp_path):
    p = build_ifc(tmp_path / "cw.ifc", (Spec("IfcCurtainWall", "CW", (0, 0, 0), None),))
    ing, res = run(p)
    rec = rec_by_name(ing, res, "CW")
    assert rec.status == "missing" and [(i.severity, i.code) for i in rec.issues] == [
        ("info", "NO_OWN_GEOMETRY")
    ]


# ---- unit conversion, coordinates, transformations ---------------------------------------------
@pytest.mark.parametrize(
    ("unit", "scale"), [("METERS", 1.0), ("CENTIMETERS", 0.01), ("MILLIMETERS", 0.001)]
)
def test_unit_conversion_gives_identical_metre_geometry(tmp_path, unit, scale):
    ing, res = run(build_ifc(tmp_path / f"{unit}.ifc", unit=unit))
    assert ing.model.length_unit_scale_m == pytest.approx(scale)
    assert res.model.coordinate_system.source_length_unit_scale_m == pytest.approx(scale)
    for spec in SCENE:
        if spec.size is None:
            continue
        rec = rec_by_name(ing, res, spec.name)
        lo, hi = expected_bbox(spec)
        np.testing.assert_allclose(rec.bbox_min_m, lo, atol=TOL, err_msg=f"{unit} {spec.name}")
        np.testing.assert_allclose(rec.bbox_max_m, hi, atol=TOL, err_msg=f"{unit} {spec.name}")


def test_rotation_and_translation_are_applied(built):
    _, ing, res = built
    w2 = rec_by_name(ing, res, "W2")  # 4 x 0.3 x 3, rotated 90 deg about Z, placed at (10, 20, 0)
    np.testing.assert_allclose(w2.bbox_min_m, (9.7, 20.0, 0.0), atol=TOL)
    np.testing.assert_allclose(w2.bbox_max_m, (10.0, 24.0, 3.0), atol=TOL)


FAR = (500_000.0, 300_000.0, 0.0)


def test_far_coordinates_are_recentred_with_a_recoverable_offset(tmp_path):
    p = build_ifc(tmp_path / "far.ifc", offset=FAR)
    ing, res = run(p)  # recenter = auto
    off = np.array(res.model.coordinate_system.origin_offset_m)
    assert np.abs(off).max() > 1e5
    for spec in SCENE:
        if spec.size is None:
            continue
        rec = rec_by_name(ing, res, spec.name)
        lo, hi = expected_bbox(spec, offset=-np.asarray(FAR))  # true world box
        np.testing.assert_allclose(np.array(rec.bbox_min_m) + off, lo, atol=TOL)
        np.testing.assert_allclose(np.array(rec.bbox_max_m) + off, hi, atol=TOL)
        assert np.abs(rec.bbox_min_m).max() < 1e3  # small, float32-safe coordinates


def test_recenter_none_and_bbox_min_modes(tmp_path):
    p = build_ifc(tmp_path / "far.ifc", offset=FAR)
    _, none = run(p, recenter="none")
    assert none.model.coordinate_system.origin_offset_m == (0.0, 0.0, 0.0)
    assert min(r.bbox_min_m[0] for r in none.model.meshes if r.bbox_min_m) > 4e5
    _, bmin = run(p, recenter="bbox_min")
    lows = np.min([r.bbox_min_m for r in bmin.model.meshes if r.bbox_min_m], axis=0)
    np.testing.assert_allclose(lows, 0.0, atol=TOL)


def test_near_origin_scene_is_not_shifted(built):
    assert built[2].model.coordinate_system.origin_offset_m == (0.0, 0.0, 0.0)


# ---- element identity --------------------------------------------------------------------------
def test_every_record_keeps_its_bim_global_id(built):
    _, ing, res = built
    bim_ids = {e.global_id for e in ing.model.elements if e.category in GEOMETRY_CATEGORIES}
    rec_ids = [r.global_id for r in res.model.meshes]
    assert set(rec_ids) == bim_ids and len(rec_ids) == len(set(rec_ids))
    assert {r.key for r in res.model.meshes} == bim_ids  # keys are the GlobalIds here
    for r in res.model.meshes:
        el = ing.model.get(r.global_id)
        assert (r.ifc_class, r.category) == (el.ifc_class, el.category)


def test_storage_round_trip_preserves_ids_and_geometry(tmp_path):
    p = build_ifc(tmp_path / "s.ifc")
    ing, res = run(p, storage=tmp_path / "store")
    gdir = res.geometry_dir
    assert gdir == tmp_path / "store" / "geometry" / ing.model.building_id
    assert load_geometry(gdir) == res.model
    for r in res.model.meshes:
        if r.status == "missing":
            continue
        assert r.mesh_file == f"meshes/{r.global_id}.ply" and (gdir / r.mesh_file).is_file()
        v, f = load_record_mesh(gdir, r)
        np.testing.assert_allclose(v, res.meshes[r.key][0], atol=1e-5)
        np.testing.assert_array_equal(f, res.meshes[r.key][1])
    assert res.report_path.read_text().startswith("# Geometry validation report")


def test_original_ifc_is_never_modified(tmp_path):
    p = build_ifc(tmp_path / "s.ifc")
    ing, _ = run(p, storage=tmp_path / "store")
    sha = lambda q: hashlib.sha256(q.read_bytes()).hexdigest()  # noqa: E731
    before = (sha(p), sha(ing.ifc_path))
    run(p, storage=tmp_path / "store")
    assert (sha(p), sha(ing.ifc_path)) == before


def test_rebuild_removes_stale_meshes(tmp_path):
    p = build_ifc(tmp_path / "s.ifc")
    _, res = run(p, storage=tmp_path / "store")
    stale = res.geometry_dir / "meshes" / "STALE.ply"
    stale.write_bytes(b"x")
    run(p, storage=tmp_path / "store")
    assert not stale.exists()


def test_pipeline_is_deterministic(tmp_path):
    p = build_ifc(tmp_path / "s.ifc")
    _, a = run(p)
    _, b = run(p)
    strip = lambda gm: gm.model_dump(exclude={"provenance"})  # noqa: E731
    assert strip(a.model) == strip(b.model)


# ---- materials ---------------------------------------------------------------------------------
def test_materials_are_flagged_assumptions(built):
    _, ing, res = built
    got = {s.name: rec_by_name(ing, res, s.name).material for s in SCENE if s.size}
    assert (got["W1"].em_material, got["W1"].status, got["W1"].composite) == (
        "concrete",
        "assumed_from_name",
        True,
    )
    assert (got["D1"].em_material, got["WIN1"].em_material) == ("wood", "glass")
    assert (got["W2"].em_material, got["W2"].status) == ("concrete", "assumed_from_category")
    assert got["COL1"].status == "assumed_from_category"  # "Zebra Stripe Fabric" matched nothing
    assert all(
        m.status.startswith("assumed") for k, m in got.items() if m is not None and k != "ROOM1"
    )
    assert got["ROOM1"] is None  # volumes carry no radio material


# ---- radio-scene membership, volumes, duplicates -----------------------------------------------
def test_spaces_are_exported_as_volumes_but_not_obstacles(built):
    _, ing, res = built
    room = rec_by_name(ing, res, "ROOM1")
    assert room.role == "volume" and room.status == "ok" and room.key in res.meshes
    assert not room.include_in_radio_scene and "volume" in room.excluded_reason
    assert room.key not in {r.key for r in res.model.radio_scene()}
    assert res.model.counts["radio_scene"] == {"included": 6, "excluded": 1}


def test_coincident_duplicates_are_excluded_by_default(tmp_path):
    dup = Spec(
        "IfcWall", "W1_copy", SCENE[0].pos, SCENE[0].size, materials=SCENE[0].materials
    )  # coincident with W1
    p = build_ifc(tmp_path / "d.ifc", (*SCENE, dup))
    ing, res = run(p)
    first, copy = rec_by_name(ing, res, "W1"), rec_by_name(ing, res, "W1_copy")
    assert first.include_in_radio_scene and not copy.include_in_radio_scene
    assert copy.excluded_reason == f"duplicate of {first.key}"
    assert "DUPLICATE_GEOMETRY" in [i.code for i in copy.issues]
    assert copy.key in res.meshes  # data kept, only excluded from the radio scene
    _, kept = run(p, duplicate_policy="keep")
    assert rec_by_name(ing, kept, "W1_copy").include_in_radio_scene


# ---- invalid meshes (stub tessellator injects bad data) ----------------------------------------
CUBE_V = np.array(
    [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float
)
CUBE_F = np.array([[0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                   [2, 3, 7], [2, 7, 6], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]])  # fmt: skip


def stub(ing, make):
    """make(index, element) -> (vertices, faces) | None (None = tessellation failure)."""
    els = [
        e
        for e in ing.model.elements
        if e.category in GEOMETRY_CATEGORIES and e.geometry.has_representation
    ]
    by_step = {e.ifc_step_id: (i, e) for i, e in enumerate(els)}

    def tessellator(ifc, step_ids, num_threads=1):
        raw, failures = {}, {}
        for sid in step_ids:
            i, e = by_step[sid]
            out = make(i, e)
            if out is None:
                failures[sid] = "simulated failure"
            else:
                raw[sid] = RawMesh(sid, e.global_id, np.asarray(out[0], float), np.asarray(out[1]))
        return raw, failures

    return tessellator


def test_invalid_meshes_are_rejected_with_specific_codes(built):
    _, ing, _ = built
    nan = CUBE_V.copy()
    nan[0, 0] = np.nan
    oob = CUBE_F.copy()
    oob[0, 0] = 50
    flat = [[0, 0, 0], [1, 0, 0], [2, 0, 0]]
    cases = [
        (nan, CUBE_F),  # NON_FINITE_VERTEX
        (CUBE_V, oob),  # FACE_INDEX_OUT_OF_RANGE
        (np.zeros((0, 3)), np.zeros((0, 3), int)),  # EMPTY_MESH
        (flat, [[0, 1, 2]]),  # EMPTY_AFTER_CLEANING
        None,  # TESSELLATION_FAILED
    ]
    want = [
        "NON_FINITE_VERTEX",
        "FACE_INDEX_OUT_OF_RANGE",
        "EMPTY_MESH",
        "EMPTY_AFTER_CLEANING",
        "TESSELLATION_FAILED",
    ]
    res = build_geometry(
        ing.model, "unused.ifc", ifc=object(), settings=GeometrySettings(),
        tessellator=stub(ing, lambda i, e: cases[i] if i < len(cases) else (CUBE_V, CUBE_F)),
    )  # fmt: skip
    gm = res.model
    els = [
        e
        for e in ing.model.elements
        if e.category in GEOMETRY_CATEGORIES and e.geometry.has_representation
    ]
    for i, code in enumerate(want):
        rec = gm.get(els[i].global_id)
        assert rec.status in ("invalid", "failed") and code in [x.code for x in rec.issues], (
            i,
            code,
            rec.issues,
        )
        assert (
            rec.key not in res.meshes and not rec.include_in_radio_scene and rec.mesh_file is None
        )
    assert gm.validation.is_valid is False
    assert gm.counts["status"].get("invalid", 0) == 4 and gm.counts["status"].get("failed", 0) == 1


def test_placement_crosscheck_flags_walls_but_not_slabs(built):
    _, ing, _ = built
    far = CUBE_V + 500.0  # mesh 500 m away from the BIM placement
    res = build_geometry(
        ing.model, "unused.ifc", ifc=object(), settings=GeometrySettings(recenter="none"),
        tessellator=stub(ing, lambda i, e: (far, CUBE_F)),
    )  # fmt: skip
    flagged = {
        r.category for r in res.model.meshes if "PLACEMENT_MISMATCH" in [i.code for i in r.issues]
    }
    assert flagged == {"wall", "door", "window"}  # slab/column/space placements are anchors, exempt
