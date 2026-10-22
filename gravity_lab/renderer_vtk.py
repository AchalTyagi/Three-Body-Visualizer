"""VTK-powered real-time 3D rendering, field slice, trails, and diagnostics.

VTK keeps the geometry on the rendering side: per-frame updates modify actor
transforms and line point buffers instead of rebuilding a Matplotlib 3D scene.
"""
from __future__ import annotations
import math
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

from .fields import field_magnitude_grid
from .themes import THEMES, BODY_COLORS
from .physics import ZONE_THRESH, ZONE_ROCHE


def _hex_rgb(hex_color):
    value = hex_color.lstrip("#")
    return tuple(int(value[k:k+2], 16) / 255.0 for k in (0, 2, 4))


def _build_lut(stops, count=256):
    colors = [_hex_rgb(c) for c in stops]
    lut = vtk.vtkLookupTable()
    lut.SetNumberOfTableValues(count)
    lut.SetRange(0.0, 1.0)
    for i in range(count):
        x = i / max(1, count - 1) * (len(colors) - 1)
        lo = int(x)
        hi = min(lo + 1, len(colors) - 1)
        t = x - lo
        c = tuple(colors[lo][j] * (1 - t) + colors[hi][j] * t for j in range(3))
        lut.SetTableValue(i, *c, 1.0)
    lut.Build()
    return lut


def _make_polyline_actor(color, width=1.5, opacity=0.8, dashed=False):
    points = vtk.vtkPoints()
    poly = vtk.vtkPolyData()
    poly.SetPoints(points)
    lines = vtk.vtkCellArray()
    poly.SetLines(lines)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(poly)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*_hex_rgb(color))
    actor.GetProperty().SetLineWidth(width)
    actor.GetProperty().SetOpacity(opacity)
    if dashed:
        actor.GetProperty().SetLineStipplePattern(0x00FF)
        actor.GetProperty().SetLineStippleRepeatFactor(2)
    return actor, poly


def _set_polyline(poly, coords):
    coords = np.asarray(coords, dtype=float).reshape(-1, 3)
    points = vtk.vtkPoints()
    if len(coords):
        arr = numpy_to_vtk(np.ascontiguousarray(coords), deep=True)
        arr.SetNumberOfComponents(3)
        points.SetData(arr)
    poly.SetPoints(points)
    lines = vtk.vtkCellArray()
    if len(coords) >= 2:
        # Bulk-fill the polyline connectivity instead of calling InsertCellPoint
        # thousands of times on each frame; this matters once trails get long.
        offsets = numpy_to_vtkIdTypeArray(np.asarray([0, len(coords)], dtype=np.int64), deep=True)
        connectivity = numpy_to_vtkIdTypeArray(np.arange(len(coords), dtype=np.int64), deep=True)
        lines.SetData(offsets, connectivity)
    poly.SetLines(lines)
    poly.Modified()


def _set_segments(poly, segments):
    """Set a polydata object to independent line segments (used for axis ticks)."""
    segments = np.asarray(segments, dtype=float).reshape(-1, 2, 3)
    points_array = segments.reshape(-1, 3)
    points = vtk.vtkPoints()
    if len(points_array):
        arr = numpy_to_vtk(np.ascontiguousarray(points_array), deep=True)
        arr.SetNumberOfComponents(3)
        points.SetData(arr)
    lines = vtk.vtkCellArray()
    if len(points_array):
        offsets = numpy_to_vtkIdTypeArray(np.arange(0, len(points_array) + 1, 2, dtype=np.int64), deep=True)
        connectivity = numpy_to_vtkIdTypeArray(np.arange(len(points_array), dtype=np.int64), deep=True)
        lines.SetData(offsets, connectivity)
    poly.SetPoints(points)
    poly.SetLines(lines)
    poly.Modified()


def _nice_tick_step(extent):
    """Readable 1-2-5 tick spacing for the current symmetric world extent."""
    raw = max(float(extent) / 5.0, 1e-6)
    power = 10.0 ** math.floor(math.log10(raw))
    fraction = raw / power
    nice = 1.0 if fraction <= 1.0 else 2.0 if fraction <= 2.0 else 5.0 if fraction <= 5.0 else 10.0
    return nice * power


