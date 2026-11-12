"""Check OSM one-way directions against a second source: the Charleston County street centerlines.

Data: data/raw/chs_county_streets_oneway.geojson, from Charleston County GIS layer
Public_Works/General_PW_Viewer_Map/MapServer/138 (Streets). Its ONE_WAY field is
B = both directions, FT = one-way in the line's digitized direction (from -> to),
TF = one-way against it, N = no travel.

Join: the same name-plus-distance rule as the width join (widths.point_matches): three
sample points per segment, nearest same-name county line within WIDTH_MATCH_MAX_M.
Each matched point gives a county state for the segment (two / ab / ba); the segment's
county state is the one at least 2 of the 3 points agree on.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import networkx as nx
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

from . import config, widths

# A matched county line must run within this angle of the segment to say anything about its
# direction (cos 45 deg); a point near an intersection can snap to a crossing piece of the same name.
MIN_ALIGN_COS = math.cos(math.radians(45))


def compass(D: nx.DiGraph, u, v) -> str:
    """8-point compass heading of travel u -> v."""
    dy = D.nodes[v]["y"] - D.nodes[u]["y"]
    dx = (D.nodes[v]["x"] - D.nodes[u]["x"]) * math.cos(math.radians(D.nodes[u]["y"]))
    ang = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((ang + 22.5) // 45) % 8]


def state_dir(D, a, b, state) -> str:
    if state == "two":
        return "two-way"
    if state in ("ab", "ba"):
        u, v = (a, b) if state == "ab" else (b, a)
        return compass(D, u, v)
    return ""


def osm_states(D: nx.DiGraph) -> dict:
    """{segment_id: 'two' | 'ab' | 'ba'} as OSM has it, (a, b) = canonical order (sorted by str)."""
    have: dict = {}
    for u, v, d in D.edges(data=True):
        have.setdefault(d["segment_id"], set()).add((u, v))
    out = {}
    for sid, es in have.items():
        if len(sid) < 2:
            continue
        a, b = sorted(sid, key=str)
        out[sid] = "two" if len(es) == 2 else ("ab" if (a, b) in es else "ba")
    return out


def load_county(path: Path | str):
    fc = json.loads(Path(path).read_text())
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True).transform
    lines, props = [], []
    for f in fc["features"]:
        if not f.get("geometry"):
            continue
        lines.append(transform(to_m, shape(f["geometry"])))
        props.append(f["properties"])
    names = [widths.norm_name(p.get("FULL_NAME")) for p in props]
    return lines, props, names


def _point_state(line, value, p, seg_vec):
    """County state at sample point p, relative to the segment's canonical a -> b direction."""
    if value == "B":
        return "two"
    if value not in ("FT", "TF"):
        return value or "?"          # 'N' (no travel) or blank
    s = line.project(p)
    p0, p1 = line.interpolate(max(s - 2.0, 0.0)), line.interpolate(min(s + 2.0, line.length))
    tx, ty = p1.x - p0.x, p1.y - p0.y
    nt, ns = math.hypot(tx, ty), math.hypot(*seg_vec)
    if nt == 0 or ns == 0:
        return None
    cos = (tx * seg_vec[0] + ty * seg_vec[1]) / (nt * ns)
    if abs(cos) < MIN_ALIGN_COS:
        return None
    along = cos > 0
    if value == "TF":
        along = not along
    return "ab" if along else "ba"


