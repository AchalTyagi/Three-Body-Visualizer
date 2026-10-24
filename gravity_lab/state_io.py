"""Versioned, checksummed simulation checkpoints at integration-step boundaries."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .service import SimulationService
from .state import SimulationState

FORMAT = "gravity-lab-3d-checkpoint"
SCHEMA_VERSION = 1


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def checkpoint_payload(service: SimulationService) -> dict[str, Any]:
    """Capture model state and important runtime counters for restartable runs."""
    if service.state is None or service.engine is None:
        raise RuntimeError("Cannot save a checkpoint before a simulation has been configured.")
    engine = service.engine
    if not engine.is_healthy():
        raise RuntimeError("Cannot save an exact checkpoint from a numerically unhealthy simulation.")
    runtime = {
        "events": [[float(t), str(event)] for t, event in engine.events],
        "impact": bool(engine.impact),
        "touching_pairs": [list(pair) for pair in sorted(engine._touching)],
        "energy_lost": float(engine.energy_lost),
        "tidal_energy_dissipated": float(engine.tidal_energy_dissipated),
        "rk45_last_error": float(engine.rk45_last_error),
        "rk45_accepted_steps": int(engine.rk45_accepted_steps),
        "rk45_rejected_steps": int(engine.rk45_rejected_steps),
        "initial_energy": float(engine.e0),
        "initial_linear_momentum": engine.p0.tolist(),
        "initial_angular_momentum": engine.l0.tolist(),
    }
    core = {"format": FORMAT, "schema_version": SCHEMA_VERSION,
            "state": service.state.to_mapping(), "runtime": runtime}
    return {**core, "sha256": hashlib.sha256(_canonical(core)).hexdigest()}


def save_checkpoint(service: SimulationService, path: str | os.PathLike[str]) -> Path:
    """Atomically save a deterministic JSON checkpoint with a SHA-256 checksum."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = checkpoint_payload(service)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target


def load_checkpoint(path: str | os.PathLike[str]) -> SimulationService:
    """Load, verify and restore a checkpoint into a new SimulationService."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read checkpoint: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ValueError("This is not a Gravity Lab 3D checkpoint.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported checkpoint schema version: {payload.get('schema_version')!r}.")
    core = {key: payload.get(key) for key in ("format", "schema_version", "state", "runtime")}
    expected = hashlib.sha256(_canonical(core)).hexdigest()
    if not isinstance(payload.get("sha256"), str) or payload["sha256"] != expected:
        raise ValueError("Checkpoint checksum mismatch: the file may be damaged or modified.")
    try:
        state = SimulationState.from_mapping(payload["state"])
        runtime = payload["runtime"]
        if not isinstance(runtime, dict):
            raise ValueError("Checkpoint runtime section must be an object.")
        service = SimulationService(state)
        engine = service.engine
        assert engine is not None
        engine.events.clear()
        for item in runtime["events"]:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError("Each runtime event must contain time and description.")
            engine.events.append((float(item[0]), str(item[1])))
        engine.impact = bool(runtime["impact"])
        engine._touching = {tuple(int(i) for i in pair) for pair in runtime["touching_pairs"]}
        if any(len(pair) != 2 or any(i not in (0, 1, 2) for i in pair) for pair in engine._touching):
            raise ValueError("Touching-pair indices must refer to the three body slots.")
        engine.energy_lost = float(runtime["energy_lost"])
        engine.tidal_energy_dissipated = float(runtime["tidal_energy_dissipated"])
        engine.rk45_last_error = float(runtime["rk45_last_error"])
        engine.rk45_accepted_steps = int(runtime["rk45_accepted_steps"])
        engine.rk45_rejected_steps = int(runtime["rk45_rejected_steps"])
        engine.e0 = float(runtime["initial_energy"])
        engine.p0 = np.asarray(runtime["initial_linear_momentum"], dtype=float).reshape(3).copy()
        engine.l0 = np.asarray(runtime["initial_angular_momentum"], dtype=float).reshape(3).copy()
        scalars = (engine.energy_lost, engine.tidal_energy_dissipated, engine.rk45_last_error, engine.e0)
        if not all(math.isfinite(value) for value in scalars):
            raise ValueError("Checkpoint contains non-finite runtime values.")
        if engine.rk45_accepted_steps < 0 or engine.rk45_rejected_steps < 0:
            raise ValueError("Checkpoint RK45 counters cannot be negative.")
        if not (np.all(np.isfinite(engine.p0)) and np.all(np.isfinite(engine.l0))):
            raise ValueError("Checkpoint contains non-finite momentum baselines.")
        engine._acc = None
        return service
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Malformed checkpoint data: {exc}") from exc
