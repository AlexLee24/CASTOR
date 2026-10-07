"""
Preset resolution — naming a site and a rig instead of spelling out the hardware.

An ObservationRequest carries around thirty required fields, most of which describe
equipment the observer did not choose and cannot change. data/presets.json already
names those combinations for the browser form; this module makes the same file
usable from Python, so a caller can say "Lulin, LOT, Sophia, Sloan r'" and get back
the fragments of the request those names stand for.

The resolution rules mirror frontend/js/etc.js (see the comment block above its
Presets section): first entry listed in a catalogue is the default, a profile fills
in a location only if it actually is a site, and median_seeing_fwhm is never applied.
The browser cannot run Python, so those rules necessarily exist in two places; what
this module is here to prevent is a third one appearing the moment a second Python
caller wants presets.

This module deliberately lives outside src/castor/. Hardware presets are out of
scope for the engine by design (docs/architecture.md §1.3, "No Hardware Databases"),
and Kinder sources its presets from a database rather than from this file — a core
module shaped around this JSON would be dead weight there.

The shipped file need not be the only one. A host can generate profiles of its own
(OWL does, from its hardware catalogue) and read them beside this repository's
sites: load() merges several files in the order given, search_path() is the list
a host reads when its caller names none, and a hardware name written PROFILE/KEY
takes that entry from another profile's catalogue — a backyard telescope under
Lulin's sky. docs/presets.md has the rules.
"""
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from castor import schema

__all__ = [
    "DEFAULT_PATH",
    "PATH_VARIABLE",
    "QUALIFIER",
    "PresetError",
    "PresetNotFound",
    "PresetFile",
    "Profile",
    "document",
    "load",
    "search_path",
]

# presets.json is not moved next to this module. Kinder vendors the repository and
# serves that path verbatim from its own presets route, and build.spec bundles the
# whole src/castorGUI/data directory into the desktop app; the reader moving is no
# reason for the data to move.
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "castorGUI" / "data" / "presets.json"

#: Further preset files a host reads after the shipped one, separated by os.pathsep
#: the way PATH is. Read by search_path(), and only there: load() never consults the
#: environment on its own, so a library caller gets the files it named and no others.
PATH_VARIABLE = "CASTOR_PRESETS_PATH"

#: Separates a profile id from a catalogue key in a qualified hardware name, as in
#: "other/RedCat51". Neither a profile id nor a catalogue key may contain it, which
#: load() enforces, so every entry can still be named both ways.
QUALIFIER = "/"

# ==========================================
# Errors
# ==========================================

class PresetError(ValueError):
    """Anything wrong with the preset file itself — missing, unreadable, malformed."""

class PresetNotFound(PresetError):
    """A name was asked for that the file does not offer.

    Carries the available names in its message: a caller picking presets by name is
    almost always a person typing them, and the useful answer to a typo is the list
    they meant to pick from.
    """

# ==========================================
# File shape
# ==========================================
#
# Leaves are the engine's own schema types, so a preset is validated as the literal
# subset of a request that it claims to be, and a misspelled field is rejected at
# load time by the StrictModel it belongs to. The envelopes around them stay lenient
# on purpose: the file carries a top-level "_comment" block, and hosts are free to
# hang their own display metadata off a profile without this loader rejecting it.

class _NamedEntry(BaseModel):
    """A catalogue entry's label. Falls back to the entry's key when absent, the way
    the form's dropdowns do."""
    name: str | None = None

class TelescopeEntry(_NamedEntry):
    telescope: schema.TelescopeSchema

class CameraEntry(_NamedEntry):
    camera: schema.CameraSchema

