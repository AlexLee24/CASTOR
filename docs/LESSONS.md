# Lessons

Traps this project has already fallen into, so it does not fall into them
twice. Each entry is a thing that once looked right and was not: what it looked
like, why it was actually wrong, how it surfaced, how to see it for yourself, and
what now stops it from coming back — with a commit or file you can follow.

This is not a to-do list. What is still *open* — the things nobody has decided
or measured yet — lives in [`../validation/QUESTIONS.md`](../validation/QUESTIONS.md),
the single place for that, with the same field on every row: who can close it.
A lesson lands here once it is closed and understood; if a row here still has an
open question hanging off it, that question belongs in QUESTIONS.md too, and this
entry links to it rather than restating it.

Below the description, each entry carries three labelled lines. **Found by** —
the check or moment that first exposed it. **Reproduce** — how to see the evidence today; where the bug is
fixed, this is the regression test that now pins it, so a green run *is* the
proof it stays fixed. **Guard** — what stops it recurring. Commit hashes in
parentheses are the source.

---

## Physics that the units cannot catch

### The same erg/s/cm²/Å can be in two different frames of reference

The heaviest bug this engine has carried. All three count rates — star, galaxy,
sky — shared `_calculate_base_electron_rate`, so the sky was routed through the
same `10^(-0.4·k·X)` extinction term as target starlight. But `mu_sky` descends
from `mu_dark`, a brightness *measured from the ground*, through the very
atmosphere that coefficient describes. Attenuating it again counts the
atmosphere twice — and worse, inverts the sign: sky surface brightness *rises*
with airmass, and the engine was making it fall. Both sides were plain floats in
erg/s/cm²/Å, so the dimensions were right and the frame of reference was wrong
(`b1df2a7`).

- **Found by** building the validation suite against ESO's FORS2 ETC and LCO's
  calculator. FORS2 puts the sky 17.6% brighter at X=1.5; we were 6% fainter —
  nobody agreed with us in either direction.
- **Reproduce** `pytest validation/test_eso.py`. The airmass-growth case is a
  strict xfail (flat sky is only exact at the zenith); the sign and
  double-count regression is asserted alongside it.
- **Guard** a top-of-atmosphere flux (star, galaxy) and a ground-measured
  surface brightness (sky) are different quantities even sharing a unit. They now
  take different paths: `calculate_sky_background_rate` does not accept `airmass`
  or `extinction_coeff` at all — "a parameter taken and discarded is an
  invitation to pass it and assume it did something, which is how this got here."

### An unobservable target is reported as a very faint observable one

`calculator.py` clamps the zenith angle to 89°. A target 35° *below* the horizon
comes back not as an error but as airmass 57 — a real-looking number for a source
that cannot be seen (its true airmass is −1.8). The clamp keeps the maths finite
at the cost of making invalidity look like faintness (`44ab4af`).

- **Found by** pinning the CLI test times: the saturation test's target, twelve
  hours off transit, was not low but below the horizon, and the engine answered
  anyway.
- **Reproduce** ask the engine for a target well below the horizon at a fixed
  time; the returned airmass is a large positive number, not a rejection.
- **Guard** reachability is not brightness. Do not read a large airmass as "hard
  to observe" — check the target is actually up. The response now carries both
  sides: `diagnostics.airmass` clamped, `ephemeris.target_elevation_deg` not, and
  `test_a_target_below_the_horizon_says_so_beside_its_clamped_airmass` holds them
  side by side. The clamp itself is unchanged; the engine still answers.

## Noise and calibration

### A missing noise term always looks like a calibration offset first

The noise model kept coming out optimistic against real frames, and the first
instinct each time was a throughput or zero-point tweak — one multiplicative
offset. It was never that. Twice the cause was a term the model did not charge
for: the sky estimate is not free (subtracting it adds variance scaling as
`k_ap²`, `051994e`), and the background is not perfectly flat (the NGC 3621
extended-source check was short a flatness term, `6a34861`).

- **Found by** the end-to-end SNR check (`validation/endtoend.py`) comparing
  predicted SNR to real frame-to-frame scatter.
- **Reproduce** `pytest validation`, then read `validation/ENDTOEND_RESIDUALS.md`
  — residuals resolved by flux.
- **Guard** when observed SNR sits below predicted, rule out a *missing noise
  source* before touching throughput or the zero point. An offset moves every
  flux bin by the same fraction; a missing noise term does not — that is how the
  two are told apart.

### The datasheet describes the detector; the observer measures the instrument

