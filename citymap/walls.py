"""Walls of a building: which triangles form each wall, and which compass direction each wall faces.

Worked out step by step in Notebook 7b, Step 2, and moved here in Step 4 so Notebook 8 can use it.
The 3D models are only triangles, so a "wall" is found like this:

    all triangles of the building
      -> keep the vertical ones (the normal is almost horizontal)           vertical_triangles
      -> make every normal point outward (count crossings of a ray)        make_outward
      -> group neighbors that face within 15 degrees of the first one      group_into_walls
      -> describe each group: compass direction, width, bottom, top        describe_wall

Typical use:
    mesh, walls = walls.find_walls(tiles, locations, floor_data, model_id)
    walls       -> a table, widest wall first: direction ("S"), bearing (172.1), width_ft, bottom_ft,
                   top_ft, area_sqft, triangles (row numbers in mesh), label_point, minor (True/False)
"""
import numpy as np
import pandas as pd
from vtkmodules.vtkCommonCore import vtkIdList, vtkPoints
from vtkmodules.vtkFiltersFlowPaths import vtkModifiedBSPTree

from citymap import floors, viewing

WALL_SETTINGS = {
    "vertical_limit": 0.3,           # vertical face: the normal's up part is below this (within ~17 degrees)
    "same_direction_deg": 15,        # a neighbor joins a wall if it faces within 15 degrees of the wall's first face
    "grid_to_true_north_deg": 0.34,  # the map grid is turned 0.34 degrees clockwise from true north (BPDA)
    "min_wall_width_ft": 20,         # narrower walls are "minor": kept in the table, but no window grid (option A)
    "label_min_width_ft": 50,        # in the view, label walls at least this wide
}

COMPASS_LABELS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
COMPASS_WORDS = {"N": "north", "NE": "northeast", "E": "east", "SE": "southeast",
                 "S": "south", "SW": "southwest", "W": "west", "NW": "northwest"}
WALL_COLORS = {"N": "#2f6bd6", "NE": "#1fa3a8", "E": "#3da34a", "SE": "#b5b81f",
               "S": "#f08c24", "SW": "#d63c3c", "W": "#b2459e", "NW": "#6d4fc4"}


# ---------------------------------------------------------------- finding the walls (Notebook 7b, Step 2)

def wall_mesh(tiles, locations, model_id):
    """One building's triangles as their own mesh, with corners at the same place merged (so neighbors share them).

    cell_data["tile_triangle"] remembers each triangle's row in the tile mesh (used to paint it).
    """
    tile, index = locations[model_id]
    buildings = tiles[tile]["buildings"]
    its_triangles = np.where(buildings.cell_data["building_index"] == index)[0]
    one_building = buildings.extract_cells(its_triangles)
    one_building.cell_data["tile_triangle"] = its_triangles
    surface = one_building.extract_surface(algorithm=None).triangulate()
    return surface.clean(tolerance=0.01, absolute=True)


def triangle_geometry(mesh):
    """Return (center, normal, area) of every triangle, one row per triangle. Normals have length 1."""
    corners = mesh.points[mesh.regular_faces]           # shape: (triangles, 3 corners, x/y/z)
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    cross = np.cross(b - a, c - a)                     # perpendicular to the triangle; length = 2 x area
    area = np.linalg.norm(cross, axis=1) / 2
    normal = cross / np.maximum(2 * area, 1e-12)[:, None]
    return (a + b + c) / 3, normal, area


def vertical_triangles(normal, area):
    """The numbers of the triangles that are vertical (walls) and not slivers."""
    is_vertical = np.abs(normal[:, 2]) < WALL_SETTINGS["vertical_limit"]
    return np.where(is_vertical & (area > 0.01))[0]


