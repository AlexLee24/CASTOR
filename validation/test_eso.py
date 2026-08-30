"""The VLT/FORS2 preset against ESO's own calculator and sky model.

Two references, doing different jobs. `eso_etc` is ESO's exposure time
calculator, which is the ground truth for what this instrument actually
collects; `skycalc` is their sky radiance model, which is the ground truth for
what the bandpass sees.

The headline is not what it looks like from the filter curve alone. The preset's
`filter_transmission` of 0.51 sits well below the measured curve's peak of 0.897,
which looks like an error until you ask ESO what the whole chain collects — and
find the preset within 8% for that filter. It is within 8% because 0.51 is
absorbing an `optical_throughput * quantum_efficiency` that is roughly twice too
optimistic. The filter that kept a believable transmission does not get that
cancellation, and is out by a factor of two and a half.
"""
import inspect

import numpy as np
import pytest

import eso_etc
import skycalc
from castor import physics
from castorCLI import presets

#: The VLT/FORS2 preset's own hardware, as presets.json describes it.
EFFECTIVE_AREA_M2 = np.pi / 4.0 * (8.0 ** 2 - 1.088 ** 2)
OPTICS_AND_DETECTOR = 0.771 * 0.781          # optical_throughput * quantum_efficiency
PIXEL_SCALE = 206264.80624709636 * 15e-6 / 24.75

#: The FWHM CASTOR is given for these cases, in arcsec: 0.8" seeing (ESO's
#: turbulence category 50) in quadrature with the preset's 0.2" diffraction,
#: 0.1" optical and 0.1" tracking terms. ESO does not take a FWHM, it derives
#: one — see `_eso_image_quality`.
PRESET_FWHM = np.sqrt(0.8 ** 2 + 0.2 ** 2 + 0.1 ** 2 + 0.1 ** 2)


@pytest.fixture(scope="module")
def sky():
    wavelength, components = skycalc.load()
    return wavelength, sum(components.values())


@pytest.fixture(scope="module")
def bandpass(sky):
    wavelength, _ = sky
    curve_nm, transmission = skycalc.load_filter()
    return np.interp(wavelength, curve_nm, transmission, left=0.0, right=0.0)


@pytest.fixture(scope="module")
def spectral_rate(sky, bandpass):
    """e-/s/pix, integrating the real spectrum through the real filter."""
    wavelength, radiance = sky
    photons = np.trapezoid(radiance * bandpass, wavelength / 1000.0)
    return photons / 1e4 * (EFFECTIVE_AREA_M2 * 1e4) * OPTICS_AND_DETECTOR * PIXEL_SCALE ** 2


def _top_hat_rate(mu_sky, central_nm, bandwidth_nm, transmission):
    return physics.calculate_sky_background_rate(
        f_lambda_sky=physics.convert_ab_to_wavelength_flux(mu_sky, central_nm),
        filter_bandwidth=bandwidth_nm,
        effective_area=EFFECTIVE_AREA_M2,
        photon_energy=physics.calculate_photon_energy(central_nm),
        total_throughput=OPTICS_AND_DETECTOR * transmission,
        pixel_scale=PIXEL_SCALE,
    )


@pytest.fixture(scope="module")
def equivalent_mu_sky(sky, bandpass, spectral_rate):
    """The AB surface brightness this spectrum represents in this band.

    Derived from the spectrum rather than assumed, so the comparison isolates the
    bandpass shape instead of also testing whoever picked a sky brightness.
    """
    wavelength, radiance = sky
    width = skycalc.effective_width_nm(wavelength, bandpass)
    centroid = float(np.trapezoid(bandpass * wavelength, wavelength) / width)
    photons = np.trapezoid(radiance * bandpass, wavelength / 1000.0)
    f_lambda = (photons * physics.calculate_photon_energy(centroid) / 1e4) / (width * 10.0)
    f_nu = f_lambda * (centroid * 10.0) ** 2 / (physics.SPEED_OF_LIGHT_CGS * 1e8)
    return -2.5 * np.log10(f_nu / 1e-23 / 3631.0), centroid, width


