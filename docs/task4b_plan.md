# Task 4b plan: SUMO with enough seeds (pre-registered)

Written 2026-11-12, before any Task 4b simulation was run. Not to be changed after results are seen.
Anything decided later (the demand level, whether Rutledge ran, 40 or 20 seeds) follows a rule fixed here
and is recorded in `outputs/final/sumo/RESULTS_4b.md`, not edited into this file.

## Question

Task 4 (5 seeds) found SUMO's run-to-run noise (SD about 3.5% of total travel time) far larger than the
static model's effects (0.1-0.2%), and one loose thread: "all three two-way" came out +3.5% in SUMO (worse
in 4 of 5 seeds) where the static model says -0.11% (AM+PM). With signals, are the conversions' effects
about 1% or larger, and with what sign?

## Design

* **Simulator:** SUMO 1.28.0 meso, exactly as Task 4 (`src/chstraffic/sumo.py`, config `SUMO_*`): same
  networks (one per variant, built from the 2026-11-09 OSM snapshot), netconvert default signal timings,
  rerouting device, 15-min warm-up, 1-h peak, 1-h drain. Nothing in signals, capacities or demand is tuned.
* **Variants:** today; Coming St two-way; all three (Coming, Rutledge, Ashley) two-way; and a **placebo**:
  today re-simulated with a different simulation seed (`sim_seed = seed + 1000`) on the same trips.
  Rutledge two-way is optional: it is queued after every other run, and is reported only if all its 40
  seeds finish in the same batch. Ashley alone is not run.
* **Peak:** AM only. The PM is not run (it needed x0.8 to run at all).
* **Demand level:** the highest of x1.0, x0.9, x0.8, ... (config `SUMO_DEMAND_STEPS`) at which the
  baseline (today, sim seed = trip seed) is stable in all of: the 5 Task 4 seeds (4100-4104; their
  x1.0 runs are recorded in `outputs/final/sumo/sumo_runs.csv`; at any lower level they are run fresh)
  and 3 fresh seeds (4105-4107). "Stable" = the project's existing rule (`14_sumo_check.is_stable`):
  every vehicle inserted, no vehicle left in the network at the end (1 h after the last departure), and
  teleports at most 0.5% of loaded vehicles. A level fails at its first unstable run. Seed 4100 at x1.0 is
  also re-run once as a reproducibility check (same vehicle and teleport counts as Task 4 expected).
* **Seeds:** 40 trip seeds, 4200-4239 (disjoint from Task 4 and from the level check). Per seed, one
  trip file (Poisson draw per OD pair from the base-scenario AM OD at the chosen level) is written once
  and used by every variant; every non-placebo variant uses `sim_seed = seed`. Each run records the
  SHA-256 of its trip file and its sim seed, so `seeds40.csv` itself shows the pairing. Before the runs,
  every junction id in every trip file is checked to exist in every variant's network.
* **Fallback:** if the timing estimate says 40 seeds will not finish in about a day of laptop time, run
  seeds 4200-4219 only and report it as 20 seeds. Never extend after looking at results.

## Statistic and decision rule

* Per seed s and variant v: `d_v(s) = TSTT_v(s) / TSTT_today(s) - 1`, TSTT = total travel time (in network
  + insertion wait) of the trips due in the peak hour (Task 4 definition).
* Report per variant: mean of d over seeds; **95% bootstrap interval** over seeds (percentile method,
  10,000 resamples of the seeds with replacement, numpy `default_rng(4242)`); share of seeds with d < 0
  (better); median; min and max.
* **Detected** iff (1) the 95% interval excludes 0, (2) |mean| > 0.5%, and (3) the placebo's 95%
  interval includes 0. If the placebo's interval excludes 0, the pairing is not working: report that and
  call every variant inconclusive.
* **Verdict per variant**, against the static model's AM sign at x1.0 (20 scenarios, bonus 1.1,
  `outputs/final/city_question.csv`: Coming -0.168%, all three -0.143%, Rutledge +0.263%; AM+PM
  -0.130%, -0.114%, +0.145% as in HANDOFF F4 are shown too, as is the static model run on SUMO's exact
  OD and level):
  * detected with the static sign: **SUMO agrees** on the sign (say separately whether the size differs);
  * detected with the opposite sign: **SUMO disagrees**, and SUMO wins (HANDOFF section 11);
  * not detected: **inconclusive** on the sign. If the whole 95% interval lies inside (-0.5%, +0.5%),
    add "SUMO rules out an effect of 0.5% or more", which is consistent with the static model's size.

## Reliability (gridlock)

* A run is **gridlock-affected** if it is not stable by the rule above (vehicles not inserted or left at
  the end, or teleports above 0.5% of loaded). A variant with more than 2 gridlock-affected runs out of 40
  is **unreliable**, whatever its interval.
* Also reported, not used in the verdict: the number of runs with any teleport at all and with any
  vehicle left, for every variant including today (Task 4 had 1-9 teleports in most AM runs, today
  included, so "any teleport" by itself would mark every variant unreliable, today too).
* Secondary analysis, fixed now: the same statistic dropping every seed where any variant or the placebo
  is gridlock-affected. Reported alongside; the verdict uses the primary analysis.

## If a variant is detected

From per-run trip and edge summaries saved during every run (no reruns): change in TSTT by origin
(gateway entries vs internal trips) and by destination; insertion delay vs in-network time; time loss on
the converted streets' SUMO edges vs elsewhere; teleports and leftover vehicles in the seeds that drive
the mean. Classify as signal/queue driven or a gridlock artifact, as far as meso output allows.

## Caveats fixed in advance

SUMO uses netconvert's default signal timings, so any result is about Charleston's street geometry with
generic signals, not real Charleston delay. Meso is a queue model, not lane-level microsimulation. Rerouting
is reactive, not an equilibrium. The OD is the static model's base scenario (no demand-scenario spread).
