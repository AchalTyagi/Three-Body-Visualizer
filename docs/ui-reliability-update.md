# UI reliability and diagnostics update

This update is based on the frozen pre-drag Gravity Lab 3D baseline plus the Phase 2 `SimulationState` foundation. It intentionally does not include the body-drag implementation or later viewport hotfixes.

## User-facing changes

- The setup sidebar and viewport pane are separated by a movable sash.
- The main workspace has a second movable sash between the VTK viewport and diagnostics workspace.
- Top toolbar now groups view selection, advanced physics, play/pause, reset simulation, Fit View and simulation speed.
- Body cards separate physical properties, position and velocity into labeled sections.
- Coordinate axes can be hidden/restored via the visual options. The new `axes` setup setting is optional and old schema-1 setup files default to axes enabled.
- Diagnostics are presented as tabs: pair separations, energy drift, linear-momentum drift, angular-momentum drift, and collision/impact events.
- Time-series plots use simulation time, mark recorded event times, and show a sampled value readout while the pointer is over a chart.
- Collision event messages substitute the currently displayed body names for generic engine body indices.
- CSV history exports now include angular-momentum error.

## Reliability changes

- Minimum active-pair separation is computed defensively; when there is no valid active pair, the UI displays `N/A` rather than `nan`.
- Non-finite status metrics display `N/A`.
- Missing pair separations remain `NaN` internally so plots can show a gap instead of a misleading zero.
- Auto-zoom is skipped for invalid states and when no active bodies exist.
- History now stores angular-momentum drift alongside energy and linear-momentum drift.

## Architecture changes

- Reusable graph rendering and diagnostic formatting helpers live in `gravity_lab/ui/diagnostics_panel.py`.
- `GravityLabApp` still owns status orchestration and directly constructs `ThreeBodyEngine`. Full service/API migration and main-window/panel extraction remain follow-up Phase 2 tasks.

## Verification

- `python -m pytest -q`: 44 passed.
- `python main.py --selftest`: 41/41 checks passed.
- Python compilation check passed.
- Tk/VTK GUI smoke passed under Xvfb on Linux, including pane presence, diagnostic tabs, status formatting, axes toggle, and the no-valid-pair `N/A` case.
- Headless PNG snapshot succeeded. The Linux VTK backend logged an X-server warning even though the snapshot was written; Windows GUI behavior has not been manually exercised in this environment.
