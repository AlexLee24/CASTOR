"""Every number in presets.json has to say where it came from.

The file predates anything that could check it, and when checks arrived, every
value that had one was wrong. So the rule now is that a preset value without a
recorded source is a defect in the record even when the number happens to be
right — because there is no way to tell the difference.
"""
import json
import pathlib

import pytest

import provenance
from castorCLI import presets

PRESETS = json.loads(
    pathlib.Path(presets.DEFAULT_PATH).read_text(encoding="utf-8"))["profiles"]
VALUES = provenance.walk(PRESETS)


def test_the_table_covers_the_file_exactly():
    """Both directions. A value with no entry is unaccounted for; an entry with no
    value is a source for something that no longer exists, which rots quietly."""
    assert set(VALUES) == set(provenance.PROVENANCE)


@pytest.mark.parametrize("path", sorted(VALUES))
def test_each_value_is_the_one_its_source_records(path):
    """Editing a preset without editing its provenance fails here.

    This is the whole mechanism: the table cannot drift from the file, so a
    number cannot quietly change its meaning while keeping its citation.
    """
    assert VALUES[path] == provenance.PROVENANCE[path][0]


@pytest.mark.parametrize("path", sorted(provenance.PROVENANCE))
def test_every_entry_says_something_useful(path):
    _, source, note = provenance.PROVENANCE[path]
    assert source in (provenance.MEASURED, provenance.DOCUMENT,
                      provenance.DERIVED, provenance.GUESS)
    assert len(note) >= 10


def test_the_default_profile_is_mostly_sourced_now():
    """Lulin is what the calculator opens on, so it is the one that has to be right.

    It began as guesswork throughout. Two thirds of it now traces to the
    observatory's published documents, its own frames, or a datasheet.
    """
    counts = provenance.summary(PRESETS)["lulin"]
    sourced = sum(counts.get(s, 0) for s in
                  (provenance.MEASURED, provenance.DOCUMENT, provenance.DERIVED))
    assert sourced / sum(counts.values()) > 0.7
    # The three per-band mu_dark entries moved from MEASURED to DERIVED when the
    # zodiacal split landed (QUESTIONS.md 9/10): they are still the photometry,
    # just with a model-supplied correction on top, so DERIVED absorbed them.
    assert counts.get(provenance.MEASURED, 0) >= 5
    assert counts.get(provenance.DERIVED, 0) >= 8


def test_nothing_a_calculation_leans_on_hardest_is_a_guess():
    """The values that set the count rate outright, for the bands with photometry.

    Geometry, bandpass, sky and throughput in g'r'i' all have sources. What is
    left as a guess is either absorbed by a measured product (the camera's flat
    QE), negligible at any realistic exposure (dark current), or confined to a
    band nobody has measured (u').
    """
    load_bearing = [
        "lulin.telescopes.LOT.primary_mirror_diameter",
        "lulin.telescopes.LOT.focal_length",
        "lulin.cameras.Sophia.pixel_pitch",
        "lulin.cameras.Sophia.readout_noise",
        "lulin.cameras.Sophia.full_well_capacity",
    ] + [f"lulin.filters.Sloan_{b}.{field}"
         for b in "gri"
         for field in ("central_wavelength", "filter_bandwidth", "filter_transmission",
                       "environment.mu_dark", "telescope.optical_throughput")]

    guesses = [p for p in load_bearing
               if provenance.PROVENANCE[p][1] == provenance.GUESS]
    assert guesses == []


def test_the_vlt_profile_is_still_mostly_invented():
    """Kept honest rather than quietly dropped.

    It is a hardware family, never the default, and nobody here observes with
    it — but it is in the file, and three quarters of it has no source. The one
    number known to be actively wrong is g_HIGH's, which over-predicts ESO's own
    calculator by 148%.
    """
    counts = provenance.summary(PRESETS)["vlt"]
    assert counts.get(provenance.GUESS, 0) > counts.get(provenance.DOCUMENT, 0)
    assert provenance.PROVENANCE[
        "vlt.filters.FORS2_g_HIGH.filter_transmission"][1] == provenance.GUESS
