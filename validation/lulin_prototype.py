"""The Perl calculators CASTOR was refactored from, transcribed.

Sources: `etc.cgi`, time-stamped 2005/11/01, and `etc2.cgi`, time-stamped
2011/03/29. Both by Kinoshita Daisuke at the Institute of Astronomy, NCU. The
2005 file serves the 1 m alone; the 2011 file is a rewrite covering a 1 m and a
2 m with a choice of three cameras.

These are not an independent check the way LCO and ESO are. They are CASTOR's
own ancestry — the project's slides record the chain as Daisuke's code, then
Ting-Wan Chen, then this refactor — so where presets.json holds a number nobody
can source, this is the likeliest place it came from. Read them as archaeology.

Transcribed as constants and formulas rather than copied as Perl, because what
is worth keeping is the numbers and the shape of the model.

Two things to know before using anything here.

**The 2011 file is an unfinished draft.** Dark current is `XXX` at every
temperature for one camera and at most temperatures for another, the Sloan
quantum efficiencies for PI1300B are empty, four PS1 bands are declared and
never filled, and si1100 has two `readout` keys where Perl silently keeps only
the second. Nothing here was ever finished, so a number's presence is not
evidence anybody stood behind it.

**The 2011 Sloan tables are the Bessell tables shifted one slot.** Extinction
and sky background for `sdss_g/r/i/z` are, value for value, those for
`bessell_B/V/R/I` — twenty-four numbers, no exceptions — and `sdss_z` is given
the same 1409 A bandwidth as `sdss_g`, where Lulin's own published curve
measures 2780 A. They are placeholders wearing Sloan labels. `SDSS_COPIED_FROM`
records the mapping and `test_lulin_prototype.py` asserts it, so that nobody
adopts them later on the strength of appearing in a document.

What *is* worth having: the 2011 file decomposes throughput the way the ATBD
does, into optics x filter x quantum efficiency, and it tabulates dark current
against CCD temperature and read noise against readout speed — three things
presets.json currently states without a source.
"""
import numpy as np

# ---------------------------------------------------------------------------
# etc.cgi, 2005
# ---------------------------------------------------------------------------

#: The 1 m, with no central obstruction: the source rate uses pi*(D/2)^2 whole.
DIAMETER_M_2005 = 1.0
PIXEL_SCALE_2005 = 0.515

BESSELL = ("U", "B", "V", "R", "I")

#: Angstrom. Named a half-width, used as the full bandwidth in the flux integral.
HALF_WIDTH_2005 = {"U": 700, "B": 1000, "V": 800, "R": 1300, "I": 3100}
WAVELENGTH_NM_2005 = {"U": 360.0, "B": 440.0, "V": 540.0, "R": 635.0, "I": 880.0}

#: mag/airmass. Falls monotonically towards the red, as extinction should.
EXTINCTION_2005 = {"U": 0.45, "B": 0.19, "V": 0.11, "R": 0.09, "I": 0.06}

#: Total system efficiency — the only efficiency factor in either rate, so it
#: carries optics, filter and detector together, the same quantity the ATBD
#: calls T_sys.
THROUGHPUT_2005 = {"U": 0.07, "B": 0.27, "V": 0.54, "R": 0.46, "I": 0.20}

#: Declared and then never referenced by any formula in the file. Dead code,
#: kept only so the transcription is complete.
FILTER_TRANSMISSION_2005 = {"U": 0.50, "B": 0.68, "V": 0.88, "R": 0.81, "I": 0.94}

#: W m^-2 A^-1 for a zero-magnitude star.
ZERO_MAG_FLUX_2005 = {
    "U": 4.175e-12, "B": 6.32e-12, "V": 3.631e-12, "R": 2.177e-12, "I": 8.83e-13,
}

#: mag/arcsec^2, keyed by days after new moon. Sourced upstream to a 1994 NOAO
#: newsletter article, and reused unchanged in 2011.
SKY_BRIGHTNESS_2005 = {
    "U": {0: 22.0, 3: 21.5, 7: 19.9, 10: 18.5, 14: 17.0},
    "B": {0: 22.7, 3: 22.4, 7: 21.6, 10: 20.7, 14: 19.5},
    "V": {0: 21.8, 3: 21.7, 7: 21.4, 10: 20.7, 14: 20.0},
    "R": {0: 20.9, 3: 20.8, 7: 20.6, 10: 20.3, 14: 19.9},
    "I": {0: 19.9, 3: 19.9, 7: 19.7, 10: 19.5, 14: 19.2},
}

#: e-/pix and seconds. Two named modes rather than a readout frequency.
READOUT_2005 = {"slow": {"noise": 4.5, "time": 40.0}, "fast": {"noise": 7.5, "time": 2.0}}


