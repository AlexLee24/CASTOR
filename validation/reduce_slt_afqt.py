"""Reduce SLT + Andor DZ936 frames of AT2026afqt (2026-11-10) to photometry tables.

This is the first night on the DZ936 since it went back on SLT in Nov 2026 as a
stand-in for the DU934P (shutter in repair). Nothing in presets.json's
`SLT_DZ936` entry has been checked against this camera on this telescope: its
QE, read noise and dark current come from Andor's brochure, the per-band
`optical_throughput` was fitted on the DU934P (`slt.py`), and the focal length
is the preset's 3.414 m, not the 3522.8 mm the headers carry. This script turns
the frames into tables; `analyze_slt_afqt.py` compares them with CASTOR.

Frames: 139 calibrated frames (bias, dark, flat, gain 0.95 e-/ADU applied, so
pixel values are electrons even though BUNIT still says 'adu'),
2026-11-10T12:41 to 20:55 UTC, 150 s in g'r'i'z', 150 s and 300 s in u'.

Two things about these frames that are not obvious:

* The WCS keywords have their first letter replaced by an underscore
  (`_RVAL1`, `_C1_1`, `_TYPE1` ...), so astropy sees no WCS. `_wcs()` rebuilds
  it from those keys. The plate solution gives 0.790"/px.
* Reference catalogue: Pan-STARRS DR2 PSF mags for g'r'i'z' (dec -2.0 is
  inside its footprint) and SkyMapper DR4 for u' (PS1 has no u). NO colour
  terms are applied; SkyMapper u is not SDSS u', and that is the largest
  systematic on the u' result.

Per frame and per reference star, aperture photometry at two radii:
`big` = 2.5 x FWHM (close to total flux, used for zero points) and `snr` =
1.5 x FWHM (used for the noise test, where a large aperture would bury the
point in sky). Sky is the median of a 4-6 x FWHM annulus, and its pixel
standard deviation is kept too, since that is the measured per-pixel noise.

Run: uv run --with numpy --with pandas --with astropy --with photutils \
     python -I validation/reduce_slt_afqt.py <frames_dir> <catalog_dir> <out_dir>
"""
import glob
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from astropy.io import fits
from astropy.stats import sigma_clip, sigma_clipped_stats
from astropy.wcs import WCS
from photutils.aperture import (CircularAnnulus, CircularAperture,
                                aperture_photometry)
from photutils.centroids import centroid_com, centroid_sources

BAND_OF = {"up": "u", "gp": "g", "rp": "r", "ip": "i", "zp": "z"}
SN = dict(ra=47.908688, dec=-2.026693)
EDGE = 40                 # px kept clear of the frame edge
PEAK_CUT_E = 50_000       # 16-bit ADC x 0.95 e-/ADU = 62258 e-; stay well below
ZP_WINDOW = {"u": (13.5, 17.5), "g": (14.0, 18.0), "r": (14.0, 18.0),
             "i": (14.0, 18.0), "z": (13.5, 17.5)}
NOISE_WINDOW = (12.0, 20.5)
ISOLATION_ARCSEC = 15.0


def load_catalog(cat_dir):
    """One table, magnitude columns u (SkyMapper) and g r i z (PS1)."""
    ps1 = pd.read_csv(os.path.join(cat_dir, "ps1_dr2.csv"))
    ps1 = ps1.replace(-999.0, np.nan)
    # Point sources only: PSF - Kron < 0.05 in r is the usual PS1 star cut.
    ps1 = ps1[(ps1["rMeanPSFMag"] - ps1["rMeanKronMag"]).abs() < 0.05]
    ps1 = pd.DataFrame({
        "id": "ps1_" + ps1["objID"].astype(str),
        "ra": ps1["raMean"], "dec": ps1["decMean"],
        **{b: ps1[f"{b}MeanPSFMag"] for b in "griz"},
        **{f"e_{b}": ps1[f"{b}MeanPSFMagErr"] for b in "griz"},
    })
    sm = pd.read_csv(os.path.join(cat_dir, "skymapper_dr4.csv"))
    sm = sm[(sm["class_star"] > 0.9) & (sm["flags"] == 0)]
    sm = pd.DataFrame({
        "id": "sm_" + sm["object_id"].astype(str),
        "ra": sm["raj2000"], "dec": sm["dej2000"],
        "u": sm["u_psf"], "e_u": sm["e_u_psf"],
        "sm_g": sm["g_psf"], "sm_r": sm["r_psf"],
    })
    # Isolation is judged against everything PS1 sees, stars or not.
    allsrc = pd.read_csv(os.path.join(cat_dir, "ps1_dr2.csv")).replace(-999.0, np.nan)
    return ps1, sm, allsrc


