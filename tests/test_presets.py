import json
import os

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
    that was actually measured. Extinction is the other way round: no band has a
    trustworthy one, so all of them still inherit the site's 0.17.
    """
    environment = shipped.resolve("lulin")["environment"]

    assert environment["location"]["elevation_m"] == 2862.0
    assert environment["extinction_coeff"] == 0.17               # site fallback
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
    """Lulin u' has an SLT throughput now, but no mu_dark and no LOT throughput,
    so those still inherit.

    The point of overriding per field rather than per section: a band can carry a
    telescope-scoped throughput without also claiming a sky brightness nobody
    measured for it, or a throughput for a telescope it was never measured on.
    """
    site = shipped.profile("lulin").environment

    fragment = shipped.resolve("lulin", optic_filter="Sloan_u")  # LOT is the default
    assert fragment["environment"]["mu_dark"] == site.mu_dark
    assert fragment["environment"]["extinction_coeff"] == site.extinction_coeff
    assert fragment["instrument"]["telescope"]["optical_throughput"] == (
        shipped.profile("lulin").telescopes["LOT"].telescope.optical_throughput)


def test_every_lulin_band_still_inherits_the_site_extinction(shipped):
    """Extinction is band-dependent, and Lulin's is still not measured well enough.

    The 2024-04-14 SLT night swept airmass 1.81-3.72 and still could not deliver
    it: the sky faded 0.1-0.4 mag between the halves of the night at matched
    airmass, degenerate with the airmass term because the target was setting.
    See validation/slt.py WHY_NO_EXTINCTION. The field exists on BandSky and is
    deliberately unset, so the site value stands.
    """
    site = shipped.profile("lulin").environment
    for band in shipped.profile("lulin").filters:
        fragment = shipped.resolve("lulin", optic_filter=band)
        assert fragment["environment"]["extinction_coeff"] == site.extinction_coeff


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


# ==========================================
# Several files
# ==========================================

def _write(path, profiles, comment=None):
    document = {"profiles": profiles}
    if comment is not None:
        document = {"_comment": comment, **document}
    path.write_text(json.dumps(document), encoding="utf-8")
    return path

def _shipped_as_written():
    return json.loads(presets.DEFAULT_PATH.read_text(encoding="utf-8"))

@pytest.fixture
def backyard(tmp_path):
    """A second file of the kind a host generates for itself: one hardware family,
    no site, and a comment block of its own."""
    return _write(tmp_path / "backyard.json", {"backyard": {
        "name": "Backyard rig",
        "telescopes": {"C8": {"name": "C8", "telescope": {
            "primary_mirror_diameter": 0.203, "secondary_mirror_diameter": 0.07,
            "focal_length": 2.032, "optical_throughput": 0.8}}},
    }}, comment=["generated somewhere else"])

def test_one_file_reads_exactly_as_it_always_has(shipped):
    """None is what callers of the old single optional argument passed for the default."""
    assert presets.load(presets.DEFAULT_PATH) == shipped
    assert presets.load(None) == shipped

def test_files_merge_in_the_order_given(backyard):
    """The first file's first profile is the one a host opens on, so order is kept
    across files exactly as it is kept within one."""
    assert list(presets.load(presets.DEFAULT_PATH, backyard).profiles) == [
        "lulin", "vlt", "other", "backyard"]
    assert list(presets.load(backyard, presets.DEFAULT_PATH).profiles) == [
        "backyard", "lulin", "vlt", "other"]

def test_a_merged_profile_is_the_one_its_file_holds(shipped, backyard):
    merged = presets.load(presets.DEFAULT_PATH, backyard)

    assert merged.profile("lulin") == shipped.profile("lulin")
    assert merged.resolve("backyard")["instrument"]["telescope"]["primary_mirror_diameter"] == 0.203

def test_a_profile_defined_twice_is_an_error_naming_both_files(tmp_path, backyard):
    """Never a quiet override: whichever one lost would sit in its file looking used."""
    again = _write(tmp_path / "again.json", {"backyard": {"name": "Another rig"}})

    with pytest.raises(presets.PresetError, match="'backyard' is defined in both") as caught:
        presets.load(backyard, again)
    assert str(backyard) in str(caught.value) and str(again) in str(caught.value)

def test_reading_one_file_twice_is_that_same_error():
    with pytest.raises(presets.PresetError, match="'lulin' is defined in both"):
        presets.load(presets.DEFAULT_PATH, presets.DEFAULT_PATH)

def test_the_hardware_family_rule_holds_in_every_file_and_names_it(tmp_path):
    rig = _write(tmp_path / "rig.json", {"rig": {"filters": {"F": {
        "optic_filter": {"central_wavelength": 500.0, "filter_bandwidth": 100.0,
                         "filter_transmission": 0.9},
        "environment": {"mu_dark": 21.0}}}}})

    with pytest.raises(presets.PresetError, match=r"rig\.json: profile 'rig'.*hardware family"):
        presets.load(presets.DEFAULT_PATH, rig)

def test_a_malformed_file_among_several_says_which_one(tmp_path):
    """The error's location starts at "profiles", which on its own names no file."""
    broken = _write(tmp_path / "broken.json", {"x": {"telescopes": {"t": {"telescope": {
        "primary_mirror_diameter": 1.0, "secondary_mirror_diameter": 0.3,
        "focal_length": 8.0, "optical_thruput": 0.8}}}}})

    with pytest.raises(ValidationError) as caught:
        presets.load(presets.DEFAULT_PATH, broken)
    assert f"in {broken}" in caught.value.__notes__

