"""Starter systems adapted from the supplied Claude and ChatGPT versions."""
from __future__ import annotations
import math

from .physics import G_AU_MSUN_YR, RK45

ARBITRARY = "Arbitrary units"
ASTRO = "Astronomical (AU, Msun, yr)"


def body(mass, radius, pos, vel):
    return (mass, radius, *pos, *vel)


def tilt(bodies, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    result = []
    for m, r, x, y, z, vx, vy, vz in bodies:
        result.append((m, r, x, y*c-z*s, y*s+z*c, vx, vy*c-vz*s, vy*s+vz*c))
    return result


def lagrange(separation_scale=4.0, mass=1.0, G=1.0, radius=0.25):
    a = separation_scale * math.sqrt(3.0)
    speed = math.sqrt(3.0 * G * mass / a**3) * separation_scale
    values = []
    for k in range(3):
        theta = math.pi / 2 + k * 2 * math.pi / 3
        values.append(body(mass, radius,
                           (separation_scale*math.cos(theta), separation_scale*math.sin(theta), 0.0),
                           (-speed*math.sin(theta), speed*math.cos(theta), 0.0)))
    return values


FIG8 = [body(1, 0.055, (-0.97000436, 0.24308753, 0), (0.466203685, 0.43236573, 0)),
        body(1, 0.055, (0.97000436, -0.24308753, 0), (0.466203685, 0.43236573, 0)),
        body(1, 0.055, (0, 0, 0), (-0.93240737, -0.86473146, 0))]

_INCL = math.radians(11.5)
# Circular speeds from the engine's own G (not a hard-coded 4*pi^2), so the preset
# orbits stay consistent with the gravitational parameter actually used.
_VJ = math.sqrt(G_AU_MSUN_YR / 5.2)
_VE = math.sqrt(G_AU_MSUN_YR * (1.0 + 3.003e-6))


def periodic_orbit(name, p1, p2, period, *, family, view=3.2, dt=0.003):
    """Build an equal-mass planar periodic-orbit seed from the published isosceles family.

    Initial positions are (-1,0), (+1,0), (0,0). Bodies 1 and 2 have equal
    velocity (p1,p2); body 3 has (-2*p1,-2*p2), giving zero total momentum.
    The rounded literature seeds are suitable for visualization, but very long
    integrations may require higher-precision initial conditions to close exactly.
    """
    return dict(
        units=ARBITRARY, G=1.0, dt=dt, steps=5, view=view, soft=0.0, threshold=1.5,
        display_scale=14.0, adaptive=False, autozoom=False, collision="Pass through", integrator=RK45,
        show_shells=False, show_field=False, show_floor=False, show_trails=True,
        description=f"{name} · published initial-condition seed · nominal period {period:.4f} time units",
        period=float(period), family=family, model_name=name,
        bodies=[body(1.0, 0.006, (-1.0, 0.0, 0.0), (p1, p2, 0.0)),
                body(1.0, 0.006, ( 1.0, 0.0, 0.0), (p1, p2, 0.0)),
                body(1.0, 0.006, ( 0.0, 0.0, 0.0), (-2*p1, -2*p2, 0.0))],
    )

PRESETS = {
    "3D inclined triple (recommended)": dict(
        units=ARBITRARY, G=1.0, dt=0.003, steps=4, view=12.0, soft=0.0, threshold=1.0,
        adaptive=True, autozoom=True, collision="Merge (inelastic)",
        bodies=[body(10, 0.48, (-3, 0, -0.55), (0, -0.22, 0.07)),
                body(10, 0.48, (3, 0, 0.45), (0, 0.22, -0.04)),
                body(1, 0.24, (0, 4, 1.7), (0.45, 0, -0.10))]),
    "Binary + inclined small body (Claude)": dict(
        units=ARBITRARY, G=1.0, dt=0.005, steps=4, view=16.0, soft=0.0, threshold=1.0,
        adaptive=False, autozoom=False, collision="Merge (inelastic)",
        bodies=[body(10, 0.6, (-3, 0, 0), (0, -0.85, 0)),
                body(10, 0.6, (3, 0, 0), (0, 0.85, 0)),
                body(1, 0.3, (14, 0, 0), (0, 1.15*math.cos(math.radians(25)), 1.15*math.sin(math.radians(25))))]),
    "Figure-eight, tilted 40 deg (Claude)": dict(
        units=ARBITRARY, G=1.0, dt=0.002, steps=4, view=2.0, soft=0.0, threshold=0.25,
        adaptive=False, autozoom=False, collision="Bounce", bodies=tilt(FIG8, 40)),
    "Pythagorean 3-4-5 (chaotic)": dict(
        units=ARBITRARY, G=1.0, dt=0.0015, steps=4, view=6.0, soft=0.0, threshold=1.0,
        adaptive=True, autozoom=True, collision="Merge (inelastic)",
        bodies=[body(3, 0.003, (1, 3, 0), (0, 0, 0)),
                body(4, 0.0035, (-2, -1, 0), (0, 0, 0)),
                body(5, 0.004, (1, -1, 0), (0, 0, 0))]),
    "Lagrange triangle (unstable)": dict(
        units=ARBITRARY, G=1.0, dt=0.01, steps=4, view=6.0, soft=0.0, threshold=0.2,
        adaptive=False, autozoom=False, collision="Bounce", bodies=tilt(lagrange(), 25)),
    "Hierarchical triple (Claude)": dict(
        units=ARBITRARY, G=1.0, dt=0.005, steps=4, view=14.0, soft=0.0, threshold=1.0,
        adaptive=True, autozoom=True, collision="Merge (inelastic)",
        bodies=[body(5, 0.4, (-1, 0, 0), (0, -1.118034, 0)),
                body(5, 0.4, (1, 0, 0), (0, 1.118034, 0)),
                body(5, 0.4, (10, 0, 0), (0, math.sqrt(1.5)*math.cos(math.radians(60)), math.sqrt(1.5)*math.sin(math.radians(60))))]),
    "Sun - Earth - Jupiter (astronomical)": dict(
        units=ASTRO, G=G_AU_MSUN_YR, dt=0.001, steps=10, view=6.5, soft=0.0, threshold=10.0,
        adaptive=False, autozoom=False, collision="Merge (inelastic)",
        bodies=[body(1.0, 0.00465, (0, 0, 0), (0, 0, 0)),
                body(3.003e-6, 4.26e-5, (1, 0, 0), (0, _VE, 0)),
                body(9.546e-4, 4.78e-4, (-5.2, 0, 0), (0, -_VJ*math.cos(_INCL), -_VJ*math.sin(_INCL)))]),

    # Published equal-mass, zero-angular-momentum periodic-orbit seeds from the
    # Šuvakov–Dmitrašinović gallery. Values are rounded; tiny closure drift is expected.
    "Periodic · Butterfly I (T≈6.2356)": periodic_orbit("Butterfly I", 0.306892758965492, 0.125506782829762, 6.23564136316479, family="Butterfly"),
    "Periodic · Butterfly II (T≈7.0039)": periodic_orbit("Butterfly II", 0.392955223941802, 0.0975792352080344, 7.00390738764014, family="Butterfly"),
    "Periodic · Butterfly III (T≈13.8658)": periodic_orbit("Butterfly III", 0.405916, 0.230163, 13.8658, family="Butterfly", view=3.8),
    "Periodic · Butterfly IV (T≈79.4759)": periodic_orbit("Butterfly IV", 0.350112, 0.079339, 79.4759, family="Butterfly", view=3.8, dt=0.003),
    "Periodic · Bumblebee (T≈63.5345)": periodic_orbit("Bumblebee", 0.184278506469727, 0.587188195800781, 63.5345412733264, family="Bumblebee", view=4.0, dt=0.003),
    "Periodic · Moth I (T≈14.8939)": periodic_orbit("Moth I", 0.464445237398184, 0.396059973403921, 14.8939113169584, family="Moth", view=3.8),
    "Periodic · Moth II (T≈28.6703)": periodic_orbit("Moth II", 0.439165939331987, 0.452967645644678, 28.6702783225658, family="Moth", view=3.8),
    "Periodic · Moth III (T≈25.8406)": periodic_orbit("Moth III", 0.383443534851074, 0.377363693237305, 25.8406180475758, family="Moth", view=3.8),
    "Periodic · Goggles (T≈10.4668)": periodic_orbit("Goggles", 0.0833000564575194, 0.127889282226563, 10.4668176954385, family="Goggles", view=2.8),
    "Periodic · Yin-Yang I (T≈17.3284)": periodic_orbit("Yin-Yang I", 0.513938054919243, 0.304736003875733, 17.328369755004, family="Yin-Yang", view=3.8),
    "Periodic · Dragonfly (T≈21.2710)": periodic_orbit("Dragonfly", 0.080584, 0.588836, 21.2710, family="Dragonfly", view=3.8),
    "Periodic · Yarn (T≈55.5018)": periodic_orbit("Yarn", 0.559064247347, 0.349191558, 55.5017624421301, family="Yarn", view=4.2, dt=0.003),
    "Periodic · Yin-Yang I (branch b, T≈10.9626)": periodic_orbit("Yin-Yang I · branch b", 0.282698682308198, 0.327208786129952, 10.9625630756217, family="Yin-Yang I", view=3.5),
    "Periodic · Yin-Yang II (branch a, T≈55.7898)": periodic_orbit("Yin-Yang II · branch a", 0.41682, 0.33033, 55.7898, family="Yin-Yang II", view=4.2, dt=0.003),
    "Periodic · Yin-Yang II (branch b, T≈54.2076)": periodic_orbit("Yin-Yang II · branch b", 0.41734, 0.31310, 54.2076, family="Yin-Yang II", view=4.2, dt=0.003),
    "Periodic · Figure-eight (classic, T≈6.3259)": dict(
        units=ARBITRARY, G=1.0, dt=0.0015, steps=5, view=2.2, soft=0.0, threshold=1.5,
        display_scale=14.0, adaptive=False, autozoom=False, collision="Pass through", integrator=RK45,
        show_shells=False, show_field=False, show_floor=False, show_trails=True,
        description="Classic Chenciner–Montgomery figure-eight · nominal period 6.3259 time units",
        period=6.32591398, family="Figure-eight", model_name="Figure-eight (classic)",
        bodies=[body(1.0, 0.006, (-0.97000436, 0.24308753, 0.0), (0.466203685, 0.43236573, 0.0)),
                body(1.0, 0.006, (0.97000436, -0.24308753, 0.0), (0.466203685, 0.43236573, 0.0)),
                body(1.0, 0.006, (0.0, 0.0, 0.0), (-0.93240737, -0.86473146, 0.0))]),
    "Periodic · Euler collinear (T≈5.6199)": dict(
        units=ARBITRARY, G=1.0, dt=0.0015, steps=5, view=2.0, soft=0.0, threshold=1.5,
        display_scale=14.0, adaptive=False, autozoom=False, collision="Pass through", integrator=RK45,
        show_shells=False, show_field=False, show_floor=False, show_trails=True,
        description="Euler rotating collinear central configuration · nominal period 5.6199 time units",
        period=2 * math.pi / math.sqrt(1.25), family="Euler", model_name="Euler collinear rotating",
        bodies=[body(1.0, 0.006, (-1.0, 0.0, 0.0), (0.0, -math.sqrt(1.25), 0.0)),
                body(1.0, 0.006, (1.0, 0.0, 0.0), (0.0, math.sqrt(1.25), 0.0)),
                body(1.0, 0.006, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]),
    "Periodic · Lagrange equilateral (T≈3.6276)": dict(
        units=ARBITRARY, G=1.0, dt=0.0015, steps=5, view=1.6, soft=0.0, threshold=1.5,
        display_scale=14.0, adaptive=False, autozoom=False, collision="Pass through", integrator=RK45,
        show_shells=False, show_field=False, show_floor=False, show_trails=True,
        description="Lagrange rotating equilateral central configuration · nominal period 3.6276 time units",
        period=2 * math.pi / math.sqrt(3.0), family="Lagrange", model_name="Lagrange equilateral",
        bodies=lagrange(separation_scale=1 / math.sqrt(3.0), mass=1.0, G=1.0, radius=0.006)),
}

PRESET_NAMES = list(PRESETS)


def engine_inputs(preset: dict):
    rows = preset["bodies"]
    masses = [row[0] for row in rows]
    radii = [row[1] for row in rows]
    pos = [row[2:5] for row in rows]
    vel = [row[5:8] for row in rows]
    return masses, radii, pos, vel
