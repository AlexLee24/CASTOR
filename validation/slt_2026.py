"""SLT and LOT throughput from Kinder's own photometry, 2025-11 to 2026-11 (QUESTIONS.md 19).

Kinder's Pipeline ran AutoPhOT on calibrated Lulin frames (already in electrons) with PSF photometry
calibrated against Pan-STARRS DR2. Its zero point zp_psf is the AB magnitude of 1 e-/s, with no
extinction removed, so the optical train above the atmosphere is

    optical_throughput = 10^(0.4 (ZP + k X)) * E_phot / (F_lambda(AB 0) * dlambda * A_eff * QE * T_filter)

with k = 0.17 (presets.json's extinction, a GUESS) and the preset's own QE, filter and geometry, i.e. the
quantity presets.json stores per telescope and band. LOT single frames carry GAIN 0.92 although their
pixels are electrons, so AutoPhOT scaled their flux by 0.92: their ZP is corrected by +0.0905 mag here
(fixed in Kinder for later runs, Kinder_web PR #113). SLT frames have no usable GAIN, AutoPhOT used 1,
which is right for electrons.

Medians per camera; nights are MJD - 0.5 rounded down. 2026-08-29 SLT frames are excluded: one raw frame
was calibrated twice (gain 1.088 and 2) and neither copy is in electrons (sky rms^2/sky 3.3 and 6.6).
"""

#: SLT, implied optical train per band and camera (Pan-STARRS, k = 0.17)
SLT_2026 = {
    "g": {"SLT_DU934P": 0.398, "SLT_DZ936": 0.418},
    "r": {"SLT_DU934P": 0.658, "SLT_DZ936": 0.671},
    # camera-dependent: presets.json has one number per telescope and band, and a flat QE per camera
    "i": {"SLT_DU934P": 0.598, "SLT_DZ936": 0.416},
    "z": {"SLT_DU934P": 0.187, "SLT_DZ936": 0.090},
}
#: frames and nights behind SLT_2026
SLT_2026_NIGHTS = {"SLT_DU934P": ["2026-10-04"], "SLT_DZ936": ["2026-11-09", "2026-11-16"]}

#: LOT/SOPHIA, same method, SN2025wny 2025-11-16 to 2026-10-12: median and the clear-night (best-frame) values
LOT_2026 = {
    "g": {"median": 0.330, "by_night": {"2025-12-17": 0.290, "2026-02-12": 0.315, "2026-09-17": 0.364, "2026-10-12": 0.356}},
    "r": {"median": 0.589, "by_night": {"2025-11-16": 0.584, "2026-02-10": 0.565, "2026-09-12": 0.648, "2026-10-10": 0.623}},
    "i": {"median": 0.338, "by_night": {"2025-12-12": 0.339, "2026-02-11": 0.333}},
}
#: 2026-04-08 gave r 0.377 and g 0.179 on both frames: cloud, left out of by_night


def preset_value(band):
    """The number presets.json carries for SLT in a band measured here the same way on both cameras."""
    a, b = SLT_2026[band]["SLT_DU934P"], SLT_2026[band]["SLT_DZ936"]
    return round((a + b) / 2, 3)
