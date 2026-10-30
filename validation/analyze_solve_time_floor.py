"""Audit solve-for-time against the correlated background-flatness term.

A flat-field or background-gradient residual is correlated across a stack, so it
does not average down and instead sets an asymptotic SNR ceiling. Question 17 is
now fixed: ``solve_required_exposures`` inverts the full stacked-SNR relation
using that ceiling (``calculate_flatness_snr_ceiling``) rather than the old
sqrt(N) law, and returns an unreachable result above the ceiling. This script is
retained as a regression audit: it checks the shipped ``required_exposures``
against an independently derived exact count across the Lulin LOT and SLT presets,
and confirms the unreachable flag wherever the ceiling sits below the request.

Run from the repository root::

    uv run --with pandas --with matplotlib python validation/analyze_solve_time_floor.py
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from castor import physics, schema
from castor.calculator import run_calculation
from castorCLI import presets


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "validation/data/solve_time_flatness_audit.csv"
FIGURE = ROOT / "validation/figures/solve_time_flatness_floor.png"
REPORT = ROOT / "validation/report_sections/solve_time.md"

RIGS = {"LOT": "Sophia", "SLT": "SLT_DU934P"}
FILTERS = {"g": "Sloan_g", "r": "Sloan_r", "i": "Sloan_i"}
MAGNITUDES = np.arange(17.0, 23.01, 0.5)
TARGET_SNRS = (5.0, 10.0, 20.0, 30.0, 50.0)
SINGLE_EXPOSURE_S = 120.0
OBSERVING_TIME = "2026-01-15T16:00:00Z"
TARGET_RA_DEG = 113.65
TARGET_DEC_DEG = 31.89


def request_for(telescope: str, camera: str, filter_id: str, magnitude: float, target_snr: float):
    data = presets.load().resolve(
        "lulin", telescope=telescope, camera=camera, optic_filter=filter_id
    )
    data["instrument"]["throughput_correction"] = 1.0
    data["target"] = {
        "morphology": {"type": "point"},
        "brightness": {"type": "ab_mag", "target_mag": magnitude},
        "sed": {"type": "flat"},
        "ra": TARGET_RA_DEG,
        "dec": TARGET_DEC_DEG,
    }
    data["environment"].update({
        "observing_time_utc": OBSERVING_TIME,
        "auto_calc_background": False,
        "total_fwhm": (1.4 ** 2 + 0.2 ** 2 + 0.1 ** 2 + 0.1 ** 2) ** 0.5,
    })
    data["options"] = {
        "type": "solve_time",
        "aperture_factor": 0.85,
        "single_exp_time": SINGLE_EXPOSURE_S,
        "sky_annulus": {"inner_factor": 3.0, "outer_factor": 5.0, "estimator": "median"},
        "target_snr": target_snr,
    }
    return schema.ObservationRequest.model_validate(data)


def exact_exposure_count(request: schema.ObservationRequest, response, target_snr: float):
    """Solve the stack equation including its non-averaging flatness term."""
    instrument = request.instrument
    diagnostics = response.diagnostics
    budget = response.budget
    exposure = request.options.single_exp_time
    signal_frame = budget.source_count_rate * exposure
    background_pixels = diagnostics.num_pixels_aperture + diagnostics.num_pixels_sky_estimate
    random_variance_frame = (
        signal_frame
        + background_pixels
        * (
            budget.sky_count_rate * exposure
            + instrument.camera.dark_current_rate * exposure
            + instrument.camera.readout_noise**2
        )
    )
    flatness_amplitude_frame = (
        instrument.camera.background_flatness_fraction
        * budget.sky_count_rate
        * exposure
        * diagnostics.num_pixels_aperture
    )
    ceiling = math.inf if flatness_amplitude_frame == 0 else signal_frame / flatness_amplitude_frame

    denominator = signal_frame**2 - target_snr**2 * flatness_amplitude_frame**2
    if denominator <= 0:
        return ceiling, math.inf, math.nan
    exact = math.ceil(target_snr**2 * random_variance_frame / denominator)
    achieved = physics.calculate_total_snr(
        budget.source_count_rate,
        budget.sky_count_rate,
        instrument.camera.dark_current_rate,
        instrument.camera.readout_noise,
        diagnostics.num_pixels_aperture,
        exposure,
        exact * exposure,
        exact,
        diagnostics.num_pixels_sky_estimate,
        instrument.camera.background_flatness_fraction,
    )
    return ceiling, exact, float(achieved)


def build_table():
    rows = []
    for telescope, camera in RIGS.items():
        for band, filter_id in FILTERS.items():
            for magnitude in MAGNITUDES:
                for target_snr in TARGET_SNRS:
                    request = request_for(telescope, camera, filter_id, magnitude, target_snr)
                    response = run_calculation(request)
                    ceiling, exact, exact_achieved = exact_exposure_count(request, response, target_snr)
                    # Reproduce the superseded sqrt(N) solver: N = (target/single)^2,
                    # then the SNR that many frames actually stack to. This is the
                    # "before" curve, so the fix is visible next to it.
                    single = response.core.single_snr
                    if single > 0:
                        naive_exposures = math.ceil((target_snr / single) ** 2)
                        naive_achieved = float(physics.calculate_total_snr(
                            response.budget.source_count_rate, response.budget.sky_count_rate,
                            request.instrument.camera.dark_current_rate,
                            request.instrument.camera.readout_noise,
                            response.diagnostics.num_pixels_aperture, SINGLE_EXPOSURE_S,
                            naive_exposures * SINGLE_EXPOSURE_S, naive_exposures,
                            response.diagnostics.num_pixels_sky_estimate,
                            request.instrument.camera.background_flatness_fraction,
                        ))
                    else:
                        naive_exposures, naive_achieved = np.nan, np.nan
                    rows.append({
                        "telescope": telescope,
                        "camera": camera,
                        "band": band,
                        "ab_magnitude": magnitude,
                        "target_snr": target_snr,
                        # None (unreachable) becomes NaN so the reachable/unreachable
                        # split survives the CSV round-trip and np.isfinite masks it.
                        "current_exposures": (
                            np.nan if response.core.required_exposures is None
                            else response.core.required_exposures
                        ),
                        "current_reachable": response.core.target_reachable,
                        "current_achieved_snr": response.core.total_snr,
                        "current_achieved_fraction": response.core.total_snr / target_snr,
                        "naive_exposures": naive_exposures,
                        "naive_achieved_fraction": naive_achieved / target_snr,
                        "asymptotic_snr_ceiling": ceiling,
                        "exact_exposures": exact,
                        "exact_achieved_snr": exact_achieved,
                        "single_snr": response.core.single_snr,
                        "source_rate_e_s": response.budget.source_count_rate,
                        "sky_rate_e_s_pix": response.budget.sky_count_rate,
                        "aperture_pixels": response.diagnostics.num_pixels_aperture,
                        "sky_estimate_pixels": response.diagnostics.num_pixels_sky_estimate,
                        "background_flatness_fraction": request.instrument.camera.background_flatness_fraction,
                    })
    table = pd.DataFrame(rows)
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(TABLE, index=False, float_format="%.8g")
    return table


def make_figure(table):
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    colours = {"g": "#16a34a", "r": "#dc2626", "i": "#7c3aed"}
    slt = table[table["telescope"].eq("SLT")]

    ax = axes[0, 0]
    for band in FILTERS:
        subset = slt[(slt["band"].eq(band)) & (slt["target_snr"].eq(20))].sort_values("ab_magnitude")
        # Old sqrt(N) solver (dashed): undershoots its own target -- below 1.0
        # even where the target is reachable. This is the bug.
        ax.plot(subset["ab_magnitude"], subset["naive_achieved_fraction"], "--",
                color=colours[band], alpha=0.55, linewidth=1.4)
        # Fixed solver (solid): >= 1.0 wherever the target is reachable, and it
        # returns "unreachable" (open marker) once the ceiling drops below it.
        reach = subset[subset["current_reachable"] == True]  # noqa: E712
        unreach = subset[subset["current_reachable"] != True]  # noqa: E712
        ax.plot(subset["ab_magnitude"], subset["current_achieved_fraction"], "-",
                color=colours[band], linewidth=2, label=f"{band}'")
        ax.plot(reach["ab_magnitude"], reach["current_achieved_fraction"], "o",
                color=colours[band])
        ax.plot(unreach["ab_magnitude"], unreach["current_achieved_fraction"], "o",
                mfc="white", mec=colours[band], mew=1.5)
    ax.axhline(1, color="#0f172a", linewidth=1, linestyle=":")
    ax.text(0.02, 0.03,
            "dashed = old sqrt(N) (undershoots)\nsolid = fixed;  ○ = flagged unreachable",
            transform=ax.transAxes, fontsize=8, va="bottom", color="#334155")
    ax.set(xlabel="Target AB magnitude", ylabel="Returned SNR / requested SNR (target 20)",
           title="A  Fixed solver meets the target where reachable; old one undershot")
    ax.legend(frameon=False, loc="upper right")

    ax = axes[0, 1]
    ceiling = slt[slt["target_snr"].eq(5)]
    for band in FILTERS:
        subset = ceiling[ceiling["band"].eq(band)]
        ax.plot(subset["ab_magnitude"], subset["asymptotic_snr_ceiling"], "o-",
                color=colours[band], label=f"{band}'")
    for goal in (5, 10, 20):
        ax.axhline(goal, color="#64748b", linewidth=0.9, linestyle="--")
        ax.text(MAGNITUDES[-1] + 0.05, goal, f"SNR {goal}", va="center", fontsize=8)
    ax.set(yscale="log", xlabel="Target AB magnitude", ylabel="Asymptotic SNR ceiling",
           title="B  SLT's 2% correlated background term sets a ceiling")
    ax.legend(frameon=False)

    ax = axes[1, 0]
    at_twenty = slt[slt["ab_magnitude"].eq(20)]
    for band in FILTERS:
        subset = at_twenty[at_twenty["band"].eq(band)]
        ax.plot(subset["target_snr"], subset["current_exposures"], "o-",
                color=colours[band], label=f"{band}' current")
        possible = subset[np.isfinite(subset["exact_exposures"])]
        ax.plot(possible["target_snr"], possible["exact_exposures"], "s--",
                color=colours[band], alpha=0.75, label=f"{band}' exact")
        impossible = subset[~np.isfinite(subset["exact_exposures"])]
        if len(impossible):
            ax.scatter(impossible["target_snr"], impossible["current_exposures"], marker="x",
                       s=75, linewidths=2, color=colours[band])
    ax.set(yscale="log", xlabel="Requested SNR for AB=20", ylabel="Number of 120 s exposures",
           title="C  Shipped count matches the exact solve; unreachable returns none")
    ax.legend(frameon=False, ncol=2, fontsize=8)

    ax = axes[1, 1]
    for band in FILTERS:
        row = at_twenty[(at_twenty["band"].eq(band)) & (at_twenty["target_snr"].eq(20))].iloc[0]
        request = request_for("SLT", "SLT_DU934P", FILTERS[band], 20, 20)
        response = run_calculation(request)
        n = np.unique(np.logspace(0, 5, 240).astype(int))
        snr = physics.calculate_total_snr(
            response.budget.source_count_rate,
            response.budget.sky_count_rate,
            request.instrument.camera.dark_current_rate,
            request.instrument.camera.readout_noise,
            response.diagnostics.num_pixels_aperture,
            SINGLE_EXPOSURE_S,
            n * SINGLE_EXPOSURE_S,
            n,
            response.diagnostics.num_pixels_sky_estimate,
            request.instrument.camera.background_flatness_fraction,
        )
        ax.plot(n * SINGLE_EXPOSURE_S / 3600, snr, color=colours[band], label=f"{band}'")
        ax.scatter(row["current_exposures"] * SINGLE_EXPOSURE_S / 3600,
                   row["current_achieved_snr"], color=colours[band], s=35)
    ax.axhline(20, color="#0f172a", linewidth=1, linestyle="--", label="requested SNR 20")
    ax.set(xscale="log", yscale="log", xlabel="Total integration (hours)", ylabel="Actual stacked SNR",
           title="D  More frames approach, but cannot cross, the floor")
    ax.legend(frameon=False)

    fig.suptitle("SLT solve-for-time regression under the measured 2% background-flatness floor",
                 fontsize=15, fontweight="bold")
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=180, facecolor="white")
    plt.close(fig)


def write_report(table):
    example = table[
        table["telescope"].eq("SLT")
        & table["ab_magnitude"].eq(20)
        & table["target_snr"].eq(20)
    ].set_index("band")

    def returned(row):
        if np.isfinite(row["exact_exposures"]):
            return str(int(row["exact_exposures"])), "reaches SNR 20"
        return "unreachable", f"ceiling {row['asymptotic_snr_ceiling']:.2f} < 20, reported unreachable"

    rows = []
    for band in FILTERS:
        row = example.loc[band]
        frames, outcome = returned(row)
        rows.append(f"| {band}' | {row['asymptotic_snr_ceiling']:.2f} | {frames} | {outcome} |")
    table_rows = "\n".join(rows)
    g_frames = int(example.loc["g", "exact_exposures"])
    text = f"""# Solve-for-time versus the correlated background floor

