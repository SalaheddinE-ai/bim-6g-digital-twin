"""Collect environment facts. Never imports Mitsuba/Sionna (slow, may touch the GPU)."""

import importlib.metadata as md
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Verified together in docs/dependency_report.md
EXPECTED_PINS: dict[str, str] = {
    "sionna-rt": "2.2.0",
    "mitsuba": "3.9.1",
    "drjit": "1.5.0",
    "ifcopenshell": "0.9.0.post1",
}


def package_version(name: str) -> str | None:
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def nvidia_smi_gpus(timeout_s: float = 10.0) -> list[str] | None:
    """GPU lines from nvidia-smi, or None if the tool is missing or fails."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines or None


def collect_env_info() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "wsl": is_wsl(),
        "cpu_count": os.cpu_count(),
        "interpreter": sys.executable,
        "gpus": nvidia_smi_gpus(),
        "packages": {name: package_version(name) for name in EXPECTED_PINS},
    }
