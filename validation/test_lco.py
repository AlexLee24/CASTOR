"""CASTOR against Las Cumbres Observatory's published calculator.

What can and cannot be concluded from these numbers is set out in lco_etc.py:
their calculator looks up measured zero points, so this compares a prediction
against a calibration, and the interesting output is *which* differences are
structural rather than how large any single one is.
"""
import inspect

import numpy as np
import pytest

import lco_etc
from castor import physics

# Captured from the live page on 2026-08-22, exposure time 100 s, mag 18.
LIVE_PAGE = (
    # instrument, band, airmass, moon, sky e-/pix, SNR
    (1, "V", 1.0, 0, 87.1, 104.7),
    (1, "V", 1.2, 0, 87.1, 103.2),
    (1, "r", 1.5, 1, 416.8, 97.6),
)


@pytest.mark.parametrize("instrument,band,airmass,moon,sky,snr", LIVE_PAGE)
def test_transcription_still_matches_the_live_page(instrument, band, airmass, moon, sky, snr):
    """Guards the transcription, and catches LCO quietly revising their tables."""
    assert lco_etc.sky_rate(instrument, band, moon) * 100 == pytest.approx(sky, abs=0.05)
    assert lco_etc.snr(instrument, band, 18.0, airmass, 100.0, moon) == pytest.approx(snr, abs=0.05)


def test_neither_engine_extinguishes_the_sky():
    """Both hold the background fixed as the target sinks, and for the same reason.

    `mu_dark` is measured looking up through the atmosphere, so the atmosphere is
    already inside it; extinguishing it again would be counting the same air
    twice. CASTOR used to do exactly that, which made its sky *fall* with airmass
    — the one direction no sky does — and the term is gone (calculator.py, ATBD
    4.2.2 C). ESO's grows instead, which is the remaining open disagreement and
    is recorded as an xfail in test_eso.py.

    Asserted structurally rather than by sampling: `calculate_sky_background_rate`
    takes no airmass, so there is nowhere for the dependence to re-enter.
    """
    assert "airmass" not in inspect.signature(
        physics.calculate_sky_background_rate).parameters
    assert "airmass" not in inspect.signature(lco_etc.sky_rate).parameters

    # The target does depend on it, in both, so the absence above is a decision
    # about the sky rather than an airmass term nobody implemented.
    assert "airmass" in inspect.signature(lco_etc.source_rate).parameters
    assert lco_etc.source_rate(1, "V", 18.0, 2.0) < lco_etc.source_rate(1, "V", 18.0, 1.0)


@pytest.mark.parametrize("band", lco_etc.FILTERS)
def test_castor_reproduces_the_lco_zero_point_exactly(band):
    """Calibrate CASTOR's optical train to their zero point and the sky agrees.

    Not a coincidence and not a check of the physics — it says the two count-rate
    chains are the same algebra, so every difference measured elsewhere in this
    file is a difference of convention or of input, never of formula.
    """
    instrument = 1
    f = lco_etc.FILTERS.index(band)
    throughput = lco_etc.implied_throughput(instrument, band)
    mu = lco_etc.SKY_BRIGHTNESS[0][f]
    lam_nm = lco_etc.CENTRAL_WAVELENGTH_UM[f] * 1e3

    zero_point_flux = (lco_etc.ZERO_POINT_JY[f] * 1e-23
                       * (physics.SPEED_OF_LIGHT_CGS * 1e8) / (lam_nm * 10.0) ** 2)
    castor = physics.calculate_sky_background_rate(
        f_lambda_sky=zero_point_flux * 10.0 ** (-0.4 * mu),
        filter_bandwidth=lco_etc.BANDWIDTH_UM[f] * 1e3,
        effective_area=lco_etc.COLLECTING_AREA_CM2[instrument] / 1e4,
        photon_energy=physics.calculate_photon_energy(lam_nm),
        total_throughput=throughput,
        pixel_scale=lco_etc.PIXEL_SCALE[instrument],
    )
    assert castor == pytest.approx(lco_etc.sky_rate(instrument, band, 0), rel=1e-9)


def test_their_zero_points_do_not_correspond_to_one_throughput():
    """So no single optical_throughput can make a preset match them across bands.

    Sinistro's implied throughput spans more than a factor of ten. The middle of
    that range is a believable optical train; u' and Y are not, and are better
    read as bands nobody has re-measured than as physics CASTOR should chase.
    """
    implied = {band: lco_etc.implied_throughput(1, band) for band in lco_etc.FILTERS}
    assert max(implied.values()) / min(implied.values()) > 10.0
    assert 0.2 < implied["V"] < 0.6
    assert implied["Y"] < 0.05


def test_the_airmass_convention_is_a_flat_per_band_offset():
    """A constant ratio, which is the shape a mis-set constant also has.

    Anyone comparing a fixed configuration against LCO and finding the same small
    percentage every run should rule this out first: it is a pure function of the
    band and the airmass, and completely independent of magnitude and exposure.
    """
    for band in lco_etc.FILTERS:
        k = lco_etc.EXTINCTION[lco_etc.FILTERS.index(band)]
        ratios = {
            magnitude: (lco_etc.source_rate(1, band, magnitude, 1.5)
                        / (10.0 ** (-0.4 * (magnitude + 1.5 * k
                                            - lco_etc.ZERO_POINT_MAG[1][lco_etc.FILTERS.index(band)]))))
            for magnitude in (12.0, 18.0, 24.0)
        }
        assert np.ptp(list(ratios.values())) < 1e-12
        assert ratios[18.0] == pytest.approx(10.0 ** (0.4 * k), rel=1e-12)
