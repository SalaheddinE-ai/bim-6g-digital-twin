# ADR-003: Dependency ranges in pyproject, exact versions in a lock file; layered config

Status: accepted. `pyproject.toml` has ranges (exact pins only for the simulation stack);
`requirements.lock` (uv pip compile) pins everything for reproducibility.
Config: YAML defaults overridden by `.env` and `BIM6G_*` environment variables, validated by
pydantic (unknown keys inside sections and invalid values are rejected).
Persistence: SQLite for development and tests, PostgreSQL for deployment (decided at M09).
