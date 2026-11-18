"""Zero points and sky for calibrated LOT + SOPHIA frames, compared with CASTOR.

Two LOT bands had no measurement of their own and fell back to LOT's band-free
optical_throughput 0.381: u' (`up_Astrodon_2017`, QUESTIONS.md 7) and z'
(`zp_Astrodon_2019`). Both turn up in the pipeline's `Calibrated_Science`
folder, on the same two nights:

* u'  GRB261011A 2026-10-11 4 x 300 s (X 1.50 -> 1.41); EP261006a 2026-10-10 1 x 300 s (X 1.22)
* z'  GRB261011A 2026-10-11 5 x 60 s + 30 x 90 s;      EP261006a 2026-10-10 1 x 300 s

Each frame was calibrated with that night's master bias, dark and flat for its
band, then multiplied by the gain (0.92 e-/ADU), so pixels are electrons even
though BUNIT says 'adu'. The sky is not subtracted. The WCS is a normal
astrometry.net TAN-SIP solution, so astropy reads it directly.

References, from `fetch_lot_catalogs.py`:

* Gaia DR3 synthetic photometry (GSPC) `<band>_sdss_mag`, standardised to SDSS.
  This is the primary reference, because the Astrodon filters are SDSS-style.
  GSPC flag 1 and flag 0 stars are also reported separately.
* SkyMapper DR4 PSF magnitudes, as a check. SkyMapper u is bluer and narrower
  than SDSS u, so it is not expected to agree exactly.
* Pan-STARRS DR2 mean PSF magnitudes (z' only), the catalogue LOT's g'r'i'
  rows were measured against in `lulin.py`, with no colour term, as there.

The CASTOR side is built from `presets.json` itself (LOT, Sophia, the band's
Sloan filter), so k, the dark sky and the throughput are whatever the preset
holds now. Neither night spans enough airmass to fit k, so ZP0 = ZP + k X uses
the preset's k on both sides; the ratio between them is then the factor the
preset's optical_throughput is off by, and `tput_implied` is that factor times
the preset value.

Run: uv run --with numpy --with pandas --with astropy --with photutils --with pydantic \
     python -I validation/reduce_lot_calibrated.py <up|zp> <frames_dir> <catalog_dir> <out_dir>
"""
import copy
import glob
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from astropy.io import fits
from astropy.stats import sigma_clip, sigma_clipped_stats
from astropy.time import Time
from astropy.wcs import WCS
from photutils.aperture import CircularAnnulus, CircularAperture, aperture_photometry
from photutils.centroids import centroid_com, centroid_sources

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from castor import calculator, schema  # noqa: E402
from castorCLI import presets  # noqa: E402

#: frame-name filter -> the band's SDSS letter, its preset filter, and which checks exist
BANDS = {
    "up": dict(band="u", preset="Sloan_u", checks=("skymapper",)),
    "zp": dict(band="z", preset="Sloan_z", checks=("skymapper", "ps1")),
}
EDGE = 40
PEAK_CUT_E = 50_000        # 16-bit x 0.92 e-/ADU = 60k e-, minus the ~560 e- bias already removed
ISOLATION_ARCSEC = 12.0
E_MAX = 0.05               # catalogue error cut
REF_MAG = 16.0
APCOR_R = 6.0              # "total" aperture radius, in FWHM


