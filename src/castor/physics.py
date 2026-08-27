import numpy as np
from numpy.typing import NDArray
from typing import TypeAlias

Numeric: TypeAlias = float | NDArray[np.float64]

# ==========================================
# Public API
# ==========================================
__all__ = [
    "calculate_airmass",
    "calculate_effective_area",
    "calculate_photon_energy",
    "calculate_total_throughput",
    "calculate_pixel_scale",
    "calculate_total_fwhm",
    "calculate_aperture_geometry",
    "convert_ab_to_wavelength_flux",
    "convert_vega_to_wavelength_flux",

    "calculate_point_source_rate",
    "calculate_extended_source_rate",
    "calculate_sky_background_rate",
    "calculate_peak_pixel_rate",

    "calculate_single_snr",
    "calculate_total_snr",
    "solve_required_exposures",
    "calculate_saturation_time",
    "calculate_optimal_exposure_time"
]

# ==========================================
# Physical Constants (CGS System)
# ==========================================
# Astronomical flux F_lambda is conventionally in erg/s/cm²/Å.
# Constants are defined in CGS units to prevent unit mismatch.
PLANCK_CONSTANT_CGS = 6.62607015e-27  # erg·s
SPEED_OF_LIGHT_CGS = 2.99792458e10    # cm/s
ARCSEC_PER_RADIAN = 206264.80624709636 # 180 * 3600 / pi

# ==========================================
# Stage 2: Physical & Environmental Conversions
# ==========================================

def calculate_airmass(zenith_angle_deg: Numeric) -> Numeric:
    """
    Calculate airmass using the secant approximation of the zenith angle.

    Corresponds to ATBD Section 4.1.1: X ≈ sec(z) = 1 / cos(z).

    Parameters
    ----------
    zenith_angle_deg : Numeric
        Zenith angle in degrees [deg].

    Returns
    -------
    Numeric
        Airmass (X) [dimensionless].
    """
    zenith_rad = np.radians(zenith_angle_deg)
    return 1.0 / np.cos(zenith_rad)

def calculate_effective_area(
    primary_mirror_diameter: Numeric, 
    secondary_mirror_diameter: Numeric
) -> Numeric:
    """
    Calculate the effective collecting area accounting for secondary mirror obscuration.

    Corresponds to ATBD Section 4.1.3: A_eff = (π/4) * (D_pri² - D_sec²).

    Parameters
    ----------
    primary_mirror_diameter : Numeric
        Primary mirror diameter (D_pri) [m].
    secondary_mirror_diameter : Numeric
        Secondary mirror diameter (D_sec) [m].

    Returns
    -------
    Numeric
        Effective collecting area (A_eff) [m²].
    """
    return (np.pi / 4.0) * (primary_mirror_diameter**2 - secondary_mirror_diameter**2)

def calculate_photon_energy(central_wavelength_nm: Numeric) -> Numeric:
    """
    Calculate the energy of a single photon at the central wavelength.

    Corresponds to ATBD Section 4.1.3: E_p = (h * c) / lambda_c.

    Parameters
    ----------
    central_wavelength_nm : Numeric
        Central wavelength (lambda_c) [nm].

    Returns
    -------
    Numeric
        Photon energy (E_p) [erg].
    """
    # Convert wavelength from nm to cm (1 nm = 1e-7 cm)
    wavelength_cm = central_wavelength_nm * 1e-7
    return (PLANCK_CONSTANT_CGS * SPEED_OF_LIGHT_CGS) / wavelength_cm

def calculate_total_throughput(
    optical_throughput: Numeric,
    filter_transmission: Numeric,
    quantum_efficiency: Numeric
) -> Numeric:
    """
    Calculate total system optical efficiency.

    Corresponds to ATBD Section 4.1.3: T_sys = R_opt * T_filt * QE.

    Parameters
    ----------
    optical_throughput : Numeric
        Optical system throughput (R_opt) [dimensionless, 0.0-1.0].
    filter_transmission : Numeric
        Filter transmission efficiency (T_filt) [dimensionless, 0.0-1.0].
    quantum_efficiency : Numeric
        Detector quantum efficiency (QE) [dimensionless, 0.0-1.0].

    Returns
    -------
    Numeric
        Total throughput (T_sys) [dimensionless, 0.0-1.0].
    """
    return optical_throughput * filter_transmission * quantum_efficiency

