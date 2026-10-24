"""Headless renderer checks for per-body visual size and 2D/3D camera panning.

These need VTK (offscreen) but not Tk.
"""
import numpy as np
import vtk

from gravity_lab.application import state_from_preset
from gravity_lab.body_size import SIZE_FIXED, SIZE_MULTIPLIER, SIZE_TRUE, display_radius
from gravity_lab.camera import pan_translation
from gravity_lab.presets import PRESETS
from gravity_lab.renderer_vtk import GravityScene
from gravity_lab.service import SimulationService


def _scene_and_frame():
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    service = SimulationService()
    service.reset(state_from_preset(next(iter(PRESETS))))
    frame = service.render_frame()
    scene = GravityScene(window, grid_size=7)
    scene.reset_trails(frame.pos, 10)
    scene.fit_camera(frame, view_halfwidth=8.0)
    return window, scene, frame


def _span(scene, frame):
    live = frame.pos[frame.alive]
    return max(scene.view_halfwidth, float(np.max(np.abs(live))) if len(live) else 1.0, 1.0)


def test_actor_scale_follows_each_bodys_size_mode():
    window, scene, frame = _scene_and_frame()
    sizes = [(SIZE_TRUE, 1.0), (SIZE_MULTIPLIER, 4.0), (SIZE_FIXED, 0.37)]
    scene.set_body_sizes(sizes)
    scene.update(frame, force_field=False)
    span = _span(scene, frame)
    for i, (mode, value) in enumerate(sizes):
        expected = display_radius(float(frame.R[i]), mode, value, scene.display_scale, span)
        assert np.allclose(scene.body_actors[i].GetScale(), expected, rtol=1e-9)
    window.Finalize()


def test_changing_size_does_not_move_bodies_or_change_physics_arrays():
    window, scene, frame = _scene_and_frame()
    radii, positions = frame.R.copy(), frame.pos.copy()
    scene.set_body_sizes([(SIZE_FIXED, 2.0)] * 3)
    scene.update(frame, force_field=False)
    assert np.array_equal(frame.R, radii) and np.array_equal(frame.pos, positions)
    window.Finalize()


def test_fit_camera_accounts_for_large_fixed_bodies():
    window, scene, frame = _scene_and_frame()
    before = scene.view_halfwidth
    scene.set_body_sizes([(SIZE_FIXED, before * 3.0)] * 3)
    scene.fit_camera(frame, view_halfwidth=before)
    assert scene.view_halfwidth > before
    window.Finalize()


def test_2d_pan_keeps_plane_orientation():
    window, scene, frame = _scene_and_frame()
    scene.set_view_mode("2D")
    camera = scene.renderer.GetActiveCamera()
    up0, dop0, scale0 = camera.GetViewUp(), camera.GetDirectionOfProjection(), camera.GetParallelScale()
    t = pan_translation(80, -30, 600, camera.GetPosition(), camera.GetFocalPoint(), camera.GetViewUp(),
                        True, camera.GetParallelScale(), camera.GetViewAngle())
    camera.SetPosition(*(np.asarray(camera.GetPosition()) + t))
    camera.SetFocalPoint(*(np.asarray(camera.GetFocalPoint()) + t))
    assert np.allclose(camera.GetViewUp(), up0) and np.allclose(camera.GetDirectionOfProjection(), dop0)
    assert camera.GetParallelScale() == scale0 and abs(t[2]) < 1e-12
    window.Finalize()
