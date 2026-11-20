# Boston 3D: map view, building. address search and estimated sunrays 

This folder is a complete static website. It shows the 15 Boston tiles in 3D in the browser and has the
tools to search and find building info, was inicially built in python notebook. 

- search
- the color menu
- future buildings
- street names and the names of the tallest buildings
- Saved: buildings and spots you save, kept in your browser
- the view check, the sun on a spot, and the whole wall colored by hours of sun

There is no server program: Cloudflare Pages (or any web server) only hands out these files, and all the
work happens in the visitor's browser.

```
web/
├── index.html      the page: the panels, buttons and styles, and which libraries to load
├── app.js          the main program: loads the data, draws the city, runs every button
├── rays.js         ray tests: "what does a line from here hit first?" (the view check, clicks)
├── sun.js          where the sun is at a given Boston date and time, and whether it reaches a spot
├── floors.js       floor numbers from a building's floor plan ("Floor ~19 of 60")
├── wall.js         the clicked wall as a grid of floors x columns, and its hours of sun
├── units.js        extra building details and apartment positions (Ora Seaport), and their mismatches
├── README.md       this file
└── data/           made by export_web.py, never edited by hand (see below)
    ├── manifest.json        the list of tiles and which files belong to each
    ├── buildings.json       one row per building: name, height, land use, floors, ...
    ├── streets.json         street name labels
    ├── annotations.json     only with --with-annotations; the page no longer reads it (see "Saved")
    ├── building_units.json  only if exported with --with-units (building details, units, mismatches)
    └── tiles/
        ├── BOS_F_4.bin.gz          buildings + ground heights of one tile
        ├── BOS_F_4_future.bin.gz   its approved / under-construction buildings (some tiles)
        └── BOS_F_4.jpg             its aerial photo, 2048 px
```

## 1. How the data gets here: Python → files → browser

The original data is 3.1 GB, which is too big for a web page. `export_web.py`, in the project folder, reads it with the same `citymap` code as the notebooks and writes small files into `web/data/`(about 38 MB):

| What | In the notebooks | On the web | How it gets smaller |
|---|---|---|---|
| Building shapes | PyVista meshes, 8-byte numbers | `tiles/*.bin.gz` | Each corner position is stored as a 2-byte whole number (about 2 cm precision). Corners shared by triangles are stored once. The file is gzipped. |
| Ground | a fine terrain mesh | a grid of heights every 10 ft, in the same file | The terrain is resampled to the grid. |
| Aerial photos | 5000 × 5000 px | 2048 × 2048 px JPEG | Scaled down. |
| Building info | the catalog + property assessment tables | `buildings.json` | Only the columns the page shows, plus each building's floor plan and bounding box. |
| Streets | `citymap.streets` labels | `streets.json` | Name, road class, length, position. |
| Annotations | `data/annotations/` | `annotations.json` | **Only with `--with-annotations`.** Not used by the page any more: it has its own Saved list instead. |

A `.bin.gz` tile file is our own simple format: 4 bytes giving the header's length, a JSON header (array
names, types, lengths, the tile's size in feet), then the raw number arrays one after another. `app.js`
(`readTileFile`) unzips it with the browser's built-in `DecompressionStream` and wraps the arrays without
copying them.

**When the data changes** (new tiles, new floor counts, new annotations), run the export again. It deletes
`web/data/` and rebuilds it. Nothing in `web/data/` should be edited by hand.

## 2. What happens when the page opens

1. **`index.html`** loads. Its *import map* tells the browser where the libraries are; they come from the
   jsdelivr CDN, nothing is installed:
   - **three.js 0.160.0**: 3D drawing with WebGL, plus the map-style mouse controls and the HTML labels.
   - **three-mesh-bvh 0.7.6**: makes ray tests fast. It sorts each tile's triangles into a tree of boxes,
     so one ray checks a few dozen triangles instead of hundreds of thousands.
2. **`app.js` → `main()`** reads `manifest.json` and `buildings.json`, then each tile:
   - `makeTerrain`: the height grid becomes a ground surface with the aerial photo on it.
   - `makeBuildings`: the 2-byte positions go straight to the graphics card, which scales them back to
     feet. Each corner remembers its building number, so one building can be recolored without touching
     the others.
   - `buildCollision` (rays.js): a second copy in normal floating-point numbers, with its box tree, used
     only for ray tests (clicks, view, sun). It is never drawn.
3. It then loads `streets.json` if the manifest lists it, draws the places saved in this browser, and starts drawing:
   `frame()` redraws only when something moved.

Everything is in feet with Z up, x east, y north, centered on the same origin as the notebooks
(`loading.GLOBAL_ORIGIN`), so a point from a notebook is the same point here.

