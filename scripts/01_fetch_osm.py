"""Download the downtown Charleston drivable street network from OpenStreetMap.

Run from the repo root on a machine with normal internet access:

    python scripts/01_fetch_osm.py

Writes:
    data/raw/chs_peninsula_drive.graphml   (osmnx MultiDiGraph, all OSM tags kept)
    data/raw/chs_peninsula_edges.geojson   (for eyeballing in QGIS / geojson.io)
    data/raw/FETCHED_AT.txt                (timestamp + osmnx version, for reproducibility)

If Overpass is down or rate-limiting you (HTTP 429/504), wait and retry, or use
the offline fallback:
    1. openstreetmap.org -> Export -> "Manually select a different area" ->
       draw the peninsula box -> Export (or use the Overpass API link it offers)
    2. save as data/raw/chs_peninsula.osm
    3. python scripts/01_fetch_osm.py --from-xml data/raw/chs_peninsula.osm
"""

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

import osmnx as ox
import requests
from osmnx._errors import ResponseStatusCodeError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config  # noqa: E402

RAW = ROOT / "data" / "raw"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-xml", type=Path, help="build from a local .osm file instead of Overpass")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.log_console = True
    # keep the tags the graph builder needs
    ox.settings.useful_tags_way = list(set(ox.settings.useful_tags_way) | {
        "oneway", "lanes", "lanes:forward", "lanes:backward", "maxspeed",
        "turn:lanes", "access", "junction", "ref"})
    ox.settings.useful_tags_node = list(set(ox.settings.useful_tags_node) | {"highway"})

    source = "local xml"
    if args.from_xml:
        G = ox.graph_from_xml(args.from_xml, simplify=True, retain_all=False)
        left, bottom, right, top = config.BBOX
        G = ox.truncate.truncate_graph_bbox(G, (left, bottom, right, top))
    else:
        G, source = fetch_with_fallback()

    ox.save_graphml(G, RAW / "chs_peninsula_drive.graphml")
    _, edges = ox.graph_to_gdfs(G)
    edges.reset_index().astype({c: str for c in edges.columns if c != "geometry"}) \
        .to_file(RAW / "chs_peninsula_edges.geojson", driver="GeoJSON")
    (RAW / "FETCHED_AT.txt").write_text(
        f"{dt.datetime.now().isoformat()}  osmnx {ox.__version__}  bbox {config.BBOX}  source {source}\n")
    print(f"nodes={G.number_of_nodes()} edges={G.number_of_edges()} -> {RAW}")


def fetch_with_fallback():
    """Try each Overpass server in config.OVERPASS_URLS with exponential backoff."""
    errors = []
    for url in config.OVERPASS_URLS:
        ox.settings.overpass_url = url
        wait = config.OVERPASS_BACKOFF_S
        for attempt in range(1, config.OVERPASS_RETRIES + 1):
            try:
                G = ox.graph_from_bbox(config.BBOX, custom_filter=config.OVERPASS_FILTER,
                                       simplify=True, retain_all=False)
                print(f"fetched from {url} (attempt {attempt})")
                return G, url
            except (ResponseStatusCodeError, requests.RequestException) as e:
                first = str(e).splitlines()[0][:120]
                errors.append(f"{url} attempt {attempt}: {first}")
                print(f"[{url}] attempt {attempt} failed: {first}")
                if attempt < config.OVERPASS_RETRIES:
                    print(f"  waiting {wait}s")
                    time.sleep(wait)
                    wait *= 2
    sys.exit("All Overpass servers failed:\n  " + "\n  ".join(errors)
             + "\nUse the --from-xml fallback (see docstring).")


if __name__ == "__main__":
    main()
