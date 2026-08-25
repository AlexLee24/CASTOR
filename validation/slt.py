"""SLT against the one night that could measure extinction.

`lulin.py` is the LOT half of this: 123 frames, 18 nights, one sightline. It
closed a great deal and could not close two things — per-band extinction
(QUESTIONS.md 4) and anything at all about SLT (QUESTIONS.md 5) — because no
single night in it spans more than 0.19 in airmass, so its extinction fit
measured night-to-night transparency wearing an airmass term's clothes.

This module is the night that did. 2024-04-14, SN2024ggi, SLT: 241 frames in
five Sloan bands sweeping airmass 1.81 to 3.72 in one continuous run, which is
exactly the observation `lulin.py`'s own "what would settle it" note asked for.

Method, which differs from lulin.py in two ways that matter:

    Reference catalogue is SkyMapper DR4, not Pan-STARRS DR2. This field sits
    at declination -32.8, outside PS1's footprint — not a preference, a fact
    checked directly: the same MAST cone search returns 2769 stars at the LOT
    field's +38.4 and zero here. SkyMapper's natural u/v/g/r/i/z system is
    close to but not identical to SDSS/Sloan, and NO COLOUR-TERM TRANSFORM HAS
    BEEN APPLIED, so every number below carries an unquantified systematic on
    top of the fit error quoted. That is the single biggest caveat here and the
    reason these values are not simply better than lulin.py's.

    Aperture radius follows each frame's own measured FWHM (2.5x, sky annulus
    4-6x) rather than a fixed size. Seeing swung 2.8 to 4.6 px within this
    night; a fixed aperture loses a seeing-dependent fraction of the flux, and
    that alone put 0.2-0.4 mag of false scatter into the first pass at this fit.

Frames are not committed — the repository is public and they are the
observatory's. `data/lulin/README.md` has the standing rule; what came out is
here, and `test_slt.py` checks presets.json against it.
"""

#: Reduced 2026-08-25 from 241 frames, 2024-04-14T12:05 to 17:07 UTC, SLT +
#: Andor DU934P-BEX2-DD, 30 s in g'r'i'z' and 150 s in u', bin 1.
#:
#:   k          atmospheric extinction, mag/airmass, from the ZP-airmass fit
#:   zp0        SkyMapper-system magnitude giving 1 ADU/s above the atmosphere
#:   throughput T_sys implied by zp0 through CASTOR's own count-rate chain
#:   optical    that throughput divided by QE and the filter's measured peak,
#:              the same "implied optical train" convention lulin.py uses
#:   n_kept     frames surviving the sigma clip, out of those reduced
#:
#: Errors on zp0 and k are the fit's own, scaled by the square root of the
#: reduced chi-squared — the scatter is dominated by real frame-to-frame
#: transparency, not by the per-frame zero point's formal precision, so the
#: unscaled covariance would understate them severalfold.
MEASURED = {
    "u": dict(k=0.622, k_err=0.094, zp0=20.024, zp0_err=0.188,
              throughput=0.086, optical=0.101, n_kept=44, n_total=47),
    "g": dict(k=0.512, k_err=0.023, zp0=21.846, zp0_err=0.049,
              throughput=0.274, optical=0.323, n_kept=37, n_total=48),
    "r": dict(k=0.314, k_err=0.024, zp0=21.835, zp0_err=0.051,
              throughput=0.401, optical=0.474, n_kept=39, n_total=49),
    "i": dict(k=0.185, k_err=0.033, zp0=21.471, zp0_err=0.073,
              throughput=0.317, optical=0.373, n_kept=45, n_total=49),
    "z": dict(k=0.155, k_err=0.028, zp0=20.720, zp0_err=0.062,
              throughput=0.104, optical=0.122, n_kept=40, n_total=48),
}

FILTER_OF = {"u": "Sloan_u", "g": "Sloan_g", "r": "Sloan_r",
             "i": "Sloan_i", "z": "Sloan_z"}

#: What the night covers, and what it does not.
#:
#: The airmass span is the whole point — 1.81 to 3.72 continuously, against a
#: largest-single-night span of 0.19 in lulin.py. It never reaches the zenith,
#: which costs nothing for a *slope* but means every zero point here is an
#: extrapolation back to X=0 rather than an anchored measurement.
#:
#: One target again, so this shares lulin.py's sightline limitation exactly
#: (QUESTIONS.md 16) and cannot say anything about pointing dependence.
NIGHT = {
    "date": "2024-04-14", "target": "SN2024ggi", "telescope": "SLT",
    "camera": "Andor DU934P-BEX2-DD CCD-26868",
    "frames_reduced": 241, "reference_stars": 970, "catalogue": "SkyMapper DR4",
    "airmass": (1.81, 3.72),
    "ra_deg": 169.5762, "dec_deg": -32.8470,
    "ecliptic_latitude_deg": -33.9, "galactic_latitude_deg": 26.1,
}

#: An hour of this night was not photometric, and the fit says so before any
#: weather record does. Residuals against the ZP-airmass line reach -1.17 mag on
#: a single frame here and stay 0.2-0.6 mag low either side of it, then recover
#: completely — the shape of cloud crossing, not of a bad fit. The sigma clip
#: removes it; this records that the removal was of something real.
CLOUDY_WINDOW_UTC = ("2024-04-14T14:34", "2024-04-14T15:32")

#: Read straight off the frames' own WCS. Not shared with LOT, and not even
#: shared across SLT's own history: this telescope has carried three cameras
#: (see presets.json's camera catalogue) at 0.76, 0.79 and other plate scales.
#: A fixed constant here is how the first pass at the Q16 sky comparison came
#: out 0.18 mag wrong.
PIXEL_SCALE_ARCSEC = 0.76


def implied_optical_throughput(band, quantum_efficiency, filter_transmission):
    """The optical train alone, backed out of the measured total.

    presets.json stores `optical_throughput` on the telescope and multiplies it
    by QE and filter transmission at request time, so what goes in the file is
    not the measured T_sys but T_sys with those two divided back out. Keeping
    the arithmetic here rather than in a comment is what lets `test_slt.py`
    assert the file matches the measurement rather than matching a number
    somebody typed.
    """
    return MEASURED[band]["throughput"] / (quantum_efficiency * filter_transmission)
