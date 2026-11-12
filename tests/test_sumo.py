"""Tests for the SUMO bridge (chstraffic.sumo) that need no SUMO binaries.

A three-node toy street, not Charleston: OSM chain recovery, tags per direction, edge-id mapping, paired trips.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chstraffic import sumo  # noqa: E402


def toy():
    # OSM: way 1 runs 10 - 11 - 12 - 13 (11 and 12 are shape points), way 2 runs 13 - 14
    nodes = {10: (32.0, -80.0, {}), 11: (32.0, -79.999, {}), 12: (32.0, -79.998, {"highway": "traffic_signals"}),
             13: (32.0, -79.997, {"highway": "traffic_signals", "name": "drop me"}), 14: (32.001, -79.997, {})}
    nbrs = {10: {11}, 11: {10, 12}, 12: {11, 13}, 13: {12, 14}, 14: {13}}
    osm = sumo.Osm(nodes, nbrs)
    D = nx.DiGraph()
    for n in (10, 13, 14):
        D.add_node(n, x=nodes[n][1], y=nodes[n][0])
    L1 = sum(sumo._hav_m(osm, a, b) for a, b in ((10, 11), (11, 12), (12, 13)))
    L2 = sumo._hav_m(osm, 13, 14)
    s1 = SimpleNamespace(a=10, b=13, highway="tertiary", name="A St", template={"length_m": L1})
    s2 = SimpleNamespace(a=13, b=14, highway="residential", name="B St", template={"length_m": L2})
    table = {frozenset((10, 13)): s1, frozenset((13, 14)): s2}
    return osm, D, table


def test_segment_paths_follow_osm_chain():
    osm, D, table = toy()
    paths, missing = sumo.segment_paths(D, table, osm)
    assert missing == []
    assert paths[frozenset((10, 13))] == [10, 11, 12, 13]
    assert paths[frozenset((13, 14))] == [13, 14]


def test_variant_osm_tags_and_edge_mapping(tmp_path):
    osm, D, table = toy()
    paths, _ = sumo.segment_paths(D, table, osm)
    G = nx.DiGraph()
    G.add_edge(10, 13, lanes=1, speed_kph=40.0)       # A St two-way, 1 lane each way
    G.add_edge(13, 10, lanes=1, speed_kph=40.0)
    G.add_edge(14, 13, lanes=2, speed_kph=40.0)       # B St one-way against its a -> b order
    wm = sumo.write_variant_osm(tmp_path / "v.osm", D, G, table, paths, osm)
    txt = (tmp_path / "v.osm").read_text()
    assert 'k="oneway" v="no"' in txt and 'k="lanes:forward" v="1"' in txt
    assert 'k="oneway" v="-1"' in txt and 'k="lanes" v="2"' in txt
    assert 'k="name" v="drop me"' not in txt and 'v="traffic_signals"' in txt
    # a fake netconvert output: forward, reverse, split and ramp-added ids map back to project edges
    wa = [w for w, ab in wm.way_of.items() if ab == (10, 13)][0]
    wb = [w for w, ab in wm.way_of.items() if ab == (13, 14)][0]
    net_xml = tmp_path / "v.net.xml"
    net_xml.write_text(
        '<net><location/>'
        f'<edge id="{wa}#0" from="10" to="12"/><edge id="{wa}#1" from="12" to="13"/>'
        f'<edge id="-{wa}#1" from="13" to="12"/><edge id="-{wb}" from="14" to="13"/>'
        f'<edge id="-{wb}-AddedOnRampEdge" from="14" to="13"/><edge id=":13_0" function="internal"/>'
        '<junction id="10" x="0" y="0"/><junction id="cluster_12_13" x="1" y="0"/><junction id="14" x="2" y="0"/>'
        '</net>')
    net = sumo.read_net(net_xml, wm, D)
    assert net.edges[f"{wa}#0"] == (10, 13) and net.edges[f"{wa}#1"] == (10, 13)
    assert net.edges[f"-{wa}#1"] == (13, 10) and net.edges[f"-{wb}"] == (14, 13)
    assert net.edges[f"-{wb}-AddedOnRampEdge"] == (14, 13) and net.unmapped_edges == []
    assert net.junction_of == {10: "10", 13: "cluster_12_13", 14: "14"}
    flows = sumo.project_flows({f"{wa}#0": 10.0, f"{wa}#1": 20.0, f"-{wb}": 5.0}, net, [(10, 13), (13, 10), (14, 13), (13, 14)])
    assert flows[0] == 15.0 and flows[1] == 0.0 and flows[2] == 2.5 and np.isnan(flows[3])


def test_trips_same_draws_across_networks(tmp_path):
    od = {(10, 14): 120.0, (14, 10): 60.0, (13, 10): 30.0}
    n1 = SimpleNamespace(junction_of={10: "10", 13: "13", 14: "14"})
    n2 = SimpleNamespace(junction_of={10: "10", 13: "c13", 14: "14"})       # renamed junction in a variant
    a = sumo.write_trips(tmp_path / "a.xml", od, n1, seed=7)
    b = sumo.write_trips(tmp_path / "b.xml", od, n2, seed=7)
    assert a == b and a["vehicles"] > 0
    ta = (tmp_path / "a.xml").read_text()
    tb = (tmp_path / "b.xml").read_text()
    assert ta.replace('Junction="13"', 'Junction="c13"') == tb
    c = sumo.write_trips(tmp_path / "c.xml", od, n1, seed=7, scale=0.5)
    assert c["expected"] == a["expected"] / 2


def test_fill_uncovered_uses_same_street_neighbours():
    G = nx.DiGraph()
    G.add_edge(1, 2, name="A")
    G.add_edge(2, 3, name="A")        # folded into a junction in SUMO
    G.add_edge(3, 4, name="A")
    G.add_edge(3, 5, name="B")        # other street: not used
    edges = list(G.edges)
    f = np.array([[100.0, np.nan, 300.0, 999.0]])
    filled, left = sumo.fill_uncovered(f, edges, G)
    assert left == 0 and filled[0, 1] == 200.0 and filled[0, 0] == 100.0
