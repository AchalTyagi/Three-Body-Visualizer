# Gravity Lab 3D keyboard and interaction guide

## Keyboard shortcuts

| Key | Action | Notes |
|---|---|---|
| `Space` | Play / pause | Disabled while a text entry or control has focus. |
| `R` | Apply current values and reset | Disabled while editing an entry or focused control. |
| `2` | Switch to 2D XY view | Disabled while editing an entry or focused control. |
| `3` | Switch to 3D view | Disabled while editing an entry or focused control. |
| `F` | Fit view to the system | Same as the **Fit view** button. Disabled while editing an entry or focused control. |
| `C` | Re-centre the camera | Removes any pan / cursor-zoom offset on the focused body (or the origin) while keeping orbit angle and zoom. |

## Pointer and controls

- Search presets by name, family, or description using **Search presets** above the preset selector.
- **3D view:** drag to orbit; **Shift+drag** or middle-drag to pan (so a touchpad works); right-drag to zoom.
- **2D view:** drag (left or middle button) to pan. The plane never rotates. Right-drag zooms.
- The mouse wheel zooms toward the cursor in both views (touchpad scrolling zooms in proportion to the scroll distance). Zoom is limited to a sensible range so the view can't be lost.
- **Visual size** (in each body card) sets how big a body is drawn: *True scale* (physical radius × the global Visual body scale), *Multiplier* (true scale × your value) or *Fixed radius* (an absolute radius in scene units). It is display-only: it never changes collisions, density or any physics, and it can be edited while the simulation runs. The **Body size preset** menu under *3D display* sets all three bodies at once. See [`body-size.md`](body-size.md).
- Use **Fit View** to frame the current system without resetting its physics state.
- Set **Focus** in the top toolbar to lock the camera to a body as it moves; your orbit angle, zoom and any pan offset are kept. Press **C** to re-centre on the body, or choose **System center** to return to the normal camera focus.
- Set **Reference** to a body to view positions, velocities, and acceleration vectors relative to it. Choose **Inertial frame** to return to the original coordinates. This changes only the visualization, not the simulated physics.
- Use the Settings menu to change theme and 2D/3D view.
- Use File → Save setup to JSON to save body inputs and physics configuration; use Save exact simulation checkpoint to preserve runtime state.

## User preference persistence

Gravity Lab 3D automatically remembers the UI theme, visualizer mode, playback speed, display scale, axes/trails/shells/field toggles, and selected view parameters. These preferences are separate from setup files and simulation checkpoints. Corrupt or unsupported preference files are ignored and defaults are used.

Preference locations:

- Windows: `%APPDATA%\GravityLab3D\preferences.json`
- macOS: `~/Library/Application Support/GravityLab3D/preferences.json`
- Linux: `$XDG_CONFIG_HOME/gravity-lab-3d/preferences.json`, or `~/.config/gravity-lab-3d/preferences.json`

## Heatmap palette

The gravitational field heatmap always uses the Midnight Dark palette regardless of the selected interface theme. UI backgrounds, text, buttons, axes, and grids remain theme-specific. This preserves the meaning of field-map colours when comparing screenshots across themes.
