import json

import pytest
from click.testing import CliRunner

from castorCLI import presets
from castorCLI.main import cli

# ==========================================
# Fixtures
# ==========================================

@pytest.fixture(autouse=True)
def no_extra_presets(monkeypatch):
    """Without --presets-file every command reads the search path, so a
    CASTOR_PRESETS_PATH left set in the shell running the suite would quietly
    change what each test here is looking at."""
    monkeypatch.delenv(presets.PATH_VARIABLE, raising=False)

@pytest.fixture
def run():
    """Invokes the CLI the way a shell would, with stdout and stderr kept apart."""
    runner = CliRunner()
    return lambda *args, **kwargs: runner.invoke(cli, list(args), **kwargs)

#: An instant at which the fixture target stands 8.5 degrees from Lulin's zenith.
#: Every calculation below pins it. Without one the CLI defaults to now, and the
#: answers swing with the sidereal clock: the same saturation case that fires at
#: this hour is six thousand times fainter twelve hours later, so the suite passed
#: or failed depending on what time of day it was run.
WELL_PLACED = "2026-01-15T16:00:00Z"


@pytest.fixture
def lulin():
    """The shortest complete calculation: a site, a target, and one question."""
    return ["calc", "--site", "lulin", "--ra", "113.65", "--dec", "31.89",
            "--mag", "18", "--exp", "300", "-n", "10", "--time", WELL_PLACED]

@pytest.fixture
def hardware_only_presets(tmp_path):
    """A presets file with one profile that has no environment.

    VLT used to be this file's only example of a hardware family — a profile
    naming instruments but no site — until it gained Paranal's own coordinates.
    Nothing shipped is hardware-only any more, so the tests that exercise that
    path need their own minimal fixture rather than depending on VLT staying
    that way.
    """
    path = tmp_path / "hardware_only.json"
    path.write_text(json.dumps({
        "profiles": {
            "bare_scope": {
                "name": "Bare Telescope",
                "telescopes": {"T": {"name": "T", "telescope": {
                    "primary_mirror_diameter": 1.0, "secondary_mirror_diameter": 0.2,
                    "focal_length": 8.0, "optical_throughput": 0.5}}},
                "cameras": {"C": {"name": "C", "camera": {
                    "pixel_pitch": 10.0, "quantum_efficiency": 0.8, "dark_current_rate": 0.01,
                    "readout_noise": 5.0, "full_well_capacity": 100000}}},
                "filters": {"F": {"name": "F", "optic_filter": {
                    "central_wavelength": 550.0, "filter_bandwidth": 100.0, "filter_transmission": 0.9}}},
            }
        }
    }))
    return path


@pytest.fixture
def saved_form(tmp_path):
    """What the web form's SAVE writes — a superset of a request.

    Every branch of every discriminated union keeps its value (zero_point_flux is
    there while the brightness says ab_mag) and the batch panel's own state rides
    along, neither of which castor.schema will accept.
    """
    path = tmp_path / "save.json"
    path.write_text(json.dumps({
        "instrument": {
            "telescope": {"primary_mirror_diameter": 1.0, "secondary_mirror_diameter": 0.3,
                          "focal_length": 8.0, "optical_throughput": 0.8},
            "camera": {"pixel_pitch": 15.0, "quantum_efficiency": 0.85, "dark_current_rate": 0.01,
                       "readout_noise": 5.0, "full_well_capacity": 100000},
            "optic_filter": {"central_wavelength": 623.0, "filter_bandwidth": 137.0,
                             "filter_transmission": 0.9},
            "throughput_correction": 1.0,
        },
        "target": {
            "morphology": {"type": "point"},
            "sed": {"type": "flat"},
            "brightness": {"type": "ab_mag", "target_mag": 19.6,
                           "zero_point_flux": 3.63e-9, "flux_value": 100.0},
            "ra": 109.1437, "dec": 38.3523,
        },
        "environment": {
            "location": {"latitude_deg": 23.47, "longitude_deg": 120.87, "elevation_m": 2862},
            "observing_time_utc": "2026-01-01T18:00:00Z", "auto_calc_background": True,
            "mu_dark": 21.0, "extinction_coeff": 0.15, "seeing_fwhm": 1.5,
            "diffraction_fwhm": 0.2, "optical_fwhm": 0.1, "tracking_fwhm": 0.1,
        },
        "options": {"type": "solve_snr", "aperture_factor": 1.5,
                    "single_exp_time": 120, "num_exposures": 1, "target_snr": 10.0},
        "batch_time": {"start_time_utc": "2026-01-01T18:00:00Z",
                       "end_time_utc": "2026-01-02T00:00:00Z", "time_step_minutes": 15},
        "batch_enabled": False,
    }), encoding="utf-8")
    return path

