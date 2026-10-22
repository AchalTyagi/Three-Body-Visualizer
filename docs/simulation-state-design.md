# Simulation state model design

Status: Phase 2 / Architecture refactor — initial model approved by implementation.

## Purpose

Introduce one validated, GUI-independent object that describes a three-body setup or state snapshot. The model is data only; it does not own a Tk widget, VTK renderer, timer, or numerical integration loop. `ThreeBodyEngine` remains the source of truth for time evolution.

## Types and ownership

- `BodyState`: one body's mass, physical radius, position, velocity, active flag, display name/colour, J2 coefficient, spin axis and spin angular velocity.
- `IntegratorSettings`: method, nominal time step, steps per frame, adaptive-step toggle, and RK45 tolerances.
- `PhysicsSettings`: G, softening, collision mode, restitution, unit label, and optional correction settings.
- `SimulationState`: exactly three bodies, current model time, and the two settings objects.

The model uses frozen dataclasses. Callers replace a value with a newly validated value rather than mutating arrays spread across UI attributes. Position/velocity/spin vectors are normalized into three-component tuples.

## Invariants

1. Exactly three `BodyState` entries are required by the current three-body engine.
2. Mass and radius are positive; values in vectors and scalars must be finite.
3. The active flag is boolean; colour is a six-digit hex code; names are non-empty.
4. G and softening are non-negative; Δt, absolute tolerance, and the speed-of-light model constant are positive; `0 < rtol < 1`; steps per frame are 1–1000; restitution is in [0, 1].
5. Enabled J2/1PN corrections require zero softening. 1PN and nonzero tidal damping require RK45.
6. With zero softening, two active bodies cannot share exactly the same position. Inactive bodies are excluded from this check to allow representations of post-collision states.

## Boundaries

The GUI currently reads `StringVar`s, validates values, creates `ThreeBodyEngine`, updates history and configures `GravityScene` in `GravityLabApp`. The first state-model task does not change this runtime path yet; it creates a tested explicit model before switching the app over. The existing setup JSON file is still schema version 1 and stays unchanged in this step. `SimulationState.to_mapping()`/`from_mapping()` are in-memory conversion helpers, not a stable file format. Versioned file formats and exact restart checkpoints remain separate tasks.

## Target data flow

```text
Tkinter widgets
    ↓ parse inputs
SimulationState (validated values and settings)
    ↓ application/service boundary
ThreeBodyEngine (time evolution, collision resolution, diagnostics)
    ↓ results/state snapshot
GravityScene + History (rendering and plotting)
```

No physics calculations should depend on Tkinter or VTK. No renderer should decide collision/integration behavior. The model is immutable so ownership and state changes become explicit.

## Migration approach

1. Add the state model and tests without changing the existing launch/runtime path.
2. Add a small application/service API that materializes engine inputs and reports state/diagnostics.
3. Switch GUI reset and preset/custom-model workflows to that API while keeping visual behavior unchanged.
4. Move the main window into `gravity_lab/ui/main_window.py`, retaining an import shim until callers migrate.
5. Extract preset, diagnostic and settings panels through narrow interfaces.

## Current module inventory

| Module | Current responsibility |
|---|---|
| `main.py` | CLI/snapshot options and interactive app entry point |
| `gravity_lab/gui.py` | 1,584-line Tkinter app: controls, preset setup, validation, reset/orchestration, import/export, menu handlers, update loop and status/plots |
| `gravity_lab/physics.py` | Mutable NumPy engine, integrators, collisions, conserved quantities, diagnostics and rolling `History` |
| `gravity_lab/renderer_vtk.py` | VTK actors, body/trajectory rendering, axes, field visualization, camera and render updates |
| `gravity_lab/presets.py` | Built-in initial conditions, preset descriptions and conversion helpers |
| `gravity_lab/ephemeris.py` | NASA/JPL Horizons query, parsing and body-state conversion |
| `gravity_lab/fields.py` | Gravitational field-map calculations |
| `gravity_lab/themes.py` | UI theme palettes, default body names/colours |
| `gravity_lab/selftest.py` | Built-in physics and rendering-related self-checks |
| `gravity_lab/rebound_compare.py` | Optional independent REBOUND IAS15 comparison |
| `tests/` | Pytest coverage for physics, ephemeris, presets and renderer axes |

## Baseline workflow checklist

- Start GUI: `python main.py` or `run_gravity_lab.bat` on Windows.
- Select preset or build a custom model; edit body values and apply/reset.
- Run/pause; observe energy/momentum diagnostics, pair separation graph and trajectory history.
- Save/load a setup JSON (currently `gravity-lab-3d-setup`, schema 1); names and colours are included.
- Export viewport PNG and history CSV.
- Import three state vectors from JPL Horizons when internet access is available.
- Optionally compare a compatible Newtonian run with REBOUND if the optional dependency is installed.
- Run tests with `python -m pytest -q`; run built-in checks through the validation action or `python main.py --self-test`.

## Explicit non-goals for this step

This step does not change the force law, integrators, collision resolution, preset values, current setup JSON schema, default visuals, dragging behavior, or Windows viewport handling. The baseline selected before drag implementation remains authoritative.
