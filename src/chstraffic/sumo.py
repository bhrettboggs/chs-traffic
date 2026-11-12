"""SUMO cross-check of the static model (finish plan Task 4): network, demand, runs, outputs.

Network. Every segment of the project graph becomes its own OSM way: the chain of OSM nodes between its
two end nodes, taken from the same Overpass response the graph was built from, tagged with the direction
and lanes that feasibility.apply_config gives it in a configuration (overrides and variants included).
netconvert turns that file into a SUMO network. Edge ids are "<way>#<k>" (forward, segment a -> b) and
"-<way>#<k>" (b -> a), so every SUMO edge maps back to one directed project edge, and a variant differs
from the baseline only in the tags of the segments it changes. Signals: OSM traffic_signals nodes, with
netconvert's own default timings (NOT Charleston's: compare variants, never absolute delay).

Demand. The project's OD matrix {(origin node, dest node): vph} (demand.build_od, base scenario). Per seed:
a Poisson number of vehicles per pair for the warm-up plus the peak hour, uniform departure times, trips
from junction to junction (sumo --junction-taz). Routes come from SUMO's rerouting device (each vehicle
routes on current travel times at departure and every config.SUMO_REROUTE_PERIOD_S seconds), which is a
reactive assignment, not a user equilibrium.

Measured. Total travel time of the vehicles that are due to depart in the peak hour (after the warm-up):
time in the network + time waiting to be inserted; teleports (SUMO's gridlock resolution); vehicles not
inserted or not arrived by the end; vehicles entering each edge during the peak hour.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import quoteattr

import networkx as nx
import numpy as np

from . import config


# ---------------------------------------------------------------------------
# OSM input
# ---------------------------------------------------------------------------

@dataclass
class Osm:
    nodes: dict          # id -> (lat, lon, tags)
    nbrs: dict           # id -> set of neighbouring node ids along any way
    timestamp: str = ""


def load_osm(path: Path | str) -> Osm:
    """Read an Overpass JSON response (osmnx cache) or an .osm XML file."""
    path = Path(path)
    nodes, ways, ts = {}, [], ""
    if path.suffix == ".json":
        d = json.loads(path.read_text())
        ts = (d.get("osm3s") or {}).get("timestamp_osm_base", "")
        for e in d["elements"]:
            if e["type"] == "node":
                nodes[e["id"]] = (e["lat"], e["lon"], e.get("tags", {}))
            elif e["type"] == "way":
                ways.append(e["nodes"])
    else:
        root = ET.parse(path).getroot()
        meta = root.find("meta")
        ts = meta.get("osm_base", "") if meta is not None else ""
        for n in root.iter("node"):
            nodes[int(n.get("id"))] = (float(n.get("lat")), float(n.get("lon")),
                                       {t.get("k"): t.get("v") for t in n.iter("tag")})
        for w in root.iter("way"):
            ways.append([int(nd.get("ref")) for nd in w.iter("nd")])
    nbrs: dict = {}
    for wn in ways:
        for p, q in zip(wn, wn[1:]):
            if p != q:
                nbrs.setdefault(p, set()).add(q)
                nbrs.setdefault(q, set()).add(p)
    return Osm(nodes, nbrs, ts)


def export_overpass_json(src: Path, dst: Path) -> None:
    """Write the osmnx Overpass cache as a plain .osm XML file (same elements, same ids, same tags)."""
    d = json.loads(Path(src).read_text())
    ts = (d.get("osm3s") or {}).get("timestamp_osm_base", "")
    with open(dst, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="chstraffic.sumo">\n')
        f.write(f'  <meta osm_base={quoteattr(ts)}/>\n')
        for e in d["elements"]:
            tags = e.get("tags", {})
            if e["type"] == "node":
                head = f'  <node id="{e["id"]}" lat="{e["lat"]}" lon="{e["lon"]}"'
                f.write(head + ("/>\n" if not tags else ">\n" + _tags(tags) + "  </node>\n"))
        for e in d["elements"]:
            if e["type"] == "way":
                f.write(f'  <way id="{e["id"]}">\n')
                f.write("".join(f'    <nd ref="{n}"/>\n' for n in e["nodes"]))
                f.write(_tags(e.get("tags", {})) + "  </way>\n")
        f.write("</osm>\n")


def _tags(tags: dict) -> str:
    return "".join(f"    <tag k={quoteattr(str(k))} v={quoteattr(str(v))}/>\n" for k, v in tags.items())


def _hav_m(osm: Osm, p, q) -> float:
    (la1, lo1, _), (la2, lo2, _) = osm.nodes[p], osm.nodes[q]
    c = math.cos(math.radians((la1 + la2) / 2))
    return math.hypot((la2 - la1) * 111_195, (lo2 - lo1) * 111_195 * c)


def segment_paths(D: nx.DiGraph, table: dict, osm: Osm) -> tuple[dict, list]:
    """{segment id: [OSM node ids from s.a to s.b]} and the segments with no OSM chain (straight line used).

    A chain starts at a graph node, follows OSM nodes that are not graph nodes, and ends at the next graph
    node. Between the same two nodes the chain closest in length to the segment's length_m is used
    (parallel ways are merged in the graph, HANDOFF section 9.5)."""
    dn = set(D.nodes)
    chains: dict = {}
    for a in dn:
        for nb in osm.nbrs.get(a, ()):
            path, prev, cur = [a, nb], a, nb
            while cur not in dn:
                nxt = [n for n in osm.nbrs.get(cur, ()) if n != prev]
                if len(nxt) != 1 or len(path) > 10_000:
                    break
                prev, cur = cur, nxt[0]
                path.append(cur)
            if cur in dn and cur != a:
                chains.setdefault((a, cur), []).append(path)
    out, missing = {}, []
    for sid, s in table.items():
        cand = chains.get((s.a, s.b), [])
        target = s.template["length_m"]
        if cand:
            out[sid] = min(cand, key=lambda p: abs(sum(_hav_m(osm, x, y) for x, y in zip(p, p[1:])) - target))
        else:
            out[sid] = [s.a, s.b]
            missing.append(sid)
    return out, missing


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

@dataclass
class WayMap:
    way_of: dict = field(default_factory=dict)    # way id -> (a, b) of its segment (way runs a -> b)


def write_variant_osm(path: Path, D: nx.DiGraph, G: nx.DiGraph, table: dict, paths: dict, osm: Osm) -> WayMap:
    """One OSM way per segment, tagged with G's directions, lanes and speed (G = apply_config output)."""
    wm = WayMap()
    used: set = set()
    lines = []
    for wid, sid in enumerate(sorted(table, key=lambda k: tuple(sorted(k))), start=1):
        s = table[sid]
        ab, ba = G.has_edge(s.a, s.b), G.has_edge(s.b, s.a)
        if not (ab or ba):
            continue
        e = G.edges[s.a, s.b] if ab else G.edges[s.b, s.a]
        lanes = int(e["lanes"])
        tags = {"highway": s.highway, "maxspeed": f"{e['speed_kph']:.1f}"}
        if isinstance(s.name, str) and s.name:
            tags["name"] = s.name
        if ab and ba:
            tags.update({"oneway": "no", "lanes": str(2 * lanes), "lanes:forward": str(lanes),
                         "lanes:backward": str(lanes)})
        else:
            tags.update({"oneway": "yes" if ab else "-1", "lanes": str(lanes)})
        p = paths[sid]
        used.update(p)
        wm.way_of[wid] = (s.a, s.b)
        lines.append(f'  <way id="{wid}">\n' + "".join(f'    <nd ref="{n}"/>\n' for n in p) + _tags(tags) + "  </way>\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="chstraffic.sumo">\n')
        for n in sorted(used):
            if n in osm.nodes:
                la, lo, tg = osm.nodes[n]
            else:
                la, lo, tg = D.nodes[n]["y"], D.nodes[n]["x"], {}
            keep = {k: v for k, v in tg.items() if k in config.SUMO_OSM_NODE_TAGS
                    and (k != "highway" or v in config.SUMO_OSM_NODE_HIGHWAY)}
            head = f'  <node id="{n}" lat="{la}" lon="{lo}"'
            f.write(head + ("/>\n" if not keep else ">\n" + _tags(keep) + "  </node>\n"))
        f.writelines(lines)
        f.write("</osm>\n")
    return wm


def sumo_home() -> Path:
    try:
        import sumo  # the eclipse-sumo wheel
        return Path(sumo.SUMO_HOME)
    except ImportError:
        exe = shutil.which("sumo")
        if exe is None:
            raise RuntimeError("SUMO not found: pip install eclipse-sumo (see HANDOFF section 3)")
        return Path(exe).resolve().parents[1]


def binary(name: str) -> str:
    b = sumo_home() / "bin" / name
    for cand in (b, b.with_suffix(".exe")):
        if cand.exists():
            return str(cand)
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(f"SUMO binary {name} not found under {sumo_home()}")
    return found


def netconvert(osm_path: Path, net_path: Path, log_path: Path) -> None:
    cmd = [binary("netconvert"), "--osm-files", str(osm_path), "-o", str(net_path),
           "--log", str(log_path), *config.SUMO_NETCONVERT_OPTS]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"netconvert failed ({r.returncode}): {r.stderr[-2000:]}")