class BandSky(BaseModel):
    """What the sky looks like through one particular filter.

    Sky brightness is not a property of a place on its own. Measured at Lulin it
    runs 21.44 in g', 20.92 in r' and 20.04 in i' — 1.4 magnitudes apart, which is
    a factor of 3.8 in background flux, so a single site-wide figure is wrong for
    at least two bands whichever one it is. Extinction is band-dependent for the
    same reason and may be given here too, though Lulin's is not yet measured well
    enough to state.

    `mu_dark` here is the *local* baseline (airglow and light pollution) with the
    interplanetary part split back out; `zodiacal_share` is what fraction of the
    original, undecomposed measurement that split removed, letting the engine add
    a pointing-dependent term back on top. See QUESTIONS.md 9 and 10.

    Only the site's own values are overridden. A profile that is a hardware family
    has no sky to override and giving one here is rejected at load, and a filter
    taken from another profile by a qualified name leaves its own site's sky behind.
    """
    model_config = ConfigDict(extra="forbid")

    mu_dark: float | None = None
    zodiacal_share: float | None = None
    extinction_coeff: float | None = None


class BandTelescope(BaseModel):
    """The part of the optical train's efficiency that depends on the band.

    Everything between the sky and the electrons except the filter itself: mirrors,
    corrector, window, and the detector's response where it is not flat. CASTOR's
    request has one number for the telescope and one for the camera, both
    band-independent, so this is where a measurement that varies with wavelength
    has to land. Measured at Lulin it runs 0.10 to 0.57 across telescopes and bands.

    It goes on the filter rather than into filter_transmission because that field
    now holds the manufacturer's measured curve, and overwriting a number that can
    be checked against a published document with one that cannot is how the FORS2
    preset came to be wrong in every band but one.
    """
    model_config = ConfigDict(extra="forbid")

    optical_throughput: float | None = None


class FilterEntry(_NamedEntry):
    optic_filter: schema.FilterSchema

    # Fragments the filter contributes to the rest of the configuration, applied
    # only when this filter is the one selected. Shaped like the sections they
    # merge into, the same way every other fragment in the file is.
    #
    # `telescope` is keyed by the telescope catalogue key (e.g. "LOT", "SLT") and
    # applies only the entry matching whichever telescope is actually selected.
    # A plain BandTelescope (not telescope-keyed) would apply to any telescope
    # this filter is used with regardless of which one it was measured on — the
    # sky is one thing a site owns, but band-dependent optical efficiency is a
    # property of one specific telescope's optics, not of the filter alone, and
    # two telescopes at the same site can both carry a measurement for the same
    # filter without one silently overwriting the other's. The keys name telescopes
    # in the filter's own profile, so a telescope taken from another profile by a
    # qualified name matches none of them.
    environment: BandSky | None = None
    telescope: dict[str, BandTelescope] | None = None

class SiteEnvironment(BaseModel):
    """The slice of EnvironmentCondition that belongs to a place rather than a night.

    Not EnvironmentCondition itself: the time, the seeing and the FWHM budget are
    properties of the observation being planned, and a site cannot supply them.
    """
    location: schema.ObservatoryLocation
    mu_dark: float
    extinction_coeff: float

class Profile(BaseModel):
    """A site and the three catalogues it owns.

    A profile with an environment block is a real observing site. A profile without
    one is a hardware family (a telescope model, a shared instrument) and resolving
    it must leave the location alone — inventing coordinates for it would silently
    produce wrong airmass and moon geometry rather than an error.
    """
    name: str | None = None
    environment: SiteEnvironment | None = None

    #: Free text, shown by every host beside the profile's name and never written
    #: into a request. A profile whose numbers are not good enough to plan real
    #: observations with says so here, in the one place a user picking it will
    #: actually look. `provenance.py` records where each value came from, but that
    #: file is in the repository, not in front of someone choosing from a dropdown.
    caveat: str | None = None

    # Read by callers that want to show it, never written into a resolved request:
    # seeing is a condition of the night being planned, not a property of the site.
    median_seeing_fwhm: float | None = None

    telescopes: dict[str, TelescopeEntry] = Field(default_factory=dict)
    cameras: dict[str, CameraEntry] = Field(default_factory=dict)
    filters: dict[str, FilterEntry] = Field(default_factory=dict)

