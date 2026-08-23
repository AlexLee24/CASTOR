# Source art

Three hand-drawn files, all authored, none derivable from the others:

| | |
|---|---|
| `castor-beaver-black.png` | line art for a light background |
| `castor-beaver-white.png` | the same figure for a dark one, **with the eye redrawn** |
| `castor-icon.png` | the app-icon composition — its own plate, rounded corners, heavier strokes, tighter crop |

A beaver reaching for a ring of stars, which is the whole name in one picture:
*castor* is Latin for beaver, and Castor is α Geminorum.

```bash
uv run assets/make_icons.py     # -> src/castorGUI/frontend/img/
```

Nothing under `frontend/img/` should be edited by hand. Redraw here, re-run,
commit both.

## Why the white one is drawn and not inverted

In the black art the eye is an outline with a small filled pupil. Invert that
and you get a white ring with a white blob inside it, which stops reading as an
eye. The white version fills the eye instead and keeps the pupil dark. It is an
artistic decision, and a script cannot make it.

The same goes for the icon: it is not the line art on a plate, it is drawn
heavier and cropped tighter, because a 32 px tab is not a page.

## What the script does add

Thickening, on the way down to the small sizes. No drawing survives that on its
own — below about 48 px the strokes fall under a pixel and the figure greys out
into a smudge whatever weight it was drawn at. The amount is tuned so the ring
of stars still reads as separate from the head at 32 px, which is the size a
browser asks for on a retina tab. The plate and its corner radius are resized
rather than thickened, so the corners stay the ones that were drawn.
