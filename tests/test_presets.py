import json

import pytest
from pydantic import ValidationError

from castor import schema
from castorCLI import presets

# ==========================================
# Fixtures
# ==========================================

@pytest.fixture
def shipped():
    """The preset file this repository actually ships.

    Loaded rather than mocked on purpose: most of the value here is catching the day
    data/presets.json stops being the shape every host reads it as.
    """
    return presets.load()

@pytest.fixture
def remainder():
    """Everything a preset cannot speak for.

    A preset describes equipment and a place. The target, the night, the seeing
    budget and the calculation strategy are the caller's, and so is
    throughput_correction — it is a property of the system as configured, not of any
    single catalogue entry.
    """
    return {
        "instrument": {"throughput_correction": 1.0},
        "target": {
            "morphology": {"type": "point"},
            "brightness": {"type": "ab_mag", "target_mag": 18.0},
            "sed": {"type": "flat"},
            "ra": 180.0,
            "dec": 0.0,
        },
        "environment": {
            "observing_time_utc": "2026-01-01T18:00:00Z",
            "auto_calc_background": True,
            "seeing_fwhm": 1.4,
            "diffraction_fwhm": 0.1,
            "optical_fwhm": 0.3,
            "tracking_fwhm": 0.2,
        },
        "options": {
            "type": "solve_snr",
            "aperture_factor": 1.5,
            "single_exp_time": 120.0,
            "num_exposures": 10,
        },
    }

def merged(fragment, remainder):
    """Layers the caller's own values over a resolved preset, one section deep."""
    request = dict(remainder)
    for section, values in fragment.items():
        request[section] = {**request.get(section, {}), **values}
    return request

# ==========================================
# Loading the shipped file
# ==========================================

def test_shipped_file_parses(shipped):
    assert list(shipped.profiles) == ["lulin", "vlt"]

def test_key_order_survives_loading(shipped):
    """Order is the file author's way of naming defaults, so it has to be preserved."""
    assert list(shipped.profile("lulin").telescopes) == ["LOT", "SLT"]

def test_top_level_comment_is_tolerated(tmp_path):
    """The file documents itself in a "_comment" block; rejecting unknown keys at the
    envelope would make the file unreadable to its own loader."""
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"_comment": ["notes"], "profiles": {}}), encoding="utf-8")

    assert presets.load(path).profiles == {}

def test_misspelled_leaf_field_is_rejected(tmp_path):
    """Leaves are validated as the engine's own strict types, so a typo fails loudly
    at load instead of silently never being applied."""
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({
        "profiles": {
            "x": {"telescopes": {"t": {"telescope": {
                "primary_mirror_diameter": 1.0,
                "secondary_mirror_diameter": 0.3,
                "focal_length": 8.0,
                "optical_thruput": 0.8,
            }}}}
        }
    }), encoding="utf-8")

    with pytest.raises(ValidationError):
        presets.load(path)

def test_missing_file_reports_its_path(tmp_path):
    with pytest.raises(presets.PresetError, match="nowhere.json"):
        presets.load(tmp_path / "nowhere.json")

def test_malformed_json_is_not_a_traceback(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(presets.PresetError, match="not valid JSON"):
        presets.load(path)

# ==========================================
# Resolution
# ==========================================

def test_naming_only_the_site_resolves_a_real_configuration(shipped):
    """First entry listed in each catalogue is the default."""
    fragment = shipped.resolve("lulin")

    assert fragment["instrument"]["telescope"]["primary_mirror_diameter"] == 1.0  # LOT
    assert fragment["instrument"]["camera"]["readout_noise"] == 5.0               # Sophia
    assert fragment["instrument"]["optic_filter"]["central_wavelength"] == 623.0  # Sloan r'

def test_named_entries_override_the_defaults(shipped):
    fragment = shipped.resolve("lulin", telescope="SLT", camera="SLT_default", optic_filter="Sloan_u")

    assert fragment["instrument"]["telescope"]["primary_mirror_diameter"] == 0.4
    assert fragment["instrument"]["camera"]["pixel_pitch"] == 9.0
    assert fragment["instrument"]["optic_filter"]["central_wavelength"] == 354.0

def test_a_site_fills_in_its_sky_and_location(shipped):
    environment = shipped.resolve("lulin")["environment"]

    assert environment["location"]["elevation_m"] == 2862.0
    assert environment["mu_dark"] == 21.5
    assert environment["extinction_coeff"] == 0.17

def test_a_hardware_family_invents_no_location(shipped):
    """VLT is listed as hardware only. Resolving it must leave the observer where they
    are rather than quietly moving them to Paranal, which would change airmass and moon
    geometry with nothing on screen to say so."""
    fragment = shipped.resolve("vlt")

    assert "environment" not in fragment
    assert fragment["instrument"]["telescope"]["primary_mirror_diameter"] == 8.0

def test_site_median_seeing_is_readable_but_never_resolved(shipped):
    """Seeing is a condition of the night being planned, not a property of the site."""
    profile = shipped.profile("lulin")

    assert profile.median_seeing_fwhm == 1.4
    assert "seeing_fwhm" not in shipped.resolve("lulin")["environment"]

# ==========================================
# Unknown names
# ==========================================

def test_unknown_profile_lists_what_there_is(shipped):
    with pytest.raises(presets.PresetNotFound, match="lulin, vlt"):
        shipped.profile("lulln")

@pytest.mark.parametrize("kwargs, expected", [
    ({"telescope": "LOT-1m"}, "LOT, SLT"),
    ({"camera": "sophia"}, "Sophia, SLT_default"),
    ({"optic_filter": "r"}, "Sloan_r, Sloan_u"),
])
def test_unknown_catalogue_entry_lists_what_there_is(shipped, kwargs, expected):
    with pytest.raises(presets.PresetNotFound, match=expected):
        shipped.resolve("lulin", **kwargs)

def test_empty_catalogue_is_only_an_error_when_something_was_asked_for(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"profiles": {"bare": {"name": "Bare"}}}), encoding="utf-8")
    bare = presets.load(path)

    assert bare.resolve("bare") == {}
    with pytest.raises(presets.PresetNotFound, match=r"\(none\)"):
        bare.resolve("bare", telescope="LOT")

# ==========================================
# The point of all of it: a resolved preset is request-shaped
# ==========================================

def test_resolved_preset_completes_into_a_valid_request(shipped, remainder):
    request = schema.ObservationRequest.model_validate(merged(shipped.resolve("lulin"), remainder))

    assert request.instrument.telescope.primary_mirror_diameter == 1.0
    assert request.environment.location.latitude_deg == 23.47

def test_resolved_preset_runs_through_the_engine(shipped, remainder):
    from castor.calculator import run_calculation

    response = run_calculation(
        schema.ObservationRequest.model_validate(merged(shipped.resolve("lulin"), remainder))
    )

    assert response.core.total_snr > 0
