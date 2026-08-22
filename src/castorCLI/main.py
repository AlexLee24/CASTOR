"""
castor — a command line over the exposure time calculator.

    python src/castorCLI/main.py calc --site lulin --ra 113.65 --dec 31.89 \
        --mag 18 --exp 300 -n 10

Written for callers who should not be inventing physics, which in practice means
agents at least as much as people. An ObservationRequest carries around thirty
required fields, and castor.schema deliberately gives several of them no default —
leaving aperture_factor undefaulted is how the contract makes a caller state it out
loud. A caller that answers a missing required field by picking a plausible-looking
number gets no error and no warning back, just a confident wrong SNR.

So this tool never quietly supplies a measurement. Every value it fills in comes
from one of three places, and it says which:

  * a named preset — a real site's own numbers (see presets.py),
  * a convention, listed in ASSUMPTIONS below and reported on every run,
  * the caller, via flags, --set, or a saved request file.

Anything still missing is an error naming the field, in the same format the HTTP
API returns, rather than a guess.

Run it straight from a checkout, the way server.py is run; the sys.path line below
is what makes that work without installing anything.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from castor import schema  # noqa: E402
from castor.calculator import run_calculation  # noqa: E402
from castorCLI import presets  # noqa: E402

# A result that saturates is still a computed result, so it leaves by the front door
# rather than as an error — but not with the exit code of an unremarkable success.
# Every caller checks the exit code; not every caller reads flags.is_saturated.
EXIT_SATURATED = 1
EXIT_INPUT = 3

# What this tool is willing to fill in, and why each one is a convention rather than
# a measurement. Reported on every run so that "the CLI chose this" never looks like
# "the observer meant this".
ASSUMPTIONS: tuple[tuple[str, Any, str], ...] = (
    ("target.morphology.type", "point", "a choice of contract, not a measurement"),
    ("target.sed.type", "flat", "a choice of contract, not a measurement"),
    ("target.brightness.type", "ab_mag", "the one brightness type needing no zero point"),
    ("instrument.throughput_correction", 1.0, "means no correction, not a measured one"),
    ("options.aperture_factor", 1.5, "the aperture convention the web form has always sent"),
    ("environment.auto_calc_background", True, "layers the real moon over the site's dark sky"),
    ("environment.diffraction_fwhm", 0.2, "form default — really depends on aperture and band"),
    ("environment.optical_fwhm", 0.1, "form default — really a property of these optics"),
    ("environment.tracking_fwhm", 0.1, "form default — really a property of this mount"),
)

# ==========================================
# Dotted paths
# ==========================================

MISSING = object()

def _get_path(data: dict, dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node

def _set_path(data: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise click.ClickException(f"Cannot set {dotted}: {part} is not a section.")
    node[parts[-1]] = value

def _deep_merge(base: dict, overlay: dict) -> dict:
    """Section-aware merge, so a preset's instrument does not wipe a file's target."""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged

def _parse_set(item: str) -> tuple[str, Any]:
    if "=" not in item:
        raise click.BadParameter(f"{item!r} is not path=value.", param_hint="--set")

    path, raw = item.split("=", 1)
    try:
        # JSON first so numbers arrive as numbers and true/false/null work; a bare
        # word like Temp is not valid JSON and is meant literally.
        return path.strip(), json.loads(raw)
    except json.JSONDecodeError:
        return path.strip(), raw

# ==========================================
# Reporting
# ==========================================

def _format_errors(exc: ValidationError) -> str:
    """The same flattening server.py returns over HTTP, so a field named by the API
    is named identically here."""
    return "; ".join(
        "{}: {}".format(".".join(str(part) for part in err["loc"]), err["msg"])
        for err in exc.errors()
    ) or "Invalid input"

def _header(labels: dict[str, str] | None, request: schema.ObservationRequest) -> list[str]:
    configuration = " · ".join(labels.values()) if labels else "custom configuration"
    brightness = request.target.brightness
    described = getattr(brightness, "target_mag", None)
    described = (
        f"{brightness.type.replace('_mag', '').upper()} {described:g}"
        if described is not None
        else f"{brightness.type} {getattr(brightness, 'flux_value', '')}"
    )
    return [
        configuration,
        "{} · {} at RA {:.4f} Dec {:+.4f}".format(
            request.environment.observing_time_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            described,
            request.target.ra,
            request.target.dec,
        ),
    ]

def _results(request: schema.ObservationRequest, response: schema.ObservationResponse) -> list[str]:
    core = response.core
    single = request.options.single_exp_time
    frames = core.required_exposures if core.required_exposures is not None else getattr(request.options, "num_exposures", None)

    rows = [
        ("Total SNR", f"{core.total_snr:.2f}"),
        ("Single-frame SNR", f"{core.single_snr:.2f}"),
    ]
    if core.required_exposures is not None:
        rows.append(("Exposures needed", f"{core.required_exposures}"))
    if frames:
        rows.append(("Total time", f"{frames * single:.0f} s  ({frames} × {single:g} s)"))
    rows += [
        ("Saturates after", f"{core.saturation_time_limit:.1f} s"),
        ("Background-limited at", f"{core.optimal_exposure_time:.1f} s"),
        ("Total FWHM", f'{response.diagnostics.total_fwhm:.2f}"'),
    ]
    return [f"  {label:<22}{value}" for label, value in rows]

def _emit_notes(assumed: list[tuple[str, Any, str]], ignored: list[str],
                response: schema.ObservationResponse, request: schema.ObservationRequest) -> None:
    """Everything the caller did not ask for goes to stderr, so stdout stays the answer."""
    if ignored:
        click.echo("ignored (a saved form holds more than a request does): "
                   + ", ".join(ignored), err=True)

    if assumed:
        click.echo("\nassumed (pass the flag or --set to state it yourself):", err=True)
        for path, value, why in assumed:
            click.echo(f"  {path} = {value!r}  — {why}", err=True)

    for warning in response.flags.warnings:
        click.echo(f"warning: {warning}", err=True)

    if response.flags.is_saturated:
        click.echo(
            "SATURATED: a {:g} s exposure passes the {:.1f} s full-well limit — "
            "the SNR above is not reachable in one frame. Lower --exp.".format(
                request.options.single_exp_time, response.core.saturation_time_limit
            ),
            err=True,
        )

# ==========================================
# Commands
# ==========================================

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """CASTOR — exposure time calculator.

    Exit codes: 0 ok · 1 the result saturates · 2 bad usage · 3 bad input.
    """

@cli.command()
@click.option("--site", help="Observing profile; fills in the site's sky and its hardware.")
@click.option("--telescope", help="Telescope within the site (default: the first it lists).")
@click.option("--camera", help="Camera within the site (default: the first it lists).")
@click.option("--filter", "optic_filter", help="Filter within the site (default: the first it lists).")
@click.option("--ra", type=float, help="Right ascension, degrees J2000.")
@click.option("--dec", type=float, help="Declination, degrees J2000.")
@click.option("--mag", type=float, help="Target magnitude (AB unless --set says otherwise).")
@click.option("--exp", type=float, help="Single exposure time, seconds.")
@click.option("-n", "--exposures", type=int, help="Number of frames; solves for SNR.")
@click.option("--snr", type=float, help="Target SNR; solves for the number of frames.")
@click.option("--seeing", type=float, help='Seeing FWHM, arcsec (default: the site median, if it has one).')
@click.option("--time", "at_time", help="Observation time, ISO 8601 UTC (default: now).")
@click.option("--request", "request_file", type=click.Path(path_type=Path),
              help="Saved request to start from; '-' reads stdin. The web form's SAVE writes this shape.")
@click.option("--set", "overrides", multiple=True, metavar="PATH=VALUE",
              help="Override any field by dotted path, e.g. --set environment.mu_dark=20.8. Repeatable.")
@click.option("--presets-file", type=click.Path(path_type=Path), help="Alternative presets.json.")
@click.option("--json", "as_json", is_flag=True, help="Emit request, response and assumptions as JSON.")
def calc(site, telescope, camera, optic_filter, ra, dec, mag, exp, exposures, snr,
         seeing, at_time, request_file, overrides, presets_file, as_json) -> None:
    """Run one exposure time calculation.

    Layered in this order, each winning over the last: --request file, --site preset,
    the flags above, then --set.
    """
    if exposures is not None and snr is not None:
        raise click.UsageError("--exposures and --snr are the two directions of the same question; pick one.")

    data: dict[str, Any] = {}
    labels = None
    catalogue = None

    if request_file is not None:
        data = _deep_merge(data, _read_request(request_file))

    if site is not None:
        catalogue = _load_presets(presets_file)
        try:
            data = _deep_merge(data, catalogue.resolve(site, telescope, camera, optic_filter))
            labels = catalogue.labels(site, telescope, camera, optic_filter)
        except presets.PresetNotFound as exc:
            raise SystemExit(_fail(exc))
    elif any(name is not None for name in (telescope, camera, optic_filter)):
        raise click.UsageError("--telescope/--camera/--filter name entries within a --site.")

    # -n and --snr are not just values, they are the choice of which question is being
    # asked; the discriminator follows from the flag rather than having to be set twice.
    if exposures is not None:
        _set_path(data, "options.type", "solve_snr")
    if snr is not None:
        _set_path(data, "options.type", "solve_time")

    for path, value in (
        ("target.ra", ra),
        ("target.dec", dec),
        ("target.brightness.target_mag", mag),
        ("options.single_exp_time", exp),
        ("options.num_exposures", exposures),
        ("options.target_snr", snr),
        ("environment.seeing_fwhm", seeing),
        ("environment.observing_time_utc", at_time),
    ):
        if value is not None:
            _set_path(data, path, value)

    for item in overrides:
        _set_path(data, *_parse_set(item))

    assumed = _apply_conventions(data, site, catalogue)

    if _get_path(data, "options.type") is MISSING:
        raise click.UsageError(
            "Nothing to solve for: give -n/--exposures for the SNR of that many frames, "
            "or --snr for the frames needed to reach it."
        )

    try:
        request, ignored = _validate(data, tolerate_extras=request_file is not None)
    except ValidationError as exc:
        raise SystemExit(_fail(_format_errors(exc)))

    response = run_calculation(request)

    if as_json:
        click.echo(json.dumps({
            "assumed": [{"path": path, "value": value, "why": why} for path, value, why in assumed],
            "ignored": ignored,
            "request": json.loads(request.model_dump_json()),
            "response": json.loads(response.model_dump_json()),
        }, indent=2))
    else:
        click.echo("\n".join(_header(labels, request) + [""] + _results(request, response)))
        _emit_notes(assumed, ignored, response, request)

    if response.flags.is_saturated:
        raise SystemExit(EXIT_SATURATED)

@cli.command(name="presets")
@click.option("--presets-file", type=click.Path(path_type=Path), help="Alternative presets.json.")
@click.option("--json", "as_json", is_flag=True, help="Emit the preset file itself.")
def list_presets(presets_file, as_json) -> None:
    """List the sites and hardware --site can name. A * marks each catalogue's default."""
    catalogue = _load_presets(presets_file)

    if as_json:
        click.echo(catalogue.model_dump_json(indent=2))
        return

    for profile_id, profile in catalogue.profiles.items():
        click.echo(f"{profile_id}  —  {profile.name or profile_id}")

        if profile.environment is None:
            click.echo("    hardware only: supply the location yourself, it will not be invented")
        else:
            site = profile.environment
            click.echo(
                "    site  lat {:g} lon {:g} {:g} m · mu_dark {:g} · k_ext {:g}".format(
                    site.location.latitude_deg, site.location.longitude_deg,
                    site.location.elevation_m, site.mu_dark, site.extinction_coeff,
                )
            )
        if profile.median_seeing_fwhm is not None:
            click.echo(f'    median seeing {profile.median_seeing_fwhm:g}" — used only if --seeing is omitted')

        for kind, entries in (("telescopes", profile.telescopes),
                              ("cameras", profile.cameras),
                              ("filters", profile.filters)):
            if entries:
                shown = ", ".join(
                    f"{key}{'*' if index == 0 else ''} ({entry.name})" if entry.name else f"{key}{'*' if index == 0 else ''}"
                    for index, (key, entry) in enumerate(entries.items())
                )
                click.echo(f"    {kind:<11} {shown}")
        click.echo("")

