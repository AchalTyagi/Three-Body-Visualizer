# Improvement roadmap

Physics and logic are changed before the GUI in every phase.

1. **Phase 1 – Body sizing and data foundation** *(implemented)*: per-body visual size, validation and file formats, plus 2D pan / 3D pan interaction fixes. See [`body-size.md`](body-size.md).
2. **Phase 2 – Camera feel**: turntable (z-up) orbit option, top/side/front preset views, smooth camera transitions, saved camera, faster autozoom, one shared camera-setup function.
3. **Phase 3 – Reliability and validation**: headless renderer/camera integration tests, replace silent `except ... pass` with debug logging, regenerate the validation logs, Windows + Linux CI.
4. **Phase 4 – Structure**: split `ui/main_window.py` (camera controller, dialogs, playback loop).
5. **Phase 5 – Performance and polish**: profile rendering with long trails, repository cleanup, final docs pass.

## Current status (2026-10-25)

- **Phase 6 — Simulation controls and timeline:** implemented in the current baseline; application starts paused and supports in-memory timeline rewind/step plus persistent checkpoints.
- **Phase 7 — Scientific diagnostics:** implemented; live conservation/close-approach diagnostics and graph export.
- **Phase 8 — JPL Horizons:** implemented; epoch validation and state-vector preview/explicit apply.
- **Phase 9 — Visualization and usability:** implemented in this release with camera-angle and visualization presets plus settings-panel wrapping/responsive columns.
- **Phase 10 — Reliability and release quality:** regression tests, release notes/checklist, compile/test/selftest validation. Native Windows GUI acceptance remains a manual step.
