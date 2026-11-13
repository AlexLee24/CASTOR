"""AT2026afqt / SLT + DZ936, 2026-11-10: CASTOR's prediction against the frames.

Reads the two tables `reduce_slt_afqt.py` writes and asks four questions, each
one isolating a different part of CASTOR's chain:

1. Count rate. For every frame, CASTOR is run on that frame's own time, FWHM
   and exposure with the request the lab actually used on 2026-11-12
   (`castor_requests/SN2026afqt_SLT_<band>_300s.json`, i.e. the SLT_DZ936
   preset). Its predicted zero point (AB mag giving 1 e-/s in total, extinction
   and airmass included) is compared with the measured one. The difference is
   a throughput error and an extinction error together; the airmass slope of
   the difference separates them as far as one night can.
2. Sky. Measured sky e-/s/px against CASTOR's `sky_count_rate`, and the same
   as surface brightness, so the pixel-scale error and the sky-model error can
   be told apart.
3. Noise. For stars on every frame of a band, the frame-to-frame scatter
   (after dividing out each frame's transparency) against the noise CASTOR's
   `calculate_single_snr` predicts from that star's measured flux and sky —
   with the preset's read noise (7.0 e-) and the header's (5.92 e-). This is
   `endtoend.py`'s test, on SLT.
4. The supernova. Its measured magnitude and SNR per frame, against what the
   shipped request would have predicted at that magnitude.

Run: uv run --with numpy --with pandas --with astropy --with pydantic \
     python -I validation/analyze_slt_afqt.py <reduce_out_dir> <castor_requests_dir>
"""
import copy
import json
import os
import sys

import numpy as np
import pandas as pd
import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, get_body
from astropy.time import Time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from castor import calculator, physics, schema  # noqa: E402

RN_PRESET, RN_HEADER = 7.0, 5.92
DARK = 0.00013
APERTURE_K, ANN_IN, ANN_OUT = 1.5, 4.0, 6.0   # what reduce_slt_afqt.py measured with
REF_MAG = 16.0
PEAK_CUT_E = 50_000


def load_requests(req_dir):
    return {b: json.load(open(os.path.join(req_dir, f"SN2026afqt_SLT_{b}_300s.json")))
            for b in "ugriz"}


def castor(req, *, t_mid, fwhm_arcsec, exptime, mag, aperture_k=None, ann=None,
           focal_length=None, rn=None):
    r = copy.deepcopy(req)
    r["environment"]["observing_time_utc"] = t_mid
    r["environment"]["total_fwhm"] = fwhm_arcsec
    r["options"]["single_exp_time"] = exptime
    r["options"]["num_exposures"] = 1
    r["target"]["brightness"]["target_mag"] = mag
    if aperture_k is not None:
        r["options"]["aperture_factor"] = aperture_k
    if ann is not None:
        r["options"]["sky_annulus"]["inner_factor"], r["options"]["sky_annulus"]["outer_factor"] = ann
    if focal_length is not None:
        r["instrument"]["telescope"]["focal_length"] = focal_length
    if rn is not None:
        r["instrument"]["camera"]["readout_noise"] = rn
    return calculator.run_calculation(schema.ObservationRequest.model_validate(r))


def per_frame_prediction(frames, reqs):
    out = []
    for f in frames.itertuples():
        t_mid = Time(f.mjd_mid, format="mjd").isot[:19] + "Z"
        fw = f.fwhm_px * f.pixscale
        o = castor(reqs[f.band], t_mid=t_mid, fwhm_arcsec=fw, exptime=f.exptime, mag=REF_MAG)
        d = o.diagnostics
        total_rate = o.budget.source_count_rate / d.enclosed_flux_fraction
        out.append(dict(
            zp_pred=REF_MAG + 2.5 * np.log10(total_rate),
            airmass_pred=d.airmass, sky_rate_pred=o.budget.sky_count_rate,
            mu_sky_pred=d.sky_surface_brightness, pixscale_pred=d.pixel_scale,
            moon_alt=o.ephemeris.moon_elevation_deg,
            moon_sep=o.ephemeris.moon_separation_deg,
            moon_phase=o.ephemeris.moon_phase_angle_deg,
        ))
    return pd.concat([frames.reset_index(drop=True), pd.DataFrame(out)], axis=1)


