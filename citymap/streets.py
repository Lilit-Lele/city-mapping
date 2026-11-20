"""Street names as 3D labels (Notebook 8, Steps 7-8).

The data: "Boston Street Segments (SAM System)", City of Boston, on Analyze Boston
(https://data.boston.gov/dataset/boston-street-segments-sam-system), license: Open Data Commons
Public Domain Dedication and License (PDDL). One line per street segment (usually one block),
with its name (PRE_DIR, ST_NAME, ST_TYPE, SUF_DIR) and a road class (CFCC).

It comes from the city's ArcGIS service in MA State Plane, US feet (EPSG:2249): the same system as
the 3D models, so no reprojection is needed, only the usual two shifts:

    State Plane feet  - (731,100, 2,902,900)   (the Metro Boston 3D origin)  = the 3D files' coordinates
                      - (52,500, 57,500)        (our global origin)           = the 3D view's coordinates

Typical use:
    streets.download_streets(tile_names)          # once: saves data/streets/street_segments.geojson
    segments = streets.load_streets()             # one row per segment, lines in view coordinates
    named = streets.join_streets(segments)        # one row per connected piece of a named street
    labels = streets.label_positions(tiles, named)
    streets.add_street_labels(plotter, streets.choose_labels(labels, classes=["highway", "major"]))
"""
import http.client
import json
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
import shapely

from citymap import loading

SERVICE_URL = "https://gisportal.boston.gov/arcgis/rest/services/SAM/Live_SAM_Address/FeatureServer/3/query"
DATASET_PAGE = "https://data.boston.gov/dataset/boston-street-segments-sam-system"
STREETS_DIR = loading.DATA_DIR / "streets"
STREETS_FILE = STREETS_DIR / "street_segments.geojson"
FIELDS = ["SEGMENT_ID", "PRE_DIR", "ST_NAME", "ST_TYPE", "SUF_DIR", "CFCC"]
PAGE_SIZE = 1000                       # segments per request (the service allows up to 2,000)

STREET_TYPES = {"ST": "St", "AVE": "Ave", "RD": "Rd", "SQ": "Sq", "PL": "Pl", "BLVD": "Blvd", "PKWY": "Pkwy",
                "HWY": "Hwy", "WAY": "Way", "LN": "Ln", "CT": "Ct", "TER": "Ter", "DR": "Dr", "PARK": "Park",
                "WHRF": "Wharf", "WHF": "Wharf", "ROW": "Row", "CIR": "Cir", "XING": "Crossing", "PLZ": "Plaza",
                "BRG": "Bridge", "TPKE": "Tpke", "EXPY": "Expy", "CTR": "Ctr", "ALY": "Aly"}
ROAD_CLASS_ORDER = ["highway", "major", "local", "other"]     # most important first


# ---------------------------------------------------------------- download (Step 7, once)

def download_box(tile_names, margin_ft=500.0):
    """The rectangle around the tiles, plus a margin, in State Plane feet: (x_min, y_min, x_max, y_max)."""
    bounds = np.array([loading.tile_grid_bounds(tile) for tile in tile_names])   # (left, right, bottom, top) each
    shift_x, shift_y = loading.STATE_PLANE_SHIFT
    return (bounds[:, 0].min() + shift_x - margin_ft, bounds[:, 2].min() + shift_y - margin_ft,
            bounds[:, 1].max() + shift_x + margin_ft, bounds[:, 3].max() + shift_y + margin_ft)


def fetch_json(url, attempts=5):
    """Download a URL and read it as JSON; try again (up to `attempts` times) if the connection breaks."""
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                return json.loads(response.read())
        except (OSError, http.client.HTTPException, json.JSONDecodeError):
            if attempt == attempts:
                raise
            time.sleep(2 * attempt)                    # wait a little longer each time


def fetch_street_features(box):
    """Ask the city's service for every segment touching the box. Out: a list of GeoJSON features.

    The service answers in pages of up to 2,000 segments; we ask again with resultOffset until done.
    """
    features = []
    while True:
        query = {"where": "1=1", "geometry": ",".join(f"{v:.0f}" for v in box),
                 "geometryType": "esriGeometryEnvelope", "inSR": 2249, "spatialRel": "esriSpatialRelIntersects",
                 "outFields": ",".join(FIELDS), "outSR": 2249, "orderByFields": "OBJECTID",
                 "geometryPrecision": 1,                       # coordinates to 0.1 ft: smaller download
                 "resultOffset": len(features), "resultRecordCount": PAGE_SIZE, "f": "geojson"}
        page = fetch_json(SERVICE_URL + "?" + urllib.parse.urlencode(query))
        features.extend(page["features"])
        if len(page["features"]) < PAGE_SIZE:          # a page that isn't full is the last one
            return features


def download_streets(tile_names, margin_ft=500.0):
    """Download the segments around the tiles and save them as data/streets/street_segments.geojson.

    Out: the number of segments. Only needed once (or to refresh the data).
    """
    features = fetch_street_features(download_box(tile_names, margin_ft))
    STREETS_DIR.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:2249"}},
                  "source": DATASET_PAGE, "license": "ODC PDDL (public domain)", "features": features}
    STREETS_FILE.write_text(json.dumps(collection), encoding="utf-8")
    return len(features)


# ---------------------------------------------------------------- read and convert (Step 7)

