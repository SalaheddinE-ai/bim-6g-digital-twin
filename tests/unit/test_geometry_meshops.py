import numpy as np
import pytest

from modules.geometry import meshops
from modules.geometry.meshops import MeshError

CUBE_V = np.array(
    [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float
)
CUBE_F = np.array(
    [
        [0, 3, 2],
        [0, 2, 1],
        [4, 5, 6],
        [4, 6, 7],
        [0, 1, 5],
        [0, 5, 4],
        [2, 3, 7],
        [2, 7, 6],
        [0, 4, 7],
        [0, 7, 3],
        [1, 2, 6],
        [1, 6, 5],
    ]
)  # fmt: skip  (outward, counter-clockwise)


def cube(size=1.0, origin=(0, 0, 0)):
    return CUBE_V * size + np.asarray(origin, float), CUBE_F.copy()


# ---- transforms / units -----------------------------------------------------------------------
def test_apply_transform_rotation_and_translation():
    m = np.array(
        [[0, -1, 0, 10], [1, 0, 0, 20], [0, 0, 1, 3], [0, 0, 0, 1]], float
    )  # 90deg about Z
    out = meshops.apply_transform([[1, 0, 0], [0, 2, 0]], m)
    np.testing.assert_allclose(out, [[10, 21, 3], [8, 20, 3]], atol=1e-12)


def test_apply_transform_identity_and_unit_scale():
    pts = np.array([[1000.0, 2000.0, 3000.0]])
    np.testing.assert_allclose(meshops.apply_transform(pts, np.eye(4)), pts)
    mm_to_m = np.diag([0.001, 0.001, 0.001, 1.0])
    np.testing.assert_allclose(meshops.apply_transform(pts, mm_to_m), [[1.0, 2.0, 3.0]])


@pytest.mark.parametrize(
    "bad",
    [
        np.eye(3),
        np.full((4, 4), np.nan),
        np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 1.0]]),
    ],
)
def test_apply_transform_rejects_bad_matrices(bad):
    with pytest.raises(MeshError):
        meshops.apply_transform([[0, 0, 0]], bad)


def test_as_mesh_shape_checks():
    with pytest.raises(MeshError):
        meshops.as_mesh([[0, 0], [1, 1]], [[0, 1, 2]])
    with pytest.raises(MeshError):
        meshops.as_mesh(CUBE_V, [[0, 1]])
    v, f = meshops.as_mesh([], [])
    assert v.shape == (0, 3) and f.shape == (0, 3)


# ---- measures ---------------------------------------------------------------------------------
def test_cube_measures():
    v, f = cube(2.0)
    assert meshops.signed_volume(v, f) == pytest.approx(8.0)
    assert meshops.face_areas(v, f).sum() == pytest.approx(24.0)
    st = meshops.edge_stats(f, len(v))
    assert st.watertight and st.inconsistent == 0 and st.boundary == 0


# ---- validation of raw meshes (invalid mesh handling) -----------------------------------------
def test_validate_raw_accepts_cube():
    assert meshops.validate_raw(*cube()) == []


def test_validate_raw_detects_problems():
    v, f = cube()
    nan = v.copy()
    nan[3, 1] = np.nan
    assert [c for _, c, _ in meshops.validate_raw(nan, f)] == ["NON_FINITE_VERTEX"]
    oob = f.copy()
    oob[0, 0] = 99
    assert [c for _, c, _ in meshops.validate_raw(v, oob)] == ["FACE_INDEX_OUT_OF_RANGE"]
    neg = f.copy()
    neg[0, 0] = -1
    assert [c for _, c, _ in meshops.validate_raw(v, neg)] == ["FACE_INDEX_OUT_OF_RANGE"]
    assert [c for _, c, _ in meshops.validate_raw(np.zeros((0, 3)), np.zeros((0, 3), int))] == [
        "EMPTY_MESH"
    ]


# ---- lossless cleaning --------------------------------------------------------------------------
def test_clean_valid_cube_changes_nothing():
    r = meshops.clean_mesh(*cube())
    assert r.repairs == [] and r.issues == [] and r.watertight
    assert r.volume_m3 == pytest.approx(1.0) and r.area_m2 == pytest.approx(6.0)


