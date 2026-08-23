# Open questions

Everything CASTOR does not know, in one place, with the same field on every
entry: **who can close it**. That field is the point of the file. Until now the
open items were spread across this document, the standing findings in
[README.md](README.md), the `GUESS` rows in `provenance.py`, the strict xfail
reasons and a docstring, and the honest answer to "what is still open?" was that
nobody could say without reading all five.

Everything here concerns Lulin unless it says otherwise. Numbers come from 123
calibrated LOT/SOPHIA frames over 15 nights (2025-09-29 to 2026-02-15), reduced
against Pan-STARRS DR2; method is in `lulin.py`. Where a prototype is cited it
is one of the two Perl calculators CASTOR was refactored from, transcribed in
`lulin_prototype.py`.

**Who can close it**

| | |
|---|---|
| **ASK** | Only the observatory knows. A conversation closes it. |
| **OBSERVE** | Needs telescope time. Nobody can answer it from a desk. |
| **BUILD** | Ours. No permission required, only work. |
| **DECIDE** | Ours, and the work is small once somebody chooses. |

| # | Question | Who | Held open by |
|---|---|---|---|
| 1 | Why is r' 1.81x g' and i'? | ASK | — |
| 2 | ~~How big is LOT's secondary?~~ | **CLOSED** | answered by Trebur's offer |
| 3 | Were the prototype's efficiencies measured, and on which camera? | ASK | — |
| 4 | What is the extinction in each band? | OBSERVE | strict xfail, `test_lulin.py` |
| 5 | SLT has no photometry at all | OBSERVE | 12 `GUESS` rows |
| 6 | SOPHIA's dark current at −80 °C | OBSERVE | `GUESS` row |
| 7 | LOT's own u' filter is still unmeasured | DECIDE | — |
| 8 | Sky and throughput are tables where the physics is a curve | BUILD | strict xfail, `test_eso.py` |
| 9 | Zodiacal light is not modelled | BUILD | — |
| 10 | Galactic background is not modelled | BUILD | — |
| 11 | Readout overhead is not modelled | BUILD | — |
| 12 | `background_dominance_factor` has no source | DECIDE | docstring only |
| 13 | SOPHIA's QE is one flat number | BUILD | `GUESS` row |
| 14 | The VLT profile is mostly invention | DECIDE | 12 `GUESS` rows |
| 15 | FORS2's throughput is a fudge that works in one band | BUILD | strict xfail, `test_eso.py` |
| 16 | Everything measured here looks in one direction | OBSERVE | `test_lulin.py` |

---

## 1. Why is r' nearly twice as efficient as g' and i'? — ASK

**Measured.** Total system throughput above the atmosphere, from aperture
photometry on 14 photometric nights: g' 0.265, r' 0.480, i' 0.265. Both ratios
are 1.81.

**Ruled out, twice over.** Not the detector: SOPHIA's datasheet QE reads 90%,
96% and 87% at the three band centres, which gives ratios of 1.07 and 1.13. Not
the filters: their transmission curves are published and measured, and the
bandpass arithmetic was checked against a full spectral integration. And now not
the optics either — the 2011 prototype decomposes throughput into
`m1 x m2 x glass x T_peak x QE`, and its optical chain is flat to 2.3% from g'
to i'. On the observatory's own model the telescope cannot do this.

**And there is now a level to compare against, not only a shape.** Trebur's offer
specifies the coating as Al+SiO2 at 90%, so two mirrors should deliver 0.81
before the filter and the detector. Dividing the measured throughputs by the
datasheet QE and the measured filter peaks leaves an implied optical train of
0.296 / 0.503 / 0.304 — **36%, 62% and 38% of the figure the telescope was sold
with.** Some of that gap is real and expected: the offer does not cover the
corrector, SOPHIA's window, or twenty-four years. A factor of 2.7 in g' is a lot
to put down to windows.

**Weakly corroborated.** The 2005 prototype's totals, interpolated onto our band
centres, give 0.37 / 0.47 / 0.32 — the same peak at r', and r' agrees to 3%. But
that total includes an unnamed camera's QE, so the shape may be that detector.
See question 3.

**What changes with an answer.** Nothing about the calculator: the measured
numbers are in `presets.json` and it predicts correctly whichever the cause is.
This matters to the observatory. If it is coating loss, these numbers are the
evidence for a recoating case.

## 2. How big is LOT's secondary? — CLOSED

