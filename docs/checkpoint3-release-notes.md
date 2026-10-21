# Checkpoint 3 release notes

## GUI and visualization

- Added standalone **Dark** and **Light** palettes, bringing the theme catalog to 13.
- Added a live **2D / 3D** visualization switch. 2D is an orthographic top-down XY view; all physics continues to integrate in 3D.
- Reordered the top-level menus to **File → Settings → Help**.
- Added `2` and `3` keyboard shortcuts for 2D and 3D view selection when a text-entry widget is not focused.
- Added `--view-mode {2D,3D}` to command-line PNG snapshots. Snapshots now retain a bounded trajectory history up to the requested simulation time.

## Advanced physics checklist

- **Spin:** rotational kinetic energy and spin angular momentum based on the uniform-sphere inertia approximation; a rotating surface marker provides visual feedback.
- **J2 oblateness:** fixed-axis exterior zonal-harmonic correction. The translational reaction force is included for linear momentum balance; spin-axis precession is not integrated.
- **1PN:** optional pairwise weak-field post-Newtonian correction. The full N-body Einstein–Infeld–Hoffmann formulation is not implemented, and the standard energy diagnostic omits the 1PN Hamiltonian.
- **Tides:** radial damping/heat proxy with the dissipated energy integrated as an auxiliary RK45 state. It is not a full equilibrium-tide model.
- **Fragmentation:** simplified two-remnant collision mode conserving pair mass, linear momentum, and total angular momentum by transferring pre-impact orbital angular momentum into the remnants' spin. This is not a hydrodynamic impact model.
- **Astronomical validation hooks:** preserved JPL Horizons state import and optional REBOUND IAS15 comparison. External access/package availability is required to execute those workflows.

## Verification performed

- `python main.py --selftest`: **42/42 passed**.
- `python -m pytest -q`: **23 passed**.
- GUI smoke test under a virtual display: verified menu order, all 13 themes, 2D/3D camera projection, J2/spin configuration, 1PN+tide RK45 stepping, and setup JSON round-trip.
- Generated both 3D and 2D off-screen snapshots, including a full nominal figure-eight period in 2D.

## Model-scope caveats

These are educational/numerical approximations. Spin torques and precession, full EIH N-body relativity, Love-number-based tidal bulges/synchronization, interior density profiles, and hydrodynamic fragmentation are not modeled. Interpret 1PN only in the weak-field regime and verify results through tolerance/time-step convergence.

## Preset catalog cleanup

- The selectable preset dropdown now contains only the 16 named periodic-orbit gallery seeds. Generic demo systems, the built-in Sun–Earth–Jupiter demo, and added Euler/Lagrange central-configuration demos were removed from the dropdown.
- User-facing names are simplified to **Butterfly I**, **Bumblebee**, **Moth I**, **Yin-Yang I (A)**, **Figure-eight**, and similar short labels without the `Periodic ·` prefix or period suffix.
- Custom model building and JPL Horizons import remain available outside the gallery preset list.