def calculate_pixel_scale(
    pixel_pitch_um: Numeric, 
    focal_length_m: Numeric
) -> Numeric:
    """
    Calculate the spatial resolution per pixel (pixel scale).

    Corresponds to ATBD Section 4.1.3: S_pixel = 206265 * (p_pixel / f_sys).

    Parameters
    ----------
    pixel_pitch_um : Numeric
        Physical pixel pitch (p_pixel) [µm].
    focal_length_m : Numeric
        Telescope focal length (f_sys) [m].

    Returns
    -------
    Numeric
        Pixel scale (S_pixel) [arcsec/pix].
    """
    # Convert pixel_pitch from µm to m (1 µm = 1e-6 m)
    pixel_pitch_m = pixel_pitch_um * 1e-6
    return ARCSEC_PER_RADIAN * (pixel_pitch_m / focal_length_m)

def calculate_total_fwhm(
    seeing_fwhm: Numeric,
    diffraction_fwhm: Numeric,
    optical_fwhm: Numeric,
    tracking_fwhm: Numeric
) -> Numeric:
    """
    Calculate the total spatial spreading (FWHM_tot) by quadrature sum.

    Corresponds to ATBD Section 4.1.2: FWHM_tot = sqrt(See² + Dif² + Opt² + Trk²).

    Parameters
    ----------
    seeing_fwhm : Numeric
        Atmospheric seeing FWHM [arcsec].
    diffraction_fwhm : Numeric
        Diffraction limit FWHM [arcsec].
    optical_fwhm : Numeric
        Optical aberrations FWHM [arcsec].
    tracking_fwhm : Numeric
        Telescope tracking error FWHM [arcsec].

    Returns
    -------
    Numeric
        Total FWHM (FWHM_tot) [arcsec].
    """
    return np.sqrt(
        seeing_fwhm**2 + diffraction_fwhm**2 + optical_fwhm**2 + tracking_fwhm**2
    )

def calculate_aperture_geometry(
    aperture_factor: Numeric,
    total_fwhm: Numeric,
    pixel_scale: Numeric
) -> tuple[Numeric, Numeric]:
    """
    Calculate the number of pixels in the aperture and the enclosed flux fraction.

    Corresponds to ATBD Section 4.2.1:
    N_pix = π * (k_ap * FWHM_tot)² / S_pixel²
    f_enc = 1 - 2^(-4 * k_ap²)

    Parameters
    ----------
    aperture_factor : Numeric
        Photometric aperture multiplier factor (k_ap, default 1.5) [dimensionless].
    total_fwhm : Numeric
        Total combined FWHM (FWHM_tot) [arcsec].
    pixel_scale : Numeric
        Pixel scale (S_pixel) [arcsec/pix].

    Returns
    -------
    tuple[Numeric, Numeric]
        (num_pixels_aperture, enclosed_flux_fraction) -> (N_pix [count], f_enc [dimensionless]).
    """
    aperture_radius_arcsec = aperture_factor * total_fwhm
    num_pixels = (np.pi * (aperture_radius_arcsec**2)) / (pixel_scale**2)
    enclosed_flux = 1.0 - (2.0 ** (-4.0 * (aperture_factor**2)))
    
    return num_pixels, enclosed_flux

def convert_vega_to_wavelength_flux(
    target_mag: Numeric, 
    zero_point_flux: Numeric
) -> Numeric:
    """
    Convert Vega magnitude to Top-of-Atmosphere wavelength flux density (F_lambda).

    Corresponds to ATBD Section 4.1.4: F_lambda = F_zp * 10^(-0.4 * m_target).
    """
    return zero_point_flux * (10.0 ** (-0.4 * target_mag))


