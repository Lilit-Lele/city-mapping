"""Turn the project's data into small files that a web browser can load (for the web page in web/).

Run it from the project folder, with the project's Python:

    .venv/bin/python export_web.py                      # all tiles of config.BLOCK_TILES, into web/data/
    .venv/bin/python export_web.py --out web_n6/data    # the same files for the older Notebook 6 page
    .venv/bin/python export_web.py BOS_F_6              # only some tiles (quick test)

It only READS data/ (and uses data/cache/ like the notebooks do). It WRITES the output folder (default
web/data/), which is deleted and rebuilt every time. Nothing in it should be edited by hand: change this
script and run it again.

What it writes (all coordinates in feet, Z up, centered on loading.GLOBAL_ORIGIN, like the notebooks):

    data/manifest.json          the list of tiles and the files of each one
    data/buildings.json         one row per 3D building: name, height, land use, ... and its box
    data/tiles/BOS_F_6.bin.gz   buildings + terrain heights of one tile (our own small binary format)
    data/tiles/BOS_F_6_future.bin.gz   the tile's approved / under-construction buildings
    data/tiles/BOS_F_6.jpg      the tile's aerial photo, made smaller
    data/streets.json           street name labels (Notebook 8, Step 7), if the street data was downloaded
    data/annotations.json       your annotations placed in 3D (Notebook 8, Steps 5-6): ONLY with --with-annotations,
                                because they may be personal and anyone who can open the page can read them
    data/building_units.json    extra details, unit positions and known mismatches for buildings in data/buildings/
                                (e.g. Ora Seaport): ONLY with --with-units, because the units come from the
                                building's own floor plates

Why each step exists, and how big things get, is explained next to each function.
"""
import argparse
import gzip
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyvista as pv
from PIL import Image

from citymap import annotations, config, floors, loading, lookup, streets

OUT_DIR = Path(__file__).resolve().parent / "web" / "data"   # web_n6 uses the same files: --out web_n6/data

FUTURE_STATUSES = {"Board Approved", "Under Construction"}   # as in Notebook 6, Step 6.6

TERRAIN_SPACING = 10.0       # feet between two terrain heights (see terrain_heights)
TEXTURE_SIZE = 2048          # pixels per side of each aerial photo on the web (the originals have 5000)
TEXTURE_QUALITY = 80         # JPEG quality, 0-100

LARGEST_UINT16 = 65_535      # the biggest whole number that fits in 2 bytes


# ---------------------------------------------------------------- 1. numbers -> fewer bytes

def quantize(values, low, high):
    """Store numbers between low and high as whole numbers 0 ... 65,535 (2 bytes each instead of 8).

    In:  values (any numpy array, in feet) and the range they lie in.
    Out: an array of the same shape, dtype uint16. low becomes 0, high becomes 65,535.

    The browser turns them back with:  feet = low + whole_number / 65,535 * (high - low).
    Precision: a tile is about 5,000 ft wide, so one step is 5,000 / 65,535 = 0.08 ft (about 2 cm).
    Much finer than the models themselves, and a quarter of the size of float64 numbers.
    """
    scaled = (values - low) / (high - low) * LARGEST_UINT16
    return np.round(scaled).astype(np.uint16)


# ---------------------------------------------------------------- 2. buildings

