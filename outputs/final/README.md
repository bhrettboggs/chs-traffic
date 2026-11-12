# outputs/final: the frozen Task 3 results

Every number the write-up quotes comes from the files in this folder. `RESULTS.md` holds the tables;
the CSVs next to it hold the same results with full precision; `raw/` holds one row per demand scenario
and run, which is what the tables are computed from.

## Settings

* AM peak and PM peak (measured peak factors, `data/reference/peak_factors.csv`); "AM+PM" adds the two peaks of the
  same scenario (scenario *i* uses the same random draws in both peaks).
* 20 demand scenarios (`config.N_SCENARIOS`, seed `config.SCENARIO_SEED`), user-equilibrium gap 1e-4.
* All demand x1.0, x1.3 and x1.6 (`config.SENSITIVITY_DEMAND_LEVELS`): the static model runs at about 1.02x
  free-flow time at x1.0 (HANDOFF finding D6), so every result is shown at three demand levels.
* One-way capacity bonus 1.10 (`config.ONEWAY_CAPACITY_BONUS`), and 1.0 and 1.2 for the city question.
* A change is called **detectable** only if the mean change over the scenarios is larger than
  `config.MIN_MEAN_IMPROVEMENT` (0.1% of total travel time) and has the same sign in at least 80% of scenarios.
  `noise_floor.csv` is the measurement behind that threshold.

## Reproduce from a clean checkout

Windows Command Prompt, Python 3.11 (`py -3.11 -m pip install --user -r requirements.txt` first):

    scripts\run_final.cmd

or step by step (each step resumes if stopped; `--workers` = number of processes):

    py -3.11 scripts\02_build_graph.py
    py -3.11 scripts\05_join_widths.py
    py -3.11 scripts\13_final_results.py noise --workers 4
    py -3.11 scripts\13_final_results.py backtest --workers 4
    py -3.11 scripts\13_final_results.py city --workers 4
    py -3.11 scripts\09_search.py --peak both --demand-scale 1 --max-rounds 20 --workers 4 --state outputs\final\search_state_both_x1.json --moves-out outputs\final\search_moves_x1.csv
    py -3.11 scripts\09_search.py --peak both --demand-scale 1.3 --max-rounds 20 --workers 4 --state outputs\final\search_state_both_x1.3.json --moves-out outputs\final\search_moves_x1.3.csv
    py -3.11 scripts\09_search.py --peak both --demand-scale 1.6 --max-rounds 20 --workers 4 --state outputs\final\search_state_both_x1.6.json --moves-out outputs\final\search_moves_x1.6.csv
    py -3.11 scripts\13_final_results.py pareto --workers 4
    py -3.11 scripts\13_final_results.py report

On Linux/macOS use `python` and forward slashes. To redo everything, delete `outputs/final/raw/` and
`outputs/final/search_state_*.json` first. The results do not depend on `--workers`
(`tests/test_search.py::test_parallel_evaluate_matches_serial_and_peaks_add`).

## Files

| File | What |
|---|---|
| `RESULTS.md` | All tables |
| `noise_floor.csv` | Same network solved twice (edge order shuffled; and gap 1e-4 vs 1e-5): per-scenario difference in TSTT |
| `backtest_tstt.csv` | Spring/Cannon two-way (today) vs one-way (2016): change in TSTT and veh-km |
| `backtest_station_volumes.csv`, `backtest_volume_change.csv` | Modeled volume at SCDOT stations 419 (Spring) and 417 (Cannon) before/after, vs SCDOT AADT 2016 to 2018, 2019, 2025 |
| `city_question.csv` | Coming, Rutledge, Ashley, all three two-way, and the P5-2 Ashley move, vs today, at bonus 1.0/1.1/1.2 |
| `city_converted_segments.csv`, `city_blocked_segments.csv` | Which segments each variant converts, and which can't go two-way |
| `search_state_both_x*.json`, `search_moves_x*.csv`, `search_moves.csv` | Open search per demand level: every move screened, confirmed and accepted |
| `pareto_screening.csv`, `pareto_confirmed.csv` | Non-dominated single moves (TSTT, veh-km, two-way share), then confirmed on all scenarios |
| `raw/*.csv` | One row per (configuration, peak, demand level, bonus, scenario) |

The model is not calibrated at link level (screenlines pass AM 4 of 6, PM 5 of 6). These are relative comparisons
between street configurations on the same model, not forecasts of Charleston traffic.
