"""Your own notes on spots of buildings ("my flat", "the office"), saved in a file (Notebook 8, Steps 5-6).

The file: data/annotations/annotations.json (kept out of git: it may contain personal places).
Each annotation stores the DESCRIPTION of the spot, not its 3D position:

    {"id": 1, "model_id": "BOS-P65JM-OO4A1-HYDGP", "floor": 19, "direction": "S", "column": 1,
     "wall_number": 1, "label": "my flat", "note": "...", "color": "#e0218a", "created": "2026-11-06T14:03:00"}

The 3D position is worked out again every time (windows.locate), so annotations keep working when
the floor data or the wall code changes.

Typical use:
    annotations.add_annotation(model_id, 19, "S", 1, "my flat", note="2 windows")
    annotations.list_annotations()                    -> a table
    annotations.update_annotation(1, note="...")      -> change any field except id and created
    annotations.delete_annotation(1)
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd
import pyvista as pv

from citymap import loading, windows

ANNOTATIONS_FILE = loading.DATA_DIR / "annotations" / "annotations.json"
FIELDS = ["id", "model_id", "floor", "direction", "column", "wall_number", "label", "note", "color", "created"]
CHANGEABLE = ["model_id", "floor", "direction", "column", "wall_number", "label", "note", "color"]
DEFAULT_COLOR = "#e0218a"      # magenta: stands out against the aerial photo and the wall colors


def load_annotations():
    """All annotations as a list of dicts (empty if there is no file yet)."""
    if not ANNOTATIONS_FILE.exists():
        return []
    return json.loads(ANNOTATIONS_FILE.read_text(encoding="utf-8"))


def save_annotations(annotations):
    """Write the whole list to the file (indented, so you can read and edit it by hand)."""
    ANNOTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS_FILE.write_text(json.dumps(annotations, indent=2, ensure_ascii=False), encoding="utf-8")


def add_annotation(model_id, floor, direction, column, label, note="", color=DEFAULT_COLOR, wall_number=1):
    """Add one annotation, save the file, and return the new annotation (a dict with its new id).

    wall_number: which of the walls facing `direction` (1 = the widest; see windows.locate).
    """
    annotations = load_annotations()
    new_id = max([a["id"] for a in annotations], default=0) + 1      # 1 more than the highest id in the file
    annotation = {"id": new_id, "model_id": model_id, "floor": int(floor), "direction": direction,
                  "column": column if isinstance(column, str) else int(column), "wall_number": int(wall_number),
                  "label": label, "note": note, "color": color,
                  "created": datetime.now().isoformat(timespec="seconds")}
    annotations.append(annotation)
    save_annotations(annotations)
    return annotation


def list_annotations():
    """All annotations as a table (one row each, columns in FIELDS order)."""
    return pd.DataFrame(load_annotations(), columns=FIELDS)


def find_annotation(annotations, annotation_id):
    """The annotation with this id from a list, or raise an error that says which ids exist."""
    for annotation in annotations:
        if annotation["id"] == annotation_id:
            return annotation
    raise KeyError(f"No annotation {annotation_id}. Existing ids: {[a['id'] for a in annotations]}")


def update_annotation(annotation_id, **changes):
    """Change fields of one annotation, e.g. update_annotation(1, note="new note"). Saves; returns it."""
    unknown = set(changes) - set(CHANGEABLE)
    if unknown:
        raise ValueError(f"Can't change {sorted(unknown)}. Changeable: {CHANGEABLE}")
    annotations = load_annotations()
    annotation = find_annotation(annotations, annotation_id)
    annotation.update(changes)
    save_annotations(annotations)
    return annotation


def delete_annotation(annotation_id):
    """Remove one annotation and save. Returns the removed annotation."""
    annotations = load_annotations()
    annotation = find_annotation(annotations, annotation_id)
    annotations.remove(annotation)
    save_annotations(annotations)
    return annotation


def place_annotations(tiles, locations, floor_data, annotations):
    """Work out each annotation's 3D point again (windows.locate).

    Out: a list of (annotation, spot) for the annotations that could be placed, and a list of
         (annotation, reason) for those that couldn't (e.g. the building isn't loaded, the floor is gone).
    """
    placed, problems = [], []
    for annotation in annotations:
        if annotation["model_id"] not in locations:
            problems.append((annotation, "building not in the loaded tiles"))
            continue
        spot = windows.locate(tiles, locations, floor_data, annotation["model_id"], annotation["floor"],
                              annotation["direction"], annotation["column"], annotation.get("wall_number", 1))
        if spot["point"] is None:
            problems.append((annotation, spot["description"]))
        else:
            placed.append((annotation, spot))
    return placed, problems


def add_annotation_markers(plotter, placed, name="annotations"):
    """Draw each placed annotation: a colored ball on the wall and its label above it.

    The actors are named name + "_markers" and name + "_labels", so they can be removed or replaced.
    """
    if not placed:
        plotter.remove_actor(name + "_markers")
        plotter.remove_actor(name + "_labels")
        return
    points = np.array([spot["point"] for annotation, spot in placed])
    colors = np.array([pv.Color(annotation["color"]).int_rgb for annotation, spot in placed], dtype=np.uint8)
    markers = pv.PolyData(points)
    markers.point_data["color"] = colors
    plotter.add_mesh(markers, scalars="color", rgb=True, point_size=16, render_points_as_spheres=True,
                     name=name + "_markers", pickable=False)
    plotter.add_point_labels(points + np.array([0.0, 0.0, 8.0]), [annotation["label"] for annotation, spot in placed],
                             font_size=12, bold=True, show_points=False, shape_color="white",
                             shape_opacity=0.85, always_visible=True, name=name + "_labels")


def nearest_annotation(placed, point, max_distance_ft=15.0):
    """The (annotation, spot) whose marker is closest to point, if within max_distance_ft; else None.

    Used for "click a marker": the click lands on the wall right behind the marker.
    """
    best, best_distance = None, max_distance_ft
    for annotation, spot in placed:
        distance = np.linalg.norm(spot["point"] - np.asarray(point))
        if distance <= best_distance:
            best, best_distance = (annotation, spot), distance
    return best
