"""Zones and commute flows from Census LEHD LODES (block-level jobs and workers).

Inputs (data/raw/lodes/, see data/raw/README.md for URLs and checksums):
  * WAC  jobs by workplace block          sc_wac_S000_JT00_<year>.csv.gz
  * RAC  workers by home block            sc_rac_S000_JT00_<year>.csv.gz
  * OD   home block -> work block jobs    sc_od_main_JT00_<year>.csv.gz (+ aux = out-of-state homes)
  * geography crosswalk (block lat/lon)   sc_xwalk.csv.gz

``build`` turns them into three small tables (written to data/reference/ by
scripts/06_build_zones.py):
  * zones       one row per zone: centroid, jobs, workers, and the split of each
                into peninsula-internal and external (crosses a gateway)
  * connectors  2-4 graph nodes per zone with a share each, so a zone loads the
                network at several points instead of one
  * internal    zone -> zone commuters who both live and work on the peninsula

LODES caveats that matter here: jobs are placed at the employer's reporting
address (a headquarters can hold jobs done elsewhere), block-level OD pairs carry
synthetic noise (zone sums are safer), students and visitors are not counted.
"""

from __future__ import annotations

import math
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from . import config

M_PER_DEG = 111_000.0


def _xy(lat, lon):
    c = math.cos(math.radians((config.BBOX[1] + config.BBOX[3]) / 2))
    return np.c_[np.asarray(lon, float) * M_PER_DEG * c, np.asarray(lat, float) * M_PER_DEG]


def eligible_nodes(D: nx.DiGraph) -> list:
    """Nodes a zone may load at: in the largest SCC, with a non-frozen edge in and out."""
    core = max(nx.strongly_connected_components(D), key=len)
    free = lambda d: d["highway"] not in config.FROZEN_HIGHWAYS  # noqa: E731
    return sorted(n for n in core
                  if any(free(d) for _, _, d in D.out_edges(n, data=True))
                  and any(free(d) for _, _, d in D.in_edges(n, data=True)))


def load_blocks(lodes_dir: Path | str, D: nx.DiGraph, year: int = config.LODES_YEAR) -> pd.DataFrame:
    """Peninsula blocks with jobs, workers and distance to the nearest eligible node."""
    L = Path(lodes_dir)
    xw = pd.read_csv(L / "sc_xwalk.csv.gz", dtype=str,
                     usecols=["tabblk2020", "trct", "blklatdd", "blklondd"])
    xw = xw[xw.trct.isin(config.PENINSULA_TRACTS)].copy()
    xw["lat"], xw["lon"] = xw.blklatdd.astype(float), xw.blklondd.astype(float)
    left, bottom, right, top = config.BBOX
    xw = xw[(xw.lon > left) & (xw.lon < right) & (xw.lat > bottom) & (xw.lat < top)]
    wac = pd.read_csv(L / f"sc_wac_S000_JT00_{year}.csv.gz", dtype={"w_geocode": str}, usecols=["w_geocode", "C000"])
    rac = pd.read_csv(L / f"sc_rac_S000_JT00_{year}.csv.gz", dtype={"h_geocode": str}, usecols=["h_geocode", "C000"])
    b = (xw[["tabblk2020", "trct", "lat", "lon"]].rename(columns={"tabblk2020": "block"})
         .merge(wac.rename(columns={"w_geocode": "block", "C000": "jobs"}), how="left")
         .merge(rac.rename(columns={"h_geocode": "block", "C000": "workers"}), how="left")
         .fillna({"jobs": 0, "workers": 0}))
    nodes = eligible_nodes(D)
    tree = cKDTree(_xy([D.nodes[n]["y"] for n in nodes], [D.nodes[n]["x"] for n in nodes]))
    b["snap_m"] = tree.query(_xy(b.lat, b.lon))[0]
    b = b[b.snap_m <= config.ZONE_BLOCK_MAX_SNAP_M]
    return b.sort_values("block").reset_index(drop=True)


def cluster(xy: np.ndarray, w: np.ndarray, k: int, seed: int = config.SCENARIO_SEED, iters: int = 100) -> np.ndarray:
    """Weighted k-means (k-means++ start, Lloyd iterations). Returns a label per point."""
    rng = np.random.default_rng(seed)
    centers = [xy[rng.choice(len(xy), p=w / w.sum())]]
    for _ in range(k - 1):
        d2 = np.min([((xy - c) ** 2).sum(1) for c in centers], axis=0) * w
        centers.append(xy[rng.choice(len(xy), p=d2 / d2.sum())])
    C = np.array(centers)
    lab = np.zeros(len(xy), int)
    for it in range(iters):
        new = ((xy[:, None, :] - C[None, :, :]) ** 2).sum(2).argmin(1)
        if it and np.array_equal(new, lab):
            break
        lab = new
        for j in range(k):
            m = lab == j
            if m.any():
                C[j] = np.average(xy[m], axis=0, weights=w[m])
    return lab


