# CASTOR

<picture>
  <source media="(prefers-color-scheme: dark)"
          srcset="src/castorGUI/frontend/img/castor-logo-white.png">
  <img align="right" width="120" alt=""
       src="src/castorGUI/frontend/img/castor-logo-black.png">
</picture>

CASTOR(Calculator for Astronomical Strategy and Time On Rigs) is a Python module for calculating the exposure time of telescopes and astronomical observations.

By inputting the settings of the instrument, target, and environment, along with either the number of exposures or the target SNR, you can calculate the resulting SNR or the suggested number of exposures.

We designed this as a lightweight, fast, and general-purpose module for anyone who needs to run these calculations. We keep it simple and easy to use.

## Requirements & Installation

To use CASTOR, you will need:

- Python >= 3.12
- `uv` (for dependency management)

You can clone the repository and install the dependencies easily:

```bash
git clone https://github.com/alexlee24/castor.git
cd castor
uv sync
```

Check the `pyproject.toml` for more details on the exact package dependencies.

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
uv run castor calc --site lulin --filter Sloan_r --ra 210.8 --dec 54.3 --mag 18 --exp 300 -n 10
```

| command | |
|---|---|
| `castor calc` | Run one calculation. `--set` overrides any field by dotted path. |
| `castor presets` | List the sites and hardware `--site` can name; `--bands` also shows what each filter overrides, which is where Lulin's measured numbers live. |
| `castor check` | Resolve every combination the preset file offers and report what a user would actually get. Loading only proves the shapes are right. |
| `castor schema` | The JSON Schema of a request, for building one `--set` at a time. |

### How much to trust the numbers

`presets.json` ships real instruments, and how well each value is known varies a
great deal — so the repository records it rather than leaving you to guess.
[`validation/`](validation/) compares CASTOR against other observatories'
calculators, published sky models, and real photometry from Lulin;
[`validation/provenance.py`](validation/provenance.py) gives an origin for every
number in `presets.json`, and a test fails if the file holds one it cannot
account for. Profiles whose numbers cannot carry a real observation say so, in
the GUI and on the command line both.

```bash
uv run pytest              # the specification suite, on every commit
uv run pytest validation   # the comparisons, on purpose — see validation/README.md
```

## Useful Resources

- **[System Architecture](docs/architecture.md):** Core engine components, modular design, and data flow pipeline.
- **[CASTOR GUI Architecture](docs/gui_architecture.md):** The reference UI product built on top of the engine (`src/castorGUI/`), and its planned integration into Kinder.
- **[Command Line](docs/cli.md):** The four commands, why nothing is filled in silently, and what `castor check` verifies.
- **[Presets](docs/presets.md):** How `presets.json` is shaped, what a profile may and may not claim, and why `mu_dark` means two different things in it.
- **[Algorithm Theoretical Basis Document (ATBD)](docs/ATBD.md):** Mathematical formulations for photon count rates, SNR, and ephemeris.
- **API Specifications:** CASTOR uses strict Pydantic schemas for data validation. For detailed request and response contracts, please refer directly to [`src/castor/schema.py`](src/castor/schema.py).
- **[Validation](validation/README.md):** What CASTOR's answers are worth, measured against outside references and real frames — and [what it still does not know](validation/QUESTIONS.md), each item labelled with who can close it.
