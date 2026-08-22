import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

# Assumes your schema lives in schema.py
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
# Fixtures: prepare valid baseline test data to avoid reinventing the wheel
# ==========================================
@pytest.fixture
def valid_target_payload():
    return {
        "ra": 180.5,
        "dec": -45.0,
        "morphology": {"type": "point"},  # <--- changed from "point" to {"type": "point"}
        "sed": {"type": "flat"},          # <--- changed from "flat" to {"type": "flat"}
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
            "elevation_m": 2862.0  # Lulin Observatory elevation
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
# Test focus 1: absolute enforcement of physical and mathematical bounds
# ==========================================
class TestPhysicalBoundaries:
    def test_ra_dec_out_of_bounds_rejected(self, valid_target_payload):
        """Tests that celestial coordinates are strictly constrained to their physical range"""
        payload = valid_target_payload.copy()
        
        # RA must not equal or exceed 360
        payload["ra"] = 360.0 
        with pytest.raises(ValidationError, match="Input should be less than 360"):
            TargetProfile(**payload)

        # DEC must not exceed 90
        payload["ra"] = 180.0
        payload["dec"] = 90.1
        with pytest.raises(ValidationError, match="Input should be less than or equal to 90"):
            TargetProfile(**payload)

    def test_earth_location_out_of_bounds_rejected(self, valid_environment_payload):
        """Tests the guard rails on Earth latitude, longitude, and elevation"""
        payload = valid_environment_payload.copy()
        
        # Latitude guard
        payload["location"]["latitude_deg"] = -95.0
        with pytest.raises(ValidationError):
            EnvironmentCondition(**payload)

        # Longitude guard
        payload["location"]["latitude_deg"] = 23.5
        payload["location"]["longitude_deg"] = 181.0
        with pytest.raises(ValidationError):
            EnvironmentCondition(**payload)

    def test_naive_datetime_rejected(self, valid_environment_payload):
        """Tests that a dangerous timezone-naive time format is correctly rejected"""
        payload = valid_environment_payload.copy()
        payload["observing_time_utc"] = "2026-07-22T12:00:00"  # missing Z or +08:00
        
        with pytest.raises(ValidationError, match="Input should have timezone info"):
            EnvironmentCondition(**payload)


# ==========================================
# Test focus 2: polymorphic routing and contract correctness
# ==========================================
class TestPolymorphicRouting:
    def test_brightness_routing(self, valid_target_payload):
        """Tests that the system correctly binds the matching brightness model and
        required fields based on the type tag"""
        
        # 1. Test AB magnitude (doesn't need zero_point_flux)
        ab_payload = valid_target_payload.copy()
        ab_payload["brightness"] = {
            "type": "ab_mag",
            "target_mag": 15.0
        }
        target = TargetProfile(**ab_payload)
        assert isinstance(target.brightness, ABMagnitude)

        # 2. Test that Vega magnitude raises an error when zero_point_flux is missing
        vega_payload = valid_target_payload.copy()
        vega_payload["brightness"] = {
            "type": "vega_mag",
            "target_mag": 15.0
            # deliberately omit zero_point_flux
        }
        with pytest.raises(ValidationError, match="Field required"):
            TargetProfile(**vega_payload)

    def test_calculation_options_mutual_exclusion(self):
        """Tests that calculation strategies are truly mutually exclusive, and their
        parameters can't be mixed"""
        from castor.schema import CalculationOptions
        from pydantic import TypeAdapter
        
        adapter = TypeAdapter(CalculationOptions)
        
        # Mixed-mode error test: declares solving for SNR, but instead of num_exposures gives target_snr
        invalid_options = {
            "type": "solve_snr",
            "aperture_factor": 1.5,
            "single_exp_time": 60.0,
            "target_snr": 100.0  # this field only exists in solve_time
        }
        
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            adapter.validate_python(invalid_options)


# ==========================================
# Test focus 3: strict mode's rejection power
# ==========================================
class TestStrictModelDefenses:
    def test_forbid_extra_garbage_fields(self, valid_target_payload):
        """Ensures typos or unknown junk parameters are rejected outright, not silently swallowed"""
        payload = valid_target_payload.copy()
        payload["ra"] = 180.0
        payload["dec"] = 45.0
        
        # deliberately inject an undefined field
        payload["what_is_this_field"] = "some_garbage_data"
        
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            TargetProfile(**payload)