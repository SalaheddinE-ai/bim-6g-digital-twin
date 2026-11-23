"""Logic of backend selection. The probe is replaced by a stub ONLY here (unit level);
the real probe is exercised in tests/integration/test_sionna_probe.py."""

import logging

import pytest

from modules.radio.probe import BackendUnavailableError, ProbeResult, probe_backend, resolve_backend


def _stub(ok_kinds):
    def probe(kind, timeout_s):
        return ProbeResult(kind, f"{kind}_variant", kind in ok_kinds, 0.0, "stub-detail")

    return probe


def _must_not_be_called(kind, timeout_s):
    raise AssertionError("probe must not be called")


def test_llvm_preference_does_not_probe():
    assert resolve_backend("llvm", probe=_must_not_be_called) == "llvm"


def test_cuda_preference_ok():
    assert resolve_backend("cuda", probe=_stub({"cuda"})) == "cuda"


def test_cuda_preference_unavailable_raises():
    with pytest.raises(BackendUnavailableError, match="stub-detail"):
        resolve_backend("cuda", probe=_stub(set()))


def test_auto_prefers_cuda():
    assert resolve_backend("auto", probe=_stub({"cuda"})) == "cuda"


def test_auto_falls_back_to_llvm_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        assert resolve_backend("auto", probe=_stub(set())) == "llvm"
    assert "falling back to LLVM" in caplog.text


def test_unknown_preference_rejected():
    with pytest.raises(ValueError):
        resolve_backend("tpu", probe=_stub(set()))


def test_probe_rejects_unknown_kind():
    with pytest.raises(ValueError):
        probe_backend("tpu")
