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

# Peak-hour factor: share of daily (AADT) traffic in the modeled peak hour.
# Used only when PEAK_FACTOR_SOURCE = "guess" (and as the fallback for a gateway missing from
# peak_factors.csv). GUESS: "K ~0.08-0.10 is typical for urban roads". The measured values are lower
# (0.065-0.085 at the AM hour, see PEAK_FACTOR_SOURCE).
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

# Coarse decision set for the search (feasibility.search_corridors): 46 corridors on the real graph
# instead of 482. A corridor is a decision only if most of its length is one of SEARCH_CLASSES, it is
# at least SEARCH_MIN_LENGTH_M long, and it is split only where it crosses a SEARCH_SPLIT_HIGHWAYS street.
# Residential streets (St. Philip included) keep today's direction.
SEARCH_CLASSES = {"primary", "secondary", "tertiary"}
SEARCH_SPLIT_HIGHWAYS = {"motorway", "trunk", "primary"}
SEARCH_MIN_LENGTH_M = 300.0
# Two-stage evaluation (scripts/09_search.py): every candidate on a few scenarios at a loose gap,
# then the best few on all scenarios at UE_GAP_SEARCH. The screening threshold is deliberately
# easier than MIN_MEAN_IMPROVEMENT so a real improvement is not lost to screening noise.
SEARCH_SCREEN_SCENARIOS = 3
SEARCH_SCREEN_GAP = 1e-3
SEARCH_SCREEN_MIN_IMPROVEMENT = 0.0005
SEARCH_CONFIRM_TOP = 4

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

# Share of the peak hour's two-way gateway volume that is inbound in the AM. GUESS (0.55-0.65 typical),
# used only when PEAK_FACTOR_SOURCE = "guess". In the PM the guess is reversed: 1 - AM_INBOUND_SPLIT.
AM_INBOUND_SPLIT = 0.60

# Which peak hour demand.py builds and calibrate.py compares against: "am" or "pm".
# AM: inbound gateway trips go to jobs, outbound trips come from residents (LODES home -> work).
# PM: the same with production and attraction swapped (work -> home), internal trips reversed.
PEAK = "am"
# Where K and the inbound split come from:
#   "ccs"   = data/reference/peak_factors.csv, measured per gateway and peak from SCDOT continuous-count
#             stations (scripts/11_peak_factors.py; Tue-Thu, Sep-Oct 2025). Gateways without a station
#             (meeting_n, jic, king_ext) and the interior count stations take the stations' AADT-weighted
#             mean: an ASSUMPTION, labeled in the file.
#   "guess" = K_FACTOR and AM_INBOUND_SPLIT above (the model before 2026-11-12).
PEAK_FACTOR_SOURCE = "ccs"
# Clock-hour windows (inclusive) searched for each peak's hour. The hour is the one with the highest summed
# weekday volume over all stations (one hour for the whole network). ASSUMPTION: windows by convention.
PEAK_WINDOWS = {"am": (6, 10), "pm": (14, 19)}

# Share of each freeway gateway's inbound volume that passes through to
# another gateway without entering the street grid. ASSUMPTION, no source yet.
# {origin gateway: {destination gateway_out: share}}
THROUGH_SHARE = {
    "ravenel":   {"i26_out": 0.35, "crosstown_out": 0.10, "jic_out": 0.05},
    "i26":       {"ravenel_out": 0.20, "crosstown_out": 0.15, "jic_out": 0.05},
    "crosstown": {"i26_out": 0.25, "ravenel_out": 0.10},
    "jic":       {"i26_out": 0.15, "ravenel_out": 0.10},
}
# One multiplier on every share above; the knob calibration turns (scripts/07_tune.py).
THROUGH_SCALE = 1.0

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
# Weight of a health-care job (LODES sector CNS16) as a peak-hour trip attractor, relative to
# any other job. Below 1 because hospitals work in shifts that start outside the peak hour and
# because LODES can report a health system's off-site staff at its main address. Three blocks
# around MUSC hold 26% of all peninsula jobs. A calibration knob (scripts/07_tune.py), no source.
HEALTH_JOB_WEIGHT = 1.0
# Non-work activity added to a zone's weight as a trip end, for gateway trips in both directions:
#   weight += NONWORK_RETAIL_FOOD_WEIGHT x (retail + accommodation/food jobs, LODES CNS07 + CNS18)
#           + NONWORK_RESIDENT_WEIGHT x (resident workers, a stand-in for population).
# 0 = commute-only weights. FITTED 2026-11-12 (Task 2, scripts/12_fit_demand.py, plan in docs/task2_fit_plan.md):
# one grid pass on screenline totals of the calibrate-half stations, AM + PM. Grid minimum R = 0, P = 1.0
# (P = 1.0 is the top of the grid, so the best P may be higher; not refined, by plan). Held-out loss 1.18 -> 0.55.
# No independent source: these are fitted values, not measurements.
NONWORK_RETAIL_FOOD_WEIGHT = 0.0
NONWORK_RESIDENT_WEIGHT = 1.0
# Peninsula-internal NON-WORK vehicle trips in the peak hour (both ends on the peninsula, not in LODES:
# errands, school runs, shopping, visits, deliveries). Produced at homes (resident workers, the LODES stand-in
# for population) and attracted by each zone's non-work weight above
#     A = NONWORK_RETAIL_FOOD_WEIGHT x retail/food jobs + NONWORK_RESIDENT_WEIGHT x resident workers,
# by gravity on free-flow minutes (GRAVITY_BETA); home -> activity in the AM, reversed in the PM. The same
# volume in both peaks (ASSUMPTION; PM non-work is usually higher). The overall scale of Task 2's
# three-parameter fit (with the two weights above); 0 = off. Scenarios vary it with SCENARIO_INTERNAL_RANGE.
# FITTED 2026-11-12 (same fit as above): 4,500 vph, an interior point of the grid {0, 1000, ..., 6000}.
# Sanity check, not a source: ~0.1-0.15 peak-hour vehicle trips per peninsula resident would give 3,500-5,000.
NONWORK_INTERNAL_VPH = 4500.0
SCENARIO_INTERNAL_RANGE = (0.5, 1.5)   # multiplier on internal demand, per scenario