def load_refs(cat_dir, field, band, checks):
    b = band
    g = pd.read_csv(os.path.join(cat_dir, f"gaia_{field}.csv"))
    allsrc = g[["ra", "dec", "phot_g_mean_mag"]].dropna()
    gb = g[g[f"{b}_sdss_mag"].notna()].copy()
    gb["e_mag"] = 1.0857 * gb[f"{b}_sdss_flux_error"] / gb[f"{b}_sdss_flux"]
    gb = gb[(gb["e_mag"] < E_MAX) & (gb["ruwe"] < 1.4)]
    parts = [pd.DataFrame(dict(id="gaia_" + gb["source_id"].astype(str), ra=gb["ra"], dec=gb["dec"],
                               mag=gb[f"{b}_sdss_mag"], e_mag=gb["e_mag"], ref="gaia",
                               gspc_flag=gb[f"{b}_sdss_flag"].astype(int), bp_rp=gb["bp_rp"]))]
    if "skymapper" in checks:
        s = pd.read_csv(os.path.join(cat_dir, f"skymapper_{field}.csv"))
        s = s[(s["flags"] == 0) & (s["class_star"] > 0.9) & s[f"{b}_psf"].notna()
              & (s[f"e_{b}_psf"] < E_MAX)]
        parts.append(pd.DataFrame(dict(id="sm_" + s["object_id"].astype(str), ra=s["raj2000"],
                                       dec=s["dej2000"], mag=s[f"{b}_psf"], e_mag=s[f"e_{b}_psf"],
                                       ref="skymapper", gspc_flag=-1, bp_rp=np.nan)))
    if "ps1" in checks:
        p = pd.read_csv(os.path.join(cat_dir, f"ps1_{field}.csv")).replace(-999.0, np.nan)
        qf = p["qualityFlag"].astype(int)
        # Point sources by PSF - Kron (extended sources lose PSF flux, so the cut is one-sided),
        # and fainter than PS1's own saturation; the faint end is left to E_MAX, as for Gaia.
        point = (p["iMeanPSFMag"] - p["iMeanKronMag"]) < 0.05
        good = ((qf & 4) > 0) & ((qf & 1) == 0) & ((qf & 128) == 0) & point
        P = f"{b}MeanPSFMag"
        p = p[good & (p[P] > 13.5) & (p[P] < 18.0) & (p[P + "Err"] < E_MAX)]
        parts.append(pd.DataFrame(dict(id="ps1_" + p["objID"].astype(str), ra=p["raMean"],
                                       dec=p["decMean"], mag=p[P], e_mag=p[P + "Err"], ref="ps1",
                                       gspc_flag=-1, bp_rp=np.nan)))
    return pd.concat(parts, ignore_index=True), allsrc


def isolated(ra, dec, mag_g, allsrc):
    """No Gaia source within ISOLATION_ARCSEC that is within 3 mag (in G) of this star."""
    cosd = np.cos(np.radians(np.median(dec)))
    out = np.ones(len(ra), bool)
    for k, (a, d, m) in enumerate(zip(ra, dec, mag_g)):
        sep = 3600 * np.hypot((allsrc["ra"].values - a) * cosd, allsrc["dec"].values - d)
        out[k] = not ((sep > 1.0) & (sep < ISOLATION_ARCSEC) & (allsrc["phot_g_mean_mag"].values < m + 3)).any()
    return out


def fwhm_px(data, xs, ys, bkg, noise):
    vals = []
    for x, y in zip(xs, ys):
        xi, yi = int(round(x)), int(round(y))
        cut = data[yi - 12:yi + 13, xi - 12:xi + 13] - bkg
        if cut.shape != (25, 25):
            continue
        peak = cut[10:15, 10:15].max()
        if peak < 25 * noise or peak + bkg > PEAK_CUT_E:
            continue
        vals.append(2.0 * np.sqrt((cut >= 0.5 * peak).sum() / np.pi))
    return (float(np.median(vals)), len(vals)) if vals else (None, 0)


def phot(data, x, y, r_ap, r_in, r_out):
    pos = np.transpose((x, y))
    ap = CircularAperture(pos, r=r_ap)
    an = CircularAnnulus(pos, r_in=r_in, r_out=r_out)
    flux = aperture_photometry(data, ap)["aperture_sum"].value
    sky = np.array([np.median(sigma_clip(m.get_values(data), sigma=3, maxiters=3).compressed())
                    for m in an.to_mask(method="center")])
    peak = np.array([np.nanmax(m.get_values(data)) for m in ap.to_mask(method="center")])
    return flux - sky * ap.area, peak