def count_crossings(locator, start, end):
    """How many times the line start -> end crosses the surface (hits closer than 0.05 ft count once)."""
    hit_points, hit_triangles = vtkPoints(), vtkIdList()
    locator.IntersectWithLine(start, end, 1e-6, hit_points, hit_triangles)
    distances = sorted(np.linalg.norm(np.array(hit_points.GetPoint(i)) - start)
                       for i in range(hit_points.GetNumberOfPoints()))
    crossings, previous = 0, -1.0
    for distance in distances:
        if distance - previous > 0.05:
            crossings += 1
        previous = distance
    return crossings


def make_outward(mesh, center, normal, triangle_ids):
    """Flip the normals that point into the building. Returns (fixed normals, how many were flipped).

    How: shoot a ray from half a foot in front of the face, outward. An odd number of crossings
    means the start point was inside the building, so the normal pointed inward.
    """
    locator = vtkModifiedBSPTree()                     # a search structure: makes ray tests fast
    locator.SetDataSet(mesh)
    locator.BuildLocator()
    fixed, flipped = normal.copy(), 0
    for t in triangle_ids:
        out = np.array([normal[t, 0], normal[t, 1], 0.0])
        out = out / np.linalg.norm(out)
        start = center[t] + 0.5 * out
        if count_crossings(locator, start, start + 5000 * out) % 2 == 1:
            fixed[t] = -normal[t]
            flipped += 1
    return fixed, flipped


def triangle_neighbors(mesh, triangle_ids):
    """{triangle: set of triangles sharing an edge with it}, among triangle_ids only."""
    corner_ids = mesh.regular_faces
    edge_to_triangles = {}
    for t in triangle_ids:
        for i in range(3):
            edge = tuple(sorted((corner_ids[t, i], corner_ids[t, (i + 1) % 3])))
            edge_to_triangles.setdefault(edge, []).append(t)
    neighbors = {t: set() for t in triangle_ids}
    for triangles in edge_to_triangles.values():
        for t1 in triangles:
            neighbors[t1].update(t2 for t2 in triangles if t2 != t1)
    return neighbors


def horizontal_direction(vector):
    """Drop the up part of a vector and make it length 1."""
    return vector[:2] / np.linalg.norm(vector[:2])


def group_into_walls(triangle_ids, normal, area, neighbors):
    """Group vertical triangles into walls: biggest triangle first, then grow over neighbors facing the same way."""
    cos_limit = np.cos(np.radians(WALL_SETTINGS["same_direction_deg"]))
    wall_of, walls = {}, []
    for seed in triangle_ids[np.argsort(-area[triangle_ids])]:
        if seed in wall_of:
            continue
        seed_direction = horizontal_direction(normal[seed])
        members, to_visit = [seed], [seed]
        wall_of[seed] = len(walls)
        while to_visit:
            for u in neighbors[to_visit.pop()]:
                if u not in wall_of and np.dot(seed_direction, horizontal_direction(normal[u])) >= cos_limit:
                    wall_of[u] = len(walls)
                    members.append(u)
                    to_visit.append(u)
        walls.append(members)
    return walls


# ---------------------------------------------------------------- compass directions (Notebook 7b, Step 2.5)

def compass_bearing(direction):
    """Map direction (east, north) -> true compass bearing in degrees (0 = north, 90 = east)."""
    grid_bearing = np.degrees(np.arctan2(direction[0], direction[1]))
    return (grid_bearing + WALL_SETTINGS["grid_to_true_north_deg"]) % 360


