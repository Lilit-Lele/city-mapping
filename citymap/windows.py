"""Window grid on a wall, and describing a spot both ways (Notebook 7b, Steps 3 and 4).

    description -> 3D point:   locate(tiles, locations, floor_data, model_id, 19, "S", "leftmost")
    3D point    -> description: describe_point(tiles, locations, floor_data, model_id, clicked_point)

The grid: one row per floor (citymap.floors), columns of about 10 ft that fill the wall exactly.
Left and right are as seen by someone standing OUTSIDE, facing the wall (column 1 = leftmost).
Floor levels and window columns are approximations: the 3D models have no floors or windows.

How a wall is laid flat ("unfolded"): every corner becomes (s, z), where s = how far to the right
(seen from outside) and z = the elevation. The wall's outline in (s, z) is a shapely shape.

      z ▲            outline of a wall seen from outside
        │   ┌───┬───┬───┐  floor 3
        │   ├───┼───┼───┤  floor 2
        │   ├───┼───┼───┤  floor 1
        └───┴───┴───┴───┴──► s (to the right)
             col1 col2 col3
"""
import numpy as np
import pandas as pd
import pyvista as pv
import shapely

from citymap import floors, walls as walls_module

GRID_SETTINGS = {
    "column_width_ft": 10.0,   # about one or two windows; adjusted so the columns fill the wall exactly
    "offset_ft": 0.5,          # draw the grid this far in front of the wall, so the wall doesn't hide it
    "marker_out_ft": 2.0,      # locate() puts its point this far in front of the wall (markers stay visible)
}


# ---------------------------------------------------------------- the grid (Step 3)

def right_of_viewer(direction):
    """Standing outside, facing the wall, you look along -direction; your right hand points this way."""
    return np.array([-direction[1], direction[0]])


def wall_frame(mesh, wall):
    """Everything needed to go between the wall's flat (s, z) picture and 3D.

    Out: {"direction": the way the wall faces (east, north), "right": the viewer's right,
          "offset": how far out along direction the wall's surface is, "outline": shapely shape in (s, z)}.
    """
    direction = walls_module.direction_from_bearing(wall["bearing"])
    right = right_of_viewer(direction)
    corners = mesh.points[mesh.regular_faces[wall["triangles"]]]      # (triangles, 3 corners, x/y/z)
    flat_triangles = [shapely.Polygon([(corner[:2] @ right, corner[2]) for corner in triangle])
                      for triangle in corners]
    outline = shapely.union_all(flat_triangles).buffer(0.01)          # buffer closes hairline gaps
    offset = (corners.reshape(-1, 3)[:, :2] @ direction).max()
    return {"direction": direction, "right": right, "offset": offset, "outline": outline}


def wall_point(frame, s, z, out_ft=0.0):
    """The 3D point at s (to the right) and height z on the wall, out_ft in front of it."""
    xy = s * frame["right"] + (frame["offset"] + out_ft) * frame["direction"]
    return np.array([xy[0], xy[1], z])


def column_layout(frame):
    """(left edge s, column width, number of columns) for this wall."""
    s_min, z_min, s_max, z_max = frame["outline"].bounds
    columns = max(1, round((s_max - s_min) / GRID_SETTINGS["column_width_ft"]))
    return s_min, (s_max - s_min) / columns, columns


def window_grid(floor_data, model_id, mesh, wall):
    """Return (frame, number of columns, cells): one cells row per (floor, column) that lies on the wall."""
    frame = wall_frame(mesh, wall)
    s_min, column_width, columns = column_layout(frame)
    count, source = floors.floor_count(floor_data, model_id)
    cells = []
    for floor_number in range(1, count + 1):
        bottom, top = floors.floor_elevation(floor_data, model_id, floor_number)
        for column in range(1, columns + 1):
            left = s_min + (column - 1) * column_width
            middle = shapely.Point(left + column_width / 2, (bottom + top) / 2)
            if frame["outline"].contains(middle):                    # only where the wall really is
                cells.append({"floor": floor_number, "column": column, "left_s": left,
                              "right_s": left + column_width, "bottom": bottom, "top": top})
    return frame, columns, pd.DataFrame(cells)


def walls_facing(walls, direction_label, height):
    """All non-minor walls facing this way that reach this height, widest first (numbered 1, 2, ...)."""
    same = walls[(walls["direction"] == direction_label) & ~walls["minor"]]
    reaching = same[(same["bottom_ft"] <= height) & (same["top_ft"] >= height)]
    return reaching.sort_values("width_ft", ascending=False).reset_index(drop=True)


def pick_wall(walls, direction_label, height):
    """The widest non-minor wall facing this way that reaches this height, or None."""
    candidates = walls_facing(walls, direction_label, height)
    return None if len(candidates) == 0 else candidates.iloc[0]


