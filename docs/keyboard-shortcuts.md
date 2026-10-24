# Gravity Lab 3D keyboard and interaction guide

## Keyboard shortcuts

| Key | Action | Notes |
|---|---|---|
| `Space` | Play / pause | Disabled while a text entry or control has focus. |
| `R` | Apply current values and reset | Disabled while editing an entry or focused control. |
| `2` | Switch to 2D XY view | Disabled while editing an entry or focused control. |
| `3` | Switch to 3D view | Disabled while editing an entry or focused control. |

## Pointer and controls

- Search presets by name, family, or description using **Search presets** above the preset selector.
- Drag inside the 3D viewport to rotate the camera; use the mouse wheel to zoom.
- Use **Fit View** to frame the current system without resetting its physics state.
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
