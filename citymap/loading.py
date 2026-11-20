"""Load BPDA 3D Smart Model tiles and place them in one shared, centered coordinate system.

Used by both notebooks, so every tile ends up in the same coordinates:
- units are feet (US survey feet), Z is up (same as pyvista);
- GLOBAL_ORIGIN is subtracted from every vertex (see Notebook 1, Step 2.1 for why).
"""
import csv
import io
import zipfile
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh
from PIL import Image

# Project folder = the folder that contains citymap/. Works no matter where a notebook runs from.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Center of tile BOS_J_3, in the files' (shifted Massachusetts State Plane) coordinates, in feet.
# Z stays 0 so heights remain "elevation in feet". Every tile and the terrain must use this same origin.
GLOBAL_ORIGIN = np.array([52_500.0, 57_500.0, 0.0])

# The files use "Metro Boston 3D" coordinates: real Massachusetts State Plane (EPSG:2249) minus this shift,
# in feet (X, Y). Found in Notebook 3, Step 1.7. Same for every tile.
STATE_PLANE_SHIFT = np.array([731_100.0, 2_902_900.0])

# Ground images that can be painted on the terrain: style -> (folder, file name). {tile} becomes the tile name.
GROUND_IMAGES = {
    "aerial": ("{tile}_Orthophoto_2023", "{tile}_Orthophoto_2023.jpg"),
    "groundplan": ("{tile}_Groundplan_2011_JPG", "{tile}_Groundplan_2011.JPG"),
}

# Which catalog Status values to load by default: only structures that exist today.
# Others in the data: "History" (demolished), "Approved Demo", "Under Construction", "Board Approved", "Complete".
DEFAULT_STATUSES = {"Current"}


def read_catalog(tile):
    """Return the tile's catalog.csv as a dict: Model_ID -> row (a dict of column -> text)."""
    path = DATA_DIR / tile / f"{tile}_BldgModels_OBJ" / "catalog.csv"
    with open(path, encoding="utf-8-sig") as f:      # utf-8-sig: the file starts with an invisible BOM marker
        return {row["Model_ID"]: row for row in csv.DictReader(f)}


def load_building_meshes(tile, statuses=DEFAULT_STATUSES):
    """Load a tile's building models as {Model_ID: trimesh.Trimesh}, in the files' original coordinates.

    A model is loaded if at least one of its catalog rows has a Status in `statuses`. (A few Model_IDs
    have several rows, e.g. one 3D file holding several buildings; Notebook 5, Step 2.4.)
    """
    path = DATA_DIR / tile / f"{tile}_BldgModels_OBJ" / "catalog.csv"
    wanted_ids = []                                   # in file order, each Model_ID once
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["Status"] in statuses and row["Model_ID"] not in wanted_ids:
                wanted_ids.append(row["Model_ID"])
    zip_dir = DATA_DIR / tile / f"{tile}_BldgModels_OBJ" / "objz"
    meshes = {}
    for model_id in wanted_ids:
        with zipfile.ZipFile(zip_dir / f"{model_id}_OBJ.zip") as zf:
            obj_bytes = zf.read(f"{model_id}.obj")
        meshes[model_id] = trimesh.load(io.BytesIO(obj_bytes), file_type="obj",
                                        skip_materials=True, force="mesh")
    return meshes


def to_pyvista_blocks(meshes, origin=GLOBAL_ORIGIN):
    """Shift trimesh meshes by -origin and collect them in a pv.MultiBlock, one block per Model_ID."""
    blocks = pv.MultiBlock()
    for model_id, mesh in meshes.items():
        blocks.append(pv.PolyData.from_regular_faces(mesh.vertices - origin, mesh.faces), model_id)
    return blocks


def load_buildings(tile, statuses=DEFAULT_STATUSES, origin=GLOBAL_ORIGIN):
    """Load a tile's buildings, centered on origin, as a pv.MultiBlock with one block per Model_ID."""
    return to_pyvista_blocks(load_building_meshes(tile, statuses), origin)


