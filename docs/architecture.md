# Gravity Lab 3D — architecture overview

This document records the selected pre-drag baseline before structural changes. It distinguishes the current runtime from the target architecture so refactoring can preserve behavior and numerical assumptions.

## Current module map

| File | Responsibility | Architectural note |
|---|---|---|
| `main.py` | CLI, optional self-test, preset listing, headless PNG snapshot and GUI entry point | Entry-point responsibilities; should remain thin. |
| `gravity_lab/gui.py` | `GravityLabApp`, `SparkGraph`, Tk widgets, menus, input parsing/validation, preset/custom model setup, JSON I/O, JPL import, REBOUND comparison, reset/orchestration, update scheduler, plots/status and rendering triggers | Current 1,584-line concentration of presentation and application-service responsibilities. |
| `gravity_lab/physics.py` | `ThreeBodyEngine`, force calculations, Verlet/Yoshida/RK45 integration, collision/contact handling, diagnostics and `History` | Engine is mutable; the GUI currently reaches into engine arrays and metrics. |
| `gravity_lab/renderer_vtk.py` | VTK body/shell/trail/field actors, axes, camera, view mode and render updates | Rendering receives the engine object directly; must not take ownership of physics rules. |
| `gravity_lab/presets.py` | Built-in initial-condition records, periodic-orbit seeds, preset names and `engine_inputs()` conversion | Preset records are dictionaries and currently have no formal metadata schema/checksum. |
| `gravity_lab/state.py` | **New in Phase 2:** immutable validated `BodyState`, `IntegratorSettings`, `PhysicsSettings`, `SimulationState` models | Introduced independently; live GUI path has not yet been switched to it. |
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
| `tests/test_simulation_state.py` | **New in Phase 2:** state validation and mapping round trip | Does not yet replace GUI-level setup JSON tests. |

## Current simulation loop

1. `main.py` creates a Tk root and constructs `GravityLabApp` from `gravity_lab.gui`.
2. `GravityLabApp.__init__` creates Tk variables, configures the theme, builds menus/widgets and VTK embedding, loads the selected preset, binds actions and schedules `_tick()`.
3. Preset or body/settings edits populate `StringVar`/`BooleanVar` values. The user invokes Apply/Reset (or chooses a preset); `_read_inputs()` parses and validates the widget values and optionally recenters them around the center of mass.
4. `_apply_reset()` constructs a new `ThreeBodyEngine`, takes an initial snapshot, resets rolling `History`, configures `GravityScene`, places initial trails and updates diagnostics.
5. `_schedule_tick()` calls `_tick()` repeatedly. When running, `_tick()` computes the frame's step budget and calls the engine. It pushes diagnostics/history, marks the view dirty, updates status/plots on their cadence, then calls `_render_once()` as needed.
6. `GravityScene.update()` reads engine positions/alive state and updates VTK actors and visualization layers. Tk graphs draw energy drift and pair separations from `History`.
7. File handlers in `GravityLabApp` save/load schema-1 setup JSON and export PNG/CSV. The setup JSON captures initial body fields and settings, not an exact restart checkpoint.

## Current ownership and coupling concerns

- GUI methods parse physics inputs, apply model-specific validity rules, instantiate the engine, mutate run metadata, reset histories and drive rendering.
- Widgets expose individual string variables as the de facto configuration schema; current-time/alive flags live on the mutable engine, names/colors/units live in GUI variables, and numerical stepping settings partly live on `GravityLabApp`.
- `GravityScene` consumes the engine directly, so a narrow immutable render snapshot is a future improvement, not yet implemented.
- `History` is declared in `physics.py` even though it stores plotting/export samples rather than integrating the equations.
- Setup JSON serialization is located in `_save_setup_json()`/`_load_setup_json()` in `gui.py`; it currently has `schema_version: 1`.

## Target data flow

```text
UI (Tkinter widgets)
  │ parsed user actions
  ▼
SimulationState (validated, explicit configuration and body state)
  │ application/service API
  ▼
ThreeBodyEngine (force law, integrators, collisions, numerical diagnostics)
  │ state/diagnostic snapshot
  ├──────────────► History / export services
  ▼
GravityScene (VTK rendering only)
```

Target boundaries: the physics core must not import Tkinter or VTK; view widgets must not implement physical behavior; `SimulationState` must not own timers/windows; state serialization should be versioned in a dedicated I/O boundary; UI panels should call a narrow application API rather than reach into engine internals.

## Collision model assumptions

- Exact Newtonian gravity is used with zero softening; nonzero Plummer softening changes the force law.
- Collision handling uses finite-radius contact, event-aware substeps and a swept-segment fallback. It is a practical numerical safeguard, not a closed-form solution of the accelerated contact path.
- Merge, bounce, pause-on-impact, pass-through and simplified fragmentation are distinct model choices. Merging and inelastic bounce dissipate mechanical energy; momentum and collision energy bookkeeping need to be interpreted accordingly.
- The fragmentation mode is an educational two-remnant toy model, not hydrodynamics.
- J2 is a fixed-spin-axis exterior-field approximation, 1PN is a pairwise correction rather than the complete N-body Einstein–Infeld–Hoffmann formulation, and tidal damping is a radial surrogate.

## Refactor sequence

1. **Completed in this change:** record boundaries; add the immutable validated state types and tests without changing live runtime behavior.
2. Add an application/service API that owns state transitions and materializes engine updates without Tk/VTK dependencies.
3. Route preset/custom setup and reset through the service; keep existing UI behavior and setup JSON compatibility.
4. Move window creation/event wiring to `gravity_lab/ui/main_window.py` with a temporary compatibility import.
5. Extract preset, diagnostics and settings panels using narrow interfaces.
6. Add end-to-end acceptance checks for presets, setup load/save, export, advanced physics, and GUI startup on the supported OSes.

## Reproduction commands

From the project root:

```bash
python -m pytest -q
python main.py --selftest
python main.py --list-presets
python main.py --snapshot baseline.png --time 0.1
```

GUI startup is `python main.py` or `run_gravity_lab.bat` on Windows. A successful headless snapshot/self-test is not a substitute for native Windows/Tk/VTK interaction testing.
