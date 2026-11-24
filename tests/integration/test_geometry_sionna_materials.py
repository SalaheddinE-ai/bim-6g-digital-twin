"""Frequency ranges documented in configs/materials.yaml must equal Sionna RT's ITU table."""

import importlib.util
import json
import subprocess
import sys

import pytest

from backend.config import PROJECT_ROOT
from modules.geometry.materials import load_material_config

pytestmark = [
    pytest.mark.integration,
    pytest.mark.sionna,
    pytest.mark.skipif(
        importlib.util.find_spec("sionna") is None, reason="sionna-rt not installed"
    ),
]


def test_configured_materials_match_installed_sionna_itu_table():
    code = (
        "import json, sionna.rt.radio_materials.itu as itu;"
        "print('TABLE ' + json.dumps({k: [list(r) for r in v] "
        "for k, v in itu.ITU_MATERIALS_PROPERTIES.items()}))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr[-500:]
    table = json.loads(next(ln for ln in out.stdout.splitlines() if ln.startswith("TABLE "))[6:])
    cfg = load_material_config(PROJECT_ROOT / "configs" / "materials.yaml")
    for name, mat in cfg.em_materials.items():
        assert mat.itu_type in table, f"{name}: ITU type '{mat.itu_type}' unknown to Sionna"
        ours = sorted(tuple(r) for r in mat.valid_frequency_ranges_ghz)
        theirs = sorted(tuple(r) for r in table[mat.itu_type])
        assert ours == theirs, f"{name}: documented ranges differ from Sionna {theirs}"