**360 mm.** Lulin publishes Trebur's 2001 offer document, which states it
outright: secondary 360 mm outside diameter, optical diameter above 350; primary
1030 mm outside, optical above 1020, with a 280 mm hole. It is a *classical*
Cassegrain — parabolic primary, hyperbolic secondary at conic −4.84 — and not the
Ritchey–Chrétien this file assumed while guessing.

**The 130 mm was never a mirror.** `APTAREA = 772125 mm²` matches
π/4 · (1030² − 280²) to 0.08%: whoever configured MaxIm subtracted the hole
through the middle of the primary instead of the shadow the secondary casts on
it. The hole sits behind the secondary and removes no light the secondary has
not already removed, so the header over-states the collecting area by 7.9%.
Reading it against a nominal 1 m aperture is what produced the phantom.

**Nothing downstream moved.** Only the product A_eff × T_sys is constrained by
the frames, so a geometry change normally forces the throughput the other way.
The documented 1020/360 gives 0.7153 m² where the invented 1000/300 gave 0.7147 —
0.09% apart, because two wrong numbers had been cancelling. `presets.json` now
carries the documented pair, `test_lulin.py` asserts all three facts, and the
strict xfail is gone.

## 3. Were the prototype's efficiencies measured, and on which camera? — ASK

**Known.** The 2005 file gives total throughputs of U 0.07 / B 0.27 / V 0.54 /
R 0.46 / I 0.20 and never names its camera. The 2011 rewrite lists three cameras
with per-band QE — PI1300B, SI1100, NCUcam-1 — and none of them is SOPHIA, which
post-dates it. The 2011 file is also an unfinished draft: `XXX` for most dark
currents, blank Sloan QE for one camera, a duplicated hash key.

**Not known.** Whether either set of numbers was measured or estimated.

**What changes with an answer.** It decides question 1. If they were estimates,
the 2005 agreement at r' is coincidence and our photometry is the only evidence
that exists. If they were measured on a camera whose QE was flat, the shape is
the telescope's and has been for twenty years.

## 4. What is the extinction in each band? — OBSERVE

**Three sources, none good enough to overrule the others.**

| source | g' | r' | i' |
|---|---|---|---|
| `presets.json` | 0.17 | 0.17 | 0.17 |
| 2005 prototype, interpolated | 0.161 | 0.092 | 0.074 |
| our fit | 0.123 ± 0.105 | 0.189 ± 0.027 | 0.108 ± 0.049 |

The 2005 values fall monotonically towards the red, which is what extinction
does; ours puts r' highest, which it cannot be, and it is now clear why. The
range looks adequate — 1.03 to 1.59 — but it is accumulated across 18 separate
nights. **The largest airmass span any single night manages is 0.19, and the
median is 0.08**, so what the fit actually measured was night-to-night
transparency wearing an airmass term's clothes.
But our r' is 3.6σ from the 2005 value, so the two genuinely disagree rather than
one refining the other. The 2011 file's Sloan column looks like a fourth source
and is not — see the trap at the end of this file.

`presets.json` therefore keeps its single site-wide 0.17, which is certainly
wrong in detail and at least is not wrong in a specific direction.

**What would settle it.** One photometric night, one field, frames from as close
to the zenith as it gets down to airmass ~2, in each filter. A short programme,
and it would also give the end-to-end SNR check its cleanest test.

## 5. SLT has no photometry at all — OBSERVE

None of the 123 frames is from SLT. Twelve of its preset values have no source,
and the one that matters is `optical_throughput = 0.804` — LOT measures 0.27 to
0.48, and there is no reason the 40 cm is twice as efficient as the metre.
`secondary_mirror_diameter = 0.12` is also unpublished and, unlike LOT's, is not
absorbed by a fitted throughput.

**What would settle it.** A night of SLT frames on a Pan-STARRS field, in any
filter, moves it from guesswork to measurement exactly as LOT's did. Cheapest if
it rides along with question 4 on the same night.

## 6. SOPHIA's dark current at −80 °C — OBSERVE

**Known.** The datasheet quotes **0.00025** e-/pix/s at −90 °C for the -152, the
15 µm variant and so ours. The frames run at −80 (`SET-TEMP` and `CCD-TEMP`
agree). `presets.json` says 0.01, forty times the −90 °C figure, with no source.

**Not known.** The value at −80 °C. The 2011 prototype tabulates two other
cameras across that range and they fall by 33x and 100x from −50 to −80 — a
halving every 5.9 °C and every 4.5 °C. Even the sign is not in doubt, but a
factor of three between two cameras in one document is why a rule of thumb
cannot replace a measurement, and nothing has been changed.

**What changes with an answer.** Very little in practice: at 300 s even 0.01
e-/s contributes 3 e- against a sky of ~750. It is listed because the preset
states a number with no source. One dark frame at −80 °C settles it, and that is
faster than asking.

