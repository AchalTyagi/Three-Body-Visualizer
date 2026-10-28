"""Building or restyling a scene must never render: rendering needs an OpenGL context.

Headless CI runners (Linux without a display, Windows without a GPU) crash inside
``vtkRenderWindow.Render()``; keeping construction and styling render-free keeps the
geometry/state tests runnable everywhere.
"""
from unittest.mock import MagicMock

from gravity_lab.renderer_vtk import GravityScene


def test_construction_theming_and_body_colors_do_not_render():
    window = MagicMock(name="render_window")
    scene = GravityScene(window, grid_size=7)
    scene.set_theme("Light")
    scene.set_theme("Dark")
    scene.set_body_colors(("#1255aa", "#e05c31", "#52a879"))
    window.Render.assert_not_called()


def test_explicit_render_still_renders():
    window = MagicMock(name="render_window")
    scene = GravityScene(window, grid_size=7)
    scene.render()
    window.Render.assert_called_once_with()