class PresetFile(BaseModel):
    """The parsed preset file.

    Key order is significant throughout and is preserved: JSON objects arrive in
    file order and dict keeps it, which is what makes "first entry listed is the
    default" a rule the file's author controls.
    """
    profiles: dict[str, Profile] = Field(default_factory=dict)

    def profile(self, profile_id: str) -> Profile:
        try:
            return self.profiles[profile_id]
        except KeyError:
            raise PresetNotFound(
                f"Unknown profile {profile_id!r}. Available: {_names(self.profiles)}"
            ) from None

    def resolve(
        self,
        profile_id: str,
        telescope: str | None = None,
        camera: str | None = None,
        optic_filter: str | None = None,
    ) -> dict[str, Any]:
        """Turns a set of names into the request fragments they stand for.

        Each catalogue defaults to its first listed entry, so naming only the site
        resolves to a complete, real configuration rather than to a half-filled one.
        The result is a plain dict holding only the parts a preset can speak for —
        the target, the timing and the calculation options are the caller's to add
        before it becomes an ObservationRequest.

        Any of the three may instead be a qualified name, PROFILE/KEY, taking that
        entry from another profile's catalogue. The site named by profile_id still
        supplies the location and the sky; only the named entry is borrowed, and a
        borrowed filter's band values apply only where they were measured (below).
        """
        profile = self.profile(profile_id)
        fragment: dict[str, Any] = {}

        if profile.environment is not None:
            fragment["environment"] = profile.environment.model_dump()

        instrument: dict[str, Any] = {}
        selection = self._selection(profile_id, telescope, camera, optic_filter)
        for section, (_, _, entry) in selection.items():
            if entry is not None:
                instrument[section] = getattr(entry, section).model_dump()

        # The chosen filter has the last word on anything that depends on the band.
        # Applied after the site and the rig so it overrides them, and only for the
        # filter actually selected — the others describe a different bandpass.
        telescope_owner, telescope_key, _ = selection["telescope"]
        filter_owner, _, chosen = selection["optic_filter"]
        if chosen is not None:
            # A filter's sky is its own site's sky through that band. Laid over
            # another site's, it would be a number measured somewhere else.
            if filter_owner == profile_id:
                _overlay(fragment.get("environment"), chosen.environment)
            # Telescope-keyed: a filter's band-dependent efficiency belongs to
            # whichever telescope it was actually measured on, not to the filter
            # in the abstract — see FilterEntry.telescope's docstring. Its keys
            # name telescopes in its own profile, so only one of those can match.
            if filter_owner == telescope_owner:
                telescope_override = (chosen.telescope or {}).get(telescope_key)
                _overlay(instrument.get("telescope"), telescope_override)

        if instrument:
            fragment["instrument"] = instrument

        return fragment

    def labels(
        self,
        profile_id: str,
        telescope: str | None = None,
        camera: str | None = None,
        optic_filter: str | None = None,
    ) -> dict[str, str]:
        """Display names for the same selection resolve() would make.

        Separate from resolve() because a resolved fragment is deliberately nothing
        but request data — a caller that wants to show which configuration produced a
        number needs the names too, and re-deriving "first entry listed wins" at the
        call site would put that rule in a second place.

        An entry taken from another profile that has no name of its own is shown by
        its qualified name, so the label still says where it came from.
        """
        profile = self.profile(profile_id)
        names = {"profile": profile.name or profile_id}

        selection = self._selection(profile_id, telescope, camera, optic_filter)
        for section, (owner, key, entry) in selection.items():
            if entry is not None:
                names[section] = entry.name or (
                    key if owner == profile_id else f"{owner}{QUALIFIER}{key}")

        return names

    def caveats(
        self,
        profile_id: str,
        telescope: str | None = None,
        camera: str | None = None,
        optic_filter: str | None = None,
    ) -> dict[str, str]:
        """The caveat of every profile the same selection draws on, by profile id.

        The site's own first, then those of the profiles any hardware was taken from,
        in the order telescope, camera, filter; a profile without one is left out.
        A caveat qualifies the numbers its profile supplies, and a camera nobody
        should plan with is no more trustworthy for being put under a measured sky.
        """
        # Checked here as resolve() and labels() check it: with every name qualified,
        # nothing on the way looks the site up, and an unknown one would surface as
        # a bare KeyError rather than as the PresetNotFound listing what there is.
        self.profile(profile_id)
        selection = self._selection(profile_id, telescope, camera, optic_filter)
        owners = dict.fromkeys(
            [profile_id, *(owner for owner, _, entry in selection.values() if entry is not None)])
        return {owner: self.profiles[owner].caveat for owner in owners if self.profiles[owner].caveat}

    def _selection(
        self,
        profile_id: str,
        telescope: str | None,
        camera: str | None,
        optic_filter: str | None,
    ) -> dict[str, tuple[str, str | None, Any]]:
        """The one place a set of requested names becomes a set of chosen entries.

        Each is (owner, key, entry): the profile whose catalogue the entry is in, its
        key there, and the entry — or (profile_id, None, None) when the site's
        catalogue is empty and nothing was asked of it.
        """
        return {
            "telescope": self._choose(profile_id, "telescopes", telescope, "telescope"),
            "camera": self._choose(profile_id, "cameras", camera, "camera"),
            "optic_filter": self._choose(profile_id, "filters", optic_filter, "filter"),
        }

    def _choose(
        self,
        profile_id: str,
        catalogue: str,
        requested: str | None,
        kind: str,
    ) -> tuple[str, str | None, Any]:
        """One selection, by plain or qualified name.

        A plain name is looked up in the site's own catalogue, a qualified one in the
        catalogue of the profile it names. Qualifying with the site's own profile id
        is the plain name written out in full and resolves identically.
        """
        owner = profile_id
        if requested is not None and QUALIFIER in requested:
            owner, requested = requested.split(QUALIFIER, 1)
        return (owner, *_pick(getattr(self.profile(owner), catalogue), requested, kind, owner))

