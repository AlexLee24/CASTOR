"""Where each number in presets.json came from.

The file was written before anything could check it, and when the checks arrived
every value that had one turned out wrong — four filters that were placeholders,
a throughput 2.6x high, a telescope carrying its neighbour's focal ratio, a
camera with the wrong sensor's pixels. That is not what a partly-sourced file
looks like. It is what an invented one looks like, and the right prior for
anything still unaccounted for is that it was invented too.

So every value is listed here with its origin, and `test_provenance.py` fails if
the file holds a number this table does not, or holds a different number than
the one recorded. Changing a preset now means saying where the new value came
from. Values marked GUESS are not defects to be hidden — they are the honest
state of the file, and the point of naming them is that nobody has to rediscover
which ones they are.

Sources, strongest first:

    MEASURED   derived from the observatory's own frames in this suite
    DOCUMENT   a manufacturer datasheet or the observatory's published pages
    DERIVED    computed from a MEASURED or DOCUMENT value
    GUESS      no source. Believe nothing about it.
"""
MEASURED, DOCUMENT, DERIVED, GUESS = "MEASURED", "DOCUMENT", "DERIVED", "GUESS"

#: path -> (value, source, note)
PROVENANCE = {
    # ---- Lulin, the site ----------------------------------------------------
    "lulin.environment.location.latitude_deg": (23.47, DOCUMENT, "site pages give 23.469447; frame SITELAT 23.4686"),
    "lulin.environment.location.longitude_deg": (120.87, DOCUMENT, "site pages give 120.872624; frame SITELONG 120.8736"),
    "lulin.environment.location.elevation_m": (2862.0, DOCUMENT, "site pages and frame SITEELEV agree"),
    "lulin.environment.mu_dark": (21.5, GUESS, "fallback only; g'r'i' measured on their filters"),
    "lulin.environment.extinction_coeff": (0.17, GUESS, "fit inconclusive, see QUESTIONS.md 3"),
    "lulin.median_seeing_fwhm": (1.4, GUESS, "no source, but 123 frames give a median FWHM of 1.34\""),

    # ---- Lulin, LOT ---------------------------------------------------------
    "lulin.telescopes.LOT.primary_mirror_diameter": (1.0, DOCUMENT, "site pages; frame APTDIA 1000 mm"),
    "lulin.telescopes.LOT.secondary_mirror_diameter": (0.3, GUESS, "frame APTAREA implies 0.130; see QUESTIONS.md 2"),
    "lulin.telescopes.LOT.focal_length": (8.054, DERIVED, "reproduces the 0.3841\"/pix the frames solve"),
    "lulin.telescopes.LOT.optical_throughput": (0.381, MEASURED, "geometric mean; g'r'i' carry their own"),

    # ---- Lulin, SLT ---------------------------------------------------------
    "lulin.telescopes.SLT.primary_mirror_diameter": (0.406, DOCUMENT, "site pages, 16 inch"),
    "lulin.telescopes.SLT.secondary_mirror_diameter": (0.12, GUESS, "not published"),
    "lulin.telescopes.SLT.focal_length": (3.414, DERIVED, "site pages, f/8.4 on 0.406 m"),
    "lulin.telescopes.SLT.optical_throughput": (0.804, GUESS, "no photometry; LOT measures 0.27-0.48"),

    # ---- Lulin, SOPHIA (e2v CCD230-42) --------------------------------------
    "lulin.cameras.Sophia.pixel_pitch": (15.0, DOCUMENT, "datasheet and frame XPIXSZ"),
    "lulin.cameras.Sophia.quantum_efficiency": (0.85, GUESS, "datasheet curve gives 90/96/87% at g'r'i'; harmless where the band throughput is measured, not elsewhere"),
    "lulin.cameras.Sophia.dark_current_rate": (0.01, GUESS, "datasheet gives 0.0001 at -90 C, frames run at -80 C"),
    "lulin.cameras.Sophia.readout_noise": (7.0, MEASURED, "photon transfer curve gives 7.9; datasheet 1 MHz port 7.0"),
    "lulin.cameras.Sophia.full_well_capacity": (100000, DOCUMENT, "datasheet, single pixel typical"),

    # ---- Lulin, Andor iKon-M DU934P-BEX2-DD ---------------------------------
    "lulin.cameras.SLT_default.pixel_pitch": (13.0, DOCUMENT, "datasheet and the SLT page, 13 x 13 um"),
    "lulin.cameras.SLT_default.quantum_efficiency": (0.85, GUESS, "no curve read for this sensor"),
    "lulin.cameras.SLT_default.dark_current_rate": (0.017, DOCUMENT, "datasheet BEX2-DD at -80 C; operating temperature assumed"),
    "lulin.cameras.SLT_default.readout_noise": (3.3, DOCUMENT, "datasheet BEX2-DD at 0.05 MHz; readout speed assumed"),
    "lulin.cameras.SLT_default.full_well_capacity": (130000, DOCUMENT, "datasheet, BEX2-DD"),

    # ---- Lulin filters: Astrodon Gen2 curves published by the observatory ----
    "lulin.filters.Sloan_g.central_wavelength": (475.9, DOCUMENT, "transmission-weighted centroid of the measured curve"),
    "lulin.filters.Sloan_g.filter_bandwidth": (147.0, DOCUMENT, "FWHM of the measured curve"),
    "lulin.filters.Sloan_g.filter_transmission": (0.996, DOCUMENT, "peak of the measured curve"),
    "lulin.filters.Sloan_r.central_wavelength": (627.8, DOCUMENT, "measured curve"),
    "lulin.filters.Sloan_r.filter_bandwidth": (131.0, DOCUMENT, "measured curve"),
    "lulin.filters.Sloan_r.filter_transmission": (0.995, DOCUMENT, "measured curve"),
    "lulin.filters.Sloan_i.central_wavelength": (767.6, DOCUMENT, "measured curve"),
    "lulin.filters.Sloan_i.filter_bandwidth": (145.0, DOCUMENT, "measured curve"),
    "lulin.filters.Sloan_i.filter_transmission": (1.0, DOCUMENT, "measured curve peaks at 1.002, clamped"),
    "lulin.filters.Sloan_z.central_wavelength": (962.1, DOCUMENT, "measured curve"),
    "lulin.filters.Sloan_z.filter_bandwidth": (278.0, DOCUMENT, "measured curve, truncated at 1100 nm"),
    "lulin.filters.Sloan_z.filter_transmission": (0.998, DOCUMENT, "measured curve"),
    "lulin.filters.Sloan_u.central_wavelength": (354.0, GUESS, "no curve published for LOT u'"),
    "lulin.filters.Sloan_u.filter_bandwidth": (56.0, GUESS, "no curve published for LOT u'"),
    "lulin.filters.Sloan_u.filter_transmission": (0.9, GUESS, "the value the other four carried before measurement"),

    # ---- Lulin per-band values, from the photometry -------------------------
    "lulin.filters.Sloan_g.environment.mu_dark": (21.44, MEASURED, "moonless frames, 7 nights"),
    "lulin.filters.Sloan_r.environment.mu_dark": (20.92, MEASURED, "moonless frames, 12 nights"),
    "lulin.filters.Sloan_i.environment.mu_dark": (20.04, MEASURED, "moonless frames, 7 nights"),
    "lulin.filters.Sloan_g.telescope.optical_throughput": (0.313, MEASURED, "Pan-STARRS photometry, T_sys 0.265"),
    "lulin.filters.Sloan_r.telescope.optical_throughput": (0.568, MEASURED, "Pan-STARRS photometry, T_sys 0.480"),
    "lulin.filters.Sloan_i.telescope.optical_throughput": (0.312, MEASURED, "Pan-STARRS photometry, T_sys 0.265"),

    # ---- VLT / FORS2 --------------------------------------------------------
    # Hardware-only profile, never the default, and nobody here observes with it.
    "vlt.telescopes.VLT.primary_mirror_diameter": (8.0, GUESS, "a VLT unit telescope is 8.2 m"),
    "vlt.telescopes.VLT.secondary_mirror_diameter": (1.088, GUESS, "no source found"),
    "vlt.telescopes.VLT.focal_length": (24.75, GUESS, "no source found"),
    "vlt.telescopes.VLT.optical_throughput": (0.771, GUESS, "ESO's rates imply about 0.36 for optics and detector together"),
    "vlt.cameras.FORS2_MIT.pixel_pitch": (15.0, GUESS, "plausible for the MIT CCD, not verified"),
    "vlt.cameras.FORS2_MIT.quantum_efficiency": (0.781, GUESS, "no source found"),
    "vlt.cameras.FORS2_MIT.dark_current_rate": (0.000583, DOCUMENT, "appears verbatim in ESO's ETC output"),
    "vlt.cameras.FORS2_MIT.readout_noise": (3.15, DOCUMENT, "appears verbatim in ESO's ETC output"),
    "vlt.cameras.FORS2_MIT.full_well_capacity": (80400, DOCUMENT, "appears verbatim in ESO's ETC output"),
    "vlt.filters.FORS2_g_HIGH.central_wavelength": (467.0, GUESS, "no source found"),
    "vlt.filters.FORS2_g_HIGH.filter_bandwidth": (160.3, GUESS, "no source found"),
    "vlt.filters.FORS2_g_HIGH.filter_transmission": (0.85, GUESS, "over-predicts ESO by 148%"),
    "vlt.filters.V_HIGH+114.central_wavelength": (550.0, GUESS, "measured curve centroid is 549.2"),
    "vlt.filters.V_HIGH+114.filter_bandwidth": (114.0, GUESS, "matches the filter's name; curve FWHM agrees"),
    "vlt.filters.V_HIGH+114.filter_transmission": (0.51, GUESS, "measured curve peaks at 0.897; the 0.51 absorbs an optical throughput twice too high"),
}


def walk(profiles):
    """Every numeric leaf in a preset file, as dotted paths."""
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
                for extra in ("environment", "telescope"):
                    for key, value in (entry.get(extra) or {}).items():
                        out[f"{profile_id}.{catalogue}.{entry_id}.{extra}.{key}"] = value
    return out


def summary(profiles):
    """How many values in this file have a source, by profile."""
    counts = {}
    for path in walk(profiles):
        profile_id = path.split(".", 1)[0]
        source = PROVENANCE.get(path, (None, "MISSING", ""))[1]
        counts.setdefault(profile_id, {}).setdefault(source, 0)
        counts[profile_id][source] += 1
    return counts
