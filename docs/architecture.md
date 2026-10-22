# Gravity Lab 3D — architecture overview

This document records the selected pre-drag baseline before structural changes. It distinguishes the current runtime from the target architecture so refactoring can preserve behavior and numerical assumptions.

## Current module map

| File | Responsibility | Architectural note |
|---|---|---|
| `main.py` | CLI, optional self-test, preset listing, headless PNG snapshot and GUI entry point | Entry-point responsibilities; should remain thin. |
| `gravity_lab/gui.py` | Backward-compatible import of `GravityLabApp` | Kept so existing scripts importing `gravity_lab.gui` continue to work. |
| `gravity_lab/ui/main_window.py` | `GravityLabApp`, menus, dialogs, widget variables, event wiring, lifecycle and renderer scheduling | Main window moved into the UI package; it still contains some orchestration and validation that will be moved behind service APIs incrementally. |
| `gravity_lab/ui/preset_panel.py` | Starting-system selector and custom-model entry controls | Panel builder receives the app/controller as an explicit dependency; no physics rules live here. |
| `gravity_lab/ui/settings_panel.py` | Body editor, units/integrator/physics controls, display options and run actions | Builds widgets and binds controller callbacks; it does not instantiate or step the engine. |
| `gravity_lab/ui/diagnostics_panel.py` | Reusable Tk Canvas time-series chart, axis/event markers, hover sample details, finite-value formatting and active-pair minimum-separation helper | First extracted presentation component; does not own the engine or VTK renderer. |
| `gravity_lab/physics.py` | `ThreeBodyEngine`, force calculations, Verlet/Yoshida/RK45 integration, collision/contact handling, diagnostics and `History` | Engine is mutable; the GUI currently reaches into engine arrays and metrics. |
| `gravity_lab/renderer_vtk.py` | VTK body/shell/trail/field actors, axes, camera, view mode and render updates | Rendering receives the engine object directly; must not take ownership of physics rules. |
| `gravity_lab/presets.py` | Built-in initial-condition records, periodic-orbit seeds, preset names and `engine_inputs()` conversion | Preset records are dictionaries and currently have no formal metadata schema/checksum. |
| `gravity_lab/state.py` | Immutable validated `BodyState`, `IntegratorSettings`, `PhysicsSettings`, `SimulationState` models | Application model; does not import GUI or rendering frameworks. |
| `gravity_lab/service.py` | `SimulationService`, `SimulationSnapshot`, `engine_from_state()` | Converts validated state into the mutable engine, owns reset/advance transitions, and returns read-only diagnostic snapshots without importing Tkinter or VTK. The engine is exposed temporarily for renderer/history compatibility. |
| `gravity_lab/ephemeris.py` | NASA/JPL Horizons request, result parsing, astronomical body metadata and frame conversion | External data ingestion; UI dialog currently calls this directly. |
| `gravity_lab/fields.py` | Grid-based gravitational field-map calculations | Physics helper used by rendering. |
| `gravity_lab/themes.py` | Theme palettes, default body names and colors | Presentation configuration. |
| `gravity_lab/selftest.py` | Built-in numerical/physics checks | Callable without constructing the GUI. |
| `gravity_lab/rebound_compare.py` | Optional REBOUND IAS15 reference comparison | Optional dependency and analysis service. |
| `tests/test_physics.py` | Pytest wrapper and targeted physics checks | Includes built-in self-check coverage. |
| `tests/test_ephemeris.py` | Horizons parsing/query tests | Network calls are monkeypatched in tests. |
| `tests/test_periodic_gallery.py` | Periodic-preset invariants/metadata checks | Protects the starter model set. |
| `tests/test_rebound_compare.py` | Optional comparison behavior | Protects supported comparison conditions. |
| `tests/test_renderer_axes.py` | Axis and view invariants | Renderer checks; not equivalent to Windows GUI interaction testing. |
| `tests/test_simulation_state.py` | State validation and mapping round trip | Distinct from GUI setup JSON serialization, which remains schema version 1. |
| `tests/test_simulation_service.py` | State-to-engine construction, frame stepping, snapshots and headless imports | Exercises the new service boundary independent of Tk/VTK. |

## Current simulation loop

