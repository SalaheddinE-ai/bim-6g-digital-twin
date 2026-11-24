"""Synthetic IFC4 scenes with real box geometry, built with the IfcOpenShell API.

Every element is a box: local X = ``length`` (0..L), local Y = ``thickness`` (0..T),
local Z = ``height`` (0..H); placed by rotating ``rot_deg`` about Z and translating (x, y, z)
in METRES (the API converts to the file's length unit), so expected world boxes are exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Spec:
    ifc_class: str
    name: str
    pos: tuple[float, float, float]
    size: (
        tuple[float, float, float] | None
    )  # (length, thickness, height) in metres; None = no geometry
    rot_deg: float = 0.0
    materials: tuple[str, ...] = ()


def expected_bbox(spec: Spec, offset=(0.0, 0.0, 0.0)):
    """Axis-aligned world box of the spec's box, minus ``offset`` (metres)."""
    length, thick, height = spec.size
    local = np.array([[x, y, z] for x in (0, length) for y in (0, thick) for z in (0, height)])
    c, s = np.cos(np.radians(spec.rot_deg)), np.sin(np.radians(spec.rot_deg))
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    world = local @ rot.T + np.asarray(spec.pos) - np.asarray(offset)
    return world.min(axis=0), world.max(axis=0)


SCENE = (
    Spec(
        "IfcWall",
        "W1",
        (1.0, 2.0, 0.0),
        (5.0, 0.2, 3.0),
        materials=("Concrete - Cast-in-Place Concrete", "Plasterboard"),
    ),
    Spec("IfcWall", "W2", (10.0, 20.0, 0.0), (4.0, 0.3, 3.0), rot_deg=90.0),
    Spec("IfcWall", "W3_nogeom", (0.0, 0.0, 0.0), None),
    Spec("IfcDoor", "D1", (3.0, 2.0, 0.0), (0.9, 0.1, 2.1), materials=("Door - Panel",)),
    Spec("IfcWindow", "WIN1", (6.0, 2.0, 0.9), (1.2, 0.1, 1.2), materials=("Glass",)),
    Spec("IfcSlab", "SLAB1", (0.0, 0.0, -0.2), (12.0, 8.0, 0.2)),
    Spec("IfcColumn", "COL1", (8.0, 5.0, 0.0), (0.3, 0.3, 3.0), materials=("Zebra Stripe Fabric",)),
    Spec("IfcSpace", "ROOM1", (1.0, 3.0, 0.0), (4.0, 3.0, 2.8)),
)


def build_ifc(
    path: Path,
    specs=SCENE,
    *,
    unit: str = "MILLIMETERS",
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Path:
    import ifcopenshell.api as api

    run = api.run
    f = run("project.create_file", version="IFC4")
    proj = run("root.create_entity", f, ifc_class="IfcProject", name="Geometry Fixture")
    run("unit.assign_unit", f, length={"is_metric": True, "raw": unit})
    ctx = run("context.add_context", f, context_type="Model")
    body = run(
        "context.add_context", f, context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=ctx,
    )  # fmt: skip
    site = run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    bld = run("root.create_entity", f, ifc_class="IfcBuilding", name="Building")
    sto = run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 0")
    run("aggregate.assign_object", f, products=[site], relating_object=proj)
    run("aggregate.assign_object", f, products=[bld], relating_object=site)
    run("aggregate.assign_object", f, products=[sto], relating_object=bld)

    materials: dict[str, object] = {}
    for spec in specs:
        el = run("root.create_entity", f, ifc_class=spec.ifc_class, name=spec.name)
        if spec.size is not None:
            pos = np.asarray(spec.pos) + np.asarray(offset)
            c, s = np.cos(np.radians(spec.rot_deg)), np.sin(np.radians(spec.rot_deg))
            m = np.array([[c, -s, 0, pos[0]], [s, c, 0, pos[1]], [0, 0, 1, pos[2]], [0, 0, 0, 1]])
            run("geometry.edit_object_placement", f, product=el, matrix=m, is_si=True)
            length, thick, height = spec.size
            rep = run(
                "geometry.add_wall_representation", f, context=body, length=length,
                height=height, thickness=thick,
            )  # fmt: skip
            run("geometry.assign_representation", f, product=el, representation=rep)
        if spec.ifc_class == "IfcSpace":
            run("aggregate.assign_object", f, products=[el], relating_object=sto)
        else:
            run("spatial.assign_container", f, products=[el], relating_structure=sto)
        if spec.materials:
            cset = run(
                "material.add_material_set", f, name=spec.name, set_type="IfcMaterialConstituentSet"
            )
            for mat_name in spec.materials:
                mat = materials.get(mat_name) or run("material.add_material", f, name=mat_name)
                materials[mat_name] = mat
                run("material.add_constituent", f, constituent_set=cset, material=mat)
            run("material.assign_material", f, products=[el], material=cset)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(path))
    return path