def building_geometry(tile, statuses):
    """Return one tile's buildings, made as small as possible for the browser.

    In:  the tile name and which statuses to load (Current, or the future ones).
    Out: None if the tile has no such buildings, otherwise a dict:
        "model_ids"   list of Model_IDs; building number i in the arrays below is model_ids[i]
        "low", "high" the corners of the box around all points (feet), used by quantize
        "positions"   (points, 3) uint16: every corner point, quantized
        "building"    (points,)   uint16: which building each point belongs to (its number i)
        "triangles"   (triangles, 3) uint32: three point numbers per triangle
        "boxes"       (buildings, 6): x_min, y_min, z_min, x_max, y_max, z_max per building, in feet

    Starts from loading.load_tile_geometry(merged=True), the same data the notebooks show (from the cache).
    Then two things make it smaller:

    1. The OBJ files repeat corner points: a corner shared by 3 walls is stored 3 times. We keep each
       distinct point once *per building*, and renumber the triangles. That removes about 2/3 of the points.
       Points stay per building, so every point still belongs to exactly one building, which is what the
       browser needs to color one building (the same idea as cell_data["building_index"], but per point,
       because WebGL colors points, not triangles).
    2. quantize: 2 bytes per coordinate.
    """
    _, merged, model_ids = loading.load_tile_geometry(tile, statuses, merged=True)
    if len(model_ids) == 0:
        return None
    if len(model_ids) > LARGEST_UINT16:
        raise ValueError(f"{tile}: {len(model_ids)} buildings don't fit in a uint16 building number")

    points = np.asarray(merged.points, dtype=np.float64)
    triangles = merged.regular_faces                         # (triangles, 3) point numbers
    triangle_building = merged.cell_data["building_index"]   # which building each triangle is part of

    low = points.min(axis=0)
    high = points.max(axis=0)
    positions = quantize(points, low, high)

    # Every triangle corner, as one row: (x, y, z, building). Two corners with the same row are the same
    # point of the same building, so they can share one entry.
    corner_point = triangles.ravel()                          # point number of every corner
    corner_building = np.repeat(triangle_building, 3)         # each triangle's building, for its 3 corners
    corner_rows = np.column_stack([positions[corner_point], corner_building]).astype(np.uint16)

    # np.unique finds the distinct rows. Its outputs:
    #   distinct_rows  each distinct row once (sorted, which mixes up the order of the file)
    #   first_corner   for each distinct row, where it appeared first among the corners
    #   corner_to_row  for each corner, which distinct row it is
    distinct_rows, first_corner, corner_to_row = np.unique(
        corner_rows, axis=0, return_index=True, return_inverse=True)

    # Put the distinct points back in the order they first appear (building by building, as in the file).
    # Points of one building then sit next to each other, which makes the file compress much better.
    file_order = np.argsort(first_corner)                     # distinct rows, in order of appearance
    new_number = np.empty(len(file_order), dtype=np.int64)
    new_number[file_order] = np.arange(len(file_order))       # distinct row -> its new point number
    new_triangles = new_number[corner_to_row.ravel()].reshape(-1, 3)

    kept = distinct_rows[file_order]                          # (points, 4): x, y, z, building
    point_building = kept[:, 3].astype(np.int64)

    # Box around each building, in feet (for "go to" and the camera). Back from quantized to feet.
    feet = low + kept[:, :3].astype(np.float64) / LARGEST_UINT16 * (high - low)
    box_min = np.full((len(model_ids), 3), np.inf)
    box_max = np.full((len(model_ids), 3), -np.inf)
    np.minimum.at(box_min, point_building, feet)              # .at: "for each point, update its building's row"
    np.maximum.at(box_max, point_building, feet)

    return {
        "model_ids": list(model_ids),
        "low": low,
        "high": high,
        "positions": np.ascontiguousarray(kept[:, :3]),
        "building": np.ascontiguousarray(kept[:, 3]),
        "triangles": new_triangles.astype(np.uint32),
        "boxes": np.hstack([box_min, box_max]),
    }


# ---------------------------------------------------------------- 3. terrain

def terrain_heights(tile, spacing=TERRAIN_SPACING):
    """Return the ground height on a regular grid over the tile, quantized, plus what's needed to read it.

    In:  the tile name and the distance between grid points (feet).
    Out: a dict with
        "heights"     (rows * columns,) uint16, the north row first, west to east in each row
                      (the same order as the pixels of the aerial photo)
        "columns", "rows"   size of the grid (501 x 501 for 10 ft)
        "low", "high"       height range, for quantize
        "bounds"            (left, right, bottom, top) of the tile in scene feet

    Why: the terrain OBJ has ~130,000 points and ~260,000 triangles per tile, placed irregularly. Sent as
    it is, that's ~1.7 MB per tile after compression, more than all of a tile's buildings. A grid of
    heights needs no x, y or triangles at all: the browser builds the flat grid itself (a "plane") and
    only lifts each point to its height. ~0.4 MB per tile.

    How the heights are found: the terrain is flattened (z = 0) and its height is kept as a value on each
    point. pyvista's sample() then finds, for each grid point, the triangle it falls in and averages
    that triangle's corner heights (linear interpolation). The few grid points exactly on the tile's
    edge can fall just outside every triangle; they take the height of their nearest neighbor in the grid.

    The aerial photo covers exactly the tile square (checked for all 12 tiles), so the browser can lay
    the photo on the grid corner to corner.
    """
    terrain, _, _ = loading.load_tile_geometry(tile, merged=True)
    points = np.asarray(terrain.points)

    flat = pv.PolyData.from_regular_faces(np.column_stack([points[:, :2], np.zeros(len(points))]),
                                          terrain.regular_faces)
    flat.point_data["height"] = points[:, 2]

    left, right, bottom, top = loading.tile_grid_bounds(tile)            # file coordinates
    left, right = left - loading.GLOBAL_ORIGIN[0], right - loading.GLOBAL_ORIGIN[0]
    bottom, top = bottom - loading.GLOBAL_ORIGIN[1], top - loading.GLOBAL_ORIGIN[1]
    columns = int(round((right - left) / spacing)) + 1
    rows = int(round((top - bottom) / spacing)) + 1

    grid = pv.ImageData(dimensions=(columns, rows, 1), spacing=(spacing, spacing, 1), origin=(left, bottom, 0))
    sampled = grid.sample(flat)
    heights = np.asarray(sampled.point_data["height"]).reshape(rows, columns)   # south row first
    found = np.asarray(sampled.point_data["vtkValidPointMask"]).reshape(rows, columns).astype(bool)
    heights = fill_missing(heights, found)

    heights = heights[::-1]                                  # north row first, like the photo
    low, high = float(heights.min()), float(heights.max())
    if high - low < 1:                                       # a flat tile: avoid dividing by ~0
        high = low + 1
    return {
        "heights": quantize(heights, low, high).ravel(),
        "columns": columns,
        "rows": rows,
        "low": low,
        "high": high,
        "bounds": [left, right, bottom, top],
    }


