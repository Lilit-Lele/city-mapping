# Boston 3D City Map (Phases 1–4)

An interactive 3D map of part of Boston, built in Python and Jupyter notebooks from the Boston Planning (BPDA) 3D Smart Model data.

- **Phase 1:** load two tiles of buildings and terrain; rotate, pan and zoom; click a building to see its ID; color a building by ID.
- **Phase 2:** aerial photo on the terrain, 14 tiles loading in a few seconds (cache + merged meshes), a light map style like the city's ArcGIS map, and future buildings (Board Approved / Under Construction) with an Existing / Future switch.
- **Phase 3:** the building table connected to the 3D buildings: click a building for its information (name, height, floors, land use, year built), highlight it, search by name or address and fly to it, color the map by height or land use, and a control panel under the view. Uses the 12 tiles of the central block.
- **Phase 4:** precise spots on buildings: floors (from the city's assessment data where possible), walls by compass direction, a window grid, "floor 19, south wall, leftmost" ↔ a 3D point (also by clicking a wall), your own saved annotations, and street names as 3D labels with show/hide controls.

Long-term goal: replicate the city's ArcGIS 3D map ([reference](https://experience.arcgis.com/experience/4e7509ea74174fff927cd83720862571/page/Future)) and add what it can't do, such as annotations pinned to precise spots ("19th floor of building X"). See the plans in `plan/`.

## Project layout

```
city-mapping/
  .venv/                         Python environment (not shared; recreate it with the steps below)
  data/                          tile data (not shared; see data/README.md)
    fy2026-property-assessment-data_rev.csv   the city's property data (Phase 3; see below)
    floor_counts.csv             one row per 3D model: ground, height, the city's floor count (Notebook 7)
    annotations/                 your files (gitignored): floor_overrides.csv, annotations.json (Phase 4)
    streets/                     street_segments.geojson, downloaded by Notebook 8 (Phase 4)
    cache/                       made automatically; safe to delete (see "Cache" below)
  notebooks/
    01_setup_inspect_view.ipynb      Phase 1, Steps 0-2: setup check, inspect the data, view one tile
    02_terrain_tiles_identify.ipynb  Phase 1, Steps 3-5: terrain + 2 tiles, click/highlight, performance
    03_aerial_and_tiles.ipynb        Phase 2, Steps 1-5: aerial photo, seams, cache, 14 tiles, merged meshes
    04_style_and_future.ipynb        Phase 2, Steps 6-7: reference map style, future buildings
    05_building_info.ipynb           Phase 3, Steps 1-4: building table, link to 3D, click for info, highlight
    06_search_and_filter.ipynb       Phase 3, Steps 5-9: search, color groups, footprints, control panel, performance
    07_floors_walls_windows.ipynb    Phase 4, Step 1: floor counts (assessment data, estimate fallback), floor levels
    07b_walls_windows.ipynb          Phase 4, Steps 2-4: walls by direction, window grid, locate / click a wall
    08_annotations_and_streets.ipynb Phase 4, Steps 5-9: annotations, street names, toggles, view check, sun exposure
  citymap/                       shared code used by the notebooks
    config.py                    which tiles to show (TILES; BLOCK_TILES from Phase 3)
    loading.py                   loading tiles, ground images, cache, merged meshes, global origin
    viewing.py                   adding tiles to a view, clicking, coloring and highlighting, camera views
    styling.py                   the light "map style" ground (recolored groundplan)
    lookup.py                    the building table: catalog, property data, search (Phase 3)
    footprints.py                building footprints from the DXF groundplans (Phase 3)
    floors.py                    floor counts and floor levels (Phase 4)
    walls.py                     a building's walls and the compass direction they face (Phase 4)
    windows.py                   window grid; locate a spot / describe a clicked point (Phase 4)
    annotations.py               your saved annotations (Phase 4)
    streets.py                   street data: download, convert, 3D labels (Phase 4)
  notes/
    arcgis_reference.md          checklist of what the reference map looks like
    future_buildings.md          Step 7 research: future buildings, the reference legend, options
    screenshots/                 reference map and tile grid screenshots
  requirements.txt
  README.md                      this file
  plan/                          phase_1_plan.md ... phase_4_plan.md
```

## Setup (from scratch)

You need **Python 3.11 or newer**, **VS Code** with the **Python** and **Jupyter** extensions, and the tile data.

1. **Get the data.** Download the tiles listed in `citymap/config.py` and unzip them into `data/` as described in [`data/README.md`](data/README.md).
   - For Notebooks 5–6, also put the city's **FY2026 property assessment** table into `data/` as `fy2026-property-assessment-data_rev.csv` (City of Boston open data, "Property Assessment"). Without it, Notebooks 5–6 stop at loading.

2. **Create the Python environment.** Run this in a terminal (VS Code: **Terminal → New Terminal**), inside the project folder:
   ```bash
   python3.11 -m venv .venv              # create the environment in .venv/
   source .venv/bin/activate             # use it in this terminal; the prompt now starts with (.venv)
   pip install -r requirements.txt       # install the libraries
   ```
   - To check it worked, run `which python`. It should print a path ending in `city-mapping/.venv/bin/python`.
   - `source .venv/bin/activate` only affects that one terminal window. Notebooks don't need it; they use the kernel you select in step 4.

3. **Open the project in VS Code** with **File → Open Folder** on the `city-mapping` folder itself (not a parent folder). VS Code then finds `.venv` on its own.

4. **Select the kernel** (the Python a notebook runs on). Open a notebook, click **Select Kernel** (top right), choose **Python Environments…**, then pick **`.venv`**.
   - If it's not listed, choose **Enter interpreter path…** and give it `<project folder>/.venv/bin/python`.
   - The top right should then show `.venv (Python 3.11.x)`.

5. **Run the notebooks in order**, each from top to bottom. After a kernel restart (**Restart** in the notebook toolbar), run the notebook from the top again.
   - The first run of Notebook 3 builds the cache (about 30 s for 14 tiles). Later runs read the cache.
   - The first run of Notebook 4 makes the map-style ground images (about 20 s) and the future-building cache (about 6 s).
   - The first run of Notebook 6 reads the footprints from the DXF files (about 7 minutes for 12 tiles, peak memory about 2.5 GB). Later runs read the cache in under a second.
   - Notebook 7 writes `data/floor_counts.csv`, which Notebooks 7b and 8 need. The first run of Notebook 8 downloads the street data (about 30–60 s, needs internet).
   - **Updating an existing environment for Phase 4:** run `pip install -r requirements.txt` again; it adds `pyproj`.

**Tested with:** Python 3.11.9, numpy 2.4.6, trimesh 5.2.0, pyvista 0.49.2, vtk 9.7.1, ipywidgets 8.1.9, pandas 3.1.1, ezdxf 1.4.5, shapely 2.2.0, pyproj 3.7.2, Pillow on macOS. `requirements.txt` doesn't pin versions, so a fresh install may get newer ones. If something breaks, install these versions.

### Libraries

| Library | Why |
|---|---|
| `trimesh` | reads the building `.obj` files; each building stays its own mesh |
| `pyvista[jupyter]` | interactive 3D views inside notebooks, picking (clicking), textures. `[jupyter]` adds the in-notebook viewer (trame) and `ipywidgets` |
| `numpy` | coordinate math |
| `pillow` | reads image sizes and pixels (aerial photo, groundplan) |
| `ipykernel` | lets VS Code run notebooks with the `.venv` Python |
| `pandas` | tables: the building catalog and the property data, searching and filtering (Phase 3) |
| `ezdxf` | reads the groundplan DXF files (building footprints, Phase 3 Step 7) |
| `shapely` | 2D shapes: a building's outline seen from above, areas, overlaps (Phase 3 Step 7); unfolded walls, joining streets (Phase 4) |
| `pyproj` | converts latitude/longitude ↔ MA State Plane; checks the coordinate conversion in Notebook 8, Step 7.1 (Phase 4) |

## How the notebooks show 3D

pyvista draws the 3D picture in Python and streams it into the notebook. pyvista calls this choice of display method a *backend*.

- **Notebook 1** uses `"trame"`. **Notebooks 2–6** use `"server"`: it only sends pictures, so the view updates in a few ms after a click or highlight, instead of about 0.4 s with `"trame"` (measured in Notebook 2, Step 5).
- Rotate with **left-drag**, zoom with **scroll**, pan with **Shift + left-drag**.
- **Click** a building (press and release without moving) to see its ID. Notebook 4 also has **Home view** (the reference map's start view, Boston Common from the south) and **Overview** (all tiles) buttons, and a **Future / Existing** switch under the view.
- **Notebooks 5–6:** clicking a building turns it red and shows its information in the view and in a box under it; clicking the ground clears it. Notebook 6 has a control panel under its last view (search, color menu, future buildings).
- Only one 3D view is live at a time. Each view cell closes the previous one with `pv.close_all()`. In Notebook 6, every cell that changes colors makes a **new view under itself** (`show_view()`, 3–4 s), so the older views stop responding.

**If cells run without errors but no 3D view appears:**
1. Restart the kernel and run all cells again.
2. Still nothing? Run **Developer: Reload Window** from the Command Palette (Cmd+Shift+P). This happened once right after switching kernels.
3. Fallback: cell 0.4 in Notebook 1 opens the view in a separate desktop window. Close the window to get the notebook back.

**If VS Code shows "No version of module @jupyter-widgets/output is registered":** VS Code couldn't load the `ipywidgets.Output` box. Notebooks 2 and 3 use it for the click printout; the 3D view and clicking still work, only that box stays empty. Notebooks 4–6 use `ipywidgets.HTML` boxes instead, which don't have this problem.

## Coordinates, units and the global origin

- **Source coordinates:** the files are in **Massachusetts State Plane (EPSG:2249), in US survey feet**, but *shifted* ("Metro Boston 3D coordinates", about 50,000 / 56,000 instead of the real ~780,000 / ~2,960,000).
- **The shift** (found in Notebook 3, Step 1 from the aerial photo's world file, checked against `catalog.csv`'s latitude/longitude within about 3 ft):
  **real State Plane = file coordinates + (731,100, 2,902,900) ft.** It's `loading.STATE_PLANE_SHIFT`. Use it to place anything given in real coordinates or by latitude/longitude.
- **Up axis:** **Z is up** in the data and in pyvista, so no axes are swapped.
- **Units:** we **keep feet** everywhere. 1 unit in the 3D view = 1 ft. (1 US survey foot = 0.3048006 m.)
- **Global origin:** `GLOBAL_ORIGIN = (52,500, 57,500, 0)` in `citymap/loading.py`, the center of tile `BOS_J_3`. It's subtracted from every point of every tile while loading.
  - **Why:** graphics cards store coordinates with only about 7 significant digits. Centering the scene near (0, 0, 0) keeps fine detail exact, which future window-level annotations will need.
  - **Z isn't shifted**, so Z stays "elevation in feet".
  - **Keep it fixed.** Every tile must use the same origin to line up, and the cache files store it (a cache made with another origin is rebuilt). To go back to file coordinates, add `GLOBAL_ORIGIN`.
- **Tile grid** (Notebook 3, Step 5.1): tiles are 5,000 × 5,000 ft. **Letters go west → east, numbers go north → south.** `loading.tile_grid_bounds(tile)` computes any tile's square from its name; checked against all 14 tiles.

## Ground images

Each tile has two images that fit the terrain exactly (Notebook 3, Steps 1–2): the **2023 aerial photo** and the **2011 drawn groundplan**, 5,000 × 5,000 px = 1 px per foot, each with a world file (`.jgw`) saying where it lies. `load_tile(tile, ground=...)` puts one on the terrain:

| `ground` | What you see |
|---|---|
| `"aerial"` | the 2023 aerial photo |
| `"groundplan"` | BPDA's drawn map: beige blocks, gray streets, blue water |
| `"plain"` | one color, no image |
| `"map"` *(Notebook 4 only)* | the groundplan recolored into a light gray basemap like the reference (`styling.map_texture`) |

## The building table (Phase 3)

**The catalog.** Each tile's `catalog.csv` has one row per 3D model. `lookup.load_catalog(config.BLOCK_TILES)` reads all 12 into one pandas table: **21,369 rows**, 45 columns plus `tile`. Useful columns:

| Column | What |
|---|---|
| `Model_ID` | the model's ID = the name of its 3D file. **The key** that links the table to the 3D view |
| `Name` | address or building name. Not unique, sometimes empty: search it, but identify buildings by `Model_ID` |
| `Status` | `Current`, `History`, `Board Approved`... (see "Future buildings"); 19,596 rows are `Current` |
| `StructType` | `Building`, `Wall`, `Dock`, `Bridge`... About 8,150 models are walls |
| `StructUse` | almost always empty, so not useful |
| `Height_Ft`, `Gnd_El_Ft` | height and ground elevation, in feet |
| `Centr_X_Ft`, `Centr_Y_Ft` | center, in the file coordinates (checked against the 3D models: median 1 ft apart) |
| `Parcel_ID` | the land parcel the model stands on: links to the property data |
| `GoogleLnk` | a Google Maps link |

**Link to 3D:** `lookup.building_locations(tiles)` gives `{Model_ID: (tile, index)}` for every loaded model (19,591), so `tiles[tile]["building_ids"][index]` is that model. Every model has a catalog row. A few IDs have several rows (one 3D file holding several buildings); `lookup.get_building` then returns the first `Current` row.

**The property data** (`data/fy2026-property-assessment-data_rev.csv`, the city's assessment table) adds **floors, land use and year built**. `lookup.add_assessment` joins it on `Parcel_ID` = `PID`; 11,217 of 11,473 existing buildings match.
- **Privacy:** the file also has owners' names and mailing addresses. `lookup.load_assessment` reads **only** `PID`, `LU`, `LU_DESC`, `RES_FLOOR` and `YR_BUILT`; nothing else is ever loaded.
- The values belong to the **parcel**: every model on a parcel shows the same ones.
- **Floors exist only for residential buildings** (7,054 of 11,473; office towers have none).
- Land-use codes used for coloring: `R1`–`R4` houses, `A` apartments, `CM` condo building, `RL` residential land, `RC` mixed, `C`/`CC`/`CL` commercial, `E`/`EA` exempt (public, schools, churches, hospitals), `I` industrial.

**Footprints** (Notebook 6, Step 7): each tile's groundplan DXF has a `Building_Footprints` layer with one outline per building, tagged with its `Model_ID`. 99% of buildings have one, but **about 5% don't match their 3D building** (e.g. the Boston Public Library, the State House), so they're not drawn. `footprints.model_shape` computes a building's outline from its 3D model instead. Drawing an outline in the view was tried and dropped (hidden by walls on the ground, confusing on top).

## Floors, walls and windows (Phase 4)

> **Estimates:** the 3D models have no floors and no windows. Floor **counts** come from the city where possible; floor **levels** and window positions are always approximate. In the text, `~` marks an estimated number.

**Floor counts** (Notebook 7, Step 1a; `citymap/floors.py`). Every count has a **source**; the first that applies wins:

| Source | Where it comes from |
|---|---|
| `manual` | your file `data/annotations/floor_overrides.csv` (columns `Model_ID, name, floors, floor_height_ft, first_floor_height_ft, note`; fill in what you know) |
| `assessment` | the city's **FY2026 Property Assessment** data: `RES_FLOOR` of the parcel's record (joined `Parcel_ID` = `PID`; for a condo building, its main `CM` record). The condo units (`CD`, found by `GIS_ID`) and their `CD_FLOOR` are only summarized in Notebook 7 as a cross-check, not used for the count |
| `estimate` | from the model's height: floor 1 = 15 ft, then 12 ft per floor; the leftover is roof |

- **Sanity check:** a city count is used only if it gives **8–25 ft per floor** (height ÷ floors). Counts outside that are **flagged** in `floor_counts.csv` (`check` column) and the estimate is used instead. Three counts pass at 21–25 ft/floor but look too low (Custom House, Fenway Triangle, 500 Atlantic); add override rows for them if you know better.
- Result for the 12 tiles' buildings: about **6,100 assessment**, **5,400 estimate**, plus your manual rows. Office towers usually have no `RES_FLOOR`, so they get estimates.
- **Floor levels:** a real count is split **evenly** over the height (`taller_ground_floor=True` in the settings makes floor 1 15 ft and splits the rest). Floor 1 starts at the **ground**.
- **The ground** is the **terrain under the building's center** (a ray straight down), not the catalog's `Gnd_El_Ft`, which is often wrong: 5–10 ft too low downtown and up to ~110 ft too low on hills (tile F_6).
- `data/floor_counts.csv` (made by Notebook 7, Step 1a): `Model_ID, Parcel_ID, StructType, LU, assessment_floors, ground_ft, height_ft, ft_per_floor, check, source, data_year`.
- **Privacy:** as in Phase 3, only ID, land-use and floor columns of the assessment file are read; no owners or mailing addresses, and no individual units are listed.

**Walls** (Notebook 7b, Step 2; `citymap/walls.py`): vertical triangles (normal's up part under 0.3) → normals made to point **outward** (count ray crossings) → neighbors facing within **15°** of the first face grouped into a wall. Each wall gets a **true compass bearing** (map grid bearing + **0.34°**, checked against the catalog's latitude/longitude: +0.26° median) and one of 8 labels (N, NE, … NW). Walls narrower than **20 ft** are **minor** (kept, but no window grid). A curved facade is split into pieces of up to ~30°.

**Window grid** (Step 3; `citymap/windows.py`): rows = floors; columns of about **10 ft**, adjusted to fill the wall exactly; a cell is kept only where the wall really is (its middle inside the wall's outline). **Left/right are as seen by someone standing outside, facing the wall** (south wall: leftmost = west; north wall: leftmost = east). A cell is an **approximate window position**, not a real window.

**Describing a spot** (Step 4): `windows.locate(tiles, locations, floor_data, model_id, 19, "S", "leftmost")` → a 3D point 2 ft in front of the wall plus *"Floor ~19 of 60 (manual count, level estimated), south-facing wall (159°), about 5 ft from the wall's left end (wall ~60 ft wide)"*. If several walls face that way at that floor, the widest is used and the others are listed (`wall_number=2` picks the next). `windows.describe_point(...)` does the reverse, for clicks.

## Annotations (Phase 4)

Saved in **`data/annotations/annotations.json`** (gitignored by the existing `data/*/` rule: it may contain personal places). A JSON list; each annotation stores the **description** of its spot, not 3D coordinates, so it stays on "floor 19, south wall" when the floor data or code changes. The 3D point is recalculated with `windows.locate` on every run.

```json
{"id": 1, "model_id": "BOS-P65JM-OO4A1-HYDGP", "floor": 19, "direction": "S", "column": "leftmost",
 "wall_number": 1, "label": "my flat", "note": "2 windows", "color": "#e0218a", "created": "2026-11-06T14:03:00"}
```

| Field | Meaning |
|---|---|
| `id` | number, used to edit or delete |
| `model_id` | the building |
| `floor` | floor number (1 = ground floor; level estimated) |
| `direction` | wall direction: N, NE, E, SE, S, SW, W, NW |
| `column` | which ~10 ft strip of the wall from the left (seen from outside); the description says it as a distance, or `"leftmost"`, `"rightmost"`, `"center"` |
| `wall_number` | which of the walls facing that way (1 = widest). Added to the plan's fields so a spot on a second wall stays there |
| `label`, `note`, `color` | text in the view, longer note (shown when you click the marker), marker color |
| `created` | date and time it was added |

Add one in code (`annotations.add_annotation(...)`) or in Notebook 8's map: click a wall, check the description, type a label, **Save annotation**. Click a marker to read its note. The file can also be edited by hand.

## Street names (Phase 4)

| | |
|---|---|
| Dataset | **Boston Street Segments (SAM System)**, City of Boston, https://data.boston.gov/dataset/boston-street-segments-sam-system |
| License | **Open Data Commons PDDL** (public domain) |
| Downloaded | by Notebook 8, Step 7.2 from the city's ArcGIS service, only the 12 tiles plus 500 ft (about 6,060 segments), into `data/streets/street_segments.geojson` |
| Coordinates | MA State Plane, US feet (EPSG:2249): **the same as the 3D data**; only the two usual shifts are subtracted (`streets.to_view`) |
| Road class | `CFCC`: A1x → highway, A2x/A3x → major, A4x → local, others (ramps, paths) → other |

- **Checks:** the conversion against the catalog's latitude/longitude with `pyproj` (7.1), and against the building footprints: 0.5% of street points fall inside a building at the true position vs 12–13% when moved by 40 ft (7.4).
- Segments with the same name that touch are joined; about **one label per 1,000 ft** of street, **15 ft above the terrain**. Labels face the camera and hide behind buildings.
- **Clutter controls** (Step 8): annotations, street names, only major streets (default), a minimum street length (default 300 ft), names of the N tallest buildings; checkboxes and sliders under the view, or the `DISPLAY` settings.

## Cache

`data/cache/` holds processed tiles so they load fast (Notebook 3, Step 4). **Safe to delete at any time**; files are rebuilt when needed.

| File | What | Made by |
|---|---|---|
| `<TILE>__Current.npz` | terrain + existing buildings, as numpy arrays, with the origin | `loading.load_tile(...)` |
| `<TILE>__Board-Approved+Under-Construction.npz` | the same for future buildings (one file per status choice) | `load_tile(..., statuses=...)` |
| `<TILE>__map_<colors>.jpg` | recolored groundplan; the colors are in the file name, so new colors make new files | `styling.map_texture` |
| `<TILE>__footprints.npz` | the building footprints from the tile's DXF (a few hundred KB) | `footprints.load_footprints` |

- `loading.clear_cache()` deletes all `.npz` files; `loading.clear_cache(["BOS_J_3"])` only those of the listed tiles. Old `map_*.jpg` files can just be deleted by hand.
- The cache is about 255 MB (14 tiles, future buildings and footprints). `clear_cache` also deletes footprint files; rebuilding them takes about 7 minutes.

## Adding tiles

1. Download and unzip the tile into `data/<TILE>/` (see `data/README.md`). Find tile names on the grid in `notes/screenshots/tile_grid.png`.
2. Add its name to `TILES` in **`citymap/config.py`**. Notebooks 3 and 4 skip tiles in the list that aren't downloaded, with a message.
3. Run the notebook. The first load builds the tile's cache (a few seconds per tile, more for dense downtown tiles).
4. If the new tiles are far from the others, you may want to move the camera (`start_view` in Notebook 4's style cell, or the camera in Notebook 3, 5.6). Don't change `GLOBAL_ORIGIN`.

## Shared code: `citymap/`

**`loading.py`**

| Name | What it does |
|---|---|
| `DATA_DIR`, `CACHE_DIR` | paths to `data/` and `data/cache/` |
| `GLOBAL_ORIGIN`, `STATE_PLANE_SHIFT` | the scene origin and the State Plane shift (see above) |
| `DEFAULT_STATUSES` | which models to load by default: `{"Current"}` |
| **`load_tile(tile, ground, statuses, merged)`** | **the main entry point**: terrain (with texture coordinates), ground texture, buildings, `building_ids`; uses the cache. Use `merged=True` |
| `read_catalog(tile)` | `catalog.csv` as `{Model_ID: row}` |
| `tile_grid_bounds(tile)`, `tile_is_downloaded(tile)` | a tile's square from its name; whether its files are in `data/` |
| `ground_image_path`, `image_bounds`, `add_texture_coordinates`, `load_ground_texture` | ground images (Notebook 3, Steps 1–3) |
| `merge_buildings`, `building_arrays` | merged meshes (below) |
| `clear_cache(tiles=None)` | delete cache files |
| `load_building_meshes`, `to_pyvista_blocks`, `load_buildings`, `load_terrain` | the Phase 1 functions (Notebooks 1–2) |

*Fixed in Phase 3:* `load_building_meshes` skipped a model when the **last** of its catalog rows had another status (2 models in BOS_I_6). It now loads a model if **any** of its rows has a wanted status. The BOS_I_6 cache was rebuilt.

**`viewing.py`**: `add_tiles` (terrain + buildings into a view, with lighting options), `add_status_buildings` (buildings colored by Status, e.g. future ones), `add_outlines` (thin lines on building edges), `enable_building_click`, `color_building`, `building_center`, `go_to_view`, `rgb`. New in Phase 3:

| Name | What it does |
|---|---|
| `highlight_building(tiles, locations, model_id, color)` / `undo_highlight(tiles, saved)` | paint one building and put exactly its old colors back; other colors stay |
| `color_buildings(tiles, model_ids, color)` | paint every building in a list of IDs (groups, coloring by height or land use) |
| `reset_building_colors(tiles, color)` | every building back to one color |
| `building_view(tiles, locations, model_id)` | a camera view that looks at one building from the south-southwest |
| `show_text_panel(plotter, lines)` / `clear_text_panel(plotter)` | the white information panel in the view |

All of them change colors in place: call `plotter.render()` afterwards (once: two quick redraws can leave the older picture in VS Code).

**`lookup.py`** (Phase 3)

| Name | What it does |
|---|---|
| `load_catalog(tiles)` | all tiles' `catalog.csv` in one DataFrame, plus `tile` |
| `load_assessment()`, `add_assessment(catalog, assessment)` | floors, land use and year built from the property data (only those columns are read) |
| `building_locations(tiles)` | `{Model_ID: (tile, index)}` for the loaded 3D models |
| `get_building(catalog, model_id)` | one building's row (the first `Current` one) |
| `building_lines(row)` | the lines of text shown for a building |
| `find_buildings(catalog, locations, text)` | search names: case and extra spaces ignored, only models in the view, tallest first |

**`footprints.py`** (Phase 3): `load_footprints(tile)` (`{Model_ID: outlines}` from the DXF, cached), `read_dxf_footprints`, `dxf_path`, and `model_shape(tiles, locations, model_id)` (a building's 3D model seen from above, as a shapely shape).

**`styling.py`**: `restyle_groundplan` (recolor a groundplan image), `map_texture` (recolored, cached texture for a tile).

**`config.py`**: `TILES` (all 14 downloaded tiles; Notebooks 3–4) and `BLOCK_TILES` (the central 4 × 3 block without the test tiles J_3 and K_3; Notebooks 5–8).

**`floors.py`** (Phase 4, Notebook 7)

| Name | What it does |
|---|---|
| `load_floor_data(settings=None)` | reads `floor_counts.csv` and your overrides: `{"counts", "overrides", "settings"}`. Pass this `floor_data` to the functions below |
| `floor_count(floor_data, model_id)` | `(62, "assessment")` |
| `floor_elevation(floor_data, model_id, n)` | `(bottom, top)` of floor n, in the view's Z (ft) |
| `floor_at_height(floor_data, model_id, z)` | the reverse: which floor is at elevation z (None outside) |
| `floor_label(floor_data, model_id)` | `"62 floors (assessment)"`, `"~50 floors (estimate)"` |
| `floor_plan`, `read_floor_overrides`, `count_with_rule`, `split_evenly`, `split_by_rule`, `apply_manual` | the details; `DEFAULT_SETTINGS` holds the estimate heights and the taller-ground-floor option |

**`walls.py`** (Phase 4, Notebook 7b, Step 2; moved there in Step 4)

| Name | What it does |
|---|---|
| **`find_walls(tiles, locations, floor_data, model_id)`** | `(mesh, walls)`: a table, widest first: `direction`, `bearing`, `width_ft`, `bottom_ft`, `top_ft`, `area_sqft`, `triangles`, `label_point`, `minor`. Remembered per building for the session |
| `WALL_SETTINGS` | vertical limit 0.3, same direction 15°, grid → true north 0.34°, minor below 20 ft, labels from 50 ft |
| `compass_bearing`, `compass_label`, `direction_from_bearing`, `COMPASS_LABELS`, `COMPASS_WORDS` | directions ↔ bearings ↔ labels |
| `color_walls`, `add_wall_labels`, `add_direction_legend`, `WALL_COLORS` | drawing |
| `wall_mesh`, `triangle_geometry`, `vertical_triangles`, `make_outward`, `count_crossings`, `triangle_neighbors`, `group_into_walls`, `describe_wall`, `wall_of_triangle` | the steps |

**`windows.py`** (Phase 4, Notebook 7b, Steps 3–4)

| Name | What it does |
|---|---|
| **`locate(tiles, locations, floor_data, model_id, floor, direction, column, wall_number=1)`** | description → dict with `point` (2 ft in front of the wall), `description`, `choice` (when several walls face that way), and the details |
| **`describe_point(tiles, locations, floor_data, model_id, point)`** | 3D point (a click) → the same dict, or why it isn't a wall spot |
| `window_grid`, `wall_frame`, `wall_point`, `column_layout`, `walls_facing`, `pick_wall`, `choose_cell`, `spot_text` | the grid and the words |
| `grid_lines`, `add_chosen_cell`, `wall_view`, `cell_corners` | drawing; a camera in front of a wall |
| `GRID_SETTINGS` | column width 10 ft, grid 0.5 ft and markers 2 ft in front of the wall |

**`annotations.py`** (Phase 4, Notebook 8): `add_annotation`, `list_annotations`, `update_annotation(id, **changes)`, `delete_annotation(id)` (each saves the file at once), `load_annotations` / `save_annotations`, `place_annotations` (3D points via `locate`, plus a list of those that couldn't be placed), `add_annotation_markers`, `nearest_annotation` (for clicks on markers).

**`streets.py`** (Phase 4, Notebook 8): `download_streets(tile_names, margin_ft)` (once), `load_streets()`, `join_streets(segments)`, `label_positions(tiles, named, spacing_ft, min_length_ft)`, `choose_labels(labels, classes, min_length_ft)`, `add_street_labels(plotter, labels)`, plus `to_view`, `full_name`, `road_class`, `terrain_height`, `download_box`, `fetch_street_features`.

**`rays.py`** (Notebook 8, Step 9.1): `build_locators(tiles)` (one ray search structure per tile, ~1 s), `first_hit(locators, tiles, start, end)` (the first building on a line), `model_area(tile_names)` and `distance_to_edge(area, start, direction)` (where our data ends), `ray_direction(bearing, elevation)` (true bearings), `view_check(locators, tiles, area, spot)` (a fan of rays: blocked / open / unknown), `add_view_rays`. Settings in `RAY_SETTINGS`.

**`sun.py`** (Notebook 8, Step 9.2): `sun_position(when, latitude, longitude)` (NOAA's formula, no library), `sun_steps(day, ...)`, `sunrise_sunset(day, ...)`, `exposure(locators, tiles, area, spot, steps)` (sun / sun? / shade / behind wall / night per step), `hours(timeline)`, `timeline_html(timeline)`, `wall_sun_hours` and `add_wall_hours` (the whole wall colored by hours of sun). Settings in `SUN_SETTINGS`.

**Web versions** (`export_web.py` at the project root, run by hand, converts the 12 tiles into small files; the generated `web/data/` and `web_*/data/` folders are gitignored):
- `web/`: the page to publish (how it works and how to deploy it: `web/README.md`). Notebook 6 plus Notebook 8: street names, tallest building names and the show/hide controls (Steps 7-8), your annotations read-only (Steps 5-6), the clicked spot in words from the floor data ("Floor ~19 of 60, south-facing wall (159°), about 5 ft from the wall's left end"), and Step 9 for any wall or annotation: view check, sun for any date, the whole wall colored by hours of sun per floor. `rays.js`, `sun.js`, `floors.js` and `wall.js` mirror `rays.py`, `sun.py`, `floors.py` and the window grid. Ray tests use the `three-mesh-bvh` library (from the CDN). Data: `export_web.py` (writes `web/data/`), plus `--with-annotations` to include your annotations (**anyone who can open the page can read them**).
- `web_n6/`: the older page, Notebook 6 only (search, color menu, future buildings, click a building). Data: `export_web.py --out web_n6/data`.
- Every export also writes each building's floor plan (from `data/floor_counts.csv` and your overrides) into `buildings.json`, and the street labels into `streets.json` (if the street data was downloaded).

The notebooks import it with `from citymap import ...` after adding the project folder to Python's search path in their first cell. `%autoreload 2` picks up edits to `citymap/` without restarting the kernel.

### Merged meshes

With VTK 9.7, creating thousands of separate meshes gets slower the more already exist (Notebook 3, Step 4), so 14 tiles with one mesh per building were too slow. With `merged=True`, **all buildings of a tile are one mesh**, and each triangle has a number saying which building it belongs to:

triangle → `buildings.cell_data["building_index"]` → `building_ids[index]` → `Model_ID`

Clicking and coloring by ID work through this lookup (`viewing.py`). Each triangle's color is in `cell_data["color"]`.

## Future buildings

Every tile's `catalog.csv` has a `Status` column, and the download includes the 3D model of every listed building, whatever its status (Notebook 4, Step 7; details in `notes/future_buildings.md`):

| Status | Meaning | Shown |
|---|---|---|
| `Current` | existing | yes |
| `Board Approved` | approved, not built yet | Notebook 4, green `#267300` |
| `Under Construction` | being built | Notebook 4, pink `#ed7894` |
| `Complete` | recently finished, not yet in `Current` | no |
| `Approved Demo` | still standing, approved for demolition | no (so they're missing from the Existing view, and correctly absent from the Future view) |
| `History` | already gone | no |

The colors are the reference map's legend (read from its public settings on arcgis.com); the reference uses the same BPDA data. Future buildings are drawn on top of today's (`Current`) city. Buildings a project replaces are usually `Approved Demo`, which isn't loaded, so old and new rarely overlap.

## Known limitations

- **Today's city is incomplete:** the 191 "Approved Demo" buildings (still standing) and the 49 "Complete" buildings (recently finished) aren't shown, because only `Current` is loaded (options A+ and B in `notes/future_buildings.md`).
- **The map stops at the tile edges.** The reference covers the whole city. J_3 and K_3 only touch the main block at one corner.
- **No 3D trees or shadows**, which the reference has (street labels came in Phase 4). Trees aren't in our data; shadows were too coarse with pyvista (Notebook 4, 6.8).
- **First turn stutters:** the first time each tile comes into view, its ground image is sent to the graphics card (a few frames of up to about 0.8 s). After that, frames take a few ms.
- **Buildings start 4–9 ft below the 2011 terrain** (Notebook 2, Step 3.2). Normal practice for 3D models; it may also come from a different vertical reference level (not confirmed). The hidden part is underground. Left as is, by decision.
- **A "model" isn't always one building.** It can be part of a building (chimneys are separate small models), several attached buildings, a wall, a dock or a bridge.
- **Names aren't unique.** `Name` is an address, often repeated or empty, and a few `Model_ID`s appear twice in a catalog. Use `Model_ID` as the ID.
- **Tile edges:** some J_3 models (Logan terminals) reach past the tile edge, where no terrain is loaded.
- **Building information has gaps:** floors only for residential buildings, `StructUse` almost always empty, many walls and some buildings without a name, and property values are per parcel, not per building.
- **About 5% of the DXF footprints are wrong or empty**, so footprints aren't drawn.
- **Future buildings can't be clicked** (only today's buildings are connected to clicks).
- **A new view takes 3–4 s**, mostly recomputing the building outlines (Notebook 6, Step 9). Computing them once would bring it to about 1 s (proposed, not built).
- **Floors and windows are approximate.** The models have neither: floor levels come from an even split of the height (or the estimate rule), window columns are a 10 ft grid. Office towers mostly have no floor count in the assessment data, so theirs are estimates (`~`). Wall directions are measured from the model, not estimated.
- **Many small walls:** every building splits into dozens of walls (roof boxes, notches, pieces of curves); walls under 20 ft are "minor" and get no grid. A curved facade is several walls a few degrees apart; `locate` says which one it chose.
- **Street labels hide behind buildings** and are placed every ~1,000 ft, so a short street can show no label from some angles. Labels are drawn for streets in our 12 tiles plus 500 ft only.
- **View check and sun exposure (Notebook 8, Step 9) only know our 12 tiles:** rays that leave them are marked "unknown" / "sun?" instead of open / sun. No trees; the sun formula has no refraction (the first and last minutes of the day can be off).

## Performance (14 tiles)

From Notebook 3, Step 5.8 and Notebook 4, on this Mac:

| Measurement | Result |
|---|---|
| Scene size | 21,772 buildings, about 4 million triangles |
| Load 14 tiles, first time (builds cache) | about 32 s |
| Load 14 tiles from cache | about 3.4 s (aerial), about 3 s (map style) |
| Draw one frame | about 2–5 ms |
| Pick (find the clicked building) | about 23 ms |
| Peak memory (whole notebook) | about 2.6 GB |

Phase 1 (2 tiles, one mesh per building): load about 3.5 s, about 3 ms per frame, peak memory about 510 MB.

**Phase 3** (12 tiles, 19,591 buildings, 2.1 million building + 1.6 million terrain triangles; Notebook 6, Step 9):

| Action | Time |
|---|---|
| Load catalog, property data and 12 tiles from cache | about 4 s |
| Search | 15–25 ms |
| Highlight one building (no redraw) | under 1 ms |
| Click or go to a building (with redraw) | 25–30 ms |
| Color the whole map (height, land use) | about 90 ms |
| Draw one frame | about 2 ms |
| A new view | 3–4 s (2.6 s of it the building outlines) |

**Phase 4** (measured without a display; frame times with labels are measured in Notebook 8, Step 8.2):

| Action | Time |
|---|---|
| `find_walls` for one building (first time; then remembered) | 0.01–0.04 s (test buildings) |
| `locate` / `describe_point` once the walls are known | under 0.05 s |
| Download the street data (once) | about 40 s |
| Join streets and place ~2,000 labels | about 0.4 s |
