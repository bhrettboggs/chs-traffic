# SUMO with enough seeds (Task 4b)

Pre-registered plan: `docs/task4b_plan.md` (sha256 `29bb87d3f6ff2e5a…`, last modified 2026-11-12T21:28:57Z; first Task 4b simulation started 2026-11-12T21:34:52Z). SUMO 1.28.0 meso, netconvert default signal timings, rerouting device, AM peak only, base-scenario OD at **demand x1.0**, **40 trip seeds** (4200-4239). Relative changes only: SUMO's signals are generic defaults, so this is Charleston's street geometry with generic signals, not real Charleston delay.

## Demand level (AM)

Chosen: x1.0 (decided 2026-11-12T21:39:55Z, before any main run). Task 4 baseline seeds 4100-4104 (recorded): 4100: 9 teleports, 4101: 4 teleports, 4102: 0 teleports, 4103: 1 teleports, 4104: 6 teleports. Fresh seeds: 4106 x1.0: 1 teleports, 0 left, stable, 4105 x1.0: 2 teleports, 0 left, stable, 4107 x1.0: 3 teleports, 0 left, stable.
Reproducibility, seed 4100 at x1.0 re-run with Task 4's generator: vehicles 35,748 (Task 4 35,748), teleports 9 (Task 4 9).

## Pairing

40 seeds; one trip draw shared by every variant in 40; same sim seed for every non-placebo variant in 40; placebo on sim seed + 1000 in 40; identical vehicle count in 40. Each run rebuilt its trip file and matched the SHA-256 checked trip by trip before the runs (`trips_sha`, `file_sha` in `seeds40.csv`).

## Results: change in AM total travel time vs today, per seed

Detected = 95% bootstrap interval excludes 0 AND |mean| > 0.5% AND the placebo's interval includes 0. Placebo interval includes 0: **yes**.

| Variant | Seeds | Mean | 95% interval | Median | Min to max | Better | Gridlock runs | Any teleport / vehicles left / teleports total | Static AM x1.0 mean (p10 to p90) | Static AM+PM | Static on SUMO's OD | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| today | 40 | (reference) | | | | | 3 | 29 / 3 / 88 | | | | |
| Coming Street | 40 | **-0.45%** | -2.04% to +1.08% | -0.62% | -14.30% to +10.63% | 60% | 0 | 25 / 0 / 74 | -0.167% (-0.207% to -0.138%) | -0.130% | -0.150% | inconclusive (no effect detected) |
| all three | 40 | **+4.26%** | +2.72% to +5.80% | +3.93% | -7.61% to +13.21% | 15% | 9 | 30 / 9 / 76 | -0.143% (-0.226% to -0.051%) | -0.114% | -0.121% | SUMO disagrees with the static model (opposite sign); SUMO wins; UNRELIABLE (9 gridlock-affected runs > 2) |
| today (other sim seed) | 40 | **-0.16%** | -3.15% to +2.83% | -0.71% | -19.76% to +20.53% | 52% | 3 | 24 / 3 / 88 |  |  |  | noise of an identical network |
| Rutledge Avenue | 40 | **+2.15%** | +0.51% to +3.82% | +2.56% | -9.37% to +19.60% | 28% | 8 | 27 / 8 / 76 | +0.263% (+0.104% to +0.509%) | +0.145% | +0.330% | SUMO agrees with the static model (same sign); UNRELIABLE (8 gridlock-affected runs > 2) |

Gridlock-affected run = not stable (vehicles not inserted or left at the end, or teleports above 0.5% of loaded); more than 2 of the seeds makes a variant unreliable. 'Any teleport' is shown for reference only (plan).

**Secondary (plan):** dropping the 10 seed(s) where today, Coming, all three or the placebo is gridlock-affected (4207, 4214, 4216, 4217, 4221, 4222, 4226, 4228, 4230, 4231):

| Variant | Seeds | Mean | 95% interval | Better |
|---|---|---|---|---|
| Coming Street | 30 | +0.00% | -1.73% to +1.64% | 53% |
| all three | 30 | +3.83% | +1.92% to +5.74% | 20% |
| today (other sim seed) | 30 | +0.35% | -3.25% to +4.01% | 53% |
| Rutledge Avenue | 30 | +2.87% | +0.93% to +4.92% | 23% |

## Where the change comes from (variants meeting the detection criteria)

Change vs today, veh-h, mean over seeds (sums over the peak-hour trips matched by id). 'Clean' = seeds where neither today's run nor the variant's is gridlock-affected. Wait = waiting to be inserted at the origin (queues backing up to the entry point); network = time from insertion to arrival. Edge time loss (edgeData, peak hour) on the converted streets, on other edges that end at a signal, and on the rest.

| Variant | Seeds | TSTT change (today's TSTT) | i26: wait / network | ravenel: wait / network | crosstown: wait / network | meeting_n: wait / network | jic: wait / network | king_ext: wait / network | internal: wait / network | Edge time loss: converted / other signalized / rest |
|---|---|---|---|---|---|---|---|---|---|---|
| all three | all 40 | +286 (6,874) | +1 / +68 | +35 / +13 | +2 / +55 | +0 / +5 | -59 / +16 | +0 / +6 | -1 / +145 | +64 / +35 / +111 |
| all three | clean 31 | +252 (6,837) | +1 / +66 | +14 / +14 | +4 / +58 | +0 / +5 | -63 / +14 | +0 / +6 | -2 / +134 | +65 / +36 / +105 |
| Rutledge Avenue | all 40 | +139 (6,874) | +1 / +75 | +41 / +12 | -5 / -25 | +0 / +1 | -59 / -33 | +0 / +9 | +0 / +123 | +0 / +20 / +106 |
| Rutledge Avenue | clean 32 | +92 (6,807) | +1 / +69 | +25 / +12 | -5 / -31 | +0 / +2 | -66 / -36 | +0 / +9 | +0 / +113 | +1 / +21 / +99 |

Same edge time loss split by place: the converted street's own edges / every other edge that ends at one of its junctions (cross-street approaches) / everything else. Signal programs: netconvert rebuilds its default program at every signalized junction whose movements change.

| Variant | Seeds | Street / approaches / elsewhere (veh-h) | Junctions on the street | Signalized | Programs changed |
|---|---|---|---|---|---|
| all three | all 40 | +64 / +92 / +54 | 65 | 22 | 22 |
| all three | clean 31 | +65 / +91 / +50 | 65 | 22 | 22 |
| Rutledge Avenue | all 40 | +0 / +16 / +110 | 21 | 5 | 5 |
| Rutledge Avenue | clean 32 | +1 / +16 / +104 | 21 | 5 | 5 |

Trips with no tripinfo record (never inserted by the end of the run, so absent from TSTT, which makes that run look slightly better): all three seed 4221: today 0, variant 19; Rutledge Avenue seed 4221: today 0, variant 31.

## Notes

* today itself has 3 gridlock-affected runs of 40 and the placebo 3: x1.0 is marginal for every network, so the secondary analysis (gridlock seeds dropped) is the check that the means are not riding on them.
* The placebo's spread (SD of d over seeds) is 10.0% against 5.0% for the variants: sharing the sim seed roughly halves the noise, which is what pairing is for. The placebo answers 'is an identical network centred on 0', not 'how noisy is a paired comparison'.
* TSTT (Task 4 definition) leaves out trips never inserted by the end of the run; that only happens in gridlock-affected runs and makes those runs look better, not worse.
* Generic signals: netconvert rebuilds a default program at every signal a conversion touches (see the table above). A real conversion would come with retimed signals and turn lanes; SUMO's answer is about the geometry with generic signals, not Charleston's real delay.