def fill_missing(heights, found):
    """Give every grid point that wasn't found the height of the nearest found point in its row or column.

    Only a few points on the tile's edge are missing (0.4% for BOS_F_6), so a simple method is enough:
    copy found values into the gaps, first along rows (left -> right, then right -> left), then columns.
    """
    heights = heights.copy()
    found = found.copy()
    if not found.any():
        raise ValueError("No terrain height found at all: is the tile's terrain inside its grid square?")
    for _ in range(2):                                       # rows, then columns (via transposing)
        for direction in (1, -1):
            for row_heights, row_found in zip(heights, found):
                last = None
                order = range(len(row_heights)) if direction == 1 else range(len(row_heights) - 1, -1, -1)
                for i in order:
                    if row_found[i]:
                        last = row_heights[i]
                    elif last is not None:
                        row_heights[i] = last
                        row_found[i] = True
        heights, found = heights.T, found.T
    return heights


# ---------------------------------------------------------------- 4. the tile file format

def write_tile_file(path, header, arrays):
    """Save some numpy arrays and a description of them in one compressed file the browser can read.

    In:  the file path, a dict of extra information (header), and {name: numpy array}.
    Out: the file size in bytes.

    The file, before compression, is:
        4 bytes            the length N of the description, as a whole number (little-endian uint32)
        N bytes            the description, as JSON text: the header plus, for each array, its type,
                           shape and where its bytes start
        the arrays' bytes  one after another, exactly as numpy holds them in memory

    The browser reads the description, then makes each array with no copying or converting, e.g.
    new Uint16Array(buffer, start, count). That's why every start is a multiple of 4 bytes: JavaScript
    requires it for 4-byte numbers (uint32). The whole file is then gzip-compressed; the browser
    decompresses it itself (DecompressionStream), so it works on any host, including Cloudflare Pages.

    Why not glTF, the standard 3D format? It would work too, but it needs extra rules (extensions) for
    the 2-byte positions and the building numbers. This format is ~30 lines on each side and easy to check.
    """
    descriptions = {}
    start = 0
    blobs = []
    for name, array in arrays.items():
        array = np.ascontiguousarray(array)
        if array.dtype.byteorder == ">":
            raise ValueError("big-endian arrays aren't supported")   # never happens on Intel / Apple chips
        data = array.tobytes()
        descriptions[name] = {"dtype": array.dtype.name, "shape": list(array.shape), "start": start}
        padding = (-len(data)) % 4                           # zeros so the next array starts at a multiple of 4
        blobs.append(data + b"\0" * padding)
        start += len(data) + padding

    text = json.dumps({**header, "arrays": descriptions}).encode("utf-8")
    text += b" " * ((-len(text)) % 4)                        # so the arrays start at a multiple of 4 too
    content = len(text).to_bytes(4, "little") + text + b"".join(blobs)
    compressed = gzip.compress(content, compresslevel=9, mtime=0)   # mtime=0: same input -> same file
    path.write_bytes(compressed)
    return len(compressed)


