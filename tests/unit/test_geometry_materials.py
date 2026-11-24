import pytest
import yaml

from backend.config import PROJECT_ROOT
from modules.geometry.materials import (
    MaterialConfigError,
    MaterialMapper,
    load_material_config,
)

MATERIALS_FILE = PROJECT_ROOT / "configs" / "materials.yaml"


@pytest.fixture(scope="module")
def mapper():
    return MaterialMapper.from_file(MATERIALS_FILE)


def _write(tmp_path, data):
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def _valid():
    return {
        "version": 1,
        "em_materials": {
            "concrete": {
                "itu_type": "concrete",
                "valid_frequency_ranges_ghz": [[1.0, 100.0]],
                "source": "ITU-R P.2040",
            }
        },
        "rules": [{"id": "c", "priority": 1, "em_material": "concrete", "pattern": "(?i)concrete"}],
        "category_fallbacks": {"wall": "concrete"},
    }


# ---- the shipped configuration is traceable ----------------------------------------------------
def test_shipped_config_is_traceable_and_consistent():
    cfg = load_material_config(MATERIALS_FILE)
    assert cfg.em_materials, "no radio materials defined"
    for name, m in cfg.em_materials.items():
        assert m.source.strip(), f"{name} has no documented source"
    assert "floorboard" not in cfg.em_materials  # ITU floorboard is invalid at 5 GHz


def test_shipped_materials_cover_5ghz_and_report_gaps(mapper):
    assert all(mapper.frequency_coverage(5e9).values())
    assert mapper.frequency_coverage(60e9)["brick"] is False  # brick range is 1-40 GHz
    assert mapper.frequency_coverage(60e9)["concrete"] is True


# ---- assignment rules: names are ASSUMPTIONS, never "verified" -----------------------------------
@pytest.mark.parametrize(
    ("category", "names", "expected"),
    [
        ("window", ["Glass", "Sash"], "glass"),
        ("wall", ["Masonry - Concrete Block"], "concrete"),  # concrete outranks masonry
        ("wall", ["Metal - Stud Layer", "Plasterboard"], "plasterboard"),  # studs do not make metal
        ("slab", ["Wood - Flooring"], "wood"),
        ("door", ["Door - Panel", "Door - Frame", "Glass", "Metal - Aluminum"], "wood"),
        ("column", ["Metal - Steel - 345 MPa"], "metal"),
        ("slab", ["Metal - Sunscreen"], "metal"),
        ("wall", ["Brick, Common"], "brick"),
    ],
)
def test_name_rules(mapper, category, names, expected):
    a = mapper.assign(category, names)
    assert a.em_material == expected and a.status == "assumed_from_name"
    assert "ASSUMPTION" in a.basis


def test_composite_is_flagged_and_lists_candidates(mapper):
    a = mapper.assign("wall", ["Metal - Stud Layer", "Plasterboard", "Insulation"])
    assert a.composite and a.candidates == ["plasterboard", "metal"]


def test_single_class_with_unmatched_extras_is_not_composite(mapper):
    assert not mapper.assign("window", ["Glass", "Sash"]).composite


def test_unmatched_names_fall_back_to_category_and_say_so(mapper):
    a = mapper.assign("column", ["Zebra Stripe Fabric"])
    assert (a.em_material, a.status, a.rule) == (
        "concrete",
        "assumed_from_category",
        "fallback:column",
    )
    assert mapper.assign("door", []).em_material == "wood"


def test_no_rule_no_fallback_is_unmapped(mapper):
    a = mapper.assign("space", ["Anything"])
    assert a.em_material is None and a.status == "unmapped"


def test_override_by_global_id_wins(tmp_path):
    cfg = _valid()
    cfg["overrides"] = {"GID123": "concrete"}
    m = MaterialMapper.from_file(_write(tmp_path, cfg))
    a = m.assign("door", ["whatever"], "GID123")
    assert (a.em_material, a.status) == ("concrete", "user_override")


def test_statuses_are_never_verified(mapper):
    seen = {mapper.assign(c, n).status for c in ("wall", "door", "space") for n in ([], ["Glass"])}
    assert seen <= {"assumed_from_name", "assumed_from_category", "unmapped", "user_override"}


# ---- invalid configurations are rejected ---------------------------------------------------------
def test_valid_minimal_config_loads(tmp_path):
    assert load_material_config(_write(tmp_path, _valid())).version == 1


def test_missing_file(tmp_path):
    with pytest.raises(MaterialConfigError):
        load_material_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["rules"][0].update(em_material="unobtainium"),
        lambda c: c["rules"][0].update(pattern="(unclosed"),
        lambda c: c["em_materials"]["concrete"].update(source=""),
        lambda c: c["rules"].append(dict(c["rules"][0])),  # duplicate id
        lambda c: c["category_fallbacks"].update(wall="unobtainium"),
        lambda c: (
            c["overrides"].update(G1="unobtainium")
            if "overrides" in c
            else c.update(overrides={"G1": "x"})
        ),
        lambda c: c.update(surprise=1),  # unknown key
    ],
)
def test_bad_configs_are_rejected(tmp_path, mutate):
    cfg = _valid()
    mutate(cfg)
    with pytest.raises(MaterialConfigError):
        load_material_config(_write(tmp_path, cfg))
