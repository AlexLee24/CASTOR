from pydantic import BaseModel, Field, PositiveFloat, PositiveInt, AwareDatetime, ConfigDict, model_validator
from typing import Literal, Union, Annotated

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class TelescopeSchema(StrictModel):
    primary_mirror_diameter: PositiveFloat = Field(
        ..., 
        description="Diameter of the primary optical aperture in meters. (ATBD: D_pri)"
    )
    secondary_mirror_diameter: float = Field(
        ..., 
        description="Diameter of the secondary mirror (central obscuration) in meters. (ATBD: D_sec)"
    )
    focal_length: PositiveFloat = Field(
        ..., 
        description="Effective focal length of the telescope system in meters. (ATBD: f_sys)"
    )
    optical_throughput: float = Field(
        ..., 
        ge=0, 
        le=1, 
        description="Transmission/reflection efficiency of the telescope optics, as a dimensionless ratio from 0.0 to 1.0. (ATBD: R_opt)"
    )

class CameraSchema(StrictModel):
    pixel_pitch: PositiveFloat = Field(
        ..., 
        description="Physical size of a single detector pixel in micrometers (µm). (ATBD: p_pixel)"
    )
    quantum_efficiency: float = Field(
        ..., 
        ge=0, 
        le=1, 
        description="Fraction of incident photons converted to electrons, as a dimensionless ratio from 0.0 to 1.0. (ATBD: QE)"
    )
    dark_current_rate: float = Field(
        ..., 
        ge=0, 
        description="Thermal electron generation rate per pixel in e-/s/pix. (ATBD: R_dark)"
    )
    readout_noise: float = Field(
        ..., 
        ge=0, 
        description="Electronic noise introduced during the readout phase in e-/pix. (ATBD: RON)"
    )
    full_well_capacity: PositiveFloat = Field(
        ...,
        description="Maximum electron capacity per pixel before saturation in e-. (ATBD: FWC)"
    )
    background_flatness_fraction: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description=(
            "Flat-field and background-gradient residual, as a fraction of the background "
            "level per frame, that does not average down as photon statistics — it is a "
            "correlated error across the aperture, not shot noise. (ATBD: f_flat). Default "
            "0.0 means not modelled, the behaviour before this field existed."
        )
    )

class FilterSchema(StrictModel):
    central_wavelength: PositiveFloat = Field(
        ..., 
        description="Central wavelength of the specific filter in nanometers (nm). (ATBD: lambda_c)"
    )
    filter_bandwidth: PositiveFloat = Field(
        ..., 
        description="Effective spectral bandwidth of the chosen filter in nanometers (nm). (ATBD: Delta_lambda)"
    )
    filter_transmission: float = Field(
        ..., 
        ge=0, 
        le=1, 
        description="Transmission efficiency of the inserted filter, as a dimensionless ratio from 0.0 to 1.0. (ATBD: T_filt)"
    )

class InstrumentProfile(StrictModel):
    telescope: TelescopeSchema
    camera: CameraSchema
    optic_filter: FilterSchema

    throughput_correction: float = Field(
        ..., 
        ge=0, 
        le=1, 
        description="Additional system-level throughput correction factor, as a dimensionless ratio from 0.0 to 1.0."
    )

class PointMorphology(StrictModel):
    type: Literal["point"] = "point"

class ExtendedMorphology(StrictModel):
    type: Literal["extended"] = "extended"

class VegaMagnitude(StrictModel):
    type: Literal["vega_mag"] = "vega_mag"
    target_mag: float = Field(
        ..., 
        description="Apparent magnitude of the observation target in the Vega system. (ATBD: m_target)"
    )
    zero_point_flux: PositiveFloat = Field(
        ..., 
        description="Reference flux density for a zero-magnitude source in erg/s/cm²/Å. (ATBD: F_zp)"
    )

class ABMagnitude(StrictModel):
    type: Literal["ab_mag"] = "ab_mag"
    target_mag: float = Field(
        ..., 
        description="Apparent magnitude of the observation target in the AB system (0 mag = 3631 Jy)."
    )

class JanskyFlux(StrictModel):
    type: Literal["jansky_flux"] = "jansky_flux"
    flux_value: PositiveFloat = Field(
        ..., 
        description="Frequency flux density (F_nu) in Jansky (Jy)."
    )