@dataclass
class Net:
    edges: dict           # sumo edge id -> (u, v) project edge
    junction_of: dict     # OSM node id -> sumo junction id
    n_junctions: int
    n_tls: int
    unmapped_edges: list


def read_net(net_path: Path, wm: WayMap, D: nx.DiGraph) -> Net:
    root = ET.parse(net_path).getroot()
    edges, unmapped = {}, []
    out_deg, in_deg = {}, {}
    for e in root.iter("edge"):
        if e.get("function") == "internal":
            continue
        eid = e.get("id")
        base = eid.split("-Added")[0]          # ramp lanes added by --ramps.guess keep their way id
        rev = base.startswith("-")
        try:
            wid = int(base.lstrip("-").split("#")[0])
            a, b = wm.way_of[wid]
            edges[eid] = (b, a) if rev else (a, b)
        except (ValueError, KeyError):
            unmapped.append(eid)
        out_deg[e.get("from")] = out_deg.get(e.get("from"), 0) + 1
        in_deg[e.get("to")] = in_deg.get(e.get("to"), 0) + 1
    junctions = {}
    for j in root.iter("junction"):
        if j.get("type") == "internal":
            continue
        junctions[j.get("id")] = (float(j.get("x")), float(j.get("y")))
    member: dict = {}
    for jid in junctions:
        if jid.startswith("cluster_"):
            for part in jid[len("cluster_"):].split("_"):
                if part.isdigit():
                    member[int(part)] = jid
        elif jid.lstrip("-").isdigit():
            member[int(jid)] = jid
    # nodes of the project graph that netconvert renamed beyond recognition: nearest junction in net coords
    loc = root.find("location")
    jo = {}
    missing = [n for n in D.nodes if n not in member]
    if missing:
        import sumolib  # noqa: F401  (needs SUMO_HOME/tools on sys.path)
        from sumolib.net import readNet
        snet = readNet(str(net_path))
        for n in missing:
            x, y = snet.convertLonLat2XY(D.nodes[n]["x"], D.nodes[n]["y"])
            best = min(junctions, key=lambda j: (junctions[j][0] - x) ** 2 + (junctions[j][1] - y) ** 2)
            jo[n] = best
    junction_of = {n: member[n] for n in D.nodes if n in member}
    junction_of.update(jo)
    n_tls = len({t.get("id") for t in root.iter("tlLogic")})
    del loc
    return Net(edges, junction_of, len(junctions), n_tls, unmapped)


