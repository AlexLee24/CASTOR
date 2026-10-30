"""
Provenance — every number in a preset file has to say where it came from.

The rule began as a test over this repository's own presets.json, and the record
it checks still lives beside that test, in validation/provenance.py: where each
shipped number came from is a fact about this repository, not something the
package should carry. The rule itself is different. A host that writes a preset
file of its own wants its numbers held to the same standard, and a rule that
exists only as assertions in a directory the wheel does not ship can only be
copied — and a copy drifts from the original without anything to say so.

So the rule lives here, as functions over plain data:

  * walk(profiles)            every number a preset file holds, by dotted path
  * check(profiles, table)    what is wrong between a file and its record
  * load_table(path)          a record kept as JSON
  * summary(profiles, table)  how much of each profile has a source

`profiles` is the "profiles" object of a preset file exactly as JSON gives it,
not a loaded PresetFile: the record vouches for what the file holds, and
loading coerces. A table maps each path to a record, (value, class, note). The
value is the number the record vouches for, so a preset that changes while its
record does not is caught. The class is how the number is known, strongest
first:

    MEASURED   derived from the observatory's own frames
    DOCUMENT   a manufacturer datasheet or the observatory's published pages
    DERIVED    computed from a MEASURED or DOCUMENT value
    GUESS      no source. Believe nothing about it.

The note says which frames, which document or which computation, in at least
MIN_NOTE_LENGTH characters. GUESS is a class and not a failure — naming a guess
is the point; the failure is a number nobody accounted for.

Like presets.py, this sits outside src/castor/: the engine holds no hardware
data, so it has nothing to check.
"""
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import ConfigDict

from castor import schema

__all__ = [
    "CLASSES",
    "DERIVED",
    "DOCUMENT",
    "GUESS",
    "MEASURED",
    "MIN_NOTE_LENGTH",
    "Problem",
    "ProvenanceError",
    "check",
    "load_table",
    "summary",
    "walk",
]

MEASURED, DOCUMENT, DERIVED, GUESS = "MEASURED", "DOCUMENT", "DERIVED", "GUESS"

#: The four classes a record may give, strongest first.
CLASSES = (MEASURED, DOCUMENT, DERIVED, GUESS)

#: Shorter than this, a note cannot name a document, a frame set or a method.
MIN_NOTE_LENGTH = 10

# ==========================================
# Errors and findings
# ==========================================

class ProvenanceError(ValueError):
    """The table file itself is unusable — missing, unreadable, not UTF-8, not a JSON object.

    Anything wrong *inside* a usable table is a Problem instead, so that a broken
    table reports every fault at once rather than the first one.
    """

class Problem(schema.StrictModel):
    """One thing wrong between a preset file and its provenance table.

    `kind` is stable, so a host can count findings, translate them or deliberately
    set one rule aside; `message` is written for people and may be reworded.

        missing_record    the file holds a number the table has no record for
        orphan_record     the table has a record for a number the file does not hold
        value_mismatch    the record vouches for a different number than the file holds
        unknown_class     the record's class is not one of CLASSES
        short_note        the note is not text of at least MIN_NOTE_LENGTH characters
        malformed_record  the record is not a (value, class, note) triple
    """
    model_config = ConfigDict(frozen=True)

    path: str
    kind: Literal["missing_record", "orphan_record", "value_mismatch",
                  "unknown_class", "short_note", "malformed_record"]
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"

# ==========================================
# The rule
# ==========================================

def walk(profiles: Mapping[str, Any]) -> dict[str, Any]:
    """Every numeric leaf in a preset file, as dotted paths.

    `profiles` is the file's "profiles" object. Paths are the profile id followed
    by where the number sits, keys joined by dots exactly as the file spells them:

        <profile>.environment.<field>
        <profile>.environment.location.<field>
        <profile>.median_seeing_fwhm
        <profile>.telescopes.<id>.<field>      (and cameras, filters)
        <profile>.filters.<id>.environment.<field>
        <profile>.filters.<id>.telescope.<telescope id>.<field>

    Keys outside those sections — names, caveats, a host's own display
    metadata — carry no numbers CASTOR reads and are not walked.

    The order is fixed by section, not by how the file happens to be written.
    Profiles, entries and fields come in file order, but within a profile it is
    always environment, median seeing, telescopes, cameras, filters, and within
    a filter its own fields, then its environment, then its telescope overrides.
    """
    out = {}
    sections = (("telescopes", "telescope"), ("cameras", "camera"), ("filters", "optic_filter"))
    for profile_id, profile in profiles.items():
        environment = profile.get("environment") or {}
        for key, value in environment.items():
            if isinstance(value, dict):
                for inner, v in value.items():
                    out[f"{profile_id}.environment.{key}.{inner}"] = v
            else:
                out[f"{profile_id}.environment.{key}"] = value
        if profile.get("median_seeing_fwhm") is not None:
            out[f"{profile_id}.median_seeing_fwhm"] = profile["median_seeing_fwhm"]
        for catalogue, section in sections:
            for entry_id, entry in (profile.get(catalogue) or {}).items():
                for key, value in entry[section].items():
                    out[f"{profile_id}.{catalogue}.{entry_id}.{key}"] = value
                if catalogue != "filters":
                    continue
                for key, value in (entry.get("environment") or {}).items():
                    out[f"{profile_id}.{catalogue}.{entry_id}.environment.{key}"] = value
                # telescope is keyed by which telescope the override belongs to
                # (FilterEntry.telescope in castorCLI/presets.py) — one extra
                # level deeper than environment, which is site-wide and needs no key.
                for tel_key, tel_value in (entry.get("telescope") or {}).items():
                    for key, value in tel_value.items():
                        out[f"{profile_id}.{catalogue}.{entry_id}.telescope.{tel_key}.{key}"] = value
    return out

