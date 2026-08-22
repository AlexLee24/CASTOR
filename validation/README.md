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

**Lulin** — nothing here yet. Note before adding any: this repository is public.
Unpublished photometry, and anything the observatory has a release policy on,
needs a decision before it lands, not after.

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
- **LCO applies no extinction to the sky; CASTOR applies the full column.**
  Neither is obviously right — `mu_dark` mixes airglow emitted at 90 km with
  zodiacal light arriving from outside the atmosphere — but ATBD 4.4 already
  flags ours as unconfirmed, and the disagreement reaches 48% in u'.
- **LCO's magnitudes are referred to the zenith,** ours to above the atmosphere.
  Feeding both the same number leaves a flat `10^(-0.4k)` per band, independent
  of magnitude and exposure. Any fixed-configuration comparison showing the same
  small percentage every run should rule this out first.
- **The VLT/FORS2 preset's throughput is a fudge that happens to work in one
  band.** Against ESO's own ETC the `v_HIGH+114` configuration is right to 8%,
  which is why nobody noticed — but only because its `filter_transmission` of
  0.51 is absorbing an `optical_throughput * quantum_efficiency` of 0.602 where
  ESO's rates imply about 0.36. `g_HIGH+115` kept a believable 0.85 and gets no
  such cancellation: it over-predicts by 148%. Fixing this needs real
  per-component numbers, not a differently-tuned fudge.
- **The sky no longer dims with airmass.** *Fixed.* It used to carry the same
  `10^(-0.4kX)` term as target starlight, which double-counted an atmosphere
  already present in the measured `mu_dark` and inverted the sign: real sky
  surface brightness rises with airmass, because a longer line of sight holds
  more emitting atmosphere. `calculate_sky_background_rate` no longer accepts an
  airmass at all. Flat matches LCO exactly; ESO is 17.6% brighter at X=1.5 and
  31.8% at X=2.0, so the growth is still unmodelled and stays as an xfail.
- **The moon model has no colour.** Krisciunas & Schaefer is Johnson V, and the
  only band-dependence CASTOR gives it is the extinction coefficient. Moonlight
  comes out far too blue and nearly vanishes in the near-infrared, where a full
  moon is under-counted by about a factor of ten.