def test_the_binned_grid_still_carries_every_photon(bandpass, sky):
    """Guards data/eso_skycalc_paranal_1nm.csv against the raw export.

    Skipped when the 2.7 MB original is not checked out, which is the normal case
    — see the README on why it is not in the repository.
    """
    if not skycalc.RAW.is_file():
        pytest.skip(f"raw SkyCalc export not present at {skycalc.RAW}")

    raw = np.loadtxt(skycalc.RAW, comments="#")
    raw_wavelength, raw_total = raw[:, 0], raw[:, 1:7].sum(axis=1)
    raw_transmission = np.interp(raw_wavelength, *skycalc.load_filter(), left=0.0, right=0.0)
    reference = np.trapezoid(raw_total * raw_transmission, raw_wavelength / 1000.0)

    wavelength, radiance = sky
    binned = np.trapezoid(radiance * bandpass, wavelength / 1000.0)
    assert binned == pytest.approx(reference, rel=1e-3)


def test_subsampling_that_grid_would_not(bandpass, sky):
    """Why the binned file is binned and not thinned.

    Taking every n-th sample moves the broadband integral by percent-level
    amounts, in a direction that does not settle as the grid coarsens — the
    airglow lines alias. This is larger than most differences this suite exists
    to measure, so it is worth a test rather than a comment.
    """
    if not skycalc.RAW.is_file():
        pytest.skip(f"raw SkyCalc export not present at {skycalc.RAW}")

    raw = np.loadtxt(skycalc.RAW, comments="#")
    raw_wavelength, raw_total = raw[:, 0], raw[:, 1:7].sum(axis=1)
    raw_transmission = np.interp(raw_wavelength, *skycalc.load_filter(), left=0.0, right=0.0)
    reference = np.trapezoid(raw_total * raw_transmission, raw_wavelength / 1000.0)

    step = int(round(1.0 / np.median(np.diff(raw_wavelength))))
    thinned = np.trapezoid(
        (raw_total * raw_transmission)[::step], raw_wavelength[::step] / 1000.0
    )
    assert abs(thinned / reference - 1.0) > 0.01


# ==========================================
# Against ESO's exposure time calculator
# ==========================================

def test_preset_geometry_matches_eso():
    """Mirrors and focal length are right, so nothing below is a geometry error."""
    case = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]
    # npix is reported rounded to a whole pixel, so this can only be so tight;
    # it is still far tighter than the factor of two a binning mismatch would give.
    assert np.sqrt(case["omega"] / case["npix"]) == pytest.approx(PIXEL_SCALE, rel=1e-3)


@pytest.mark.parametrize("mag", [18, 20])
def test_implied_throughput_does_not_depend_on_magnitude(mag):
    """Sanity check on the inversion before anything is concluded from it."""
    assert eso_etc.implied_throughput("v_HIGH+114", mag, 1.0, 0) == pytest.approx(
        eso_etc.implied_throughput("v_HIGH+114", 20, 1.0, 0), rel=1e-6)


def test_the_v_high_preset_lands_within_a_few_percent():
    """Which is why nobody noticed anything was wrong with it."""
    preset = eso_etc.preset_throughput("v_HIGH+114")
    assert preset / eso_etc.implied_throughput("v_HIGH+114", 20, 1.0, 0) - 1 < 0.10


def test_0_51_is_not_a_filter_transmission():
    """The proof that the v_HIGH agreement is a cancellation, not a calibration.

    A real transmission is a property of the filter. If 0.51 were one, swapping
    to the other filter in the same profile — same mirrors, same detector, same
    night — would leave the error where it was. Instead it explodes, because
    g_HIGH's 0.85 is a believable transmission and so absorbs nothing.
    """
    v = eso_etc.preset_throughput("v_HIGH+114") / eso_etc.implied_throughput("v_HIGH+114", 20, 1.0, 0)
    g = eso_etc.preset_throughput("g_HIGH+115") / eso_etc.implied_throughput("g_HIGH+115", 20, 1.0, 0)
    assert v == pytest.approx(1.08, abs=0.03)
    assert g > 2.0


