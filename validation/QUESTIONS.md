# Open questions

Everything CASTOR does not know, in one place, with the same field on every
entry: **who can close it**. That field is the point of the file. Until now the
open items were spread across this document, the standing findings in
[README.md](README.md), the `GUESS` rows in `provenance.py`, the strict xfail
reasons and a docstring, and the honest answer to "what is still open?" was that
nobody could say without reading all five.

Everything here concerns Lulin unless it says otherwise. Numbers come from 123
calibrated LOT/SOPHIA frames over 18 nights (2025-09-29 to 2026-02-15), reduced
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
| 3 | Were the prototype's efficiencies measured, and on which camera? | ASK | likely unanswerable — 2005, nobody left to ask |
| 4 | What is the extinction in each band? | OBSERVE | still open — 2024-04-14 was not photometric |
| 5 | SLT has no photometry at all | OBSERVE | **CLOSED** — SN2024ggi/SLT, 2024-04-14 |
| 6 | SOPHIA's dark current at −80 °C | OBSERVE | **Closed to an upper limit** — see below |
| 7 | LOT's own u' filter is still unmeasured | DECIDE | — |
| 8 | Sky and throughput are tables where the physics is a curve | BUILD | strict xfail, `test_eso.py` |
| 9 | Zodiacal light is not modelled | BUILD | Partly closed |
| 10 | Galactic background is not modelled | BUILD | Partly closed |
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

**Not corroborated by the second analysis, despite appearances.** Wang Tong's
reduction of this ratio gives about 1.5, close enough to look like independent
support, but it is the same frames run through an older version of the core;
feeding her inputs to that version reproduces 1.60, so the gap to 1.81 measures
our own change of engine, not the sky. Nothing here is a second observation.

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

**Not known, and probably staying that way.** Whether either set of numbers was
measured or estimated — asked 2026-08-24, the answer is 2005, and there is
nobody left to ask who would know. Treat this as unlikely to close on any
useful timescale rather than pending.

**What changes with an answer.** It decides question 1. If they were estimates,
the 2005 agreement at r' is coincidence and our photometry is the only evidence
that exists. If they were measured on a camera whose QE was flat, the shape is
the telescope's and has been for twenty years. Absent an answer, the honest
default is the weaker reading: `lulin_prototype.py`'s comparison stays what
README.md already calls it — "weakly corroborated," not confirmed.

## 4. What is the extinction in each band? — OBSERVE

**Attempted and failed, on a night that had everything except photometric
conditions.** SLT/SN2024ggi, 2024-04-14: 241 frames, five bands, airmass 1.81
to 3.72 in one continuous run. That is precisely the observation this question
had been asking for since it was written, and it still did not deliver.

**Why not, established without any model.** Take frames at the *same* airmass
from early and late in the night. The extinction term between them is identical
by definition, so any difference in zero point is transparency alone. Pairing
the 12:0x-14:2x frames against the 14:50-15:35 ones at matched airmass:

| band | fainter, late vs early, at equal airmass |
|---|---|
| u' | 0.35 mag |
| g' | 0.40 |
| r' | 0.17 |
| i' | 0.11 |
| z' | 0.14 |

An hour of cloud crossed at 14:34 and the sky never fully came back. Because
the target was setting, the second half of the night is also the high-airmass
half — so a transparency decline and an airmass rise move together, and
`zp = zp0 - k*X` cannot tell them apart. It attributes the fade to airmass.

