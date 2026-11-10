"""Join City of Charleston curb-to-curb widths to every graph segment.

    python scripts/05_join_widths.py

Reads  data/processed/chs_digraph.gpickle, data/raw/chs_city_pavement_2024.geojson
Writes data/processed/segment_widths.csv (used by 03/04 for segments with no OSM lanes tag)
Prints coverage, and how often the width rule agrees with explicit OSM lanes tags.
"""

import collections
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, widths  # noqa: E402


def main() -> None:
    D = pickle.loads((ROOT / "data" / "processed" / "chs_digraph.gpickle").read_bytes())
    W = widths.join(D, ROOT / "data" / "raw" / "chs_city_pavement_2024.geojson")
    widths.save(W, D, ROOT / "data" / "processed" / "segment_widths.csv")

    segs = {}
    for u, v, d in D.edges(data=True):
        segs.setdefault(d["segment_id"], []).append(d)
    grid = {s: es for s, es in segs.items() if es[0]["highway"] not in config.FROZEN_HIGHWAYS and len(s) == 2}
    untagged = {s for s, es in grid.items() if not es[0].get("lanes_tagged", True)}
    print(f"street segments (non-freeway): {len(grid)}, with a city width: {sum(s in W for s in grid)}, "
          f"untagged in OSM: {len(untagged)}, of those with a city width: {sum(s in W for s in untagged)}")
    agree = collections.Counter()
    for s, es in grid.items():
        if s in W and es[0].get("lanes_tagged", True):
            osm_total = sum(d["lanes"] for d in es)
            agree[(osm_total, W[s]["lanes"])] += 1
    n = sum(agree.values())
    same = sum(c for (a, b), c in agree.items() if a == b)
    print(f"explicit OSM tag vs width rule: {same}/{n} agree ({same / max(n, 1):.0%}); (osm, width) counts:")
    for k, c in sorted(agree.items(), key=lambda kv: -kv[1])[:10]:
        print(f"   {k}: {c}")
    print(f"wrote {ROOT / 'data' / 'processed' / 'segment_widths.csv'}")


if __name__ == "__main__":
    main()
