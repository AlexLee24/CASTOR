"""LOT and SOPHIA measured against the sky, and against Lulin's own documentation.

Every other reference in this directory compares CASTOR to somebody else's model.
This one compares it to photons that actually landed on the detector CASTOR is
meant to describe, which makes it the only file here that can say whether the
`lulin` profile — the one the calculator opens on — is right.

The frames are ~2 GB of calibrated LOT/SOPHIA science images and stay out of the
repository; `validation/data/lulin/README.md` says what they are. What is
committed is the result of reducing them, below, so the tests run without them.

Method, so the numbers can be argued with:

* Zero points come from aperture photometry against Pan-STARRS DR2 PSF
  magnitudes, which are AB and good to about 0.005 mag — not from the PinPoint
  ZMAG in the frame headers, which is tied to USNO-B1.0 and lands 0.73 mag out
  in g', 0.21 in r' and 0.05 in i'. Using it would have put the throughput
  wrong by a factor that changes with band.
* A 3 x FWHM aperture with a 5-8 x FWHM sky annulus, stars isolated by 8 x FWHM,
  peak below 90 ke- to stay clear of the 100 ke- well.
* ZP is fitted against airmass as ZP(X) = ZP0 - k X, so ZP0 is above the
  atmosphere, which is where CASTOR wants its flux. 2025-09-30 is dropped: it
  sits 0.8-1.2 mag faint in every band on its own, which is cloud, not physics.
* Sky surface brightness uses only frames with the Moon below the horizon, from
  the sigma-clipped median of the central quarter of each frame. The data is
  already in electrons (`BUNIT`), so no gain assumption enters.
"""
import json
import pathlib

FRAMES = pathlib.Path(__file__).resolve().parent / "data" / "raw"
CATALOGUE = FRAMES / "ps1"

#: Nights that are not photometric. Every band is faint by roughly the same
#: amount on this one date, which is what cloud looks like.
CLOUDY = frozenset({"2025-09-30"})

#: Reduced 2026-08-22 from 123 frames over 15 nights, 2025-09-29 to 2026-02-15.
#:
#:   k          atmospheric extinction, mag/airmass, from the ZP-airmass fit
#:   zp0        AB magnitude giving 1 e-/s above the atmosphere
#:   throughput T_sys implied by zp0 through CASTOR's own count-rate chain
#:   mu_dark    moonless sky surface brightness, AB mag/arcsec2, from the
#:              measured sky rate and that same throughput
#:   sky_rate   what the detector actually recorded, e-/s/pixel, moonless
MEASURED = {
    "g": dict(k=0.123, k_err=0.105, zp0=23.763, zp0_err=0.127,
              throughput=0.265, mu_dark=21.44, sky_rate=1.252, nights=7),
    "r": dict(k=0.189, k_err=0.027, zp0=23.985, zp0_err=0.031,
              throughput=0.480, mu_dark=20.92, sky_rate=2.493, nights=12),
    "i": dict(k=0.108, k_err=0.049, zp0=23.229, zp0_err=0.059,
              throughput=0.265, mu_dark=20.04, sky_rate=2.779, nights=7),
}

FILTER_OF = {"g": "Sloan_g", "r": "Sloan_r", "i": "Sloan_i"}

#: Astrodon Gen2 curves published by Lulin, integrated below 1100 nm because
#: silicon stops responding there and the filters leak in the near infrared.
#: These are now in presets.json; kept here as the record of where they came from.
MEASURED_BANDPASS = {
    "Sloan_g": dict(centroid=475.9, fwhm=147.0, peak=0.996, integral=146.6),
    "Sloan_r": dict(centroid=627.8, fwhm=131.0, peak=0.995, integral=130.5),
    "Sloan_i": dict(centroid=767.6, fwhm=145.0, peak=1.002, integral=145.2),
    "Sloan_z": dict(centroid=962.1, fwhm=278.0, peak=0.998, integral=274.6),
}

