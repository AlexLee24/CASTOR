import pytest
import numpy as np
from datetime import datetime, timezone

from castor import schema
from castor.batch_calculator import run_batch_calculation, _expand_time_series
from castor.calculator import run_calculation

# ==========================================
# Fixtures: prepare fake batch test data and interceptors
# ==========================================

@pytest.fixture
def mock_moon_batch(monkeypatch):
    """
    Intercepts Astropy's ephemeris computation, purpose-built for batch processing!
    Dynamically returns a NumPy array of length N based on the length (N) of the
    incoming time series.
    """
    def mock_geometry(*args, **kwargs):
        # Grab the incoming time series (may be the 3rd positional arg, or a keyword)
        times = kwargs.get("obs_time_utc") if "obs_time_utc" in kwargs else args[2]
        n = len(times) # type: ignore
        
        # Simulate the zenith angle changing over time (e.g. slowly dropping from 30° to 60°)
        alpha = np.zeros(n)
        rho = np.full(n, 90.0)
        z_moon = np.full(n, 45.0)
        z_target = np.linspace(30.0, 60.0, n) 
        return alpha, rho, z_moon, z_target
        
    def mock_sky_brightness(*args, **kwargs):
        times = kwargs.get("obs_time_utc") if "obs_time_utc" in kwargs else args[2]
        return np.full(len(times), 21.0) # Always return a sky brightness array of magnitude 21.0 # type: ignore

    monkeypatch.setattr("castor.moon.get_moon_and_target_geometry", mock_geometry)
    monkeypatch.setattr("castor.moon.calculate_sky_brightness", mock_sky_brightness)

@pytest.fixture
def batch_base_request():
    """Builds a standard batch observation request (time series)"""
    return schema.BatchObservationRequest(
        instrument=schema.InstrumentProfile(
            telescope=schema.TelescopeSchema(
                primary_mirror_diameter=1.0, secondary_mirror_diameter=0.3, 
                focal_length=8.0, optical_throughput=0.8
            ),
            camera=schema.CameraSchema(
                pixel_pitch=13.5, quantum_efficiency=0.9, dark_current_rate=0.01, 
                readout_noise=3.0, full_well_capacity=100000.0
            ),
            optic_filter=schema.FilterSchema(
                central_wavelength=550.0, filter_bandwidth=100.0, filter_transmission=0.95
            ),
            throughput_correction=1.0
        ),
        target=schema.TargetProfile(
            morphology=schema.PointMorphology(),
            brightness=schema.VegaMagnitude(target_mag=15.0, zero_point_flux=3.6e-9),
            sed=schema.FlatSED(),
            ra=180.0, dec=0.0
        ),
        environment=schema.TimeSeriesEnvironment(
            location=schema.ObservatoryLocation(latitude_deg=23.47, longitude_deg=120.87, elevation_m=2862.0),
            start_time_utc=datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc),
            end_time_utc=datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc), # Two-hour observation
            time_step_minutes=10.0, # Compute once every 10 minutes
            mu_dark=21.5,
            extinction_coeff=0.17,
            # Lesson learned last time — use 0.1 here to satisfy PositiveFloat
            seeing_fwhm=1.5, diffraction_fwhm=0.1, optical_fwhm=0.1, tracking_fwhm=0.1 
        ),
        options=schema.BatchSolveForTime(
            aperture_factor=1.5, single_exp_time=300.0, target_snr=100.0
        )
    )

# ==========================================
# Test cases
# ==========================================

def test_expand_time_series():
    """Ensure the time-expansion helper works correctly and has a bound in place"""
    start = datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 19, 0, tzinfo=timezone.utc)
    
    # Test 1: normal expansion (one hour, every 10 minutes, 7 points total)
    times = _expand_time_series(start, end, 10.0)
    assert len(times) == 7
    # No UTC offset suffix: astropy's Time(..., format="isot") rejects "+00:00" outright,
    # see test_expand_time_series_is_astropy_isot_compatible below.
    assert times[0] == "2026-01-01T18:00:00"

    # Test 2: bound enforcement (tests the max_points = 1000 limit)
    end_far = datetime(2026, 2, 1, 18, 0, tzinfo=timezone.utc) # one month later
    times_far = _expand_time_series(start, end_far, 1.0)
    assert len(times_far) == 1000

