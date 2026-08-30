# Command line

`src/castorCLI/` — the engine reached from a shell, and the reader for the
preset catalogue it shares with the GUI.

> Companion to [CASTOR GUI Architecture](gui_architecture.md). Both are clients
> of the same engine ([Architecture](architecture.md)) and the same preset file
> ([Presets](presets.md)); neither is part of it.

```bash
uv run castor calc --site lulin --filter Sloan_r --ra 210.8 --dec 54.3 --mag 18 --exp 300 -n 10
```

For a session of several commands, put the environment on the path once and drop
the prefix. `rehash` is what zsh needs to notice — it caches command lookups, so
without it the shell keeps insisting there is no `castor`:

```bash
source .venv/bin/activate && rehash
castor calc --site lulin --filter Sloan_r --mag 18 --exp 300 -n 10 --ra 210.8 --dec 54.3
```

## The four commands

| | |
|---|---|
| `calc` | Run one calculation. |
| `presets` | List what `--site` can name. `--bands` also shows what each filter overrides. |
| `check` | Resolve every combination the preset file offers and inspect the results. |
| `schema` | The JSON Schema of a request, for building one `--set` at a time. |

## What makes this more than a wrapper

### Nothing is filled in silently

A request has around thirty required fields. Most describe equipment the observer
did not choose, and a calculator that refused to run without all thirty would be
unusable — but one that quietly invents them is worse, because its output looks
identical to a measured one.

So the CLI fills in what it must and **reports every single one on stderr**, with
the reason it is a convention rather than a measurement:

```
assumed (pass the flag or --set to state it yourself):
  environment.seeing_fwhm = 1.4  — lulin's published median, not tonight's seeing
  options.aperture_factor = 0.85  — near worst-case-optimal, but the best aperture is the one you will actually use
  target.sed.type = 'flat'  — a choice of contract, not a measurement
  ...
```

The list lives in one place, `ASSUMPTIONS` in `main.py`. Adding a default means
writing the sentence that justifies it; there is nowhere to put one without a
reason. Results go to stdout and everything else to stderr, so a pipeline gets
the answer and a person gets the caveats.

### A profile that cannot be trusted says so

Some profiles ship numbers good enough to plan a real observation and some do
not. `calc` prints the chosen profile's caveat above every other note, because
it qualifies every number printed with it:

```
CAVEAT: Demonstration only - do not plan real observations with this. ...
```

Same text the GUI shows beside the site selector, from the same `caveat` field.
[`validation/provenance.py`](../validation/provenance.py) is the full record of
where each number came from, but that file is in the repository and this is where
the calculation is actually being run.

### Layered input, in one direction

Each layer wins over the last, so a saved request can be reused with one thing
changed:

```
--request file  →  --site preset  →  the flags  →  --set
```

`--set` takes any dotted path in the schema (`--set environment.mu_dark=20.8`)
and is repeatable, which is what keeps the flag list short: the common fields get
flags, everything else is reachable without one.

`--request` reads what the GUI's SAVE writes. A saved form holds more than a
request does — the batch fields, both branches of every either/or — so the extras
are dropped and named on stderr rather than rejected.

### Exit codes distinguish kinds of outcome

| code | |
|---|---|
| 0 | ok |
| 1 | the result saturates |
| 2 | bad usage (Click's own) |
| 3 | bad input |

Saturation leaves by the front door with a computed result attached, but not with
the exit code of an unremarkable success: every caller checks the exit code, and
not every caller reads `flags.is_saturated`.

## `castor schema`

The contract, in the form a caller can read without a person in the loop. What
makes it worth printing rather than documenting is that the descriptions carry
the two things a caller otherwise has to guess:

```console
$ castor schema | jq -r '..|objects|select(.description).description' | grep ATBD | head -4
Physical size of a single detector pixel in micrometers (µm). (ATBD: p_pixel)
Fraction of incident photons converted to electrons, as a dimensionless ratio from 0.0 to 1.0. (ATBD: QE)
Thermal electron generation rate per pixel in e-/s/pix. (ATBD: R_dark)
Electronic noise introduced during the readout phase in e-/pix. (ATBD: RON)
```

Forty-four fields carry a description and twenty-six of those name their
[ATBD](ATBD.md) symbol, so a caller never has to guess whether `pixel_pitch` is
metres or micrometres — the class of mistake that produces a plausible wrong
answer rather than an error. With the `assumed` list beside it, that is the whole
of what an autonomous caller needs: what the request must contain, and what was
filled in when it did not.

## `castor check`

Loading a preset file proves its shapes are right and nothing else. `check`
resolves all 42 combinations the shipped file offers and inspects what a user
would actually receive.

It exists because of a real bug that shipped: a filter carried a throughput
override keyed by a telescope the profile did not list. The file loaded
perfectly, the override applied to nothing, and the only way to see it was to
resolve that combination and look. `check` now looks:

- an override naming a telescope the profile does not have
- `mu_dark` outside any real night sky
- non-physical extinction
- a secondary mirror not smaller than its primary

Exit 3 on any finding, so CI can run it. Verified against a deliberately broken
file rather than only against the good one.

## Design notes

**Why `presets.py` lives here and not in the engine.** Hardware presets are out
of scope for `castor/` by design, and a host with its own hardware database has
no use for a reader of this repository's JSON. It sits in `castorCLI/` because
that is the first caller that needed it, and the GUI reads the same file through
its own path — see [Presets](presets.md).

**Why the resolution rules exist twice.** `presets.py` and `frontend/js/etc.js`
both implement "first entry listed is the default", "a hardware-only profile
fills in no location", "`median_seeing_fwhm` is displayed and never applied". The
browser cannot run Python, so two implementations are unavoidable; what
`presets.py` prevents is a *third* appearing the moment another Python caller
wants presets.
