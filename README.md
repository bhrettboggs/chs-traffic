# chs-traffic

**Can downtown Charleston move more cars on the same pavement?**

This project models every drivable street on the Charleston peninsula as a weighted directed graph, simulates commuter traffic flowing onto the peninsula, and searches for one-way / two-way street configurations that cut total travel time. The physical roads don't change. Only the direction of travel and how each street's existing lanes are split between directions.

Created by **Bhrett Boggs**.

## Why this question
Charleston has spent 30 years converting peninsula one-way pairs back to two-way: Upper King St (1994), Spring & Cannon (2017), Line St. In 2025 the city commissioned a feasibility study for Coming St, Rutledge Ave and Ashley Ave. The studies look at a few corridors at a time. This project searches the entire network at once and puts a number on what each configuration costs or saves in vehicle-hours.

## Pipeline
```
01_fetch_osm.py     OpenStreetMap ──► data/raw/chs_peninsula_drive.graphml
02_build_graph.py   graphml ──► weighted DiGraph (length, speed, lanes, capacity, one-way flag)
10_oneway_check.py  OSM one-way directions vs Charleston County street centerlines; fixes go in overrides.csv
06_build_zones.py   Census LODES jobs and workers by block ──► 90 zones, connectors, internal commutes
11_peak_factors.py  SCDOT hourly continuous counts ──► peak-hour K and inbound split per gateway, AM and PM
04_calibrate.py     model flows vs 37 SCDOT count stations (GEH, screenlines), AM and/or PM peak
12_fit_demand.py    one fitting pass of non-work demand on half the stations, the other half held out
                    (plan written first: docs/task2_fit_plan.md); 07_tune.py is the older GEH grid
08_backtest_...py   Spring/Cannon before vs after the 2017 two-way conversion (plausibility check)
09_search.py        greedy search over 46 corridors, two-stage evaluation, resumable
demand              SCDOT AADT at the gateways + LODES zones ──► peak-hour origin-destination matrix
(next) assignment   Frank-Wolfe user equilibrium with BPR congestion ──► flow on every street
(next) optimize     search over one-way/two-way configurations ──► lower total system travel time
```

## Quickstart
```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
pytest                                               # offline tests
python scripts/01_fetch_osm.py                       # needs internet
python scripts/02_build_graph.py
```

## Data
* Street network: © OpenStreetMap contributors (ODbL)
* Jobs, workers and commute flows: U.S. Census Bureau, LEHD Origin-Destination Employment Statistics (LODES 8.5, 2024)
* Traffic counts: SCDOT 2025 Average Daily Traffic, Charleston County, and SCDOT continuous-count stations (hourly, via the SCDOT traffic data site) for peak-hour factors (see `data/raw/README.md`)
* One-way check and street widths: Charleston County GIS (Streets centerlines; City of Charleston pavement inventory)

## Status
Early stage. See `HANDOFF.md` for the build plan.

MIT License.
