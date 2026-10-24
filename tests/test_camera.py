import numpy as np

from gravity_lab.camera import (MACOS_NOTCH, recentre, follow_translation,
                                wheel_zoom_factor, zoom_about_point, zoom_limits)


def _screen_offset(position, focal, anchor, parallel, scale):
    """Anchor's offset from view centre, in screen units (focal plane)."""
    u = np.asarray(anchor, float) - np.asarray(focal, float)
    if parallel:
        return u / scale
    return u / np.linalg.norm(np.asarray(position, float) - np.asarray(focal, float))


def test_wheel_factor_is_exponential_and_symmetric():
    one = wheel_zoom_factor(delta=120)
    assert np.isclose(one, 1.15)
    assert np.isclose(wheel_zoom_factor(delta=60) ** 2, one)
    assert np.isclose(wheel_zoom_factor(delta=120) * wheel_zoom_factor(delta=-120), 1.0)
    assert np.isclose(wheel_zoom_factor(direction=1), 1.15)
    assert np.isclose(wheel_zoom_factor(direction=-1), 1 / 1.15)
    assert wheel_zoom_factor() == 1.0


def test_wheel_factor_is_bounded_and_macos_scaled():
    assert wheel_zoom_factor(delta=120000) <= 1.15 ** 4 + 1e-9
    assert np.isclose(wheel_zoom_factor(delta=1, notch_size=MACOS_NOTCH), 1.15)


def test_perspective_zoom_keeps_cursor_point_fixed_on_screen():
    pos, foc, anchor = np.array([10., -12., 8.]), np.zeros(3), np.array([1.5, 0.5, 0.0])
    before = _screen_offset(pos, foc, anchor, False, 1.0)
    p2, f2, _, applied = zoom_about_point(pos, foc, anchor, 1.15, False, 1.0, extent=10.0)
    assert applied > 1.0
    assert np.allclose(_screen_offset(p2, f2, anchor, False, 1.0), before)
    # distance shrank by exactly the applied factor
    assert np.isclose(np.linalg.norm(p2 - f2), np.linalg.norm(pos - foc) / applied)


def test_parallel_zoom_changes_scale_and_keeps_cursor_fixed():
    # Regression: Dolly() is a no-op in parallel projection, so 2D zoom did nothing.
    pos, foc, anchor = np.array([0., 0., 80.]), np.zeros(3), np.array([2.0, -1.0, 0.0])
    before = _screen_offset(pos, foc, anchor, True, 10.5)
    p2, f2, scale, applied = zoom_about_point(pos, foc, anchor, 1.15, True, 10.5, extent=10.0)
    assert np.isclose(scale, 10.5 / 1.15)
    assert np.allclose(_screen_offset(p2, f2, anchor, True, scale), before)
    assert np.isclose(p2[2], 80.0)  # camera height unchanged in parallel mode


def test_zoom_in_then_out_round_trips():
    pos, foc, anchor = np.array([10., -12., 8.]), np.zeros(3), np.array([3.0, 1.0, 0.0])
    p, f, s, _ = zoom_about_point(pos, foc, anchor, 1.3, False, 1.0, extent=10.0)
    p, f, s, _ = zoom_about_point(p, f, anchor, 1 / 1.3, False, s, extent=10.0)
    assert np.allclose(p, pos) and np.allclose(f, foc)


def test_zoom_clamps_and_does_not_drift_at_limit():
    min_d, max_d, min_s, max_s = zoom_limits(10.0)
    foc, anchor = np.zeros(3), np.array([4.0, 0.0, 0.0])
    # already at the closest allowed distance: zooming in further is a no-op
    pos = np.array([0.0, -min_d, 0.0])
    p2, f2, _, applied = zoom_about_point(pos, foc, anchor, 1.15, False, 1.0, extent=10.0)
    assert applied == 1.0 and np.allclose(p2, pos) and np.allclose(f2, foc)
    # a huge zoom-out stops at the maximum distance
    pos = np.array([0.0, -(max_d * 0.99), 0.0])
    p3, f3, _, applied = zoom_about_point(pos, foc, anchor, 1 / 5.0, False, 1.0, extent=10.0)
    assert np.isclose(np.linalg.norm(p3 - f3), max_d)
    assert 0.2 < applied < 1.0
    # parallel scale clamps too
    _, _, scale, _ = zoom_about_point(np.array([0, 0, 80.]), foc, anchor, 1e9, True, 10.0, extent=10.0)
    assert np.isclose(scale, min_s)


def test_invalid_input_is_ignored():
    pos, foc = np.array([1., 2., 3.]), np.zeros(3)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        p, f, _, applied = zoom_about_point(pos, foc, foc, bad, False, 1.0, extent=5.0)
        assert applied == 1.0 and np.allclose(p, pos)
    p, f, _, applied = zoom_about_point(pos, foc, np.array([np.nan, 0, 0]), 1.2, False, 1.0, extent=5.0)
    assert applied == 1.0


def test_recentre_removes_pan_but_keeps_view_vector():
    pos, foc, target = np.array([5., 5., 5.]), np.array([1., 0., 0.]), np.array([3., 3., 3.])
    p, f = recentre(pos, foc, target)
    assert np.allclose(f, target)
    assert np.allclose(p - f, pos - foc)


def test_follow_translation_snaps_first_then_tracks_displacement():
    focal = np.array([1.0, 1.0, 0.0])
    assert np.allclose(follow_translation([4, 1, 0], None, focal), [3, 0, 0])
    assert np.allclose(follow_translation([5, 2, 0], np.array([4., 1., 0.]), focal), [1, 1, 0])
    assert np.allclose(follow_translation([np.nan, 0, 0], None, focal), 0.0)
