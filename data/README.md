# Data: BPDA 3D Smart Model tiles

The tile files are **not** included in the project (they're large and are ignored by `.gitignore`). Download them yourself as described below.

## Where to download

Boston Planning (BPDA) 3D Smart Model downloads:
https://www.bostonplans.org/3d-data-maps/3d-smart-model/3d-data-download

Boston is cut into square **tiles**, each 5,000 × 5,000 ft (about 1.5 km), named like `BOS_J_3`. **Letters go west → east, numbers go north → south**: `BOS_K_3` is directly east of `BOS_J_3`, `BOS_J_4` directly south of it (checked for all our tiles in Notebook 3, Step 5). The download page's grid is saved in `notes/screenshots/tile_grid.png`.

For each tile, this project uses these downloads:

| Download | Folder it unzips to | Used for |
|---|---|---|
| **Building Model Collection OBJ** | `<TILE>_BldgModels_OBJ` | the buildings (one model per file), all statuses |
| **Terrain Mesh OBJ** | `<TILE>_TerrainMesh_2011_OBJ` | the ground surface |
| **Aerial Photo JPG** | `<TILE>_Orthophoto_2023` | the aerial photo on the ground (`ground="aerial"`) |
| **Groundplan JPG** | `<TILE>_Groundplan_2011_JPG` | the drawn map (`ground="groundplan"`), and the light map style in Notebook 4 |

Not used: Vector Groundplan DXF (`<TILE>_Groundplan_DXF`, maybe later), SketchUp SKP.

## Where to put the files

Make one folder per tile inside `data/`, named exactly like the tile, and unzip the downloads into it. The result must look like this (shown for `BOS_J_3`):

```
data/
  BOS_J_3/
    BOS_J_3_BldgModels_OBJ/
      catalog.csv              one row per building model (ID, address, height, status, project, ...)
      objz/
        BOS-00LNF-2UCVH-7HOOV_OBJ.zip    one small zip per model -- do NOT unzip these
        ...
      ModelFinder.htm, catalog_jsonp.js, catalog_resources/   (BPDA's own viewer + documentation)
    BOS_J_3_TerrainMesh_2011_OBJ/
      BOS_J_3_TerrainMesh_2011.obj
      materials.mtl
      materials_textures/BOS_J_3_Groundplan_2011.JPG
    BOS_J_3_Orthophoto_2023/
      BOS_J_3_Orthophoto_2023.jpg        5,000 x 5,000 px, 1 px = 1 ft
      BOS_J_3_Orthophoto_2023.jgw        world file: where the photo lies (Notebook 3, Step 1)
      ...jpg.aux.xml, ...jpg.xml         coordinate system and metadata
    BOS_J_3_Groundplan_2011_JPG/
      BOS_J_3_Groundplan_2011.JPG
      BOS_J_3_Groundplan_2011.jgw
      ...
  cache/                       made by the code; safe to delete (see the main README.md)
```

The folder and file names matter: `citymap/loading.py` finds files by these names (`GROUND_IMAGES` lists the image ones).

**Leave the per-building zips in `objz/` zipped.** The code reads each model straight out of its zip.

## Tiles currently used

Listed in `TILES` in `citymap/config.py`. A 4 × 3 block (F–I, 4–6) plus the two Phase 1 tiles, which touch the block only at one corner (J_3's southwest corner = I_4's northeast corner).

| Tile | Building models (all statuses) | Of which "Current" | Future (Board Approved + Under Construction) | Notes |
|---|---:|---:|---:|---|
| `BOS_F_4` | 101 | 98 | 0 | |
| `BOS_G_4` | 768 | 761 | 0 | |
| `BOS_H_4` | 1,774 | 1,662 | 11 | |
| `BOS_I_4` | 875 | 799 | 10 | |
| `BOS_F_5` | 1,290 | 1,108 | 14 | |
| `BOS_G_5` | 2,205 | 2,098 | 6 | |
| `BOS_H_5` | 1,541 | 1,309 | 18 | |
| `BOS_I_5` | 1,624 | 1,414 | 20 | |
| `BOS_F_6` | 3,685 | 3,588 | 13 | |
| `BOS_G_6` | 2,926 | 2,808 | 13 | |
| `BOS_H_6` | 1,856 | 1,647 | 9 | |
| `BOS_I_6` | 2,724 | 2,304 | 6 | |
| `BOS_J_3` | 2,336 | 2,142 | 10 | East Boston + Logan terminals. Its center is the project's global origin |
| `BOS_K_3` | 121 | 40 | 0 | Logan airport and water |

## Adding another tile

1. Download and unzip it into `data/<TILE>/` as above (all four downloads).
2. Add its name to `TILES` in `citymap/config.py`.
3. Run Notebook 3 or 4. The first load builds its cache in `data/cache/`.

Do **not** change `GLOBAL_ORIGIN` when adding tiles (see the main `README.md`).

## What's in the files (short version)

Details in Notebook 1, Step 1 and Notebook 3, Step 1.

- **Coordinates:** shifted Massachusetts State Plane ("Metro Boston 3D"), **US survey feet**, **Z is up**. Real State Plane = file coordinates + (731,100, 2,902,900) ft. The aerial photo's and groundplan's world files are in real State Plane.
- **Buildings:** each model is its own `.obj` inside its own zip. The file name is the model's unique **`Model_ID`**. `catalog.csv` adds the address (`Name`), type, height, **`Status`** (`Current`, `Board Approved`, `Under Construction`, `Complete`, `Approved Demo`, `History`; see the main README) and, for development projects, `Project_ID` and `ProjectLnk` (a bostonplans.org page).
- **Terrain:** one `.obj` per tile, from 2011. It covers exactly the same 5,000 × 5,000 ft square as the tile's images.
- **Documentation:** BPDA's data dictionary ships with each building download at `catalog_resources/bpda_datadict.js` (it's HTML text inside a JavaScript file). Also `data/3D_Data_Documentation.pdf`.