#: Every transmission curve Lulin publishes, measured the same way as
#: MEASURED_BANDPASS above: passband taken as the contiguous run above 5% of
#: peak, integrated to 1100 nm where silicon stops responding. `leak` is
#: everything outside that run and below 1100 nm, as a fraction of the passband.
#:
#: Two sets exist and they are not the same glass: LOT carries an Astrodon 2019
#: griz set, SLT an Astrodon 2018 ugriz set and a 2018 UBVRI set. LOT's u' is a
#: third filter again, up_Astrondon_2017, and Lulin publishes no curve for it.
PUBLISHED_BANDPASS = {
    # LOT, Astrodon 2019. z' is a long-pass stopped by the detector, not by the
    # filter, so its width is the 1100 nm cut rather than a red edge.
    ("LOT", "g"): dict(centroid=475.9, fwhm=147.0, peak=0.996, integral=146.6, leak=0.048),
    ("LOT", "r"): dict(centroid=627.8, fwhm=131.0, peak=0.995, integral=130.5, leak=0.031),
    ("LOT", "i"): dict(centroid=767.6, fwhm=145.0, peak=1.002, integral=145.2, leak=0.048),
    ("LOT", "z"): dict(centroid=962.1, fwhm=278.0, peak=0.998, integral=274.6, leak=0.000),
    # SLT, Astrodon 2018.
    ("SLT", "u"): dict(centroid=353.4, fwhm=63.0, peak=1.000, integral=64.8, leak=0.051),
    ("SLT", "g"): dict(centroid=476.2, fwhm=148.0, peak=1.000, integral=148.0, leak=0.042),
    ("SLT", "r"): dict(centroid=627.4, fwhm=131.0, peak=0.946, integral=121.9, leak=0.042),
    ("SLT", "i"): dict(centroid=771.8, fwhm=152.0, peak=1.000, integral=155.4, leak=0.055),
    ("SLT", "z"): dict(centroid=962.2, fwhm=275.0, peak=1.000, integral=275.4, leak=0.000),
    # SLT Johnson-Cousins, Astrodon 2018. Not in presets.json, which is Sloan
    # only; recorded because the U leak is the worst in the collection.
    ("SLT", "U"): dict(centroid=369.2, fwhm=45.0, peak=0.981, integral=43.6, leak=0.226),
    ("SLT", "B"): dict(centroid=427.2, fwhm=93.0, peak=0.983, integral=90.0, leak=0.071),
    ("SLT", "V"): dict(centroid=544.8, fwhm=98.0, peak=1.000, integral=97.3, leak=0.090),
    ("SLT", "Rc"): dict(centroid=656.4, fwhm=150.0, peak=0.984, integral=152.2, leak=0.087),
    ("SLT", "Ic"): dict(centroid=799.5, fwhm=158.0, peak=1.000, integral=156.8, leak=0.063),
}

#: Transmission at 1200 nm, the red end of the published measurements. Every one
#: of these filters is wide open in the infrared; what closes the band is the
#: detector, and how much leaks through depends on the source's colour. Johnson
#: U is the extreme: 96% at 1200 nm, and a fifth of everything it passes below
#: 1100 nm is already outside its own band.
TRANSMISSION_AT_1200 = {
    ("LOT", "g"): 0.38, ("LOT", "r"): 0.40, ("LOT", "i"): 0.31, ("LOT", "z"): 0.73,
    ("SLT", "u"): 0.39, ("SLT", "U"): 0.96, ("SLT", "B"): 0.83, ("SLT", "V"): 0.87,
}

#: Measured from a photon transfer curve: 89 adjacent same-night pairs, sky
#: levels 401-7002 e-, fitting var(A-B)/2 = sky + RON^2 over the difference
#: images so stars and flat structure drop out. The slope comes out 0.982,
#: which says the header's GAIN 0.92 is right and BUNIT = electron is honest.
#: The intercept puts read noise at 7.9 e-, between the -152 datasheet's 100 kHz
#: port (3.6 e-) and its 1 MHz port (8.5 e-) and much nearer the latter, and
#: consistent with the RMSNOISE 7.27 the headers carry.
MEASURED_READ_NOISE = 7.9

