"""Project settings that are shared by several notebooks. Change them here, in one place."""

# Tiles to show (Notebook 3, Step 5).
# Grid rule: letters go west -> east, numbers go north -> south (see notes/screenshots/tile_grid.png).
# Tiles listed here but not downloaded into data/ are skipped with a message.
TILES = [
    # Central block, 5 columns x 3 rows: Back Bay, downtown, South End, South Boston, Roxbury
    # (column J added later; the block stays a full rectangle, which rays.model_area relies on)
    "BOS_F_4", "BOS_G_4", "BOS_H_4", "BOS_I_4", "BOS_J_4",
    "BOS_F_5", "BOS_G_5", "BOS_H_5", "BOS_I_5", "BOS_J_5",
    "BOS_F_6", "BOS_G_6", "BOS_H_6", "BOS_I_6", "BOS_J_6",
    # Phase 1 tiles, northeast of the block (J_3 touches I_4 at one corner): East Boston, Logan
    "BOS_J_3", "BOS_K_3",
]

# Tiles used from Phase 3 on (Notebooks 5-6): only the central 5 x 3 block, without the two test tiles.
# TILES above stays as it is so Notebooks 3-4 still run the same.
# GLOBAL_ORIGIN (in loading.py) stays the center of BOS_J_3 even though J_3 isn't shown: changing it
# would invalidate the cache, and any fixed origin near the scene works.
BLOCK_TILES = [tile for tile in TILES if tile not in ("BOS_J_3", "BOS_K_3")]
