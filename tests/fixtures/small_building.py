"""Deterministic generator for the small IFC4 test building (no IfcOpenShell needed).

Layout (project unit: millimetre, to exercise unit conversion), one storey 10 m x 6 m:

    W_North ------------------------------   (y = 6000)   W01 window in W_North
    |  Room A       | D01 |   Room B    |
    W_West        W_Part              W_East
    |               |                   |
    W_South ------ D02 -----------------    (y = 0)      D02 door in W_South (exterior)

* 4 IfcWall + 1 IfcWallStandardCase (W_Part) -> 5 walls; the first 5 carry extruded geometry
* D01 (interior, in W_Part, 900x2100) and D02 (exterior, in W_South) -> 2 doors
* 1 IfcCurtainWall (in the storey) aggregating panel door D03 (no opening: host_kind=aggregate)
* W01 (window, in W_North) -> 1 window;  1 slab;  1 column with NO name/properties/material
* 2 IfcSpace (Room A, Room B) aggregated in the storey, with IfcRelSpaceBoundary
* materials: Concrete (walls), Wood (doors), Glass (window); psets on walls and D01
* doors/window/slab/column have no representation (exercises 'missing geometry' reporting)
"""

from __future__ import annotations

import uuid
from pathlib import Path

_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
_NS = uuid.UUID("6c1a3d0e-5b5e-4c55-9d6c-000000000b16")


def make_guid(name: str) -> str:
    """Deterministic, valid 22-character IFC GlobalId derived from a name."""
    n = uuid.uuid5(_NS, name).int
    out = ""
    for _ in range(22):
        out = _CHARS[n % 64] + out
        n //= 64
    return out


NAMES = [
    "project", "site", "building", "storey", "RoomA", "RoomB",
    "W_South", "W_North", "W_West", "W_East", "W_Part",
    "D01", "D02", "D03", "CurtainWall", "W01", "Slab", "Column",
    "OpenD01", "OpenD02", "OpenW01",
]  # fmt: skip
GUIDS: dict[str, str] = {n: make_guid(n) for n in NAMES}


def _s(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def _f(v: float) -> str:
    return repr(float(v))


class _Step:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str) -> str:
        self.lines.append(f"#{len(self.lines) + 1}={text};")
        return f"#{len(self.lines)}"

    def guid(self, key: str) -> str:
        return _s(GUIDS[key])


def _header() -> str:
    return (
        "ISO-10303-21;\nHEADER;\n"
        "FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');\n"
        "FILE_NAME('small_building.ifc','2026-01-01T00:00:00',('bim-6g'),('bim-6g'),"
        "'bim-6g generator','bim-6g tests','');\n"
        "FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
    )


_FOOTER = "ENDSEC;\nEND-ISO-10303-21;\n"


def _base(w: _Step) -> dict[str, str]:
    pt0 = w.add("IFCCARTESIANPOINT((0.,0.,0.))")
    dz = w.add("IFCDIRECTION((0.,0.,1.))")
    dx = w.add("IFCDIRECTION((1.,0.,0.))")
    dy = w.add("IFCDIRECTION((0.,1.,0.))")
    world = w.add(f"IFCAXIS2PLACEMENT3D({pt0},{dz},{dx})")
    ctx = w.add(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,{world},$)")
    length = w.add("IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)")
    angle = w.add("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")
    units = w.add(f"IFCUNITASSIGNMENT(({length},{angle}))")
    return {"pt0": pt0, "dz": dz, "dx": dx, "dy": dy, "world": world, "ctx": ctx, "units": units}


def build_empty_ifc() -> str:
    """Valid IFC4 file with a project but no building elements."""
    w = _Step()
    b = _base(w)
    w.add(f"IFCPROJECT({w.guid('project')},$,'Empty Project',$,$,$,$,({b['ctx']}),{b['units']})")
    return _header() + "\n".join(w.lines) + "\n" + _FOOTER


def build_no_entities_ifc() -> str:
    """Syntactically valid IFC4 file whose DATA section is empty (no project at all)."""
    return _header() + _FOOTER


