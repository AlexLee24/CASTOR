# Validation

Comparisons between CASTOR and things outside CASTOR: other observatories'
calculators, published sky models, and — in time — real photometry from Lulin.

This is deliberately not `tests/`. A unit test asserts that the engine does what
we specified, runs on every commit, and is red when someone breaks it. What lives
here asserts what our answers are *worth*, and a failure is usually a finding
that needs a human to interpret. Mixing the two would make the fast suite slow
and the honest suite look broken.

```bash
pytest              # tests/ only — the specification suite
pytest validation   # this suite, on purpose
```

## What is here

| | |
|---|---|
| `lco_etc.py` | Las Cumbres Observatory's published calculator, transcribed |
| `eso_etc.py` | ESO's FORS2 ETC — captured reference results, plus a live client |
| `lulin.py` | LOT/SOPHIA measured against real frames and Lulin's own documents |
| `skycalc.py` | Loading and rebinning ESO SkyCalc radiance exports |
| `test_lco.py` | Count-rate chain and extinction conventions against LCO |
| `test_eso.py` | The top-hat bandpass against a full spectral integration |
| `test_sky_model.py` | How the Krisciunas & Schaefer moon term behaves per band |

## What the references are, and are not

**LCO** stopped being a physical model in 2023. Their calculator now looks up
photometric zero points measured from real images — their own source annotates
the collecting-area table "not used in code" and comments out the zero-point
fluxes. Comparing CASTOR against it checks a prediction against a calibration.
Where the two disagree, the interesting question is which *convention* differs,
not which number is right.

**ESO** gives us two references. Their **ETC** (`etc.eso.org/fors`, and a REST
API behind it) is a real physical model over measured instrument curves, and is
the ground truth for the VLT/FORS2 preset — which came from it in the first
place: `dark_current_rate`, `readout_noise` and `full_well_capacity` appear
verbatim in both. Their **SkyCalc** radiance model is six emission components at
R=20000, and is the right reference for bandpass shape and for what the sky is
made of. Neither is the right reference for absolute agreement on a given night.

**Lulin** is the only reference here made of photons rather than models, and the
only one that can judge the profile the calculator opens on. 123 calibrated
LOT/SOPHIA frames over 15 nights, reduced against Pan-STARRS DR2. The frames
stay out of the repository — it is public — and `lulin.py` carries the reduced
result so the tests run without them. Its docstring has the method.

## Data

`data/eso_skycalc_paranal_1nm.csv` is committed: 700 rows, 62 KB, the six
components binned to 1 nm. **The moon was up in this export** —
scattered moonlight is 80-93% of the total from u' through r' — so it is a
bright-sky dataset, not the dark-sky baseline `mu_dark` describes. `data/fors2_v_high_114.dat` is the measured FORS2
V_HIGH+114 transmission curve.

`data/raw/` is ignored. It holds the original 2.7 MB R=20000 SkyCalc export,
which is regenerable and would nearly double the size of a repository that
currently tracks no binary data at all — the same call already made for
`de421.bsp`. Regenerate the binned file from it with:

```bash
python validation/skycalc.py
```

Binning rather than thinning is not a detail. The sky spectrum is full of narrow
airglow lines, and taking every n-th sample moves a broadband integral by 3-5%
in a direction that does not settle as the grid coarsens. `test_eso.py` asserts
both halves of that: the binned grid conserves the integral, and subsampling
would not.

## Standing findings

Each of these is asserted by a test, so it either stays true or announces itself.

- **The two count-rate chains are the same algebra.** Calibrate CASTOR's optical
  train to an LCO zero point and the sky rate matches to nine digits, in every
  band. Every other difference below is convention or input, never formula.
- **LCO applies no extinction to the sky; ESO's sky grows with airmass; ours is
  now flat.** Flat matches LCO exactly and stops the double-counting that used
  to make it *fall*. ESO is 17.6% brighter at X=1.5 and 31.8% at X=2.0, so the
  growth is still unmodelled and stays as an xfail.
- **LCO's magnitudes are referred to the zenith,** ours to above the atmosphere.
  The two conventions differ by a constant, so relative to the zenith all three
  calculators agree on airmass dependence to 0.02%.
- **The aperture convention is the largest remaining difference against ESO.**
  Matched apertures agree to under a percent; unmatched they differ by 11%.
- **The VLT/FORS2 preset's throughput is a fudge that works in one band.**
  `v_HIGH+114` is right to 8% only because a 0.51 'transmission' absorbs an
  optical throughput twice too optimistic; `g_HIGH+115` over-predicts by 148%.
- **Lulin's four Sloan filters were placeholders.** All carried transmission 0.9
  and three shared a bandwidth of 137 nm. Against the Astrodon curves Lulin
  publishes, g' was out by 16%, r' and i' by 5%, and z' by 55% — a 278 nm filter
  described as a 137 nm one. Now corrected from the measured curves. LOT u' has
  no published curve and keeps its placeholder.
- **LOT's throughput was 2.6x too high, and band-dependent.** Pan-STARRS
  photometry over 14 photometric nights puts T_sys at 0.265 (g'), 0.480 (r'),
  0.265 (i'), where the preset asserted 0.68 in all three. Both this and the sky
  below now live on the filter entry, which is the only place in the file that
  varies with band — see the note on band fragments in presets.json.
- **Lulin's sky is not one number either.** Moonless, it measures 21.44 (g'),
  20.92 (r'), 20.04 (i') AB mag/arcsec2, against a single site-wide 21.5 that
  suited g' and was 1.46 mag out in i'. Bands with no measurement, u' among
  them, still inherit the site value.
- **The frame headers' own zero point cannot be used.** PinPoint's `ZMAG` is
  tied to USNO-B1.0 and sits 0.73 mag out in g', 0.21 in r' and 0.05 in i'.
- **The moon model has no colour.** Krisciunas & Schaefer is Johnson V, and the
  only band-dependence CASTOR gives it is the extinction coefficient. Moonlight
  comes out far too blue and nearly vanishes in the near-infrared, where a full
  moon is under-counted by about a factor of ten.

## Open questions

Five for the observatory and two for us, written up so they can be asked without
reading this directory: **[QUESTIONS.md](QUESTIONS.md)**.

Two that were on that list are now closed, by looking harder rather than by
asking. Lulin's SLT page names the camera in full — Andor iKon-M DU934P-BEX2-DD
CCD-26868 — which fixes the sensor variant and with it the 130 ke- well depth.
And a photon transfer curve over the frames puts read noise at 7.9 e-, the
datasheet's 1 MHz port, while confirming the header gain to 2%.
