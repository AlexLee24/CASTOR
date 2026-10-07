import math

import numpy as np
import pytest
from datetime import datetime, timezone

# Assumes your module path is castor
from castor import moon, schema
from castor.calculator import run_calculation

# ==========================================
# Fixtures: prepare standard fake test data
# ==========================================

@pytest.fixture
def mock_moon(monkeypatch):
    """
    Intercepts Astropy's ephemeris computation so the test environment is fully
    isolated and fast. Returns a fixed zenith angle and moon brightness so the physics
    calculations aren't affected by the real current time.
    """
    def mock_geometry(*args, **kwargs):
        # Returns: alpha=0 (full moon), rho=90, z_moon=45, z_target=30
        return (0.0, 90.0, 45.0, 30.0)
        
    def mock_sky_brightness(*args, **kwargs):
        return 21.0 # Always return a sky brightness of magnitude 21.0

    monkeypatch.setattr("castor.moon.get_moon_and_target_geometry", mock_geometry)
    monkeypatch.setattr("castor.moon.calculate_sky_brightness", mock_sky_brightness)

@pytest.fixture
def base_request():
    """Builds standard fake point-source observation data for the Lulin One-meter Telescope (LOT)"""
    return schema.ObservationRequest(
        instrument=schema.InstrumentProfile(
            telescope=schema.TelescopeSchema(
                primary_mirror_diameter=1.0, 
                secondary_mirror_diameter=0.3, 
                focal_length=8.0, 
                optical_throughput=0.8
            ),
            camera=schema.CameraSchema(
                pixel_pitch=13.5, 
                quantum_efficiency=0.9, 
                dark_current_rate=0.01, 
                readout_noise=3.0, 
                full_well_capacity=100000.0
            ),
            optic_filter=schema.FilterSchema(
                central_wavelength=550.0, # approximates the V band
                filter_bandwidth=100.0,
                filter_transmission=0.95
            ),
            throughput_correction=1.0
        ),
        target=schema.TargetProfile(
            morphology=schema.PointMorphology(),
            brightness=schema.VegaMagnitude(target_mag=15.0, zero_point_flux=3.6e-9),
            sed=schema.FlatSED(),
            ra=180.0, 
            dec=0.0
        ),
        environment=schema.EnvironmentCondition(
            location=schema.ObservatoryLocation(
                latitude_deg=23.47, longitude_deg=120.87, elevation_m=2862.0
            ),
            observing_time_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            auto_calc_background=False,
            mu_dark=21.5,
            extinction_coeff=0.17,
            seeing_fwhm=1.5, diffraction_fwhm=0.1, optical_fwhm=0.1, tracking_fwhm=0.1
        ),
        # Defaults to mode B: given a target SNR, solve backward for the number of exposures needed
        options=schema.SolveForTime(
            aperture_factor=1.5, single_exp_time=300.0, target_snr=100.0
        )
    )

# ==========================================
# Test cases: pipeline assembly and routing verification
# ==========================================

def test_pipeline_point_solve_time(mock_moon, base_request):
    """
    Test pipeline A: point-source target (Point) + solve exposures backward (SolveForTime)
    """
    response = run_calculation(base_request)
    
    # 1. Ensure the return value is a standard contract object
    assert isinstance(response, schema.ObservationResponse)
    
    # 2. Ensure core data isn't empty (in SolveForTime mode, required_exposures must be present)
    assert response.core.required_exposures is not None
    assert response.core.total_snr >= 100.0 # an SNR that meets the target must be >= the target SNR
    
    # 3. Ensure physical properties were computed correctly
    assert response.budget.source_count_rate > 0
    assert 0.0 < response.diagnostics.enclosed_flux_fraction < 1.0

def test_pipeline_extended_solve_snr(mock_moon, base_request):
    """
    Test pipeline B: extended-source target (Extended) + solve SNR forward (SolveForSNR)
    """
    # Swap out a piece of the request: change the target to an extended source (e.g. galaxy surface brightness)
    base_request.target.morphology = schema.ExtendedMorphology()
    # Swap out the brightness in the request: switch to AB magnitude
    base_request.target.brightness = schema.ABMagnitude(target_mag=18.0)
    # Swap out the options in the request: directly give 5 exposures and solve for the resulting SNR
    base_request.options = schema.SolveForSNR(
        aperture_factor=1.5, single_exp_time=300.0, num_exposures=5
    )
    
    response = run_calculation(base_request)
    
    # 1. In SolveForSNR mode, there's no need to solve for exposures backward, so this should be None
    assert response.core.required_exposures is None
    
    # 2. Ensure the computed SNR is a valid number
    assert response.core.total_snr > 0
    
    # 3. Extended sources have no enclosed-flux loss, so the enclosed fraction can still be
    #    computed as usual, but ensure the system doesn't crash
    assert response.budget.source_count_rate > 0