#: Princeton Instruments' SOPHIA 2048B datasheet, which Lulin publishes:
#: download/equipment/documents/lot/SOPHIA-2048B-2-4-port-Datasheet_sch.pdf
#: The **-152** column, which is the 15.0 um one and so ours; an earlier reading
#: of this suite took the -132 column, whose sensor is 13.5 um, and carried its
#: full well and read noise into presets.json. Both -152 sensor options quote
#: the same figures here, so the frame name SOPHIA-2048BX pointing at the
#: eXcelon variant rather than the plain e2v CCD230-42 changes none of them.
DATASHEET_152 = {
    "pixel_pitch_um": 15.0,
    "full_well_e": 150000,               # single pixel, typical
    "dark_at_minus_90_e_s": 0.00025,     # ambient air +20 C
    "read_noise_e": {100e3: 3.6, 1e6: 8.5, 4e6: 22.0},   # system, per port
    "gains_e_per_adu": (1, 2, 4),
}
MEASURED_GAIN_SLOPE = 0.982

#: Read off the QE curves on page 8 of the SOPHIA datasheet, the 2048B-152
#: which is the 15 um CCD230-42 this camera has. Two coatings are plotted;
#: these are the midband one, at our four band centres. Nearly flat across
#: g'r'i', which matters because it rules the detector out as the reason the
#: measured throughput in r' is 1.8x its neighbours' — whatever causes that,
#: it is not the CCD.
DATASHEET_QE = {"Sloan_g": 0.90, "Sloan_r": 0.96, "Sloan_i": 0.87, "Sloan_z": 0.28}

#: Lulin's SLT page names the camera in full: Andor iKon-M DU934P-BEX2-DD
#: CCD-26868. The BEX2-DD variant is what fixes the well depth at 130 ke-.
SLT_CAMERA = "Andor iKon-M DU934P-BEX2-DD CCD-26868"

#: Trebur's 2001 offer document, which Lulin publishes in full:
#: lulin.ncu.edu.tw/download/equipment/documents/lot/
#:     Offer_for_1m_Trebur_Cassegrain_Telescope.pdf
#: A classical Cassegrain — parabolic primary, hyperbolic secondary — and not
#: the Ritchey-Chretien this suite assumed before reading it. Diameters are
#: "outside" and "optical specified" as the document gives them; light is
#: blocked by the secondary's whole glass disc, so the obstruction is the
#: outside 360 and not the figured 350.
OFFER = {
    "primary_outside_mm": 1030.0, "primary_optical_mm": 1020.0,
    "primary_hole_mm": 280.0, "primary_focal_length_mm": 3000.0,
    "primary_conic": -1.0,                        # parabolic
    "secondary_outside_mm": 360.0, "secondary_optical_mm": 350.0,
    "secondary_conic": -4.84,                     # hyperbolic
    "secondary_roc_mm": -3229.0,
    "mirror_distance_mm": 1990.9, "focal_length_mm": 8000.0,
    "back_focus_mm": 700.12,
    "coating": "Al+SiO2", "coating_reflectivity": 0.90,
}

#: What MaxIm wrote into every frame. It is not the collecting area: it matches
#: pi/4 * (primary outside^2 - primary HOLE^2) to 0.08%, so whoever configured
#: it subtracted the hole through the middle of the primary instead of the
#: shadow the secondary casts on it. Dividing it by a nominal 1 m aperture is
#: what produced the phantom "130 mm secondary" this suite chased.
HEADER_APTAREA_M2 = 0.7721249559223652
HEADER_FOCAL_LENGTH_MM = (8016.5, 8026.4)      # varies with focus position
SOLVED_PIXEL_SCALE = 0.3841                    # arcsec, from the astrometric solution


def available():
    """True when the frames are checked out; the tests skip on False."""
    return FRAMES.is_dir() and any(FRAMES.glob("*.fits")) and CATALOGUE.is_dir()