@pytest.mark.xfail(
    strict=True,
    reason="presets.json gives FORS2 optical_throughput 0.771 and QE 0.781, a "
           "product of 0.602 where ESO's rates imply roughly 0.36. v_HIGH+114 "
           "hides it in a 0.51 'transmission'; g_HIGH+115 over-predicts by 2.5x. "
           "Fixing it means real per-component numbers, not a different fudge.",
)
def test_both_filters_agree_with_eso():
    for band in eso_etc.PRESET_FILTERS:
        assert eso_etc.preset_throughput(band) == pytest.approx(
            eso_etc.implied_throughput(band, 20, 1.0, 0), rel=0.15)


#: V-band extinction implied by ESO's own target rates across the captured
#: airmasses: 0.9378 at X=1.5 and 0.8798 at X=2.0, relative to the zenith, both
#: giving k = 0.139 once the encircled-energy difference is divided out.
ESO_K_V = 0.139


def test_the_sky_no_longer_falls_with_airmass():
    """The fix. Sky rate is flat in airmass because it cannot be given one.

    Flat is not ESO's answer, but it is on the correct side of theirs. The number
    this test really pins is the second one: what the old extinction term would
    have done, so the size of what was corrected stays on the record.
    """
    accepted = inspect.signature(physics.calculate_sky_background_rate).parameters
    assert "airmass" not in accepted and "extinction_coeff" not in accepted

    zenith = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]["sky_cpix"]
    for airmass in (1.5, 2.0):
        eso = eso_etc.CAPTURED[("v_HIGH+114", 20, airmass, 0)]["sky_cpix"] / zenith
        was = 10.0 ** (-0.4 * ESO_K_V * (airmass - 1.0))
        assert eso > 1.0          # ESO: brighter
        assert was < 1.0          # CASTOR, before: fainter
        assert 1.0 - was > 0.05   # by 6% at X=1.5, 12% at X=2.0


@pytest.mark.xfail(
    strict=True,
    reason="Flat stops the double-counting but does not model the growth. A "
           "longer line of sight holds more emitting atmosphere, and ESO's sky "
           "is 17.6% brighter at X=1.5 and 31.8% at X=2.0. Nor is one number "
           "enough: queried per band, SkyCalc grows the sky 23% in g' and 58% "
           "in i' between X=1.1 and X=2.0, because the emitted and the arriving "
           "components respond oppositely. Closing this needs a van Rhijn term "
           "over the emitted components only, which belongs with the spectral "
           "background work rather than as another scalar fudge.",
)
def test_the_sky_grows_with_airmass_the_way_esos_does():
    zenith = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]["sky_cpix"]
    for airmass in (1.5, 2.0):
        eso = eso_etc.CAPTURED[("v_HIGH+114", 20, airmass, 0)]["sky_cpix"] / zenith
        assert 1.0 == pytest.approx(eso, rel=0.05)   # ours is flat


def test_eso_sky_agrees_with_a_believable_dark_paranal():
    """A cross-check that the inversion is not nonsense.

    Run ESO's dark-sky rate back through CASTOR's chain with the preset as
    shipped and it lands on 22.4 mag/arcsec2 in V, which is what a moonless
    Paranal with the airglow term switched off should look like.
    """
    case = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]
    central, bandwidth, _ = eso_etc.PRESET_FILTERS["v_HIGH+114"]
    unit = (bandwidth * 10 * EFFECTIVE_AREA_M2 * 1e4
            / physics.calculate_photon_energy(central)
            * eso_etc.preset_throughput("v_HIGH+114") * PIXEL_SCALE ** 2)
    f_lambda = case["sky_cpix"] / eso_etc.EXPOSURE_TIME / unit
    assert -2.5 * np.log10(f_lambda / 3.63e-9) == pytest.approx(22.4, abs=0.2)


# ==========================================
# Where the two engines actually part company
# ==========================================

