"""Project-wide constants and modeling assumptions.

Every number in this file is an ASSUMPTION unless a source is cited next to it.
Change them here (not inside the modules) so experiments stay reproducible.
"""

# Study area: the Charleston peninsula, from the Battery north to just past
# Mount Pleasant St / the I-26 + US 17 interchange. (left, bottom, right, top)
# in WGS84 lon/lat, the order osmnx 2.x expects for graph_from_bbox.
BBOX = (-79.968, 32.765, -79.912, 32.826)

# OSM highway classes treated as drivable for this project. "service" is
# excluded on purpose (parking aisles and alleys add thousands of edges and
# almost no through traffic). Add it back if you need garage access.
DRIVABLE_HIGHWAYS = [
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "residential", "unclassified", "living_street",
]
OVERPASS_FILTER = '["highway"~"^(' + "|".join(DRIVABLE_HIGHWAYS) + ')$"]["access"!~"private|no"]'

# Overpass servers tried in order by scripts/01_fetch_osm.py. The main server
# often answers 502 "at capacity"; the others are public mirrors.
OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.private.coffee/api",
    "https://overpass.kumi.systems/api",
]
OVERPASS_RETRIES = 3          # attempts per server
OVERPASS_BACKOFF_S = 30       # first wait; doubles after each failure

# Default free-flow speeds (km/h) by class when OSM has no maxspeed tag.
# Downtown Charleston posted speeds are mostly 25 mph (~40 km/h).
DEFAULT_SPEED_KPH = {
    "motorway": 89, "motorway_link": 56, "trunk": 72, "trunk_link": 48,
    "primary": 48, "primary_link": 40, "secondary": 48, "secondary_link": 40,
    "tertiary": 40, "tertiary_link": 32, "residential": 40,
    "unclassified": 40, "living_street": 16,
}

# Default lanes PER DIRECTION when OSM has no lanes tag.
DEFAULT_LANES_PER_DIR = {
    "motorway": 2, "motorway_link": 1, "trunk": 2, "trunk_link": 1,
    "primary": 1, "primary_link": 1, "secondary": 1, "secondary_link": 1,
    "tertiary": 1, "tertiary_link": 1, "residential": 1,
    "unclassified": 1, "living_street": 1,
}

# Practical capacity, vehicles/hour/lane. Rough planning-level values in the
# spirit of the Highway Capacity Manual: freeways ~1,900-2,200; signalized
# urban streets are governed by green time, ~600-900 effective. CALIBRATE.
CAPACITY_VPHPL = {
    "motorway": 2000, "motorway_link": 1500, "trunk": 1600, "trunk_link": 1200,
    "primary": 900, "primary_link": 800, "secondary": 800, "secondary_link": 700,
    "tertiary": 700, "tertiary_link": 600, "residential": 500,
    "unclassified": 500, "living_street": 200,
}

# BPR link performance function: t = t0 * (1 + ALPHA * (v/c) ** BETA)
# 0.15 / 4 are the classic 1964 Bureau of Public Roads values.
BPR_ALPHA = 0.15
BPR_BETA = 4.0

# Converting a two-way street to one-way usually raises effective capacity per
# lane (no opposing left turns, simpler signal phasing). Drezner-style models
# use a speed factor; we use a capacity multiplier. ASSUMPTION — sensitivity-test it.
ONEWAY_CAPACITY_BONUS = 1.10

# Peak-hour factor: share of daily (AADT) traffic in the design peak hour.
# "K-factor" ~0.08-0.10 is typical for urban roads. ASSUMPTION.
K_FACTOR = 0.09

# ---------------------------------------------------------------------------
# Configuration search (feasibility.py / robust.py)
# ---------------------------------------------------------------------------

# Road classes whose direction is never changed (freeways, ramps, bridges, US 17).
FROZEN_HIGHWAYS = {"motorway", "motorway_link", "trunk", "trunk_link"}

# Two one-way segments with the same name, opposite directions, and both ends
# within this distance of each other are treated as one divided road (frozen).
DIVIDED_MAX_SEP_M = 60.0

# A corridor (one same-named street) is split into separate decisions where it
# crosses a street of one of these classes.
MAJOR_HIGHWAYS = {"motorway", "trunk", "primary", "secondary"}

# Tier-1 screen: mean free-flow O-D time may grow by at most this factor.
SCREEN_MAX_DETOUR = 1.25

# Tier-2 acceptance rule (robust.py). See HANDOFF 3b for why.
UE_GAP_SEARCH = 1e-4          # relative gap for every assignment in the search
UE_MAX_ITER = 500
MIN_MEAN_IMPROVEMENT = 0.001  # 0.1% of TSTT; smaller gains are solver noise
MIN_WIN_RATE = 0.80           # must beat the incumbent in >= 80% of scenarios

# ---------------------------------------------------------------------------
# Demand (demand.py)
# ---------------------------------------------------------------------------

# Share of the peak hour's two-way gateway volume that is inbound in the AM.
# ASSUMPTION (0.55-0.65 typical); check against SCDOT hourly count stations.
AM_INBOUND_SPLIT = 0.60

# Share of each freeway gateway's inbound volume that passes through to
# another gateway without entering the street grid. ASSUMPTION, no source yet.
# {origin gateway: {destination gateway_out: share}}
THROUGH_SHARE = {
    "ravenel":   {"i26_out": 0.35, "crosstown_out": 0.10},
    "i26":       {"ravenel_out": 0.20, "crosstown_out": 0.15},
    "crosstown": {"i26_out": 0.25, "ravenel_out": 0.10},
}

# Load AM OUTBOUND trips too (gateway volume x (1 - AM_INBOUND_SPLIT)). The counts used
# for calibration are two-way, so an inbound-only model can't match them.
INCLUDE_OUTBOUND = True

# Gravity model deterrence f(c) = exp(-beta * c), c = free-flow minutes.
GRAVITY_BETA = 0.10

# Demand scenarios for robustness (demand.scenarios)
N_SCENARIOS = 20
SCENARIO_GATEWAY_SPREAD = 0.20     # each gateway volume x U(0.8, 1.2)
SCENARIO_ATTRACTION_SIGMA = 0.30   # each zone weight x lognormal(0, 0.3)
SCENARIO_BETA_RANGE = (0.05, 0.20)
SCENARIO_SEED = 2026
