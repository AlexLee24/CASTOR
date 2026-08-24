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


def _resolved(band):
    """The configuration a caller actually gets when they name this filter.

    Not the raw catalogue entry: the band's own sky and throughput are applied
    during resolution, which is the whole point of them living on the filter.
    """
    return presets.load().resolve(PROFILE, optic_filter=lulin.FILTER_OF[band])


def _throughput(lot, band):
    instrument = _resolved(band)["instrument"]
    return (instrument["telescope"]["optical_throughput"]
            * instrument["camera"]["quantum_efficiency"]
            * instrument["optic_filter"]["filter_transmission"])


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


def test_the_frames_are_one_target_down_one_sightline():
    """The limit that bounds most of what this suite can conclude.

    123 frames over 18 nights reads like coverage. It is not: the headers give
    four names to one supernova, so the ecliptic latitude spans 0.1 degrees, the
    galactic latitude spans 0.1, and the solar elongation spans 7. Every
    throughput, every sky brightness and every extinction coefficient here is
    measured looking in one direction.

    Asserted rather than remarked because two open questions turn on it.
    Zodiacal light and scattered starlight (QUESTIONS.md 9 and 10) cannot be
    calibrated against data with no pointing diversity, only modelled. And the
    measured mu_dark is the sky *towards ecliptic +16*, where those two are a
    large share of a moonless total — it is not a site constant, and
    presets.json has no way to say so.
    """
    s = lulin.SIGHTLINE
    assert s["targets"] == 1 and s["header_names"] == 4
    for key in ("ecliptic_latitude_deg", "galactic_latitude_deg"):
        lo, hi = s[key]
        assert hi - lo < 0.5


def test_no_night_sweeps_enough_airmass_to_fit_extinction():
    """Why QUESTIONS.md 4 needs telescope time and not more reduction.

    Fitting an airmass term needs one night that moves through airmass, so that
    transparency is held roughly fixed while the column changes. Every night
    here is a 20 to 70 minute snapshot: the largest span is 0.19 and the median
    0.08, against an overall 1.03 to 1.59 accumulated across 18 separate nights.
    What the fit measured was therefore mostly night-to-night transparency,
    which is exactly why it returned r' as the most extinguished band.
    """
    s = lulin.SIGHTLINE
    assert s["largest_single_night_airmass_span"] < 0.25
    assert s["airmass"][1] - s["airmass"][0] > 0.5   # plenty of range, wrong axis


def test_the_mirrors_are_the_ones_trebur_supplied(lot):
    """Closes the question this suite held open with a strict xfail.

    Lulin publishes the 2001 offer document, and it states both figures
    outright: primary 1030 mm outside with an optical diameter above 1020, and
    secondary 360 mm outside above 350. The preset's 300 mm had no source, and
    the 130 mm the frame headers seemed to imply was never a mirror at all.

    Light is stopped by the secondary's whole glass disc, so the obstruction is
    the outside 360 rather than the figured 350. The primary contributes its
    optical diameter, since the last 10 mm of the blank is not figured.
    """
    assert lot["telescope"].primary_mirror_diameter == lulin.OFFER["primary_optical_mm"] / 1000
    assert lot["telescope"].secondary_mirror_diameter == lulin.OFFER["secondary_outside_mm"] / 1000


def test_the_header_area_is_the_hole_in_the_primary_not_the_secondary(lot):
    """Where the phantom 130 mm secondary came from.

    APTAREA matches pi/4 * (1030^2 - 280^2) to 0.08% — the primary's outside
    diameter less the hole bored through its middle. That hole is behind the
    secondary and takes no light out of the beam that the secondary has not
    already taken; the number MaxIm wrote is not a collecting area. Read against
    a nominal 1 m aperture it implies a 130 mm obstruction, which is the value
    this suite spent a while trying to reconcile with a real mirror.

    Against the real geometry the header is 7.9% high, so it was never harmless:
    it over-states how much light the telescope collects.
    """
    import math
    hole = math.pi / 4 * ((lulin.OFFER["primary_outside_mm"] / 1000) ** 2
                          - (lulin.OFFER["primary_hole_mm"] / 1000) ** 2)
    assert lulin.HEADER_APTAREA_M2 == pytest.approx(hole, rel=0.001)
    assert lulin.HEADER_APTAREA_M2 / lot["area"] == pytest.approx(1.079, abs=0.005)


def test_adopting_the_documented_mirrors_left_the_photometry_alone(lot):
    """Why no throughput had to be refitted.

    Only the product A_eff x T_sys is constrained by the frames, so changing the
    geometry normally forces the throughput the other way. Here it did not: the
    documented 1020/360 gives 0.7153 m2 against the 0.7147 the fit assumed from
    an invented 1000/300, a difference of 0.09%. The two errors in the old pair
    had been cancelling almost exactly.

    Which is luck, not vindication — and it is the reason the *level* in
    QUESTIONS.md 1 can now be compared against the coating specification at all.
    """
    assert lot["area"] == pytest.approx(0.7153, abs=0.0002)
    assert lot["area"] / 0.7147 == pytest.approx(1.0, abs=0.002)


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


def test_the_u_band_filter_is_slt_glass_standing_in_for_lot_glass(lot):
    """u' is no longer a placeholder, and is not LOT's filter either.

    Lulin publishes no curve for LOT's up_Astrondon_2017. It does publish one
    for SLT's up_Astrodon_2018, and the preset now carries that: 353.4 nm and an
    equivalent width of 64.8 nm at unit peak, against a placeholder 354/56/0.9
    that was 14% narrow and 10% dim. Two Astrodon u' filters bought a year apart
    are close, but they are not the same piece of glass, and predictions for
    LOT u' should be read as an Astrodon u' rather than as this telescope's.
    """
    optic = lot["filters"]["Sloan_u"]
    curve = lulin.PUBLISHED_BANDPASS[("SLT", "u")]
    assert optic.filter_bandwidth * optic.filter_transmission == pytest.approx(
        curve["integral"], rel=0.02)
    assert optic.central_wavelength == pytest.approx(curve["centroid"], abs=0.5)


