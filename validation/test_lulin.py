"""The `lulin` profile against the telescope it claims to describe.

These are the only tests in the repository backed by real photons. Where they
disagree with presets.json, presets.json is what is wrong.
"""
import json
import pathlib

import numpy as np
import pytest

import lulin
from castor import physics
from castorCLI import presets

PROFILE = "lulin"


@pytest.fixture(scope="module")
def lot():
    """Telescope, camera and derived geometry as the shipped preset defines them."""
    profile = presets.load().profile(PROFILE)
    telescope = profile.telescopes["LOT"].telescope
    camera = profile.cameras["Sophia"].camera
    return dict(
        telescope=telescope,
        camera=camera,
        environment=profile.environment,
        area=float(physics.calculate_effective_area(
            telescope.primary_mirror_diameter, telescope.secondary_mirror_diameter)),
        scale=float(physics.calculate_pixel_scale(
            camera.pixel_pitch, telescope.focal_length)),
        filters={k: v.optic_filter for k, v in profile.filters.items()},
    )


def _throughput(lot, band):
    optic = lot["filters"][lulin.FILTER_OF[band]]
    return (lot["telescope"].optical_throughput
            * lot["camera"].quantum_efficiency
            * optic.filter_transmission)


def _rate_per_unit_throughput(lot, band, ab_mag):
    """e-/s above the atmosphere for a source of this AB magnitude, at T_sys = 1."""
    optic = lot["filters"][lulin.FILTER_OF[band]]
    return (physics.convert_ab_to_wavelength_flux(ab_mag, optic.central_wavelength)
            * optic.filter_bandwidth * 10 * lot["area"] * 1e4
            / physics.calculate_photon_energy(optic.central_wavelength))


# ==========================================
# Geometry, which the frames settle outright
# ==========================================

def test_the_preset_reproduces_the_solved_plate_scale(lot):
    """Astrometry.net solves 0.3841"/pix against a star catalogue on every frame.

    Pixel scale is the one geometric quantity the images measure directly, and
    it enters the sky background as its square, so getting it right is worth
    more than it looks. The preset's focal length exists to reproduce it.
    """
    assert lot["scale"] == pytest.approx(lulin.SOLVED_PIXEL_SCALE, rel=0.002)


def test_sophia_pixels_are_fifteen_microns(lot):
    """Header XPIXSZ, the datasheet and the e2v CCD230-42 spec all agree."""
    assert lot["camera"].pixel_pitch == 15.0


@pytest.mark.xfail(
    strict=True,
    reason="Every frame header carries APTAREA 772125 mm2, which is a 130 mm "
           "central obstruction on the 1 m primary. The preset says 300 mm, "
           "typical for an f/8 Ritchey-Chretien. They differ by 8% in "
           "collecting area and Lulin publishes neither. Needs asking.",
)
def test_collecting_area_agrees_with_the_frame_headers(lot):
    assert lot["area"] == pytest.approx(lulin.HEADER_APTAREA_M2, rel=0.01)


# ==========================================
# Bandpasses, from Lulin's published curves
# ==========================================

@pytest.mark.parametrize("name", sorted(lulin.MEASURED_BANDPASS))
def test_filters_match_their_measured_curves(lot, name):
    """bandwidth x transmission has to equal the curve's integral, or nothing else can be right.

    Before these were corrected the four Sloan entries carried a flat 0.9
    transmission and three shared a bandwidth of 137 nm — z' was out by 55%,
    being a 278 nm filter described as a 137 nm one.
    """
    optic = lot["filters"][name]
    curve = lulin.MEASURED_BANDPASS[name]
    # FWHM x peak only equals the integral for a perfectly square filter; the
    # Astrodon curves have shoulders, and z' is 1% wide of its own integral.
    assert optic.filter_bandwidth * optic.filter_transmission == pytest.approx(
        curve["integral"], rel=0.02)
    assert optic.central_wavelength == pytest.approx(curve["centroid"], abs=0.5)


def test_the_u_band_filter_is_still_unverified(lot):
    """Lulin publishes no curve for LOT u', so it keeps the placeholder shape.

    Marked here rather than silently left: 0.9 transmission is what the other
    four carried before measurement, and all four turned out wrong.
    """
    assert lot["filters"]["Sloan_u"].filter_transmission == 0.9


