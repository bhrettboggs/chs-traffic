"""Turn an OSM street network into the project's weighted directed graph.

Model
-----
* A node is an intersection (OSM node after osmnx simplification).
* A directed edge (u, v) is one direction of travel along a street segment.
  - two-way street  -> two edges, (u, v) and (v, u)
  - one-way street  -> one edge in the legal direction
* Every directed edge carries:
    length_m, speed_kph, fftt_s (free-flow travel time), lanes (in that
    direction), capacity_vph, highway, name, oneway, segment_id
* ``segment_id`` groups the directed edges that share one physical piece of
  pavement. The redesign step changes how a segment's lanes are split between
  directions, never the pavement itself — which is the "keep the physical roads
  the same" constraint.
"""

from __future__ import annotations

import math
import re
from typing import Any

import networkx as nx

from . import config


def _first(value: Any) -> Any:
    """osmnx stores merged attributes as lists; take the first."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _parse_speed_kph(maxspeed: Any) -> float | None:
    maxspeed = _first(maxspeed)
    if maxspeed is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(maxspeed))
    if not m:
        return None
    val = float(m.group(1))
    # US OSM data is almost always "25 mph"; a bare number <= 50 is assumed mph.
    is_mph = "mph" in str(maxspeed).lower() or val <= 50
    return val * 1.609344 if is_mph else val


def _parse_int(value: Any) -> int | None:
    value = _first(value)
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def _hwy(data: dict) -> str:
    h = _first(data.get("highway")) or "residential"
    return h if h in config.CAPACITY_VPHPL else "residential"


def build_digraph(G_osm: nx.MultiDiGraph) -> nx.DiGraph:
    """Collapse an osmnx MultiDiGraph into a weighted DiGraph.

    Parallel edges between the same (u, v) are merged by keeping the one with
    the lowest free-flow time and summing capacity (they are parallel lanes of
    supply between the same two intersections).
    """
    D = nx.DiGraph()
    D.graph["crs"] = G_osm.graph.get("crs", "epsg:4326")

    for n, d in G_osm.nodes(data=True):
        D.add_node(n, x=d.get("x"), y=d.get("y"),
                   signal=str(d.get("highway", "")) == "traffic_signals")

    for u, v, _k, d in G_osm.edges(keys=True, data=True):
        hwy = _hwy(d)
        oneway = bool(d.get("oneway", False))
        length = float(d.get("length", 0.0)) or 1.0

        speed = _parse_speed_kph(d.get("maxspeed")) or config.DEFAULT_SPEED_KPH[hwy]
        fftt = length / (speed / 3.6)

        total_lanes = _parse_int(d.get("lanes"))
        if total_lanes is None:
            lanes_dir = config.DEFAULT_LANES_PER_DIR[hwy]
        elif oneway:
            lanes_dir = max(1, total_lanes)
        else:
            lanes_dir = max(1, math.floor(total_lanes / 2))

        cap = lanes_dir * config.CAPACITY_VPHPL[hwy]
        if oneway:
            cap *= config.ONEWAY_CAPACITY_BONUS

        attrs = dict(
            length_m=length, speed_kph=speed, fftt_s=fftt, lanes=lanes_dir,
            capacity_vph=cap, highway=hwy, name=_first(d.get("name")),
            oneway=oneway, segment_id=frozenset((u, v)),
            osmid=_first(d.get("osmid")),
        )
        if D.has_edge(u, v):
            e = D[u][v]
            e["capacity_vph"] += cap
            if fftt < e["fftt_s"]:
                keep_cap = e["capacity_vph"]
                e.update(attrs)
                e["capacity_vph"] = keep_cap
        else:
            D.add_edge(u, v, **attrs)

    return D


def segments(D: nx.DiGraph) -> dict[frozenset, list[tuple]]:
    """Map each physical segment to its directed edges (1 for one-way, 2 for two-way)."""
    out: dict[frozenset, list[tuple]] = {}
    for u, v, d in D.edges(data=True):
        out.setdefault(d["segment_id"], []).append((u, v))
    return out


def summarize(D: nx.DiGraph) -> dict[str, Any]:
    segs = segments(D)
    one = sum(1 for e in segs.values() if len(e) == 1)
    return {
        "nodes": D.number_of_nodes(),
        "directed_edges": D.number_of_edges(),
        "physical_segments": len(segs),
        "one_way_segments": one,
        "two_way_segments": len(segs) - one,
        "signalized_nodes": sum(1 for _, d in D.nodes(data=True) if d.get("signal")),
        "strongly_connected": nx.is_strongly_connected(D) if D.number_of_nodes() else False,
    }
