"""ESO's own FORS2 exposure time calculator, and what it says about our preset.

    https://etc.eso.org/fors            the web form
    POST https://etc.eso.org/api/Fors/  the same calculation as JSON

Unlike LCO's, this is a real physical model — ESO's sky model plus measured
instrument curves at full spectral resolution. It is the closest thing we have
to a ground truth for the VLT/FORS2 preset, which is itself derived from it:
`dark_current_rate` 0.000583, `readout_noise` 3.15 and `full_well_capacity`
80400 appear verbatim in both.

Results below were captured on 2026-08-22 from ETC 2.0 v118.0.0 so the suite
stays offline. `query()` re-runs them live when you want to check for drift.
"""
import json
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

ENDPOINT = "https://etc.eso.org/api/Fors/"

#: Held fixed across every captured case. A flat F_lambda source is the one SED
#: CASTOR can represent exactly, so any difference that remains is ours.
TEMPLATE = {
    "target": {
        "morphology": {"morphologytype": "point"},
        "sed": {"sedtype": "spectrum", "extinctionav": 0,
                "spectrum": {"spectrumtype": "powerlaw", "params": {"exponent": 0}}},
        "brightness": {"brightnesstype": "mag", "mag": 20, "magband": "V", "magsys": "vega"},
    },
    "sky": {"airmass": 1.0, "fli": 0, "waterVapour": 30,
            "moonDistance": 180, "airglowEnabled": False},
    "seeing": {"turbulence_category": 50, "aperturepix": 0},
    "instrument": {"ins_configuration": "img_nopol",
                   "DET.READ.CLKIND": "200kHz,1x1,low",
                   "INS.FILT1.NAME": "v_HIGH+114",
                   "SEQ.CCD": "R", "INS.COLL.NAID": "COLL_SR+6"},
    "timesnr": {"DET.WIN1.UIT1": 100, "SEQ.NEXPO": 1},
    "output": {"snr": {"snr": {"flag": True}}},
}

EXPOSURE_TIME = 100.0

#: e- accumulated over EXPOSURE_TIME, except sky_cpix which is e- per pixel.
#: 1x1 readout throughout, so the pixel scale is the preset's unbinned 0.125"/pix.
CAPTURED = {
    ("v_HIGH+114", 20, 1.0, 0): dict(target=152440.374, sky_cpix=286.4505, npix=95,
                                     omega=1.484893, encircled=0.947115, snr=358.707),
    ("v_HIGH+114", 18, 1.0, 0): dict(target=961833.737, sky_cpix=286.4505, npix=95,
                                     omega=1.484893, encircled=0.947115, snr=966.682),
    ("v_HIGH+114", 20, 1.5, 0): dict(target=145163.578, sky_cpix=337.0002, npix=177,
                                     omega=2.761165, encircled=0.961683, snr=319.385),
    ("v_HIGH+114", 20, 2.0, 0): dict(target=133895.051, sky_cpix=377.4390, npix=227,
                                     omega=3.546564, encircled=0.945512, snr=284.279),
    ("v_HIGH+114", 20, 1.0, 1): dict(target=152440.374, sky_cpix=20662.811, npix=95,
                                     omega=1.484893, encircled=0.947115, snr=104.787),
    ("g_HIGH+115", 20, 1.0, 0): dict(target=135785.696, sky_cpix=168.6406, npix=133,
                                     omega=2.073942, encircled=0.976784, snr=339.951),
}

#: How the preset describes the same two filters. Central wavelength in nm.
PRESET_FILTERS = {"v_HIGH+114": (550.0, 114.0, 0.510), "g_HIGH+115": (467.0, 160.3, 0.850)}


def payload(band="v_HIGH+114", mag=20, airmass=1.0, moon=0):
    """The captured cases' inputs, as JSON the API accepts."""
    request = json.loads(json.dumps(TEMPLATE))
    request["instrument"]["INS.FILT1.NAME"] = band
    request["target"]["brightness"]["mag"] = mag
    request["sky"].update(airmass=airmass, fli=moon, moonDistance=30 if moon else 180)
    return request


def query(**kwargs):
    """Run one case against the live service. Needs network; used by an opt-in test."""
    body = json.dumps(payload(**kwargs)).encode()
    headers = {"Content-Type": "application/json"}
    with urllib.request.urlopen(
            urllib.request.Request(ENDPOINT, body, headers), timeout=30) as response:
        return json.load(response)["data"]["plots"]["imaging"]


def implied_throughput(band, mag, airmass, moon):
    """The T_sys CASTOR would need to reproduce ESO's count rate.

    Everything ESO folds in that CASTOR's chain does not name separately — the
    real filter curve, the real CCD response, the atmosphere at this airmass —
    lands in this one number. Comparing it against the preset's
    optical_throughput * quantum_efficiency * filter_transmission is the only
    honest way to ask whether the preset's throughput is right.
    """
    import numpy as np

    from castor import physics

    case = CAPTURED[(band, mag, airmass, moon)]
    central_nm, bandwidth_nm, _ = PRESET_FILTERS[band]
    area_cm2 = np.pi / 4 * (8.0 ** 2 - 1.088 ** 2) * 1e4
    f_lambda = 3.63e-9 * 10 ** (-0.4 * mag)            # V=0 Vega, erg/s/cm2/A
    unit = (f_lambda * bandwidth_nm * 10 * area_cm2
            / physics.calculate_photon_energy(central_nm))
    return (case["target"] / EXPOSURE_TIME / case["encircled"]) / unit


def preset_throughput(band):
    """optical_throughput * quantum_efficiency * filter_transmission, as shipped."""
    return 0.771 * 0.781 * PRESET_FILTERS[band][2]


# ==========================================
# Paranal's atmospheric extinction, and the VLT profile's site
# ==========================================

def paranal_extinction_curve():
    """Patat et al. 2011's measured Paranal extinction curve.

    Returns (wavelength_angstrom, k_mag_per_airmass). Source: A&A 527, A91,
    Table B.1 — spectrophotometry of 8 standard stars with FORS1, the sibling
    instrument to the FORS2 this preset models, over six months in 2008-2009.
    data/patat2011_paranal_extinction.csv is the transcription; regenerate by
    re-parsing arXiv:1011.6156's Table B.1 if it ever needs checking again.
    """
    import numpy as np
    table = np.loadtxt(
        DATA_DIR / "patat2011_paranal_extinction.csv", delimiter=",", skiprows=5)
    return table[:, 0], table[:, 1]


def paranal_extinction_for_filter(filter_wavelength_nm, filter_transmission):
    """Patat's curve, weighted by a measured filter's own transmission.

    A single band value (`presets.json`'s extinction_coeff is one number, not a
    curve) has to be *some* weighted average rather than a value picked off the
    table by eye — this is that average, done properly: interpolated onto the
    filter's own grid and weighted by its own transmission.
    """
    import numpy as np
    wl_k, k = paranal_extinction_curve()
    wl_f_a = filter_wavelength_nm * 10.0  # nm -> Angstrom, Patat's grid
    k_on_filter = np.interp(wl_f_a, wl_k, k)
    return float(np.trapezoid(k_on_filter * filter_transmission, wl_f_a)
                / np.trapezoid(filter_transmission, wl_f_a))
