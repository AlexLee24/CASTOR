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
- **LOT's throughput was 2.6x too high.** Pan-STARRS photometry over 14
  photometric nights puts T_sys at 0.265 (g'), 0.480 (r'), 0.265 (i'), where the
  preset asserted 0.68 in all three. `optical_throughput` is now set so the
  geometric mean is right, which leaves +22/-33/+22% — because the real
  throughput is band-dependent and the schema has nowhere to say so.
- **Lulin's sky is not one number.** Moonless, it measures 21.44 (g'), 20.92
  (r'), 20.04 (i') AB mag/arcsec2. `mu_dark` is a single value on the profile's
  environment and ships as 21.5, which suits g' and is 1.46 mag out in i'.
- **The frame headers' own zero point cannot be used.** PinPoint's `ZMAG` is
  tied to USNO-B1.0 and sits 0.73 mag out in g', 0.21 in r' and 0.05 in i'.
- **The moon model has no colour.** Krisciunas & Schaefer is Johnson V, and the
  only band-dependence CASTOR gives it is the extinction coefficient. Moonlight
  comes out far too blue and nearly vanishes in the near-infrared, where a full
  moon is under-counted by about a factor of ten.

## Open questions

Things the measurements raised that need someone who knows the instrument.

1. **LOT's secondary.** Every frame header carries `APTAREA` 772125 mm2, a
   130 mm obstruction on the 1 m primary. The preset says 300 mm, typical for an
   f/8 Ritchey-Chretien. 8% in collecting area, and Lulin publishes neither.
2. **Where band-dependent throughput should live.** Measured T_sys spans
   0.265-0.480 across g'r'i'. `optical_throughput` belongs to the telescope and
   `quantum_efficiency` to the camera; both are single numbers, and
   `filter_transmission` is now spoken for by the measured curves. A per-filter
   throughput field, or a QE curve on the camera, would both work — but it is a
   schema change and a contract other hosts read.
3. **Same question for `mu_dark`**, which is one number per site but measures
   1.4 mag apart across three bands.
4. **Why r' is 1.8x more efficient than g' and i'.** That shape is odd for a
   back-illuminated deep-depletion CCD, which should peak broadly in the red.
   Real, or an artefact of the reduction?
5. **Extinction per band.** The fit gives r' 0.189 +/- 0.027, but g' 0.123 +/-
   0.105 and i' 0.108 +/- 0.049 are too loose to adopt, and the ordering comes
   out backwards. Frames spanning airmass on one photometric night would settle
   it; these span nights instead.
6. **SOPHIA dark current and QE.** The datasheet quotes dark only at -90 C
   (0.0001 e-/p/s) and the camera runs at -80 C. The preset says 0.01, roughly
   100x the -90 C figure. QE is published as a figure, not a table.
7. **SLT's camera.** The corrections applied — 13 um pixels, 130 ke- well,
   2.9 e- read noise — assume the Andor iKon-M DU934P-BEX2-DD that Lulin's SLT
   page links. Confirm the model, and which sensor variant, since dark current
   differs by 50x between BEX2-DD and BV.
8. **SOPHIA's readout speed.** Read noise is now 7.0 e-, the datasheet's 1 MHz
   port, which matches the `RMSNOISE` 7.27 in the headers. Confirm the frames
   were taken at 1 MHz and not 100 kHz (3.5 e-).