@cli.command(name="schema")
@click.option("--batch", is_flag=True, help="The time-series contract instead of the single-point one.")
def dump_schema(batch) -> None:
    """Print the JSON Schema of a request, for building one --set at a time."""
    model = schema.BatchObservationRequest if batch else schema.ObservationRequest
    click.echo(json.dumps(model.model_json_schema(), indent=2))

# ==========================================
# Wiring
# ==========================================

def _validate(data: dict, tolerate_extras: bool) -> tuple[schema.ObservationRequest, list[str]]:
    """Validates, optionally dropping fields a request has no room for.

    The web form's SAVE writes a superset of a request on purpose: it keeps every
    branch of every discriminated union so that switching brightness type after a
    load does not find the fields blank, and it carries the batch panel's own state
    besides. Feeding one back is a thing people will reasonably try, so the extras
    are dropped rather than refused — but only for a file the caller pointed at, and
    never silently. A stray --set path stays an error, because there it is a typo.

    The schema decides what is extra; nothing here keeps a second list of the fields
    a request may hold.
    """
    dropped: list[str] = []

    for _ in range(64):
        try:
            return schema.ObservationRequest.model_validate(data), dropped
        except ValidationError as exc:
            extras = [err["loc"] for err in exc.errors() if err["type"] == "extra_forbidden"]
            if not extras or not tolerate_extras:
                raise
            for loc in extras:
                removed = _drop_path(data, loc)
                if removed:
                    dropped.append(removed)

    raise click.ClickException("Gave up pruning the request; it holds more extra fields than expected.")