def _eso_image_quality(case):
    """The FWHM implied by ESO's aperture and its enclosed energy, arcsec.

    They report an aperture and how much light it holds, which for a Gaussian
    pins the width. Recovering it is the only way to compare like with like:
    ESO derives image quality from seeing, wavelength and airmass, where
    CASTOR takes a FWHM as given.
    """
    radius = np.sqrt(case["omega"] / np.pi)
    sigma_squared = radius ** 2 / (2 * -np.log(1 - case["encircled"]))
    return 2 * np.sqrt(2 * np.log(2)) * np.sqrt(sigma_squared)


def _eso_aperture_factor(case):
    """ESO's aperture radius in units of its own image quality — their k_ap.

    Not a number they publish, but the one their aperture and enclosed energy
    imply, which is what CASTOR's `aperture_factor` has to be compared against.
    """
    return np.sqrt(case["omega"] / np.pi) / _eso_image_quality(case)


def _snr(source_total, sky_per_pixel, npix, enclosed, time=eso_etc.EXPOSURE_TIME):
    signal = source_total * enclosed * time
    return signal / np.sqrt(
        signal + npix * (sky_per_pixel * time + 0.000583 * time + 3.15 ** 2))


def test_the_two_engines_are_the_same_algebra():
    """Give CASTOR ESO's aperture and the SNR lands on theirs exactly.

    Which is the useful thing to know before reading any other number here: no
    difference measured in this file comes from the arithmetic. They come from
    the aperture, the image quality, and the throughput.
    """
    case = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]
    ours = _snr(case["target"] / eso_etc.EXPOSURE_TIME / case["encircled"],
                case["sky_cpix"] / eso_etc.EXPOSURE_TIME,
                case["npix"], case["encircled"])
    assert ours == pytest.approx(case["snr"], rel=1e-3)


def test_the_aperture_convention_alone_is_worth_a_few_percent():
    """CASTOR's aperture rule against ESO's, with the image quality held equal.

    ESO derives image quality from seeing, wavelength and airmass; CASTOR takes
    a FWHM as given, and for this preset the two are not the same number. Run
    CASTOR's aperture over its own assumed FWHM and the result measures both
    differences at once — so this test runs it over ESO's implied FWHM instead,
    and moves nothing but `aperture_factor`. The PSF difference has its own test
    below.

    What is left is the convention alone, and it is small: 2.5% of the SNR at
    the shipped 0.85, 4.6% at the superseded 1.5. The direction is the part
    worth having on the record. At 0.85 CASTOR's aperture is *narrower* than
    ESO's — 0.85 against 1.03 FWHM, holding 86.5% of the star against 94.7% —
    where 1.5 was twice ESO's area, and three times the area 0.85 uses. Both
    fall short of ESO's SNR by comparable amounts, but for opposite reasons:
    0.85 by leaving starlight outside the aperture, 1.5 by letting sky into it.
    """
    case = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]
    fwhm = _eso_image_quality(case)
    source = case["target"] / eso_etc.EXPOSURE_TIME / case["encircled"]
    sky = case["sky_cpix"] / eso_etc.EXPOSURE_TIME

    npix, enclosed = physics.calculate_aperture_geometry(0.85, fwhm, PIXEL_SCALE)
    assert npix < case["npix"]                                  # narrower, not wider
    assert enclosed == pytest.approx(0.865, abs=0.002)          # against ESO's 94.7%
    ours = _snr(source, sky, npix, enclosed)
    assert ours / case["snr"] - 1 == pytest.approx(-0.025, abs=0.005)

    npix, enclosed = physics.calculate_aperture_geometry(1.5, fwhm, PIXEL_SCALE)
    assert npix / case["npix"] > 2.0                            # wider, and
    assert enclosed > 0.99                                      # nearly all of it
    was = _snr(source, sky, npix, enclosed)
    assert was / case["snr"] - 1 == pytest.approx(-0.046, abs=0.005)


