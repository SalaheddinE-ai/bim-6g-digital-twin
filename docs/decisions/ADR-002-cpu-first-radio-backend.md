# ADR-002: CPU-first radio backend, GPU optional

Status: accepted. Context: on the target WSL2 machine CUDA initialises but OptiX is missing, so
Sionna RT scene loading fails on the CUDA variant, while LLVM works.
Decision: `radio.backend: auto|cuda|llvm`; `auto` probes CUDA with a real tiny simulation in a
subprocess and falls back to LLVM. GPU tests are marked `gpu` and report BLOCKED when unusable.
Consequences: development is never blocked by the GPU path. Revisit at M05 if CPU is too slow.
