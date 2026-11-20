"""Ray tests against all buildings, and the view check (Notebook 8, Step 9.1).

A "ray" here is a straight line from a spot (e.g. an annotated window) in one direction. The question is
always the same: which building does it meet first, and how far away?

    locators = rays.build_locators(tiles)                     # once, ~1 s per tile
    hit = rays.first_hit(locators, tiles, start, end)         # the first building on the line, or None
    area = rays.model_area(tile_names)                        # where our 3D data ends
    fan = rays.view_check(locators, tiles, area, spot)        # Step 9.1: a fan of rays from a spot

Where the data ends: buildings outside the loaded tiles don't exist in the model. A ray that leaves the
loaded area without hitting anything is therefore "unknown beyond the edge", never "open".
"""
import numpy as np
import pandas as pd
import pyvista as pv
from vtkmodules.vtkCommonCore import vtkIdList, vtkPoints
from vtkmodules.vtkFiltersFlowPaths import vtkModifiedBSPTree

from citymap import loading, walls as walls_module

RAY_SETTINGS = {
    "skip_near_ft": 0.5,           # hits closer than this to the start are ignored (the spot's own wall surface)
    "max_view_ft": 10_560.0,       # 2 miles: a view ray that reaches this far without a hit is "open"
    "fan_step_deg": 2.0,           # the view check's rays are this many degrees apart
}

OUTCOME_COLORS = {"blocked": "#d62728", "open": "#2ca02c", "unknown": "#9a9a9a"}   # for drawing the rays


# ---------------------------------------------------------------- search structures and the first hit

def build_locators(tiles):
    """One ray-search structure (vtkModifiedBSPTree, as in Notebook 7b, 2.3) per tile's buildings mesh.

    In:  the tiles dict (loading.load_tile(..., merged=True)).
    Out: {tile name: locator}. Building them takes about a second per tile; then each ray test takes
         a fraction of a millisecond, because the tree only checks triangles near the line.
    """
    locators = {}
    for tile, parts in tiles.items():
        locator = vtkModifiedBSPTree()
        locator.SetDataSet(parts["buildings"])
        locator.BuildLocator()
        locators[tile] = locator
    return locators


def first_hit(locators, tiles, start, end):
    """The first building the straight line start -> end meets, in any tile.

    Out: None if it meets nothing, else {"tile", "model_id", "point" (where it hits), "distance" (ft from start)}.
    Hits closer than RAY_SETTINGS["skip_near_ft"] are ignored, so a ray that starts just outside a wall
    doesn't count that wall.
    """
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    best = None
    for tile, locator in locators.items():
        hit_points, hit_triangles = vtkPoints(), vtkIdList()
        locator.IntersectWithLine(start, end, 1e-6, hit_points, hit_triangles)   # every hit on the line
        for i in range(hit_points.GetNumberOfPoints()):
            point = np.array(hit_points.GetPoint(i))
            distance = np.linalg.norm(point - start)
            if distance < RAY_SETTINGS["skip_near_ft"] or (best is not None and distance >= best["distance"]):
                continue
            triangle = hit_triangles.GetId(i)
            index = tiles[tile]["buildings"].cell_data["building_index"][triangle]
            best = {"tile": tile, "model_id": tiles[tile]["building_ids"][index], "point": point, "distance": distance}
    return best


# ---------------------------------------------------------------- where the data ends

def model_area(tile_names):
    """The rectangle around the loaded tiles, in view coordinates: (x_min, x_max, y_min, y_max).

    Our 12 tiles form a full 4 x 3 block, so they fill this rectangle exactly. (With tiles missing from
    the rectangle, it would be too big, and rays over the gaps would wrongly count as "inside".)
    """
    boxes = np.array([loading.tile_grid_bounds(tile) for tile in tile_names])     # file coordinates
    x0, y0 = loading.GLOBAL_ORIGIN[0], loading.GLOBAL_ORIGIN[1]
    return boxes[:, 0].min() - x0, boxes[:, 1].max() - x0, boxes[:, 2].min() - y0, boxes[:, 3].max() - y0


