# Solve-for-time versus the correlated background floor

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
| g' | 29.78 | 7 | reaches SNR 20 |
| r' | 18.46 | unreachable | ceiling 18.46 < 20, reported unreachable |
| i' | 8.27 | unreachable | ceiling 8.27 < 20, reported unreachable |

The r' request sits above its own ceiling: the response now returns
`target_reachable = false`, `required_exposures = null`, `total_snr` = the
ceiling, and a warning, rather than the six frames / SNR 14.44 the square-root
law used to claim. The i' target is farther beyond its ceiling. The g' target is
reachable and now takes 7 frames — enough to actually clear SNR 20 —
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
