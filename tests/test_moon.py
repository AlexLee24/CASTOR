import pytest
import numpy as np
import numpy.testing as npt

from castor.moon import (
    krisciunas_schaefer_1991,
    calculate_sky_brightness,
    get_moon_and_target_geometry
)

# ==========================================
# 1. Core physics engine tests (KS91 model)
# ==========================================

def test_ks91_vectorization():
    """Ensure the KS91 empirical model fully supports NumPy array operations"""
    alpha = np.array([0.0, 90.0, 180.0])
    rho = np.array([30.0, 60.0, 90.0])
    z_moon = np.array([30.0, 45.0, 60.0])
    z_target = np.array([30.0, 45.0, 60.0])
    
    result = krisciunas_schaefer_1991(alpha, rho, z_moon, z_target)
    
    assert isinstance(result, np.ndarray)
    assert len(result) == 3

def test_ks91_physical_limits():
    """Physical limits: ensure full moon vs. new moon, and near vs. far distance,
    brightness relationships match real physics"""
    base_args = {"z_moon_deg": 45.0, "z_target_deg": 45.0}
    
    b_full_moon = krisciunas_schaefer_1991(alpha_deg=0.0, rho_deg=60.0, **base_args)
    b_new_moon = krisciunas_schaefer_1991(alpha_deg=180.0, rho_deg=60.0, **base_args)
    assert b_full_moon > (b_new_moon * 10.0)
    
    b_close = krisciunas_schaefer_1991(alpha_deg=0.0, rho_deg=10.0, **base_args)
    b_far = krisciunas_schaefer_1991(alpha_deg=0.0, rho_deg=90.0, **base_args)
    assert b_close > b_far

# ==========================================
# 2. Sky brightness integration logic tests (moon rise/set edge cases)
# ==========================================

def test_sky_brightness_moon_below_horizon(monkeypatch):
    """Edge-case test: when the moon is below the horizon, total sky brightness must
    exactly equal the moonless dark-sky magnitude"""
    def mock_geometry(*args, **kwargs):
        return (0.0, 60.0, 95.0, 45.0)
    
    monkeypatch.setattr("castor.moon.get_moon_and_target_geometry", mock_geometry)
    
    base_dark_sky = 21.5
    result_mag = calculate_sky_brightness(
        target_ra=0.0, target_dec=0.0, 
        obs_time_utc="2026-01-01T00:00:00", 
        mu_dark=base_dark_sky,
        extinction_coeff=0.15,
    )
    
    assert result_mag == pytest.approx(base_dark_sky)

def test_sky_brightness_moon_above_horizon(monkeypatch):
    """Logic test: when the moon is above the horizon, total sky brightness must brighten"""
    def mock_geometry(*args, **kwargs):
        return (0.0, 30.0, 30.0, 30.0)
    
    monkeypatch.setattr("castor.moon.get_moon_and_target_geometry", mock_geometry)
    
    base_dark_sky = 21.5
    result_mag = calculate_sky_brightness(
        target_ra=0.0, target_dec=0.0, 
        obs_time_utc="2026-01-01T00:00:00", 
        mu_dark=base_dark_sky,
        extinction_coeff=0.15,
    )
    
    assert result_mag < base_dark_sky

# ==========================================
# 3. Ephemeris engine execution tests (Ephemeris Sanity Check & Vectorization)
# ==========================================

def test_ephemeris_execution_scalar():
    """Ensure Astropy ephemeris computation runs for a single point without type errors"""
    result = get_moon_and_target_geometry(
        target_ra=10.68, target_dec=41.27, 
        obs_time_utc="2026-07-23T12:00:00" 
    )
    
    assert len(result) == 4
    for val in result:
        # numpy.where and astropy may return a float, np.float64, or a 0-d array once unwrapped
        assert np.isscalar(val) or (isinstance(val, np.ndarray) and val.ndim == 0)

def test_ephemeris_time_series_vectorization():
    """Ensure the core ephemeris engine correctly handles a time array (List[str] -> NDArray)"""
    # Given three consecutive time points
    time_series = [
        "2026-07-23T12:00:00",
        "2026-07-23T13:00:00",
        "2026-07-23T14:00:00"
    ]
    
    # 1. Test that the geometry calculation outputs an array of length 3
    alpha, rho, z_moon, z_target = get_moon_and_target_geometry(
        target_ra=10.68, target_dec=41.27, obs_time_utc=time_series
    )
    assert isinstance(z_moon, np.ndarray)
    assert len(z_moon) == 3
    
    # 2. Test that the sky brightness calculation outputs an array of length 3
    mu_sky_array = calculate_sky_brightness(
        target_ra=10.68, target_dec=41.27, 
        obs_time_utc=time_series, 
        mu_dark=21.5,
        extinction_coeff=0.15,
    )
    assert isinstance(mu_sky_array, np.ndarray)
    assert len(mu_sky_array) == 3