def add_sumo_tools_to_path() -> None:
    import sys
    tools = sumo_home() / "tools"
    if str(tools) not in sys.path:
        sys.path.append(str(tools))


# ---------------------------------------------------------------------------
# Demand
# ---------------------------------------------------------------------------

def write_trips(path: Path, od: dict, net: Net, seed: int, scale: float = 1.0) -> dict:
    """Poisson vehicles per OD pair over warm-up + peak hour; returns counts for the log."""
    rng = np.random.default_rng(seed)
    horizon = config.SUMO_WARMUP_S + config.SUMO_PEAK_S
    keys = sorted(od, key=str)
    q = np.array([od[k] for k in keys]) * scale * horizon / 3600.0
    n = rng.poisson(q)
    trips, dropped = [], 0.0
    for (o, d), k in zip(keys, n):
        if k == 0:
            continue
        jo, jd = net.junction_of.get(o), net.junction_of.get(d)
        if jo is None or jd is None or jo == jd:
            dropped += k
            continue
        for t in rng.uniform(0, horizon, size=k):
            trips.append((float(t), jo, jd))
    trips.sort()
    with open(path, "w", encoding="utf-8") as f:
        f.write('<routes>\n  <vType id="car" vClass="passenger"/>\n')
        for i, (t, jo, jd) in enumerate(trips):
            f.write(f'  <trip id="{i}" type="car" depart="{t:.1f}" fromJunction="{jo}" toJunction="{jd}" '
                    f'departLane="best" departSpeed="max"/>\n')
        f.write("</routes>\n")
    return dict(vehicles=len(trips), dropped_same_junction=int(dropped), expected=float(q.sum()))


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def run(net_path: Path, trips_path: Path, out_dir: Path, sim_seed: int, meso: bool = True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    w, p = config.SUMO_WARMUP_S, config.SUMO_PEAK_S
    add = out_dir / "edgedata.add.xml"
    add.write_text(f'<additional>\n  <edgeData id="peak" file="edgedata.xml" begin="{w}" end="{w + p}" '
                   f'excludeEmpty="true"/>\n</additional>\n')
    cmd = [binary("sumo"), "-n", str(net_path), "-r", str(trips_path), "-a", str(add),
           "--junction-taz", "--seed", str(sim_seed),
           "--begin", "0", "--end", str(w + p + config.SUMO_DRAIN_S),
           "--time-to-teleport", str(config.SUMO_TELEPORT_S),
           "--device.rerouting.probability", "1",
           "--device.rerouting.period", str(config.SUMO_REROUTE_PERIOD_S),
           "--device.rerouting.adaptation-steps", str(config.SUMO_REROUTE_ADAPTATION_STEPS),
           "--routing-algorithm", "astar",
           "--tripinfo-output", str(out_dir / "tripinfo.xml"), "--tripinfo-output.write-unfinished",
           "--statistic-output", str(out_dir / "stats.xml"),
           "--no-step-log", "--duration-log.disable", "--log", str(out_dir / "sumo.log"),
           "--threads", "1", *config.SUMO_SIM_OPTS]
    if meso:
        cmd += ["--mesosim", *config.SUMO_MESO_OPTS]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"sumo failed ({r.returncode}): {r.stderr[-2000:]}")
    return parse_outputs(out_dir)


