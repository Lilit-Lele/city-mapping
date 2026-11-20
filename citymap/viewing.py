"""Show loaded tiles in a 3D view, click buildings, and color a building by its ID.

Works with tiles loaded by loading.load_tile(..., merged=True): one mesh for all buildings of a tile,
where cell_data["building_index"] says which building each triangle belongs to.
Used in Notebook 3, Step 5 (and later notebooks).
"""
import numpy as np
import pyvista as pv
from vtkmodules.vtkRenderingCore import vtkCellPicker


def rgb(color):
    """Turn a color name or hex code (e.g. "lightgray", "#c9d6b8") into 3 numbers 0-255 (red, green, blue)."""
    return np.array(pv.Color(color).int_rgb, dtype=np.uint8)


def add_tiles(plotter, tiles, building_color="lightgray", terrain_color="#c9d6b8",
              flat_ground=False, building_ambient=0.0, building_diffuse=1.0):
    """Add every tile's terrain and buildings to a plotter.

    In:
        plotter           a pv.Plotter
        tiles             {tile name: dict from load_tile(..., merged=True)}
        building_color    color of all buildings
        terrain_color     used only for tiles without a ground texture ("plain")
        flat_ground       True: the ground shows its image/color exactly, with no light and shade
                          (like a printed map). False: the ground is shaded by the lights like the buildings.
        building_ambient  how much buildings are lit evenly from everywhere (0 to 1). Higher = brighter,
                          softer, less contrast between walls.
        building_diffuse  how much buildings are lit by the lights' direction (0 to 1). This makes walls
                          that face the light brighter than walls facing away.
        (Notebook 3 uses the defaults; Notebook 4, Step 6 sets them from the style cell.)
    Out: {tile name: the buildings actor}. Needed for clicking (enable_building_click).

    Each building triangle gets its own color, stored in cell_data["color"]. That's what lets
    color_building paint one building red without touching the others.
    """
    ground_light = {"ambient": 1.0, "diffuse": 0.0, "specular": 0.0} if flat_ground else {}
    building_actors = {}
    for tile, parts in tiles.items():
        if parts["texture"] is None:
            plotter.add_mesh(parts["terrain"], color=terrain_color, **ground_light)
        else:
            plotter.add_mesh(parts["terrain"], texture=parts["texture"], **ground_light)

        buildings = parts["buildings"]
        one_color_per_triangle = np.tile(rgb(building_color), (buildings.n_cells, 1))   # n_cells rows of (r, g, b)
        buildings.cell_data["color"] = one_color_per_triangle
        building_actors[tile] = plotter.add_mesh(buildings, scalars="color", rgb=True,
                                                 ambient=building_ambient, diffuse=building_diffuse,
                                                 specular=0.0)
    return building_actors


def add_status_buildings(plotter, status_tiles, catalogs, status_colors, building_ambient=0.0,
                         building_diffuse=1.0):
    """Add buildings colored by their Status (e.g. future buildings: green / pink). No terrain.

    In:
        plotter        a pv.Plotter that already shows the terrain (from add_tiles)
        status_tiles   {tile name: dict from load_tile(..., statuses=..., merged=True)}
        catalogs       {tile name: loading.read_catalog(tile)}, to look up each building's Status
        status_colors  {Status: color}, e.g. {"Board Approved": "#267300"}. Every loaded Status needs a color.
        building_ambient, building_diffuse   lighting, as in add_tiles
    Out: {tile name: the buildings actor}, only for tiles that have such buildings. Use it for
         clicking (enable_building_click) and to show / hide them (actor.visibility = True / False).

    How the colors are made: first one color per building (from its Status), then each triangle
    takes the color of its building, using building_index (see loading.merge_buildings).
    """
    actors = {}
    for tile, parts in status_tiles.items():
        if len(parts["building_ids"]) == 0:
            continue                                  # no such buildings in this tile: nothing to draw
        building_colors = []
        for model_id in parts["building_ids"]:
            status = catalogs[tile][model_id]["Status"]
            building_colors.append(rgb(status_colors[status]))
        building_colors = np.array(building_colors)                         # one row (r, g, b) per building
        buildings = parts["buildings"]
        buildings.cell_data["color"] = building_colors[buildings.cell_data["building_index"]]  # per triangle
        actors[tile] = plotter.add_mesh(buildings, scalars="color", rgb=True, ambient=building_ambient,
                                        diffuse=building_diffuse, specular=0.0)
    return actors


