import numpy as np
import pytest

from gravity_lab.ephemeris import (
    HorizonsBodyState,
    SOLAR_SYSTEM_BODIES,
    G_AU_MSUN_YR,
    fetch_three_body_horizons,
    parse_horizons_vectors,
)


def test_parse_horizons_labeled_vector_converts_au_per_day_to_au_per_year():
    sample = """JPL test result
$$SOE
2450000.500000000 = A.D. 1995-Oct-09 00:00:00.0000 TDB
 X = 1.000000000000000E+00 Y = -2.000000000000000E+00 Z = 3.000000000000000E-01
 VX= 1.000000000000000E-02 VY= -2.000000000000000E-02 VZ= 3.000000000000000E-03
$$EOE
"""
    position, velocity = parse_horizons_vectors(sample)
    np.testing.assert_allclose(position, [1.0, -2.0, 0.3])
    np.testing.assert_allclose(velocity, np.array([0.01, -0.02, 0.003]) * 365.25)


def test_parse_horizons_rejects_missing_vector_block():
    with pytest.raises(ValueError, match="vector data block"):
        parse_horizons_vectors("API error: no ephemeris generated")


def test_three_body_import_recenters_selected_system(monkeypatch):
    states = {
        "Sun": HorizonsBodyState("Sun", "10", 1.0, 0.00465, (0.01, 0.02, 0.0), (0.001, 0.002, 0.0)),
        "Earth": HorizonsBodyState("Earth", "399", 3e-6, 4e-5, (1.01, 0.02, 0.0), (0.001, 6.28, 0.0)),
        "Jupiter": HorizonsBodyState("Jupiter", "599", 9.5e-4, 4.7e-4, (-5.19, 0.03, 0.1), (-0.001, -2.75, 0.02)),
    }

    def fake_fetch(name, epoch, timeout=20.0):
        assert epoch == "2026-10-21"
        return states[name]

    monkeypatch.setattr("gravity_lab.ephemeris.fetch_horizons_body", fake_fetch)
    result = fetch_three_body_horizons(("Sun", "Earth", "Jupiter"), "2026-10-21")
    assert result.gravitational_constant == G_AU_MSUN_YR
    assert result.names == ("Sun", "Earth", "Jupiter")
    np.testing.assert_allclose(np.sum(result.masses[:, None] * result.positions, axis=0), 0, atol=1e-12)
    np.testing.assert_allclose(np.sum(result.masses[:, None] * result.velocities, axis=0), 0, atol=1e-12)
    # Recentering does not change relative vectors.
    np.testing.assert_allclose(result.positions[1] - result.positions[0], np.array(states["Earth"].position_au) - np.array(states["Sun"].position_au))


def test_ephemeris_body_catalog_has_unique_horizons_ids():
    ids = [body["id"] for body in SOLAR_SYSTEM_BODIES.values()]
    assert len(ids) >= 8
    assert len(ids) == len(set(ids))


def test_fetch_horizons_body_constructs_barycentric_vector_query(monkeypatch):
    import json
    from urllib.parse import parse_qs, urlparse
    import gravity_lab.ephemeris as ephemeris

    sample = {
        "signature": {"source": "NASA/JPL Horizons API", "version": "1.0"},
        "result": """$$SOE\n2450000.500000000 = A.D. 1995-Oct-09 00:00:00.0000 TDB\n X = 1.0E+00 Y = 2.0E+00 Z = 3.0E+00\n VX= 1.0E-02 VY= 2.0E-02 VZ= 3.0E-02\n$$EOE\n""",
    }

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(sample).encode("utf-8")

    captured = {}
    def fake_urlopen(request, timeout=20.0):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(ephemeris, "urlopen", fake_urlopen)
    state = ephemeris.fetch_horizons_body("Earth", "2026-10-21")
    query = parse_qs(urlparse(captured["url"]).query)
    assert query["CENTER"] == ["'@0'"]
    assert query["EPHEM_TYPE"] == ["'VECTORS'"]
    assert query["VEC_TABLE"] == ["'2'"]
    assert query["OUT_UNITS"] == ["'AU-D'"]
    np.testing.assert_allclose(state.position_au, (1.0, 2.0, 3.0))
    np.testing.assert_allclose(state.velocity_au_per_year, np.array([0.01, 0.02, 0.03]) * 365.25)


def test_moon_is_available_in_jpl_horizons_catalog():
    moon = SOLAR_SYSTEM_BODIES["Moon"]
    assert moon["id"] == "301"
    assert moon["mass"] > 0
    assert 0 < moon["radius_au"] < SOLAR_SYSTEM_BODIES["Earth"]["radius_au"]
    assert moon["id"] not in {body["id"] for name, body in SOLAR_SYSTEM_BODIES.items() if name != "Moon"}


def test_fetch_moon_uses_horizons_moon_target_id(monkeypatch):
    import json
    from urllib.parse import parse_qs, urlparse
    import gravity_lab.ephemeris as ephemeris

    sample = {
        "signature": {"source": "NASA/JPL Horizons API", "version": "1.0"},
        "result": """$$SOE\n2450000.500000000 = A.D. 1995-Oct-09 00:00:00.0000 TDB\n X = 1.0E+00 Y = 2.0E+00 Z = 3.0E+00\n VX= 1.0E-02 VY= 2.0E-02 VZ= 3.0E-02\n$$EOE\n""",
    }
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(sample).encode("utf-8")
    captured = {}
    def fake_urlopen(request, timeout=20.0):
        captured["url"] = request.full_url
        return FakeResponse()
    monkeypatch.setattr(ephemeris, "urlopen", fake_urlopen)
    state = ephemeris.fetch_horizons_body("Moon", "2026-10-24")
    query = parse_qs(urlparse(captured["url"]).query)
    assert query["COMMAND"] == ["'301'"]
    assert state.name == "Moon"
    assert state.target_id == "301"
    assert state.mass_solar == SOLAR_SYSTEM_BODIES["Moon"]["mass"]
