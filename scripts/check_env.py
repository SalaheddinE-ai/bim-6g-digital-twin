"""Environment check: python scripts/check_env.py

PASS / FAIL for what must work, BLOCKED for optional capabilities (GPU ray tracing).
Exit code 1 only if something required FAILS.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.env_info import EXPECTED_PINS, collect_env_info  # noqa: E402
from modules.radio.probe import probe_backend  # noqa: E402


def main() -> int:
    info = collect_env_info()
    rows: list[tuple[str, str, str]] = []

    py_ok = info["python"].startswith("3.12.")
    rows.append(("Python 3.12", "PASS" if py_ok else "FAIL", info["python"]))
    rows.append(("WSL", "INFO", str(info["wsl"])))
    rows.append(("CPU threads", "INFO", str(info["cpu_count"])))

    for name, expected in EXPECTED_PINS.items():
        found = info["packages"][name]
        ok = found == expected
        rows.append((f"pin {name}", "PASS" if ok else "FAIL", f"found={found} expected={expected}"))

    gpus = info["gpus"]
    rows.append(("GPU visible (nvidia-smi)", "PASS" if gpus else "BLOCKED", "; ".join(gpus or [])))

    llvm = probe_backend("llvm")
    rows.append(("Sionna RT on LLVM (CPU)", "PASS" if llvm.ok else "FAIL", llvm.detail))
    cuda = probe_backend("cuda")
    rows.append(("Sionna RT on CUDA/OptiX", "PASS" if cuda.ok else "BLOCKED", cuda.detail))

    width = max(len(r[0]) for r in rows)
    for name, status, detail in rows:
        print(f"{status:8s} {name:<{width}}  {detail}")
    failed = [r for r in rows if r[1] == "FAIL"]
    print(f"\nRESULT: {'FAIL' if failed else 'OK'} ({len(failed)} failed)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