def test_batch_pipeline_solve_time(mock_moon_batch, batch_base_request):
    """Test the pipeline: solving SNR backward over a time series (SolveForTime)"""
    response = run_batch_calculation(batch_base_request)
    
    # 1. Ensure the returned array length is correct (18:00 to 20:00, every 10 minutes, 13 points total)
    assert len(response.core.timestamps_iso) == 13
    assert len(response.core.total_snr) == 13
    assert len(response.core.single_snr) == 13
    
    # 2. Ensure the Pydantic conversion is correct (the return value must be a native Python list, not a numpy array)
    assert isinstance(response.core.total_snr, list)
    assert isinstance(response.core.total_snr[0], float)

    # 2b. Ephemeris is elevation (90 - zenith angle), derived from the mocked z_target (30deg -> 60deg)
    # and constant z_moon (45deg)
    assert len(response.ephemeris.target_elevation_deg) == 13
    assert response.ephemeris.target_elevation_deg[0] == pytest.approx(60.0)
    assert response.ephemeris.target_elevation_deg[-1] == pytest.approx(30.0)
    assert all(m == pytest.approx(45.0) for m in response.ephemeris.moon_elevation_deg)

    # 3. Ensure every computed SNR meets the target (100.0)
    for snr in response.core.total_snr:
        assert snr >= 100.0

def test_batch_pipeline_solve_snr(mock_moon_batch, batch_base_request):
    """Test the pipeline: solving SNR forward over a time series (SolveForSNR), switched to an extended source"""
    # Swap out the request content
    batch_base_request.target.morphology = schema.ExtendedMorphology()
    batch_base_request.options = schema.BatchSolveForSNR(
        aperture_factor=1.5, single_exp_time=300.0, num_exposures=5
    )
    
    response = run_batch_calculation(batch_base_request)
    
    assert len(response.core.timestamps_iso) == 13
    assert len(response.core.total_snr) == 13
    
    # Since z_target varies in the mock (30° -> 60°), airmass grows, causing the signal
    # to decay — so the SNR array across the whole night should be decreasing!
    snr_array = response.core.total_snr
    assert snr_array[0] > snr_array[-1] # the first point's SNR must be greater than the last point's

def test_batch_pipeline_warning_flag(mock_moon_batch, batch_base_request):
    """Test the pipeline: whether the warning flag is correctly raised when an excessive airmass appears in the series"""
    def mock_high_airmass_geometry(*args, **kwargs):
        times = kwargs.get("obs_time_utc") if "obs_time_utc" in kwargs else args[2]
        n = len(times) # type: ignore
        # Force the zenith angle to 70° (this makes Airmass = sec(70) = 2.92 > 2.0)
        return (np.zeros(n), np.full(n, 90.0), np.full(n, 45.0), np.full(n, 70.0))
        
    # Override the original mock
    pytest.MonkeyPatch().setattr("castor.moon.get_moon_and_target_geometry", mock_high_airmass_geometry)
    
    response = run_batch_calculation(batch_base_request)
    
    # Must trigger the warning
    assert len(response.flags.warnings) > 0
    assert "Airmass > 2.0" in response.flags.warnings[0]

def test_batch_pipeline_real_astropy_path(batch_base_request):
    """
    Deliberately does NOT use mock_moon_batch: every other test in this file mocks
    castor.moon out entirely, which means the real astropy call path
    (moon.get_moon_and_target_geometry -> astropy.time.Time(..., format="isot") and
    moon.calculate_sky_brightness's full argument list) was never actually exercised
    end-to-end. It previously broke two ways that only showed up here:
      1. _expand_time_series fed astropy an ISO string with a "+00:00" offset suffix,
         which the strict "isot" format parser rejects.
      2. batch_calculator's call to moon.calculate_sky_brightness omitted the required
         extinction_coeff argument.
    Regression coverage for both — this just has to run without raising.
    """
    response = run_batch_calculation(batch_base_request)

    assert len(response.core.timestamps_iso) == 13
    assert len(response.core.total_snr) == 13
    assert all(snr > 0 for snr in response.core.total_snr)


