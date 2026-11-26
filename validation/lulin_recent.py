"""Refit Lulin's per-telescope sky (and, given zero points, throughput) from recent frames.

LOT and SLT share a mountain but not a sky: their stray light differs, and a band's
throughput drifts as mirrors age and cameras change. presets.json keeps what each
telescope measured where it belongs — `telescope.<TEL>` for throughput, `sky.<TEL>`
for the moonless sky, the band's `environment.moon_scale` for moonlight — and this
script recomputes those numbers from the newest calibrated frames, in the order
they depend on each other (validation/QUESTIONS.md 21):

    1. throughput  per telescope and band, from zero points (optional --zp):
                   measured ZP - CASTOR ZP for the same frame -> optical_throughput
    2. dark sky    per telescope and band, moonless frames -> sky.<TEL>.mu_dark
    3. moonlight   per band, both telescopes pooled -> environment.moon_scale

Each step uses the presets as the previous one left them: the sky is measured in
e-, so a throughput change moves it, and the moon is what remains above the dark
sky. Fitting them out of order is how the first pass of question 21 put a u'
throughput error into SLT's u' sky.

    python validation/lulin_recent.py measure <Calibrated_Science> --since 2026-01-01 > sky.jsonl
        (on the machine that holds the frames; read-only; needs astropy and numpy)
    python validation/lulin_recent.py fit sky.jsonl [--zp zp.csv] [--write]

`measure` takes up to --per-night frames per target, band and night, and records the
sigma-clipped median sky of the central 1024 px with the facts CASTOR needs to
predict it (time, pointing, exposure, gain, BUNIT, camera). `fit` prints every
number it would change, with the frames behind it, and changes presets.json only
with --write; validation/provenance.py then needs the new values and their source
(test_provenance.py says which).

--zp is a CSV with one row per frame: tel (LOT/SLT), band (u g r i z), dzp (measured
minus CASTOR zero point, mag, e.g. from calibration stars). A band's throughput moves
only when --min-zp-frames frames agree on more than --zp-tolerance.
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import math
import os
import re
import statistics as st
import sys
from datetime import timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESETS = ROOT / "src" / "castorGUI" / "data" / "presets.json"
BAND = {"u": "Sloan_u", "g": "Sloan_g", "r": "Sloan_r", "i": "Sloan_i", "z": "Sloan_z"}
NAME = re.compile(
    r"Calibrated_(?P<target>.+?)_D(?P<date>\d{4}-\d\d-\d\d)T\d{6}_T\d{6}_(?P<band>[ugriz])p_.*?_"
    r"(?P<tel>LOT|SLT)_(?P<cam>.*?)_bin1_gain(?P<gain>[\d_.]+)_(?P<exp>\d+)sec")


def camera_key(tel: str, cam: str) -> str:
    if tel == "LOT":
        return "Sophia"
    return "SLT_DU934P" if "DU934P" in cam else "SLT_DZ936"


# ---------------------------------------------------------------- measure

def measure(args: argparse.Namespace) -> None:
    import numpy as np
    from astropy.io import fits
    from astropy.stats import sigma_clipped_stats

    count: dict[tuple, int] = {}
    for path in sorted(glob.glob(os.path.join(args.root, "*", "Calibrated_*.fits"))):
        m = NAME.search(os.path.basename(path))
        if not m or m["date"] < args.since:
            continue
        key = (m["target"], m["band"], m["date"], m["tel"])
        if count.get(key, 0) >= args.per_night:
            continue
        count[key] = count.get(key, 0) + 1
        try:
            with fits.open(path, memmap=True) as hdul:
                h, data = hdul[0].header, hdul[0].data
                ny, nx = data.shape
                core = data[ny // 2 - 512:ny // 2 + 512, nx // 2 - 512:nx // 2 + 512].astype(float)
            _, sky, std = sigma_clipped_stats(core, sigma=3, maxiters=5)
            diff = (core[:, 1:] - core[:, :-1]).ravel()
            _, _, dstd = sigma_clipped_stats(diff, sigma=3, maxiters=5)
            record = dict(
                file=os.path.basename(path), target=m["target"], band=m["band"], tel=m["tel"],
                cam=camera_key(m["tel"], m["cam"]), gain=float(m["gain"].replace("_", ".")),
                exptime=float(h.get("EXPTIME") or m["exp"]), date=h.get("DATE-OBS"),
                ra=h.get("CRVAL1"), dec=h.get("CRVAL2"), bunit=h.get("BUNIT"),
                sky=float(sky), pix_std=float(dstd / np.sqrt(2)))
        except Exception as exc:                      # a damaged frame is skipped, and said so
            record = dict(file=os.path.basename(path), error=str(exc))
        print(json.dumps(record), flush=True)


# ---------------------------------------------------------------- fit

def _nl(mu: float) -> float:
    return 34.08 * 10.0 ** (0.4 * (22.5 - mu))


def _frames(path: str) -> list[dict]:
    out = []
    for line in open(path):
        rec = json.loads(line)
        if "crval" in rec and rec.get("crval") and rec["crval"][0] is not None:   # older measure output
            rec["ra"], rec["dec"] = rec["crval"]
        if "error" in rec or rec.get("ra") is None or not rec.get("date") or rec.get("band") not in BAND:
            continue
        if rec["cam"] not in ("Sophia", "SLT_DZ936", "SLT_DU934P"):
            rec["cam"] = camera_key(rec["tel"], rec["cam"])
        out.append(rec)
    return out


def _evaluate(doc: dict, frames: list[dict]) -> list[dict]:
    """Per frame: the measured sky in nanolamberts as CASTOR's throughput sees it,
    CASTOR's dark (mu_dark + zodiacal) and unscaled KS91 parts, and the geometry."""
    sys.path.insert(0, str(ROOT / "src"))
    import astropy.units as u
    from astropy.time import Time
    from castor import moon, schema
    from castor.calculator import run_calculation
    from castorCLI import presets
    from castorCLI.main import ASSUMPTIONS

    catalogue = presets.PresetFile.model_validate(doc)
    out = []
    for rec in frames:
        frag = catalogue.resolve("lulin", rec["tel"], rec["cam"], BAND[rec["band"]])
        env = frag["environment"]
        mid = Time(rec["date"], format="isot", scale="utc") + rec["exptime"] / 2 * u.s
        req = dict(frag)
        req["target"] = {"ra": float(rec["ra"]), "dec": float(rec["dec"]), "morphology": {"type": "point"},
                         "sed": {"type": "flat"}, "brightness": {"type": "ab_mag", "target_mag": 18.0}}
        req["environment"] = {**env, "total_fwhm": 2.5, "auto_calc_background": True,
                              "observing_time_utc": mid.to_datetime(timezone=timezone.utc).isoformat()}
        req["options"] = {"type": "solve_snr", "single_exp_time": rec["exptime"], "num_exposures": 1}
        for dotted, value, _ in ASSUMPTIONS:
            node = req
            *parts, last = dotted.split(".")
            for part in parts:
                node = node.setdefault(part, {})
            node.setdefault(last, value)
        res = run_calculation(schema.ObservationRequest.model_validate(req))
        gain = 1.0 if str(rec.get("bunit") or "").lower().startswith("electron") else rec["gain"]
        sky_e = rec["sky"] * gain / rec["exptime"]
        if sky_e <= 0 or res.budget.sky_count_rate <= 0:
            continue
        loc = env["location"]
        alpha, rho, zm, zt = moon.get_moon_and_target_geometry(
            float(rec["ra"]), float(rec["dec"]), mid.isot, loc["longitude_deg"], loc["latitude_deg"], loc["elevation_m"])
        k_moon = env.get("moon_extinction_coeff") or env["extinction_coeff"]
        moon_up = float(zm) < 90.0
        out.append(dict(
            tel=rec["tel"], band=rec["band"], date=rec["date"][:10],
            measured=_nl(res.diagnostics.sky_surface_brightness) * sky_e / res.budget.sky_count_rate,
            dark=_nl(moon.apply_zodiacal_baseline(env["mu_dark"], float(rec["ra"]), float(rec["dec"]), env.get("zodiacal_share"))),
            ks=float(moon.krisciunas_schaefer_1991(alpha, rho, zm, zt, k_ext_v=k_moon)) if moon_up else 0.0,
            moon_up=moon_up, sun_alt=res.ephemeris.sun_elevation_deg, mu_dark=env["mu_dark"]))
    return out