# ==========================================
# Throughput and sky, against the photometry
# ==========================================

@pytest.mark.parametrize("band", ["g", "r", "i"])
def test_measured_zero_points_are_self_consistent(band):
    """Guards the reduction, not the engine: ZP0 must reproduce its own throughput."""
    m = lulin.MEASURED[band]
    assert 22.0 < m["zp0"] < 25.0
    assert 0.0 < m["throughput"] < 1.0
    assert m["nights"] >= 7


@pytest.mark.xfail(
    strict=True,
    reason="Pan-STARRS photometry puts LOT+SOPHIA at T_sys 0.265 (g'), 0.480 "
           "(r'), 0.265 (i'). The preset's optical_throughput 0.804 x QE 0.85 "
           "x the measured filter transmissions gives 0.68 in every band: too "
           "high by 2.6x, 1.4x, 2.6x. Worse, the real throughput is strongly "
           "band-dependent and the schema has nowhere band-dependent to put it "
           "except filter_transmission, which is already spoken for by the "
           "measured curves. See the questions in validation/README.md.",
)
@pytest.mark.parametrize("band", ["g", "r", "i"])
def test_preset_throughput_matches_the_photometry(lot, band):
    assert _throughput(lot, band) == pytest.approx(
        lulin.MEASURED[band]["throughput"], rel=0.15)


@pytest.mark.parametrize("band", ["g", "r", "i"])
def test_the_measured_throughput_reproduces_the_measured_sky(lot, band):
    """The loop closes: photometry gives T_sys, and T_sys turns sky counts into mu_dark.

    Not a test of the preset — a test that the two independent measurements in
    `lulin.MEASURED` are consistent with each other through CASTOR's own
    equations. If this breaks, the reduction is wrong, not the engine.
    """
    m = lulin.MEASURED[band]
    rate = (_rate_per_unit_throughput(lot, band, m["mu_dark"])
            * m["throughput"] * lot["scale"] ** 2)
    assert rate == pytest.approx(m["sky_rate"], rel=0.02)


@pytest.mark.xfail(
    strict=True,
    reason="Sky brightness is strongly band-dependent — measured 21.44 (g'), "
           "20.92 (r'), 20.04 (i') — but mu_dark is one number on the profile's "
           "environment, shared by every filter. The shipped 21.5 happens to "
           "suit g' and is 1.46 mag out in i', a factor of 3.8 in background "
           "flux. Not parametrised: one value cannot be right for all three, "
           "which is the point.",
)
def test_preset_mu_dark_matches_the_sky_that_was_measured(lot):
    for band in ("g", "r", "i"):
        assert lot["environment"].mu_dark == pytest.approx(
            lulin.MEASURED[band]["mu_dark"], abs=0.15)


def test_the_sky_is_bluer_than_one_number_can_describe():
    """Quantifies the spread, so the size of the problem above stays on record."""
    values = [lulin.MEASURED[b]["mu_dark"] for b in ("g", "r", "i")]
    assert max(values) - min(values) > 1.3
    assert values == sorted(values, reverse=True)   # bluer sky is darker


@pytest.mark.xfail(
    strict=True,
    reason="extinction_coeff is one number per site, 0.17. The fit gives 0.189 "
           "(r', +/-0.027) but only 0.123 +/- 0.105 (g') and 0.108 +/- 0.049 "
           "(i'), and g'/i' have too little airmass range over too few nights "
           "to be worth adopting. Wavelength ordering is wrong too: extinction "
           "should fall towards the red and r' comes out highest. Needs frames "
           "spanning airmass on a single photometric night.",
)
def test_extinction_falls_towards_the_red():
    k = [lulin.MEASURED[b]["k"] for b in ("g", "r", "i")]
    assert k == sorted(k, reverse=True)


# ==========================================
# The reduction is reproducible
# ==========================================

def test_the_frames_and_catalogue_are_where_the_module_says():
    if not lulin.available():
        pytest.skip("science frames not checked out; see data/lulin/README.md")
    assert len(list(lulin.FRAMES.glob("*.fits"))) > 50
    assert len(list(lulin.CATALOGUE.glob("*.csv"))) >= 1
