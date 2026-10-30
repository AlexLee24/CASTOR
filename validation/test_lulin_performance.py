"""Structural checks for the forward-only Lulin capability curves.

The full sweep behind the forward-performance report section (2 telescopes x 3 bands x 101
magnitudes x 9 frame counts, see analyze_lulin_performance.py) is entirely
synthetic - the forward model evaluated over a grid, nothing measured - and
fully reproducible from the code and presets.json already in this repo, so
the 5000+-row table itself is not committed (see .gitignore and each
report's "Regenerate with" command). These two properties are checked
directly against a handful of live requests instead, which also keeps
`pytest validation` free of a pandas/matplotlib dependency it doesn't
otherwise need.
"""

import numpy as np

from castor import schema
from castor.calculator import run_calculation
from castorCLI import presets


RIGS = {"LOT": "Sophia", "SLT": "SLT_DU934P"}
FILTERS = {"g": "Sloan_g", "r": "Sloan_r", "i": "Sloan_i"}
OBSERVING_TIME = "2026-01-15T16:00:00Z"
TARGET_RA_DEG = 113.65
TARGET_DEC_DEG = 31.89


def _request(telescope, band, magnitude, frame_count):
    data = presets.load().resolve(
        "lulin", telescope=telescope, camera=RIGS[telescope], optic_filter=FILTERS[band]
    )
    data["instrument"]["throughput_correction"] = 1.0
    data["target"] = {
        "morphology": {"type": "point"},
        "brightness": {"type": "ab_mag", "target_mag": magnitude},
        "sed": {"type": "flat"},
        "ra": TARGET_RA_DEG,
        "dec": TARGET_DEC_DEG,
    }
    data["environment"].update({
        "observing_time_utc": OBSERVING_TIME,
        "auto_calc_background": False,
        "total_fwhm": (1.4 ** 2 + 0.2 ** 2 + 0.1 ** 2 + 0.1 ** 2) ** 0.5,
    })
    data["options"] = {
        "type": "solve_snr",
        "aperture_factor": 0.85,
        "single_exp_time": 120.0,
        "sky_annulus": {"inner_factor": 3.0, "outer_factor": 5.0, "estimator": "median"},
        "num_exposures": frame_count,
    }
    return schema.ObservationRequest.model_validate(data)


def _snr(telescope, band, magnitude, frame_count):
    request = _request(telescope, band, magnitude, frame_count)
    return run_calculation(request).core.total_snr


def test_every_forward_curve_gets_fainter_and_deeper_monotonically():
    magnitudes = [15.0, 17.0, 19.0, 21.0, 23.0, 25.0]
    for telescope in RIGS:
        for band in FILTERS:
            for frame_count in (1, 30, 120):
                snr = np.array([_snr(telescope, band, m, frame_count) for m in magnitudes])
                assert np.all(np.diff(snr) < 0)


def test_lot_obeys_sqrt_n_while_slt_flatness_grows_sublinearly():
    assert np.isclose(
        _snr("LOT", "r", 20.0, 120) / _snr("LOT", "r", 20.0, 1),
        np.sqrt(120),
        rtol=1e-6,
    )
    assert _snr("SLT", "r", 20.0, 120) / _snr("SLT", "r", 20.0, 1) < 3.0