# ---------------------------------------------------------------------------
# etc2.cgi, 2011
# ---------------------------------------------------------------------------

SDSS = ("g", "r", "i", "z")

TELESCOPES_2011 = {
    "1mtel": {"name": "Lulin 1-m Telescope", "diameter": 1.00, "focallength": 8.0},
    "2mtel": {"name": "Lulin 2-m Telescope", "diameter": 2.00, "focallength": 16.0},
}

#: nm, Angstrom, peak transmission. sdss_z repeats sdss_g's 1409 A; the curve
#: Lulin publishes for that filter measures 2780 A.
FILTERS_2011 = {
    "bessell_U": {"centre_nm": 366.0, "width_a": 500, "t_peak": 0.57},
    "bessell_B": {"centre_nm": 440.0, "width_a": 1180, "t_peak": 0.93},
    "bessell_V": {"centre_nm": 538.0, "width_a": 910, "t_peak": 0.90},
    "bessell_R": {"centre_nm": 655.0, "width_a": 1290, "t_peak": 0.94},
    "bessell_I": {"centre_nm": 797.0, "width_a": 1630, "t_peak": 0.97},
    "sdss_g": {"centre_nm": 480.3, "width_a": 1409, "t_peak": 0.95},
    "sdss_r": {"centre_nm": 625.4, "width_a": 1388, "t_peak": 0.95},
    "sdss_i": {"centre_nm": 766.8, "width_a": 1535, "t_peak": 0.95},
    "sdss_z": {"centre_nm": 911.4, "width_a": 1409, "t_peak": 0.95},
}

#: Primary, secondary and the corrector glass. Flat to 2% across g' to i', which
#: is the whole point of transcribing it: on this model the telescope cannot be
#: the reason one visible band outperforms its neighbours.
OPTICS_2011 = {
    "bessell_U": {"m1": 0.89, "m2": 0.89, "glass": 0.94},
    "bessell_B": {"m1": 0.89, "m2": 0.89, "glass": 0.95},
    "bessell_V": {"m1": 0.89, "m2": 0.89, "glass": 0.95},
    "bessell_R": {"m1": 0.88, "m2": 0.88, "glass": 0.95},
    "bessell_I": {"m1": 0.85, "m2": 0.85, "glass": 0.95},
    "sdss_g": {"m1": 0.89, "m2": 0.89, "glass": 0.95},
    "sdss_r": {"m1": 0.89, "m2": 0.89, "glass": 0.95},
    "sdss_i": {"m1": 0.88, "m2": 0.88, "glass": 0.95},
    "sdss_z": {"m1": 0.85, "m2": 0.85, "glass": 0.95},
}

#: None of these is SOPHIA, which post-dates the file. `dark` is e-/s/pix keyed
#: by CCD temperature in Celsius and `readout` is e-/pix keyed by readout
#: frequency in kHz — the two tables presets.json most needs and does not have.
#: Entries the source leaves as `XXX` or blank are simply absent here.
CAMERAS_2011 = {
    "pi1300b": {
        "name": "PI1300B CCD Camera",
        "manufacturer": "Princeton Instruments",
        "chip": "E2V CCD36-40",
        "type": "back-illuminated thinned CCD",
        "pixel_um": 20.0, "npix": (1340, 1300), "namp": 1,
        "qe": {"bessell_U": 0.25, "bessell_B": 0.80, "bessell_V": 0.92,
               "bessell_R": 0.88, "bessell_I": 0.73},
        "dark": {0: 20.0, -10: 5.0, -20: 1.5, -30: 0.4, -40: 0.1, -45: 0.08, -50: 0.064},
        "readout": {50: 4.0, 100: 4.5, 125: 4.5, 200: 5.0, 400: 6.0, 800: 7.0, 1000: 7.5},
    },
    "si1100": {
        "name": "SI1100 Series CCD Camera",
        "manufacturer": "Spectral Instruments",
        "chip": "E2V CCD44-82-1-D23",
        "type": "back-illuminated deep depletion CCD",
        "pixel_um": 15.0, "npix": (2048, 4096), "namp": 2,
        "qe": {"bessell_U": 0.33, "bessell_B": 0.58, "bessell_V": 0.83,
               "bessell_R": 0.93, "bessell_I": 0.85,
               "sdss_g": 0.60, "sdss_r": 0.80, "sdss_i": 0.91, "sdss_z": 0.55},
        "dark": {-50: 1.0, -80: 0.03, -100: 3.0e-4, -110: 3.0e-5},
        # The source declares `readout` twice, first {50: 4.0, 1000: 7.5} and
        # then this; Perl keeps the last, so the first is unreachable.
        "readout": {50: 2.1, 100: 2.5, 125: 2.6, 200: 3.0, 400: 4.0, 800: 7.0, 1000: 10.0},
    },
    "ncucam1": {
        "name": "NCUcam-1 CCD Camera",
        "manufacturer": "Institute of Astronomy, NCU",
        "chip": "Hamamatsu 2Kx4K fully depleted CCD",
        "type": "back-illuminated fully depleted CCD",
        "pixel_um": 15.0, "npix": (2048, 4096), "namp": 4,
        "qe": {"bessell_U": 0.40, "bessell_B": 0.77, "bessell_V": 0.95,
               "bessell_R": 0.94, "bessell_I": 0.84,
               "sdss_g": 0.88, "sdss_r": 0.95, "sdss_i": 0.87, "sdss_z": 0.80},
        "dark": {-50: 3.0, -80: 0.03, -100: 2.0e-4, -110: 6.0e-5},
        "readout": {50: 2.5, 100: 3.0, 125: 3.5, 200: 7.5, 400: 10.0, 800: 20.0, 1000: 30.0},
    },
}

