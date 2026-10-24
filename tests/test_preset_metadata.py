import copy

import pytest

from gravity_lab.preset_metadata import preset_fingerprint, preset_manifest
from gravity_lab.presets import PRESETS


def test_preset_manifest_is_stable_and_checksummed():
    first = preset_manifest()
    second = preset_manifest()
    assert first == second
    assert first["schema_version"] == 1
    assert len(first["sha256"]) == 64
    assert all(len(item["sha256"]) == 64 for item in first["presets"])
    assert first["presets"] == sorted(first["presets"], key=lambda item: item["name"])


def test_preset_fingerprint_changes_when_initial_condition_changes():
    name = next(iter(PRESETS))
    original = preset_fingerprint(name)
    altered = copy.deepcopy(PRESETS)
    row = list(altered[name]["bodies"][0])
    row[2] += 0.001
    altered[name]["bodies"][0] = row
    assert preset_fingerprint(name, altered) != original


def test_preset_fingerprint_rejects_unknown_name():
    with pytest.raises(KeyError, match="Unknown preset"):
        preset_fingerprint("missing")