class WavelengthFlux(StrictModel):
    type: Literal["wavelength_flux"] = "wavelength_flux"
    flux_value: PositiveFloat = Field(
        ..., 
        description="Wavelength flux density (F_lambda) in erg/s/cm²/Å."
    )

class FlatSED(StrictModel):
    type: Literal["flat"] = "flat"

class TempSED(StrictModel):
    type: Literal["Temp"] = "Temp"

class TargetProfile(StrictModel):
    morphology: Annotated[Union[PointMorphology, ExtendedMorphology], Field(discriminator="type")]
    brightness: Annotated[
        Union[VegaMagnitude, ABMagnitude, JanskyFlux, WavelengthFlux], 
        Field(discriminator="type", description="Brightness definition and zero-point reference.")
    ]
    sed: Annotated[Union[FlatSED, TempSED], Field(discriminator="type")]

    ra: float = Field(
        ..., 
        ge=0.0, 
        lt=360.0,
        description="Right Ascension of the target in decimal degrees (J2000)."
    )
    dec: float = Field(
        ..., 
        ge=-90.0, 
        le=90.0,
        description="Declination of the target in decimal degrees (J2000)."
    )

class ObservatoryLocation(StrictModel):
    latitude_deg: float = Field(
        ..., 
        ge=-90.0, 
        le=90.0, 
        description="Observer's latitude in degrees. Must be between -90.0 and +90.0."
    )
    longitude_deg: float = Field(
        ..., 
        ge=-180.0, 
        le=180.0, 
        description="Observer's longitude in degrees. Must be between -180.0 and +180.0."
    )
    elevation_m: float = Field(..., description="Observer's elevation above sea level in meters.")

class EnvironmentCondition(StrictModel):
    location: ObservatoryLocation = Field(
        ..., 
        description="Observer's geographic location."
    )
    observing_time_utc: AwareDatetime = Field(
        ..., 
        description="Observation timestamp in ISO 8601 UTC format."
    )
    auto_calc_background: bool = Field(
        ...,
        description=(
            "Boolean toggle for whether to layer the real-time lunar/geometric sky-brightness "
            "contribution (derived from observing_time_utc, location, and the target's position) "
            "on top of the user-supplied `mu_dark` baseline. When False, the moon is left out and "
            "the sky is `mu_dark`, completed by its zodiacal term when `zodiacal_share` is set, which "
            "applies either way. `mu_dark` is required either way — this flag never "
            "derives mu_dark itself, since moonless-sky brightness (light pollution, airglow, etc.) "
            "cannot be inferred from time and location alone."
        )
    )

    mu_dark: float = Field(
        ...,
        description="Moonless-night baseline surface brightness of the sky in mag/arcsec², the base every sky is built on: completed by a zodiacal term when zodiacal_share is set, with the moon on top when auto_calc_background is True. (ATBD: mu_dark)"
    )
    zodiacal_share: float | None = Field(
        default=None,
        ge=0,
        lt=1,
        description=(
            "Fraction of the moonless sky that was zodiacal light and scattered starlight, "
            "not airglow or light pollution, in the original measurement `mu_dark` was split "
            "from — at this site's own reference sightline. Adds a pointing-dependent term on top "
            "of mu_dark (now the local-only baseline that split left behind) whether or not "
            "auto_calc_background is True: the two together are the moonless sky, and that flag "
            "only adds the moon. None means not modelled: mu_dark is treated as "
            "the whole moonless sky with no pointing correction, the behaviour before this field "
            "existed. Site-specific and rarely known; see validation/QUESTIONS.md 9 and 10."
        )
    )
    extinction_coeff: float = Field(
        ..., 
        description="Atmospheric attenuation per unit airmass in mag/airmass. (ATBD: k_ext)"
    )
    
    seeing_fwhm: PositiveFloat = Field(
        ..., 
        description="Atmospheric seeing FWHM in arcseconds. (ATBD: FWHM_See)"
    )
    diffraction_fwhm: PositiveFloat = Field(
        ..., 
        description="Diffraction limit FWHM in arcseconds. (ATBD: FWHM_Dif)"
    )
    optical_fwhm: PositiveFloat = Field(
        ..., 
        description="Optical aberrations FWHM in arcseconds. (ATBD: FWHM_Opt)"
    )
    tracking_fwhm: PositiveFloat = Field(
        ..., 
        description="Tracking error FWHM in arcseconds. (ATBD: FWHM_Trk)"
    )

