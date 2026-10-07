import json

import pytest

from castorCLI import provenance

# ==========================================
# Fixtures
# ==========================================

@pytest.fixture
def profiles():
    """A small preset file with a number in every place walk() looks.

    A site with a location, a median seeing and a band that overrides both its sky
    and one telescope's throughput, plus a hardware family with no site at all.
    Plain JSON data, the way a host's own file arrives.
    """
    return {
        "site": {
            "name": "A site",
            "caveat": "names and caveats carry no numbers",
            "environment": {
                "location": {"latitude_deg": 23.5, "longitude_deg": 120.9, "elevation_m": 2800.0},
                "mu_dark": 21.5,
                "extinction_coeff": 0.17,
            },
            "median_seeing_fwhm": 1.4,
            "telescopes": {"T": {"name": "T", "telescope": {
                "primary_mirror_diameter": 1.0, "secondary_mirror_diameter": 0.3,
                "focal_length": 8.0, "optical_throughput": 0.5}}},
            "cameras": {"C": {"camera": {
                "pixel_pitch": 15.0, "quantum_efficiency": 0.85, "dark_current_rate": 0.001,
                "readout_noise": 7.9, "full_well_capacity": 150000}}},
            "filters": {"r": {
                "optic_filter": {"central_wavelength": 627.8, "filter_bandwidth": 131.0,
                                 "filter_transmission": 0.995},
                "environment": {"mu_dark": 21.26},
                "telescope": {"T": {"optical_throughput": 0.568}},
            }},
        },
        "family": {
            "cameras": {"C2": {"camera": {
                "pixel_pitch": 3.76, "quantum_efficiency": 0.8, "dark_current_rate": 0.0005,
                "readout_noise": 1.5, "full_well_capacity": 16650}}},
        },
    }

#: Every number in the fixture, by the path a record names it with. Spelled out
#: rather than computed: these paths are what a host's table is keyed by, so a
#: change to their form is a change to the contract.
EXPECTED = {
    "site.environment.location.latitude_deg": 23.5,
    "site.environment.location.longitude_deg": 120.9,
    "site.environment.location.elevation_m": 2800.0,
    "site.environment.mu_dark": 21.5,
    "site.environment.extinction_coeff": 0.17,
    "site.median_seeing_fwhm": 1.4,
    "site.telescopes.T.primary_mirror_diameter": 1.0,
    "site.telescopes.T.secondary_mirror_diameter": 0.3,
    "site.telescopes.T.focal_length": 8.0,
    "site.telescopes.T.optical_throughput": 0.5,
    "site.cameras.C.pixel_pitch": 15.0,
    "site.cameras.C.quantum_efficiency": 0.85,
    "site.cameras.C.dark_current_rate": 0.001,
    "site.cameras.C.readout_noise": 7.9,
    "site.cameras.C.full_well_capacity": 150000,
    "site.filters.r.central_wavelength": 627.8,
    "site.filters.r.filter_bandwidth": 131.0,
    "site.filters.r.filter_transmission": 0.995,
    "site.filters.r.environment.mu_dark": 21.26,
    "site.filters.r.telescope.T.optical_throughput": 0.568,
    "family.cameras.C2.pixel_pitch": 3.76,
    "family.cameras.C2.quantum_efficiency": 0.8,
    "family.cameras.C2.dark_current_rate": 0.0005,
    "family.cameras.C2.readout_noise": 1.5,
    "family.cameras.C2.full_well_capacity": 16650,
}

@pytest.fixture
def table():
    """A record for every number in the fixture, and nothing else."""
    return {path: (value, provenance.DOCUMENT, "fixture datasheet, page 1")
            for path, value in EXPECTED.items()}

def kinds(problems):
    return [(problem.path, problem.kind) for problem in problems]

# ==========================================
# Walking a file
# ==========================================

def test_walk_names_every_number_by_where_it_sits(profiles):
    assert provenance.walk(profiles) == EXPECTED

def test_walk_keeps_the_file_order(profiles):
    """Problems are reported in this order, so it has to be the file's own."""
    assert list(provenance.walk(profiles)) == list(EXPECTED)

