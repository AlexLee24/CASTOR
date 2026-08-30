import pytest
import numpy as np
import numpy.testing as npt

# Assumes your module path is castor.physics
from castor.physics import (
    calculate_airmass,
    calculate_effective_area,
    convert_ab_to_wavelength_flux,
    calculate_point_source_rate,
    calculate_extended_source_rate,
    calculate_sky_background_rate,
    calculate_sky_estimate_pixels,
    calculate_single_snr,
    calculate_total_snr,
    solve_required_exposures,
    calculate_optimal_exposure_time
)

# ==========================================
# Global Core Properties (vectorization and boundary tests)
# ==========================================

def test_vectorization_support():
    """Ensures the core function fully supports NumPy arrays without raising TypeError."""
    zenith_angles = np.array([0.0, 60.0])
    expected_airmass = np.array([1.0, 2.0])
    
    result = calculate_airmass(zenith_angles)
    
    assert isinstance(result, np.ndarray)
    npt.assert_allclose(result, expected_airmass, rtol=1e-5)

# ==========================================
# Stage 2: Physical & Environmental 
# ==========================================

def test_calculate_airmass():
    """Baseline and boundary test: 0° is 1.0, 60° is 2.0"""
    assert calculate_airmass(0.0) == pytest.approx(1.0)
    assert calculate_airmass(60.0) == pytest.approx(2.0, rel=1e-5)

def test_calculate_effective_area():
    """Tests the area calculation with/without secondary mirror obstruction"""
    # Primary mirror only (2m), no secondary mirror obstruction
    area_no_obs = calculate_effective_area(2.0, 0.0)
    expected_no_obs = np.pi * (1.0 ** 2)  # pi * r^2, r=1
    assert area_no_obs == pytest.approx(expected_no_obs)
    
    # With a 1m secondary mirror obstruction
    area_obs = calculate_effective_area(2.0, 1.0)
    expected_obs = (np.pi / 4.0) * (2.0**2 - 1.0**2)
    assert area_obs == pytest.approx(expected_obs)

def test_convert_ab_to_wavelength_flux():
    """Tests whether the flux conversion at AB magnitude 0 matches the 3631 Jy baseline"""
    mag_ab = 0.0
    wavelength_nm = 500.0  # 500 nm = 5000 Å
    
    result_f_lambda = convert_ab_to_wavelength_flux(mag_ab, wavelength_nm)
    
    # Theoretical hand-calculated value:
    # F_nu = 3631 Jy = 3631 * 1e-23 erg/s/cm²/Hz = 3.631e-20
    # lambda = 5000 Å
    # c = 2.99792458e18 Å/s
    # F_lambda = F_nu * (c / lambda^2) = 3.631e-20 * (2.99792458e18 / 25000000)
    expected_f_lambda = 3.631e-20 * (2.99792458e18 / (5000.0 ** 2))
    
    assert result_f_lambda == pytest.approx(expected_f_lambda, rel=1e-5)

# ==========================================
# Stage 3: Photoelectron Count Rates
# ==========================================

@pytest.fixture
def dummy_stage3_params():
    """Provides a standard set of fake Stage 3 parameters for testing"""
    return {
        "f_lambda": 1e-15,
        "extinction_coeff": 0.2,
        "airmass": 1.5,
        "filter_bandwidth": 100.0,
        "effective_area": 3.14,
        "photon_energy": 4e-12,
        "total_throughput": 0.6
    }

def test_extinction_null_effect(dummy_stage3_params):
    """Atmospheric extinction guard: when the extinction coefficient is 0, the arriving flux is not attenuated"""
    params = dummy_stage3_params.copy()

    base_flux = params.pop("f_lambda")
    
    # With atmospheric extinction
    rate_with_ext = calculate_point_source_rate(
        **params, f_lambda_total=base_flux, enclosed_flux_fraction=0.8
    )
    
    # No atmospheric extinction (k_ext = 0)
    params["extinction_coeff"] = 0.0
    rate_no_ext = calculate_point_source_rate(
        **params, f_lambda_total=base_flux, enclosed_flux_fraction=0.8
    )
    
    # The count rate computed without extinction must be strictly greater than with extinction
    assert rate_no_ext > rate_with_ext