# ==========================================
# The happy path
# ==========================================

def test_a_site_and_a_target_are_enough(run, lulin):
    result = run(*lulin)

    assert result.exit_code == 0
    assert "Lulin Observatory · LOT 1.0 m · Sophia · Sloan r'" in result.stdout
    assert "Total SNR" in result.stdout

def test_solving_for_time_reports_the_frames_needed(run):
    result = run("calc", "--site", "lulin", "--ra", "113.65", "--dec", "31.89",
                 "--mag", "21", "--exp", "300", "--snr", "50", "--time", WELL_PLACED)

    assert result.exit_code == 0
    assert "Exposures needed" in result.stdout

def test_named_hardware_shows_up_in_the_header(run, lulin):
    result = run(*lulin, "--telescope", "SLT", "--filter", "Sloan_z")

    assert "SLT 0.4 m" in result.stdout and "Sloan z'" in result.stdout

# ==========================================
# Never inventing a number quietly
# ==========================================

def test_every_supplied_value_is_reported(run, lulin):
    """The whole point of the tool: what it chose is on screen, not buried in the request."""
    result = run(*lulin)

    assert "options.aperture_factor = 0.85" in result.stderr
    assert "instrument.throughput_correction = 1.0" in result.stderr

def test_assumptions_stay_off_stdout(run, lulin):
    """stdout is the answer, so it survives being piped somewhere that only wants the answer."""
    result = run(*lulin)

    assert "assumed" not in result.stdout

def test_seeing_falls_back_to_the_site_median_and_says_which(run, lulin):
    result = run(*lulin)

    assert "environment.seeing_fwhm = 1.4" in result.stderr
    assert "not tonight's seeing" in result.stderr

def test_a_stated_value_is_not_an_assumption(run, lulin):
    result = run(*lulin, "--seeing", "2.2")

    assert "environment.seeing_fwhm" not in result.stderr

def test_a_hardware_only_profile_names_what_it_cannot_supply(run, hardware_only_presets):
    """A hardware-only profile lists no site, and the tool would rather fail than
    place the observer somewhere. VLT was this suite's example until it gained
    Paranal's own coordinates; see hardware_only_presets for why this now needs
    its own fixture instead of a shipped profile."""
    result = run("calc", "--presets-file", str(hardware_only_presets), "--site", "bare_scope",
                 "--ra", "113.65", "--dec", "31.89", "--mag", "18", "--exp", "300", "-n", "1")

    assert result.exit_code == 3
    assert "environment.location: Field required" in result.stderr

# ==========================================
# Saying no usefully
# ==========================================

def test_a_missing_field_is_named_not_guessed(run):
    result = run("calc", "--site", "lulin", "--mag", "18", "--exp", "300", "-n", "10")

    assert result.exit_code == 3
    assert "target.ra: Field required" in result.stderr

def test_an_unknown_site_lists_the_real_ones(run):
    result = run("calc", "--site", "lulln", "--ra", "1", "--dec", "1",
                 "--mag", "18", "--exp", "300", "-n", "1")

    assert result.exit_code == 3
    assert "Available: lulin, vlt" in result.stderr

def test_the_two_directions_of_the_question_are_exclusive(run, lulin):
    result = run(*lulin, "--snr", "20")

    assert result.exit_code == 2
    assert "pick one" in result.stderr

def test_asking_nothing_says_what_to_ask(run):
    result = run("calc", "--site", "lulin", "--ra", "1", "--dec", "1",
                 "--mag", "18", "--exp", "300")

    assert result.exit_code == 2
    assert "--snr" in result.stderr

def test_hardware_without_a_site_is_a_usage_error(run):
    result = run("calc", "--telescope", "LOT", "--ra", "1", "--dec", "1",
                 "--mag", "18", "--exp", "300", "-n", "1")

    assert result.exit_code == 2

# ==========================================
# Overrides
# ==========================================

def test_set_beats_the_preset(run, lulin):
    result = run(*lulin, "--set", "environment.mu_dark=18.0", "--json")

    assert json.loads(result.stdout)["request"]["environment"]["mu_dark"] == 18.0

def test_a_misspelled_set_path_is_an_error_not_a_shrug(run, lulin):
    """Dropping it would leave the caller believing a value was applied."""
    result = run(*lulin, "--set", "environment.mu_drak=18.0")

    assert result.exit_code == 3
    assert "mu_drak" in result.stderr

def test_set_parses_json_values(run, lulin):
    result = run(*lulin, "--set", "target.morphology.type=extended", "--json")

    assert json.loads(result.stdout)["request"]["target"]["morphology"]["type"] == "extended"

# ==========================================
# Reading back what the form saved
# ==========================================

