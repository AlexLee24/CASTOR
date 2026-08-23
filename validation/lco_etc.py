"""Las Cumbres Observatory's exposure time calculator, transcribed.

Source: https://exposure-time-calculator.lco.global/jquery.etczp.js?v=9
Authors: Andrew Pickles and Doug Thomas; 2023 revision by Daniel Harbeck.

Transcribed rather than queried so this suite stays offline and deterministic.
Retrieved 2026-08-22; `test_lco.py` pins a handful of outputs captured from the
live page on that date, so a silent upstream change shows up as a failure here
rather than as a mystery in someone's comparison spreadsheet.

The one thing to understand before comparing anything against it: since Harbeck's
2023 revision this is not a physical model. It is a lookup of *measured*
photometric zero points, and their own source says so — the collecting-area table
is annotated "not used in code", the zero-point flux table is commented out, and
the throughput it reports back is undefined. There is no aperture, no bandwidth,
no quantum efficiency and no photon energy anywhere in the calculation. CASTOR
predicts these numbers from an optical train; LCO looks them up from images they
took. Agreement between the two is a calibration check, not an independent
verification of either.
"""
import numpy as np

FILTERS = ("U", "B", "V", "R", "I", "u", "g", "r", "i", "Z", "Y")
INSTRUMENTS = ("0m4 SBIG", "1m0 Sinistro", "0m4 QHY", "2m0 Spectral", "2m0 MuSCAT3")

CENTRAL_WAVELENGTH_UM = (0.350, 0.437, 0.549, 0.653, 0.789, 0.354, 0.476, 0.623, 0.760, 0.853, 0.975)
BANDWIDTH_UM = (0.050, 0.107, 0.083, 0.137, 0.128, 0.057, 0.140, 0.135, 0.148, 0.113, 0.118)
EXTINCTION = (0.54, 0.23, 0.12, 0.09, 0.04, 0.59, 0.14, 0.08, 0.06, 0.04, 0.03)

#: Commented out in their source since the 2023 revision, kept because CASTOR
#: still needs a zero-point flux to convert a magnitude into F_lambda.
ZERO_POINT_JY = (1755, 4050, 3690, 3060, 2540, 3680, 3631, 3631, 3631, 3631, 3631)

#: Annotated "not used in code" upstream. cm².
COLLECTING_AREA_CM2 = (1200.0, 6260.0, 660.0, 27000.0, 27000.0)
PIXEL_SCALE = (0.57, 0.389, 0.73, 0.304, 0.27)
GAIN = (1.6, 2.3, 0.7, 7.7, 1.9)
READ_NOISE = (14.0, 8.0, 3.0, 11.0, 14.5)
DARK_CURRENT = (0.02, 0.002, 0.04, 0.002, 0.005)

#: log10(e-/s) for a zero-magnitude source. 0.0 means no data or no such filter.
ZERO_POINT_MAG = (
    (18.0, 20.3, 20.7, 21.2, 20.3, 16.11, 21.4, 21.5, 20.75, 19.4, 17.8),
    (21.4, 23.5, 23.5, 23.8, 23.2, 22.45, 24.3, 23.8, 23.5, 22.2, 20.3),
    (0.0, 21.4, 21.4, 21.2, 20.3, 17.5, 21.8, 21.2, 20.1, 18.4, 0.0),
    (21.3, 24.4, 24.6, 24.9, 24.1, 21.4, 25.4, 25.25, 24.75, 23.75, 21.6),
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 25.4, 25.2, 24.5, 24.3, 0.0),
)

#: mag/arcsec², at new / half / full moon. UBVRI Vega, ugriz AB.
SKY_BRIGHTNESS = (
    (23.0, 22.5, 21.6, 20.6, 19.8, 23.5, 22.0, 21.1, 20.6, 20.2, 19.4),
    (20.0, 20.5, 20.3, 20.0, 18.8, 21.0, 20.3, 20.2, 19.7, 19.2, 18.0),
    (17.0, 17.8, 17.5, 17.4, 17.0, 18.0, 17.6, 17.5, 17.5, 16.8, 16.5),
)

APERTURE_DIAMETER_ARCSEC = 3.0


def sky_rate(instrument, band, moon_phase):
    """e-/s/pix from the sky.

    Note what is absent: airmass. LCO applies extinction to the object only, so
    their background is the same at the zenith as at airmass 2.
    """
    f = FILTERS.index(band)
    mu = SKY_BRIGHTNESS[moon_phase][f]
    per_arcsec2 = 10.0 ** (-0.4 * (mu - ZERO_POINT_MAG[instrument][f]))
    return per_arcsec2 * PIXEL_SCALE[instrument] ** 2


def source_rate(instrument, band, magnitude, airmass):
    """e-/s from the target.

    The airmass term is (X-1)·k, not X·k: their magnitudes are referred to the
    zenith, where CASTOR's are above the atmosphere. Feed both the same number
    and they disagree by a flat 10^(-0.4k) per band before anything else.
    """
    f = FILTERS.index(band)
    at_airmass = magnitude + (airmass - 1.0) * EXTINCTION[f]
    return 10.0 ** (-0.4 * (at_airmass - ZERO_POINT_MAG[instrument][f]))


def aperture(instrument):
    """(arcsec² in the aperture, pixels in the aperture).

    A fixed 3" aperture with no seeing term, and no enclosed-flux fraction — the
    measured zero point already refers to a star's total light.
    """
    area = np.pi / 4.0 * APERTURE_DIAMETER_ARCSEC ** 2
    return area, area / PIXEL_SCALE[instrument] ** 2


def snr(instrument, band, magnitude, airmass, exposure_time, moon_phase):
    _, n_pix = aperture(instrument)
    n_object = source_rate(instrument, band, magnitude, airmass) * exposure_time
    n_sky = sky_rate(instrument, band, moon_phase) / PIXEL_SCALE[instrument] ** 2
    n_sky = n_sky * aperture(instrument)[0] * exposure_time
    n_dark = n_pix * DARK_CURRENT[instrument] * exposure_time
    n_read = n_pix * READ_NOISE[instrument] ** 2
    return n_object / np.sqrt(n_object + n_sky + n_dark + n_read)


def implied_throughput(instrument, band):
    """The T_sys CASTOR would need to reproduce this zero point.

    Inverting their calibration through CASTOR's own chain. Useful mostly as a
    smell test: a physical throughput lands somewhere near 0.2-0.6, and the
    entries that do not are the ones nobody has re-measured.
    """
    from castor import physics

    f = FILTERS.index(band)
    lam_angstrom = CENTRAL_WAVELENGTH_UM[f] * 1e4
    f_lambda = (ZERO_POINT_JY[f] * 1e-23
                * (physics.SPEED_OF_LIGHT_CGS * 1e8) / lam_angstrom ** 2)
    photon_energy = physics.calculate_photon_energy(CENTRAL_WAVELENGTH_UM[f] * 1e3)
    unit_rate = (f_lambda * BANDWIDTH_UM[f] * 1e4
                 * COLLECTING_AREA_CM2[instrument] / photon_energy)
    return 10.0 ** (0.4 * ZERO_POINT_MAG[instrument][f]) / unit_rate
