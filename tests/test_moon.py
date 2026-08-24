import pytest
import numpy as np
import numpy.testing as npt

from castor.moon import (
    krisciunas_schaefer_1991,
    calculate_sky_brightness,
    get_moon_and_target_geometry,
    ecliptic_latitude,
    calculate_zodiacal_brightness_nl,
    ZODIACAL_REFERENCE_ECLIPTIC_LATITUDE_DEG,
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


# ==========================================
# 4. Zodiacal light (QUESTIONS.md 9/10)
# ==========================================

def test_ecliptic_latitude_is_a_pure_coordinate_transform():
    """No time, no site — the ecliptic does not move relative to the stars."""
    on_the_ecliptic = ecliptic_latitude(target_ra=0.0, target_dec=0.0)
    near_the_pole = ecliptic_latitude(target_ra=270.0, target_dec=66.56)

    assert on_the_ecliptic == pytest.approx(0.0, abs=0.01)
    assert near_the_pole == pytest.approx(90.0, abs=0.01)


def test_zodiacal_brightness_recombines_to_the_original_measurement():
    """At the reference latitude, mu_dark plus the zodiacal term must reproduce
    exactly what zodiacal_share was computed to remove — that recombination is
    the whole point of the split, and is what validation/test_lulin.py checks
    per band against real photometry. Here it is checked as pure algebra: 21.44
    split into a 21.79 local baseline and a 0.274 share must add back to 21.44.
    """
    mu_local = 21.79
    share = 0.274

    b_zodi = calculate_zodiacal_brightness_nl(
        ZODIACAL_REFERENCE_ECLIPTIC_LATITUDE_DEG, share, mu_local)
    b_local = 34.08 * (10.0 ** (0.4 * (22.5 - mu_local)))
    mu_total = 22.5 - 2.5 * np.log10((b_local + b_zodi) / 34.08)

    assert mu_total == pytest.approx(21.44, abs=0.005)


def test_zodiacal_brightness_fades_towards_the_poles():
    """Real zodiacal light is brightest near the ecliptic plane. `>=` at 60/90
    because the shape table is documented to saturate there, not keep falling."""
    share, mu_local = 0.274, 21.79
    b = {lat: calculate_zodiacal_brightness_nl(lat, share, mu_local)
         for lat in (0.0, 15.9, 30.0, 60.0, 90.0)}

    assert b[0.0] > b[15.9] > b[30.0] > b[60.0]
    assert b[60.0] >= b[90.0]


def test_zodiacal_share_none_matches_the_old_unsplit_behaviour():
    """A profile that carries no zodiacal_share (VLT, other, Lulin's u') must
    compute exactly as it did before this parameter existed — this is the
    backward-compatibility guarantee the whole feature depends on."""
    kwargs = dict(target_ra=270.0, target_dec=66.56,
                  obs_time_utc="2026-07-23T12:00:00",
                  mu_dark=21.5, extinction_coeff=0.17)

    without_the_parameter = calculate_sky_brightness(**kwargs)
    with_it_explicitly_absent = calculate_sky_brightness(**kwargs, zodiacal_share=None)

    assert with_it_explicitly_absent == pytest.approx(without_the_parameter)


def test_zodiacal_share_brightens_the_sky_relative_to_local_only():
    """Adding a real, positive flux component can only brighten the sky (smaller
    mag), never dim it — checked at a pointing away from the reference latitude
    so the zodiacal term is not exactly what mu_dark already had split out."""
    kwargs = dict(target_ra=270.0, target_dec=66.56,   # near the ecliptic pole
                  obs_time_utc="2026-07-23T12:00:00",
                  mu_dark=21.79, extinction_coeff=0.17)

    local_only = calculate_sky_brightness(**kwargs)
    with_zodiacal = calculate_sky_brightness(**kwargs, zodiacal_share=0.274)

    assert with_zodiacal < local_only
