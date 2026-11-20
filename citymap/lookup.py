"""Connect the building table (catalog.csv) to the 3D buildings (Notebook 5, Step 2).

- load_catalog: all tiles' catalog.csv in one pandas table.
- building_locations: where each Model_ID is in the loaded 3D tiles (tile + position).
- get_building: one building's catalog row, by Model_ID.
- load_assessment, add_assessment: floors, land use and year built from the city's property data.
- building_lines: the text shown for a building (Notebook 5, Step 3).
- find_buildings: search by name or address (Notebook 6, Step 5).

The link between the two is Model_ID: it's a column in the catalog, and the name of each 3D model.
"""
import pandas as pd

from citymap import loading


def load_catalog(tiles):
    """Read the catalog.csv of every tile into one pandas DataFrame (one row per 3D model).

    In:  a list of tile names, e.g. config.BLOCK_TILES.
    Out: a DataFrame with all catalog columns plus "tile" (which file the row came from).
         Rows of every status are included (Current, History, ...): filter on "Status" if needed.
    """
    tables = []
    for tile in tiles:
        path = loading.DATA_DIR / tile / f"{tile}_BldgModels_OBJ" / "catalog.csv"
        table = pd.read_csv(path, encoding="utf-8-sig")   # utf-8-sig: skip the invisible BOM marker
        table["tile"] = tile
        tables.append(table)
    return pd.concat(tables, ignore_index=True)          # one table, rows numbered 0, 1, 2, ...


# The city's property assessment table (one row per parcel or condo unit). Only these columns are read:
# the file also has owner names and mailing addresses, which we don't need.
ASSESSMENT_FILE = loading.DATA_DIR / "fy2026-property-assessment-data_rev.csv"
ASSESSMENT_COLUMNS = {           # column in the file -> our name
    "PID": "PID",                # parcel ID, same number as the catalog's Parcel_ID
    "LU": "Land_Use_Code",       # short code: R1-R4 houses, A apartments, CM condo building, C commercial, E exempt...
    "LU_DESC": "Land_Use",       # e.g. "CONDO MAIN", "THREE-FAM DWELLING", "OFFICE CLS A"
    "RES_FLOOR": "Floors",       # number of floors; only filled for residential properties
    "YR_BUILT": "Year_Built",
}


def load_assessment():
    """Read the city's FY2026 property assessment table (Notebook 5, Step 3b), only the columns we use.

    Out: a DataFrame with PID, Land_Use_Code, Land_Use, Floors, Year_Built. One row per parcel (PID is unique).
    """
    table = pd.read_csv(ASSESSMENT_FILE, usecols=list(ASSESSMENT_COLUMNS))
    return table.rename(columns=ASSESSMENT_COLUMNS)


def add_assessment(catalog, assessment):
    """Add Land_Use_Code, Land_Use, Floors and Year_Built to every catalog row, by matching Parcel_ID to PID.

    In:  the catalog (load_catalog) and the assessment table (load_assessment).
    Out: a new DataFrame: the catalog with four more columns, empty where the parcel isn't found.
         Same rows in the same order. The values belong to the *parcel*: every 3D model standing
         on that parcel gets the same ones (e.g. a garage behind a 3-floor house also gets 3).
         Floors of 0 are treated as unknown.
    """
    with_parcel = catalog.copy()
    with_parcel["PID"] = with_parcel["Parcel_ID"].astype("Int64")     # 2100360000.0 -> 2100360000 (Int64 allows empty)
    joined = with_parcel.merge(assessment, on="PID", how="left")      # left join: keep every catalog row
    joined.loc[joined["Floors"] == 0, "Floors"] = None
    joined.loc[joined["Year_Built"] == 0, "Year_Built"] = None
    return joined.drop(columns="PID")


def building_locations(tiles):
    """Find where each building is in the loaded 3D tiles.

    In:  tiles = {tile name: dict from loading.load_tile(..., merged=True)}.
    Out: {Model_ID: (tile name, index)}. index is the building's position in that tile's
         "building_ids" list, which is also the number in cell_data["building_index"] of its triangles.
    """
    locations = {}
    for tile, parts in tiles.items():
        for index, model_id in enumerate(parts["building_ids"]):
            locations[model_id] = (tile, index)
    return locations


def get_building(catalog, model_id):
    """Return one building's catalog row (a pandas Series: column name -> value), or None if unknown.

    A few Model_IDs have several rows (Notebook 5, Step 2.4). Then the first "Current" row is
    returned, or the first row if none is Current.
    """
    rows = catalog[catalog["Model_ID"] == model_id]
    if len(rows) == 0:
        return None
    current_rows = rows[rows["Status"] == "Current"]
    if len(current_rows) > 0:
        return current_rows.iloc[0]          # iloc[0]: the first row, by position
    return rows.iloc[0]


def building_lines(row):
    """Return the text shown for one building, as a list of lines (Notebook 5, Steps 3 and 3b).

    In:  one catalog row (from get_building), after add_assessment (it needs Floors, Land_Use, Year_Built).
    Out: name; height and floors; type and use; land use and year built; status; tile and ID.
    """
    name = "(no name)" if pd.isna(row["Name"]) else row["Name"]
    use = "unknown" if pd.isna(row["StructUse"]) else row["StructUse"]
    floors = "not in city data" if pd.isna(row["Floors"]) else f"{row['Floors']:.0f}"
    land_use = "not in city data" if pd.isna(row["Land_Use"]) else row["Land_Use"]
    year = "not in city data" if pd.isna(row["Year_Built"]) else f"{row['Year_Built']:.0f}"
    return [
        name,
        f"Height: {row['Height_Ft']:.0f} ft   Floors: {floors}",
        f"Type: {row['StructType']}, use: {use}",
        f"Land use (parcel): {land_use}   Built: {year}",
        f"Status: {row['Status']}",
        f"Tile: {row['tile']}   ID: {row['Model_ID']}",
    ]


SEARCH_RESULT_COLUMNS = ["Model_ID", "Name", "Height_Ft", "Floors", "Land_Use", "tile"]


def find_buildings(catalog, locations, text):
    """Find the buildings whose Name contains `text` (Notebook 6, Step 5).

    In:  the catalog (after add_assessment), locations (building_locations), and the text to look for.
    Out: a DataFrame with SEARCH_RESULT_COLUMNS, tallest first, rows numbered 0, 1, 2, ...
         Empty if nothing matches.
    - Upper/lower case doesn't matter, and repeated spaces count as one ("90  OLIVER ST" matches "90 oliver st").
    - Only models that are in the 3D view (in locations) are returned, each Model_ID once.
    """
    search_text = " ".join(text.split()).lower()                    # "  Beacon   St " -> "beacon st"
    names = catalog["Name"].fillna("").str.split().str.join(" ").str.lower()   # the same cleanup for every name
    name_matches = names.str.contains(search_text, regex=False)     # regex=False: search the text as typed
    in_3d = catalog["Model_ID"].isin(list(locations))
    matches = catalog[name_matches & in_3d].drop_duplicates("Model_ID")
    matches = matches.sort_values("Height_Ft", ascending=False)
    return matches[SEARCH_RESULT_COLUMNS].reset_index(drop=True)