## 7. LOT's own u' filter is still unmeasured — DECIDE

**Half closed.** Lulin's filter inventory turns out to publish more than the LOT
griz set: SLT carries an Astrodon 2018 *ugriz* set with a u' curve, and a 2018
UBVRI set. The preset's u' now carries that measurement — 353.4 nm at an
equivalent width of 64.8 nm and unit peak — against a placeholder 354/56/0.9
that was 14% narrow and 10% dim.

**What is left.** LOT's u' is a third filter again, `up_Astrondon_2017`, and
Lulin publishes no curve for it. Two Astrodon u' filters bought a year apart are
close but not identical, so LOT u' predictions should be read as *an* Astrodon
u' rather than as this telescope's. There is also no photometry: none of the 123
frames is u'.

**The decision.** u' is the band where a 1 m struggles most. If nobody observes
in it, this is now good enough and the remaining gap can simply be labelled. If
somebody does, it needs a night — and the same night would settle question 4.

## 8. Sky and throughput are tables where the physics is a curve — BUILD

Both are now stored per filter, which works and is honest, but a filter-indexed
lookup cannot express a spectrum. Doing it properly — a sky spectrum and a
throughput curve integrated against the real bandpass — closes four other things
at once:

- **the sky's growth with airmass, which is band-dependent.** Flat matches LCO
  exactly and stopped the double-counting that used to make it *fall*, but the
  sky does grow: from X=1.1 to X=2.0 SkyCalc puts it at +23% in g' and +58% in
  i'. The ratio between those is the whole point — i' is mostly upper atmosphere
  and airglow, emitted inside the column and lengthening with it, while over half
  of g' is zodiacal light, which arrives from outside and is extinguished
  instead. A scalar fitted in one band is wrong in every other. Strict xfail in
  `test_eso.py`.
- **the moon model has no colour.** Krisciunas & Schaefer is Johnson V and the
  only band dependence CASTOR gives it is the extinction coefficient. Moonlight
  comes out far too blue and nearly vanishes in the near infrared, where a full
  moon is under-counted by roughly a factor of ten.
- **`target.sed` is never read.** The schema accepts and validates it (ATBD 3.2)
  and the flux unification path ignores it, so a field the API advertises does
  nothing.
- **the blackbody SED is hidden in the GUI**, for the same reason.

The 2026 project slides record why this was deferred, and the reasons still
hold: spectral data is incomplete, uncertain inputs make debugging impossible,
and the rectangular approximation meets current precision needs.

## 9. Zodiacal light is not modelled — BUILD

`mu_sky = -2.5 log10(Flux_dark + Flux_moon)`. Two components, and zodiacal light
is not one of them — it is sunlight scattered off interplanetary dust, it depends
on ecliptic latitude and solar elongation, and near the ecliptic it is a
substantial fraction of a dark sky. Queried from SkyCalc at the sightline our own
photometry looks down, and rescaled to Lulin's measured brightness, zodiacal
light plus scattered starlight is **27% of a moonless g' sky**, 27% of r' and
14% of i'. (The uncorrected Paranal figures are 53 / 35 / 16 — see question 16
for why Lulin's are smaller.)

## 10. Galactic background is not modelled — BUILD

The same gap and the same fix: integrated starlight plus diffuse galactic light,
strongly dependent on galactic latitude, absent from `mu_sky`. Both are named a
core issue in the project's slides, which propose ESO's SkyCalc as the route.

**Adding them naively would double-count.** `mu_dark` is a *measured* ground-level
brightness, so it already contains both, at whatever sightline it was measured
down. Computing them separately and adding them on top repeats the mistake the
extinction term made and the slides named — *"Hidden Errors (Two Wrongs Make a
Right)"*. Doing this properly means redefining `mu_dark` as airglow and
atmosphere only, and that means knowing how much to take out — which is
question 16.

## 11. Readout overhead is not modelled — BUILD

CASTOR returns integration time. An observer planning a night needs elapsed time,
and both prototypes reported it: 2005 as two named modes, 40 s and 2 s; 2011 as a
readout-frequency table per camera. Neither the schema nor `presets.json` has a
place to put it. This is a feature the ancestor had and the refactor dropped.

## 12. `background_dominance_factor` has no source — DECIDE

The optimal single exposure time uses a default of 1.0, the crossover where
background shot noise just overtakes read noise, and `physics.py` says so in its
own docstring: "Provisional default — not yet backed by a specific reference
guideline, revisit before relying on it for real observation planning." That
warning has never been anywhere but the docstring. Either find a reference, or
decide the crossover is the right convention and say so in the ATBD.