def parse_outputs(out_dir: Path) -> dict:
    w, p = config.SUMO_WARMUP_S, config.SUMO_PEAK_S
    tt, n, unfinished, tt_all = 0.0, 0, 0, 0.0
    for _, el in ET.iterparse(out_dir / "tripinfo.xml"):
        if el.tag != "tripinfo":
            continue
        dur, delay = float(el.get("duration")), float(el.get("departDelay"))
        planned = float(el.get("depart")) - delay
        tt_all += dur + delay
        if w <= planned < w + p:
            tt += dur + delay
            n += 1
            if float(el.get("arrival", -1)) < 0:
                unfinished += 1
        el.clear()
    st = ET.parse(out_dir / "stats.xml").getroot()
    veh, tel = st.find("vehicles"), st.find("teleports")
    edges = {}
    for _, el in ET.iterparse(out_dir / "edgedata.xml"):
        if el.tag == "edge":
            edges[el.get("id")] = float(el.get("entered", 0) or 0)
            el.clear()
    return dict(tstt_h=tt / 3600.0, vehicles_peak=n, unfinished_peak=unfinished, tstt_all_h=tt_all / 3600.0,
                loaded=int(veh.get("loaded")), inserted=int(veh.get("inserted")), running=int(veh.get("running")),
                waiting=int(veh.get("waiting")),
                teleports=int(tel.get("total")), teleports_jam=int(tel.get("jam")),
                teleports_yield=int(tel.get("yield")), teleports_wronglane=int(tel.get("wrongLane")),
                edge_entered=edges)


def project_flows(edge_entered: dict, net: Net, edge_list: list) -> np.ndarray:
    """Vehicles entering each project edge in the peak hour: mean over the SUMO edges it was split into."""
    acc: dict = {}
    for eid, uv in net.edges.items():
        acc.setdefault(uv, []).append(edge_entered.get(eid, 0.0))
    return np.array([float(np.mean(acc[e])) if e in acc else np.nan for e in edge_list])


def fill_uncovered(flows: np.ndarray, edge_list: list, G: nx.DiGraph, passes: int = 3) -> tuple[np.ndarray, int]:
    """Project edges with no SUMO edge (short pieces netconvert folded into a joined junction) take the mean
    flow of the adjacent edges on the same street in the same direction: inside a junction they carry the
    same through traffic. Returns the filled array and how many edges stay empty."""
    f = flows.copy()
    idx = {e: k for k, e in enumerate(edge_list)}
    for _ in range(passes):
        missing = np.where(np.isnan(f[..., :] if f.ndim == 1 else f[0]))[0]
        if not len(missing):
            break
        for k in missing:
            u, v = edge_list[k]
            name = G.edges[u, v].get("name")
            nb = [idx[(v, w)] for w in G.successors(v) if w != u and G.edges[v, w].get("name") == name]
            nb += [idx[(t, u)] for t in G.predecessors(u) if t != v and G.edges[t, u].get("name") == name]
            vals = [f[..., j] for j in nb if not np.isnan(f[..., j]).any()]
            if vals:
                f[..., k] = np.mean(vals, axis=0)
    return f, int(np.isnan(f if f.ndim == 1 else f[0]).sum())
