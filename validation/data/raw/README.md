# Raw observations

None of this is committed. `.gitignore` excludes the whole directory except this
file, so the data can sit here and be used like any other reference without ever
being published — the repository is public and these are the observatory's frames.

One directory per dataset, because they are not interchangeable: different
telescopes, different cameras, different reference catalogues, and each reduced
by a different module for a different question.

| directory | what it is | reduced by |
|---|---|---|
| `lot_sn2025wny/` | 123 calibrated LOT/SOPHIA frames, 18 nights 2025-09-29 to 2026-02-15, one supernova under four header names. `ps1/` holds the Pan-STARRS DR2 reference photometry. | `lulin.py` |
| `slt_sn2024ggi/` | 1090 calibrated SLT frames of SN2024ggi. The 2024-04-14 night is the one that sweeps airmass 1.81-3.72 and closed QUESTIONS.md 4 and 5. | `slt.py` |
| `slt_nightly/` | The observatory's own nightly archive, `sltYYYYMMDD/` per night, each with `janet/` (science), `flat/` and `bias-dark/`. **Raw, not calibrated** — unlike the two above, these need bias/dark/flat applied first. Many targets per night, so this is the only set with real spread on the sky. | nothing committed yet — see QUESTIONS.md 16 |
| `sophia_darks_minus80/` | 20 SOPHIA darks, 300 s at -80 °C. Bounded QUESTIONS.md 6. | one-off, result in `provenance.py` |
| `Radiance_Components.csv` | The one loose file, not a directory: a single ESO SkyCalc export of sky radiance by component, which is what the zodiacal split is checked against. | `skycalc.py` |
| `lulin_web/` | Filter transmission curves and datasheets downloaded from the observatory's site. | `lulin.py`, `slt.py` |

Three things worth knowing before reducing any of it, each learned the hard way:

**`slt_nightly/` spans three cameras** on the same telescope — Andor DZ936
(2021), Apogee Alta U9000 (2022), Andor DU934P-BEX2-DD (2023 on) — with
different chips, pixel pitches and plate scales. Some 2022 headers name the
camera "U42", a real but different Apogee model; the frames' own geometry says
U9000, and the geometry is the one to believe. All three are in `presets.json`.

**Read the plate scale from each frame's WCS**, never from a constant. Mixing
eras with a fixed pixel scale put 0.18 mag of error into a sky-brightness
comparison before it was caught.

**Declination decides the reference catalogue.** Pan-STARRS DR2 stops around
-30; `slt_sn2024ggi` sits at -32.8 and returns literally zero PS1 stars, so it
uses SkyMapper DR4 instead — whose photometric system is close to but not the
same as Sloan's, an uncorrected systematic on everything derived from it.

Anything derived from these that *is* safe to publish — a fitted throughput, a
measured sky brightness, a table of residuals — belongs in the tracked part of
`validation/`, with a line saying which night it came from.
