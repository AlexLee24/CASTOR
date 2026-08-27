# Lulin observations

Real photometry from the telescope this calculator is actually for.

**What is here now:** 123 calibrated LOT/SOPHIA science frames sit in
`../raw/`, not in this directory — 2 GB of them, over 18 nights from 2025-09-29
to 2026-02-15, in g'r'i' on the AT/SN2025wny and ZTF25abnjznp fields. Alongside
them `../raw/ps1/` holds the Pan-STARRS DR2 reference photometry queried for
each field, and `../raw/lulin_web/` the filter curves and datasheets downloaded
from the observatory site. All of it is ignored. What came out is in
`validation/lulin.py`, and `validation/test_lulin.py` checks the preset against
it. Drop anything further in here.

Everything else in `validation/` compares CASTOR against another model. This is
the only reference that compares it against the sky, and it is the only one that
can say whether the Lulin profile in `presets.json` is right — the FORS2 profile
turned out to be a plausible-looking fudge that only worked in one filter, and
nothing has checked Lulin's at all. All five of its filters carry
`filter_transmission` 0.9 and three share the same bandwidth, which is what
placeholder values look like.

Those frames carried everything the list below asks for, in their headers —
exposure, airmass, filter, binning, a measured FWHM, and `BUNIT = electron` so
no gain assumption was needed. The one thing they did not carry was a usable
zero point: PinPoint's `ZMAG` is calibrated against USNO-B1.0 and is out by up
to 0.73 mag, band-dependently, so photometry against Pan-STARRS was needed
instead.

## What has to come with the data

A measured SNR on its own cannot be compared to anything. To reproduce a frame
we need to know what CASTOR would have been told:

- **Which rig** — telescope, camera, and filter as named in `presets.json`, plus
  the **binning**, because that sets the pixel scale and a 2x2 frame has four
  times the sky per pixel.
- **When** — timestamp in UTC, or the airmass if that is all that survives. The
  moon is derived from the time, so a time is worth more than an airmass.
- **Exposure time and frame count**, kept separate: read noise enters per frame.
- **Seeing**, ideally the FWHM measured on the frame rather than the site
  forecast. CASTOR takes this as an input and does not adjust it for band or
  airmass, so a measured value removes a whole class of disagreement.
- **The photometric aperture** the measurement used, in arcsec or in pixels.
  This is not a detail: an aperture of 1.5 FWHM against one of 0.85 changes the
  sky in the aperture by three times, which is larger than every modelling
  difference this suite has measured so far.
- **What was measured** — instrumental counts, a calibrated magnitude with its
  uncertainty, or an SNR — and for which star. A catalogue magnitude for the
  target is needed to drive the calculation at all.
- **Sky background**, if it was measured, in counts per pixel or mag/arcsec².
  This is the single most valuable number here, because it is the one input
  CASTOR cannot derive: `mu_dark` is required and never inferred.

Frames without an aperture and a seeing measurement are still useful for the
sky background alone, which needs neither.

## Nothing in here is committed

This repository is public, so the observations stay out of it. `.gitignore`
keeps everything in this directory except this file, which means the data can
sit here and be used exactly like the other references without ever being
published. Tests that read it skip when it is absent, the same way the SkyCalc
tests skip without the raw export.

Anything derived from it that *is* safe to publish — a fitted throughput, a
measured sky brightness, a table of residuals — belongs in the tracked part of
`validation/`, with a line saying which night it came from.
