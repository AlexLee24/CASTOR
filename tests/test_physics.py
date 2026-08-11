import pytest
import numpy as np
import numpy.testing as npt

# 假設你的模組路徑是 castor.physics
from castor.physics import (
    calculate_airmass,
    calculate_effective_area,
    convert_ab_to_wavelength_flux,
    calculate_point_source_rate,
    calculate_extended_source_rate,
    calculate_sky_background_rate,
    calculate_single_snr,
    calculate_total_snr,
    solve_required_exposures,
    calculate_optimal_exposure_time
)

# ==========================================
# Global Core Properties (向量化與極限測試)
# ==========================================

def test_vectorization_support():
    """確保核心函式能完美支援 NumPy 陣列，不拋出 TypeError。"""
    zenith_angles = np.array([0.0, 60.0])
    expected_airmass = np.array([1.0, 2.0])
    
    result = calculate_airmass(zenith_angles)
    
    assert isinstance(result, np.ndarray)
    npt.assert_allclose(result, expected_airmass, rtol=1e-5)

# ==========================================
# Stage 2: Physical & Environmental 
# ==========================================

def test_calculate_airmass():
    """基準與極限測試：0 度為 1.0，60 度為 2.0"""
    assert calculate_airmass(0.0) == pytest.approx(1.0)
    assert calculate_airmass(60.0) == pytest.approx(2.0, rel=1e-5)

def test_calculate_effective_area():
    """測試有/無副鏡遮蔽時的面積計算"""
    # 只有主鏡 (2m)，沒有副鏡遮蔽
    area_no_obs = calculate_effective_area(2.0, 0.0)
    expected_no_obs = np.pi * (1.0 ** 2)  # pi * r^2, r=1
    assert area_no_obs == pytest.approx(expected_no_obs)
    
    # 加上 1m 的副鏡遮蔽
    area_obs = calculate_effective_area(2.0, 1.0)
    expected_obs = (np.pi / 4.0) * (2.0**2 - 1.0**2)
    assert area_obs == pytest.approx(expected_obs)

def test_convert_ab_to_wavelength_flux():
    """測試 AB 星等為 0 時的通量轉換是否符合 3631 Jy 的基準"""
    mag_ab = 0.0
    wavelength_nm = 500.0  # 500 nm = 5000 Å
    
    result_f_lambda = convert_ab_to_wavelength_flux(mag_ab, wavelength_nm)
    
    # 理論手算值：
    # F_nu = 3631 Jy = 3631 * 1e-23 erg/s/cm²/Hz = 3.631e-20
    # lambda = 5000 Å
    # c = 2.99792458e18 Å/s
    # F_lambda = F_nu * (c / lambda^2) = 3.631e-20 * (2.99792458e18 / 25000000)
    expected_f_lambda = 3.631e-20 * (2.99792458e18 / (5000.0 ** 2))
    
    assert result_f_lambda == pytest.approx(expected_f_lambda, rel=1e-5)

# ==========================================
# Stage 3: Photoelectron Count Rates
# ==========================================

@pytest.fixture
def dummy_stage3_params():
    """提供一組標準的 Stage 3 假參數供測試使用"""
    return {
        "f_lambda": 1e-15,
        "extinction_coeff": 0.2,
        "airmass": 1.5,
        "filter_bandwidth": 100.0,
        "effective_area": 3.14,
        "photon_energy": 4e-12,
        "total_throughput": 0.6
    }

def test_extinction_null_effect(dummy_stage3_params):
    """大氣消光防呆：消光係數為 0 時，抵達通量不衰減"""
    params = dummy_stage3_params.copy()

    base_flux = params.pop("f_lambda")
    
    # 有大氣消光
    rate_with_ext = calculate_point_source_rate(
        **params, f_lambda_total=base_flux, enclosed_flux_fraction=0.8
    )
    
    # 無大氣消光 (k_ext = 0)
    params["extinction_coeff"] = 0.0
    rate_no_ext = calculate_point_source_rate(
        **params, f_lambda_total=base_flux, enclosed_flux_fraction=0.8
    )
    
    # 沒有消光時算出的計數率必須嚴格大於有消光時
    assert rate_no_ext > rate_with_ext