Two of the same shape. SOPHIA's read noise was kept at the datasheet's 1 MHz
7.0 e⁻ over a measured 7.9, on the sound reasoning that a PTC intercept bounds
the *sensor* — but an ETC predicts what the *observer* measures, and the observer
gets the residual pattern noise too (`2128f7d`). Separately, SLT's read noise was
a real DU934P datasheet number, 3.3 e⁻, for the wrong readout port (`f393a54`).
Both plausible, both passed review, both understated noise in the unsafe
direction.

- **Found by** a photon-transfer curve over 89 adjacent frame pairs (SOPHIA), and
  tracing SLT's value back to its datasheet row (which port).
- **Reproduce** compare the `read_noise` in `presets.json` against the
  frame-measured value recorded in its provenance row.
- **Guard** use the value the frames show, not the datasheet's, and record the
  readout configuration (port, speed, temperature) beside the number — every
  camera in the 2011 prototype spans ×2–12 across its ports.

### A hardcoded instrument constant is a latent bug the day a second instrument appears

The Q16 sky-brightness comparison used a fixed 0.76 arcsec/pixel plate scale —
which belongs to only one of three camera bodies this archive has run on the same
telescope over the years (DU934P 0.76, DZ936 0.79). It also multiplied the ADU
sky level by the frame's GAIN before applying a zero point already calibrated in
ADU counts, mixing two unit systems on the sky side only (`d7a7000`).

- **Found by** recomputing the Q16 comparison and finding gain folded in on one
  side of a conversion whose other side never used it.
- **Reproduce** read plate scale, gain and units from each frame's own WCS and
  header; a constant that matches one camera silently corrupts the others.
- **Guard** read per-frame quantities from the frame, and keep a conversion in
  the same unit system its calibration used. A hardcoded instrument constant is
  correct right up until the second instrument.

### The reference data has limits too — check them before blaming the model

Above ~60 ke⁻ the observed SNR fell short and the shortfall grew with brightness
— the shape of a real model defect. It was not one: the reference
frames' own 16-bit ADC was saturating, so the "systematic" was in the data
CASTOR was judged against, not in CASTOR (`a4dd05c`).

- **Found by** binning the end-to-end residual by electrons in the aperture and
  watching it turn over only at the bright end.
- **Reproduce** `pytest validation`; the per-flux-bin table in
  `ENDTOEND_RESIDUALS.md` shows the turnover above the linear range.
- **Guard** a discrepancy that appears only at the bright end is a saturation
  suspect first. Establish the reference instrument's linear range before adding
  a term to chase a residual outside it.

### You cannot fit extinction from a night that was not photometric

Per-band extinction coefficients were fitted, shipped, and marked CLOSED — then
retracted. The night (2024-04-14) had an hour of cloud and never fully
recovered, and because the target was setting, transparency was fading while
airmass rose. `zp = zp0 − k·X` cannot separate those two moving together: the fit
charges the fade to airmass and inflates `k`, band by band in step with how much
each faded — which is what identifies it as weather, not a dusty site (`ad0c78b`).

- **Found by** a model-free test: frames at the *same* airmass early and late in
  the night have an identical extinction term by definition, so any zero-point
  gap between them is transparency alone — and the sky was fainter later in every
  band.
- **Reproduce** `pytest validation/test_slt.py`; it asserts the per-band values
  are ABSENT and pins the fade/excess correlation. `slt.WHY_NO_EXTINCTION` holds
  the numbers.
- **Guard** extinction needs a night *verified* photometric — returning to the
  same airmass and finding the same zero point, not merely spanning a range.

### A borrowed model needs one in-situ check before you trust it

Standing SkyCalc's Paranal sky in for Lulin looked reasonable until checked
against our own frames: Lulin is brighter in every band, and *monotonically
worst in the blue*. Airglow lives in the near-infrared, so an airglow excess
would be red-weighted — this is the other way round, which is scattered
artificial light and aerosol, a term SkyCalc has for neither (`5b45ad5`).

- **Found by** comparing SkyCalc's absolute moonless sky at our sightline against
  the absolute sky the 123 frames measure.
- **Reproduce** `pytest validation/test_sky_model.py` (and `validation/skycalc.py`
  for the component split).
- **Guard** when you borrow another site's model, check the one quantity you can
  against local data first. Only what is genuinely site-independent transfers —
  here, the interplanetary zodiacal component, anchored throughout to our own
  photometry.

### A large dataset can still be a single measurement

The Lulin suite is 123 calibrated frames over 18 nights, which reads like broad
coverage and is not. They are one supernova under four header names: ecliptic
latitude spans 0.1°, galactic latitude 0.1°, and no single night sweeps enough
airmass to fit extinction (largest span 0.19). So `mu_dark` is not "Lulin's dark
sky" but "Lulin's dark sky *toward ecliptic +16*", and the airmass leverage the
extinction question needs is not in the data at all (`1404c3a`; this is
QUESTIONS.md item 16).