class SkyAnnulus(StrictModel):
    """How the sky under the target is estimated, and so how noisy that estimate is."""
    inner_factor: PositiveFloat = Field(
        ...,
        description="Annulus inner radius as a multiple of FWHM_tot. (ATBD: k_in)"
    )
    outer_factor: PositiveFloat = Field(
        ...,
        description="Annulus outer radius as a multiple of FWHM_tot. (ATBD: k_out)"
    )
    estimator: Literal["median", "mean"] = Field(
        "median",
        description="How the annulus is reduced to one sky value. A median costs pi/2 more variance than a mean, and is what most pipelines use."
    )

    @model_validator(mode="after")
    def _outer_encloses_inner(self):
        if self.outer_factor <= self.inner_factor:
            raise ValueError("outer_factor must exceed inner_factor; the annulus has no area otherwise")
        return self

class BaseOptions(StrictModel):
    aperture_factor: PositiveFloat = Field(
        ..., # Deliberately no default value; the frontend must always supply it explicitly (both shipped clients send 0.85 — see ATBD 5.2)
        description="Multiplier defining the photometric aperture radius. (ATBD: k_ap)"
    )
    single_exp_time: PositiveFloat = Field(
        ..., 
        description="Integration time for an individual sub-exposure frame in seconds. (ATBD: t_single)"
    )
    # Optional, unlike aperture_factor, because omitting it has a defined meaning:
    # a sky known exactly, which is what every CASTOR release before this one
    # assumed. Both shipped clients now send an annulus. The diagnostics report
    # N_est either way, so a caller who leaves it out can see that they did.
    sky_annulus: SkyAnnulus | None = Field(
        None,
        description="Annulus the sky is estimated in. Omit to assume the sky is known exactly, which no real reduction achieves."
    )

class SolveForSNR(BaseOptions):
    type: Literal["solve_snr"] = "solve_snr"
    num_exposures: PositiveInt = Field(
        ..., 
        description="Total number of exposure frames. (ATBD: N_exp)"
    )

class SolveForTime(BaseOptions):
    type: Literal["solve_time"] = "solve_time"
    target_snr: PositiveFloat = Field(
        ..., 
        description="Goal Signal-to-Noise Ratio to solve for time or exposures. (ATBD: SNR_target)"
    )

CalculationOptions = Annotated[
    Union[SolveForSNR, SolveForTime], 
    Field(
        discriminator="type", 
        description="User-configurable settings that dictate the desired constraints and computation modes. (ATBD 3.4)"
    )
]

class ObservationRequest(StrictModel):
    instrument: InstrumentProfile = Field(
        ..., 
        description="Hardware configuration including telescope, camera, and filter specifications. (Ref: ATBD Section 3.1)"
    )
    target: TargetProfile = Field(
        ..., 
        description="Observation target definition, decoupled into spatial coordinates, morphology, SED, and brightness. (Ref: ATBD Section 3.2)"
    )
    environment: EnvironmentCondition = Field(
        ..., 
        description="Environmental parameters including observer location, time, atmospheric conditions, and seeing FWHM. (Ref: ATBD Section 3.3)"
    )
    options: CalculationOptions = Field(
        ..., 
        description="Mutually exclusive calculation strategies (e.g., solve for SNR given exposures, or solve for time given target SNR). (Ref: ATBD Section 3.4)"
    )

class CoreResult(StrictModel):
    total_snr: float = Field(
        ..., 
        description="Total Signal-to-Noise Ratio aggregated across all exposures. (ATBD: SNR_total) [dimensionless]"
    )
    single_snr: float = Field(
        ..., 
        description="Signal-to-Noise Ratio for a single exposure frame. (ATBD: SNR_single) [dimensionless]"
    )
    required_exposures: int | None = Field(
        None, 
        description="Required number of exposures to achieve the target SNR. (ATBD: N_exp_out). Available only in 'solve_time' mode."
    )
    saturation_time_limit: float = Field(
        ..., 
        description="Time limit before a single pixel reaches its Full Well Capacity. (ATBD: t_sat) [s]"
    )
    optimal_exposure_time: float = Field(
        ...,
        description=(
            "Background-limited single exposure time in seconds — the point at which sky + dark "
            "current shot noise overtakes readout noise. (ATBD: t_opt) [s]"
        )
    )
    total_exp_time: float = Field(
        ...,
        description=(
            "Integration time across all exposures, t_single × N_exp: num_exposures in 'solve_snr' "
            "mode, required_exposures in 'solve_time'. Integration only — readout overhead is not "
            "modelled (validation/QUESTIONS.md 11). (ATBD: t_total) [s]"
        )
    )

