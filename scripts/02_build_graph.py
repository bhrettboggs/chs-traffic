"""Build the weighted directed graph from the downloaded OSM network.

    python scripts/02_build_graph.py

Reads  data/raw/chs_peninsula_drive.graphml
Writes data/processed/chs_digraph.gpickle   (networkx DiGraph, pickled)
       data/processed/edges.csv             (one row per directed edge)
       prints a summary (one-way vs two-way segment counts, connectivity)
"""

import pickle
import sys
from pathlib import Path

import osmnx as ox
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic.graph import build_digraph, summarize  # noqa: E402

RAW = ROOT / "data" / "raw" / "chs_peninsula_drive.graphml"
OUT = ROOT / "data" / "processed"


def main() -> None:
    if not RAW.exists():
        sys.exit(f"Missing {RAW}. Run scripts/01_fetch_osm.py first.")
    G = ox.load_graphml(RAW)
    D = build_digraph(G)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "chs_digraph.gpickle", "wb") as f:
        pickle.dump(D, f)
    rows = [{"u": u, "v": v, **{k: val for k, val in d.items() if k != "segment_id"}}
            for u, v, d in D.edges(data=True)]
    pd.DataFrame(rows).to_csv(OUT / "edges.csv", index=False)
    for k, v in summarize(D).items():
        print(f"{k:>20}: {v}")


if __name__ == "__main__":
    main()
