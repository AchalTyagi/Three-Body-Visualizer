import numpy as np
import vtk

from gravity_lab.renderer_vtk import ray_plane_intersection
from gravity_lab.gui import GravityLabApp


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


class _FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeInteractor:
    def __init__(self, position=(321, 123)):
        self.position = position

    def GetEventPosition(self):
        return self.position


def test_native_vtk_press_uses_interactor_coordinates_for_body_pick():
    """Regression: the embedded native render window may bypass Tk canvas events."""
    app = object.__new__(GravityLabApp)
    app.move_bodies_var = _FakeVar(True)
    app.vtk_interactor = _FakeInteractor((321, 123))
    seen = []
    app._begin_body_drag_at_display = lambda x, y: seen.append((x, y))

    app._on_interactor_left_press(None, "LeftButtonPressEvent")

    assert seen == [(321.0, 123.0)]


def test_native_vtk_motion_and_release_forward_to_drag_handlers():
    app = object.__new__(GravityLabApp)
    app.move_bodies_var = _FakeVar(True)
    app.vtk_interactor = _FakeInteractor((260, 170))
    app._body_drag_state = {"index": 0}
    moved, released = [], []
    app._move_dragged_body_to_display = lambda x, y: moved.append((x, y))
    app._finish_body_drag_at_display = lambda x, y: released.append((x, y))

    app._on_interactor_mouse_move(None, "MouseMoveEvent")
    app._on_interactor_left_release(None, "LeftButtonReleaseEvent")

    assert moved == [(260.0, 170.0)]
    assert released == [(260.0, 170.0)]


def test_placement_mode_uses_user_interactor_style_to_prevent_camera_rotation():
    app = object.__new__(GravityLabApp)
    app.vtk_interactor = vtk.vtkRenderWindowInteractor()
    app.scene = type("SceneStub", (), {"renderer": vtk.vtkRenderer()})()

    app._set_viewport_interaction_style(True)
    assert isinstance(app.vtk_interactor.GetInteractorStyle(), vtk.vtkInteractorStyleUser)

    app._set_viewport_interaction_style(False)
    assert isinstance(app.vtk_interactor.GetInteractorStyle(), vtk.vtkInteractorStyleTrackballCamera)
