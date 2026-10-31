"""Solve-for-time honours the correlated background-flatness ceiling.

`solve_required_exposures` used to assume SNR grows as sqrt(N), which ignores
the non-averaging flatness term and let solve-for-time report an exposure count
that never reached its own target (validation question 17). The solver now takes
the asymptotic ceiling from `calculate_flatness_snr_ceiling` and the response
expresses an unreachable target explicitly. These tests pin both halves of the
fixed contract on the SLT/DU934P r' preset, whose measured 2% flatness fraction
sets a ceiling near 18.5.
"""

from castor import schema
from castor.calculator import run_calculation
from castorCLI import presets


def _slt_r_request(target_snr: float) -> schema.ObservationRequest:
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
        "total_fwhm": (1.4 ** 2 + 0.2 ** 2 + 0.1 ** 2 + 0.1 ** 2) ** 0.5,
    })
    data["options"] = {
        "type": "solve_time",
        "aperture_factor": 0.85,
        "single_exp_time": 120.0,
        "sky_annulus": {"inner_factor": 3.0, "outer_factor": 5.0, "estimator": "median"},
        "target_snr": target_snr,
    }
    return schema.ObservationRequest.model_validate(data)


def test_reachable_target_actually_reaches_the_snr_it_was_asked_for():
    """A target below the ceiling returns a count whose stacked SNR meets it."""
    request = _slt_r_request(target_snr=15.0)
    response = run_calculation(request)

    assert response.core.target_reachable is True
    assert response.core.required_exposures is not None
    # The whole point of question 17: the returned frame count must actually
    # deliver at least the requested SNR, not merely satisfy a sqrt(N) formula.
    assert response.core.total_snr >= request.options.target_snr


def test_unreachable_target_is_reported_not_faked():
    """A target above the ceiling is flagged, not answered with a wrong count."""
    request = _slt_r_request(target_snr=20.0)
    response = run_calculation(request)

    assert response.core.target_reachable is False
    assert response.core.required_exposures is None
    # The best the stack can ever do is its asymptotic ceiling, which is below
    # the request; the response reports that ceiling rather than a fake count.
    assert response.core.snr_ceiling is not None
    assert request.options.target_snr > response.core.snr_ceiling
    assert response.core.total_snr == response.core.snr_ceiling
    assert any("ceiling" in w.lower() for w in response.flags.warnings)


def test_no_flatness_floor_leaves_the_ceiling_open():
    """LOT/Sophia has flatness fraction 0, so no ceiling constrains the solve."""
    data = presets.load().resolve(
        "lulin", telescope="LOT", camera="Sophia", optic_filter="Sloan_r"
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
        "total_fwhm": (1.4 ** 2 + 0.2 ** 2 + 0.1 ** 2 + 0.1 ** 2) ** 0.5,
    })
    data["options"] = {
        "type": "solve_time",
        "aperture_factor": 0.85,
        "single_exp_time": 120.0,
        "sky_annulus": {"inner_factor": 3.0, "outer_factor": 5.0, "estimator": "median"},
        "target_snr": 20.0,
    }
    response = run_calculation(schema.ObservationRequest.model_validate(data))

    assert response.core.snr_ceiling is None
    assert response.core.target_reachable is True
    assert response.core.required_exposures is not None
    assert response.core.total_snr >= 20.0
