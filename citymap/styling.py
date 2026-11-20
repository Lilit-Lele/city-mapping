"""Make a light "map style" ground image, like the gray street basemap of the ArcGIS reference map.

We start from BPDA's drawn groundplan (2011): beige blocks, gray streets, blue water, green parks.
Each pixel gets one of our own colors instead, chosen from what the pixel shows.
Used in Notebook 4, Step 6.
"""
import numpy as np
import pyvista as pv
from PIL import Image

from citymap import loading
from citymap.viewing import rgb

# The groundplan's own two main colors, as brightness (average of red, green, blue; 0 = black, 255 = white).
# Measured in Notebook 4, Step 6.2.
GROUNDPLAN_STREET_BRIGHTNESS = 176     # gray streets (176, 176, 176)
GROUNDPLAN_BLOCK_BRIGHTNESS = 226      # beige blocks (232, 232, 200)


def restyle_groundplan(image, colors):
    """Recolor a groundplan image.

    In:
        image   numpy array (height, width, 3) of the groundplan, values 0-255
        colors  dict with "land", "street", "water", "park" (color names or hex codes)
    Out: a new numpy array of the same size with our colors.

    How each pixel is colored:
        water (blue is clearly stronger than red)                  -> colors["water"]
        park  (green is stronger than both red and blue)           -> colors["park"]
        else: a mix between "street" (dark pixels) and "land" (bright pixels), by brightness
    """
    image = image.astype(np.float32)
    red, green, blue = image[..., 0], image[..., 1], image[..., 2]

    # 0 for street-gray pixels, 1 for block-beige pixels, in between for edges (keeps lines smooth)
    brightness = (red + green + blue) / 3
    mix = (brightness - GROUNDPLAN_STREET_BRIGHTNESS) / (GROUNDPLAN_BLOCK_BRIGHTNESS - GROUNDPLAN_STREET_BRIGHTNESS)
    mix = np.clip(mix, 0, 1)[..., None]           # [..., None]: one value per pixel, used for all 3 colors

    street = rgb(colors["street"]).astype(np.float32)
    land = rgb(colors["land"]).astype(np.float32)
    result = street + mix * (land - street)

    result[blue > red + 30] = rgb(colors["water"])
    result[(green > red + 8) & (green > blue + 8)] = rgb(colors["park"])
    return result.astype(np.uint8)


def map_image_path(tile, colors):
    """Where the recolored image for this tile and these colors is cached (data/cache/...jpg).

    The colors are part of the file name, so changing a color makes a new file automatically.
    """
    color_text = "-".join(colors[name].lstrip("#") for name in ["land", "street", "water", "park"])
    return loading.CACHE_DIR / f"{tile}__map_{color_text}.jpg"


def map_texture(tile, colors):
    """Return the recolored groundplan of a tile as a pv.Texture, ready to put on its terrain.

    The first time (for these colors) it recolors the groundplan and saves it in data/cache/ (about 1 s
    per tile). Later it just reads that file. The terrain must have texture coordinates for the
    groundplan, i.e. be loaded with loading.load_tile(tile, ground="groundplan").
    """
    path = map_image_path(tile, colors)
    if not path.exists():
        groundplan = np.asarray(Image.open(loading.ground_image_path(tile, "groundplan")).convert("RGB"))
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(restyle_groundplan(groundplan, colors)).save(path, quality=92)
    return loading.load_ground_texture(path)