class SignalNoiseBudget(StrictModel):
    source_count_rate: float = Field(
        ..., 
        description="Total detected photoelectron count rate from the target within the aperture. (ATBD: Rate_src) [e-/s]"
    )
    sky_count_rate: float = Field(
        ..., 
        description="Photoelectron count rate generated by the sky background per pixel. (ATBD: Rate_sky) [e-/s/pix]"
    )
    peak_pixel_rate: float = Field(
        ..., 
        description="Peak photoelectron count rate hitting the central pixel. (ATBD: Rate_peak) [e-/s/pix]"
    )

class PhysicalDiagnostics(StrictModel):
    total_fwhm: float = Field(
        ..., 
        description="Total spatial spreading incorporating seeing, diffraction, optical, and tracking errors. (ATBD: FWHM_tot) [arcsec]"
    )
    effective_area: float = Field(
        ..., 
        description="Effective collecting area of the telescope, accounting for central obscuration. (ATBD: A_eff) [m²]"
    )
    pixel_scale: float = Field(
        ..., 
        description="Spatial resolution per pixel. (ATBD: S_pix) [arcsec/pix]"
    )
    total_throughput: float = Field(
        ..., 
        description="Combined efficiency of optics, filter, and detector. (ATBD: T_sys) [dimensionless]"
    )
    enclosed_flux_fraction: float = Field(
        ..., 
        description="Fraction of target flux enclosed within the photometric aperture. (ATBD: f_enc) [dimensionless]"
    )
    num_pixels_aperture: float = Field(
        ..., 
        description="Number of pixels enclosed within the photometric aperture. (ATBD: N_pix) [count]"
    )
    num_pixels_sky_estimate: float = Field(
        ..., 
        description="Pixel-equivalent noise cost of estimating the sky in the annulus; zero when no annulus was given. (ATBD: N_est) [count]"
    )
    airmass: float = Field(
        ...,
        description=(
            "Airmass the target's extinction was computed at: sec(z), with the zenith angle clamped "
            "to at most 89° to keep it finite. A target below the horizon therefore reads as about "
            "57, not as an error — ephemeris.target_elevation_deg is the unclamped check. "
            "(ATBD: X) [dimensionless]"
        )
    )
    sky_surface_brightness: float = Field(
        ...,
        description=(
            "Total sky surface brightness the sky count rate was computed from: mu_dark, completed "
            "by its zodiacal term when zodiacal_share is set, plus the moon when "
            "auto_calc_background is True. Converted to flux as an AB magnitude, although the "
            "lunar term is Krisciunas & Schaefer's Johnson V. (ATBD: mu_sky) [mag/arcsec²]"
        )
    )

class NoiseComponents(StrictModel):
    """The signal behind one SNR and every variance term that divides it, each summed over the aperture."""
    exp_time: PositiveFloat = Field(
        ...,
        description="Integration time these terms accumulated over: t_single in `single`, t_total in `total`. [s]"
    )
    num_exposures: PositiveInt = Field(
        ...,
        description="Frames the per-frame terms (dark current, read noise) were charged for: 1 in `single`, N_exp in `total`. (ATBD: N_exp) [count]"
    )
    signal: float = Field(
        ...,
        description="Source electrons in the aperture, Rate_src · t. [e-]"
    )
    source_variance: float = Field(
        ...,
        description="Poisson variance of the source, Rate_src · t. [e-²]"
    )
    sky_variance: float = Field(
        ...,
        description="Sky shot noise over the background pixels, N_bkg · Rate_sky · t. [e-²]"
    )
    dark_variance: float = Field(
        ...,
        description="Dark-current shot noise, N_exp · N_bkg · R_dark · t_single. [e-²]"
    )
    readout_variance: float = Field(
        ...,
        description="Read noise, N_exp · N_bkg · RON². [e-²]"
    )
    flatness_variance: float = Field(
        ...,
        description="Correlated flat-field/background residual; zero unless background_flatness_fraction is set. (ATBD: V_flat) [e-²]"
    )
    total_variance: float = Field(
        ...,
        description=(
            "The variance the SNR divides by: signal / sqrt(total_variance) is the SNR exactly. Equal "
            "to the sum of the five terms above to rounding, not bit for bit. [e-²]"
        )
    )
    num_pixels_background: float = Field(
        ...,
        description="Pixel count the per-pixel terms were multiplied by, N_pix + N_est. (ATBD: N_bkg) [count]"
    )

