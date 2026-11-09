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
(next) demand       SCDOT AADT at the gateways ──► peak-hour origin-destination matrix
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
* Traffic counts: SCDOT 2025 Average Daily Traffic, Charleston County (see `data/raw/README.md`)

## Status
Early stage. See `HANDOFF.md` for the build plan.

MIT License.
