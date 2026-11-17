"""SLT and LOT throughput from Kinder's own photometry, 2025-11 to 2026-11 (QUESTIONS.md 19).

Kinder's Pipeline ran AutoPhOT on calibrated Lulin frames with PSF photometry against Pan-STARRS DR2. Its zero
point zp_psf is the AB magnitude of 1 "electron"/s, with no extinction removed, so

    T_sys = 10^(0.4 (ZP + k X)) * E_phot / (F_lambda(AB 0) * dlambda * A_eff)        (k = 0.17, presets.json's GUESS)

What AutoPhOT called electrons was pixels x the gain it read, and the pixels are not always electrons. Lulin's
reduction divides back to ADU (BUNIT adu); an older version kept electrons (BUNIT electron). AutoPhOT read LOT's
GAIN 0.92 and fell back to 1 for SLT's '0.95 [electrons/ADU]' / '1.088 [electrons/ADU]'. So the true zero point is
ZP + 2.5 log10(g_true / g_used), with g_true = 1 for electron frames and the header gain for ADU frames.

The optical train presets.json stores is T_sys / (QE_band * filter_transmission), with each camera's QE in that band
(presets.json filters.*.camera, read off Andor's published curves). Medians per camera. 2026-08-29 SLT frames are left
out: one raw frame was calibrated twice, with gain 1.088 and 2 (the gain-2 copies have since been moved aside).
"""

#: SLT T_sys (above the atmosphere, incl. filter) per band and camera, 2026
SLT_TSYS_2026 = {
    "g": {"SLT_DU934P": 0.367, "SLT_DZ936": 0.356},
    "r": {"SLT_DU934P": 0.606, "SLT_DZ936": 0.571},
    "i": {"SLT_DU934P": 0.553, "SLT_DZ936": 0.356},
    "z": {"SLT_DU934P": 0.173, "SLT_DZ936": 0.076},
}
#: the same, as the optical train through each camera's band QE: what should agree if the QE curves are right
SLT_OPTICS_2026 = {
    "g": {"SLT_DU934P": 0.409, "SLT_DZ936": 0.411},
    "r": {"SLT_DU934P": 0.669, "SLT_DZ936": 0.604},
    "i": {"SLT_DU934P": 0.591, "SLT_DZ936": 0.434},     # DZ936: one frame
    "z": {"SLT_DU934P": 0.347, "SLT_DZ936": 0.232},     # DZ936: one frame
}
SLT_2026_NIGHTS = {"SLT_DU934P": ["2026-10-04"], "SLT_DZ936": ["2026-11-09", "2026-11-16"]}

#: LOT/SOPHIA, SN2025wny 2025-11-16 to 2026-10-12, same method: median optical train (flat QE 0.85)
LOT_2026 = {"g": {"median": 0.326}, "r": {"median": 0.577}, "i": {"median": 0.338}}


def preset_value(band):
    """SLT's band optical train in presets.json: the two cameras' mean."""
    a, b = SLT_OPTICS_2026[band]["SLT_DU934P"], SLT_OPTICS_2026[band]["SLT_DZ936"]
    return round((a + b) / 2, 3)
