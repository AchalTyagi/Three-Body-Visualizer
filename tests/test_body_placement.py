import numpy as np

from gravity_lab.renderer_vtk import ray_plane_intersection


def test_ray_plane_intersection_hits_target_plane():
    point = ray_plane_intersection(
        ray_origin=(0, 0, 10),
        ray_direction=(1, 2, -2),
        plane_origin=(0, 0, 0),
        plane_normal=(0, 0, 1),
    )
    np.testing.assert_allclose(point, (5, 10, 0), atol=1e-12)


def test_ray_plane_intersection_supports_camera_facing_oblique_plane():
    point = ray_plane_intersection(
        ray_origin=(0, 0, 0),
        ray_direction=(1, 0, 2),
        plane_origin=(0, 0, 3),
        plane_normal=(1, 0, -1),
    )
    assert point is not None
    # The returned point lies on the ray and on the plane.
    np.testing.assert_allclose(np.cross(point, (1, 0, 2)), (0, 0, 0), atol=1e-12)
    assert abs(float(np.dot(point - np.array((0, 0, 3)), np.array((1, 0, -1))))) < 1e-12


def test_ray_parallel_to_plane_returns_none():
    assert ray_plane_intersection(
        ray_origin=(0, 0, 1),
        ray_direction=(1, 0, 0),
        plane_origin=(0, 0, 0),
        plane_normal=(0, 0, 1),
    ) is None


def test_invalid_plane_normal_returns_none():
    assert ray_plane_intersection((0, 0, 0), (1, 0, 0), (0, 0, 0), (0, 0, 0)) is None