def _scale_to_zero_median(rows: list[dict], dark_scale: dict) -> float:
    """The moon multiple that leaves the median moonlit residual at zero."""
    def residual(s: float) -> float:
        return st.median(-2.5 * math.log10(r["measured"] / (dark_scale[r["tel"]] * r["dark"] + s * r["ks"]))
                         for r in rows)
    lo, hi = 0.0, 20.0
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if residual(mid) > 0 else (mid, hi)
    return (lo + hi) / 2


def fit(args: argparse.Namespace) -> None:
    doc = json.loads(PRESETS.read_text())
    lulin = doc["profiles"]["lulin"]
    frames = _frames(args.sky)
    changes: list[str] = []

    # 1. throughput, per telescope and band, from zero points
    if args.zp:
        byband = collections.defaultdict(list)
        for row in csv.DictReader(open(args.zp)):
            if row.get("band") in BAND and row.get("dzp") not in ("", None):
                byband[(row["tel"], row["band"])].append(float(row["dzp"]))
        print("1. throughput (measured - CASTOR zero point)")
        for (tel, band), dz in sorted(byband.items()):
            med = st.median(dz)
            entry = lulin["filters"][BAND[band]].setdefault("telescope", {}).setdefault(tel, {})
            old = entry.get("optical_throughput") or lulin["telescopes"][tel]["telescope"]["optical_throughput"]
            move = len(dz) >= args.min_zp_frames and abs(med) > args.zp_tolerance
            new = round(old * 10 ** (0.4 * med), 3)
            print(f"   {tel} {band}': {len(dz):3d} frames, median {med:+.3f} mag -> "
                  + (f"optical_throughput {old} -> {new}" if move else "kept"))
            if move:
                entry["optical_throughput"] = new
                changes.append(f"{BAND[band]}.telescope.{tel}.optical_throughput {old} -> {new}")

    rows = _evaluate(doc, frames)
    night = [r for r in rows if r["sun_alt"] < -18]

    # 2. moonless sky, per telescope and band
    print("2. moonless sky (sky.<TEL>.mu_dark)")
    dark_scale: dict[tuple, float] = {}
    for tel in ("LOT", "SLT"):
        for band in BAND:
            dark = [r for r in night if r["tel"] == tel and r["band"] == band and not r["moon_up"]]
            if len(dark) < args.min_frames:
                print(f"   {tel} {band}': {len(dark)} moonless frames, kept")
                dark_scale[(tel, band)] = 1.0
                continue
            ds = st.median(r["measured"] / r["dark"] for r in dark)
            dark_scale[(tel, band)] = ds
            old = st.median(r["mu_dark"] for r in dark)
            new = round(old - 2.5 * math.log10(ds), 2)
            f = lulin["filters"][BAND[band]]
            base = f.get("environment", {}).get("mu_dark", lulin["environment"]["mu_dark"])
            own = (f.get("sky") or {}).get(tel, {})
            # A telescope keeps its own sky only where it differs from the band's by more
            # than the noise of a median over nights; inside that, the band's measured
            # value stands and an override would only be a second copy of it.
            want = new if abs(new - base) >= args.sky_tolerance else None
            print(f"   {tel} {band}': {len(dark):4d} moonless frames, mu_dark {old} -> {new}"
                  + ("" if want is not None else f" (within {args.sky_tolerance} of the band's {base}: band value)"))
            if want is not None and own.get("mu_dark") != want:
                f.setdefault("sky", {}).setdefault(tel, {})["mu_dark"] = want
                changes.append(f"{BAND[band]}.sky.{tel}.mu_dark {own.get('mu_dark', base)} -> {want}")
            elif want is None and "mu_dark" in own:
                del own["mu_dark"]
                if not own:
                    del f["sky"][tel]
                if not f["sky"]:
                    del f["sky"]
                changes.append(f"{BAND[band]}.sky.{tel}.mu_dark {old} -> removed (band's {base})")

    # 3. moonlight, per band, both telescopes
    print("3. moonlight (environment.moon_scale)")
    for band in BAND:
        lit = [r for r in night if r["band"] == band and r["moon_up"]]
        env = lulin["filters"][BAND[band]].setdefault("environment", {})
        if len(lit) < args.min_frames:
            print(f"   {band}': {len(lit)} moonlit frames, kept")
            continue
        old = env.get("moon_scale", 1.0)
        s_unit = _scale_to_zero_median(lit, {t: dark_scale[(t, band)] for t in ("LOT", "SLT")})
        new = round(s_unit, 2)                      # ks is unscaled KS91, so this is the whole multiple
        spread = st.median(abs(-2.5 * math.log10(r["measured"] / (dark_scale[(r["tel"], band)] * r["dark"] + s_unit * r["ks"])))
                           for r in lit)
        print(f"   {band}': {len(lit):4d} moonlit frames, moon_scale {old} -> {new} (typical |residual| {spread:.2f} mag)")
        if abs(new - old) >= 0.05:
            env["moon_scale"] = new
            changes.append(f"{BAND[band]}.environment.moon_scale {old} -> {new}")

    print(f"\n{len(changes)} change(s)" + (":" if changes else "."))
    for c in changes:
        print("  ", c)
    if args.write and changes:
        PRESETS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"written to {PRESETS}; add each value's source to validation/provenance.py")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("measure", help="sky of each calibrated frame, as JSON lines on stdout")
    m.add_argument("root", help="Calibrated_Science folder (one sub-folder per target)")
    m.add_argument("--since", default="2026-01-01", help="first night, YYYY-MM-DD")
    m.add_argument("--per-night", type=int, default=2, help="frames per target, band and night")
    m.set_defaults(run=measure)
    f = sub.add_parser("fit", help="refit throughput, moonless sky and moonlight")
    f.add_argument("sky", help="JSON lines from measure")
    f.add_argument("--zp", help="CSV of per-frame zero-point offsets: tel, band, dzp")
    f.add_argument("--min-frames", type=int, default=20, help="frames a sky number needs")
    f.add_argument("--sky-tolerance", type=float, default=0.05, help="mag a telescope's sky must differ from the band's to keep its own")
    f.add_argument("--min-zp-frames", type=int, default=5, help="frames a throughput change needs")
    f.add_argument("--zp-tolerance", type=float, default=0.15, help="mag a throughput change must exceed")
    f.add_argument("--write", action="store_true", help="write the changes into presets.json")
    f.set_defaults(run=fit)
    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
