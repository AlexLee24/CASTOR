"""ESO SkyCalc radiance output, as this suite consumes it.

SkyCalc hands back six emission components on a wavelength grid, and the whole
reason for keeping the components apart rather than pre-summed is the open
question in ATBD 4.4: airglow is emitted at ~90 km and zodiacal light arrives
from outside the atmosphere, so they cannot both carry the same extinction term.
A pre-summed spectrum throws away the only information that can settle it.

The grid is also deliberately coarser here than what SkyCalc produced. The raw
export is R=20000, which is 2.7 MB of a spectrum whose narrow airglow lines make
it *impossible* to thin by subsampling — taking every n-th sample aliases the
lines and moves a broadband integral by 3-5%, which is larger than most of the
discrepancies this suite exists to measure. Integrating into bins conserves flux
instead, and at 1 nm reproduces the full-resolution broadband integral to a few
parts in 100000. Regenerate with:

    python validation/skycalc.py
"""
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent / "data"
BINNED = DATA_DIR / "eso_skycalc_paranal_1nm.csv"
RAW = DATA_DIR / "raw" / "Radiance_Components.csv"

COMPONENTS = (
    "scattered_moonlight",
    "scattered_starlight",
    "zodiacal_light",
    "lower_atmosphere",
    "upper_atmosphere",
    "airglow",
)

#: Components emitted inside the atmosphere. These are the unambiguous half of
#: the ATBD 4.4 question: light that starts at 90 km has not crossed the column
#: the extinction coefficient describes, and its path length grows with airmass
#: rather than shrinking. The scattered components are the ambiguous half —
#: moonlight enters the atmosphere, turns somewhere inside it, and arrives having
#: been attenuated over a path nobody can name from a single number.
EMITTED_IN_ATMOSPHERE = ("lower_atmosphere", "upper_atmosphere", "airglow")

#: What the shipped export actually is. Worth stating loudly: the moon was up.
#: Scattered moonlight is 80-93% of the total from u' through r', so this is a
#: bright sky and not the dark-sky baseline `mu_dark` is meant to describe.
#: Comparisons that derive a surface brightness from this spectrum are fine;
#: comparisons that pair it with a dark-sky mu_dark are not.
DATASET = "Paranal, moon up, airmass as exported — see data/raw/ for the query"


def rebin(wavelength_nm, values, step_nm):
    """Integrate onto a coarser grid without losing flux.

    Interpolating the cumulative integral and differencing it is what makes this
    flux-conserving: every photon between two new bin edges lands in that bin,
    however narrow the line that carried it.
    """
    edges = np.arange(wavelength_nm[0], wavelength_nm[-1] + step_nm, step_nm)
    trapezoids = np.diff(wavelength_nm) * (values[1:] + values[:-1]) / 2.0
    cumulative = np.concatenate([[0.0], np.cumsum(trapezoids)])
    integrated = np.interp(edges, wavelength_nm, cumulative)
    centres = (edges[:-1] + edges[1:]) / 2.0
    return centres, np.diff(integrated) / np.diff(edges)


def load(path=BINNED):
    """Returns (wavelength_nm, {component: photons/s/m²/µm/arcsec²})."""
    table = np.loadtxt(path, comments="#", delimiter=",")
    return table[:, 0], dict(zip(COMPONENTS, table[:, 1:].T))


def load_filter(path=DATA_DIR / "fors2_v_high_114.dat"):
    """Returns (wavelength_nm, transmission) for a measured filter curve."""
    curve = np.loadtxt(path)
    return curve[:, 0], curve[:, 1]


def effective_width_nm(wavelength_nm, transmission):
    """∫T dλ — the only bandpass number a top-hat model has to match.

    CASTOR multiplies flux by `filter_bandwidth * filter_transmission`. For that
    product to mean anything it has to equal this integral; a preset that pairs a
    FWHM with an average transmission instead of a peak one silently scales every
    count rate it touches.
    """
    return float(np.trapezoid(transmission, wavelength_nm))


def _regenerate():
    wavelength, raw = np.loadtxt(RAW, comments="#")[:, 0], np.loadtxt(RAW, comments="#")[:, 1:7]
    binned = [rebin(wavelength, raw[:, i], 1.0) for i in range(raw.shape[1])]
    centres = binned[0][0]
    table = np.column_stack([centres] + [values for _, values in binned])
    header = "Wavelength_nm," + ",".join(COMPONENTS)
    np.savetxt(BINNED, table, delimiter=",", fmt="%.6e", header=header)
    print(f"{BINNED}: {len(centres)} rows, {BINNED.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    _regenerate()
