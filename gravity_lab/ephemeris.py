"""Optional JPL Horizons import helpers for three-body astronomical initial states.

Horizons vectors are fetched at one epoch in the solar-system-barycentric (SSB)
origin, ecliptic reference plane, AU and AU/day. This module converts velocities
to AU/Julian-year and recentres the selected three-body subsystem so its COM is
at rest. The imported system is thereafter evolved as an isolated three-body
model; omitted planets are not kept as external perturbing bodies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import math
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np

from .physics import AU_M, YEAR_S, MSUN_KG, G_SI, G_AU_MSUN_YR

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
JULIAN_YEAR_DAYS = 365.25

# Values are approximate mean/nominal radii and masses expressed in AU and solar masses.
# Horizons supplies state vectors, not physical mass/radius properties.
SOLAR_SYSTEM_BODIES = {
    "Sun":     {"id": "10",  "mass": 1.0,          "radius_au": 0.00465047},
    "Mercury": {"id": "199", "mass": 1.66012e-7,  "radius_au": 2.4397e3 / (AU_M / 1000.0)},
    "Venus":   {"id": "299", "mass": 2.44784e-6,  "radius_au": 6.0518e3 / (AU_M / 1000.0)},
    "Earth":   {"id": "399", "mass": 3.00349e-6,  "radius_au": 6.3710e3 / (AU_M / 1000.0)},
    # JPL Horizons target ID 301 is the Moon's center; mass and radius are
    # physical properties supplied locally because Horizons vectors omit them.
    "Moon":    {"id": "301", "mass": 3.694298e-8, "radius_au": 1.7374e3 / (AU_M / 1000.0)},
    "Mars":    {"id": "499", "mass": 3.22715e-7,  "radius_au": 3.3895e3 / (AU_M / 1000.0)},
    "Jupiter": {"id": "599", "mass": 9.54588e-4,  "radius_au": 6.9911e4 / (AU_M / 1000.0)},
    "Saturn":  {"id": "699", "mass": 2.85812e-4,  "radius_au": 5.8232e4 / (AU_M / 1000.0)},
    "Uranus":  {"id": "799", "mass": 4.36587e-5,  "radius_au": 2.5362e4 / (AU_M / 1000.0)},
    "Neptune": {"id": "899", "mass": 5.15079e-5,  "radius_au": 2.4622e4 / (AU_M / 1000.0)},
}

class HorizonsServerError(RuntimeError):
    """JPL Horizons failed on its own side (outage, overload or internal fault).

    Nothing is wrong with the requested body or epoch; retrying later usually works.
    """


# Fragments of messages that come from Horizons' own backend (for example
# "wldini(): missing required file ..."), not from a problem with the request.
_SERVER_FAULT_MARKERS = (
    "wldini", "missing required file", "var not declared", "execution-control",
    "internal error", "internal server error", "service unavailable",
    "temporarily unavailable", "try again later", "server is busy", "too many requests",
)
_TRANSIENT_HTTP_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_sleep = time.sleep  # indirection so tests can run without real delays


def _looks_like_server_fault(text) -> bool:
    lowered = str(text).lower()
    return any(marker in lowered for marker in _SERVER_FAULT_MARKERS)


def _query_horizons(request, name: str, timeout: float, retries: int, backoff: float) -> dict:
    """Return Horizons' JSON reply, retrying transient server/network failures.

    Request errors (unknown target, bad epoch, ...) are returned immediately for the
    caller to report; they are never retried. Delays grow as backoff, 2*backoff, ...
    """
    attempts = max(0, int(retries)) + 1
    kind, detail = "server", ""
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in _TRANSIENT_HTTP_CODES:
                raise RuntimeError(f"Could not contact JPL Horizons for {name}: HTTP {exc.code} {exc.reason}") from exc
            kind, detail = "server", f"HTTP {exc.code} {exc.reason}"
        except ValueError as exc:  # non-JSON reply, e.g. an HTML maintenance page
            kind, detail = "server", f"unreadable reply ({exc})"
        except (URLError, OSError) as exc:  # DNS failure, refused connection, timeout
            kind, detail = "network", str(exc)
        else:
            result_text = str(payload.get("result", ""))
            error = payload.get("error")
            if error and _looks_like_server_fault(error):
                kind, detail = "server", str(error).strip()
            elif "$$SOE" not in result_text and _looks_like_server_fault(result_text):
                kind, detail = "server", result_text.strip()
            else:
                return payload
        if attempt < attempts - 1:
            _sleep(backoff * (2 ** attempt))
    if kind == "network":
        raise RuntimeError(
            f"Could not contact JPL Horizons for {name} after {attempts} attempts: {detail}. "
            "Check your internet connection or try again later.")
    raise HorizonsServerError(
        f"JPL Horizons is having a server-side problem (not caused by your inputs) while "
        f"fetching {name}; {attempts} attempts failed. This is usually temporary, so try again later. "
        f"Last response: {detail[:300]}")


_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"


@dataclass(frozen=True)
class HorizonsBodyState:
    name: str
    target_id: str
    mass_solar: float
    radius_au: float
    position_au: tuple[float, float, float]
    velocity_au_per_year: tuple[float, float, float]


@dataclass(frozen=True)
class HorizonsImport:
    epoch: str
    names: tuple[str, str, str]
    masses: np.ndarray
    radii: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray
    gravitational_constant: float = G_AU_MSUN_YR
    source: str = "NASA/JPL Horizons API"
    reference_frame: str = "Ecliptic J2000 / ICRF orientation, SSB origin"


def _float(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


def parse_horizons_vectors(result_text: str) -> tuple[np.ndarray, np.ndarray]:
    """Parse one Horizons VECTORS result block containing X/Y/Z and VX/VY/VZ labels."""
    if not isinstance(result_text, str) or "$$SOE" not in result_text or "$$EOE" not in result_text:
        raise ValueError("Horizons response has no $$SOE/$$EOE vector data block.")
    block = result_text.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    pos_patterns = [
        rf"X\s*=\s*({_NUMBER}).*?Y\s*=\s*({_NUMBER}).*?Z\s*=\s*({_NUMBER})",
    ]
    vel_patterns = [
        rf"VX\s*=\s*({_NUMBER}).*?VY\s*=\s*({_NUMBER}).*?VZ\s*=\s*({_NUMBER})",
    ]
    pm = next((re.search(p, block, re.IGNORECASE | re.DOTALL) for p in pos_patterns
               if re.search(p, block, re.IGNORECASE | re.DOTALL)), None)
    vm = next((re.search(p, block, re.IGNORECASE | re.DOTALL) for p in vel_patterns
               if re.search(p, block, re.IGNORECASE | re.DOTALL)), None)
    if pm is None or vm is None:
        raise ValueError("Could not parse the Horizons position/velocity vector labels.")
    position = np.array([_float(pm.group(i)) for i in range(1, 4)], dtype=float)
    velocity_au_day = np.array([_float(vm.group(i)) for i in range(1, 4)], dtype=float)
    velocity = velocity_au_day * JULIAN_YEAR_DAYS
    if not np.all(np.isfinite(position)) or not np.all(np.isfinite(velocity)):
        raise ValueError("Horizons returned a non-finite state vector.")
    return position, velocity



def validate_horizons_epoch(epoch: str) -> str:
    """Validate and normalize a Horizons calendar epoch (TDB interpretation).

    Accepted forms are YYYY-MM-DD and YYYY-MM-DD HH:MM. Horizons interprets
    the submitted calendar time as TDB through TIME_TYPE.
    """
    value = str(epoch).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(value, fmt)
            # strptime is permissive about some zero-padding; enforce canonical input.
            if parsed.strftime(fmt) == value:
                return value if fmt.endswith("%M") else value + " 00:00"
        except ValueError:
            pass
    raise ValueError("Epoch must be a valid YYYY-MM-DD date or YYYY-MM-DD HH:MM time (TDB).")


def fetch_horizons_body(name: str, epoch: str, timeout: float = 20.0, *,
                        retries: int = 2, backoff: float = 1.5) -> HorizonsBodyState:
    """Fetch a single body's geometric SSB state from the official JPL Horizons API.

    Transient server-side failures are retried ``retries`` times with exponential
    backoff before ``HorizonsServerError`` is raised.
    """
    if name not in SOLAR_SYSTEM_BODIES:
        raise ValueError(f"Unsupported Solar System body: {name!r}.")
    parsed_epoch = validate_horizons_epoch(epoch)
    target = SOLAR_SYSTEM_BODIES[name]
    params = {
        "format": "json",
        "COMMAND": f"'{target['id']}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'VECTORS'",
        "CENTER": "'@0'",
        "TLIST": f"'{parsed_epoch}'",
        "TLIST_TYPE": "'CAL'",
        "TIME_TYPE": "'TDB'",
        "REF_PLANE": "'ECLIPTIC'",
        "REF_SYSTEM": "'ICRF'",
        "OUT_UNITS": "'AU-D'",
        "VEC_TABLE": "'2'",
        "VEC_LABELS": "'YES'",
        "VEC_CORR": "'NONE'",
    }
    url = HORIZONS_URL + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "GravityLab3D/1.0 (JPL Horizons state import)"})
    payload = _query_horizons(request, name, timeout, retries, backoff)
    if payload.get("error"):
        raise RuntimeError(f"JPL Horizons error for {name}: {payload['error']}")
    result_text = payload.get("result", "")
    if "$$SOE" not in result_text and payload.get("signature"):
        # Some response-level failures are embedded in the result text.
        if "error" in result_text.lower() or "cannot" in result_text.lower():
            raise RuntimeError(f"JPL Horizons rejected {name}: {result_text.strip()[:500]}")
    position, velocity = parse_horizons_vectors(result_text)
    return HorizonsBodyState(
        name=name,
        target_id=target["id"],
        mass_solar=float(target["mass"]),
        radius_au=float(target["radius_au"]),
        position_au=tuple(position.tolist()),
        velocity_au_per_year=tuple(velocity.tolist()),
    )


def fetch_three_body_horizons(names, epoch: str, timeout: float = 20.0) -> HorizonsImport:
    """Fetch three unique Solar System bodies and return COM-centred AU/Msun/year state."""
    names = tuple(names)
    if len(names) != 3 or len(set(names)) != 3:
        raise ValueError("Choose exactly three different bodies.")
    if any(name not in SOLAR_SYSTEM_BODIES for name in names):
        raise ValueError("One or more selected bodies are not supported.")
    states = [fetch_horizons_body(name, epoch, timeout=timeout) for name in names]
    masses = np.array([s.mass_solar for s in states], dtype=float)
    radii = np.array([s.radius_au for s in states], dtype=float)
    positions = np.array([s.position_au for s in states], dtype=float)
    velocities = np.array([s.velocity_au_per_year for s in states], dtype=float)
    # Use an inertial frame with the selected subsystem's COM at rest. This
    # preserves all relative states while preventing bulk translation.
    total_mass = float(masses.sum())
    positions -= np.sum(masses[:, None] * positions, axis=0) / total_mass
    velocities -= np.sum(masses[:, None] * velocities, axis=0) / total_mass
    return HorizonsImport(
        epoch=validate_horizons_epoch(epoch), names=names, masses=masses, radii=radii,
        positions=positions, velocities=velocities,
    )