def build_small_building_ifc() -> str:
    w = _Step()
    b = _base(w)
    pt0, dz, dx, dy, world, ctx = (b[k] for k in ("pt0", "dz", "dx", "dy", "world", "ctx"))

    project = w.add(
        f"IFCPROJECT({w.guid('project')},$,'Small Test Project',$,$,$,$,({ctx}),{b['units']})"
    )
    site_pl = w.add(f"IFCLOCALPLACEMENT($,{world})")
    site = w.add(f"IFCSITE({w.guid('site')},$,'Test Site',$,$,{site_pl},$,$,.ELEMENT.,$,$,$,$,$)")
    bld_pl = w.add(f"IFCLOCALPLACEMENT({site_pl},{world})")
    bld = w.add(
        f"IFCBUILDING({w.guid('building')},$,'Test Building',$,$,{bld_pl},$,$,.ELEMENT.,$,$,$)"
    )
    st_pl = w.add(f"IFCLOCALPLACEMENT({bld_pl},{world})")
    storey = w.add(
        f"IFCBUILDINGSTOREY({w.guid('storey')},$,'Ground Floor',$,$,{st_pl},$,$,.ELEMENT.,0.)"
    )

    def place(x: float, y: float, z: float, ref: str) -> str:
        p = w.add(f"IFCCARTESIANPOINT(({_f(x)},{_f(y)},{_f(z)}))")
        a = w.add(f"IFCAXIS2PLACEMENT3D({p},{dz},{ref})")
        return w.add(f"IFCLOCALPLACEMENT({st_pl},{a})")

    def wall_shape(length: float, thickness: float, height: float) -> str:
        c = w.add(f"IFCCARTESIANPOINT(({_f(length / 2)},0.))")
        a2 = w.add(f"IFCAXIS2PLACEMENT2D({c},$)")
        prof = w.add(f"IFCRECTANGLEPROFILEDEF(.AREA.,$,{a2},{_f(length)},{_f(thickness)})")
        a3 = w.add(f"IFCAXIS2PLACEMENT3D({pt0},$,$)")
        solid = w.add(f"IFCEXTRUDEDAREASOLID({prof},{a3},{dz},{_f(height)})")
        rep = w.add(f"IFCSHAPEREPRESENTATION({ctx},'Body','SweptSolid',({solid}))")
        return w.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,({rep}))")

    # ---- walls (4 IfcWall + 1 IfcWallStandardCase), geometry attached ------------------------
    wall_specs = [  # key, class, name, tag, x, y, ref-direction, length
        ("W_South", "IFCWALL", "W_South", "W-001", 0, 0, dx, 10000),
        ("W_North", "IFCWALL", "W_North", "W-002", 0, 6000, dx, 10000),
        ("W_West", "IFCWALL", "W_West", "W-003", 0, 0, dy, 6000),
        ("W_East", "IFCWALL", "W_East", "W-004", 10000, 0, dy, 6000),
        ("W_Part", "IFCWALLSTANDARDCASE", "W_Part", "W-005", 5000, 0, dy, 6000),
    ]
    walls: dict[str, str] = {}
    for key, cls, name, tag, x, y, ref, length in wall_specs:
        pl = place(x, y, 0, ref)
        shp = wall_shape(length, 200, 3000)
        walls[key] = w.add(
            f"{cls}({w.guid(key)},$,{_s(name)},$,'Basic Wall:Generic 200',{pl},{shp},"
            f"{_s(tag)},.STANDARD.)"
        )

    # ---- openings + doors + window ---------------------------------------------------------
    def opening(key: str, name: str, x: float, y: float, z: float, ref: str, host: str) -> str:
        pl = place(x, y, z, ref)
        op = w.add(f"IFCOPENINGELEMENT({w.guid(key)},$,{_s(name)},$,$,{pl},$,$,.OPENING.)")
        w.add(f"IFCRELVOIDSELEMENT({_s(make_guid('void' + key))},$,$,$,{walls[host]},{op})")
        return op

    def door(key: str, name: str, tag: str, x: float, y: float, ref: str, host: str) -> str:
        op = opening("Open" + key, "Opening " + name, x, y, 0, ref, host)
        pl = place(x, y, 0, ref)
        d = w.add(f"IFCDOOR({w.guid(key)},$,{_s(name)},$,$,{pl},$,{_s(tag)},2100.,900.,.DOOR.,$,$)")
        w.add(f"IFCRELFILLSELEMENT({_s(make_guid('fill' + key))},$,$,$,{op},{d})")
        return d

    d01 = door("D01", "D01", "DR-01", 5000, 2500, dy, "W_Part")
    d02 = door("D02", "D02", "DR-02", 2000, 0, dx, "W_South")
    op_w = opening("OpenW01", "Opening W01", 7500, 6000, 1000, dx, "W_North")
    pl_w = place(7500, 6000, 1000, dx)
    w01 = w.add(f"IFCWINDOW({w.guid('W01')},$,'W01',$,$,{pl_w},$,'WN-01',1200.,1500.,.WINDOW.,$,$)")
    w.add(f"IFCRELFILLSELEMENT({_s(make_guid('fillW01'))},$,$,$,{op_w},{w01})")

    cw = w.add(
        f"IFCCURTAINWALL({w.guid('CurtainWall')},$,'CW01',$,$,{place(2000, 6000, 0, dx)},$,'CW-01',"
        ".NOTDEFINED.)"
    )
    d03 = w.add(
        f"IFCDOOR({w.guid('D03')},$,'D03',$,$,{place(2500, 6000, 0, dx)},$,'DR-03',2100.,900.,"
        ".DOOR.,$,$)"
    )
    w.add(f"IFCRELAGGREGATES({_s(make_guid('aggcw'))},$,$,$,{cw},({d03}))")

    slab = w.add(
        f"IFCSLAB({w.guid('Slab')},$,'Slab 01',$,$,{place(0, 0, 0, dx)},$,'SL-01',.FLOOR.)"
    )
    column = w.add(f"IFCCOLUMN({w.guid('Column')},$,$,$,$,{place(5000, 3000, 0, dx)},$,$,$)")

    # ---- spaces ------------------------------------------------------------------------------
    room_a = w.add(
        f"IFCSPACE({w.guid('RoomA')},$,'Room A',$,$,{place(0, 0, 0, dx)},$,'Living room',"
        ".ELEMENT.,.INTERNAL.,0.)"
    )
    room_b = w.add(
        f"IFCSPACE({w.guid('RoomB')},$,'Room B',$,$,{place(5000, 0, 0, dx)},$,'Bedroom',"
        ".ELEMENT.,.INTERNAL.,0.)"
    )

    # ---- spatial structure ---------------------------------------------------------------------
    def agg(key: str, parent: str, children: list[str]) -> None:
        w.add(
            f"IFCRELAGGREGATES({_s(make_guid('agg' + key))},$,$,$,{parent},({','.join(children)}))"
        )

    agg("a", project, [site])
    agg("b", site, [bld])
    agg("c", bld, [storey])
    agg("d", storey, [room_a, room_b])
    contained = [*walls.values(), d01, d02, cw, w01, slab, column]  # D03 only via cw
    w.add(
        f"IFCRELCONTAINEDINSPATIALSTRUCTURE({_s(make_guid('contain'))},$,$,$,"
        f"({','.join(contained)}),{storey})"
    )

    # ---- space boundaries ----------------------------------------------------------------------
    def bound(i: int, space: str, el: str, inner: bool = True) -> None:
        kind = ".INTERNAL." if inner else ".EXTERNAL."
        w.add(
            f"IFCRELSPACEBOUNDARY({_s(make_guid(f'sb{i}'))},$,$,$,{space},{el},$,.PHYSICAL.,{kind})"
        )

    bound(1, room_a, walls["W_Part"])
    bound(2, room_b, walls["W_Part"])
    bound(3, room_a, d01)
    bound(4, room_b, d01)
    bound(5, room_a, walls["W_South"], False)
    bound(6, room_b, walls["W_North"], False)
    bound(7, room_a, d02, False)
    bound(8, room_b, w01, False)

    # ---- materials ---------------------------------------------------------------------------
    def material(name: str, objs: list[str]) -> None:
        m = w.add(f"IFCMATERIAL({_s(name)},$,{_s(name)})")
        w.add(
            f"IFCRELASSOCIATESMATERIAL({_s(make_guid('mat' + name))},$,$,$,({','.join(objs)}),{m})"
        )

    material("Concrete", list(walls.values()))
    material("Wood", [d01, d02, d03])
    material("Glass", [w01])

    # ---- property sets ------------------------------------------------------------------------
    def pset(key: str, name: str, props: list[str], objs: list[str]) -> None:
        ps = w.add(
            f"IFCPROPERTYSET({_s(make_guid('ps' + key))},$,{_s(name)},$,({','.join(props)}))"
        )
        w.add(
            f"IFCRELDEFINESBYPROPERTIES({_s(make_guid('rd' + key))},$,$,$,({','.join(objs)}),{ps})"
        )

    def prop(name: str, typed_value: str) -> str:
        return w.add(f"IFCPROPERTYSINGLEVALUE({_s(name)},$,{typed_value},$)")

    ext = [walls["W_South"], walls["W_North"], walls["W_West"], walls["W_East"]]
    pset("ext", "Pset_WallCommon", [prop("IsExternal", "IFCBOOLEAN(.T.)"),
                                    prop("FireRating", "IFCLABEL('1HR')")], ext)  # fmt: skip
    pset("int", "Pset_WallCommon", [prop("IsExternal", "IFCBOOLEAN(.F.)")], [walls["W_Part"]])
    pset("d01", "Pset_DoorCommon", [prop("FireRating", "IFCLABEL('30min')"),
                                    prop("IsExternal", "IFCBOOLEAN(.F.)")], [d01])  # fmt: skip

    return _header() + "\n".join(w.lines) + "\n" + _FOOTER


EXPECTED = {
    "counts": {"project": 1, "site": 1, "building": 1, "storey": 1, "space": 2, "wall": 5,
               "curtain_wall": 1, "door": 3, "window": 1, "slab": 1, "column": 1},
}  # fmt: skip


def write(path: Path | str, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


if __name__ == "__main__":  # python -m tests.fixtures.small_building
    out = write(Path(__file__).with_name("small_building.ifc"), build_small_building_ifc())
    print(out)