K_CASTOR = 0.17          # presets.json's site-wide extinction, used for every band
ZP_ERR_MAX = 0.05        # two i' frames (17:55, 18:39) sit at 0.2: stars disagree, frame is bad
X_FIT_MAX = 3.0          # beyond this, colour-dependent extinction and twilight take over
X_DARK_SKY = 1.6         # sky compared near the meridian only
TRANSIT_MJD = 61354.656  # 2026-11-10 ~15:45 UTC, airmass minimum 1.107


def erased_frames(stars):
    """Frames where the delivered calibration has wiped bright stars out.

    On 12 i'/z' frames, all after the meridian flip and all with the night's
    sharpest seeing (FWHM <= 2.26 px), stars brighter than 15.5 come back at
    2-10% of their usual flux and the pixels where they should be hold runs of
    repeated values: something in the delivered calibration, which leaves no
    header record, has replaced them with neighbours. Not CASTOR's doing; those
    frames are removed from everything below rather than corrected.
    """
    s = stars[stars["mag"] < 15.5].copy()
    s["rel"] = s["net_big"] / s.groupby(["id", "band"])["net_big"].transform("median")
    return set(s.loc[s["rel"] < 0.3, "file"])


def flag_frames(fr, erased=frozenset()):
    fr = fr.copy()
    fr["erased"] = fr["file"].isin(erased)
    loc = EarthLocation(lat=23.4694 * u.deg, lon=120.8724 * u.deg, height=2862 * u.m)
    t = Time(fr["mjd_mid"].values, format="mjd")
    fr["sun_alt"] = get_body("sun", t).transform_to(AltAz(obstime=t, location=loc)).alt.deg
    fr["good"] = (fr["zp_err"] < ZP_ERR_MAX) & ~fr["erased"]
    fr["branch"] = np.where(fr["mjd_mid"] < TRANSIT_MJD, "rising", "setting")
    fr["dzp"] = fr["zp"] - fr["zp_pred"]                  # >0: more counts than predicted
    fr["sky_rate"] = fr["sky_e"] / fr["exptime"]
    return fr


def _fit(g):
    A = np.vstack([np.ones(len(g)), g["airmass"]]).T
    coef, res, *_ = np.linalg.lstsq(A, g["zp"], rcond=None)
    rms = float(np.std(g["zp"] - A @ coef))
    return coef[0], -coef[1], rms


def q1_extinction_throughput(fr):
    """ZP = ZP0 - k X on the good frames, both branches together and apart.

    The field rises to the meridian and sets again, so time and airmass are not
    the same variable here: a transparency drift would make the two branches
    disagree. Where they agree, k is an extinction and ZP0 a throughput.
    """
    rows = []
    for band, g in fr[fr["good"] & (fr["airmass"] < X_FIT_MAX)].groupby("band"):
        zp0, k, rms = _fit(g)
        kr = _fit(g[g["branch"] == "rising"])[1] if (g["branch"] == "rising").sum() >= 4 else np.nan
        ks = _fit(g[g["branch"] == "setting"])[1]
        # CASTOR's own zero point above the atmosphere: its prediction with
        # its own k*X added back, constant by construction.
        zp0_castor = float((g["zp_pred"] + K_CASTOR * g["airmass_pred"]).median())
        rows.append(dict(band=band, n=len(g), X=f"{g['airmass'].min():.2f}-{g['airmass'].max():.2f}",
                         k=round(k, 3), k_rising=round(kr, 3), k_setting=round(ks, 3),
                         k_castor=K_CASTOR, fit_rms=round(rms, 3),
                         zp0=round(zp0, 3), zp0_castor=round(zp0_castor, 3),
                         throughput_obs_over_castor=round(10 ** (0.4 * (zp0 - zp0_castor)), 3),
                         counts_obs_over_castor_X1_2=round(
                             10 ** (0.4 * ((zp0 - k * 1.2) - (zp0_castor - K_CASTOR * 1.2))), 3)))
    return pd.DataFrame(rows)


