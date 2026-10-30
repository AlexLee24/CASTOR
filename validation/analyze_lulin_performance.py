"""Build a forward-only LOT/SLT capability and noise-budget atlas.

The inverse exposure solver is deliberately not used.  One live CASTOR request
establishes each rig/band's geometry and rates, then the forward stack equation
is evaluated over source magnitude and actual integer frame counts.

Run from the repository root::

    uv run --with pandas --with matplotlib python validation/analyze_lulin_performance.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from castor import physics, schema
from castor.calculator import run_calculation
from castorCLI import presets


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "validation/data/lulin_forward_performance.csv"
FIGURE = ROOT / "validation/figures/lulin_forward_performance.png"
REPORT = ROOT / "validation/report_sections/performance.md"

RIGS = {"LOT": "Sophia", "SLT": "SLT_DU934P"}
FILTERS = {"g": "Sloan_g", "r": "Sloan_r", "i": "Sloan_i"}
FRAME_COUNTS = np.array([1, 2, 3, 5, 10, 20, 30, 60, 120])
MAGNITUDES = np.round(np.arange(15.0, 25.01, 0.1), 1)
SINGLE_EXPOSURE_S = 120.0
REFERENCE_MAG = 20.0
OBSERVING_TIME = "2026-01-15T16:00:00Z"
TARGET_RA_DEG = 113.65
TARGET_DEC_DEG = 31.89


def base_request(telescope: str, camera: str, filter_id: str):
    data = presets.load().resolve(
        "lulin", telescope=telescope, camera=camera, optic_filter=filter_id
    )
    data["instrument"]["throughput_correction"] = 1.0
    data["target"] = {
        "morphology": {"type": "point"},
        "brightness": {"type": "ab_mag", "target_mag": REFERENCE_MAG},
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
        "type": "solve_snr",
        "aperture_factor": 0.85,
        "single_exp_time": SINGLE_EXPOSURE_S,
        "sky_annulus": {"inner_factor": 3.0, "outer_factor": 5.0, "estimator": "median"},
        "num_exposures": 1,
    }
    return schema.ObservationRequest.model_validate(data)


def build_table():
    rows = []
    for telescope, camera in RIGS.items():
        for band, filter_id in FILTERS.items():
            request = base_request(telescope, camera, filter_id)
            reference = run_calculation(request)
            instrument = request.instrument
            diagnostics = reference.diagnostics
            budget = reference.budget
            for magnitude in MAGNITUDES:
                scale = 10 ** (-0.4 * (magnitude - REFERENCE_MAG))
                source_rate = budget.source_count_rate * scale
                peak_rate = budget.peak_pixel_rate * scale
                saturation_time = physics.calculate_saturation_time(
                    instrument.camera.full_well_capacity,
                    peak_rate,
                    budget.sky_count_rate,
                    instrument.camera.dark_current_rate,
                )
                for frame_count in FRAME_COUNTS:
                    total_time = frame_count * SINGLE_EXPOSURE_S
                    snr = physics.calculate_total_snr(
                        source_rate,
                        budget.sky_count_rate,
                        instrument.camera.dark_current_rate,
                        instrument.camera.readout_noise,
                        diagnostics.num_pixels_aperture,
                        SINGLE_EXPOSURE_S,
                        total_time,
                        frame_count,
                        diagnostics.num_pixels_sky_estimate,
                        instrument.camera.background_flatness_fraction,
                    )
                    signal_variance = source_rate * total_time
                    sky_variance = (
                        diagnostics.num_pixels_aperture + diagnostics.num_pixels_sky_estimate
                    ) * budget.sky_count_rate * total_time
                    detector_variance = frame_count * (
                        diagnostics.num_pixels_aperture + diagnostics.num_pixels_sky_estimate
                    ) * (
                        instrument.camera.dark_current_rate * SINGLE_EXPOSURE_S
                        + instrument.camera.readout_noise**2
                    )
                    flatness_variance = physics.calculate_background_flatness_variance(
                        budget.sky_count_rate,
                        total_time,
                        diagnostics.num_pixels_aperture,
                        instrument.camera.background_flatness_fraction,
                    )
                    rows.append({
                        "telescope": telescope,
                        "camera": camera,
                        "band": band,
                        "ab_magnitude": magnitude,
                        "frame_count": int(frame_count),
                        "single_exposure_s": SINGLE_EXPOSURE_S,
                        "total_exposure_s": total_time,
                        "snr": float(snr),
                        "saturation_time_s": float(saturation_time),
                        "model_saturated": SINGLE_EXPOSURE_S > saturation_time,
                        "source_variance": signal_variance,
                        "sky_variance": sky_variance,
                        "detector_variance": detector_variance,
                        "flatness_variance": flatness_variance,
                        "source_rate_e_s": source_rate,
                        "sky_rate_e_s_pix": budget.sky_count_rate,
                        "pixel_scale_arcsec": diagnostics.pixel_scale,
                        "aperture_pixels": diagnostics.num_pixels_aperture,
                        "sky_estimate_pixels": diagnostics.num_pixels_sky_estimate,
                    })
    table = pd.DataFrame(rows)
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(TABLE, index=False, float_format="%.8g")
    return table


def limiting_magnitude(table, telescope, band, frame_count, target_snr):
    subset = table[
        table["telescope"].eq(telescope)
        & table["band"].eq(band)
        & table["frame_count"].eq(frame_count)
        & ~table["model_saturated"]
    ].sort_values("ab_magnitude")
    if subset["snr"].min() > target_snr or subset["snr"].max() < target_snr:
        return np.nan
    return float(np.interp(target_snr, subset["snr"].to_numpy()[::-1],
                           subset["ab_magnitude"].to_numpy()[::-1]))


def make_figure(table):
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    colours = {"g": "#16a34a", "r": "#dc2626", "i": "#7c3aed"}

    ax = axes[0, 0]
    for telescope, style in (("LOT", "-"), ("SLT", "--")):
        subset = table[
            table["telescope"].eq(telescope)
            & table["band"].eq("r")
            & table["frame_count"].eq(1)
        ]
        ax.plot(subset["ab_magnitude"], subset["snr"], style, linewidth=2,
                color=colours["r"], label=f"{telescope} r'")
    for goal in (5, 10, 20):
        ax.axhline(goal, color="#94a3b8", linewidth=0.8, linestyle=":")
    ax.set(yscale="log", xlabel="Target AB magnitude", ylabel="SNR in one 120 s frame",
           title="A  Single-frame r' capability")
    ax.legend(frameon=False)

    ax = axes[0, 1]
    for telescope, style in (("LOT", "-"), ("SLT", "--")):
        for band in FILTERS:
            subset = table[
                table["telescope"].eq(telescope)
                & table["band"].eq(band)
                & table["frame_count"].eq(30)
            ]
            ax.plot(subset["ab_magnitude"], subset["snr"], style, linewidth=1.8,
                    color=colours[band], label=f"{telescope} {band}'")
    ax.axhline(5, color="#0f172a", linewidth=1, linestyle=":")
    ax.set(yscale="log", xlabel="Target AB magnitude", ylabel="SNR in 1 hour",
           title="B  One-hour capability from the forward model")
    ax.legend(frameon=False, ncol=2, fontsize=8)

    ax = axes[1, 0]
    for telescope, style in (("LOT", "-"), ("SLT", "--")):
        for band in FILTERS:
            limits = [limiting_magnitude(table, telescope, band, n, 5.0) for n in FRAME_COUNTS]
            ax.plot(FRAME_COUNTS * SINGLE_EXPOSURE_S / 3600, limits, style,
                    marker="o", markersize=4, color=colours[band], label=f"{telescope} {band}'")
    ax.set(xscale="log", xlabel="Total integration (hours)", ylabel="SNR=5 limiting AB magnitude",
           title="C  Depth gained by stacking actual frame counts")
    ax.legend(frameon=False, ncol=2, fontsize=8)

    ax = axes[1, 1]
    standard = table[
        table["ab_magnitude"].eq(20)
        & table["frame_count"].eq(1)
    ].copy()
    standard["label"] = standard["telescope"] + " " + standard["band"] + "'"
    variances = standard[["source_variance", "sky_variance", "detector_variance", "flatness_variance"]]
    fractions = variances.div(variances.sum(axis=1), axis=0)
    bottom = np.zeros(len(standard))
    components = [
        ("source_variance", "Source shot", "#2563eb"),
        ("sky_variance", "Sky + annulus", "#f59e0b"),
        ("detector_variance", "Read + dark", "#64748b"),
        ("flatness_variance", "Correlated flatness", "#dc2626"),
    ]
    for column, label, colour in components:
        values = fractions[column].to_numpy()
        ax.bar(standard["label"], values, bottom=bottom, color=colour, label=label)
        bottom += values
    ax.set(ylabel="Fraction of total variance", title="D  Noise budget at AB=20, one 120 s frame")
    ax.tick_params(axis="x", rotation=35)
    ax.legend(frameon=False, fontsize=8)

    fig.suptitle("Lulin forward-performance atlas · 1.4 arcsec seeing + instrument terms · near zenith · 120 s frames",
                 fontsize=15, fontweight="bold")
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=180, facecolor="white")
    plt.close(fig)


def write_report(table):
    rows = []
    for telescope in RIGS:
        for band in FILTERS:
            one = limiting_magnitude(table, telescope, band, 1, 5)
            hour = limiting_magnitude(table, telescope, band, 30, 5)
            four = limiting_magnitude(table, telescope, band, 120, 5)
            hour10 = limiting_magnitude(table, telescope, band, 30, 10)
            rows.append(
                f"| {telescope} | {band}' | {one:.2f} | {hour:.2f} | {four:.2f} | {hour10:.2f} |"
            )
    result_rows = "\n".join(rows)
    text = f"""# Lulin forward-performance atlas

