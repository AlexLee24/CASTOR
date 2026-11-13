"""Does joining four nights recover the absolute extinction one night could not?

Reads the committed per-frame zero points (`slt_sn2024ggi_zp_per_frame.csv`,
produced by `reduce_slt_extinction.py`) and fits three models per band. The
answer is no, for a reason the fit itself reports: the target sets every night,
so within each night airmass and time are collinear, and the extinction slope
is degenerate with any per-night transparency term. Adding nights does not help
because every night has the same collinearity.

The zero point per frame is ZP = m_ref - m_inst, so brighter atmosphere gives a
smaller ZP and ZP rises with airmass: ZP = Z + k*X, slope k is the extinction.

Model A  shared k, a free zero point per night (assumes each night photometric).
Model B  Model A plus a linear-in-time transparency term per night.
Model C  the single most internally consistent night (2024-04-16) on its own.

The diagnostic that matters is not k but its correlation with the per-night
nuisance terms: in Model B it reaches 0.98, i.e. k is not identified. Several
bands return negative k (stars brightening as they set), which is unphysical and
is transparency improving faster than the air dims. Only the *ordering*
(extinction falls towards the red) survives, matching slt.py's single-night
finding, so none of these k reached presets.json; its per-band values came
from 2026-11-10's rising-and-setting field instead (slt_dz936.py).

Run: `uv run --with numpy --with pandas python validation/analyze_slt_extinction.py`
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ZP_TABLE = os.path.join(HERE, "data", "slt_sn2024ggi_zp_per_frame.csv")

BAND_OF = {"up": "u", "gp": "g", "rp": "r", "ip": "i", "zp": "z"}
BANDS = ["u", "g", "r", "i", "z"]
#: Literature extinction for a good site, mag/airmass, for comparison only.
LITERATURE_K = {"u": 0.55, "g": 0.20, "r": 0.11, "i": 0.07, "z": 0.06}


def _load():
    df = pd.read_csv(ZP_TABLE)
    df["b"] = df["band"].map(BAND_OF)
    return df[df["zp_err"] > 0].dropna(subset=["zp", "airmass", "mjd"])


def _wls(design, y, w):
    root = np.sqrt(w)
    coef, *_ = np.linalg.lstsq(design * root[:, None], y * root, rcond=None)
    resid = y - design @ coef
    dof = max(len(y) - design.shape[1], 1)
    s2 = np.sum(w * resid ** 2) / dof
    cov = s2 * np.linalg.pinv((design * root[:, None]).T @ (design * root[:, None]))
    return coef, cov, resid, s2


def fit_band(df, band, drift):
    """Joint fit for one band. `drift` adds a per-night linear time term.

    Returns k, its formal error, the max |correlation| of k with a nuisance
    term (the identifiability tell), the residual RMS and reduced chi-square.
    """
    d = df[df["b"] == band]
    if len(d) < 8:
        return None
    nights = sorted(d["night"].unique())
    X = d["airmass"].values
    y = d["zp"].values
    w = 1.0 / d["zp_err"].values ** 2
    t = d["mjd"].values.copy()
    for n in nights:                       # centre time within each night
        m = d["night"].values == n
        t[m] -= t[m].mean()

    cols = [X] + [(d["night"].values == n).astype(float) for n in nights]
    if drift:
        cols += [np.where(d["night"].values == n, t, 0.0) for n in nights]
    design = np.array(cols).T
    coef, cov, resid, s2 = _wls(design, y, w)
    sd = np.sqrt(np.diag(cov))
    corr = cov / np.sqrt(np.outer(np.diag(cov), np.diag(cov)))
    return dict(k=coef[0], k_err=sd[0], corr_k=float(np.max(np.abs(corr[0, 1:]))),
                rms=float(np.sqrt(np.mean(resid ** 2))), chi2r=float(s2), n=len(d))


def fit_single_night(df, band, night):
    d = df[(df["b"] == band) & (df["night"] == night)]
    if len(d) < 6:
        return None
    X = d["airmass"].values
    y = d["zp"].values
    w = 1.0 / d["zp_err"].values ** 2
    coef, cov, resid, _ = _wls(np.vstack([X, np.ones_like(X)]).T, y, w)
    return dict(k=coef[0], k_err=float(np.sqrt(np.diag(cov))[0]),
                rms=float(np.sqrt(np.mean(resid ** 2))), n=len(d))


def main():
    df = _load()
    print("Per-band extinction k (mag/airmass); 'corr' is |corr(k, nuisance)|max.\n")
    print("Model A  shared k + per-night zero point")
    for b in BANDS:
        r = fit_band(df, b, drift=False)
        if r:
            print(f"  {b}: k={r['k']:+.3f}±{r['k_err']:.3f}  lit {LITERATURE_K[b]:.2f}"
                  f"  rms={r['rms']:.3f}  chi2r={r['chi2r']:.1f}  corr={r['corr_k']:.2f}")
    print("\nModel B  + per-night linear transparency drift")
    for b in BANDS:
        r = fit_band(df, b, drift=True)
        if r:
            print(f"  {b}: k={r['k']:+.3f}±{r['k_err']:.3f}  lit {LITERATURE_K[b]:.2f}"
                  f"  rms={r['rms']:.3f}  chi2r={r['chi2r']:.1f}  corr={r['corr_k']:.2f}")
    print("\nModel C  2024-04-16 alone")
    for b in BANDS:
        r = fit_single_night(df, b, "2024-04-16")
        if r:
            print(f"  {b}: k={r['k']:+.3f}±{r['k_err']:.3f}  lit {LITERATURE_K[b]:.2f}"
                  f"  rms={r['rms']:.3f}")


if __name__ == "__main__":
    main()