def q2_sky(fr, ext):
    """Measured sky against CASTOR's, astronomical night and near the meridian.

    CASTOR's mu_sky is a ground-level surface brightness and gets no
    extinction, so the measured one is put on the same footing with the
    fitted zero point at the frame's own airmass (i.e. the measured zp, which
    already includes the atmosphere) plus k*X back to the top: the sky is
    scattered light *in* the atmosphere, and the top-of-atmosphere zero point
    is the one that converts its counts to the ground-level brightness CASTOR
    tabulates.
    """
    k = ext.set_index("band")["k"]
    sel = fr[fr["good"] & (fr["sun_alt"] < -18) & (fr["airmass"] < X_DARK_SKY)].copy()
    sel["mu_obs"] = (sel["zp"] + sel["band"].map(k) * sel["airmass"]
                     - 2.5 * np.log10(sel["sky_rate"] / sel["pixscale"] ** 2))
    rows = []
    for (band, exp), g in sel.groupby(["band", "exptime"]):
        rows.append(dict(band=band, exptime=exp, n=len(g),
                         mu_obs=round(float(g["mu_obs"].median()), 2),
                         mu_obs_range=f"{g['mu_obs'].min():.2f}-{g['mu_obs'].max():.2f}",
                         mu_castor=round(float(g["mu_sky_pred"].median()), 2),
                         sky_rate_obs=round(float(g["sky_rate"].median()), 3),
                         sky_rate_castor=round(float(g["sky_rate_pred"].median()), 3),
                         rate_obs_over_castor=round(float((g["sky_rate"] / g["sky_rate_pred"]).median()), 3)))
    return pd.DataFrame(rows)


def implied_read_noise(fr, stars):
    """Local sky std^2 = sky + RN^2 + anything else (flat residuals, fringes).

    Uses the annuli around the noise-test stars, not the whole frame, so
    large-scale gradients stay out. Whatever is left above the header's read
    noise is extra pixel noise CASTOR does not model.
    """
    loc = stars.groupby("file").agg(sky_loc=("sky", "median"), std_loc=("sky_std", "median"))
    f = fr[fr["good"] & (fr["sun_alt"] < -18)].join(loc, on="file")
    f["rn_implied"] = np.sqrt(np.clip(f["std_loc"] ** 2 - f["sky_loc"], 0, None))
    f["excess_over_header"] = np.sqrt(np.clip(f["std_loc"] ** 2 - f["sky_loc"] - RN_HEADER ** 2, 0, None))
    return f.groupby(["band", "exptime"])[["sky_loc", "std_loc", "rn_implied", "excess_over_header"]].median().round(2)


def q3(stars, frames):
    rows = []
    frames = frames[frames["good"] & (frames["airmass"] < X_DARK_SKY) & (frames["sun_alt"] < -18)]
    # Per side of the pier: after the flip every star lands on different
    # pixels, and flat-field error between the two halves is not a noise term.
    for (band, exp, branch), fg in frames.groupby(["band", "exptime", "branch"]):
        files = set(fg["file"])
        s = stars[stars["file"].isin(files)].copy()
        nf = len(files)
        if nf < 6:
            continue
        # Stars clean on every frame of this group.
        ok = s.groupby("id").filter(
            lambda g: len(g) == nf and (g["net_snr"] > 0).all() and (g["peak"] < PEAK_CUT_E).all())
        if ok.empty:
            continue
        # Transparency *and* aperture loss per frame, from the bright stars in
        # the same 1.5 x FWHM aperture: the fraction of light inside it moves
        # with the PSF's shape, which a 2.5 x FWHM normaliser does not see.
        med_star = ok.groupby("id")["net_snr"].transform("median")
        ok["rel"] = ok["net_snr"] / med_star
        bright_ids = ok.groupby("id")["net_snr"].median().nlargest(15).index
        cf = ok[ok["id"].isin(bright_ids)].groupby("file")["rel"].median()
        ok["F"] = ok["net_snr"] / ok["file"].map(cf)
        ok["sky_n"] = ok["sky"] / ok["file"].map(cf)
        n_est = (np.pi / 2) * ok["area_snr"] ** 2 / ok["n_ann"]
        for tag, rn in (("preset", RN_PRESET), ("header", RN_HEADER)):
            snr = physics.calculate_single_snr(
                source_count_rate=ok["F"].values / exp, sky_count_rate=ok["sky"].values / exp,
                dark_current_rate=DARK, readout_noise=rn,
                num_pixels_aperture=ok["area_snr"].values, single_exp_time=exp,
                num_pixels_sky_estimate=n_est.values)
            ok[f"sig_{tag}"] = ok["F"] / snr
        # Measured pixel noise in place of any model: the annulus std itself.
        ok["sig_pix"] = np.sqrt(np.clip(ok["F"], 0, None)
                                + (ok["area_snr"] + n_est) * ok["sky_std"] ** 2)
        mean_F = ok.groupby("id")["F"].transform("mean")
        corr = np.sqrt(nf / (nf - 1))
        per = []
        for sid, g in ok.groupby("id"):
            res = (g["F"] - g["F"].mean()) * corr
            per.append(dict(id=sid, flux=g["F"].median(), mag=g["mag"].iloc[0],
                            **{f"ratio_{t}": 1 / np.sqrt(np.mean((res / g[f"sig_{t}"]) ** 2))
                               for t in ("preset", "header", "pix")},
                            snr_obs=g["F"].mean() / (g["F"].std())))
        per = pd.DataFrame(per)
        edges = [0, 3e3, 1e4, 3e4, 1e5, 3e5, np.inf]
        per["bin"] = pd.cut(per["flux"], edges)
        for b, g in per.groupby("bin", observed=True):
            if len(g) < 5:
                continue
            rows.append(dict(band=band, exptime=exp, branch=branch, frames=nf, flux_bin=str(b), n=len(g),
                             mag_med=round(g["mag"].median(), 2),
                             snr_obs_med=round(g["snr_obs"].median(), 1),
                             obs_pred_preset=round(g["ratio_preset"].median(), 3),
                             obs_pred_header=round(g["ratio_header"].median(), 3),
                             obs_pred_pixnoise=round(g["ratio_pix"].median(), 3)))
    return pd.DataFrame(rows)


