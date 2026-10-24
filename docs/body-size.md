# Body size

Each body has two independent sizes.

| | Where | Used for |
|---|---|---|
| **Physical radius** | `Radius` field (`BodyState.radius`) | collisions, density, escape velocity, J2, contact checks |
| **Visual size** | *Visual size* row in each body card (`BodyState.size_mode`, `size_value`) | drawing only |

Changing a visual size never changes the simulation, and can be done while it runs.

## Modes

| Mode | On-screen radius |
|---|---|
| **True scale** (default) | physical radius × global *Visual body scale* |
| **Multiplier** | physical radius × global *Visual body scale* × your value |
| **Fixed radius** | your value, in scene units (ignores physics and the global scale) |

A body is never drawn smaller than 0.8 % of the scene span, so a realistic-scale planet next to a star stays visible.

The **Body size preset** menu (under *3D display*) applies *Realistic*, *Exaggerated (×5)* or *Uniform (equal size)* to all three bodies. Choosing a built-in preset system resets sizes to *True scale*, because its physical scale differs.

If the physical radii already overlap at t = 0, applying the setup shows a warning in the event line, since the bodies would collide immediately.

## Files

* **Setup JSON** gains an optional `body_sizes` list of three `{"mode", "value"}` objects. The schema version stays 1: older files without the key load with default sizes, and older versions of the app ignore the key.
* **Checkpoints** store `size_mode` / `size_value` per body; older checkpoints load with default sizes.

## Code map

* `gravity_lab/body_size.py` – modes, validation, `display_radius`, overlap check (no VTK/Tk).
* `gravity_lab/state.py` – `BodyState.size_mode` / `size_value`.
* `gravity_lab/renderer_vtk.py` – `GravityScene.set_body_sizes`, per-body radius in `update` and `fit_camera`.
* `gravity_lab/ui/settings_panel.py`, `ui/main_window.py` – the controls and live apply.