def test_clean_welds_triangle_soup():
    v, f = cube()
    soup_v = v[f].reshape(-1, 3)  # 36 unshared vertices
    soup_f = np.arange(36).reshape(-1, 3)
    r = meshops.clean_mesh(soup_v, soup_f)
    assert len(r.vertices) == 8 and r.watertight
    assert any("welded 28" in x for x in r.repairs)
    assert r.volume_m3 == pytest.approx(1.0)


def test_clean_flips_inward_normals():
    v, f = cube()
    r = meshops.clean_mesh(v, f[:, [0, 2, 1]])  # all faces reversed
    assert r.volume_m3 == pytest.approx(1.0)
    assert any("flipped" in x for x in r.repairs)
    assert meshops.signed_volume(r.vertices, r.faces) > 0


def test_clean_reports_inconsistent_orientation_without_guessing():
    v, f = cube()
    f[0] = f[0][[0, 2, 1]]  # one neighbour flipped
    r = meshops.clean_mesh(v, f)
    assert [c for _, c, _ in r.issues] == ["INCONSISTENT_ORIENTATION"]
    assert r.volume_m3 is None and r.repairs == []


def test_clean_open_mesh_is_reported_not_watertight():
    v, f = cube()
    r = meshops.clean_mesh(v, f[:-2])  # drop one side
    assert r.watertight is False and r.volume_m3 is None
    assert "NOT_WATERTIGHT" in [c for _, c, _ in r.issues]


def test_clean_removes_degenerate_and_unreferenced():
    v, f = cube()
    v2 = np.vstack([v, [[5, 5, 5], [5, 5, 5], [9, 9, 9]]])
    f2 = np.vstack([f, [[8, 9, 8], [0, 0, 1]]])  # zero-area + repeated index
    r = meshops.clean_mesh(v2, f2)
    assert len(r.faces) == 12 and len(r.vertices) == 8
    assert any("degenerate" in x for x in r.repairs) and any("unreferenced" in x for x in r.repairs)


def test_clean_all_degenerate_is_an_error():
    v = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0.0]])
    r = meshops.clean_mesh(v, [[0, 1, 2]])
    assert [(s, c) for s, c, _ in r.issues] == [("error", "EMPTY_AFTER_CLEANING")]


@pytest.mark.parametrize("size", [5000.0, 0.001])
def test_suspicious_size_flagged(size):
    codes = [c for _, c, _ in meshops.clean_mesh(*cube(size)).issues]
    assert "SUSPICIOUS_SIZE" in codes


# ---- duplicates / distances -------------------------------------------------------------------
def test_fingerprint_is_order_independent_and_position_sensitive():
    v, f = cube()
    perm = np.random.default_rng(0).permutation(8)
    inv = np.argsort(perm)
    assert meshops.mesh_fingerprint(v[perm], inv[f]) == meshops.mesh_fingerprint(v, f)
    assert meshops.mesh_fingerprint(*cube(origin=(0.1, 0, 0))) != meshops.mesh_fingerprint(v, f)


def test_point_to_aabb_distance():
    assert meshops.point_to_aabb_distance([0.5, 0.5, 0.5], [0, 0, 0], [1, 1, 1]) == 0.0
    assert meshops.point_to_aabb_distance([4, 0, 0], [0, 0, 0], [1, 1, 1]) == pytest.approx(3.0)


# ---- PLY ----------------------------------------------------------------------------------------
def test_ply_round_trip(tmp_path):
    v, f = cube(3.0, (10, 20, 1))
    p = meshops.write_ply(tmp_path / "a" / "x.ply", v, f)
    v2, f2 = meshops.read_ply(p)
    np.testing.assert_allclose(v2, v, atol=1e-5)
    np.testing.assert_array_equal(f2, f)


def test_ply_rejects_garbage_and_wrong_format(tmp_path):
    bad = tmp_path / "bad.ply"
    bad.write_bytes(b"not a ply")
    with pytest.raises(MeshError):
        meshops.read_ply(bad)
    ascii_ply = tmp_path / "ascii.ply"
    ascii_ply.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 0\nelement face 0\nend_header\n")
    with pytest.raises(MeshError):
        meshops.read_ply(ascii_ply)