# ==========================================
# Checking a file against its table
# ==========================================

def test_a_table_that_covers_the_file_exactly_has_no_problems(profiles, table):
    assert provenance.check(profiles, table) == []

def test_a_number_without_a_record_is_reported(profiles, table):
    del table["site.cameras.C.readout_noise"]

    assert kinds(provenance.check(profiles, table)) == [
        ("site.cameras.C.readout_noise", "missing_record")]

def test_a_record_without_a_number_is_reported(profiles, table):
    """A source for something that no longer exists rots quietly, so it is a
    problem too: the rule covers both directions."""
    table["site.cameras.C.gain"] = (1.0, provenance.MEASURED, "photon transfer curve")

    assert kinds(provenance.check(profiles, table)) == [
        ("site.cameras.C.gain", "orphan_record")]

def test_a_number_that_changed_without_its_record_is_reported(profiles, table):
    """The whole mechanism: a number cannot change while keeping its citation."""
    profiles["site"]["filters"]["r"]["telescope"]["T"]["optical_throughput"] = 0.6

    problems = provenance.check(profiles, table)

    assert kinds(problems) == [("site.filters.r.telescope.T.optical_throughput", "value_mismatch")]
    assert "0.6" in problems[0].message and "0.568" in problems[0].message

@pytest.mark.parametrize("source", ["VERIFIED", "guess", None])
def test_a_class_outside_the_four_is_reported(profiles, table, source):
    path = "site.environment.mu_dark"
    table[path] = (21.5, source, "fallback only; nothing measured")

    assert kinds(provenance.check(profiles, table)) == [(path, "unknown_class")]

def test_a_guess_is_a_class_not_a_problem(profiles, table):
    """Naming a guess is the point. What fails is a number nobody accounted for."""
    table["site.environment.mu_dark"] = (21.5, provenance.GUESS, "no source found at all")

    assert provenance.check(profiles, table) == []

@pytest.mark.parametrize("note, ok", [
    ("x" * (provenance.MIN_NOTE_LENGTH - 1), False),
    ("x" * provenance.MIN_NOTE_LENGTH, True),
    ("", False),
    (None, False),
])
def test_a_note_too_short_to_name_a_source_is_reported(profiles, table, note, ok):
    path = "site.cameras.C.pixel_pitch"
    table[path] = (15.0, provenance.DOCUMENT, note)

    expected = [] if ok else [(path, "short_note")]
    assert kinds(provenance.check(profiles, table)) == expected

@pytest.mark.parametrize("entry", [(15.0, provenance.DOCUMENT), 15.0, "datasheet, page 1"])
def test_a_record_that_is_not_a_triple_is_reported_not_raised(profiles, table, entry):
    path = "site.cameras.C.pixel_pitch"
    table[path] = entry

    assert kinds(provenance.check(profiles, table)) == [(path, "malformed_record")]

def test_every_problem_is_found_in_one_pass(profiles, table):
    """A broken table lists all of its faults, unrecorded numbers first in file
    order, then the table's own findings in table order."""
    del table["site.environment.mu_dark"]
    del table["family.cameras.C2.readout_noise"]
    table["site.cameras.C.readout_noise"] = (8.5, "DATASHEET", "short")
    table["site.retired.X.pixel_pitch"] = (13.0, provenance.DOCUMENT, "retired camera, datasheet")

    assert kinds(provenance.check(profiles, table)) == [
        ("site.environment.mu_dark", "missing_record"),
        ("family.cameras.C2.readout_noise", "missing_record"),
        ("site.cameras.C.readout_noise", "value_mismatch"),
        ("site.cameras.C.readout_noise", "unknown_class"),
        ("site.cameras.C.readout_noise", "short_note"),
        ("site.retired.X.pixel_pitch", "orphan_record"),
    ]

def test_a_problem_reads_as_its_path_and_what_is_wrong(profiles, table):
    del table["site.cameras.C.readout_noise"]

    problem, = provenance.check(profiles, table)

    assert str(problem) == f"site.cameras.C.readout_noise: {problem.message}"
    assert "7.9" in problem.message