def load_terrain(tile, origin=GLOBAL_ORIGIN):
    """Load a tile's terrain mesh (2011), centered on origin, as one pv.PolyData.

    The texture referenced by its materials.mtl is skipped. To paint an image on it, use
    add_texture_coordinates (or load_tile, which does everything).
    """
    path = DATA_DIR / tile / f"{tile}_TerrainMesh_2011_OBJ" / f"{tile}_TerrainMesh_2011.obj"
    mesh = trimesh.load(path, skip_materials=True, force="mesh")
    return pv.PolyData.from_regular_faces(mesh.vertices - origin, mesh.faces)


# ---------------------------------------------------------------- the tile grid (Notebook 3, Step 5)

TILE_SIZE = 5_000.0      # every tile is a 5,000 x 5,000 ft square


def tile_grid_bounds(tile):
    """Predict a tile's square from its name alone, in file coordinates (feet).

    In:  a tile name like "BOS_J_3": a letter (column) and a number (row).
    Out: (left, right, bottom, top).

    The rule (Notebook 3, Step 5.1): letters go west -> east, numbers go north -> south.
    Column A starts at X = 5,000 and each letter adds 5,000; row 3 has its bottom edge at Y = 55,000
    and each row number adds 5,000 further south. Checked against the terrain of every loaded tile.
    """
    letter = tile.split("_")[1]            # "BOS_J_3" -> "J"
    row = int(tile.split("_")[2])          # "BOS_J_3" -> 3
    column = ord(letter) - ord("A")        # A -> 0, B -> 1, ..., J -> 9
    left = TILE_SIZE * (column + 1)
    top = 75_000.0 - TILE_SIZE * row       # row 3 -> top 60,000
    return left, left + TILE_SIZE, top - TILE_SIZE, top


def tile_is_downloaded(tile):
    """True if the tile's building and terrain folders are in data/<tile>/ (the minimum load_tile needs)."""
    buildings = DATA_DIR / tile / f"{tile}_BldgModels_OBJ" / "catalog.csv"
    terrain = DATA_DIR / tile / f"{tile}_TerrainMesh_2011_OBJ" / f"{tile}_TerrainMesh_2011.obj"
    return buildings.exists() and terrain.exists()


# ---------------------------------------------------------------- ground images (Notebook 3, Steps 1-3)

def ground_image_path(tile, ground):
    """Return the path of a tile's ground image.

    In:  tile, e.g. "BOS_J_3"; ground, "aerial" or "groundplan" (the keys of GROUND_IMAGES).
    Out: a Path to the .jpg file. Its world file (.jgw) sits next to it.
    """
    folder, file_name = GROUND_IMAGES[ground]
    return DATA_DIR / tile / folder.format(tile=tile) / file_name.format(tile=tile)


def image_bounds(image_path, origin=GLOBAL_ORIGIN):
    """Return the rectangle an image covers on the ground, in our scene coordinates.

    In:  the path of an image that has a world file (same name, ending in .jgw) next to it.
    Out: (left, right, bottom, top) in feet, in the same centered coordinates as load_terrain,
         i.e. real State Plane minus STATE_PLANE_SHIFT minus origin.

    How (Notebook 3, Steps 1.3, 1.4 and 2.1): the world file gives the pixel size and the center
    of the top-left pixel; the image file gives the number of pixels.
    """
    numbers = image_path.with_suffix(".jgw").read_text().split()
    pixel_width = float(numbers[0])
    pixel_height = abs(float(numbers[3]))          # negative in the file: image rows go down, Y goes up
    top_left_x = float(numbers[4])                 # center of the top-left pixel
    top_left_y = float(numbers[5])
    if float(numbers[1]) != 0 or float(numbers[2]) != 0:
        raise ValueError(f"{image_path.name} is rotated; this code only handles north-up images")

    with Image.open(image_path) as image:           # reads only the header, so it's fast
        width_px, height_px = image.size

    # Outer edges, in real State Plane coordinates (half a pixel beyond the pixel centers)
    left = top_left_x - pixel_width / 2
    top = top_left_y + pixel_height / 2
    right = left + width_px * pixel_width
    bottom = top - height_px * pixel_height

    # Real State Plane -> file coordinates (minus the shift) -> scene coordinates (minus the origin)
    subtract_x = float(STATE_PLANE_SHIFT[0] + origin[0])   # float(): plain Python number, prints nicely
    subtract_y = float(STATE_PLANE_SHIFT[1] + origin[1])
    return left - subtract_x, right - subtract_x, bottom - subtract_y, top - subtract_y


