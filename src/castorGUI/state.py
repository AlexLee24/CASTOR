import sys
import json
from pathlib import Path
from datetime import datetime, timezone

PRESETS_PATH = Path(__file__).resolve().parent / "data" / "presets.json"

# castorGUI/ and castor/ are two sibling packages under src/; this package itself isn't
# pip-installed (pyproject.toml has no build-system), so src/ has to be pushed onto
# sys.path manually before "from castor import schema" can find it.
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from castor import schema  # noqa: E402
from castor.calculator import run_calculation  # noqa: E402
from pydantic import ValidationError  # noqa: E402


class AppState:
    """
    Centralized store for the GUI form data. Every field is accessed via a dotted path
    (e.g. "instrument.telescope.focal_length"), which maps directly onto the nested
    structure of castor.schema.ObservationRequest and matches the key format used in
    data/presets.json, making it easy to wire up to the calculation engine or LOAD/SAVE JSON.
    """

    def __init__(self):
        self.instrument = {
            "telescope": {
                "primary_mirror_diameter": 1.0,
                "secondary_mirror_diameter": 0.3,
                "focal_length": 8.0,
                "optical_throughput": 0.85
            },
            "camera": {
                "pixel_pitch": 15.0,
                "quantum_efficiency": 0.85,
                "dark_current_rate": 0.01,
                "readout_noise": 5.0,
                "full_well_capacity": 100000.0
            },
            "optic_filter": {
                "central_wavelength": 550.0,
                "filter_bandwidth": 89.0,
                "filter_transmission": 0.9
            },
            "throughput_correction": 1.0
        }

        self.target = {
            "morphology": {"type": "point"},
            "brightness": {
                "type": "vega_mag",
                "target_mag": 15.0,
                "zero_point_flux": 3.63e-9,
                # Used when switching to jansky_flux / wavelength_flux; ignored in vega_mag/ab_mag mode
                "flux_value": 100.0
            },
            "sed": {
                "type": "flat",
                # Used when switching to the Temp (blackbody) SED; ignored in flat mode
                "temperature_k": 5800.0
            },
            "ra": 180.0,
            "dec": 45.0
        }

        self.environment = {
            "location": {
                "latitude_deg": 23.47,
                "longitude_deg": 120.87,
                "elevation_m": 2862.0
            },
            "observing_time_utc": datetime.now(timezone.utc).isoformat(),
            "auto_calc_background": False,
            "mu_dark": 21.0,
            "extinction_coeff": 0.15,
            "seeing_fwhm": 1.5,
            "diffraction_fwhm": 0.2,
            "optical_fwhm": 0.1,
            "tracking_fwhm": 0.1
        }

        self.options = {
            "type": "solve_snr",
            "aperture_factor": 1.5,
            "single_exp_time": 300.0,
            "num_exposures": 1,
            # Used in solve_time mode; ignored in solve_snr mode
            "target_snr": 10.0
        }

        self.presets = self._load_presets()

    # ==========================================
    # Dotted-path access
    # ==========================================
    def get(self, path: str):
        parts = path.split(".")
        node = getattr(self, parts[0])
        for part in parts[1:]:
            node = node[part]
        return node

    def set(self, path: str, value) -> None:
        parts = path.split(".")
        node = getattr(self, parts[0])
        for part in parts[1:-1]:
            node = node[part]
        node[parts[-1]] = value

    # ==========================================
    # Hardware presets (data/presets.json)
    # ==========================================
    def _load_presets(self) -> dict:
        if not PRESETS_PATH.exists():
            return {}
        with open(PRESETS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def apply_preset(self, category: str, key: str) -> list[str]:
        """
        Applies a preset (e.g. category="telescopes", key="LOT").
        Returns the list of changed dotted paths, so the caller can sync the
        corresponding input fields' displayed values.
        """
        preset = self.presets.get(category, {}).get(key)
        if not preset:
            return []
        for dotted_path, value in preset.items():
            self.set(dotted_path, value)
        return list(preset.keys())

    # ==========================================
    # Calculation engine payload (flattened version for LOAD/SAVE JSON,
    # keeps every branch's fields, no filtering)
    # ==========================================
    def get_api_payload(self) -> dict:
        return {
            "instrument": self.instrument,
            "target": self.target,
            "environment": self.environment,
            "options": self.options
        }

    # ==========================================
    # LOAD: overwrite the current state with saved content
    # ==========================================
    def load_from_dict(self, data: dict) -> None:
        """
        Overwrites the current state with a save file (in the format produced by
        get_api_payload()). Uses a deep-merge rather than a wholesale replace: fields
        missing from the save file (e.g. an old file predating throughput_correction)
        keep their current default values instead of blowing away the whole state.
        """
        for section in ("instrument", "target", "environment", "options"):
            incoming = data.get(section)
            if isinstance(incoming, dict):
                self._deep_update(getattr(self, section), incoming)

    @staticmethod
    def _deep_update(base: dict, incoming: dict) -> None:
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                AppState._deep_update(base[key], value)
            else:
                base[key] = value

    # ==========================================
    # Builds a castor.schema.ObservationRequest
    # ==========================================
    def build_observation_request(self) -> schema.ObservationRequest:
        """
        Takes the dict-shaped form state and, based on the currently selected type
        (discriminator), picks out only the relevant fields to assemble a valid strict
        Pydantic ObservationRequest.
        Missing fields or wrong types let pydantic's ValidationError propagate outward
        directly, to be caught centrally by recalculate().
        """
        inst = self.instrument
        instrument = schema.InstrumentProfile(
            telescope=schema.TelescopeSchema(**inst["telescope"]),
            camera=schema.CameraSchema(**inst["camera"]),
            optic_filter=schema.FilterSchema(**inst["optic_filter"]),
            throughput_correction=inst["throughput_correction"],
        )

        tgt = self.target

        if tgt["morphology"]["type"] == "extended":
            morphology = schema.ExtendedMorphology()
        else:
            morphology = schema.PointMorphology()

        b = tgt["brightness"]
        match b["type"]:
            case "vega_mag":
                brightness = schema.VegaMagnitude(target_mag=b["target_mag"], zero_point_flux=b["zero_point_flux"])
            case "ab_mag":
                brightness = schema.ABMagnitude(target_mag=b["target_mag"])
            case "jansky_flux":
                brightness = schema.JanskyFlux(flux_value=b["flux_value"])
            case "wavelength_flux":
                brightness = schema.WavelengthFlux(flux_value=b["flux_value"])
            case _:
                raise ValueError(f"Unknown brightness type: {b['type']!r}")

        if tgt["sed"]["type"] == "Temp":
            # castor.calculator doesn't currently read sed; temperature_k doesn't affect
            # any calculation result yet — this just lets the form hold the value until
            # spectral calculations are wired up later.
            sed = schema.TempSED()
        else:
            sed = schema.FlatSED()

        target = schema.TargetProfile(
            morphology=morphology,
            brightness=brightness,
            sed=sed,
            ra=tgt["ra"],
            dec=tgt["dec"],
        )

        env = self.environment
        observing_time = datetime.fromisoformat(env["observing_time_utc"])
        if observing_time.tzinfo is None:
            observing_time = observing_time.replace(tzinfo=timezone.utc)

        environment = schema.EnvironmentCondition(
            location=schema.ObservatoryLocation(**env["location"]),
            observing_time_utc=observing_time,
            auto_calc_background=env["auto_calc_background"],
            mu_dark=env["mu_dark"],
            extinction_coeff=env["extinction_coeff"],
            seeing_fwhm=env["seeing_fwhm"],
            diffraction_fwhm=env["diffraction_fwhm"],
            optical_fwhm=env["optical_fwhm"],
            tracking_fwhm=env["tracking_fwhm"],
        )

        opt = self.options
        if opt["type"] == "solve_time":
            options: schema.CalculationOptions = schema.SolveForTime(
                aperture_factor=opt["aperture_factor"],
                single_exp_time=opt["single_exp_time"],
                target_snr=opt["target_snr"],
            )
        else:
            options = schema.SolveForSNR(
                aperture_factor=opt["aperture_factor"],
                single_exp_time=opt["single_exp_time"],
                num_exposures=opt["num_exposures"],
            )

        return schema.ObservationRequest(
            instrument=instrument, target=target, environment=environment, options=options
        )

    # ==========================================
    # Live calculation: never let exceptions escape, hand them to the caller to display
    # ==========================================
    def recalculate(self) -> tuple[schema.ObservationResponse | None, str | None]:
        """
        Returns (response, None) on success; (None, error_message) on failure
        (invalid input, or a physical boundary error raised during calculation).
        """
        try:
            request = self.build_observation_request()
            response = run_calculation(request)
            return response, None
        except ValidationError as e:
            return None, self._format_validation_error(e)
        except ValueError as e:
            return None, str(e)
        except Exception as e:  # noqa: BLE001 - at the GUI layer, showing an error beats crashing outright
            return None, f"Unexpected error: {e}"

    @staticmethod
    def _format_validation_error(e: ValidationError) -> str:
        lines = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"{loc}: {err['msg']}")
        return "\n".join(lines) if lines else str(e)
