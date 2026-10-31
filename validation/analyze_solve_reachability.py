"""Map the reachable/unreachable structure solve-for-time now respects.

The solve-for-time section reports one operating point.  The audit CSV sweeps
LOT/SLT x g'/r'/i' x AB 17-23 x target SNR 5-50, so the whole reachable/
unreachable structure can be drawn as a heat map instead of three numbers.

Colour is the fraction of the requested SNR the returned exposure count actually
reaches (1.0 = honest, a small overshoot = integer-frame rounding).  Cells where
the model's asymptotic ceiling is itself below the target -- physically
unreachable at any exposure -- are hatched, and since the question-17 fix these
are the only cells that fall short: the solver returns the unreachable flag there
rather than an undershooting count.

Run from the repository root::

    uv run --with pandas --with matplotlib python validation/analyze_solve_reachability.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "validation/data/solve_time_flatness_audit.csv"
FIGURE = ROOT / "validation/figures/solve_time_reachability.png"

TELESCOPES = ["LOT", "SLT"]
BANDS = ["g", "r", "i"]


def main() -> None:
    df = pd.read_csv(TABLE)
    mags = np.sort(df["ab_magnitude"].unique())
    snrs = np.sort(df["target_snr"].unique())
    norm = TwoSlopeNorm(vmin=0.0, vcenter=1.0, vmax=1.3)
    cmap = plt.get_cmap("RdBu")

    fig, axes = plt.subplots(2, 3, figsize=(13.5, 6.6), sharex=True, sharey=True)
    mesh = None
    for r, telescope in enumerate(TELESCOPES):
        for c, band in enumerate(BANDS):
            ax = axes[r, c]
            sub = df[(df.telescope == telescope) & (df.band == band)]
            frac = sub.pivot(index="target_snr", columns="ab_magnitude",
                             values="current_achieved_fraction").reindex(
                index=snrs, columns=mags)
            ceil = sub.pivot(index="target_snr", columns="ab_magnitude",
                             values="asymptotic_snr_ceiling").reindex(
                index=snrs, columns=mags)
            mesh = ax.pcolormesh(frac.values, cmap=cmap, norm=norm,
                                 edgecolors="white", linewidth=0.5)
            # Hatch physically unreachable cells (ceiling below the request).
            unreach = ceil.values < snrs[:, None]
            for iy, ix in zip(*np.where(unreach)):
                ax.add_patch(plt.Rectangle((ix, iy), 1, 1, fill=False,
                                           hatch="xxx", edgecolor="0.25", lw=0))
            flat = sub["background_flatness_fraction"].iloc[0]
            ax.set_title(f"{telescope} {band}'  (flatness {flat:.0%})", fontsize=10)
            ax.set_xticks(np.arange(len(mags)) + 0.5)
            ax.set_xticklabels([f"{m:g}" for m in mags], fontsize=7.5)
            ax.set_yticks(np.arange(len(snrs)) + 0.5)
            ax.set_yticklabels([f"{s:g}" for s in snrs], fontsize=8)
            if r == 1:
                ax.set_xlabel("source AB magnitude")
            if c == 0:
                ax.set_ylabel("requested SNR")

    cbar = fig.colorbar(mesh, ax=axes, fraction=0.025, pad=0.02,
                        extend="max")
    cbar.set_label("achieved / requested SNR  (1.0 = honest)")
    fig.suptitle(
        "Solve-for-time reachability: the fixed solver reaches the request "
        "wherever the ceiling allows\n"
        "hatched = requested SNR above the model's asymptotic ceiling "
        "(unreachable at any exposure, now flagged)", fontsize=11)
    fig.savefig(FIGURE, dpi=140, bbox_inches="tight")
    print(f"wrote {FIGURE.relative_to(ROOT)}")

    worst = df.loc[df["current_achieved_fraction"].idxmin()]
    print(f"worst undershoot: {worst.telescope} {worst.band}' AB={worst.ab_magnitude}"
          f" SNR req {worst.target_snr:g} -> got {worst.current_achieved_fraction:.2f}x")


if __name__ == "__main__":
    main()
