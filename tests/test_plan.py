"""Simple mode's planner (castorCLI/plan.py) and the route that serves it.

The compute_plan tests are Kinder's own (Kinder_web tests/test_etc_quick.py), moved here
with the module, so the copy that now lives in CASTOR is held to what Kinder already
checked. The target is placed near the zenith over Lulin (RA 22h, Dec +20 at 14:00
UTC on 2025-09-28).
"""
import asyncio
import json

import pytest

from castorCLI import presets
from castorCLI.plan import (PREFERRED_EXPOSURES, QuickInputError, compute_plan, compute_snr,
                            parse_coordinates)

WHEN = "2025-09-28T14:00:00Z"


@pytest.fixture(scope="module")
def catalogue():
    return presets.load()


def plan(catalogue, **overrides):
    args = dict(site="lulin", telescope="LOT", camera="Sophia", optic_filter="Sloan_r",
                ra=330.0, dec=20.0, mag=21.0, target_snr=10.0,
                observing_time_utc=WHEN, fwhm=1.4)
    args.update(overrides)
    return compute_plan(catalogue, **args)


def test_recommended_plan_reaches_the_target(catalogue):
    result = plan(catalogue)
    assert result["status"] == "ok"
    rec = result["recommended"]
    assert rec["snr"] >= 10.0
    assert rec["exp_s"] < result["conditions"]["saturation_time_s"]
    # The least time at the telescope once each frame's readout is paid for.
    assert rec["elapsed_s"] == min(row["elapsed_s"] for row in result["rows"])
    assert rec["exp_s"] in PREFERRED_EXPOSURES


def test_few_long_frames_beat_many_short_ones(catalogue):
    """30 s x 1 rather than 8 s x 4: the same integration, three readouts fewer."""
    result = plan(catalogue, ra=109.143762, dec=38.352239, mag=19.8, fwhm=1.0,
                  observing_time_utc="2026-10-31T22:00:00Z")
    assert result["recommended"]["frames"] == 1
    assert min(row["exp_s"] for row in result["rows"]) == 15


def test_single_frame_time_is_what_castor_says(catalogue):
    """The closed-form single-frame time, fed back to CASTOR, gives the target SNR."""
    from castor import schema
    from castor.calculator import run_calculation

    result = plan(catalogue)
    t_one = result["single_frame_time_s"]
    request = catalogue.resolve("lulin", "LOT", "Sophia", "Sloan_r")
    request["target"] = {"ra": 330.0, "dec": 20.0, "morphology": {"type": "point"},
                         "sed": {"type": "flat"}, "brightness": {"type": "ab_mag", "target_mag": 21.0}}
    request["environment"].update({"total_fwhm": 1.4, "observing_time_utc": WHEN, "auto_calc_background": True})
    request["instrument"]["throughput_correction"] = 1.0
    request["options"] = {"type": "solve_snr", "num_exposures": 1, "single_exp_time": t_one,
                          "aperture_factor": 0.85,
                          "sky_annulus": {"inner_factor": 3.0, "outer_factor": 5.0, "estimator": "median"}}
    snr = run_calculation(schema.ObservationRequest.model_validate(request)).core.total_snr
    assert snr == pytest.approx(10.0, rel=1e-6)


def test_faint_target_needs_several_frames(catalogue):
    result = plan(catalogue, mag=23.5)
    assert result["recommended"]["frames"] > 1
    assert [row["exp_s"] for row in result["rows"]] == sorted(row["exp_s"] for row in result["rows"])


def test_target_below_the_horizon(catalogue):
    result = plan(catalogue, ra=150.0)
    assert result["status"] == "below_horizon"
    assert result["rows"] == []


def test_bright_star_saturates(catalogue):
    result = plan(catalogue, mag=6.0)
    assert result["status"] == "saturated"


# ==========================================
# compute_snr: the frames in, their SNR out
# ==========================================

def snr(catalogue, **overrides):
    args = dict(site="lulin", telescope="LOT", camera="Sophia", optic_filter="Sloan_r",
                ra=330.0, dec=20.0, mag=21.0, single_exp_time=120.0, num_exposures=3,
                observing_time_utc=WHEN, fwhm=1.4)
    args.update(overrides)
    return compute_snr(catalogue, **args)


def test_snr_is_what_castor_says_for_those_frames(catalogue):
    """The answer is Advanced mode's solve_snr on the same request, number for number."""
    from castor import schema
    from castor.calculator import run_calculation

    result = snr(catalogue)
    request = catalogue.resolve("lulin", "LOT", "Sophia", "Sloan_r")
    request["target"] = {"ra": 330.0, "dec": 20.0, "morphology": {"type": "point"},
                         "sed": {"type": "flat"}, "brightness": {"type": "ab_mag", "target_mag": 21.0}}
    request["environment"].update({"total_fwhm": 1.4, "observing_time_utc": WHEN, "auto_calc_background": True})
    request["instrument"]["throughput_correction"] = 1.0
    request["options"] = {"type": "solve_snr", "num_exposures": 3, "single_exp_time": 120.0,
                          "aperture_factor": 0.85,
                          "sky_annulus": {"inner_factor": 3.0, "outer_factor": 5.0, "estimator": "median"}}
    core = run_calculation(schema.ObservationRequest.model_validate(request)).core

    assert result["status"] == "ok"
    assert result["goal"] == "solve_snr"
    assert result["chosen"]["snr"] == pytest.approx(core.total_snr, rel=1e-12)
    assert result["chosen"]["single_snr"] == pytest.approx(core.single_snr, rel=1e-12)
    assert result["chosen"]["total_s"] == 360.0