def convert_ab_to_wavelength_flux(
    ab_mag: Numeric, 
    central_wavelength_nm: Numeric
) -> Numeric:
    """
    Convert AB magnitude to Top-of-Atmosphere wavelength flux density (F_lambda).

    Corresponds to ATBD Section 4.1.4:
    F_nu = 3631 * 10^(-0.4 * m_AB) [Jy]
    F_lambda = F_nu * (c / lambda_c²) [erg/s/cm²/Å]
    """
    # 1 Jy = 1e-23 erg/s/cm²/Hz
    f_nu_jy = 3631.0 * (10.0 ** (-0.4 * ab_mag))
    f_nu_cgs = f_nu_jy * 1e-23  # erg/s/cm²/Hz
    
    # Convert wavelength from nm to Ångström (1 nm = 10 Å)
    wavelength_angstrom = central_wavelength_nm * 10.0
    
    # Speed of light in Å/s (1 cm = 1e8 Å)
    c_angstrom = SPEED_OF_LIGHT_CGS * 1e8
    
    # F_lambda = F_nu * (c / lambda²)
    return f_nu_cgs * (c_angstrom / (wavelength_angstrom**2))

# ==========================================
# Stage 3: Photoelectron Count Rates
# ==========================================

def _collected_electron_rate(
    f_lambda: Numeric,
    filter_bandwidth: Numeric,
    effective_area: Numeric,
    photon_energy: Numeric,
    total_throughput: Numeric
) -> Numeric:
    """
    (Private) Convert flux *arriving at the aperture* into photoelectrons.

    No atmosphere appears here. This is only the telescope and the detector: the
    bandpass the flux is collected over, the area collecting it, the energy of one
    photon, and the fraction of them that become electrons.

    Whether the atmosphere has already taken its cut is the caller's business,
    and the two callers answer differently — see _calculate_base_electron_rate
    for light that arrives from outside, and calculate_sky_background_rate for
    light that does not.

    Parameters
    ----------
    f_lambda : Numeric
        Wavelength flux density at the aperture [erg/s/cm²/Å].
    filter_bandwidth : Numeric
        Effective spectral bandwidth [nm].
    effective_area : Numeric
        Effective collecting area of the telescope [m²].
    photon_energy : Numeric
        Energy of a single photon at central wavelength [erg].
    total_throughput : Numeric
        Combined system optical efficiency [dimensionless, 0.0-1.0].

    Returns
    -------
    Numeric
        Photoelectron generation rate before geometric scaling.
    """
    # Convert effective area from m² to cm²
    effective_area_cm2 = effective_area * 1e4

    # Convert filter bandwidth from nm to Ångströms (1 nm = 10 Å)
    filter_bandwidth_angstrom = filter_bandwidth * 10.0

    return (f_lambda * filter_bandwidth_angstrom * effective_area_cm2
            * (1.0 / photon_energy) * total_throughput)

def _calculate_base_electron_rate(
    f_lambda: Numeric,
    extinction_coeff: Numeric,
    airmass: Numeric,
    filter_bandwidth: Numeric,
    effective_area: Numeric,
    photon_energy: Numeric,
    total_throughput: Numeric
) -> Numeric:
    """
    (Private) Calculate the base photoelectron generation rate for light from outside.

    Corresponds to ATBD Section 4.2.2.
    It applies atmospheric extinction to the Top-of-Atmosphere (TOA) flux and
    converts the arriving energy into photoelectrons using system efficiencies.

    Only for sources above the atmosphere — stars and galaxies alike, since a
    galaxy's surface brightness is just as much a TOA quantity as a star's total
    flux. The sky background is not one of these and must not come through here.

    Parameters
    ----------
    f_lambda : Numeric
        TOA wavelength flux density [erg/s/cm²/Å].
    extinction_coeff : Numeric
        Atmospheric attenuation per unit airmass [mag/airmass].
    airmass : Numeric
        Approximated secant of the zenith angle [dimensionless].
    filter_bandwidth : Numeric
        Effective spectral bandwidth [nm].
    effective_area : Numeric
        Effective collecting area of the telescope [m²].
    photon_energy : Numeric
        Energy of a single photon at central wavelength [erg].
    total_throughput : Numeric
        Combined system optical efficiency [dimensionless, 0.0-1.0].

    Returns
    -------
    Numeric
        Base photoelectron generation rate before geometric scaling.
    """
    extinction_mag = extinction_coeff * airmass
    arriving_flux = f_lambda * (10.0 ** (-0.4 * extinction_mag))

    return _collected_electron_rate(
        arriving_flux, filter_bandwidth, effective_area, photon_energy, total_throughput
    )