def test_pipeline_saturation_warning(mock_moon, base_request):
    """
    Test pipeline C: extreme brightness correctly triggers the saturation flag (is_saturated)
    """
    # Make the star extremely bright (magnitude 0) and use a very long single exposure time (1000s)
    base_request.target.brightness = schema.VegaMagnitude(target_mag=0.0, zero_point_flux=3.6e-9)
    base_request.options.single_exp_time = 1000.0

    response = run_calculation(base_request)

    # Should trip the saturation warning
    assert response.flags.is_saturated is True

# ==========================================
# Test case: system-level throughput correction (throughput_correction)
# ==========================================

def test_throughput_correction_scales_output(mock_moon, base_request):
    """throughput_correction is an extra correction factor multiplied on after
    optical/filter/QE; halving it should exactly halve both the reported
    total_throughput and the source_count_rate, which is proportional to it."""
    baseline = run_calculation(base_request)

    base_request.instrument.throughput_correction = 0.5
    halved = run_calculation(base_request)

    assert halved.diagnostics.total_throughput == pytest.approx(
        baseline.diagnostics.total_throughput * 0.5
    )
    assert halved.budget.source_count_rate == pytest.approx(
        baseline.budget.source_count_rate * 0.5
    )

# ==========================================
# Test case: sky background source switching (auto_calc_background)
# ==========================================

def test_auto_calc_background_selects_moon_model(monkeypatch, base_request):
    """auto_calc_background decides the source of sky brightness: when False, mu_dark
    should be used directly, completely skipping the moon model lookup; only when True
    is calculate_sky_brightness called. mu_dark itself is required in both modes — this
    switch only decides whether moonlight is layered on top."""
    sky_brightness_calls = []

    monkeypatch.setattr(
        "castor.moon.get_moon_and_target_geometry",
        lambda *a, **k: (0.0, 90.0, 45.0, 30.0),
    )
    monkeypatch.setattr(
        "castor.moon.calculate_sky_brightness",
        lambda *a, **k: sky_brightness_calls.append(1) or 21.0,
    )

    base_request.environment.auto_calc_background = False
    run_calculation(base_request)
    assert len(sky_brightness_calls) == 0, "The moon model should not be queried when disabled"

    base_request.environment.auto_calc_background = True
    run_calculation(base_request)
    assert len(sky_brightness_calls) == 1, "The moon model should be queried once when enabled"

# ==========================================
# Saturation is a property of the target, not of the aperture
# ==========================================

@pytest.mark.parametrize("aperture_factor", [0.5, 0.85, 1.0, 1.5, 2.5])
def test_saturation_does_not_move_with_the_photometric_aperture(base_request, aperture_factor):
    """The brightest pixel belongs to the star and the seeing, and to nothing else.

    Drawing a wider or narrower circle for photometry cannot change how fast the
    central pixel fills up. This was worth pinning because for a long time it did:
    the peak rate was derived from the aperture-enclosed rate, so shrinking the
    aperture quietly reported saturation as arriving later than it does. At the
    old default of 1.5 the enclosed fraction is 0.998 and the error was invisible;
    at 0.85 it would have been 13%, in the direction that tells you a frame is safe
    when it is not.
    """
    reference = base_request.model_copy(deep=True)
    reference.options.aperture_factor = 1.5
    expected = run_calculation(reference).core.saturation_time_limit

    request = base_request.model_copy(deep=True)
    request.options.aperture_factor = aperture_factor
    assert run_calculation(request).core.saturation_time_limit == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("aperture_factor", [0.85, 1.5, 2.5])
def test_extended_sources_have_no_psf_peak(base_request, aperture_factor):
    """Uniform surface brightness means every pixel in the aperture is the peak.

    The old code ran the Gaussian peak-fraction over an extended source too, which
    made its saturation time depend on the aperture squared — a galaxy that
    saturated in one aperture was safe in another.
    """
    request = base_request.model_copy(deep=True)
    request.target.morphology = schema.ExtendedMorphology()
    request.options.aperture_factor = aperture_factor
    response = run_calculation(request)

    per_pixel = response.budget.source_count_rate / response.diagnostics.num_pixels_aperture
    assert response.budget.peak_pixel_rate == pytest.approx(per_pixel, rel=1e-9)


