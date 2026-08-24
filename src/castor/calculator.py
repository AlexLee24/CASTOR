import math
import numpy as np

from castor import schema
from castor import physics
from castor import moon

__all__ = ["run_calculation"]

# ==========================================
# Helper: Flux Unification
# ==========================================

BrightnessType = (
    schema.VegaMagnitude | 
    schema.ABMagnitude | 
    schema.JanskyFlux | 
    schema.WavelengthFlux
)

def _unify_flux(
    brightness: BrightnessType,
    central_wavelength: float
) -> float:
    """
    Converts every different input brightness type into a unified Top-of-Atmosphere (TOA)
    F_lambda (erg/s/cm²/Å). A clean showcase of how powerful match/case destructuring can be.
    """
    match brightness:
        case schema.VegaMagnitude(target_mag=mag, zero_point_flux=zp):
            return float(physics.convert_vega_to_wavelength_flux(mag, zp))
            
        case schema.ABMagnitude(target_mag=mag):
            return float(physics.convert_ab_to_wavelength_flux(mag, central_wavelength))
            
        case schema.JanskyFlux(flux_value=jy):
            # 1 Jy = 10^-23 erg/s/cm²/Hz
            f_nu_cgs = jy * 1e-23
            wl_angstrom = central_wavelength * 10.0
            c_angstrom = physics.SPEED_OF_LIGHT_CGS * 1e8
            return float(f_nu_cgs * (c_angstrom / (wl_angstrom ** 2.0)))
            
        case schema.WavelengthFlux(flux_value=fl):
            return float(fl)
            
        case _:
            raise ValueError(f"Unknown brightness type: {type(brightness)}")

# ==========================================
# Main Orchestrator
# ==========================================