1. `main.py` creates a Tk root and constructs `GravityLabApp` from `gravity_lab.ui.main_window`. Existing callers may still import it through `gravity_lab.gui`.
2. `GravityLabApp.__init__` creates Tk variables, configures the theme, builds menus/widgets and VTK embedding, loads the selected preset, binds actions and schedules `_tick()`.
3. Preset or body/settings edits populate `StringVar`/`BooleanVar` values. The user invokes Apply/Reset (or chooses a preset); `_read_inputs()` parses and validates the widget values and optionally recenters them around the center of mass.
4. `_apply_reset()` converts those values to `BodyState`, `IntegratorSettings`, `PhysicsSettings`, and `SimulationState`, then passes the model to `SimulationService.reset()`. The service builds the engine; the window resets rolling `History`, configures `GravityScene`, places initial trails and updates diagnostics.
5. `_schedule_tick()` calls `_tick()` repeatedly. When running, `_tick()` calls `SimulationService.advance()` with the current frame budget and speed control, obtains the current engine for legacy renderer/history adapters, updates diagnostics, then calls `_render_once()` as needed.
6. `GravityScene.update()` reads engine positions/alive state and updates VTK actors and visualization layers. The diagnostics notebook displays pair separations, energy drift, linear-momentum drift, angular-momentum drift and a named collision-event log. The chart component uses simulation time on the x-axis, mouse-hover sample details, and event-time markers.
7. File handlers in `GravityLabApp` save/load schema-1 setup JSON and export PNG/CSV. The setup JSON captures initial body fields and settings, not an exact restart checkpoint.

## Current ownership and coupling concerns

- `GravityLabApp` still parses inputs and coordinates metadata, histories and rendering; engine creation/advancement now goes through `SimulationService`, but some validation and preset orchestration remain in the window.
- The settings panel extracts body, units/integrator, display and run-control widgets. Theme selection and the advanced-physics dialog remain owned by `main_window.py` and are not considered fully extracted yet.
- UI input variables still form the edit buffer; Apply/Reset commits them as a validated `SimulationState`. Names/colors/units live in state between frames and are mapped from GUI controls on reset.
- `GravityScene` and `History` still consume the mutable engine for compatibility. `SimulationSnapshot` is now available as a read-only service boundary; migrating all renderer/history reads to snapshots remains future work.
- `History` is declared in `physics.py` even though it stores plotting/export samples rather than integrating the equations.
- Setup JSON serialization is located in `_save_setup_json()`/`_load_setup_json()` in `ui/main_window.py`; it currently has `schema_version: 1`.

## Current-to-target data flow

```text
Tkinter panel builders
  │ edit buffer (StringVar / BooleanVar)
  ▼
GravityLabApp input validation
  │ Apply/Reset creates a validated model
  ▼
SimulationState ──► SimulationService.reset/advance
                         │
                         ▼
                 ThreeBodyEngine
                  │            │
         SimulationSnapshot    └── compatibility access for renderer/History
                  │
                  └── intended future read-only input to diagnostics/rendering
```

Target boundaries: the physics core must not import Tkinter or VTK; view widgets must not implement physical behavior; `SimulationState` must not own timers/windows; state serialization should be versioned in a dedicated I/O boundary; UI panels should call a narrow application API rather than reach into engine internals. The service is now live for reset/advance, but full snapshot-only rendering and extraction of input/setup orchestration are remaining work.

## Collision model assumptions

- Exact Newtonian gravity is used with zero softening; nonzero Plummer softening changes the force law.
- Collision handling uses finite-radius contact, event-aware substeps and a swept-segment fallback. It is a practical numerical safeguard, not a closed-form solution of the accelerated contact path.
- Merge, bounce, pause-on-impact, pass-through and simplified fragmentation are distinct model choices. Merging and inelastic bounce dissipate mechanical energy; momentum and collision energy bookkeeping need to be interpreted accordingly.
- The fragmentation mode is an educational two-remnant toy model, not hydrodynamics.
- J2 is a fixed-spin-axis exterior-field approximation, 1PN is a pairwise correction rather than the complete N-body Einstein–Infeld–Hoffmann formulation, and tidal damping is a radial surrogate.

## Refactor sequence

1. **Completed earlier:** record boundaries and add immutable validated state types with tests.
2. **Completed in this change:** add `SimulationService`/`SimulationSnapshot` and route reset/frame advancement through the service without Tk/VTK dependencies.
3. **Completed in this change:** convert GUI setup input to a validated `SimulationState` before engine creation; keep schema-1 setup JSON unchanged.
4. **Completed in this change:** move window construction/event wiring into `gravity_lab/ui/main_window.py` with the `gravity_lab.gui` compatibility import.
5. **Partially completed:** extract starting-system selection into `ui/preset_panel.py`, body editor/settings/run controls into `ui/settings_panel.py`, and retain the extracted chart/diagnostic helpers in `ui/diagnostics_panel.py`.
6. Continue moving validation, setup serialization, preset activation and orchestration behind testable services; then add end-to-end acceptance checks for preset, save/load, export, advanced physics, and native Windows GUI startup.

## Reproduction commands

From the project root:

```bash
python -m pytest -q
python main.py --selftest
python main.py --list-presets
python main.py --snapshot baseline.png --time 0.1
```

GUI startup is `python main.py` or `run_gravity_lab.bat` on Windows. A successful headless snapshot/self-test is not a substitute for native Windows/Tk/VTK interaction testing.
