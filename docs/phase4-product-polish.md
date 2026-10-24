# Phase 4 Product Polish — Initial Implementation

## Delivered in this increment

1. **Preset search/filter**: search by preset name, family, or description while keeping the custom-model entry available at all times.
2. **Persistent UI preferences**: save and restore theme, view mode, playback speed, visual body scale, axes, trails, floor projection, influence shells, field map, acceleration vectors, COM display, autozoom, view width, and trail length. Preferences are stored separately from setup files and simulation checkpoints.
3. **Consistent gravity heatmap**: all 13 interface themes use the exact Midnight Dark field-map colour ramp. Backgrounds, typography, controls and axes continue to use the selected UI theme.
4. **Keyboard/action documentation**: documented shortcuts, pointer controls, persistence locations, and the distinction between UI preferences and simulation files.
5. **Cross-platform CI matrix**: automated tests run on Linux, Windows and macOS, with Python 3.10 and 3.12 coverage on Linux.

## Preference data safety

The preferences file contains UI settings only. It does not store body masses, radii, initial positions/velocities, integrator state, or collision history. Use setup JSON for editable starting configurations and simulation checkpoints for runtime restoration. Unsupported/corrupt preferences fall back to safe defaults. Writes are atomic.

## Heatmap palette contract

The shared palette is `("#0b1026", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf")`, matching Midnight Dark. The regression test asserts every theme carries the same field stops so a future theme cannot silently alter field-map interpretation.

## Validation in this environment

- `python -m pytest -q`: 80 passed.
- `python main.py --selftest`: 41/41 checks passed.
- `python main.py --list-presets`: passed.
- `python -m compileall -q main.py gravity_lab tests`: passed.
- GUI startup/close smoke test under Xvfb: see `validation/phase4-gui-smoke.log`.

The CI workflow is configured for Windows and macOS, but remote CI runs are not available from this local session. Those runners must execute after push to verify platform-specific behavior.

## Remaining Phase 4 work

This is the start of Phase 4, not the entire phase. Remaining polish candidates include geometry/window-size persistence, a full keyboard-accessibility pass, preset categorization chips, Windows/macOS manual UI review, and final lint/type-check cleanup.

6. **Clean shutdown**: the scheduled Tk update callback is now tracked and cancelled on window close. This prevents Tcl `invalid command name ..._tick` warnings when closing the application while the simulation timer is pending.
