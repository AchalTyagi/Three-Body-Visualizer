import json

import pytest

from gravity_lab.body_size import (SIZE_FIXED, SIZE_MODES, SIZE_MULTIPLIER, SIZE_TRUE, default_sizes,
                                   display_radius, normalise_sizes, overlap_warnings, sizes_to_payload,
                                   validate_size)
from gravity_lab.application import state_from_preset
from gravity_lab.service import SimulationService
from gravity_lab.setup_io import validate_setup_payload
from gravity_lab.state import BodyState, SimulationState

SPAN = 10.0
FLOOR = SPAN * 0.008


def test_true_scale_uses_physical_radius_and_global_scale():
    assert display_radius(0.5, SIZE_TRUE, 99.0, 2.0, SPAN) == pytest.approx(1.0)   # value ignored


def test_multiplier_scales_true_size():
    assert display_radius(0.5, SIZE_MULTIPLIER, 3.0, 2.0, SPAN) == pytest.approx(3.0)


def test_fixed_ignores_physics_and_global_scale():
    assert display_radius(0.001, SIZE_FIXED, 0.7, 24.0, SPAN) == pytest.approx(0.7)
    assert display_radius(500.0, SIZE_FIXED, 0.7, 0.5, SPAN) == pytest.approx(0.7)


def test_tiny_bodies_stay_visible():
    assert display_radius(1e-9, SIZE_TRUE, 1.0, 1.8, SPAN) == pytest.approx(FLOOR)
    assert display_radius(1.0, SIZE_FIXED, 1e-9, 1.8, SPAN) == pytest.approx(FLOOR)


def test_render_loop_helper_never_raises_on_bad_input():
    for bad in (float("nan"), float("inf"), -1.0, 0.0, None, "x"):
        r = display_radius(0.5, SIZE_MULTIPLIER, bad, 1.0, SPAN)
        assert r >= FLOOR and r == r
    assert display_radius(0.5, "nonsense", 2.0, 1.0, SPAN) == pytest.approx(0.5)
    assert display_radius(float("nan"), SIZE_TRUE, 1.0, 1.0, SPAN) == pytest.approx(FLOOR)


def test_validate_size_accepts_and_rejects():
    assert validate_size(SIZE_FIXED, "0.25") == (SIZE_FIXED, 0.25)
    for mode, value in (("Huge", 1.0), (SIZE_FIXED, 0), (SIZE_FIXED, -2), (SIZE_FIXED, float("nan")),
                        (SIZE_FIXED, "abc"), (SIZE_FIXED, True), (SIZE_FIXED, 1e12)):
        with pytest.raises(ValueError):
            validate_size(mode, value)


def test_normalise_sizes_defaults_and_forms():
    assert normalise_sizes(None) == default_sizes(3)
    assert normalise_sizes([]) == default_sizes(3)
    got = normalise_sizes([(SIZE_TRUE, 1), {"mode": SIZE_FIXED, "value": 0.2}, [SIZE_MULTIPLIER, 4]])
    assert got == [(SIZE_TRUE, 1.0), (SIZE_FIXED, 0.2), (SIZE_MULTIPLIER, 4.0)]
    with pytest.raises(ValueError):
        normalise_sizes([(SIZE_TRUE, 1)])                     # wrong count
    with pytest.raises(ValueError):
        normalise_sizes([(SIZE_TRUE, 1), (SIZE_TRUE, 1), ("bad", 1)])
    assert json.dumps(sizes_to_payload(got))                  # JSON-serialisable


def _body(**kw):
    base = dict(name="A", mass=1.0, radius=0.1, position=(0, 0, 0), velocity=(0, 0, 0))
    base.update(kw)
    return BodyState(**base)


def test_body_state_defaults_and_validation():
    b = _body()
    assert (b.size_mode, b.size_value) == (SIZE_TRUE, 1.0)
    assert _body(size_mode=SIZE_FIXED, size_value=0.3).size_value == 0.3
    with pytest.raises(ValueError):
        _body(size_mode="Giant")
    with pytest.raises(ValueError):
        _body(size_mode=SIZE_FIXED, size_value=-1)


def test_state_mapping_round_trip_and_old_checkpoint_compat():
    state = state_from_preset(next(iter(__import__("gravity_lab.presets", fromlist=["PRESETS"]).PRESETS)))
    bodies = list(state.bodies)
    bodies[1] = BodyState(**{**{f: getattr(bodies[1], f) for f in bodies[1].__slots__},
                             "size_mode": SIZE_MULTIPLIER, "size_value": 5.0})
    state = SimulationState(tuple(bodies), state.current_time, state.integrator, state.physics)
    mapping = state.to_mapping()
    assert mapping["bodies"][1]["size_mode"] == SIZE_MULTIPLIER
    assert SimulationState.from_mapping(mapping).bodies[1].size_value == 5.0
    for item in mapping["bodies"]:                          # a checkpoint written before this feature
        item.pop("size_mode"); item.pop("size_value")
    old = SimulationState.from_mapping(mapping)
    assert all((b.size_mode, b.size_value) == (SIZE_TRUE, 1.0) for b in old.bodies)


def test_service_updates_sizes_without_touching_engine():
    from gravity_lab.presets import PRESETS
    service = SimulationService()
    service.reset(state_from_preset(next(iter(PRESETS))))
    before = service.engine.pos.copy(), service.engine.t
    service.set_body_sizes([(SIZE_FIXED, 0.4), (SIZE_TRUE, 1.0), (SIZE_MULTIPLIER, 2.0)])
    assert [(b.size_mode, b.size_value) for b in service.state.bodies] == \
        [(SIZE_FIXED, 0.4), (SIZE_TRUE, 1.0), (SIZE_MULTIPLIER, 2.0)]
    assert (service.engine.pos == before[0]).all() and service.engine.t == before[1]
    service.advance(0.01) if hasattr(service, "advance") else None
    assert service.state.bodies[0].size_mode == SIZE_FIXED  # preserved across state re-sync


def _setup_payload(**extra):
    return {"format": "gravity-lab-3d-setup", "schema_version": 1, "bodies": [[1] * 8] * 3, **extra}


def test_setup_file_sizes_are_optional_and_validated():
    validate_setup_payload(_setup_payload())                                    # old file, no key
    validate_setup_payload(_setup_payload(body_sizes=sizes_to_payload(default_sizes())))
    with pytest.raises(ValueError):
        validate_setup_payload(_setup_payload(body_sizes=[{"mode": "Nope", "value": 1}] * 3))
    with pytest.raises(ValueError):
        validate_setup_payload(_setup_payload(body_sizes=[{"mode": SIZE_TRUE, "value": 1}]))
    with pytest.raises(ValueError):
        validate_setup_payload(_setup_payload(body_sizes="big"))


def test_overlap_warnings():
    names = ["A", "B", "C"]
    pos = [(0, 0, 0), (1, 0, 0), (10, 0, 0)]
    assert overlap_warnings(names, [0.2, 0.2, 0.2], pos) == []
    w = overlap_warnings(names, [0.6, 0.6, 0.2], pos)
    assert len(w) == 1 and "A and B" in w[0]
    assert overlap_warnings(names, [0.6, 0.6, 0.2], pos, active=[True, False, True]) == []