def test_geometric_divergence(dummy_stage3_params):
    """幾何分流驗證：確保不同來源僅因為幾何常數（面積、比例）而有倍數差異"""
    params = dummy_stage3_params.copy()
    
    # 把通用的 f_lambda 拿出來，避免 kwargs 報錯
    base_flux = params.pop("f_lambda") 
    
    # 1. 點源 (f_enc = 0.5)
    rate_point = calculate_point_source_rate(
        **params, 
        f_lambda_total=base_flux, 
        enclosed_flux_fraction=0.5
    )
    
    # 2. 天光背景 (單一像素，S_pixel = 2.0，面積為 4)
    rate_sky = calculate_sky_background_rate(
        **params, 
        f_lambda_sky=base_flux, 
        pixel_scale=2.0
    )
    
    # 3. 延伸源 (N_pix = 10, S_pixel = 2.0，總面積為 40)
    rate_ext = calculate_extended_source_rate(
        **params, 
        f_lambda_surface=base_flux, 
        num_pixels_aperture=10.0, 
        pixel_scale=2.0
    )
    
    # 斷言它們之間的純幾何倍率關係
    assert rate_sky == pytest.approx(rate_point * 8.0)
    assert rate_ext == pytest.approx(rate_sky * 10.0)

# ==========================================
# Stage 4: Final Output Metrics
# ==========================================

@pytest.fixture
def dummy_stage4_params():
    """提供一組標準的 Stage 4 假參數供測試使用"""
    return {
        "source_count_rate": 100.0,
        "sky_count_rate": 10.0,
        "dark_current_rate": 0.1,
        "readout_noise": 5.0,
        "num_pixels_aperture": 4.0
    }

def test_zero_exposure(dummy_stage4_params):
    """曝光時間歸零：沒有曝光時間就沒有 SNR"""
    snr = calculate_single_snr(**dummy_stage4_params, single_exp_time=0.0)
    assert snr == 0.0

def test_readout_noise_scaling(dummy_stage4_params):
    """多重曝光噪聲累積：總時間相同，分多次拍的 SNR 必須較低（因為讀取雜訊累積）"""
    params = dummy_stage4_params.copy()
    
    # 情況 A：單次曝光 100 秒 (1 張)
    snr_single_shot = calculate_total_snr(
        **params, single_exp_time=100.0, total_exp_time=100.0, num_exposures=1
    )
    
    # 情況 B：單次曝光 10 秒，拍 10 張 (總時間一樣是 100 秒)
    snr_multi_shot = calculate_total_snr(
        **params, single_exp_time=10.0, total_exp_time=100.0, num_exposures=10
    )
    
    assert snr_single_shot > snr_multi_shot

def test_snr_reversibility():
    """完美可逆性：反推所需的曝光張數必須精準"""
    target_snr = 20.0
    single_snr = 10.0

    required_exposures = solve_required_exposures(target_snr, single_snr)

    # (20 / 10)^2 = 4.0
    assert required_exposures == pytest.approx(4.0)

def test_optimal_exposure_time_crossover_point():
    """臨界點定義：background_dominance_factor=1.0 時，算出的 t_opt 代入
    背景 shot noise 公式 sqrt(background_rate * t_opt)，必須剛好等於 RON。"""
    sky_rate, dark_rate, readout_noise = 2.0, 0.5, 5.0

    t_opt = calculate_optimal_exposure_time(sky_rate, dark_rate, readout_noise)

    background_shot_noise = np.sqrt((sky_rate + dark_rate) * t_opt)
    assert background_shot_noise == pytest.approx(readout_noise)

def test_optimal_exposure_time_scales_with_dominance_factor_squared():
    """k 值是站在標準差比例上定義的，換算到時間（變異數）上要呈平方關係：
    k 加倍，t_opt 要變成 4 倍。"""
    sky_rate, dark_rate, readout_noise = 2.0, 0.5, 5.0

    t_k1 = calculate_optimal_exposure_time(sky_rate, dark_rate, readout_noise, background_dominance_factor=1.0)
    t_k2 = calculate_optimal_exposure_time(sky_rate, dark_rate, readout_noise, background_dominance_factor=2.0)

    assert t_k2 == pytest.approx(t_k1 * 4.0)