class GravityScene:
    def __init__(self, render_window=None, theme="Dark", grid_size=53):
        self.render_window = render_window or vtk.vtkRenderWindow()
        self.owns_window = render_window is None
        self.renderer = vtk.vtkRenderer()
        self.render_window.AddRenderer(self.renderer)
        self.render_window.SetMultiSamples(4)
        self.render_window.SetAlphaBitPlanes(1)
        self.grid_size = int(grid_size)
        self.theme_name = theme
        self.theme = THEMES[theme]
        self.display_scale = 1.8
        self.view_mode = "3D"
        self.show_shells = True
        self.show_field = True
        self.show_trails = True
        self.show_floor = True
        self.show_acceleration = False
        self.zone_mode = ZONE_THRESH
        self.threshold = 0.2
        self.view_halfwidth = 8.0
        self._field_update_counter = 0
        self._frame_counter = 0
        self._history = [[], [], []]
        self.body_colors = list(BODY_COLORS)
        self.max_trails = 1200
        self._field_extent = 8.0
        self._field_z = 0.0
        self._make_axes()
        self._make_body_actors()
        self._make_zones()
        self._make_trails()
        self._make_acceleration_vectors()
        self._make_field_map()
        self._make_ground_grid()
        self.set_theme(theme)

    def _make_axes(self):
        """Draw world-fixed RGB axes through the origin with visible +/- ticks.

        No outer cube-axis actor is used: that actor draws a second coordinate
        frame on the box edges and can make the true world axes confusing.
        These lines, tick marks, labels, and extents are all in world coordinates.
        """
        self.axis_extent = 1.0
        self.axis_colors = ("#ff4545", "#38e86b", "#438bff")  # X red, Y green, Z blue
        self.axis_names = ("X", "Y", "Z")
        self.axis_actors, self.axis_polys, self.axis_labels = [], [], []
        self.axis_tick_actors, self.axis_tick_polys = [], []
        self.axis_tick_label_actors = []
        self.axis_tick_label_groups = [[], [], []]

        for axis_index, (name, color) in enumerate(zip(self.axis_names, self.axis_colors)):
            actor, poly = _make_polyline_actor(color, width=3.6, opacity=1.0)
            actor.GetProperty().SetLighting(False)
            actor.GetProperty().SetRenderLinesAsTubes(True)
            self.renderer.AddActor(actor)
            self.axis_actors.append(actor)
            self.axis_polys.append(poly)

            tick_actor, tick_poly = _make_polyline_actor(color, width=1.5, opacity=0.95)
            tick_actor.GetProperty().SetLighting(False)
            self.renderer.AddActor(tick_actor)
            self.axis_tick_actors.append(tick_actor)
            self.axis_tick_polys.append(tick_poly)

            ends = []
            for sign, text in ((-1, f"−{name}"), (1, f"+{name}")):
                label = vtk.vtkBillboardTextActor3D()
                label.SetInput(text)
                prop = label.GetTextProperty()
                prop.SetColor(*_hex_rgb(color))
                prop.SetFontSize(19)
                prop.SetBold(True)
                prop.SetShadow(True)
                prop.SetJustificationToCentered()
                prop.SetVerticalJustificationToCentered()
                self.renderer.AddActor(label)
                ends.append((sign, label))
            self.axis_labels.append(ends)

        self.axis_tick_step = 1.0
        self.axis_tick_values = ()
        self.set_axis_extent(1.0)

    def _new_axis_text(self, text, color, font_size=11, bold=False):
        actor = vtk.vtkBillboardTextActor3D()
        actor.SetInput(text)
        prop = actor.GetTextProperty()
        prop.SetColor(*_hex_rgb(color))
        prop.SetFontSize(font_size)
        prop.SetBold(bold)
        prop.SetShadow(True)
        prop.SetJustificationToCentered()
        prop.SetVerticalJustificationToCentered()
        self.renderer.AddActor(actor)
        return actor

    def set_axis_extent(self, extent):
        """Set symmetric RGB axes and numeric tick labels in world coordinates."""
        extent = max(float(extent), 0.5)
        self.axis_extent = extent
        inner = extent * 0.90
        end_label_at = extent * 0.96
        coords = (
            np.array([[-inner, 0.0, 0.0], [0.0, 0.0, 0.0], [inner, 0.0, 0.0]], dtype=float),
            np.array([[0.0, -inner, 0.0], [0.0, 0.0, 0.0], [0.0, inner, 0.0]], dtype=float),
            np.array([[0.0, 0.0, -inner], [0.0, 0.0, 0.0], [0.0, 0.0, inner]], dtype=float),
        )
        label_positions = (
            ((-end_label_at, 0.0, 0.0), (end_label_at, 0.0, 0.0)),
            ((0.0, -end_label_at, 0.0), (0.0, end_label_at, 0.0)),
            ((0.0, 0.0, -end_label_at), (0.0, 0.0, end_label_at)),
        )
        for poly, points, labels, pos_pair in zip(self.axis_polys, coords, self.axis_labels, label_positions):
            _set_polyline(poly, points)
            for (_, actor), position in zip(labels, pos_pair):
                actor.SetPosition(*position)

        # Recreate number labels only when the camera/world extent is reframed.
        for actor in self.axis_tick_label_actors:
            self.renderer.RemoveActor(actor)
        self.axis_tick_label_actors = []
        self.axis_tick_label_groups = [[], [], []]
        tick_step = _nice_tick_step(extent)
        self.axis_tick_step = tick_step
        max_index = int(math.floor(inner / tick_step + 1e-9))
        tick_values = [float(k * tick_step) for k in range(-max_index, max_index + 1) if k != 0]
        self.axis_tick_values = tuple(tick_values)
        tick_half = max(extent * 0.012, 0.012)
        label_offset = tick_half * 2.5

        tick_segments = [[], [], []]
        for value in tick_values:
            # X ticks run along the X axis and extend in Y.
            tick_segments[0].append(((value, -tick_half, 0.0), (value, tick_half, 0.0)))
            # Y ticks run along Y and extend in X.
            tick_segments[1].append(((-tick_half, value, 0.0), (tick_half, value, 0.0)))
            # Z ticks run along Z and extend in X for readability in 3D.
            tick_segments[2].append(((-tick_half, 0.0, value), (tick_half, 0.0, value)))

            rendered = f"{value:g}".replace("-", "−")
            positions = ((value, -label_offset, 0.0), (label_offset, value, 0.0),
                         (label_offset, 0.0, value))
            for i, position in enumerate(positions):
                actor = self._new_axis_text(rendered, self.axis_colors[i], font_size=13)
                actor.SetPosition(*position)
                self.axis_tick_label_actors.append(actor)
                self.axis_tick_label_groups[i].append(actor)

        self._apply_axis_view_visibility()
        for poly, segments in zip(self.axis_tick_polys, tick_segments):
            _set_segments(poly, segments)
        self.renderer.ResetCameraClippingRange()

    def _apply_axis_view_visibility(self):
        """Hide Z-axis graphics in top-down 2D mode while retaining world axes in 3D."""
        is_3d = self.view_mode == "3D"
        if hasattr(self, "axis_actors"):
            self.axis_actors[2].SetVisibility(is_3d)
            self.axis_tick_actors[2].SetVisibility(is_3d)
            for _sign, label in self.axis_labels[2]:
                label.SetVisibility(is_3d)
            for actor in self.axis_tick_label_groups[2]:
                actor.SetVisibility(is_3d)

    def set_view_mode(self, mode: str):
        """Switch between a perspective 3D camera and an orthographic XY view."""
        normalized = str(mode).strip().upper()
        if normalized not in ("2D", "3D"):
            raise ValueError("View mode must be '2D' or '3D'.")
        self.view_mode = normalized
        camera = self.renderer.GetActiveCamera()
        extent = max(float(self.view_halfwidth), 0.5)
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetClippingRange(0.001, max(extent * 1000.0, 100.0))
        if normalized == "2D":
            camera.ParallelProjectionOn()
            camera.SetPosition(0.0, 0.0, 8.0 * extent)
            camera.SetViewUp(0.0, 1.0, 0.0)
            camera.SetParallelScale(extent * 1.05)
        else:
            camera.ParallelProjectionOff()
            camera.SetPosition(2.9 * extent, -3.4 * extent, 2.5 * extent)
            camera.SetViewUp(0.0, 0.0, 1.0)
        self._apply_axis_view_visibility()
        self.renderer.ResetCameraClippingRange()

    def _make_body_actors(self):
        self.body_sources, self.body_actors = [], []
        self.body_glow_actors = []
        self.body_spin_transforms = []
        self.spin_marker_sources, self.spin_marker_actors = [], []
        for color in self.body_colors:
            src = vtk.vtkSphereSource()
            src.SetRadius(1.0)
            src.SetThetaResolution(28)
            src.SetPhiResolution(22)
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(src.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            prop = actor.GetProperty()
            prop.SetColor(*_hex_rgb(color))
            prop.SetInterpolationToPhong()
            prop.SetSpecular(0.35)
            prop.SetSpecularPower(28)
            prop.SetAmbient(0.18)
            prop.SetDiffuse(0.82)
            self.renderer.AddActor(actor)
            self.body_sources.append(src)
            self.body_actors.append(actor)
            self.body_spin_transforms.append(vtk.vtkTransform())
            # A faint translucent halo gives the bodies a stronger visual anchor.
            halo_src = vtk.vtkSphereSource()
            halo_src.SetRadius(1.0)
            halo_src.SetThetaResolution(16)
            halo_src.SetPhiResolution(12)
            halo_mapper = vtk.vtkPolyDataMapper()
            halo_mapper.SetInputConnection(halo_src.GetOutputPort())
            halo = vtk.vtkActor()
            halo.SetMapper(halo_mapper)
            halo.GetProperty().SetColor(*_hex_rgb(color))
            halo.GetProperty().SetOpacity(0.10)
            halo.GetProperty().SetRepresentationToWireframe()
            self.renderer.AddActor(halo)
            self.body_glow_actors.append(halo)
            # A tiny white equatorial marker makes body spin rate visible even
            # when the oblate body itself is visually symmetric around its axis.
            marker_src = vtk.vtkSphereSource()
            marker_src.SetRadius(1.0)
            marker_src.SetThetaResolution(12)
            marker_src.SetPhiResolution(10)
            marker_mapper = vtk.vtkPolyDataMapper()
            marker_mapper.SetInputConnection(marker_src.GetOutputPort())
            marker_actor = vtk.vtkActor()
            marker_actor.SetMapper(marker_mapper)
            marker_actor.GetProperty().SetColor(0.96, 0.97, 1.0)
            marker_actor.GetProperty().SetLighting(False)
            self.renderer.AddActor(marker_actor)
            self.spin_marker_sources.append(marker_src)
            self.spin_marker_actors.append(marker_actor)

    def _make_zones(self):
        self.zone_sources, self.zone_actors = [], []
        for color in self.body_colors:
            src = vtk.vtkSphereSource()
            src.SetRadius(1.0)
            src.SetThetaResolution(26)
            src.SetPhiResolution(18)
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(src.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*_hex_rgb(color))
            actor.GetProperty().SetRepresentationToWireframe()
            actor.GetProperty().SetOpacity(0.32)
            actor.GetProperty().SetLineWidth(1.0)
            self.renderer.AddActor(actor)
            self.zone_sources.append(src)
            self.zone_actors.append(actor)

    def _make_trails(self):
        self.trail_actors, self.trail_polys = [], []
        self.floor_actors, self.floor_polys = [], []
        for i, color in enumerate(self.body_colors):
            actor, poly = _make_polyline_actor(color, width=1.8, opacity=0.88)
            self.renderer.AddActor(actor)
            self.trail_actors.append(actor)
            self.trail_polys.append(poly)
            floor, floor_poly = _make_polyline_actor(color, width=1.1, opacity=0.28)
            self.renderer.AddActor(floor)
            self.floor_actors.append(floor)
            self.floor_polys.append(floor_poly)

    def _make_acceleration_vectors(self):
        self.acc_actors, self.acc_polys = [], []
        for color in self.body_colors:
            actor, poly = _make_polyline_actor(color, width=3.0, opacity=0.95)
            self.renderer.AddActor(actor)
            self.acc_actors.append(actor)
            self.acc_polys.append(poly)

    def _make_field_map(self):
        self.field_poly = vtk.vtkPolyData()
        self.field_points = vtk.vtkPoints()
        self.field_poly.SetPoints(self.field_points)
        cells = vtk.vtkCellArray()
        n = self.grid_size
        for j in range(n - 1):
            for i in range(n - 1):
                p = j * n + i
                cells.InsertNextCell(4)
                cells.InsertCellPoint(p)
                cells.InsertCellPoint(p + 1)
                cells.InsertCellPoint(p + n + 1)
                cells.InsertCellPoint(p + n)
        self.field_poly.SetPolys(cells)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self.field_poly)
        mapper.SetLookupTable(_build_lut(self.theme["field_stops"]))
        mapper.SetScalarRange(-4, 2)
        mapper.SetScalarModeToUsePointData()
        mapper.SetColorModeToMapScalars()
        self.field_actor = vtk.vtkActor()
        self.field_actor.SetMapper(mapper)
        self.field_actor.GetProperty().SetOpacity(0.48)
        self.field_actor.GetProperty().SetLighting(False)
        self.renderer.AddActor(self.field_actor)

    def _make_ground_grid(self):
        actor, poly = _make_polyline_actor(self.theme["grid"], width=1.0, opacity=0.15)
        self.renderer.AddActor(actor)
        self.ground_actor, self.ground_poly = actor, poly

    def set_theme(self, name):
        self.theme_name = name if name in THEMES else "Dark"
        self.theme = THEMES[self.theme_name]
        bg = _hex_rgb(self.theme["plot_bg"])
        self.renderer.SetBackground(*bg)
        self.ground_actor.GetProperty().SetColor(*_hex_rgb(self.theme["grid"]))
        # Keep the coordinate axes in conventional RGB colors across themes.
        for actor, color in zip(self.axis_actors, self.axis_colors):
            actor.GetProperty().SetColor(*_hex_rgb(color))
        for actor, color in zip(self.axis_tick_actors, self.axis_colors):
            actor.GetProperty().SetColor(*_hex_rgb(color))
        self.field_actor.GetMapper().SetLookupTable(_build_lut(self.theme["field_stops"]))
        self.render_window.Render()

    def set_body_colors(self, colors):
        """Apply the user's three display colors to bodies, shells and trajectories."""
        if len(colors) != 3:
            raise ValueError("Exactly three body colors are required.")
        self.body_colors = [str(c).lower() for c in colors]
        if not hasattr(self, "body_actors"):
            return
        actor_groups = (
            getattr(self, "body_actors", []), getattr(self, "body_glow_actors", []),
            getattr(self, "zone_actors", []), getattr(self, "trail_actors", []),
            getattr(self, "floor_actors", []), getattr(self, "acc_actors", []),
        )
        for actors in actor_groups:
            for actor, color in zip(actors, self.body_colors):
                actor.GetProperty().SetColor(*_hex_rgb(color))
        self.render_window.Render()

    def set_display_options(self, *, display_scale=None, show_shells=None, show_field=None,
                            show_trails=None, show_floor=None, show_acceleration=None,
                            zone_mode=None, threshold=None):
        if display_scale is not None:
            self.display_scale = max(0.1, float(display_scale))
        for attr, val in (("show_shells", show_shells), ("show_field", show_field),
                          ("show_trails", show_trails), ("show_floor", show_floor),
                          ("show_acceleration", show_acceleration), ("zone_mode", zone_mode),
                          ("threshold", threshold)):
            if val is not None:
                setattr(self, attr, val)
        self.field_actor.SetVisibility(self.show_field)
        self._field_update_counter = 1000

    def reset_trails(self, positions, max_trails=1200):
        self.max_trails = max(10, int(max_trails))
        self._history = [[np.asarray(p, float).copy()] for p in positions]
        for i in range(3):
            _set_polyline(self.trail_polys[i], self._history[i])
            _set_polyline(self.floor_polys[i], self._history[i])

    def push_positions(self, positions, alive):
        for i in range(3):
            if alive[i]:
                self._history[i].append(np.asarray(positions[i], float).copy())
                if len(self._history[i]) > self.max_trails:
                    del self._history[i][0:len(self._history[i]) - self.max_trails]

    def fit_camera(self, engine, view_halfwidth=None, include_shells=True):
        """Fit the complete scene about world origin so RGB axes stay fixed there."""
        active = engine.pos[engine.alive]
        if len(active) == 0:
            return
        extent = max(float(view_halfwidth or self.view_halfwidth), 0.5)
        # Symmetric bounds preserve the negative half of each axis and keep the
        # origin-crossing RGB axes in a stable world-coordinate frame.
        max_coord = float(np.max(np.abs(active))) if len(active) else 1.0
        spread_from_origin = max_coord + float(np.max(engine.R)) * self.display_scale
        if include_shells:
            for i in range(3):
                if engine.alive[i]:
                    zone_r = engine.zone_radius(i, self.zone_mode, self.threshold)
                    if math.isfinite(zone_r):
                        spread_from_origin = max(spread_from_origin,
                                                 float(np.max(np.abs(engine.pos[i]))) + zone_r)
        extent = max(extent, spread_from_origin * 1.12,
                     float(np.max(engine.R)) * self.display_scale * 2, 0.5)
        self.view_halfwidth = extent
        bounds = (-extent, extent, -extent, extent, -extent, extent)
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetClippingRange(0.001, extent * 1000)
        self.set_axis_extent(extent)
        if self.view_mode == "2D":
            camera.ParallelProjectionOn()
            camera.SetPosition(0.0, 0.0, 8.0 * extent)
            camera.SetViewUp(0.0, 1.0, 0.0)
            camera.SetParallelScale(extent * 1.05)
            self._apply_axis_view_visibility()
        else:
            camera.ParallelProjectionOff()
            camera.SetPosition(2.9*extent, -3.4*extent, 2.5*extent)
            camera.SetViewUp(0, 0, 1)
            self.renderer.ResetCamera(bounds)
        self.renderer.ResetCameraClippingRange()
        self._field_extent = extent
        self._field_update_counter = 1000

    def _update_body_actors(self, engine):
        accel = engine.accelerations()
        span = max(self.view_halfwidth, float(np.max(np.abs(engine.pos[engine.alive]))) if np.any(engine.alive) else 1.0, 1.0)
        accel_max = max(float(np.linalg.norm(accel[i])) for i in range(3) if engine.alive[i]) if np.any(engine.alive) else 1.0
        accel_scale = span * 0.20 / max(accel_max, 1e-14)
        for i in range(3):
            alive = bool(engine.alive[i])
            self.body_actors[i].SetVisibility(alive)
            self.body_glow_actors[i].SetVisibility(alive)
            spin_rate = float(np.linalg.norm(engine.spin_omega[i])) if hasattr(engine, "spin_omega") else 0.0
            self.spin_marker_actors[i].SetVisibility(alive and spin_rate > 1e-12)
            self.zone_actors[i].SetVisibility(alive and self.show_shells)
            self.trail_actors[i].SetVisibility(alive and self.show_trails)
            self.floor_actors[i].SetVisibility(alive and self.show_floor and self.show_trails)
            self.acc_actors[i].SetVisibility(alive and self.show_acceleration)
            if not alive:
                continue
            p = engine.pos[i]
            radius = max(float(engine.R[i]) * self.display_scale, span * 0.008)
            self.body_actors[i].SetPosition(*p)
            j2 = float(engine.j2[i]) if getattr(engine, "enable_oblateness", False) else 0.0
            shape = min(0.35, 4.0 * abs(j2))
            polar_scale = radius * (1.0 - shape if j2 >= 0 else 1.0 + shape)
            self.body_actors[i].SetScale(radius, radius, polar_scale)
            axis = np.asarray(engine.spin_axes[i], dtype=float) if getattr(engine, "spin_axes", None) is not None else np.array([0., 0., 1.])
            axis = axis / max(float(np.linalg.norm(axis)), 1e-15)
            dot_z = min(1.0, max(-1.0, float(axis[2])))
            angle = math.degrees(math.acos(dot_z))
            rot_axis = np.cross(np.array([0.0, 0.0, 1.0]), axis)
            rot_norm = float(np.linalg.norm(rot_axis))
            transform = self.body_spin_transforms[i]
            transform.Identity()
            if rot_norm > 1e-12:
                rot_axis /= rot_norm
                transform.RotateWXYZ(angle, *rot_axis)
            elif dot_z < 0:
                transform.RotateWXYZ(180.0, 1.0, 0.0, 0.0)
            self.body_actors[i].SetUserTransform(transform)
            self.body_glow_actors[i].SetPosition(*p)
            self.body_glow_actors[i].SetScale(radius * 1.45, radius * 1.45, radius * 1.45)
            if spin_rate > 1e-12:
                # Place marker on the equator orthogonal to the fixed spin axis.
                ref = np.array([1.0, 0.0, 0.0])
                if abs(float(axis @ ref)) > 0.85:
                    ref = np.array([0.0, 1.0, 0.0])
                u = np.cross(axis, ref)
                u /= max(float(np.linalg.norm(u)), 1e-15)
                v_axis = np.cross(axis, u)
                phase = spin_rate * float(engine.t)
                marker_dir = math.cos(phase) * u + math.sin(phase) * v_axis
                marker_pos = p + radius * 0.82 * marker_dir
                marker_radius = max(radius * 0.11, span * 0.0012)
                self.spin_marker_actors[i].SetPosition(*marker_pos)
                self.spin_marker_actors[i].SetScale(marker_radius, marker_radius, marker_radius)
            zone_r = engine.zone_radius(i, self.zone_mode, self.threshold)
            if math.isfinite(zone_r) and zone_r > 0:
                self.zone_actors[i].SetPosition(*p)
                self.zone_actors[i].SetScale(zone_r, zone_r, zone_r)
            else:
                self.zone_actors[i].SetVisibility(False)
            if self._history[i]:
                trail = np.asarray(self._history[i])
                _set_polyline(self.trail_polys[i], trail)
                floor_z = min(float(np.min(engine.pos[engine.alive, 2])) - span * 0.32, -span * 0.55)
                floor = trail.copy()
                floor[:, 2] = floor_z
                _set_polyline(self.floor_polys[i], floor)
            vector_end = p + accel[i] * accel_scale
            _set_polyline(self.acc_polys[i], np.vstack((p, vector_end)))

    def _update_field(self, engine):
        n = self.grid_size
        active = engine.pos[engine.alive]
        if len(active) == 0:
            self.field_actor.SetVisibility(False)
            return
        com = engine.center_of_mass()
        span = max(self._field_extent, float(np.max(np.abs(active[:, :2] - com[:2]))) * 1.25, 1.0)
        x = np.linspace(com[0] - span, com[0] + span, n)
        y = np.linspace(com[1] - span, com[1] + span, n)
        X, Y = np.meshgrid(x, y)
        z_slice = float(com[2])
        masses = np.where(engine.alive, engine.m, 0.0)
        magnitude = field_magnitude_grid(
            X, Y, z_slice, masses, engine.pos, engine.G, engine.softening,
            enable_oblateness=getattr(engine, "enable_oblateness", False),
            j2=getattr(engine, "j2", None), spin_axes=getattr(engine, "spin_axes", None),
            radii=engine.R)
        logmag = np.log10(np.maximum(magnitude, 1e-14))
        # Keep range robust to singular regions and stop the palette flickering.
        lo, hi = np.percentile(logmag, (3, 98))
        if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
            lo, hi = -8, 2
        self.field_points = vtk.vtkPoints()
        pts = np.column_stack((X.ravel(), Y.ravel(), np.full(n*n, z_slice - span * 0.008)))
        self.field_points.SetData(numpy_to_vtk(np.ascontiguousarray(pts), deep=True))
        self.field_poly.SetPoints(self.field_points)
        scalars = numpy_to_vtk(np.ascontiguousarray(logmag.ravel()), deep=True)
        scalars.SetName("log10 |g|")
        self.field_poly.GetPointData().SetScalars(scalars)
        self.field_poly.Modified()
        mapper = self.field_actor.GetMapper()
        mapper.SetScalarRange(float(lo), float(hi))
        self.field_actor.SetVisibility(self.show_field)
        self._field_z = z_slice
        self._field_extent = span

    def update(self, engine, force_field=False):
        self._frame_counter += 1
        self._update_body_actors(engine)
        self._field_update_counter += 1
        # Recompute the denser field grid less often than the orbital geometry.
        if force_field or self._field_update_counter >= 5:
            self._update_field(engine)
            self._field_update_counter = 0
        self.renderer.ResetCameraClippingRange()

    def render(self):
        self.render_window.Render()

    def save_png(self, path):
        self.render_window.Render()
        capture = vtk.vtkWindowToImageFilter()
        capture.SetInput(self.render_window)
        capture.SetInputBufferTypeToRGBA()
        capture.ReadFrontBufferOff()
        capture.Update()
        writer = vtk.vtkPNGWriter()
        writer.SetFileName(path)
        writer.SetInputConnection(capture.GetOutputPort())
        writer.Write()


def make_offscreen_snapshot(engine, path, theme="Dark", view_halfwidth=8.0, display_scale=1.8):
    window = vtk.vtkRenderWindow()
    window.SetSize(1500, 950)
    window.SetOffScreenRendering(1)
    scene = GravityScene(window, theme=theme, grid_size=61)
    scene.display_scale = display_scale
    scene.view_halfwidth = view_halfwidth
    scene.reset_trails(engine.pos, 10)
    scene.fit_camera(engine, view_halfwidth=view_halfwidth)
    scene.update(engine, force_field=True)
    scene.render()
    scene.save_png(path)
    window.Finalize()
