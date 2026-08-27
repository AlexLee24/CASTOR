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
| `slt.py` | SLT measured against the 2024-04-14 airmass sweep, and why its extinction is unusable |
| `lulin_prototype.py` | The two Perl calculators CASTOR was refactored from, 2005 and 2011 |
| `provenance.py` | Where every number in presets.json came from, or that it came from nowhere |
| `skycalc.py` | Loading and rebinning ESO SkyCalc radiance exports |
| `test_lco.py` | Count-rate chain and extinction conventions against LCO |
| `test_eso.py` | The top-hat bandpass against a full spectral integration |
| `test_sky_model.py` | How the Krisciunas & Schaefer moon term behaves per band |
| `test_lulin.py` | Throughput, sky and detector against 123 calibrated frames |
| `test_slt.py` | SLT's throughput against that night's fit, and that its extinction stayed out |
| `test_lulin_prototype.py` | Which of the ancestors' numbers survive, and which are placeholders |
| `test_provenance.py` | Fails on any preset value the provenance table does not account for |

## What the references are, and are not

**LCO** stopped being a physical model in 2023. Their calculator now looks up
photometric zero points measured from real images — their own source annotates
the collecting-area table "not used in code" and comments out the zero-point
fluxes. Comparing CASTOR against it checks a prediction against a calibration.
Where the two disagree, the interesting question is which *convention* differs,
not which number is right.

**The prototypes** are not an outside reference at all — they are CASTOR's own
ancestry. The project's slides record the chain as Kinoshita Daisuke's Perl CGI,
then Ting-Wan Chen, then this refactor, so where `presets.json` holds a number
nobody can source, `etc.cgi` (2005) and `etc2.cgi` (2011) are the likeliest
places it came from. Read them as archaeology, and read them warily: the 2011
file was never finished, and its Sloan tables are the Bessell tables relabelled.

**ESO** gives us two references. Their **ETC** (`etc.eso.org/fors`, and a REST
API behind it) is a real physical model over measured instrument curves, and is
the ground truth for the VLT/FORS2 preset — which came from it in the first
place: `dark_current_rate`, `readout_noise` and `full_well_capacity` appear
verbatim in both. Their **SkyCalc** radiance model is six emission components at
R=20000, and is the right reference for bandpass shape and for what the sky is
made of. Neither is the right reference for absolute agreement on a given night.

**Lulin** is the only reference here made of photons rather than models, and the
only one that can judge the profile the calculator opens on. Two separate
reductions, and the split between them is not administrative — they answer
different questions because they cover different things:

`lulin.py` is 123 calibrated LOT/SOPHIA frames over 18 nights against
Pan-STARRS DR2. Deep, but no single night in it spans more than 0.19 in
airmass, so it can measure throughput and sky and *cannot* measure extinction.

`slt.py` is 241 SLT frames from one night, 2024-04-14, sweeping airmass 1.81 to
3.72 in five bands — the observation `lulin.py`'s own open question asked for.
It gives SLT its first photometry ever, and it does **not** close extinction:
the sweep was real but the night was not photometric through it, and `slt.py`'s
`WHY_NO_EXTINCTION` shows how that was established from matched-airmass pairs
alone. Its reference catalogue is SkyMapper DR4 rather than Pan-STARRS, because
the field is at declination -32.8 and PS1 does not reach it; no colour-term
transform between the two systems has been applied, which is that reduction's
other large caveat.

Neither set of frames is in the repository — it is public — and both modules
carry the reduced result so the tests run without them. Their docstrings have
the methods.

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

- **The ancestors had the same disease, and one of them documented the cure.**
  The 2011 prototype decomposes throughput exactly as the ATBD specifies, into
  optics x filter x quantum efficiency — so the VLT preset hiding an optimistic
  throughput inside a filter transmission violates a form the project has had
  since 2011. It also fabricated its Sloan tables by relabelling the Bessell
  ones, twenty-four numbers with no exceptions, which is why nothing Sloan from
  that file may be adopted as a source. The 2026 slides had already named the
  pattern in the original prototype: *"Hidden Errors (Two Wrongs Make a Right)"*.

- **Lulin publishes more than anyone had looked for.** Trebur's 2001 offer
  document gives LOT's mirrors outright, SOPHIA's datasheet is on the same page,
  and the filter inventory carries transmission curves for SLT's Astrodon 2018
  ugriz and UBVRI sets as well as LOT's 2019 griz. Between them they closed the
  secondary mirror, corrected a full well that was 50% low, and replaced the u'
  placeholder with a measured curve. Every one of those had been sitting behind
  a link on the observatory's own site.