# ==========================================
# Per-timestamp data: what each step was computed from
# ==========================================

def _per_step_arrays(response):
    """Every list the batch response carries, by dotted name."""
    arrays = {}
    for block in ("core", "budget", "diagnostics", "ephemeris"):
        for name, value in getattr(response, block).model_dump().items():
            if isinstance(value, list):
                arrays[f"{block}.{name}"] = value
    for which in ("single", "total"):
        for name, value in getattr(response.noise, which).model_dump().items():
            arrays[f"noise.{which}.{name}"] = value
    return arrays

def test_every_per_step_array_is_as_long_as_the_series(mock_moon_batch, batch_base_request):
    """Including the terms built only from constants, such as read noise, which
    physics hands back as a single number."""
    response = run_batch_calculation(batch_base_request)
    arrays = _per_step_arrays(response)

    assert {len(values) for values in arrays.values()} == {13}
    assert len(set(arrays["noise.total.readout_variance"])) == 1
    assert len(set(arrays["noise.single.num_pixels_background"])) == 1

def test_a_single_point_series_is_still_a_series(mock_moon_batch, batch_base_request):
    batch_base_request.environment.end_time_utc = batch_base_request.environment.start_time_utc
    arrays = _per_step_arrays(run_batch_calculation(batch_base_request))
    assert {len(values) for values in arrays.values()} == {1}

@pytest.mark.parametrize("options", [
    schema.BatchSolveForTime(aperture_factor=0.85, single_exp_time=120.0, target_snr=50.0),
    schema.BatchSolveForSNR(aperture_factor=0.85, single_exp_time=120.0, num_exposures=7),
])
def test_each_steps_snr_is_exactly_its_noise_over_root_variance(mock_moon_batch, batch_base_request, options):
    batch_base_request.options = options
    batch_base_request.options.sky_annulus = schema.SkyAnnulus(inner_factor=3.0, outer_factor=5.0)
    batch_base_request.instrument.camera.background_flatness_fraction = 0.02
    response = run_batch_calculation(batch_base_request)
    single, total = response.noise.single, response.noise.total

    for i in range(len(response.core.timestamps_iso)):
        assert single.signal[i] / np.sqrt(single.total_variance[i]) == response.core.single_snr[i]
        assert total.signal[i] / np.sqrt(total.total_variance[i]) == response.core.total_snr[i]

def test_total_time_follows_the_frames_at_each_step(mock_moon_batch, batch_base_request):
    """In solve_time the frame count moves with the sky, and the total time and the
    stacked noise terms move with it."""
    response = run_batch_calculation(batch_base_request)
    frames = response.core.required_exposures

    assert response.core.total_exp_time == [300.0 * n for n in frames]
    assert response.noise.total.num_exposures == frames
    assert response.noise.total.exp_time == response.core.total_exp_time
    assert set(response.noise.single.exp_time) == {300.0}
    assert set(response.noise.single.num_exposures) == {1.0}

    batch_base_request.options = schema.BatchSolveForSNR(aperture_factor=1.5, single_exp_time=300.0, num_exposures=5)
    given = run_batch_calculation(batch_base_request)
    assert set(given.core.total_exp_time) == {1500.0}
    assert set(given.noise.total.num_exposures) == {5.0}

def test_each_step_reports_the_airmass_sky_and_moon_it_used(mock_moon_batch, batch_base_request):
    """mock_moon_batch walks the target from 30 to 60 degrees from the zenith under a
    full moon 90 degrees away, with the sky held at 21.0."""
    response = run_batch_calculation(batch_base_request)
    zenith = np.linspace(30.0, 60.0, 13)

    np.testing.assert_allclose(response.diagnostics.airmass, 1.0 / np.cos(np.radians(zenith)), rtol=1e-12)
    assert set(response.diagnostics.sky_surface_brightness) == {21.0}
    assert set(response.ephemeris.moon_phase_angle_deg) == {0.0}
    assert set(response.ephemeris.moon_separation_deg) == {90.0}