def test_a_saved_form_runs_as_is(run, saved_form):
    result = run("calc", "--request", str(saved_form))

    assert result.exit_code == 0
    assert "Total SNR" in result.stdout

def test_what_a_request_had_no_room_for_is_listed(run, saved_form):
    result = run("calc", "--request", str(saved_form))

    assert "batch_enabled" in result.stderr
    assert "target.brightness.zero_point_flux" in result.stderr

def test_a_saved_form_can_be_piped_in(run, saved_form):
    result = run("calc", "--request", "-", input=saved_form.read_text(encoding="utf-8"))

    assert result.exit_code == 0

def test_flags_layer_over_a_saved_form(run, saved_form):
    result = run("calc", "--request", str(saved_form), "--mag", "22", "--json")

    assert json.loads(result.stdout)["request"]["target"]["brightness"]["target_mag"] == 22.0

# ==========================================
# Saturation
# ==========================================

def test_saturation_leaves_by_a_different_exit_code(run):
    """A caller that only checks the exit code still finds out."""
    result = run("calc", "--site", "lulin", "--ra", "113.65", "--dec", "31.89",
                 "--mag", "8", "--exp", "300", "-n", "1", "--time", WELL_PLACED)

    assert result.exit_code == 1
    assert "SATURATED" in result.stderr
    assert "Total SNR" in result.stdout  # the number is still reported, just not endorsed

# ==========================================
# Machine-readable output
# ==========================================

def test_json_carries_the_request_the_response_and_the_choices(run, lulin):
    payload = json.loads(run(*lulin, "--json").stdout)

    assert payload["response"]["core"]["total_snr"] > 0
    assert payload["request"]["instrument"]["telescope"]["primary_mirror_diameter"] == 1.02
    assert any(item["path"] == "options.aperture_factor" for item in payload["assumed"])

def test_json_stdout_is_only_json(run, lulin):
    """Anything else on stdout would break the caller that reaches for --json."""
    json.loads(run(*lulin, "--json").stdout)

# ==========================================
# Discovery
# ==========================================

def test_presets_lists_sites_and_marks_the_defaults(run):
    result = run("presets")

    assert "lulin" in result.stdout
    assert "LOT*" in result.stdout

def test_presets_warns_that_a_hardware_profile_has_no_place(run, hardware_only_presets):
    result = run("presets", "--presets-file", str(hardware_only_presets))
    assert "hardware only" in result.stdout

def test_schema_is_the_contract_itself(run):
    contract = json.loads(run("schema").stdout)

    assert contract["title"] == "ObservationRequest"
    assert "instrument" in contract["properties"]

# ==========================================
# Several preset files
# ==========================================

SHIPPED = str(presets.DEFAULT_PATH)

def test_one_presets_file_still_replaces_the_shipped_one(run, hardware_only_presets):
    result = run("presets", "--presets-file", str(hardware_only_presets))

    assert "bare_scope" in result.stdout and "lulin" not in result.stdout

def test_presets_file_repeats_to_merge_in_order(run, hardware_only_presets):
    result = run("presets", "--presets-file", SHIPPED, "--presets-file", str(hardware_only_presets))

    assert result.exit_code == 0
    assert result.stdout.index("lulin") < result.stdout.index("bare_scope")

def test_the_variable_adds_files_after_the_shipped_one(run, monkeypatch, hardware_only_presets):
    monkeypatch.setenv(presets.PATH_VARIABLE, str(hardware_only_presets))
    result = run("presets")

    assert result.exit_code == 0
    assert result.stdout.index("lulin") < result.stdout.index("bare_scope")

def test_naming_a_presets_file_sets_the_variable_aside(run, monkeypatch, tmp_path,
                                                       hardware_only_presets):
    monkeypatch.setenv(presets.PATH_VARIABLE, str(tmp_path / "nowhere.json"))
    result = run("presets", "--presets-file", str(hardware_only_presets))

    assert result.exit_code == 0

def test_a_missing_file_on_the_variable_is_bad_input(run, monkeypatch, tmp_path):
    monkeypatch.setenv(presets.PATH_VARIABLE, str(tmp_path / "nowhere.json"))
    result = run("presets")

    assert result.exit_code == 3
    assert "nowhere.json" in result.stderr

def test_a_profile_in_two_files_is_bad_input(run):
    result = run("presets", "--presets-file", SHIPPED, "--presets-file", SHIPPED)

    assert result.exit_code == 3
    assert "'lulin' is defined in both" in result.stderr

@pytest.fixture
def misspelled_presets(tmp_path, hardware_only_presets):
    broken = json.loads(hardware_only_presets.read_text())
    telescope = broken["profiles"]["bare_scope"]["telescopes"]["T"]["telescope"]
    telescope["focal_lenght"] = telescope.pop("focal_length")
    path = tmp_path / "misspelled.json"
    path.write_text(json.dumps(broken))
    return path

