# Phase 2 implementation progress

Baseline used: the frozen pre-drag `Gravity_Lab_3D_GUI_Customization_Update` project. Drag-placement code and subsequent viewport hotfixes are excluded.

## Completed in this increment

- **T01 — Inventory current architecture and behaviors:** documented current module ownership, the GUI/update loop, preset/reset path, save/load/export workflows, model assumptions, and target data flow in `docs/architecture.md`.
- **T14 — Design explicit SimulationState:** recorded boundaries, ownership, invariants, and migration order in `docs/simulation-state-design.md`.
- **T15 — Implement SimulationState with validation:** added `gravity_lab/state.py` with frozen `BodyState`, `IntegratorSettings`, `PhysicsSettings`, and `SimulationState` models. Includes clear validation and JSON-compatible mapping helpers for test/in-memory boundaries.
- Added `tests/test_simulation_state.py` for field validation, active/inactive states, correct defaults, immutable replacement semantics, advanced-model compatibility, and JSON mapping round-trip.
- Updated README links and the improvement task sheet.

## Validation

- Pytest: **38 passed**.
- Built-in physics checks: **41/41 passed**.
- Python compile check: passed.
- Import smoke (`state`, `gui`, `physics`, `renderer_vtk`): passed.
- Headless PNG snapshot: passed; see `validation/snapshot-smoke.log` and `validation/baseline-smoke.png`.

## Not changed

- The live `GravityLabApp` still uses the existing Tkinter variables and constructs `ThreeBodyEngine` directly. It has not yet been migrated to `SimulationState`.
- The physics equations, integrators, collision behavior, presets, setup JSON schema (still version 1), GUI layout and rendering pipeline were not changed.
- No drag-placement or later viewport-hotfix code was included.

## Remaining Phase 2 work

1. Finish remaining T02 coverage with a GUI-independent test for the current setup JSON payload save/load contract.
2. **T16:** build a narrow simulation-engine/service API that accepts validated state and returns explicit state/diagnostic snapshots without creating Tk or VTK objects.
3. **T17–T21:** switch the app through that API, move the main-window module, extract preset/diagnostics/settings panels, and move orchestration/validation out of widget handlers in small, testable steps.
4. Finalize architecture documentation after those boundaries are live and compare the baseline user-workflow checklist.

The current increment is the state-model foundation, not completion of the entire architecture phase.