- **Found by** resolving the 123 frames by pointing and finding every one within
  0.1° of the same patch of sky.
- **Reproduce** read `validation/lulin.py`'s `SIGHTLINE` — the coordinate span
  across all frames is a tenth of a degree.
- **Guard** count independent *conditions*, not rows. N frames of one target
  down one sightline is one measurement made N times; a fit constrains only what
  the inputs actually vary.

## Software structure

### The same physics implemented twice will drift, silently

A band's throughput is keyed by telescope (a value measured on LOT says nothing
about SLT). The browser applied that fragment flat, naming a field
(`instrument.telescope.LOT`) that does not exist, and `applyFragment` silently
skips fields it cannot find — so the measured override applied as *nothing*, and
the rig's default stood in. The shipped page was 33% low in r' with nothing to
announce it, because the overrides beside it worked (`2d93107`).

- **Found by** the engine having a test for this exact bug (the schema fix) while
  the form had none — "which is why one was fixed and the other went on being
  wrong."
- **Reproduce** check the fragment's field path against the schema: a name the
  model does not define is dropped without error.
- **Guard** when the same physics lives in two places (engine and client), a
  divergence is invisible until a test pins them to the same answer. Give the
  second copy the first copy's test.

### A default value can hide a bug that a different default exposes

Moving the photometric aperture default from 1.5×FWHM to 0.85 (for SNR reasons)
surfaced a latent saturation bug. `calculate_peak_pixel_rate` was being handed
the source rate already scaled by the enclosed fraction, where its docstring
asks for the target's *total* (`calculator.py` now divides f_enc back out). At the old f_enc=0.998 the error was 0.2% and
invisible; at 0.865 it becomes 13%, in the direction that reports a frame safe
when it is not. Extended sources were worse: the Gaussian peak fraction ran over
a rate already integrated across the whole aperture, so their saturation time
scaled with aperture² — a galaxy that saturated in one aperture was safe in
another (`982c21f`).

- **Found by** changing an unrelated default (the aperture) and watching a
  saturation number move that must not depend on it.
- **Reproduce** vary `k_ap` for a near-saturation point source; the peak-pixel
  fill time must not change with the photometry aperture — the brightest pixel
  belongs to the star and the seeing, not the circle drawn around them.
- **Guard** an invariant that holds at one parameter value is not being tested
  there. When a default makes an error negligible, the error is still live for
  every other caller — assert the invariant, not the one happy number.

### A cross-check is only a cross-check if the two sides are independent

`test_lulin.py` said it checked that "two independent measurements" agree. They
were not independent: `mu_dark` is derived from `sky_rate` through the same
throughput, so the 0.4% residual it reported was `mu_dark` rounded to two
decimals and nothing more. The test was still worth having — it pins the
round-trip through CASTOR's equations — but its docstring claimed a cross-check
the repo does not have (`a4dd05c`).

- **Found by** tracing each side of the "agreement" back to its source and
  finding one derived from the other.
- **Reproduce** read `validation/test_lulin.py`: the assertion pins a round-trip,
  and now says exactly that rather than claiming independence.
- **Guard** before citing agreement as evidence, check that the inputs are
  independent, not just the code paths. A test can be worth keeping while its
  docstring is wrong; make the docstring claim only what it asserts.

### An inverse solver must invert the same noise model the forward path uses

`calculate_total_snr()` correctly models the 2% background-flatness term as
correlated across a stack, creating an asymptotic SNR *ceiling*. But
`solve_required_exposures()` still returned `(target_snr / single_snr)²`, which
assumes every noise term averages down as √N. So the solver promised six frames
reach SNR 20 when its own forward model puts the ceiling below 20 and no frame
count gets there (`14e0e6c`).

- **Found by** the forward model and the inverse solver disagreeing on one case:
  SLT/DU934P, r', AB=20, 120 s frames, requested SNR 20 — six frames "enough",
  achieved SNR 14.44.
- **Reproduce** `pytest validation/test_solve_time_floor.py` (strict xfail pinning
  the contradiction); QUESTIONS.md item 17 records the fix.
- **Guard** a forward model and its inverse must share one noise model. A
  correlated term breaks the √N shortcut; the solver must invert
  `SNR(N)=N·S/√(N·V+N²·F²)` and return an explicit unreachable result past S/F.

### Prose and diagrams drift from the schema they describe