def check(profiles: Mapping[str, Any], table: Mapping[str, Any]) -> list[Problem]:
    """Everything wrong between a preset file and its provenance table.

    An empty list means the table covers the file exactly, in both directions,
    and every record says something useful:

      * every number in the file has a record, and every record a number — a
        record for a number that no longer exists is a source for nothing, and
        rots quietly;
      * each record's value equals the number the file holds, so a preset cannot
        change while keeping its old citation;
      * each class is one of CLASSES, and each note is text of at least
        MIN_NOTE_LENGTH characters.

    Every record is checked, including one with no number to vouch for. Problems
    come in a stable order: unrecorded numbers in walk() order, then the table's
    findings in table order.
    """
    values = walk(profiles)
    problems: list[Problem] = []

    for path, value in values.items():
        if path not in table:
            problems.append(Problem(
                path=path, kind="missing_record",
                message=f"the file holds {value!r} and the table does not say where it came from"))

    for path, entry in table.items():
        if not isinstance(entry, (tuple, list)) or len(entry) != 3:
            problems.append(Problem(
                path=path, kind="malformed_record",
                message=f"a record is (value, class, note), not {entry!r}"))
            continue

        recorded, source, note = entry
        if path not in values:
            problems.append(Problem(
                path=path, kind="orphan_record",
                message=f"the table records {recorded!r} for a number the file does not hold"))
        elif values[path] != recorded:
            problems.append(Problem(
                path=path, kind="value_mismatch",
                message=f"the file holds {values[path]!r} but its record vouches for {recorded!r}"))

        if source not in CLASSES:
            problems.append(Problem(
                path=path, kind="unknown_class",
                message=f"class {source!r} is not one of {', '.join(CLASSES)}"))
        if not isinstance(note, str) or len(note) < MIN_NOTE_LENGTH:
            problems.append(Problem(
                path=path, kind="short_note",
                message=f"note {note!r} is under {MIN_NOTE_LENGTH} characters — "
                        f"say which document, frames or computation"))

    return problems

def summary(profiles: Mapping[str, Any], table: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """How many values in this file have a source, by profile.

    Counts each profile's numbers by the class its record gives; a number with no
    record counts as "MISSING". Meant for a table check() has passed.
    """
    counts = {}
    # One profile at a time, rather than reading the id back off each path: an id
    # is any JSON key, and one with a dot in it would be split in the wrong place.
    for profile_id, profile in profiles.items():
        for path in walk({profile_id: profile}):
            source = table.get(path, (None, "MISSING", ""))[1]
            counts.setdefault(profile_id, {}).setdefault(source, 0)
            counts[profile_id][source] += 1
    return counts

# ==========================================
# Tables kept as JSON
# ==========================================

def load_table(path: Path | str) -> dict[str, Any]:
    """Reads a provenance table kept as JSON, {path: [value, class, note]}.

    Only the file's own shape is checked here: that it is UTF-8 text holding one
    JSON object, naming each path once. A path given twice would otherwise keep only its last record,
    and the first would vanish without ever being read. Whether each record is a
    well-formed triple is check()'s to report, alongside everything else.
    """
    source = Path(path)

    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProvenanceError(f"Cannot read provenance table at {source}: {exc}") from exc
    except UnicodeDecodeError as exc:
        # Windows PowerShell 5.1 writes UTF-16 when the export is redirected with >,
        # so this is the likeliest unreadable table there is, not a corner case.
        raise ProvenanceError(
            f"Cannot read provenance table at {source}: it is not UTF-8 text ({exc})") from exc

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise ProvenanceError(f"{source}: {key} is recorded twice")
            seen[key] = value
        return seen

    try:
        data = json.loads(raw, object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"{source} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProvenanceError(
            f"{source} should hold one object of path: [value, class, note], "
            f"not a {type(data).__name__}")

    return {key: tuple(entry) if isinstance(entry, list) else entry
            for key, entry in data.items()}
