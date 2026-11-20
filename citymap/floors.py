"""Floors of a building: how many there are, where the count comes from, and where each floor is.

Made in Notebook 7, Step 1b, and moved here so later notebooks (07b, 08) can use it.
It reads two files:
    data/floor_counts.csv                 made by Notebook 7, Step 1a: one row per 3D model, with its ground,
                                          height and the city's floor count (if it passed the sanity check)
    data/annotations/floor_overrides.csv  your own floor counts for buildings you know (optional)

Where a floor count comes from, first match wins:
    "manual"      your override file
    "assessment"  the city's Property Assessment data (only counts that passed the check)
    "estimate"    from the height: floor 1 = 15 ft, then 12 ft per floor, leftover = roof
Floor *levels* are always approximate: the 3D models have no floors.

Typical use:
    floor_data = floors.load_floor_data()
    floors.floor_count(floor_data, model_id)          -> (62, "assessment")
    floors.floor_elevation(floor_data, model_id, 19)  -> (bottom, top) in ft
    floors.floor_label(floor_data, model_id)          -> "62 floors (assessment)"
"""
import pandas as pd

from citymap import loading

FLOOR_COUNTS_FILE = loading.DATA_DIR / "floor_counts.csv"
OVERRIDES_FILE = loading.DATA_DIR / "annotations" / "floor_overrides.csv"
OVERRIDE_COLUMNS = ["Model_ID", "name", "floors", "floor_height_ft", "first_floor_height_ft", "note"]

DEFAULT_SETTINGS = {
    "estimate_first_floor_ft": 15.0,     # estimate: floor 1 (lobby, shops)
    "estimate_typical_floor_ft": 12.0,   # estimate: every floor above it
    "taller_ground_floor": False,        # real counts: False = even split, True = floor 1 taller
    "ground_floor_ft": 15.0,             # ... how tall floor 1 is then
}


def read_floor_overrides():
    """Read your override file as {Model_ID: row}. Makes an empty file first if there is none."""
    if not OVERRIDES_FILE.exists():
        OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=OVERRIDE_COLUMNS).to_csv(OVERRIDES_FILE, index=False)
    overrides = {}
    for index, row in pd.read_csv(OVERRIDES_FILE).iterrows():
        overrides[row["Model_ID"]] = row
    return overrides


def load_floor_data(settings=None):
    """Load everything the floor functions need, once, into one dict.

    In:  settings (optional): a dict like DEFAULT_SETTINGS; missing keys use the defaults.
    Out: {"counts": the floor_counts table indexed by Model_ID, "overrides": {Model_ID: row}, "settings": dict}.
    Re-run it after editing the override file.
    """
    all_settings = dict(DEFAULT_SETTINGS)
    if settings is not None:
        all_settings.update(settings)
    counts = pd.read_csv(FLOOR_COUNTS_FILE, dtype={"Parcel_ID": str}).set_index("Model_ID")
    return {"counts": counts, "overrides": read_floor_overrides(), "settings": all_settings}


