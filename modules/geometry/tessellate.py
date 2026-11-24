"""IfcOpenShell tessellation (world coordinates, metres). The only file here needing IfcOpenShell.

IfcOpenShell reports geometry in METRES whatever the file's length unit (verified on millimetre,
centimetre and metre files in tests). Opening subtractions are kept (walls have holes where
doors/windows sit), so door/window meshes can be exported as separate fillers.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RawMesh:
    step_id: int
    global_id: str | None
    vertices: np.ndarray  # (N, 3) metres, world frame
    faces: np.ndarray  # (M, 3)


def tessellate_with_ifcopenshell(
    ifc, step_ids: Iterable[int], num_threads: int = 1
) -> tuple[dict[int, RawMesh], dict[int, str]]:
    """Return ({step_id: RawMesh}, {step_id: failure message}) for the requested products."""
    import ifcopenshell.geom as geom

    wanted = list(dict.fromkeys(step_ids))
    meshes: dict[int, RawMesh] = {}
    failures: dict[int, str] = {}
    if not wanted:
        return meshes, failures

    products = []
    for sid in wanted:
        try:
            products.append(ifc.by_id(sid))
        except Exception as exc:  # noqa: BLE001
            failures[sid] = f"entity #{sid} not found: {exc}"

    settings = geom.settings()
    settings.set("use-world-coords", True)
    try:
        it = geom.iterator(settings, ifc, max(1, int(num_threads)), include=products)
        ok = it.initialize()
    except Exception as exc:  # noqa: BLE001
        msg = f"geometry iterator failed: {exc}"
        return meshes, {**failures, **{sid: msg for sid in wanted if sid not in failures}}
    while ok:
        try:
            shape = it.get()
            verts = np.asarray(shape.geometry.verts, dtype=np.float64).reshape(-1, 3)
            faces = np.asarray(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
            meshes[shape.id] = RawMesh(shape.id, shape.guid, verts, faces)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tessellation of one shape failed: %s", exc)
        ok = it.next()
    for sid in wanted:
        if sid not in meshes and sid not in failures:
            failures[sid] = "IfcOpenShell produced no shape for this element"
    return meshes, failures
