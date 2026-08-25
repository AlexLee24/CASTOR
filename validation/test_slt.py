"""The `lulin` profile's SLT half, against the night that measured it.

Companion to test_lulin.py, which does the same job for LOT. Where these
disagree with presets.json, presets.json is what is wrong — every number
asserted here came out of real frames, and `slt.py` records how.
"""
import pytest

import slt
from castor import physics
from castorCLI import presets

PROFILE = "lulin"
BANDS = ["u", "g", "r", "i", "z"]


@pytest.fixture(scope="module")
def shipped():
    return presets.load()


def _resolved(shipped, band):
    """What a caller naming SLT and this filter actually receives."""
    return shipped.resolve(PROFILE, telescope="SLT", camera="SLT_DU934P",
                           optic_filter=slt.FILTER_OF[band])


# ==========================================
# The reduction is self-consistent
# ==========================================

@pytest.mark.parametrize("band", BANDS)
def test_the_fit_kept_most_of_the_night(band):
    """Guards the reduction, not the engine. A clip that threw away most of a
    night would mean the fit, not the weather, was the problem."""
    m = slt.MEASURED[band]
    assert m["n_kept"] >= 0.7 * m["n_total"]
    assert m["n_kept"] >= 30


@pytest.mark.parametrize("band", BANDS)
def test_every_band_has_a_believable_throughput(band):
    m = slt.MEASURED[band]
    assert 0.0 < m["throughput"] < 1.0
    assert m["optical"] >= m["throughput"]      # dividing out QE and filter can only raise it


def test_extinction_falls_towards_the_red():
    """The thing lulin.py could not do, and the reason this night was worth reducing.

    Rayleigh scattering goes as lambda^-4, so extinction must fall monotonically
    from u' to z'. The LOT 18-night fit puts r' highest instead — a real result
    of too little airmass range per night, still recorded as a strict xfail in
    test_lulin.py. This dataset gets the ordering right, which is the evidence
    that the airmass sweep is what mattered.
    """
    k = [slt.MEASURED[b]["k"] for b in BANDS]
    assert k == sorted(k, reverse=True)


def test_the_extinction_ordering_is_not_within_the_errors():
    """Monotonic ordering means little if every band overlaps every other.

    Checks the span rather than adjacent pairs: u' and z' are separated by many
    times their combined uncertainty, so the trend is real even though the
    neighbouring bands are not each individually resolved.
    """
    u, z = slt.MEASURED["u"], slt.MEASURED["z"]
    separation = u["k"] - z["k"]
    combined_error = (u["k_err"] ** 2 + z["k_err"] ** 2) ** 0.5
    assert separation > 4 * combined_error


# ==========================================
# presets.json carries what was measured
# ==========================================

@pytest.mark.parametrize("band", BANDS)
def test_preset_extinction_matches_the_fit(shipped, band):
    """Each band carries its own measured extinction, not the site's fallback."""
    environment = _resolved(shipped, band)["environment"]
    assert environment["extinction_coeff"] == pytest.approx(slt.MEASURED[band]["k"], abs=0.001)
    assert environment["extinction_coeff"] != shipped.profile(PROFILE).environment.extinction_coeff


@pytest.mark.parametrize("band", BANDS)
def test_preset_throughput_reproduces_the_measured_total(shipped, band):
    """The loop closes: what the file stores, multiplied back out by the engine's
    own chain, has to return the T_sys the photometry measured.

    This is the test that would have caught storing a raw T_sys where an implied
    optical train belongs, which is a factor of QE — about 20% — and exactly the
    shape of the FORS2 mistake this suite spent the month unpicking.
    """
    instrument = _resolved(shipped, band)["instrument"]
    reassembled = (instrument["telescope"]["optical_throughput"]
                   * instrument["camera"]["quantum_efficiency"]
                   * instrument["optic_filter"]["filter_transmission"])
    assert reassembled == pytest.approx(slt.MEASURED[band]["throughput"], rel=0.02)


@pytest.mark.parametrize("band", BANDS)
def test_the_file_stores_the_optical_train_not_the_total(shipped, band):
    """And states which of the two conventions the number is in."""
    instrument = _resolved(shipped, band)["instrument"]
    expected = slt.implied_optical_throughput(
        band,
        instrument["camera"]["quantum_efficiency"],
        instrument["optic_filter"]["filter_transmission"],
    )
    assert instrument["telescope"]["optical_throughput"] == pytest.approx(expected, abs=0.002)


def test_the_telescope_fallback_is_the_geometric_mean_of_its_bands(shipped):
    """A band with no measurement of its own falls back to the telescope's number,
    so that number has to represent the set rather than any one member."""
    optical = [slt.MEASURED[b]["optical"] for b in BANDS]
    geometric_mean = 1.0
    for value in optical:
        geometric_mean *= value
    geometric_mean **= 1.0 / len(optical)

    stored = shipped.profile(PROFILE).telescopes["SLT"].telescope.optical_throughput
    assert stored == pytest.approx(geometric_mean, abs=0.002)


# ==========================================
# SLT against LOT
# ==========================================

def test_slt_is_not_more_efficient_than_lot(shipped):
    """The guess this replaced said it was, and there was never a reason to think so.

    presets.json used to give SLT 0.804 against LOT's measured 0.27-0.48 — a
    40 cm beating a metre by nearly two to one, unsourced. QUESTIONS.md 5 flagged
    it as implausible before there was any photometry to check it with; there now
    is, and it was implausible.
    """
    slt_optical = shipped.profile(PROFILE).telescopes["SLT"].telescope.optical_throughput
    lot_optical = shipped.profile(PROFILE).telescopes["LOT"].telescope.optical_throughput
    assert slt_optical < lot_optical
    assert slt_optical < 0.804 / 2      # the old guess was more than twice too high


def test_the_night_actually_swept_airmass():
    """The one property that makes this dataset able to measure extinction at all,
    asserted so a future reduction cannot quietly lose it."""
    low, high = slt.NIGHT["airmass"]
    assert high - low > 1.5