def test_not_matching_image_quality_first_measures_the_psf_as_well():
    """Why the test above recovers ESO's FWHM, kept as an assertion.

    Compare from CASTOR's assumed 0.8367" against the 0.6677" ESO's own numbers
    imply and the gap more than doubles, to 5.7%. The extra is the PSF: hold the
    aperture at ESO's 1.03 and moving only the FWHM costs 4.2% by itself, which
    is more than the aperture convention is worth at the shipped default. Two
    differences of similar size, and reading either off an unmatched comparison
    gets both.
    """
    case = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]
    source = case["target"] / eso_etc.EXPOSURE_TIME / case["encircled"]
    sky = case["sky_cpix"] / eso_etc.EXPOSURE_TIME

    def shortfall(aperture_factor, fwhm):
        return _snr(source, sky, *physics.calculate_aperture_geometry(
            aperture_factor, fwhm, PIXEL_SCALE)) / case["snr"] - 1

    matched = _eso_image_quality(case)
    assert PRESET_FWHM == pytest.approx(0.8367, abs=0.001)
    assert matched == pytest.approx(0.6677, abs=0.001)

    assert shortfall(0.85, PRESET_FWHM) == pytest.approx(-0.057, abs=0.005)   # both
    assert shortfall(0.85, matched) == pytest.approx(-0.025, abs=0.005)       # aperture
    assert shortfall(_eso_aperture_factor(case), PRESET_FWHM) == pytest.approx(
        -0.042, abs=0.005)                                                    # PSF


def test_our_aperture_and_esos_are_two_points_on_one_curve():
    """0.85 and 1.03 are two choices on one trade-off, not two conventions.

    For a Gaussian PSF the SNR-optimal radius is not a constant: it sits near
    0.673 FWHM when the sky dominates and moves outward as the source does
    (ATBD 5.2). ESO's captures span both ends without changing their own rule —
    1.03 FWHM in the dark and under a full moon alike — so the pair says where
    each choice falls on the curve rather than which curve each is on.

    Dark, the star outweighs the sky in the aperture 5:1, the optimum is
    1.07 FWHM, and ESO's 1.03 is essentially on it while 0.85 gives up 2.5%.
    Under the moon the sky outweighs the star 13:1, the optimum falls to 0.70,
    and the ordering reverses: 0.85 now beats 1.03 by 9%. Neither is the wrong
    convention, and ESO's is the better one for the case they happened to
    publish. 0.85 is the choice that stays within 3% of the best available in
    both, which is what a default has to do when it does not know which case it
    will be asked about. 1.5 does not: it gives up a third of a moonlit
    measurement.
    """
    dark = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]
    moonlit = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 1)]

    # One aperture rule across both, so the two cases differ only in regime.
    k_eso = _eso_aperture_factor(dark)
    assert k_eso == pytest.approx(_eso_aperture_factor(moonlit), rel=1e-6)
    assert k_eso == pytest.approx(1.03, abs=0.01)

    factors = np.linspace(0.3, 3.0, 271)

    def curve(case):
        """(k_ap at the optimum, SNR at a given k_ap as a fraction of it)."""
        fwhm = _eso_image_quality(case)
        source = case["target"] / eso_etc.EXPOSURE_TIME / case["encircled"]
        sky = case["sky_cpix"] / eso_etc.EXPOSURE_TIME
        def at(k):
            return _snr(source, sky, *physics.calculate_aperture_geometry(
                k, fwhm, PIXEL_SCALE))

        sampled = np.array([at(k) for k in factors])
        return factors[sampled.argmax()], lambda k: at(k) / sampled.max()

    optimum, fraction = curve(dark)
    assert optimum > 1.0                                    # source-dominated: wide
    assert fraction(k_eso) > 0.99                           # and ESO sits on it
    assert fraction(0.85) == pytest.approx(0.975, abs=0.005)

    optimum, fraction = curve(moonlit)
    assert optimum < 0.75                                   # sky-dominated: collapses
    assert fraction(0.85) == pytest.approx(0.971, abs=0.005)
    assert fraction(k_eso) == pytest.approx(0.888, abs=0.005)   # now the wide one pays
    assert fraction(1.5) < 0.70                                 # and 1.5 pays a third