def _isolated(ra, dec, mag, allsrc):
    """True where no PS1 source within ISOLATION_ARCSEC is brighter than mag+3."""
    ra_all = allsrc["raMean"].values
    dec_all = allsrc["decMean"].values
    m_all = allsrc[["gMeanPSFMag", "rMeanPSFMag", "iMeanPSFMag"]].min(axis=1).values
    out = np.ones(len(ra), bool)
    cosd = np.cos(np.radians(np.median(dec)))
    for k, (a, d, m) in enumerate(zip(ra, dec, mag)):
        sep = 3600 * np.hypot((ra_all - a) * cosd, dec_all - d)
        near = (sep > 1.0) & (sep < ISOLATION_ARCSEC) & (m_all < m + 3)
        out[k] = not near.any()
    return out


def _wcs(h):
    w = WCS(naxis=2)
    w.wcs.crpix = [h["_RPIX1"], h["_RPIX2"]]
    w.wcs.crval = [h["_RVAL1"], h["_RVAL2"]]
    w.wcs.cd = [[h["_C1_1"], h["_C1_2"]], [h["_C2_1"], h["_C2_2"]]]
    w.wcs.ctype = [h["_TYPE1"], h["_TYPE2"]]
    return w


def _fwhm(data, xs, ys, bkg, noise):
    """Half-maximum-area FWHM in px, median over well-exposed stars.

    A second moment over a fixed box is pulled up by sky noise in the wings
    (it gave ~2x the header's FWHM on these frames); counting the pixels above
    half the peak is not, as long as the peak is well above the noise.
    """
    vals = []
    for x, y in zip(xs, ys):
        xi, yi = int(round(x)), int(round(y))
        cut = data[yi - 10:yi + 11, xi - 10:xi + 11] - bkg
        if cut.shape != (21, 21):
            continue
        peak = cut[8:13, 8:13].max()
        if peak < 30 * noise or peak + bkg > PEAK_CUT_E:
            continue
        n_half = (cut >= 0.5 * peak).sum()
        vals.append(2.0 * np.sqrt(n_half / np.pi))
    return float(np.median(vals)) if len(vals) >= 3 else None


def _phot(data, x, y, r_ap, r_in, r_out):
    pos = np.transpose((x, y))
    ap = CircularAperture(pos, r=r_ap)
    an = CircularAnnulus(pos, r_in=r_in, r_out=r_out)
    flux = aperture_photometry(data, ap)["aperture_sum"].value
    sky, sky_std, n_ann = [], [], []
    for m in an.to_mask(method="center"):
        v = m.get_values(data)
        v = sigma_clip(v, sigma=3, maxiters=3).compressed()
        sky.append(np.median(v))
        sky_std.append(np.std(v))
        n_ann.append(v.size)
    sky = np.array(sky)
    peak = np.array([np.nanmax(m.get_values(data)) if m.get_values(data).size else np.nan
                     for m in ap.to_mask(method="center")])
    return flux - sky * ap.area, sky, np.array(sky_std), np.array(n_ann), ap.area, peak


