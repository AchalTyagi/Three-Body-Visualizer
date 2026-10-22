# Gravity Lab 3D — Step 1: Baseline Freeze and Scope Guardrails

## Frozen baseline
- Selected baseline: `Gravity_Lab_3D_GUI_Customization_Update.zip` (the project version immediately before the drag-placement implementation).
- Exact source package copy: `Gravity_Lab_3D_GUI_Customization_Update_source_archive.zip`.
- SHA-256 hashes for the source archive and every file in the extracted baseline are recorded in `SHA256SUMS.txt`.
- The provided package does not include Git metadata (`.git`), so a Git branch or commit cannot honestly be recorded from this source. The exact archive, extracted source tree, hashes, and validation logs provide the baseline snapshot instead.

## In scope and must be preserved
- Existing three-body Newtonian simulation engine and advanced physics options.
- Preset gallery, custom model setup, 2D/3D rendering, diagnostics and exports.
- Renameable bodies and the **Customize Body** color picker.
- Existing soft **Dark** and **Light** themes, with Dark as the default.
- Existing setup JSON save/load and optional astronomical integrations present in the baseline.

## Out of scope unless explicitly requested
- Drag-to-move body placement and the later body-placement patch.
- The later VTK-native mouse-drag fixes, runtime fix patch, and Windows viewport hotfix.
- Any unrelated visual redesign or physics behavior change during baseline/stability work.

## Baseline identity checks
- GUI has `body_name_vars`, the `Customize Body` action, and the normal camera-drag binding used to rotate the view.
- The baseline source scan found no `Move bodies` control, no `body_placement` test/module, and no drag-to-place handler.
- The theme and body-customization features are present in `gravity_lab/gui.py` and `gravity_lab/themes.py`.

## Validation run
Commands were executed from the extracted project root (`baseline_project/gravity_lab_3d`):

```powershell
python -m pytest -q
python main.py --selftest
python main.py --snapshot <path> --preset "Periodic · Butterfly I (T≈6.2356)" --time 0.2 --theme Dark --width 960 --height 540 --view-mode 3D
```

Results are recorded in `validation/pytest.log`, `validation/physics_selftest.log`, and `validation/snapshot_smoke.log`. The snapshot image is `validation/baseline_smoke.png`.

- Pytest: **24 passed**.
- Built-in physics self-checks: **41/41 passed**.
- Headless 3D snapshot smoke test: **passed** and emitted a 960 × 540 PNG.
- Interactive native-window launch was **not tested on Windows** in this environment; the snapshot smoke test is not a substitute for that manual check.

## Reproduction notes
1. Extract `baseline_project/gravity_lab_3d` to a separate directory.
2. Install runtime dependencies using `python -m pip install -r requirements.txt`.
3. Run `python -m pytest -q` and `python main.py --selftest`.
4. Verify all files against `SHA256SUMS.txt` if integrity checking is required.
5. Make future project changes in a separate working copy; do not edit this baseline snapshot.
