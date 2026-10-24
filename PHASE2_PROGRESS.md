# Phase 2 architecture refactor — completion notes

The application now has explicit `SimulationState` dataclasses, a GUI-independent `SimulationService`, a command/controller layer in `gravity_lab/application.py`, schema-validated setup I/O in `gravity_lab/setup_io.py`, and versioned checksummed checkpoint I/O in `gravity_lab/state_io.py`, and a read-only `SceneFrame` adapter so VTK rendering receives renderer-facing data rather than owning the mutable engine.

The UI modules are split under `gravity_lab/ui/`: main-window composition, preset controls, settings/body editor controls, and diagnostic graph widgets. `gravity_lab/gui.py` remains a compatibility import. Existing schema-1 GUI setup files are kept separate from the new version-1 simulation checkpoint schema; no implicit migration or overwrite is performed.

The preset catalog has a stable SHA-256 manifest. The renderer boundary exposes positions, velocities, active flags, body properties, acceleration, centre of mass and influence-shell calculations through `SceneFrame`. Physics remains in `physics.py`; rendering consumes frame data. The live UI still coordinates a few presentation concerns (theme and dialogs), but no longer constructs `SimulationState` directly from widget variables.

Validation after the Phase 2 completion pass: 69 pytest tests passed; all 41 built-in physics self-checks passed; an Xvfb GUI startup/render/graceful-shutdown smoke test passed. See `docs/architecture.md`, `docs/simulation-service-api.md`, and `docs/simulation-state-design.md`.