def test_geometric_divergence(dummy_stage3_params):
    """Geometric branching verification: ensures different sources differ only by a
    geometric-constant multiple (area, ratio)"""
    params = dummy_stage3_params.copy()
    
    # Pull out the shared f_lambda to avoid a kwargs error
    base_flux = params.pop("f_lambda") 
    
    # 1. Point source (f_enc = 0.5)
    rate_point = calculate_point_source_rate(
        **params, 
        f_lambda_total=base_flux, 
        enclosed_flux_fraction=0.5
    )
    
    # 2. Sky background (single pixel, S_pixel = 2.0, area = 4). It takes no
    #    extinction, so the comparison is only geometric with the atmosphere off.
    sky_params = {k: v for k, v in params.items()
                  if k not in ("extinction_coeff", "airmass")}
    rate_sky = calculate_sky_background_rate(
        **sky_params,
        f_lambda_sky=base_flux,
        pixel_scale=2.0
    )
    
    # 3. Extended source (N_pix = 10, S_pixel = 2.0, total area = 40)
    rate_ext = calculate_extended_source_rate(
        **params, 
        f_lambda_surface=base_flux, 
        num_pixels_aperture=10.0, 
        pixel_scale=2.0
    )
    
    # Assert the purely geometric ratio between them
    attenuation = 10.0 ** (-0.4 * params["extinction_coeff"] * params["airmass"])
    assert rate_sky == pytest.approx(rate_point * 8.0 / attenuation)
    assert rate_ext == pytest.approx(rate_sky * 10.0 * attenuation)

def test_sky_background_does_not_respond_to_airmass(dummy_stage3_params):
    """The sky is emitted inside the atmosphere, so it is not dimmed by crossing it.

    mu_sky descends from mu_dark, a brightness measured from the ground. The
    atmosphere is already in that number, and applying the extinction term again
    would both double-count it and push the sky the wrong way — real sky surface
    brightness rises with airmass, because a longer line of sight holds more
    emitting atmosphere. Target light, arriving from outside, still dims normally.
    """
    params = dummy_stage3_params.copy()
    base_flux = params.pop("f_lambda")
    sky_params = {k: v for k, v in params.items()
                  if k not in ("extinction_coeff", "airmass")}

    # Not "ignores them" — cannot be given them. A parameter that is accepted and
    # discarded is an invitation to pass it and assume it did something.
    import inspect
    accepted = inspect.signature(calculate_sky_background_rate).parameters
    assert "airmass" not in accepted and "extinction_coeff" not in accepted

    with pytest.raises(TypeError):
        calculate_sky_background_rate(
            **sky_params, f_lambda_sky=base_flux, pixel_scale=1.0, airmass=2.0)

    zenith = calculate_point_source_rate(
        **{**params, "airmass": 1.0}, f_lambda_total=base_flux, enclosed_flux_fraction=1.0)
    low = calculate_point_source_rate(
        **{**params, "airmass": 2.0}, f_lambda_total=base_flux, enclosed_flux_fraction=1.0)
    assert low < zenith

# ==========================================
# Stage 4: Final Output Metrics
# ==========================================

@pytest.fixture
def dummy_stage4_params():
    """Provides a standard set of fake Stage 4 parameters for testing"""
    return {
        "source_count_rate": 100.0,
        "sky_count_rate": 10.0,
        "dark_current_rate": 0.1,
        "readout_noise": 5.0,
        "num_pixels_aperture": 4.0
    }

# ------------------------------------------
# Cost of the sky estimate (ATBD 4.3.2)
# ------------------------------------------

def test_sky_estimate_grows_with_the_square_of_the_aperture():
    """N_est goes as N_pix^2: one sky number is subtracted from every aperture
    pixel at once, so widening the aperture costs twice over."""
    small = calculate_sky_estimate_pixels(10.0, 3.0, 5.0, 2.0, 0.5)
    large = calculate_sky_estimate_pixels(20.0, 3.0, 5.0, 2.0, 0.5)
    npt.assert_allclose(large / small, 4.0)

def test_a_wider_annulus_costs_less():
    """More annulus pixels means a better-determined sky, so a smaller penalty."""
    narrow = calculate_sky_estimate_pixels(10.0, 3.0, 4.0, 2.0, 0.5)
    wide = calculate_sky_estimate_pixels(10.0, 3.0, 8.0, 2.0, 0.5)
    assert wide < narrow

def test_a_median_annulus_costs_pi_over_two_more_than_a_mean():
    """The only difference between the two estimators, and it is not a free choice:
    the median is what rejects the faint neighbours a mean would swallow."""
    mean = calculate_sky_estimate_pixels(10.0, 3.0, 5.0, 2.0, 0.5, "mean")
    median = calculate_sky_estimate_pixels(10.0, 3.0, 5.0, 2.0, 0.5, "median")
    npt.assert_allclose(median / mean, np.pi / 2.0)

def test_an_unknown_estimator_is_refused():
    """Silently falling back to one estimator or the other would misstate the noise
    by pi/2 with nothing in the output to show for it."""
    with pytest.raises(ValueError):
        calculate_sky_estimate_pixels(10.0, 3.0, 5.0, 2.0, 0.5, "sigma_clipped_mode")