def as_floats(values, digits=2):
    """numpy numbers -> a plain list of rounded Python floats, so json.dumps can write them."""
    return [round(float(v), digits) for v in values]


def export_buildings(tile, statuses, path):
    """Write one tile's buildings (Current, or future) to path. Returns (model_ids, boxes, bytes) or None."""
    geometry = building_geometry(tile, statuses)
    if geometry is None:
        return None
    header = {"tile": tile, "low": as_floats(geometry["low"]), "high": as_floats(geometry["high"])}
    arrays = {name: geometry[name] for name in ("positions", "building", "triangles")}
    size = write_tile_file(path, header, arrays)
    return geometry["model_ids"], geometry["boxes"], size


def export_terrain_and_buildings(tile, path):
    """Write one tile's terrain heights and today's buildings into one file. Returns (model_ids, boxes, bytes)."""
    geometry = building_geometry(tile, loading.DEFAULT_STATUSES)
    terrain = terrain_heights(tile)
    header = {
        "tile": tile,
        "low": as_floats(geometry["low"]),
        "high": as_floats(geometry["high"]),
        "terrain": {key: terrain[key] for key in ("columns", "rows", "low", "high", "bounds")},
    }
    arrays = {name: geometry[name] for name in ("positions", "building", "triangles")}
    arrays["terrain_heights"] = terrain["heights"]
    size = write_tile_file(path, header, arrays)
    return geometry["model_ids"], geometry["boxes"], size


# ---------------------------------------------------------------- 5. aerial photos

def export_photo(tile, path, size=TEXTURE_SIZE, quality=TEXTURE_QUALITY):
    """Save a smaller copy of the tile's aerial photo. Returns the file size in bytes.

    The originals are 5000 x 5000 pixels (1 pixel = 1 ft) and 20 MB each. Many phones and laptops can't
    use images over 4096 pixels on the GPU, and 12 x 20 MB is too much to download. 2048 pixels (about
    2.4 ft per pixel) is ~1 MB per tile and still shows streets, trees and roofs.
    """
    with Image.open(loading.ground_image_path(tile, "aerial")) as image:
        small = image.convert("RGB").resize((size, size), Image.LANCZOS)   # LANCZOS: sharp downscaling
    small.save(path, quality=quality, optimize=True)
    return path.stat().st_size


# ---------------------------------------------------------------- 6. the building table

# Columns of buildings.json, in order: our name -> catalog column (after lookup.add_assessment).
BUILDING_COLUMNS = {
    "id": "Model_ID",
    "name": "Name",
    "status": "Status",
    "struct_type": "StructType",
    "struct_use": "StructUse",
    "height_ft": "Height_Ft",
    "floors": "Floors",
    "land_use_code": "Land_Use_Code",
    "land_use": "Land_Use",
    "year_built": "Year_Built",
    "google_link": "GoogleLnk",
}


def catalog_rows(catalog, statuses):
    """One catalog row per Model_ID, among the rows with a Status in statuses (the first one, by file order).

    The same rule as lookup.get_building: a few Model_IDs have several rows (Notebook 5, Step 2.4).
    Out: a DataFrame indexed by Model_ID.
    """
    rows = catalog[catalog["Status"].isin(statuses)]
    return rows.drop_duplicates("Model_ID").set_index("Model_ID")