def q4(fr, reqs, fixed_reqs=None):
    rows = []
    for f in fr[fr["good"] & (fr["sun_alt"] < -18)].itertuples():
        if f.sn_net_big <= 0:
            continue
        mag = f.zp - 2.5 * np.log10(f.sn_net_big / f.exptime)
        n_est = (np.pi / 2) * f.sn_area_snr ** 2 / f.sn_n_ann
        snr_meas = f.sn_net_snr / np.sqrt(f.sn_net_snr + (f.sn_area_snr + n_est) * f.sn_sky_std ** 2)
        t_mid = Time(f.mjd_mid, format="mjd").isot[:19] + "Z"
        fw = f.fwhm_px * f.pixscale
        shipped = castor(reqs[f.band], t_mid=t_mid, fwhm_arcsec=fw, exptime=f.exptime, mag=mag)
        same_ap = castor(reqs[f.band], t_mid=t_mid, fwhm_arcsec=fw, exptime=f.exptime, mag=mag,
                         aperture_k=APERTURE_K, ann=(ANN_IN, ANN_OUT))
        fixed = castor(fixed_reqs[f.band], t_mid=t_mid, fwhm_arcsec=fw, exptime=f.exptime, mag=mag,
                       aperture_k=APERTURE_K, ann=(ANN_IN, ANN_OUT)) if fixed_reqs else None
        rows.append(dict(band=f.band, exptime=f.exptime, date_obs=f.date_obs,
                         airmass=round(f.airmass, 2), mag=round(mag, 3),
                         snr_meas=round(snr_meas, 1),
                         snr_castor_same_ap=round(same_ap.core.single_snr, 1),
                         snr_castor_corrected=round(fixed.core.single_snr, 1) if fixed else np.nan,
                         snr_castor_shipped=round(shipped.core.single_snr, 1)))
    return pd.DataFrame(rows)


def corrected_requests(reqs, ext, sky):
    """The shipped requests with every input this night measured put back in.

    Focal length from the header, read noise from the header (and the u'
    frames' own sky noise, which agree), extinction per band from Q1, the
    count-rate ratio from Q1 as `throughput_correction`, and the sky from Q2
    as a fixed mu with no moon or zodiacal term (moon below -35 deg all night).
    If CASTOR's engine is right, this is what it should have said.
    """
    out = {}
    e = ext.set_index("band")
    m = sky.groupby("band")["mu_obs"].median()
    for b, r in reqs.items():
        r = copy.deepcopy(r)
        r["instrument"]["telescope"]["focal_length"] = 3.5228
        r["instrument"]["camera"]["readout_noise"] = RN_HEADER
        # throughput_correction is capped at 1 by the schema, and g'/r' need >1.
        r["instrument"]["telescope"]["optical_throughput"] *= float(e.loc[b, "throughput_obs_over_castor"])
        r["environment"]["extinction_coeff"] = float(e.loc[b, "k"])
        r["environment"]["auto_calc_background"] = False
        r["environment"]["zodiacal_share"] = None
        r["environment"]["mu_dark"] = float(m.loc[b])
        out[b] = r
    return out