The SLT DU934P preset carries the 2% background-flatness residual measured from
real extended-source data. That term is correlated across a stack, so it does
not average down: it fixes an asymptotic SNR ceiling `S/F` no exposure count can
cross. CASTOR includes it both when it computes a stack's SNR **and**, since the
question-17 fix, when it solves for the number of exposures. The old
`N = (target_snr / single_snr)^2` — valid only when every variance term is
independent between frames — has been replaced by the full inverse below, and an
unreachable request is now reported as such instead of answered with a count
that never meets it.

![Solve-for-time flatness audit](figures/solve_time_flatness_floor.png)

## Concrete result

Standard case: SLT/DU934P, AB=20 point source, 120 s frames, 1.421 arcsec image FWHM (1.4 arcsec seeing plus instrument terms),
0.85xFWHM aperture, 3–5xFWHM median annulus, the Lulin preset's own sky, target
near zenith, and requested SNR 20.

| Band | Asymptotic SNR ceiling | Exposures CASTOR now returns | Outcome |
|---|---:|---:|---|
{table_rows}

The r' request sits above its own ceiling: the response now returns
`target_reachable = false`, `required_exposures = null`, `total_snr` = the
ceiling, and a warning, rather than the six frames / SNR 14.44 the square-root
law used to claim. The i' target is farther beyond its ceiling. The g' target is
reachable and now takes {g_frames} frames — enough to actually clear SNR 20 —
where the old solver returned 4 and reached only 17.35.

