"""Stable preset metadata and SHA-256 fingerprints for reproducible experiments."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .presets import PRESETS

MANIFEST_SCHEMA_VERSION = 1


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data deterministically for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def preset_fingerprint(name: str, catalog: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    """Return a stable SHA-256 hash of one preset's full initial-condition metadata."""
    presets = PRESETS if catalog is None else catalog
    if name not in presets:
        raise KeyError(f"Unknown preset: {name!r}.")
    return hashlib.sha256(canonical_json(presets[name]).encode("utf-8")).hexdigest()


def preset_manifest(catalog: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Create a versioned manifest suitable for release notes and benchmark reports."""
    presets = PRESETS if catalog is None else catalog
    items = []
    for name in sorted(presets):
        data = presets[name]
        items.append({
            "name": name,
            "description": str(data.get("description", "")),
            "units": str(data.get("units", "Arbitrary units")),
            "integrator": str(data.get("integrator", "Yoshida (4th order, symplectic)")),
            "collision_mode": str(data.get("collision", "Merge (inelastic)")),
            "body_count": len(data.get("bodies", ())),
            "sha256": preset_fingerprint(name, presets),
        })
    core = {"schema_version": MANIFEST_SCHEMA_VERSION, "presets": items}
    core["sha256"] = hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()
    return core