def add_texture_coordinates(terrain, bounds):
    """Give every terrain point a position (u, v) in an image that lies flat over it.

    In:  terrain, a pv.PolyData in scene coordinates; bounds, (left, right, bottom, top) from image_bounds.
    Out: nothing is returned; the terrain is changed in place: terrain.active_texture_coordinates is set.

    u goes 0 -> 1 from the image's left to right edge, v goes 0 -> 1 from bottom to top (Notebook 3, Step 2.2).
    """
    left, right, bottom, top = bounds
    x = terrain.points[:, 0]
    y = terrain.points[:, 1]
    u = (x - left) / (right - left)
    v = (y - bottom) / (top - bottom)
    terrain.active_texture_coordinates = np.column_stack((u, v))


def load_ground_texture(image_path):
    """Load an image as a pyvista texture, set up to look good when zoomed in or out.

    In:  the image's path. Out: a pv.Texture, to pass to plotter.add_mesh(terrain, texture=...).
    """
    texture = pv.read_texture(image_path)
    texture.interpolate = True    # smooth when zoomed in, instead of square blocks
    texture.mipmap = True         # no shimmer when zoomed out
    return texture


# ---------------------------------------------------------------- cache (Notebook 3, Step 4)

# Processed tiles are saved here. Safe to delete: it's rebuilt automatically. Ignored by git (data/*/).
CACHE_DIR = DATA_DIR / "cache"


def cache_path(tile, statuses=DEFAULT_STATUSES):
    """Return the cache file path for a tile and a set of statuses.

    The statuses are part of the file name, so e.g. "only Current" and "Current + Board Approved"
    get separate cache files. Example: data/cache/BOS_J_3__Current.npz
    """
    status_text = "+".join(sorted(statuses)).replace(" ", "-")
    return CACHE_DIR / f"{tile}__{status_text}.npz"


def save_tile_cache(tile, statuses=DEFAULT_STATUSES, origin=GLOBAL_ORIGIN):
    """Read a tile's original files (slow) and save its terrain and buildings into one cache file.

    In:  the tile name, which statuses to include, and the origin to center on.
    Out: the path of the written file (see cache_path).

    The file is a numpy .npz (several arrays in one file). All buildings are stored together:
    their points one after another in "building_points", their triangles in "building_faces",
    and per building how many points and triangles it has, so read_tile_cache can cut them apart again.
    Triangles are stored as point numbers *within their own building* (0 = that building's first point).
    """
    terrain = load_terrain(tile, origin)
    arrays = building_arrays(load_building_meshes(tile, statuses), origin)

    path = cache_path(tile, statuses)
    CACHE_DIR.mkdir(exist_ok=True)
    np.savez(
        path,
        origin=origin,                                   # remembered, so a different origin is detected
        terrain_points=terrain.points,
        terrain_faces=terrain.regular_faces,             # one row of 3 point numbers per triangle
        building_ids=np.array(arrays["model_ids"]),
        building_point_counts=arrays["point_counts"],
        building_face_counts=arrays["face_counts"],
        building_points=arrays["points"],
        building_faces=arrays["faces"],
    )
    return path


