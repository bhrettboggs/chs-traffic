# SUMO check of the static model (Task 4)

SUMO 1.28.0 mesoscopic, signals from OSM with netconvert's default timings (not Charleston's), routes by the rerouting device. Base-scenario OD, demand AM x1.0, PM x0.8 (highest level without gridlock per peak), 5 seeds (each seed = its own Poisson trip draw, the same trips for every variant). Measured: total travel time of trips due in the peak hour after a 15-min warm-up, AM and PM added per seed. Relative changes only.

SUMO noise floor (today re-simulated with another sim seed, median |change|): am 5.587%, pm 4.067%, am+pm 2.542%. Detectable threshold: am 11.174%, pm 8.133%, am+pm 5.084%.

## Static vs SUMO, AM+PM

| Two-way | Static (20 scenarios, x1.0) mean (p10 to p90), better | Static, same OD and level as SUMO | SUMO mean (min to max over seeds), better | Verdict |
|---|---|---|---|---|
| Coming Street | -0.130% (-0.170% to -0.081%), 100% | -0.152% | -1.147% (-6.406% to +4.560%), 60% | inconclusive (SUMO cannot resolve it) |
| Rutledge Avenue | +0.145% (+0.033% to +0.253%), 10% | +0.172% | +0.164% (-3.983% to +5.409%), 60% | inconclusive (SUMO cannot resolve it) |
| Ashley Avenue | +0.089% (+0.035% to +0.147%), 0% | +0.033% | +0.267% (-5.739% to +5.025%), 40% | agree (neither detects an effect) |
| all three | -0.114% (-0.189% to -0.016%), 90% | -0.182% | +3.476% (-2.071% to +6.496%), 20% | inconclusive (SUMO cannot resolve it) |

## How to read this

* The same network re-simulated with another sim seed changes AM+PM total travel time by 3.5% (standard deviation over seeds). Telling a 0.15% effect from zero at 2 sigma would take about 2,190 seeds. With 5 seeds SUMO can confirm or contradict only effects of several percent; the static effects are 0.03 to 0.2%.
* Runs that ended with vehicles still in the network (stability is tested on the baseline only): all three am seed 4103: 2; Rutledge Avenue am seed 4104: 14; all three am seed 4104: 17; today (other sim seed) am seed 4104: 107.
* The PM runs at demand x0.8; the screenline counts below are the x1.0 counts, so part of the PM shortfall is the demand cut itself. The static column uses the same OD and level as SUMO.
* Absolute travel times are not reported: signal timings are netconvert defaults.

## By peak

| Two-way | Peak | Static mean | SUMO mean (min to max) | SUMO better |
|---|---|---|---|---|
| Coming Street | am | -0.167% | +1.015% (-4.684% to +7.292%) | 40% |
| Coming Street | pm | -0.093% | -4.526% (-14.892% to +2.734%) | 60% |
| Rutledge Avenue | am | +0.263% | +3.319% (-2.242% to +9.605%) | 20% |
| Rutledge Avenue | pm | +0.033% | -4.675% (-13.529% to -0.600%) | 100% |
| Ashley Avenue | am | -0.032% | +1.396% (-4.087% to +7.884%) | 60% |
| Ashley Avenue | pm | +0.204% | -1.556% (-8.657% to +5.386%) | 40% |
| all three | am | -0.143% | +3.990% (-0.904% to +7.224%) | 20% |
| all three | pm | -0.087% | +2.615% (-4.133% to +6.457%) | 20% |
| today (other sim seed) | am |  | +0.968% (-9.336% to +5.891%) | 20% |
| today (other sim seed) | pm |  | +1.466% (-4.067% to +5.364%) | 40% |

## Teleports (gridlock) per run

| Variant | Peak | Teleports per seed | Stable |
|---|---|---|---|
| Ashley Avenue | am | 8, 3, 1, 3, 1 | 5/5 |
| Ashley Avenue | pm | 1, 1, 0, 3, 0 | 5/5 |
| Coming Street | am | 1, 1, 2, 1, 2 | 5/5 |
| Coming Street | pm | 0, 0, 1, 1, 4 | 5/5 |
| Rutledge Avenue | am | 4, 2, 3, 0, 9 | 4/5 |
| Rutledge Avenue | pm | 1, 0, 1, 0, 1 | 5/5 |
| all three | am | 8, 4, 5, 4, 5 | 3/5 |
| all three | pm | 0, 0, 0, 0, 0 | 5/5 |
| today | am | 9, 4, 0, 1, 6 | 5/5 |
| today | pm | 0, 0, 1, 2, 1 | 5/5 |
| today (other sim seed) | am | 2, 3, 0, 0, 2 | 4/5 |
| today (other sim seed) | pm | 1, 0, 0, 1, 6 | 5/5 |

## Screenlines, baseline volumes (vph, both directions, middle segment)

| Peak | Line | Count | Tol. | SUMO median (min to max) | dev | Static base OD | dev | SUMO/static |
|---|---|---|---|---|---|---|---|---|
| am | A | 4,778 | ±30% | 5,016 (4,998 to 5,139) | +5% | 3,019 | -37% ✗ | 1.66 |
| am | B | 2,204 | ±41% | 4,669 (4,539 to 4,849) | +112% ✗ | 3,611 | +64% ✗ | 1.29 |
| am | C | 6,046 | ±28% | 5,043 (4,960 to 5,120) | -17% | 6,028 | -0% | 0.84 |
| am | D | 811 | ±59% | 980 (969 to 1,039) | +21% | 657 | -19% | 1.49 |
| am | E | 9,798 | ±25% | 5,856 (5,754 to 5,974) | -40% ✗ | 9,366 | -4% | 0.63 |
| am | F | 3,042 | ±35% | 2,835 (2,798 to 2,885) | -7% | 3,221 | +6% | 0.88 |
| pm | A | 5,052 | ±30% | 3,699 (3,662 to 3,774) | -27% | 2,711 | -46% ✗ | 1.36 |
| pm | B | 2,329 | ±41% | 4,006 (3,859 to 4,077) | +72% ✗ | 2,224 | -4% | 1.8 |
| pm | C | 6,389 | ±28% | 4,562 (4,491 to 4,650) | -29% ✗ | 4,898 | -23% | 0.93 |
| pm | D | 857 | ±59% | 931 (858 to 952) | +9% | 565 | -34% | 1.65 |
| pm | E | 10,356 | ±25% | 5,123 (5,080 to 5,203) | -51% ✗ | 7,846 | -24% | 0.65 |
| pm | F | 3,215 | ±35% | 2,676 (2,614 to 2,722) | -17% | 2,559 | -20% | 1.05 |
