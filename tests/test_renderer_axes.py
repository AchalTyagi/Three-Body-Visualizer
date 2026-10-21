import numpy as np
import vtk

from gravity_lab.renderer_vtk import GravityScene


def test_rgb_axes_cross_origin_and_show_both_signs():
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    scene = GravityScene(window, grid_size=7)
    scene.set_axis_extent(12.0)
    expected_colors = ((1.0, 69 / 255, 69 / 255), (56 / 255, 232 / 255, 107 / 255), (67 / 255, 139 / 255, 1.0))
    for i, poly in enumerate(scene.axis_polys):
        points = poly.GetPoints()
        coords = np.array([points.GetPoint(j) for j in range(points.GetNumberOfPoints())])
        assert np.any(coords < 0) and np.any(coords > 0)
        assert np.any(np.all(np.isclose(coords, [0, 0, 0]), axis=1))
        np.testing.assert_allclose(scene.axis_actors[i].GetProperty().GetColor(), expected_colors[i], atol=1e-12)
        assert scene.axis_labels[i][0][1].GetInput().startswith("−")
        assert scene.axis_labels[i][1][1].GetInput().startswith("+")
    assert scene.axis_extent == 12.0
    assert scene.axis_tick_values
    assert any(value < 0 for value in scene.axis_tick_values)
    assert any(value > 0 for value in scene.axis_tick_values)
    # There is no competing gray outer-edge cube axis; every coordinate label
    # belongs to one of the colored world axes.
    assert not hasattr(scene, "cube_axes")
    assert len(scene.axis_tick_label_actors) == 3 * len(scene.axis_tick_values)
    window.Finalize()


def test_2d_mode_hides_z_axis_and_3d_restores_it():
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    scene = GravityScene(window, grid_size=7)
    scene.set_view_mode("2D")
    assert scene.view_mode == "2D"
    assert scene.renderer.GetActiveCamera().GetParallelProjection() == 1
    assert scene.axis_actors[0].GetVisibility() == 1
    assert scene.axis_actors[1].GetVisibility() == 1
    assert scene.axis_actors[2].GetVisibility() == 0
    scene.set_view_mode("3D")
    assert scene.renderer.GetActiveCamera().GetParallelProjection() == 0
    assert scene.axis_actors[2].GetVisibility() == 1
    window.Finalize()


def test_dark_and_light_themes_are_available():
    from gravity_lab.themes import THEMES
    assert "Dark" in THEMES and "Light" in THEMES
    for name in ("Dark", "Light"):
        for key in ("app_bg", "panel_bg", "plot_bg", "text", "muted", "accent", "field_stops"):
            assert key in THEMES[name]
