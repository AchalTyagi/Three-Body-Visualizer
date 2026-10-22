# Phase 2 implementation progress

Baseline used: the frozen pre-drag `Gravity_Lab_3D_GUI_Customization_Update` project. Drag-placement code and subsequent viewport hotfixes are excluded.

## Completed in this increment

- **T01 — Inventory current architecture and behaviors:** documented current module ownership, the GUI/update loop, preset/reset path, save/load/export workflows, model assumptions, and target data flow in `docs/architecture.md`.
- **T14 — Design explicit SimulationState:** recorded boundaries, ownership, invariants, and migration order in `docs/simulation-state-design.md`.
- **T15 — Implement SimulationState with validation:** added `gravity_lab/state.py` with frozen `BodyState`, `IntegratorSettings`, `PhysicsSettings`, and `SimulationState` models. Includes clear validation and JSON-compatible mapping helpers for test/in-memory boundaries.
- Added `tests/test_simulation_state.py` for field validation, active/inactive states, correct defaults, immutable replacement semantics, advanced-model compatibility, and JSON mapping round-trip.
- Updated README links and the improvement task sheet.

## Initial state-model milestone validation (before UI diagnostics work)

- Pytest: **38 passed**.
- Built-in physics checks: **41/41 passed**.
- Python compile check: passed.
- Import smoke (`state`, `gui`, `physics`, `renderer_vtk`): passed.
- Headless PNG snapshot: passed; see `validation/snapshot-smoke.log` and `validation/baseline-smoke.png`.

## UI reliability and diagnostics increment

- Extracted the Tk Canvas plotting component and defensive diagnostic helpers into `gravity_lab/ui/diagnostics_panel.py`.
- Replaced the fixed sidebar/viewport split with user-resizable horizontal and vertical panes.
- Added diagnostic tabs for pair separation, energy drift, linear momentum drift, angular momentum drift, and collision events.
- Added time axes, hover readouts and event markers to time-series plots; event text resolves generic engine indices to the current body names.
- Added an optional coordinate-axes visibility toggle and persisted it in setup JSON settings (existing schema version 1 remains compatible; absence means the default is enabled).
- Added a top-toolbar speed control, separate **Fit view** and **Reset simulation** actions, and clearer body-card sections.
- Replaced non-finite diagnostic display with `N/A`; minimum separation is now `N/A` when there is no valid active pair. Auto-zoom skips invalid states, and History stores angular-momentum drift and preserves missing separation values as NaN gaps rather than converting them to misleading values.

## Validation

- Pytest: **44 passed**.
- Built-in physics checks: **41/41 passed**.
- Python compile check: passed.
- Tk/VTK GUI smoke under Xvfb: passed; verified panes, four diagnostic graph widgets, axis toggle and status formatting.
- Headless PNG snapshot: passed; see `validation/updated-scene-snapshot.png`.
- A GUI screenshot from the smoke test is saved as `validation/improved_gui_smoke.png`; this is a Linux/Xvfb smoke, not a manual Windows interaction test.

## Not changed

- The live `GravityLabApp` still uses existing Tkinter variables and constructs `ThreeBodyEngine` directly. It has not yet been migrated to `SimulationState`.
- The physics equations, integrators, collision response rules, presets, and setup JSON schema (still version 1) remain unchanged. The new axes setting is optional and backward-compatible.
- No drag-placement feature or subsequent viewport hotfix was included.

## Remaining Phase 2 work

1. Finish remaining T02 coverage with a GUI-independent test for the current setup JSON payload save/load contract.
2. **T16:** build a narrow simulation-engine/service API that accepts validated state and returns explicit state/diagnostic snapshots without creating Tk or VTK objects.
3. **T17–T21:** switch the app through that API, move the main-window module, extract preset/diagnostics/settings panels, and move orchestration/validation out of widget handlers in small, testable steps.
4. Finalize architecture documentation after those boundaries are live and compare the baseline user-workflow checklist.

This increment delivers the state-model foundation plus a safer, more flexible diagnostics workspace. It does not yet complete the full service/API and UI-panel migration.
