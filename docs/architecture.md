# Architecture (M00 baseline)

Layers (from the master prompt): **A** Streamlit UI -> **B** FastAPI backend -> **C** AI
orchestration (LangGraph) -> **D** engineering modules -> **E** persistence (SQLite in dev,
PostgreSQL later) + filesystem storage.

## Module roadmap

| Module | Scope | Status |
|---|---|---|
| M00 | Foundation: config, logging, API skeleton, env check, tests | see `testing_strategy.md` |
| M01 | IFC ingestion (IfcOpenShell) | tests PASS (author sandbox) - rerun on user machine pending |
| M02 | Geometry processing | tests PASS (author sandbox) - rerun on user machine pending |
| M03 | BIM spatial graph | NOT RUN |
| M04 | Radio scene builder (IFC meshes -> Mitsuba scene) | NOT RUN |
| M05 | Radio simulation (Sionna RT) | NOT RUN |
| M06 | Measurements + graph reconstruction | NOT RUN |
| M07 | Scenario management | NOT RUN |
| M08 | LLM assistant (hybrid RAG, tools) | NOT RUN |
| M09 | Backend API | NOT RUN |
| M10 | Interface | NOT RUN |

## Radio backend selection

`radio.backend` in `configs/default.yaml` (or `BIM6G_RADIO__BACKEND`): `auto | cuda | llvm`.
`modules/radio/probe.py` runs a real tiny Sionna RT simulation in a subprocess to decide
whether CUDA/OptiX works. `auto` falls back to LLVM (CPU) with a logged warning.
GPU is optional by design (ADR-002).

## Conventions

- Configuration: YAML defaults < `<project root>/.env` < environment (`BIM6G_*`, nested with `__`).
- Every module: explicit contracts, unit tests, integration tests, logging, docs.
- Simulated data is never described as real measurements.