def choose_cell(cells, floor_number, column):
    """One cells row. column: a number, "leftmost", "rightmost" or "center" (on that floor). None if not there."""
    on_floor = cells[cells["floor"] == floor_number] if len(cells) else cells
    if len(on_floor) == 0:
        return None
    if column == "leftmost":
        column = on_floor["column"].min()
    elif column == "rightmost":
        column = on_floor["column"].max()
    elif column == "center":
        column = int(round(on_floor["column"].median()))
    chosen = on_floor[on_floor["column"] == column]
    return None if len(chosen) == 0 else chosen.iloc[0]


def along_wall_text(from_left_ft, wall_width_ft):
    """Where along a wall, in words: "about 165 ft from the wall's left end (wall ~340 ft wide)".

    Left = as seen from outside, facing the wall. Rounded to 5 ft: spots and walls are only that exact.
    (Not "column 17 of 34": the models have no windows, so a column number would look like a window.)
    """
    width = max(5, 5 * round(wall_width_ft / 5))
    distance = 5 * round(max(0.0, min(from_left_ft, wall_width_ft)) / 5)
    where = "at the wall's left end" if distance == 0 else (
        "at the wall's right end" if distance >= width else f"about {distance} ft from the wall's left end")
    return f"{where} (wall ~{width} ft wide)"


def spot_text(floor_data, model_id, wall, floor_number, from_left_ft, wall_width_ft):
    """The words for a spot, e.g. "Floor ~19 of 41 (assessment count, level estimated), south-facing wall
    (172°), about 15 ft from the wall's left end (wall ~190 ft wide)". "~" = estimated.
    from_left_ft: how far along the wall the spot is, from its left end seen from outside."""
    count, source = floors.floor_count(floor_data, model_id)
    of_count = f"~{count}" if source == "estimate" else str(count)
    return (f"Floor ~{floor_number} of {of_count} ({source} count, level estimated), "
            f"{walls_module.COMPASS_WORDS[wall['direction']]}-facing wall ({wall['bearing']:.0f}°), "
            f"{along_wall_text(from_left_ft, wall_width_ft)}")


# ---------------------------------------------------------------- both ways (Step 4)

def locate(tiles, locations, floor_data, model_id, floor_number, direction_label, column="leftmost", wall_number=1):
    """Description -> 3D point.

    In:  floor number, direction ("N", "NE", ... "NW"), column (a number, "leftmost", "rightmost", "center"),
         wall_number: if several walls face that way at that height, 1 = the widest (default), 2 = next, ...
    Out: a dict:
         "point"        3D point slightly in front of the wall (None if the spot doesn't exist)
         "description"  the spot in words (or why it doesn't exist)
         "choice"       which wall was used, when there was a choice ("" otherwise)
         "floor", "direction", "column" (a number), "wall_number", "columns", "wall", "frame", "cell", "cells"
    """
    count, source = floors.floor_count(floor_data, model_id)
    if not 1 <= floor_number <= count:
        return {"point": None, "description": f"Floor {floor_number} doesn't exist: floors 1 to {count} ({source})."}
    mesh, walls = walls_module.find_walls(tiles, locations, floor_data, model_id)
    bottom, top = floors.floor_elevation(floor_data, model_id, floor_number)
    candidates = walls_facing(walls, direction_label, (bottom + top) / 2)
    if len(candidates) < wall_number:
        return {"point": None, "description": f"No {direction_label}-facing wall (at least "
                f"{walls_module.WALL_SETTINGS['min_wall_width_ft']} ft wide) reaches floor {floor_number}"
                + (f" (asked for wall {wall_number}, there are {len(candidates)})." if len(candidates) else ".")}
    wall = candidates.iloc[wall_number - 1]
    choice = ""
    if len(candidates) > 1:
        widths = ", ".join(f"#{i + 1} {w['width_ft']:.0f} ft ({w['bearing']:.0f}°)" for i, w in candidates.iterrows())
        choice = (f"{len(candidates)} {direction_label}-facing walls reach floor {floor_number}: {widths}. "
                  f"Using #{wall_number}" + (" (the widest)." if wall_number == 1 else "."))
    frame, columns, cells = window_grid(floor_data, model_id, mesh, wall)
    cell = choose_cell(cells, floor_number, column)
    if cell is None:
        return {"point": None, "description": f"The wall has no column '{column}' on floor {floor_number}.",
                "choice": choice}
    s_middle = (cell["left_s"] + cell["right_s"]) / 2
    point = wall_point(frame, s_middle, (cell["bottom"] + cell["top"]) / 2, GRID_SETTINGS["marker_out_ft"])
    s_min, column_width, _ = column_layout(frame)
    return {"point": point, "choice": choice, "wall_number": wall_number,
            "description": spot_text(floor_data, model_id, wall, floor_number, s_middle - s_min, column_width * columns),
            "floor": floor_number, "direction": direction_label, "column": int(cell["column"]),
            "columns": columns, "wall": wall, "frame": frame, "cell": cell, "cells": cells}