@pytest.mark.parametrize("from_variable", [False, True])
def test_a_misspelled_field_names_the_file_it_is_in(run, monkeypatch, misspelled_presets,
                                                    from_variable):
    """The field's location starts at "profiles", which on its own does not say which
    of the files read is the broken one."""
    if from_variable:
        monkeypatch.setenv(presets.PATH_VARIABLE, str(misspelled_presets))
        result = run("presets")
    else:
        result = run("presets", "--presets-file", SHIPPED, "--presets-file", str(misspelled_presets))

    assert result.exit_code == 3
    assert "profiles.bare_scope.telescopes.T.telescope.focal_lenght" in result.stderr
    assert f"(in {misspelled_presets})" in result.stderr

def test_check_covers_every_merged_file(run, hardware_only_presets):
    result = run("check", "--presets-file", SHIPPED, "--presets-file", str(hardware_only_presets))

    assert result.exit_code == 0
    assert "43 resolvable configurations checked across 4 profiles" in result.stdout

def test_check_finds_a_problem_in_a_later_file(run, tmp_path, hardware_only_presets):
    broken = json.loads(hardware_only_presets.read_text())
    broken["profiles"]["bare_scope"]["telescopes"]["T"]["telescope"]["secondary_mirror_diameter"] = 1.0
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken))

    result = run("check", "--presets-file", SHIPPED, "--presets-file", str(path))

    assert result.exit_code == 3
    assert "PROBLEM  bare_scope/T/C/F: secondary is not smaller" in result.stderr

# ==========================================
# Hardware named from another profile
# ==========================================

def test_calc_takes_a_telescope_from_another_profile(run, lulin):
    """Lulin's sky and location, with the RedCat from the "other" profile, which
    keeps its own throughput rather than Sloan r''s figure measured on LOT."""
    result = run(*lulin, "--telescope", "other/RedCat51", "--json")
    request = json.loads(result.stdout)["request"]

    assert result.exit_code == 0
    assert request["environment"]["location"]["elevation_m"] == 2862.0
    assert request["environment"]["mu_dark"] == 21.26
    assert request["instrument"]["telescope"]["primary_mirror_diameter"] == 0.051
    assert request["instrument"]["telescope"]["optical_throughput"] == 0.9

def test_the_header_names_the_borrowed_telescope(run, lulin):
    result = run(*lulin, "--telescope", "other/RedCat51")

    assert "Lulin Observatory · William Optics RedCat 51 · Sophia · Sloan r'" in result.stdout

def test_a_hardware_family_runs_under_a_site(run, lulin, hardware_only_presets):
    """What a file of hardware families is for: someone's own rig under a real
    site's sky. On its own such a profile still exits 3 for want of a location."""
    result = run(*lulin, "--presets-file", SHIPPED, "--presets-file", str(hardware_only_presets),
                 "--telescope", "bare_scope/T", "--camera", "bare_scope/C",
                 "--filter", "bare_scope/F", "--json")
    request = json.loads(result.stdout)["request"]

    assert result.exit_code == 0
    assert request["environment"]["location"]["latitude_deg"] == 23.47
    assert request["environment"]["mu_dark"] == 21.5   # site-wide: F brings no Lulin band sky
    assert request["instrument"]["camera"]["readout_noise"] == 5.0
    assert request["instrument"]["optic_filter"]["central_wavelength"] == 550.0

def test_an_unknown_qualified_name_lists_what_there_is(run, lulin):
    result = run(*lulin, "--telescope", "other/RedCat99")

    assert result.exit_code == 3
    assert "Available: RedCat51, RedCat71" in result.stderr

def test_borrowed_hardware_brings_its_profiles_caveat(run, lulin):
    result = run(*lulin, "--camera", "vlt/FORS2_MIT")

    assert "CAVEAT: vlt: Demonstration only" in result.stderr

def test_json_carries_a_borrowed_caveat(run, lulin):
    payload = json.loads(run(*lulin, "--camera", "vlt/FORS2_MIT", "--json").stdout)

    assert payload["caveat"] == "vlt: " + presets.load().profile("vlt").caveat

def test_a_sites_own_caveat_reads_as_it_always_has(run):
    caveat = presets.load().profile("vlt").caveat
    args = ["calc", "--site", "vlt", "--ra", "113.65", "--dec", "-31.89",
            "--mag", "18", "--exp", "30", "-n", "1", "--seeing", "0.8", "--time", WELL_PLACED]

    assert f"\nCAVEAT: {caveat}\n" in run(*args).stderr
    assert json.loads(run(*args, "--json").stdout)["caveat"] == caveat