# Demand-level sensitivity (Task 2 stop rule, used by Task 3). DEMAND_SCALE multiplies the WHOLE OD matrix,
# gateway trips included, so at anything but 1.0 the gateways no longer match their counts: it is a stress test
# of how results depend on congestion, not a calibrated state. Report every Task 3 result at each level.
DEMAND_SCALE = 1.0
SENSITIVITY_DEMAND_LEVELS = (1.0, 1.3, 1.6)

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

# ---------------------------------------------------------------------------
# Screenline validation (calibrate.screenline_table)
# ---------------------------------------------------------------------------
# FHWA "maximum desirable deviation in total screenline volumes" (Model Validation and
# Reasonableness Checking Manual, 1997, fig. 7-2; curve from NCHRP Report 255), read as
# (daily screenline volume, allowed error) points quoted in published MPO validation memos:
# Mendocino COG (20k 45%, 40k 35%, 60k 30%, 80k 28%, 200k+ 20%) and MACORTS (11.6k 60%).
# Not read off the original figure. Values between points are interpolated.
SCREENLINE_TOLERANCE = [(10_000, 0.60), (20_000, 0.45), (40_000, 0.35), (60_000, 0.30),
                        (80_000, 0.28), (200_000, 0.20)]

# ---------------------------------------------------------------------------
# SUMO cross-check (sumo.py, scripts/14_sumo_check.py). ASSUMPTIONS unless noted.
# ---------------------------------------------------------------------------
# netconvert: OSM import recommended by the SUMO docs (join junction clusters, signals from OSM tags,
# ramps and roundabouts guessed). Signal programs are netconvert's defaults, NOT Charleston's timings:
# only relative changes between variants are reported.
SUMO_NETCONVERT_OPTS = [
    "--junctions.join", "--tls.guess-signals", "--tls.discard-simple", "--tls.join",
    "--ramps.guess", "--roundabouts.guess", "--remove-edges.isolated",
    "--keep-edges.by-vclass", "passenger", "--output.original-names", "--osm.elevation", "false",
]
SUMO_OSM_NODE_TAGS = {"highway", "traffic_signals", "traffic_signals:direction"}   # node tags passed on
SUMO_OSM_NODE_HIGHWAY = {"traffic_signals", "stop", "give_way"}
SUMO_WARMUP_S = 900          # demand runs at the peak-hour rate from t=0; only trips due after this count
SUMO_PEAK_S = 3600           # the measured peak hour
SUMO_DRAIN_S = 3600          # extra time for the last vehicles to finish
SUMO_TELEPORT_S = 300        # SUMO default: a vehicle stuck this long is teleported (gridlock resolution)
SUMO_REROUTE_PERIOD_S = 120  # rerouting device: each vehicle re-plans on current travel times this often
SUMO_REROUTE_ADAPTATION_STEPS = 18   # SUMO default smoothing of edge travel times
SUMO_SIM_OPTS = ["--ignore-route-errors"]
SUMO_MESO_OPTS = ["--meso-junction-control"]   # junctions (signals, right of way) limit flow in meso
SUMO_SEEDS = 5
SUMO_SEED_BASE = 4100
# A run is "stable" (no gridlock) if teleports are below this share of loaded vehicles, every vehicle was
# inserted and none is left in the network at the end. If the baseline fails at demand x1.0, demand is
# lowered in these steps.
SUMO_STABLE_TELEPORT_SHARE = 0.005
SUMO_DEMAND_STEPS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
# Verdict per variant (fixed before the runs). SUMO effect "detectable" = same sign in >= 80% of seeds AND
# |mean| > max(0.1%, 2 x the SUMO noise floor: median |change| of the baseline re-run with another sim seed).
SUMO_MIN_SIGN_SHARE = 0.8