def distance_to_edge(area, start, direction):
    """How far one can go from start along direction (3D, length 1) before leaving the area, seen from above.

    Out: a distance in ft, along the 3D direction (0 if start is already outside; inf for a ray
         straight up). How: for x and for y, the distance until that coordinate reaches the side it
         moves toward; the smaller of the two is where the ray leaves.
    """
    x_min, x_max, y_min, y_max = area
    distances = []
    for value, step, low, high in [(start[0], direction[0], x_min, x_max), (start[1], direction[1], y_min, y_max)]:
        if step > 1e-12:
            distances.append((high - value) / step)
        elif step < -1e-12:
            distances.append((low - value) / step)
    return max(0.0, min(distances)) if distances else np.inf


def ray_direction(bearing, elevation=0.0):
    """A direction (3D, length 1) from a TRUE compass bearing (0 = north, 90 = east) and an angle above level.

    Uses walls.direction_from_bearing, so the 0.34-degree grid/true north correction (Notebook 7b, 2.5)
    is the same as for the walls.
    """
    flat = walls_module.direction_from_bearing(bearing)
    up = np.radians(elevation)
    return np.array([flat[0] * np.cos(up), flat[1] * np.cos(up), np.sin(up)])


# ---------------------------------------------------------------- the view check (Step 9.1)

def view_check(locators, tiles, area, spot, elevations=(0.0,), step_deg=None, max_distance=None):
    """Shoot a fan of rays from an annotated spot over the half the wall faces, and see what each one meets.

    In:
        locators, tiles, area    from build_locators, the tiles dict, model_area
        spot                     from windows.locate (needs "point", 2 ft in front of the wall, and "wall")
        elevations               angles above level, in degrees, e.g. (0,) or (-10, 0, 10)
        step_deg, max_distance   default: RAY_SETTINGS
    Out: a DataFrame, one row per ray:
        bearing, elevation       its direction (true bearing, degrees)
        outcome                  "blocked" (meets a building), "open" (nothing within max_distance)
                                 or "unknown" (leaves the loaded tiles first: no data beyond)
        model_id, distance_ft    the building it meets (blocked only) and how far away
        end                      where to draw the ray to: the hit, max_distance, or the edge

    The fan: from the wall's bearing - 88 to + 88 degrees (straight along the wall, +-90, is left out).
    """
    step_deg = step_deg or RAY_SETTINGS["fan_step_deg"]
    max_distance = max_distance or RAY_SETTINGS["max_view_ft"]
    start = np.asarray(spot["point"], dtype=float)
    facing = spot["wall"]["bearing"]
    rows = []
    for elevation in elevations:
        for offset in np.arange(-88.0, 88.0 + 1e-9, step_deg):
            bearing = (facing + offset) % 360
            direction = ray_direction(bearing, elevation)
            edge = distance_to_edge(area, start, direction)
            length = min(max_distance, edge)
            hit = first_hit(locators, tiles, start, start + length * direction)
            if hit is not None:
                row = {"outcome": "blocked", "model_id": hit["model_id"], "distance_ft": hit["distance"], "end": hit["point"]}
            elif edge < max_distance:
                row = {"outcome": "unknown", "model_id": None, "distance_ft": edge, "end": start + edge * direction}
            else:
                row = {"outcome": "open", "model_id": None, "distance_ft": max_distance, "end": start + max_distance * direction}
            rows.append({"bearing": round(bearing, 1), "elevation": elevation, **row})
    return pd.DataFrame(rows)


def ray_lines(start, fan):
    """The fan's rays as one pyvista mesh of lines, with cell_data["color"] from OUTCOME_COLORS."""
    start = np.asarray(start, dtype=float)
    points = [start]
    lines, colors = [], []
    for index, ray in fan.iterrows():
        points.append(ray["end"])
        lines.extend([2, 0, len(points) - 1])                     # a line from point 0 (the spot) to this end
        colors.append(pv.Color(OUTCOME_COLORS[ray["outcome"]]).int_rgb)
    mesh = pv.PolyData(np.array(points), lines=np.array(lines))
    mesh.cell_data["color"] = np.array(colors, dtype=np.uint8)
    return mesh


def add_view_rays(plotter, start, fan, name="view_rays"):
    """Draw the fan from view_check (red = blocked, green = open, gray = unknown beyond the data)."""
    plotter.add_mesh(ray_lines(start, fan), scalars="color", rgb=True, line_width=2, name=name, pickable=False)
