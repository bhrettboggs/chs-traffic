"""Toy street grid in osmnx's data shape, for tests and dry runs.

NOT Charleston. Never report numbers from this grid as results.

Layout: ``cols`` north-south avenues x ``rows`` east-west streets, ~110 m apart.
* Avenue 0 is a two-way primary arterial (2 lanes each way).
* Odd avenues are one-way north, even avenues (>0) one-way south, 2 lanes:
  one-way pairs, like Ashley/Rutledge.
* Every third street is a one-lane one-way residential street; the rest are
  two-way with 1 lane each way.
* A freeway runs in from the north-west corner (frozen gateway).
"""

from __future__ import annotations

import networkx as nx

DEG = 0.001  # ~110 m of latitude


def grid_osm(cols: int = 8, rows: int = 10) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph(crs="epsg:4326")

    def nid(i, j):
        return i * 1000 + j

    for i in range(cols):
        for j in range(rows):
            G.add_node(nid(i, j), x=-79.95 + i * DEG * 1.19, y=32.78 + j * DEG)

    def add(a, b, oneway, **tags):
        ya, yb = G.nodes[a]["y"], G.nodes[b]["y"]
        xa, xb = G.nodes[a]["x"], G.nodes[b]["x"]
        length = ((ya - yb) ** 2 + ((xa - xb) * 0.841) ** 2) ** 0.5 * 111_000
        attrs = dict(length=length, oneway=oneway, maxspeed="25 mph", osmid=hash((a, b)) % 10**8, **tags)
        G.add_edge(a, b, **attrs)
        if not oneway:
            G.add_edge(b, a, **attrs)

    for i in range(cols):  # avenues
        name = f"Avenue {i}"
        for j in range(rows - 1):
            a, b = nid(i, j), nid(i, j + 1)
            if i == 0:
                add(a, b, False, highway="primary", lanes="4", name=name)
            elif i % 2 == 1:
                add(a, b, True, highway="secondary", lanes="2", name=name)
            else:
                add(b, a, True, highway="secondary", lanes="2", name=name)
    for j in range(rows):  # streets
        name = f"Street {j}"
        for i in range(cols - 1):
            a, b = nid(i, j), nid(i + 1, j)
            if j % 3 == 2:
                (add(a, b, True, highway="residential", lanes="1", name=name) if j % 2
                 else add(b, a, True, highway="residential", lanes="1", name=name))
            else:
                add(a, b, False, highway="residential", lanes="2", name=name)

    # freeway gateway from the north-west, and its outbound twin
    G.add_node("fw_in", x=-79.955, y=32.78 + rows * DEG)
    G.add_node("fw_out", x=-79.956, y=32.78 + rows * DEG)
    G.add_edge("fw_in", nid(0, rows - 1), length=500.0, oneway=True, highway="motorway",
               lanes="2", maxspeed="55 mph", name="Freeway", osmid=1)
    G.add_edge(nid(0, rows - 1), "fw_out", length=500.0, oneway=True, highway="motorway",
               lanes="2", maxspeed="55 mph", name="Freeway", osmid=2)
    return G


def toy_zones(cols: int = 8, rows: int = 10):
    """(gateways {name: (node, vph)}, destinations {name: (node, weight)})."""
    gateways = {
        "freeway": ("fw_in", 1800.0),
        "south_west": (0 * 1000 + 0, 900.0),
        "south_east": ((cols - 1) * 1000 + 0, 700.0),
    }
    dests = {
        "core": ((cols // 2) * 1000 + rows // 2, 5.0),
        "north_east": ((cols - 2) * 1000 + rows - 2, 3.0),
        "middle_west": (2 * 1000 + rows // 2, 2.0),
        "south_mid": ((cols // 2) * 1000 + 1, 2.0),
    }
    return gateways, dests
