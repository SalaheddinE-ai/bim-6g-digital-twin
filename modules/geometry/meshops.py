"""Pure-numpy mesh operations (no IfcOpenShell needed). Triangle meshes: V (N,3) float, F (M,3) int.

Cleaning is LOSSLESS: weld coincident vertices, drop degenerate faces and unreferenced vertices,
and flip faces only when a closed, consistently-oriented mesh has negative volume. No decimation:
simplifying would change wall thickness and openings, which matters for radio propagation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


class MeshError(ValueError):
    """Malformed array shapes / transforms (programming or data-contract errors)."""


Issue = tuple[str, str, str]  # (severity, code, message)


def as_mesh(vertices, faces) -> tuple[np.ndarray, np.ndarray]:
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    if v.size == 0:
        v = v.reshape(0, 3)
    if f.size == 0:
        f = f.reshape(0, 3)
    if v.ndim != 2 or v.shape[1] != 3:
        raise MeshError(f"vertices must have shape (N, 3), got {v.shape}")
    if f.ndim != 2 or f.shape[1] != 3:
        raise MeshError(f"faces must have shape (M, 3), got {f.shape}")
    return v, f


def apply_transform(vertices, matrix) -> np.ndarray:
    """Apply a 4x4 rigid/affine matrix (row-major, last row 0 0 0 1) to (N,3) points."""
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    m = np.asarray(matrix, dtype=np.float64)
    if m.shape != (4, 4) or not np.all(np.isfinite(m)):
        raise MeshError("transform must be a finite 4x4 matrix")
    if not np.allclose(m[3], [0.0, 0.0, 0.0, 1.0]):
        raise MeshError("projective transforms are not supported (last row must be 0 0 0 1)")
    return v @ m[:3, :3].T + m[:3, 3]


def face_areas(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    if len(f) == 0:
        return np.zeros(0)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)


def signed_volume(v: np.ndarray, f: np.ndarray) -> float:
    """Positive for a closed mesh with outward (counter-clockwise) faces."""
    if len(f) == 0:
        return 0.0
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


@dataclass(frozen=True)
class EdgeStats:
    n_edges: int
    boundary: int  # edges used by exactly one face (open boundary)
    non_manifold: int  # edges used by more than two faces
    inconsistent: int  # directed edges used twice in the same direction (flipped neighbours)

    @property
    def watertight(self) -> bool:
        return self.n_edges > 0 and self.boundary == 0 and self.non_manifold == 0


def edge_stats(f: np.ndarray, n_vertices: int) -> EdgeStats:
    if len(f) == 0:
        return EdgeStats(0, 0, 0, 0)
    directed = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    n = max(int(n_vertices), 1)
    lo, hi = directed.min(axis=1), directed.max(axis=1)
    _, counts = np.unique(lo * n + hi, return_counts=True)
    dkey = directed[:, 0] * n + directed[:, 1]
    _, dcounts = np.unique(dkey, return_counts=True)
    return EdgeStats(
        n_edges=len(counts),
        boundary=int((counts == 1).sum()),
        non_manifold=int((counts > 2).sum()),
        inconsistent=int((dcounts > 1).sum()),
    )


def weld_vertices(v: np.ndarray, f: np.ndarray, tol: float) -> tuple[np.ndarray, np.ndarray]:
    """Merge vertices closer than ``tol`` (grid quantisation; first occurrence is kept)."""
    if len(v) == 0:
        return v, f
    q = np.round(v / tol).astype(np.int64)
    _, first, inverse = np.unique(q, axis=0, return_index=True, return_inverse=True)
    return v[first], inverse.reshape(-1)[f]


def drop_degenerate_faces(v, f, min_area: float) -> tuple[np.ndarray, int]:
    if len(f) == 0:
        return f, 0
    distinct = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    keep = distinct & (face_areas(v, f) > min_area)
    return f[keep], int((~keep).sum())


def drop_unreferenced(v: np.ndarray, f: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    if len(f) == 0:
        return v[:0], f, len(v)
    used = np.unique(f)
    remap = np.full(len(v), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return v[used], remap[f], len(v) - len(used)


def validate_raw(v: np.ndarray, f: np.ndarray) -> list[Issue]:
    """Structural checks that make a mesh unusable (all error-level)."""
    issues: list[Issue] = []
    if len(v) == 0 or len(f) == 0:
        return [("error", "EMPTY_MESH", f"mesh has {len(v)} vertices and {len(f)} faces")]
    if not np.all(np.isfinite(v)):
        issues.append(("error", "NON_FINITE_VERTEX", "vertices contain NaN or infinity"))
    if f.min() < 0 or f.max() >= len(v):
        issues.append(
            ("error", "FACE_INDEX_OUT_OF_RANGE", f"face indices outside [0, {len(v) - 1}]")
        )
    return issues


@dataclass
class CleanResult:
    vertices: np.ndarray
    faces: np.ndarray
    repairs: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    watertight: bool | None = None
    volume_m3: float | None = None
    area_m2: float = 0.0


def clean_mesh(v, f, *, weld_tol: float = 1e-6, min_face_area: float = 1e-10) -> CleanResult:
    """Lossless cleaning of a structurally valid mesh. Records every repair performed."""
    v, f = as_mesh(v, f)
    repairs: list[str] = []
    n_v0 = len(v)
    v, f = weld_vertices(v, f, weld_tol)
    if len(v) < n_v0:
        repairs.append(f"welded {n_v0 - len(v)} duplicate vertices")
    f, n_deg = drop_degenerate_faces(v, f, min_face_area)
    if n_deg:
        repairs.append(f"removed {n_deg} degenerate faces")
    v, f, n_unref = drop_unreferenced(v, f)
    if n_unref:
        repairs.append(f"removed {n_unref} unreferenced vertices")
    issues: list[Issue] = []
    if len(f) == 0:
        issues.append(("error", "EMPTY_AFTER_CLEANING", "no valid faces remain after cleaning"))
        return CleanResult(v, f, repairs, issues, area_m2=0.0)

    stats = edge_stats(f, len(v))
    watertight = stats.watertight
    volume: float | None = None
    if watertight:
        if stats.inconsistent:
            issues.append(
                ("warning", "INCONSISTENT_ORIENTATION", f"{stats.inconsistent} flipped edges")
            )
        else:
            volume = signed_volume(v, f)
            if volume < 0:
                f = f[:, [0, 2, 1]]
                volume = -volume
                repairs.append("flipped faces (closed mesh had inward normals)")
    else:
        if stats.non_manifold:
            issues.append(("info", "NON_MANIFOLD_EDGES", f"{stats.non_manifold} edges"))
        issues.append(("info", "NOT_WATERTIGHT", f"{stats.boundary} open boundary edges"))
    diag = float(np.linalg.norm(v.max(axis=0) - v.min(axis=0)))
    if diag > 1000.0 or diag < 0.01:
        issues.append(("warning", "SUSPICIOUS_SIZE", f"bounding-box diagonal {diag:.4g} m"))
    return CleanResult(v, f, repairs, issues, watertight, volume, float(face_areas(v, f).sum()))


def mesh_fingerprint(v: np.ndarray, f: np.ndarray, tol: float = 1e-5) -> str:
    """Order-independent hash of the vertex set + face count, to detect coincident duplicates."""
    q = np.unique(np.round(v / tol).astype(np.int64), axis=0)
    h = hashlib.sha1(q.tobytes())
    h.update(str(len(f)).encode())
    return h.hexdigest()


def point_to_aabb_distance(p, bbox_min, bbox_max) -> float:
    p, lo, hi = (np.asarray(x, dtype=np.float64) for x in (p, bbox_min, bbox_max))
    return float(np.linalg.norm(np.maximum(np.maximum(lo - p, 0.0), p - hi)))


# ---- binary little-endian PLY (what Mitsuba/Sionna RT can load) -------------------------------
_FACE_DTYPE = np.dtype([("n", "u1"), ("idx", "<i4", (3,))])


def write_ply(path: Path | str, v: np.ndarray, f: np.ndarray) -> Path:
    v, f = as_mesh(v, f)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment bim-6g M02 element mesh (metres, Z up)\n"
        f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
        f"element face {len(f)}\nproperty list uchar int vertex_indices\nend_header\n"
    )
    faces = np.empty(len(f), dtype=_FACE_DTYPE)
    faces["n"] = 3
    faces["idx"] = f
    with p.open("wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(v.astype("<f4").tobytes())
        fh.write(faces.tobytes())
    return p


def read_ply(path: Path | str) -> tuple[np.ndarray, np.ndarray]:
    data = Path(path).read_bytes()
    end = data.find(b"end_header\n")
    if end < 0 or not data.startswith(b"ply"):
        raise MeshError(f"not a PLY file: {path}")
    header = data[:end].decode("ascii").splitlines()
    if "format binary_little_endian 1.0" not in header:
        raise MeshError("only binary_little_endian PLY is supported")
    n_v = next(int(h.split()[2]) for h in header if h.startswith("element vertex"))
    n_f = next(int(h.split()[2]) for h in header if h.startswith("element face"))
    body = memoryview(data)[end + len(b"end_header\n") :]
    v = np.frombuffer(body, dtype="<f4", count=n_v * 3).reshape(n_v, 3).astype(np.float64)
    f = np.frombuffer(body, dtype=_FACE_DTYPE, count=n_f, offset=n_v * 12)["idx"].astype(np.int64)
    return v, f
