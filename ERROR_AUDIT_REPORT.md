# Error Audit and Fix Report

## Fixed
- Corrected the NASA/JPL Horizons import in `gravity_lab/ui/main_window.py` from
  `from .ephemeris import SOLAR_SYSTEM_BODIES` to
  `from ..ephemeris import SOLAR_SYSTEM_BODIES`. The ephemeris module is a sibling
  of `ui`, so the old relative import resolved to a nonexistent
  `gravity_lab.ui.ephemeris` module.
- Added `tests/test_ephemeris_ui_import_path.py` to prevent the incorrect relative
  import from returning.

## Verification performed
- `python -m compileall -q main.py gravity_lab tests`: passed.
- `python -m pytest -q`: 70 passed.
- `python main.py --selftest`: 41/41 physics self-checks passed.
- `python main.py --list-presets`: passed.
- CLI snapshot smoke test using `Figure-eight, tilted 40 deg (Claude)`: passed.
- Import smoke test for all application modules, including the GUI, renderer,
  ephemeris, application service and state persistence modules: passed.

## Environment-only limitations
- Ruff and mypy are declared development extras but are not installed in this
  offline runtime, so their checks were not run here.
- `pip check` reports an existing environment-level conflict: installed
  `moviepy 2.2.1` requires `pillow<12`, while the environment has Pillow 12.3.0.
  Neither package is a Gravity Lab 3D runtime dependency; no project dependency
  was changed to mask this unrelated conflict.
- GUI smoke testing was performed in a Linux environment. Native Windows UI
  behavior still needs to be confirmed on the target Windows machine.