def calculate_point_source_rate(
    f_lambda_total: Numeric,
    extinction_coeff: Numeric,
    airmass: Numeric,
    filter_bandwidth: Numeric,
    effective_area: Numeric,
    photon_energy: Numeric,
    total_throughput: Numeric,
    enclosed_flux_fraction: Numeric
) -> Numeric:
    """
    Calculate the photoelectron count rate for a point source target.

    Corresponds to ATBD Section 4.2.2 (A). 
    For point sources, f_lambda represents the total flux. 
    The base rate is scaled by the dimensionless enclosed flux fraction (f_enc).
    """
    base_rate = _calculate_base_electron_rate(
        f_lambda_total, extinction_coeff, airmass, filter_bandwidth, 
        effective_area, photon_energy, total_throughput
    )
    return base_rate * enclosed_flux_fraction

def calculate_extended_source_rate(
    f_lambda_surface: Numeric,
    extinction_coeff: Numeric,
    airmass: Numeric,
    filter_bandwidth: Numeric,
    effective_area: Numeric,
    photon_energy: Numeric,
    total_throughput: Numeric,
    num_pixels_aperture: Numeric,
    pixel_scale: Numeric
) -> Numeric:
    """
    Calculate the photoelectron count rate for an extended source target.

    Corresponds to ATBD Section 4.2.2 (B). 
    For extended sources, f_lambda represents surface flux density (per arcsec²). 
    The base rate is scaled by the total aperture area in arcsec².
    """
    base_rate = _calculate_base_electron_rate(
        f_lambda_surface, extinction_coeff, airmass, filter_bandwidth, 
        effective_area, photon_energy, total_throughput
    )
    aperture_area = num_pixels_aperture * (pixel_scale ** 2.0)
    return base_rate * aperture_area

def calculate_sky_background_rate(
    f_lambda_sky: Numeric,
    filter_bandwidth: Numeric,
    effective_area: Numeric,
    photon_energy: Numeric,
    total_throughput: Numeric,
    pixel_scale: Numeric
) -> Numeric:
    """
    Calculate the photoelectron count rate generated by the sky background per pixel.

    Corresponds to ATBD Section 4.2.2 (C).
    The sky brightness is treated as a surface flux density, scaled by the area of a
    single pixel.

    Takes no extinction and no airmass, deliberately. Every other rate in this module
    describes light crossing the atmosphere to reach us, and is dimmed by
    10^(-0.4 k X) on the way. The sky is not crossing anything: mu_sky comes from
    mu_dark, which is a brightness someone measured from the ground, through the very
    atmosphere the coefficient describes. Attenuating it again counts the same
    atmosphere twice.

    Doing so also gets the sign wrong, which is how it was found. Sky surface
    brightness rises with airmass — a longer line of sight holds more emitting
    atmosphere — where an extinction factor can only ever make it fall. Against
    ESO's FORS2 model the sky is 17.6% brighter at airmass 1.5 and 31.8% brighter at
    airmass 2.0, and LCO's calculator holds it flat; the old behaviour here lost 6%
    and 12% respectively. Flat is the honest floor: it stops double-counting without
    claiming a van Rhijn geometry this module does not model. See validation/test_eso.py.

    Parameters
    ----------
    f_lambda_sky : Numeric
        Sky surface flux density as observed from the ground [erg/s/cm²/Å/arcsec²].
    filter_bandwidth : Numeric
        Effective spectral bandwidth [nm].
    effective_area : Numeric
        Effective collecting area of the telescope [m²].
    photon_energy : Numeric
        Energy of a single photon at central wavelength [erg].
    total_throughput : Numeric
        Combined system optical efficiency [dimensionless, 0.0-1.0].
    pixel_scale : Numeric
        Spatial resolution per pixel [arcsec/pix].

    Returns
    -------
    Numeric
        Sky photoelectron count rate per pixel [e-/s/pix].
    """
    base_rate = _collected_electron_rate(
        f_lambda_sky, filter_bandwidth, effective_area, photon_energy, total_throughput
    )
    pixel_area = pixel_scale ** 2.0
    return base_rate * pixel_area