def building_arrays(meshes, origin=GLOBAL_ORIGIN):
    """Put the points and triangles of many building meshes one after another into big arrays.

    In:  {Model_ID: trimesh mesh} (from load_building_meshes), and the origin to subtract.
    Out: a dict with
        "model_ids"     list of Model_IDs, in order
        "point_counts"  how many points each building has
        "face_counts"   how many triangles each building has
        "points"        all buildings' points (centered), one after another
        "faces"         all buildings' triangles, as point numbers *within their own building*
    """
    model_ids = []
    point_counts = []
    face_counts = []
    points_per_building = []
    faces_per_building = []
    for model_id, mesh in meshes.items():
        model_ids.append(model_id)
        point_counts.append(len(mesh.vertices))
        face_counts.append(len(mesh.faces))
        points_per_building.append(mesh.vertices - origin)   # centered, like load_buildings
        faces_per_building.append(mesh.faces)

    if not model_ids:                                        # a tile without buildings
        return {"model_ids": [], "point_counts": np.zeros(0, dtype=int), "face_counts": np.zeros(0, dtype=int),
                "points": np.zeros((0, 3)), "faces": np.zeros((0, 3), dtype=int)}
    return {
        "model_ids": model_ids,
        "point_counts": np.array(point_counts),
        "face_counts": np.array(face_counts),
        "points": np.concatenate(points_per_building),
        "faces": np.concatenate(faces_per_building),
    }


def merge_buildings(arrays):
    """Make ONE mesh holding all buildings, and remember which triangle belongs to which building.

    In:  the dict from building_arrays (or the same arrays read from a cache file).
    Out: a pv.PolyData. Its cell_data["building_index"] says, for every triangle, the position of its
         building in arrays["model_ids"]. So the Model_ID of triangle t is
         model_ids[mesh.cell_data["building_index"][t]].

    Why: VTK gets slower the more separate meshes exist (Notebook 3, Step 4.2). One mesh per tile
    avoids that, and drawing one big mesh is also faster than thousands of small ones.
    """
    faces = arrays["faces"].copy()
    building_index = np.zeros(len(faces), dtype=int)     # filled in below, one number per triangle
    point_start = 0
    face_start = 0
    for i in range(len(arrays["model_ids"])):
        face_end = face_start + arrays["face_counts"][i]
        # The triangles count points from 0 within their own building. In the big mesh, building i's
        # points start at row point_start, so shift its point numbers by that much.
        faces[face_start:face_end] += point_start
        building_index[face_start:face_end] = i
        point_start = point_start + arrays["point_counts"][i]
        face_start = face_end

    merged = pv.PolyData.from_regular_faces(arrays["points"], faces)
    merged.cell_data["building_index"] = building_index
    return merged


def read_tile_cache(path, origin=GLOBAL_ORIGIN, merged=False):
    """Read a cache file written by save_tile_cache (fast).

    In:  the cache file path, the origin we expect, and merged (see Out).
    Out: (terrain, buildings, model_ids). terrain is a pv.PolyData; model_ids the list of Model_IDs.
         buildings is either
           merged=False: a pv.MultiBlock with one block per Model_ID, in the same order as load_buildings;
           merged=True:  one pv.PolyData for all buildings (see merge_buildings).
         Returns None if the file was made with a different origin.
    """
    with np.load(path) as data:
        if not np.array_equal(data["origin"], origin):
            return None
        terrain = pv.PolyData.from_regular_faces(data["terrain_points"], data["terrain_faces"])
        arrays = {
            "model_ids": [str(model_id) for model_id in data["building_ids"]],
            "point_counts": data["building_point_counts"],
            "face_counts": data["building_face_counts"],
            "points": data["building_points"],
            "faces": data["building_faces"],
        }

    if merged:
        return terrain, merge_buildings(arrays), arrays["model_ids"]

    model_ids = arrays["model_ids"]
    point_counts = arrays["point_counts"]
    face_counts = arrays["face_counts"]
    all_points = arrays["points"]
    all_faces = arrays["faces"]
    buildings = pv.MultiBlock()
    point_start = 0
    face_start = 0
    for i in range(len(model_ids)):
        point_end = point_start + point_counts[i]       # this building's rows in all_points
        face_end = face_start + face_counts[i]          # this building's rows in all_faces
        block = pv.PolyData.from_regular_faces(all_points[point_start:point_end],
                                               all_faces[face_start:face_end])
        buildings.append(block, model_ids[i])           # block name = Model_ID, as in load_buildings
        point_start = point_end
        face_start = face_end
    return terrain, buildings, model_ids


