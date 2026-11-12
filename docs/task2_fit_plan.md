# Demand-level fit: plan written before fitting (2026-11-12)

Written before any fitting run of the non-work parameters. The only model runs before this file:
`04_calibrate.py` with the old demand (K 0.09, split 0.60) and with the measured peak factors, AM only,
non-work off. Their screenline results are the "before" tables.

## Held out

* **Held-out half = every station with `split = test` in `data/reference/count_stations.csv`** (18 stations;
  the split was set in P2 by alternating in file order, before any model run). The fit never reads their model flows.
* Screenline totals are computed per half: for each screenline A-F, the sum over its calibrate-half stations
  (fit) and the sum over its test-half stations (held out). Membership is `data/reference/screenlines.csv`
  as of commit `dbf20af`, unchanged.

| Line | Calibrate half (fit) | Test half (held out) |
|---|---|---|
| A | 145, 423 | 171, 180 |
| B | 437, 434 | 432, 458, 560, 428 |
| C | 425, 431, 439, 583 | 429, 438, 169 |
| D | 454, 433 | 426, 436 |
| E | 414, 407, 125, 596, 427 | 403, 585 |
| F | 417 | 415, 419, 421 |

## Free parameters (three, nothing else moves)

`NONWORK_RETAIL_FOOD_WEIGHT` (R), `NONWORK_RESIDENT_WEIGHT` (P), `NONWORK_INTERNAL_VPH` (N, the overall scale).
Grid: R in {0, 0.5, 1, 2}, P in {0, 0.5, 1}, N in {0, 1000, 2000, 3000, 4500, 6000} vph; pairs with
R = P = 0 and N > 0 are skipped (no activity to attract the trips). 67 points. Everything else stays at its
config value, including the measured peak factors (`PEAK_FACTOR_SOURCE = "ccs"`), which are data, not fitted.

## Objective

Base demand (no scenario noise), UE gap 1e-4, AM and PM peaks.
Loss = mean over the 6 lines x 2 peaks of ( ln(model / count) )^2, using the calibrate-half totals.
The chosen point is the grid minimum. One pass: no second grid, no refinement around the minimum.

## Held-out report and adoption rule

After the choice, compute the same loss on the test-half totals for exactly two points, neutral
(R = P = N = 0) and chosen. Report it once. **Adopt the chosen values only if the calibrate loss and the
held-out loss are both lower than at neutral.** Otherwise adopt nothing and say so.
Then rerun `04_calibrate.py --peak both` (10 scenarios, gap 1e-4) for the full screenline table and the link GEH table.

## Stop rule

If screenlines A and D still fail after this (full-line totals, either peak), stop: record the gap and set up the
demand-level sensitivity (all demand x1.0, x1.3, x1.6) for Task 3. No per-street capacity or speed tuning.
