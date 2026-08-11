import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

# 假設你的 schema 存在 schema.py 中
from castor.schema import (
    TargetProfile,
    EnvironmentCondition,
    ObservationRequest,
    ABMagnitude,
    VegaMagnitude,
    SolveForSNR,
    SolveForTime
)

# ==========================================
# Fixtures: 準備合法的基礎測資，避免重複造輪子
# ==========================================
@pytest.fixture
def valid_target_payload():
    return {
        "ra": 180.5,
        "dec": -45.0,
        "morphology": {"type": "point"},  # <--- 從 "point" 改成 {"type": "point"}
        "sed": {"type": "flat"},          # <--- 從 "flat" 改成 {"type": "flat"}
        "brightness": {
            "type": "vega_mag",
            "target_mag": 15.0,
            "zero_point_flux": 3.44e-9
        }
    }

@pytest.fixture
def valid_environment_payload():
    return {
        "location": {
            "latitude_deg": 23.5,
            "longitude_deg": 120.0,
            "elevation_m": 2862.0  # 鹿林天文台高度
        },
        "observing_time_utc": "2026-07-22T12:00:00Z",
        "auto_calc_background": False,
        "mu_dark": 21.5,
        "extinction_coeff": 0.15,
        "seeing_fwhm": 1.2,
        "diffraction_fwhm": 0.5,
        "optical_fwhm": 0.3,
        "tracking_fwhm": 0.2
    }


# ==========================================
# 測試重點 1: 物理與數學邊界的絕對防護
# ==========================================
class TestPhysicalBoundaries:
    def test_ra_dec_out_of_bounds_rejected(self, valid_target_payload):
        """測試天球座標是否被嚴格限制在物理範圍內"""
        payload = valid_target_payload.copy()
        
        # RA 不可等於或超過 360
        payload["ra"] = 360.0 
        with pytest.raises(ValidationError, match="Input should be less than 360"):
            TargetProfile(**payload)

        # DEC 不可超過 90
        payload["ra"] = 180.0
        payload["dec"] = 90.1
        with pytest.raises(ValidationError, match="Input should be less than or equal to 90"):
            TargetProfile(**payload)

    def test_earth_location_out_of_bounds_rejected(self, valid_environment_payload):
        """測試地球經緯度與海拔高度的防呆機制"""
        payload = valid_environment_payload.copy()
        
        # 緯度防呆
        payload["location"]["latitude_deg"] = -95.0
        with pytest.raises(ValidationError):
            EnvironmentCondition(**payload)

        # 經度防呆
        payload["location"]["latitude_deg"] = 23.5
        payload["location"]["longitude_deg"] = 181.0
        with pytest.raises(ValidationError):
            EnvironmentCondition(**payload)

    def test_naive_datetime_rejected(self, valid_environment_payload):
        """測試是否成功擋下沒有時區資訊的危險時間格式"""
        payload = valid_environment_payload.copy()
        payload["observing_time_utc"] = "2026-07-22T12:00:00"  # 缺少 Z 或 +08:00
        
        with pytest.raises(ValidationError, match="Input should have timezone info"):
            EnvironmentCondition(**payload)


# ==========================================
# 測試重點 2: 多型路由與契約正確性
# ==========================================
class TestPolymorphicRouting:
    def test_brightness_routing(self, valid_target_payload):
        """測試系統是否能根據 type 標籤，正確綁定對應的亮度模型與必填欄位"""
        
        # 1. 測試 AB 星等 (不需要 zero_point_flux)
        ab_payload = valid_target_payload.copy()
        ab_payload["brightness"] = {
            "type": "ab_mag",
            "target_mag": 15.0
        }
        target = TargetProfile(**ab_payload)
        assert isinstance(target.brightness, ABMagnitude)

        # 2. 測試 Vega 星等若缺少 zero_point_flux 必須報錯
        vega_payload = valid_target_payload.copy()
        vega_payload["brightness"] = {
            "type": "vega_mag",
            "target_mag": 15.0
            # 刻意遺漏 zero_point_flux
        }
        with pytest.raises(ValidationError, match="Field required"):
            TargetProfile(**vega_payload)

    def test_calculation_options_mutual_exclusion(self):
        """測試運算策略是否真的互斥，無法將兩個模式的參數混搭"""
        from castor.schema import CalculationOptions
        from pydantic import TypeAdapter
        
        adapter = TypeAdapter(CalculationOptions)
        
        # 混搭錯誤測試：宣告要求解 SNR，卻不給張數而給了 target_snr
        invalid_options = {
            "type": "solve_snr",
            "aperture_factor": 1.5,
            "single_exp_time": 60.0,
            "target_snr": 100.0  # 這是 solve_time 才有的欄位
        }
        
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            adapter.validate_python(invalid_options)


# ==========================================
# 測試重點 3: Strict 模式的封殺能力
# ==========================================
class TestStrictModelDefenses:
    def test_forbid_extra_garbage_fields(self, valid_target_payload):
        """確保打字錯誤或未知的垃圾參數會被直接擋在門外，不會被默默吃掉"""
        payload = valid_target_payload.copy()
        payload["ra"] = 180.0
        payload["dec"] = 45.0
        
        # 刻意塞入一個未定義的欄位
        payload["what_is_this_field"] = "some_garbage_data"
        
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            TargetProfile(**payload)