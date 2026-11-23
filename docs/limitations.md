# Known limitations

1. **CUDA/OptiX on WSL2**: not available out of the box (`libnvoptix.so.1` missing). Mitsuba
   documents an unofficial workaround that copies files into a Windows system folder and may
   degrade performance. Deferred; everything runs on CPU (LLVM) meanwhile.
2. System Python is 3.14 in the WSL distro; the project uses uv-managed 3.12 (ADR-001).
3. The CPU backend is slower than GPU for large scenes; M00 only runs a tiny box scene.
4. No real IFC has been processed yet (M01).
