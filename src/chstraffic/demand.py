"""Peak-hour demand (AM or PM): gateway volumes and LODES zones -> origin-destination (OD) matrix.

* Gateway inbound vph = AADT x K x inbound split, outbound = AADT x K x (1 - split), per gateway and
  peak (config.PEAK, config.PEAK_FACTOR_SOURCE: measured in peak_factors.csv, or the old guesses)
* Part of each freeway gateway's volume is through traffic to another gateway
  (config.THROUGH_SHARE). It is routed explicitly so it loads the freeway links
  but is not spread over the street grid.
* The rest goes to interior destination zones with a production-constrained
  gravity model: T_ij = O_i * A_j f(c_ij) / sum_k A_k f(c_ik), f(c) = exp(-beta c).
* AM outbound (1 - split) leaves through each gateway, drawn from the zones by
  the same gravity form.
* Internal trips (zone to zone, both on the peninsula) follow the LODES commute
  pattern, scaled by config.INTERNAL_VEH_PER_COMMUTER.
* Internal non-work trips (config.NONWORK_INTERNAL_VPH): homes -> non-work activity by gravity.
* PM peak: the AM structure with production and attraction swapped (inbound trips go home to
  resident workers, outbound trips leave from jobs; internal trips reversed).

With config.ZONE_SOURCE = "lodes" a zone is a cluster of census blocks that loads
the network at 2-4 connector nodes (lodes.py). Inbound trips are attracted by
jobs held by people living off the peninsula, outbound trips are produced by
residents working off it. Gateway totals are fixed by the counts either way.

OD demand is the weakest link of the whole model (HANDOFF 7.3), hence
``scenarios()``, which perturbs every uncertain input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from . import config


def gateway_vph(aadt: float, k: float = config.K_FACTOR, split: float = config.AM_INBOUND_SPLIT) -> float:
    return aadt * k * split


def peak_factor(gateway: str, peak: str | None = None, ref_dir: Path | str | None = None) -> tuple[float, float]:
    """(K, inbound split) for one gateway in one peak. gateway "_interior" = interior count stations."""
    peak = peak or config.PEAK
    if peak not in ("am", "pm"):
        raise ValueError(f"peak must be 'am' or 'pm', not {peak!r}")
    guess = (config.K_FACTOR, config.AM_INBOUND_SPLIT if peak == "am" else 1 - config.AM_INBOUND_SPLIT)
    if config.PEAK_FACTOR_SOURCE == "guess":
        return guess
    if config.PEAK_FACTOR_SOURCE != "ccs":
        raise ValueError(f"unknown PEAK_FACTOR_SOURCE {config.PEAK_FACTOR_SOURCE!r}")
    from . import peaks
    ref_dir = Path(ref_dir) if ref_dir else Path(__file__).resolve().parents[2] / "data" / "reference"
    table = peaks.load_factors(ref_dir / "peak_factors.csv")
    if (gateway, peak) not in table:
        raise KeyError(f"no peak factor for {gateway!r} {peak}; rerun scripts/11_peak_factors.py")
    return table[(gateway, peak)]


@dataclass
class Zones:
    gateways: dict      # name -> (node, inbound vph)
    sinks: dict         # name -> node   (gateway_out rows, for through traffic)
    dests: dict         # name -> (node, attraction weight)
    snap_report: list   # rows describing each snap, for printing
    outbound: dict = None   # gateway name -> (exit node, outbound vph); None = inbound-only model
    # LODES zones only (None for hand-placed zones and the toy grid):
    origins: dict = None    # name -> (node, outbound production weight); None = use dests
    zone_of: dict = None    # dests/origins key -> zone id (one zone has several connector keys)
    connectors: dict = None  # zone id -> [(node, share), ...]
    internal: dict = None   # (origin zone, dest zone) -> LODES commuters, intrazonal dropped
    job_weight: dict = None  # zone id -> peak-hour weight of its jobs (config.HEALTH_JOB_WEIGHT), 1 = no change
    peak: str = "am"
    nonwork: dict = None    # (o zone, d zone) -> share of config.NONWORK_INTERNAL_VPH (sums to 1); None = none


def _road_nodes(D, road):
    if not isinstance(road, str) or not road:
        return set(D.nodes())
    import re
    rx = re.compile(road, re.I)
    return {n for u, v, d in D.edges(data=True) if rx.search(str(d.get("name"))) for n in (u, v)}


def _nearest(D, nodes, lat, lon, need_out=False, need_in=False):
    best, best_d = None, math.inf
    c = math.cos(math.radians(lat))
    for n in nodes:
        if need_out and D.out_degree(n) == 0:
            continue
        if need_in and D.in_degree(n) == 0:
            continue
        d = math.hypot((D.nodes[n]["y"] - lat) * 111_000, (D.nodes[n]["x"] - lon) * 111_000 * c)
        if d < best_d:
            best, best_d = n, d
    return best, best_d


def load_zones(D: nx.DiGraph, path: Path | str, peak: str | None = None) -> Zones:
    """Snap each row of zones.csv to the nearest graph node on a road matching ``snap_road``.

    peak = "am" or "pm" (default config.PEAK) sets K, the inbound split and the trip direction."""
    peak = peak or config.PEAK
    df = pd.read_csv(path, comment="#")
    gw, sinks, dests, rep, outbound = {}, {}, {}, [], {}
    for r in df.itertuples():
        if r.kind == "dest" and config.ZONE_SOURCE == "lodes":
            continue                                 # hand-placed zones are replaced by LODES zones
        cand = _road_nodes(D, r.snap_road)
        node, dist = _nearest(D, cand, r.lat, r.lon,
                              need_out=r.kind in ("gateway_in", "dest"),
                              need_in=r.kind in ("gateway_out", "dest"))
        if node is None:
            raise ValueError(f"zone {r.zone_id}: no node on road {r.snap_road!r}")
        rep.append(dict(zone=r.zone_id, kind=r.kind, road=r.snap_road, node=node, snap_m=round(dist)))
        if r.kind == "gateway_in":
            k, split = peak_factor(r.zone_id, peak, Path(path).parent)
            gw[r.zone_id] = (node, gateway_vph(float(r.aadt), k, split))
            out_name = f"{r.zone_id}_out"
            if out_name in set(df.zone_id):          # freeway: separate sink row
                exit_node = None
            else:                                    # arterial: leave where it enters
                exit_node, _ = _nearest(D, cand, r.lat, r.lon, need_in=True)
            outbound[r.zone_id] = (exit_node, out_name, gateway_vph(float(r.aadt), k, 1 - split))
        elif r.kind == "gateway_out":
            sinks[r.zone_id] = node
        else:
            dests[r.zone_id] = (node, float(r.attraction))
    out = {g: ((node if node is not None else sinks[name]), q) for g, (node, name, q) in outbound.items()
           if node is not None or name in sinks}
    zones = Zones(gw, sinks, dests, rep, out if config.INCLUDE_OUTBOUND else None, peak=peak)
    if config.ZONE_SOURCE == "lodes":
        _load_lodes_zones(D, Path(path).parent, zones)
    elif config.NONWORK_INTERNAL_VPH > 0:
        raise ValueError("NONWORK_INTERNAL_VPH needs LODES zones (config.ZONE_SOURCE = 'lodes')")
    return zones


def _load_lodes_zones(D, ref_dir: Path, zones: Zones) -> None:
    """Fill dests / origins / connectors / internal from the tables written by 06_build_zones.py."""
    files = [ref_dir / n for n in ("zones_lodes.csv", "zone_connectors.csv", "internal_od.csv")]
    if not all(f.exists() for f in files):
        raise FileNotFoundError("LODES zone tables missing; run scripts/06_build_zones.py "
                                "(or set config.ZONE_SOURCE = 'hand')")
    z, con, internal = (pd.read_csv(f, comment="#") for f in files)
    missing = set(con.node) - set(D.nodes())
    if missing:
        raise ValueError(f"{len(missing)} connector nodes are not in the graph; rerun scripts/06_build_zones.py")
    zrow = z.set_index("zone")
    zones.origins, zones.zone_of, zones.connectors = {}, {}, {}
    health = zrow.jobs_health / zrow.jobs.clip(lower=1) if "jobs_health" in zrow else zrow.jobs * 0.0
    zones.job_weight = {zone: 1.0 - (1.0 - config.HEALTH_JOB_WEIGHT) * float(h) for zone, h in health.items()}
    retail = zrow.jobs_retail_food if "jobs_retail_food" in zrow else zrow.jobs * 0.0
    nonwork = config.NONWORK_RETAIL_FOOD_WEIGHT * retail + config.NONWORK_RESIDENT_WEIGHT * zrow.workers
    for zone, grp in con.groupby("zone"):
        tot = float(grp.share.sum())             # shares are stored rounded; make them sum to 1
        zones.connectors[zone] = [(int(n), float(s) / tot) for n, s in zip(grp.node, grp.share)]
        jobs = float(zrow.jobs_external[zone]) * zones.job_weight[zone]   # where commuters from off the peninsula work
        homes = float(zrow.workers_external[zone])                        # where residents working off it live
        attract, produce = (jobs, homes) if zones.peak == "am" else (homes, jobs)
        for i, (node, share) in enumerate(zones.connectors[zone]):
            key = f"{zone}#{i}"
            zones.zone_of[key] = zone
            extra = float(nonwork[zone])
            zones.dests[key] = (node, (attract + extra) * share)
            zones.origins[key] = (node, (produce + extra) * share)
    pairs = ((o, d, float(q)) for o, d, q in internal.itertuples(index=False) if o != d)
    zones.internal = {((o, d) if zones.peak == "am" else (d, o)): q for o, d, q in pairs}
    if config.NONWORK_INTERNAL_VPH > 0:
        zones.nonwork = _nonwork_pattern(D, zones, zrow.workers, nonwork)


def _nonwork_pattern(D, zones: Zones, homes: pd.Series, activity: pd.Series,
                     beta: float = config.GRAVITY_BETA) -> dict:
    """Shares of the internal non-work volume by zone pair: homes x activity x exp(-beta x free-flow minutes),
    intrazonal pairs dropped, normalized to 1. AM = home -> activity; PM = the reverse."""
    if float(activity.sum()) <= 0:
        raise ValueError("NONWORK_INTERNAL_VPH > 0 needs a non-work weight > 0 "
                         "(NONWORK_RETAIL_FOOD_WEIGHT or NONWORK_RESIDENT_WEIGHT)")
    rep = {z: max(c, key=lambda x: x[1])[0] for z, c in zones.connectors.items()}   # heaviest connector node
    w = {}
    for o, on in rep.items():
        if homes.get(o, 0) <= 0:
            continue
        dist = nx.single_source_dijkstra_path_length(D, on, weight="fftt_s")
        for d, dn in rep.items():
            if d != o and activity.get(d, 0) > 0 and dn in dist:
                w[(o, d)] = float(homes[o]) * float(activity[d]) * math.exp(-beta * dist[dn] / 60.0)
    tot = sum(w.values())
    return {((o, d) if zones.peak == "am" else (d, o)): q / tot for (o, d), q in w.items()}


def ff_minutes(D, origins, dests) -> dict:
    out = {}
    for o in origins:
        dist = nx.single_source_dijkstra_path_length(D, o, weight="fftt_s")
        for d in dests:
            out[(o, d)] = dist.get(d, math.inf) / 60.0
    return out


def gravity_od(origins: dict, dests: dict, cost_min: dict, beta: float = config.GRAVITY_BETA) -> dict:
    """origins {node: vph}, dests {node: weight}, cost_min {(o, d): minutes}.

    Production-constrained: every origin's total is preserved exactly (unless no
    destination is reachable from it).
    """
    od = {}
    for o, prod in origins.items():
        w = {d: a * math.exp(-beta * cost_min[(o, d)]) for d, a in dests.items()
             if d != o and a > 0 and math.isfinite(cost_min.get((o, d), math.inf))}
        tot = sum(w.values())
        if tot <= 0:
            continue
        for d, wd in w.items():
            od[(o, d)] = od.get((o, d), 0.0) + prod * wd / tot
    return od


def build_od(D, zones: Zones, gateway_scale: dict | None = None, attraction_scale: dict | None = None,
             beta: float = config.GRAVITY_BETA, through_share: dict | None = None,
             cost_min: dict | None = None, production_scale: dict | None = None,
             internal_scale: float = 1.0, cost_out: dict | None = None) -> dict:
    """One OD matrix {(origin node, dest node): vph}.

    attraction_scale / production_scale are keyed by zone id (hand-placed zones:
    the zone name). cost_min / cost_out are optional precomputed free-flow minutes
    (gateway -> dest node, origin node -> exit node).
    """
    gateway_scale = gateway_scale or {}
    attraction_scale = attraction_scale or {}
    production_scale = attraction_scale if production_scale is None else production_scale
    zone_of = zones.zone_of or {}
    through_share = config.THROUGH_SHARE if through_share is None else through_share
    od: dict = {}
    grid_prod: dict = {}
    thru = through_flows(zones, gateway_scale, through_share)
    for g, (node, vph) in zones.gateways.items():
        vph = vph * gateway_scale.get(g, 1.0)
        for (a, sink_name), q in thru.items():
            if a == g:
                key = (node, zones.sinks[sink_name])
                od[key] = od.get(key, 0.0) + q
                vph -= q
        grid_prod[node] = grid_prod.get(node, 0.0) + vph
    dest_w: dict = {}
    for z, (node, a) in zones.dests.items():
        dest_w[node] = dest_w.get(node, 0.0) + a * attraction_scale.get(zone_of.get(z, z), 1.0)
    cost_min = cost_min or ff_minutes(D, list(grid_prod), list(dest_w))
    for k, q in gravity_od(grid_prod, dest_w, cost_min, beta).items():
        od[k] = od.get(k, 0.0) + q
    if zones.outbound:
        if zones.origins is None:
            orig_w = dest_w
        else:
            orig_w = {}
            for z, (node, p) in zones.origins.items():
                orig_w[node] = orig_w.get(node, 0.0) + p * production_scale.get(zone_of.get(z, z), 1.0)
        _add_outbound(D, zones, od, gateway_scale, orig_w, beta, thru, cost_out)
    if zones.internal:
        _add_internal(zones, od, attraction_scale, internal_scale)
    if zones.nonwork:
        _spread(zones, od, {k: s * config.NONWORK_INTERNAL_VPH * internal_scale for k, s in zones.nonwork.items()})
    if config.DEMAND_SCALE != 1.0:                       # demand-level sensitivity: everything, gateways included
        od = {k: q * config.DEMAND_SCALE for k, q in od.items()}
    return od


def through_flows(zones: Zones, gateway_scale: dict, through_share: dict) -> dict:
    """Gateway-to-gateway through traffic {(entry gateway, sink name): vph}.

    A through trip is counted once at each end: it is part of the entry gateway's
    inbound count AND of the exit gateway's outbound count. So when outbound
    demand is modeled, the through flows into one exit are scaled down together
    if they would exceed config.THROUGH_MAX_SHARE_OF_EXIT of that exit's outbound
    volume. (Before 2026-11-09 they were added on top of it, and mirrored, which
    overloaded the freeway gateways by 26-100%.)
    """
    flows = {}
    for g, (_, vph) in zones.gateways.items():
        for sink_name, share in through_share.get(g, {}).items():
            if sink_name in zones.sinks:
                flows[(g, sink_name)] = vph * gateway_scale.get(g, 1.0) * min(share * config.THROUGH_SCALE, 1.0)
    for g, (_, vph) in zones.gateways.items():       # shares of one gateway may not add up to more than 1
        mine = [k for k in flows if k[0] == g]
        tot, cap = sum(flows[k] for k in mine), vph * gateway_scale.get(g, 1.0)
        if tot > cap > 0:
            for k in mine:
                flows[k] *= cap / tot
    if zones.outbound:
        for g, (_, out_vph) in zones.outbound.items():
            into = [k for k in flows if k[1] == f"{g}_out"]
            tot = sum(flows[k] for k in into)
            cap = config.THROUGH_MAX_SHARE_OF_EXIT * out_vph * gateway_scale.get(g, 1.0)
            if tot > cap > 0:
                for k in into:
                    flows[k] *= cap / tot
    return flows


def internal_vph(zones: Zones, attraction_scale: dict | None = None, internal_scale: float = 1.0) -> dict:
    """Zone-to-zone internal vehicle trips {(o zone, d zone): vph}.

    LODES commuters x config.INTERNAL_VEH_PER_COMMUTER x internal_scale. A zone's
    attraction_scale shifts trips toward or away from it; the total is then put
    back, so internal_scale alone sets the volume.
    """
    attraction_scale = attraction_scale or {}
    jw = zones.job_weight or {}
    work = 1 if zones.peak == "am" else 0        # which end of the pair is the job (PM pairs run work -> home)
    raw = {k: q * attraction_scale.get(k[1], 1.0) * jw.get(k[work], 1.0) for k, q in zones.internal.items()}
    base, tot = sum(zones.internal.values()), sum(raw.values())
    f = config.INTERNAL_VEH_PER_COMMUTER * internal_scale * (base / tot if tot > 0 else 0.0)
    return {k: q * f for k, q in raw.items()}


def _add_internal(zones, od, attraction_scale, internal_scale):
    _spread(zones, od, internal_vph(zones, attraction_scale, internal_scale))


def _spread(zones, od, zone_pairs):
    """Add zone-to-zone vph to `od`, split over the connector nodes of both zones."""
    for (oz, dz), q in zone_pairs.items():
        for on, os_ in zones.connectors[oz]:
            for dn, ds in zones.connectors[dz]:
                if on != dn:
                    od[(on, dn)] = od.get((on, dn), 0.0) + q * os_ * ds


def exit_minutes(D, zones: Zones) -> dict:
    """Free-flow minutes from every node to each outbound exit node: {(exit, node): min}."""
    R = D.reverse(copy=False)
    cost = {}
    for exit_node in {x for x, _ in zones.outbound.values()}:
        for n, t in nx.single_source_dijkstra_path_length(R, exit_node, weight="fftt_s").items():
            cost[(exit_node, n)] = t / 60.0
    return cost


def _add_outbound(D, zones, od, gateway_scale, dest_w, beta, thru, cost=None):
    """Outbound: each gateway's (1 - inbound split) share of the peak hour leaves
    through that gateway. Through traffic arriving from other gateways (``thru``,
    already in ``od``) is part of that volume; the rest comes from the zones by
    gravity, weighted by ``dest_w`` (LODES zones: residents working off the
    peninsula in the AM, jobs in the PM; hand-placed zones: the attraction weight)."""
    exit_prod: dict = {}
    for g, (exit_node, vph) in zones.outbound.items():
        vph = vph * gateway_scale.get(g, 1.0)
        arriving = sum(q for (_, sink_name), q in thru.items() if sink_name == f"{g}_out")
        exit_prod[exit_node] = exit_prod.get(exit_node, 0.0) + max(vph - arriving, 0.0)
    cost = cost or exit_minutes(D, zones)
    # gravity from the exit's point of view: which zones do its trips start from
    for (x, d), q in gravity_od(exit_prod, dest_w, cost, beta).items():
        od[(d, x)] = od.get((d, x), 0.0) + q


def scenarios(D, zones: Zones, n: int = config.N_SCENARIOS, seed: int = config.SCENARIO_SEED) -> list[dict]:
    """n perturbed OD matrices (gateway volumes, zone attractions and productions,
    distance decay, internal-trip volume)."""
    rng = np.random.default_rng(seed)
    grid_origins = [node for node, _ in zones.gateways.values()]
    cost_min = ff_minutes(D, grid_origins, [node for node, _ in zones.dests.values()])
    cost_out = exit_minutes(D, zones) if zones.outbound else None
    zone_ids = sorted(set(zones.zone_of.values())) if zones.zone_of else list(zones.dests)
    out = []
    lo_b, hi_b = config.SCENARIO_BETA_RANGE
    lo_i, hi_i = config.SCENARIO_INTERNAL_RANGE
    sig = config.SCENARIO_ATTRACTION_SIGMA
    for _ in range(n):
        s = config.SCENARIO_GATEWAY_SPREAD
        gscale = {g: float(rng.uniform(1 - s, 1 + s)) for g in zones.gateways}
        ascale = {z: float(rng.lognormal(0.0, sig)) for z in zone_ids}
        beta = float(rng.uniform(lo_b, hi_b))
        pscale, iscale = None, 1.0
        if zones.origins is not None:      # extra draws only for LODES zones
            pscale = {z: float(rng.lognormal(0.0, sig)) for z in zone_ids}
            iscale = float(rng.uniform(lo_i, hi_i))
        out.append(build_od(D, zones, gscale, ascale, beta, cost_min=cost_min,
                            production_scale=pscale, internal_scale=iscale, cost_out=cost_out))
    return out