def test_load_reads_no_environment_on_its_own(monkeypatch, tmp_path):
    """A library caller gets the files it named and no others; honouring the
    variable is a host's choice, made through search_path()."""
    monkeypatch.setenv(presets.PATH_VARIABLE, str(tmp_path / "nowhere.json"))

    assert list(presets.load().profiles) == ["lulin", "vlt", "other"]

def test_the_search_path_is_the_shipped_file_alone_by_default(monkeypatch):
    monkeypatch.delenv(presets.PATH_VARIABLE, raising=False)

    assert presets.search_path() == [presets.DEFAULT_PATH]

def test_the_search_path_appends_the_variables_files_in_order(monkeypatch, tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    monkeypatch.setenv(presets.PATH_VARIABLE, os.pathsep.join([str(first), "", str(second)]))

    assert presets.search_path() == [presets.DEFAULT_PATH, first, second]

def test_the_search_path_starts_from_a_hosts_own_copy(monkeypatch, tmp_path):
    """The desktop build's copy of the shipped file is not at DEFAULT_PATH."""
    monkeypatch.delenv(presets.PATH_VARIABLE, raising=False)

    assert presets.search_path(tmp_path / "presets.json") == [tmp_path / "presets.json"]

def test_one_file_is_handed_on_exactly_as_written():
    """What the browser has always been served: the parsed file, comment and all."""
    assert json.dumps(presets.document()) == json.dumps(_shipped_as_written())

def test_a_merged_document_holds_each_profile_as_written(backyard):
    """No defaults filled in and no nulls added, unlike a dump of what load() parsed."""
    merged = presets.document(presets.DEFAULT_PATH, backyard)
    written = json.loads(backyard.read_text(encoding="utf-8"))

    assert merged["_comment"] == _shipped_as_written()["_comment"]
    assert list(merged["profiles"]) == ["lulin", "vlt", "other", "backyard"]
    assert merged["profiles"]["backyard"] == written["profiles"]["backyard"]
    assert merged["profiles"]["lulin"] == _shipped_as_written()["profiles"]["lulin"]

def test_a_merged_document_is_held_to_the_same_rules(backyard):
    with pytest.raises(presets.PresetError, match="defined in both"):
        presets.document(backyard, backyard)

# ==========================================
# Hardware named from another profile
# ==========================================

def test_a_qualified_name_puts_another_profiles_hardware_under_this_sky(shipped):
    """Lulin's sky, location and camera, with a telescope from the "other" profile."""
    fragment = shipped.resolve("lulin", telescope="other/RedCat51")
    redcat = shipped.profile("other").telescopes["RedCat51"].telescope

    assert fragment["environment"]["location"]["elevation_m"] == 2862.0
    assert fragment["environment"]["mu_dark"] == 21.26           # Sloan r', still Lulin's
    assert fragment["instrument"]["camera"]["readout_noise"] == 7.9  # Sophia, still the default
    assert fragment["instrument"]["telescope"] == redcat.model_dump()

def test_a_borrowed_telescope_takes_no_throughput_measured_on_another(shipped):
    """Sloan r' carries LOT's and SLT's measured throughput. Neither says anything
    about a RedCat, so the RedCat keeps its own number rather than inheriting one
    measured on a different telescope — the bug the telescope keying exists to stop."""
    fragment = shipped.resolve("lulin", telescope="other/RedCat51", optic_filter="Sloan_r")

    assert fragment["instrument"]["telescope"]["optical_throughput"] == 0.9

def test_qualifying_with_the_sites_own_profile_is_the_plain_name(shipped):
    plain = dict(telescope="SLT", optic_filter="Sloan_g")
    spelled_out = dict(telescope="lulin/SLT", optic_filter="lulin/Sloan_g")

    assert shipped.resolve("lulin", **spelled_out) == shipped.resolve("lulin", **plain)
    assert shipped.labels("lulin", **spelled_out) == shipped.labels("lulin", **plain)

def test_a_borrowed_filter_leaves_its_own_sky_behind(shipped):
    """Sloan r' carries Lulin's sky through r'. Under Paranal's sky that would be a
    number measured somewhere else, so VLT's own site values stand."""
    fragment = shipped.resolve("vlt", optic_filter="lulin/Sloan_r")
    paranal = shipped.profile("vlt").environment

    assert fragment["environment"]["mu_dark"] == paranal.mu_dark
    assert "zodiacal_share" not in fragment["environment"]
    assert fragment["instrument"]["optic_filter"]["central_wavelength"] == 627.8

def test_a_borrowed_filter_keeps_its_throughput_for_its_own_telescope(shipped):
    """Telescope and filter both from Lulin: the r' throughput measured on LOT is
    exactly the one that belongs to this pairing, wherever the sky is."""
    with_lot = shipped.resolve("vlt", telescope="lulin/LOT", optic_filter="lulin/Sloan_r")
    with_vlt = shipped.resolve("vlt", optic_filter="lulin/Sloan_r")

    assert with_lot["instrument"]["telescope"]["optical_throughput"] == 0.568
    assert with_vlt["instrument"]["telescope"]["optical_throughput"] == (
        shipped.profile("vlt").telescopes["VLT"].telescope.optical_throughput)

def test_a_hardware_family_still_cannot_gain_a_sky(shipped):
    """Borrowing a site's filter does not bring the site along."""
    catalogue = presets.PresetFile(profiles={
        **shipped.profiles,
        "bare": presets.Profile(name="Bare Telescope"),
    })

    fragment = catalogue.resolve("bare", optic_filter="lulin/Sloan_r")

    assert "environment" not in fragment
    assert fragment["instrument"]["optic_filter"]["central_wavelength"] == 627.8

@pytest.mark.parametrize("kwargs, expected", [
    ({"telescope": "othr/RedCat51"}, "Unknown profile 'othr'. Available: lulin, vlt, other"),
    ({"telescope": "other/RedCat99"}, "for profile 'other'. Available: RedCat51, RedCat71"),
    ({"camera": "vlt/Sophia"}, "for profile 'vlt'. Available: FORS2_MIT"),
    ({"optic_filter": "other/Sloan_r"}, r"for profile 'other'. Available: \(none\)"),
])
def test_an_unknown_qualified_name_lists_what_there_is(shipped, kwargs, expected):
    with pytest.raises(presets.PresetNotFound, match=expected):
        shipped.resolve("lulin", **kwargs)

def test_labels_name_borrowed_hardware(shipped):
    labels = shipped.labels("lulin", telescope="other/RedCat51")

    assert labels["profile"] == "Lulin Observatory"
    assert labels["telescope"] == "William Optics RedCat 51"

def test_a_borrowed_entry_with_no_name_is_labelled_by_where_it_came_from(shipped):
    catalogue = presets.PresetFile(profiles={
        **shipped.profiles,
        "rig": presets.Profile(telescopes={"C8": presets.TelescopeEntry(
            telescope=schema.TelescopeSchema(
                primary_mirror_diameter=0.203, secondary_mirror_diameter=0.07,
                focal_length=2.032, optical_throughput=0.8))}),
    })

    assert catalogue.labels("lulin", telescope="rig/C8")["telescope"] == "rig/C8"
    assert catalogue.labels("rig")["telescope"] == "C8"

def test_borrowed_hardware_brings_its_profiles_caveat(shipped):
    """VLT's instrument values are mostly guesses, and say so. Mounting its camera
    under Lulin's measured sky does not make them any less of one."""
    vlt = shipped.profile("vlt").caveat

    assert shipped.caveats("lulin") == {}
    assert shipped.caveats("vlt") == {"vlt": vlt}
    assert shipped.caveats("lulin", camera="vlt/FORS2_MIT") == {"vlt": vlt}
    assert shipped.caveats("vlt", telescope="lulin/LOT") == {"vlt": vlt}

@pytest.mark.parametrize("profiles", [
    {"a/b": {"name": "slash in the profile id"}},
    {"rig": {"telescopes": {"C8/f10": {"telescope": {
        "primary_mirror_diameter": 0.203, "secondary_mirror_diameter": 0.07,
        "focal_length": 2.032, "optical_throughput": 0.8}}}}},
])
def test_a_name_holding_the_qualifier_is_refused(tmp_path, profiles):
    """It could not be told from a qualified name, so it could never be asked for."""
    path = _write(tmp_path / "slash.json", profiles)

    with pytest.raises(presets.PresetError, match="separates a profile from a key"):
        presets.load(path)
