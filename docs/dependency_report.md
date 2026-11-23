# Dependency report (M00)

## Target environment (user machine, verified by user output)

ASUS ROG Strix G17, Ryzen 9 7945HX, RTX 4060 Laptop 8 GB, Windows 10 Home, WSL2 with Ubuntu
26.04 (project distro "Ubuntu"), driver 617.42. 32 threads and 7.4 GiB RAM visible in WSL.

## Pinned simulation stack

| Package | Version | Note |
|---|---|---|
| Python | 3.12.x (uv-managed) | system Python 3.14 left untouched (ADR-001) |
| sionna-rt | 2.2.0 | requires Python >= 3.10, pins mitsuba/drjit |
| mitsuba | 3.9.1 | LLVM backend needs libLLVM (apt `llvm`) |
| drjit | 1.5.0 | |
| ifcopenshell | 0.9.0.post1 | wheels exist for cp311 to cp314 |

Exact versions of everything else are in `requirements.lock` (compiled with uv for 3.12).

## Verification evidence

| Check | Where | Result |
|---|---|---|
| sionna-rt + ifcopenshell install, Python 3.12 | user's WSL | PASS |
| `smoke_env.py llvm` (real radio map 20x20) | user's WSL | PASS |
| `smoke_env.py cuda` | user's WSL | FAIL: `libnvoptix.so.1` not loadable (WSL2 OptiX) |
| GPU visible via `nvidia-smi -L` in WSL | user's WSL | PASS |
| Full M00 suite from `requirements.lock` in fresh venv | author sandbox (no GPU, 1 vCPU) | 29 passed, 1 BLOCKED |
| Full M00 suite on the user's machine | user's WSL | NOT RUN until the user pastes the output |

## Not verified

- CUDA/OptiX on WSL2 (needs Mitsuba's unofficial OptiX workaround, see `limitations.md`).
- Python 3.13/3.14 with the full stack (wheels exist, never run end to end).
- Blender/Bonsai (not required by the pipeline, ADR-004 if ever added).

## Known warning

Starlette deprecation warning about `httpx` in `TestClient`; harmless, test-only.