def full_name(properties):
    """ "PRE_DIR ST_NAME ST_TYPE SUF_DIR" -> e.g. "Federal St", "W Broadway". None if there's no name."""
    if not properties.get("ST_NAME"):
        return None
    street_type = properties.get("ST_TYPE") or ""
    parts = [properties.get("PRE_DIR"), properties["ST_NAME"].title(),
             STREET_TYPES.get(street_type, street_type.title()), properties.get("SUF_DIR")]
    return " ".join(part for part in parts if part)


def road_class(cfcc):
    """Census road code (CFCC) -> "highway" (A1x), "major" (A2x, A3x), "local" (A4x) or "other" (ramps, paths, ...)."""
    if not cfcc:
        return "other"
    return {"A1": "highway", "A2": "major", "A3": "major", "A4": "local"}.get(cfcc[:2], "other")


def to_view(coordinates):
    """State Plane feet (N, 2) -> 3D view coordinates (N, 2): subtract the Metro Boston shift, then our origin."""
    return np.asarray(coordinates, dtype=float)[:, :2] - loading.STATE_PLANE_SHIFT - loading.GLOBAL_ORIGIN[:2]


def segments_from_features(features):
    """GeoJSON features -> a table: segment_id, name, road_class, cfcc, line (shapely, view coordinates)."""
    rows = []
    for feature in features:
        geometry, properties = feature["geometry"], feature["properties"]
        if geometry is None:
            continue
        parts = geometry["coordinates"] if geometry["type"] == "MultiLineString" else [geometry["coordinates"]]
        for part in parts:
            rows.append({"segment_id": properties["SEGMENT_ID"], "name": full_name(properties),
                         "road_class": road_class(properties.get("CFCC")), "cfcc": properties.get("CFCC"),
                         "line": shapely.LineString(to_view(part))})
    return pd.DataFrame(rows)


def load_streets(path=STREETS_FILE):
    """Read the saved segments (download_streets) as a table, in view coordinates."""
    return segments_from_features(json.loads(path.read_text(encoding="utf-8"))["features"])


def join_streets(segments):
    """Join segments with the same name that touch into longer lines.

    Out: one row per connected piece: name, road_class (the most important of its segments), length_ft, line.
    Two streets with the same name in different places (not touching) stay separate rows.
    """
    rows = []
    for name, group in segments.dropna(subset=["name"]).groupby("name"):
        merged = shapely.line_merge(shapely.union_all(list(group["line"])))      # touching ends -> one line
        pieces = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        best_class = min(group["road_class"], key=ROAD_CLASS_ORDER.index)
        for piece in pieces:
            rows.append({"name": name, "road_class": best_class, "length_ft": piece.length, "line": piece})
    return pd.DataFrame(rows).sort_values("length_ft", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------- label positions (Step 7)

def terrain_height(tiles, x, y):
    """Ground elevation at (x, y) in view coordinates: a ray straight down onto the terrain. None if no terrain."""
    for parts in tiles.values():
        x_min, x_max, y_min, y_max = parts["terrain"].bounds[:4]
        if x_min <= x <= x_max and y_min <= y <= y_max:
            hit_points, hit_cells = parts["terrain"].ray_trace((x, y, 3000.0), (x, y, -500.0))
            if len(hit_points) > 0:
                return float(hit_points[0, 2])
    return None


def label_positions(tiles, named, spacing_ft=1000.0, min_length_ft=150.0):
    """Where the labels go: about one per spacing_ft of street, evenly spread; a short piece gets one in its middle.

    Pieces shorter than min_length_ft get no label (tiny stubs). Labels outside the terrain are dropped.
    Out: a table: name, road_class, length_ft (of its street piece), x, y, ground_ft.
    """
    rows = []
    for index, street in named[named["length_ft"] >= min_length_ft].iterrows():
        count = max(1, round(street["length_ft"] / spacing_ft))
        for i in range(count):
            point = street["line"].interpolate((i + 0.5) * street["length_ft"] / count)   # evenly along the line
            ground = terrain_height(tiles, point.x, point.y)
            if ground is not None:
                rows.append({"name": street["name"], "road_class": street["road_class"],
                             "length_ft": round(street["length_ft"]), "x": point.x, "y": point.y, "ground_ft": ground})
    return pd.DataFrame(rows)


def choose_labels(labels, classes=None, min_length_ft=0.0):
    """Only the labels of these road classes (None = all) on street pieces at least min_length_ft long (Step 8)."""
    chosen = labels[labels["length_ft"] >= min_length_ft]
    if classes is not None:
        chosen = chosen[chosen["road_class"].isin(classes)]
    return chosen


def add_street_labels(plotter, labels, height_above_ft=15.0, font_size=11, name="street_names"):
    """Draw the labels a little above the ground. They always face the camera, so they read from any angle.

    always_visible=False: a label is hidden when a building stands in front of it (less clutter).
    An empty table removes the labels.
    """
    if len(labels) == 0:
        plotter.remove_actor(name)
        return
    points = np.column_stack([labels["x"], labels["y"], labels["ground_ft"] + height_above_ft])
    plotter.add_point_labels(points, list(labels["name"]), font_size=font_size, text_color="#1d2a3a",
                             shape_color="#fff7d6", shape_opacity=0.8, show_points=False,
                             always_visible=False, name=name)
