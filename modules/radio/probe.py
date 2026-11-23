"""Backend probe for Sionna RT / Mitsuba.

A real tiny ray-tracing run (built-in box scene, 5 GHz, one transmitter) executed in a
SUBPROCESS, because a broken CUDA/OptiX setup can fail late (at scene load) or crash the
interpreter. Run directly:  python -m modules.radio.probe cuda|llvm
"""

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

VARIANTS = {"cuda": "cuda_ad_mono_polarized", "llvm": "llvm_ad_mono_polarized"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OK_PREFIX = "PROBE_OK "


class BackendUnavailableError(RuntimeError):
    """The requested radio backend cannot run a real simulation."""


@dataclass(frozen=True)
class ProbeResult:
    kind: str
    variant: str
    ok: bool
    seconds: float
    detail: str


def _run_probe_in_process(kind: str) -> dict:
    import mitsuba as mi

    mi.set_variant(VARIANTS[kind])  # must happen BEFORE importing sionna.rt
    import sionna.rt as rt

    scene = rt.load_scene(rt.scene.box_one_screen)
    scene.frequency = 5e9
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = scene.tx_array
    scene.add(rt.Transmitter("AP_PROBE", position=[0, 0, 1.5]))
    radio_map = rt.RadioMapSolver()(
        scene, cell_size=(0.5, 0.5), samples_per_tx=100_000, max_depth=3
    )
    return {"variant": mi.variant(), "path_gain_shape": list(radio_map.path_gain.shape)}


def probe_backend(kind: str, timeout_s: float = 120.0) -> ProbeResult:
    if kind not in VARIANTS:
        raise ValueError(f"Unknown backend '{kind}', expected one of {sorted(VARIANTS)}")
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "modules.radio.probe", kind],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(kind, VARIANTS[kind], False, timeout_s, f"timeout after {timeout_s}s")
    seconds = time.perf_counter() - start
    for line in proc.stdout.splitlines():
        if line.startswith(_OK_PREFIX) and proc.returncode == 0:
            return ProbeResult(kind, VARIANTS[kind], True, seconds, line[len(_OK_PREFIX) :])
    lines = [ln for ln in (proc.stderr + proc.stdout).splitlines() if ln.strip()]
    detail = lines[-1][:300] if lines else f"exit code {proc.returncode}, no output"
    return ProbeResult(kind, VARIANTS[kind], False, seconds, detail)


def resolve_backend(preference: str, timeout_s: float = 120.0, probe=probe_backend) -> str:
    """Map the configured preference (auto|cuda|llvm) to a usable backend kind."""
    if preference == "llvm":
        return "llvm"
    if preference == "cuda":
        result = probe("cuda", timeout_s)
        if not result.ok:
            raise BackendUnavailableError(f"CUDA backend unavailable: {result.detail}")
        return "cuda"
    if preference == "auto":
        result = probe("cuda", timeout_s)
        if result.ok:
            return "cuda"
        log.warning("CUDA backend unavailable, falling back to LLVM (CPU): %s", result.detail)
        return "llvm"
    raise ValueError(f"Unknown backend preference '{preference}'")


def main(argv: list[str]) -> int:
    kind = argv[1] if len(argv) > 1 else "llvm"
    try:
        info = _run_probe_in_process(kind)
    except Exception as exc:  # noqa: BLE001 - any failure means "backend unusable"
        print(f"PROBE_FAIL {type(exc).__name__}: {exc}")
        return 1
    print(_OK_PREFIX + json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
