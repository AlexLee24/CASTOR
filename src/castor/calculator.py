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
    將所有不同型態的輸入亮度，統一轉換為 Top-of-Atmosphere (TOA) 的 F_lambda (erg/s/cm²/Å)。
    完美展現 match/case 對於解構 (Destructuring) 的強大能力。
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
    CASTOR 核心計算管線。
    遵循 f(input) = output 的純函數原則，無狀態、高併發安全。
    """
    # 提取 Domain Pillars 縮寫以保持程式碼簡潔
    inst = request.instrument
    tgt = request.target
    env = request.environment
    opt = request.options

    # ---------------------------------------------------------
    # Phase 1: Context Enrichment (環境豐富化與天文幾何)
    # ---------------------------------------------------------
    # 1.1 動態天體座標與月光影響
    alpha, rho, z_moon, z_target = moon.get_moon_and_target_geometry(
        target_ra=tgt.ra,
        target_dec=tgt.dec,
        obs_time_utc=env.observing_time_utc.strftime('%Y-%m-%dT%H:%M:%S'),
        lon=env.location.longitude_deg,
        lat=env.location.latitude_deg,
        elevation=env.location.elevation_m
    )
    
    # 限制天頂角避免 Airmass 趨於無限大
    z_target_safe = min(float(z_target), 89.0)
    airmass = float(physics.calculate_airmass(z_target_safe))
    
    # auto_calc_background 只決定要不要在 mu_dark 之上疊加即時月光/幾何貢獻，
    # 兩種模式下 mu_dark 都是必要的基礎值，不會被自動推導出來。
    if env.auto_calc_background:
        mu_sky = moon.calculate_sky_brightness(
            target_ra=tgt.ra, target_dec=tgt.dec,
            obs_time_utc=env.observing_time_utc.strftime('%Y-%m-%dT%H:%M:%S'),
            mu_dark=env.mu_dark,
            extinction_coeff=env.extinction_coeff,
            lon=env.location.longitude_deg, lat=env.location.latitude_deg,
            elevation=env.location.elevation_m
        )
    else:
        mu_sky = env.mu_dark

    # 1.2 光學與硬體物理量前置計算
    eff_area = float(physics.calculate_effective_area(
        inst.telescope.primary_mirror_diameter, 
        inst.telescope.secondary_mirror_diameter
    ))
    photon_energy = float(physics.calculate_photon_energy(inst.optic_filter.central_wavelength))
    # throughput_correction 是無法拆解到 optical_throughput / filter_transmission /
    # quantum_efficiency 個別項目時的總體校正乘數，套用在三者的乘積之上。
    total_throughput = float(physics.calculate_total_throughput(
        inst.telescope.optical_throughput,
        inst.optic_filter.filter_transmission,
        inst.camera.quantum_efficiency
    )) * inst.throughput_correction
    pixel_scale = float(physics.calculate_pixel_scale(inst.camera.pixel_pitch, inst.telescope.focal_length))
    total_fwhm = float(physics.calculate_total_fwhm(
        env.seeing_fwhm, env.diffraction_fwhm, env.optical_fwhm, env.tracking_fwhm
    ))
    
    # 1.3 測光幾何與涵蓋範圍
    n_pix, f_enc = physics.calculate_aperture_geometry(opt.aperture_factor, total_fwhm, pixel_scale)
    n_pix, f_enc = float(n_pix), float(f_enc)

    # ---------------------------------------------------------
    # Phase 2: Flux Unification & Count Rates (通量正規化與光電子計數)
    # ---------------------------------------------------------
    # 目標通量統一化
    f_lambda_target = _unify_flux(tgt.brightness, inst.optic_filter.central_wavelength)
    
    # 天光通量轉換 (預設 mu_sky 屬於 AB 星等系統)
    f_lambda_sky = float(physics.convert_ab_to_wavelength_flux(mu_sky, inst.optic_filter.central_wavelength))

    # 計算天光計數率
    sky_rate = float(physics.calculate_sky_background_rate(
        f_lambda_sky, env.extinction_coeff, airmass, 
        inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, pixel_scale
    ))

    # 根據目標形狀 (Morphology) 進行分流計算
    match tgt.morphology:
        case schema.PointMorphology():
            source_rate = float(physics.calculate_point_source_rate(
                f_lambda_target, env.extinction_coeff, airmass,
                inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, f_enc
            ))
        case schema.ExtendedMorphology():
            source_rate = float(physics.calculate_extended_source_rate(
                f_lambda_target, env.extinction_coeff, airmass,
                inst.optic_filter.filter_bandwidth, eff_area, photon_energy, total_throughput, n_pix, pixel_scale
            ))
        case _:
            raise ValueError("Unknown target morphology")

    peak_rate = float(physics.calculate_peak_pixel_rate(source_rate, total_fwhm, pixel_scale))

    # ---------------------------------------------------------
    # Phase 3 & 4: Strategy Execution & Assembly (策略解算與回傳包裝)
    # ---------------------------------------------------------
    single_snr = float(physics.calculate_single_snr(
        source_count_rate=source_rate,
        sky_count_rate=sky_rate,
        dark_current_rate=inst.camera.dark_current_rate,
        readout_noise=inst.camera.readout_noise,
        num_pixels_aperture=n_pix,
        single_exp_time=opt.single_exp_time
    ))

    # 根據使用者的模式 (Options) 進行反推或正推
    match opt:
        case schema.SolveForSNR(num_exposures=n_exp):
            total_exp_time = opt.single_exp_time * n_exp
            total_snr = float(physics.calculate_total_snr(
                source_rate, sky_rate, inst.camera.dark_current_rate, inst.camera.readout_noise,
                n_pix, opt.single_exp_time, total_exp_time, n_exp
            ))
            final_req_exposures = None # SolveForSNR 模式下不需要回傳 req_exposures

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

    # 計算飽和極限與危險旗標
    t_sat = float(physics.calculate_saturation_time(
        inst.camera.full_well_capacity, peak_rate, sky_rate, inst.camera.dark_current_rate
    ))

    # background_dominance_factor 沿用預設值 1.0；細節見 calculate_optimal_exposure_time 的 docstring。
    t_opt = float(physics.calculate_optimal_exposure_time(
        sky_rate, inst.camera.dark_current_rate, inst.camera.readout_noise
    ))

    warnings = []
    if airmass > 2.0:
        warnings.append("Airmass > 2.0: Extinction model accuracy may degrade.")

    # 組裝 Pydantic Response 完美合約
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