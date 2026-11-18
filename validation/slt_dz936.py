"""SLT + Andor DZ936 against the first night after it went back on the telescope.

The DZ936 (iKon-L 936, E2V CCD42-40) was SLT's camera in 2021-22 and went back
on in Nov 2026 as a stand-in while the DU934P's shutter is repaired. Everything
presets.json said about it came from Andor's brochure; nothing had been checked
on the telescope. This is that check.

The night: 2026-11-10, AT2026afqt, 139 calibrated frames, 12:41-20:55 UTC,
150 s in g'r'i'z', 150 s and 300 s in u'. Moon below the horizon throughout.
The field rises from airmass 1.64 to the meridian (1.107, ~15:45 UTC) and sets
to 4.9 — the property SN2024ggi's night (`slt.py`) lacked. There the target
only set, so a transparency drift and an airmass term were the same variable
and no extinction could be measured. Here the two branches are separate looks
at the same airmass range at different times, and where they agree the slope
is an extinction.

Method, in `reduce_slt_afqt.py` (frames -> tables) and `analyze_slt_afqt.py`
(tables -> the numbers below):

* Reference stars: Pan-STARRS DR2 PSF mags for g'r'i'z' (dec -2.0 is inside
  PS1), SkyMapper DR4 for u'. NO colour terms. SkyMapper u is not SDSS u', so
  u' carries the largest systematic here, as it does in slt.py.
* Aperture photometry at 2.5 x FWHM for zero points, 1.5 x FWHM for the noise
  test; sky from a 4-6 x FWHM annulus. FWHM by half-maximum area, since a
  second moment over a box doubled it on these frames.
* A per-frame affine correction to the header WCS from bright-star centroids
  (median residual 0.2 px).

Frames dropped, none of them for anything CASTOR did (see FRAME_PROBLEMS):
12 i'/z' frames where the delivered calibration erased bright stars, 2 i'
frames whose stars disagree (zp_err ~0.2), 2 u' frames with no plate solution.

What went into presets.json from here: SLT's focal length, the DZ936's read
noise, u' and z' sky, and a k for every band. What did NOT: the DZ936's
band-dependent response (BAND_RESPONSE). presets.json can key a band's
throughput by telescope but not by camera, so storing it would also change the
DU934P's predictions. It stays here, recorded and asserted as absent.

Frames are not committed (`data/raw/slt_at2026afqt/`, gitignored; RESULT.md
there has the long form).
"""

NIGHT = {
    "date": "2026-11-10", "target": "AT2026afqt", "telescope": "SLT",
    "camera": "Andor DZ936 (E2V CCD42-40), gain 0.95 e-/ADU, -80 C",
    "frames_delivered": 139, "frames_used": 124,
    "ra_deg": 47.9087, "dec_deg": -2.0267,
    "ecliptic_latitude_deg": -19.1, "galactic_latitude_deg": -48.1,
    "airmass_min": 1.107, "airmass_max": 4.92,
    "transit_utc": "2026-11-10T15:45",
    "moon_altitude_deg": (-87.7, -35.2),
    "catalogues": {"u": "SkyMapper DR4", "g": "PS1 DR2", "r": "PS1 DR2",
                   "i": "PS1 DR2", "z": "PS1 DR2"},
}

#: ZP = ZP0 - k X over good frames with X < 3, both branches together, and
#: each branch alone. `rms` is the fit's residual, mag. A transparency drift
#: would pull the two branches apart; they agree to 0.01 in g'r', 0.05 in
#: u'i'z'. One night: a k that changes night to night is not ruled out.
EXTINCTION = {
    "u": dict(k=0.443, k_rising=0.381, k_setting=0.433, rms=0.024, n=45, airmass=(1.11, 2.94)),
    "g": dict(k=0.158, k_rising=0.162, k_setting=0.153, rms=0.007, n=21, airmass=(1.11, 2.49)),
    "r": dict(k=0.071, k_rising=0.062, k_setting=0.073, rms=0.005, n=21, airmass=(1.11, 2.55)),
    "i": dict(k=0.038, k_rising=0.093, k_setting=0.042, rms=0.013, n=14, airmass=(1.11, 2.62)),
    "z": dict(k=0.051, k_rising=0.082, k_setting=0.052, rms=0.014, n=16, airmass=(1.11, 2.69)),
}

#: Total sky, AB mag/arcsec^2, astronomical night, X < 1.6, moon down: the
#: median over frames, and the frame-to-frame standard deviation. Converted
#: with the measured zero point plus k*X, so it is the ground-level brightness
#: CASTOR's mu_sky means. Not split into local and zodiacal parts.
SKY = {
    "u": dict(mu=22.73, sd=0.13, n=35),
    "g": dict(mu=21.63, sd=0.16, n=17),
    "r": dict(mu=20.77, sd=0.13, n=17),
    "i": dict(mu=19.86, sd=0.13, n=11),
    "z": dict(mu=18.71, sd=0.15, n=13),
}

