# Phase 5 — Reference frames and orbital analysis

## Reference selector

- **Inertial frame**: original simulation coordinates.
- **Barycentric frame**: positions and velocities relative to the mass-weighted center-of-mass position and velocity of the currently active bodies. This is a translating, non-rotating frame.
- **Body name**: positions, velocities, and acceleration vectors relative to that body's current state. This frame translates with the selected body but does not rotate with its orientation.

The selected frame affects rendering and displayed trails only. It does not rewrite engine state, change the integrator, or alter gravitational forces. Switching frames clears the existing trail buffer so a trajectory never mixes coordinates from different frames.

## Live orbital measurements

The status area lists every active body pair with:

- `r`: instantaneous separation.
- `v_rel`: magnitude of relative velocity.
- `closest`: smallest separation sampled during the current run, followed by its simulation time.

Closest approach is based on simulation update samples, not continuous event detection. A close pass occurring entirely between samples can have a smaller true minimum than the displayed value. Distances use AU and speeds AU/yr in astronomical units; arbitrary-unit models are labeled L and L/T.

## Validation

Pure numerical helpers are tested independently for mass-weighted barycentric centering and pairwise distance/relative-speed calculations. The original physics engine remains unchanged by the display transforms.
