import math
import numpy as np
from datetime import timedelta, timezone

from castor import schema
from castor import physics
from castor import moon
from castor.calculator import _unify_flux

__all__ = ["run_batch_calculation"]

def _expand_time_series(start: schema.AwareDatetime, end: schema.AwareDatetime, step_minutes: float) -> list[str]:
    """Expands the user's start and end time into a discrete array of ISO 8601 strings, stepped by step_minutes.

    Normalizes each point to UTC and formats it without a UTC offset suffix (e.g. "2026-01-01T18:00:00",
    not "...+00:00"): moon.py hands this straight to astropy's Time(..., format="isot"), and isot's strict
    parser rejects an offset suffix outright, so datetime.isoformat()'s default output can't be used as-is.
    """
    times = []
    current = start
    delta = timedelta(minutes=step_minutes)

    max_points = 1000

    while current <= end and len(times) < max_points:
        times.append(current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
        current += delta

    return times

def run_batch_calculation(request: schema.BatchObservationRequest) -> schema.BatchObservationResponse:
    """
    CASTOR batch calculation pipeline.
    Takes a time-series contract, expands it into arrays, and uses NumPy broadcasting to
    compute the physics for the whole night in one pass.
    """
    inst = request.instrument
    tgt = request.target
    env = request.environment
    opt = request.options

    time_series_iso = _expand_time_series(env.start_time_utc, env.end_time_utc, env.time_step_minutes)
    if not time_series_iso:
        raise ValueError("Time series expansion resulted in an empty array. Check start and end times.")

    alpha_arr, rho_arr, z_moon_arr, z_target_arr = moon.get_moon_and_target_geometry(
        target_ra=tgt.ra, target_dec=tgt.dec,
        obs_time_utc=time_series_iso,
        lon=env.location.longitude_deg, lat=env.location.latitude_deg,
        elevation=env.location.elevation_m
    )
    
    # Daylight is a plotting concern only, so it is fetched separately rather than
    # threaded through the photometry path — see moon.get_sun_elevation.
    sun_elev_arr = moon.get_sun_elevation(
        obs_time_utc=time_series_iso,
        lon=env.location.longitude_deg, lat=env.location.latitude_deg,
        elevation=env.location.elevation_m
    )

    z_target_safe = np.clip(z_target_arr, 0.0, 89.0)
    airmass_arr = physics.calculate_airmass(z_target_safe)
    
    mu_sky_arr = moon.calculate_sky_brightness(
        target_ra=tgt.ra, target_dec=tgt.dec,
        obs_time_utc=time_series_iso, mu_dark=env.mu_dark,
        extinction_coeff=env.extinction_coeff,
        lon=env.location.longitude_deg, lat=env.location.latitude_deg,
        elevation=env.location.elevation_m,
        zodiacal_share=env.zodiacal_share
    )

    eff_area = float(physics.calculate_effective_area(inst.telescope.primary_mirror_diameter, inst.telescope.secondary_mirror_diameter))
    photon_energy = float(physics.calculate_photon_energy(inst.optic_filter.central_wavelength))
    total_throughput = float(physics.calculate_total_throughput(inst.telescope.optical_throughput, inst.optic_filter.filter_transmission, inst.camera.quantum_efficiency))
    pixel_scale = float(physics.calculate_pixel_scale(inst.camera.pixel_pitch, inst.telescope.focal_length))
    total_fwhm = float(physics.calculate_total_fwhm(env.seeing_fwhm, env.diffraction_fwhm, env.optical_fwhm, env.tracking_fwhm))
    n_pix, f_enc = physics.calculate_aperture_geometry(opt.aperture_factor, total_fwhm, pixel_scale)
    n_pix, f_enc = float(n_pix), float(f_enc)

    # The sky subtracted from the aperture is an estimate made in the annulus, and
    # its error lands on every aperture pixel at once. Without an annulus there is
    # nothing to estimate from, so the cost is zero and the sky is taken as exact.
    n_est = 0.0
    if opt.sky_annulus is not None:
        n_est = float(physics.calculate_sky_estimate_pixels(
            n_pix,
            opt.sky_annulus.inner_factor, opt.sky_annulus.outer_factor,
            total_fwhm, pixel_scale, opt.sky_annulus.estimator
        ))

    f_lambda_target = _unify_flux(tgt.brightness, inst.optic_filter.central_wavelength)
    
    f_lambda_sky_arr = physics.convert_ab_to_wavelength_flux(mu_sky_arr, inst.optic_filter.central_wavelength)

    sky_rate_arr = physics.calculate_sky_background_rate(
        f_lambda_sky_arr,
        inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, pixel_scale
    )

    # Each branch also states its brightest pixel; see calculator.py for why that
    # cannot be derived from source_rate once an aperture has been applied to it.
    match tgt.morphology:
        case schema.PointMorphology():
            source_rate_arr = physics.calculate_point_source_rate(
                f_lambda_target, env.extinction_coeff, airmass_arr,
                inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, f_enc
            )
            peak_rate_arr = physics.calculate_peak_pixel_rate(
                source_rate_arr / f_enc, total_fwhm, pixel_scale
            )
        case schema.ExtendedMorphology():
            source_rate_arr = physics.calculate_extended_source_rate(
                f_lambda_target, env.extinction_coeff, airmass_arr,
                inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, n_pix, pixel_scale
            )
            peak_rate_arr = source_rate_arr / n_pix
        case _:
            raise ValueError("Unknown target morphology")

    single_snr_arr = physics.calculate_single_snr(
        source_rate_arr, sky_rate_arr, inst.camera.dark_current_rate, inst.camera.readout_noise,
        n_pix, opt.single_exp_time, n_est
    )

    # Stays None for solve_snr, where "how many exposures" is an input rather than
    # an answer and there is nothing per-timestamp to report.
    req_exp_int_arr = None

    match opt:
        case schema.BatchSolveForSNR(num_exposures=n_exp):
            total_exp_time = opt.single_exp_time * n_exp
            total_snr_arr = physics.calculate_total_snr(
                source_rate_arr, sky_rate_arr, inst.camera.dark_current_rate, inst.camera.readout_noise,
                n_pix, opt.single_exp_time, total_exp_time, n_exp, n_est
            )

        case schema.BatchSolveForTime(target_snr=t_snr):
            req_exp_float_arr = physics.solve_required_exposures(t_snr, single_snr_arr)
            
            req_exp_int_arr = np.ceil(req_exp_float_arr)
            total_exp_time_arr = opt.single_exp_time * req_exp_int_arr
            
            total_snr_arr = physics.calculate_total_snr(
                source_rate_arr, sky_rate_arr, inst.camera.dark_current_rate, inst.camera.readout_noise,
                n_pix, opt.single_exp_time, total_exp_time_arr, req_exp_int_arr, n_est
            )
            
        case _:
            raise ValueError("Unknown batch calculation option")

    t_sat_arr = physics.calculate_saturation_time(
        inst.camera.full_well_capacity, peak_rate_arr, sky_rate_arr, inst.camera.dark_current_rate
    )
    
    warnings = []
    if np.any(airmass_arr > 2.0):
        warnings.append("Airmass > 2.0 detected in time series: Extinction model accuracy may degrade.")

    # np.atleast_1d ensures that even a single expanded time point becomes a list cleanly,
    # without crashing
    def to_list(arr) -> list[float]:
        return np.atleast_1d(arr).tolist()

    return schema.BatchObservationResponse(
        core=schema.BatchCoreResult(
            timestamps_iso=time_series_iso,
            total_snr=to_list(total_snr_arr),
            single_snr=to_list(single_snr_arr),
            required_exposures=None if req_exp_int_arr is None else to_list(req_exp_int_arr),
            saturation_time_limit=to_list(t_sat_arr)
        ),
        # Reuses the zenith angles the photometry already needed; elevation is just
        # their complement. Deliberately the raw z_target_arr, not the z_target_safe
        # clamped for airmass, so a target below the horizon reads as negative
        # elevation rather than as a floor value.
        ephemeris=schema.BatchEphemeris(
            target_elevation_deg=to_list(90.0 - z_target_arr),
            moon_elevation_deg=to_list(90.0 - z_moon_arr),
            sun_elevation_deg=to_list(sun_elev_arr)
        ),
        flags=schema.SystemFlags(
            is_saturated=bool(np.any(opt.single_exp_time > t_sat_arr)),
            warnings=warnings
        )
    )