def json_value(value):
    """One table value -> something json.dumps can write. Empty values become null."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return round(float(value), 1)
    return str(value)


# Each building's floor plan (citymap/floors.py, floor_plan): where floor 1 starts, how many floors, how tall
# floor 1 and the others are, and where the count comes from. With these five numbers the browser can do what
# floors.floor_elevation and floors.floor_at_height do (Notebook 7). Only today's buildings have floor data.
FLOOR_COLUMNS = ["floor_ground", "floor_count", "floor_first", "floor_typical", "floor_source"]


def floor_values(floor_data, model_id):
    """The FLOOR_COLUMNS values of one building, or None for each if it has no floor data (future buildings)."""
    if floor_data is None or model_id not in floor_data["counts"].index:
        return [None] * len(FLOOR_COLUMNS)
    plan = floors.floor_plan(floor_data, model_id)
    return [round(plan["ground"], 2), int(plan["count"]), round(plan["first"], 3), round(plan["typical"], 3), plan["source"]]


def building_table_rows(layer, tile, model_ids, boxes, rows_by_id, floor_data=None):
    """The buildings.json rows of one tile and layer ("current" or "future").

    Each row: layer, tile, index (the building number in the tile file), the BUILDING_COLUMNS values,
    box (x_min, y_min, z_min, x_max, y_max, z_max in feet), and the FLOOR_COLUMNS values.
    """
    table_rows = []
    for index, model_id in enumerate(model_ids):
        if model_id in rows_by_id.index:
            catalog_row = rows_by_id.loc[model_id]
            values = [model_id] + [json_value(catalog_row[column]) for column in list(BUILDING_COLUMNS.values())[1:]]
        else:                                                # in 3D but not in the catalog (shouldn't happen)
            values = [model_id] + [None] * (len(BUILDING_COLUMNS) - 1)
        table_rows.append([layer, tile, index] + values + [as_floats(boxes[index], 1)] + floor_values(floor_data, model_id))
    return table_rows


# ---------------------------------------------------------------- 7. street names and annotations (Notebook 8)

def export_streets(loaded_tiles, path):
    """Write the street name labels of Notebook 8, Step 7 to path. Returns (labels, bytes), or None without street data.

    The same functions and settings as the notebook (7.5): segments with the same name that touch are joined,
    about one label per 1,000 ft, none on pieces under 150 ft. Each label: name, road class, length of its
    street piece (for the "minimum length" control), x, y and the ground height there.
    """
    if not streets.STREETS_FILE.exists():
        print("No street data (data/streets/street_segments.geojson): run Notebook 8, Step 7.2 once. Skipped.")
        return None
    named = streets.join_streets(streets.load_streets())
    labels = streets.label_positions(loaded_tiles, named, spacing_ft=1000, min_length_ft=150)
    rows = [[label.name, label.road_class, int(label.length_ft), round(label.x, 1), round(label.y, 1), round(label.ground_ft, 1)]
            for label in labels.itertuples()]
    text = json.dumps({"source": "City of Boston, Boston Street Segments (SAM System), ODC Public Domain (PDDL)",
                       "columns": ["name", "road_class", "length_ft", "x", "y", "ground_ft"], "rows": rows},
                      separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(rows), len(text)


def export_annotations(loaded_tiles, floor_data, path):
    """Write your annotations (Notebook 8, Steps 5-6), placed in 3D, to path. Returns (count, bytes).

    Each one is placed with windows.locate, as in the notebook, so the web page gets exactly the notebook's
    spot: its point (2 ft in front of the wall), the wall's bearing and the words ("Floor ~19 of 60, ...").
    Annotations that can't be placed are listed and left out.
    PRIVATE: data/annotations/ is kept out of git because it may hold personal places. Only call this
    when you want them on the web page (export_web.py --with-annotations).
    """
    locations = lookup.building_locations(loaded_tiles)
    placed, problems = annotations.place_annotations(loaded_tiles, locations, floor_data, annotations.load_annotations())
    for annotation, reason in problems:
        print(f"  annotation {annotation['id']} ({annotation['label']}) not placed: {reason}")
    rows = [{"id": annotation["id"], "label": annotation["label"], "note": annotation.get("note", ""),
             "color": annotation.get("color", annotations.DEFAULT_COLOR), "created": annotation.get("created", ""),
             "model_id": annotation["model_id"], "description": spot["description"],
             "floor": int(spot["floor"]), "direction": spot["direction"], "column": int(spot["column"]),
             "point": as_floats(spot["point"], 2), "bearing": round(float(spot["wall"]["bearing"]), 2)}
            for annotation, spot in placed]
    text = json.dumps(rows, indent=1)
    path.write_text(text, encoding="utf-8")
    return len(rows), len(text)


BUILDINGS_DIR = loading.DATA_DIR / "buildings"     # your per-building extras (see export_units)


def issue_list(text, category):
    """ "kind: text | kind: text" (a units-file cell) -> [{"category", "kind", "text"}].
    category: "website" (the website contradicts itself) or "model" (the 3D model can't follow the website)."""
    return [{"category": category, "kind": part.split(":", 1)[0].strip(), "text": part.split(":", 1)[1].strip()}
            for part in str(text).split(" | ") if ":" in part]


def export_units(path):
    """Write the per-building extras of data/buildings/ to path: each building's details and its units.

    For every data/buildings/<Model_ID>_units.csv (one row per unit and wall; start_ft/end_ft measured along
    the wall from its left end seen from outside), it also needs <Model_ID>_walls.csv (each wall's ends in
    view coordinates, written with the units file) and reads <Model_ID>_details.json if there is one
    (name, also_known_as, website, listing_fetched, positions_status, lines, notes). Returns (number of buildings, bytes), or None if there are none.
    The units come from the building's own floor plates: only export them if you may publish that
    (export_web.py --with-units).
    """
    buildings = {}
    for units_file in sorted(BUILDINGS_DIR.glob("*_units.csv")):
        model_id = units_file.name.removesuffix("_units.csv")
        walls_file = BUILDINGS_DIR / f"{model_id}_walls.csv"
        if not walls_file.exists():
            print(f"  {units_file.name}: no {walls_file.name} next to it, skipped")
            continue
        units = pd.read_csv(units_file, dtype={"unit": str, "wall": str})
        for column in ["rent", "max_rent", "available"]:            # units files made before rents were kept
            if column not in units:
                units[column] = None
        text_columns = ["wall", "wall_direction", "status", "note", "bedrooms", "website_issues", "model_notes",
                        "windows_ft", "listed_fetched", "available"]
        units[text_columns] = units[text_columns].astype(object).fillna("").astype(str)
        used_walls = set(units["wall"]) - {""}
        walls = [{"wall": w.wall, "direction": w.direction, "bearing": round(float(w.bearing), 1),
                  "left": [round(float(w.left_x), 2), round(float(w.left_y), 2)],
                  "right": [round(float(w.right_x), 2), round(float(w.right_y), 2)]}
                 for w in pd.read_csv(walls_file).itertuples() if w.wall in used_walls]
        unit_rows = []
        for u in units.itertuples():
            unit_rows.append({
                "unit": u.unit, "floor": int(u.floor), "wall": u.wall, "direction": u.wall_direction,
                "start": json_value(u.start_ft), "end": json_value(u.end_ft), "status": u.status, "note": u.note,
                "bedrooms": u.bedrooms or None, "baths": json_value(u.baths), "listed_sqft": json_value(u.listed_sqft),
                "drawn_sqft": json_value(u.drawn_sqft), "listed_fetched": u.listed_fetched or None,
                "rent": json_value(u.rent), "max_rent": json_value(u.max_rent), "available": u.available or None,
                "notes": [*issue_list(u.website_issues, "website"), *issue_list(u.model_notes, "model")]})
        details_file = BUILDINGS_DIR / f"{model_id}_details.json"
        details = json.loads(details_file.read_text(encoding="utf-8")) if details_file.exists() else {}
        buildings[model_id] = {"details": details, "walls": walls, "units": unit_rows}
        print(f"  {model_id}: {units['unit'].nunique()} units, {len(walls)} walls"
              f"{', details' if details else ''}")
    if not buildings:
        return None
    text = json.dumps({"buildings": buildings}, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(buildings), len(text)


# ---------------------------------------------------------------- 8. everything

def export(tiles, out_dir=OUT_DIR, with_annotations=False, with_units=False):
    """Rebuild out_dir (normally web/data/) for these tiles. Prints what it does and how big each file is."""
    start = time.perf_counter()
    if out_dir.exists():
        if not (out_dir / "manifest.json").exists() and any(out_dir.iterdir()):
            raise SystemExit(f"{out_dir} has files that weren't made by this script: not deleting it")
        shutil.rmtree(out_dir)                               # it only holds files made by this script
    (out_dir / "tiles").mkdir(parents=True)

    catalog = lookup.add_assessment(lookup.load_catalog(tiles), lookup.load_assessment())
    current_rows = catalog_rows(catalog, loading.DEFAULT_STATUSES)
    future_rows = catalog_rows(catalog, FUTURE_STATUSES)
    floor_data = floors.load_floor_data() if floors.FLOOR_COUNTS_FILE.exists() else None
    if floor_data is None:
        print("No floor data (data/floor_counts.csv, made by Notebook 7): buildings get no floor plans.")

    manifest_tiles = []
    table_rows = []
    total_bytes = 0
    for tile in tiles:
        tile_start = time.perf_counter()
        main_file = f"tiles/{tile}.bin.gz"
        model_ids, boxes, main_bytes = export_terrain_and_buildings(tile, out_dir / main_file)
        table_rows += building_table_rows("current", tile, model_ids, boxes, current_rows, floor_data)

        future_file = f"tiles/{tile}_future.bin.gz"
        future = export_buildings(tile, FUTURE_STATUSES, out_dir / future_file)
        future_bytes = 0
        if future is None:
            future_file = None
        else:
            future_ids, future_boxes, future_bytes = future
            table_rows += building_table_rows("future", tile, future_ids, future_boxes, future_rows)

        photo_file = f"tiles/{tile}.jpg"
        photo_bytes = export_photo(tile, out_dir / photo_file)

        manifest_tiles.append({"name": tile, "file": main_file, "future_file": future_file, "photo": photo_file})
        total_bytes += main_bytes + future_bytes + photo_bytes
        print(f"{tile}: {len(model_ids):6,} buildings  {main_bytes / 1e6:5.2f} MB   "
              f"future {future_bytes / 1e6:4.2f} MB   photo {photo_bytes / 1e6:4.2f} MB"
              f"   ({time.perf_counter() - tile_start:.1f} s)")

    columns = ["layer", "tile", "index"] + list(BUILDING_COLUMNS) + ["box"] + FLOOR_COLUMNS
    table_text = json.dumps({"columns": columns, "rows": table_rows}, separators=(",", ":"))
    (out_dir / "buildings.json").write_text(table_text, encoding="utf-8")
    total_bytes += len(table_text)
    print(f"\nbuildings.json: {len(table_rows):,} rows, {len(table_text) / 1e6:.1f} MB "
          f"(Cloudflare compresses JSON when sending it, to roughly a fifth)")

    # Street names and annotations need the tiles as the notebooks load them (terrain for the label heights,
    # buildings for windows.locate). From data/cache/, so this takes a few seconds.
    loaded_tiles = {tile: loading.load_tile(tile, ground="plain", merged=True) for tile in tiles}
    streets_file = "streets.json"
    street_result = export_streets(loaded_tiles, out_dir / streets_file)
    if street_result is None:
        streets_file = None
    else:
        print(f"streets.json: {street_result[0]:,} street name labels, {street_result[1] / 1e6:.2f} MB")
        total_bytes += street_result[1]

    annotations_file = None
    if with_annotations:
        if floor_data is None:
            print("Annotations need the floor data (Notebook 7): skipped.")
        else:
            annotations_file = "annotations.json"
            count, size = export_annotations(loaded_tiles, floor_data, out_dir / annotations_file)
            total_bytes += size
            print(f"annotations.json: {count} annotations. NOTE: anyone who can open the web page can read them.")
    else:
        print("Annotations not exported (they may be personal): add --with-annotations to include them.")

    buildings_file = None
    if with_units:
        result = export_units(out_dir / "building_units.json")
        if result is None:
            print("No data/buildings/*_units.csv: no building units exported.")
        else:
            buildings_file = "building_units.json"
            total_bytes += result[1]
            print(f"building_units.json: {result[0]} building(s), {result[1] / 1e6:.2f} MB. "
                  "NOTE: drawn from the buildings' own floor plates; anyone who can open the page can read it.")
    else:
        print("Building units not exported: add --with-units to include data/buildings/ (details, units, mismatches).")

    manifest = {
        "units": "feet; Z up; x east, y north; centered on loading.GLOBAL_ORIGIN",
        "texture_size": TEXTURE_SIZE,
        "tiles": manifest_tiles,
        "streets": streets_file,
        "annotations": annotations_file,
        "building_units": buildings_file,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"Total: {total_bytes / 1e6:.1f} MB in {out_dir}  ({time.perf_counter() - start:.0f} s)")


def main():
    parser = argparse.ArgumentParser(description="Export the 3D city for the web page (see the top of this file).")
    parser.add_argument("tiles", nargs="*", help="tile names, e.g. BOS_F_6 (default: all of config.BLOCK_TILES)")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output folder (default: web/data)")
    parser.add_argument("--with-annotations", action="store_true",
                        help="also export your annotations (they may be personal: anyone with the page can read them)")
    parser.add_argument("--with-units", action="store_true",
                        help="also export data/buildings/ (building details, unit positions, mismatches)")
    arguments = parser.parse_args()
    tiles = arguments.tiles or config.BLOCK_TILES
    missing = [tile for tile in tiles if not loading.tile_is_downloaded(tile)]
    if missing:
        raise SystemExit(f"Not downloaded into data/: {', '.join(missing)}")
    export(tiles, arguments.out, arguments.with_annotations, arguments.with_units)


if __name__ == "__main__":
    main()