## 3. What each part of the page does

### Search, colors, future buildings (Notebook 6)
- **Search** (`search`): looks in the building names and addresses of `buildings.json` and lists up to
  15 matches. Clicking one flies to it and highlights it.
- **Color** (`COLOR_CHOICES`, `recolor`): height classes, land use groups, ... as in Notebook 6's
  `STYLE`. Each building's corners get a new color; the shapes are not rebuilt.
- **Show future buildings**: shows or hides the approved / under-construction layer.
- **Clicking** (`pick` in rays.js): a ray from the camera through the mouse finds the first building or
  ground it hits. The ground counts too, so a click on a street does not select a building behind it.

### Labels and the Show section (Notebook 8, Steps 7-8)
- **Street names** are HTML labels pinned to 3D points (three.js `CSS2DRenderer`). Which ones show
  depends on *Only major streets* and *Min. street length*, as in the notebook.
- A label hides when a building stands in front of it (`checkHiddenLabels`). This is checked with one ray
  per label, after the camera stops moving.
- **Web-only choice:** names more than 9,000 ft from the camera are hidden too. Otherwise the overview is
  a wall of text. Change `streetMaxDistanceFt` in `LABEL_SETTINGS` (app.js) to adjust it.
- **Tallest buildings** puts name labels on the N tallest buildings.

### Saved (buildings and spots you save)
- Click a building (search for a name or an address, or click it on the map). The building box has
  **☆ Save building**. If you clicked a wall, it also has **☆ Save this spot**, which keeps the exact
  floor, wall and position. The page asks you for a name, and suggests the building's name.
- A saved spot is a magenta ball with its name. A saved building has its name over the roof.
- In the **Saved** list, click an entry to fly there. A spot also opens the spot tools exactly there.
  Use ✎ to rename an entry and × to remove it. Clicking a saved spot's ball also opens it.
- The **Saved** box under "Show" hides or shows the balls and names.
- **Saved places are kept in this browser only** (`localStorage`, key `boston3d.saved.v1`). Nothing is sent
  anywhere, so other visitors and your other devices don't see them, and clearing the browser's site data
  deletes them. A private window doesn't keep them after it closes.
- Buildings are remembered by their Model_ID, so saved places survive a re-export. If a building is no
  longer in the data, its entry stays in the list but is greyed out.
- The notebook's annotations (`data/annotations/annotations.json`) are separate and not shown here.

### Building details and apartments (units.js, today only Ora Seaport)
Data comes from `data/buildings/`, which is private and not in git:
- `<Model_ID>_details.json`, which you can edit by hand. It holds:
  - the name and other names;
  - the website link and the date the listing was fetched;
  - `positions_status`;
  - info lines and the building's notes.
- `<Model_ID>_units.csv`: one row per apartment and wall. Each row has:
  - the floor and the wall;
  - `start_ft` and `end_ft` (along the wall from its left end, seen from outside);
  - the status;
  - the listed size (with its fetch date) and the drawn size;
  - `website_issues` and `model_notes`.
- `<Model_ID>_walls.csv`: where each wall is.

**The building's website is the authority.** Its floor plates list every apartment. The 3D model only says
which way each wall faces and where along it a unit is. Ora's rows are drafted by
`data/buildings/scripts/ora_units.py`, and a re-run keeps the rows you marked `checked`.

**Checking the positions:** every position comes from one fit of the floor plates onto the model. If a
few corner units match reality, set `"positions_status": "checked"` in the details file, and every unit
counts as checked.

Ora's floor count (11) is in `data/annotations/floor_overrides.csv`, with a note that there may be more
floors.

On the page:
- **Clicking the building** shows its details: a link to the website to check the real, current info, the
  date of the listing fetch, the positions status, and notes marked by who disagrees:
  - **⚠ Website inconsistency** (highlighted): the website contradicts itself. Example: a listing's sq ft
    vs the unit's size on the floor plate.
  - **ℹ 3D model note** and **ℹ City data note**: the website is trusted, but the model is too coarse or
    the city names it differently. Examples: the model includes the hotel; the catalog calls it
    "Parcel K".
  - **? Not known**: nobody says. Examples: windows, possibly more floors, sizes of units not for rent.
  - **For rent**: how many apartments were for rent when the listing was fetched, and the rent range a
    month for each type (studio, 1 bed, 2 bed).