class NoiseBudget(StrictModel):
    single: NoiseComponents = Field(
        ...,
        description="One frame of t_single. Its signal / sqrt(total_variance) is core.single_snr."
    )
    total: NoiseComponents = Field(
        ...,
        description="The whole stack. Its signal / sqrt(total_variance) is core.total_snr."
    )

class ObservationEphemeris(StrictModel):
    """Where the target and the moon were, as the calculation saw them.

    Reported whether or not auto_calc_background layered the moon onto the sky:
    the geometry is computed either way.
    """
    target_elevation_deg: float = Field(
        ...,
        description=(
            "Target's altitude above the horizon, in degrees. Negative when the target is below the "
            "horizon: not clamped, unlike the zenith angle behind diagnostics.airmass."
        )
    )
    moon_elevation_deg: float = Field(
        ..., description="Moon's altitude above the horizon, in degrees."
    )
    moon_phase_angle_deg: float = Field(
        ...,
        description="Lunar phase angle, 0 at full moon and 180 at new moon. (Krisciunas & Schaefer 1991: alpha) [deg]"
    )
    moon_separation_deg: float = Field(
        ...,
        description="Angular distance between the target and the moon. (Krisciunas & Schaefer 1991: rho) [deg]"
    )

class SystemFlags(StrictModel):
    is_saturated: bool = Field(
        ..., 
        description="Boolean flag marked as True if the single exposure time (t_single) exceeds the saturation limit (t_sat)."
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of warning messages for physical boundary violations (e.g., 'Airmass > 2.0: Extinction model may degrade')."
    )

class ObservationResponse(StrictModel):
    core: CoreResult = Field(
        ..., 
        description="Final observational metrics required for telescope planning. (ATBD Stage 4)"
    )
    budget: SignalNoiseBudget = Field(
        ..., 
        description="Intermediate photoelectron count rates for source and background. (ATBD Stage 3)"
    )
    diagnostics: PhysicalDiagnostics = Field(
        ..., 
        description="Physical characteristics and optical efficiencies translated from inputs. (ATBD Stage 2)"
    )
    flags: SystemFlags = Field(
        ..., 
        description="System safety flags and boundary warnings."
    )
    # Appended after flags rather than grouped with budget, so that every key a
    # response carried before keeps its place in a dump.
    noise: NoiseBudget = Field(
        ...,
        description="Signal and every variance term behind single_snr and total_snr. (ATBD 4.3.6)"
    )
    ephemeris: ObservationEphemeris = Field(
        ...,
        description="Target and moon geometry at observing_time_utc, as the calculation used it."
    )

class TimeSeriesEnvironment(StrictModel):
    location: ObservatoryLocation = Field(
        ..., 
        description="Observer's geographic location."
    )
    start_time_utc: AwareDatetime = Field(
        ..., 
        description="Observation start timestamp in ISO 8601 UTC format."
    )
    end_time_utc: AwareDatetime = Field(
        ..., 
        description="Observation end timestamp in ISO 8601 UTC format."
    )
    time_step_minutes: PositiveFloat = Field(
        ..., 
        description="Time step interval for discrete expansion in minutes."
    )
    
    mu_dark: float = Field(
        ...,
        description="Intrinsic surface brightness of the moonless night sky in mag/arcsec²."
    )
    zodiacal_share: float | None = Field(
        default=None,
        ge=0,
        lt=1,
        description=(
            "Fraction of the moonless sky that was zodiacal light and scattered starlight in "
            "the original measurement mu_dark was split from, at this site's own reference "
            "sightline. None means not modelled — see EnvironmentCondition.zodiacal_share."
        )
    )
    extinction_coeff: float = Field(
        ...,
        description="Atmospheric attenuation per unit airmass in mag/airmass."
    )

    seeing_fwhm: PositiveFloat = Field(..., description="Atmospheric seeing FWHM in arcseconds.")
    diffraction_fwhm: PositiveFloat = Field(..., description="Diffraction limit FWHM in arcseconds.")
    optical_fwhm: PositiveFloat = Field(..., description="Optical aberrations FWHM in arcseconds.")
    tracking_fwhm: PositiveFloat = Field(..., description="Tracking error FWHM in arcseconds.")

