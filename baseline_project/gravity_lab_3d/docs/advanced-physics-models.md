# Advanced physics models

Gravity Lab 3D includes optional correction models for learning and controlled numerical experiments. They are disabled by default. Select **Settings → Advanced physics options…** to configure them.

## Body spin

Each body can have a spin angular-velocity vector in radians per model-time unit. The engine accounts for rotational kinetic energy and spin angular momentum using a uniform-sphere moment of inertia, \(I=2MR^2/5\). A small surface marker rotates for visualization. Rigid-body torque, angular acceleration, and spin-axis precession are not integrated. Keep the `spin omega` and `spin axis` directions aligned for a self-consistent fixed-axis body.

## J2 oblateness

The optional `J2` correction adds the exterior zonal-harmonic field of an oblate/prolate source with a fixed symmetry axis. The translation reaction force is included so internal pair forces remain momentum-balanced. The model does not evolve spin-axis torque/precession or update the quadrupole from a changing shape. The field expression is exterior-only and should not be applied inside the source body.

## First post-Newtonian correction

The optional 1PN mode is a pairwise weak-field two-body approximation. It is not the full Einstein–Infeld–Hoffmann equations for a general N-body system, and the default energy diagnostic does not include the full 1PN Hamiltonian. The GUI automatically selects the adaptive Dormand–Prince RK45 integrator. This mode is not appropriate for strong-field black-hole/neutron-star encounters.

## Tidal damping proxy

The optional tidal mode damps each pair's relative radial motion and integrates the removed mechanical energy as a heat proxy. The force is momentum balanced and the dissipated energy is included in the diagnostic energy budget. It does not model tidal bulges, Love numbers, frequency-dependent response, obliquity tides, torques, or spin synchronization. RK45 is required.

## Simplified fragmentation

The **Fragment (simplified two-remnant model)** collision mode retains two remnants, partitions mass and volume, gives a small separating velocity, and logs the event. It is intentionally a visual/educational surrogate. It is not based on material strength, impact equations of state, shock hydrodynamics, gravitational reaccumulation, or a realistic fragment distribution.

## Numerical validation

Run `python main.py --selftest` or choose **Help → Run physics validation…**. Tests include the unsoftened inverse-square force, J2 potential/force consistency and momentum balance, pairwise 1PN momentum balance, tidal heat accounting, spin bookkeeping, fragmentation mass/momentum conservation, event-aware collision checks, periodic-orbit closures, and integrator convergence. For every advanced experiment, compare smaller time steps/tighter tolerances and document the selected model settings.

## View modes

The **2D** mode is an orthographic top-down XY projection for studying planar trajectories. The physics remains three-dimensional: Z coordinates and velocities are still integrated, but are not directly visible in this projection. The **3D** mode exposes all coordinates and offers an interactive camera. Both view modes use the same physical state.