def add_outlines(plotter, tiles, color="gray", opacity=0.6):
    """Draw thin lines along the edges of buildings (roof edges, wall corners), like the reference map.

    In:
        plotter   a pv.Plotter
        tiles     {tile name: dict from load_tile(..., merged=True)} (existing or future buildings)
        color, opacity   of the lines (opacity 0 = invisible, 1 = solid)
    Out: {tile name: the lines actor}, e.g. to hide them together with future buildings.

    How: in the building files every triangle has its own corner points, so neighbouring triangles
    don't share edges. clean() merges points that are at the same place (within 0.01 ft). Then
    extract_feature_edges keeps the edges where the surface bends by more than 30 degrees (edges of
    roofs and walls), plus open edges, and skips the edges inside flat walls or roofs.
    The lines are separate meshes, so clicking still finds the buildings behind them.
    """
    actors = {}
    for tile, parts in tiles.items():
        if parts["buildings"].n_cells == 0:
            continue
        merged_points = parts["buildings"].clean(tolerance=0.01, absolute=True)
        edges = merged_points.extract_feature_edges(feature_angle=30, boundary_edges=True,
                                                    non_manifold_edges=False, manifold_edges=False)
        actors[tile] = plotter.add_mesh(edges, color=color, opacity=opacity, line_width=1)
    return actors


def color_building(tiles, model_id, color="red", building_color="lightgray"):
    """Paint one building (by Model_ID) in `color` and set all other buildings back to building_color.

    In:  the tiles dict, the Model_ID, the highlight color, and the normal building color.
    Out: the tile name the building is in, or None if no loaded tile has that Model_ID.
    Call plotter.render() afterwards to update the view.
    """
    found_in = None
    for tile, parts in tiles.items():
        buildings = parts["buildings"]
        buildings.cell_data["color"][:] = rgb(building_color)          # everything back to normal
        if model_id in parts["building_ids"]:
            index = parts["building_ids"].index(model_id)              # position in the ID list
            its_triangles = buildings.cell_data["building_index"] == index   # mask: True for its triangles
            buildings.cell_data["color"][its_triangles] = rgb(color)
            found_in = tile
    return found_in


def highlight_building(tiles, locations, model_id, color="red"):
    """Paint one building in `color` and leave every other building as it is (Notebook 5, Step 4).

    In:  the tiles dict, locations (lookup.building_locations), the Model_ID, the highlight color.
    Out: what's needed to undo it later: {"model_id", "tile", "triangles" (positions in the tile's mesh),
         "old_colors" (their colors before)}. Pass it to undo_highlight.
    Unlike color_building, it doesn't reset the other buildings, so colors set by other code stay.
    It changes the existing color array (no new mesh). Call plotter.render() afterwards.
    """
    tile, index = locations[model_id]
    buildings = tiles[tile]["buildings"]
    its_triangles = np.where(buildings.cell_data["building_index"] == index)[0]   # positions of its triangles
    saved = {"model_id": model_id, "tile": tile, "triangles": its_triangles,
             "old_colors": buildings.cell_data["color"][its_triangles].copy()}  # copy: keep the old values
    buildings.cell_data["color"][its_triangles] = rgb(color)
    return saved


def undo_highlight(tiles, saved):
    """Give the triangles in `saved` (from highlight_building) their old colors back. Then plotter.render()."""
    buildings = tiles[saved["tile"]]["buildings"]
    buildings.cell_data["color"][saved["triangles"]] = saved["old_colors"]


def building_center(tiles, tile, model_id):
    """Return the 3D center of one building's bounding box (useful to point the camera at it)."""
    parts = tiles[tile]
    index = parts["building_ids"].index(model_id)
    its_triangles = np.where(parts["buildings"].cell_data["building_index"] == index)[0]
    return np.array(parts["buildings"].extract_cells(its_triangles).center)


def enable_building_click(plotter, building_actors, tiles, on_click, max_move_pixels=5):
    """Call on_click(tile, model_id, point) when the user clicks (not drags) on a building.

    In:
        plotter, building_actors (from add_tiles), tiles (the tiles dict)
        on_click   your function. Gets (tile name, Model_ID, 3D point), or (None, None, None)
                   when the click hit the ground or the sky.
    Same idea as Notebook 2, Step 4.2: a press and release that moved less than max_move_pixels
    is a click (anything more is a drag = rotate). The picker shoots a ray from the camera through
    the mouse position; the triangle it hits gives building_index, which gives the Model_ID.
    """
    picker = vtkCellPicker()
    picker.SetTolerance(0.0005)
    picker.PickFromListOn()                     # only buildings can be hit (not labels or markers)
    for actor in building_actors.values():
        picker.AddPickList(actor)
    press_position = {}                         # a dict so the inner functions can update it

    def on_press(*args):
        press_position["xy"] = plotter.iren.get_event_position()

    def on_release(*args):
        x, y = plotter.iren.get_event_position()
        x0, y0 = press_position.get("xy", (x, y))
        if (x - x0) ** 2 + (y - y0) ** 2 > max_move_pixels ** 2:
            return                              # the mouse moved: a drag, not a click
        picker.Pick(x, y, 0, plotter.renderer)
        hit_actor = picker.GetActor()
        for tile, actor in building_actors.items():
            if hit_actor is actor:
                triangle = picker.GetCellId()                                   # which triangle was hit
                index = tiles[tile]["buildings"].cell_data["building_index"][triangle]
                on_click(tile, tiles[tile]["building_ids"][index], np.array(picker.GetPickPosition()))
                return
        on_click(None, None, None)              # hit the terrain or nothing

    plotter.iren.add_observer("LeftButtonPressEvent", on_press)
    plotter.iren.add_observer("LeftButtonReleaseEvent", on_release)


