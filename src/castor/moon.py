"""Everything in a request that depends on when it is and where it points.

The name understates the module. The moon is one of three sky-brightness
components here, and the smallest part of what it does:

    mu_sky = -2.5 log10( Flux_dark + Flux_zodiacal + Flux_moon )

`Flux_dark` is the caller's `mu_dark`, a brightness someone measured from the
ground. `Flux_moon` is Krisciunas & Schaefer 1991, scattered moonlight from the
lunar phase, the target's separation from the moon, and both altitudes.
`Flux_zodiacal` is sunlight off interplanetary dust, a function of the target's
ecliptic latitude, and is zero unless the caller supplies `zodiacal_share`.

Two things about that third term are easy to get wrong, and both have been:

**It is a subtraction before it is an addition.** `mu_dark` is *measured*, so
whatever zodiacal light was in the sky when it was measured is already inside
it. Computing zodiacal light separately and adding it counts a quarter of the
sky twice — the same shape of error as the extinction term that used to be
applied to the sky, and the one the project's own slides named "Hidden Errors
(Two Wrongs Make a Right)". The construction that works splits `mu_dark` into a
local-only baseline first; `zodiacal_share` records how much was taken out, and
`apply_zodiacal_baseline` puts back an equivalent amount sized to the actual
pointing. See docs/presets.md and validation/QUESTIONS.md 9 and 10.

**It is not the moon's business.** `apply_zodiacal_baseline` is deliberately
independent of `auto_calc_background`: that flag decides whether moonlight is
layered on, while `mu_dark` plus `zodiacal_share` together describe the
*moonless* sky. Gating the zodiacal term behind it meant every caller leaving
that flag at its default — the GUI does — silently got a fainter sky than the
one actually measured.

This is also the only module in the engine that depends on an external astronomy
library rather than pure local maths, which is why the IERS configuration below
lives here rather than anywhere else.
"""
import numpy as np
from numpy.typing import NDArray
from typing import TypeAlias, cast, Any

from astropy.time import Time
from astropy.coordinates import (
    SkyCoord, EarthLocation, AltAz, GeocentricMeanEcliptic, get_sun, get_body
)
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
    "krisciunas_schaefer_1991",
    "ecliptic_latitude",
    "calculate_zodiacal_brightness_nl",
    "apply_zodiacal_baseline",
]

# Krisciunas & Schaefer (1991), foot-candles/sr to nanoLamberts.
KS91_FC_TO_NL_CONVERSION = 1e5

# ==========================================
# Ephemeris — where things are
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


def ecliptic_latitude(target_ra: float, target_dec: float) -> float:
    """Absolute ecliptic latitude of a target, degrees.

    A coordinate transform of RA/Dec alone, not of when or from where it is
    observed — the ecliptic is fixed relative to the stars, so unlike everything
    else in this module this needs no time, no site, and returns a scalar even
    when the caller is otherwise running a time series. Absolute value because
    zodiacal light's brightness (see `calculate_zodiacal_brightness_nl`) is
    symmetric about the ecliptic plane; only the distance from it matters.
    """
    coord = SkyCoord(ra=target_ra * u.deg, dec=target_dec * u.deg, frame="icrs")
    ecl = coord.transform_to(GeocentricMeanEcliptic())
    return abs(float(ecl.lat.deg))   # type: ignore


# ==========================================
# Sky brightness — what that makes the sky do
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

#: Ecliptic latitude our own Lulin photometry looks down, degrees — the
#: sightline `zodiacal_share` is measured relative to (validation/skycalc.py's
#: OUR_SIGHTLINE). `zodiacal_share` is only meaningful anchored to this latitude.
ZODIACAL_REFERENCE_ECLIPTIC_LATITUDE_DEG = 15.9

#: Zodiacal + scattered-starlight brightness as a function of |ecliptic
#: latitude|, relative to its own value at the reference latitude above.
#: Brightest towards the ecliptic plane, dimmest towards the poles, saturating
#: past about 60 degrees — real zodiacal light behaviour, not a fitted curve.
#:
#: Derived, not measured directly here: ESO's SkyCalc gives Paranal's *total*
#: moonless sky over a spread of ecliptic latitudes at a fixed solar elongation
#: (validation/skycalc.py SIGHTLINE_STUDY.pointing_dmag), and that total mixes
#: airglow with zodiacal light. Assuming the airglow/light-pollution part holds
#: still with pointing — the same assumption the mu_dark split in presets.json
#: relies on — lets it be subtracted out, band by band, using Paranal's own
#: zodiacal share at that sightline (SIGHTLINE_STUDY.zodiacal_and_starlight_share):
#:
#:   r(L) = [10^(-0.4 * dmag_paranal(L)) - (1 - share_paranal)] / share_paranal
#:
#: Done separately for g', r' and i', the three curves agree to within 11% at
#: the pole and closer everywhere nearer the plane — the table below is their
#: mean. That closeness is not assumed, it is the check: recombined with each
#: band's own local/zodiacal split, the three curves reproduce Lulin's
#: independently-published plane-to-pole swings (validation/skycalc.py
#: AT_LULIN.pointing_dmag_plane_to_pole: 0.174 / 0.193 / 0.101 mag) to the third
#: decimal, which is the two derivations agreeing rather than one another's
#: rounding. Treating the residual per-band spread as zero — one curve instead
#: of three — is this table's actual approximation.
#:
#: What this does not do: SkyCalc was only queried at one solar elongation (130
#: degrees, OUR_SIGHTLINE's), so this shape holds near that elongation and is
#: applied regardless of it — an unmodelled dependence, not a zero one. See
#: QUESTIONS.md 9 and 10.
ZODIACAL_LATITUDE_SHAPE = {
    0.0:  1.2077,
    15.9: 1.0000,
    30.0: 0.7879,
    45.0: 0.6619,
    60.0: 0.5813,
    90.0: 0.5813,
}


