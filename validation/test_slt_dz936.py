"""The `lulin` profile's SLT + DZ936, against the night behind it.

Companion to test_slt.py (SLT + DU934P, 2024). Every number asserted here came
out of the frames `slt_dz936.py` describes; where these disagree with
presets.json, presets.json is what is wrong.
"""
import math

import pytest

import slt_dz936 as dz
from castor import moon
from castorCLI import presets

PROFILE = "lulin"
BANDS = ["u", "g", "r", "i", "z"]
FILTER_OF = {"u": "Sloan_u", "g": "Sloan_g", "r": "Sloan_r", "i": "Sloan_i", "z": "Sloan_z"}


@pytest.fixture(scope="module")
def shipped():
    return presets.load()


def _resolved(shipped, band, camera="SLT_DZ936"):
    return shipped.resolve(PROFILE, telescope="SLT", camera=camera, optic_filter=FILTER_OF[band])


# ==========================================
# The night measured what it claims to
# ==========================================

@pytest.mark.parametrize("band", BANDS)
def test_both_branches_agree_on_extinction(band):
    """The point of this night over SN2024ggi's: the field rose and set, so a
    transparency drift would show as the two branches disagreeing. They agree
    to 0.01 in g'r' and 0.05 elsewhere — against 0.1-0.4 mag of fade that
    sank slt.py's attempt."""
    e = dz.EXTINCTION[band]
    assert abs(e["k_rising"] - e["k_setting"]) < 0.06


def test_extinction_falls_towards_the_red():
    k = {b: dz.EXTINCTION[b]["k"] for b in BANDS}
    assert k["u"] > k["g"] > k["r"] > max(k["i"], k["z"])


def test_the_fit_spans_real_airmass():
    for band in BANDS:
        lo, hi = dz.EXTINCTION[band]["airmass"]
        assert hi - lo > 1.3


# ==========================================
# presets.json carries what was measured
# ==========================================

@pytest.mark.parametrize("band", BANDS)
def test_every_band_carries_this_nights_extinction(shipped, band):
    env = _resolved(shipped, band)["environment"]
    assert env["extinction_coeff"] == pytest.approx(dz.EXTINCTION[band]["k"], abs=0.006)


@pytest.mark.parametrize("band", ["u", "z"])
def test_u_and_z_carry_their_measured_sky(shipped, band):
    """The two bands that had only the site-wide 21.5. z' was 2.8 mag too dark,
    u' 1.2 mag too bright."""
    env = _resolved(shipped, band)["environment"]
    assert env["mu_dark"] == pytest.approx(dz.SKY[band]["mu"], abs=0.005)
    assert env.get("zodiacal_share") is None


@pytest.mark.parametrize("band", ["g", "r", "i"])
def test_gri_sky_from_lot_holds_on_this_sightline(shipped, band):
    """g'r'i' were measured from LOT down one sightline (ecliptic +16). Rebuilt
    at this night's pointing (ecliptic -19) through CASTOR's own zodiacal
    baseline, they have to land within this night's scatter, plus margin."""
    env = _resolved(shipped, band)["environment"]
    predicted = moon.apply_zodiacal_baseline(
        env["mu_dark"], dz.NIGHT["ra_deg"], dz.NIGHT["dec_deg"], env["zodiacal_share"])
    assert predicted == pytest.approx(dz.SKY[band]["mu"], abs=0.25)


def test_slt_focal_length_reproduces_both_cameras_plate_scale(shipped):
    import slt
    f_m = shipped.profile(PROFILE).telescopes["SLT"].telescope.focal_length
    scale = lambda pitch_um: 206265 * pitch_um * 1e-6 / f_m
    assert scale(dz.PIXEL_PITCH_UM) == pytest.approx(dz.PIXEL_SCALE_ARCSEC, rel=0.005)
    assert scale(13.0) == pytest.approx(slt.PIXEL_SCALE_ARCSEC, rel=0.01)
    assert f_m * 1000 == pytest.approx(dz.HEADER_FOCALLEN_MM, rel=0.002)


def test_dz936_read_noise_is_the_measured_one(shipped):
    camera = shipped.profile(PROFILE).cameras["SLT_DZ936"].camera
    assert camera.readout_noise == pytest.approx(dz.READ_NOISE["header_rmsnoise"])
    assert dz.READ_NOISE["implied_u150"] == pytest.approx(camera.readout_noise, abs=0.5)


@pytest.mark.parametrize("band", BANDS)
def test_dz936_band_response_is_not_in_presets_yet(shipped, band):
    """Recorded, asserted as absent, so it cannot arrive silently.

    presets.json keys band throughput by telescope only. Putting the DZ936's
    measured response there would also move every DU934P prediction. If this
    fails, the file has learned to key by camera: replace this test with one
    asserting the values."""
    dz936 = _resolved(shipped, band, "SLT_DZ936")["instrument"]
    du934p = _resolved(shipped, band, "SLT_DU934P")["instrument"]
    assert dz936["telescope"]["optical_throughput"] == du934p["telescope"]["optical_throughput"]


def test_the_band_response_gap_is_largest_in_z_and_u():
    """Why u' and z' predictions stay worst after this night's other fixes."""
    r = dz.BAND_RESPONSE
    off = {b: abs(math.log(r[b])) for b in BANDS}
    assert max(off, key=off.get) == "z"
    assert r["z"] < 0.7 and r["u"] < 0.85


# ==========================================
# The noise model against frame-to-frame scatter
# ==========================================

@pytest.mark.parametrize("key", [k for k, v in dz.NOISE.items() if v["n"] >= 25])
def test_noise_model_holds_where_the_scatter_is_well_measured(key):
    assert dz.NOISE[key]["obs_over_pred"] == pytest.approx(1.0, abs=0.12)


def test_bright_stars_hit_a_floor_castor_does_not_model():
    bright = [v["obs_over_pred"] for (b, t, bin_), v in dz.NOISE.items()
              if bin_ in ("100-300k", "30-100k")]
    assert max(bright) < 0.9