def compass_label(bearing):
    """Bearing in degrees -> one of 8 labels: N, NE, E, ... (each covers 45 degrees)."""
    return COMPASS_LABELS[int(((bearing + 22.5) % 360) // 45)]


def direction_from_bearing(bearing):
    """The reverse of compass_bearing: true bearing -> map direction (east, north), length 1."""
    grid_bearing = np.radians(bearing - WALL_SETTINGS["grid_to_true_north_deg"])
    return np.array([np.sin(grid_bearing), np.cos(grid_bearing)])


def describe_wall(mesh, members, normal, area, ground):
    """One row of the walls table for one group of triangles."""
    members = np.array(members)
    direction = horizontal_direction((normal[members] * area[members, None]).sum(axis=0))   # area-weighted
    bearing = compass_bearing(direction)
    corners = mesh.points[mesh.regular_faces[members].ravel()]
    along = np.array([direction[1], -direction[0]])    # horizontal, along the wall
    position_along = corners[:, :2] @ along
    return {"direction": compass_label(bearing), "bearing": round(bearing, 1),
            "width_ft": round(position_along.max() - position_along.min(), 1),
            "bottom_ft": round(max(corners[:, 2].min(), ground), 1),     # not below the ground
            "top_ft": round(corners[:, 2].max(), 1), "area_sqft": round(area[members].sum()),
            "triangles": list(members),
            "label_point": corners.mean(axis=0) + 5.0 * np.array([direction[0], direction[1], 0.0])}


_found_walls = {}       # model_id -> (mesh, walls): the ray tests take a moment, so each building is done once


def find_walls(tiles, locations, floor_data, model_id, use_saved=True):
    """Find all walls of one building. Returns (mesh, walls); walls is sorted widest first.

    use_saved=True reuses the result from an earlier call in this session (much faster for clicks).
    """
    if use_saved and model_id in _found_walls:
        return _found_walls[model_id]
    mesh = wall_mesh(tiles, locations, model_id)
    center, normal, area = triangle_geometry(mesh)
    vertical = vertical_triangles(normal, area)
    normal, flipped = make_outward(mesh, center, normal, vertical)
    neighbors = triangle_neighbors(mesh, vertical)
    ground = floors.floor_plan(floor_data, model_id)["ground"]
    rows = [describe_wall(mesh, members, normal, area, ground)
            for members in group_into_walls(vertical, normal, area, neighbors)]
    walls = pd.DataFrame(rows).sort_values("width_ft", ascending=False).reset_index(drop=True)
    walls["minor"] = walls["width_ft"] < WALL_SETTINGS["min_wall_width_ft"]
    _found_walls[model_id] = (mesh, walls)
    return mesh, walls


def wall_of_triangle(walls, triangle):
    """The row of the wall that contains this triangle (a row number in the wall mesh), or None (roof, floor)."""
    for index, wall in walls.iterrows():
        if triangle in wall["triangles"]:
            return wall
    return None


# ---------------------------------------------------------------- drawing (Notebook 7b, Step 2.7)

def color_walls(tiles, locations, model_id, mesh, walls):
    """Paint each wall of the building in its direction's color (WALL_COLORS). Call plotter.render() afterwards."""
    tile = locations[model_id][0]
    colors = tiles[tile]["buildings"].cell_data["color"]       # the colors the view shows (made by add_tiles)
    for index, wall in walls.iterrows():
        colors[mesh.cell_data["tile_triangle"][wall["triangles"]]] = viewing.rgb(WALL_COLORS[wall["direction"]])


def add_wall_labels(plotter, walls, min_width_ft=None):
    """Label the walls at least min_width_ft wide with their direction and bearing, e.g. "S 172°"."""
    if min_width_ft is None:
        min_width_ft = WALL_SETTINGS["label_min_width_ft"]
    wide = walls[walls["width_ft"] >= min_width_ft]
    labels = [f"{wall['direction']} {wall['bearing']:.0f}°" for index, wall in wide.iterrows()]
    plotter.add_point_labels(np.array(list(wide["label_point"])), labels, font_size=11,
                             show_points=False, shape_color="white")


def add_direction_legend(plotter):
    """The color legend: "faces N", "faces NE", ... in the upper right."""
    entries = [[f"faces {label}", WALL_COLORS[label]] for label in COMPASS_LABELS]
    plotter.add_legend(entries, bcolor="white", face="rectangle", loc="upper right", size=(0.14, 0.3))