## 13. SOPHIA's quantum efficiency is one flat number — BUILD

`presets.json` gives 0.85 for every band; the datasheet curve reads 90 / 96 / 87 /
28% at g' r' i' z'. The datasheet is now pinned to the right column — the -152,
whose sensor is the 15 µm one — but its QE curves are a chart, not a table, so
the four numbers above remain read off a rendered page. In g'r'i' this is harmless because the measured band
throughputs absorb it. In **u' and z' it is not** — those two have no measured
throughput, so they inherit the site value and multiply it by a QE that is wrong
by a factor of three in z'. Fixing it properly is part of question 8; labelling
it is not.

## 14. The VLT profile is mostly invention — DECIDE

Twelve of its fifteen values are `GUESS`, against Lulin's twelve out of
forty-five. It is not the default, but it is selectable, and a user who picks it
gets an answer assembled mostly from numbers nobody sourced. Either source it,
mark it in the GUI as a demonstration profile, or drop it.

## 15. FORS2's throughput is a fudge that works in one band — BUILD

`presets.json` gives optical throughput 0.771 and QE 0.781, a product of 0.602
where ESO's own rates imply about 0.36. `v_HIGH+114` agrees to 8% only because a
0.51 "filter transmission" absorbs the difference; `g_HIGH+115` over-predicts by
148%. The fix is real per-component numbers, not a different fudge. Strict xfail
in `test_eso.py`.

It is the same disease the project diagnosed in the original prototype and named
*"Hidden Errors (Two Wrongs Make a Right)"*, and question 2 is a second instance:
an unknown secondary cancelling a fitted throughput.

## 16. Everything measured here looks in one direction — OBSERVE

**Measured.** 123 frames over 18 nights, and one target: the headers give four
names — AT2025wny, SN2025wny, ZTF25abnjznp, 20251017-AT2025wny — to one
supernova. Ecliptic latitude spans 0.1°, galactic latitude 0.1°, solar elongation
7°.

**What it costs.** The measured `mu_dark` values, 21.44 / 20.92 / 20.04, are not
Lulin's dark sky. They are Lulin's dark sky *towards ecliptic +16 and galactic
+21*, where zodiacal light and scattered starlight are a large share of the
total. Corrected to Lulin's own brightness, the full swing from the ecliptic
plane to the pole is **0.17 mag in g'**, 0.19 in r' and 0.10 in i', saturating
above about 60° of ecliptic latitude. `presets.json` carries one number per band and has no way to
say which direction it applies to. This is a known bias in a shipped value,
which makes it worse than questions 9 and 10 — those are merely missing.

It also means those two questions cannot be *calibrated* here at all, only
modelled. A model can still be anchored, and the anchoring turns out to be
cheap: SkyCalc answers for this exact sightline, so the measured value stays the
absolute reference while the model supplies only the variation. The obvious
objection — that SkyCalc has no Lulin, only ESO sites — bites less than it looks. Altitude is
irrelevant — across La Silla, Paranal and Armazones, 2400 m to 3060 m, the
component shares move by 0.1 percentage point. Geography is not, and the check
is direct: SkyCalc's moonless Paranal sky at our sightline is 22.16 / 21.21 /
20.21 AB mag/arcsec² in g'r'i' where the frames measure 21.44 / 20.92 / 20.04.

**Lulin is brighter in every band, by 0.72 / 0.29 / 0.17, and the colour says
what it is.** Airglow lives in the near-infrared OH bands, so an airglow excess
would be red-weighted; this is monotonically the other way. That is scattered
artificial light or aerosol, and SkyCalc has no term for either at a site it does
not have.

It does not block the correction, because zodiacal light is interplanetary and
therefore identical from both mountains. Lulin's total is measured and 1.94×
Paranal's in g', so the zodiacal share is smaller by exactly that ratio and the
pointing term shrinks with it. What it *does* mean is that the excess is a third
component nobody has characterised, and artificial light scatters worse towards
the horizon and towards towns — so the real sky at Lulin varies with azimuth and
elevation for a reason no model here contains, and 123 frames down one sightline
cannot separate it. `skycalc.AT_LULIN` holds the corrected numbers,
`skycalc.LULIN_VS_PARANAL` the comparison, and `skycalc.query()` regenerates
both.

**What would settle it.** Fields spread in ecliptic and galactic latitude — which
the airmass night in question 4 could carry for free if the fields are chosen for
it rather than for convenience.

---

## Building 9, 10 and 16: the plan, with the numbers already in hand

