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
    "lulin.environment.mu_dark": (21.5, GUESS, "fallback only; g'r'i' measured on their filters, all down one sightline"),
    "lulin.environment.extinction_coeff": (0.17, GUESS, "three sources disagree; see QUESTIONS.md 4"),
    "lulin.median_seeing_fwhm": (1.4, GUESS, "no source, but 123 frames give a median FWHM of 1.34\""),

    # ---- Lulin, LOT ---------------------------------------------------------
    "lulin.telescopes.LOT.primary_mirror_diameter": (1.02, DOCUMENT, "Trebur offer, optical specified >1020 mm; 1030 outside. \"1 m\" is the name"),
    "lulin.telescopes.LOT.secondary_mirror_diameter": (0.36, DOCUMENT, "Trebur offer, outside 360 mm; the whole disc obstructs, not the figured 350"),
    "lulin.telescopes.LOT.focal_length": (8.054, DERIVED, "reproduces the 0.3841\"/pix the frames solve"),
    "lulin.telescopes.LOT.optical_throughput": (0.381, MEASURED, "geometric mean; g'r'i' carry their own"),

    # ---- Lulin, SLT ---------------------------------------------------------
    "lulin.telescopes.SLT.primary_mirror_diameter": (0.406, DOCUMENT, "site pages, 16 inch"),
    "lulin.telescopes.SLT.secondary_mirror_diameter": (0.12, GUESS, "not published"),
    "lulin.telescopes.SLT.focal_length": (3.414, DERIVED, "site pages, f/8.4 on 0.406 m"),
    "lulin.telescopes.SLT.optical_throughput": (0.804, GUESS, "no photometry; LOT measures 0.27-0.48; QUESTIONS.md 5"),

    # ---- Lulin, SOPHIA (e2v CCD230-42) --------------------------------------
    "lulin.cameras.Sophia.pixel_pitch": (15.0, DOCUMENT, "datasheet and frame XPIXSZ"),
    "lulin.cameras.Sophia.quantum_efficiency": (0.85, GUESS, "datasheet curve gives 90/96/87% at g'r'i'; harmless where the band throughput is measured, wrong 3x in z'; QUESTIONS.md 13"),
    "lulin.cameras.Sophia.dark_current_rate": (0.01, GUESS, "datasheet -152 gives 0.00025 at -90 C, frames run at -80 C; QUESTIONS.md 6"),
    "lulin.cameras.Sophia.readout_noise": (7.9, MEASURED, "photon transfer curve over 123 frames; datasheet -152 1 MHz port says 8.5"),
    "lulin.cameras.Sophia.full_well_capacity": (150000, DOCUMENT, "datasheet -152, single pixel typical; 100000 was the 13.5 um -132 column"),

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
    "lulin.filters.Sloan_u.central_wavelength": (353.4, DOCUMENT, "SLT's Astrodon 2018 u'; LOT's up_Astrondon_2017 has no published curve"),
    "lulin.filters.Sloan_u.filter_bandwidth": (64.8, DOCUMENT, "equivalent width of the same curve; the 56.0 placeholder was 14% narrow"),
    "lulin.filters.Sloan_u.filter_transmission": (1.0, DOCUMENT, "peak of the same curve; 0.9 was the placeholder all five once carried"),

    # ---- Lulin per-band values, from the photometry -------------------------
    "lulin.filters.Sloan_g.environment.mu_dark": (21.79, DERIVED, "21.44 measured (7 nights, ecliptic +16/galactic +21) minus zodiacal_share via skycalc.AT_LULIN"),
    "lulin.filters.Sloan_r.environment.mu_dark": (21.26, DERIVED, "20.92 measured (12 nights, ecliptic +16/galactic +21) minus zodiacal_share via skycalc.AT_LULIN"),
    "lulin.filters.Sloan_i.environment.mu_dark": (20.20, DERIVED, "20.04 measured (7 nights, ecliptic +16/galactic +21) minus zodiacal_share via skycalc.AT_LULIN"),
    "lulin.filters.Sloan_g.environment.zodiacal_share": (0.274, DERIVED, "skycalc.AT_LULIN, SkyCalc's Paranal zodiacal+starlight share rescaled to Lulin's measured total"),
    "lulin.filters.Sloan_r.environment.zodiacal_share": (0.267, DERIVED, "skycalc.AT_LULIN, SkyCalc's Paranal zodiacal+starlight share rescaled to Lulin's measured total"),
    "lulin.filters.Sloan_i.environment.zodiacal_share": (0.137, DERIVED, "skycalc.AT_LULIN, SkyCalc's Paranal zodiacal+starlight share rescaled to Lulin's measured total"),
    "lulin.filters.Sloan_g.telescope.optical_throughput": (0.313, MEASURED, "Pan-STARRS photometry, T_sys 0.265"),
    "lulin.filters.Sloan_r.telescope.optical_throughput": (0.568, MEASURED, "Pan-STARRS photometry, T_sys 0.480"),
    "lulin.filters.Sloan_i.telescope.optical_throughput": (0.312, MEASURED, "Pan-STARRS photometry, T_sys 0.265"),

    # ---- VLT / FORS2 --------------------------------------------------------
    # Never the default, and nobody here observes with it. It did lack a site
    # entirely until a user asked why: unlike the amateur rigs, Paranal's
    # location is exactly known, so leaving it unset was an oversight rather
    # than the deliberate choice that omission is for genuinely portable gear.
    "vlt.environment.location.latitude_deg": (-24.6275, DOCUMENT, "ESO/Wikidata, 24d37'38\"S"),
    "vlt.environment.location.longitude_deg": (-70.4042, DOCUMENT, "ESO/Wikidata, 70d24'17\"W"),
    "vlt.environment.location.elevation_m": (2635.0, DOCUMENT, "ESO's published Paranal elevation"),
    "vlt.environment.mu_dark": (21.61, DOCUMENT, "ESO Paranal astroclimate page, Table 1: zenith-corrected V-band mean, FORS1, 3900 images over 174 nights Apr 2000-Sep 2001, rms 0.20"),
    "vlt.environment.extinction_coeff": (0.135, DERIVED, "Patat et al. 2011 (A&A 527, A91) spectral extinction curve, integrated against the measured V_HIGH+114 curve in data/fors2_v_high_114.dat; plain 5500A value is 0.131"),
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

    # ---- Other, the user's own amateur rig ----------------------------------
    # Nominally sited at Hehuan Mountain's Yuanfeng viewpoint, an IDA-certified
    # dark-sky park entrance, but the gear travels — this is a starting point,
    # not a claim about where any given exposure was actually taken.
    "other.environment.location.latitude_deg": (24.1144, DOCUMENT, "darksky.tw park boundary map, Yuanfeng (south) anchor"),
    "other.environment.location.longitude_deg": (121.2220, DOCUMENT, "darksky.tw park boundary map, Yuanfeng (south) anchor"),
    "other.environment.location.elevation_m": (2756.0, DOCUMENT, "Yuanfeng checkpoint, Taiwan Highway 14A km 24.3"),
    "other.environment.mu_dark": (21.1, GUESS, "SQM reading reported at Yuanfeng by Taiwan's dark-sky monitoring group; park average is quoted 21.3-21.7. SQM is not exactly Johnson V"),
    "other.environment.extinction_coeff": (0.17, DERIVED, "borrowed from Lulin's own site value; Yuanfeng is 2756 m against Lulin's 2862 m, both Taiwan high-mountain sites"),

    "other.telescopes.RedCat51.primary_mirror_diameter": (0.051, DOCUMENT, "William Optics spec"),
    "other.telescopes.RedCat51.secondary_mirror_diameter": (0.0, DOCUMENT, "refractor; no central obstruction"),
    "other.telescopes.RedCat51.focal_length": (0.250, DOCUMENT, "William Optics spec, f/4.9"),
    "other.telescopes.RedCat51.optical_throughput": (0.9, GUESS, "no photometric measurement; a plausible multi-coated apo figure, not validated end to end"),
    "other.telescopes.RedCat71.primary_mirror_diameter": (0.071, DOCUMENT, "William Optics spec"),
    "other.telescopes.RedCat71.secondary_mirror_diameter": (0.0, DOCUMENT, "refractor; no central obstruction"),
    "other.telescopes.RedCat71.focal_length": (0.350, DOCUMENT, "William Optics spec, f/4.9"),
    "other.telescopes.RedCat71.optical_throughput": (0.9, GUESS, "no photometric measurement; a plausible multi-coated apo figure, not validated end to end"),
    "other.telescopes.FLT91.primary_mirror_diameter": (0.091, DOCUMENT, "William Optics spec (Fluorostar 91)"),
    "other.telescopes.FLT91.secondary_mirror_diameter": (0.0, DOCUMENT, "refractor; no central obstruction"),
    "other.telescopes.FLT91.focal_length": (0.540, DOCUMENT, "William Optics spec, f/5.9"),
    "other.telescopes.FLT91.optical_throughput": (0.9, GUESS, "no photometric measurement; a plausible multi-coated apo figure, not validated end to end"),
    "other.telescopes.ZS73III.primary_mirror_diameter": (0.073, DOCUMENT, "William Optics spec"),
    "other.telescopes.ZS73III.secondary_mirror_diameter": (0.0, DOCUMENT, "refractor; no central obstruction"),
    "other.telescopes.ZS73III.focal_length": (0.430, DOCUMENT, "William Optics spec, f/5.9"),
    "other.telescopes.ZS73III.optical_throughput": (0.9, GUESS, "no photometric measurement; a plausible multi-coated apo figure, not validated end to end"),
    "other.telescopes.FSQ106.primary_mirror_diameter": (0.106, DOCUMENT, "Takahashi spec (FSQ-106EDX4)"),
    "other.telescopes.FSQ106.secondary_mirror_diameter": (0.0, DOCUMENT, "refractor; no central obstruction"),
    "other.telescopes.FSQ106.focal_length": (0.530, DOCUMENT, "Takahashi spec, f/5.0"),
    "other.telescopes.FSQ106.optical_throughput": (0.9, GUESS, "no photometric measurement; a plausible multi-coated apo figure, not validated end to end"),

    "other.cameras.ASI2600MC.pixel_pitch": (3.76, DOCUMENT, "ZWO spec, Sony IMX571"),
    "other.cameras.ASI2600MC.quantum_efficiency": (0.80, DOCUMENT, "ZWO spec, peak QE"),
    "other.cameras.ASI2600MC.dark_current_rate": (0.000514, DERIVED, "interpolated between ZWO's own published 0.0022 e-/s at 0C and 0.00012 e-/s at -20C to a -10C operating point, assuming the halving-per-degree scaling this suite used for SOPHIA"),
    "other.cameras.ASI2600MC.readout_noise": (1.51, DOCUMENT, "community-measured at gain 100 (HCG mode); ZWO's headline 1.0e is a different, higher gain"),
    "other.cameras.ASI2600MC.full_well_capacity": (16760, DOCUMENT, "community-measured at gain 100; ZWO's headline 73ke is gain 0"),
    "other.cameras.ASI533MC.pixel_pitch": (3.76, DOCUMENT, "ZWO spec, Sony IMX533"),
    "other.cameras.ASI533MC.quantum_efficiency": (0.80, DOCUMENT, "ZWO spec, peak QE"),
    "other.cameras.ASI533MC.dark_current_rate": (0.000514, GUESS, "no ASI533-specific figure found; borrowed the ASI2600's own -10C interpolation as a same-generation Sony back-illuminated sensor proxy"),
    "other.cameras.ASI533MC.readout_noise": (1.5, DOCUMENT, "community-measured at gain 100 (HCG mode); ZWO's headline 1.0e is a different, higher gain"),
    "other.cameras.ASI533MC.full_well_capacity": (16650, DERIVED, "no ASI533-specific figure found; derived from its own commonly-cited ~13.4 stop dynamic range at gain 100 times its 1.5e read noise, which lands within 1% of the ASI2600's own directly-measured gain-100 full well"),
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