def test_the_same_total_split_into_more_frames_loses_snr(catalogue):
    """Every row integrates the same 360 s; each extra readout costs SNR."""
    rows = snr(catalogue)["rows"]

    assert [row["frames"] for row in rows] == sorted(row["frames"] for row in rows)
    assert all(row["total_s"] == pytest.approx(360.0) for row in rows)
    assert [row["snr"] for row in rows] == sorted((row["snr"] for row in rows), reverse=True)
    assert [row["frames"] for row in rows if row.get("chosen")] == [3]


def test_frames_longer_than_saturation_are_flagged(catalogue):
    result = snr(catalogue, mag=9.0, single_exp_time=300.0, num_exposures=1)

    assert result["status"] == "saturated"
    assert result["chosen"]["saturates"]
    t_sat = result["conditions"]["saturation_time_s"]
    assert all(row["saturates"] == (row["exp_s"] >= t_sat) for row in result["rows"])


def test_snr_for_a_target_below_the_horizon(catalogue):
    result = snr(catalogue, ra=150.0)
    assert result["status"] == "below_horizon"
    assert result["rows"] == []


@pytest.mark.parametrize("change", [{"single_exp_time": 0}, {"num_exposures": 0}, {"num_exposures": 1.5}])
def test_frames_must_be_real(catalogue, change):
    with pytest.raises(QuickInputError):
        snr(catalogue, **change)


def test_coordinates_in_either_notation():
    assert parse_coordinates("22:00:00", "+20:00:00") == pytest.approx((330.0, 20.0))
    assert parse_coordinates("330", "20") == pytest.approx((330.0, 20.0))
    with pytest.raises(QuickInputError):
        parse_coordinates("xyz", "1")


# ==========================================
# The quick route
# ==========================================
#
# Called directly with a stand-in request, as test_gui_server.py calls the presets
# route: what is under test is what the route does with the body, not FastAPI.

class _Body:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


def quick(data):
    from castorGUI import server
    response = asyncio.run(server.calculate_quick(_Body(data)))
    return response.status_code, json.loads(response.body)


@pytest.fixture(autouse=True)
def no_extra_presets(monkeypatch):
    monkeypatch.delenv(presets.PATH_VARIABLE, raising=False)


FORM = {"site": "lulin", "telescope": "LOT", "camera": "Sophia", "filter": "Sloan_r",
        "ra": "22:00:00", "dec": "+20:00:00", "mag": 21.0, "target_snr": 10.0,
        "fwhm": 1.4, "observing_time_utc": WHEN}


def test_the_route_returns_the_planners_answer(catalogue):
    """What Simple mode posts, in the shape Kinder's route of the same path answers.
    Degrees rather than FORM's sexagesimal, so the comparison can be exact: 22:00:00
    converts to 330 only to the last bit, which moves the airmass in the 16th digit."""
    status, body = quick({**FORM, "ra": "330", "dec": "20"})

    assert status == 200
    assert body == json.loads(json.dumps(plan(catalogue)))


def test_the_route_solves_for_snr_when_asked(catalogue):
    """goal takes Advanced mode's names; solve_snr posts the frames instead of an SNR."""
    status, body = quick({**FORM, "ra": "330", "dec": "20", "goal": "solve_snr",
                          "target_snr": None, "single_exp_time": 120, "num_exposures": 3})

    assert status == 200
    assert body == json.loads(json.dumps(snr(catalogue)))


def test_the_route_reads_the_same_presets_the_form_is_offered(monkeypatch, tmp_path):
    """A profile served by the presets route (here one from CASTOR_PRESETS_PATH) is one
    the quick route can resolve, so no choice in the Simple form is a dead end."""
    path = tmp_path / "backyard.json"
    path.write_text(json.dumps({"profiles": {"backyard": {
        "name": "Backyard",
        "environment": {"location": {"latitude_deg": 23.47, "longitude_deg": 120.87, "elevation_m": 2862.0},
                        "mu_dark": 21.5, "extinction_coeff": 0.17},
        "telescopes": {"C8": {"telescope": {"primary_mirror_diameter": 0.203, "secondary_mirror_diameter": 0.07,
                                            "focal_length": 2.032, "optical_throughput": 0.8}}},
        "cameras": {"CCD": {"camera": {"pixel_pitch": 9.0, "quantum_efficiency": 0.8, "dark_current_rate": 0.01,
                                       "readout_noise": 8.0, "full_well_capacity": 50000}}},
        "filters": {"R": {"optic_filter": {"central_wavelength": 640.0, "filter_bandwidth": 150.0,
                                           "filter_transmission": 0.9}}},
    }}}), encoding="utf-8")
    monkeypatch.setenv(presets.PATH_VARIABLE, str(path))

    status, body = quick({**FORM, "site": "backyard", "telescope": "C8", "camera": "CCD", "filter": "R", "mag": 15})

    assert status == 200, body
    assert body["labels"]["telescope"] == "C8"


@pytest.mark.parametrize("change, message", [
    ({"ra": ""}, "Enter the target RA and Dec."),
    ({"mag": None}, "Fill in the magnitude, target SNR and seeing."),
    ({"site": "nowhere"}, "Unknown profile 'nowhere'"),
    ({"fwhm": 0}, "Seeing must be a positive number"),
    ({"goal": "solve_snr"}, "Fill in the magnitude, exposure time and seeing."),
    ({"goal": "solve_snr", "single_exp_time": 60, "num_exposures": 0}, "Number of exposures must be"),
    ({"goal": "solve_everything"}, "Unknown goal 'solve_everything'"),
])
def test_bad_input_is_a_readable_400(change, message):
    status, body = quick({**FORM, **change})

    assert status == 400
    assert message in body["error"]


def test_an_empty_body_is_refused():
    status, body = quick({})

    assert status == 400
    assert body == {"error": "No data provided"}