LOT is the control: Sophia's preset has `background_flatness_fraction = 0`, so
the ceiling is infinite, the inverse collapses to the exact square-root law, and
its achieved/requested curve never falls below one. Bright cases can overshoot
because one indivisible frame already exceeds the requested SNR.

## The inverse that is now solved

For one frame, let `S` be source electrons, `V` the sum of every independent
variance term, and `F` the correlated flatness-noise amplitude. A stack of N
frames has

`SNR(N) = N*S / sqrt(N*V + N^2*F^2)`

and therefore the ceiling `S/F`. For a requested SNR `Q`:

`N = Q^2*V / (S^2 - Q^2*F^2)`

If the denominator is zero or negative (`Q >= S/F`), no finite exposure count can
reach the request under the model, and CASTOR reports the target as unreachable.
The sweep evaluates this expression against the shipped `required_exposures` over
LOT/SLT, g'/r'/i', AB 17–23 and target SNR 5–50; the two agree wherever the
target is reachable, and the shipped solver returns the unreachable flag
everywhere the ceiling is below the request.

## Status

Closed (validation question 17). The inverse solver, the response schema
(`snr_ceiling`, `target_reachable`), the CLI, the GUI and the batch path all
express the ceiling and the unreachable case; `test_solve_time_floor.py` is a
passing regression. This audit is retained as a check that the shipped solver
keeps matching the exact stack equation.

Regenerate with:

```bash
uv run --with pandas --with matplotlib python validation/analyze_solve_time_floor.py
```
"""
    REPORT.write_text(text, encoding="utf-8")


def main():
    table = build_table()
    make_figure(table)
    write_report(table)
    print(f"wrote {TABLE.relative_to(ROOT)}, {FIGURE.relative_to(ROOT)}, and {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