class BatchBaseOptions(StrictModel):
    aperture_factor: PositiveFloat = Field(
        ..., 
        description="Multiplier defining the photometric aperture radius."
    )
    single_exp_time: PositiveFloat = Field(
        ..., 
        description="Integration time for an individual sub-exposure frame in seconds."
    )
    sky_annulus: SkyAnnulus | None = Field(
        None,
        description="Annulus the sky is estimated in. Omit to assume the sky is known exactly."
    )

class BatchSolveForSNR(BatchBaseOptions):
    type: Literal["solve_snr"] = "solve_snr"
    num_exposures: PositiveInt = Field(
        ..., 
        description="Total number of exposure frames."
    )

class BatchSolveForTime(BatchBaseOptions):
    type: Literal["solve_time"] = "solve_time"
    target_snr: PositiveFloat = Field(
        ..., 
        description="Goal Signal-to-Noise Ratio to solve for time."
    )

BatchCalculationOptions = Annotated[
    Union[BatchSolveForSNR, BatchSolveForTime], 
    Field(discriminator="type", description="Batch calculation strategies.")
]

class BatchObservationRequest(StrictModel):
    instrument: InstrumentProfile = Field(..., description="Hardware configuration.")
    target: TargetProfile = Field(..., description="Observation target profile.")
    environment: TimeSeriesEnvironment = Field(..., description="Time-series environmental conditions.")
    options: BatchCalculationOptions = Field(..., description="Batch calculation strategies.")

class BatchCoreResult(StrictModel):
    timestamps_iso: list[str] = Field(..., description="Expanded discrete UTC timestamps.")
    total_snr: list[float] = Field(..., description="Total SNR array across the time series.")
    single_snr: list[float] = Field(..., description="Single exposure SNR array.")
    required_exposures: list[float] | None = Field(
        None,
        description=(
            "Exposures needed to reach the target SNR at each timestamp. Available only in "
            "'solve_time' mode, and the only result array that responds to the calculation "
            "goal — single_snr and saturation_time_limit describe the sky and the detector "
            "and are the same whichever goal is set."
        )
    )
    saturation_time_limit: list[float] = Field(..., description="Saturation time limit array [s].")
    optimal_exposure_time: list[float] = Field(
        ...,
        description=(
            "Background-limited single exposure time at each timestamp; it moves with the sky. "
            "(ATBD: t_opt) [s]"
        )
    )
    total_exp_time: list[float] = Field(
        ...,
        description=(
            "Integration time t_single × N at each timestamp: N is num_exposures in 'solve_snr' mode, "
            "the same at every step, and required_exposures in 'solve_time'. Integration only — "
            "readout overhead is not modelled (validation/QUESTIONS.md 11). (ATBD: t_total) [s]"
        )
    )

class BatchSignalNoiseBudget(StrictModel):
    source_count_rate: list[float] = Field(
        ..., description="Source photoelectron count rate within the aperture at each timestamp. (ATBD: Rate_src) [e-/s]"
    )
    sky_count_rate: list[float] = Field(
        ..., description="Sky photoelectron count rate per pixel at each timestamp. (ATBD: Rate_sky) [e-/s/pix]"
    )
    peak_pixel_rate: list[float] = Field(
        ..., description="Peak photoelectron count rate on the central pixel at each timestamp. (ATBD: Rate_peak) [e-/s/pix]"
    )

class BatchPhysicalDiagnostics(StrictModel):
    """The Stage 2 values that move during a time series.

    Only these two: seeing, tracking, the optics and the aperture are fixed for the
    whole series, so FWHM_tot, A_eff, S_pix, f_enc, N_pix and N_est are each one
    number, the same as a single request's at any of these timestamps.
    """
    airmass: list[float] = Field(
        ...,
        description=(
            "Airmass the target's extinction was computed at, at each timestamp: sec(z) with the "
            "zenith angle clamped to at most 89°. ephemeris.target_elevation_deg is the unclamped "
            "check. (ATBD: X) [dimensionless]"
        )
    )
    sky_surface_brightness: list[float] = Field(
        ...,
        description=(
            "Total sky surface brightness each sky count rate was computed from: mu_dark, completed "
            "by its zodiacal term when zodiacal_share is set, plus the moon, which a time series "
            "always layers on. (ATBD: mu_sky) [mag/arcsec²]"
        )
    )

