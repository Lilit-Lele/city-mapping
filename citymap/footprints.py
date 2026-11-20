"""Building footprints (ground outlines) (Notebook 6, Step 7).

Two sources:
- the tiles' DXF groundplans (load_footprints). About 5% don't match their 3D building (empty, or
  only one part of it), as Step 7 found.
- model_shape: the building's 3D model seen from above. Always matches the 3D building; used to
  check the DXF footprints.

About the DXF:

Each tile's groundplan DXF has a layer "Building_Footprints": one closed outline per building.
ArcGIS stored the building's catalog row on each outline (hidden "XRECORD" attributes), including
its Model_ID, so footprints are matched to 3D buildings by ID, not by position.

Reading a DXF is slow (up to about 1 minute per tile: the files are mostly contour lines and
pavement markings), so the footprints are read once and saved in data/cache/<TILE>__footprints.npz.
"""
import ezdxf
import numpy as np
import shapely

from citymap import loading

FOOTPRINT_LAYER = "Building_Footprints"


def dxf_path(tile):
    """Return the path of a tile's groundplan DXF file."""
    return loading.DATA_DIR / tile / f"{tile}_Groundplan_DXF" / f"{tile}_Groundplan_DXF.dxf"


def read_dxf_footprints(tile):
    """Read a tile's footprints from its DXF (slow). Coordinates are the file's own (not shifted).

    Out: {Model_ID: list of outlines}, each outline a numpy array of (x, y) corners, in feet.
         Outlines without attributes (about 1 in 6) are skipped: they can't be matched to a building.
    """
    document = ezdxf.readfile(dxf_path(tile))                        # the slow part
    outlines = document.modelspace().query(f'LWPOLYLINE[layer=="{FOOTPRINT_LAYER}"]')
    footprints = {}
    for outline in outlines:
        if not outline.has_extension_dict:                           # no attributes attached
            continue
        attributes = outline.get_extension_dict().dictionary.get("ESRI_Attributes")
        if attributes is None or "Model_ID" not in attributes:
            continue
        model_id = attributes.get("Model_ID").tags[0].value          # the XRECORD's single value
        corners = np.array(list(outline.get_points("xy")))
        footprints.setdefault(model_id, []).append(corners)          # a building may have several parts
    return footprints


def footprint_cache_path(tile):
    """Return the footprint cache file of a tile, e.g. data/cache/BOS_G_5__footprints.npz."""
    return loading.CACHE_DIR / f"{tile}__footprints.npz"


def save_footprint_cache(tile):
    """Read the DXF (slow) and save its footprints in one small file. Out: the file path.

    Stored like the building cache: all corners one after another ("points"), and per outline
    its Model_ID and number of corners, so load_footprints can cut them apart again.
    """
    model_ids = []
    corner_counts = []
    all_corners = []
    for model_id, outlines in read_dxf_footprints(tile).items():
        for corners in outlines:
            model_ids.append(model_id)
            corner_counts.append(len(corners))
            all_corners.append(corners)
    path = footprint_cache_path(tile)
    loading.CACHE_DIR.mkdir(exist_ok=True)
    np.savez(path, model_ids=np.array(model_ids), corner_counts=np.array(corner_counts),
             points=np.concatenate(all_corners) if all_corners else np.zeros((0, 2)))
    return path


def load_footprints(tile, origin=loading.GLOBAL_ORIGIN):
    """Return a tile's footprints, centered on origin like the 3D tiles: {Model_ID: list of (N, 2) arrays}.

    Reads the cache file; if there is none yet, reads the DXF first and writes it (slow, once).
    """
    path = footprint_cache_path(tile)
    if not path.exists():
        save_footprint_cache(tile)
    footprints = {}
    with np.load(path) as data:
        start = 0
        for model_id, count in zip(data["model_ids"], data["corner_counts"]):
            corners = data["points"][start:start + count] - origin[:2]     # same shift as every 3D point
            footprints.setdefault(str(model_id), []).append(corners)
            start += count
    return footprints


def model_shape(tiles, locations, model_id, crack_ft=1.0):
    """Return a building's 3D model seen from above, as one shapely shape (Polygon or MultiPolygon).

    In:  tiles, locations (lookup.building_locations), the Model_ID.
         crack_ft: gaps narrower than this between triangles are closed (they're modelling cracks).
    Out: the shape, centered like the 3D tiles. Use .area for its area.

    How: flatten every triangle of the model onto the ground (drop z), turn each into a 2D shape,
    and merge them all into one shape (union). Walls become flat lines when flattened (no area),
    so only roofs and floors count.
    """
    tile, index = locations[model_id]
    buildings = tiles[tile]["buildings"]
    its_triangles = np.where(buildings.cell_data["building_index"] == index)[0]
    corners_2d = buildings.points[buildings.regular_faces[its_triangles]][:, :, :2]   # (triangles, 3, x/y)

    flat_triangles = []
    for triangle in corners_2d:
        shape = shapely.Polygon(triangle)
        if shape.area > 0.01:                       # skip walls (they have no area seen from above)
            flat_triangles.append(shape)
    merged = shapely.union_all(flat_triangles)      # core: one shape covering all triangles
    # Close hairline cracks where the model's triangles don't quite meet: grow by crack_ft / 2, then
    # shrink back. "mitre" keeps sharp corners sharp.
    return merged.buffer(crack_ft / 2, join_style="mitre").buffer(-crack_ft / 2, join_style="mitre")

