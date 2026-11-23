from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.config import DEFAULT_CONFIG, PROJECT_ROOT, load_settings


def test_default_config_file_exists():
    assert DEFAULT_CONFIG.is_file()


def test_default_config_loads():
    s = load_settings()
    assert s.app.name == "bim-6g-digital-twin"
    assert s.radio.backend == "auto"
    assert s.radio.probe_timeout_s > 0


def test_yaml_values_are_used(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("app:\n  env: test\nradio:\n  backend: llvm\n")
    s = load_settings(cfg)
    assert s.app.env == "test"
    assert s.radio.backend == "llvm"


def test_env_overrides_yaml(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("radio:\n  backend: cuda\n")
    monkeypatch.setenv("BIM6G_RADIO__BACKEND", "llvm")
    assert load_settings(cfg).radio.backend == "llvm"


def test_dotenv_overrides_yaml_and_env_overrides_dotenv(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("radio:\n  backend: cuda\napp:\n  env: test\n")
    dotenv = tmp_path / "x.env"
    dotenv.write_text("BIM6G_RADIO__BACKEND=llvm\nBIM6G_APP__ENV=prod\n")
    s = load_settings(cfg, env_file=dotenv)
    assert (s.radio.backend, s.app.env) == ("llvm", "prod")  # .env beats YAML
    monkeypatch.setenv("BIM6G_APP__ENV", "dev")
    assert load_settings(cfg, env_file=dotenv).app.env == "dev"  # real env beats .env


def test_missing_dotenv_is_ignored(tmp_path):
    assert load_settings(env_file=tmp_path / "absent.env").radio.backend == "auto"


def test_real_project_dotenv_does_not_leak_into_tests():
    from backend import config

    assert config.DEFAULT_ENV_FILE.name == "no-such.env"


def test_invalid_backend_rejected(monkeypatch):
    monkeypatch.setenv("BIM6G_RADIO__BACKEND", "tpu")
    with pytest.raises(ValidationError):
        load_settings()


def test_unknown_key_in_section_rejected(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("radio:\n  bakend: llvm\n")  # typo on purpose
    with pytest.raises(ValidationError):
        load_settings(cfg)


def test_non_positive_timeout_rejected(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("radio:\n  probe_timeout_s: 0\n")
    with pytest.raises(ValidationError):
        load_settings(cfg)


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "nope.yaml")


def test_resolve_path_anchors_relative_paths():
    s = load_settings()
    assert s.resolve_path(Path("storage")) == PROJECT_ROOT / "storage"
    assert s.resolve_path(Path("/tmp/x")) == Path("/tmp/x")