def describe_point(tiles, locations, floor_data, model_id, point):
    """3D point on a building (e.g. a click) -> description. The reverse of locate.

    Out: the same dict as locate (with "point" = the clicked point), or {"point": None, "description": why}
         when the point is on a roof, a minor wall, or outside the floors. "wall_number" says which of the
         walls facing that way it is (1 = widest), so locate(..., wall_number=...) finds the same wall again.
    How: the wall mesh triangle nearest the point -> its wall -> (s, z) on that wall -> column and floor.
    """
    mesh, walls = walls_module.find_walls(tiles, locations, floor_data, model_id)
    wall = walls_module.wall_of_triangle(walls, int(mesh.find_closest_cell(point)))
    if wall is None:
        return {"point": None, "description": "Not a wall (a roof or a ledge). Click a wall."}
    if wall["minor"]:
        return {"point": None, "description": f"A minor wall ({wall['width_ft']:.0f} ft wide, "
                f"under {walls_module.WALL_SETTINGS['min_wall_width_ft']} ft): no window grid."}
    floor_number = floors.floor_at_height(floor_data, model_id, point[2])
    if floor_number is None:
        return {"point": None, "description": "Below floor 1 or above the top floor (roof structure)."}
    frame, columns, cells = window_grid(floor_data, model_id, mesh, wall)
    s_min, column_width, columns = column_layout(frame)
    from_left = point[:2] @ frame["right"] - s_min
    column = int(np.clip(from_left // column_width + 1, 1, columns))
    cell = choose_cell(cells, floor_number, column)
    bottom, top = floors.floor_elevation(floor_data, model_id, floor_number)
    same_way = walls_facing(walls, wall["direction"], (bottom + top) / 2)      # its number among them, for locate
    numbers = [i + 1 for i, other in same_way.iterrows() if other["triangles"] == wall["triangles"]]
    return {"point": np.asarray(point), "choice": "", "wall_number": numbers[0] if numbers else 1,
            "description": spot_text(floor_data, model_id, wall, floor_number, from_left, column_width * columns),
            "floor": floor_number, "direction": wall["direction"], "column": column,
            "columns": columns, "wall": wall, "frame": frame, "cell": cell, "cells": cells}


# ---------------------------------------------------------------- drawing (Step 3.7)

def cell_corners(frame, cell, out_ft):
    """The cell's 4 corners in 3D: bottom left, bottom right, top right, top left."""
    return [wall_point(frame, s, z, out_ft) for s, z in [(cell["left_s"], cell["bottom"]), (cell["right_s"], cell["bottom"]),
                                                       (cell["right_s"], cell["top"]), (cell["left_s"], cell["top"])]]


def grid_lines(frame, cells):
    """Every cell as a thin rectangle in front of the wall, as one pyvista mesh of lines."""
    points, lines = [], []
    for index, cell in cells.iterrows():
        first = len(points)
        points.extend(cell_corners(frame, cell, GRID_SETTINGS["offset_ft"]))
        lines.extend([5, first, first + 1, first + 2, first + 3, first])   # closed rectangle
    return pv.PolyData(np.array(points), lines=np.array(lines))


def add_chosen_cell(plotter, frame, cell, text, name="chosen_cell"):
    """A yellow rectangle on the cell and a text label above it. Replaces the previous one with the same name."""
    corners = np.array(cell_corners(frame, cell, GRID_SETTINGS["offset_ft"] + 0.3))
    plotter.add_mesh(pv.PolyData(corners, faces=[4, 0, 1, 2, 3]), color="#ffd400", opacity=0.9, name=name)
    middle = wall_point(frame, (cell["left_s"] + cell["right_s"]) / 2, cell["top"] + 5, 3.0)
    plotter.add_point_labels(np.array([middle]), [text], font_size=11, show_points=False,
                             shape_color="white", always_visible=True, name=name + "_label")


def wall_view(frame, cell, distance=350.0):
    """A camera outside, in front of the wall, looking at the cell. Out: (position, focal point, up)."""
    focus = wall_point(frame, (cell["left_s"] + cell["right_s"]) / 2, (cell["bottom"] + cell["top"]) / 2)
    out = np.array([frame["direction"][0], frame["direction"][1], 0.0])
    return focus + distance * out - np.array([0.0, 0.0, 40.0]), focus, np.array([0.0, 0.0, 1.0])
