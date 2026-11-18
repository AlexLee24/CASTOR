# SLT + DZ936 on its first night back

The Andor DZ936 went back on SLT in Nov 2026 as a stand-in while the DU934P's
shutter is repaired. Until this night every number presets.json held for it was
Andor's brochure. 2026-11-10, AT2026afqt: 139 calibrated frames, 150 s in
g'r'i'z', 150 and 300 s in u', moon below the horizon throughout. The field rose
from airmass 1.64 to the meridian (1.107, ~15:45 UTC) and set to 4.9.

Frames, reduction and per-frame tables stay out of the repository
(`data/raw/slt_at2026afqt/`). The scripts are `reduce_slt_afqt.py` and
`analyze_slt_afqt.py`; the numbers are in `slt_dz936.py` and asserted by
`test_slt_dz936.py`.

## Extinction, separated from the weather

ZP = ZP0 − kX over 124 good frames, X < 3. PS1 DR2 references in g'r'i'z',
SkyMapper DR4 in u' (no colour terms).

| Band | k | rising only | setting only | fit rms | in presets.json |
|---|---:|---:|---:|---:|---:|
| u' | 0.443 | 0.381 | 0.433 | 0.024 | 0.44 |
| g' | 0.158 | 0.162 | 0.153 | 0.007 | 0.16 |
| r' | 0.071 | 0.062 | 0.073 | 0.005 | 0.07 |
| i' | 0.038 | 0.093 | 0.042 | 0.013 | 0.04 |
| z' | 0.051 | 0.082 | 0.052 | 0.014 | 0.05 |

Two branches observing the same airmass at different times would disagree if
the sky had drifted. They agree to within 0.01 in g'r' and 0.05 in u'i'z', so
the slope is extinction rather than drift. This is what SN2024ggi's
setting-only nights could not show. It is one night's worth.

## Sky, read noise, plate scale

| | u' | g' | r' | i' | z' |
|---|---:|---:|---:|---:|---:|
| sky, mag/arcsec², X < 1.6, astronomical night | 22.73 | 21.63 | 20.77 | 19.86 | 18.71 |
| what presets.json gave | 21.50 | 21.46 | 20.94 | 20.05 | 21.50 |

u' and z' had only the site-wide fallback, and z' was 2.8 mag too dark: 7.5×
too little sky. Both now carry this night's value. g'r'i' came from LOT on a
different sightline and still hold to within 0.2 mag.

Read noise is 5.92 e- (frame RMSNOISE). The u' 150 s frames carry only 6 e-/pix
of sky, and their local sky noise gives 5.7 e-. The brochure figure was 7.0. In
g'r'i'z' each pixel has another 7–8.5 e- of noise beyond sky Poisson and read
noise. Its cause is unknown, and CASTOR does not model it.

Every frame plate-solves to 0.790″/pix at 13.5 µm. The DU934P solved to
0.76″/pix at 13 µm. Both scales give SLT a focal length of 3.52 m, as does the
header's FOCALLEN of 3522.8 mm. presets.json had 3.414, which is f/8.4 × 0.406 m
from the site pages, so every SLT prediction used a pixel 3% too large.

## Noise model

Field stars present on every frame of one pier side, with each frame's
transparency divided out. Where the bins hold 25 or more stars, the
frame-to-frame SNR is 0.92–1.02 of what `calculate_single_snr` predicts from the
star's own flux and sky. The brightest stars level off at 0.4–0.85, which is a
per-frame floor of roughly 0.5% that CASTOR does not model. With only 8–9 frames,
each star's scatter is uncertain by about 25%, so the small bins are recorded
but not asserted on.

## Not in presets.json: the camera's band response

Measured counts above the atmosphere against CASTOR's prediction are u' 0.78,
g' 1.23, r' 1.20, i' 0.98, z' 0.62. presets.json keys a band's throughput by
telescope and holds a camera's QE as one number. Storing this response would
therefore move every DU934P prediction as well. QUESTIONS.md 19 has what it
would take. Until then, SLT + DZ936 is optimistic in source counts by about 1.6×
in z' and 1.3× in u'.

## Problems in the delivered frames

These are not CASTOR's, but anyone reducing these frames should know them:

* 12 i'/z' frames have bright stars erased. All are after the meridian flip, and
  all have the night's sharpest seeing (FWHM ≤ 2.26 px). The stars' pixels hold
  runs of repeated neighbouring values. No header records it.
* The WCS keys are renamed with a leading underscore (`_RVAL1`, `_C1_1`, ...).
* BUNIT says adu, but GAINCOR has been applied, so the pixels are e-.
* Two u' frames have no plate solution.

The supernova itself tests nothing here. Its aperture flux follows the frame's
FWHM (r = −0.96) because of host light.