- **Clicking one of its walls** finds the apartment there:
  - The wall is matched by direction (within 25°) and distance (within 6 ft).
  - The floor comes from the floor plan.
  - The apartment is the one whose stretch of that wall holds the spot.
  - It then shows the unit number, its size (the website listing with its fetch date, or about X sq ft
    measured from the plate), whether it was for rent, its stretch of facade, the other walls of a corner
    unit, and that unit's own notes.
  - If it was for rent, it shows the rent a month and the date: *"available now (since 9/6/2026)"* if that
    date had passed when the listing was fetched, otherwise *"available from 12/14/2026"*. It also shows the
    page's hidden "Max Rent" column; the website doesn't say what that means. Otherwise it shows
    *"Not for rent on 2026-11-18"*.

**Rents go stale within days.** Before each deploy, fetch the listing again:
1. Save `https://oraseaport.com/availability` again as `data/buildings/ora_raw/availability.html`.
2. Run `data/buildings/scripts/parse_ora.py`, which writes `ora_availability.csv` with `rent` and `max_rent`.
3. Run `data/buildings/scripts/ora_units.py`, which copies rent, max rent and the available date into the units file.
4. Set `listing_fetched` in `<Model_ID>_details.json` to the new date.
5. Run `export_web.py --with-units` again.

### The spot: view and sun (Notebook 8, Step 9)
Clicking a **wall** (a face that is close to vertical) sets *the spot*: a point 2 ft in front of the wall,
like `windows.locate`. The Spot panel describes it with `floors.js` + `wall.js`, e.g. *"Floor ~19 of 60
(manual count, level estimated), south-facing wall (159°), about 5 ft from the wall's left end (wall ~60 ft wide)"*.

- **View check** (`viewCheck` in rays.js): level rays every 2° across the half the wall faces, up to
  2 miles. Each ray is:
  - **blocked**: it hits a building;
  - **open**: it reaches 2 miles without hitting anything, inside our data;
  - **unknown**: it leaves our 12 tiles first. There may be buildings out there that we don't have.
- **Sun** (sun.js): the sun's position every 10 minutes of the chosen day, using NOAA's formula, in Boston
  time with daylight saving. Each step is:
  - **night**: the sun is below the horizon;
  - **behind wall**: the sun is behind the wall, so the wall itself blocks it;
  - **shade**: a building blocks the sun ray (it is drawn in purple);
  - **sun?**: the ray leaves our data while still low, so a building outside our tiles might block it;
  - **sun**: direct sun.

  Hover over the timeline to see the sun ray of that moment.
- **Whole wall** (wall.js):
  - The wall is cut into cells: one row per floor (or ~12 ft bands without a floor plan) and ~10 ft
    columns.
  - The sun test runs for the center of every cell over the day.
  - The cells are colored from dark blue (no sun) to yellow (most sun).
  - The work is done in small batches so the page doesn't freeze.

`rays.js`, `sun.js` and `floors.js` are JavaScript copies of `citymap/rays.py`, `citymap/sun.py` and
`citymap/floors.py`. They were checked to give the same numbers as the notebooks. If you change the
method in one, change the other.

### Limits
- Only the 12 tiles have buildings. No trees.
- Floors and spots are approximate.
- On a curved facade, the web joins fewer wall pieces than `walls.py` does, so its column numbers can
  differ from the notebook's.

## 4. Running it locally

From the project folder:

```
.venv/bin/python export_web.py                 # (re)build web/data/
python3 -m http.server -d web 8000             # then open http://localhost:8000
```

Stop the server with **Ctrl+C**. Opening `index.html` directly as a file does **not** work, because
browsers block loading data files from `file://`.

To include the building details and apartments (`data/buildings/`), add `--with-units`. The apartment
positions are drawn from Ora's own floor plates, and the site's terms reserve its content. Publish them
only if you're comfortable with that, or after asking the owner.

## 5. Deploying to Cloudflare Pages

The `web/` folder is all that is needed: the page, the scripts and the data. The libraries come from the
CDN.

1. **Export without `--with-annotations`.** The page doesn't use `annotations.json` any more, and anyone
   who can open a public page could download it.

   ```
   .venv/bin/python export_web.py
   ```

2. **Upload the folder directly.** The first time:

   ```
   npx wrangler login
   ```

   Then, for the first deploy and every update after it:

   ```
   npx wrangler pages deploy web --project-name boston-3d
   ```

   Wrangler needs Node 18 or newer (`node -v`).

   Use this direct upload rather than connecting a GitHub repository: `web/data/` is gitignored, so a
   site built from Git would have no data.

3. **Size limits:** Pages allows 25 MiB per file and 20,000 files. The largest file here is
   `buildings.json` (~5.5 MB), and there are about 40 files.

Everything in `web/` is public once deployed, this README included.

**Before publishing,** check that the licenses of the 3D models, aerial photos and property data allow
redistribution. The street names are PDDL, which allows it.
