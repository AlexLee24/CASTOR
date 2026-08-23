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


#: Lulin's Sloan passbands as measured, for integrating a queried spectrum.
#: (centre_nm, equivalent_width_nm), matching presets.json.
SLOAN = {"u'": (353.4, 64.8), "g'": (475.9, 147.0), "r'": (627.8, 131.0), "i'": (767.6, 145.0)}


def query(centre_nm, width_nm, **overrides):
    """One band's sky radiance from ESO's live SkyCalc, integrated.

    Returns photons/s/m2/arcsec2 over the band. Needs `skycalc_cli` and the
    network; everything the tests assert is captured in SIGHTLINE_STUDY below so
    the suite stays offline.

    Ask for one band at a time. A single 300-1000 nm request never returned in
    nine minutes while the same total range split into four band-width windows
    completes in about six seconds each — the cost is in the range, not the
    resolution. `wres` turns out not to matter at all for a broadband integral:
    2000 and 20000 agree to 0.00% over r', because the server bins
    flux-conservingly rather than sampling.
    """
    from skycalc_cli.skycalc import SkyModel      # optional dependency
    from astropy.io import fits
    import io

    params = dict(airmass=1.10, observatory="paranal", incl_moon="N", wres=2000,
                  wmin=round(centre_nm - width_nm / 2, 1),
                  wmax=round(centre_nm + width_nm / 2, 1),
                  wdelta=0.5, wgrid_mode="fixed_wavelength_step")
    params.update(overrides)
    model = SkyModel()
    model.callwith(params)
    with fits.open(io.BytesIO(model.data)) as hdul:
        table = hdul[1].data
        return float(np.trapezoid(np.asarray(table["flux"], float),
                                  np.asarray(table["lam"], float)))


#: The sightline our photometry was taken down, in SkyCalc's coordinates.
#: Ecliptic latitude +15.9 and a solar elongation of 130 degrees, which puts the
#: target at ecliptic longitude 131.9 relative to the sun.
OUR_SIGHTLINE = dict(ecl_lat=15.9, ecl_lon=131.9)

#: Captured from the live service on 2026-08-23, moonless, Paranal, X=1.10
#: unless stated. Four things, each answering an open question:
#:
#: `zodiacal_and_starlight_share` — how much of a moonless sky at OUR sightline
#: is light that did not come from the atmosphere. This is the fraction already
#: baked into the measured mu_dark, and therefore the amount that would be
#: double-counted by computing it separately and adding it on.
#:
#: `pointing_dmag` — magnitudes the sky darkens moving from the ecliptic plane
#: to the pole at fixed ecliptic longitude. The full swing, not a share: this is
#: how wrong a single site-wide mu_dark can be from pointing alone. It saturates
#: above about 60 degrees.
#:
#: `growth_to_airmass_2` — how much brighter the sky gets from X=1.1 to X=2.0.
#: Strongly band-dependent, and that is the finding: i' grows two and a half
#: times faster than g' because its sky is mostly upper atmosphere and airglow,
#: which lengthen with the path, while g' is over half zodiacal light, which is
#: above the atmosphere and gets extinguished instead. No scalar can do this.
#:
#: `site_insensitivity` — the shares move by 0.1 percentage point across La
#: Silla, Paranal and Armazones, 2400 m to 3060 m. SkyCalc has no Lulin at 2862
#: m, and on this evidence it does not need one.
SIGHTLINE_STUDY = {
    "zodiacal_and_starlight_share": {"u'": 0.249, "g'": 0.532, "r'": 0.349, "i'": 0.160},
    "pointing_dmag": {                      # ecliptic latitude -> mag, relative to ours
        0.0:  {"g'": -0.103, "r'": -0.078, "i'": -0.038},
        15.9: {"g'": +0.000, "r'": +0.000, "i'": +0.000},
        30.0: {"g'": +0.117, "r'": +0.086, "i'": +0.040},
        45.0: {"g'": +0.194, "r'": +0.141, "i'": +0.064},
        60.0: {"g'": +0.246, "r'": +0.177, "i'": +0.080},
        90.0: {"g'": +0.246, "r'": +0.177, "i'": +0.080},
    },
    "growth_to_airmass_2": {"u'": 0.136, "g'": 0.228, "r'": 0.388, "i'": 0.578},
    "site_insensitivity": {"lasilla": 0.532, "paranal": 0.532, "armazones": 0.533},  # g'
}


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
