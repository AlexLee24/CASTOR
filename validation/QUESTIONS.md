# Open questions

Things measuring CASTOR against real data raised that the data cannot answer.
Each one says what was measured, what is not known, and what would change if it
were — so it can be asked without reading the rest of this directory.

Everything here concerns Lulin unless it says otherwise. Numbers come from 123
calibrated LOT/SOPHIA frames over 15 nights (2025-09-29 to 2026-02-15), reduced
against Pan-STARRS DR2; method is in `lulin.py`.

---

## 1. Why is r' nearly twice as efficient as g' and i'?

**Measured.** Total system throughput above the atmosphere, from aperture
photometry on 14 photometric nights:

| band | T_sys |
|---|---|
| g' | 0.265 |
| r' | 0.480 |
| i' | 0.265 |

**Ruled out.** Not the detector: the SOPHIA datasheet's QE curve reads 90%, 96%
and 87% at the three band centres — flat to within 10% where a factor of 1.8 is
needed. Not the filters: their transmission curves are measured and published,
and their integrals are known to a percent. Not the bandpass arithmetic, which
was checked against a full spectral integration.

**Not known.** What is left is the optics, something band-dependent in the
reduction, or LOT genuinely running at 40–70% of a nominal system. A 2002
telescope on original coatings could well be the last of those, and aluminium
does dip in the near infrared, but not by a factor of two.

**What changes with an answer.** Nothing about the calculator: the measured
numbers are in `presets.json` and it now predicts correctly whichever the cause
is. This matters to the observatory, not to CASTOR — if it is coating loss,
that is a recoating case, and the numbers here are the evidence for it.

---

## 2. How big is LOT's secondary?

**Measured.** Every frame header carries `APTAREA = 772125 mm²`, which on a
1000 mm primary is a 130 mm central obstruction. `presets.json` says 300 mm,
which is typical for an f/8 Ritchey–Chrétien. The difference is 8% in collecting
area. Lulin's site publishes neither figure.

**Not known.** Which is right, and where MaxIm's value came from.

**What changes with an answer.** Currently nothing, and this is worth being
explicit about: the throughput above was fitted using the preset's own collecting
area, so the two errors cancel exactly. Changing the secondary **without
refitting the throughput** would break agreement by 8%. There is a strict xfail
in `test_lulin.py` holding this open so it cannot be changed quietly.

---

## 3. What is the extinction in each band?

**Measured, badly.** Fitting zero point against airmass gives:

| band | k (mag/airmass) | uncertainty | airmass range |
|---|---|---|---|
| g' | 0.123 | ±0.105 | 1.04–1.48 |
| r' | 0.189 | ±0.027 | 1.03–1.55 |
| i' | 0.108 | ±0.049 | 1.05–1.38 |

`presets.json` carries 0.17 for the whole site, in every band.

**Not known.** Only r' is usefully constrained, and it comes out *higher* than
g', which is backwards — extinction should fall towards the red. The frames span
nights rather than airmass, so night-to-night transparency is masquerading as an
airmass term.

**What would settle it.** One photometric night, one field, frames from as close
to the zenith as it gets down to airmass ~2, in each filter. That is a short
programme and it would also give the end-to-end SNR check its cleanest test.

---

## 4. SOPHIA's dark current at its operating temperature

**Known.** The datasheet quotes 0.0001 e-/pixel/s at −90 °C. The frames run at
−80 °C (`SET-TEMP` and `CCD-TEMP` both say so). `presets.json` says 0.01, about
100× the −90 °C figure.

**Not known.** The value at −80 °C. Dark current roughly doubles every 5–7 °C,
which would put it near 0.0004 — but that is a rule of thumb, not a measurement,
so nothing has been changed.

**What changes with an answer.** Very little in practice: at 300 s even 0.01
e-/s contributes 3 e- against a sky of ~750, so it is far below the noise. It is
listed because the preset currently states a number with no source, not because
it is doing damage. A dark frame at −80 °C would settle it in one measurement.

---

## 5. Is LOT u' worth measuring?

**Known.** Lulin publishes transmission curves for the Astrodon g'r'i'z' set but
not for u', and none for the Johnson–Cousins filters. The u' entry in
`presets.json` therefore still carries the placeholder shape the other four had
before they were measured — bandwidth 56 nm, transmission 0.9 — and all four of
those turned out wrong, one by 55%. There is also no photometry: none of the 123
frames is u'.

**What changes with an answer.** u' predictions become trustworthy. Whether that
is worth a night depends on whether anyone observes in u' — it is the band where
a 1 m telescope struggles most, so possibly not.

---

## Not for the observatory: two we own

These are ours to decide, recorded here so the list is complete.

**Sky and throughput as spectra.** Both are now stored per filter, which works
and is honest, but it is a table where the physics is a curve. Doing it properly
— a sky spectrum and a throughput curve, integrated against the real bandpass —
would also close the four other things waiting on it: the sky's growth with
airmass, the moon model having no colour, `target.sed` never being read, and the
blackbody SED being hidden in the GUI.

**FORS2's throughput decomposition.** `g_HIGH+115` over-predicts by 148% because
`v_HIGH+114` hides an over-optimistic optical throughput inside a filter
transmission. The same disease Lulin had, and the same fix would work, but it is
not our telescope and nobody here observes with it.
