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
"""
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from castor import schema

__all__ = [
    "DEFAULT_PATH",
    "PresetError",
    "PresetNotFound",
    "PresetFile",
    "Profile",
    "load",
]

# presets.json is not moved next to this module. Kinder vendors the repository and
# serves that path verbatim from its own presets route, and build.spec bundles the
# whole src/castorGUI/data directory into the desktop app; the reader moving is no
# reason for the data to move.
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "castorGUI" / "data" / "presets.json"

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
    has no sky to override and giving one here is rejected at load.
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
    # filter without one silently overwriting the other's.
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
        """
        profile = self.profile(profile_id)
        fragment: dict[str, Any] = {}

        if profile.environment is not None:
            fragment["environment"] = profile.environment.model_dump()

        instrument: dict[str, Any] = {}
        selection = self._selection(profile_id, profile, telescope, camera, optic_filter)
        for section, (_, entry) in selection.items():
            if entry is not None:
                instrument[section] = getattr(entry, section).model_dump()

        # The chosen filter has the last word on anything that depends on the band.
        # Applied after the site and the rig so it overrides them, and only for the
        # filter actually selected — the others describe a different bandpass.
        chosen_telescope_key = selection["telescope"][0]
        chosen = selection["optic_filter"][1]
        if chosen is not None:
            _overlay(fragment.get("environment"), chosen.environment)
            # Telescope-keyed: a filter's band-dependent efficiency belongs to
            # whichever telescope it was actually measured on, not to the filter
            # in the abstract — see FilterEntry.telescope's docstring.
            telescope_override = (chosen.telescope or {}).get(chosen_telescope_key)
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
        """
        profile = self.profile(profile_id)
        names = {"profile": profile.name or profile_id}

        selection = self._selection(profile_id, profile, telescope, camera, optic_filter)
        for section, (key, entry) in selection.items():
            if entry is not None:
                names[section] = entry.name or key

        return names

    def _selection(
        self,
        profile_id: str,
        profile: "Profile",
        telescope: str | None,
        camera: str | None,
        optic_filter: str | None,
    ) -> dict[str, tuple[str | None, Any]]:
        """The one place a set of requested names becomes a set of chosen entries."""
        return {
            "telescope": _pick(profile.telescopes, telescope, "telescope", profile_id),
            "camera": _pick(profile.cameras, camera, "camera", profile_id),
            "optic_filter": _pick(profile.filters, optic_filter, "filter", profile_id),
        }

# ==========================================
# Loading and selection
# ==========================================

def load(path: Path | str | None = None) -> PresetFile:
    """Reads and validates a preset file, defaulting to the one this repository ships."""
    source = Path(path) if path is not None else DEFAULT_PATH

    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise PresetError(f"Cannot read presets at {source}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PresetError(f"{source} is not valid JSON: {exc}") from exc

    presets = PresetFile.model_validate(data)

    # A filter may correct the sky it looks through, but only where there is a sky
    # to correct. Silently dropping the value would leave a number in the file that
    # looks applied and never is, which is the kind of thing this suite exists to
    # stop, so it is an error at load rather than a surprise at resolve.
    for profile_id, profile in presets.profiles.items():
        if profile.environment is not None:
            continue
        for filter_id, entry in profile.filters.items():
            if entry.environment is not None:
                raise PresetError(
                    f"{source}: profile {profile_id!r} has no environment of its own, "
                    f"so filter {filter_id!r} cannot override one. A profile without "
                    f"an environment block is a hardware family, not a site."
                )

    return presets

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
