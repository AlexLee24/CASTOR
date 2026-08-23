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


#: Apple's required .iconset members: (filename, pixel size). The @2x entries
#: are what a Retina Dock actually samples — omit them and Big Sur silently
#: falls back to its own generic rounded-square plate behind an inset copy of
#: whatever size it could find, which is the "icon in a box" look this exists
#: to avoid. 16 px was missing from the previous approach entirely.
ICONSET_MEMBERS = (
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
)


def _desktop(source):
    """The platform icon containers build.spec points at.

    The .ico is written directly — Pillow's writer needs only the size list.
    The .icns is not: Pillow's own ICNS encoder skips 16 px and writes a single
    entry per byte-size with no @1x/@2x distinction, which is exactly the
    malformed shape that makes Big Sur+ distrust an icon and re-box it in a
    system-drawn plate. `iconutil` is the tool Apple's own icon compiler uses
    and is what actually settles that, which needs macOS and is why both output
    files are committed rather than built fresh every time.
    """
    import shutil, subprocess, tempfile

    DESKTOP.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert("RGBA")
    image.save(DESKTOP / "castor.ico",
               sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    if shutil.which("iconutil") is None:
        print("  iconutil not found (not macOS) — castor.icns left as committed")
        return

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "castor.iconset"
        iconset.mkdir()
        for name, size in ICONSET_MEMBERS:
            image.resize((size, size), Image.LANCZOS).save(iconset / name)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(DESKTOP / "castor.icns")],
            check=True,
        )


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