Written out because the measuring is done and only the coding is left. Nothing
below needs the observatory, a new night, or an answer from anyone.

**The target.** `mu_sky` gains a term and `mu_dark` changes meaning:

```
mu_sky = -2.5 log10( Flux_local(mu_dark) + Flux_zodiacal(pointing) + Flux_moon )
```

where `mu_dark` stops being "the dark sky" and becomes **airglow, upper
atmosphere and Lulin's own light pollution** — everything emitted or scattered
below the top of the atmosphere. Zodiacal light and scattered starlight leave it
and are computed from where the telescope is pointing.

**Step 1 — take the interplanetary part out of the measured values.** Already
computed: at Lulin, zodiacal plus starlight is 27.4% of the g' sky, 26.7% of r'
and 13.7% of i' (`skycalc.AT_LULIN`). So the three band `mu_dark` entries in
`presets.json` become

| band | now (total) | becomes (local only) |
|---|---|---|
| g' | 21.44 | **21.79** |
| r' | 20.92 | **21.26** |
| i' | 20.04 | **20.20** |

and their provenance changes from MEASURED to DERIVED, since a model supplied
the split. The site-wide fallback 21.5 and u' have no measurement to split and
should stay as they are, labelled.

**Step 2 — give the engine the pointing.** It already has what it needs:
`target.coordinates` and the observation time are how airmass is computed, so
ecliptic latitude and solar elongation are a coordinate transform away, no new
input. The zodiacal term is a function of those two and the band.

**Step 3 — the zodiacal model itself.** `skycalc.query()` regenerates it for any
geometry. A table over ecliptic latitude at a few elongations, interpolated,
is enough — the dependence is smooth and saturates above about 60° of ecliptic
latitude. The whole swing is 0.17 mag in g', 0.19 in r', 0.10 in i', so this is
a correction and not a rewrite.

**Step 4 — what will break, and should.** `test_provenance.py` fails on any
changed preset until the table is updated. `test_lulin.py` asserts CASTOR
reproduces the measured sky to under 0.5%; that comparison has to move to the
new decomposition or it will be comparing a local-only `mu_dark` against a total
measurement. Anything asserting `mu_dark` is a scalar per band needs the
pointing argument threaded through.

**What this still will not do.** The light pollution in step 1 is folded into
`mu_dark` as if it were isotropic, and it is not — artificial light scatters
worse towards the horizon and towards towns. That part stays uncharacterised
until there are frames pointing in more than one direction, which is why 16 is
an OBSERVE and not a BUILD.

**Do not** compute zodiacal light and add it to the present `mu_dark`. That
counts a quarter of the sky twice, and it is the same error the extinction term
made.

---

## Traps

Not open questions. Recorded because each one looks like a source and is not, and
somebody will find it again.

**The 2011 prototype's Sloan tables are the Bessell tables shifted one slot.**
`sdss_g` ≡ `bessell_B`, `sdss_r` ≡ `bessell_V`, `sdss_i` ≡ `bessell_R`,
`sdss_z` ≡ `bessell_I` — four extinction coefficients and twenty sky brightnesses,
identical value for value. `sdss_z` also inherits `sdss_g`'s 1409 Å bandwidth
where Lulin's published curve measures 2780 Å. Asserted in
`test_lulin_prototype.py` so the claim cannot rot. Its centres and widths for
g'r'i' *are* sound, within 1% and 6% of measurement; only the Sloan-labelled
tables are placeholders.

**PinPoint's `ZMAG` in the frame headers cannot be used as a zero point.** It is
tied to USNO-B1.0 and sits 0.73 mag out in g', 0.21 in r' and 0.05 in i'.

**CASTOR and ESO disagree by 11% on aperture, and it is a convention.** Matched
apertures agree to under a percent. This is the largest remaining difference
against ESO and it is not a defect in either.

**SOPHIA's datasheet has two columns and only one of them is ours.** The -132 is
the 13.5 µm sensor; the -152, ours, is the 15 µm one. An earlier pass through
this suite took the -132 column and carried its full well (100 ke- against 150),
its dark current (0.0001 against 0.00025) and its read noise into presets.json.
The full well was a 50% under-statement of the saturation limit.

**The old spec PDF still shows extinction applied to the sky.** `R_sky` in the
`ETC Core Formula` slides carries a `10^(-0.4 k X)` factor, because that document
was written by reading the prototype's code. `docs/ATBD.md` is the current spec
and no longer does. Four independent sources — LCO, ESO's opposite sign, and both
prototypes — say the sky does not carry the target's extinction.
