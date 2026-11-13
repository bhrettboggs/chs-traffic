# Claims check

Every number in [README.md](../README.md), with the file and row it comes from. "Computed" means
computed from that file by `scripts/15_make_figures.py` (the same code that draws the figures). Percent
changes are rounded from the file's full-precision values.

| README section | Claim | Source file | Row / field |
|---|---|---|---|
| Intro, 3 | Coming St two-way -0.13% (static) | `outputs/final/city_question.csv` | Coming Street, bonus 1.1, demand 1.0, am+pm: mean -0.00130 |
| Intro, 3 | All three about 4% slower in SUMO (+4.3%) | `outputs/final/sumo/seeds40_summary.csv` | all three: mean 0.04259 |
| Intro | 9 of 40 runs hit the gridlock flag; holds without them | `outputs/final/sumo/seeds40_summary.csv` | all three: gridlock_runs 9; sec_mean +3.83% (+1.92% to +5.74%), see note 1 |
| 1 | 30 years of conversions: Upper King 1994, Spring/Cannon 2017 | `data/reference/oneway_review.csv` (evidence column); city release 2017-09-20 (link in README section 5) | King St rows: "Upper King (Line St to Calhoun St) went back to two-way in 1994"; release: work from 2017-10-02 |
| 1 | 2025 study, about $230,000, Kimley-Horn; study limits | City project page; Live 5 News 2025-09-04 (links in README section 7) | — |
| 1, 3 | 46 corridors | `outputs/final/RESULTS.md` | section 4 heading "46 corridors" |
| 2 | 1,141 intersections, 2,991 directed links | `data/processed/chs_digraph.gpickle` (built by `02_build_graph.py`) | node and edge counts (Task 1 network QA, finding Q1 context) |
| 2 | OSM right in 35 of 37 on-corridor disagreements; 2 Beaufain segments fixed | `data/reference/oneway_review.csv`; `data/reference/overrides.csv` | verdict column (35 OSM correct, 2 fixed, 5 unknown of 42); 1 direction override row |
| 2 | 16 lane overrides | `data/reference/overrides.csv` | 17 rows: 16 lane overrides + 1 direction override (Beaufain) |
| 2 | Six gateways | `data/reference/zones.csv` | 6 inbound gateway rows |
| 2 | Hourly counts Sept-Oct 2025 | `data/raw/scdot_ccs_hourly_2025.csv` | dates 2025-09-02 to 2025-10-30 |
| 2 | 90 zones, LODES 2024 | `data/reference/zones_lodes.csv`; `config.N_ZONES`, `config.LODES_YEAR` | 90 rows |
| 2 | 20 scenarios, x1.0/1.3/1.6, gap 1e-4 | `outputs/final/README.md` Settings; `config.SENSITIVITY_DEMAND_LEVELS` | — |
| 2 | Detectable = mean > 0.1% and same sign in >= 80% | `outputs/final/RESULTS.md` section 1; `config.MIN_MEAN_IMPROVEMENT` | — |
| 2 | 40 paired seeds, flag if > 2 of 40 runs gridlock | `docs/task4b_plan.md` | "Reliability (gridlock)" |
| 3 | Coming -0.13% (p10 -0.17%, p90 -0.08%), better in every scenario | `outputs/final/city_question.csv` | Coming Street, 1.1, 1.0, am+pm: mean -0.00130, p10 -0.00170, p90 -0.00081, improved_share 1.0 |
| 3 | Coming still detectable at x1.3 and x1.6 | `outputs/final/city_question.csv` | Coming Street, 1.1, 1.3 / 1.6, am+pm: -0.112% / -0.113%, verdict "detectable: better" |
| 3 | About 4.6 veh-h over the two peak hours, out of about 3,600 | `outputs/final/raw/city.csv` | computed: mean over 20 scenarios of (today - Coming) AM+PM TSTT at scale 1.0, bonus 1.1 = 4.62 veh-h; today AM+PM mean 3,604 veh-h |
| 3 | Rutledge +0.15% (+0.03% to +0.25%) | `outputs/final/city_question.csv` | Rutledge Avenue, 1.1, 1.0, am+pm: +0.145%, p10 +0.033%, p90 +0.253% |
| 3 | Rutledge more so at higher demand | `outputs/final/city_question.csv` | same, demand 1.3 / 1.6: +0.332% / +0.480% |
| 3 | Ashley +0.09% at x1.0, not detectable; worse at x1.3 and x1.6 | `outputs/final/city_question.csv` | Ashley Avenue, 1.1, am+pm: +0.089% n.d.; +0.189%, +0.282% "detectable: worse" |
| 3 | All three -0.11% x1.0; n.d. x1.3; +0.21% x1.6 | `outputs/final/city_question.csv` | all three, 1.1, am+pm: -0.114% / +0.066% n.d. / +0.208% |
| 3 | 86 moves screened per level, none beat 0.1% | `outputs/final/RESULTS.md` | section 4 "Screening ... round 1": 86 evaluated, 0 better than -0.1% at each level |
| 3 | Model streets reach past the city's study limits | `outputs/final/city_converted_segments.csv` + `docs/figures/fig5_converted_streets.png` | segment endpoints (Coming to Beaufain; Rutledge/Ashley north of the Crosstown; Broad-Tradd) |
| 3 | SUMO all three +4.3% (+2.7% to +5.8%) | `outputs/final/sumo/seeds40_summary.csv` | all three: mean 0.04259, ci_lo 0.02724, ci_hi 0.05796 |
| 3 | Worse in 34 of 40 seeds | `outputs/final/sumo/seeds40.csv` | all three rows: d_vs_today > 0 in 34 of 40 (better_share 0.15 in the summary) |
| 3 | Static model -0.14% for the same AM peak | `outputs/final/sumo/seeds40_summary.csv` | all three: static_am_mean -0.00143 (= city_question.csv all three, 1.1, 1.0, am) |
| 3 | 9 of 40 runs gridlock-affected | `outputs/final/sumo/seeds40_summary.csv` | all three: gridlock_runs 9 |
| 3 | Without gridlock seeds +3.8% (+1.9% to +5.7%) ⚠ | `outputs/final/sumo/seeds40_summary.csv` | all three: sec_mean 0.03829, sec_ci_lo 0.01917, sec_ci_hi 0.05740 (see note 1) |
| 3 | Rutledge +2.2% (+0.5% to +3.8%) | `outputs/final/sumo/seeds40_summary.csv` | Rutledge Avenue: mean 0.02151, ci_lo 0.00506, ci_hi 0.03816 |
| 3 | Static +0.26% for the AM; SUMO about 8 times larger | `outputs/final/sumo/seeds40_summary.csv` | Rutledge Avenue: static_am_mean 0.00263; 2.151 / 0.263 = 8.2 |
| 3 | 8 of 40 runs gridlock-affected | `outputs/final/sumo/seeds40_summary.csv` | Rutledge Avenue: gridlock_runs 8 |
| 3 | Without gridlock seeds +2.9% (+0.9% to +4.9%) ⚠ | `outputs/final/sumo/seeds40_summary.csv` | Rutledge Avenue: sec_mean 0.02872, sec_ci_lo 0.00933, sec_ci_hi 0.04923 (see note 1) |
| 3 | Coming -0.45% (-2.0% to +1.1%), 0 gridlock runs | `outputs/final/sumo/seeds40_summary.csv` | Coming Street: mean -0.00447, ci_lo -0.02039, ci_hi 0.01079, gridlock_runs 0 |
| 3 | Placebo -0.16% (-3.1% to +2.8%) | `outputs/final/sumo/seeds40_summary.csv` | today (other sim seed): mean -0.00165, ci_lo -0.03150, ci_hi 0.02833 |
| 3 | Where: +64 / +92 / +54 veh-h (all 40 seeds) | `outputs/final/sumo/seeds40_where.csv` | computed: mean of loss_street_h, loss_approaches_h, loss_elsewhere_h over the 40 "all three" rows = 64.3 / 91.8 / 54.2 (= RESULTS_4b.md "Street / approaches / elsewhere", all 40) |
| 3 | Where, 31 seeds without gridlock: +65 / +91 / +50 | `outputs/final/sumo/seeds40_where.csv`; `RESULTS_4b.md` | rows with gridlock_today and gridlock_variant both False (31); RESULTS_4b.md "all three, clean 31: +65 / +91 / +50" |
| 3 | About three quarters of the extra delay on the streets and their cross-street approaches | `outputs/final/sumo/seeds40_where.csv` | computed: (64.3 + 91.8) / (64.3 + 91.8 + 54.2) = 74% (all 40 seeds) |
| 3 | 65 junctions, 22 signals, programs rebuilt at all 22 | `outputs/final/sumo/RESULTS_4b.md` | "Junctions on the street 65, Signalized 22, Programs changed 22" |
| 3 | Rutledge: extra delay mostly elsewhere (I-26 entrants, internal trips) | `outputs/final/sumo/RESULTS_4b.md` | Rutledge Avenue, clean 32: elsewhere +104 of +92 total; i26 network +69, internal +113 |
| 4 | Early Ashley result -0.23% AM | `outputs/final/decompose_city.csv` | Ashley Calhoun-Crosstown, "old: K .09, split .60, no non-work", am: mean -0.00231 |
| 4 | Guessed 60/40 split | `src/chstraffic/config.py` | `AM_INBOUND_SPLIT = 0.60` (used when `PEAK_FACTOR_SOURCE = "guess"`) |
| 4 | Measured 51-56% inbound in the AM | `data/reference/peak_factors.csv` | am rows: inbound_split 0.507 to 0.558 |
| 4 | -0.23% to -0.09% to -0.03% (AM), PM +0.12%, AM+PM +0.05% | `outputs/final/decompose_city.csv` | Ashley Calhoun-Crosstown rows: -0.231%, -0.091%, -0.033% (am), +0.122% (pm), +0.046% (am+pm) |
| 4 | 5-seed SUMO noise about 3.5% | `outputs/final/sumo/SUMO_CHECK.md` | "How to read this": SD 3.5% |
| 5 | Screenlines 4/6 AM, 5/6 PM after; 5/6 and 4/6 before | `outputs/final/task2_screenlines/` | `final_am.csv`, `final_pm.csv`, `guess_nonwork0_am.csv`, `guess_nonwork0_pm.csv`: column passes |
| 5 | Line A 31-37% short | `outputs/final/task2_screenlines/final_{am,pm}.csv` | A: deviation -0.37 (AM), -0.31 (PM) |
| 5 | Line B 59% over in the AM | `outputs/final/task2_screenlines/final_am.csv` | B: deviation +0.59 |
| 5 | 17-22% of held-out stations GEH < 5; target 85% | `04_calibrate.py --peak both` output, 2026-11-12 (Task 2, finding D5) | test half: AM 22%, PM 17% |
| 5 | Spring/Cannon: total travel time -0.16% | `outputs/final/backtest_tstt.csv` | bonus 1.1, demand 1.0, am+pm: mean -0.00156 |
| 5 | Spring +37% modeled vs -7% to -25% counted | `outputs/final/backtest_volume_change.csv` | demand 1, spring: am_plus_pm_change +36.8%; observed 2016 to 2018 / 2019 / 2025: -7.5% / -25.4% / -16.4% |
| 5 | Cannon -13% modeled vs 0% to +7% counted | `outputs/final/backtest_volume_change.csv` | demand 1, cannon: -12.6%; observed +1.8% / +7.0% / 0.0% |
| 5 | What the 2017 project added | City of Charleston release 2017-09-20; Charleston City Paper 2017-09-21 | links in README section 5 |
| 6 | Static model at 1.02x free flow; 1.07-1.09x at x1.6 | `04_calibrate.py --peak both` congestion output, 2026-11-12 (Task 2, finding D6) | AM 1.019, PM 1.025; x1.6 AM 1.073, PM 1.089 |
| 6 | Programs rebuilt at 22 signals | `outputs/final/sumo/RESULTS_4b.md` | see above |
| 6 | PM needed demand x0.8 | `outputs/final/sumo/SUMO_CHECK.md` | first paragraph: "PM x0.8" |
| 6 | 3 of 40 baseline runs gridlock-affected | `outputs/final/sumo/seeds40_summary.csv` | today: gridlock_runs 3 |
| 6 | Effects of about 1.5% or more | `outputs/final/sumo/seeds40_summary.csv` | 95% interval half-widths: Coming 1.56, all three 1.54, Rutledge 1.66 points |
| 6 | One-way bonus checked at 0%, 10%, 20% | `outputs/final/city_question.csv` | bonus column 1.0 / 1.1 / 1.2 |
| 7 | Nothing published as of 2026-11-13; meeting 2025-09-04; parking 57 / 129 / 115 | City project page and meeting boards (links in README section 7) | checked 2026-11-13 |
| Reproduce | 1.5-3 hours | `scripts/run_final.cmd` | header comment |
| Reproduce | LODES 17.5 MB | `data/raw/README.md` | LODES row |
| Reproduce | SUMO runs about 4 hours on an 8-core laptop | `outputs/final/sumo/seeds40.csv` | started_utc + seconds of the 200 runs: 2026-11-12 22:27 UTC to 2026-11-13 02:39 UTC (platform win32) |

**Note 1 (⚠).** The two "without gridlock seeds" numbers are the secondary analysis exactly as
`seeds40_summary.csv` reports it. The pre-registered plan (`docs/task4b_plan.md`, "Reliability") says to drop
every seed where *any* variant or the placebo is gridlock-affected; the report script dropped the 10 seeds
of today, Coming, all three and the placebo but not Rutledge's own three extra gridlock seeds (4205, 4224,
4232). Dropping all 13 (27 seeds left; same bootstrap as the script): all three +3.6% (+1.6% to +5.6%),
Rutledge +2.1% (+0.3% to +3.8%). Both conclusions hold either way; the numbers in the README are the
frozen ones until the report is rerun.
