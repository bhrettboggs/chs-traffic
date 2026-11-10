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

# Through trips into one exit gateway may take at most this share of that gateway's AM
# outbound volume; the rest must start on the peninsula. ASSUMPTION. It binds today:
# THROUGH_SHARE sends more traffic to I-26 than I-26's outbound count holds, so the two
# guesses (THROUGH_SHARE, AM_INBOUND_SPLIT) disagree with each other. Source both in P2.
THROUGH_MAX_SHARE_OF_EXIT = 0.80

# Load AM OUTBOUND trips too (gateway volume x (1 - AM_INBOUND_SPLIT)). The counts used
# for calibration are two-way, so an inbound-only model can't match them.
INCLUDE_OUTBOUND = True

# ---------------------------------------------------------------------------
# Zones from Census LEHD LODES (lodes.py, scripts/06_build_zones.py)
# ---------------------------------------------------------------------------
# "lodes": zones, connectors and internal commutes from data/reference/zones_lodes.csv,
# zone_connectors.csv and internal_od.csv. "hand": the 11 hand-placed dest rows in zones.csv.
ZONE_SOURCE = "lodes"
LODES_YEAR = 2024   # LODES 8.5, data vintage 20261014, JT00 (all jobs), S000 (all workers)
# 2020 census tracts (Charleston County, FIPS 45019) on the peninsula inside BBOX. Read off the
# LODES crosswalk 2026-11-09: every tract with a block within 250 m of a non-frozen graph node,
# minus tract 30 (west bank of the Ashley; its traffic enters through the crosstown gateway).
PENINSULA_TRACTS = ["45019000100", "45019000200", "45019000400", "45019000500", "45019000600",
                    "45019000700", "45019000900", "45019001000", "45019001100", "45019001500",
                    "45019004400", "45019005100", "45019005300", "45019005400", "45019005900"]
N_ZONES = 90                       # weighted k-means clusters of blocks (weight = jobs + workers)
ZONE_BLOCK_MAX_SNAP_M = 400.0      # blocks farther than this from a loadable node are dropped
CONNECTOR_NODES_PER_BLOCK = 3      # a block spreads over its 3 nearest loadable nodes (1/distance)
MAX_CONNECTORS_PER_ZONE = 4        # a zone keeps its heaviest nodes

# AM peak-hour VEHICLE trips per peninsula-internal LODES commuter (lives and works on the
# peninsula, different zones). ASSUMPTION, NO SOURCE. Rough build-up: 0.75 at work that day
# x 0.5 driving (short trips, high walk/bike share) x 0.3 of AM commutes in the peak hour
# = 0.11 commute trips, x ~2.2 to stand in for non-work internal trips (school runs,
# errands, deliveries), which LODES does not see and which here simply copy the commute
# pattern. Scenarios vary it by SCENARIO_INTERNAL_RANGE. Calibrate in P2.
INTERNAL_VEH_PER_COMMUTER = 0.25
SCENARIO_INTERNAL_RANGE = (0.5, 1.5)   # multiplier on internal demand, per scenario

# Gravity model deterrence f(c) = exp(-beta * c), c = free-flow minutes.
GRAVITY_BETA = 0.10

# Demand scenarios for robustness (demand.scenarios)
N_SCENARIOS = 20
SCENARIO_GATEWAY_SPREAD = 0.20     # each gateway volume x U(0.8, 1.2)
SCENARIO_ATTRACTION_SIGMA = 0.30   # each zone weight x lognormal(0, 0.3)
SCENARIO_BETA_RANGE = (0.05, 0.20)
SCENARIO_SEED = 2026

# ---------------------------------------------------------------------------
# Street widths (widths.py): City of Charleston pavement inventory, curb-to-curb
# ---------------------------------------------------------------------------
# Travel lanes a street can carry = floor((width - parking) / LANE_WIDTH_FT), keeping
# parking on one side (both sides if width >= BOTH_SIDE_PARKING_MIN_FT). ASSUMPTIONS.
LANE_WIDTH_FT = 10.0
PARKING_LANE_FT = 8.0
BOTH_SIDE_PARKING_MIN_FT = 36.0
# A city section matches a graph segment if it has the same street name and lies
# within this distance of the segment's quarter, middle and three-quarter points.
WIDTH_MATCH_MAX_M = 15.0
# Use width-derived lanes for segments with no OSM lanes tag? OFF: on the 608 segments where OSM
# does tag lanes, no width rule matched better than 62% (lane width x parking grid search,
# 2026-11-09). One-way 1-lane streets have median width 26 ft vs 29 ft for 2-lane ones; parking,
# which the inventory doesn't record, decides it. Width is kept as data, not as a lane count.
# Priority if ON: overrides.csv > explicit OSM lanes tag > city width > class default.
USE_WIDTH_LANES = False