def build(D: nx.DiGraph, lodes_dir: Path | str, year: int = config.LODES_YEAR, k: int = config.N_ZONES):
    """Returns (zones, connectors, internal, report) DataFrames / dict."""
    L = Path(lodes_dir)
    blocks_all = load_blocks(L, D, year)
    b = blocks_all[(blocks_all.jobs + blocks_all.workers) > 0].reset_index(drop=True)
    xy = _xy(b.lat, b.lon)
    act = (b.jobs + b.workers).to_numpy(float)
    lab = cluster(xy, act, k)
    # stable ids: north to south
    cy = np.array([np.average(xy[lab == j, 1], weights=act[lab == j]) if (lab == j).any() else -np.inf for j in range(k)])
    order = {j: i for i, j in enumerate(np.argsort(-cy)) if (lab == j).any()}
    b["zone"] = [f"z{order[j] + 1:03d}" for j in lab]

    # commute flows: peninsula-internal vs across a gateway
    zone_of = dict(zip(b.block, b.zone))
    od = pd.read_csv(L / f"sc_od_main_JT00_{year}.csv.gz", dtype={"w_geocode": str, "h_geocode": str},
                     usecols=["w_geocode", "h_geocode", "S000"])
    od = od[od.w_geocode.isin(zone_of) | od.h_geocode.isin(zone_of)]
    aux = pd.read_csv(L / f"sc_od_aux_JT00_{year}.csv.gz", dtype={"w_geocode": str, "h_geocode": str},
                      usecols=["w_geocode", "h_geocode", "S000"])
    aux = aux[aux.w_geocode.isin(zone_of)]
    both = od[od.w_geocode.isin(zone_of) & od.h_geocode.isin(zone_of)].copy()
    both["o_zone"], both["d_zone"] = both.h_geocode.map(zone_of), both.w_geocode.map(zone_of)
    internal = both.groupby(["o_zone", "d_zone"], as_index=False).S000.sum().rename(columns={"S000": "commuters"})
    jobs_in_od = pd.concat([od[od.w_geocode.isin(zone_of)], aux]).groupby("w_geocode").S000.sum()
    jobs_internal = both.groupby("w_geocode").S000.sum()
    workers_internal = both.groupby("h_geocode").S000.sum()
    b["jobs_internal"] = b.block.map(jobs_internal).fillna(0)
    b["jobs_external"] = (b.block.map(jobs_in_od).fillna(0) - b.jobs_internal).clip(lower=0)
    b["workers_internal"] = b.block.map(workers_internal).fillna(0)
    # RAC counts every job held by a resident, wherever it is (incl. out of state)
    b["workers_external"] = (b.workers - b.workers_internal).clip(lower=0)

    g = b.groupby("zone")
    zones = g[["jobs", "workers", "jobs_internal", "jobs_external", "workers_internal", "workers_external"]].sum()
    zones["n_blocks"] = g.size()
    zones["lat"] = g.apply(lambda d: np.average(d.lat, weights=d.jobs + d.workers))
    zones["lon"] = g.apply(lambda d: np.average(d.lon, weights=d.jobs + d.workers))
    zones = zones.reset_index()

    # connectors: each block spreads its activity over its nearest eligible nodes
    # (inverse distance); a zone keeps its MAX_CONNECTORS_PER_ZONE heaviest nodes.
    nodes = eligible_nodes(D)
    tree = cKDTree(_xy([D.nodes[n]["y"] for n in nodes], [D.nodes[n]["x"] for n in nodes]))
    dist, idx = tree.query(xy, k=config.CONNECTOR_NODES_PER_BLOCK)
    wts = 1.0 / np.maximum(dist, 10.0)
    wts = wts / wts.sum(1, keepdims=True) * act[:, None]
    load = pd.DataFrame({"zone": np.repeat(b.zone.to_numpy(), idx.shape[1]),
                         "node": [nodes[i] for i in idx.ravel()], "w": wts.ravel(), "dist_m": dist.ravel()})
    con = load.groupby(["zone", "node"], as_index=False).agg(w=("w", "sum"), dist_m=("dist_m", "mean"))
    con = (con.sort_values(["zone", "w", "node"], ascending=[True, False, True])
           .groupby("zone").head(config.MAX_CONNECTORS_PER_ZONE).copy())
    con["share"] = con.w / con.groupby("zone").w.transform("sum")
    con = con[["zone", "node", "share", "dist_m"]].round({"share": 4, "dist_m": 0}).reset_index(drop=True)

    dropped = blocks_all[(blocks_all.jobs + blocks_all.workers) > 0]
    report = dict(
        year=year, blocks_with_activity=len(b), zones=len(zones),
        jobs=float(b.jobs.sum()), workers=float(b.workers.sum()),
        jobs_in_od=float(b.jobs_internal.sum() + b.jobs_external.sum()),
        internal_commuters=float(internal.commuters.sum()),
        intrazonal_commuters=float(internal[internal.o_zone == internal.d_zone].commuters.sum()),
        jobs_external=float(b.jobs_external.sum()), workers_external=float(b.workers_external.sum()),
        connectors_per_zone=con.groupby("zone").size().describe()[["min", "50%", "max"]].to_dict(),
        max_zone_activity_share=float((zones.jobs + zones.workers).max() / act.sum()),
        blocks_kept=len(dropped),
    )
    return zones, con, internal, report