**The inflation matches the fade, band by band**, which is what identifies it as
weather rather than a genuinely dusty site. Against literature for a good site,
the excess is +0.06 (u') / +0.29 (g') / +0.15 (r') / +0.13 (i') / -0.01 (z'):
g' faded most and is inflated most.

Re-fitting the post-cloud ascending branch alone lowers everything without
rescuing it — u' 0.605, g' 0.485, r' 0.258, i' 0.197, z' 0.049, still 2-3x
literature in g'r'i' while u' and z' land near it, which is not a physical
extinction curve since real extinction is smooth in wavelength.

**What the night did establish.** Extinction falls monotonically towards the
red, on every cut of the data. That is more than the LOT 18-night fit could do —
it gets the ordering backwards (see the strict xfail in `test_lulin.py`) — and
it is the one extinction result this project can currently defend.

`presets.json` therefore still carries the single site-wide 0.17, and
`test_slt.py` asserts the per-band values are *absent* so they cannot be
reinstated quietly. Evidence and numbers in `slt.py`'s `WHY_NO_EXTINCTION`.

**What would settle it.** The same request as before, with one condition added
that turned out to matter more than the airmass range: a night that is
photometric *throughout*, verified by returning to the same airmass at the end
and finding the same zero point. Ideally both rising and setting, so the airmass
term and any residual time drift are not degenerate.

## 5. SLT has no photometry at all — CLOSED

**Settled by the same SN2024ggi/SLT night.** SLT's per-band `optical_throughput`
(the implied optical train, `T_sys / (QE * filter_transmission)`, same
convention as LOT's rows):

| band | optical_throughput |
|---|---|
| u' | 0.101 ± 0.018 |
| g' | 0.323 ± 0.015 |
| r' | 0.474 ± 0.022 |
| i' | 0.373 ± 0.025 |
| z' | 0.122 ± 0.007 |

The guessed 0.804 was wrong in the direction this file already suspected — SLT
is *not* twice as efficient as LOT; its real numbers (0.10-0.47) sit in the same
range as LOT's own measured 0.27-0.48. That conclusion is robust to the
transparency problem in question 4: it is a factor of two, and the drift moves
these values by about 15%. The individual per-band numbers are softer than their
quoted errors suggest, because `zp0` and `k` trade off in the same fit and
question 4's contamination therefore reaches them too. `telescopes.SLT.telescope.optical_throughput`
now carries the geometric mean of these five (0.234) as its fallback, the same
role LOT's 0.381 plays. `secondary_mirror_diameter = 0.12` remains unpublished —
this closes the throughput question, not the geometry one.

**A real bug found while wiring this in.** `presets.json`'s per-filter telescope
override had no telescope of its own: `_overlay()` applied whichever
telescope's number was on a filter regardless of which telescope was actually
selected, so `SLT + Sloan_r'` was silently returning *LOT's* measured 0.568.
Latent until now because only LOT had ever written to these fields. Fixed by
keying `FilterEntry.telescope` by telescope catalogue id (`castorCLI/presets.py`).

## 6. SOPHIA's dark current at −80 °C — Closed to an upper limit

**Measured, and the honest answer is "too small to see."** 20 real −80°C, 300s
dark frames arrived. With no bias frame to subtract the mean level against,
dark current was measured through the frame-to-frame *variance* instead: it
should equal `read_noise² + dark_rate × exptime`. The measured variance (48.4
e-²) came in *below* read-noise-squared (62.4 e-², from the 7.9 e- read noise
measured elsewhere in this suite) — statistically solid (SE of the median
0.03 e-²), not just noisy. Dark current at −80°C is too small for 20×300s
frames to resolve against this camera's own read noise; this is an upper
limit, not a detection.

**What changed anyway.** The guessed 0.01 e-/pix/s — forty times the
datasheet's −90°C figure of 0.00025 with no source — is replaced with 0.001,
the datasheet figure scaled to −80°C by the same halving-interval method
(4.5-5.9°C/halving) already used for the ASI2600MC. This estimate is
*consistent with* the non-detection above, not contradicted by it, so it
replaces the guess as DERIVED rather than staying a GUESS. As before: very
little in practice either way — at 300s even the old 0.01 e-/s contributed only
3 e- against a sky of ~750.

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

**Partly closed.** `mu_sky = -2.5 log10(Flux_dark + Flux_zodi + Flux_moon)` now
has the term. `Flux_zodi` is zero unless a profile carries `zodiacal_share`;
Lulin's g'/r'/i' are the only bands that do — queried from SkyCalc at the
sightline our own photometry looks down and rescaled to Lulin's measured
brightness, zodiacal light plus scattered starlight is **27% of a moonless g'
sky**, 27% of r' and 14% of i' (`skycalc.AT_LULIN`; the uncorrected Paranal
figures are 53 / 35 / 16 — see question 16 for why Lulin's are smaller).
`presets.json`'s `mu_dark` for those three bands is now the *local* component
only (21.79 / 21.26 / 20.20, up from 21.44 / 20.92 / 20.04), and the engine adds
the zodiacal share back on top, sized to wherever the target actually is —
`castor.moon.ecliptic_latitude` and `ZODIACAL_LATITUDE_SHAPE` — rather than
baking in the one sightline the frames happened to look down.

**What is left.** The shape table is one curve averaged across g'/r'/i' (they
agreed to within 11%, not identically) and holds only near the one solar
elongation SkyCalc was queried at (130°); neither dependence is modelled beyond
that. `background_dominance_factor` (question 12) and the moon's own colour are
untouched by this. See `src/castor/moon.py` for the full derivation.

## 10. Galactic background is not modelled — BUILD

**Partly closed, less than question 9.** Integrated starlight and diffuse
galactic light are folded into the same split as the zodiacal term above —
`zodiacal_share` is named for what it lumps together, "zodiacal *and starlight*"
— so the double-counting this question warned about (`mu_dark` is a *measured*
ground-level brightness and already contains both) is now avoided rather than
committed, and both components leave `mu_dark` together.

**What is left, and it is the real gap.** Only the zodiacal piece has its own
correct pointing dependence: `ZODIACAL_LATITUDE_SHAPE` is a function of ecliptic
latitude, which is right for zodiacal light and not for starlight, whose real
dependence is on *galactic* latitude. The starlight share currently rides along
scaled by the zodiacal shape — a documented approximation, not a galactic
background model. Untangling the two needs their separate shares as a function
of their own coordinate, which SkyCalc can supply but nothing here has queried
for yet.

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

**Partly closed.** VLT had no `environment` at all — no location, no sky — while
every amateur-gear question this session was busy asking who could source one.
The difference is that Paranal's site is not a question: it is one of the most
precisely documented observatory locations there is, and leaving it unset was
an oversight from treating VLT like a genuinely portable hardware family
rather than what it actually is, a fixed installation.

It now has one, fully sourced. Location and `mu_dark` are ESO's own published
figures (Paranal astroclimate page, Table 1: zenith-corrected V-band mean from
3900 FORS1 images over 174 nights). `extinction_coeff` is Patat et al. 2011's
measured spectral extinction curve for Paranal, integrated against V_HIGH+114's
own measured transmission curve rather than read off a table by eye —
`eso_etc.paranal_extinction_for_filter()` reproduces it, and
`test_paranal_extinction_falls_toward_the_red()` guards the transcription.

Twelve of fifteen *instrument* values are still `GUESS` — the telescope's
secondary and focal length, the CCD's pixel pitch and QE, both filters'
centres and bandwidths. It is still not the default, still selectable, and a
user who picks it still gets an instrument assembled mostly from numbers
nobody sourced. Source them, mark VLT in the GUI as a demonstration profile,
or drop it — that decision is unchanged.

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

**A second attempt, from the observatory's own nightly archive.** Unlike
SN2024ggi, this archive isn't locked to one target — each night's `janet/`
folder holds whatever the night's targets were, spread across the whole sky.
Four nights (2023-06 to 2024-02, the Andor DU934P camera era, to stay on the
plate scale and QE this suite already has) gave 8 targets from ecliptic -43° to
+74° and galactic -82° to +69° — real spread, reduced from raw frames (bias,
dark, flat, all from each night's own calibration set) rather than pre-reduced
ones. Building this surfaced the same two conversion bugs the correction above
describes, independently, before they could contaminate anything new.

**Still only one clean point, and this one disagrees with itself.** Of 8
targets, 7 were taken with the moon well above the horizon (moon_alt up to
+85°) — the same wall question 4's "what would settle it" already ran into.
The one exception, AT2023jac (ecliptic +74°, galactic +38°, moon 38° below the
horizon, X=1.14, against Pan-STARRS — no cross-catalogue systematic this time):

| band | measured | model predicts | difference |
|---|---|---|---|
| g' | 21.07 | 21.58 | **+0.51** (brighter) |
| r' | 20.78 | 21.05 | **+0.27** (brighter) |
| i' | 20.44 | 20.10 | **-0.34** (fainter) |

g' and r' brighter than predicted is the same direction as every excess this
file has found; i' going the other way is not, and n=1 target with no repeat
measurement can't settle whether that is real or a bad frame. Recorded as
found, not smoothed over.

**The pattern holding across three attempts is the finding.** Real archival
data, mined for whatever nights happen to be moonless, keeps landing on one or
two usable points per pass — not because the archive is small, but because
nobody was observing *for this question*. Settling it needs time allocated on
purpose: moonless, low airmass, fields chosen for ecliptic/galactic spread.
Everything else here is a byproduct of other people's supernovae.

**A first, inconclusive look, from the SN2024ggi field (ecliptic -34°).** Sky
brightness measured the same way as everything else in this file (whole-frame
sigma-clipped median, converted through the same SkyCalc-calibrated zero point
as questions 4 and 5) correlates strongly with airmass in this dataset — moon-
free frames past X~3.4 read 1.4-2.9 mag brighter than the two moon-free, near-
zenith ones (X=1.81), which is horizon light pollution and airglow path length,
not zodiacal light, and lines up with the "worse towards the horizon" excess
already named above. The only clean, comparable point — r', X=1.81, moon 40°
below the horizon — measures **20.68**; the zodiacal model (question 9) predicts
**21.00** at this pointing. n=2, and both figures carry the SkyMapper-vs-Sloan
systematic questions 4 and 5 already flag, so this is not a real test of the
model either way — but a *measured brighter than predicted* result is the same
direction as the unexplained excess this question already describes, not a new
contradiction. (An earlier pass at this got 20.50: the sky-to-surface-brightness
conversion multiplied by the frame's `GAIN` keyword, which is wrong — the zero
point is already calibrated in raw ADU counts, so re-scaling only the sky side
by gain mixed two unit systems — and used a fixed 0.76"/pix, which is LOT/DU934P's
plate scale, not this specific frame's; this archive turns out to span three
camera bodies on the same telescope over the years, with different chips and
pixel scales. Both are fixed by reading everything from the frame's own WCS and
never introducing gain into a ratio zp already accounts for — see
`castor.moon`-adjacent scratch scripts, not committed here since they are
analysis, not the engine.) Settling question 9's shape needs the same thing this
question already asks for: fields chosen for ecliptic/galactic spread, at low
airmass, on purpose.

---

## Building 9, 10 and 16: the plan, with the numbers already in hand

**Done for 9, most of 10; 16 is still OBSERVE.** Written out because the
measuring was done and only the coding was left; the plan below matches what
shipped, step for step. One thing changed from the plan: `Flux_zodiacal` had to
be independent of `auto_calc_background` rather than living inside it —
gating it behind the same flag as the moon would have meant the GUI's default
(that flag off) silently under-counted the sky for every preset carrying this
split, the exact failure mode this whole file exists to catch. See
`moon.apply_zodiacal_baseline`. Question 10's starlight component is split out
(no more double-counting) but rides on the zodiacal shape rather than its own
galactic-latitude model — see question 10 above for what that leaves open.

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

**CASTOR and ESO pick different points on one aperture trade-off curve, worth
2.5%.** Matched apertures agree to under a percent, so the difference is the
choice of `aperture_factor` and nothing else. The 11% this entry used to claim
was measured without matching image quality first and so counted the PSF
difference as well; matched, the aperture is worth 2.5% and the PSF 4.2%.
Neither aperture is a defect: ESO's 1.03 FWHM is near-optimal for the
source-dominated case they publish, 0.85 wins by 9% under a full moon, and 0.85
is the one that stays within 3% of the best available at both ends.

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
