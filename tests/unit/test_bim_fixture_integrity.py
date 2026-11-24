"""The hand-generated IFC fixture is self-consistent (pure Python, no IfcOpenShell)."""

import re
from pathlib import Path

from modules.bim.validator import GLOBAL_ID_RE
from tests.fixtures.small_building import (
    GUIDS,
    build_empty_ifc,
    build_small_building_ifc,
    make_guid,
)

TEXT = build_small_building_ifc()
ENTITY_RE = re.compile(r"^#(\d+)=([A-Z0-9_]+)\((.*)\);$")


def _entities(text):
    out = {}
    for line in text.splitlines():
        m = ENTITY_RE.match(line)
        if m:
            out[int(m.group(1))] = (m.group(2), m.group(3))
    return out


def _arity(args: str) -> int:
    depth, n, in_str = 0, 1, False
    for ch in args:
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                n += 1
    return n


def test_entity_ids_unique_and_references_resolve():
    ents = _entities(TEXT)
    data_lines = [ln for ln in TEXT.splitlines() if ln.startswith("#")]
    assert len(ents) == len(data_lines)  # every line parsed, so ids are unique
    for eid, (_, args) in ents.items():
        for ref in re.findall(r"#(\d+)", re.sub(r"'[^']*'", "''", args)):
            assert int(ref) in ents, f"#{eid} references missing #{ref}"
            assert int(ref) < eid, f"#{eid} forward-references #{ref}"


def test_guids_valid_and_unique():
    guids = re.findall(r"^#\d+=IFC[A-Z0-9]+\('([^']{22})'", TEXT, flags=re.M)
    assert len(guids) >= 30
    assert len(set(guids)) == len(guids)
    assert all(GLOBAL_ID_RE.match(g) for g in guids)
    assert all(GLOBAL_ID_RE.match(g) for g in GUIDS.values())
    assert make_guid("x") == make_guid("x") != make_guid("y")


def test_attribute_arity_matches_ifc4():
    """Attribute counts per IFC4 entity definition (guards against typos in the generator)."""
    expected = {
        "IFCPROJECT": 9, "IFCSITE": 14, "IFCBUILDING": 12, "IFCBUILDINGSTOREY": 10,
        "IFCSPACE": 11, "IFCWALL": 9, "IFCWALLSTANDARDCASE": 9, "IFCDOOR": 13, "IFCWINDOW": 13,
        "IFCSLAB": 9, "IFCCURTAINWALL": 9, "IFCCOLUMN": 9, "IFCOPENINGELEMENT": 9,
        "IFCRELVOIDSELEMENT": 6,
        "IFCRELFILLSELEMENT": 6, "IFCRELAGGREGATES": 6, "IFCRELCONTAINEDINSPATIALSTRUCTURE": 6,
        "IFCRELSPACEBOUNDARY": 9, "IFCMATERIAL": 3, "IFCRELASSOCIATESMATERIAL": 6,
        "IFCPROPERTYSET": 5, "IFCRELDEFINESBYPROPERTIES": 6, "IFCPROPERTYSINGLEVALUE": 4,
        "IFCLOCALPLACEMENT": 2, "IFCAXIS2PLACEMENT3D": 3, "IFCEXTRUDEDAREASOLID": 4,
        "IFCRECTANGLEPROFILEDEF": 5, "IFCSHAPEREPRESENTATION": 4,
        "IFCGEOMETRICREPRESENTATIONCONTEXT": 6,
    }  # fmt: skip
    for eid, (cls, args) in _entities(TEXT).items():
        if cls in expected:
            assert _arity(args) == expected[cls], f"#{eid} {cls}: {_arity(args)} attributes"


def test_expected_entity_counts():
    classes = [c for c, _ in _entities(TEXT).values()]
    assert classes.count("IFCWALL") + classes.count("IFCWALLSTANDARDCASE") == 5
    assert classes.count("IFCDOOR") == 3
    assert classes.count("IFCCURTAINWALL") == 1
    assert classes.count("IFCWINDOW") == 1
    assert classes.count("IFCSPACE") == 2
    assert "IFC4" in TEXT.split("FILE_SCHEMA")[1][:12]


def test_empty_fixture_has_project_only():
    classes = [c for c, _ in _entities(build_empty_ifc()).values()]
    assert classes.count("IFCPROJECT") == 1
    assert not {"IFCWALL", "IFCDOOR", "IFCBUILDINGSTOREY"} & set(classes)


def test_committed_fixture_matches_generator():
    committed = Path(__file__).parents[1] / "fixtures" / "small_building.ifc"
    assert committed.read_text(encoding="utf-8") == TEXT, (
        "regenerate with: python -m tests.fixtures.small_building"
    )