def _drop_path(data: dict, loc: tuple) -> str | None:
    """Removes one field pydantic rejected.

    A tagged union puts the tag it matched into the error location, and that tag is
    not a key in the data, so components that are not there are walked past rather
    than treated as a miss.
    """
    node: Any = data
    trail: list[str] = []

    for part in loc[:-1]:
        if isinstance(node, dict) and part in node:
            node = node[part]
            trail.append(str(part))

    leaf = loc[-1]
    if isinstance(node, dict) and leaf in node:
        del node[leaf]
        return ".".join(trail + [str(leaf)])
    return None

def _load_presets(presets_file: Path | None) -> presets.PresetFile:
    try:
        return presets.load(presets_file)
    except (presets.PresetError, ValidationError) as exc:
        message = _format_errors(exc) if isinstance(exc, ValidationError) else str(exc)
        raise SystemExit(_fail(message))

def _read_request(path: Path) -> dict:
    try:
        raw = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(_fail(f"Cannot read {path}: {exc}"))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(_fail(f"{path} is not valid JSON: {exc}"))

    if not isinstance(data, dict):
        raise SystemExit(_fail(f"{path} should hold a request object."))
    return data

def _apply_conventions(data: dict, site: str | None, catalogue: presets.PresetFile | None
                       ) -> list[tuple[str, Any, str]]:
    """Fills the gaps this tool is allowed to fill, and records every one of them."""
    assumed: list[tuple[str, Any, str]] = []

    if _get_path(data, "environment.observing_time_utc") is MISSING:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        _set_path(data, "environment.observing_time_utc", now.isoformat())
        assumed.append(("environment.observing_time_utc", now.isoformat(),
                        "now — the moon and the airmass both move"))

    # Seeing belongs to the night, not the site, which is why a preset never applies
    # it. Falling back to the site's published median is still a stated figure rather
    # than an invented one, so it is allowed here as long as it is reported.
    if _get_path(data, "environment.seeing_fwhm") is MISSING and catalogue is not None and site is not None:
        median = catalogue.profile(site).median_seeing_fwhm
        if median is not None:
            _set_path(data, "environment.seeing_fwhm", median)
            assumed.append(("environment.seeing_fwhm", median,
                            f"{site}'s published median, not tonight's seeing"))

    for path, value, why in ASSUMPTIONS:
        if _get_path(data, path) is MISSING:
            _set_path(data, path, value)
            assumed.append((path, value, why))

    return assumed

def _fail(message: object) -> int:
    click.echo(f"error: {message}", err=True)
    return EXIT_INPUT

if __name__ == "__main__":
    cli()