def count_with_rule(height, first, typical):
    """The estimate's floor count: floor 1 is `first` ft, every other floor `typical` ft; leftover = roof."""
    floors_above_first = int((height - first) // typical)   # // : divide and round down
    return max(1, 1 + floors_above_first)                   # at least 1 floor, even for a small shed


def split_by_rule(plan, first, typical):
    """Fill in a plan with the estimate: these two floor heights and the rule's count."""
    plan["first"] = first
    plan["typical"] = typical
    plan["count"] = count_with_rule(plan["height"], first, typical)


def split_evenly(plan, count, settings):
    """Fill in a plan for a known count: every floor = height / count, or a taller floor 1 (setting)."""
    plan["count"] = count
    if settings["taller_ground_floor"] and count > 1:
        plan["first"] = settings["ground_floor_ft"]
        plan["typical"] = (plan["height"] - plan["first"]) / (count - 1)   # the others share the rest
    else:
        plan["first"] = plan["height"] / count                             # every floor the same
        plan["typical"] = plan["height"] / count


def apply_manual(plan, override, settings):
    """Fill in a plan from one row of your override file, using whatever you filled in.

    only floors -> split evenly; floors + floor_height_ft -> as entered (floor 1 = first_floor_height_ft
    if given); floors + first_floor_height_ft -> floor 1 as entered, the rest shared; no floors -> the rule
    with your heights where given.
    """
    floors, typical, first = override["floors"], override["floor_height_ft"], override["first_floor_height_ft"]
    if pd.isna(floors):                               # no count: the rule, with your heights where given
        rule_first = settings["estimate_first_floor_ft"] if pd.isna(first) else float(first)
        rule_typical = settings["estimate_typical_floor_ft"] if pd.isna(typical) else float(typical)
        split_by_rule(plan, rule_first, rule_typical)
    elif not pd.isna(typical):                        # count and floor height: as entered
        plan["count"] = int(floors)
        plan["typical"] = float(typical)
        plan["first"] = float(typical) if pd.isna(first) else float(first)
    elif not pd.isna(first) and floors > 1:           # count and floor 1: the others share the rest
        plan["count"] = int(floors)
        plan["first"] = float(first)
        plan["typical"] = (plan["height"] - plan["first"]) / (plan["count"] - 1)
    else:                                             # only the count
        split_evenly(plan, int(floors), settings)


def floor_plan(floor_data, model_id):
    """Everything about one building's floors, as a dict.

    Out: {"ground": elevation of floor 1's bottom (terrain), "height": top of the model minus the ground,
          "count": number of floors, "first": height of floor 1, "typical": height of the other floors,
          "source": "manual", "assessment" or "estimate"}.
    """
    record = floor_data["counts"].loc[model_id]       # this model's row from data/floor_counts.csv
    settings = floor_data["settings"]
    plan = {"ground": float(record["ground_ft"]), "height": float(record["height_ft"])}
    if model_id in floor_data["overrides"]:           # 1. your override file
        apply_manual(plan, floor_data["overrides"][model_id], settings)
        plan["source"] = "manual"
    elif record["source"] == "assessment":            # 2. the city's count (passed the check)
        split_evenly(plan, int(record["assessment_floors"]), settings)   # 2.5 -> 2: the half floor is roof
        plan["source"] = "assessment"
    else:                                             # 3. the estimate rule
        split_by_rule(plan, settings["estimate_first_floor_ft"], settings["estimate_typical_floor_ft"])
        plan["source"] = "estimate"
    return plan


def floor_count(floor_data, model_id):
    """Return (number of floors, source), e.g. (62, "assessment")."""
    plan = floor_plan(floor_data, model_id)
    return plan["count"], plan["source"]


def floor_elevation(floor_data, model_id, floor_number):
    """Return (bottom, top) elevation of one floor, in ft (the same Z as the 3D view). Floor 1 = ground floor."""
    plan = floor_plan(floor_data, model_id)
    if floor_number < 1 or floor_number > plan["count"]:
        raise ValueError(f"Floor {floor_number} doesn't exist: this building has floors 1 to {plan['count']}.")
    if floor_number == 1:
        return plan["ground"], plan["ground"] + plan["first"]
    bottom = plan["ground"] + plan["first"] + (floor_number - 2) * plan["typical"]
    return bottom, bottom + plan["typical"]


def floor_at_height(floor_data, model_id, z):
    """Return the floor number at elevation z (ft, the 3D view's Z), or None if z is below floor 1 or above the top.

    The reverse of floor_elevation (Notebook 7b, Step 4: click a wall -> which floor).
    """
    plan = floor_plan(floor_data, model_id)
    for floor_number in range(1, plan["count"] + 1):
        bottom, top = floor_elevation(floor_data, model_id, floor_number)
        if bottom <= z < top:
            return floor_number
    return None


def floor_label(floor_data, model_id):
    """The text for labels: "62 floors (assessment)", "60 floors (manual)" or "~50 floors (estimate)"."""
    count, source = floor_count(floor_data, model_id)
    approximately = "~" if source == "estimate" else ""          # a guessed count gets a "~"
    return f"{approximately}{count} floors ({source})"