def reduce_frame(path, refs, allsrc):
    with fits.open(path) as hd:
        h = hd[0].header
        data = hd[0].data.astype(float)
    exp = float(h["EXPTIME"])
    w = WCS(h)
    pixscale = 3600 * np.sqrt(abs(np.linalg.det(w.pixel_scale_matrix)))
    _, med, std = sigma_clipped_stats(data[EDGE:-EDGE, EDGE:-EDGE], sigma=3.0, maxiters=5)

    x, y = w.all_world2pix(refs["ra"].values, refs["dec"].values, 0)
    inb = (x > EDGE) & (x < data.shape[1] - EDGE) & (y > EDGE) & (y < data.shape[0] - EDGE)
    r, x, y = refs[inb].copy(), x[inb], y[inb]
    # Isolation uses the star's G from the nearest Gaia source (SkyMapper rows included).
    cosd = np.cos(np.radians(r["dec"].median()))
    gmag = []
    for a, d in zip(r["ra"], r["dec"]):
        sep = 3600 * np.hypot((allsrc["ra"].values - a) * cosd, allsrc["dec"].values - d)
        gmag.append(allsrc["phot_g_mean_mag"].values[np.argmin(sep)] if sep.min() < 1.5 else 21.0)
    iso = isolated(r["ra"].values, r["dec"].values, np.array(gmag), allsrc)
    r, x, y = r[iso], x[iso], y[iso]

    # The astrometry.net solution is good to ~0.2"; still, re-centre on each star
    # and drop any whose centroid wanders more than 2 px (faint, or blended).
    xc, yc = centroid_sources(data - med, x, y, box_size=11, centroid_func=centroid_com)
    ok = np.isfinite(xc) & np.isfinite(yc) & (np.hypot(xc - x, yc - y) < 2.0)
    r, x, y = r[ok], xc[ok], yc[ok]

    fw, n_fw = fwhm_px(data, x, y, med, std)
    if fw is None:
        fw = float(h.get("FWHM") or 3.0)
    net, peak = phot(data, x, y, 2.5 * fw, 4.0 * fw, 6.0 * fw)
    good = (net > 0) & (peak < PEAK_CUT_E)
    # CASTOR's ZP is for the total flux, and 2.5 FWHM misses the PSF wings (~10% in u',
    # ~5% in z'). Correct to APCOR_R FWHM on the brighter half of the stars, sky taken
    # further out; the 5 -> APCOR_R step is reported so convergence can be checked.
    bright = good & (net > np.median(net[good]))
    big, _ = phot(data, x[bright], y[bright], APCOR_R * fw, (APCOR_R + 2) * fw, (APCOR_R + 4) * fw)
    mid, _ = phot(data, x[bright], y[bright], 5.0 * fw, (APCOR_R + 2) * fw, (APCOR_R + 4) * fw)
    small, _ = phot(data, x[bright], y[bright], 2.5 * fw, (APCOR_R + 2) * fw, (APCOR_R + 4) * fw)
    apcor = float(np.median(small / big))
    conv = float(np.median(mid / big))
    net = net / apcor
    r = r.assign(x=x, y=y, net_e=net, peak_e=peak, used=good,
                 zp_star=r["mag"].values + 2.5 * np.log10(np.where(net > 0, net, np.nan) / exp))

    frame = dict(file=os.path.basename(path), field=h["OBJECT"] if "OBJECT" in h else "",
                 date_obs=h["DATE-OBS"], mjd_mid=float(h["MJD-OBS"]) + exp / 2 / 86400,
                 exptime=exp, airmass=float(h["AIRMASS"]), alt=float(h["OBJCTALT"]),
                 fwhm_px=round(fw, 2), fwhm_arcsec=round(fw * pixscale, 2), n_fwhm_stars=n_fw,
                 apcor=round(apcor, 4), apcor_5_over_total=round(conv, 4), n_apcor=int(bright.sum()),
                 pixscale=round(pixscale, 4), sky_e=round(med, 2), sky_std_e=round(std, 2),
                 usedbias=h.get("USEDBIAS"), useddark=h.get("USEDDARK"), usedflat=h.get("USEDFLAT"))
    for ref in ("gaia", "skymapper", "ps1"):
        for tag, sel in ((ref, r["ref"] == ref),
                         (ref + "_flag1", (r["ref"] == ref) & (r["gspc_flag"] == 1)),
                         (ref + "_flag0", (r["ref"] == ref) & (r["gspc_flag"] == 0))):
            if not tag.startswith("gaia") and tag != ref:
                continue
            z = r.loc[sel & r["used"], "zp_star"].dropna().values
            if len(z) == 0:
                frame[f"zp_{tag}"], frame[f"zp_err_{tag}"], frame[f"n_{tag}"] = np.nan, np.nan, 0
                continue
            c = sigma_clip(z, sigma=2.5, maxiters=5).compressed()
            frame[f"zp_{tag}"] = round(float(np.median(c)), 3)
            frame[f"zp_err_{tag}"] = round(float(np.std(c) / np.sqrt(len(c))) if len(c) > 1 else np.nan, 3)
            frame[f"n_{tag}"] = len(c)
    r["file"] = frame["file"]
    return frame, r


def preset_request(preset_filter):
    """A whole request for LOT + Sophia through this filter, from presets.json."""
    fragment = presets.load(presets.DEFAULT_PATH).resolve(
        "lulin", telescope="LOT", camera="Sophia", optic_filter=preset_filter)
    req = {"instrument": {"throughput_correction": 1.0},
           "target": {"morphology": {"type": "point"}, "sed": {"type": "flat"},
                      "brightness": {"type": "ab_mag", "target_mag": REF_MAG}}}
    for section, values in fragment.items():
        req[section] = {**req.get(section, {}), **values}
    req["environment"]["auto_calc_background"] = True
    return req