def go_to_view(plotter, view):
    """Move the camera to a saved view and redraw.

    In:  view = (camera position, focal point, up direction), each 3 numbers, like plotter.camera_position.
    Used for the start view and the "Home view" button (Notebook 4, Step 6).
    """
    position, focal_point, up = view
    plotter.camera_position = [tuple(map(float, position)), tuple(map(float, focal_point)), tuple(map(float, up))]
    plotter.render()


def show_text_panel(plotter, text_lines, name="info_panel"):
    """Show lines of text in the upper left of the 3D view, on a white background (Notebook 5, Step 3).

    A panel with the same name replaces the previous one. Call plotter.render() afterwards.
    """
    panel = plotter.add_text("\n".join(text_lines), position="upper_left", font_size=10,
                             color="black", name=name)
    panel.prop.background_color = "white"       # readable over the aerial photo
    panel.prop.background_opacity = 0.8
    return panel


def clear_text_panel(plotter, name="info_panel"):
    """Remove the text panel (does nothing if there is none). Call plotter.render() afterwards."""
    plotter.remove_actor(name)


def building_view(tiles, locations, model_id, from_angle=20, down_angle=30):
    """Return a camera view that looks at one building from a sensible distance (Notebook 6, Step 5).

    In:
        tiles, locations   as usual; model_id the building
        from_angle         where the camera stands, in degrees: 0 = due south of the building,
                           20 = south-southwest (a bit to the left), 90 = west
        down_angle         how steeply the camera looks down: 0 = level, 90 = straight down
    Out: (camera position, focal point, up), for go_to_view.

    The focal point is the center of the building's box (half way up). The distance is 2.5 times
    the building's height or width, whichever is bigger, but at least 700 ft, so tall towers fit
    in the picture and small houses still show their street.
    """
    tile, index = locations[model_id]
    its_triangles = np.where(tiles[tile]["buildings"].cell_data["building_index"] == index)[0]
    x_min, x_max, y_min, y_max, z_min, z_max = tiles[tile]["buildings"].extract_cells(its_triangles).bounds
    center = np.array([(x_min + x_max) / 2, (y_min + y_max) / 2, (z_min + z_max) / 2])
    size = max(z_max - z_min, x_max - x_min, y_max - y_min)
    distance = max(2.5 * size, 700.0)

    side = np.radians(from_angle)
    down = np.radians(down_angle)
    direction = np.array([-np.sin(side) * np.cos(down),     # west part   (negative x = west)
                          -np.cos(side) * np.cos(down),     # south part  (negative y = south)
                          np.sin(down)])                    # up part
    return center + distance * direction, center, np.array([0.0, 0.0, 1.0])


def color_buildings(tiles, model_ids, color):
    """Paint every building whose Model_ID is in model_ids; all other buildings keep their colors.

    In:  the tiles dict, a list (or pandas column) of Model_IDs, and a color (Notebook 6, Step 6).
    Out: how many buildings were painted (IDs not in the 3D view are skipped).
    Call plotter.render() afterwards.
    How: per tile, first one True/False per building ("is it in the group?"), then per triangle,
    using building_index (the same trick as add_status_buildings).
    """
    wanted = set(model_ids)
    painted = 0
    for tile, parts in tiles.items():
        building_in_group = np.array([model_id in wanted for model_id in parts["building_ids"]], dtype=bool)
        if not building_in_group.any():
            continue
        triangle_in_group = building_in_group[parts["buildings"].cell_data["building_index"]]
        parts["buildings"].cell_data["color"][triangle_in_group] = rgb(color)
        painted += int(building_in_group.sum())
    return painted


def reset_building_colors(tiles, building_color):
    """Give every building the normal color again. Call plotter.render() afterwards."""
    for parts in tiles.values():
        parts["buildings"].cell_data["color"][:] = rgb(building_color)

