"""REAL Sionna RT runs (no mocks). CPU test must pass; the GPU test reports BLOCKED
(skipped with a 'BLOCKED:' reason) when CUDA/OptiX is not usable, e.g. on WSL2."""

import json

import pytest

from modules.radio.probe import probe_backend

pytestmark = [pytest.mark.integration, pytest.mark.sionna]


def test_llvm_backend_runs_real_simulation():
    res = probe_backend("llvm")
    assert res.ok, res.detail
    info = json.loads(res.detail)
    assert info["variant"] == "llvm_ad_mono_polarized"
    assert info["path_gain_shape"] == [1, 20, 20]


@pytest.mark.gpu
def test_cuda_backend_runs_real_simulation():
    res = probe_backend("cuda")
    if not res.ok:
        pytest.skip(f"BLOCKED: {res.detail}")
    info = json.loads(res.detail)
    assert info["variant"] == "cuda_ad_mono_polarized"
    assert info["path_gain_shape"] == [1, 20, 20]