def calculate_peak_pixel_rate(
    source_count_rate: Numeric,
    total_fwhm: Numeric,
    pixel_scale: Numeric
) -> Numeric:
    """
    Calculate the peak photoelectron count rate hitting the central pixel.

    This function isolates the peak flux hitting a single pixel based on a 
    standard 2D Gaussian Point Spread Function (PSF) geometry. 
    It is required for evaluating the sensor saturation time limit (ATBD Section 4.3.3).

    Parameters
    ----------
    source_count_rate : Numeric
        Total detected photoelectron count rate from the target [e-/s].
    total_fwhm : Numeric
        Total spatial spreading FWHM [arcsec].
    pixel_scale : Numeric
        Spatial resolution per pixel [arcsec/pix].

    Returns
    -------
    Numeric
        Peak photoelectron count rate on the central pixel [e-/s/pix].
    """
    # For a Gaussian PSF, FWHM = 2 * sqrt(2 * ln(2)) * sigma
    # The fraction of total flux falling into a central pixel (approximated for small pixels)
    # is (S_pixel^2) / (2 * pi * sigma^2).
    
    sigma_squared = (total_fwhm ** 2.0) / (8.0 * np.log(2.0))
    peak_fraction = (pixel_scale ** 2.0) / (2.0 * np.pi * sigma_squared)
    
    return source_count_rate * peak_fraction

# ==========================================
# Stage 4: Final Output Metrics
# ==========================================

def calculate_single_snr(
    source_count_rate: Numeric,
    sky_count_rate: Numeric,
    dark_current_rate: Numeric,
    readout_noise: Numeric,
    num_pixels_aperture: Numeric,
    single_exp_time: Numeric
) -> Numeric:
    """
    Calculate the Signal-to-Noise Ratio (SNR) for a single exposure frame.

    Corresponds to ATBD Section 4.3.1.
    Calculates the signal from the source against the noise contributions from 
    the source itself (Poisson noise), sky background, dark current, and readout noise.

    Parameters
    ----------
    source_count_rate : Numeric
        Detected photoelectron count rate from the target [e-/s].
    sky_count_rate : Numeric
        Background photoelectron count rate per pixel [e-/s/pix].
    dark_current_rate : Numeric
        Thermal electron generation rate per pixel [e-/s/pix].
    readout_noise : Numeric
        Electronic noise introduced during readout [e-/pix].
    num_pixels_aperture : Numeric
        Number of pixels in the photometric aperture [count].
    single_exp_time : Numeric
        Integration time for the single exposure [s].

    Returns
    -------
    Numeric
        Single exposure SNR [dimensionless].
    """
    # Signal = Source rate * time
    signal = source_count_rate * single_exp_time
    
    # Noise Variance Components
    source_variance = source_count_rate * single_exp_time
    sky_variance = sky_count_rate * single_exp_time
    dark_variance = dark_current_rate * single_exp_time
    readout_variance = readout_noise ** 2.0
    
    # Total Variance = Source + N_pix * (Sky + Dark + RON^2)
    total_variance = source_variance + num_pixels_aperture * (sky_variance + dark_variance + readout_variance)
    
    return signal / np.sqrt(total_variance)

def calculate_total_snr(
    source_count_rate: Numeric,
    sky_count_rate: Numeric,
    dark_current_rate: Numeric,
    readout_noise: Numeric,
    num_pixels_aperture: Numeric,
    single_exp_time: Numeric,
    total_exp_time: Numeric,
    num_exposures: Numeric
) -> Numeric:
    """
    Calculate the Total Signal-to-Noise Ratio (SNR) across multiple exposures.

    Corresponds to ATBD Section 4.3.1.
    Aggregates the signal over the total exposure time and accounts for the 
    accumulation of read noise across multiple frames.

    Parameters
    ----------
    ... (Shared parameters matched with calculate_single_snr) ...
    total_exp_time : Numeric
        Cumulative integration time across all frames [s].
    num_exposures : Numeric
        Total number of exposure frames [count].

    Returns
    -------
    Numeric
        Total stacked SNR [dimensionless].
    """
    signal = source_count_rate * total_exp_time
    
    source_variance = source_count_rate * total_exp_time
    sky_variance_total = sky_count_rate * total_exp_time
    
    # Dark current and Readout Noise scale with the number of discrete frames
    dark_variance_frame = dark_current_rate * single_exp_time
    readout_variance_frame = readout_noise ** 2.0
    
    total_variance = source_variance + (num_pixels_aperture * sky_variance_total) + \
                     (num_exposures * num_pixels_aperture * (dark_variance_frame + readout_variance_frame))
                     
    return signal / np.sqrt(total_variance)