def calculate_zodiacal_brightness_nl(
    ecliptic_latitude_deg: Numeric,
    zodiacal_share: float,
    mu_dark: float,
) -> Numeric:
    """Zodiacal + scattered-starlight contribution to the sky, in nanolamberts.

    `mu_dark` here is already the *local* baseline (airglow and light pollution
    only, with the interplanetary part split out — see presets.json's comment on
    Lulin's g'/r'/i' entries) and `zodiacal_share` is what fraction of the
    *original, undecomposed* measurement that split removed, at
    `ZODIACAL_REFERENCE_ECLIPTIC_LATITUDE_DEG`. Inverting the split recovers the
    zodiacal brightness at the reference latitude:

        share = B_zodi / (B_local + B_zodi)  =>  B_zodi = B_local * share / (1 - share)

    which `ZODIACAL_LATITUDE_SHAPE` then scales to wherever the target actually
    is. At the reference latitude this returns exactly the amount `mu_dark` had
    subtracted from it, so `calculate_sky_brightness` there reproduces the
    original total the split started from.
    """
    lat = np.clip(np.abs(ecliptic_latitude_deg), 0.0, 90.0)
    anchors = sorted(ZODIACAL_LATITUDE_SHAPE)
    shape = np.interp(lat, anchors, [ZODIACAL_LATITUDE_SHAPE[a] for a in anchors])

    b_local_nl = 34.08 * (10.0 ** (0.4 * (22.5 - mu_dark)))
    b_zodi_at_reference_nl = b_local_nl * zodiacal_share / (1.0 - zodiacal_share)

    return cast(Numeric, b_zodi_at_reference_nl * shape)


def apply_zodiacal_baseline(
    mu_dark: float,
    target_ra: float,
    target_dec: float,
    zodiacal_share: float | None = None,
) -> float:
    """`mu_dark`, completed with its zodiacal component if it has one.

    Deliberately independent of the moon and of `auto_calc_background`:
    `mu_dark` plus `zodiacal_share` together describe the *moonless* sky, and
    the split that produced them exists to make that moonless sky pointing-
    dependent instead of one fixed number per band — it has nothing to do with
    the moon. Gating it behind the same flag that turns lunar scattering on and
    off would mean a caller who leaves that flag at its default False (as the
    GUI does) silently gets a fainter sky than the one actually measured, for
    every preset that carries this split. `auto_calc_background` still decides
    only whether the moon is layered on top of whatever this returns.

    `zodiacal_share` of `None` or `0` returns `mu_dark` unchanged — every
    profile without this measurement behaves exactly as before this function
    existed.
    """
    if not zodiacal_share:
        return mu_dark
    ecl_lat = ecliptic_latitude(target_ra, target_dec)
    b_local_nl = 34.08 * (10.0 ** (0.4 * (22.5 - mu_dark)))
    b_zodi_nl = calculate_zodiacal_brightness_nl(ecl_lat, zodiacal_share, mu_dark)
    return 22.5 - 2.5 * np.log10((b_local_nl + b_zodi_nl) / 34.08)


def calculate_sky_brightness(
    target_ra: float,
    target_dec: float,
    obs_time_utc: str | list[str],
    mu_dark: float,
    extinction_coeff: float,
    lon: float = 120.87,
    lat: float = 23.47,
    elevation: float = 2862.0,
    zodiacal_share: float | None = None,
) -> Numeric:
    """
    Calculate total sky surface brightness including lunar contribution.

    `zodiacal_share` adds a third, pointing-dependent term on top of the moon
    and `mu_dark` — see `calculate_zodiacal_brightness_nl`. `None` (the default)
    leaves the behaviour exactly as it was before this parameter existed:
    `mu_dark` is the whole moonless sky and carries no pointing dependence.

    Returns
    -------
    float
        Total sky surface brightness [mag/arcsec^2].
    """
    alpha, rho, z_moon, z_target = get_moon_and_target_geometry(
        target_ra, target_dec, obs_time_utc, lon, lat, elevation
    )

    B_moon_nl = krisciunas_schaefer_1991(alpha, rho, z_moon, z_target, k_ext_v=extinction_coeff)

    mu_local = apply_zodiacal_baseline(mu_dark, target_ra, target_dec, zodiacal_share)
    B_local_nl = 34.08 * (10.0 ** (0.4 * (22.5 - mu_local)))

    B_total = B_moon_nl + B_local_nl

    B_total_safe = np.where(z_moon >= 90.0, B_local_nl, B_total)

    mu_sky = 22.5 - 2.5 * np.log10(B_total_safe / 34.08)

    return cast(Numeric, mu_sky)