def run_calculation(request: schema.ObservationRequest) -> schema.ObservationResponse:
    """
    CASTOR core calculation pipeline.
    Follows the pure-function principle f(input) = output: stateless and safe under high concurrency.
    """
    # Extract domain-pillar aliases to keep the code concise
    inst = request.instrument
    tgt = request.target
    env = request.environment
    opt = request.options

    # ---------------------------------------------------------
    # Phase 1: Context Enrichment (environmental enrichment and astronomical geometry)
    # ---------------------------------------------------------
    # 1.1 Dynamic target coordinates and moonlight contribution
    alpha, rho, z_moon, z_target = moon.get_moon_and_target_geometry(
        target_ra=tgt.ra,
        target_dec=tgt.dec,
        obs_time_utc=env.observing_time_utc.strftime('%Y-%m-%dT%H:%M:%S'),
        lon=env.location.longitude_deg,
        lat=env.location.latitude_deg,
        elevation=env.location.elevation_m
    )
    
    # Clamp the zenith angle to keep airmass from tending to infinity
    z_target_safe = min(float(z_target), 89.0)
    airmass = float(physics.calculate_airmass(z_target_safe))
    
    # auto_calc_background only decides whether to layer the real-time moon/geometry
    # contribution on top of mu_dark — in both modes, mu_dark is a required baseline value
    # and is never derived automatically.
    if env.auto_calc_background:
        mu_sky = moon.calculate_sky_brightness(
            target_ra=tgt.ra, target_dec=tgt.dec,
            obs_time_utc=env.observing_time_utc.strftime('%Y-%m-%dT%H:%M:%S'),
            mu_dark=env.mu_dark,
            extinction_coeff=env.extinction_coeff,
            lon=env.location.longitude_deg, lat=env.location.latitude_deg,
            elevation=env.location.elevation_m,
            zodiacal_share=env.zodiacal_share
        )
    else:
        # zodiacal_share is independent of the moon: it completes mu_dark into
        # the actual moonless sky whether or not lunar scattering is being
        # modelled, so it applies here too — see moon.apply_zodiacal_baseline.
        mu_sky = moon.apply_zodiacal_baseline(
            env.mu_dark, tgt.ra, tgt.dec, env.zodiacal_share
        )

    # 1.2 Precompute optical and hardware physical quantities
    eff_area = float(physics.calculate_effective_area(
        inst.telescope.primary_mirror_diameter, 
        inst.telescope.secondary_mirror_diameter
    ))
    photon_energy = float(physics.calculate_photon_energy(inst.optic_filter.central_wavelength))
    # throughput_correction is an overall correction multiplier for when the loss can't be
    # broken down into optical_throughput / filter_transmission / quantum_efficiency
    # individually; it's applied on top of the product of all three.
    total_throughput = float(physics.calculate_total_throughput(
        inst.telescope.optical_throughput,
        inst.optic_filter.filter_transmission,
        inst.camera.quantum_efficiency
    )) * inst.throughput_correction
    pixel_scale = float(physics.calculate_pixel_scale(inst.camera.pixel_pitch, inst.telescope.focal_length))
    total_fwhm = float(physics.calculate_total_fwhm(
        env.seeing_fwhm, env.diffraction_fwhm, env.optical_fwhm, env.tracking_fwhm
    ))
    
    # 1.3 Photometric geometry and aperture coverage
    n_pix, f_enc = physics.calculate_aperture_geometry(opt.aperture_factor, total_fwhm, pixel_scale)
    n_pix, f_enc = float(n_pix), float(f_enc)

    # ---------------------------------------------------------
    # Phase 2: Flux Unification & Count Rates (flux normalization and photoelectron counts)
    # ---------------------------------------------------------
    # Unify the target flux
    f_lambda_target = _unify_flux(tgt.brightness, inst.optic_filter.central_wavelength)
    
    # Sky flux conversion (mu_sky is assumed to be in the AB magnitude system)
    f_lambda_sky = float(physics.convert_ab_to_wavelength_flux(mu_sky, inst.optic_filter.central_wavelength))

    # Compute the sky background count rate. No extinction term: mu_sky was
    # measured from the ground, so the atmosphere is already in it (ATBD 4.2.2 C).
    sky_rate = float(physics.calculate_sky_background_rate(
        f_lambda_sky,
        inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, pixel_scale
    ))

    # Branch the calculation based on target morphology. Each also says what its
    # brightest pixel is: saturation is a property of the target and the optics, so
    # it must not move when the photometric aperture drawn around them changes.
    match tgt.morphology:
        case schema.PointMorphology():
            source_rate = float(physics.calculate_point_source_rate(
                f_lambda_target, env.extinction_coeff, airmass,
                inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, f_enc
            ))
            # Divide f_enc back out: calculate_peak_pixel_rate wants the star's whole
            # flux, and source_rate is only the part the aperture kept.
            peak_rate = float(physics.calculate_peak_pixel_rate(
                source_rate / f_enc, total_fwhm, pixel_scale
            ))
        case schema.ExtendedMorphology():
            source_rate = float(physics.calculate_extended_source_rate(
                f_lambda_target, env.extinction_coeff, airmass,
                inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, n_pix, pixel_scale
            ))
            # No PSF peak to find: the model holds surface brightness uniform, so
            # every pixel in the aperture sees the same rate as every other.
            peak_rate = source_rate / n_pix
        case _:
            raise ValueError("Unknown target morphology")

    # ---------------------------------------------------------
    # Phase 3 & 4: Strategy Execution & Assembly (strategy solving and response assembly)
    # ---------------------------------------------------------
    single_snr = float(physics.calculate_single_snr(
        source_count_rate=source_rate,
        sky_count_rate=sky_rate,
        dark_current_rate=inst.camera.dark_current_rate,
        readout_noise=inst.camera.readout_noise,
        num_pixels_aperture=n_pix,
        single_exp_time=opt.single_exp_time
    ))

    # Solve forward or backward depending on the user's mode (Options)
    match opt:
        case schema.SolveForSNR(num_exposures=n_exp):
            total_exp_time = opt.single_exp_time * n_exp
            total_snr = float(physics.calculate_total_snr(
                source_rate, sky_rate, inst.camera.dark_current_rate, inst.camera.readout_noise,
                n_pix, opt.single_exp_time, total_exp_time, n_exp
            ))
            final_req_exposures = None # req_exposures isn't returned in SolveForSNR mode

        case schema.SolveForTime(target_snr=t_snr):
            req_exp_float = physics.solve_required_exposures(t_snr, single_snr)
            final_req_exposures = int(math.ceil(req_exp_float))
            total_exp_time = opt.single_exp_time * final_req_exposures
            
            total_snr = float(physics.calculate_total_snr(
                source_rate, sky_rate, inst.camera.dark_current_rate, inst.camera.readout_noise,
                n_pix, opt.single_exp_time, total_exp_time, final_req_exposures
            ))
            
        case _:
            raise ValueError("Unknown calculation option")

    # Compute the saturation limit and danger flags
    t_sat = float(physics.calculate_saturation_time(
        inst.camera.full_well_capacity, peak_rate, sky_rate, inst.camera.dark_current_rate
    ))

    # background_dominance_factor keeps its default value of 1.0; see the docstring of
    # calculate_optimal_exposure_time for details.
    t_opt = float(physics.calculate_optimal_exposure_time(
        sky_rate, inst.camera.dark_current_rate, inst.camera.readout_noise
    ))

    warnings = []
    if airmass > 2.0:
        warnings.append("Airmass > 2.0: Extinction model accuracy may degrade.")

    # Assemble the Pydantic Response contract
    return schema.ObservationResponse(
        core=schema.CoreResult(
            total_snr=total_snr,
            single_snr=single_snr,
            required_exposures=final_req_exposures,
            saturation_time_limit=t_sat,
            optimal_exposure_time=t_opt
        ),
        budget=schema.SignalNoiseBudget(
            source_count_rate=source_rate,
            sky_count_rate=sky_rate,
            peak_pixel_rate=peak_rate
        ),
        diagnostics=schema.PhysicalDiagnostics(
            total_fwhm=total_fwhm,
            effective_area=eff_area,
            pixel_scale=pixel_scale,
            total_throughput=total_throughput,
            enclosed_flux_fraction=f_enc,
            num_pixels_aperture=n_pix
        ),
        flags=schema.SystemFlags(
            is_saturated=bool(opt.single_exp_time > t_sat),
            warnings=warnings
        )
    )