def q5_sn_empirical(fr, cal):
    """The supernova's own frame-to-frame scatter, per band and pier side.

    Its flux in the 1.5 x FWHM aperture divided by the frame's transparency
    and aperture factor (bright comparison stars, same aperture), then
    mean/std over the frames. A supernova does not change measurably within a
    few hours, so this is a noise measurement that does not depend on how
    smooth the host galaxy is around it.
    """
    rows = []
    for (band, exp, branch), g in fr[fr["good"] & (fr["airmass"] < X_DARK_SKY)].groupby(
            ["band", "exptime", "branch"]):
        if len(g) < 5:
            continue
        F = g["sn_net_snr"] / g["file"].map(cal)
        rows.append(dict(band=band, exptime=exp, branch=branch, frames=len(g),
                         snr_empirical=round(float(F.mean() / F.std()), 1)))
    return pd.DataFrame(rows)


def frame_calibration(stars, fr):
    out = {}
    good = fr[fr["good"]]
    s = stars[stars["file"].isin(good["file"])].copy()
    for (band, branch), g in good.groupby(["band", "branch"]):
        ss = s[s["file"].isin(g["file"])]
        n = len(g)
        full = ss.groupby("id").filter(lambda x: len(x) == n and (x["peak"] < PEAK_CUT_E).all())
        if full.empty:
            continue
        rel = full["net_snr"] / full.groupby("id")["net_snr"].transform("median")
        bright = full.groupby("id")["net_snr"].median().nlargest(15).index
        cf = rel[full["id"].isin(bright)].groupby(full["file"]).median()
        out.update(cf.to_dict())
    return pd.Series(out)


def main(red_dir, req_dir):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 200)
    frames = pd.read_csv(os.path.join(red_dir, "frames.csv"))
    stars = pd.read_csv(os.path.join(red_dir, "stars.csv"))
    reqs = load_requests(req_dir)
    fr = flag_frames(per_frame_prediction(frames, reqs), erased_frames(stars))
    print("== erased frames:", int(fr["erased"].sum()), "| zp_err bad:", int((fr["zp_err"] >= ZP_ERR_MAX).sum()))
    print("== frames: good", int(fr["good"].sum()), "of", len(fr),
          "| astronomical night", int((fr["sun_alt"] < -18).sum()),
          "| last dark frame", fr.loc[fr["sun_alt"] < -18, "date_obs"].max())
    print("== frame geometry\n", fr[["pixscale", "pixscale_pred"]].describe().round(3).T)
    print("== moon\n", fr[["moon_alt", "moon_sep", "moon_phase"]].describe().round(1).T)
    ext = q1_extinction_throughput(fr)
    print("== Q1 extinction and throughput\n", ext.to_string(index=False))
    summary = q2_sky(fr, ext)
    print("== Q2 sky, sun < -18, X < %.1f\n" % X_DARK_SKY, summary.to_string(index=False))
    print("== local pixel noise\n", implied_read_noise(fr, stars))
    q3t = q3(stars, fr)
    print("== Q3 noise: SNR_obs / SNR_pred per flux bin\n", q3t.to_string(index=False))
    fixed = corrected_requests(reqs, ext, summary)
    sn = q4(fr, reqs, fixed)
    print("== Q4 supernova\n", sn.groupby(["band", "exptime"]).median(numeric_only=True).round(2))
    print("== Q5 supernova, empirical scatter\n", q5_sn_empirical(fr, frame_calibration(stars, fr)).to_string(index=False))
    fr.to_csv(os.path.join(red_dir, "frames_vs_castor.csv"), index=False)
    ext.to_csv(os.path.join(red_dir, "summary_q1.csv"), index=False)
    summary.to_csv(os.path.join(red_dir, "summary_q2.csv"), index=False)
    q3t.to_csv(os.path.join(red_dir, "summary_q3.csv"), index=False)
    sn.to_csv(os.path.join(red_dir, "sn_vs_castor.csv"), index=False)


if __name__ == "__main__":
    main(*sys.argv[1:3])
