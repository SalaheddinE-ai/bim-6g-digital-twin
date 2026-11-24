# BIM-6G Electromagnetic Digital Twin

IFC/BIM building models + Sionna RT radio simulation + sparse-measurement reconstruction +
LLM assistant (hybrid RAG, tool calling). Research demonstrator, built module by module
(M00 to M10). Current module: **M02 - Geometry processing** (M00 foundation, M01 IFC ingestion done).

## Quick start (WSL2 Ubuntu, Python 3.12 via uv)

```bash
cd ~/projects/bim-6g-digital-twin
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.lock
cp .env.example .env
python scripts/check_env.py          # environment report
python -m pytest                      # full M00 test suite
uvicorn backend.main:app --reload     # http://127.0.0.1:8000/docs
```

## Status labels used everywhere

PASS (tested OK) | FAIL (ran and failed) | BLOCKED (cannot run, external/environment issue) |
NOT RUN | PARTIAL. A skipped test whose reason starts with `BLOCKED:` is reported as BLOCKED.

## Layout

`apps/` UI (M10) | `backend/` API + config + logging | `modules/` engineering modules |
`database/` persistence (later) | `storage/` generated files (git-ignored) | `configs/` YAML |
`tests/{unit,integration,end_to_end,fixtures}` | `docs/` | `scripts/` | `notebooks/`

See `docs/` for architecture, dependency report, limitations and decision records.


## M01 - IFC ingestion

```bash
pytest tests/unit/test_bim_* -v
python scripts/ingest_ifc.py tests/fixtures/real_ifc/*.ifc --samples-dir docs/samples
```
See `docs/module_specifications.md` and `docs/decisions/ADR-004-bim-data-model.md`.

## Geometry (M02)

```bash
python scripts/build_geometry.py tests/fixtures/real_ifc/BuildingBIMModel.ifc
# -> storage/geometry/<building_id>/{geometry.json, meshes/*.ply, validation_report.md}
```
Material classes in `configs/materials.yaml` are ASSUMPTIONS until confirmed (see docs/limitations.md).
