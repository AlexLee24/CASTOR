# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""Resize the hand-drawn art into the files the frontend serves.

    uv run assets/make_icons.py

Pillow and scipy are declared inline rather than added to the project: this runs
when the drawing changes, which is roughly never, and neither library has any
business being installed to calculate an exposure time.

All three sources are authored, and none is derivable from another:

  castor-beaver-black.png   line art for a light background
  castor-beaver-white.png   the same figure for a dark one, with the eye redrawn
                            — inverting the black one turns an outlined pupil
                            into a white blob inside a white ring, which stops
                            reading as an eye
  castor-icon.png           the app-icon composition: its own plate, rounded
                            corners, heavier strokes and a tighter crop

So this script only ever resizes. The one thing it adds is thickening, and only
because no drawing survives it: below about 48 px the strokes fall under a pixel
and the figure greys out into a smudge whatever weight it was drawn at.
"""
import numpy as np
from PIL import Image
from pathlib import Path
from scipy import ndimage

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "src" / "castorGUI" / "frontend" / "img"
DESKTOP = HERE / "desktop"

LOGO_HEIGHT = 900

#: Thickening, in source pixels, as a function of the target size. Tuned by eye
#: against a browser tab: at 32 px this is the point where the ring of stars
#: still reads as separate from the head instead of merging into it.
THICKEN = 1600


def _trim(alpha, pad=0.02):
    ink = alpha > 16
    cols, rows = np.nonzero(ink.sum(axis=0))[0], np.nonzero(ink.sum(axis=1))[0]
    margin = int(max(np.ptp(cols), np.ptp(rows)) * pad)
    return (max(0, cols.min() - margin), max(0, rows.min() - margin),
            cols.max() + margin, rows.max() + margin)


def _logo(source, destination):
    """Trim to the drawing and scale. Transparency and colour are left alone."""
    image = Image.open(source).convert("RGBA")
    body = image.crop(_trim(np.array(image)[..., 3]))
    width = round(body.width * LOGO_HEIGHT / body.height)
    body.resize((width, LOGO_HEIGHT), Image.LANCZOS).save(destination)


def _icon(source, destination, size):
    """Scale the app icon, thickening its strokes on the way down.

    The plate and its rounded corners ride along in the resize; only the ink is
    thickened, so the corner radius stays the one that was drawn rather than
    swelling shut at small sizes.
    """
    image = Image.open(source).convert("RGBA")
    plate, ink_dark = image.getchannel("A"), 255 - np.array(image.convert("L"))
    ink = (ink_dark * (np.array(plate) > 16)).astype(np.float32)

    thickness = round(THICKEN / size)
    if thickness > 1:
        ink = ndimage.grey_dilation(ink, size=(thickness, thickness))

    scaled_plate = plate.resize((size, size), Image.LANCZOS)
    scaled_ink = Image.fromarray(ink.astype(np.uint8), "L").resize((size, size), Image.LANCZOS)

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(image.convert("RGB").resize((size, size), Image.LANCZOS), (0, 0), scaled_plate)
    black = Image.new("RGBA", (size, size), (17, 17, 17, 0))
    black.putalpha(scaled_ink)
    out.alpha_composite(black)
    out.putalpha(scaled_plate)
    return out.save(destination)


def _desktop(source):
    """The platform icon containers build.spec points at.

    Written out rather than letting PyInstaller convert a PNG at build time:
    that path needs Pillow installed wherever the build runs, and this way a
    Windows build gets the right .ico without anyone having to think about it.
    Regenerating the .icns needs macOS — Pillow shells out to iconutil — which
    is why both are committed.
    """
    DESKTOP.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert("RGBA")
    image.resize((1024, 1024), Image.LANCZOS).save(DESKTOP / "castor.icns")
    image.save(DESKTOP / "castor.ico",
               sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    _logo(HERE / "castor-beaver-black.png", OUT / "castor-logo-black.png")
    _logo(HERE / "castor-beaver-white.png", OUT / "castor-logo-white.png")
    _icon(HERE / "castor-icon.png", OUT / "favicon-32.png", 32)
    _icon(HERE / "castor-icon.png", OUT / "apple-touch-icon.png", 180)
    _desktop(HERE / "castor-icon.png")

    for path in sorted(OUT.iterdir()) + sorted(DESKTOP.iterdir()):
        with Image.open(path) as image:
            print(f"  {path.name:<24} {image.size[0]}x{image.size[1]}  "
                  f"{path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
