import sys
import json
from pathlib import Path
from datetime import datetime, timezone

PRESETS_PATH = Path(__file__).resolve().parent / "data" / "presets.json"

# castorGUI/ 和 castor/ 是 src/ 底下的兩個平行套件，這個套件本身不是用
# pip 安裝的（pyproject.toml 沒有 build-system），所以要手動把 src/ 塞進
# sys.path，"from castor import schema" 才找得到人。
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from castor import schema  # noqa: E402
from castor.calculator import run_calculation  # noqa: E402
from pydantic import ValidationError  # noqa: E402


class AppState:
    """
    集中管理 GUI 表單資料。所有欄位都用 dotted path（例如
    "instrument.telescope.focal_length"）存取，直接對應
    castor.schema.ObservationRequest 的巢狀結構，也跟 data/presets.json
    的 key 格式一致，之後接計算引擎或 LOAD/SAVE JSON 都方便。
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
                # 供 jansky_flux / wavelength_flux 切換時使用，vega_mag/ab_mag 模式下會被忽略
                "flux_value": 100.0
            },
            "sed": {
                "type": "flat",
                # 供 Temp（黑體）SED 切換時使用，flat 模式下會被忽略
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
            # 供 solve_time 模式使用，solve_snr 模式下會被忽略
            "target_snr": 10.0
        }

        self.presets = self._load_presets()

    # ==========================================
    # Dotted-path 存取
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
    # 硬體 Preset（data/presets.json）
    # ==========================================
    def _load_presets(self) -> dict:
        if not PRESETS_PATH.exists():
            return {}
        with open(PRESETS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def apply_preset(self, category: str, key: str) -> list[str]:
        """
        套用 preset（例如 category="telescopes", key="LOT"）。
        回傳被改動的 dotted path 清單，方便呼叫端同步更新對應輸入框的顯示值。
        """
        preset = self.presets.get(category, {}).get(key)
        if not preset:
            return []
        for dotted_path, value in preset.items():
            self.set(dotted_path, value)
        return list(preset.keys())

    # ==========================================
    # 計算引擎 Payload（給 LOAD/SAVE JSON 用的攤平版本，
    # 保留所有分流欄位，不篩選）
    # ==========================================
    def get_api_payload(self) -> dict:
        return {
            "instrument": self.instrument,
            "target": self.target,
            "environment": self.environment,
            "options": self.options
        }

    # ==========================================
    # LOAD：用存檔內容覆蓋目前狀態
    # ==========================================
    def load_from_dict(self, data: dict) -> None:
        """
        用存檔（get_api_payload() 存出來的格式）覆蓋目前狀態。
        用 deep-merge 而不是整段取代：存檔裡缺欄位（例如舊檔案沒有新加的
        throughput_correction）就保留目前的預設值，不會整組炸掉。
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
    # 組成 castor.schema.ObservationRequest
    # ==========================================
    def build_observation_request(self) -> schema.ObservationRequest:
        """
        把 dict 形式的表單狀態，依照目前選到的 type（discriminator）只挑出
        相關欄位，組成一份合法的 strict Pydantic ObservationRequest。
        欄位缺漏或型別不對時，會直接讓 pydantic 的 ValidationError 往外拋，
        交給 recalculate() 統一接住。
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
            # castor.calculator 目前不會讀取 sed，temperature_k 尚未影響任何計算結果，
            # 這裡先讓表單存在，之後補上光譜計算時再串接。
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
    # 即時運算：永遠不讓例外往外炸，交給呼叫端顯示
    # ==========================================
    def recalculate(self) -> tuple[schema.ObservationResponse | None, str | None]:
        """
        回傳 (response, None) 表示成功；(None, error_message) 表示失敗
        （輸入不合法、或計算過程中的物理邊界錯誤）。
        """
        try:
            request = self.build_observation_request()
            response = run_calculation(request)
            return response, None
        except ValidationError as e:
            return None, self._format_validation_error(e)
        except ValueError as e:
            return None, str(e)
        except Exception as e:  # noqa: BLE001 - GUI 這層寧可顯示錯誤也不要整個崩掉
            return None, f"Unexpected error: {e}"

    @staticmethod
    def _format_validation_error(e: ValidationError) -> str:
        lines = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"{loc}: {err['msg']}")
        return "\n".join(lines) if lines else str(e)
