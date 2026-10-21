# Gravity Lab 3D

**An interactive 3D Newtonian three-body gravity simulator built with Python, NumPy, Tkinter, and VTK.**

Explore orbital motion, change the mass and physical radius of each body, inspect gravitational influence zones, and experiment with collisions in an interactive 3D scene. Gravity Lab 3D combines an editable simulation setup with field visualization and numerical diagnostics.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-array%20computing-4DABCF?logo=numpy&logoColor=white)
![VTK](https://img.shields.io/badge/Rendering-VTK-1863A4)

## Preview

### Interactive 3D scene

The scene shows the three bodies, gravitational influence shells, and a colored slice of the combined gravitational field.

![Gravity Lab 3D preview](docs/images/gravity-lab-3d-preview.png)

### Astronomical preset

The project includes a Sun–Earth–Jupiter starting system using astronomical units, solar masses, and years.

![Astronomical preset preview](docs/images/astronomical-preview.png)

## Features

- **Interactive 3D viewport** rendered with VTK, with mouse-driven camera rotation and zoom.
- **Editable bodies:** mass, physical radius, 3D position `(x, y, z)`, and velocity `(vx, vy, vz)`.
- **Body-property calculations:** surface gravity, escape speed, and mean density.
- **Newtonian three-body dynamics** with Plummer softening.
- **Two numerical integrators:** Velocity Verlet (2nd order) and Yoshida (4th order).
- **Adaptive time-step option** for close encounters.
- **Finite-radius collision modes:** merge, bounce with adjustable restitution, pass through, or pause on impact.
- **Gravitational influence visualization:** acceleration-threshold shells and an approximate Eggleton Roche-lobe mode.
- **Combined gravitational-field map:** an XY slice of the total gravitational acceleration produced by the active bodies.
- **Visual aids:** trajectory trails, floor projections, acceleration-direction vectors, adjustable visual-size exaggeration, and camera fitting.
- **Six themes:** Midnight Dark, Light Minimal, Ocean Blue, Solarized Light, Purple Nebula, and High Contrast.
- **Diagnostics:** energy drift, angular-momentum drift, linear-momentum drift, minimum separation, pair-separation plots, and an energy-drift plot.
- **Exports:** PNG snapshots and CSV simulation history.
- **Astronomical preset** with AU, solar-mass, and year units and selected SI conversions for body properties.
- **Windows high-DPI awareness** configured before Tkinter is imported.
- **Automated checks** and a command-line snapshot mode.

## Requirements

- Python **3.10 or newer** is recommended.
- NumPy
- VTK 9.2 or newer
- Tkinter for the desktop GUI. Tkinter is included with many standard Python installations; on some Linux distributions it must be installed separately.

VTK is a relatively large dependency, so its first installation may take a little while. The 3D view is embedded in the main Tkinter window; it does not require the optional VTK Tcl/Tk bridge.

## Installation

### 1. Download the repository

Clone the repository, or download it from GitHub as a ZIP and extract it.

```bash
git clone <YOUR-REPOSITORY-URL>
cd <repository-folder-name>
```

Replace `<YOUR-REPOSITORY-URL>` with your GitHub repository URL and `<repository-folder-name>` with the folder created by `git clone`. If you downloaded a ZIP, open a terminal in the extracted `gravity_lab_3d` project folder instead.

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Launch the application

```bash
python main.py
```

On Windows, you can also launch `run_gravity_lab.bat` from the project folder.

## Quick start

1. Launch the application. The **3D inclined triple (recommended)** preset is selected by default.
2. Rotate the 3D view by dragging with the mouse and zoom using the mouse wheel.
3. Edit a body's mass, radius, position, or velocity in the sidebar.
4. Click **Apply values & reset** to validate the new values and restart the simulation with them.
5. Choose a collision behavior and an influence-shell mode to explore different outcomes.
6. Select a theme under **Appearance**, then click **Apply selected theme**.
7. Use **Play / Pause** to control the simulation, **Fit camera** to reframe the scene, and the export buttons to save a PNG or CSV history.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Space` | Play or pause the simulation |
| `R` | Apply values and reset (when a text field is not focused) |

## Presets

List available starting systems from the terminal:

```bash
python main.py --list-presets
```

Included presets:

- 3D inclined triple (recommended)
- Binary + inclined small body (Claude)
- Figure-eight, tilted 40 deg (Claude)
- Pythagorean 3-4-5 (chaotic)
- Lagrange triangle (unstable)
- Hierarchical triple (Claude)
- Sun - Earth - Jupiter (astronomical)

These presets are initial conditions for experimentation, not a guarantee that every system is stable indefinitely. Three-body dynamics can be chaotic and small numerical differences may lead to large changes over time.

## Run the physics checks

Run the built-in numerical self-test suite:

```bash
python main.py --selftest
```

Run the pytest test(s):

```bash
python -m pip install pytest
python -m pytest -q
```

## Render a PNG from the command line

The application supports a headless snapshot mode that advances a preset to a chosen simulation time and saves a PNG. The renderer and your system's OpenGL setup must support offscreen rendering. Some Linux systems may need a virtual display such as Xvfb.

```bash
python main.py --snapshot preview.png \
  --preset "3D inclined triple (recommended)" \
  --time 3
```

Render the astronomical preset with another theme:

```bash
python main.py --snapshot solar.png \
  --preset "Sun - Earth - Jupiter (astronomical)" \
  --time 2 \
  --theme "Ocean Blue"
```

You can customize the image dimensions with `--width` and `--height`. See all command-line options with:

```bash
python main.py --help
```

## Project structure

```text
gravity_lab_3d/
├── main.py                    # GUI entry point and command-line options
├── requirements.txt           # Python dependencies
├── run_gravity_lab.bat        # Windows launcher
├── gravity_lab/
│   ├── physics.py              # Three-body integration and collision logic
│   ├── fields.py               # Gravitational-field calculations
│   ├── presets.py              # Initial conditions and unit presets
│   ├── renderer_vtk.py         # VTK scene, geometry, camera, and snapshots
│   ├── gui.py                  # Tkinter interface and simulation controls
│   ├── themes.py               # Theme palettes
│   └── selftest.py             # Numerical self-test suite
├── tests/
│   └── test_physics.py         # Pytest entry point
└── docs/
    └── images/                 # README preview images
```

## Physics model and limitations

Gravity Lab 3D is designed for interactive exploration and numerical experimentation. Keep these assumptions in mind when interpreting results:

- **Gravity model:** the simulation uses Plummer-softened Newtonian point-mass forces. The softening parameter is a numerical regularizer; it is not the physical radius of a body.
- **Body radius:** physical radius is used for surface gravity, escape speed, mean density, and optional collision handling. The simulation does not model the internal gravitational structure of a finite-density sphere.
- **Collision modes:** merge and bounce are simplified idealized models. They do not include deformation, fragmentation, tidal forces, or realistic material behavior.
- **Influence shells:** a threshold shell shows where one body's isolated acceleration reaches a chosen value. It is a visualization threshold, not a finite edge to gravity.
- **Roche-lobe visualization:** the Eggleton expression is a two-body approximation. Its use in a changing three-body system is indicative, not an exact three-body equipotential calculation.
- **Visual-size exaggeration:** changing the displayed size of a sphere does not change its physical radius or the physics calculations.
- **Numerical accuracy:** close encounters may require a smaller time step or adaptive stepping. Check the energy-drift diagnostic when interpreting long simulations.

## Contributing

Bug reports, ideas, and pull requests are welcome. For a useful bug report, include your operating system, Python and VTK versions, the preset and settings used, and the relevant terminal output.

## License

A license has not yet been selected for this repository. Add a `LICENSE` file before publishing if you want to specify the terms under which others may use, modify, or redistribute the code.
