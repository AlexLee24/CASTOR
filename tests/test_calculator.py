import pytest
from datetime import datetime, timezone

# Assumes your module path is castor
from castor import schema
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