def test_sky_estimate_matches_the_measured_geometry():
    """The 2026-08-30 LOT/SOPHIA check: a 3xFWHM aperture with a 5-8xFWHM median
    annulus adds 36% to the background variance. That number was arrived at twice,
    from this geometry and from the observed scatter of 314 stars, and they agree.
    See validation/data/raw/_endtoend_2026-08-30/RESULT.md."""
    fwhm, scale = 2.44945, 1.0
    n_pix = np.pi * (3.0 * fwhm) ** 2 / scale ** 2
    n_est = calculate_sky_estimate_pixels(n_pix, 5.0, 8.0, fwhm, scale)
    npt.assert_allclose(n_est / n_pix, 0.3625, rtol=1e-3)

def test_the_sky_estimate_is_the_only_thing_that_changed(dummy_stage4_params):
    """Omitting the annulus must reproduce the textbook CCD equation exactly, so
    that every result computed before this term existed still holds."""
    without = calculate_single_snr(**dummy_stage4_params, single_exp_time=60.0)
    explicit_zero = calculate_single_snr(
        **dummy_stage4_params, single_exp_time=60.0, num_pixels_sky_estimate=0.0
    )
    with_cost = calculate_single_snr(
        **dummy_stage4_params, single_exp_time=60.0, num_pixels_sky_estimate=2.0
    )
    npt.assert_allclose(without, explicit_zero)
    assert with_cost < without

def test_the_sky_estimate_averages_down_with_stacking(dummy_stage4_params):
    """Each frame carries its own sky estimate, so N_est must enter per frame --
    not once for the whole stack, which would make it vanish as frames are added."""
    kwargs = dict(**dummy_stage4_params, single_exp_time=10.0, total_exp_time=100.0, num_exposures=10)
    plain = calculate_total_snr(**kwargs)
    costed = calculate_total_snr(**kwargs, num_pixels_sky_estimate=4.0)

    # N_pix 4 -> 8 is the same doubling as adding N_est = 4, so the two must agree.
    doubled = dummy_stage4_params.copy()
    doubled["num_pixels_aperture"] = 8.0
    npt.assert_allclose(
        costed,
        calculate_total_snr(**doubled, single_exp_time=10.0, total_exp_time=100.0, num_exposures=10)
    )
    assert costed < plain

def test_zero_exposure(dummy_stage4_params):
    """Zeroed exposure time: no exposure time means no SNR"""
    snr = calculate_single_snr(**dummy_stage4_params, single_exp_time=0.0)
    assert snr == 0.0

def test_readout_noise_scaling(dummy_stage4_params):
    """Multi-exposure noise accumulation: for the same total time, splitting into multiple
    exposures must yield a lower SNR (because readout noise accumulates)"""
    params = dummy_stage4_params.copy()
    
    # Case A: a single 100-second exposure (1 frame)
    snr_single_shot = calculate_total_snr(
        **params, single_exp_time=100.0, total_exp_time=100.0, num_exposures=1
    )
    
    # Case B: 10-second exposures, 10 frames (same total time of 100 seconds)
    snr_multi_shot = calculate_total_snr(
        **params, single_exp_time=10.0, total_exp_time=100.0, num_exposures=10
    )
    
    assert snr_single_shot > snr_multi_shot

def test_snr_reversibility():
    """Perfect reversibility: the backward-solved number of exposures must be exact"""
    target_snr = 20.0
    single_snr = 10.0

    required_exposures = solve_required_exposures(target_snr, single_snr)

    # (20 / 10)^2 = 4.0
    assert required_exposures == pytest.approx(4.0)

def test_optimal_exposure_time_crossover_point():
    """Crossover point definition: when background_dominance_factor=1.0, plugging the
    computed t_opt into the background shot-noise formula sqrt(background_rate * t_opt)
    must equal RON exactly."""
    sky_rate, dark_rate, readout_noise = 2.0, 0.5, 5.0

    t_opt = calculate_optimal_exposure_time(sky_rate, dark_rate, readout_noise)

    background_shot_noise = np.sqrt((sky_rate + dark_rate) * t_opt)
    assert background_shot_noise == pytest.approx(readout_noise)

def test_optimal_exposure_time_scales_with_dominance_factor_squared():
    """k is defined as a ratio of standard deviations, so converted to time (variance) it
    must scale quadratically: doubling k should quadruple t_opt."""
    sky_rate, dark_rate, readout_noise = 2.0, 0.5, 5.0

    t_k1 = calculate_optimal_exposure_time(sky_rate, dark_rate, readout_noise, background_dominance_factor=1.0)
    t_k2 = calculate_optimal_exposure_time(sky_rate, dark_rate, readout_noise, background_dominance_factor=2.0)

    assert t_k2 == pytest.approx(t_k1 * 4.0)