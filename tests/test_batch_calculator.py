import pytest
import numpy as np
from datetime import datetime, timezone

from castor import schema
from castor.batch_calculator import run_batch_calculation, _expand_time_series

# ==========================================
# Fixtures: 準備測試用的批次假資料與攔截器
# ==========================================

@pytest.fixture
def mock_moon_batch(monkeypatch):
    """
    攔截 Astropy 的曆書運算，專為批次處理設計！
    會根據傳入的時間序列長度 (N)，動態回傳長度為 N 的 Numpy 陣列。
    """
    def mock_geometry(*args, **kwargs):
        # 抓取傳入的時間序列 (可能是 positional 的第三個，或是 keyword)
        times = kwargs.get("obs_time_utc") if "obs_time_utc" in kwargs else args[2]
        n = len(times) # type: ignore
        
        # 模擬天頂角隨時間變化的情況 (例如從 30 度慢慢降到 60 度)
        alpha = np.zeros(n)
        rho = np.full(n, 90.0)
        z_moon = np.full(n, 45.0)
        z_target = np.linspace(30.0, 60.0, n) 
        return alpha, rho, z_moon, z_target
        
    def mock_sky_brightness(*args, **kwargs):
        times = kwargs.get("obs_time_utc") if "obs_time_utc" in kwargs else args[2]
        return np.full(len(times), 21.0) # 固定回傳 21.0 星等的天光陣列 # type: ignore

    monkeypatch.setattr("castor.moon.get_moon_and_target_geometry", mock_geometry)
    monkeypatch.setattr("castor.moon.calculate_sky_brightness", mock_sky_brightness)

@pytest.fixture
def batch_base_request():
    """建立一個標準的批次觀測請求 (Time-Series)"""
    return schema.BatchObservationRequest(
        instrument=schema.InstrumentProfile(
            telescope=schema.TelescopeSchema(
                primary_mirror_diameter=1.0, secondary_mirror_diameter=0.3, 
                focal_length=8.0, optical_throughput=0.8
            ),
            camera=schema.CameraSchema(
                pixel_pitch=13.5, quantum_efficiency=0.9, dark_current_rate=0.01, 
                readout_noise=3.0, full_well_capacity=100000.0
            ),
            optic_filter=schema.FilterSchema(
                central_wavelength=550.0, filter_bandwidth=100.0, filter_transmission=0.95
            ),
            throughput_correction=1.0
        ),
        target=schema.TargetProfile(
            morphology=schema.PointMorphology(),
            brightness=schema.VegaMagnitude(target_mag=15.0, zero_point_flux=3.6e-9),
            sed=schema.FlatSED(),
            ra=180.0, dec=0.0
        ),
        environment=schema.TimeSeriesEnvironment(
            location=schema.ObservatoryLocation(latitude_deg=23.47, longitude_deg=120.87, elevation_m=2862.0),
            start_time_utc=datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc),
            end_time_utc=datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc), # 觀測兩小時
            time_step_minutes=10.0, # 每 10 分鐘算一次
            mu_dark=21.5,
            extinction_coeff=0.17,
            # 記取上次的教訓，這裡給 0.1 滿足 PositiveFloat
            seeing_fwhm=1.5, diffraction_fwhm=0.1, optical_fwhm=0.1, tracking_fwhm=0.1 
        ),
        options=schema.BatchSolveForTime(
            aperture_factor=1.5, single_exp_time=300.0, target_snr=100.0
        )
    )

# ==========================================
# 測試案例
# ==========================================

def test_expand_time_series():
    """確保時間展開輔助函數運作正常，且有極限防護"""
    start = datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 19, 0, tzinfo=timezone.utc)
    
    # 測試 1: 正常展開 (一小時，每 10 分鐘一次，共 7 個點)
    times = _expand_time_series(start, end, 10.0)
    assert len(times) == 7
    assert times[0] == "2026-01-01T18:00:00+00:00"
    
    # 測試 2: 極限防護 (測試 max_points = 1000 限制)
    end_far = datetime(2026, 2, 1, 18, 0, tzinfo=timezone.utc) # 一個月後
    times_far = _expand_time_series(start, end_far, 1.0)
    assert len(times_far) == 1000

def test_batch_pipeline_solve_time(mock_moon_batch, batch_base_request):
    """測試管線：支援時間序列的 SNR 逆推 (SolveForTime)"""
    response = run_batch_calculation(batch_base_request)
    
    # 1. 確保回傳陣列長度正確 (18:00 到 20:00，每 10 分鐘，共 13 個點)
    assert len(response.core.timestamps_iso) == 13
    assert len(response.core.total_snr) == 13
    assert len(response.core.single_snr) == 13
    
    # 2. 確保 Pydantic 轉換無誤 (回傳的必須是 Python native list，不是 numpy array)
    assert isinstance(response.core.total_snr, list)
    assert isinstance(response.core.total_snr[0], float)
    
    # 3. 確保算出來的 SNR 都有達到目標 (100.0)
    for snr in response.core.total_snr:
        assert snr >= 100.0

def test_batch_pipeline_solve_snr(mock_moon_batch, batch_base_request):
    """測試管線：支援時間序列的 SNR 正推 (SolveForSNR)，並切換為延伸源"""
    # 抽換 request 內容
    batch_base_request.target.morphology = schema.ExtendedMorphology()
    batch_base_request.options = schema.BatchSolveForSNR(
        aperture_factor=1.5, single_exp_time=300.0, num_exposures=5
    )
    
    response = run_batch_calculation(batch_base_request)
    
    assert len(response.core.timestamps_iso) == 13
    assert len(response.core.total_snr) == 13
    
    # 因為在 mock 中 z_target 是變動的 (30 -> 60 度)，Airmass 會變大，
    # 導致訊號衰減，所以整晚的 SNR 陣列應該要是遞減的！
    snr_array = response.core.total_snr
    assert snr_array[0] > snr_array[-1] # 第一個點的 SNR 必須大於最後一個點

def test_batch_pipeline_warning_flag(mock_moon_batch, batch_base_request):
    """測試管線：當序列中出現過大的 Airmass 時，是否能正確亮起警告旗標"""
    def mock_high_airmass_geometry(*args, **kwargs):
        times = kwargs.get("obs_time_utc") if "obs_time_utc" in kwargs else args[2]
        n = len(times) # type: ignore
        # 強制讓天頂角達到 70 度 (這會讓 Airmass = sec(70) = 2.92 > 2.0)
        return (np.zeros(n), np.full(n, 90.0), np.full(n, 45.0), np.full(n, 70.0))
        
    # 覆蓋原本的 mock
    pytest.MonkeyPatch().setattr("castor.moon.get_moon_and_target_geometry", mock_high_airmass_geometry)
    
    response = run_batch_calculation(batch_base_request)
    
    # 必須觸發警告
    assert len(response.flags.warnings) > 0
    assert "Airmass > 2.0" in response.flags.warnings[0]