import pytest
from datetime import datetime, timezone

# 假設你的模組路徑是 castor
from castor import schema
from castor.calculator import run_calculation

# ==========================================
# Fixtures: 準備測試用的標準假資料
# ==========================================

@pytest.fixture
def mock_moon(monkeypatch):
    """
    攔截 Astropy 的曆書運算，讓測試環境完全獨立且極速。
    回傳固定的天頂角與月光亮度，確保物理運算不被真實時間干擾。
    """
    def mock_geometry(*args, **kwargs):
        # 回傳: alpha=0(滿月), rho=90, z_moon=45, z_target=30
        return (0.0, 90.0, 45.0, 30.0)
        
    def mock_sky_brightness(*args, **kwargs):
        return 21.0 # 固定回傳 21.0 星等的天光

    monkeypatch.setattr("castor.moon.get_moon_and_target_geometry", mock_geometry)
    monkeypatch.setattr("castor.moon.calculate_sky_brightness", mock_sky_brightness)

@pytest.fixture
def base_request():
    """建立一個標準的鹿林一米望遠鏡 (LOT) 觀測點源假資料"""
    return schema.ObservationRequest(
        instrument=schema.InstrumentProfile(
            telescope=schema.TelescopeSchema(
                primary_mirror_diameter=1.0, 
                secondary_mirror_diameter=0.3, 
                focal_length=8.0, 
                optical_throughput=0.8
            ),
            camera=schema.CameraSchema(
                pixel_pitch=13.5, 
                quantum_efficiency=0.9, 
                dark_current_rate=0.01, 
                readout_noise=3.0, 
                full_well_capacity=100000.0
            ),
            optic_filter=schema.FilterSchema(
                central_wavelength=550.0, # V band 近似
                filter_bandwidth=100.0,
                filter_transmission=0.95
            ),
            throughput_correction=1.0
        ),
        target=schema.TargetProfile(
            morphology=schema.PointMorphology(),
            brightness=schema.VegaMagnitude(target_mag=15.0, zero_point_flux=3.6e-9),
            sed=schema.FlatSED(),
            ra=180.0, 
            dec=0.0
        ),
        environment=schema.EnvironmentCondition(
            location=schema.ObservatoryLocation(
                latitude_deg=23.47, longitude_deg=120.87, elevation_m=2862.0
            ),
            observing_time_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            auto_calc_background=False,
            mu_dark=21.5,
            extinction_coeff=0.17,
            seeing_fwhm=1.5, diffraction_fwhm=0.1, optical_fwhm=0.1, tracking_fwhm=0.1
        ),
        # 預設為模式 B：給定目標 SNR，反推需要拍幾張
        options=schema.SolveForTime(
            aperture_factor=1.5, single_exp_time=300.0, target_snr=100.0
        )
    )

# ==========================================
# 測試案例: 裝配線與路由驗證
# ==========================================

def test_pipeline_point_solve_time(mock_moon, base_request):
    """
    測試管線 A：點源目標 (Point) + 反推曝光時間 (SolveForTime)
    """
    response = run_calculation(base_request)
    
    # 1. 確保回傳的是標準合約物件
    assert isinstance(response, schema.ObservationResponse)
    
    # 2. 確保核心數據不為空 (因為是 SolveForTime 模式，一定有 required_exposures)
    assert response.core.required_exposures is not None
    assert response.core.total_snr >= 100.0 # 達標的 SNR 一定大於等於目標 SNR
    
    # 3. 確保物理屬性有被正確計算
    assert response.budget.source_count_rate > 0
    assert 0.0 < response.diagnostics.enclosed_flux_fraction < 1.0

def test_pipeline_extended_solve_snr(mock_moon, base_request):
    """
    測試管線 B：延伸源目標 (Extended) + 正推訊噪比 (SolveForSNR)
    """
    # 抽換 request 內的零件：把目標改成延伸源 (例如星系表面亮度)
    base_request.target.morphology = schema.ExtendedMorphology()
    # 抽換 request 內的亮度：改為 AB 星等
    base_request.target.brightness = schema.ABMagnitude(target_mag=18.0)
    # 抽換 request 內的選項：改為直接給定 5 張曝光，求算出來的 SNR
    base_request.options = schema.SolveForSNR(
        aperture_factor=1.5, single_exp_time=300.0, num_exposures=5
    )
    
    response = run_calculation(base_request)
    
    # 1. 在 SolveForSNR 模式下，不需要反推曝光次數，所以應該是 None
    assert response.core.required_exposures is None
    
    # 2. 確保算出的 SNR 是一個合法的數字
    assert response.core.total_snr > 0
    
    # 3. 延伸源沒有包絡損失，所以包絡比例在算數上可以照常出，但要確保系統沒當機
    assert response.budget.source_count_rate > 0

def test_pipeline_saturation_warning(mock_moon, base_request):
    """
    測試管線 C：極端亮度導致飽和旗標 (is_saturated) 被正確觸發
    """
    # 把星星調得超級亮 (0 等星)，並用超長的單張曝光時間 (1000秒)
    base_request.target.brightness = schema.VegaMagnitude(target_mag=0.0, zero_point_flux=3.6e-9)
    base_request.options.single_exp_time = 1000.0

    response = run_calculation(base_request)

    # 應該要亮起飽和紅燈
    assert response.flags.is_saturated is True

# ==========================================
# 測試案例: 系統級透過率修正 (throughput_correction)
# ==========================================

def test_throughput_correction_scales_output(mock_moon, base_request):
    """throughput_correction 是乘在 optical/filter/QE 之後的額外修正係數，
    減半應該讓回報的 total_throughput、以及跟訊號成正比的 source_count_rate
    都精準減半。"""
    baseline = run_calculation(base_request)

    base_request.instrument.throughput_correction = 0.5
    halved = run_calculation(base_request)

    assert halved.diagnostics.total_throughput == pytest.approx(
        baseline.diagnostics.total_throughput * 0.5
    )
    assert halved.budget.source_count_rate == pytest.approx(
        baseline.budget.source_count_rate * 0.5
    )

# ==========================================
# 測試案例: 天空背景來源切換 (auto_calc_background)
# ==========================================

def test_auto_calc_background_selects_moon_model(monkeypatch, base_request):
    """auto_calc_background 決定天空亮度的來源：False 時應直接採用 mu_dark，
    完全跳過月光模型查詢；True 時才會呼叫 calculate_sky_brightness。
    mu_dark 本身在兩種模式下都必填，這個開關只決定要不要疊加月光。"""
    sky_brightness_calls = []

    monkeypatch.setattr(
        "castor.moon.get_moon_and_target_geometry",
        lambda *a, **k: (0.0, 90.0, 45.0, 30.0),
    )
    monkeypatch.setattr(
        "castor.moon.calculate_sky_brightness",
        lambda *a, **k: sky_brightness_calls.append(1) or 21.0,
    )

    base_request.environment.auto_calc_background = False
    run_calculation(base_request)
    assert len(sky_brightness_calls) == 0, "關閉時不應該查詢月光模型"

    base_request.environment.auto_calc_background = True
    run_calculation(base_request)
    assert len(sky_brightness_calls) == 1, "開啟時應該查詢一次月光模型"