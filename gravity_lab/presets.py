"""Curated periodic-orbit presets and helpers for Gravity Lab 3D."""
from __future__ import annotations
import math

from .physics import RK45

ARBITRARY = "Arbitrary units"
ASTRO = "Astronomical (AU, Msun, yr)"


def body(mass, radius, pos, vel):
    return (mass, radius, *pos, *vel)




def periodic_orbit(name, p1, p2, period, *, family, view=1.4, dt=0.003):
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
    # User-facing catalog contains only the named periodic-orbit families represented
    # by the supplied orbit-gallery image. Generic demos and classical central
    # configurations are intentionally not selectable gallery presets.
    "Butterfly I": periodic_orbit("Butterfly I", 0.306892758965492, 0.125506782829762,
                                  6.23564136316479, family="Butterfly", view=1.35),
    "Butterfly II": periodic_orbit("Butterfly II", 0.392955223941802, 0.0975792352080344,
                                   7.00390738764014, family="Butterfly", view=1.40),
    "Butterfly III": periodic_orbit("Butterfly III", 0.405916, 0.230163, 13.8658,
                                    family="Butterfly", view=1.41),
    "Butterfly IV": periodic_orbit("Butterfly IV", 0.350112, 0.079339, 79.4759,
                                   family="Butterfly", view=1.39, dt=0.003),
    "Bumblebee": periodic_orbit("Bumblebee", 0.184278506469727, 0.587188195800781,
                                63.5345412733264, family="Bumblebee", view=1.51, dt=0.003),
    "Dragonfly": periodic_orbit("Dragonfly", 0.080584, 0.588836, 21.2710,
                                family="Dragonfly", view=1.34),
    "Figure-eight": dict(
        units=ARBITRARY, G=1.0, dt=0.0015, steps=5, view=1.41, soft=0.0, threshold=1.5,
        display_scale=14.0, adaptive=False, autozoom=False, collision="Pass through", integrator=RK45,
        show_shells=False, show_field=False, show_floor=False, show_trails=True,
        description="Classic planar figure-eight orbit · nominal period 6.3259 time units",
        period=6.32591398, family="Figure-eight", model_name="Figure-eight",
        bodies=[body(1.0, 0.006, (-0.97000436, 0.24308753, 0.0), (0.466203685, 0.43236573, 0.0)),
                body(1.0, 0.006, (0.97000436, -0.24308753, 0.0), (0.466203685, 0.43236573, 0.0)),
                body(1.0, 0.006, (0.0, 0.0, 0.0), (-0.93240737, -0.86473146, 0.0))]),
    "Goggles": periodic_orbit("Goggles", 0.0833000564575194, 0.127889282226563,
                              10.4668176954385, family="Goggles", view=1.36),
    "Moth I": periodic_orbit("Moth I", 0.464445237398184, 0.396059973403921,
                             14.8939113169584, family="Moth", view=1.48),
    "Moth II": periodic_orbit("Moth II", 0.439165939331987, 0.452967645644678,
                              28.6702783225658, family="Moth", view=1.51),
    "Moth III": periodic_orbit("Moth III", 0.383443534851074, 0.377363693237305,
                               25.8406180475758, family="Moth", view=1.41),
    "Yarn": periodic_orbit("Yarn", 0.559064247347, 0.349191558, 55.5017624421301,
                           family="Yarn", view=1.95, dt=0.003),
    "Yin-Yang I (A)": periodic_orbit("Yin-Yang I (A)", 0.513938054919243, 0.304736003875733,
                                     17.328369755004, family="Yin-Yang I", view=1.66),
    "Yin-Yang I (B)": periodic_orbit("Yin-Yang I (B)", 0.282698682308198, 0.327208786129952,
                                     10.9625630756217, family="Yin-Yang I", view=1.35),
    "Yin-Yang II (A)": periodic_orbit("Yin-Yang II (A)", 0.41682, 0.33033, 55.7898,
                                      family="Yin-Yang II", view=1.41, dt=0.003),
    "Yin-Yang II (B)": periodic_orbit("Yin-Yang II (B)", 0.41734, 0.31310, 54.2076,
                                      family="Yin-Yang II", view=1.41, dt=0.003),
}

PRESET_NAMES = list(PRESETS)


def engine_inputs(preset: dict):
    rows = preset["bodies"]
    masses = [row[0] for row in rows]
    radii = [row[1] for row in rows]
    pos = [row[2:5] for row in rows]
    vel = [row[5:8] for row in rows]
    return masses, radii, pos, vel
