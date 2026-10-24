# Phase 2 and Phase 3 implementation summary

## Phase 2 — Architecture refactor

- Explicit immutable state types: `BodyState`, `IntegratorSettings`, `PhysicsSettings`, `SimulationState`.
- `SimulationService` owns engine reset/advance and returns immutable diagnostic snapshots.
- `SimulationController` converts preset definitions and parsed values to validated state objects outside Tk widgets.
- `SceneFrame` is a read-only renderer-facing adapter; VTK methods consume the frame API rather than owning/mutating the integration engine.
- UI modules are organized under `gravity_lab/ui/`; `gravity_lab/gui.py` is retained as a compatibility import.
- Setup JSON validation and atomic file I/O live in `setup_io.py`; exact simulation checkpoint persistence is separated from legacy setup JSON. Checkpoints use schema version 1, canonical JSON SHA-256 verification, atomic writes, runtime event/collision bookkeeping, conservation baselines, and RK45 counters.
- A deterministic, versioned preset manifest records per-preset and whole-catalog hashes.

## Phase 3 — Performance and verification

- Repeatable benchmark harness compares Velocity Verlet, Yoshida and RK45, collision-free orbital cases, merge collision mode, and a synthetic overlap/bounce case.
- cProfile and tracemalloc profiling is available via the same harness.
- The standard Newtonian force path uses allocation-light symmetric pair accumulation. J2, pairwise 1PN, and tidal-damping paths continue using the general correction implementation.
- Numerical parity tests compare the optimized force calculation against an independent reference for softened/unsoftened and inactive-body cases.
- `docs/performance-benchmarks.md` records the before/after timings and their limitations.

## Validation in this environment

- `python -m pytest -q`: 65 passed.
- `python main.py --selftest`: 41/41 passed.
- Xvfb GUI startup, `SceneFrame` generation, VTK render and graceful shutdown: passed.
- Headless snapshot generation: passed.
- Editable package install: passed with `--no-build-isolation`; isolated build dependency installation could not be verified because this environment had no network access.

Benchmark timing is hardware-dependent; the JSON reports include Python/platform/NumPy versions and the preset catalog hash. CI does not enforce timing thresholds.