def reduce_frame(path, ps1, sm, allsrc):
    with fits.open(path) as hd:
        h = hd[0].header
        data = hd[0].data.astype(float)
    band = BAND_OF[re.search(r"_(up|gp|rp|ip|zp)_", os.path.basename(path)).group(1)]
    exp = float(h["EXPTIME"])
    w = _wcs(h)
    pixscale = 3600 * np.sqrt(abs(np.linalg.det(w.wcs.cd)))
    _, med, std = sigma_clipped_stats(data, sigma=3.0, maxiters=5)

    cat = sm if band == "u" else ps1
    c = cat[cat[band].notna() & cat[f"e_{band}"].notna()]
    c = c[(c[band] > NOISE_WINDOW[0]) & (c[band] < NOISE_WINDOW[1])]
    x, y = w.all_world2pix(c["ra"].values, c["dec"].values, 0)
    inb = (x > EDGE) & (x < data.shape[1] - EDGE) & (y > EDGE) & (y < data.shape[0] - EDGE)
    c, x, y = c[inb], x[inb], y[inb]
    iso = _isolated(c["ra"].values, c["dec"].values, c[band].values, allsrc)
    c, x, y = c[iso], x[iso], y[iso]

    # The header WCS is off by more than a shift on some frames after the
    # meridian flip (bright stars fell out of their apertures at random), so
    # fit an affine correction WCS-pixel -> centroid-pixel on the brighter
    # stars and apply it to all. Faint stars keep forced positions: their own
    # centroids are noise.
    bright = (c[band] < ZP_WINDOW[band][1]).values
    x0, y0 = x.copy(), y.copy()
    xb, yb = x[bright], y[bright]
    keep = np.ones(bright.sum(), bool)
    for box in (21, 9):
        xc, yc = centroid_sources(data - med, xb, yb, box_size=box, centroid_func=centroid_com)
        ok = np.isfinite(xc) & np.isfinite(yc) & keep
        A = np.vstack([np.ones(ok.sum()), x0[bright][ok], y0[bright][ok]]).T
        cx, *_ = np.linalg.lstsq(A, xc[ok], rcond=None)
        cy, *_ = np.linalg.lstsq(A, yc[ok], rcond=None)
        Ab = np.vstack([np.ones(bright.sum()), x0[bright], y0[bright]]).T
        resid = np.hypot(Ab @ cx - xc, Ab @ cy - yc)
        keep = np.isfinite(resid) & (resid < max(1.0, 3 * np.nanmedian(resid)))
        xb, yb = Ab @ cx, Ab @ cy
    Aall = np.vstack([np.ones(len(x0)), x0, y0]).T
    x, y = Aall @ cx, Aall @ cy
    dx, dy = float(np.median(x - x0)), float(np.median(y - y0))
    fit_resid = float(np.median(resid[keep]))
    max_corr = float(np.max(np.hypot(x - x0, y - y0)))

    fwhm = _fwhm(data, x, y, med, std)
    if fwhm is None:
        return None, None
    rows = {}
    for tag, k in (("big", 2.5), ("snr", 1.5)):
        net, sky, sky_std, n_ann, area, peak = _phot(data, x, y, k * fwhm, 4 * fwhm, 6 * fwhm)
        rows[tag] = (net, sky, sky_std, n_ann, area, peak)

    mag = c[band].values
    net_big, peak_big = rows["big"][0], rows["big"][5]
    zsel = ((mag > ZP_WINDOW[band][0]) & (mag < ZP_WINDOW[band][1])
            & (c[f"e_{band}"].values < 0.03) & (net_big > 0) & (peak_big < PEAK_CUT_E))
    zp_star = mag[zsel] + 2.5 * np.log10(net_big[zsel] / exp)
    clip = sigma_clip(zp_star, sigma=2.5, maxiters=5)
    zp = float(np.mean(clip.compressed()))
    zp_err = float(np.std(clip.compressed()) / np.sqrt(clip.count()))

    # The supernova itself, through the same two apertures.
    sx0, sy0 = w.all_world2pix([SN["ra"]], [SN["dec"]], 0)
    sx = cx[0] + cx[1] * sx0 + cx[2] * sy0
    sy = cy[0] + cy[1] * sx0 + cy[2] * sy0
    sn = {}
    for tag, k in (("big", 2.5), ("snr", 1.5)):
        net, sky, sky_std, n_ann, area, peak = _phot(data, sx, sy, k * fwhm, 4 * fwhm, 6 * fwhm)
        sn[tag] = dict(net=net[0], sky=sky[0], sky_std=sky_std[0], n_ann=n_ann[0], area=area)

    frame = dict(
        file=os.path.basename(path), band=band, date_obs=h["DATE-OBS"],
        mjd_mid=float(h["MJD-OBS"]) + exp / 2 / 86400, exptime=exp,
        airmass=float(h["AIRMASS"]), alt=float(h["OBJCTALT"]),
        fwhm_px=round(fwhm, 3), fwhm_hdr_px=float(h.get("FWHM", np.nan)),
        pixscale=round(pixscale, 4), wcs_dx=round(dx, 2), wcs_dy=round(dy, 2),
        wcs_max_corr=round(max_corr, 2), wcs_fit_resid=round(fit_resid, 3),
        sky_e=med, sky_std_e=std, zp=zp, zp_err=zp_err, n_zp=int(clip.count()),
        zmag_hdr=float(h.get("ZMAG", np.nan)),
        sn_net_big=sn["big"]["net"], sn_net_snr=sn["snr"]["net"],
        sn_sky=sn["snr"]["sky"], sn_sky_std=sn["snr"]["sky_std"],
        sn_area_snr=sn["snr"]["area"], sn_n_ann=sn["snr"]["n_ann"],
    )
    stars = pd.DataFrame(dict(
        file=frame["file"], band=band, mjd_mid=frame["mjd_mid"], id=c["id"].values,
        mag=mag, e_mag=c[f"e_{band}"].values, x=x, y=y,
        net_big=net_big, net_snr=rows["snr"][0], sky=rows["snr"][1],
        sky_std=rows["snr"][2], n_ann=rows["snr"][3], area_snr=rows["snr"][4],
        peak=peak_big, used_for_zp=zsel,
    ))
    return frame, stars


def main(frames_dir, cat_dir, out_dir):
    ps1, sm, allsrc = load_catalog(cat_dir)
    frames, stars = [], []
    paths = sorted(glob.glob(os.path.join(frames_dir, "*.fits")))
    for i, p in enumerate(paths):
        try:
            f, s = reduce_frame(p, ps1, sm, allsrc)
        except Exception as exc:  # report, keep going
            print(f"skip {os.path.basename(p)}: {exc}", flush=True)
            continue
        if f is None:
            print(f"skip {os.path.basename(p)}: no FWHM", flush=True)
            continue
        frames.append(f)
        stars.append(s)
        if i % 20 == 0:
            print(f"{i + 1}/{len(paths)} {f['band']} zp={f['zp']:.3f} fwhm={f['fwhm_px']:.2f} "
                  f"dxy=({f['wcs_dx']},{f['wcs_dy']}) n={f['n_zp']}", flush=True)
    pd.DataFrame(frames).to_csv(os.path.join(out_dir, "frames.csv"), index=False)
    pd.concat(stars).to_csv(os.path.join(out_dir, "stars.csv"), index=False)
    print(f"wrote {len(frames)} frames", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
