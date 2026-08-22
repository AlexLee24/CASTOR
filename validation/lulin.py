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

#: Measured from a photon transfer curve: 89 adjacent same-night pairs, sky
#: levels 401-7002 e-, fitting var(A-B)/2 = sky + RON^2 over the difference
#: images so stars and flat structure drop out. The slope comes out 0.982,
#: which says the header's GAIN 0.92 is right and BUNIT = electron is honest.
#: The intercept puts read noise at 7.9 e-, squarely the datasheet's 1 MHz port
#: (7 e-) rather than 100 kHz (3.5 e-), and consistent with the RMSNOISE 7.27
#: the headers carry. So the preset's 7.0 is measured, not assumed.
MEASURED_READ_NOISE = 7.9
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

#: What MaxIm wrote into every frame, against what the preset assumes.
#: APTAREA implies a 130 mm central obstruction on a 1 m primary, which is small
#: for an f/8 Ritchey-Chretien; the preset says 300 mm, which is typical. Lulin
#: does not publish the figure and the two disagree by 8% in collecting area.
HEADER_APTAREA_M2 = 0.7721249559223652
HEADER_FOCAL_LENGTH_MM = (8016.5, 8026.4)      # varies with focus position
SOLVED_PIXEL_SCALE = 0.3841                    # arcsec, from the astrometric solution


def available():
    """True when the frames are checked out; the tests skip on False."""
    return FRAMES.is_dir() and any(FRAMES.glob("*.fits")) and CATALOGUE.is_dir()
