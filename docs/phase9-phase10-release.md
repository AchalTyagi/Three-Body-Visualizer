# Phase 9 and Phase 10 — Visualization and Release Reliability

## Phase 9: Visualization & usability

- Added named camera angles: Free orbit, Top (XY), Front (XZ), and Side (YZ).
- Added visualization presets: Orbit study, Gravity field, Influence zones, and Clean view.
- Camera presets preserve the current focal point and camera distance; selecting a body in Focus remains independent of the camera angle.
- Visualization presets only alter display toggles. They do not alter the engine, body masses, radii, integration step, or force model.
- Fixed the settings-panel label clipping visible on narrow Windows layouts. Labels now wrap, the label column has a minimum width, and control columns expand/shrink with the panel.
- Existing per-body visual sizing remains separate from physical radii.

## Phase 10: Reliability & release quality

- Added this release checklist and updated keyboard/control documentation.
- Added regression coverage for settings label sizing policy and camera math/preset invariants where the behavior is headlessly testable.
- Release checks: compile all Python files, run the full pytest suite, run `python main.py --selftest`, and verify ZIP integrity.
- Native Windows validation remains a user-side acceptance step for the Tk/VTK GUI, wheel behavior, high-DPI scaling, and resizing.

## Manual release checklist

1. Launch from a clean extracted folder; the simulation should start paused.
2. Verify all Physics and units labels remain readable at 100%, 125%, and 150% Windows scaling.
3. Resize the sidebar narrow/wide; fields should remain visible and labels wrap rather than truncate.
4. Try Top, Front, Side, and Free orbit camera views.
5. Try each visualization preset and confirm physics continues unchanged.
6. Verify Focus, Reference, cursor zoom, JPL import, body visual sizing, timeline rewind, and checkpoint save/load.
7. Check no errors are emitted during close/shutdown.
