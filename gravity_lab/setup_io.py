"""Version-1 GUI setup file I/O, separated from Tkinter widget orchestration.

This file format stores editable UI preferences as well as body inputs. It is
intentionally distinct from ``state_io`` simulation checkpoints.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .body_size import normalise_sizes

FORMAT = "gravity-lab-3d-setup"
SCHEMA_VERSION = 1
BODY_FIELD_COUNT = 8


def validate_setup_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Setup JSON root must be an object.")
    if payload.get("format") != FORMAT or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("This file is not a supported Gravity Lab 3D setup JSON (schema version 1).")
    bodies = payload.get("bodies")
    if not isinstance(bodies, list) or len(bodies) != 3 or any(
        not isinstance(row, list) or len(row) != BODY_FIELD_COUNT for row in bodies
    ):
        raise ValueError("Setup must contain three bodies with mass, radius, position and velocity values.")
    settings = payload.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("Setup settings must be an object.")
    names = payload.get("body_names", [])
    if names and (not isinstance(names, list) or len(names) != 3):
        raise ValueError("body_names must contain exactly three names when provided.")
    colors = payload.get("body_colors", [])
    if colors and (not isinstance(colors, list) or len(colors) != 3):
        raise ValueError("body_colors must contain exactly three colours when provided.")
    # Optional and additive (no schema bump): files written before per-body
    # visual sizes existed simply omit the key and load with default sizes.
    sizes = payload.get("body_sizes", [])
    if sizes and not isinstance(sizes, list):
        raise ValueError("body_sizes must be a list of three {mode, value} objects when provided.")
    normalise_sizes(sizes, 3, names if isinstance(names, list) else None)
    metadata = payload.get("metadata", {})
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("Setup metadata must be an object.")
    return payload


def write_setup_json(path: str | os.PathLike[str], payload: Mapping[str, Any]) -> Path:
    """Validate and atomically write a schema-1 setup file."""
    data = validate_setup_payload(dict(payload))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
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


def read_setup_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read and validate a legacy-compatible schema-1 GUI setup."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read setup JSON: {exc}") from exc
    return validate_setup_payload(payload)
