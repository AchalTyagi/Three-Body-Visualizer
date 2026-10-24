import json

import pytest

from gravity_lab.setup_io import read_setup_json, write_setup_json


def sample_setup():
    return {
        "format": "gravity-lab-3d-setup", "schema_version": 1, "preset": "Custom / Build your own",
        "bodies": [["1", "0.1", "0", "0", "0", "0", "0", "0"] for _ in range(3)],
        "body_names": ["Sun", "Earth", "Moon"],
        "body_colors": ["#ffd166", "#40c4ff", "#c4cbd4"],
        "settings": {"axes": True, "dt": "0.001"}, "metadata": {"source": "test"},
    }


def test_setup_json_round_trip_keeps_schema_one_payload(tmp_path):
    path = write_setup_json(tmp_path / "setup.json", sample_setup())
    loaded = read_setup_json(path)
    assert loaded == sample_setup()


def test_setup_json_rejects_wrong_schema(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"format": "gravity-lab-3d-setup", "schema_version": 2}))
    with pytest.raises(ValueError, match="schema version 1"):
        read_setup_json(path)


def test_setup_json_rejects_bad_body_shape():
    payload = sample_setup()
    payload["bodies"] = [["1"]] * 3
    with pytest.raises(ValueError, match="three bodies"):
        write_setup_json("unused.json", payload)


def test_setup_json_rejects_nonfinite_json_numbers(tmp_path):
    payload = sample_setup()
    payload["settings"]["speed"] = float("nan")
    with pytest.raises(ValueError):
        write_setup_json(tmp_path / "bad.json", payload)
