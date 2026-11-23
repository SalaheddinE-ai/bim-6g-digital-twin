# ADR-001: Python 3.12 managed by uv

Status: accepted. Context: WSL Ubuntu ships Python 3.14, the Sionna RT stack was verified end
to end on 3.12 only, and the LLM-side libraries are less proven on 3.14.
Decision: use uv-managed Python 3.12 in a project-local `.venv`; `requires-python = ">=3.12,<3.13"`.
Consequences: reproducible, no system changes. Revisit when 3.13/3.14 are verified.
