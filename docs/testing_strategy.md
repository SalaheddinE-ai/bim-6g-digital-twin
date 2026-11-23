# Testing strategy

- `tests/unit`: pure logic, no external components. The Sionna probe is stubbed ONLY in
  `test_backend_resolution.py` (selection logic); this never counts as proof the simulator works.
- `tests/integration`: real components. `test_sionna_probe.py` runs real Sionna RT (marker
  `sionna`); the GPU test (marker `gpu`) is reported BLOCKED when CUDA/OptiX is unusable.
- `tests/end_to_end`: the full workflow (late modules). Never marked PASS if a step is mocked.
- Commands: `python -m pytest` (all), `-m "not gpu"`, `-m sionna`, `-m "not sionna"`.
- Always run with `-ra` (already in config) so skip reasons, including `BLOCKED:`, are visible.

## M00 acceptance criteria

| Criterion | Evidence |
|---|---|
| Environment validation | `scripts/check_env.py` |
| Dependencies reproducible | `requirements.lock` installs in a fresh Python 3.12 venv |
| Configuration loading | `tests/unit/test_config.py` |
| Logging initialisation | `tests/unit/test_logging.py` |
| Application startup | `tests/integration/test_api_health.py` |
| Pytest infrastructure | markers registered, `--strict-markers` |

## Test isolation (lesson from M00 review)

Tests must not depend on the developer's machine. `tests/conftest.py` removes `BIM6G_*`
environment variables and redirects `DEFAULT_ENV_FILE` to a non-existent file, so a real `.env`
cannot change results. (A failing `test_yaml_values_are_used` on the user's machine revealed this:
a copied `.env` set `app.env=dev` and, by design, outranked the YAML value.)
