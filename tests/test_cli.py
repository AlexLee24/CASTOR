import json

import pytest
from click.testing import CliRunner

from castorCLI import presets, provenance
from castorCLI.main import check_file, cli

# ==========================================
# Fixtures
# ==========================================

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
# Checking a preset file
# ==========================================

def _shipped_profiles():
    return json.loads(presets.DEFAULT_PATH.read_text(encoding="utf-8"))["profiles"]

@pytest.fixture
def overridden_nothing(tmp_path):
    """Loads perfectly, and a band's throughput applies to nothing: the filter
    names a telescope its profile does not list."""
    path = tmp_path / "overridden_nothing.json"
    path.write_text(json.dumps({
        "profiles": {
            "bare_scope": {
                "telescopes": {"T": {"telescope": {
                    "primary_mirror_diameter": 1.0, "secondary_mirror_diameter": 0.2,
                    "focal_length": 8.0, "optical_throughput": 0.5}}},
                "cameras": {"C": {"camera": {
                    "pixel_pitch": 10.0, "quantum_efficiency": 0.8, "dark_current_rate": 0.01,
                    "readout_noise": 5.0, "full_well_capacity": 100000}}},
                "filters": {"F": {
                    "optic_filter": {"central_wavelength": 550.0, "filter_bandwidth": 100.0,
                                     "filter_transmission": 0.9},
                    "telescope": {"X": {"optical_throughput": 0.4}}}},
            }
        }
    }), encoding="utf-8")
    return path

@pytest.fixture
def table_for_shipped(tmp_path):
    """A provenance table that covers the shipped file exactly.

    Built from the file rather than taken from validation/provenance.py, which is
    the shipped file's real record but is not part of this suite: what is under
    test here is the command, not the record.
    """
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps({
        key: [value, provenance.GUESS, "fixture: no source claimed"]
        for key, value in provenance.walk(_shipped_profiles()).items()
    }), encoding="utf-8")
    return path

def test_check_passes_the_shipped_file(run):
    result = run("check")

    assert result.exit_code == 0
    assert result.stdout.splitlines()[0].endswith("resolvable configurations checked across 3 profiles")
    assert result.stdout.splitlines()[-1] == "no problems found"
    assert result.stderr == ""

def test_check_finds_what_loading_cannot(run, overridden_nothing):
    result = run("check", "--presets-file", str(overridden_nothing))

    assert result.exit_code == 3
    assert ("  PROBLEM  bare_scope: filter 'F' overrides telescope 'X', which this profile "
            "does not list — it applies to nothing") in result.stderr.splitlines()

def test_check_file_is_the_command_without_the_printing(run, overridden_nothing):
    """What a host calls on its own file instead of shelling out."""
    checked, problems = check_file(presets.load())
    assert problems == []
    assert run("check").stdout.startswith(f"{checked} resolvable configurations checked")

    checked, problems = check_file(presets.load(overridden_nothing))
    assert checked == 1
    assert problems == ["bare_scope: filter 'F' overrides telescope 'X', which this profile "
                        "does not list — it applies to nothing"]

def test_check_holds_the_file_to_a_provenance_table(run, table_for_shipped):
    result = run("check", "--provenance", str(table_for_shipped))

    assert result.exit_code == 0
    held = len(provenance.walk(_shipped_profiles()))
    assert f"{held} values checked against {table_for_shipped}" in result.stdout
    assert result.stdout.splitlines()[-1] == "no problems found"

def test_check_without_a_table_says_nothing_about_provenance(run):
    """The flag is opt-in: a run without it prints exactly what it always has."""
    assert "values checked against" not in run("check").stdout

def test_a_bad_provenance_table_fails_the_check(run, table_for_shipped):
    table = json.loads(table_for_shipped.read_text(encoding="utf-8"))
    del table["lulin.cameras.Sophia.readout_noise"]
    table["lulin.environment.mu_dark"][2] = "guessed"
    table_for_shipped.write_text(json.dumps(table), encoding="utf-8")

    result = run("check", "--provenance", str(table_for_shipped))

    assert result.exit_code == 3
    problems = [line for line in result.stderr.splitlines() if line.startswith("  PROBLEM  ")]
    assert [line.split(":")[0] for line in problems] == [
        "  PROBLEM  lulin.cameras.Sophia.readout_noise",
        "  PROBLEM  lulin.environment.mu_dark",
    ]
    assert "no problems found" not in result.stdout

def test_provenance_problems_follow_the_files_own(run, overridden_nothing, tmp_path):
    table = tmp_path / "provenance.json"
    table.write_text("{}", encoding="utf-8")

    result = run("check", "--presets-file", str(overridden_nothing), "--provenance", str(table))

    problems = [line for line in result.stderr.splitlines() if line.startswith("  PROBLEM  ")]
    assert result.exit_code == 3
    assert problems[0].startswith("  PROBLEM  bare_scope: filter 'F'")
    assert problems[1].startswith("  PROBLEM  bare_scope.telescopes.T.primary_mirror_diameter:")

def test_provenance_vouches_for_the_file_as_written(run, overridden_nothing, tmp_path):
    """Loading coerces a quoted number to a float; the record must match what the
    file actually says, so the check reads the file, not the loaded catalogue."""
    data = json.loads(overridden_nothing.read_text(encoding="utf-8"))
    data["profiles"]["bare_scope"]["telescopes"]["T"]["telescope"]["focal_length"] = "8.0"
    overridden_nothing.write_text(json.dumps(data), encoding="utf-8")
    table = tmp_path / "provenance.json"
    table.write_text(json.dumps({
        key: [8.0 if key.endswith("focal_length") else value, provenance.DOCUMENT, "fixture datasheet"]
        for key, value in provenance.walk(data["profiles"]).items()
    }), encoding="utf-8")

    result = run("check", "--presets-file", str(overridden_nothing), "--provenance", str(table))

    assert ("  PROBLEM  bare_scope.telescopes.T.focal_length: the file holds '8.0' "
            "but its record vouches for 8.0") in result.stderr.splitlines()

def test_an_unreadable_provenance_table_is_bad_input(run, tmp_path):
    result = run("check", "--provenance", str(tmp_path / "nowhere.json"))

    assert result.exit_code == 3
    assert result.stderr.startswith("error: Cannot read provenance table")