def compare(D: nx.DiGraph, county_path: Path | str, model_states: dict | None = None) -> list[dict]:
    """One row per OSM segment with a street name: OSM state, county state, and the verdict.

    model_states: {segment_id: state} of today's network after overrides.csv, reported alongside
    so a rerun shows which disagreements an override has already resolved.
    """
    lines, props, names = load_county(county_path)
    osm = osm_states(D)
    rows = []
    for sid, (a, b), seg, hits in widths.point_matches(D, lines, names):
        seg_vec = (seg.coords[1][0] - seg.coords[0][0], seg.coords[1][1] - seg.coords[0][1])
        states, ids, vals, dists = [], [], [], []
        for p, near in hits:
            if not near:
                continue
            i, dist = min(near, key=lambda t: t[1])
            st = _point_state(lines[i], props[i].get("ONE_WAY"), p, seg_vec)
            if st is None:
                continue
            states.append(st)
            ids.append(props[i].get("OBJECTID"))
            vals.append(props[i].get("ONE_WAY"))
            dists.append(dist)
        d0 = D.edges[a, b] if D.has_edge(a, b) else D.edges[b, a]
        o = osm.get(sid)
        row = dict(a=a, b=b, name=d0.get("name"), highway=d0.get("highway"), osmid=d0.get("osmid"),
                   length_m=round(d0.get("length_m", 0.0), 1),
                   osm_state=o, osm_dir=state_dir(D, a, b, o),
                   county_value="", county_state="", county_dir="", county_objectids="", match_dist_m="",
                   points_matched=len(states), result="no match", note="")
        if len(states) < 2:
            row["note"] = "fewer than 2 of 3 points matched a same-name county line"
            rows.append(row)
            continue
        (cs, n), = Counter(states).most_common(1)
        row.update(county_objectids=";".join(str(x) for x in dict.fromkeys(ids)),
                   county_value=";".join(dict.fromkeys(vals)), match_dist_m=round(max(dists), 1))
        if n < 2:
            row["note"] = f"county states disagree along the segment ({','.join(states)})"
            rows.append(row)
            continue
        if cs not in ("two", "ab", "ba"):
            row.update(county_state=cs, result="disagree", note=f"county ONE_WAY={cs}")
            rows.append(row)
            continue
        row.update(county_state=cs, county_dir=state_dir(D, a, b, cs),
                   result="agree" if cs == o else "disagree")
        rows.append(row)
    if model_states is not None:
        for r in rows:
            sid = frozenset((r["a"], r["b"]))
            ms = model_states.get(sid)
            r["model_state"], r["model_dir"] = ms, state_dir(D, r["a"], r["b"], ms)
    return rows


def mark_divided(D: nx.DiGraph, rows: list[dict], max_m: float = 40.0) -> int:
    """Re-label disagreements that are only a drawing difference on divided roads.

    OSM draws each carriageway of a divided road as its own one-way; the county often draws one
    centerline ('B') or only one carriageway. A disagreement is a drawing difference when the OSM
    segment is one-way, a same-name OSM one-way running the opposite way lies within max_m, and the
    county says either two-way or the partner's direction. Those rows become result 'agree' with
    note 'divided road ...'. Returns how many rows were re-labelled.
    """
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True).transform
    osm = osm_states(D)
    by_name: dict = {}
    for sid, st in osm.items():
        if st == "two":
            continue
        a, b = sorted(sid, key=str)
        u, v = (a, b) if st == "ab" else (b, a)
        nm = D.edges[u, v].get("name")
        if nm:
            by_name.setdefault(nm, []).append((sid, widths.segment_line(D, u, v, to_m)))

    def partner(sid, name):
        mine = [ln for s, ln in by_name.get(name, []) if s == sid]
        if not mine:
            return None
        (x0, y0), (x1, y1) = mine[0].coords
        best = None
        for s, ln in by_name[name]:
            if s == sid:
                continue
            (p0, q0), (p1, q1) = ln.coords
            n = math.hypot(x1 - x0, y1 - y0) * math.hypot(p1 - p0, q1 - q0)
            if n == 0 or ((x1 - x0) * (p1 - p0) + (y1 - y0) * (q1 - q0)) / n > -0.7:
                continue
            dist = mine[0].distance(ln)
            if dist <= max_m and (best is None or dist < best[1]):
                best = (s, dist)
        return best

    n = 0
    for r in rows:
        if r["result"] != "disagree" or r["osm_state"] not in ("ab", "ba"):
            continue
        p = partner(frozenset((r["a"], r["b"])), r["name"])
        if p is None:
            continue
        partner_state = "ba" if r["osm_state"] == "ab" else "ab"
        if r["county_state"] in ("two", partner_state):
            r["result"] = "agree"
            r["note"] = (f"divided road: OSM maps each carriageway as a one-way (opposite carriageway "
                         f"{round(p[1])} m away); county draws "
                         + ("one two-way centerline" if r["county_state"] == "two" else "the other carriageway"))
            n += 1
    return n