def solve_required_exposures(
    target_snr: Numeric,
    single_snr: Numeric
) -> Numeric:
    """
    Calculate the required number of exposures to reach a target SNR.

    Corresponds to ATBD Section 4.3.2.
    Derived algebraically from the SNR accumulation principles.

    Parameters
    ----------
    target_snr : Numeric
        Goal Signal-to-Noise Ratio [dimensionless].
    single_snr : Numeric
        SNR achieved in a single exposure [dimensionless].

    Returns
    -------
    Numeric
        Required number of exposures (exact float). 
        Note: The scheduling layer should apply np.ceil() if integer frame counts are required.
    """
    return (target_snr / single_snr) ** 2.0

def calculate_saturation_time(
    full_well_capacity: Numeric,
    peak_pixel_rate: Numeric,
    sky_count_rate: Numeric,
    dark_current_rate: Numeric
) -> Numeric:
    """
    Calculate the time limit before a single pixel reaches its Full Well Capacity.

    Corresponds to ATBD Section 4.3.3.
    Evaluates the combined flux of the target peak, sky background, and dark current.

    Parameters
    ----------
    full_well_capacity : Numeric
        Maximum electron capacity per pixel before saturation [e-].
    peak_pixel_rate : Numeric
        Peak photoelectron count rate on the central pixel [e-/s/pix].
    sky_count_rate : Numeric
        Background photoelectron count rate per pixel [e-/s/pix].
    dark_current_rate : Numeric
        Thermal electron generation rate per pixel [e-/s/pix].

    Returns
    -------
    Numeric
        Saturation time limit (t_sat) [s].
    """
    total_pixel_rate = peak_pixel_rate + sky_count_rate + dark_current_rate
    return full_well_capacity / total_pixel_rate

def calculate_optimal_exposure_time(
    sky_count_rate: Numeric,
    dark_current_rate: Numeric,
    readout_noise: Numeric,
    background_dominance_factor: Numeric = 1.0
) -> Numeric:
    """
    Calculate the "background-limited" single exposure time.

    This is the single-exposure integration time at which the combined shot
    noise from sky background + dark current overtakes the fixed per-frame
    readout noise, per pixel. Past this point, lengthening a single exposure
    further gives rapidly diminishing SNR returns per unit of *total*
    integration time (splitting a fixed total exposure into more sub-frames
    stops costing meaningful SNR) — so it becomes more efficient to add more
    exposures than to keep extending a single one.

    Derived from a standard-deviation ratio between the two noise sources:
    background shot noise reaches `background_dominance_factor` times the
    readout noise once

        sqrt((sky_count_rate + dark_current_rate) * t_opt) = background_dominance_factor * readout_noise

    which solves to:

        t_opt = (background_dominance_factor * readout_noise)² / (sky_count_rate + dark_current_rate)

    Parameters
    ----------
    sky_count_rate : Numeric
        Background photoelectron count rate per pixel [e-/s/pix].
    dark_current_rate : Numeric
        Thermal electron generation rate per pixel [e-/s/pix].
    readout_noise : Numeric
        Electronic noise introduced during readout [e-/pix].
    background_dominance_factor : Numeric, optional
        Desired ratio of (sky + dark) shot-noise stddev to readout-noise
        stddev, by default 1.0 — the literal crossover point where
        background noise just overtakes readout noise. Values > 1.0 push
        readout noise further into negligibility at the cost of a longer
        single exposure (more saturation / tracking / cosmic-ray risk).
        Provisional default — not yet backed by a specific reference
        guideline, revisit before relying on it for real observation
        planning.

    Returns
    -------
    Numeric
        Optimal single exposure time (t_opt) [s].
    """
    background_rate = sky_count_rate + dark_current_rate
    return ((background_dominance_factor * readout_noise) ** 2.0) / background_rate
