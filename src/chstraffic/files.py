"""Input files that are not in git: fail early with a message that says how to get them."""

from __future__ import annotations

import pickle
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[2]

GRAPH_HINT = "run `python scripts/02_build_graph.py` (and then `python scripts/05_join_widths.py`) first"
NETS_HINT = ("run `python scripts/14_sumo_check.py nets` first (the SUMO networks are not in git; "
             "install requirements-sumo.txt)")
LODES_HINT = ("the Census LODES files are not in git (17.5 MB): download the five files listed in "
              "data/raw/README.md from https://lehd.ces.census.gov/data/lodes/LODES8/sc/ into data/raw/lodes/. "
              "Only scripts/06_build_zones.py needs them; the zone tables built from them are in data/reference/")


def require(path: Path | str, hint: str) -> Path:
    """Return path if it exists, else stop with a readable message instead of a traceback."""
    path = Path(path)
    if not path.exists():
        try:
            shown = path.resolve().relative_to(ROOT)
        except ValueError:
            shown = path
        raise SystemExit(f"missing input: {shown}\n  {hint}")
    return path


def load_graph(path: Path | str | None = None) -> nx.DiGraph:
    """The pickled street graph written by scripts/02_build_graph.py."""
    path = Path(path) if path is not None else ROOT / "data" / "processed" / "chs_digraph.gpickle"
    return pickle.loads(require(path, GRAPH_HINT).read_bytes())
