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
    assert list(shipped.profiles) == ["lulin", "vlt", "other"]

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

    assert fragment["instrument"]["telescope"]["primary_mirror_diameter"] == 1.02  # LOT
    assert fragment["instrument"]["camera"]["readout_noise"] == 7.9               # Sophia
    assert fragment["instrument"]["optic_filter"]["central_wavelength"] == 627.8  # Sloan r'

def test_named_entries_override_the_defaults(shipped):
    fragment = shipped.resolve("lulin", telescope="SLT", camera="SLT_DU934P", optic_filter="Sloan_u")

    assert fragment["instrument"]["telescope"]["primary_mirror_diameter"] == 0.406
    assert fragment["instrument"]["camera"]["pixel_pitch"] == 13.0
    assert fragment["instrument"]["optic_filter"]["central_wavelength"] == 353.4

def test_a_site_fills_in_its_sky_and_location(shipped):
    """The location is the site's alone; the sky is the site's until a band knows better.

    Resolving with no filter named lands on the first listed, which for Lulin is
    Sloan r' and carries its own measured mu_dark — the local-only baseline, with
    zodiacal light split back out (validation/QUESTIONS.md 9/10), not the 20.92
    that was actually measured — and its own measured extinction_coeff, not the
    site's flat 0.17 (QUESTIONS.md 4). The site's 21.5/0.17 are what a band
    without a measurement still inherits — see the u' test below.
    """
    environment = shipped.resolve("lulin")["environment"]

    assert environment["location"]["elevation_m"] == 2862.0
    assert shipped.profile("lulin").environment.extinction_coeff == 0.17
    assert environment["extinction_coeff"] == 0.314               # r', measured
    assert shipped.profile("lulin").environment.mu_dark == 21.5
    assert environment["mu_dark"] == 21.26                       # r', local only
    assert environment["zodiacal_share"] == 0.267                # r'

def test_a_hardware_family_invents_no_location():
    """A profile with no environment block is a hardware family, and resolving it
    must leave the observer where they are rather than inventing coordinates —
    that would change airmass and moon geometry with nothing on screen to say so.

    Built inline rather than read from the shipped file: VLT was this suite's
    example of a hardware-only profile until it gained Paranal's own sourced
    coordinates (ESO's published site data, and Patat et al. 2011's measured
    extinction curve integrated against FORS2's own V_HIGH+114 filter), so
    nothing shipped is hardware-only any more. The behaviour this test protects
    still needs covering on its own.
    """
    catalogue = presets.PresetFile(profiles={
        "bare": presets.Profile(
            name="Bare Telescope",
            telescopes={"T": presets.TelescopeEntry(
                name="T", telescope=schema.TelescopeSchema(
                    primary_mirror_diameter=1.0, secondary_mirror_diameter=0.2,
                    focal_length=8.0, optical_throughput=0.5))},
        )
    })

    fragment = catalogue.resolve("bare")

    assert "environment" not in fragment
    assert fragment["instrument"]["telescope"]["primary_mirror_diameter"] == 1.0

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
    ({"camera": "sophia"}, "Sophia, SLT_DU934P"),
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

    assert request.instrument.telescope.primary_mirror_diameter == 1.02
    assert request.environment.location.latitude_deg == 23.47

def test_resolved_preset_runs_through_the_engine(shipped, remainder):
    from castor.calculator import run_calculation

    response = run_calculation(
        schema.ObservationRequest.model_validate(merged(shipped.resolve("lulin"), remainder))
    )

    assert response.core.total_snr > 0


# ==========================================
# Band-dependent values a filter carries
# ==========================================

def test_choosing_a_filter_changes_the_sky_it_looks_through(shipped):
    """Sky brightness is a property of the site and the band, not the site alone.

    Measured at Lulin the three Sloan bands sit 1.4 magnitudes apart, so whichever
    single figure the site carried was wrong for the other two by up to a factor
    of 3.8 in background flux.
    """
    skies = {band: shipped.resolve("lulin", optic_filter=band)["environment"]["mu_dark"]
             for band in ("Sloan_g", "Sloan_r", "Sloan_i")}

    assert len(set(skies.values())) == 3
    assert skies["Sloan_g"] > skies["Sloan_r"] > skies["Sloan_i"]


def test_choosing_a_filter_changes_the_throughput_in_front_of_it(shipped):
    """The same for optical efficiency, which the photometry puts at 0.27-0.48."""
    def throughput(band):
        fragment = shipped.resolve("lulin", optic_filter=band)
        return fragment["instrument"]["telescope"]["optical_throughput"]

    assert throughput("Sloan_r") > throughput("Sloan_g")
    assert throughput("Sloan_r") > throughput("Sloan_i")


def test_a_filter_without_a_measurement_leaves_the_site_values_alone(shipped):
    """Lulin u' has extinction and SLT throughput now, but still no mu_dark or LOT
    throughput measurement, so those two still inherit.

    The point of overriding per field rather than per section: a band can correct
    its extinction without also having to claim a sky brightness nobody measured
    for it, and a telescope-scoped throughput without claiming one for a telescope
    it was never measured on.
    """
    site = shipped.profile("lulin").environment

    fragment = shipped.resolve("lulin", optic_filter="Sloan_u")  # LOT is the default
    assert fragment["environment"]["mu_dark"] == site.mu_dark
    assert fragment["environment"]["extinction_coeff"] != site.extinction_coeff
    assert fragment["instrument"]["telescope"]["optical_throughput"] == (
        shipped.profile("lulin").telescopes["LOT"].telescope.optical_throughput)


def test_every_lulin_band_now_has_its_own_extinction(shipped):
    """Extinction is band-dependent too, and now it is measured (QUESTIONS.md 4).

    A single photometric night with a real airmass sweep (SLT, 2024-04-14) gave
    every one of Lulin's five bands its own extinction_coeff, so none of them
    fall back to the site's single 0.17 any more — falling towards the red the
    way real extinction should, unlike the flat number it replaced.
    """
    site = shipped.profile("lulin").environment
    for band in shipped.profile("lulin").filters:
        fragment = shipped.resolve("lulin", optic_filter=band)
        assert fragment["environment"]["extinction_coeff"] != site.extinction_coeff


def test_a_hardware_family_cannot_be_given_a_sky(tmp_path):
    """Refused at load, not ignored at resolve — an unapplied number in a data file
    is indistinguishable from a wrong one until somebody measures the difference."""
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"profiles": {"rig": {
        "name": "Hardware only",
        "filters": {"F": {
            "optic_filter": {"central_wavelength": 500.0, "filter_bandwidth": 100.0,
                             "filter_transmission": 0.9},
            "environment": {"mu_dark": 21.0}}}}}}), encoding="utf-8")

    with pytest.raises(presets.PresetError, match="hardware family"):
        presets.load(path)


def test_a_misspelled_band_override_is_an_error(tmp_path):
    """The override models forbid extras for the same reason the leaves do."""
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"profiles": {"site": {
        "environment": {"location": {"latitude_deg": 0.0, "longitude_deg": 0.0,
                                     "elevation_m": 0.0},
                        "mu_dark": 21.5, "extinction_coeff": 0.17},
        "filters": {"F": {
            "optic_filter": {"central_wavelength": 500.0, "filter_bandwidth": 100.0,
                             "filter_transmission": 0.9},
            "environment": {"mu_drak": 21.0}}}}}}), encoding="utf-8")

    with pytest.raises(ValidationError):
        presets.load(path)