# ==========================================
# Loading and selection
# ==========================================

def load(*paths: Path | str | None) -> PresetFile:
    """Reads, validates and merges preset files, defaulting to the one this repository ships.

    With no path it reads DEFAULT_PATH alone, as it always has, and None counts as
    no path — it is what callers of the single optional argument this used to take
    pass for "the default". It does not read PATH_VARIABLE: a host that wants the
    environment's files too asks for them, with load(*search_path()).

    Several files merge in the order given, one profile at a time:

      * profiles keep the order they are listed in, file by file, so the first
        file's first profile is still the one a host opens on;
      * a profile id defined in two files is an error naming both, never a quiet
        override, because whichever one lost would stay in a file looking used;
      * everything outside "profiles", each file's "_comment" block among it, is
        ignored, as it always was.

    Every rule a single file is held to applies to each profile in each file.
    """
    return _merge(_sources(paths))[0]

def search_path(default: Path | str = DEFAULT_PATH) -> list[Path]:
    """The preset files a host reads when its caller names none.

    The shipped file first, so its first profile stays the default, then each file
    PATH_VARIABLE lists, in order; empty entries are skipped, as in PATH. With the
    variable unset this is the shipped file alone, and every host that reads it
    behaves exactly as it did before the variable existed.

    `default` is for a host whose copy of the shipped file is not at DEFAULT_PATH.
    castorGUI's desktop build is one: PyInstaller unpacks the data directory beside
    the frozen modules rather than inside castorGUI/, so DEFAULT_PATH, worked out
    from this module's own location, names nothing there (see _asset_root in
    castorGUI/server.py).
    """
    extra = os.environ.get(PATH_VARIABLE, "")
    return [Path(default), *(Path(entry) for entry in extra.split(os.pathsep) if entry)]

def document(*paths: Path | str | None) -> dict[str, Any]:
    """The merged files as written, for a host that hands them on to a browser.

    load() parses; this keeps every profile exactly as its file holds it — no
    defaults filled in, no nulls added, key order intact — because the browser
    reads the document itself and applies the first entry it finds. Keys outside
    "profiles" come from the first file, so one file comes back the way json.loads
    would return it.

    All the same, it is validated exactly as load() validates. The browser skips a
    field it does not recognise without a word (docs/LESSONS.md, "The same physics
    implemented twice will drift, silently"), so a file the CLI would refuse must
    not reach it either.
    """
    return _merge(_sources(paths))[1]

