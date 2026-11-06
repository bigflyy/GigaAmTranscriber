"""Draw the app icon (idea A, "wave into lines", chosen by the owner on 2026-11-06).

Writes into gigaam_app/icons/:
    gigaam.ico  Windows: the EXE resource and the window icon (16, 20, 24, 32, 40, 48, 64, 128, 256 px)
    gigaam.png  Linux: the window icon (256 px)
    gigaam.svg  the master drawing, for editing or a Linux .desktop entry

The icon is a rounded blue tile: three sound bars on the left, three lines of text on the
right. Big sizes are the master drawing scaled down. Sizes up to 32 px have their own
drawings on the pixel grid (whole-pixel edges), because a scaled master turns into blur there.

Needs Pillow, which the app itself does not use:  pip install pillow
Run from the project root:  python tools/make_icon.py [--preview DIR]
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "gigaam_app" / "icons"

# Colors: the tile runs from light blue (top left) to deep blue (bottom right); the app's
# accent #2f6fe0 sits in the middle. Text lines are slightly see-through white.
TILE_TOP_LEFT = (0x4F, 0x8C, 0xF2)
TILE_BOTTOM_RIGHT = (0x1D, 0x52, 0xC2)
WHITE = (255, 255, 255, 255)
LINE_WHITE = (255, 255, 255, 230)

# Master drawing on a 256 grid: (x, y, width, height). Same numbers as the mockup page.
MASTER = {
    "size": 256,
    "tile": (12, 12, 232, 232), "tile_radius": 56,
    "bars": [(46, 100, 20, 56), (76, 70, 20, 116), (106, 88, 20, 80)],
    "lines": [(140, 84, 72, 18), (140, 119, 56, 18), (140, 154, 66, 18)],
    "round": True,
}

# Small sizes drawn by hand on whole pixels. Bars and lines are plain rectangles (rounded
# ends of 2 px wide shapes only smear); the tile keeps rounded corners.
SMALL = {
    16: {"tile": (0, 0, 16, 16), "tile_radius": 3.5,
         "bars": [(3, 6, 2, 4), (6, 3, 2, 10)],
         "lines": [(9, 4, 4, 2), (9, 7, 3, 2), (9, 10, 4, 2)]},
    20: {"tile": (0, 0, 20, 20), "tile_radius": 4.5,
         "bars": [(3, 8, 2, 4), (6, 5, 2, 10), (9, 7, 2, 6)],
         "lines": [(12, 6, 5, 2), (12, 9, 4, 2), (12, 12, 5, 2)]},
    24: {"tile": (1, 1, 22, 22), "tile_radius": 5,
         "bars": [(4, 9, 2, 6), (7, 6, 2, 12), (10, 8, 2, 8)],
         "lines": [(13, 7, 7, 2), (13, 11, 5, 2), (13, 15, 6, 2)]},
    32: {"tile": (1, 1, 30, 30), "tile_radius": 7,
         "bars": [(5, 12, 3, 8), (9, 8, 3, 16), (13, 11, 3, 10)],
         "lines": [(18, 11, 9, 2), (18, 15, 7, 2), (18, 19, 8, 2)]},
}

ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
SUPERSAMPLE = 8  # draw this many times larger, then shrink: smooth curves, crisp whole-pixel edges


def gradient(size):
    """A square image filled with the tile's diagonal gradient."""
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            pixels[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TILE_TOP_LEFT, TILE_BOTTOM_RIGHT))
    return image


def render(size):
    """The icon at one pixel size: the hand-drawn version if there is one, else the master scaled."""
    if size in SMALL:
        spec, unit, round_ends = SMALL[size], 1.0, False
    else:
        spec, unit, round_ends = MASTER, size / MASTER["size"], True
    big = size * SUPERSAMPLE
    k = unit * SUPERSAMPLE  # spec units to supersampled pixels

    def box(rect):
        x, y, w, h = rect
        return [x * k, y * k, (x + w) * k - 1, (y + h) * k - 1]

    # Tile: the gradient cut out by a rounded-rectangle mask.
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box(spec["tile"]), radius=spec["tile_radius"] * k, fill=255)
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    canvas.paste(gradient(big), (0, 0), mask)

    # Bars and lines go on their own layer so the see-through white of the lines blends once.
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for rect, color in [(r, WHITE) for r in spec["bars"]] + [(r, LINE_WHITE) for r in spec["lines"]]:
        radius = min(rect[2], rect[3]) / 2 * k if round_ends else 0
        draw.rounded_rectangle(box(rect), radius=radius, fill=color)
    canvas.alpha_composite(layer)
    return canvas.resize((size, size), Image.LANCZOS)


def master_svg():
    """The master drawing as SVG text, from the same numbers as the PNG renderer."""
    def hexcolor(rgb):
        return "#%02x%02x%02x" % rgb

    x, y, w, h = MASTER["tile"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">',
        '  <defs><linearGradient id="tile" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{hexcolor(TILE_TOP_LEFT)}"/>'
        f'<stop offset="1" stop-color="{hexcolor(TILE_BOTTOM_RIGHT)}"/></linearGradient></defs>',
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{MASTER["tile_radius"]}" fill="url(#tile)"/>',
    ]
    for rect, opacity in [(r, 1) for r in MASTER["bars"]] + [(r, round(LINE_WHITE[3] / 255, 2)) for r in MASTER["lines"]]:
        x, y, w, h = rect
        fade = "" if opacity == 1 else f' fill-opacity="{opacity}"'
        parts.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{min(w, h) / 2:g}" fill="#ffffff"{fade}/>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def preview(images, folder):
    """A sheet of every size blown up 8 times without smoothing, on light and dark, to check pixels."""
    zoom, pad = 8, 16
    width = sum(im.width * zoom + pad for im in images) + pad
    height = max(im.height for im in images) * zoom + 2 * pad
    sheet = Image.new("RGB", (width, height * 2), (240, 241, 244))
    sheet.paste((29, 30, 34), (0, height, width, height * 2))
    x = pad
    for im in images:
        big = im.resize((im.width * zoom, im.height * zoom), Image.NEAREST)
        for row in (0, height):
            sheet.paste(big, (x, row + pad), big)
        x += big.width + pad
    folder.mkdir(parents=True, exist_ok=True)
    sheet.save(folder / "icon-preview.png")
    return folder / "icon-preview.png"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", type=Path, help="also write icon-preview.png (sizes up to 64, zoomed) here")
    args = parser.parse_args()

    images = {size: render(size) for size in ICO_SIZES}
    OUT.mkdir(parents=True, exist_ok=True)
    # Pillow takes the other sizes from append_images when they match the requested sizes,
    # so the hand-drawn small ones go into the .ico as drawn, not shrunk from 256.
    images[256].save(OUT / "gigaam.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                     append_images=[images[s] for s in ICO_SIZES if s != 256])
    images[256].save(OUT / "gigaam.png")
    (OUT / "gigaam.svg").write_text(master_svg(), encoding="utf-8")
    print("wrote", OUT / "gigaam.ico", OUT / "gigaam.png", OUT / "gigaam.svg")
    if args.preview:
        print("preview", preview([images[s] for s in ICO_SIZES if s <= 64], args.preview))


if __name__ == "__main__":
    main()
