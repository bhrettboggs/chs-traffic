"""Offline tests: run with `pytest` from the repo root. No network needed."""

import sys
from pathlib import Path

import networkx as nx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chstraffic.assignment import bpr_time, user_equilibrium  # noqa: E402
from chstraffic.graph import build_digraph, segments, summarize  # noqa: E402


def _toy_osm():
    """Tiny osmnx-shaped MultiDiGraph: a two-way street A-B and a one-way B->C."""
    G = nx.MultiDiGraph(crs="epsg:4326")
    for n, (x, y) in {1: (0, 0), 2: (1, 0), 3: (2, 0)}.items():
        G.add_node(n, x=x, y=y)
    G.nodes[2]["highway"] = "traffic_signals"
    two = dict(length=400.0, highway="secondary", oneway=False, maxspeed="25 mph", lanes="2", name="Calhoun")
    G.add_edge(1, 2, **two)
    G.add_edge(2, 1, **two)
    G.add_edge(2, 3, length=300.0, highway="residential", oneway=True, lanes="2", name="Coming")
    return G


def test_build_digraph_directions_and_lanes():
    D = build_digraph(_toy_osm())
    assert D.has_edge(1, 2) and D.has_edge(2, 1)
    assert D.has_edge(2, 3) and not D.has_edge(3, 2)
    assert D[1][2]["lanes"] == 1          # 2 total lanes, two-way -> 1 per direction
    assert D[2][3]["lanes"] == 2          # one-way gets all lanes
    assert D[1][2]["speed_kph"] == pytest.approx(25 * 1.609344)
    s = summarize(D)
    assert s["one_way_segments"] == 1 and s["two_way_segments"] == 1
    assert s["signalized_nodes"] == 1
    assert len(segments(D)) == 2


def test_ue_two_route_wardrop():
    """Two parallel routes; at equilibrium both used routes have equal time."""
    D = nx.DiGraph()
    D.add_edge("o", "d", fftt_s=600, capacity_vph=1000)     # direct, slower free-flow
    D.add_edge("o", "m", fftt_s=200, capacity_vph=500)      # via m, fast but small
    D.add_edge("m", "d", fftt_s=200, capacity_vph=500)
    res = user_equilibrium(D, {("o", "d"): 1500}, max_iter=500, tol=1e-6)
    t_direct = res.times[("o", "d")]
    t_via = res.times[("o", "m")] + res.times[("m", "d")]
    assert res.flows[("o", "d")] + res.flows[("o", "m")] == pytest.approx(1500, rel=1e-6)
    assert t_direct == pytest.approx(t_via, rel=1e-2)
    assert res.relative_gap < 1e-3


def test_braess_paradox_removing_link_helps():
    """Classic Braess network: adding a free shortcut makes everyone slower.
    This is the core reason the one-way/two-way search can find real gains."""
    def net(with_shortcut):
        D = nx.DiGraph()
        # variable-cost links: t = fftt*(1+0.15*(v/c)^4); fixed-cost links: huge capacity
        D.add_edge("s", "a", fftt_s=100, capacity_vph=200)
        D.add_edge("a", "t", fftt_s=450, capacity_vph=1e9)
        D.add_edge("s", "b", fftt_s=450, capacity_vph=1e9)
        D.add_edge("b", "t", fftt_s=100, capacity_vph=200)
        if with_shortcut:
            D.add_edge("a", "b", fftt_s=1, capacity_vph=1e9)
        return D
    od = {("s", "t"): 1000}
    with_sc = user_equilibrium(net(True), od, max_iter=1000, tol=1e-6)
    without = user_equilibrium(net(False), od, max_iter=1000, tol=1e-6)
    assert with_sc.total_system_time_h > without.total_system_time_h


def test_bpr():
    assert bpr_time(60, 0, 100) == 60
    assert bpr_time(60, 100, 100) == pytest.approx(60 * 1.15)