#: The plate scale every frame solved to, and what it implies for SLT.
PIXEL_SCALE_ARCSEC = 0.790
PIXEL_PITCH_UM = 13.5
HEADER_FOCALLEN_MM = 3522.8

#: Read noise. The header's figure, and the one the u' 150 s frames imply
#: through their own local sky noise (sqrt(std^2 - sky), with only 6 e-/pix of
#: sky): the two agree. g'r'i'z' carry 7-8.5 e- per pixel beyond sky Poisson
#: and this read noise; the cause is not identified, and it is not in CASTOR.
READ_NOISE = {
    "header_rmsnoise": 5.92,
    "implied_u150": 5.74,
    "excess_e_per_pixel": {"g": 7.5, "r": 8.4, "i": 8.6, "z": 7.0},
}

#: Counts above the atmosphere, measured / what CASTOR predicted with the
#: presets as they stood (SLT band throughput fitted on the DU934P in slt.py,
#: DZ936 QE 0.9 in every band). Part camera, part catalogue (PS1 here,
#: SkyMapper there) and part slt.py's own ~15% zero-point uncertainty; one
#: camera on one night cannot split them. NOT in presets.json — see above.
BAND_RESPONSE = {"u": 0.782, "g": 1.233, "r": 1.204, "i": 0.975, "z": 0.616}

#: Noise: field stars on every frame of a band, one pier side (rising), after
#: dividing out each frame's transparency and aperture loss from its 15
#: brightest stars. `obs_over_pred` is the median over the bin's stars of
#: (frame-to-frame SNR) / (CASTOR's calculate_single_snr from that star's own
#: flux and sky, read noise 5.92). Bins with n >= 25 are the only ones a
#: 9-frame scatter measures well enough to assert on; the rest are kept for the
#: record. The bright bins show a ~0.5% per-frame floor CASTOR does not model.
NOISE = {
    ("u", 150, "<3k"):      dict(n=52, frames=9, obs_over_pred=0.922),
    ("u", 150, "10-30k"):   dict(n=11, frames=9, obs_over_pred=0.892),
    ("u", 300, "<3k"):      dict(n=37, frames=8, obs_over_pred=0.969),
    ("u", 300, "3-10k"):    dict(n=13, frames=8, obs_over_pred=0.890),
    ("u", 300, "30-100k"):  dict(n=8,  frames=8, obs_over_pred=0.751),
    ("g", 150, "10-30k"):   dict(n=7,  frames=9, obs_over_pred=0.908),
    ("g", 150, "100-300k"): dict(n=5,  frames=9, obs_over_pred=0.658),
    ("r", 150, "10-30k"):   dict(n=8,  frames=9, obs_over_pred=1.338),
    ("r", 150, "100-300k"): dict(n=5,  frames=9, obs_over_pred=0.699),
    ("i", 150, "<3k"):      dict(n=31, frames=9, obs_over_pred=0.964),
    ("i", 150, "10-30k"):   dict(n=8,  frames=9, obs_over_pred=1.108),
    ("i", 150, "100-300k"): dict(n=5,  frames=9, obs_over_pred=0.408),
    ("z", 150, "<3k"):      dict(n=29, frames=9, obs_over_pred=1.022),
    ("z", 150, "3-10k"):    dict(n=9,  frames=9, obs_over_pred=0.993),
    ("z", 150, "30-100k"):  dict(n=5,  frames=9, obs_over_pred=0.850),
}

#: What is wrong with the delivered frames, for anyone else reducing them.
FRAME_PROBLEMS = {
    "erased_bright_stars": (
        "12 i'/z' frames, all after the meridian flip and all with FWHM <= 2.26 px "
        "(the night's sharpest): stars brighter than 15.5 come back at 2-10% of "
        "their flux, their pixels holding runs of repeated neighbouring values. "
        "No header record of what did it."),
    "renamed_wcs_keys": "_RVAL1, _RPIX1, _C1_1, _TYPE1 ...: astropy finds no WCS.",
    "bunit": "BUNIT says adu; GAINCOR (0.95 e-/ADU) has been applied, pixels are e-.",
    "no_plate_solution": "u' 300 s at 20:36 and 20:41 UTC.",
}

#: The supernova itself is no test of anything here: its 1.5 x FWHM aperture
#: flux tracks the frame's FWHM at r = -0.96 in g'r'i'z' (host light), giving
#: 5-10% scatter that a noise model has no business reproducing.
SN_APERTURE_FLUX_VS_FWHM_CORRELATION = -0.96