def test_our_image_quality_ignores_wavelength_and_airmass():
    """ESO's PSF narrows in the red and widens with airmass; ours does neither.

    A quadrature sum of fixed inputs cannot: `seeing_fwhm` arrives already
    decided. Documented rather than fixed — it is an input, and the caller is
    the one who knows what it should be for their band and altitude.
    """
    zenith = _eso_image_quality(eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)])
    low = _eso_image_quality(eso_etc.CAPTURED[("v_HIGH+114", 20, 2.0, 0)])
    assert low > zenith * 1.3

    assert PRESET_FWHM > zenith * 1.2   # and we start wider than they end up at zenith


def test_all_three_agree_on_how_the_target_dims_with_airmass():
    """The one axis with no disagreement at all.

    LCO refers magnitudes to the zenith and CASTOR to above the atmosphere, so
    they read the same input differently — but the two conventions differ by a
    constant, and the shape relative to the zenith is identical in all three.
    Any residual is a difference of opinion about the extinction coefficient,
    not about the model.
    """
    k = ESO_K_V
    zenith = eso_etc.CAPTURED[("v_HIGH+114", 20, 1.0, 0)]
    for airmass in (1.5, 2.0):
        case = eso_etc.CAPTURED[("v_HIGH+114", 20, airmass, 0)]
        eso = ((case["target"] / case["encircled"])
               / (zenith["target"] / zenith["encircled"]))
        castor = 10 ** (-0.4 * k * airmass) / 10 ** (-0.4 * k)
        lco = 10 ** (-0.4 * k * (airmass - 1.0))
        assert castor == pytest.approx(lco, rel=1e-12)
        assert castor == pytest.approx(eso, rel=1e-3)


# ==========================================
# Paranal's atmospheric extinction — the VLT profile's site
# ==========================================

def test_paranal_extinction_falls_toward_the_red():
    """Sanity check on the transcription: extinction is supposed to do this.

    Rayleigh scattering goes as lambda^-4, so a real atmospheric extinction
    curve falls steeply from the blue to the red overall. Not point-to-point
    monotonically, though — real molecular absorption bumps sit on top of it,
    and the two here (a few 0.001-0.004 mag rises around 5600-5700 and 6450 A)
    line up with the Chappuis ozone band and are the kind of thing a real
    measured curve should have. What a transcription error would produce is a
    jump two orders of magnitude bigger than that, which the 0.01 step bound
    below would catch.
    """
    wl, k = eso_etc.paranal_extinction_curve()
    assert len(wl) == 77
    assert k[0] > 0.6                      # near-UV, 3325 A
    assert k[-1] < 0.05                    # near-IR, 10000 A
    step = np.diff(k[:-4])                 # last 4 points are LBLRTM interpolations
    assert step.max() < 0.01               # no rise bigger than a real absorption bump
    assert k[:-4][0] - k[:-4][-1] > 0.5     # net fall, blue to red, dwarfs the bumps


def test_the_vlt_profiles_extinction_is_v_high_114_weighted_by_the_real_curve():
    """Where presets.json's vlt.environment.extinction_coeff actually comes from.

    Not a value read off Patat's table by eye: V_HIGH+114's own measured
    transmission curve (data/fors2_v_high_114.dat) weights the integral, so a
    filter that leans blue of nominal V gets a slightly steeper number than the
    textbook 0.13-ish quoted for Johnson V. It does — 0.135 against a plain
    5500 A value of 0.131 — which is the direction V_HIGH+114's centroid
    (549.2 nm, blue of 550) predicts.
    """
    curve = np.loadtxt(eso_etc.DATA_DIR / "fors2_v_high_114.dat")
    weighted = eso_etc.paranal_extinction_for_filter(curve[:, 0], curve[:, 1])

    assert weighted == pytest.approx(0.135, abs=0.001)

    wl, k = eso_etc.paranal_extinction_curve()
    plain_v = np.interp(5500.0, wl, k)
    assert weighted > plain_v