def test_a_problem_is_plain_data(profiles, table):
    """Hosts serialise findings into their own reports."""
    del table["site.cameras.C.readout_noise"]

    problem, = provenance.check(profiles, table)

    assert problem.model_dump() == {
        "path": "site.cameras.C.readout_noise",
        "kind": "missing_record",
        "message": problem.message,
    }

# ==========================================
# Summary
# ==========================================

def test_summary_counts_each_profile_by_class(profiles, table):
    table["site.environment.mu_dark"] = (21.5, provenance.GUESS, "no source found at all")
    del table["family.cameras.C2.dark_current_rate"]

    assert provenance.summary(profiles, table) == {
        "site": {provenance.DOCUMENT: 19, provenance.GUESS: 1},
        "family": {provenance.DOCUMENT: 4, "MISSING": 1},
    }

def test_summary_keeps_a_profile_id_with_a_dot_in_it_whole():
    """A profile id is any JSON key. Reading it back off the path up to the first
    dot would merge these two under "owl", a profile that does not exist."""
    profiles = {"owl.home": {"median_seeing_fwhm": 1.2},
                "owl.away": {"median_seeing_fwhm": 1.5}}
    table = {"owl.home.median_seeing_fwhm": (1.2, provenance.MEASURED, "142 frames, FWHM median"),
             "owl.away.median_seeing_fwhm": (1.5, provenance.GUESS, "no seeing monitor there")}
    assert provenance.check(profiles, table) == []

    assert provenance.summary(profiles, table) == {
        "owl.home": {provenance.MEASURED: 1},
        "owl.away": {provenance.GUESS: 1},
    }

# ==========================================
# Tables kept as JSON
# ==========================================

def test_a_json_table_reads_back_as_records(tmp_path, profiles, table):
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps({key: list(record) for key, record in table.items()}),
                    encoding="utf-8")

    loaded = provenance.load_table(path)

    assert loaded == table
    assert provenance.check(profiles, loaded) == []

def test_a_missing_table_names_its_path(tmp_path):
    with pytest.raises(provenance.ProvenanceError, match="nowhere.json"):
        provenance.load_table(tmp_path / "nowhere.json")

def test_a_table_that_is_not_utf8_is_an_error_not_a_traceback(tmp_path, table):
    """Windows PowerShell 5.1 writes UTF-16 when the export is redirected with >.
    A host catching ProvenanceError has to catch this too."""
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps({key: list(record) for key, record in table.items()}),
                    encoding="utf-16")

    with pytest.raises(provenance.ProvenanceError, match="not UTF-8 text"):
        provenance.load_table(path)

def test_a_table_that_is_not_json_is_an_error_not_a_traceback(tmp_path):
    path = tmp_path / "provenance.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(provenance.ProvenanceError, match="not valid JSON"):
        provenance.load_table(path)

def test_a_table_must_be_one_object(tmp_path):
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps([["site.environment.mu_dark", 21.5, "GUESS", "fallback only"]]),
                    encoding="utf-8")

    with pytest.raises(provenance.ProvenanceError, match="one object"):
        provenance.load_table(path)

def test_a_path_recorded_twice_is_an_error(tmp_path):
    """JSON keeps only the last of two equal keys, so the first record would be
    dropped without anyone having read it."""
    path = tmp_path / "provenance.json"
    path.write_text(
        '{"site.environment.mu_dark": [21.5, "GUESS", "fallback only, no source"],\n'
        ' "site.environment.mu_dark": [21.5, "MEASURED", "123 frames, one sightline"]}',
        encoding="utf-8")

    with pytest.raises(provenance.ProvenanceError, match="site.environment.mu_dark is recorded twice"):
        provenance.load_table(path)

def test_bad_records_in_a_readable_table_are_problems_not_errors(tmp_path, profiles, table):
    """Loading checks only the file; the records are check()'s, so every fault in
    them is reported together."""
    table = {key: list(record) for key, record in table.items()}
    table["site.cameras.C.pixel_pitch"] = [15.0, "DOCUMENT"]
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps(table), encoding="utf-8")

    problems = provenance.check(profiles, provenance.load_table(path))

    assert kinds(problems) == [("site.cameras.C.pixel_pitch", "malformed_record")]