EXTINCTION_2011 = {
    "bessell_U": 0.43, "bessell_B": 0.22, "bessell_V": 0.13,
    "bessell_R": 0.10, "bessell_I": 0.07,
    "sdss_g": 0.22, "sdss_r": 0.13, "sdss_i": 0.10, "sdss_z": 0.07,
}

SKY_BRIGHTNESS_2011 = {
    "bessell_U": {0: 22.0, 3: 21.5, 7: 19.9, 10: 18.5, 14: 17.0},
    "bessell_B": {0: 22.7, 3: 22.4, 7: 21.6, 10: 20.7, 14: 19.5},
    "bessell_V": {0: 21.8, 3: 21.7, 7: 21.4, 10: 20.7, 14: 20.0},
    "bessell_R": {0: 20.9, 3: 20.8, 7: 20.6, 10: 20.3, 14: 19.9},
    "bessell_I": {0: 19.9, 3: 19.9, 7: 19.7, 10: 19.5, 14: 19.2},
    "sdss_g": {0: 22.7, 3: 22.4, 7: 21.6, 10: 20.7, 14: 19.5},
    "sdss_r": {0: 21.8, 3: 21.7, 7: 21.4, 10: 20.7, 14: 20.0},
    "sdss_i": {0: 20.9, 3: 20.8, 7: 20.6, 10: 20.3, 14: 19.9},
    "sdss_z": {0: 19.9, 3: 19.9, 7: 19.7, 10: 19.5, 14: 19.2},
}

ZERO_MAG_FLUX_2011 = {
    "bessell_U": 4.175e-12, "bessell_B": 6.32e-12, "bessell_V": 3.631e-12,
    "bessell_R": 2.177e-12, "bessell_I": 8.83e-13,
    "sdss_g": 5.20e-12, "sdss_r": 2.44e-12, "sdss_i": 1.32e-12, "sdss_z": 8.03e-13,
}

#: The Sloan entry each of the 2011 tables copies. Asserted, not assumed.
SDSS_COPIED_FROM = {
    "sdss_g": "bessell_B",
    "sdss_r": "bessell_V",
    "sdss_i": "bessell_R",
    "sdss_z": "bessell_I",
}


# ---------------------------------------------------------------------------

def optics(band):
    """The 2011 telescope-and-filter chain, detector excluded.

    m1 * m2 * glass * T_peak, which is the ATBD's R_optics * T_filter.
    """
    o = OPTICS_2011[band]
    return o["m1"] * o["m2"] * o["glass"] * FILTERS_2011[band]["t_peak"]


def throughput(camera, band):
    """The 2011 T_sys: optics * filter * quantum efficiency.

    The same decomposition the ATBD specifies, six years earlier. Raises
    KeyError for a band the source leaves blank for that camera, which is the
    honest answer — the draft never filled them in.
    """
    return optics(band) * CAMERAS_2011[camera]["qe"][band]


def interpolate_2005(table, wavelength_nm):
    """A 2005 Bessell quantity at an arbitrary wavelength.

    The 2005 file predates Lulin's Sloan filters, so comparing it against
    anything measured on g'r'i' means interpolating between the Johnson points.
    Linear, and crude where the points are far apart — the R-to-I gap is 245 nm,
    which straddles i' — so treat a single interpolated value as an indication
    of the shape rather than as a number to adopt.
    """
    x = [WAVELENGTH_NM_2005[b] for b in BESSELL]
    y = [table[b] for b in BESSELL]
    return float(np.interp(wavelength_nm, x, y))