def test_every_filter_lulin_publishes_leaks_in_the_infrared(lot):
    """A limit on what the top-hat model can be right about, in one band badly.

    None of these filters closes in the infrared; the detector does. Below
    1100 nm, where silicon still responds, 3 to 9% of what the Sloan filters
    pass is already outside their own band — small, and absorbed by the fitted
    throughputs. Johnson U is not small: 22.6% out of band, and 96%
    transmission at 1200 nm. A rectangle cannot express that, and how much of
    the leak actually matters depends on the colour of the source, which is
    exactly what the spectral work in QUESTIONS.md 8 would fix.

    presets.json is Sloan-only, so nothing here changes a preset; it bounds how
    far the four measured Sloan entries can be trusted.
    """
    sloan = [v["leak"] for k, v in lulin.PUBLISHED_BANDPASS.items()
             if k[1] in ("u", "g", "r", "i")]
    assert max(sloan) < 0.06
    assert lulin.PUBLISHED_BANDPASS[("SLT", "U")]["leak"] > 0.20
    assert min(lulin.TRANSMISSION_AT_1200.values()) > 0.30


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


@pytest.mark.parametrize("band", ["g", "r", "i"])
def test_preset_throughput_matches_the_photometry(lot, band):
    """Each band now carries the throughput its own photometry measured.

    It reached 2.6x wrong in g' and i' while looking merely optimistic, because a
    single number was being asked to cover a quantity that runs 0.27 to 0.48
    across three filters. It lives on the filter now.
    """
    assert _throughput(lot, band) == pytest.approx(
        lulin.MEASURED[band]["throughput"], rel=0.01)


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


@pytest.mark.parametrize("band", ["g", "r", "i"])
def test_preset_mu_dark_plus_zodiacal_reproduces_the_sky_that_was_measured(band):
    """And each band carries the sky that was measured through it — split in two.

    `mu_dark` no longer carries the whole measurement (QUESTIONS.md 9/10): the
    zodiacal and scattered-starlight part our sightline happened to contain was
    split back out, so this test recombines mu_dark with zodiacal_share at the
    reference sightline (moon.ZODIACAL_REFERENCE_ECLIPTIC_LATITUDE_DEG, where the
    zodiacal shape table is 1.0 by construction) rather than reading mu_dark alone.
    The site's single 21.5 suited g' and was 1.46 mag out in i', a factor of 3.8
    in background flux. It survives as the fallback for bands nobody has measured,
    and carries no zodiacal_share to split.
    """
    env = _resolved(band)["environment"]
    b_local = 34.08 * (10.0 ** (0.4 * (22.5 - env["mu_dark"])))
    share = env["zodiacal_share"]
    b_zodi_at_reference = b_local * share / (1.0 - share)
    mu_total = 22.5 - 2.5 * np.log10((b_local + b_zodi_at_reference) / 34.08)
    assert mu_total == pytest.approx(lulin.MEASURED[band]["mu_dark"], abs=0.01)


@pytest.mark.parametrize("band", ["g", "r", "i"])
def test_preset_mu_dark_is_now_fainter_than_what_was_measured(band):
    """The local-only baseline must be strictly fainter (larger mag) than the
    original total: removing a real, positive flux component can only do that.
    """
    env = _resolved(band)["environment"]
    assert env["mu_dark"] > lulin.MEASURED[band]["mu_dark"]


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


def test_read_noise_is_the_one_the_frames_show(lot):
    """A photon transfer curve over the frames settles which readout port was used.

    var(A-B)/2 against sky level across 89 adjacent pairs: the slope confirms the
    gain and the intercept is the read noise. It lands at 7.9 e-, which is the
    datasheet's 1 MHz port and not its 100 kHz one.

    The preset carries 7.9 rather than the datasheet's 7.0, and the difference is
    a choice worth stating. An intercept collects every noise source that does
    not scale with signal, so it includes whatever residual pattern noise the
    system delivers and is an upper bound on the sensor alone. But an exposure
    time calculator predicts what an observer will measure, and that observer
    gets the pattern noise too. The datasheet number describes the detector; this
    one describes the instrument.
    """
    assert lulin.MEASURED_GAIN_SLOPE == pytest.approx(1.0, abs=0.05)
    assert lot["camera"].readout_noise == pytest.approx(lulin.MEASURED_READ_NOISE, abs=0.05)
    # Still close enough to the datasheet port that the identification holds.
    assert abs(lot["camera"].readout_noise - 7.0) < 1.5


def test_the_detector_does_not_explain_the_band_shape():
    """Measured throughput has r' at 1.8x g' and i'. QE is flat to within 10%.

    Reading the datasheet curve was worth doing because it removes the obvious
    suspect. Whatever makes r' stand out is in the optics, the atmosphere, or
    the reduction — not the sensor.
    """
    qe = lulin.DATASHEET_QE
    assert max(qe[f"Sloan_{b}"] for b in "gri") / min(qe[f"Sloan_{b}"] for b in "gri") < 1.15
    t = {b: lulin.MEASURED[b]["throughput"] for b in "gri"}
    assert max(t.values()) / min(t.values()) > 1.7
