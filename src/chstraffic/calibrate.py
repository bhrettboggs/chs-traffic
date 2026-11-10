"""Compare modeled link flows with SCDOT counts (GEH statistic). Used by scripts/04 and 07.

Count side:  AADT x K_FACTOR = peak-hour volume, both directions.
Model side:  UE flow on the matched segment (both directions), or on every edge of
             a road that crosses a cut line (divided roads).
GEH = sqrt(2 (M - C)^2 / (M + C)); common practice wants GEH < 5 at ~85% of stations.
"""

from __future__ import annotations

import math
import pickle
import re
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from . import config, demand, feasibility, widths


def baseline_graph(root: Path) -> nx.DiGraph:
    """Today's network with overrides applied (what every script calls the baseline)."""
    D = pickle.loads((root / "data" / "processed" / "chs_digraph.gpickle").read_bytes())
    table = feasibility.segment_table(D, feasibility.load_overrides(root / "data" / "reference" / "overrides.csv"),
                                      widths.load(root / "data" / "processed" / "segment_widths.csv"))
    return feasibility.apply_config(D, table, feasibility.baseline_config(table))


def load_counts(root: Path):
    counts = pd.read_csv(root / "data" / "raw" / "scdot_aadt_2025_peninsula.csv")
    st = pd.read_csv(root / "data" / "reference" / "count_stations.csv", comment="#")
    return st, counts


def geh(m, c):
    return math.sqrt(2 * (m - c) ** 2 / (m + c)) if m + c > 0 else 0.0


def locate(D, road, frm, to):
    """Middle segment of `road` between its crossings with `frm` and `to`."""
    rx, fx, tx = (re.compile(p, re.I) for p in (road, frm, to))
    name = lambda d: str(d.get("name"))  # noqa: E731
    R = nx.Graph()
    R.add_edges_from((u, v) for u, v, d in D.edges(data=True) if rx.search(name(d)))
    def crossing(px):
        return {n for u, v, d in D.edges(data=True) if px.search(name(d)) and not rx.search(name(d))
                for n in (u, v) if n in R}
    A, B = crossing(fx), crossing(tx)
    if not A or not B:
        return None, f"no crossing with {frm if not A else to}"
    best = None
    for a in A:
        lengths = nx.single_source_shortest_path_length(R, a)
        for b in B:
            if b in lengths and (best is None or lengths[b] < best[0]) and a != b:
                best = (lengths[b], a, b)
    if best is None:
        return None, "crossings not connected along road"
    path = nx.shortest_path(R, best[1], best[2])
    i = (len(path) - 1) // 2
    return frozenset((path[i], path[i + 1])), f"{len(path) - 1} segments"


def cut_edges(D, road, cut):
    """Every directed edge of `road` that crosses the line 'lon=<v>' or 'lat=<v>' (both carriageways)."""
    axis, val = cut.split("=")
    key, val, rx = {"lon": "x", "lat": "y"}[axis.strip()], float(val), re.compile(road, re.I)
    return [(u, v) for u, v, d in D.edges(data=True) if rx.search(str(d.get("name")))
            and (D.nodes[u][key] - val) * (D.nodes[v][key] - val) < 0]


def fit_table(B, net, flows, st, counts) -> pd.DataFrame:
    """One row per station: count, modeled flow (median and spread over scenarios), ratio, GEH."""
    eidx = {e: k for k, e in enumerate(net.edges)}
    rows = []
    for r in st.merge(counts[["station", "aadt_2025"]], on="station").itertuples():
        if isinstance(r.cut, str) and r.cut:
            ks, how = [eidx[e] for e in cut_edges(B, r.road, r.cut)], f"cut {r.cut}"
            if not ks:
                rows.append(dict(station=r.station, road=r.road, split=r.split, note="cut crosses no edge"))
                continue
        else:
            seg, how = locate(B, r.road, r.from_street, r.to_street)
            if seg is None:
                rows.append(dict(station=r.station, road=r.road, split=r.split, note=how))
                continue
            a, b = tuple(seg)
            ks = [eidx[e] for e in ((a, b), (b, a)) if e in eidx]
        m = flows[:, ks].sum(axis=1)
        c = r.aadt_2025 * config.K_FACTOR
        rows.append(dict(station=r.station, road=r.road.strip("^$").replace("\\", ""), split=r.split,
                         conf=r.mapping_confidence, aadt=r.aadt_2025, count_peak=round(c),
                         model_median=round(float(np.median(m))),
                         model_p10=round(float(np.percentile(m, 10))), model_p90=round(float(np.percentile(m, 90))),
                         ratio=round(float(np.median(m)) / c, 2), geh=round(geh(float(np.median(m)), c), 1),
                         directions=len(ks), note=how))
    return pd.DataFrame(rows)


def summary(df: pd.DataFrame, part: str, drop_low: bool = False) -> dict:
    p = df.dropna(subset=["geh"])
    p = p[p.split == part]
    if drop_low:
        p = p[p.conf != "low"]
    return dict(n=len(p), geh5=float(np.mean(p.geh < 5)), geh10=float(np.mean(p.geh < 10)),
                median_geh=float(p.geh.median()), total_ratio=float(p.model_median.sum() / p.count_peak.sum()),
                log2=float(np.median(np.abs(np.log2(np.maximum(p.ratio, 0.01))))))