def test_the_optimal_exposure_moves_with_the_sky(mock_moon_batch, batch_base_request):
    camera = batch_base_request.instrument.camera
    response = run_batch_calculation(batch_base_request)

    expected = [camera.readout_noise ** 2 / (sky + camera.dark_current_rate)
                for sky in response.budget.sky_count_rate]
    np.testing.assert_allclose(response.core.optimal_exposure_time, expected, rtol=1e-12)

def _leaves(dumped: dict, prefix: str = ""):
    """(dotted path, value) for every non-dict value in a model_dump()."""
    for key, value in dumped.items():
        if isinstance(value, dict):
            yield from _leaves(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}", value

# What the single response carries and a batch response does not: the Stage 2
# values that are fixed for a whole series (architecture.md §5.2).
SINGLE_ONLY = {
    "diagnostics.total_fwhm", "diagnostics.effective_area", "diagnostics.pixel_scale",
    "diagnostics.total_throughput", "diagnostics.enclosed_flux_fraction",
    "diagnostics.num_pixels_aperture", "diagnostics.num_pixels_sky_estimate",
}

def test_a_batch_step_is_the_single_request_at_that_instant(batch_base_request):
    """The same physics in two orchestrators drifts unless a test holds them
    together (LESSONS.md). Unmocked, at one pinned instant, with the moon on in
    both, everything the two responses share must agree.

    "Share" is read off the two dumps, not listed by hand, so a field added to
    both is compared without anyone remembering to add it here, and a field the
    single response gains alone fails until it is named in SINGLE_ONLY. Each
    per-step list holds one value, which must be the single response's. flags
    are not per step — the batch's summarise the whole series, here one step —
    so is_saturated must match, and so must the number of warnings; their
    wording differs (the batch's says "in time series").

    throughput_correction stays at 1.0 here: the batch calculator does not apply
    it (the single one does), which is a separate fix this test does not cover."""
    assert batch_base_request.instrument.throughput_correction == 1.0
    batch_base_request.instrument.camera.background_flatness_fraction = 0.02
    batch_base_request.options = schema.BatchSolveForTime(
        aperture_factor=0.85, single_exp_time=120.0, target_snr=40.0,
        sky_annulus=schema.SkyAnnulus(inner_factor=3.0, outer_factor=5.0))
    env = batch_base_request.environment
    env.end_time_utc = env.start_time_utc
    batch = run_batch_calculation(batch_base_request)

    single = run_calculation(schema.ObservationRequest(
        instrument=batch_base_request.instrument,
        target=batch_base_request.target,
        environment=schema.EnvironmentCondition(
            location=env.location, observing_time_utc=env.start_time_utc, auto_calc_background=True,
            mu_dark=env.mu_dark, zodiacal_share=env.zodiacal_share, extinction_coeff=env.extinction_coeff,
            seeing_fwhm=env.seeing_fwhm, diffraction_fwhm=env.diffraction_fwhm,
            optical_fwhm=env.optical_fwhm, tracking_fwhm=env.tracking_fwhm),
        options=schema.SolveForTime(**batch_base_request.options.model_dump(exclude={"type"})),
    ))

    in_batch = dict(_leaves(batch.model_dump()))
    in_single = dict(_leaves(single.model_dump()))
    assert set(in_single) - set(in_batch) == SINGLE_ONLY

    assert batch.flags.is_saturated == single.flags.is_saturated
    assert len(batch.flags.warnings) == len(single.flags.warnings)
    per_step = {path: value for path, value in in_single.items()
                if path in in_batch and not path.startswith("flags.")}
    assert {"core.saturation_time_limit", "ephemeris.moon_elevation_deg"} <= set(per_step)
    for path, value in per_step.items():
        assert in_batch[path] == [pytest.approx(value, rel=1e-9, abs=1e-9)], path
