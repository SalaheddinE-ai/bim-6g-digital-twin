import platform

from backend import env_info
from backend.env_info import EXPECTED_PINS, collect_env_info, package_version


def test_collect_env_info_shape():
    info = collect_env_info()
    assert info["python"] == platform.python_version()
    assert set(info["packages"]) == set(EXPECTED_PINS)
    assert isinstance(info["wsl"], bool)


def test_package_version():
    assert package_version("pytest") is not None
    assert package_version("definitely-not-installed-xyz") is None


def test_nvidia_smi_missing_returns_none(monkeypatch):
    monkeypatch.setattr(env_info.shutil, "which", lambda _: None)
    assert env_info.nvidia_smi_gpus() is None