- **presets.json was invented, and now says which parts still are.** Nothing in
  it had a source when it was written, and every value a check reached turned
  out wrong — so the prior for anything unaccounted for is that it was made up
  too. `provenance.py` records an origin for all 118 values and a test fails if
  the file holds one the table does not, or a different number than the one
  recorded. Lulin is now 57 sourced against 6 guesses; VLT — not the default,
  and not what anyone here observes with — is 8 against 12, up from 3 once its
  site stopped being left unset. `other` (a personal amateur rig, nominally at
  Hehuan Mountain's Yuanfeng dark-sky viewpoint) is new and starts at 28 sourced
  against 7 — every telescope's collecting geometry and every camera's read
  noise and full well are real, only the optical throughputs and one borrowed
  dark current are placeholders. See `provenance.summary()`.

- **SLT went from a completely unmeasured guess to real photometry — and the
  same night failed to measure extinction, for a reason worth keeping.** SLT,
  2024-04-14, SN2024ggi: 241 frames sweeping airmass 1.81-3.72, the first
  LOT/SLT data ever to have a real single-night sweep. It closed QUESTIONS.md 5,
  giving SLT per-band throughput of 0.10-0.47 and replacing a guessed 0.804 that
  had no reason to beat LOT's own measured 0.27-0.48 and didn't. It did **not**
  close question 4: matched-airmass pairs show the sky faded 0.1-0.4 mag between
  the halves of the night, and since the target was setting, that fade is
  degenerate with the airmass term and inflates every k. The band that faded
  most is the band inflated most, which is what identifies it as weather. The
  *ordering* survives — extinction falls towards the red on every cut — and no
  absolute value does, so presets.json keeps the site-wide 0.17 and `test_slt.py`
  asserts the per-band values stay out. Calibrated against SkyMapper DR4, not
  Pan-STARRS DR2 — this field's declination (-32.8°) is outside PS1's
  footprint — so it carries an uncorrected systematic on top of the fit error
  from the two systems' natural photometric bands not being identical.
  Discovered along the way: presets.json's per-filter telescope override had
  no telescope of its own — selecting SLT with a filter LOT had measured
  silently applied LOT's number. Fixed by keying the override by telescope id;
  see `castorCLI/presets.py`'s `FilterEntry.telescope`.

- **SLT has had three cameras, and one of its own header fields lies about
  which.** The observatory's raw nightly archive (not `2024ggi`'s pre-reduced
  set) spans Andor DZ936 (2021), Apogee Alta U9000 (2022 on), then the current
  DU934P-BEX2-DD. Some 2022 headers name the camera "U42" — a real, different
  Apogee model, 2048x2048 at 13.5um — but the frames themselves are 3056x3056
  at 12um, U9000's geometry exactly. The name is stale, not the hardware; only
  the pixel geometry, read straight from the detector, can be trusted. Both
  retired cameras are now in `presets.json` (`SLT_DZ936`, `SLT_U9000`) so
  frames from those eras can still be reduced, sourced from Andor's own iKon
  brochure and a U9000 datasheet Lulin hosts itself.

- **SOPHIA's dark current at -80°C is now bounded by a real dark frame, not
  guessed.** 20 real -80°C, 300s frames (QUESTIONS.md 6) — no bias frame to
  subtract, so measured through the frame-to-frame variance instead of the
  mean level. The variance came in *below* read-noise-squared: dark current is
  too small for this method to detect, an upper limit rather than a
  measurement. The guessed 0.01 e-/s/pix is replaced with 0.001, the
  datasheet's -90°C figure scaled to -80°C by the same halving-interval method
  used for the ASI2600MC — consistent with, not contradicted by, the
  non-detection.

- **`mu_dark` stopped meaning "the whole sky" for Lulin's g'/r'/i'.** Zodiacal
  light and scattered starlight — 27%, 27% and 14% of what those three bands'
  photometry actually measured — have been split back out, leaving `mu_dark` as
  airglow and light pollution only and letting the engine add the zodiacal part
  back in sized to wherever the target actually points, rather than baking in
  the one sightline the frames happened to look down. `zodiacal_share` records
  what was split out; `castor.moon.ZODIACAL_LATITUDE_SHAPE` derives the pointing
  dependence from ESO SkyCalc, and independently reproduces the plane-to-pole
  swing `skycalc.AT_LULIN` already published (0.174 / 0.193 / 0.101 mag) to the
  third decimal. Every other profile is unaffected — this needs a measurement
  nobody else has. See `QUESTIONS.md` 9 and 10.

## Open questions

**[QUESTIONS.md](QUESTIONS.md)** is the single index: fifteen items, each
labelled with who can close it — the observatory, a night of telescope time, us,
or a decision. Nothing open is recorded only here, in a `GUESS` row, or in an
xfail reason; if it is open, it is in that file.

Four items have been closed by looking harder rather than by asking. Lulin
publishes Trebur's 2001 offer document, which gives LOT's mirrors outright — a
360 mm secondary, not the 300 the preset guessed, and not the 130 the frame
headers seemed to imply, which turns out to be the hole through the primary
rather than any obstruction at all. Lulin's SLT
page names the camera in full — Andor iKon-M DU934P-BEX2-DD CCD-26868 — which
fixes the sensor variant and with it the 130 ke- well depth. A photon transfer
curve over the frames puts read noise at 7.9 e-, confirming the header gain to 2%
and identifying the 1 MHz port. And the question of whether the telescope's
optics could explain the r' excess is answered in the negative by the 2011
prototype's own decomposition, which leaves them flat to 2.3% across g' to i'.