# ==========================================
# What the response says about how it got there
# ==========================================

def _with_every_noise_term(request):
    """A copy with N_est and the flatness term both switched on, so that no term in
    the breakdown is zero by construction."""
    request = request.model_copy(deep=True)
    request.instrument.camera.background_flatness_fraction = 0.02
    request.options.sky_annulus = schema.SkyAnnulus(inner_factor=3.0, outer_factor=5.0)
    return request

@pytest.mark.parametrize("options", [
    schema.SolveForTime(aperture_factor=0.85, single_exp_time=120.0, target_snr=50.0),
    schema.SolveForSNR(aperture_factor=0.85, single_exp_time=120.0, num_exposures=7),
])
def test_each_snr_is_exactly_its_noise_blocks_signal_over_root_variance(mock_moon, base_request, options):
    """The breakdown is the one the SNRs were divided from, not a re-derivation that
    agrees to a tolerance: a caller combining frames from noise.* gets the engine's
    own numbers back."""
    base_request.options = options
    response = run_calculation(_with_every_noise_term(base_request))
    noise = response.noise

    assert noise.single.signal / np.sqrt(noise.single.total_variance) == response.core.single_snr
    assert noise.total.signal / np.sqrt(noise.total.total_variance) == response.core.total_snr
    for block in (noise.single, noise.total):
        assert min(block.source_variance, block.sky_variance, block.dark_variance,
                   block.readout_variance, block.flatness_variance) > 0
        summed = (block.source_variance + block.sky_variance + block.dark_variance
                  + block.readout_variance + block.flatness_variance)
        assert summed == pytest.approx(block.total_variance, rel=1e-12)
        assert block.num_pixels_background == pytest.approx(
            response.diagnostics.num_pixels_aperture + response.diagnostics.num_pixels_sky_estimate,
            rel=1e-15)

def test_total_time_is_the_frames_actually_counted(mock_moon, base_request):
    """t_single × N, where N is the request's own count when solving for SNR and the
    engine's answer when solving for time. The noise blocks are charged for the
    same frames and seconds."""
    solved = run_calculation(base_request)
    frames = solved.core.required_exposures
    assert solved.core.total_exp_time == 300.0 * frames
    assert (solved.noise.total.exp_time, solved.noise.total.num_exposures) == (300.0 * frames, frames)
    assert (solved.noise.single.exp_time, solved.noise.single.num_exposures) == (300.0, 1)

    base_request.options = schema.SolveForSNR(aperture_factor=1.5, single_exp_time=300.0, num_exposures=5)
    given = run_calculation(base_request)
    assert given.core.total_exp_time == 1500.0
    assert (given.noise.total.exp_time, given.noise.total.num_exposures) == (1500.0, 5)

@pytest.mark.parametrize("zenith_deg", [0.0, 30.0, 60.0, 88.0, 89.0, 95.0, 125.0])
def test_airmass_is_the_clamped_secant_the_extinction_used(monkeypatch, base_request, zenith_deg):
    monkeypatch.setattr("castor.moon.get_moon_and_target_geometry",
                        lambda *a, **k: (0.0, 90.0, 45.0, zenith_deg))
    response = run_calculation(base_request)

    assert response.diagnostics.airmass == pytest.approx(
        1.0 / math.cos(math.radians(min(zenith_deg, 89.0))), rel=1e-12)
    assert response.ephemeris.target_elevation_deg == pytest.approx(90.0 - zenith_deg)

def test_a_target_below_the_horizon_says_so_beside_its_clamped_airmass(monkeypatch, base_request):
    """The clamp keeps the maths finite by reporting an unobservable target as a
    very faint one: 35° below the horizon comes back as airmass 57 (LESSONS.md).
    The elevation is reported unclamped so a caller can tell the two apart."""
    monkeypatch.setattr("castor.moon.get_moon_and_target_geometry",
                        lambda *a, **k: (0.0, 90.0, 45.0, 125.0))
    response = run_calculation(base_request)

    assert response.ephemeris.target_elevation_deg == pytest.approx(-35.0)
    assert response.diagnostics.airmass == pytest.approx(57.2987, rel=1e-5)
    assert response.core.total_snr > 0   # still a number, which is the trap

