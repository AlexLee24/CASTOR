import numpy as np
from numpy.typing import NDArray
from typing import TypeAlias, cast, Any

from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_sun, get_body
from astropy.utils import iers
import astropy.units as u

Numeric: TypeAlias = float | NDArray[np.float64]

# astropy's IERS_Auto raises ValueError rather than extrapolating once its bundled
# Earth-orientation table is more than 30 days stale relative to *now* — a policy
# aimed at applications doing sub-arcsecond astrometry, not at seeing-limited
# pointing. It bites on the exact thing an exposure time calculator is for:
# planning a night more than a month out, offline. None here means "extrapolate
# and warn" instead of "raise" — astropy's own fallback is a 50-year polar-motion
# mean, good to the arcsecond, which is well inside seeing_fwhm for any target this
# reaches. This is a process-wide astropy setting, so it is set once at import time
# rather than per call.
iers.conf.auto_max_age = None

__all__ = [
    "calculate_sky_brightness",
    "krisciunas_schaefer_1991"
]

# Photometric unit conversion constant
# Reference: Krisciunas and Schaefer (1991), conversion from foot-candles/sr to nanoLamberts
KS91_FC_TO_NL_CONVERSION = 1e5

# ==========================================
# Phase 1: Astronomical & Ephemeris Engine
# ==========================================

def get_moon_and_target_geometry(
    target_ra: float, 
    target_dec: float, 
    obs_time_utc: str | list[str],
    lon: float = 120.87,     # Default to Lulin Observatory; unused when the caller
    lat: float = 23.47,      # supplies env.location, which calculator.py always does
    elevation: float = 2862.0
) -> tuple[Numeric, Numeric, Numeric, Numeric]:
    """
    Calculate the geometric relationship between the moon and the target using Astropy.
    
    Returns
    -------
    tuple[float, float, float, float]
        (alpha_deg, rho_deg, z_moon_deg, z_target_deg)
    """
    obs_time = Time(obs_time_utc, format="isot", scale="utc")
    location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=elevation*u.m)
    altaz_frame = AltAz(obstime=obs_time, location=location)
    
    target_coord = SkyCoord(ra=target_ra*u.deg, dec=target_dec*u.deg, frame="icrs")
    target_altaz = target_coord.transform_to(altaz_frame)

    sun = get_sun(obs_time)
    moon = get_body("moon", obs_time, location=location)
    
    sun_altaz = sun.transform_to(altaz_frame)
    moon_altaz = moon.transform_to(altaz_frame)

    rho_deg = cast(Numeric, target_altaz.separation(moon_altaz).deg)
    
    elongation = sun_altaz.separation(moon_altaz)
    alpha_deg = 180.0 - cast(Numeric, elongation.deg)
    
    z_moon_deg = 90.0 - cast(Numeric, moon_altaz.alt.deg)       # type: ignore
    z_target_deg = 90.0 - cast(Numeric, target_altaz.alt.deg)   # type: ignore
    
    return alpha_deg, rho_deg, z_moon_deg, z_target_deg

def get_sun_elevation(
    obs_time_utc: str | list[str],
    lon: float = 120.87,     # Default to Lulin Observatory; unused when the caller
    lat: float = 23.47,      # supplies env.location, which calculator.py always does
    elevation: float = 2862.0
) -> Numeric:
    """
    Calculate the Sun's altitude above the horizon, for daylight/twilight plotting.

    Separate from get_moon_and_target_geometry, which already derives the Sun's
    position for the lunar phase angle but returns only what the sky-brightness model
    needs. Kept as its own entry point rather than widening that tuple: its callers
    and their test doubles all agree on a four-value contract, and the visibility
    plot is a presentation concern that has no business reshaping the photometry path.

    Returns
    -------
    float
        Sun altitude in degrees. Negative below the horizon; below -18 is
        astronomical night.
    """
    obs_time = Time(obs_time_utc, format="isot", scale="utc")
    location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=elevation*u.m)
    altaz_frame = AltAz(obstime=obs_time, location=location)

    sun_altaz = get_sun(obs_time).transform_to(altaz_frame)

    return cast(Numeric, sun_altaz.alt.deg)   # type: ignore


# ==========================================
# Phase 2: Sky Brightness Modeling
# ==========================================

def krisciunas_schaefer_1991(
    alpha_deg: Numeric, 
    rho_deg: Numeric, 
    z_moon_deg: Numeric, 
    z_target_deg: Numeric, 
    k_ext_v: float = 0.17
) -> Numeric:
    """
    Krisciunas and Schaefer (1991) empirical model for lunar sky brightness.
    Calculates the scattered lunar flux contribution in the direction of the target.
    
    Returns
    -------
    Numeric
        Lunar surface brightness contribution [nanoLamberts].
    """
    # Constrain values to physical limits to prevent math domain errors
    rho = np.clip(rho_deg, 1e-2, 180.0)
    z_moon = np.clip(z_moon_deg, 0.0, 89.9)
    z_target = np.clip(z_target_deg, 0.0, 89.9)
    
    X_moon = 1.0 / np.cos(np.radians(z_moon))
    X_target = 1.0 / np.cos(np.radians(z_target))
    
    V_m = -12.73 + 0.026 * np.abs(alpha_deg) + (4e-9 * (alpha_deg ** 4.0))
    I_star = 10.0 ** (-0.4 * (V_m + 16.57))
    
    cos_rho2 = np.cos(np.radians(rho)) ** 2.0
    f_rho = 1e5 * (2.28e-5 * (rho ** -2.5) + 2.22e-4 * (10.0 ** (-0.0173 * rho)) + 2.13e-6 * cos_rho2)
    
    B_moon_raw = f_rho * I_star * (10.0 ** (-0.4 * k_ext_v * X_moon)) * (1.0 - 10.0 ** (-0.4 * k_ext_v * X_target))

    B_moon = B_moon_raw * KS91_FC_TO_NL_CONVERSION
    
    return B_moon

def calculate_sky_brightness(
    target_ra: float, 
    target_dec: float, 
    obs_time_utc: str | list[str],
    mu_dark: float,
    extinction_coeff: float,
    lon: float = 120.87,
    lat: float = 23.47,
    elevation: float = 2862.0
) -> Numeric:
    """
    Calculate total sky surface brightness including lunar contribution.
    
    Returns
    -------
    float
        Total sky surface brightness [mag/arcsec^2].
    """
    alpha, rho, z_moon, z_target = get_moon_and_target_geometry(
        target_ra, target_dec, obs_time_utc, lon, lat, elevation
    )
    
    B_moon_nl = krisciunas_schaefer_1991(alpha, rho, z_moon, z_target, k_ext_v=extinction_coeff)
    B_dark_nl = 34.08 * (10.0 ** (0.4 * (22.5 - mu_dark)))

    B_total = B_moon_nl + B_dark_nl

    B_total_safe = np.where(z_moon >= 90.0, B_dark_nl, B_total)
    
    mu_sky = 22.5 - 2.5 * np.log10(B_total_safe / 34.08)
    
    return cast(Numeric, mu_sky)