def _sources(paths: tuple[Path | str | None, ...]) -> list[Path]:
    return [Path(path) for path in paths if path is not None] or [DEFAULT_PATH]

def _read(source: Path) -> Any:
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise PresetError(f"Cannot read presets at {source}: {exc}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PresetError(f"{source} is not valid JSON: {exc}") from exc

def _merge(sources: list[Path]) -> tuple[PresetFile, dict[str, Any]]:
    """Reads each file once and merges them in order, both parsed and as written."""
    parsed: dict[str, Profile] = {}
    written: dict[str, Any] = {}
    origin: dict[str, Path] = {}
    head: dict[str, Any] = {}

    for index, source in enumerate(sources):
        data = _read(source)
        try:
            part = PresetFile.model_validate(data)
        except ValidationError as exc:
            # Its location starts at "profiles", which does not say which file.
            exc.add_note(f"in {source}")
            raise
        if index == 0:
            head = data

        for profile_id, profile in part.profiles.items():
            if profile_id in origin:
                raise PresetError(
                    f"Profile {profile_id!r} is defined in both {origin[profile_id]} and "
                    f"{source}. One of the two would never be read, so rename one of them."
                )
            _check_profile(source, profile_id, profile)
            origin[profile_id] = source
            parsed[profile_id] = profile
            written[profile_id] = data["profiles"][profile_id]

    return PresetFile(profiles=parsed), {**head, "profiles": written}

def _check_profile(source: Path, profile_id: str, profile: Profile) -> None:
    """What a profile's shape cannot say about itself, checked once it is read."""
    # A qualified name splits at its QUALIFIER, so a profile id or a key holding one
    # could not be told from a qualified name and could not be asked for at all.
    for name in (profile_id, *profile.telescopes, *profile.cameras, *profile.filters):
        if QUALIFIER in name:
            raise PresetError(
                f"{source}: profile {profile_id!r} uses the name {name!r}, but "
                f"{QUALIFIER!r} separates a profile from a key in a qualified name "
                f"such as other/RedCat51, so neither may contain it."
            )

    # A filter may correct the sky it looks through, but only where there is a sky
    # to correct. Silently dropping the value would leave a number in the file that
    # looks applied and never is, which is the kind of thing this suite exists to
    # stop, so it is an error at load rather than a surprise at resolve.
    if profile.environment is not None:
        return
    for filter_id, entry in profile.filters.items():
        if entry.environment is not None:
            raise PresetError(
                f"{source}: profile {profile_id!r} has no environment of its own, "
                f"so filter {filter_id!r} cannot override one. A profile without "
                f"an environment block is a hardware family, not a site."
            )

def _overlay(target: dict[str, Any] | None, override: BaseModel | None) -> None:
    """Write a band's values over a section already resolved, in place.

    Fields left unset carry no opinion and leave the site or rig value standing,
    which is what makes a filter able to correct only its sky and say nothing about
    extinction. Nothing happens when there is no section to write into: a hardware
    family has no environment, and load() has already refused any filter that tried
    to give it one.
    """
    if target is None or override is None:
        return
    target.update({k: v for k, v in override.model_dump().items() if v is not None})


def _pick(
    catalogue: dict[str, Any],
    requested: str | None,
    kind: str,
    profile_id: str,
) -> tuple[str | None, Any]:
    """Resolves one catalogue selection to its (key, entry), or (None, None).

    An empty catalogue is not an error by itself — a profile is allowed to list no
    filters — but asking for one by name when none exist is, because the caller
    named something that will never be applied.
    """
    if requested is None:
        return next(iter(catalogue.items()), (None, None))

    try:
        return requested, catalogue[requested]
    except KeyError:
        raise PresetNotFound(
            f"Unknown {kind} {requested!r} for profile {profile_id!r}. "
            f"Available: {_names(catalogue)}"
        ) from None

def _names(entries: dict[str, Any]) -> str:
    return ", ".join(entries) if entries else "(none)"
