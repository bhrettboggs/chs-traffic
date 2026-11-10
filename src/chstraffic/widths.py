"""Join City of Charleston curb-to-curb widths to graph segments.

Data: data/raw/chs_city_pavement_2024.geojson, from Charleston County GIS layer
Public_Works/Pavement_Condition_2024 (the city's pavement inventory). CHSC_WIDTH is
curb-to-curb width in feet. Its NUMBER_OF_ lane field seems to count parking lanes,
so lanes are derived from width with the rule in config.
"""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform
from shapely.strtree import STRtree

from . import config

_ABBR = {"AVENUE": "AV", "AVE": "AV", "STREET": "ST", "BOULEVARD": "BLVD", "DRIVE": "DR", "LANE": "LN",
         "ROAD": "RD", "PLACE": "PL", "COURT": "CT", "ALLEY": "ALY", "EAST": "E", "WEST": "W",
         "NORTH": "N", "SOUTH": "S", "PARKWAY": "PKWY", "EXTENSION": "EXT", "TERRACE": "TER"}


def norm_name(name) -> str:
    s = str(name or "").upper().replace(".", " ")
    s = re.sub(r"\(.*", "", s)                 # city names carry "(FROM - TO)"
    s = re.sub(r"MGMT SECTNO.*", "", s)
    words = s.split()
    if words and words[0] == "ST" and len(words) > 2:   # "St. Philip Street" -> SAINT PHILIP ST
        words[0] = "SAINT"
    return " ".join(_ABBR.get(w, w) for w in words)


def lanes_from_width(width_ft: float) -> int:
    parking = 2 * config.PARKING_LANE_FT if width_ft >= config.BOTH_SIDE_PARKING_MIN_FT else config.PARKING_LANE_FT
    return max(1, int((width_ft - parking) // config.LANE_WIDTH_FT))


def join(D: nx.DiGraph, geojson_path: Path | str) -> dict:
    """Return {segment_id: dict(width_ft, lanes, section, dist_m)} for matched segments."""
    fc = json.loads(Path(geojson_path).read_text())
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True).transform
    lines, props = [], []
    for f in fc["features"]:
        if not f.get("geometry") or not f["properties"].get("CHSC_WIDTH"):
            continue
        lines.append(transform(to_m, shape(f["geometry"])))
        props.append(f["properties"])
    tree = STRtree(lines)
    names = [norm_name(p["PMS_SECTIO"]) for p in props]

    out = {}
    seen = set()
    for u, v, d in D.edges(data=True):
        sid = d["segment_id"]
        if sid in seen or len(sid) < 2:
            continue
        seen.add(sid)
        nm = norm_name(d.get("name"))
        if not nm:
            continue
        seg = LineString([to_m(D.nodes[u]["x"], D.nodes[u]["y"]), to_m(D.nodes[v]["x"], D.nodes[v]["y"])])
        votes = {}
        for frac in (0.25, 0.5, 0.75):
            p = seg.interpolate(frac, normalized=True)
            for i in tree.query(p.buffer(config.WIDTH_MATCH_MAX_M)):
                if names[i] == nm:
                    dist = lines[i].distance(p)
                    if dist <= config.WIDTH_MATCH_MAX_M:
                        best = votes.get(i)
                        votes[i] = (best[0] + 1, min(best[1], dist)) if best else (1, dist)
        if not votes:
            continue
        i, (n, dist) = max(votes.items(), key=lambda kv: (kv[1][0], -kv[1][1]))
        if n < 2:   # must match at least 2 of the 3 sample points
            continue
        w = float(props[i]["CHSC_WIDTH"])
        out[sid] = dict(width_ft=w, lanes=lanes_from_width(w),
                        section=re.sub(r"\s+", " ", props[i]["PMS_SECTIO"].split("Mgmt")[0]).strip(),
                        dist_m=round(dist, 1))
    return out


def save(widths: dict, D: nx.DiGraph, path: Path | str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["u", "v", "name", "width_ft", "lanes_from_width", "section", "dist_m"])
        for sid, r in widths.items():
            a, b = sorted(sid, key=str)
            name = D.edges[a, b]["name"] if D.has_edge(a, b) else D.edges[b, a]["name"]
            w.writerow([a, b, name, r["width_ft"], r["lanes"], r["section"], r["dist_m"]])


def load(path: Path | str) -> dict:
    """{frozenset((u, v)): lanes} from save()'s CSV. Node ids are read as int where possible."""
    path = Path(path)
    if not path.exists():
        return {}
    def nid(x):
        try:
            return int(x)
        except ValueError:
            return x
    with open(path, newline="", encoding="utf-8") as f:
        return {frozenset((nid(r["u"]), nid(r["v"]))): int(r["lanes_from_width"]) for r in csv.DictReader(f)}