class BatchNoiseComponents(StrictModel):
    """NoiseComponents at each timestamp; every list is as long as timestamps_iso."""
    exp_time: list[float] = Field(
        ..., description="Integration time the terms accumulated over: t_single in `single`, t_total in `total`. [s]"
    )
    num_exposures: list[float] = Field(
        ...,
        description=(
            "Frames the per-frame terms were charged for: 1 in `single`, N_exp in `total`. A float "
            "list, like required_exposures. (ATBD: N_exp) [count]"
        )
    )
    signal: list[float] = Field(..., description="Source electrons in the aperture, Rate_src · t. [e-]")
    source_variance: list[float] = Field(..., description="Poisson variance of the source, Rate_src · t. [e-²]")
    sky_variance: list[float] = Field(..., description="Sky shot noise over the background pixels, N_bkg · Rate_sky · t. [e-²]")
    dark_variance: list[float] = Field(..., description="Dark-current shot noise, N_exp · N_bkg · R_dark · t_single. [e-²]")
    readout_variance: list[float] = Field(..., description="Read noise, N_exp · N_bkg · RON². [e-²]")
    flatness_variance: list[float] = Field(
        ..., description="Correlated flat-field/background residual; zero unless background_flatness_fraction is set. (ATBD: V_flat) [e-²]"
    )
    total_variance: list[float] = Field(
        ..., description="The variance each SNR divides by: signal / sqrt(total_variance) is that SNR exactly. [e-²]"
    )
    num_pixels_background: list[float] = Field(
        ..., description="Pixel count the per-pixel terms were multiplied by, N_pix + N_est; the same at every step. (ATBD: N_bkg) [count]"
    )

class BatchNoiseBudget(StrictModel):
    single: BatchNoiseComponents = Field(
        ..., description="One frame of t_single at each timestamp. Its signal / sqrt(total_variance) is core.single_snr."
    )
    total: BatchNoiseComponents = Field(
        ..., description="The whole stack at each timestamp. Its signal / sqrt(total_variance) is core.total_snr."
    )

class BatchEphemeris(StrictModel):
    target_elevation_deg: list[float] = Field(
        ...,
        description=(
            "Target's altitude above the horizon at each timestamp, in degrees. Can go negative "
            "when the target is below the horizon (unlike the airmass calculation internally used "
            "for the SNR pipeline, this is not clamped to a minimum elevation)."
        )
    )
    moon_elevation_deg: list[float] = Field(
        ..., description="Moon's altitude above the horizon at each timestamp, in degrees."
    )
    sun_elevation_deg: list[float] = Field(
        ...,
        description=(
            "Sun's altitude above the horizon at each timestamp, in degrees. Purely for the "
            "visibility plot — nothing in the SNR pipeline reads it. Above 0 is daylight; "
            "0 to -18 is twilight; below -18 is astronomical night."
        )
    )
    moon_phase_angle_deg: list[float] = Field(
        ...,
        description="Lunar phase angle at each timestamp, 0 at full moon and 180 at new moon. (Krisciunas & Schaefer 1991: alpha) [deg]"
    )
    moon_separation_deg: list[float] = Field(
        ...,
        description="Angular distance between the target and the moon at each timestamp. (Krisciunas & Schaefer 1991: rho) [deg]"
    )

class BatchObservationResponse(StrictModel):
    core: BatchCoreResult = Field(..., description="Vectorized calculation results over time.")
    ephemeris: BatchEphemeris = Field(..., description="Target/moon geometry over the time series, for visibility plots.")
    flags: SystemFlags = Field(..., description="System safety flags and boundary warnings.")
    # Appended, as in ObservationResponse, so existing keys keep their place.
    budget: BatchSignalNoiseBudget = Field(
        ..., description="Photoelectron count rates at each timestamp. (ATBD Stage 3)"
    )
    diagnostics: BatchPhysicalDiagnostics = Field(
        ..., description="The airmass and sky each timestamp was computed with. (ATBD Stage 2)"
    )
    noise: BatchNoiseBudget = Field(
        ..., description="Signal and every variance term behind single_snr and total_snr at each timestamp. (ATBD 4.3.6)"
    )