"""Which one-way / two-way configurations are possible on the SAME pavement.

Rules (HANDOFF 6B):
* A physical segment has a fixed number of total lanes.
* >= 2 total lanes: two-way (lanes split) or one-way in either direction.
* 1 total lane: one-way in either direction only. Making it two-way would
  mean removing parking, which changes the physical road.
* Freeways, ramps, trunks and divided roads are frozen.

Configurations are dicts {segment_id: state}, state in {"two", "ab", "ba"}.
For a segment, (a, b) is a fixed canonical node order and "ab" means one-way a->b.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np

from . import config

STATES = ("two", "ab", "ba")


@dataclass
class Segment:
    sid: frozenset
    a: object
    b: object
    total_lanes: int
    highway: str
    name: str | None
    state: str                    # current (baseline) state
    allowed: tuple[str, ...]
    template: dict = field(repr=False, default_factory=dict)
    frozen_reason: str | None = None
    lanes_source: str = "osm"     # "osm" or "override"


def _canon(sid):
    a, b = sorted(sid, key=str)
    return a, b


def _dist_m(D, p, q):
    dy = (D.nodes[p]["y"] - D.nodes[q]["y"]) * 111_000
    dx = (D.nodes[p]["x"] - D.nodes[q]["x"]) * 111_000 * math.cos(math.radians(D.nodes[p]["y"]))
    return math.hypot(dx, dy)


def load_overrides(path: Path | str) -> list[dict]:
    """Read data/reference/overrides.csv (lines starting with # are comments)."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(line for line in f if not line.startswith("#"))]
    return [r for r in rows if (r.get("total_lanes") or r.get("frozen"))]


def _override_for(seg_osmids: set, name, rows):
    """Most specific match wins: osmid beats name."""
    by_name = None
    for r in rows:
        if r.get("osmid") and str(r["osmid"]).strip() in seg_osmids:
            return r
        if not r.get("osmid") and r.get("name") and r["name"] == name:
            by_name = r
    return by_name


def segment_table(D: nx.DiGraph, overrides: list[dict] | None = None,
                  widths: dict | None = None) -> dict[frozenset, Segment]:
    """widths: {segment_id: lanes} from widths.load(); used only where OSM has no lanes tag."""
    overrides = overrides or []
    widths = widths or {}
    edges_by_seg: dict[frozenset, list] = {}
    for u, v, d in D.edges(data=True):
        edges_by_seg.setdefault(d["segment_id"], []).append((u, v, d))

    table: dict[frozenset, Segment] = {}
    for sid, es in edges_by_seg.items():
        if len(sid) < 2:
            continue  # self-loop: ignore
        a, b = _canon(sid)
        has_ab = any(u == a for u, _, _ in es)
        has_ba = any(u == b for u, _, _ in es)
        state = "two" if (has_ab and has_ba) else ("ab" if has_ab else "ba")
        d0 = es[0][2]
        total = d0.get("seg_total_lanes") or sum(d["lanes"] for _, _, d in es)
        hwy, name = d0["highway"], d0.get("name")
        osmids = {str(d.get("osmid")) for _, _, d in es}
        frozen_reason, src = None, "osm"
        if (config.USE_WIDTH_LANES and sid in widths and not d0.get("lanes_tagged", True)
                and not d0.get("seg_total_lanes")):
            total, src = widths[sid], "city width"
        ov = _override_for(osmids, name, overrides)
        if ov:
            if ov.get("total_lanes"):
                total, src = int(ov["total_lanes"]), "override"
            if str(ov.get("frozen", "")).strip().lower() in {"1", "true", "yes"}:
                frozen_reason = "override"
        if hwy in config.FROZEN_HIGHWAYS:
            frozen_reason = frozen_reason or "freeway/trunk"
        table[sid] = Segment(sid=sid, a=a, b=b, total_lanes=int(total), highway=hwy, name=name,
                             state=state, allowed=(), template=dict(d0),
                             frozen_reason=frozen_reason, lanes_source=src)

    _mark_divided(D, table)
    for s in table.values():
        if s.frozen_reason:
            s.allowed = (s.state,)
        elif s.total_lanes >= 2:
            s.allowed = STATES
        else:
            s.allowed = ("ab", "ba")
    return table


def _mark_divided(D, table):
    """Opposite one-way segments of the same street lying side by side = divided road."""
    by_name: dict[str, list[Segment]] = {}
    for s in table.values():
        if s.state != "two" and s.name and not s.frozen_reason:
            by_name.setdefault(s.name, []).append(s)
    lim = config.DIVIDED_MAX_SEP_M
    for segs in by_name.values():
        for i, s in enumerate(segs):
            fs, ts = (s.a, s.b) if s.state == "ab" else (s.b, s.a)
            for t in segs[i + 1:]:
                ft, tt = (t.a, t.b) if t.state == "ab" else (t.b, t.a)
                # opposite directions: s's start near t's end and vice versa
                if _dist_m(D, fs, tt) <= lim and _dist_m(D, ts, ft) <= lim and {fs, ts} != {ft, tt}:
                    s.frozen_reason = t.frozen_reason = "divided road"


def baseline_config(table) -> dict:
    return {sid: s.state for sid, s in table.items()}


def apply_config(D: nx.DiGraph, table: dict, cfg: dict) -> nx.DiGraph:
    """Rebuild the directed graph for configuration cfg on the same pavement.

    Lanes: one-way gets all total lanes; two-way gets max(1, total // 2) each way
    (an odd lane is treated as a turn lane). Capacity is recomputed the same way
    for the baseline and every candidate, so comparisons are like for like.
    """
    G = nx.DiGraph()
    G.graph.update(D.graph)
    G.add_nodes_from(D.nodes(data=True))
    for sid, s in table.items():
        st = cfg.get(sid, s.state)
        if st not in s.allowed:
            raise ValueError(f"state {st!r} not allowed for segment {s.a}-{s.b} ({s.name})")
        dirs = {"two": [(s.a, s.b), (s.b, s.a)], "ab": [(s.a, s.b)], "ba": [(s.b, s.a)]}[st]
        oneway = st != "two"
        lanes = s.total_lanes if oneway else max(1, s.total_lanes // 2)
        cap = lanes * config.CAPACITY_VPHPL[s.highway] * (config.ONEWAY_CAPACITY_BONUS if oneway else 1.0)
        for u, v in dirs:
            attrs = {k: val for k, val in s.template.items() if k != "geometry"}
            attrs.update(lanes=lanes, capacity_vph=cap, oneway=oneway, segment_id=sid,
                         seg_total_lanes=s.total_lanes)
            G.add_edge(u, v, **attrs)
    # edges not in the table (self-loops) pass through unchanged
    for u, v, d in D.edges(data=True):
        if d["segment_id"] not in table and not G.has_edge(u, v):
            G.add_edge(u, v, **d)
    return G


def random_config(table, rng: random.Random) -> dict:
    return {sid: rng.choice(s.allowed) for sid, s in table.items()}


# ---------------------------------------------------------------------------
# Corridors: the unit of decision for the search
# ---------------------------------------------------------------------------

@dataclass
class Corridor:
    cid: int
    name: str
    segments: list[frozenset]
    axis: tuple[float, float]       # unit vector of the street's direction
    fwd: dict                       # sid -> state that points along +axis

    def config_for(self, table, mode: str) -> tuple[dict, list]:
        """mode in {"two", "fwd", "rev"}. Returns (partial cfg, blocked segments)."""
        cfg, blocked = {}, []
        for sid in self.segments:
            s = table[sid]
            if mode == "two":
                want = "two"
            else:
                f = self.fwd[sid]
                want = f if mode == "fwd" else ("ba" if f == "ab" else "ab")
            if want in s.allowed:
                cfg[sid] = want
            else:
                blocked.append(sid)
        return cfg, blocked


def corridors(D: nx.DiGraph, table: dict, split_highways: set | None = None,
              classes: set | None = None, min_length_m: float = 0.0) -> list[Corridor]:
    """Group same-named, connected, non-frozen segments; split at major cross streets.

    split_highways: classes of cross street that break a corridor (default config.MAJOR_HIGHWAYS).
    classes: keep only corridors whose longest highway class (by length) is in this set.
    min_length_m: drop shorter corridors. Dropped corridors simply stay as they are today.
    """
    split_highways = config.MAJOR_HIGHWAYS if split_highways is None else split_highways
    major_nodes: dict = {}
    for s in table.values():
        if s.highway in split_highways:
            for n in (s.a, s.b):
                major_nodes.setdefault(n, set()).add(s.name)

    H = nx.Graph()
    by_node: dict = {}
    for sid, s in table.items():
        if s.frozen_reason or not s.name or len(s.allowed) < 2:
            continue
        H.add_node(sid)
        for n in (s.a, s.b):
            by_node.setdefault((s.name, n), []).append(sid)
    for (name, n), sids in by_node.items():
        crosses_major = any(other != name for other in major_nodes.get(n, ()))
        if crosses_major:
            continue  # break the corridor here
        for i in range(len(sids)):
            for j in range(i + 1, len(sids)):
                H.add_edge(sids[i], sids[j])

    out = []
    for k, comp in enumerate(sorted(nx.connected_components(H), key=lambda c: sorted(map(str, c)))):
        comp = list(comp)
        by_class: dict = {}
        for sid in comp:
            by_class[table[sid].highway] = by_class.get(table[sid].highway, 0.0) + table[sid].template["length_m"]
        if sum(by_class.values()) < min_length_m or (classes is not None and max(by_class, key=by_class.get) not in classes):
            continue
        pts = np.array([[D.nodes[n]["x"] * math.cos(math.radians(D.nodes[n]["y"])), D.nodes[n]["y"]]
                        for sid in comp for n in (table[sid].a, table[sid].b)])
        if len(pts) >= 2 and np.ptp(pts, axis=0).sum() > 0:
            _, _, vt = np.linalg.svd(pts - pts.mean(axis=0))
            ax = vt[0]
        else:
            ax = np.array([1.0, 0.0])
        if ax[1] < 0 or (ax[1] == 0 and ax[0] < 0):
            ax = -ax  # +axis points north-ish so "fwd" is stable
        fwd = {}
        for sid in comp:
            s = table[sid]
            vec = np.array([(D.nodes[s.b]["x"] - D.nodes[s.a]["x"]) * math.cos(math.radians(D.nodes[s.a]["y"])),
                            D.nodes[s.b]["y"] - D.nodes[s.a]["y"]])
            fwd[sid] = "ab" if float(vec @ ax) >= 0 else "ba"
        out.append(Corridor(cid=len(out), name=table[comp[0]].name, segments=sorted(comp, key=lambda x: sorted(map(str, x))),
                            axis=(float(ax[0]), float(ax[1])), fwd=fwd))
    return out


def search_corridors(D: nx.DiGraph, table: dict) -> list[Corridor]:
    """The coarse decision set used by the search (config.SEARCH_*)."""
    return corridors(D, table, split_highways=config.SEARCH_SPLIT_HIGHWAYS, classes=config.SEARCH_CLASSES,
                     min_length_m=config.SEARCH_MIN_LENGTH_M)


def corridor_length_m(table: dict, c: Corridor) -> float:
    return float(sum(table[sid].template["length_m"] for sid in c.segments))


def two_way_share(table: dict, cfg: dict) -> float:
    """Share of changeable street length (not frozen) that is two-way under cfg."""
    tot = two = 0.0
    for sid, s in table.items():
        if s.frozen_reason:
            continue
        tot += s.template["length_m"]
        two += s.template["length_m"] * (cfg.get(sid, s.state) == "two")
    return two / tot if tot else 0.0


# ---------------------------------------------------------------------------
# Tier-1 screen
# ---------------------------------------------------------------------------

def core_nodes(D_base: nx.DiGraph) -> set:
    """Nodes that must stay mutually reachable: the baseline's largest SCC.

    Freeway stubs where the road leaves the study box (gateway sources/sinks)
    sit outside it by construction; see HANDOFF 9, step A.
    """
    return max(nx.strongly_connected_components(D_base), key=len)


def _ff_times(D, sources, targets):
    out = {}
    for s in sources:
        dist = nx.single_source_dijkstra_path_length(D, s, weight="fftt_s")
        for t in targets:
            out[(s, t)] = dist.get(t, math.inf)
    return out


@dataclass
class ScreenResult:
    ok: bool
    reason: str
    detour_ratio: float = float("nan")


def screen(D_base: nx.DiGraph, D_new: nx.DiGraph, od_pairs: list[tuple], core: set | None = None,
           base_times: dict | None = None, max_detour: float = config.SCREEN_MAX_DETOUR) -> ScreenResult:
    """Cheap graph checks before running any assignment.

    1. Every core node stays mutually reachable (one SCC contains all of them).
    2. Every O-D pair still has a path.
    3. Mean free-flow O-D time is at most max_detour x baseline.
    """
    core = core if core is not None else core_nodes(D_base)
    sub = D_new.subgraph(core)
    if not nx.is_strongly_connected(sub) and not _core_in_one_scc(D_new, core):
        return ScreenResult(False, "core no longer strongly connected")
    srcs = sorted({o for o, _ in od_pairs}, key=str)
    dsts = sorted({d for _, d in od_pairs}, key=str)
    new_t = _ff_times(D_new, srcs, dsts)
    base_t = base_times or _ff_times(D_base, srcs, dsts)
    if any(math.isinf(new_t[p]) for p in od_pairs):
        return ScreenResult(False, "an O-D pair lost its path")
    ratio = float(np.mean([new_t[p] for p in od_pairs]) / np.mean([base_t[p] for p in od_pairs]))
    if ratio > max_detour:
        return ScreenResult(False, f"mean detour {ratio:.2f}x > {max_detour}x", ratio)
    return ScreenResult(True, "ok", ratio)


def _core_in_one_scc(D, core):
    first = next(iter(core))
    reach_f = nx.descendants(D, first) | {first}
    reach_b = nx.ancestors(D, first) | {first}
    return core <= (reach_f & reach_b)


def robbins_orientable(D: nx.DiGraph, nodes: set | None = None) -> bool:
    """Robbins (1939): an undirected graph has a strongly connected orientation
    iff it is connected and 2-edge-connected (has no bridge)."""
    U = nx.Graph()
    sub = D.subgraph(nodes) if nodes is not None else D
    U.add_edges_from((u, v) for u, v in sub.edges() if u != v)
    return U.number_of_nodes() > 0 and nx.is_connected(U) and not nx.has_bridges(U)
