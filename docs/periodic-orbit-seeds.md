# Periodic-orbit seed catalog

Gravity Lab 3D includes selected initial conditions for equal-mass planar Newtonian three-body periodic-orbit families. The supplied inspiration image is an unlabeled gallery of 20 trajectories. This project exposes the 16 named periodic-orbit seeds for which this repository has initial conditions; the labels below refer to the standard seed families, not a claim that every displayed path is an exact pixel-by-pixel reconstruction of the inspiration image.

## Canonical equal-mass family setup

For the Butterfly, Bumblebee, Moth, Goggles, Dragonfly, Yarn and Yin–Yang seeds, the initial positions are

\[
\mathbf r_1=(-1,0,0),\quad \mathbf r_2=(1,0,0),\quad \mathbf r_3=(0,0,0),
\]

and velocities use

\[
\mathbf v_1=\mathbf v_2=(p_x,p_y,0),\quad
\mathbf v_3=(-2p_x,-2p_y,0).
\]

The three masses and gravitational constant are all 1 in arbitrary units. This makes total linear momentum zero and places the center of mass at the origin. The nominal periods below are reference values from published tables/catalogues, not promises of exact numerical closure for the finite-precision seeds in this project.

## Included periodic presets

| Preset | \(p_x\) | \(p_y\) | Nominal period | Notes |
|---|---:|---:|---:|---|
| Butterfly I | 0.306892758965492 | 0.125506782829762 | 6.235641 | Higher-precision seed |
| Butterfly II | 0.392955223941802 | 0.0975792352080344 | 7.003907 | Higher-precision seed |
| Butterfly III | 0.405916 | 0.230163 | 13.8658 | Rounded seed |
| Butterfly IV | 0.350112 | 0.079339 | 79.4759 | Rounded seed |
| Bumblebee | 0.184278506469727 | 0.587188195800781 | 63.534541 | Higher-precision seed |
| Moth I | 0.464445237398184 | 0.396059973403921 | 14.893911 | Higher-precision seed |
| Moth II | 0.439165939331987 | 0.452967645644678 | 28.670278 | Higher-precision seed |
| Moth III | 0.383443534851074 | 0.377363693237305 | 25.840618 | Higher-precision seed |
| Goggles | 0.0833000564575194 | 0.127889282226563 | 10.466818 | Higher-precision seed |
| Yin-Yang I (A) | 0.513938054919243 | 0.304736003875733 | 17.328370 | Higher-precision seed |
| Yin-Yang I (B) | 0.282698682308198 | 0.327208786129952 | 10.962563 | Higher-precision seed |
| Yin-Yang II (A) | 0.41682 | 0.33033 | 55.7898 | Rounded seed |
| Yin-Yang II (B) | 0.41734 | 0.31310 | 54.2076 | Rounded seed |
| Dragonfly | 0.080584285736084 | 0.588836087036132 | 21.270975 | Higher-precision seed |
| Yarn | 0.559064247347 | 0.349191558 | 55.501762 | Approximate high-precision seed |

### Classic figure-eight

The **Figure-eight** preset uses a separate initial-state representation rather than the collinear isosceles seed scheme above. It uses equal masses, Newtonian gravity, and a nominal period of approximately 6.325914 model-time units.

## Scientific use

The core named families are based on the numerical periodic-orbit literature, including:

- M. Šuvakov and V. Dmitrašinović, “Three Classes of Newtonian Three-Body Planar Periodic Orbits,” *Physical Review Letters* **110**, 114301 (2013), [doi:10.1103/PhysRevLett.110.114301](https://doi.org/10.1103/PhysRevLett.110.114301), [arXiv:1303.0181](https://arxiv.org/abs/1303.0181).
- A later tabulation of higher-precision initial values is described in the discussion of periodic-orbit seed refinement; an accessible copy includes a table of the seven higher-precision seeds: [PDF reference](https://www.scl.rs/papers/PhysRevLett.110.114301.pdf).

The application uses adaptive RK45 by default for these presets because close encounters can be difficult for a coarse fixed step. To validate a seed scientifically, measure state closure after one nominal period, lower the RK45 tolerances, and repeat with tighter tolerances. A small visual resemblance to a published orbit is not itself a validation result. Rounded initial values, accumulated integration error, and unstable orbit families can all produce visible closure drift.
