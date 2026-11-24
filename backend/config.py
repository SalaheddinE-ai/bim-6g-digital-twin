"""Application configuration: YAML defaults, overridden by .env / environment variables.

Priority (high to low): init kwargs > environment (BIM6G_*) > .env > YAML file.
Nested keys use a double underscore, e.g. BIM6G_RADIO__BACKEND=llvm.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "default.yaml"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"  # anchored at the project root, not the cwd


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AppSettings(_Section):
    name: str = "bim-6g-digital-twin"
    env: Literal["dev", "test", "prod"] = "dev"


class LoggingSettings(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: Path | None = Path("storage/logs/app.log")


class RadioSettings(_Section):
    backend: Literal["auto", "cuda", "llvm"] = "auto"
    probe_timeout_s: float = Field(default=120.0, gt=0)


class PathSettings(_Section):
    storage_dir: Path = Path("storage")


class GeometrySettings(_Section):
    """M02 geometry processing parameters."""

    recenter: Literal["none", "auto", "bbox_min"] = "auto"
    recenter_threshold_m: float = Field(default=10_000.0, gt=0)  # `auto` shifts beyond this
    weld_tolerance_m: float = Field(default=1e-6, gt=0)
    min_face_area_m2: float = Field(default=1e-10, ge=0)
    duplicate_policy: Literal["exclude", "keep"] = "exclude"
    placement_tolerance_m: float = Field(default=1.0, gt=0)
    num_threads: int = Field(default=4, ge=1)
    materials_file: Path = Path("configs/materials.yaml")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BIM6G_", env_nested_delimiter="__", extra="ignore"
    )

    app: AppSettings = AppSettings()
    logging: LoggingSettings = LoggingSettings()
    radio: RadioSettings = RadioSettings()
    paths: PathSettings = PathSettings()
    geometry: GeometrySettings = GeometrySettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    def resolve_path(self, path: Path) -> Path:
        """Relative paths are anchored at the project root, absolute paths are kept."""
        return path if path.is_absolute() else PROJECT_ROOT / path


def load_settings(
    config_file: Path | str | None = None, env_file: Path | str | None = None
) -> Settings:
    """Load settings. `env_file` defaults to <project root>/.env (ignored if it does not exist)."""
    path = Path(config_file) if config_file else DEFAULT_CONFIG
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    dotenv = Path(env_file) if env_file else DEFAULT_ENV_FILE

    class _Loaded(Settings):
        model_config = SettingsConfigDict(
            **{**Settings.model_config, "yaml_file": str(path), "env_file": str(dotenv)}
        )

    return _Loaded()
