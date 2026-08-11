"""
Renders a castor.schema.BatchObservationResponse into a PNG (bytes), styled to match
the rest of the app's Design tokens. This is the only place in castorGUI that imports
matplotlib — kept separate from rightPanel.py so the "response -> pixels" transform is
testable on its own, independent of any Flet control.

Uses matplotlib's object-oriented API (Figure + FigureCanvasAgg) rather than pyplot:
pyplot keeps a global figure registry that's meant for interactive/scripty use and isn't
thread-safe, which is the wrong shape for a function called repeatedly from a live GUI.
"""
import io
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from castor import schema  # noqa: E402
from constant import Design  # noqa: E402

__all__ = ["render_batch_chart", "CHART_ASPECT_RATIO"]

# Figure size is fixed rather than driven by the container: the PNG is displayed via
# ft.RawImage with fit=ft.BoxFit.CONTAIN (see rightPanel.py), so it scales to whatever
# space is available without being re-rendered on every window resize. rightPanel.py
# imports CHART_ASPECT_RATIO to size that container correctly.
_FIG_WIDTH_IN = 9.2
_FIG_HEIGHT_IN = 9.2
_DPI = 160

CHART_ASPECT_RATIO = _FIG_WIDTH_IN / _FIG_HEIGHT_IN

_GRID_COLOR = (1, 1, 1, 0.08)
_SPINE_COLOR = (1, 1, 1, 0.10)


def render_batch_chart(response: schema.BatchObservationResponse, single_exp_time: float) -> bytes:
    """
    Three stacked panels sharing one time axis, in reading order:
      1. Target & Moon elevation (°) — is this window even pointed above the horizon?
      2. Single-exposure SNR — how good is one frame right now?
      3. Saturation time limit (s) vs. your chosen single_exp_time — will one frame saturate?

    Deliberately not total_snr: it's dominated by whatever exposure count/strategy the
    user picked, not by the sky conditions the rest of this chart is about. Deliberately
    not a dual-axis chart: panels 2 and 3 have incompatible units (SNR vs. seconds), and
    dataviz's #1 rule is that two different scales never share one y-axis.
    """
    core = response.core
    ephem = response.ephemeris

    times = [datetime.fromisoformat(t) for t in core.timestamps_iso]
    single_snr = np.array(core.single_snr)
    t_sat = np.array(core.saturation_time_limit)
    target_el = np.array(ephem.target_elevation_deg)
    moon_el = np.array(ephem.moon_elevation_deg)

    fig = Figure(figsize=(_FIG_WIDTH_IN, _FIG_HEIGHT_IN), dpi=_DPI)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(Design.SURFACE_1)

    (ax_elev, ax_snr, ax_sat) = fig.subplots(
        3, 1, sharex=True, gridspec_kw={"height_ratios": [1, 1, 1], "hspace": 0.45}
    )

    _plot_elevation(ax_elev, times, target_el, moon_el)
    _plot_single_snr(ax_snr, times, single_snr)
    _plot_saturation(ax_sat, times, t_sat, single_exp_time)

    ax_sat.set_xlabel("Time (UTC)", color=Design.TEXT_MUTED, fontsize=10)
    ax_sat.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    # No title and no top-level warning banner painted in here on purpose: rightPanel.py
    # already has an "Observing Window" section title and a shared warning box (fed from
    # response.flags by RightPanel.render_batch) — this image is just the plots.
    fig.subplots_adjust(top=0.98, bottom=0.06, left=0.10, right=0.97)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    return buf.getvalue()


# ==========================================
# Helpers: contiguous-run detection, shared axis chrome
# ==========================================