This compares LOT/Sophia and SLT/DU934P by evaluating CASTOR's forward noise
equation over actual integer stacks. It deliberately does not call the inverse
exposure solver audited in the solve-for-time section.

![Lulin forward performance](figures/lulin_forward_performance.png)

## Standard scene

Point source, AB magnitudes, g'/r'/i', 120 s sub-exposures, 1.421 arcsec image FWHM (1.4 arcsec seeing plus instrument terms),
0.85xFWHM aperture, 3–5xFWHM median sky annulus, fixed target near zenith at
Lulin, no lunar term, and each filter's current preset sky and throughput.

| Telescope | Band | SNR=5, 120 s | SNR=5, 1 h | SNR=5, 4 h | SNR=10, 1 h |
|---|---|---:|---:|---:|---:|
{result_rows}

The one-hour curves show the expected aperture advantage of LOT. They also
show the consequence of model completeness: SLT carries a measured 2%
background-flatness floor and gains progressively less depth with long stacks,
while Sophia currently carries zero because no equivalent floor has been
measured for it. Zero means "not modelled", not evidence that LOT has no
correlated background residual.

At AB=20, sky photons dominate most 120 s configurations. Read noise matters
more for SLT because there are fewer source electrons, while the correlated
term is already visible in its one-frame variance and controls its long-stack
limit. Dark current is negligible in these particular 120 s cases.

## Limits on interpretation

These are conditional model predictions, not measured limiting magnitudes or
uncertainty intervals. They use the current top-hat filters, one pointing, one
image FWHM and the site-wide 0.17 extinction fallback. Readout overhead is
not modelled. Saturation uses the preset physical full well; LOT frames in the
end-to-end night actually hit their 16-bit ADC ceiling near 60,292 e-, so the
bright boundary in the CSV is optimistic for that operating mode.

Regenerate with:

```bash
uv run --with pandas --with matplotlib python validation/analyze_lulin_performance.py
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