def castor_prediction(req, frame, ra, dec):
    q = copy.deepcopy(req)
    q["target"]["ra"], q["target"]["dec"] = ra, dec
    q["environment"]["observing_time_utc"] = Time(frame["mjd_mid"], format="mjd").isot[:19] + "Z"
    q["environment"]["total_fwhm"] = frame["fwhm_arcsec"]
    # Only the total source rate (rate / enclosed fraction) and the sky rate are
    # used, so the aperture choice does not enter the comparison.
    q["options"] = dict(type="solve_snr", single_exp_time=frame["exptime"], num_exposures=1,
                        aperture_factor=0.85,
                        sky_annulus=dict(inner_factor=3.0, outer_factor=5.0, estimator="median"),
                        background_dominance_factor=1.0)
    o = calculator.run_calculation(schema.ObservationRequest.model_validate(q))
    d = o.diagnostics
    total_rate = o.budget.source_count_rate / d.enclosed_flux_fraction
    return dict(zp_pred=REF_MAG + 2.5 * np.log10(total_rate), airmass_pred=d.airmass,
                sky_rate_pred=o.budget.sky_count_rate, mu_sky_pred=d.sky_surface_brightness,
                moon_alt=o.ephemeris.moon_elevation_deg, moon_sep=o.ephemeris.moon_separation_deg,
                moon_phase=o.ephemeris.moon_phase_angle_deg)


def main(filt, frames_dir, cat_dir, out_dir):
    cfg = BANDS[filt]
    req = preset_request(cfg["preset"])
    k = req["environment"]["extinction_coeff"]
    tput = req["instrument"]["telescope"]["optical_throughput"]
    refs_tags = ("gaia", "gaia_flag1", "gaia_flag0") + cfg["checks"]
    frames, stars = [], []
    for p in sorted(glob.glob(os.path.join(frames_dir, f"*_{filt}_*.fits"))):
        field = os.path.basename(p).split("_")[1]
        refs, allsrc = load_refs(cat_dir, field, cfg["band"], cfg["checks"])
        f, s = reduce_frame(p, refs, allsrc)
        f["field"] = field
        w = WCS(fits.getheader(p))
        ra, dec = (float(v) for v in w.all_pix2world(1024, 1024, 0))
        f.update(castor_prediction(req, f, ra, dec))
        frames.append(f)
        stars.append(s)
    fr = pd.DataFrame(frames)
    st = pd.concat(stars, ignore_index=True)

    # Above the atmosphere, both sides with the preset's k.
    fr["k_preset"], fr["tput_preset"] = k, tput
    for tag in refs_tags:
        fr[f"zp0_{tag}"] = fr[f"zp_{tag}"] + k * fr["airmass"]
        fr[f"tput_ratio_{tag}"] = 10 ** (0.4 * (fr[f"zp0_{tag}"] - (fr["zp_pred"] + k * fr["airmass_pred"])))
        fr[f"tput_implied_{tag}"] = tput * fr[f"tput_ratio_{tag}"]
    # Sky: the measured counts per arcsec^2 on the top-of-atmosphere scale, as in analyze_slt_afqt.q2_sky.
    fr["sky_rate"] = fr["sky_e"] / fr["exptime"]
    fr["mu_sky_gaia"] = fr["zp0_gaia"] - 2.5 * np.log10(fr["sky_rate"] / fr["pixscale"] ** 2)
    fr["sky_ratio_obs_over_castor"] = fr["sky_rate"] / fr["sky_rate_pred"]

    os.makedirs(out_dir, exist_ok=True)
    fr.to_csv(os.path.join(out_dir, "frames.csv"), index=False)
    st.to_csv(os.path.join(out_dir, "stars.csv"), index=False)
    cols = ["field", "date_obs", "exptime", "airmass", "fwhm_arcsec", "apcor", "apcor_5_over_total",
            "sky_e", "sky_std_e"]
    for tag in refs_tags:
        cols += [f"zp_{tag}", f"n_{tag}", f"tput_ratio_{tag}"]
    cols += ["zp_pred", "tput_implied_gaia", "mu_sky_gaia", "mu_sky_pred",
             "sky_ratio_obs_over_castor", "moon_alt"]
    with pd.option_context("display.width", 250, "display.max_columns", 60, "display.max_rows", 200):
        print(f"{cfg['preset']}: preset k {k}, optical_throughput {tput}")
        print(fr[cols].round(3).to_string())


if __name__ == "__main__":
    main(*sys.argv[1:5])