`architecture.md` claimed `environment` was "a discriminated union from the
start". It is not — `EnvironmentCondition` is a flat model with no discriminator;
the pillar that genuinely is a union is `options`, on `type`. The words and the
picture had drifted from the models and disagreed with each other (`090c40e`,
`f0ddcf7`).

- **Found by** reading the prose next to `schema.py` and finding they disagreed.
- **Reproduce** grep `schema.py` for a discriminator on `EnvironmentCondition` —
  there is none; the `Union`/discriminator is on the options model.
- **Guard** documentation is only true the moment it is written. When a claim
  names a structural property (a union, a required field, a count), check it
  against the code, not the last version of the prose. This file included.

## Frontend

### A CSS reset built on `inherit` breaks where the DOM grows a new boundary

`* { box-sizing: inherit }` resolved up to the `border-box` on `.castor-etc` —
until a `<select>` was placed inside a native `<details>`. `<details>` inserts a
`::details-content` pseudo-element between the element and its children, and `*`
does not match a pseudo-element, so it kept the UA's `content-box` and every
field inside every disclosure inherited that. Invisible until a `width: 100%`
select with 46px of padding and border pushed past the panel edge (`25bfc8b`).

- **Found by** putting the first `<select>` inside a `<details>` and watching it
  overflow 46px past the panel.
- **Reproduce** nest a full-width control in `<details>` under a
  `*{box-sizing:inherit}` reset; it renders content-box though its ancestor is
  border-box.
- **Guard** set `box-sizing: border-box` outright, not by inheritance.
  `inherit` follows the flat tree, and any pseudo-element boundary silently
  breaks the chain.

### Setting an input's value in JS fires no change event

A profile with one empty filter catalogue fell back to "Custom" but never
revealed the fields underneath. The reveal logic listens for `change`, and the
code set the control's `.value` in JS — which does not fire it (`e132a2e`).

- **Found by** testing the personal-gear profile (its filter catalogue was
  empty) and finding the Custom fields stayed hidden.
- **Reproduce** set `el.value = …` in JS and watch no `change`/`input` listener
  run; only a user edit or an explicit `dispatchEvent` does.
- **Guard** after a programmatic value change, dispatch the event or call the
  handler yourself. The DOM fires input events for user interaction, not for
  assignment.

## Packaging and robustness

### A planning tool must not crash on planning ahead

astropy's `iers.conf.auto_max_age` defaults to 30 days: once the bundled
Earth-orientation table is that stale relative to *now*, an AltAz transform does
not extrapolate, it raises — and a packaged desktop app has no network fallback
to fetch a fresh table. So any observation more than ~a month out raised
`ValueError`, in a calculator whose whole job is planning ahead (`dc15bbd`).

- **Found by** offline planning for a date more than a month out crashing in the
  desktop build.
- **Reproduce** call `moon.get_moon_and_target_geometry` for a date >30 days out
  with `astropy` downloads forced off; without the fix it raises. Confirmed
  against 2026-12-01 and 2028-06-01.
- **Guard** `auto_max_age = None` is set deliberately. It costs no real precision
  — astropy's out-of-coverage fallback is a 50-year polar-motion mean, good to the
  arcsecond, well inside any seeing FWHM this tool sees.

### A dependency imported nowhere is still shipped

The desktop build was 56 MB. `scipy`, `speclite` and `skyfield` were declared in
`pyproject.toml` and imported nowhere in the shipped source — the one scipy user,
`assets/make_icons.py`, declares it inline via PEP 723. Dropping them, and
resyncing a venv that had drifted from `uv.lock` (leftover Flet packages, a full
PyObjC suite), cut the app to 32 MB (`ff47d52`).

- **Found by** asking why the packaged app was twice the size it needed to be.
- **Reproduce** grep the shipped source for each declared dependency; one that
  never appears is dead weight PyInstaller still bundles.
- **Guard** the declared dependency set and the imported set drift apart. Audit
  imports against `pyproject.toml`, keep the venv synced to `uv.lock`, and
  declare build-only tools (icon generation) inline rather than as project deps.

### A test that reads the clock passes until it doesn't

Every calculating test in `tests/test_cli.py` let the CLI default its observing
time to *now*, so each silently asked where the sky happened to be. They passed
when written and failed the same afternoon with nothing changed: the target had
set, and a source that filled the well in half a second was six thousand times
fainter twelve hours later (`44ab4af`).

- **Found by** the suite going red in the afternoon with no code change since the
  morning it was written.
- **Reproduce** historically, running `tests/test_cli.py` at different times of
  day; now every ephemeris-touching test passes an explicit `--time`, so it does
  not recur.
- **Guard** any test that touches the ephemeris pins a `--time`. A test whose
  result depends on wall-clock time is not testing what it claims to.
