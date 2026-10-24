import numpy as np

from gravity_lab.orbital_analysis import barycentric_frame, pairwise_relative_metrics


def test_barycentric_frame_centers_position_and_velocity_of_live_mass():
    pos = np.array([[0., 0., 0.], [2., 0., 0.], [10., 0., 0.]])
    vel = np.array([[0., 0., 0.], [4., 0., 0.], [99., 0., 0.]])
    masses = np.array([3., 1., 100.])
    alive = np.array([True, True, False])
    acc = np.array([[1., 0., 0.], [-3., 0., 0.], [20., 0., 0.]])
    p, v, a = barycentric_frame(pos, vel, masses, alive, acc)
    assert np.allclose((masses[alive, None] * p[alive]).sum(axis=0), 0.0)
    assert np.allclose((masses[alive, None] * v[alive]).sum(axis=0), 0.0)
    assert np.allclose((masses[alive, None] * a[alive]).sum(axis=0), 0.0)
    assert np.allclose(p[2], [9.5, 0, 0])


def test_barycentric_frame_empty_live_mass_is_safe():
    pos = np.arange(9, dtype=float).reshape(3, 3)
    vel = pos + 1
    p, v, a = barycentric_frame(pos, vel, np.zeros(3), np.zeros(3, dtype=bool), np.ones((3, 3)))
    assert np.allclose(p, pos)
    assert np.allclose(v, vel)
    assert np.allclose(a, 1)


def test_pairwise_metrics_return_distance_and_relative_speed_for_live_pairs():
    pos = np.array([[0., 0., 0.], [3., 4., 0.], [100., 0., 0.]])
    vel = np.array([[1., 0., 0.], [1., 12., 0.], [0., 0., 0.]])
    metrics = pairwise_relative_metrics(pos, vel, [True, True, False])
    assert list(metrics) == [(0, 1)]
    assert np.isclose(metrics[(0, 1)][0], 5.0)
    assert np.isclose(metrics[(0, 1)][1], 12.0)