def test_the_sky_reported_is_mu_dark_when_nothing_is_layered_on(mock_moon, base_request):
    """auto_calc_background off and no zodiacal_share: mu_sky is mu_dark, untouched."""
    assert base_request.environment.zodiacal_share is None
    response = run_calculation(base_request)
    assert response.diagnostics.sky_surface_brightness == base_request.environment.mu_dark

def test_the_sky_reported_is_the_one_the_moon_model_returned(mock_moon, base_request):
    base_request.environment.auto_calc_background = True
    response = run_calculation(base_request)
    assert response.diagnostics.sky_surface_brightness == 21.0   # mock_moon's sky

def test_the_sky_reported_includes_the_zodiacal_term(mock_moon, base_request):
    """zodiacal_share completes mu_dark whether or not the moon is modelled, so the
    sky the response reports is no longer mu_dark even with the moon off."""
    base_request.environment.zodiacal_share = 0.35
    response = run_calculation(base_request)

    expected = moon.apply_zodiacal_baseline(
        base_request.environment.mu_dark, base_request.target.ra, base_request.target.dec, 0.35)
    assert response.diagnostics.sky_surface_brightness == pytest.approx(float(expected), rel=1e-12)
    assert response.diagnostics.sky_surface_brightness < base_request.environment.mu_dark

def test_the_ephemeris_is_the_geometry_the_calculation_used(mock_moon, base_request):
    """mock_moon puts a full moon (alpha 0) 90° from the target, 45° up, and the
    target 30° from the zenith. Reported even with the moon switched off."""
    assert base_request.environment.auto_calc_background is False
    ephemeris = run_calculation(base_request).ephemeris

    assert ephemeris.moon_phase_angle_deg == 0.0
    assert ephemeris.moon_separation_deg == 90.0
    assert ephemeris.moon_elevation_deg == pytest.approx(45.0)
    assert ephemeris.target_elevation_deg == pytest.approx(60.0)

def test_the_ephemeris_matches_astropy_at_the_requested_instant(base_request):
    """Deliberately unmocked, at a pinned time: the block carries astropy's own
    numbers, not stand-ins, and they survive into a JSON dump."""
    env, tgt = base_request.environment, base_request.target
    env.observing_time_utc = datetime(2026, 1, 15, 16, 0, tzinfo=timezone.utc)
    alpha, rho, z_moon, z_target = moon.get_moon_and_target_geometry(
        tgt.ra, tgt.dec, "2026-01-15T16:00:00",
        env.location.longitude_deg, env.location.latitude_deg, env.location.elevation_m)

    response = run_calculation(base_request)

    assert response.ephemeris.target_elevation_deg == pytest.approx(90.0 - float(z_target), abs=1e-9)
    assert response.ephemeris.moon_elevation_deg == pytest.approx(90.0 - float(z_moon), abs=1e-9)
    assert response.ephemeris.moon_phase_angle_deg == pytest.approx(float(alpha), abs=1e-9)
    assert response.ephemeris.moon_separation_deg == pytest.approx(float(rho), abs=1e-9)
    assert response.diagnostics.airmass == pytest.approx(
        1.0 / math.cos(math.radians(min(float(z_target), 89.0))), rel=1e-12)
    assert '"ephemeris"' in response.model_dump_json()

def test_the_flatness_ceiling_can_be_read_off_the_single_frame(mock_moon, base_request):
    """With f_flat set, a stack's SNR approaches signal / sqrt(flatness_variance) of
    one frame and never passes it (ATBD 4.3.1a; validation/QUESTIONS.md 17). The
    solver does not yet know that, but a caller can now read the ceiling."""
    base_request.instrument.camera.background_flatness_fraction = 0.02
    base_request.target.morphology = schema.ExtendedMorphology()
    base_request.target.brightness = schema.ABMagnitude(target_mag=22.0)
    base_request.options = schema.SolveForSNR(aperture_factor=3.0, single_exp_time=120.0, num_exposures=1)
    single = run_calculation(base_request).noise.single
    ceiling = single.signal / math.sqrt(single.flatness_variance)

    snrs = []
    for frames in (1, 10, 100, 10_000, 1_000_000):
        base_request.options.num_exposures = frames
        snrs.append(run_calculation(base_request).core.total_snr)

    assert snrs == sorted(snrs)
    assert all(snr < ceiling for snr in snrs)
    assert snrs[-1] == pytest.approx(ceiling, rel=1e-2)
