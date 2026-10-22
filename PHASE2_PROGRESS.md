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

## Architecture service and panel extraction increment

- Added `gravity_lab/service.py` with a GUI-independent `SimulationService`, `engine_from_state()`, and immutable `SimulationSnapshot` diagnostics. It materializes validated state, supports reset/advance/step, and tracks a validated state representation from healthy engine state.
- Routed the live GUI reset path through `SimulationState` and `SimulationService.reset()`. The frame loop now advances via `SimulationService.advance()`; the VTK renderer and History retain temporary read access to the engine for compatibility.
- Moved `GravityLabApp` to `gravity_lab/ui/main_window.py`; retained `gravity_lab/gui.py` as a compatibility import. `main.py` now imports the new main-window module.
- Extracted the starting-system panel to `gravity_lab/ui/preset_panel.py`, and body-editor/physics/display/run controls to `gravity_lab/ui/settings_panel.py`. The chart component and defensive diagnostic helpers remain in `ui/diagnostics_panel.py`.
- Added service tests for state materialization, frame advancement, immutable snapshots, inactive-body behavior and headless imports.
- Added `docs/simulation-service-api.md`; updated the README and architecture map to reflect live data flow.

## Validation for this increment

- Pytest: **49 passed**.
- Built-in physics self-checks: **41/41 passed**.
- Python compilation: passed for the main entry point, core modules, UI modules and tests.
- Xvfb GUI smoke: passed; verified the new main-window import, backward-compatible `gravity_lab.gui` import, extracted panels, service reset and service advancement.
- CLI headless snapshot: passed at `t=0.1`. The runtime emitted a non-fatal `DISPLAY=:0` warning in this container, so this is not a Windows OpenGL/interactive test.
- Baseline guardrail: no drag-placement code or viewport hotfix included.

## Remaining Phase 2 work

1. Finish remaining T02 coverage for the existing schema-1 setup JSON payload contract and collision edge cases.
2. Move preset activation and input validation from window methods into a GUI-independent application controller.
3. Finish settings extraction by moving theme selection and the advanced-physics dialog behind focused UI/controller modules.
4. Move setup JSON serialization/migration into a dedicated, versioned I/O module without breaking schema-1 files.
5. Migrate renderer/history consumers from direct engine access to immutable snapshots where feasible.
6. Complete diagnostics panel ownership (currently the chart component/helpers are extracted; notebook assembly/status orchestration still lives in the window).
7. Add end-to-end acceptance checks for built-in presets, setup load/save, PNG/CSV exports, advanced physics options and native Windows startup.

This increment makes the state/service boundary live in the application and extracts the main-window and sidebar panel modules while preserving the legacy import and renderer compatibility. It does not claim to complete all Phase 2 work.