def load_tile_geometry(tile, statuses=DEFAULT_STATUSES, origin=GLOBAL_ORIGIN, merged=False):
    """Return (terrain, buildings, model_ids) for a tile, from the cache if possible.

    merged=False: buildings is a pv.MultiBlock (one block per Model_ID); True: one merged pv.PolyData.
    If there's no cache file yet (or it was made with another origin), the original files are read
    and the cache file is written first. So the first call is slow, later calls are fast.
    """
    path = cache_path(tile, statuses)
    if path.exists():
        cached = read_tile_cache(path, origin, merged)
        if cached is not None:
            return cached
    save_tile_cache(tile, statuses, origin)
    return read_tile_cache(path, origin, merged)


def clear_cache(tiles=None):
    """Delete cache files. The next load_tile rebuilds them.

    In:  tiles, a list of tile names (deletes only their cache files, for every status choice),
         or None to delete all cache files in data/cache/.
    Out: how many files were deleted.
    """
    deleted = 0
    if not CACHE_DIR.exists():
        return deleted
    for path in CACHE_DIR.glob("*.npz"):
        tile_of_file = path.name.split("__")[0]          # "BOS_J_3__Current.npz" -> "BOS_J_3"
        if tiles is None or tile_of_file in tiles:
            path.unlink()
            deleted += 1
    return deleted


# ---------------------------------------------------------------- everything for one tile

def load_tile(tile, ground="aerial", statuses=DEFAULT_STATUSES, origin=GLOBAL_ORIGIN, use_cache=True,
              merged=False):
    """Load everything for one tile: terrain (with texture coordinates), its ground image, and buildings.

    In:
        tile       e.g. "BOS_J_3"
        ground     "aerial" (2023 photo), "groundplan" (2011 drawn map) or "plain" (no image)
        statuses   which building models to load (see DEFAULT_STATUSES)
        use_cache  True: use data/cache/ (fast after the first time). False: always read the original files.
        merged     False: one pyvista block per building. True: all buildings in one mesh (much faster
                   for many tiles; see merge_buildings for how to find a triangle's building).
    Out: a dict with four entries:
        "terrain"       pv.PolyData, centered; has texture coordinates unless ground is "plain"
        "texture"       pv.Texture to paint on the terrain, or None for "plain"
        "buildings"     merged=False: pv.MultiBlock, one block per Model_ID (same as load_buildings);
                        merged=True: one pv.PolyData with cell_data["building_index"]
        "building_ids"  list of Model_IDs, in order (block order, or the meaning of building_index)
    """
    if use_cache:
        terrain, buildings, model_ids = load_tile_geometry(tile, statuses, origin, merged)
    else:
        terrain = load_terrain(tile, origin)
        meshes = load_building_meshes(tile, statuses)
        model_ids = list(meshes.keys())
        if merged:
            buildings = merge_buildings(building_arrays(meshes, origin))
        else:
            buildings = to_pyvista_blocks(meshes, origin)

    texture = None
    if ground != "plain":
        image_path = ground_image_path(tile, ground)
        add_texture_coordinates(terrain, image_bounds(image_path, origin))
        texture = load_ground_texture(image_path)
    return {"terrain": terrain, "texture": texture, "buildings": buildings, "building_ids": model_ids}
