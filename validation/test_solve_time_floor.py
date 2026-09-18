"""The inverse solver does not yet account for correlated background noise."""

import pytest

from castor import schema
from castor.calculator import run_calculation
from castorCLI import presets


def _slt_r_request():
    data = presets.load().resolve(
        "lulin", telescope="SLT", camera="SLT_DU934P", optic_filter="Sloan_r"
    )
    data["instrument"]["throughput_correction"] = 1.0
    data["target"] = {
        "morphology": {"type": "point"},
        "brightness": {"type": "ab_mag", "target_mag": 20.0},
        "sed": {"type": "flat"},
        "ra": 113.65,
        "dec": 31.89,
    }
    data["environment"].update({
        "observing_time_utc": "2026-01-15T16:00:00Z",
        "auto_calc_background": False,
        "seeing_fwhm": 1.4,
        "diffraction_fwhm": 0.2,
        "optical_fwhm": 0.1,
        "tracking_fwhm": 0.1,
    })
    data["options"] = {
        "type": "solve_time",
        "aperture_factor": 0.85,
        "single_exp_time": 120.0,
        "sky_annulus": {"inner_factor": 3.0, "outer_factor": 5.0, "estimator": "median"},
        "target_snr": 20.0,
    }
    return schema.ObservationRequest.model_validate(data)


@pytest.mark.xfail(
    strict=True,
    reason="solve_required_exposures assumes sqrt(N) despite the non-averaging flatness term",
)
def test_solve_time_reaches_the_snr_it_was_asked_for():
    request = _slt_r_request()
    response = run_calculation(request)
    assert response.core.total_snr >= request.options.target_snr


def test_solve_time_discloses_when_estimate_misses_target():
    request = _slt_r_request()
    response = run_calculation(request)
    assert response.core.total_snr < request.options.target_snr
    assert any("does not reach the requested SNR" in warning for warning in response.flags.warnings)