def _contiguous_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Returns [(start_idx, end_idx), ...] for each contiguous stretch where mask is True
    (end_idx inclusive). Used for shading "at risk" / "below horizon" time windows —
    there can be more than one such window in a single night."""
    runs = []
    run_start = None
    for i, flag in enumerate(mask):
        if flag and run_start is None:
            run_start = i
        elif not flag and run_start is not None:
            runs.append((run_start, i - 1))
            run_start = None
    if run_start is not None:
        runs.append((run_start, len(mask) - 1))
    return runs


def _style_axis(ax) -> None:
    ax.set_facecolor(Design.SURFACE_1)
    ax.tick_params(colors=Design.TEXT_MUTED, labelsize=9)
    ax.grid(True, color=_GRID_COLOR, linewidth=0.8)
    for spine in ax.spines.values():
        spine.set_color(_SPINE_COLOR)


def _mark_extreme(ax, times, values, index: int, label: str, dy_points: float) -> None:
    """Direct-labels a single point (the peak or the trough) — per dataviz's mark specs,
    never label every point, only the one the story is about."""
    ax.scatter([times[index]], [values[index]], s=36, color=Design.PRIMARY,
               edgecolors=Design.SURFACE_1, linewidths=2, zorder=4)
    ax.annotate(label, (times[index], values[index]), textcoords="offset points",
                xytext=(0, dy_points), ha="center", color=Design.TEXT_MAIN,
                fontsize=9, fontweight="bold")


# ==========================================
# Panel 1: Target & Moon elevation
# ==========================================

def _plot_elevation(ax, times, target_el: np.ndarray, moon_el: np.ndarray) -> None:
    _style_axis(ax)

    for a, b in _contiguous_runs(target_el < 0):
        ax.axvspan(times[a], times[b], color=Design.WARNING, alpha=0.06, zorder=1)

    ax.axhline(0, color=Design.TEXT_MUTED, linewidth=1, alpha=0.4, zorder=2)
    ax.plot(times, target_el, color=Design.PRIMARY, linewidth=2, solid_capstyle="round",
            zorder=3, label="Target")
    ax.plot(times, moon_el, color=Design.MOON, linewidth=2, solid_capstyle="round",
            zorder=3, label="Moon")
    ax.set_ylabel("Elevation (°)", color=Design.TEXT_MUTED, fontsize=10)
    ax.legend(loc="upper right", frameon=False, labelcolor=Design.TEXT_MAIN, fontsize=9, ncols=2)


# ==========================================
# Panel 2: Single-exposure SNR
# ==========================================

def _plot_single_snr(ax, times, single_snr: np.ndarray) -> None:
    _style_axis(ax)

    ax.plot(times, single_snr, color=Design.PRIMARY, linewidth=2, solid_capstyle="round", zorder=3)
    peak_i = int(np.argmax(single_snr))
    _mark_extreme(ax, times, single_snr, peak_i, f"{single_snr[peak_i]:.0f}", dy_points=10)

    ax.set_ylabel("Single-Exposure SNR", color=Design.TEXT_MUTED, fontsize=10)
    pad = (single_snr.max() - single_snr.min()) * 0.3 or single_snr.max() * 0.1 or 1.0
    ax.set_ylim(single_snr.min() - pad * 0.4, single_snr.max() + pad)


# ==========================================
# Panel 3: Saturation margin vs. the chosen single_exp_time
# ==========================================

def _plot_saturation(ax, times, t_sat: np.ndarray, single_exp_time: float) -> None:
    _style_axis(ax)

    at_risk = t_sat < single_exp_time
    risk_runs = _contiguous_runs(at_risk)
    for a, b in risk_runs:
        ax.axvspan(times[a], times[b], color=Design.WARNING, alpha=0.08, zorder=1)

    ax.plot(times, t_sat, color=Design.PRIMARY, linewidth=2, solid_capstyle="round", zorder=3)
    # Dashed on purpose: this is a real threshold reference, not a gridline — dataviz's
    # "no dashed gridlines" rule is about not dashing plain grids, not about this case.
    ax.axhline(single_exp_time, color=Design.TEXT_MUTED, linewidth=1.5, linestyle=(0, (5, 4)), zorder=2)
    # Anchored at the line's right end (not the left, near where a risk-window label can
    # also land when saturation risk starts right at the beginning of the window) —
    # matches "lines carry their value at the end" from the dataviz skill's label rules.
    ax.annotate(f"your exposure: {single_exp_time:.0f}s", (times[-1], single_exp_time),
                textcoords="offset points", xytext=(0, 8), color=Design.TEXT_MUTED,
                fontsize=8.5, va="bottom", ha="right")

    y_top = max(t_sat.max() * 1.25, single_exp_time * 1.25)
    if risk_runs:
        ax.text(times[risk_runs[0][0]], y_top * 0.93, "⚠ saturation risk window",
                color=Design.WARNING, fontsize=8.5, ha="left", va="top")

    trough_i = int(np.argmin(t_sat))
    _mark_extreme(ax, times, t_sat, trough_i, f"{t_sat[trough_i]:.0f}s", dy_points=-16)

    ax.set_ylabel("Saturation Limit (s)", color=Design.TEXT_MUTED, fontsize=10)
    ax.set_ylim(0, y_top)
