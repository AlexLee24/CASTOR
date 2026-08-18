import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

PRESETS_PATH = Path(__file__).resolve().parent / "data" / "presets.json"

# castorGUI/ and castor/ are two sibling packages under src/; this package itself isn't
# pip-installed (pyproject.toml has no build-system), so src/ has to be pushed onto
# sys.path manually before "from castor import schema" can find it.
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from castor import schema  # noqa: E402
from castor.calculator import run_calculation  # noqa: E402
from castor.batch_calculator import run_batch_calculation  # noqa: E402
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

        # Batch is not a separate mode — it's an optional extra: when True, the GUI also
        # runs BatchObservationRequest / recalculate_batch() alongside the always-on single
        # calculation, and the Options tab swaps environment.observing_time_utc for the
        # start/end/step trio in batch_time. instrument/target/options are shared as-is
        # either way (field-for-field identical schemas); environment's
        # location/mu_dark/extinction_coeff/FWHM fields are shared too — only the time axis
        # differs. TimeSeriesEnvironment has no auto_calc_background equivalent — the batch
        # path always layers the dynamic moon/geometry contribution, regardless of that
        # switch's value.
        self.batch_enabled = False
        _now = datetime.now(timezone.utc)
        self.batch_time = {
            "start_time_utc": _now.isoformat(),
            "end_time_utc": (_now + timedelta(hours=6)).isoformat(),
            "time_step_minutes": 15.0,
        }

        self.presets = self._load_presets()

        # Which preset the current values came from, or None for "Custom". None is the
        # honest starting value: the defaults above are generic, not a copy of any one
        # profile, so claiming a profile on first paint would misdescribe them. Set by
        # apply_profile()/apply_filter(), cleared by load_from_dict().
        self.active_profile: str | None = None
        self.active_rig: str | None = None
        self.active_filter: str | None = None

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

    def apply_profile(self, profile_id: str) -> list[str]:
        """
        Selects an observing profile (e.g. "lulin") and its first rig — one of the two
        preset actions the UI offers, the other being apply_rig().

        A profile carrying an "environment" block is a real site, so its coordinates,
        mu_dark and extinction are filled in alongside the hardware; that cross-tab
        fill-in is the whole point of grouping them. A profile without one only ever
        touches "instrument": see the note in data/presets.json about why a telescope
        model must not carry an invented location.

        Note what is deliberately *not* applied: median_seeing_fwhm. Seeing describes
        the night being planned rather than the site, and it is the field an observer
        is most likely to have set on purpose, so it is surfaced as a reference figure
        (see median_seeing()) instead of overwriting their input.

        Returns the dotted paths it changed, so the caller can refresh exactly those
        fields' displayed values.
        """
        profile = self.presets.get("profiles", {}).get(profile_id)
        if profile is None:
            return []

        self.active_profile = profile_id
        changed: list[str] = []

        site = profile.get("environment")
        if site:
            changed += self._apply_fragment("environment", site)

        first_rig = next(iter(profile.get("rigs", {})), None)
        if first_rig is not None:
            changed += self.apply_rig(first_rig)
        else:
            self.active_rig = None
        return changed

    def apply_rig(self, rig_id: str) -> list[str]:
        """
        Swaps the telescope/camera within the active profile, and touches nothing else.

        Kept separate from apply_profile() rather than folded in as an argument: picking
        a different instrument at the same site is not a reason to re-apply that site's
        sky, which would quietly discard an mu_dark or extinction the observer had
        adjusted for the night they are actually planning.
        """
        rigs = self.presets.get("profiles", {}).get(self.active_profile or "", {}).get("rigs", {})
        rig = rigs.get(rig_id)
        if rig is None:
            return []
        self.active_rig = rig_id
        return self._apply_fragment("instrument", rig.get("instrument", {}))

    def apply_filter(self, key: str) -> list[str]:
        """Filters stay their own choice rather than being folded into a rig: which
        band you observe in changes between exposures, while the telescope and camera
        don't."""
        preset = self.presets.get("filters", {}).get(key)
        if not preset:
            return []
        self.active_filter = key
        return self._apply_fragment("instrument.optic_filter", preset.get("optic_filter", {}))

    def median_seeing(self) -> float | None:
        """The active site's typical seeing, for display next to the seeing field.
        None for hardware-only profiles and for Custom."""
        profile = self.presets.get("profiles", {}).get(self.active_profile or "", {})
        return profile.get("median_seeing_fwhm")

    def _apply_fragment(self, section: str, fragment: dict) -> list[str]:
        """Writes a nested, schema-shaped preset fragment into the state and reports
        the dotted paths it touched."""
        changed = []
        for path, value in self._flatten(section, fragment):
            self.set(path, value)
            changed.append(path)
        return changed

    @staticmethod
    def _flatten(prefix: str, fragment: dict):
        for key, value in fragment.items():
            path = f"{prefix}.{key}"
            if isinstance(value, dict):
                yield from AppState._flatten(path, value)
            else:
                yield path, value

    # ==========================================
    # Calculation engine payload (flattened version for LOAD/SAVE JSON,
    # keeps every branch's fields, no filtering)
    # ==========================================
    def get_api_payload(self) -> dict:
        return {
            "instrument": self.instrument,
            "target": self.target,
            "environment": self.environment,
            "options": self.options,
            "batch_time": self.batch_time,
            "batch_enabled": self.batch_enabled,
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
        for section in ("instrument", "target", "environment", "options", "batch_time"):
            incoming = data.get(section)
            if isinstance(incoming, dict):
                self._deep_update(getattr(self, section), incoming)

        # batch_enabled is a plain bool, not a dict to deep-merge — validate it rather than
        # trusting an arbitrary value from a hand-edited save file
        batch_enabled = data.get("batch_enabled")
        if isinstance(batch_enabled, bool):
            self.batch_enabled = batch_enabled

        # Loaded values are the user's own and needn't match any preset — leaving the
        # selectors pointing at whatever was chosen before would claim a provenance the
        # numbers on screen no longer have.
        self.active_profile = None
        self.active_rig = None
        self.active_filter = None

    @staticmethod
    def _deep_update(base: dict, incoming: dict) -> None:
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                AppState._deep_update(base[key], value)
            else:
                base[key] = value

    # ==========================================
    # Shared builders — instrument/target/options are field-for-field identical between
    # single and batch mode, so both build_observation_request() and
    # build_batch_observation_request() assemble them the same way. Only environment
    # differs (a single observing_time_utc vs. a start/end/step time series), so it's
    # built separately by each.
    # ==========================================
    def _build_instrument(self) -> schema.InstrumentProfile:
        inst = self.instrument
        return schema.InstrumentProfile(
            telescope=schema.TelescopeSchema(**inst["telescope"]),
            camera=schema.CameraSchema(**inst["camera"]),
            optic_filter=schema.FilterSchema(**inst["optic_filter"]),
            throughput_correction=inst["throughput_correction"],
        )

    def _build_target(self) -> schema.TargetProfile:
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

        return schema.TargetProfile(
            morphology=morphology,
            brightness=brightness,
            sed=sed,
            ra=tgt["ra"],
            dec=tgt["dec"],
        )

    def _build_options(self, batch: bool):
        """batch=False builds SolveForSNR/SolveForTime; batch=True builds their
        BatchSolveForSNR/BatchSolveForTime equivalents. Same source dict either way —
        the two schema families share the exact same field names."""
        opt = self.options
        snr_cls = schema.BatchSolveForSNR if batch else schema.SolveForSNR
        time_cls = schema.BatchSolveForTime if batch else schema.SolveForTime

        if opt["type"] == "solve_time":
            return time_cls(
                aperture_factor=opt["aperture_factor"],
                single_exp_time=opt["single_exp_time"],
                target_snr=opt["target_snr"],
            )
        return snr_cls(
            aperture_factor=opt["aperture_factor"],
            single_exp_time=opt["single_exp_time"],
            num_exposures=opt["num_exposures"],
        )

    @staticmethod
    def _parse_aware(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

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
        env = self.environment
        environment = schema.EnvironmentCondition(
            location=schema.ObservatoryLocation(**env["location"]),
            observing_time_utc=self._parse_aware(env["observing_time_utc"]),
            auto_calc_background=env["auto_calc_background"],
            mu_dark=env["mu_dark"],
            extinction_coeff=env["extinction_coeff"],
            seeing_fwhm=env["seeing_fwhm"],
            diffraction_fwhm=env["diffraction_fwhm"],
            optical_fwhm=env["optical_fwhm"],
            tracking_fwhm=env["tracking_fwhm"],
        )

        return schema.ObservationRequest(
            instrument=self._build_instrument(),
            target=self._build_target(),
            environment=environment,
            options=self._build_options(batch=False),
        )

    # ==========================================
    # Builds a castor.schema.BatchObservationRequest
    # ==========================================
    def build_batch_observation_request(self) -> schema.BatchObservationRequest:
        """
        Same idea as build_observation_request(), but for batch/time-series mode.
        environment.location/mu_dark/extinction_coeff/FWHM fields are shared with single
        mode (self.environment); only the time axis comes from self.batch_time.
        """
        env = self.environment
        bt = self.batch_time
        environment = schema.TimeSeriesEnvironment(
            location=schema.ObservatoryLocation(**env["location"]),
            start_time_utc=self._parse_aware(bt["start_time_utc"]),
            end_time_utc=self._parse_aware(bt["end_time_utc"]),
            time_step_minutes=bt["time_step_minutes"],
            mu_dark=env["mu_dark"],
            extinction_coeff=env["extinction_coeff"],
            seeing_fwhm=env["seeing_fwhm"],
            diffraction_fwhm=env["diffraction_fwhm"],
            optical_fwhm=env["optical_fwhm"],
            tracking_fwhm=env["tracking_fwhm"],
        )

        return schema.BatchObservationRequest(
            instrument=self._build_instrument(),
            target=self._build_target(),
            environment=environment,
            options=self._build_options(batch=True),
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

    def recalculate_batch(self) -> tuple[schema.BatchObservationResponse | None, str | None]:
        """Batch/time-series counterpart to recalculate(). Same error-handling shape:
        never raises, hands (None, message) back on any failure."""
        try:
            request = self.build_batch_observation_request()
            response = run_batch_calculation(request)
            return response, None
        except ValidationError as e:
            return None, self._format_validation_error(e)
        except ValueError as e:
            return None, str(e)
        except Exception as e:  # noqa: BLE001
            return None, f"Unexpected error: {e}"

    @staticmethod
    def _format_validation_error(e: ValidationError) -> str:
        lines = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"{loc}: {err['msg']}")
        return "\n".join(lines) if lines else str(e)
