# CASTOR

<picture>
  <source media="(prefers-color-scheme: dark)"
          srcset="src/castorGUI/frontend/img/castor-logo-white.png">
  <img align="right" width="120" alt=""
       src="src/castorGUI/frontend/img/castor-logo-black.png">
</picture>

CASTOR (Calculator for Astronomical Strategy and Time On Rigs) is a Python tool
for estimating signal-to-noise ratio and exposure counts for optical observations.

By inputting the settings of the instrument, target, and environment, along with either the number of exposures or the target SNR, you can calculate the resulting SNR or the suggested number of exposures.

It provides a Python API, command-line interface, and reference GUI. The
[validation report](validation/VALIDATION_REPORT.md) describes where its
predictions have been checked against observations and where they remain
model estimates.

## Requirements & Installation

CASTOR needs Python >= 3.12.

### To use it

Install it like any Python package, and the `castor` command works from any
directory:

```bash
pip install git+https://github.com/happpycorn/CASTOR.git
```

Either of these does the same, keeping CASTOR in an environment of its own so it
cannot clash with your other packages:

```bash
pipx install git+https://github.com/happpycorn/CASTOR.git
uv tool install git+https://github.com/happpycorn/CASTOR.git
```

Then check it runs:

```bash
castor presets
```

pip and pipx resolve dependencies from the minimum versions in `pyproject.toml`,
so they may pick newer releases than the ones tested; `uv.lock` records those,
and only a checkout installed with `uv sync` follows it. The install also brings
in the GUI's dependencies (FastAPI, pywebview) even if you only use the command
line.

### To work on it

Clone the repository and let `uv` install the exact locked versions:

```bash
git clone https://github.com/happpycorn/CASTOR.git
cd CASTOR
uv sync
```

Inside a checkout, run the CLI as `uv run castor ...`.

## Usage

You can run calculations by constructing an `ObservationRequest` and passing it to the core calculator engine.

```python
from castor.calculator import run_calculation
from castor.schema import ObservationRequest

# 1. Define your request parameters
request = ObservationRequest(...)

# 2. Execute the calculation
response = run_calculation(request)

# 3. Get the results
print(f"Total SNR: {response.core.total_snr}")
print(f"Required Exposures: {response.core.required_exposures}")
```

For more details on batch processing and data schemas, check the `src/castor/` source code.

### From the command line

Naming a site fills in its coordinates, sky and hardware, so a calculation is
usually one line. Everything the CLI filled in for you is reported on stderr, so
"the tool chose this" never gets mistaken for "the observer meant this".

```bash
castor calc --site lulin --filter Sloan_r --ra 210.8 --dec 54.3 --mag 18 --fwhm 1.5 --exp 300 -n 10
```

From a development checkout, prefix it with `uv run`.

| command | |
|---|---|
| `castor calc` | Run one calculation. `--set` overrides any field by dotted path. |
| `castor presets` | List the sites and hardware `--site` can name; `--bands` also shows what each filter overrides, which is where Lulin's measured numbers live. Preset files of your own can be read beside the shipped one: repeat `--presets-file`, or list them in `CASTOR_PRESETS_PATH`. |
| `castor check` | Resolve every combination the preset file offers and report what a user would actually get. Loading only proves the shapes are right. `--provenance` also holds every number to a table of where it came from. |
| `castor schema` | The JSON Schema of a request, for building one `--set` at a time. |

### How much to trust the numbers

`presets.json` ships real instruments, and how well each value is known varies a
great deal — so the repository records it rather than leaving you to guess.
[`validation/`](validation/) compares CASTOR against other observatories'
calculators, published sky models, and real photometry from Lulin;
[`validation/provenance.py`](validation/provenance.py) gives an origin for every
number in `presets.json`, and a test fails if the file holds one it cannot
account for. The rule itself is `castorCLI.provenance`, so a preset file of your
own can be held to it too (`castor check --provenance`). Profiles whose numbers
cannot carry a real observation say so, in the GUI and on the command line both.

```bash
uv run pytest              # the specification suite, on every commit
uv run pytest validation   # the comparisons, on purpose — see validation/VALIDATION_REPORT.md
```

The browser form's tests (`tests/test_gui_form.py`) run `etc.js` under Node.js
and are skipped where it is not installed.

## Useful Resources

- **[System Architecture](docs/architecture.md):** Core engine components, modular design, and data flow pipeline.
- **[CASTOR GUI Architecture](docs/gui_architecture.md):** The reference UI product built on top of the engine (`src/castorGUI/`), and its planned integration into Kinder.
- **[Command Line](docs/cli.md):** The four commands, why nothing is filled in silently, and what `castor check` verifies.
- **[Presets](docs/presets.md):** How `presets.json` is shaped, what a profile may and may not claim, why `mu_dark` means two different things in it, and how several preset files merge and lend each other hardware.
- **[Algorithm Theoretical Basis Document (ATBD)](docs/ATBD.md):** Mathematical formulations for photon count rates, SNR, and ephemeris.
- **API Specifications:** CASTOR uses strict Pydantic schemas for data validation. For detailed request and response contracts, please refer directly to [`src/castor/schema.py`](src/castor/schema.py).
- **[Validation](validation/VALIDATION_REPORT.md):** What CASTOR's answers are worth, measured against outside references and real frames — and [what it still does not know](validation/QUESTIONS.md), each item labelled with who can close it.

Before using a calculated exposure count for an observing plan, read the
[current limitations and release handoff](validation/QUESTIONS.md). Solve-for-time
now accounts for the correlated background-flatness floor: it returns a count
that actually reaches the requested SNR, and where that SNR sits above the floor's
asymptotic ceiling it reports the target as unreachable rather than returning a
frame count that never meets it.
