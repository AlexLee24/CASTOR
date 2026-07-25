# CASTOR

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

## Useful Resources

- **[System Architecture](docs/architecture.md):** Core components, modular design, and data flow pipeline.
- **[Algorithm Theoretical Basis Document (ATBD)](docs/ATBD.md):** Mathematical formulations for photon count rates, SNR, and ephemeris.
- **API Specifications:** CASTOR uses strict Pydantic schemas for data validation. For detailed request and response contracts, please refer directly to [`src/castor/schema.py`](src/castor/schema.py).
