"""AM-peak inbound demand: gateway volumes -> origin-destination (OD) matrix.

* Gateway inbound vph = AADT x K-factor x AM inbound split  (all in config)
* Part of each freeway gateway's volume is through traffic to another gateway
  (config.THROUGH_SHARE). It is routed explicitly so it loads the freeway links
  but is not spread over the street grid.
* The rest goes to interior destination zones with a production-constrained
  gravity model: T_ij = O_i * A_j f(c_ij) / sum_k A_k f(c_ik), f(c) = exp(-beta c).

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


@dataclass
class Zones:
    gateways: dict      # name -> (node, inbound vph)
    sinks: dict         # name -> node   (gateway_out rows, for through traffic)
    dests: dict         # name -> (node, attraction weight)
    snap_report: list   # rows describing each snap, for printing


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


def load_zones(D: nx.DiGraph, path: Path | str) -> Zones:
    """Snap each row of zones.csv to the nearest graph node on a road matching ``snap_road``."""
    df = pd.read_csv(path, comment="#")
    gw, sinks, dests, rep = {}, {}, {}, []
    for r in df.itertuples():
        cand = _road_nodes(D, r.snap_road)
        node, dist = _nearest(D, cand, r.lat, r.lon,
                              need_out=r.kind in ("gateway_in", "dest"),
                              need_in=r.kind in ("gateway_out", "dest"))
        if node is None:
            raise ValueError(f"zone {r.zone_id}: no node on road {r.snap_road!r}")
        rep.append(dict(zone=r.zone_id, kind=r.kind, road=r.snap_road, node=node, snap_m=round(dist)))
        if r.kind == "gateway_in":
            gw[r.zone_id] = (node, gateway_vph(float(r.aadt)))
        elif r.kind == "gateway_out":
            sinks[r.zone_id] = node
        else:
            dests[r.zone_id] = (node, float(r.attraction))
    return Zones(gw, sinks, dests, rep)


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
             if d != o and math.isfinite(cost_min.get((o, d), math.inf))}
        tot = sum(w.values())
        if tot <= 0:
            continue
        for d, wd in w.items():
            od[(o, d)] = od.get((o, d), 0.0) + prod * wd / tot
    return od


def build_od(D, zones: Zones, gateway_scale: dict | None = None, attraction_scale: dict | None = None,
             beta: float = config.GRAVITY_BETA, through_share: dict | None = None,
             cost_min: dict | None = None) -> dict:
    gateway_scale = gateway_scale or {}
    attraction_scale = attraction_scale or {}
    through_share = config.THROUGH_SHARE if through_share is None else through_share
    od: dict = {}
    grid_prod: dict = {}
    for g, (node, vph) in zones.gateways.items():
        vph = vph * gateway_scale.get(g, 1.0)
        thru = through_share.get(g, {})
        for sink_name, share in thru.items():
            if sink_name in zones.sinks:
                key = (node, zones.sinks[sink_name])
                od[key] = od.get(key, 0.0) + vph * share
        grid_prod[node] = grid_prod.get(node, 0.0) + vph * (1 - sum(
            s for k, s in thru.items() if k in zones.sinks))
    dest_w: dict = {}
    for z, (node, a) in zones.dests.items():
        dest_w[node] = dest_w.get(node, 0.0) + a * attraction_scale.get(z, 1.0)
    cost_min = cost_min or ff_minutes(D, list(grid_prod), list(dest_w))
    for k, q in gravity_od(grid_prod, dest_w, cost_min, beta).items():
        od[k] = od.get(k, 0.0) + q
    return od


def scenarios(D, zones: Zones, n: int = config.N_SCENARIOS, seed: int = config.SCENARIO_SEED) -> list[dict]:
    """n perturbed OD matrices (gateway volumes, zone attractions, distance decay)."""
    rng = np.random.default_rng(seed)
    grid_origins = [node for node, _ in zones.gateways.values()]
    cost_min = ff_minutes(D, grid_origins, [node for node, _ in zones.dests.values()])
    out = []
    lo_b, hi_b = config.SCENARIO_BETA_RANGE
    for _ in range(n):
        s = config.SCENARIO_GATEWAY_SPREAD
        gscale = {g: float(rng.uniform(1 - s, 1 + s)) for g in zones.gateways}
        ascale = {z: float(rng.lognormal(0.0, config.SCENARIO_ATTRACTION_SIGMA)) for z in zones.dests}
        beta = float(rng.uniform(lo_b, hi_b))
        out.append(build_od(D, zones, gscale, ascale, beta, cost_min=cost_min))
    return out
