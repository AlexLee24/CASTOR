# Solve-for-time reachability map

The single operating point in the section above is one cell of a larger grid.
Sweeping LOT/SLT x g'/r'/i' x AB 17-23 x requested SNR 5-50 shows the whole
reachable/unreachable structure the fixed solver now respects.

![Solve-for-time reachability map](figures/solve_time_reachability.png)

Colour is achieved-over-requested SNR for the returned exposure count, so 1.0 is
honest and blue is a harmless integer-frame overshoot. Before the question-17
fix the SLT row turned red across a wide band of faint targets and high SNR
goals — requests the old sqrt(N) solver accepted but undershot, worst of all SLT
i' at AB 23, SNR 50, where it delivered 1% of the request. The corrected solver
returns a count that meets the request wherever the target is below the ceiling,
so those cells now sit at 1.0 or a small integer-frame overshoot. The hatched
cells are requests above the model's asymptotic ceiling: unreachable at any
exposure, and now reported as `target_reachable = false` with no frame count
rather than silently undershot. The LOT row (flatness 0) has an infinite ceiling,
so the exact square-root law applies and it is honest everywhere.

Regenerate with:

```bash
uv run --with pandas --with matplotlib python validation/analyze_solve_reachability.py
```
